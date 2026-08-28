"""
Phase 3I.16 — Scientific action record types (research-only, append-only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceIndependenceProfile,
    stable_hash,
    utc_now_iso,
    new_id,
)

GENERATOR_VERSION = "scientific_action_generator_v1_3i16"
SELECTOR_VERSION = "lexicographic_scientific_action_selector_v1_3i16"
OPERATOR_SET_VERSION = "scientific_action_operators_v1_3i16"
OBJECTIVE_RECORD_VERSION = "scientific_objective_record_v1_3i16"
CANDIDATE_RECORD_VERSION = "scientific_action_candidate_v1_3i16"
PACKAGE_RECORD_VERSION = "next_action_package_v1_3i16"


class ExecutabilityClass(str, Enum):
    SCIENTIFICALLY_VALID_EXECUTABLE = "SCIENTIFICALLY_VALID_EXECUTABLE"
    SCIENTIFICALLY_VALID_NOT_EXECUTABLE = "SCIENTIFICALLY_VALID_NOT_EXECUTABLE"
    EXECUTABLE_BUT_LOW_INFORMATION = "EXECUTABLE_BUT_LOW_INFORMATION"
    REPRESENTATION_ONLY = "REPRESENTATION_ONLY"
    RESCUE_RISK = "RESCUE_RISK"
    INVALID = "INVALID"


class RedundancyClass(str, Enum):
    NOVEL = "NOVEL"
    MARGINAL = "MARGINAL"
    REDUNDANT = "REDUNDANT"


class RescueRiskClass(str, Enum):
    PASS = "pass"
    POPULATION_NARROWING = "population_narrowing"
    HORIZON_MUTATION = "horizon_mutation"
    OUTCOME_MUTATION = "outcome_mutation"
    FEATURE_MUTATION = "feature_mutation"
    FORK_REQUIRED = "FORK_REQUIRED"


class ActionDisposition(str, Enum):
    SELECTED = "SELECTED"
    HOLD = "HOLD"
    NO_HIGH_INFORMATION_ACTION = "NO_HIGH_INFORMATION_ACTION"
    AMBIGUOUS_TIE = "AMBIGUOUS_TIE"


@dataclass(frozen=True)
class ScientificActionCore:
    """Semantic identity — excludes tool representation envelope."""

    objective_target_uncertainty: str
    proposition_commitment_challenged: str
    cohort_strategy: str
    contrast_relation: str
    expected_epistemic_consequence_type: str
    information_gain_type: str

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "objective_target_uncertainty": self.objective_target_uncertainty,
            "proposition_commitment_challenged": self.proposition_commitment_challenged,
            "cohort_strategy": self.cohort_strategy,
            "contrast_relation": self.contrast_relation,
            "expected_epistemic_consequence_type": self.expected_epistemic_consequence_type,
            "information_gain_type": self.information_gain_type,
        }

    @property
    def core_hash(self) -> str:
        return stable_hash(self.to_canonical_dict())


@dataclass(frozen=True)
class EpistemicConsequenceContract:
    if_supporting: str
    if_disconfirming: str
    if_contradictory: str
    if_non_informative: str
    if_invalid: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "if_supporting": self.if_supporting,
            "if_disconfirming": self.if_disconfirming,
            "if_contradictory": self.if_contradictory,
            "if_non_informative": self.if_non_informative,
            "if_invalid": self.if_invalid,
        }


@dataclass(frozen=True)
class ScientificObjectiveRecord:
    objective_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    synthesis_id: str
    synthesis_hash: str
    priority_decision_id: str
    priority_record_hash: str
    target_uncertainty: str
    scientific_vulnerability: str
    reason_this_uncertainty_matters: str
    current_evidence_coverage: Tuple[str, ...]
    desired_information_contribution: str
    required_independence_characteristics: Tuple[str, ...]
    falsification_relevant: bool
    contradiction_resolution_relevant: bool
    forbidden_rescue_mutations: Tuple[str, ...]
    provenance: Dict[str, str]
    created_at: str
    objective_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "synthesis_id": self.synthesis_id,
            "synthesis_hash": self.synthesis_hash,
            "priority_decision_id": self.priority_decision_id,
            "priority_record_hash": self.priority_record_hash,
            "target_uncertainty": self.target_uncertainty,
            "scientific_vulnerability": self.scientific_vulnerability,
            "reason_this_uncertainty_matters": self.reason_this_uncertainty_matters,
            "current_evidence_coverage": list(self.current_evidence_coverage),
            "desired_information_contribution": self.desired_information_contribution,
            "required_independence_characteristics": list(self.required_independence_characteristics),
            "falsification_relevant": self.falsification_relevant,
            "contradiction_resolution_relevant": self.contradiction_resolution_relevant,
            "forbidden_rescue_mutations": list(self.forbidden_rescue_mutations),
            "provenance": dict(self.provenance),
            "created_at": self.created_at,
            "objective_hash": self.objective_hash,
        }


@dataclass(frozen=True)
class ScientificActionCandidateRecord:
    action_candidate_id: str
    record_version: str
    objective_id: str
    objective_hash: str
    action_scientific_semantics: str
    proposition_commitment_challenged: str
    evidence_cohort_semantics: str
    expected_new_uncertainty_coverage: str
    expected_independence_profile: Dict[str, str]
    epistemic_consequences: EpistemicConsequenceContract
    falsification_capability: bool
    contradiction_resolution_capability: bool
    redundancy_classification: str
    rescue_risk_classification: str
    executability_classification: str
    executability_detail: str
    scientific_action_core: ScientificActionCore
    representation_envelope: Dict[str, Any]
    experiment_spec: Optional[Dict[str, Any]]
    operator_id: str
    provenance: Dict[str, str]
    created_at: str
    record_hash: str

    @property
    def scientific_action_core_hash(self) -> str:
        return self.scientific_action_core.core_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_candidate_id": self.action_candidate_id,
            "record_version": self.record_version,
            "objective_id": self.objective_id,
            "objective_hash": self.objective_hash,
            "action_scientific_semantics": self.action_scientific_semantics,
            "proposition_commitment_challenged": self.proposition_commitment_challenged,
            "evidence_cohort_semantics": self.evidence_cohort_semantics,
            "expected_new_uncertainty_coverage": self.expected_new_uncertainty_coverage,
            "expected_independence_profile": dict(self.expected_independence_profile),
            "epistemic_consequences": self.epistemic_consequences.to_dict(),
            "falsification_capability": self.falsification_capability,
            "contradiction_resolution_capability": self.contradiction_resolution_capability,
            "redundancy_classification": self.redundancy_classification,
            "rescue_risk_classification": self.rescue_risk_classification,
            "executability_classification": self.executability_classification,
            "executability_detail": self.executability_detail,
            "scientific_action_core": self.scientific_action_core.to_canonical_dict(),
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "representation_envelope": dict(self.representation_envelope),
            "experiment_spec": dict(self.experiment_spec) if self.experiment_spec else None,
            "operator_id": self.operator_id,
            "provenance": dict(self.provenance),
            "created_at": self.created_at,
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class NextActionPackage:
    package_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    synthesis_id: str
    synthesis_hash: str
    priority_decision_id: str
    priority_record_hash: str
    disposition: str
    selected_objective: Optional[ScientificObjectiveRecord]
    candidate_set_hash: str
    generator_version: str
    generator_content_hash: str
    operator_set_hash: str
    selector_version: str
    selected_candidate: Optional[ScientificActionCandidateRecord]
    selected_core_hash: Optional[str]
    experiment_spec: Optional[Dict[str, Any]]
    epistemic_consequence_contract: Optional[Dict[str, Any]]
    cutoff_leakage_policy: str
    anti_rescue_constraints: Tuple[str, ...]
    created_at: str
    execution_status: str
    package_hash: str
    candidate_count: int
    eligible_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "synthesis_id": self.synthesis_id,
            "synthesis_hash": self.synthesis_hash,
            "priority_decision_id": self.priority_decision_id,
            "priority_record_hash": self.priority_record_hash,
            "disposition": self.disposition,
            "selected_objective": self.selected_objective.to_dict() if self.selected_objective else None,
            "candidate_set_hash": self.candidate_set_hash,
            "generator_version": self.generator_version,
            "generator_content_hash": self.generator_content_hash,
            "operator_set_hash": self.operator_set_hash,
            "selector_version": self.selector_version,
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            "selected_core_hash": self.selected_core_hash,
            "experiment_spec": dict(self.experiment_spec) if self.experiment_spec else None,
            "epistemic_consequence_contract": dict(self.epistemic_consequence_contract) if self.epistemic_consequence_contract else None,
            "cutoff_leakage_policy": self.cutoff_leakage_policy,
            "anti_rescue_constraints": list(self.anti_rescue_constraints),
            "created_at": self.created_at,
            "execution_status": self.execution_status,
            "package_hash": self.package_hash,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
        }


FORBIDDEN_RESCUE_MUTATIONS = (
    "outcome_field",
    "horizon",
    "population_refine",
    "population_widen",
    "feature_change",
    "relation_direction",
    "threshold_change",
)


def build_objective_record(
    *,
    proposition_id: str,
    proposition_hash: str,
    synthesis_id: str,
    synthesis_hash: str,
    priority_decision_id: str,
    priority_record_hash: str,
    target_uncertainty: str,
    scientific_vulnerability: str,
    reason_this_uncertainty_matters: str,
    current_evidence_coverage: Tuple[str, ...],
    desired_information_contribution: str,
    required_independence_characteristics: Tuple[str, ...],
    falsification_relevant: bool,
    contradiction_resolution_relevant: bool,
    provenance: Dict[str, str],
    created_at: Optional[str] = None,
    objective_id: Optional[str] = None,
) -> ScientificObjectiveRecord:
    oid = objective_id or new_id("obj")
    ts = created_at or utc_now_iso()
    payload = {
        "record_version": OBJECTIVE_RECORD_VERSION,
        "proposition_id": proposition_id,
        "proposition_hash": proposition_hash,
        "synthesis_id": synthesis_id,
        "synthesis_hash": synthesis_hash,
        "priority_decision_id": priority_decision_id,
        "priority_record_hash": priority_record_hash,
        "target_uncertainty": target_uncertainty,
        "scientific_vulnerability": scientific_vulnerability,
        "reason_this_uncertainty_matters": reason_this_uncertainty_matters,
        "current_evidence_coverage": current_evidence_coverage,
        "desired_information_contribution": desired_information_contribution,
        "required_independence_characteristics": required_independence_characteristics,
        "falsification_relevant": falsification_relevant,
        "contradiction_resolution_relevant": contradiction_resolution_relevant,
        "forbidden_rescue_mutations": FORBIDDEN_RESCUE_MUTATIONS,
        "provenance": provenance,
        "created_at": ts,
    }
    return ScientificObjectiveRecord(
        objective_id=oid,
        objective_hash=stable_hash(payload),
        **payload,
    )


def build_candidate_record(
    *,
    objective: ScientificObjectiveRecord,
    action_scientific_semantics: str,
    proposition_commitment_challenged: str,
    evidence_cohort_semantics: str,
    expected_new_uncertainty_coverage: str,
    expected_independence_profile: Dict[str, str],
    epistemic_consequences: EpistemicConsequenceContract,
    falsification_capability: bool,
    contradiction_resolution_capability: bool,
    redundancy_classification: str,
    rescue_risk_classification: str,
    executability_classification: str,
    executability_detail: str,
    scientific_action_core: ScientificActionCore,
    representation_envelope: Dict[str, Any],
    experiment_spec: Optional[Dict[str, Any]],
    operator_id: str,
    provenance: Dict[str, str],
    created_at: Optional[str] = None,
    action_candidate_id: Optional[str] = None,
) -> ScientificActionCandidateRecord:
    cid = action_candidate_id or new_id("sac")
    ts = created_at or utc_now_iso()
    payload = {
        "record_version": CANDIDATE_RECORD_VERSION,
        "objective_id": objective.objective_id,
        "objective_hash": objective.objective_hash,
        "action_scientific_semantics": action_scientific_semantics,
        "proposition_commitment_challenged": proposition_commitment_challenged,
        "evidence_cohort_semantics": evidence_cohort_semantics,
        "expected_new_uncertainty_coverage": expected_new_uncertainty_coverage,
        "expected_independence_profile": expected_independence_profile,
        "epistemic_consequences": epistemic_consequences.to_dict(),
        "falsification_capability": falsification_capability,
        "contradiction_resolution_capability": contradiction_resolution_capability,
        "redundancy_classification": redundancy_classification,
        "rescue_risk_classification": rescue_risk_classification,
        "executability_classification": executability_classification,
        "executability_detail": executability_detail,
        "scientific_action_core": scientific_action_core.to_canonical_dict(),
        "representation_envelope": representation_envelope,
        "experiment_spec": experiment_spec,
        "operator_id": operator_id,
        "provenance": provenance,
        "created_at": ts,
    }
    return ScientificActionCandidateRecord(
        action_candidate_id=cid,
        record_hash=stable_hash(payload),
        epistemic_consequences=epistemic_consequences,
        scientific_action_core=scientific_action_core,
        objective_id=objective.objective_id,
        objective_hash=objective.objective_hash,
        action_scientific_semantics=action_scientific_semantics,
        proposition_commitment_challenged=proposition_commitment_challenged,
        evidence_cohort_semantics=evidence_cohort_semantics,
        expected_new_uncertainty_coverage=expected_new_uncertainty_coverage,
        expected_independence_profile=expected_independence_profile,
        falsification_capability=falsification_capability,
        contradiction_resolution_capability=contradiction_resolution_capability,
        redundancy_classification=redundancy_classification,
        rescue_risk_classification=rescue_risk_classification,
        executability_classification=executability_classification,
        executability_detail=executability_detail,
        representation_envelope=representation_envelope,
        experiment_spec=experiment_spec,
        operator_id=operator_id,
        provenance=provenance,
        created_at=ts,
        record_version=CANDIDATE_RECORD_VERSION,
    )
