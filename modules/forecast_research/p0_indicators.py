"""Deterministic VNINDEX technical indicators (no future bars)."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


def rsi14(closes: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI; NaN until enough history. avg_loss==0 with gain → 100."""
    c = pd.to_numeric(closes, errors="coerce").astype(float)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # Pure uptrend: loss average is 0 → RSI = 100
    out = out.mask((avg_loss == 0) & avg_gain.notna() & (avg_gain > 0), 100.0)
    # Pure downtrend: gain average is 0 → RSI = 0
    out = out.mask((avg_gain == 0) & avg_loss.notna() & (avg_loss > 0), 0.0)
    out = out.where(avg_gain.notna() & avg_loss.notna())
    return out


def macd_line_signal_hist(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, pd.Series]:
    c = pd.to_numeric(closes, errors="coerce").astype(float)
    ema_fast = c.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = c.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd - sig
    return {"macd": macd, "macd_signal": sig, "macd_histogram": hist}


def bollinger(
    closes: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> Dict[str, pd.Series]:
    c = pd.to_numeric(closes, errors="coerce").astype(float)
    mid = c.rolling(period, min_periods=period).mean()
    std = c.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    position = (c - lower) / (upper - lower).replace(0.0, np.nan)
    return {
        "bb_middle": mid,
        "bb_upper": upper,
        "bb_lower": lower,
        "bb_width": width,
        "bb_position": position,
    }


def indicators_asof(closes: pd.Series, asof_index: int) -> Dict[str, Optional[float]]:
    """
    Compute indicators using closes[:asof_index+1] only (no future bars).
    Returns last values at asof_index.
    """
    if asof_index < 0 or asof_index >= len(closes):
        return {
            "vnindex_rsi14": None,
            "vnindex_macd": None,
            "vnindex_macd_signal": None,
            "vnindex_macd_histogram": None,
            "vnindex_bb_middle": None,
            "vnindex_bb_upper": None,
            "vnindex_bb_lower": None,
            "vnindex_bb_width": None,
            "vnindex_bb_position": None,
        }
    hist = closes.iloc[: asof_index + 1]
    r = rsi14(hist)
    m = macd_line_signal_hist(hist)
    b = bollinger(hist)

    def last(s: pd.Series) -> Optional[float]:
        v = s.iloc[-1]
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return None
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return None
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv

    return {
        "vnindex_rsi14": last(r),
        "vnindex_macd": last(m["macd"]),
        "vnindex_macd_signal": last(m["macd_signal"]),
        "vnindex_macd_histogram": last(m["macd_histogram"]),
        "vnindex_bb_middle": last(b["bb_middle"]),
        "vnindex_bb_upper": last(b["bb_upper"]),
        "vnindex_bb_lower": last(b["bb_lower"]),
        "vnindex_bb_width": last(b["bb_width"]),
        "vnindex_bb_position": last(b["bb_position"]),
    }
