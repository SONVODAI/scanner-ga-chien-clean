"""Research join contract for market context. Not a trading rule.

Camera 5-minute bars are labeled at the start of the bucket. A bar whose
timestamp is T is complete at T + 5 minutes. Both clocks are Asia/Ho_Chi_Minh.

A later research reader may use a Market Context row for that bar only when:

    market_context.captured_at <= T + 5 minutes

Previous close may be used only when:

    previous_close_date < session_date

This module does not score stocks, nominate candidates, or read production
ledgers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from modules.live_candidate.calendar import as_vn

BAR_BUCKET = timedelta(minutes=5)
SOURCE_VNSTOCK_D1 = "vnstock_d1_bar_before_session"
PRICE_UNIT_INTEGER_VND = "integer_vnd"
SOURCE_STREAMLIT_SCAN = "streamlit_scan"
SOURCE_CLOSE_SCAN = "close_scan"

# A normal weekend is 3 calendar days (Friday close -> Monday session).
# Longer gaps stay stored, with status=stale, so research can see them.
STALE_GAP_DAYS = 7


def bar_completion_at(bar_timestamp: datetime) -> datetime:
    """Completion time of a start-labeled 5-minute bar."""
    return as_vn(bar_timestamp) + BAR_BUCKET


def market_context_asof_eligible(captured_at: datetime, bar_timestamp: datetime) -> bool:
    """True when the context row was known by the time the bar completed.

    ``captured_at == T + 5 minutes`` is eligible. A later row is not.
    """
    return as_vn(captured_at) <= bar_completion_at(bar_timestamp)


def previous_close_date_eligible(previous_close_date: date, session_date: date) -> bool:
    """Canonical previous close must come from a bar strictly before the session."""
    return previous_close_date < session_date
