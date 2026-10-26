"""Frozen feature evaluators — exact V1 definitions (confirmation only)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def rolling_z_60(net: pd.Series) -> pd.Series:
    m = net.rolling(60, min_periods=60).mean()
    sd = net.rolling(60, min_periods=60).std(ddof=0)
    return (net - m) / sd.replace(0, np.nan)


def abn_abs_z20(net: pd.Series) -> pd.Series:
    """Trigger series: 1.0 where |net_z_60| > 2.0; NaN where lookback incomplete."""
    z = rolling_z_60(net)
    out = (z.abs() > 2.0).astype(float)
    out = out.where(z.notna(), np.nan)
    return out


def net_pct_252(net: pd.Series) -> pd.Series:
    return net.rolling(252, min_periods=252).rank(pct=True)


def net_hi_pct90(net: pd.Series) -> pd.Series:
    pct = net_pct_252(net)
    out = (pct >= 0.90).astype(float)
    out = out.where(pct.notna(), np.nan)
    return out


def net_streak(net: pd.Series) -> pd.Series:
    signs = np.sign(net.fillna(0.0).to_numpy())
    out = np.zeros(len(signs), dtype=int)
    for i, v in enumerate(signs):
        if i == 0 or v == 0 or v != signs[i - 1]:
            out[i] = int(v)
        else:
            prev = out[i - 1]
            out[i] = prev + int(np.sign(prev) or v)
    return pd.Series(out, index=net.index)


def streak_neg_le_m5(net: pd.Series) -> pd.Series:
    st = net_streak(net)
    return (st <= -5).astype(float)


FEATURE_FNS = {
    "abn_abs_z20": abn_abs_z20,
    "net_hi_pct90": net_hi_pct90,
    "streak_neg_le_m5": streak_neg_le_m5,
}


def intermediate_value(feature: str, net: pd.Series) -> Optional[float]:
    """Last-row intermediate for logging (not the 0/1 trigger alone)."""
    if len(net) == 0:
        return None
    if feature == "abn_abs_z20":
        z = rolling_z_60(net)
        v = z.iloc[-1]
        return None if pd.isna(v) else float(abs(v))
    if feature == "net_hi_pct90":
        v = net_pct_252(net).iloc[-1]
        return None if pd.isna(v) else float(v)
    if feature == "streak_neg_le_m5":
        return float(net_streak(net).iloc[-1])
    raise KeyError(feature)
