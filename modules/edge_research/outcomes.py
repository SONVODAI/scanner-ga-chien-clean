"""
Trading-session forward outcomes for Edge Research.

T+n = close at +n TRADING SESSIONS (not observation rows, not calendar days).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_HORIZONS: Tuple[int, ...] = (3, 5, 10)


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Expect columns date, close; return sorted normalized frame."""
    if df.empty:
        return df.copy()
    out = df.copy()
    if "date" not in out.columns:
        raise ValueError("OHLCV frame must include 'date' column")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "close"])
    out = out.sort_values("date", kind="stable").drop_duplicates(subset=["date"], keep="last")
    return out.reset_index(drop=True)


def forward_return_at_index(
    closes: pd.Series,
    t0_index: int,
    horizon: int,
) -> Optional[float]:
    """
    return_Tn = (close_T+n / close_T0 - 1) * 100
    Returns None when future session unavailable.
    """
    future_index = t0_index + horizon
    if future_index >= len(closes):
        return None
    c0 = closes.iloc[t0_index]
    cn = closes.iloc[future_index]
    if pd.isna(c0) or pd.isna(cn) or float(c0) == 0:
        return None
    return float((float(cn) / float(c0) - 1.0) * 100.0)


def compute_trading_session_outcomes(
    ohlcv: pd.DataFrame,
    t0_date: pd.Timestamp,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> Dict[str, Any]:
    """
    Compute T3/T5/T10 from per-symbol trading sessions.

    Returns dict with t3_return, t5_return, t10_return, outcome_source,
    outcome_missing_reason.
    """
    frame = normalize_ohlcv(ohlcv)
    if frame.empty:
        return {
            "t3_return": np.nan,
            "t5_return": np.nan,
            "t10_return": np.nan,
            "outcome_source": "unavailable",
            "outcome_missing_reason": "empty_ohlcv",
        }

    t0 = pd.Timestamp(t0_date).normalize()
    matches = frame.index[frame["date"] == t0].tolist()
    if not matches:
        return {
            "t3_return": np.nan,
            "t5_return": np.nan,
            "t10_return": np.nan,
            "outcome_source": "unavailable",
            "outcome_missing_reason": "t0_date_not_in_series",
        }

    t0_idx = int(matches[0])
    closes = frame["close"]
    result: Dict[str, Any] = {
        "outcome_source": "ohlcv_trading_sessions",
        "outcome_missing_reason": "",
    }
    missing: list[str] = []
    for h in horizons:
        key = f"t{h}_return"
        val = forward_return_at_index(closes, t0_idx, h)
        if val is None:
            result[key] = np.nan
            missing.append(f"T{h}")
        else:
            result[key] = val
    if missing:
        result["outcome_missing_reason"] = "missing_sessions:" + ",".join(missing)
    return result


def attach_outcomes_to_panel(
    panel: pd.DataFrame,
    ohlcv_by_symbol: Dict[str, pd.DataFrame],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """
    Attach trading-session outcomes to a panel with trade_date, symbol.

    Does NOT use lifecycle t*_return_pct columns (observation-row semantics).
    """
    if panel.empty:
        return panel.copy()

    out = panel.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.normalize()

    t3_list: list = []
    t5_list: list = []
    t10_list: list = []
    sources: list = []
    reasons: list = []

    for _, row in out.iterrows():
        sym = str(row["symbol"])
        t0 = row["trade_date"]
        ohlcv = ohlcv_by_symbol.get(sym)
        if ohlcv is None or ohlcv.empty:
            t3_list.append(np.nan)
            t5_list.append(np.nan)
            t10_list.append(np.nan)
            sources.append("unavailable")
            reasons.append("no_ohlcv_for_symbol")
            continue
        computed = compute_trading_session_outcomes(ohlcv, t0, horizons=horizons)
        t3_list.append(computed.get("t3_return", np.nan))
        t5_list.append(computed.get("t5_return", np.nan))
        t10_list.append(computed.get("t10_return", np.nan))
        sources.append(computed.get("outcome_source", "unavailable"))
        reasons.append(computed.get("outcome_missing_reason", ""))

    out["t3_return"] = t3_list
    out["t5_return"] = t5_list
    out["t10_return"] = t10_list
    out["outcome_source"] = sources
    out["outcome_missing_reason"] = reasons
    return out
