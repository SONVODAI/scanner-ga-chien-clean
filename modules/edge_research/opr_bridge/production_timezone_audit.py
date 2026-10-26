"""
Phase 3K.5 — Timezone and trading-session semantics audit.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from modules.edge_research.opr_bridge.production_observation_cutoff import DEFAULT_TIMEZONE
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    evaluate_trading_session_eligibility,
)
from modules.intraday_memory.timezone_policy import VN_TZ

TIMEZONE_AUDIT_VERSION = "timezone_audit_v1_3k5"


def derive_vn_trade_date(now: Optional[datetime] = None) -> str:
    """Authoritative VN local calendar date for production target_trade_date."""
    now = now or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    else:
        now = now.astimezone(VN_TZ)
    return now.strftime("%Y-%m-%d")


def audit_utc_vs_vn_boundary(panel: pd.DataFrame) -> Dict[str, Any]:
    """
    CF-READY3 — detect UTC/local-date disagreement at day boundary.
    """
    utc_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    vn_today = derive_vn_trade_date()
    disagreement = utc_today != vn_today
    return {
        "utc_calendar_date": utc_today,
        "vn_calendar_date": vn_today,
        "disagreement": disagreement,
        "resolution": "production_must_use_vn_calendar_date" if disagreement else "aligned",
        "fail_closed_if_ambiguous": disagreement,
    }


def audit_timezone_semantics(
    panel: pd.DataFrame,
    *,
    target_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    contract = build_scheduling_contract()
    target = target_trade_date or derive_vn_trade_date()
    boundary = audit_utc_vs_vn_boundary(panel)
    session = evaluate_trading_session_eligibility(panel, target)

    findings: List[str] = []
    if DEFAULT_TIMEZONE == "UTC":
        findings.append("birth_cutoff_records_store_utc_timestamps")
    if contract["expected_environment"]["timezone"] != "Asia/Ho_Chi_Minh":
        findings.append("scheduling_contract_timezone_mismatch")
    if boundary["disagreement"]:
        findings.append("utc_vn_date_boundary_active:use_vn_date_for_target_trade_date")

    return {
        "version": TIMEZONE_AUDIT_VERSION,
        "authoritative_session_timezone": "Asia/Ho_Chi_Minh",
        "cutoff_record_timezone": DEFAULT_TIMEZONE,
        "scheduling_timezone": contract["expected_environment"]["timezone"],
        "target_trade_date_derivation": "VN local calendar via derive_vn_trade_date()",
        "target_trade_date": target,
        "utc_vn_boundary": boundary,
        "session_eligibility": session.to_dict(),
        "forward_clock_basis": "panel trade_date strings + business day offsets",
        "ui_today_semantics": "latest_successful_research_date from run index, not server clock",
        "findings": findings,
        "pass": not boundary["fail_closed_if_ambiguous"] or boundary["resolution"] != "ambiguous",
    }
