"""
Indicator helpers mirroring Mr.BOT app.py definitions (research-only copy).

Avoids importing app.py (Streamlit dependency).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """app.py calc_rsi L291-299."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_rs5(close: pd.Series) -> pd.Series:
    """app.py build_indicators L1229."""
    return ((close / close.shift(5)) - 1) * 100


def calc_rs10(close: pd.Series) -> pd.Series:
    """app.py build_indicators L1230."""
    return ((close / close.shift(10)) - 1) * 100


def calc_rs_spread(rs5: pd.Series, rs10: pd.Series) -> pd.Series:
    """earning_learning._adapt_board L1104-1106."""
    return rs5 - rs10


def build_stock_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add rsi14, rs5, rs10, rs_spread to OHLCV frame sorted by date."""
    out = df.sort_values("date").copy()
    out["rsi14"] = calc_rsi(out["close"], 14)
    out["rs5"] = calc_rs5(out["close"])
    out["rs10"] = calc_rs10(out["close"])
    out["rs_spread"] = calc_rs_spread(out["rs5"], out["rs10"])
    return out
