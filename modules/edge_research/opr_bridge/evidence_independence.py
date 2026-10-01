"""
Phase 3I.12 — Structured evidence independence profiles.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_relationship_classifier import classify_pair
from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceIndependenceProfile,
    EvidenceLedgerEntry,
    EvidenceRelationship,
    IndependenceLevel,
)


def compute_independence_profile(
    entry: EvidenceLedgerEntry,
    prior_entries: List[EvidenceLedgerEntry],
) -> EvidenceIndependenceProfile:
    if not prior_entries:
        return EvidenceIndependenceProfile(
            sample_independence=IndependenceLevel.HIGH,
            episode_independence=IndependenceLevel.HIGH,
            temporal_independence=IndependenceLevel.HIGH,
            population_independence=IndependenceLevel.HIGH,
            measurement_independence=IndependenceLevel.HIGH,
            methodological_independence=IndependenceLevel.HIGH,
            semantic_independence=IndependenceLevel.HIGH,
            rationale=("Initial evidence — no prior ledger entries.",),
        )

    most_similar = _most_similar_prior(entry, prior_entries)
    rel = classify_pair(entry, most_similar)
    rationale: List[str] = []

    sample = _level_from_overlap(entry.cohort_overlap_ratio)
    rationale.append(f"cohort_overlap_ratio={entry.cohort_overlap_ratio:.3f}")

    episode = _episode_level(entry, most_similar, rationale)
    temporal = _temporal_level(entry, most_similar, rationale)
    population = _population_level(entry, most_similar, rationale)
    measurement = _measurement_level(entry, most_similar, rationale)
    methodological = _methodological_level(entry, most_similar, rationale)
    semantic = _semantic_level(entry, most_similar, rationale)

    if rel == EvidenceRelationship.EXACT_REPLICATION:
        sample = episode = temporal = population = measurement = methodological = semantic = IndependenceLevel.NONE
        rationale.append("EXACT_REPLICATION — no independence on any dimension.")

    return EvidenceIndependenceProfile(
        sample_independence=sample,
        episode_independence=episode,
        temporal_independence=temporal,
        population_independence=population,
        measurement_independence=measurement,
        methodological_independence=methodological,
        semantic_independence=semantic,
        rationale=tuple(rationale),
    )


def compute_all_profiles(
    entries: List[EvidenceLedgerEntry],
) -> Dict[str, EvidenceIndependenceProfile]:
    profiles: Dict[str, EvidenceIndependenceProfile] = {}
    for i, entry in enumerate(entries):
        profiles[entry.evidence_id] = compute_independence_profile(entry, entries[:i])
    return profiles


def _most_similar_prior(entry: EvidenceLedgerEntry, priors: List[EvidenceLedgerEntry]) -> EvidenceLedgerEntry:
    best = priors[0]
    best_overlap = entry.cohort_overlap_ratio
    for p in priors:
        if entry.feature_semantics == p.feature_semantics and entry.outcome_semantics == p.outcome_semantics:
            if entry.cohort_overlap_ratio >= best_overlap:
                best = p
    return best


def _level_from_overlap(ratio: float) -> IndependenceLevel:
    if ratio >= 0.95:
        return IndependenceLevel.NONE
    if ratio >= 0.85:
        return IndependenceLevel.LOW
    if ratio >= 0.5:
        return IndependenceLevel.MEDIUM
    if ratio >= 0.0:
        return IndependenceLevel.HIGH
    return IndependenceLevel.UNKNOWN


def _episode_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.cohort_episode_scope == b.cohort_episode_scope:
        rationale.append("episode_scope unchanged")
        return IndependenceLevel.NONE
    if "holdout" in a.cohort_episode_scope.lower() or "exclude" in a.cohort_episode_scope.lower():
        if a.cohort_overlap_ratio >= 0.85:
            rationale.append("episode holdout with high overlap — partial episode independence")
            return IndependenceLevel.LOW
        if a.cohort_overlap_ratio >= 0.5:
            return IndependenceLevel.MEDIUM
        return IndependenceLevel.HIGH
    return IndependenceLevel.UNKNOWN


def _temporal_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.data_cutoff == b.data_cutoff:
        return IndependenceLevel.NONE
    return IndependenceLevel.MEDIUM


def _population_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.population_semantics == b.population_semantics:
        return IndependenceLevel.NONE
    if a.cohort_overlap_ratio < 0.5:
        return IndependenceLevel.HIGH
    return IndependenceLevel.LOW


def _measurement_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.feature_semantics == b.feature_semantics and a.outcome_semantics == b.outcome_semantics:
        if a.measurement_tool == b.measurement_tool:
            return IndependenceLevel.NONE
        rationale.append("tool changed but same feature/outcome — not measurement independence")
        return IndependenceLevel.LOW
    return IndependenceLevel.HIGH


def _methodological_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.measurement_tool != b.measurement_tool:
        if a.feature_semantics == b.feature_semantics and a.outcome_semantics == b.outcome_semantics:
            rationale.append("methodological change without semantic change")
            return IndependenceLevel.LOW
        return IndependenceLevel.MEDIUM
    return IndependenceLevel.NONE


def _semantic_level(a: EvidenceLedgerEntry, b: EvidenceLedgerEntry, rationale: List[str]) -> IndependenceLevel:
    if a.uncertainty_axis_tested == b.uncertainty_axis_tested:
        return IndependenceLevel.NONE
    return IndependenceLevel.HIGH


def independence_summary(profiles: Dict[str, EvidenceIndependenceProfile]) -> str:
    if not profiles:
        return "no_evidence"
    highs = sum(
        1
        for p in profiles.values()
        if p.semantic_independence == IndependenceLevel.HIGH or p.sample_independence == IndependenceLevel.HIGH
    )
    if highs == 0:
        return "predominantly_correlated"
    if highs == len(profiles):
        return "predominantly_independent"
    return "mixed_independence"
