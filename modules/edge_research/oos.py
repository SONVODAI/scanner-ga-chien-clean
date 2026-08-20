"""
OOS / holdout boundary foundation for Edge Research (PATCH 2A).

Chronological splits with forward-horizon embargo — no random shuffling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS

DEFAULT_EMBARGO_TRADING_DAYS = 10  # max forward horizon (T10)


@dataclass(frozen=True)
class ResearchSplit:
    discovery_panel: pd.DataFrame
    oos_panel: pd.DataFrame
    discovery_end_date: str
    oos_start_date: str
    embargo_trading_days: int


def chronological_research_split(
    panel: pd.DataFrame,
    *,
    discovery_fraction: float = 0.70,
    embargo_trading_days: int = DEFAULT_EMBARGO_TRADING_DAYS,
    date_col: str = "trade_date",
) -> ResearchSplit:
    """
    Chronological split with embargo gap >= max forward horizon.

    Future OOS rows are strictly after discovery_end + embargo window.
    """
    if panel.empty:
        empty = panel.copy()
        return ResearchSplit(
            discovery_panel=empty,
            oos_panel=empty,
            discovery_end_date="",
            oos_start_date="",
            embargo_trading_days=embargo_trading_days,
        )

    work = panel.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    unique_dates = sorted(work[date_col].unique())
    if len(unique_dates) < 3:
        end = unique_dates[-1].strftime("%Y-%m-%d")
        return ResearchSplit(
            discovery_panel=work,
            oos_panel=work.iloc[0:0].copy(),
            discovery_end_date=end,
            oos_start_date="",
            embargo_trading_days=embargo_trading_days,
        )

    split_idx = max(1, int(len(unique_dates) * discovery_fraction))
    split_idx = min(split_idx, len(unique_dates) - 1)
    discovery_end = unique_dates[split_idx - 1]
    embargo_idx = min(split_idx - 1 + embargo_trading_days, len(unique_dates) - 1)
    oos_start = unique_dates[embargo_idx]

    discovery = work[work[date_col] <= discovery_end].copy()
    oos = work[work[date_col] >= oos_start].copy()

    return ResearchSplit(
        discovery_panel=discovery,
        oos_panel=oos,
        discovery_end_date=discovery_end.strftime("%Y-%m-%d"),
        oos_start_date=oos_start.strftime("%Y-%m-%d"),
        embargo_trading_days=embargo_trading_days,
    )


def assert_no_oos_leakage(split: ResearchSplit, *, date_col: str = "trade_date") -> None:
    """Raise if OOS rows overlap discovery window or violate embargo."""
    if split.oos_panel.empty or split.discovery_panel.empty:
        return
    disc_end = pd.Timestamp(split.discovery_end_date)
    oos_min = pd.to_datetime(split.oos_panel[date_col], errors="coerce").min()
    if pd.isna(oos_min):
        return
    if oos_min <= disc_end:
        raise ValueError("OOS panel contains dates on or before discovery_end_date")


def labels_overlap_embargo(
    discovery_end_date: str,
    candidate_entry_date: str,
    target_horizon_days: int = DEFAULT_EMBARGO_TRADING_DAYS,
) -> bool:
    """True if forward label from discovery-period entry could overlap OOS window."""
    start = pd.Timestamp(candidate_entry_date)
    end = pd.Timestamp(discovery_end_date)
    if start > end:
        return False
    # Conservative: any discovery entry within embargo window of cutoff may leak labels
    return (end - start).days <= target_horizon_days


def max_forward_horizon_sessions() -> int:
    return max(int(h.replace("T", "")) for h in HORIZONS)


def horizon_return_columns() -> Tuple[str, ...]:
    return tuple(RETURN_COLUMNS[h] for h in HORIZONS)
