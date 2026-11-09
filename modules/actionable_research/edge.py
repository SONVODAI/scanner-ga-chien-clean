"""Read-only ACTIVE-edge + Phase B recognition adapter. Never evaluates edges."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from modules.actionable_research.contracts import (
    EDGE_STATUS_ACTIVE_MATCH,
    EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE,
    EDGE_STATUS_NO_ACTIVE_MATCH,
    EDGE_STATUS_UNKNOWN,
)
from modules.actionable_research.paths import FusionPaths, read_json

try:
    from modules.edge_research.contracts import EDGE_MEMORY_STATUS_ACTIVE
except Exception:  # pragma: no cover - older main without the constant
    EDGE_MEMORY_STATUS_ACTIVE = "ACTIVE"


def _read_csv(path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame()


def load_active_edges(paths: FusionPaths) -> Dict[str, Any]:
    path = paths.edge_memory_path()
    if not path.exists():
        return {
            "available": False,
            "active_count": 0,
            "rows": [],
            "source": str(path),
            "source_status": "EDGE_MEMORY_UNAVAILABLE",
        }
    memory = _read_csv(path)
    if memory.empty:
        return {
            "available": True,
            "active_count": 0,
            "rows": [],
            "source": str(path),
            "source_status": "EDGE_MEMORY_EMPTY",
        }
    if "status" not in memory.columns:
        return {
            "available": False,
            "active_count": 0,
            "rows": [],
            "source": str(path),
            "source_status": "EDGE_MEMORY_UNREADABLE",
        }
    active = memory[memory["status"].astype(str).str.upper() == EDGE_MEMORY_STATUS_ACTIVE]
    rows: List[Dict[str, Any]] = []
    for _, rec in active.iterrows():
        rows.append(
            {
                "edge_id": str(rec.get("edge_id") or ""),
                "hypothesis_id": str(rec.get("hypothesis_id") or ""),
                "best_horizon": str(rec.get("best_horizon") or "") or None,
                "status": EDGE_MEMORY_STATUS_ACTIVE,
                "spec_path": str(rec.get("spec_path") or ""),
                "spec_hash": str(rec.get("spec_hash") or ""),
            }
        )
    return {
        "available": True,
        "active_count": len(rows),
        "rows": rows,
        "source": str(path),
        "source_status": "OK",
    }


def load_recognition(
    trade_date: str,
    *,
    paths: FusionPaths,
) -> Dict[str, Any]:
    """Prefer daily sidecar; fall back to latest_future_recognition.json if date matches."""
    td = str(trade_date)[:10]
    daily = read_json(paths.daily_edge_matches_path(td))
    if daily is not None:
        daily_date = str(daily.get("trade_date") or daily.get("t0_date") or "")[:10]
        if daily_date and daily_date != td:
            return {
                "available": False,
                "source": str(paths.daily_edge_matches_path(td)),
                "source_status": "DAILY_MATCHES_DATE_MISMATCH",
                "payload": daily,
            }
        return {
            "available": True,
            "source": str(paths.daily_edge_matches_path(td)),
            "source_status": "OK",
            "payload": daily,
        }

    latest = read_json(paths.latest_recognition_path())
    if latest is None:
        return {
            "available": False,
            "source": str(paths.latest_recognition_path()),
            "source_status": "RECOGNITION_UNAVAILABLE",
            "payload": {},
        }
    latest_date = str(latest.get("trade_date") or latest.get("t0_date") or "")[:10]
    if latest_date and latest_date != td:
        return {
            "available": False,
            "source": str(paths.latest_recognition_path()),
            "source_status": "LATEST_RECOGNITION_OTHER_DATE",
            "payload": latest,
        }
    return {
        "available": True,
        "source": str(paths.latest_recognition_path()),
        "source_status": "OK_LATEST",
        "payload": latest,
    }


def _matches_by_symbol(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    candidates = (
        payload.get("matches")
        or payload.get("qualified_matches")
        or payload.get("births")
        or payload.get("records")
        or []
    )
    if isinstance(payload.get("by_symbol"), dict):
        for sym, items in payload["by_symbol"].items():
            key = str(sym).upper()
            if isinstance(items, list):
                out.setdefault(key, []).extend(items)
            elif isinstance(items, dict):
                out.setdefault(key, []).append(items)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol") or "").upper().strip()
        if not sym:
            continue
        out.setdefault(sym, []).append(item)
    return out


def assess_edge_for_symbols(
    symbols: Sequence[str],
    *,
    active: Dict[str, Any],
    recognition: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Per-stock edge status. Absence of Camera/foreign never changes these values.

    Does not re-run Phase B matching.
    """
    result: Dict[str, Dict[str, Any]] = {}
    if not active.get("available"):
        status = EDGE_STATUS_UNKNOWN
        session_reason = str(active.get("source_status") or "EDGE_MEMORY_UNAVAILABLE")
    elif int(active.get("active_count") or 0) <= 0:
        status = EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE
        session_reason = "NO_ACTIVE_EDGE_IN_MEMORY"
    else:
        status = None
        session_reason = "ACTIVE_EDGES_PRESENT"

    payload = recognition.get("payload") if recognition.get("available") else {}
    matches = _matches_by_symbol(payload if isinstance(payload, dict) else {})
    session_verdict = ""
    if isinstance(payload, dict):
        session_verdict = str(
            payload.get("assessment_state")
            or payload.get("edge_context_verdict")
            or payload.get("reason")
            or ""
        )

    rec_ok = bool(recognition.get("available"))

    for raw in symbols:
        symbol = str(raw).upper()
        if status == EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE:
            result[symbol] = {
                "edge_status": EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE,
                "active_edge_match_count": 0,
                "matched_edge_ids": [],
                "best_horizon": None,
                "edge_context_verdict": session_verdict or "NO_ACTIVE_EDGE_AVAILABLE",
                "edge_source": active.get("source"),
                "recognition_source": recognition.get("source"),
                "recognition_source_status": recognition.get("source_status"),
            }
            continue
        if status == EDGE_STATUS_UNKNOWN:
            result[symbol] = {
                "edge_status": EDGE_STATUS_UNKNOWN,
                "active_edge_match_count": 0,
                "matched_edge_ids": [],
                "best_horizon": None,
                "edge_context_verdict": session_reason,
                "edge_source": active.get("source"),
                "recognition_source": recognition.get("source"),
                "recognition_source_status": recognition.get("source_status"),
            }
            continue
        if not rec_ok:
            result[symbol] = {
                "edge_status": EDGE_STATUS_UNKNOWN,
                "active_edge_match_count": 0,
                "matched_edge_ids": [],
                "best_horizon": None,
                "edge_context_verdict": "RECOGNITION_UNAVAILABLE",
                "edge_source": active.get("source"),
                "recognition_source": recognition.get("source"),
                "recognition_source_status": recognition.get("source_status"),
            }
            continue
        items = matches.get(symbol) or []
        edge_ids = []
        horizons = []
        verdicts = []
        for item in items:
            eid = str(item.get("edge_id") or item.get("hypothesis_id") or "").strip()
            if eid:
                edge_ids.append(eid)
            h = item.get("best_horizon") or item.get("horizon")
            if h:
                horizons.append(str(h))
            v = item.get("edge_context_verdict") or item.get("context_verdict")
            if v:
                verdicts.append(str(v))
        if items:
            result[symbol] = {
                "edge_status": EDGE_STATUS_ACTIVE_MATCH,
                "active_edge_match_count": len(items),
                "matched_edge_ids": edge_ids,
                "best_horizon": horizons[0] if horizons else None,
                "edge_context_verdict": verdicts[0] if verdicts else (session_verdict or "CONTEXT_COMPATIBLE"),
                "edge_source": active.get("source"),
                "recognition_source": recognition.get("source"),
                "recognition_source_status": recognition.get("source_status"),
            }
        else:
            result[symbol] = {
                "edge_status": EDGE_STATUS_NO_ACTIVE_MATCH,
                "active_edge_match_count": 0,
                "matched_edge_ids": [],
                "best_horizon": None,
                "edge_context_verdict": session_verdict or "NO_STOCK_SATISFIES_ACTIVE_EDGE",
                "edge_source": active.get("source"),
                "recognition_source": recognition.get("source"),
                "recognition_source_status": recognition.get("source_status"),
            }
    return result
