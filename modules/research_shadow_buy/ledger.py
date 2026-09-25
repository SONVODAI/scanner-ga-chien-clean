"""Append-only SHADOW BUY event ledger.

One first-met event per candidate session and evaluated route.
A later reversal does not delete it. An identical rerun does not append again.
This directory is not read by NAV, Telegram, orders, or production BUY.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    EXECUTION_ENABLED,
    PXV_IMPLIES_BUY,
    RESEARCH_DECISION_SHADOW_BUY,
)
from modules.research_market_context.previous_close import append_json_line

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "research" / "shadow_buy_events"
EVENTS_NAME = "shadow_buy_events.jsonl"
STATUS_NAME = "shadow_buy_status.json"
ENV_DIR = "MRBOT_SHADOW_BUY_DIR"
SCHEMA = "research_shadow_buy_event.v1"
ORIGIN_SOURCE = "production_scan_df"


def shadow_buy_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_DIR, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DIR


def events_path(directory: Path | None = None) -> Path:
    return shadow_buy_dir(directory) / EVENTS_NAME


def status_path(directory: Path | None = None) -> Path:
    return shadow_buy_dir(directory) / STATUS_NAME


def event_key(session: str, symbol: str, route: str) -> str:
    return f"{str(session)[:10]}|{str(symbol).strip().upper()}|{str(route).strip()}"


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _event_row(nom: Any, result: Any) -> dict[str, Any]:
    session = str(getattr(result, "session", "") or getattr(nom, "session", ""))
    symbol = str(getattr(result, "symbol", "") or getattr(nom, "symbol", "")).strip().upper()
    route = str(getattr(result, "evaluated_route", "") or getattr(nom, "route", ""))
    origin_setup = str(getattr(result, "origin_setup", "") or getattr(nom, "origin_setup", "") or "")
    return {
        "schema": SCHEMA,
        "event_key": event_key(session, symbol, route),
        "trade_date": str(session)[:10],
        "session": str(session)[:10],
        "symbol": symbol,
        "candidate_source": str(getattr(result, "source", "") or getattr(nom, "source", "") or ""),
        "origin_source": ORIGIN_SOURCE if origin_setup or getattr(nom, "origin_group", "") else "",
        "origin_setup": origin_setup,
        "origin_group": str(getattr(result, "origin_group", "") or getattr(nom, "origin_group", "") or ""),
        "origin_ema9": getattr(nom, "origin_ema9", None),
        "origin_breakout_ref": getattr(nom, "origin_breakout_ref", None),
        "origin_pull_label": str(getattr(nom, "origin_pull_label", "") or ""),
        "evaluated_setup": str(getattr(result, "setup", "") or getattr(nom, "setup", "") or ""),
        "evaluated_route": route,
        "route_became_evaluable_at": str(getattr(nom, "route_became_evaluable_at", "") or ""),
        "research_qualification": str(getattr(nom, "research_qualification", "") or ""),
        "first_met_at": getattr(result, "first_met_at", None),
        "legal_bar_ts": getattr(result, "first_met_at", None),
        "price_at_first_met": getattr(result, "price_at_first_met", None),
        "frozen_ref_kind": getattr(result, "frozen_ref_kind", ""),
        "frozen_ref_value": getattr(result, "frozen_ref_value", None),
        "evaluator_reason": getattr(result, "condition_reason", "") or getattr(result, "action_reason", ""),
        "published_evidence": getattr(result, "published_evidence", ""),
        "volume_expansion_state": getattr(result, "volume_expansion_state", None),
        "price_volume_state": getattr(result, "price_volume_state", None),
        "close_vs_ref": getattr(result, "close_vs_ref", None),
        "close_vs_ref_pct": getattr(result, "close_vs_ref_pct", None),
        "condition_met": True,
        "market_permission": getattr(result, "market_permission", ""),
        "market_real": getattr(result, "market_real", None),
        "market_ok": bool(getattr(result, "market_ok", False)),
        "market_blocked": bool(getattr(result, "market_blocked", False)),
        "candidate_is_buy": CANDIDATE_IS_BUY,
        "pxv_implies_buy": PXV_IMPLIES_BUY,
        "alert_eligible": ALERT_ELIGIBLE,
        "execution_enabled": EXECUTION_ENABLED,
        "research_decision": RESEARCH_DECISION_SHADOW_BUY,
        "action_state": getattr(result, "action_state", ""),
    }


def _status_row(nom: Any, result: Any) -> dict[str, Any]:
    row = _event_row(nom, result)
    row["condition_met"] = bool(getattr(result, "condition_met", False))
    row["research_decision"] = str(getattr(result, "research_decision", "") or "")
    row["non_event_reason"] = str(getattr(result, "non_event_reason", "") or "")
    row["action_reason"] = str(getattr(result, "action_reason", "") or "")
    row["execution_enabled"] = False
    row["candidate_is_buy"] = False
    row["pxv_implies_buy"] = False
    row["alert_eligible"] = False
    return row


def _write_status(path: Path, key: str, row: Mapping[str, Any]) -> None:
    current: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            current = {}
    current[key] = dict(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def try_record_shadow_buy(
    nom: Any,
    result: Any,
    *,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Fail-open. Append the first SHADOW BUY only. Always refresh the status snapshot."""
    try:
        base = shadow_buy_dir(directory)
        status = _status_row(nom, result)
        key = str(status.get("event_key") or "")
        if key:
            _write_status(status_path(base), key, status)
        if not bool(getattr(result, "condition_met", False)):
            return {"appended": False, "reason": status.get("non_event_reason") or "CONDITION_NOT_MET"}
        if str(getattr(result, "research_decision", "")) != RESEARCH_DECISION_SHADOW_BUY:
            return {"appended": False, "reason": "NOT_SHADOW_BUY"}
        route = str(status.get("evaluated_route") or "")
        if not route:
            return {"appended": False, "reason": "NO_EVALUATED_ROUTE"}
        path = events_path(base)
        existing = {str(row.get("event_key") or "") for row in _read_events(path)}
        if key in existing:
            return {"appended": False, "reason": "ALREADY_RECORDED", "event_key": key}
        append_json_line(path, _event_row(nom, result))
        return {"appended": True, "event_key": key}
    except Exception as exc:  # noqa: BLE001 — research ledger must not break the caller
        return {"appended": False, "reason": f"{type(exc).__name__}: {exc}"}


def load_shadow_buy_events(directory: Path | None = None) -> list[dict[str, Any]]:
    return _read_events(events_path(directory))


def load_shadow_buy_status(directory: Path | None = None) -> dict[str, Any]:
    path = status_path(directory)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
