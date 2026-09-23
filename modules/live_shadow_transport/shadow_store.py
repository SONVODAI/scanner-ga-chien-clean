"""Copy minimum live-shadow UI artifacts into the isolated VPS store.

Never writes /var/lib/mrbot/intraday_memory. Never writes Edge bundle.tar.gz.
Elite live_evidence.jsonl + live_shadow_status.json stay required.
V2 SHADOW state is optional: missing V2 must not fail Elite publication.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from modules.live_shadow_transport.contract import (
    ENV_SHADOW_STORE,
    EVIDENCE_NAME,
    EVIDENCE_TRANSPORT_ERROR,
    FORBIDDEN_CAMERA_ARCHIVE,
    STATUS_NAME,
    V2_ACTION_EVIDENCE_NAME,
    V2_ACTION_STATE_NAME,
    V2_ACTION_SUBDIR,
    VPS_SHADOW_STORE,
)

ALLOWED_SHADOW_FILES = (EVIDENCE_NAME, STATUS_NAME)


def default_shadow_store() -> Path:
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return Path(VPS_SHADOW_STORE)


def resolve_shadow_store(explicit: Path | None = None) -> Path | None:
    """Only auto-use the VPS default when env is set or a path is injected.

    Unit tests without env skip the copy so they never touch /var/lib/mrbot.
    The --live runner passes the isolated default explicitly.
    """
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return None


def _atomic_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(src.read_bytes())
    os.replace(tmp, dest)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _publish_state_merging_history(src_state: Path, dest: Path) -> None:
    """Atomic replace. Same-session BUY_READY validation survives the replace."""
    from modules.live_candidate_v2_action.artifact import merge_historical_buy_ready

    new_doc = _read_json_object(src_state)
    if new_doc is None:
        _atomic_replace(src_state, dest)
        return
    merged = merge_historical_buy_ready(new_doc, _read_json_object(dest))
    if merged.get("historical_buy_ready") == new_doc.get("historical_buy_ready") or (
        not merged.get("historical_buy_ready") and "historical_buy_ready" not in new_doc
    ):
        _atomic_replace(src_state, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(merged, ensure_ascii=False, indent=2, default=str) + "\n"
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dest)


def publish_v2_action_state(src_state: Path, dest_dir: Path) -> dict[str, Any]:
    """Copy only v2_action_state.json. Does not rewrite Elite evidence."""
    dest_dir = Path(dest_dir)
    dest_s = str(dest_dir)
    if dest_s.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest_s == FORBIDDEN_CAMERA_ARCHIVE:
        return {"v2_status": "ERROR", "v2_detail": "refusing Camera archive path", "v2_copied": []}
    if not Path(src_state).exists():
        return {"v2_status": "ABSENT", "v2_detail": "no v2_action_state.json", "v2_copied": []}
    dest_dir.mkdir(parents=True, exist_ok=True)
    _publish_state_merging_history(Path(src_state), dest_dir / V2_ACTION_STATE_NAME)
    return {
        "v2_status": "OK",
        "v2_detail": str(dest_dir / V2_ACTION_STATE_NAME),
        "v2_copied": [V2_ACTION_STATE_NAME],
    }


def _copy_optional_v2(src_dir: Path, dest_dir: Path) -> dict[str, Any]:
    """Publish V2 SHADOW state next to Elite artifacts. Fail-open for Elite."""
    src_state = src_dir / V2_ACTION_SUBDIR / V2_ACTION_STATE_NAME
    if not src_state.exists():
        src_state = src_dir / V2_ACTION_STATE_NAME
    if not src_state.exists():
        return {"v2_status": "ABSENT", "v2_detail": "no v2_action_state.json", "v2_copied": []}
    copied: list[str] = []
    try:
        _publish_state_merging_history(src_state, dest_dir / V2_ACTION_STATE_NAME)
        copied.append(V2_ACTION_STATE_NAME)
        src_ev = src_dir / V2_ACTION_SUBDIR / V2_ACTION_EVIDENCE_NAME
        if not src_ev.exists():
            src_ev = src_dir / V2_ACTION_EVIDENCE_NAME
        if src_ev.exists():
            dest_ev = dest_dir / V2_ACTION_EVIDENCE_NAME
            shutil.copy2(src_ev, dest_ev)
            copied.append(V2_ACTION_EVIDENCE_NAME)
    except OSError as exc:
        return {
            "v2_status": "ERROR",
            "v2_detail": f"copy V2 SHADOW failed: {exc}",
            "v2_copied": copied,
        }
    return {
        "v2_status": "OK",
        "v2_detail": str(dest_dir / V2_ACTION_STATE_NAME),
        "v2_copied": copied,
    }


def publish_shadow_artifacts(
    src_dir: Path,
    dest_dir: Path,
) -> dict[str, Any]:
    """Copy Elite live_evidence + status. Optionally copy V2 SHADOW state."""
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)
    dest_s = str(dest_dir.resolve()) if dest_dir.exists() or dest_dir.parent.exists() else str(dest_dir)
    if dest_s.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest_s == FORBIDDEN_CAMERA_ARCHIVE:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": "refusing Camera archive path",
            "copied": [],
            "v2_status": "ABSENT",
            "v2_detail": "",
            "v2_copied": [],
        }
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": f"mkdir failed: {exc}",
            "copied": [],
            "v2_status": "ABSENT",
            "v2_detail": "",
            "v2_copied": [],
        }
    copied: list[str] = []
    for name in ALLOWED_SHADOW_FILES:
        src = src_dir / name
        if not src.exists():
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
                "detail": f"missing {name}",
                "copied": copied,
                "v2_status": "ABSENT",
                "v2_detail": "",
                "v2_copied": [],
            }
        dest = dest_dir / name
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
                "detail": f"copy {name} failed: {exc}",
                "copied": copied,
                "v2_status": "ABSENT",
                "v2_detail": "",
                "v2_copied": [],
            }
        copied.append(name)
    extra = _copy_optional_v2(src_dir, dest_dir)
    return {
        "ok": True,
        "status": "OK",
        "detail": "",
        "copied": copied,
        "dest": str(dest_dir),
        **extra,
    }
