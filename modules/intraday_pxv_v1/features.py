"""Five approved feature families. Invalid families are OMITTED (not zero-filled)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.constants import (
    DATA_LOW,
    DATA_QUALIFIED,
    RESEARCH_DEFAULT_CONTRACTION_X,
    RESEARCH_DEFAULT_EXPANSION_X,
    RESEARCH_DEFAULT_PACE_AHEAD_X,
    RESEARCH_DEFAULT_SESSION_MEDIAN_BARS,
    TOD_PRELIMINARY,
)
from modules.intraday_pxv_v1.gate import GATE_CUMULATIVE, GATE_INTERVAL, GateResult

FAM_TOD_RVOL = "tod_relative_volume"
FAM_PACE = "cumulative_pace"
FAM_EXPANSION = "volume_expansion"
FAM_PXV = "price_volume"
FAM_SELL = "selling_pressure_expansion"

PXV_CONFIRMING = "CONFIRMING"
PXV_WEAK = "WEAK"
PXV_SELL_EXP = "SELL_EXPANSION"
PXV_NEUTRAL = "FLAT"


def _slot(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(VN_TZ)
    return t.strftime("%H:%M")


def _asof_bar(bars: pd.DataFrame, asof: datetime) -> pd.Series | None:
    ts = pd.Timestamp(asof)
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    work = bars[bars["timestamp"] <= ts]
    if work.empty:
        return None
    return work.iloc[-1]


def compute_features(
    bars: pd.DataFrame,
    gate: GateResult,
    *,
    asof: datetime,
    tod_rvol_baseline: float | None,
    tod_pace_baseline: float | None,
) -> dict[str, Any]:
    """Return only families the gate allows. No zeros for invalid families."""
    out: dict[str, Any] = {}
    if not gate.usable_volume:
        return out

    work = bars.sort_values("timestamp").reset_index(drop=True)
    ts = pd.Timestamp(asof)
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    work = work[work["timestamp"] <= ts].reset_index(drop=True)
    if work.empty:
        return out

    last = work.iloc[-1]
    vol = float(pd.to_numeric(last["volume"], errors="coerce") or 0.0)
    close = float(pd.to_numeric(last["close"], errors="coerce") or 0.0)
    open_ = float(pd.to_numeric(last["open"], errors="coerce") or 0.0)
    high = float(pd.to_numeric(last.get("high", close), errors="coerce") or close)
    low = float(pd.to_numeric(last.get("low", close), errors="coerce") or close)
    real_range = high > low and close != open_

    if gate.volume_kind == GATE_INTERVAL:
        cum = float(pd.to_numeric(work["volume"], errors="coerce").fillna(0).sum())
    elif gate.volume_kind == GATE_CUMULATIVE:
        cum = vol
    else:
        cum = None

    # 1. same-TOD RVOL — increment only; preliminary at <20 sessions
    if gate.allow_increments and tod_rvol_baseline is not None and tod_rvol_baseline > 0:
        out[FAM_TOD_RVOL] = {
            "value": vol / tod_rvol_baseline,
            "confidence": DATA_LOW if gate.tod_maturity == TOD_PRELIMINARY else DATA_QUALIFIED,
            "tod_maturity": gate.tod_maturity,
            "research_default": True,
            "baseline": tod_rvol_baseline,
        }

    # 2. cumulative pace
    if gate.allow_cumulative_pace and cum is not None and tod_pace_baseline is not None and tod_pace_baseline > 0:
        out[FAM_PACE] = {
            "value": cum / tod_pace_baseline,
            "confidence": DATA_LOW if gate.tod_maturity == TOD_PRELIMINARY else DATA_QUALIFIED,
            "tod_maturity": gate.tod_maturity,
            "research_default": True,
            "baseline": tod_pace_baseline,
            "cumulative_used": cum,
        }

    expansion_flag = None
    contraction_flag = None
    # 3. 5m expansion vs same-session prior bars — interval only
    if gate.allow_increments and len(work) >= 2:
        k = RESEARCH_DEFAULT_SESSION_MEDIAN_BARS
        prior = pd.to_numeric(work["volume"], errors="coerce").iloc[max(0, len(work) - 1 - k): -1]
        sess_med = float(prior.median()) if len(prior) else None
        if sess_med is not None and sess_med > 0:
            ratio = vol / sess_med
            expansion_flag = ratio >= RESEARCH_DEFAULT_EXPANSION_X
            contraction_flag = ratio <= RESEARCH_DEFAULT_CONTRACTION_X
            out[FAM_EXPANSION] = {
                "value": ratio,
                "state": (
                    "EXPANSION" if expansion_flag else ("CONTRACTION" if contraction_flag else "NORMAL")
                ),
                "confidence": DATA_QUALIFIED,
                "research_default": True,
                "threshold_expansion": RESEARCH_DEFAULT_EXPANSION_X,
                "threshold_contraction": RESEARCH_DEFAULT_CONTRACTION_X,
            }

    # 4–5. P×V and selling pressure require a real candle and increment volume
    if gate.allow_increments and real_range and expansion_flag is not None:
        up = close > open_
        down = close < open_
        near_high = (high - low) > 0 and (close - low) / (high - low) >= 0.7
        if up and expansion_flag:
            pxv_state = PXV_CONFIRMING
        elif up and contraction_flag:
            pxv_state = PXV_WEAK
        elif down and expansion_flag:
            pxv_state = PXV_SELL_EXP
        else:
            pxv_state = PXV_NEUTRAL
        out[FAM_PXV] = {
            "state": pxv_state,
            "confidence": DATA_QUALIFIED,
            "up_bar": up,
            "down_bar": down,
            "near_high": bool(near_high),
            "price_change_pct": ((close / open_) - 1.0) * 100.0 if open_ else None,
            "research_default": True,
        }
        if down and expansion_flag:
            out[FAM_SELL] = {
                "state": True,
                "confidence": DATA_QUALIFIED,
                "research_default": True,
            }

    return out


def pace_ahead(features: dict[str, Any]) -> bool:
    fam = features.get(FAM_PACE)
    if not fam:
        return False
    return float(fam["value"]) >= RESEARCH_DEFAULT_PACE_AHEAD_X
