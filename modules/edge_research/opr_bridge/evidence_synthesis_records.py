"""
Phase 3I.12 — Evidence synthesis record types (append-only, research-only).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SYNTHESIS_ENGINE_VERSION = "evidence_synthesis_v1_3i12"


class EvidenceRelationship(str, Enum):
    EXACT_REPLICATION = "EXACT_REPLICATION"
    REPRESENTATION_REPLICATION = "REPRESENTATION_REPLICATION"
    PARTIAL_REPLICATION = "PARTIAL_REPLICATION"
    INDEPENDENT_REPLICATION = "INDEPENDENT_REPLICATION"
    INDEPENDENT_FALSIFICATION = "INDEPENDENT_FALSIFICATION"
    RELATED_EVIDENCE = "RELATED_EVIDENCE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    NON_INFORMATIVE = "NON_INFORMATIVE"
    INVALID = "INVALID"


class IndependenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class SaturationLevel(str, Enum):
    LOW = "LOW"
    PARTIAL = "PARTIAL"
    HIGH = "HIGH"
    INDETERMINATE = "INDETERMINATE"


class ResearchPriorityAction(str, Enum):
    SEEK_FALSIFICATION = "SEEK_FALSIFICATION"
    SEEK_REPLICATION = "SEEK_REPLICATION"
    SEEK_CONTRADICTION_RESOLUTION = "SEEK_CONTRADICTION_RESOLUTION"
    HOLD_PROVISIONALLY = "HOLD_PROVISIONALLY"
    HOLD_UNRESOLVED = "HOLD_UNRESOLVED"
    ABANDON = "ABANDON"


@dataclass(frozen=True)
class EvidenceIndependenceProfile:
    sample_independence: IndependenceLevel
    episode_independence: IndependenceLevel
    temporal_independence: IndependenceLevel
    population_independence: IndependenceLevel
    measurement_independence: IndependenceLevel
    methodological_independence: IndependenceLevel
    semantic_independence: IndependenceLevel
    rationale: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_independence": self.sample_independence.value,
            "episode_independence": self.episode_independence.value,
            "temporal_independence": self.temporal_independence.value,
            "population_independence": self.population_independence.value,
            "measurement_independence": self.measurement_independence.value,
            "methodological_independence": self.methodological_independence.value,
            "semantic_independence": self.semantic_independence.value,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class EvidenceLedgerEntry:
    """Minimal ledger index — authoritative data lives in referenced records."""

    evidence_id: str
    proposition_id: str
    proposition_hash: str
    experiment_id: str
    experiment_content_hash: str
    epistemic_update_ref: Optional[str]
    evidence_class: str
    validity: str  # VALID | INVALID
    feature_semantics: str
    population_semantics: str
    outcome_semantics: str
    horizon: str
    cohort_episode_scope: str
    data_cutoff: str
    sample_size: int
    effect_direction: str  # positive | negative | neutral | unknown
    effect_magnitude: str  # strong | weak | none | unknown
    measurement_tool: str
    uncertainty_axis_tested: str
    falsification_intent: bool
    cohort_overlap_ratio: float  # vs most similar prior (0-1)
    provenance_refs: Dict[str, str]
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "experiment_id": self.experiment_id,
            "experiment_content_hash": self.experiment_content_hash,
            "epistemic_update_ref": self.epistemic_update_ref,
            "evidence_class": self.evidence_class,
            "validity": self.validity,
            "feature_semantics": self.feature_semantics,
            "population_semantics": self.population_semantics,
            "outcome_semantics": self.outcome_semantics,
            "horizon": self.horizon,
            "cohort_episode_scope": self.cohort_episode_scope,
            "data_cutoff": self.data_cutoff,
            "sample_size": self.sample_size,
            "effect_direction": self.effect_direction,
            "effect_magnitude": self.effect_magnitude,
            "measurement_tool": self.measurement_tool,
            "uncertainty_axis_tested": self.uncertainty_axis_tested,
            "falsification_intent": self.falsification_intent,
            "cohort_overlap_ratio": self.cohort_overlap_ratio,
            "provenance_refs": dict(self.provenance_refs),
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class EvidenceSaturationAssessment:
    level: SaturationLevel
    unresolved_contradictions: bool
    major_uncertainty_dimensions_remaining: Tuple[str, ...]
    independence_obtained: Tuple[str, ...]
    redundant_test_axes: Tuple[str, ...]
    executable_high_info_opportunities: Tuple[str, ...]
    marginal_information: str  # high | medium | low | none
    rationale: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "unresolved_contradictions": self.unresolved_contradictions,
            "major_uncertainty_dimensions_remaining": list(self.major_uncertainty_dimensions_remaining),
            "independence_obtained": list(self.independence_obtained),
            "redundant_test_axes": list(self.redundant_test_axes),
            "executable_high_info_opportunities": list(self.executable_high_info_opportunities),
            "marginal_information": self.marginal_information,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class EvidenceSynthesisRecord:
    synthesis_id: str
    proposition_id: str
    proposition_hash: str
    evidence_ids: Tuple[str, ...]
    evidence_hashes: Tuple[str, ...]
    relationship_map: Dict[str, str]
    independence_profiles: Dict[str, Dict[str, Any]]
    supporting_structure: List[Dict[str, Any]]
    disconfirming_structure: List[Dict[str, Any]]
    contradiction_structure: List[Dict[str, Any]]
    invalid_non_informative: List[Dict[str, Any]]
    uncertainty_covered: Tuple[str, ...]
    uncertainty_unresolved: Tuple[str, ...]
    saturation_assessment: Dict[str, Any]
    synthesized_epistemic_state: str
    prior_epistemic_state: str
    scientific_rationale: Tuple[str, ...]
    counterfactual_causality_refs: Tuple[str, ...]
    synthesis_engine_version: str
    created_at: str
    synthesis_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "synthesis_id": self.synthesis_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "evidence_ids": list(self.evidence_ids),
            "evidence_hashes": list(self.evidence_hashes),
            "relationship_map": dict(self.relationship_map),
            "independence_profiles": dict(self.independence_profiles),
            "supporting_structure": list(self.supporting_structure),
            "disconfirming_structure": list(self.disconfirming_structure),
            "contradiction_structure": list(self.contradiction_structure),
            "invalid_non_informative": list(self.invalid_non_informative),
            "uncertainty_covered": list(self.uncertainty_covered),
            "uncertainty_unresolved": list(self.uncertainty_unresolved),
            "saturation_assessment": dict(self.saturation_assessment),
            "synthesized_epistemic_state": self.synthesized_epistemic_state,
            "prior_epistemic_state": self.prior_epistemic_state,
            "scientific_rationale": list(self.scientific_rationale),
            "counterfactual_causality_refs": list(self.counterfactual_causality_refs),
            "synthesis_engine_version": self.synthesis_engine_version,
            "created_at": self.created_at,
            "synthesis_hash": self.synthesis_hash,
        }


@dataclass(frozen=True)
class ResearchPriorityDecision:
    decision_id: str
    proposition_id: str
    synthesis_id: str
    synthesized_epistemic_state: str
    unresolved_uncertainty: Tuple[str, ...]
    saturation_level: str
    marginal_information: str
    contradiction_status: str
    independence_summary: str
    chosen_priority_action: str
    rationale: Tuple[str, ...]
    rejected_alternatives: Tuple[Dict[str, str], ...]
    created_at: str
    synthesis_engine_version: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "proposition_id": self.proposition_id,
            "synthesis_id": self.synthesis_id,
            "synthesized_epistemic_state": self.synthesized_epistemic_state,
            "unresolved_uncertainty": list(self.unresolved_uncertainty),
            "saturation_level": self.saturation_level,
            "marginal_information": self.marginal_information,
            "contradiction_status": self.contradiction_status,
            "independence_summary": self.independence_summary,
            "chosen_priority_action": self.chosen_priority_action,
            "rationale": list(self.rationale),
            "rejected_alternatives": list(self.rejected_alternatives),
            "created_at": self.created_at,
            "synthesis_engine_version": self.synthesis_engine_version,
            "record_hash": self.record_hash,
        }


def stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
