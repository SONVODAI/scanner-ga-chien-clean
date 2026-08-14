"""
Bar validation and quality classification.

Distinguishes INVALID DATA from VALID BUT ATYPICAL SESSION.
Does not reject symbols for exchange-specific session start differences.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from modules.intraday_memory.normalize import normalize_price_to_integer_vnd, normalize_volume
from modules.intraday_memory.schema import (
    QF_ATYPICAL_SESSION,
    QF_OK,
    QF_REJECTED,
    SOURCE_VNSTOCK_KBS,
    CanonicalBar,
)
from modules.intraday_memory.timezone_policy import (
    is_within_plausible_session,
    parse_provider_timestamp,
    session_date_from_timestamp,
)


@dataclass
class ValidationOutcome:
    bar: CanonicalBar | None
    accepted: bool
    quality_flag: str
    reason: str = ""


def _validate_ohlc(open_: int, high: int, low: int, close: int) -> str | None:
    if min(open_, high, low, close) <= 0:
        return "non_positive_price"
    if high < max(open_, close):
        return "high_below_body"
    if low > min(open_, close):
        return "low_above_body"
    if high < low:
        return "high_below_low"
    return None


def validate_raw_bar(
    symbol: str,
    raw: dict[str, Any],
    *,
    collected_at: datetime | None = None,
    source: str = SOURCE_VNSTOCK_KBS,
    expected_session_date: date | None = None,
) -> ValidationOutcome:
    """
    Validate and normalize one raw provider bar into canonical form.

    Malformed rows are rejected (quality_flag=rejected).
    Valid but atypical session bars are accepted with warning flag.
    """
    symbol = str(symbol).strip().upper()
    if not symbol:
        return ValidationOutcome(None, False, QF_REJECTED, "empty_symbol")

    try:
        ts = parse_provider_timestamp(raw.get("time") or raw.get("timestamp"))
    except (ValueError, TypeError) as exc:
        return ValidationOutcome(None, False, QF_REJECTED, f"bad_timestamp:{exc}")

    session_date = session_date_from_timestamp(ts)
    if expected_session_date and session_date != expected_session_date:
        return ValidationOutcome(
            None, False, QF_REJECTED,
            f"session_date_mismatch:{session_date}!={expected_session_date}",
        )

    try:
        open_ = normalize_price_to_integer_vnd(raw.get("open"))
        high = normalize_price_to_integer_vnd(raw.get("high"))
        low = normalize_price_to_integer_vnd(raw.get("low"))
        close = normalize_price_to_integer_vnd(raw.get("close"))
        volume = normalize_volume(raw.get("volume"))
    except ValueError as exc:
        return ValidationOutcome(None, False, QF_REJECTED, str(exc))

    ohlc_err = _validate_ohlc(open_, high, low, close)
    if ohlc_err:
        return ValidationOutcome(None, False, QF_REJECTED, ohlc_err)

    quality = QF_OK
    if not is_within_plausible_session(ts):
        quality = QF_ATYPICAL_SESSION

    bar = CanonicalBar(
        symbol=symbol,
        timestamp=ts,
        session_date=session_date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source=source,
        collected_at=collected_at,
        quality_flag=quality,
    )
    return ValidationOutcome(bar, True, quality)


def detect_duplicates(bars: list[CanonicalBar]) -> list[tuple[str, datetime]]:
    """Return list of duplicate (symbol, timestamp) keys."""
    seen: set[tuple[str, datetime]] = set()
    dups: list[tuple[str, datetime]] = []
    for bar in bars:
        key = (bar.symbol, bar.timestamp)
        if key in seen:
            dups.append(key)
        seen.add(key)
    return dups
