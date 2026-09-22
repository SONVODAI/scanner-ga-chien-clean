"""One-time copy of the Streamlit forward-ledger cache onto GitHub Contents.

Upload a file only when that GitHub object is absent. Validate the required
columns, then verify the read-back row count and sha256. Rows are not merged
and an existing non-empty GitHub file is not overwritten.

Statuses: ``MIGRATED``, ``ALREADY_EXISTS``, ``NO_LOCAL_HISTORY``, or ``FAILED``.
``ready`` is true only when every ledger is in the first three and the report
itself was written to GitHub.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from modules.forward_ledger_store import (
    FORWARD_LEDGER_NAMES,
    MIGRATION_REPORT_NAME,
    MIGRATION_REPORT_SCHEMA,
    brain_dir,
    migration_report_path,
    report_marks_ready,
)

REQUIRED_COLUMNS = ("session_date", "symbol", "evaluation_mode")
SAFE_STATUSES = {"MIGRATED", "ALREADY_EXISTS", "NO_LOCAL_HISTORY"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _inspect(text: str) -> dict[str, Any]:
    digest = _sha256(text)
    header = text.splitlines()[0] if text.splitlines() else ""
    schema_sha = _sha256(header)
    if not text.strip():
        return {
            "schema_ok": False,
            "reason": "EMPTY",
            "sha256": digest,
            "schema_sha256": schema_sha,
            "row_count": 0,
            "columns": [],
            "date_min": None,
            "date_max": None,
        }
    try:
        frame = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        return {
            "schema_ok": False,
            "reason": f"CSV_PARSE:{type(exc).__name__}",
            "sha256": digest,
            "schema_sha256": schema_sha,
            "row_count": 0,
            "columns": [],
            "date_min": None,
            "date_max": None,
        }
    columns = [str(column) for column in frame.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    dates: list[str] = []
    if "session_date" in frame.columns:
        for value in frame["session_date"].tolist():
            text_value = str(value).strip()
            if text_value and text_value.lower() != "nan":
                dates.append(text_value)
    return {
        "schema_ok": not missing,
        "reason": None if not missing else "SCHEMA:" + ",".join(missing),
        "sha256": digest,
        "schema_sha256": schema_sha,
        "row_count": int(len(frame)),
        "columns": columns,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
    }


def _public(info: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = {
        "row_count": info.get("row_count", 0),
        "sha256": info.get("sha256"),
        "schema_sha256": info.get("schema_sha256"),
        "columns": list(info.get("columns") or []),
        "date_min": info.get("date_min"),
        "date_max": info.get("date_max"),
    }
    out.update(extra)
    return out


def _migrate_one(name: str, store: Any) -> dict[str, Any]:
    path = brain_dir() / name
    if path.is_file():
        local_text = path.read_text(encoding="utf-8-sig")
    else:
        local_text = ""
    local = _inspect(local_text)
    try:
        remote_payload = store._github_read(name)
    except Exception as exc:
        return _public(
            local,
            status="FAILED",
            reason=f"GITHUB_READ:{type(exc).__name__}",
        )

    remote = _inspect(remote_payload.text) if remote_payload is not None else None
    if remote is not None and remote["row_count"] > 0:
        same = local["sha256"] == remote["sha256"] and local["row_count"] > 0
        if local["row_count"] > 0 and not same:
            return _public(
                remote,
                status="FAILED",
                reason="REMOTE_CONFLICT",
                local_row_count=local["row_count"],
                local_sha256=local["sha256"],
                bytes_match=False,
            )
        return _public(
            remote,
            status="ALREADY_EXISTS",
            local_row_count=local["row_count"],
            local_sha256=local["sha256"],
            bytes_match=local["sha256"] == remote["sha256"],
        )

    if remote is not None and local["row_count"] > 0:
        return _public(
            local,
            status="FAILED",
            reason="REMOTE_EXISTS_EMPTY",
        )

    if local["row_count"] <= 0:
        return _public(local, status="NO_LOCAL_HISTORY")

    if not local["schema_ok"]:
        return _public(local, status="FAILED", reason=local["reason"])

    try:
        store._github_write(
            name,
            local_text,
            f"Migrate forward ledger {name} from Streamlit cache",
        )
        readback = store._github_read(name)
    except Exception as exc:
        return _public(local, status="FAILED", reason=f"GITHUB_WRITE:{type(exc).__name__}")

    if readback is None:
        return _public(local, status="FAILED", reason="READBACK_MISSING")
    verified = _inspect(readback.text)
    if verified["sha256"] != local["sha256"] or verified["row_count"] != local["row_count"]:
        return _public(
            local,
            status="FAILED",
            reason="READBACK_MISMATCH",
            readback_sha256=verified["sha256"],
            readback_row_count=verified["row_count"],
        )
    return _public(verified, status="MIGRATED", bytes_match=True)


def migrate_forward_ledgers(*, storage: Any = None) -> dict[str, Any]:
    """Copy the three cache files. Safe to run again; it will not overwrite."""
    if storage is None:
        from modules.forward_ledger_store import _storage_for

        storage = _storage_for(brain_dir() / FORWARD_LEDGER_NAMES[0])

    ledgers: dict[str, Any] = {}
    if not getattr(getattr(storage, "github", None), "enabled", False):
        for name in FORWARD_LEDGER_NAMES:
            ledgers[name] = {"status": "FAILED", "reason": "GITHUB_DISABLED"}
        report = _report(ledgers, ready=False, report_status="GITHUB_DISABLED")
        _write_local(report)
        return report

    for name in FORWARD_LEDGER_NAMES:
        ledgers[name] = _migrate_one(name, storage)

    ready = all(item.get("status") in SAFE_STATUSES for item in ledgers.values())
    report = _report(ledgers, ready=ready, report_status="PENDING")
    if ready:
        try:
            text = json.dumps(report, ensure_ascii=False, indent=2)
            storage._github_write(
                MIGRATION_REPORT_NAME,
                text,
                "Record forward ledger migration readiness",
            )
            readback = storage._github_read(MIGRATION_REPORT_NAME)
            if readback is None or not report_marks_ready(readback.text):
                report["ready"] = False
                report["report_status"] = "FAILED"
                report["reason"] = "REPORT_READBACK"
            else:
                report["report_status"] = "RECORDED"
        except Exception as exc:
            report["ready"] = False
            report["report_status"] = "FAILED"
            report["reason"] = f"REPORT_WRITE:{type(exc).__name__}"
    else:
        report["report_status"] = "NOT_READY"
    _write_local(report)
    return report


def _report(ledgers: dict[str, Any], *, ready: bool, report_status: str) -> dict[str, Any]:
    return {
        "schema": MIGRATION_REPORT_SCHEMA,
        "ready": ready,
        "report_status": report_status,
        "migrated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ledgers": ledgers,
    }


def _write_local(report: dict[str, Any]) -> None:
    path = migration_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
