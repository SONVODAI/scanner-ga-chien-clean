"""Read-only loaders for the LIVE CANDIDATE × P×V panel.

Sources (only):
  - research Dynamic Watchlist snapshot (local Cloud persist / GitHub path)
  - live_evidence.jsonl
  - live_shadow_status.json

Remote evidence/status: existing EDGE_RESEARCH_DURABLE_URL + bearer GET.
Never writes. Never imports a Camera/provider. Never imports the Interpreter.
Never falls back to stale local P×V when remote mode is active.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from modules.live_candidate.watchlist import WATCHLIST_NAME, output_root
from modules.live_shadow_transport.artifact_get import (
    EvidenceTransportError,
    LiveShadowNotFound,
    get_live_evidence_text,
    get_live_status_text,
    remote_artifact_configured,
    transport_error_payload,
)
from modules.live_shadow_transport.contract import (
    ENV_UI_SOURCE,
    EVIDENCE_TRANSPORT_ERROR,
)

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


def parse_evidence_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def resolve_ui_source(explicit: str | None = None) -> str:
    mode = (explicit or os.environ.get(ENV_UI_SOURCE) or "auto").strip().lower()
    if mode == "auto":
        return "remote" if remote_artifact_configured() else "local"
    if mode in {"remote", "local"}:
        return mode
    return "local"


def load_panel_sources(
    *,
    watchlist_path: Path | None = None,
    evidence_path: Path | None = None,
    status_path: Path | None = None,
    source_mode: str | None = None,
    evidence_fetcher: Optional[Callable[[], str]] = None,
    status_fetcher: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """One read pass. No provider. No writes. Remote GET never synthesizes P×V."""
    mode = resolve_ui_source(source_mode)
    transport = {"mode": mode, "evidence": "OK", "status": "OK", "error": None, "detail": ""}
    watchlist = load_watchlist(watchlist_path)

    if mode == "remote":
        evidence: list[dict[str, Any]] = []
        status: dict[str, Any] = {}
        try:
            ev_text = evidence_fetcher() if evidence_fetcher is not None else get_live_evidence_text()
            evidence = parse_evidence_text(ev_text)
        except LiveShadowNotFound:
            evidence = []
        except EvidenceTransportError as exc:
            transport["evidence"] = EVIDENCE_TRANSPORT_ERROR
            transport["error"] = EVIDENCE_TRANSPORT_ERROR
            transport["detail"] = str(exc)
            evidence = []
        except Exception as exc:  # noqa: BLE001 — no silent local fallback
            transport["evidence"] = EVIDENCE_TRANSPORT_ERROR
            transport["error"] = EVIDENCE_TRANSPORT_ERROR
            transport["detail"] = str(exc)
            evidence = []
        try:
            st_text = status_fetcher() if status_fetcher is not None else get_live_status_text()
            parsed = json.loads(st_text)
            status = parsed if isinstance(parsed, dict) else {}
        except LiveShadowNotFound:
            status = {}
        except EvidenceTransportError as exc:
            transport["status"] = EVIDENCE_TRANSPORT_ERROR
            transport["error"] = EVIDENCE_TRANSPORT_ERROR
            if not transport["detail"]:
                transport["detail"] = str(exc)
            status = transport_error_payload(str(exc))
        except Exception as exc:  # noqa: BLE001
            transport["status"] = EVIDENCE_TRANSPORT_ERROR
            transport["error"] = EVIDENCE_TRANSPORT_ERROR
            if not transport["detail"]:
                transport["detail"] = str(exc)
            status = transport_error_payload(str(exc))
        return {
            "watchlist": watchlist,
            "evidence": evidence,
            "status": status,
            "transport": transport,
        }

    return {
        "watchlist": watchlist,
        "evidence": load_evidence(evidence_path),
        "status": load_shadow_status(status_path),
        "transport": transport,
    }
