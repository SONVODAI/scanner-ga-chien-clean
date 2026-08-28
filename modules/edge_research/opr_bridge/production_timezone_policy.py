"""
Phase 3K.5A — Canonical timezone semantics for production research.

trading_session_date = Asia/Ho_Chi_Minh market date.
Operational timestamps may remain UTC. Scientific records carry explicit semantics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
)
from modules.intraday_memory.timezone_policy import VN_TZ

TIMEZONE_POLICY_VERSION = "production_timezone_policy_v1_3k5a"
TRADING_SESSION_TIMEZONE = "Asia/Ho_Chi_Minh"
OPERATIONAL_TIMESTAMP_TIMEZONE = "UTC"


def derive_vn_trade_date(now: Optional[datetime] = None) -> str:
    """Authoritative VN local calendar date for trading_session_date."""
    now = now or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    else:
        now = now.astimezone(VN_TZ)
    return now.strftime("%Y-%m-%d")


def derive_utc_calendar_date(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y-%m-%d")


def canonical_trading_session_metadata(trade_date: str) -> Dict[str, Any]:
    """Explicit semantics attached to scientific records (non-destructive metadata)."""
    cal = evaluate_calendar_session_eligibility(trade_date)
    return {
        "trading_session_date": str(trade_date)[:10],
        "trading_session_timezone": TRADING_SESSION_TIMEZONE,
        "operational_timestamp_timezone": OPERATIONAL_TIMESTAMP_TIMEZONE,
        "calendar_eligible": cal.eligible,
        "calendar_disposition": cal.disposition,
        "policy_version": TIMEZONE_POLICY_VERSION,
    }


def resolve_target_trade_date(
    explicit_date: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
) -> str:
    """
    Resolve production target date. Explicit VN session date wins;
    otherwise derive from VN calendar (never server-local date).
    """
    if explicit_date:
        return str(explicit_date)[:10]
    return derive_vn_trade_date(now)


def audit_utc_vn_boundary(now: Optional[datetime] = None) -> Dict[str, Any]:
    utc_date = derive_utc_calendar_date(now)
    vn_date = derive_vn_trade_date(now)
    disagreement = utc_date != vn_date
    return {
        "utc_calendar_date": utc_date,
        "vn_trading_session_date": vn_date,
        "disagreement": disagreement,
        "authoritative_for_trading_session": TRADING_SESSION_TIMEZONE,
        "must_use_vn_date_for_target_trade_date": True,
    }


def reject_utc_derived_genesis_date(
    first_eligible_trade_date: str,
    *,
    activation_now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    CF-PR11 — genesis first eligible date must not be UTC calendar artifact
    when VN trading session date differs.
    """
    boundary = audit_utc_vn_boundary(activation_now)
    if not boundary["disagreement"]:
        return True, "ok"
    utc_date = boundary["utc_calendar_date"]
    vn_date = boundary["vn_trading_session_date"]
    if first_eligible_trade_date == utc_date and first_eligible_trade_date != vn_date:
        return False, "genesis_date_derived_from_utc_not_vn_session"
    return True, "ok"


def validate_genesis_first_eligible_date(
    first_eligible_trade_date: str,
    *,
    activation_now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Genesis date must be a valid VN trading session per calendar contract."""
    ok, reason = reject_utc_derived_genesis_date(
        first_eligible_trade_date, activation_now=activation_now
    )
    if not ok:
        return False, reason
    cal = evaluate_calendar_session_eligibility(first_eligible_trade_date)
    if not cal.eligible:
        return False, f"genesis_first_eligible_not_trading_session:{cal.reason}"
    return True, "ok"
