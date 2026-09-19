"""
Leakage-safe V2 research panel.

Reads production lifecycle/outcomes/market snapshots without writing them.
Keeps non-RS T0 columns that production build_research_panel drops.
Forward labels come from outcomes.csv only — never lifecycle t*_return_pct as features.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from modules.edge_research.adapters import (
    attach_outcomes_from_outcomes_csv,
    build_canonical_market_series,
    load_lifecycle,
)
from modules.edge_research.market_state import enrich_date_with_market_research
from modules.multifamily_discovery_v2.contracts import OUTCOME_COLUMNS

STOCK_FEATURE_COLUMNS: tuple[str, ...] = (
    "rs5",
    "rs10",
    "rsi14",
    "rs_spread",
    "obv_status",
    "obv",
    "obv_ema9",
    "volume",
    "vol_ma20",
    "volume_ratio20",
    "dryup",
    "ema9",
    "ma20",
    "ema9_ma20_slope",
    "ema9_ma20_slope_change",
    "price_vs_ema9_pct",
    "price_vs_ma20_pct",
    "dist_from_ema9_pct",
    "health_score",
    "health_rank",
    "health_group",
    "group",
    "group_rank",
    "total_score",
    "leader_score",
    "green2",
    "early",
    "pull",
    "rsi_slope",
)


def _normalize_obv_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"nan", "none", "null"}:
        return ""
    if any(tok in text for tok in ("🟢", "positive", "above", "strong", "dương", "duong")):
        return "POSITIVE"
    if any(tok in text for tok in ("🔴", "negative", "below", "weak", "âm", "giảm", "giam")):
        return "NEGATIVE"
    return ""


def _normalize_health_group(value: object) -> str:
    text = str(value or "").strip().lower()
    if "đang hồi" in text or "dang hoi" in text:
        return "RECOVERING"
    if "trung tính" in text or "trung tinh" in text:
        return "NEUTRAL"
    if "yếu dần" in text or "yeu dan" in text:
        return "WEAKENING"
    if "rất yếu" in text or "rat yeu" in text:
        return "VERY_WEAK"
    if "yếu" in text or "yeu" in text:
        return "WEAK"
    return ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    def _one(value: object) -> object:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return pd.NA
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        if text in {"", "nan", "none"}:
            return pd.NA
        return pd.NA

    return series.map(_one)


def _stock_frame(lifecycle: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    df = lifecycle.copy()
    date_col = "trade_date" if "trade_date" in df.columns else "entry_date"
    df["trade_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    df["symbol"] = df["symbol"].astype(str)
    df = df.dropna(subset=["trade_date", "symbol"])
    if start:
        df = df[df["trade_date"] >= start]
    if end:
        df = df[df["trade_date"] <= end]
    price_col = "price" if "price" in df.columns else "close"
    out = pd.DataFrame(
        {
            "trade_date": df["trade_date"],
            "symbol": df["symbol"],
            "close": pd.to_numeric(df.get(price_col), errors="coerce"),
        }
    )
    for col in STOCK_FEATURE_COLUMNS:
        if col == "rs_spread":
            continue
        if col in df.columns:
            if col in {"obv_status", "health_group", "group"}:
                out[col] = df[col]
            elif col in {"dryup", "green2", "early", "pull"}:
                out[col] = _coerce_bool(df[col])
            else:
                out[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            out[col] = np.nan
    if "rs_spread" in df.columns:
        out["rs_spread"] = pd.to_numeric(df["rs_spread"], errors="coerce")
    else:
        out["rs_spread"] = pd.to_numeric(out["rs5"], errors="coerce") - pd.to_numeric(
            out["rs10"], errors="coerce"
        )
    out["obv_status"] = out["obv_status"].map(_normalize_obv_status)
    out["health_group"] = out["health_group"].map(_normalize_health_group)
    leaked = [c for c in out.columns if c in OUTCOME_COLUMNS]
    if leaked:
        raise ValueError(f"V2 panel leaked outcome columns into features: {leaked}")
    return out.drop_duplicates(subset=["trade_date", "symbol"], keep="last")


def build_v2_panel(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    lifecycle: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Canonical V2 T0 panel with extra families. Read-only sources."""
    src = lifecycle.copy() if lifecycle is not None else load_lifecycle()
    stock = _stock_frame(src, start, end)
    if stock.empty:
        return stock

    market_canonical = build_canonical_market_series(start=start, end=end)
    if market_canonical.empty:
        market_series = pd.DataFrame(
            columns=["date", "market_real", "market_forecast", "breadth_score", "ambiguous"]
        )
    else:
        market_series = market_canonical[
            ["date", "market_real", "market_forecast", "breadth_score", "ambiguous"]
        ].copy()

    state_history: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    for trade_date, day_df in stock.groupby("trade_date", sort=True):
        market_fields = enrich_date_with_market_research(
            str(trade_date),
            market_series,
            day_df,
            state_history,
        )
        canon_row = market_canonical[market_canonical["date"] == trade_date] if not market_canonical.empty else pd.DataFrame()
        for _, srow in day_df.iterrows():
            row = dict(srow)
            row["market_real"] = market_fields.get("mr_t0")
            row["market_forecast"] = (
                None if canon_row.empty else canon_row.iloc[0].get("market_forecast")
            )
            row["breadth_score"] = market_fields.get("breadth_t0")
            row.update(market_fields)
            rows.append(row)

    panel = pd.DataFrame(rows)
    panel["t3_return"] = np.nan
    panel["t5_return"] = np.nan
    panel["t10_return"] = np.nan
    panel["outcome_source"] = "unavailable"
    panel["outcome_missing_reason"] = "ohlcv_not_provided"
    panel = attach_outcomes_from_outcomes_csv(panel)
    return panel.reset_index(drop=True)
