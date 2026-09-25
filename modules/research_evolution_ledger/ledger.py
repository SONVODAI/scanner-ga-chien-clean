"""Append-only Evolution Observer ledger. Research collection only.

Copies fields already present on the production scan frame. Does not call a
market-data provider, re-score, or read market-context JSONL.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from market_snapshot import market_session_slot
from modules.live_candidate.calendar import as_vn
from modules.research_evolution_ledger.contract import (
    BOOL_FIELDS,
    LEDGER_NAME,
    OBSERVED_FIELDS,
    PROVENANCE_FIELDS,
    STATUS_OK,
    TEXT_FIELDS,
)
from modules.research_market_context.market_context import scan_fingerprint
from modules.research_market_context.previous_close import append_json_line

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "research" / "evolution_history"
ENV_DIR = "MRBOT_EVOLUTION_LEDGER_DIR"


def ledger_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_DIR, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DIR


def ledger_path(directory: Path | None = None) -> Path:
    return ledger_dir(directory) / LEDGER_NAME


def _json_number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    rounded = round(number)
    if number == rounded and abs(rounded) < 10**15:
        return int(rounded)
    return number


def _json_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>", "nat"}:
        return None
    return text


def _json_bool(value: object) -> bool | None:
    if value is None:
        return None
    try:
        if not isinstance(value, (bool, str, int)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return bool(value)
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "<na>"}:
        return None
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _observed_value(record: dict[str, Any], column: str) -> Any:
    if column not in record:
        return None
    raw = record[column]
    if column in TEXT_FIELDS:
        return _json_text(raw)
    if column in BOOL_FIELDS:
        return _json_bool(raw)
    return _json_number(raw)


def _observed_state(record: dict[str, Any]) -> dict[str, Any]:
    return {column: _observed_value(record, column) for column in OBSERVED_FIELDS}


def state_hash(observed: dict[str, Any]) -> str:
    """Hash of observed fields only. Provenance is not part of the hash."""
    payload = json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _symbol(value: object) -> str:
    text = _json_text(value)
    return "" if text is None else text.upper()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _row_state_hash(row: dict[str, Any]) -> str:
    stored = str(row.get("state_hash") or "").strip()
    if stored:
        return stored
    observed = {column: row.get(column) for column in OBSERVED_FIELDS}
    return state_hash(observed)


def _last_hashes(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    found: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = (
            str(row.get("trade_date") or ""),
            str(row.get("source") or ""),
            _symbol(row.get("symbol")),
        )
        if not key[0] or not key[1] or not key[2]:
            continue
        found[key] = _row_state_hash(row)
    return found


def load_evolution_ledger(path: Path) -> list[dict[str, Any]]:
    return _read_rows(path)


def append_evolution_ledger(
    *,
    trade_date: date | str,
    source: str,
    scan_df: pd.DataFrame | None,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one row per symbol whose observed state changed.

    Identical ``(trade_date, source, symbol)`` state is skipped. Prior rows
    are never rewritten. ``close_scan`` is a different source from
    ``streamlit_scan``, so its first row is kept even when the state matches.
    """
    day = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)[:10]
    src = str(source or "").strip()
    if not day or not src:
        raise ValueError("trade_date and source are required")

    now = as_vn(captured_at or datetime.now())
    slot = market_session_slot(now)
    dest = Path(path) if path is not None else ledger_path()
    fingerprint = scan_fingerprint(scan_df if isinstance(scan_df, pd.DataFrame) else None)

    if scan_df is None or not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return {
            "ok": True,
            "written": False,
            "appended": 0,
            "skipped": 0,
            "reason": "empty_scan",
            "scan_fingerprint": fingerprint,
        }
    if "symbol" not in scan_df.columns:
        return {
            "ok": True,
            "written": False,
            "appended": 0,
            "skipped": 0,
            "reason": "no_symbol_column",
            "scan_fingerprint": fingerprint,
        }

    present = set(scan_df.columns)
    records = scan_df.to_dict("records")
    last = _last_hashes(_read_rows(dest) if dest.exists() else [])
    appended = 0
    skipped = 0

    for record in records:
        symbol = _symbol(record.get("symbol"))
        if not symbol:
            skipped += 1
            continue
        observed = {
            column: (_observed_value(record, column) if column in present else None)
            for column in OBSERVED_FIELDS
        }
        digest = state_hash(observed)
        key = (day, src, symbol)
        if last.get(key) == digest:
            skipped += 1
            continue
        row = {
            "trade_date": day,
            "captured_at": now.isoformat(),
            "session_slot": slot,
            "symbol": symbol,
            "source": src,
            "status": STATUS_OK,
            "scan_fingerprint": fingerprint,
            "state_hash": digest,
        }
        row.update(observed)
        ordered = {name: row[name] for name in (*PROVENANCE_FIELDS, *OBSERVED_FIELDS)}
        append_json_line(dest, ordered)
        last[key] = digest
        appended += 1

    return {
        "ok": True,
        "written": appended > 0,
        "appended": appended,
        "skipped": skipped,
        "reason": "appended" if appended else "unchanged",
        "scan_fingerprint": fingerprint,
    }


def try_append_evolution_ledger(
    *,
    trade_date: date | str,
    source: str,
    scan_df: pd.DataFrame | None,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Fail-open. A research write error does not propagate."""
    try:
        return append_evolution_ledger(
            trade_date=trade_date,
            source=source,
            scan_df=scan_df,
            captured_at=captured_at,
            path=path,
        )
    except Exception as exc:  # noqa: BLE001 — research retention must not stop the scan
        return {
            "ok": False,
            "written": False,
            "appended": 0,
            "skipped": 0,
            "reason": "write_failed",
            "error": type(exc).__name__,
        }
