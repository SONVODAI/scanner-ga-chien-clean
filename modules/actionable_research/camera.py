"""
VPS Camera activity evidence from 5-minute OHLCV.

Camera schema is price+volume only. No foreign buy/sell. No stored value column.
Session traded value is derived as sum(close * volume) and labeled as derived
activity / trading value — NEVER as directional money inflow/outflow.

PIT: bars with timestamp > cutoff are ignored.
Missing feed / missing symbol → UNKNOWN, never LOW/NORMAL.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Sequence

import pandas as pd

from modules.actionable_research.contracts import (
    ACCEL_BARS,
    ACTIVITY_HIGH_PERCENTILE,
    ACTIVITY_LOW_PERCENTILE,
    CAMERA_DATA_FEED_MISSING,
    CAMERA_DATA_INSUFFICIENT,
    CAMERA_DATA_MISSING_SYMBOL,
    CAMERA_DATA_OK,
    CAMERA_DATA_PARTIAL,
    CLOSE_LOCATION_UNKNOWN,
    CLOSE_MID,
    CLOSE_NEAR_HIGH,
    CLOSE_NEAR_HIGH_THRESHOLD,
    CLOSE_NEAR_LOW,
    CLOSE_NEAR_LOW_THRESHOLD,
    INTRADAY_ACTIVITY_HIGH,
    INTRADAY_ACTIVITY_LOW,
    INTRADAY_ACTIVITY_NORMAL,
    INTRADAY_ACTIVITY_UNKNOWN,
    MIN_CROSS_SECTION,
    PRICE_DIRECTION_DOWN,
    PRICE_DIRECTION_FLAT,
    PRICE_DIRECTION_UNKNOWN,
    PRICE_DIRECTION_UP,
    TRADING_VALUE_NORMAL,
    TRADING_VALUE_UNKNOWN,
    TRADING_VALUE_UNUSUALLY_HIGH,
    VOLUME_ACCEL_HIGH_RATIO,
    VOLUME_ACCELERATION_HIGH,
    VOLUME_ACCELERATION_NORMAL,
    VOLUME_ACCELERATION_UNKNOWN,
)
from modules.actionable_research.paths import FusionPaths
from modules.intraday_memory.storage import load_session
from modules.intraday_memory.timezone_policy import VN_TZ

ACTIVITY_PROVENANCE = (
    "VPS Camera 5-minute OHLCV (vnstock4_kbs). "
    "Derived session traded value = sum(close * volume). "
    "This measures approximate traded activity/value, not buy-flow or sell-flow. "
    "No foreign fields."
)


def _parse_cutoff(cutoff: Optional[datetime | str], trade_date: str) -> Optional[datetime]:
    if cutoff is None:
        return None
    if isinstance(cutoff, datetime):
        ts = cutoff
    else:
        raw = str(cutoff).strip()
        if not raw:
            return None
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=VN_TZ)
    return ts.astimezone(VN_TZ)


def default_session_cutoff(trade_date: str) -> datetime:
    """End of regular VN session — still PIT-safe; later-day bars never exist in Camera."""
    d = date.fromisoformat(str(trade_date)[:10])
    return datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=VN_TZ)


def load_camera_session(
    trade_date: str,
    *,
    paths: FusionPaths,
    cutoff: Optional[datetime | str] = None,
) -> Dict[str, Any]:
    d = date.fromisoformat(str(trade_date)[:10])
    root = paths.camera_data_root()
    partition = (
        root
        / "canonical"
        / f"year={d.year}"
        / f"month={d.month:02d}"
        / f"session_date={d.isoformat()}"
        / "bars.parquet"
    )
    if not partition.exists():
        return {
            "feed_status": CAMERA_DATA_FEED_MISSING,
            "bars": pd.DataFrame(),
            "cutoff": _parse_cutoff(cutoff, trade_date) or default_session_cutoff(trade_date),
            "source": str(partition),
            "bars_before_filter": 0,
            "bars_used": 0,
        }
    try:
        bars = load_session(root, d)
    except Exception:
        return {
            "feed_status": CAMERA_DATA_FEED_MISSING,
            "bars": pd.DataFrame(),
            "cutoff": _parse_cutoff(cutoff, trade_date) or default_session_cutoff(trade_date),
            "source": str(partition),
            "bars_before_filter": 0,
            "bars_used": 0,
        }
    cutoff_ts = _parse_cutoff(cutoff, trade_date)
    before = 0 if bars.empty else int(len(bars))
    if bars.empty:
        return {
            "feed_status": CAMERA_DATA_FEED_MISSING,
            "bars": bars,
            "cutoff": cutoff_ts or default_session_cutoff(trade_date),
            "source": str(partition),
            "bars_before_filter": 0,
            "bars_used": 0,
        }
    work = bars.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=False)
    if work["timestamp"].dt.tz is None:
        work["timestamp"] = work["timestamp"].dt.tz_localize(VN_TZ)
    else:
        work["timestamp"] = work["timestamp"].dt.tz_convert(VN_TZ)
    if cutoff_ts is not None:
        work = work[work["timestamp"] <= cutoff_ts]
    else:
        cutoff_ts = work["timestamp"].max().to_pydatetime()
    if "quality_flag" in work.columns:
        work = work[work["quality_flag"].astype(str).str.lower() != "rejected"]
    used = int(len(work))
    feed_status = CAMERA_DATA_OK if used > 0 else CAMERA_DATA_FEED_MISSING
    return {
        "feed_status": feed_status,
        "bars": work,
        "cutoff": cutoff_ts,
        "source": str(partition),
        "bars_before_filter": before,
        "bars_used": used,
        "look_ahead_bars_dropped": max(0, before - used),
    }


def _close_location(first_open: Optional[float], last_close: Optional[float], high: Optional[float], low: Optional[float]) -> str:
    if last_close is None:
        return CLOSE_LOCATION_UNKNOWN
    session_high = high
    session_low = low
    if session_high is None or session_low is None:
        if first_open is None:
            return CLOSE_LOCATION_UNKNOWN
        session_high = max(first_open, last_close)
        session_low = min(first_open, last_close)
    span = float(session_high) - float(session_low)
    if span <= 0:
        return CLOSE_MID
    loc = (float(last_close) - float(session_low)) / span
    if loc >= CLOSE_NEAR_HIGH_THRESHOLD:
        return CLOSE_NEAR_HIGH
    if loc <= CLOSE_NEAR_LOW_THRESHOLD:
        return CLOSE_NEAR_LOW
    return CLOSE_MID


def _symbol_metrics(sym_bars: pd.DataFrame) -> Dict[str, Any]:
    if sym_bars.empty:
        return {}
    ordered = sym_bars.sort_values("timestamp")
    volume = pd.to_numeric(ordered["volume"], errors="coerce").fillna(0.0)
    close = pd.to_numeric(ordered["close"], errors="coerce")
    derived_value = (close * volume).fillna(0.0)
    n = int(len(ordered))
    last_n = volume.iloc[-ACCEL_BARS:] if n else volume
    prior_n = volume.iloc[-2 * ACCEL_BARS : -ACCEL_BARS] if n >= ACCEL_BARS * 2 else volume.iloc[: max(n // 2, 1)]
    last_sum = float(last_n.sum())
    prior_sum = float(prior_n.sum()) if len(prior_n) else 0.0
    accel = (last_sum / prior_sum) if prior_sum > 0 else None
    last_close = float(close.iloc[-1]) if close.notna().any() else None
    first_open = None
    if "open" in ordered.columns:
        opens = pd.to_numeric(ordered["open"], errors="coerce")
        if opens.notna().any():
            first_open = float(opens.iloc[0])
    if first_open is None and close.notna().any():
        first_open = float(close.iloc[0])
    high = None
    low = None
    if "high" in ordered.columns:
        highs = pd.to_numeric(ordered["high"], errors="coerce")
        if highs.notna().any():
            high = float(highs.max())
    if "low" in ordered.columns:
        lows = pd.to_numeric(ordered["low"], errors="coerce")
        if lows.notna().any():
            low = float(lows.min())
    session_return_pct = None
    direction = PRICE_DIRECTION_UNKNOWN
    if first_open is not None and last_close is not None and first_open != 0:
        session_return_pct = (last_close / first_open - 1.0) * 100.0
        if last_close > first_open:
            direction = PRICE_DIRECTION_UP
        elif last_close < first_open:
            direction = PRICE_DIRECTION_DOWN
        else:
            direction = PRICE_DIRECTION_FLAT
    last_ts = ordered["timestamp"].iloc[-1]
    last_ts_s = last_ts.isoformat() if hasattr(last_ts, "isoformat") else str(last_ts)
    accel_status = VOLUME_ACCELERATION_UNKNOWN
    if accel is None:
        accel_status = VOLUME_ACCELERATION_UNKNOWN
    elif accel >= VOLUME_ACCEL_HIGH_RATIO:
        accel_status = VOLUME_ACCELERATION_HIGH
    else:
        accel_status = VOLUME_ACCELERATION_NORMAL
    return {
        "bar_count": n,
        "session_volume": float(volume.sum()),
        "session_value_derived": float(derived_value.sum()),
        "first_open": first_open,
        "last_close": last_close,
        "session_high": high,
        "session_low": low,
        "session_return_pct": session_return_pct,
        "price_direction": direction,
        "close_location": _close_location(first_open, last_close, high, low),
        "volume_acceleration_ratio": accel,
        "volume_acceleration_status": accel_status,
        "last_bar_timestamp": last_ts_s,
        "value_derivation": (
            "sum(close * volume) from Camera OHLCV; approximate traded value/activity. "
            "Not directional money inflow or outflow. Value is not a stored Camera field."
        ),
        "direction_note": (
            "price_direction is session open→close on Camera OHLCV. "
            "Conservative price-path observation, not buy-flow/sell-flow."
        ),
    }


def _missing_symbol_payload(cutoff_iso: str, source: str, *, feed_missing: bool) -> Dict[str, Any]:
    status = CAMERA_DATA_FEED_MISSING if feed_missing else CAMERA_DATA_MISSING_SYMBOL
    note = (
        "CAMERA_DATA_MISSING — not INTRADAY_ACTIVITY_LOW / NORMAL."
        if feed_missing
        else "CAMERA_DATA_MISSING — symbol has no bars <= cutoff. Not INTRADAY_ACTIVITY_LOW / NORMAL."
    )
    return {
        "camera_data_status": status,
        "camera_cutoff_timestamp": cutoff_iso,
        "activity_status": INTRADAY_ACTIVITY_UNKNOWN,
        "trading_value_status": TRADING_VALUE_UNKNOWN,
        "volume_acceleration_status": VOLUME_ACCELERATION_UNKNOWN,
        "price_direction": PRICE_DIRECTION_UNKNOWN,
        "close_location": CLOSE_LOCATION_UNKNOWN,
        "metrics": {},
        "source": source,
        "provenance": ACTIVITY_PROVENANCE,
        "note": note,
    }


def classify_intraday_activity(
    trade_date: str,
    symbols: Sequence[str],
    *,
    paths: FusionPaths,
    cutoff: Optional[datetime | str] = None,
    camera_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bundle = camera_bundle or load_camera_session(trade_date, paths=paths, cutoff=cutoff)
    cutoff_ts = bundle.get("cutoff")
    cutoff_iso = cutoff_ts.isoformat() if hasattr(cutoff_ts, "isoformat") else str(cutoff_ts or "")
    source = str(bundle.get("source") or "intraday_memory")
    feed = str(bundle.get("feed_status") or CAMERA_DATA_FEED_MISSING)
    bars: pd.DataFrame = bundle.get("bars") if isinstance(bundle.get("bars"), pd.DataFrame) else pd.DataFrame()

    per_symbol: Dict[str, Dict[str, Any]] = {}
    if feed == CAMERA_DATA_FEED_MISSING or bars is None or bars.empty:
        for raw in symbols:
            symbol = str(raw).upper()
            per_symbol[symbol] = _missing_symbol_payload(cutoff_iso, source, feed_missing=True)
        return {
            "feed_status": CAMERA_DATA_FEED_MISSING,
            "cutoff": cutoff_iso,
            "source": source,
            "cross_section_n": 0,
            "by_symbol": per_symbol,
            "look_ahead_bars_dropped": int(bundle.get("look_ahead_bars_dropped") or 0),
        }

    metrics_map: Dict[str, Dict[str, Any]] = {}
    values = []
    for raw in symbols:
        symbol = str(raw).upper()
        if "symbol" not in bars.columns:
            sym_bars = pd.DataFrame()
        else:
            sym_bars = bars[bars["symbol"].astype(str).str.upper() == symbol]
        if sym_bars.empty:
            metrics_map[symbol] = {}
            continue
        m = _symbol_metrics(sym_bars)
        metrics_map[symbol] = m
        values.append((symbol, float(m.get("session_value_derived") or 0.0)))

    cross_n = len(values)
    percentiles: Dict[str, float] = {}
    if cross_n >= MIN_CROSS_SECTION:
        series = pd.Series({s: v for s, v in values})
        ranks = series.rank(method="average", pct=True) * 100.0
        percentiles = {str(k): float(v) for k, v in ranks.items()}

    for raw in symbols:
        symbol = str(raw).upper()
        m = metrics_map.get(symbol) or {}
        if not m:
            per_symbol[symbol] = _missing_symbol_payload(cutoff_iso, source, feed_missing=False)
            continue
        if cross_n < MIN_CROSS_SECTION:
            activity = INTRADAY_ACTIVITY_UNKNOWN
            trading_value = TRADING_VALUE_UNKNOWN
            cam_status = CAMERA_DATA_INSUFFICIENT
            note = "INSUFFICIENT_CROSS_SECTION — not converted to LOW/NORMAL."
        else:
            pct = percentiles.get(symbol)
            m["session_value_percentile"] = pct
            if pct is None:
                activity = INTRADAY_ACTIVITY_UNKNOWN
                trading_value = TRADING_VALUE_UNKNOWN
                cam_status = CAMERA_DATA_PARTIAL
                note = "Percentile unavailable."
            elif pct >= ACTIVITY_HIGH_PERCENTILE:
                activity = INTRADAY_ACTIVITY_HIGH
                trading_value = TRADING_VALUE_UNUSUALLY_HIGH
                cam_status = CAMERA_DATA_OK
                note = (
                    "Universe-relative derived session traded value (close*volume). "
                    "Activity/value observation — not money inflow."
                )
            elif pct <= ACTIVITY_LOW_PERCENTILE:
                activity = INTRADAY_ACTIVITY_LOW
                trading_value = TRADING_VALUE_NORMAL
                cam_status = CAMERA_DATA_OK
                note = (
                    "Universe-relative derived session traded value (close*volume). "
                    "Low activity — not money outflow."
                )
            else:
                activity = INTRADAY_ACTIVITY_NORMAL
                trading_value = TRADING_VALUE_NORMAL
                cam_status = CAMERA_DATA_OK
                note = "Universe-relative derived session traded value (close*volume)."
        per_symbol[symbol] = {
            "camera_data_status": cam_status,
            "camera_cutoff_timestamp": cutoff_iso,
            "activity_status": activity,
            "trading_value_status": trading_value,
            "volume_acceleration_status": m.get("volume_acceleration_status")
            or VOLUME_ACCELERATION_UNKNOWN,
            "price_direction": m.get("price_direction") or PRICE_DIRECTION_UNKNOWN,
            "close_location": m.get("close_location") or CLOSE_LOCATION_UNKNOWN,
            "metrics": m,
            "source": source,
            "provenance": ACTIVITY_PROVENANCE,
            "note": note,
        }

    return {
        "feed_status": CAMERA_DATA_OK,
        "cutoff": cutoff_iso,
        "source": source,
        "cross_section_n": cross_n,
        "by_symbol": per_symbol,
        "look_ahead_bars_dropped": int(bundle.get("look_ahead_bars_dropped") or 0),
    }


# Back-compat alias for older call sites / tests that imported the previous name.
classify_money_flow = classify_intraday_activity
