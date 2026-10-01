"""
Phase 3I.18 — Scientific frontier reassessment records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, new_id

FRONTIER_REASSESSOR_VERSION = "scientific_frontier_reassessor_v1_3i18"


class ResearchabilityClass(str, Enum):
    RESEARCHABLE_NOW = "RESEARCHABLE_NOW"
    RESEARCHABLE_BUT_REDUNDANT = "RESEARCHABLE_BUT_REDUNDANT"
    NOT_CURRENTLY_EXECUTABLE = "NOT_CURRENTLY_EXECUTABLE"
    LOW_INFORMATION = "LOW_INFORMATION"
    REQUIRES_NEW_PROPOSITION = "REQUIRES_NEW_PROPOSITION"
    COHORT_UNAVAILABLE = "COHORT_UNAVAILABLE"
    HOLD = "HOLD"


class FrontierDecision(str, Enum):
    SELECTED_NON_COHORT_ACTION = "SELECTED_NON_COHORT_ACTION"
    AMBIGUOUS_FRONTIER = "AMBIGUOUS_FRONTIER"
    NO_HIGH_INFORMATION_ACTION = "NO_HIGH_INFORMATION_ACTION"
    HOLD_PROVISIONALLY = "HOLD_PROVISIONALLY"


class StrategyFamilyClass(str, Enum):
    SCIENTIFICALLY_DISTINCT = "SCIENTIFICALLY_DISTINCT"
    REPRESENTATION_ONLY = "REPRESENTATION_ONLY"
    REDUNDANT_WITH_EVIDENCE = "REDUNDANT_WITH_EVIDENCE"
    COHORT_DEPENDENT = "COHORT_DEPENDENT"
    NON_COHORT = "NON_COHORT"
    PROPOSITION_MUTATING = "PROPOSITION_MUTATING"
    NON_EXECUTABLE = "NON_EXECUTABLE"


@dataclass(frozen=True)
class MarginalInformationProfile:
    unresolved_dimension: str
    ledger_overlap_estimate: str
    independence_estimate: str
    counterexample_potential: str
    vulnerability_challenge: str
    epistemic_state_change_potential: str
    redundancy: str
    executability: str
    rescue_risk: str
    rationale: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unresolved_dimension": self.unresolved_dimension,
            "ledger_overlap_estimate": self.ledger_overlap_estimate,
            "independence_estimate": self.independence_estimate,
            "counterexample_potential": self.counterexample_potential,
            "vulnerability_challenge": self.vulnerability_challenge,
            "epistemic_state_change_potential": self.epistemic_state_change_potential,
            "redundancy": self.redundancy,
            "executability": self.executability,
            "rescue_risk": self.rescue_risk,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class UncertaintyFrontierRecord:
    uncertainty_axis: str
    scientific_meaning: str
    evidence_coverage: Tuple[str, ...]
    why_unresolved: str
    partially_addressed: bool
    cohort_binding_impact: str
    epistemic_interpretation_impact: str
    executable_investigation_exists: bool
    researchability: str
    researchability_rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uncertainty_axis": self.uncertainty_axis,
            "scientific_meaning": self.scientific_meaning,
            "evidence_coverage": list(self.evidence_coverage),
            "why_unresolved": self.why_unresolved,
            "partially_addressed": self.partially_addressed,
            "cohort_binding_impact": self.cohort_binding_impact,
            "epistemic_interpretation_impact": self.epistemic_interpretation_impact,
            "executable_investigation_exists": self.executable_investigation_exists,
            "researchability": self.researchability,
            "researchability_rationale": self.researchability_rationale,
        }


@dataclass(frozen=True)
class FrontierActionAssessment:
    candidate_id: str
    core_hash: str
    uncertainty_axis: str
    cohort_strategy: str
    strategy_family_class: str
    scientific_identity: str
    marginal_information: MarginalInformationProfile
    cohort_binding_required: bool
    cohort_binding_disposition: Optional[str]
    available: bool
    availability_reason: str
    disposition: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "core_hash": self.core_hash,
            "uncertainty_axis": self.uncertainty_axis,
            "cohort_strategy": self.cohort_strategy,
            "strategy_family_class": self.strategy_family_class,
            "scientific_identity": self.scientific_identity,
            "marginal_information": self.marginal_information.to_dict(),
            "cohort_binding_required": self.cohort_binding_required,
            "cohort_binding_disposition": self.cohort_binding_disposition,
            "available": self.available,
            "availability_reason": self.availability_reason,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class FrontierReassessmentResult:
    reassessor_version: str
    frontier_decision: FrontierDecision
    uncertainty_frontier: Tuple[UncertaintyFrontierRecord, ...]
    action_assessments: Tuple[FrontierActionAssessment, ...]
    selected_candidate_id: Optional[str]
    selected_core_hash: Optional[str]
    package: Optional[Any]
    reason: str
    silence_rationale: Optional[str]
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reassessor_version": self.reassessor_version,
            "frontier_decision": self.frontier_decision.value,
            "uncertainty_frontier": [u.to_dict() for u in self.uncertainty_frontier],
            "action_assessments": [a.to_dict() for a in self.action_assessments],
            "selected_candidate_id": self.selected_candidate_id,
            "selected_core_hash": self.selected_core_hash,
            "reason": self.reason,
            "silence_rationale": self.silence_rationale,
            "record_hash": self.record_hash,
        }


def reassessor_content_hash() -> str:
    return stable_hash({"version": FRONTIER_REASSESSOR_VERSION})
