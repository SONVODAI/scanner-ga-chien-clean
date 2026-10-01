"""
Phase 3J.2 — Birth-evidence fingerprint and candidate independence (generalized 3I.17b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.cohort_overlap_estimator import (
    PanelMetadataIndex,
    candidate_row_keys,
    derive_independence_from_overlap,
    estimate_overlap,
)
from modules.edge_research.opr_bridge.falsification_candidate_generator import collect_motivating_episode_dates


@dataclass(frozen=True)
class BirthEvidenceFingerprint:
    """Rows/dates that encoded the proposition's birth evidence — pre-result only."""

    row_keys: Set[Tuple[str, str]]
    dates: Set[str]
    population_semantics: str
    feature_semantics: str
    outcome_semantics: str
    contrast_relation: str
    motivating_dates: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_count": len(self.row_keys),
            "dates": sorted(self.dates),
            "population_semantics": self.population_semantics,
            "feature_semantics": self.feature_semantics,
            "outcome_semantics": self.outcome_semantics,
            "contrast_relation": self.contrast_relation,
            "motivating_dates": list(self.motivating_dates),
        }


def _feature_semantics(prop: Dict[str, Any]) -> str:
    ptype = prop.get("proposition_type", "partition_contrast")
    if ptype == "context_modulation":
        return str(prop.get("feature") or "context_gate")
    rel = prop.get("explanatory_relation", {})
    if rel.get("relation_kind") == "surface_skew":
        return str(rel.get("feature_or_contrast") or prop.get("feature") or "skew_measure")
    return str(
        rel.get("feature_or_contrast")
        or prop.get("feature")
        or prop.get("execution_requirements", {}).get("partition_column", "partition_feature")
    )


def _outcome_semantics(prop: Dict[str, Any]) -> str:
    outcome = prop.get("outcome", {})
    if isinstance(outcome, dict):
        return str(outcome.get("field", "outcome_field"))
    return str(outcome)


def _contrast_relation(prop: Dict[str, Any]) -> str:
    ptype = prop.get("proposition_type", "partition_contrast")
    if ptype == "context_modulation":
        return "context_modulation_contrast"
    rel = prop.get("explanatory_relation", {})
    if rel.get("relation_kind") == "surface_skew":
        return "surface_skew_contrast"
    return "partition_quintile_contrast"


def build_birth_evidence_fingerprint(
    prop: Dict[str, Any],
    panel: PanelMetadataIndex,
) -> BirthEvidenceFingerprint:
    """
    Derive birth-evidence cohort from proposition provenance — not from tool names.
    """
    motivating = collect_motivating_episode_dates(prop)
    anchor = prop.get("observation_provenance", {}).get("evidence_anchor", {})
    focal = anchor.get("focal_date")
    dates = set(motivating)
    if focal:
        dates.add(str(focal))

    if dates:
        birth_keys = {(d, s) for d, s in panel.row_keys if d in dates}
    else:
        birth_keys = set(panel.row_keys)

    struct = prop.get("observation_provenance", {}).get("structural_context", {})
    pop_spec = struct.get("population_spec") or prop.get("population_context", {"kind": "all"})
    pop_kind = pop_spec.get("kind", "all")
    population_semantics = "full_universe" if pop_kind == "all" else f"birth_{pop_kind}"

    return BirthEvidenceFingerprint(
        row_keys=birth_keys,
        dates=dates or {d for d, _ in birth_keys},
        population_semantics=population_semantics,
        feature_semantics=_feature_semantics(prop),
        outcome_semantics=_outcome_semantics(prop),
        contrast_relation=_contrast_relation(prop),
        motivating_dates=motivating,
    )


def measure_birth_overlap(
    *,
    candidate_population_spec: Dict[str, Any],
    candidate_contrast_relation: str,
    candidate_feature: str,
    panel: PanelMetadataIndex,
    birth: BirthEvidenceFingerprint,
) -> Tuple[float, Dict[str, str]]:
    """
    Quantify overlap with birth evidence. Identity dimensions must match for overlap to bind.
    """
    if candidate_contrast_relation != birth.contrast_relation:
        return 0.0, _unknown_independence("contrast_mismatch")

    if candidate_feature != birth.feature_semantics:
        return 0.0, _unknown_independence("feature_mismatch")

    cand_keys = candidate_row_keys(panel, candidate_population_spec)
    if not birth.row_keys:
        return 0.0, {"sample_independence": "HIGH"}

    inter = len(cand_keys & birth.row_keys)
    overlap_frac = inter / max(len(cand_keys), 1)

    from modules.edge_research.opr_bridge.cohort_overlap_estimator import PriorCohortFingerprint

    prior = PriorCohortFingerprint(
        evidence_id="birth_evidence",
        row_keys=birth.row_keys,
        dates=birth.dates,
        symbols={s for _, s in birth.row_keys},
        contexts=set(),
        population_semantics=birth.population_semantics,
        cohort_overlap_ratio=1.0,
    )
    profile = estimate_overlap(
        cand_keys,
        panel,
        [prior],
        motivating_dates=birth.motivating_dates,
    )
    indep = derive_independence_from_overlap(profile, source_dimension="birth_evidence")
    return overlap_frac, indep.to_dict()


def _unknown_independence(reason: str) -> Dict[str, str]:
    return {
        "sample_independence": "UNKNOWN",
        "episode_independence": "UNKNOWN",
        "population_independence": "UNKNOWN",
        "context_independence": "UNKNOWN",
        "measurement_independence": "UNKNOWN",
        "semantic_continuity": "UNKNOWN",
        "rationale": reason,
    }
