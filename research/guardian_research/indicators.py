"""Indicator inputs Guardian already consumes. No download and no live injection."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.guardian_research.contract import (
    EMA_MA_DIGITS,
    MINIMUM_DAILY_BARS,
    OBV_DIGITS,
    PRICE_DIGITS,
)


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).fillna(0).cumsum()


def safe_round(value, digits=2):
    try:
        if pd.isna(value):
            return np.nan
        return round(float(value), digits)
    except Exception:
        return np.nan


def finite_number(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def scan_fields_from_daily(frame: pd.DataFrame) -> dict:
    """Last-bar Guardian inputs from a daily frame, without live-price injection.

    Rounding matches analyze_symbol: price and OBV to 0 digits, EMA9 and MA20 to 2.
    The caller still has to prove session, provenance, and quality before classification.
    """
    if frame is None or len(frame) < MINIMUM_DAILY_BARS:
        return {
            "ok": False,
            "reason": "INSUFFICIENT_HISTORY",
            "bar_count": 0 if frame is None else int(len(frame)),
        }
    if "close" not in frame.columns:
        return {"ok": False, "reason": "INPUT_INCOMPLETE", "bar_count": int(len(frame))}
    work = frame.copy()
    close = pd.to_numeric(work["close"], errors="coerce")
    if "volume" in work.columns:
        volume = pd.to_numeric(work["volume"], errors="coerce")
        obv = calc_obv(close, volume)
        obv_ema9 = ema(obv, 9)
    else:
        obv = pd.Series(np.nan, index=work.index)
        obv_ema9 = pd.Series(np.nan, index=work.index)
    ema9 = ema(close, 9)
    ma20 = sma(close, 20)
    last = len(work) - 1
    bar_date = work["date"].iloc[last] if "date" in work.columns else None
    return {
        "ok": True,
        "reason": None,
        "bar_count": int(len(work)),
        "bar_date": bar_date,
        "price": safe_round(close.iloc[last], PRICE_DIGITS),
        "ema9": safe_round(ema9.iloc[last], EMA_MA_DIGITS),
        "ma20": safe_round(ma20.iloc[last], EMA_MA_DIGITS),
        "obv": safe_round(obv.iloc[last], OBV_DIGITS),
        "obv_ema9": safe_round(obv_ema9.iloc[last], OBV_DIGITS),
        "live_injected": False,
    }
