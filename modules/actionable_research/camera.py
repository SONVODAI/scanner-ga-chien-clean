"""
VPS Camera money-flow evidence from 5-minute OHLCV.

Camera schema is price+volume only. No foreign buy/sell. No stored value column.
Session value is derived as close * volume and labeled as derived.
PIT: bars with timestamp > cutoff are ignored.
Missing feed / missing symbol → UNKNOWN, never WEAK/NORMAL.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Sequence

import pandas as pd

from modules.actionable_research.contracts import (
    ACCEL_BARS,
    CAMERA_DATA_FEED_MISSING,
    CAMERA_DATA_INSUFFICIENT,
    CAMERA_DATA_MISSING_SYMBOL,
    CAMERA_DATA_OK,
    CAMERA_DATA_PARTIAL,
    MIN_CROSS_SECTION,
    MONEY_FLOW_NORMAL,
    MONEY_FLOW_STRONG,
    MONEY_FLOW_STRONG_PERCENTILE,
    MONEY_FLOW_UNKNOWN,
    MONEY_FLOW_WEAK,
    MONEY_FLOW_WEAK_PERCENTILE,
)
from modules.actionable_research.paths import FusionPaths
from modules.intraday_memory.storage import load_session
from modules.intraday_memory.timezone_policy import VN_TZ


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
    last_ts = ordered["timestamp"].iloc[-1]
    last_ts_s = last_ts.isoformat() if hasattr(last_ts, "isoformat") else str(last_ts)
    return {
        "bar_count": n,
        "session_volume": float(volume.sum()),
        "session_value_derived": float(derived_value.sum()),
        "last_close": last_close,
        "volume_acceleration_ratio": accel,
        "last_bar_timestamp": last_ts_s,
        "value_derivation": "sum(close * volume) from Camera OHLCV; value is not a stored Camera field",
    }


def classify_money_flow(
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
            per_symbol[symbol] = {
                "camera_data_status": CAMERA_DATA_FEED_MISSING,
                "camera_cutoff_timestamp": cutoff_iso,
                "money_flow_status": MONEY_FLOW_UNKNOWN,
                "metrics": {},
                "source": source,
                "provenance": "VPS Camera 5-minute OHLCV (vnstock4_kbs). No foreign fields.",
                "note": "CAMERA_DATA_MISSING — not MONEY_FLOW_WEAK / NORMAL.",
            }
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
            per_symbol[symbol] = {
                "camera_data_status": CAMERA_DATA_MISSING_SYMBOL,
                "camera_cutoff_timestamp": cutoff_iso,
                "money_flow_status": MONEY_FLOW_UNKNOWN,
                "metrics": {},
                "source": source,
                "provenance": "VPS Camera 5-minute OHLCV. Symbol has no bars <= cutoff.",
                "note": "CAMERA_DATA_MISSING — not MONEY_FLOW_WEAK / NORMAL.",
            }
            continue
        if cross_n < MIN_CROSS_SECTION:
            status = MONEY_FLOW_UNKNOWN
            cam_status = CAMERA_DATA_INSUFFICIENT
            note = "INSUFFICIENT_CROSS_SECTION — not converted to WEAK/NORMAL."
        else:
            pct = percentiles.get(symbol)
            m["session_value_percentile"] = pct
            if pct is None:
                status = MONEY_FLOW_UNKNOWN
                cam_status = CAMERA_DATA_PARTIAL
                note = "Percentile unavailable."
            elif pct >= MONEY_FLOW_STRONG_PERCENTILE:
                status = MONEY_FLOW_STRONG
                cam_status = CAMERA_DATA_OK
                note = "Universe-relative session value (derived close*volume)."
            elif pct <= MONEY_FLOW_WEAK_PERCENTILE:
                status = MONEY_FLOW_WEAK
                cam_status = CAMERA_DATA_OK
                note = "Universe-relative session value (derived close*volume)."
            else:
                status = MONEY_FLOW_NORMAL
                cam_status = CAMERA_DATA_OK
                note = "Universe-relative session value (derived close*volume)."
        per_symbol[symbol] = {
            "camera_data_status": cam_status,
            "camera_cutoff_timestamp": cutoff_iso,
            "money_flow_status": status,
            "metrics": m,
            "source": source,
            "provenance": "VPS Camera 5-minute OHLCV (price, volume). Value derived. No foreign.",
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
