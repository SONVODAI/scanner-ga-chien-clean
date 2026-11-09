"""Frozen OOS evaluation for V2 candidates. No re-search, no threshold retuning."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.baseline import compute_baseline_profiles
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
)
from modules.edge_research.oos import chronological_research_split
from modules.multifamily_discovery_v2.clauses import apply_clauses, clause_from_dict
from modules.multifamily_discovery_v2.contracts import (
    CANDIDATE_MIN_N,
    DISCOVERY_FRACTION,
    EMBARGO_TRADING_DAYS,
)


def split_panel(panel: pd.DataFrame):
    return chronological_research_split(
        panel,
        discovery_fraction=DISCOVERY_FRACTION,
        embargo_trading_days=EMBARGO_TRADING_DAYS,
    )


def evaluate_oos(oos_panel: pd.DataFrame, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for cand in candidates:
        clauses = tuple(clause_from_dict(c) for c in cand.get("clauses") or [])
        transition = str(cand.get("market_transition", ""))
        state = str(cand.get("market_state", ""))
        ctx = oos_panel[oos_panel["research_market_transition"] == transition]
        if ctx.empty:
            ctx = oos_panel[oos_panel["research_market_state"] == state]
        matched = apply_clauses(ctx, clauses) if not ctx.empty else ctx
        baseline = compute_baseline_profiles(
            oos_panel, market_transition=transition, market_state=state
        )
        horizon_stats: Dict[str, Any] = {}
        for h in HORIZONS:
            col = RETURN_COLUMNS[h]
            rets = pd.to_numeric(matched[col], errors="coerce").dropna() if not matched.empty else pd.Series(dtype=float)
            cand_prof = compute_horizon_profile(rets, h)
            base_prof = baseline.profiles.get(h, compute_horizon_profile(pd.Series(dtype=float), h))
            inc = compute_incremental_metrics(cand_prof, base_prof)
            horizon_stats[h] = {
                "candidate_n": cand_prof.n,
                "baseline_n": baseline.sample_n if baseline.is_valid else 0,
                "incremental": inc,
                "candidate_median": cand_prof.median_return,
                "baseline_median": base_prof.median_return,
                "insufficient": cand_prof.n < CANDIDATE_MIN_N or not baseline.is_valid,
            }
        t5 = horizon_stats["T5"]
        rows.append(
            {
                "condition_text": cand.get("condition_text"),
                "condition_key": cand.get("condition_key"),
                "families": cand.get("families"),
                "market_transition": transition,
                "oos_horizons": horizon_stats,
                "oos_t5_incremental_median": t5["incremental"].get("incremental_median"),
                "oos_t5_insufficient": t5["insufficient"],
            }
        )
    return {
        "n_candidates": len(candidates),
        "evaluations": rows,
    }
