"""
Phase 3K.5A — Deterministic Vietnam-market trading session calendar.

Weekends and configured exchange holidays excluded. No runtime network fetch.

CANONICAL TRADING-SESSION CLOCK (source of truth for T3/T5/T10 eligibility)
---------------------------------------------------------------------------
Do not add a parallel calendar. Callers that need future horizon dates must
use these primitives from this module:

1. evaluate_calendar_session_eligibility(date)
   Session yes/no (weekend, JSON holidays, closure_overrides).
2. offset_trading_sessions(anchor, n)
   Move ±N eligible VN sessions. Integer session arithmetic.
3. compute_horizon_eligible_date_vn(birth, "T3"|"T5"|"T10")
   CANONICAL T3/T5/T10 eligibility date. Always session offsets; never
   pandas BDay / weekday-only arithmetic.

Data file: config/vn_trading_calendar.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.intraday_memory.scheduler import is_vn_weekend
from modules.intraday_memory.timezone_policy import VN_TZ

CALENDAR_VERSION = "vn_trading_calendar_contract_v1_3k5a_nd"
DEFAULT_CALENDAR_PATH = Path(__file__).resolve().parents[3] / "config" / "vn_trading_calendar.json"
HORIZON_SESSION_OFFSETS = {"T3": 3, "T5": 5, "T10": 10}


@dataclass(frozen=True)
class TradingCalendarIdentity:
    calendar_id: str
    version: str
    timezone: str
    holiday_count: int
    override_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calendar_id": self.calendar_id,
            "version": self.version,
            "timezone": self.timezone,
            "holiday_count": self.holiday_count,
            "override_count": self.override_count,
        }


@dataclass(frozen=True)
class SessionEligibilityResult:
    trade_date: str
    eligible: bool
    disposition: str  # ELIGIBLE | SKIPPED_NON_TRADING_DAY | CALENDAR_UNKNOWN
    reason: str
    is_weekend: bool
    is_holiday: bool
    is_closure_override: bool
    calendar_identity: TradingCalendarIdentity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "eligible": self.eligible,
            "disposition": self.disposition,
            "reason": self.reason,
            "is_weekend": self.is_weekend,
            "is_holiday": self.is_holiday,
            "is_closure_override": self.is_closure_override,
            "calendar_identity": self.calendar_identity.to_dict(),
        }


def _parse_date(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def load_trading_calendar(calendar_path: Optional[Path] = None) -> Dict[str, Any]:
    path = calendar_path or DEFAULT_CALENDAR_PATH
    if not path.exists():
        return {
            "version": "missing",
            "calendar_id": "unknown",
            "timezone": "Asia/Ho_Chi_Minh",
            "holidays": [],
            "closure_overrides": {},
            "_load_error": f"calendar_not_found:{path}",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def calendar_identity(calendar: Optional[Dict[str, Any]] = None) -> TradingCalendarIdentity:
    cal = calendar or load_trading_calendar()
    overrides = cal.get("closure_overrides") or {}
    return TradingCalendarIdentity(
        calendar_id=str(cal.get("calendar_id", "unknown")),
        version=str(cal.get("version", "unknown")),
        timezone=str(cal.get("timezone", "Asia/Ho_Chi_Minh")),
        holiday_count=len(cal.get("holidays") or []),
        override_count=len(overrides),
    )


def holiday_set(calendar: Optional[Dict[str, Any]] = None) -> Set[str]:
    cal = calendar or load_trading_calendar()
    return {str(h)[:10] for h in (cal.get("holidays") or [])}


def closure_overrides(calendar: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    cal = calendar or load_trading_calendar()
    return {str(k)[:10]: dict(v) for k, v in (cal.get("closure_overrides") or {}).items()}


def is_calendar_loaded(calendar: Optional[Dict[str, Any]] = None) -> bool:
    cal = calendar or load_trading_calendar()
    return not cal.get("_load_error") and cal.get("version") not in (None, "missing", "unknown")


def is_exchange_holiday(trade_date: str, calendar: Optional[Dict[str, Any]] = None) -> bool:
    return str(trade_date)[:10] in holiday_set(calendar)


def is_closure_override_closed(trade_date: str, calendar: Optional[Dict[str, Any]] = None) -> bool:
    ov = closure_overrides(calendar).get(str(trade_date)[:10])
    return bool(ov and ov.get("closed"))


def evaluate_calendar_session_eligibility(
    target_trade_date: str,
    *,
    calendar_path: Optional[Path] = None,
) -> SessionEligibilityResult:
    """Fail closed when calendar cannot be loaded."""
    cal = load_trading_calendar(calendar_path)
    ident = calendar_identity(cal)
    td = str(target_trade_date)[:10]

    if not is_calendar_loaded(cal):
        return SessionEligibilityResult(
            trade_date=td,
            eligible=False,
            disposition="CALENDAR_UNKNOWN",
            reason="trading_calendar_not_loaded",
            is_weekend=False,
            is_holiday=False,
            is_closure_override=False,
            calendar_identity=ident,
        )

    try:
        d = _parse_date(td)
    except ValueError:
        return SessionEligibilityResult(
            trade_date=td,
            eligible=False,
            disposition="CALENDAR_UNKNOWN",
            reason="invalid_trade_date_format",
            is_weekend=False,
            is_holiday=False,
            is_closure_override=False,
            calendar_identity=ident,
        )

    weekend = is_vn_weekend(d)
    holiday = is_exchange_holiday(td, cal)
    closed_override = is_closure_override_closed(td, cal)

    if closed_override:
        return SessionEligibilityResult(
            trade_date=td,
            eligible=False,
            disposition="SKIPPED_NON_TRADING_DAY",
            reason="exceptional_closure_override",
            is_weekend=weekend,
            is_holiday=holiday,
            is_closure_override=True,
            calendar_identity=ident,
        )

    if weekend:
        return SessionEligibilityResult(
            trade_date=td,
            eligible=False,
            disposition="SKIPPED_NON_TRADING_DAY",
            reason="weekend_non_session",
            is_weekend=True,
            is_holiday=holiday,
            is_closure_override=False,
            calendar_identity=ident,
        )

    if holiday:
        return SessionEligibilityResult(
            trade_date=td,
            eligible=False,
            disposition="SKIPPED_NON_TRADING_DAY",
            reason="exchange_holiday",
            is_weekend=False,
            is_holiday=True,
            is_closure_override=False,
            calendar_identity=ident,
        )

    return SessionEligibilityResult(
        trade_date=td,
        eligible=True,
        disposition="ELIGIBLE",
        reason="calendar_trading_session",
        is_weekend=False,
        is_holiday=False,
        is_closure_override=False,
        calendar_identity=ident,
    )


def iter_trading_sessions(
    start_date: str,
    end_date: str,
    *,
    calendar_path: Optional[Path] = None,
) -> List[str]:
    """Inclusive list of VN trading sessions between start and end."""
    cal = load_trading_calendar(calendar_path)
    if not is_calendar_loaded(cal):
        return []
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    sessions: List[str] = []
    cur = start
    while cur <= end:
        td = cur.strftime("%Y-%m-%d")
        if evaluate_calendar_session_eligibility(td, calendar_path=calendar_path).eligible:
            sessions.append(td)
        cur += timedelta(days=1)
    return sessions


def count_trading_sessions(
    start_date: str,
    end_date: str,
    *,
    calendar_path: Optional[Path] = None,
) -> int:
    return len(iter_trading_sessions(start_date, end_date, calendar_path=calendar_path))


def offset_trading_sessions(
    anchor_date: str,
    offset: int,
    *,
    calendar_path: Optional[Path] = None,
) -> Optional[str]:
    """
    Move anchor by N trading sessions (positive = forward).
    Used for T3/T5/T10 horizon counting.
    """
    if offset == 0:
        return str(anchor_date)[:10]
    cal_path = calendar_path
    step = 1 if offset > 0 else -1
    remaining = abs(offset)
    cur = _parse_date(anchor_date)
    guard = 0
    while remaining > 0 and guard < 366 * 3:
        cur += timedelta(days=step)
        guard += 1
        td = cur.strftime("%Y-%m-%d")
        if evaluate_calendar_session_eligibility(td, calendar_path=cal_path).eligible:
            remaining -= 1
    if remaining > 0:
        return None
    return cur.strftime("%Y-%m-%d")


def compute_horizon_eligible_date_vn(
    birth_trade_date: str,
    horizon: str,
    *,
    calendar_path: Optional[Path] = None,
    panel_sessions: Optional[List[str]] = None,
) -> str:
    """
    CANONICAL T3/T5/T10 eligibility date.

    Counts N subsequent Vietnam trading sessions from birth_trade_date.
    Never uses pandas BDay / weekday-only arithmetic.

    panel_sessions is a compatibility fallback only when the calendar file
    cannot be loaded. It is not a second calendar.
    """
    offset = HORIZON_SESSION_OFFSETS.get(horizon, 0)
    birth = str(birth_trade_date)[:10]
    cal = load_trading_calendar(calendar_path)
    if is_calendar_loaded(cal):
        result = offset_trading_sessions(birth, offset, calendar_path=calendar_path)
        if result:
            return result
    if panel_sessions and birth in panel_sessions:
        idx = panel_sessions.index(birth)
        target_idx = idx + offset
        if 0 <= target_idx < len(panel_sessions):
            return panel_sessions[target_idx]
    return ""
