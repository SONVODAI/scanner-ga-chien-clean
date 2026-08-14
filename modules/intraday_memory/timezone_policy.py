"""
Timezone policy for intraday memory.

Canonical timezone: Asia/Ho_Chi_Minh (VN market local time).
All stored timestamps are timezone-aware in VN_TZ.
session_date is derived from the VN-local calendar date of the bar.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Plausible regular-session bounds (local VN time, inclusive).
SESSION_HOUR_MIN = 9
SESSION_HOUR_MAX = 15
SESSION_MINUTE_MAX = 30  # allow UPCOM extended close ~15:00


def parse_provider_timestamp(raw: Any) -> datetime:
    """
    Parse provider timestamp into timezone-aware VN datetime.

    Naive timestamps from KBS are interpreted as Asia/Ho_Chi_Minh local time.
    """
    if raw is None:
        raise ValueError("Timestamp is None")

    if isinstance(raw, datetime):
        ts = raw
    else:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=VN_TZ)
    else:
        ts = ts.astimezone(VN_TZ)

    return ts


def session_date_from_timestamp(ts: datetime) -> date:
    """Derive trading session calendar date in VN local time."""
    local = ts.astimezone(VN_TZ)
    return local.date()


def is_within_plausible_session(ts: datetime) -> bool:
    """Check if timestamp falls within plausible VN trading hours."""
    local = ts.astimezone(VN_TZ)
    hour, minute = local.hour, local.minute

    if hour < SESSION_HOUR_MIN:
        return False
    if hour > SESSION_HOUR_MAX:
        return False
    if hour == SESSION_HOUR_MAX and minute > SESSION_MINUTE_MAX:
        return False
    return True
