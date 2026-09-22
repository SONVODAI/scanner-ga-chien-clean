"""Session gate for Streamlit research below the Daily Report boundary.

The gate only answers whether that block may execute. It does not run
engines, change scoring, or write artifacts.

Clock is Asia/Ho_Chi_Minh wall time:

- Weekday 09:15 inclusive through 15:10 exclusive: LOCKED.
  That span covers both live sessions, lunch (11:30–13:00), and the
  14:50–15:10 close buffer.
- Weekday 15:10 onward, and before 09:15: unlocked.
- Saturday and Sunday: unlocked.

Weekend behavior matches the current app, which still executes the full
page on non-session days. This repo has no exchange holiday calendar.
``is_vnindex_trading_today()`` is not used here: it is also false on a
real trading morning before the daily bar exists, which would fail the
09:30 lock. A weekday exchange holiday therefore follows the clock.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Inclusive start of the research lock (live open).
RESEARCH_LOCK_START = time(9, 15)
# Exclusive end of the lock. 15:10:00 is the first unlocked minute.
RESEARCH_UNLOCK_AT = time(15, 10)


def as_vn(now: datetime) -> datetime:
    """Interpret naive datetimes as Vietnam wall time."""
    if now.tzinfo is None:
        return now.replace(tzinfo=VN_TZ)
    return now.astimezone(VN_TZ)


def research_below_boundary_locked(now: datetime) -> bool:
    """True when code below the Daily Report boundary must not execute."""
    local = as_vn(now)
    if local.weekday() >= 5:
        return False
    clock = local.timetz().replace(tzinfo=None)
    return RESEARCH_LOCK_START <= clock < RESEARCH_UNLOCK_AT
