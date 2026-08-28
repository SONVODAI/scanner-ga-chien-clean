"""
Phase 3I.17b — Evidence-derived cohort binding records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso, new_id

COHORT_BINDER_VERSION = "evidence_derived_cohort_binder_v1_3i17b"
COHORT_CANDIDATE_VERSION = "cohort_candidate_record_v1_3i17b"


class CohortRedundancy(str, Enum):
    NOVEL = "NOVEL"
    REDUNDANT = "REDUNDANT"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"


class CohortSelectionDisposition(str, Enum):
    SELECTED = "SELECTED"
    AMBIGUOUS_COHORT_SELECTION = "AMBIGUOUS_COHORT_SELECTION"
    NO_DEFENSIBLE_COHORT = "NO_DEFENSIBLE_COHORT"


class IndependenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CohortOverlapProfile:
    candidate_row_count: int
    row_overlap_fraction: float
    date_overlap_fraction: float
    symbol_overlap_fraction: float
    context_overlap_fraction: float
    relation_to_prior: str  # subset | superset | complement | partial_overlap | disjoint | unknown
    overlaps_motivating_dates: bool
    overlaps_prior_falsification_cohort: bool
    max_prior_row_overlap: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_row_count": self.candidate_row_count,
            "row_overlap_fraction": self.row_overlap_fraction,
            "date_overlap_fraction": self.date_overlap_fraction,
            "symbol_overlap_fraction": self.symbol_overlap_fraction,
            "context_overlap_fraction": self.context_overlap_fraction,
            "relation_to_prior": self.relation_to_prior,
            "overlaps_motivating_dates": self.overlaps_motivating_dates,
            "overlaps_prior_falsification_cohort": self.overlaps_prior_falsification_cohort,
            "max_prior_row_overlap": self.max_prior_row_overlap,
        }


@dataclass(frozen=True)
class ScientificEvidenceIndependenceProfile:
    sample_independence: str
    episode_independence: str
    population_independence: str
    context_independence: str
    measurement_independence: str
    semantic_continuity: str
    rationale: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, str]:
        return {
            "sample_independence": self.sample_independence,
            "episode_independence": self.episode_independence,
            "population_independence": self.population_independence,
            "context_independence": self.context_independence,
            "measurement_independence": self.measurement_independence,
            "semantic_continuity": self.semantic_continuity,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class CohortCandidateRecord:
    cohort_id: str
    record_version: str
    cohort_semantic_definition: str
    source_dimension: str
    population_spec: Dict[str, Any]
    derivation_provenance: Dict[str, str]
    relation_to_proposition_population: str
    overlap_profile: CohortOverlapProfile
    expected_sample_coverage: int
    independence_profile: ScientificEvidenceIndependenceProfile
    redundancy_status: str
    rescue_risk_status: str
    executability_status: str
    scientific_rationale: str
    cohort_semantic_hash: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "record_version": self.record_version,
            "cohort_semantic_definition": self.cohort_semantic_definition,
            "source_dimension": self.source_dimension,
            "population_spec": dict(self.population_spec),
            "derivation_provenance": dict(self.derivation_provenance),
            "relation_to_proposition_population": self.relation_to_proposition_population,
            "overlap_profile": self.overlap_profile.to_dict(),
            "expected_sample_coverage": self.expected_sample_coverage,
            "independence_profile": self.independence_profile.to_dict(),
            "redundancy_status": self.redundancy_status,
            "rescue_risk_status": self.rescue_risk_status,
            "executability_status": self.executability_status,
            "scientific_rationale": self.scientific_rationale,
            "cohort_semantic_hash": self.cohort_semantic_hash,
            "record_hash": self.record_hash,
        }


def build_cohort_candidate(
    *,
    cohort_semantic_definition: str,
    source_dimension: str,
    population_spec: Dict[str, Any],
    derivation_provenance: Dict[str, str],
    relation_to_proposition_population: str,
    overlap_profile: CohortOverlapProfile,
    independence_profile: ScientificEvidenceIndependenceProfile,
    redundancy_status: str,
    rescue_risk_status: str,
    executability_status: str,
    scientific_rationale: str,
    cohort_id: Optional[str] = None,
) -> CohortCandidateRecord:
    cid = cohort_id or new_id("coh")
    semantic_payload = {
        "definition": cohort_semantic_definition,
        "source_dimension": source_dimension,
        "population_spec": population_spec,
    }
    cohort_semantic_hash = stable_hash(semantic_payload)
    body = {
        "record_version": COHORT_CANDIDATE_VERSION,
        "cohort_semantic_definition": cohort_semantic_definition,
        "source_dimension": source_dimension,
        "population_spec": population_spec,
        "derivation_provenance": derivation_provenance,
        "overlap_profile": overlap_profile.to_dict(),
        "independence_profile": independence_profile.to_dict(),
        "redundancy_status": redundancy_status,
        "cohort_semantic_hash": cohort_semantic_hash,
    }
    return CohortCandidateRecord(
        cohort_id=cid,
        record_hash=stable_hash(body),
        cohort_semantic_hash=cohort_semantic_hash,
        expected_sample_coverage=overlap_profile.candidate_row_count,
        record_version=COHORT_CANDIDATE_VERSION,
        cohort_semantic_definition=cohort_semantic_definition,
        source_dimension=source_dimension,
        population_spec=population_spec,
        derivation_provenance=derivation_provenance,
        relation_to_proposition_population=relation_to_proposition_population,
        overlap_profile=overlap_profile,
        independence_profile=independence_profile,
        redundancy_status=redundancy_status,
        rescue_risk_status=rescue_risk_status,
        executability_status=executability_status,
        scientific_rationale=scientific_rationale,
    )


def binder_content_hash() -> str:
    return stable_hash({"version": COHORT_BINDER_VERSION})
