"""
Phase 3I.5 — Pre-emission semantic projection.

Derives the minimum semantic content needed for identity comparison and prioritization
WITHOUT emitting a full PropositionRecord. Uses frozen CONTRAST_TO_PROPOSITION semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from modules.edge_research.opr_bridge.constants import ALLOWED_RELATIONS, OBSERVATION_HORIZON
from modules.edge_research.opr_bridge.evidence_ingest import DispersionEvidencePayload
from modules.edge_research.opr_bridge.proposition_synthesizer import (
    _infer_relation_and_direction,
    _outcome_spec_compare,
    _population_spec_all,
)
from modules.edge_research.opr_bridge.surprise_detector import SurpriseAssessment
from modules.edge_research.research_proposition_core import (
    CanonicalPropositionCore,
    build_canonical_proposition_core,
)


@dataclass(frozen=True)
class SemanticProjection:
    """Minimum semantic projection for identity grouping and prioritization."""

    scientific_question: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    uncertainty_family: str
    feature: str
    relation_type: str
    contrast_direction: str
    empirical_delta: float
    canonical_core: CanonicalPropositionCore
    executability_pass: bool
    min_cohort_n: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scientific_question": self.scientific_question,
            "population_spec": self.population_spec,
            "outcome_spec": self.outcome_spec,
            "observation_horizon": self.observation_horizon,
            "uncertainty_family": self.uncertainty_family,
            "feature": self.feature,
            "relation_type": self.relation_type,
            "contrast_direction": self.contrast_direction,
            "empirical_delta": self.empirical_delta,
            "scientific_question_key": self.canonical_core.scientific_question_key(),
            "executability_pass": self.executability_pass,
            "min_cohort_n": self.min_cohort_n,
        }


def project_contrast_semantics(
    evidence: DispersionEvidencePayload,
    surprise: SurpriseAssessment,
) -> SemanticProjection:
    """
    Project frozen CONTRAST_TO_PROPOSITION semantics without creating PropositionRecord.

    Mirrors proposition_synthesizer.synthesize_contrast_to_proposition field derivation.
    """
    feat = evidence.dispersion_feature
    outcome = evidence.outcome_field
    relation, direction, low_q, high_q = _infer_relation_and_direction(evidence.quintile_slices)

    if relation not in ALLOWED_RELATIONS:
        relation = "contrasts_with"

    pop_spec = _population_spec_all()
    out_spec = _outcome_spec_compare(outcome)
    min_cohort = low_q.n + high_q.n

    core = build_canonical_proposition_core(
        population_spec=pop_spec,
        outcome_spec=out_spec,
        observation_horizon=OBSERVATION_HORIZON,
        uncertainty_codes=("CROSS_SECTIONAL_DISPERSION",),
        conditioning_context={
            "dispersion_feature": feat,
            "focal_date": evidence.focal_date,
            "contrast_direction": direction,
        },
        enrichment_sources=("opr_contrast_to_proposition",),
    )

    scientific_q = (
        f"Does cross-sectional {feat} dispersion tier predict differential forward {outcome} "
        f"across the market cross-section?"
    )

    executability_pass = min_cohort >= 10

    return SemanticProjection(
        scientific_question=scientific_q,
        population_spec=pop_spec,
        outcome_spec=out_spec,
        observation_horizon=OBSERVATION_HORIZON,
        uncertainty_family=core.uncertainty_family,
        feature=feat,
        relation_type=relation,
        contrast_direction=direction,
        empirical_delta=high_q.mean_outcome - low_q.mean_outcome,
        canonical_core=core,
        executability_pass=executability_pass,
        min_cohort_n=min_cohort,
    )
