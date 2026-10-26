"""
Operational OutcomeSpec evaluation against research panels (Phase 3F).

Deterministic, cutoff-safe, no eval/arbitrary Python. Experiments compute
metrics from the OutcomeSpec attached to the current research question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.metrics import RETURN_COLUMNS
from modules.edge_research.research_grammar import (
    OutcomeKind,
    OutcomeSpec,
    evaluate_outcome_spec,
    parse_outcome_spec,
    validate_outcome_spec,
)
from modules.edge_research.research_tools import apply_research_cutoff

OUTCOME_EVALUATOR_VERSION = "outcome_evaluator_v1"


@dataclass(frozen=True)
class OutcomeProfile:
    """Aggregate outcome metrics for a cohort under one OutcomeSpec."""

    outcome_spec_hash: str
    n_total: int
    n_eligible: int
    n_missing: int
    n_success: int
    success_rate: Optional[float]
    mean_primary_return: Optional[float]
    median_primary_return: Optional[float]
    primary_return_field: Optional[str]
    missing_reason_counts: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_evaluator_version": OUTCOME_EVALUATOR_VERSION,
            "outcome_spec_hash": self.outcome_spec_hash,
            "n_total": self.n_total,
            "n_eligible": self.n_eligible,
            "n_missing": self.n_missing,
            "n_success": self.n_success,
            "success_rate": self.success_rate,
            "mean_primary_return": self.mean_primary_return,
            "median_primary_return": self.median_primary_return,
            "primary_return_field": self.primary_return_field,
            "missing_reason_counts": dict(self.missing_reason_counts),
        }


def _outcome_fields_used(spec: OutcomeSpec) -> Set[str]:
    """Collect forward return columns referenced by an OutcomeSpec tree."""
    fields: Set[str] = set()

    def walk(s: OutcomeSpec) -> None:
        if s.outcome_field:
            fields.add(s.outcome_field)
        if s.kind == OutcomeKind.PERSIST.value:
            for h in s.horizons:
                fields.add(RETURN_COLUMNS[h])
        if s.kind == OutcomeKind.CONTINUATION.value:
            if s.early_horizon:
                fields.add(RETURN_COLUMNS[s.early_horizon])
            if s.late_horizon:
                fields.add(RETURN_COLUMNS[s.late_horizon])
        if s.kind == OutcomeKind.REVERSAL.value:
            if s.early_horizon:
                fields.add(RETURN_COLUMNS[s.early_horizon])
            if s.late_horizon:
                fields.add(RETURN_COLUMNS[s.late_horizon])
        for c in s.children:
            walk(c)

    walk(spec)
    return fields


def _primary_return_field(spec: OutcomeSpec) -> Optional[str]:
    """Primary continuous return field for mean/median summaries."""
    if spec.kind == OutcomeKind.COMPARE.value and spec.outcome_field:
        return spec.outcome_field
    fields = sorted(_outcome_fields_used(spec))
    return fields[0] if fields else None


def _eligibility_mask(panel: pd.DataFrame, spec: OutcomeSpec) -> Tuple[pd.Series, pd.Series]:
    """
    Return (eligible_mask, missing_mask) for rows.

    Eligible = all referenced outcome fields present (not NaN).
    Missing = referenced fields exist but at least one is NaN.
    """
    required = _outcome_fields_used(spec)
    if not required:
        eligible = pd.Series(True, index=panel.index)
        return eligible, pd.Series(False, index=panel.index)

    present_cols = [c for c in required if c in panel.columns]
    if not present_cols:
        missing = pd.Series(True, index=panel.index)
        return pd.Series(False, index=panel.index), missing

    missing_parts = []
    for col in present_cols:
        missing_parts.append(panel[col].isna())
    missing = missing_parts[0]
    for part in missing_parts[1:]:
        missing = missing | part
    eligible = ~missing
    return eligible, missing


def outcome_success_mask(panel: pd.DataFrame, spec: OutcomeSpec) -> pd.Series:
    """Row-level boolean success under OutcomeSpec; False when ineligible."""
    validate_outcome_spec(spec)
    eligible, _ = _eligibility_mask(panel, spec)
    results = pd.Series(False, index=panel.index, dtype=bool)
    for idx in panel.index[eligible]:
        results.at[idx] = evaluate_outcome_spec(spec, panel.loc[idx])
    return results


def compute_outcome_profile(
    panel: pd.DataFrame,
    spec: OutcomeSpec,
    *,
    data_cutoff_date: Optional[str] = None,
    horizons_for_cutoff: Optional[Sequence[str]] = None,
) -> OutcomeProfile:
    """
    Compute cohort-level outcome metrics from OutcomeSpec.

    Applies cutoff when data_cutoff_date provided.
    """
    validate_outcome_spec(spec)
    work = panel.copy()
    if data_cutoff_date:
        hs = list(horizons_for_cutoff or ["T3", "T5", "T10"])
        work, _ = apply_research_cutoff(work, data_cutoff_date, horizons=hs)

    n_total = int(len(work))
    if n_total == 0:
        return OutcomeProfile(
            outcome_spec_hash=spec.content_hash(),
            n_total=0,
            n_eligible=0,
            n_missing=0,
            n_success=0,
            success_rate=None,
            mean_primary_return=None,
            median_primary_return=None,
            primary_return_field=_primary_return_field(spec),
            missing_reason_counts={"empty_panel": 1},
        )

    eligible, missing = _eligibility_mask(work, spec)
    n_eligible = int(eligible.sum())
    n_missing = int(missing.sum())
    success = outcome_success_mask(work, spec)
    n_success = int(success.sum())

    success_rate: Optional[float] = None
    if n_eligible > 0:
        success_rate = float(n_success / n_eligible * 100.0)

    primary = _primary_return_field(spec)
    mean_ret: Optional[float] = None
    median_ret: Optional[float] = None
    if primary and primary in work.columns and n_eligible > 0:
        rets = pd.to_numeric(work.loc[eligible, primary], errors="coerce").dropna()
        if len(rets):
            mean_ret = float(rets.mean())
            median_ret = float(rets.median())

    missing_reasons: Dict[str, int] = {}
    if n_missing:
        missing_reasons["outcome_field_nan"] = n_missing

    return OutcomeProfile(
        outcome_spec_hash=spec.content_hash(),
        n_total=n_total,
        n_eligible=n_eligible,
        n_missing=n_missing,
        n_success=n_success,
        success_rate=success_rate,
        mean_primary_return=mean_ret,
        median_primary_return=median_ret,
        primary_return_field=primary,
        missing_reason_counts=missing_reasons,
    )


def resolve_outcome_spec_from_scope(research_scope: Dict[str, Any]) -> Optional[OutcomeSpec]:
    """Extract OutcomeSpec from research_scope if present."""
    raw = research_scope.get("outcome_spec")
    if not raw:
        return None
    if isinstance(raw, OutcomeSpec):
        return raw
    return parse_outcome_spec(dict(raw))


def compare_group_outcome_profiles(
    panel: pd.DataFrame,
    group_key: pd.Series,
    spec: OutcomeSpec,
    *,
    data_cutoff_date: Optional[str] = None,
) -> Tuple[Dict[str, Any], OutcomeProfile]:
    """
    Compute per-group and baseline outcome profiles under one OutcomeSpec.

    Returns (groups_dict, baseline_profile).
    """
    work = panel.copy()
    if data_cutoff_date:
        work, _ = apply_research_cutoff(work, data_cutoff_date, horizons=["T3", "T5", "T10"])

    baseline = compute_outcome_profile(work, spec)
    groups: Dict[str, Any] = {}
    valid = group_key.notna()
    matured = work[valid].copy()
    matured["_group"] = group_key[valid].astype(str)

    for g, grp in matured.groupby("_group", sort=True):
        prof = compute_outcome_profile(grp, spec)
        baseline_rate = baseline.success_rate if baseline.success_rate is not None else 0.0
        grp_rate = prof.success_rate if prof.success_rate is not None else 0.0
        groups[str(g)] = {
            **prof.to_dict(),
            "incremental_success_rate": grp_rate - baseline_rate,
            "incremental_mean_return": (
                (prof.mean_primary_return - baseline.mean_primary_return)
                if prof.mean_primary_return is not None and baseline.mean_primary_return is not None
                else None
            ),
        }

    return groups, baseline


def default_outcome_spec_for_horizon(horizon: str) -> OutcomeSpec:
    """Fallback when scope lacks outcome_spec — positive return at horizon."""
    col = RETURN_COLUMNS.get(horizon, "t5_return")
    return OutcomeSpec.compare(col, ">", 0.0)
