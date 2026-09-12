"""Completed 5m bar filter + live provenance. Read-only. No archive writes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from modules.intraday_memory.timezone_policy import VN_TZ, parse_provider_timestamp
from modules.intraday_memory.validate import validate_raw_bar
from modules.live_candidate.calendar import as_vn

BAR_MINUTES = 5
STALE_MINUTES = 15


def is_completed_bar(bar_ts: datetime, now: datetime) -> bool:
    """bar_ts is the exchange slot open. Complete only after the 5m window ends."""
    bar = as_vn(bar_ts)
    now_l = as_vn(now)
    return now_l >= bar + timedelta(minutes=BAR_MINUTES)


def classify_stale(latest_completed: datetime | None, now: datetime) -> bool:
    if latest_completed is None:
        return False
    return as_vn(now) - as_vn(latest_completed) > timedelta(minutes=STALE_MINUTES + BAR_MINUTES)


def validate_live_records(
    symbol: str,
    records: list[dict[str, Any]],
    *,
    session_date,
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (completed_canonical, unfinished_or_rejected). Never invent OHLCV."""
    completed: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    seen: set[datetime] = set()
    for raw in records:
        outcome = validate_raw_bar(
            symbol,
            raw,
            collected_at=observed_at,
            expected_session_date=session_date,
        )
        if not outcome.accepted or outcome.bar is None:
            other.append({"reason": outcome.reason or "REJECTED", "raw_time": raw.get("time")})
            continue
        bar = outcome.bar
        if bar.timestamp in seen:
            continue
        seen.add(bar.timestamp)
        rec = {
            "symbol": bar.symbol,
            "bar_ts": bar.timestamp,
            "observed_at": observed_at,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "source": bar.source,
            "data_quality": bar.quality_flag,
            "session_date": bar.session_date,
        }
        if is_completed_bar(bar.timestamp, observed_at):
            completed.append(rec)
        else:
            other.append({"reason": "UNFINISHED", "bar_ts": bar.timestamp.isoformat()})
    completed.sort(key=lambda r: r["bar_ts"])
    return completed, other


def completed_to_overlay(completed: list[dict[str, Any]]) -> Any:
    import pandas as pd

    if not completed:
        return pd.DataFrame()
    rows = []
    for r in completed:
        ts = r["bar_ts"]
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=VN_TZ)
        rows.append(
            {
                "symbol": r["symbol"],
                "timestamp": ts,
                "session_date": r["session_date"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
                "source": r["source"],
                "collected_at": r["observed_at"],
                "quality_flag": r["data_quality"],
                "overlay_applied": False,
                "bar_source": "live_shadow",
            }
        )
    return pd.DataFrame(rows)
