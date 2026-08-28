"""
Phase 3I.12 — Generic uncertainty dimension derivation and coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import EvidenceLedgerEntry


# Generic uncertainty dimensions — derived from proposition type, not market-specific answers.
PARTITION_UNCERTAINTY_AXES = (
    "directional_effect_full_universe",
    "episode_robustness",
    "temporal_regime_robustness",
    "population_robustness",
    "horizon_robustness",
    "effect_stability",
    "concentration_dominance",
    "measurement_robustness",
    "counterexample_exposure",
    "alternative_explanation_exposure",
    "regime_context_robustness",
)

CONTEXT_MODULATION_UNCERTAINTY_AXES = (
    "context_modulation_direction",
    "context_independence",
    "population_robustness",
    "temporal_regime_robustness",
    "measurement_robustness",
    "counterexample_exposure",
    "alternative_explanation_exposure",
)


def derive_uncertainty_dimensions(proposition_spec: Dict[str, Any]) -> Tuple[str, ...]:
    ptype = proposition_spec.get("proposition_type", "partition_contrast")
    if ptype == "context_modulation":
        return CONTEXT_MODULATION_UNCERTAINTY_AXES
    return PARTITION_UNCERTAINTY_AXES


def assess_coverage(
    entries: List[EvidenceLedgerEntry],
    all_dimensions: Tuple[str, ...],
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    covered: Set[str] = set()
    for e in entries:
        if e.validity != "VALID":
            continue
        if e.evidence_class in ("INVALID", "NON_INFORMATIVE"):
            continue
        axis = e.uncertainty_axis_tested
        if axis:
            covered.add(axis)
        # Full-universe supporting evidence also covers directional effect
        if e.evidence_class == "SUPPORTING" and "full" in e.population_semantics.lower():
            covered.add("directional_effect_full_universe")
        if e.evidence_class == "SUPPORTING" and "holdout" in e.cohort_episode_scope.lower():
            covered.add("episode_robustness")

    unresolved = tuple(d for d in all_dimensions if d not in covered)
    covered_tuple = tuple(sorted(covered))
    return covered_tuple, unresolved
