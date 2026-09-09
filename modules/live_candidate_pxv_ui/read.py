"""Read-only loaders for the LIVE CANDIDATE × P×V panel.

Sources (only):
  - research Dynamic Watchlist snapshot
  - live_evidence.jsonl
  - live_shadow_status.json

Never writes. Never imports a Camera/provider. Never imports the Interpreter.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from modules.live_candidate.watchlist import WATCHLIST_NAME, output_root

EVIDENCE_NAME = "live_evidence.jsonl"
STATUS_NAME = "live_shadow_status.json"


def default_shadow_dir() -> Path:
    raw = os.environ.get("MRBOT_LIVE_CAMERA_SHADOW_OUT", "").strip()
    if raw:
        return Path(raw)
    return Path("data/intraday_pxv_live_shadow")


def default_watchlist_path() -> Path:
    return output_root() / WATCHLIST_NAME


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_watchlist(path: Path | None = None) -> list[dict[str, Any]]:
    src = Path(path) if path is not None else default_watchlist_path()
    if not src.exists():
        return []
    data = json.loads(_read_text(src))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("rows") or [])
    return []


def load_evidence(path: Path | None = None) -> list[dict[str, Any]]:
    src = Path(path) if path is not None else default_shadow_dir() / EVIDENCE_NAME
    if not src.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in _read_text(src).splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_shadow_status(path: Path | None = None) -> dict[str, Any]:
    src = Path(path) if path is not None else default_shadow_dir() / STATUS_NAME
    if not src.exists():
        return {}
    data = json.loads(_read_text(src))
    return data if isinstance(data, dict) else {}


def load_panel_sources(
    *,
    watchlist_path: Path | None = None,
    evidence_path: Path | None = None,
    status_path: Path | None = None,
) -> dict[str, Any]:
    """One read pass. No provider. No writes."""
    return {
        "watchlist": load_watchlist(watchlist_path),
        "evidence": load_evidence(evidence_path),
        "status": load_shadow_status(status_path),
    }
