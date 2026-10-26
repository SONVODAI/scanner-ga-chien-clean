"""
Phase 3I.5 — Scientific-identity grouping and pairwise classification.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Literal, Tuple

from modules.edge_research.opr_bridge.observation_entities import (
    EvidenceEvent,
    ObservationEvent,
    ScientificPropositionGroup,
)
from modules.edge_research.opr_bridge.semantic_projection import SemanticProjection, project_contrast_semantics
from modules.edge_research.research_proposition_core import (
    CanonicalPropositionCore,
    cores_materially_different,
    cores_same_question,
)

PairwiseClassification = Literal[
    "SAME_PROPOSITION_DIFFERENT_EVIDENCE",
    "RELATED_BUT_DISTINCT",
    "GENUINELY_INDEPENDENT",
    "INSUFFICIENT_EVIDENCE",
]


def scientific_identity_key(projection: SemanticProjection) -> str:
    """
    Stable identity excluding focal_date, evidence_hash, proposition_id, and relation_type.

    Relation type is inferred per-date and may vary without changing the scientific question.
    """
    ident = {
        "population": projection.population_spec,
        "outcome": projection.outcome_spec,
        "horizon": projection.observation_horizon,
        "uncertainty_family": projection.uncertainty_family,
        "scientific_question": projection.scientific_question,
        "feature": projection.feature,
    }
    return hashlib.sha256(json.dumps(ident, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _same_proposition(a: SemanticProjection, b: SemanticProjection) -> bool:
    return cores_same_question(a.canonical_core, b.canonical_core) and a.scientific_question == b.scientific_question


def _evidence_role(direction: str, group_direction: str) -> str:
    if direction == "flat":
        return "NEUTRAL"
    if direction != group_direction and group_direction != "flat":
        return "CONTRADICT"
    return "SUPPORT"


def group_observation_events(
    events: List[ObservationEvent],
) -> List[ScientificPropositionGroup]:
    """
    Group observation events by underlying scientific proposition identity.

    Preserves each evidence event separately with append-only lineage.
    """
    indexed: List[Tuple[ObservationEvent, SemanticProjection]] = []
    for obs in events:
        if not obs.surprise.is_surprising:
            continue
        proj = project_contrast_semantics(obs.evidence, obs.surprise)
        indexed.append((obs, proj))

    # Cluster by cores_same_question — avoid over-split on relation_type noise
    clusters: List[List[Tuple[ObservationEvent, SemanticProjection]]] = []
    for obs, proj in indexed:
        placed = False
        for cluster in clusters:
            if _same_proposition(proj, cluster[0][1]):
                cluster.append((obs, proj))
                placed = True
                break
        if not placed:
            clusters.append([(obs, proj)])

    groups: List[ScientificPropositionGroup] = []
    for cluster in clusters:
        _, head_proj = cluster[0]
        key = scientific_identity_key(head_proj)
        group = ScientificPropositionGroup(
            identity_key=key,
            scientific_question=head_proj.scientific_question,
            uncertainty_family=head_proj.uncertainty_family,
            population_spec=head_proj.population_spec,
            outcome_spec=head_proj.outcome_spec,
            observation_horizon=head_proj.observation_horizon,
            feature=head_proj.feature,
            relation_type=head_proj.relation_type,
        )

        for obs, proj in cluster:
            role = "SUPPORT"
            if group.evidence_events:
                rep_dir = group.evidence_events[0].contrast_direction
                role = _evidence_role(proj.contrast_direction, rep_dir)
            group.evidence_events.append(
                EvidenceEvent(
                    observation_event=obs,
                    role=role,
                    contrast_direction=proj.contrast_direction,
                    empirical_delta=proj.empirical_delta,
                )
            )

        group.representative = _select_representative(group)
        groups.append(group)

    return groups


def classify_pairwise(
    a: SemanticProjection,
    b: SemanticProjection,
) -> PairwiseClassification:
    """Classify relationship between two semantic projections."""
    if not a.canonical_core.has_minimal_semantics() or not b.canonical_core.has_minimal_semantics():
        return "INSUFFICIENT_EVIDENCE"

    if _same_proposition(a, b):
        return "SAME_PROPOSITION_DIFFERENT_EVIDENCE"

    if cores_materially_different(a.canonical_core, b.canonical_core):
        if a.uncertainty_family == b.uncertainty_family or a.feature == b.feature:
            return "RELATED_BUT_DISTINCT"
        return "GENUINELY_INDEPENDENT"

    if a.scientific_question == b.scientific_question:
        return "SAME_PROPOSITION_DIFFERENT_EVIDENCE"

    return "RELATED_BUT_DISTINCT"


def _select_representative(group: ScientificPropositionGroup) -> ObservationEvent:
    """Choose highest-information representative evidence within a group."""
    return max(
        group.evidence_events,
        key=lambda e: (
            e.observation_event.evidence.quintile_return_spread,
            abs(e.empirical_delta),
            abs(e.observation_event.surprise.zscore_vs_baseline),
        ),
    ).observation_event


def cores_match(a: CanonicalPropositionCore, b: CanonicalPropositionCore) -> bool:
    """Public wrapper for grouping checks."""
    return cores_same_question(a, b)
