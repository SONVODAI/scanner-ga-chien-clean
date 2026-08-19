"""
Same-state baseline computation for Edge Research (Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    BASELINE_MIN_N,
    BASELINE_TYPE_INSUFFICIENT,
    BASELINE_TYPE_SAME_STATE,
    BASELINE_TYPE_SAME_TRANSITION,
)
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    HorizonProfile,
    compute_horizon_profile,
)

BaselineKey = Tuple[str, str, str]  # baseline_type, transition, state


@dataclass(frozen=True)
class BaselineResult:
    baseline_type: str
    market_transition: str
    market_state: str
    profiles: Dict[str, HorizonProfile]
    sample_n: int

    @property
    def is_valid(self) -> bool:
        return self.baseline_type != BASELINE_TYPE_INSUFFICIENT and self.sample_n >= BASELINE_MIN_N


def _matured_mask(panel: pd.DataFrame, horizon_col: str) -> pd.Series:
    return pd.to_numeric(panel[horizon_col], errors="coerce").notna()


def _filter_context(
    panel: pd.DataFrame,
    *,
    transition: Optional[str] = None,
    state: Optional[str] = None,
) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    out = panel.copy()
    if transition is not None and "research_market_transition" in out.columns:
        out = out[out["research_market_transition"] == transition]
    if state is not None and "research_market_state" in out.columns:
        out = out[out["research_market_state"] == state]
    return out


def compute_baseline_profiles(
    panel: pd.DataFrame,
    *,
    market_transition: str,
    market_state: str,
    min_n: int = BASELINE_MIN_N,
) -> BaselineResult:
    """
    Baseline hierarchy:
    LEVEL 1 — same research_market_transition
    LEVEL 2 — same research_market_state (if transition sample insufficient)
    LEVEL 3 — INSUFFICIENT (never whole-history fallback)
    """
    profiles: Dict[str, HorizonProfile] = {}

    transition_panel = _filter_context(
        panel,
        transition=market_transition,
    )
    if len(transition_panel) >= min_n:
        for h in HORIZONS:
            col = RETURN_COLUMNS[h]
            matured = transition_panel[_matured_mask(transition_panel, col)]
            profiles[h] = compute_horizon_profile(matured[col], h)
        return BaselineResult(
            baseline_type=BASELINE_TYPE_SAME_TRANSITION,
            market_transition=market_transition,
            market_state=market_state,
            profiles=profiles,
            sample_n=len(transition_panel),
        )

    state_panel = _filter_context(panel, state=market_state)
    if len(state_panel) >= min_n:
        for h in HORIZONS:
            col = RETURN_COLUMNS[h]
            matured = state_panel[_matured_mask(state_panel, col)]
            profiles[h] = compute_horizon_profile(matured[col], h)
        return BaselineResult(
            baseline_type=BASELINE_TYPE_SAME_STATE,
            market_transition=market_transition,
            market_state=market_state,
            profiles=profiles,
            sample_n=len(state_panel),
        )

    for h in HORIZONS:
        profiles[h] = compute_horizon_profile(pd.Series(dtype=float), h)
    return BaselineResult(
        baseline_type=BASELINE_TYPE_INSUFFICIENT,
        market_transition=market_transition,
        market_state=market_state,
        profiles=profiles,
        sample_n=len(state_panel),
    )


def count_valid_market_contexts(panel: pd.DataFrame, min_n: int = BASELINE_MIN_N) -> int:
    """Count distinct transitions with enough observations for baseline."""
    if panel.empty:
        return 0
    counts = panel.groupby("research_market_transition").size()
    return int((counts >= min_n).sum())
