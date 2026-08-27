"""
Development-only fixtures for OPR pipeline validation.

NOT used in Zone B blind evaluation. Injects empirical structure for Zone A tests only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def inject_dispersion_anomaly(
    panel: pd.DataFrame,
    *,
    focal_date: str,
    dispersion_feature: str = "rs_spread",
    outcome_field: str = "t5_return",
    seed: int = 42,
) -> pd.DataFrame:
    """
    Create a genuine cross-sectional dispersion anomaly on one date for dev testing.

    Modifies numeric columns only — no OBS/GAP labels. Used to verify OPR synthesis path.
    """
    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    mask = df["trade_date"] == str(focal_date)
    if not mask.any():
        return df

    rng = np.random.default_rng(seed)
    idx = df.index[mask]
    df.loc[idx, dispersion_feature] = rng.uniform(-15, 15, len(idx))
    ranks = df.loc[idx, dispersion_feature].rank(method="first")
    q = pd.qcut(ranks, 5, labels=False, duplicates="drop")
    df.loc[idx, outcome_field] = q.astype(float) * 2.5 - 3.0 + rng.normal(0, 0.2, len(idx))
    return df


def build_extended_dev_panel(
    base_panel: pd.DataFrame,
    *,
    n_dates: int = 30,
    symbols_per_date: int = 40,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Build multi-date cross-sectional panel for Zone A dev tests.

    Uses deterministic synthetic numeric data — NOT hidden benchmark phenomena.
    """
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:03d}" for i in range(symbols_per_date)]
    rows = []
    for day in range(n_dates):
        date = f"2026-01-{day + 1:02d}"
        for sym in symbols:
            rs = float(rng.normal(0, 5))
            rows.append(
                {
                    "trade_date": date,
                    "symbol": sym,
                    "rs_spread": rs,
                    "t5_return": float(rng.normal(0, 1)),
                    "t3_return": float(rng.normal(0, 1)),
                    "t10_return": float(rng.normal(0, 1)),
                }
            )
    df = pd.DataFrame(rows)
    focal = f"2026-01-{n_dates:02d}"
    return inject_dispersion_anomaly(df, focal_date=focal, seed=seed + 1)
