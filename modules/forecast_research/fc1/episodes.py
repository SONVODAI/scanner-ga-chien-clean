"""
FC-1 episode accounting — PIT-safe only (no future outcomes).

Episodes change when the same-day strength regime changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _regime_from_row(row: pd.Series) -> str:
    real = pd.to_numeric(row.get("market_real"), errors="coerce")
    if pd.notna(real):
        if float(real) >= 8.0:
            return "STRONG"
        if float(real) < 6.0:
            return "WEAK"
        return "MID"
    # Fallback: RSI breadth tertile proxy without looking ahead
    rsi = pd.to_numeric(row.get("rsi50_share"), errors="coerce")
    if pd.notna(rsi):
        if float(rsi) >= 0.55:
            return "STRONG"
        if float(rsi) < 0.35:
            return "WEAK"
        return "MID"
    return "UNKNOWN"


def assign_episodes(pit: pd.DataFrame) -> pd.DataFrame:
    """Append episode_id / regime_pit columns; episode increments on regime change."""
    df = pit.sort_values("trade_date").reset_index(drop=True).copy()
    regimes: List[str] = []
    episode_ids: List[int] = []
    eid = 0
    prev: Optional[str] = None
    for _, row in df.iterrows():
        reg = _regime_from_row(row)
        if prev is None:
            eid = 0
        elif reg != prev:
            eid += 1
        regimes.append(reg)
        episode_ids.append(eid)
        prev = reg
    df["regime_pit"] = regimes
    df["episode_id"] = episode_ids
    return df


def episode_summary(pit_with_episodes: pd.DataFrame, dates: Optional[List[str]] = None) -> Dict[str, Any]:
    df = pit_with_episodes
    if dates is not None:
        ds = set(str(d)[:10] for d in dates)
        df = df[df["trade_date"].astype(str).str[:10].isin(ds)]
    if df.empty:
        return {
            "date_count": 0,
            "episode_count": 0,
            "concentration_by_episode": {},
            "regime_switches": 0,
        }
    conc = df.groupby("episode_id").size().to_dict()
    conc = {str(k): int(v) for k, v in conc.items()}
    switches = int(df["episode_id"].nunique() - 1) if len(df) else 0
    return {
        "date_count": int(len(df)),
        "episode_count": int(df["episode_id"].nunique()),
        "concentration_by_episode": conc,
        "regime_switches": max(switches, 0),
        "regimes_present": sorted(df["regime_pit"].dropna().unique().tolist()),
    }


def direction_switches_from_labels(labels: pd.DataFrame, horizon: int = 3) -> int:
    """Count favorable_median flips across consecutive matured dates (reporting only)."""
    sub = labels[labels["horizon"] == horizon].sort_values("trade_date")
    if sub.empty or "favorable_median" not in sub.columns:
        return 0
    vals = pd.to_numeric(sub["favorable_median"], errors="coerce").dropna().astype(int).tolist()
    if len(vals) < 2:
        return 0
    return sum(1 for i in range(1, len(vals)) if vals[i] != vals[i - 1])
