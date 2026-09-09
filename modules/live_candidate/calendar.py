"""VN cash session clock for Candidate eligibility. Not a Camera collector."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CASH_CLOSE = time(14, 45)
SESSION_OPEN = time(9, 15)


def as_vn(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=VN_TZ)
    return ts.astimezone(VN_TZ)


def cash_session_end(session: date) -> datetime:
    return datetime.combine(session, CASH_CLOSE, tzinfo=VN_TZ)


def session_open_at(session: date) -> datetime:
    return datetime.combine(session, SESSION_OPEN, tzinfo=VN_TZ)


def next_trading_date(day: date) -> date:
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def next_trading_session_open(session: date) -> datetime:
    """09:15 VN on the next weekday after `session` (no holiday calendar)."""
    return session_open_at(next_trading_date(session))
