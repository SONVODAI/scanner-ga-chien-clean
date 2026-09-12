"""Rotation Watch board artifact. Isolated from Candidate / Edge / Learning."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.config import default_watch_dir
from modules.rotation_watch.constants import BOARD_NAME, SCHEMA_BOARD, STATUS_NAME
from modules.rotation_watch.session import apply_actionability, session_phase


def default_board_path() -> Path:
    return default_watch_dir() / BOARD_NAME


def default_status_path() -> Path:
    return default_watch_dir() / STATUS_NAME


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def board_from_rows(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    watchlist_path: str = "",
    empty_message: str = "",
    runner: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = as_vn(now)
    phase = session_phase(now)
    observed = now.isoformat()
    gated = [apply_actionability(row, now, artifact_observed_at=now) for row in rows]
    for row in gated:
        row.setdefault("observed_at", observed)
    return {
        "schema": SCHEMA_BOARD,
        "observed_at": observed,
        "session_phase": phase,
        "watchlist_path": watchlist_path,
        "empty": not gated,
        "empty_message": empty_message,
        "alert_eligible": False,
        "source": "rotation_watch_sidecar",
        "runner": runner or {},
        "rows": gated,
    }


def write_board(payload: dict[str, Any], path: Path | None = None) -> Path:
    return write_json(path or default_board_path(), payload)


def write_status(payload: dict[str, Any], path: Path | None = None) -> Path:
    return write_json(path or default_status_path(), payload)
