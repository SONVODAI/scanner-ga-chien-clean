"""
Phase 3I.7 — Quintile metric extraction for lifecycle experiments.

Uses same quintile assignment as OPR evidence ingest (deterministic pd.qcut).
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_ingest import _assign_quintiles
from modules.edge_research.opr_bridge.lifecycle_records import QuintileMetrics
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import ToolStatus, resolve_cohort


def extract_quintile_metrics(
    panel: pd.DataFrame,
    spec: ExperimentSpec,
    *,
    partition_column: str,
    outcome_field: str,
    n_quintiles: int = 5,
) -> QuintileMetrics:
    """Extract quintile means from cohort — pre-registered in interpretation contract."""
    horizon = spec.inputs.get("horizon", "T5")
    cohort, _ = resolve_cohort(
        panel,
        spec.research_scope or {},
        data_cutoff_date=spec.data_cutoff_date,
        horizon=str(horizon) if horizon else None,
    )
    if partition_column not in cohort.columns or outcome_field not in cohort.columns:
        return QuintileMetrics(
            quintile_means=tuple(),
            quintile_ns=tuple(),
            low_quintile_mean=0.0,
            high_quintile_mean=0.0,
            quintile_mean_spread=0.0,
            low_high_delta=0.0,
            sample_size=0,
        )

    slice_df = cohort[[partition_column, outcome_field]].dropna()
    if slice_df.empty:
        return QuintileMetrics(
            quintile_means=tuple(),
            quintile_ns=tuple(),
            low_quintile_mean=0.0,
            high_quintile_mean=0.0,
            quintile_mean_spread=0.0,
            low_high_delta=0.0,
            sample_size=0,
        )

    slice_df = slice_df.copy()
    slice_df["_q"] = _assign_quintiles(slice_df[partition_column], n_quintiles=n_quintiles)
    slice_df = slice_df.dropna(subset=["_q"])

    means = []
    ns = []
    for q in range(n_quintiles):
        grp = slice_df[slice_df["_q"] == q]
        if len(grp) == 0:
            means.append(float("nan"))
            ns.append(0)
        else:
            means.append(float(grp[outcome_field].mean()))
            ns.append(int(len(grp)))

    valid_means = [m for m in means if m == m]
    spread = max(valid_means) - min(valid_means) if len(valid_means) >= 2 else 0.0
    low_mean = means[0] if means and means[0] == means[0] else 0.0
    high_mean = means[-1] if means and means[-1] == means[-1] else 0.0

    return QuintileMetrics(
        quintile_means=tuple(means),
        quintile_ns=tuple(ns),
        low_quintile_mean=low_mean,
        high_quintile_mean=high_mean,
        quintile_mean_spread=spread,
        low_high_delta=high_mean - low_mean,
        sample_size=int(len(slice_df)),
    )


def tool_result_hash(result_dict: Dict[str, Any]) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(result_dict, sort_keys=True, default=str).encode()).hexdigest()
