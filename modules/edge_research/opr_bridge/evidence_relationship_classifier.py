"""
Phase 3I.12 — Deterministic evidence relationship classification.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceLedgerEntry,
    EvidenceRelationship,
)


def classify_pair(
    current: EvidenceLedgerEntry,
    prior: EvidenceLedgerEntry,
) -> EvidenceRelationship:
    """Classify relationship of current evidence to a prior evidence event."""
    if current.validity == "INVALID" or prior.validity == "INVALID":
        return EvidenceRelationship.INVALID

    if current.evidence_class in ("NON_INFORMATIVE",) or prior.evidence_class == "NON_INFORMATIVE":
        if current.evidence_class == "NON_INFORMATIVE":
            return EvidenceRelationship.NON_INFORMATIVE

    if current.experiment_content_hash == prior.experiment_content_hash:
        return EvidenceRelationship.EXACT_REPLICATION

    # Contradictory: opposing directional implications on same semantic axis
    if _is_contradictory(current, prior):
        return EvidenceRelationship.CONTRADICTORY_EVIDENCE

    if current.falsification_intent and not prior.falsification_intent:
        if _is_independent_enough(current, prior):
            return EvidenceRelationship.INDEPENDENT_FALSIFICATION
        return EvidenceRelationship.PARTIAL_REPLICATION

    if (
        current.feature_semantics == prior.feature_semantics
        and current.outcome_semantics == prior.outcome_semantics
        and current.measurement_tool != prior.measurement_tool
        and current.population_semantics == prior.population_semantics
        and current.cohort_episode_scope == prior.cohort_episode_scope
    ):
        return EvidenceRelationship.REPRESENTATION_REPLICATION

    if _is_independent_enough(current, prior):
        if current.falsification_intent:
            return EvidenceRelationship.INDEPENDENT_FALSIFICATION
        return EvidenceRelationship.INDEPENDENT_REPLICATION

    if current.cohort_overlap_ratio >= 0.85 or (
        current.feature_semantics == prior.feature_semantics
        and current.outcome_semantics == prior.outcome_semantics
        and current.uncertainty_axis_tested == prior.uncertainty_axis_tested
        and current.cohort_overlap_ratio >= 0.5
    ):
        return EvidenceRelationship.PARTIAL_REPLICATION

    if current.uncertainty_axis_tested == prior.uncertainty_axis_tested:
        return EvidenceRelationship.RELATED_EVIDENCE

    return EvidenceRelationship.PARTIAL_REPLICATION


def classify_all_relationships(
    entries: List[EvidenceLedgerEntry],
) -> Dict[str, str]:
    """Map evidence_id -> relationship to most relevant prior evidence."""
    rel_map: Dict[str, str] = {}
    for i, entry in enumerate(entries):
        if i == 0:
            rel_map[entry.evidence_id] = "INITIAL"
            continue
        priors = entries[:i]
        # Classify against most similar prior (highest overlap)
        best_rel = EvidenceRelationship.RELATED_EVIDENCE
        best_overlap = -1.0
        for prior in priors:
            rel = classify_pair(entry, prior)
            overlap = entry.cohort_overlap_ratio if prior.evidence_id == priors[-1].evidence_id else 0.0
            if entry.cohort_overlap_ratio >= best_overlap:
                best_overlap = entry.cohort_overlap_ratio
                best_rel = rel
        rel_map[entry.evidence_id] = best_rel.value
    return rel_map


def pairwise_relationships(
    entries: List[EvidenceLedgerEntry],
) -> List[Tuple[str, str, EvidenceRelationship]]:
    pairs: List[Tuple[str, str, EvidenceRelationship]] = []
    for i, current in enumerate(entries):
        for prior in entries[:i]:
            pairs.append((current.evidence_id, prior.evidence_id, classify_pair(current, prior)))
    return pairs


def _is_contradictory(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry) -> bool:
    if a.evidence_class == "CONTRADICTORY" or b.evidence_class == "CONTRADICTORY":
        return True
    classes = {a.evidence_class, b.evidence_class}
    if "SUPPORTING" in classes and "DISCONFIRMING" in classes:
        if (
            a.feature_semantics == b.feature_semantics
            and a.outcome_semantics == b.outcome_semantics
            and a.uncertainty_axis_tested == b.uncertainty_axis_tested
        ):
            return True
    return False


def _is_independent_enough(current: EvidenceLedgerEntry, prior: EvidenceLedgerEntry) -> bool:
    """Independence requires more than tool/date/representation change alone."""
    if current.cohort_overlap_ratio >= 0.85:
        return False
    if current.uncertainty_axis_tested != prior.uncertainty_axis_tested:
        return True
    if current.population_semantics != prior.population_semantics and current.cohort_overlap_ratio < 0.5:
        return True
    if current.cohort_episode_scope != prior.cohort_episode_scope and current.cohort_overlap_ratio < 0.7:
        return True
    if current.cohort_overlap_ratio < 0.3:
        return True
    return False
