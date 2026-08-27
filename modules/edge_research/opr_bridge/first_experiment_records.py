"""
Phase 3J.2 — Initial first-experiment records (pre-result, proposition-birth only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

OBJECTIVE_RECORD_VERSION = "initial_experiment_objective_v1_3j2"
CANDIDATE_RECORD_VERSION = "first_experiment_candidate_v1_3j2"
PACKAGE_RECORD_VERSION = "initial_experiment_package_v1_3j2"
GENERATOR_VERSION = "first_experiment_generator_v1_3j2"
SELECTOR_VERSION = "first_experiment_selector_lex_v1_3j2"


class CandidateClassification(str, Enum):
    DIRECT_INITIAL_TEST = "DIRECT_INITIAL_TEST"
    FALSIFICATION_CAPABLE = "FALSIFICATION_CAPABLE"
    CONFIRMATORY_ONLY = "CONFIRMATORY_ONLY"
    REDUNDANT_WITH_BIRTH_EVIDENCE = "REDUNDANT_WITH_BIRTH_EVIDENCE"
    REPRESENTATION_ONLY = "REPRESENTATION_ONLY"
    RESCUE_MUTATION = "RESCUE_MUTATION"
    NEW_PROPOSITION_REQUIRED = "NEW_PROPOSITION_REQUIRED"
    NON_INFORMATIVE = "NON_INFORMATIVE"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"


class FirstExperimentDisposition(str, Enum):
    SELECTED = "SELECTED"
    NO_HIGH_INFORMATION_FIRST_EXPERIMENT = "NO_HIGH_INFORMATION_FIRST_EXPERIMENT"
    AMBIGUOUS_FIRST_EXPERIMENT = "AMBIGUOUS_FIRST_EXPERIMENT"


class PackageExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


@dataclass(frozen=True)
class InitialExperimentObjectiveRecord:
    objective_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    target_uncertainty: str
    scientific_vulnerability: str
    why_first: str
    outcome_branches: Dict[str, str]
    forbidden_rescue_mutations: Tuple[str, ...]
    provenance: Dict[str, str]
    directness_rank: int
    created_at: str
    objective_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "target_uncertainty": self.target_uncertainty,
            "scientific_vulnerability": self.scientific_vulnerability,
            "why_first": self.why_first,
            "outcome_branches": dict(self.outcome_branches),
            "forbidden_rescue_mutations": list(self.forbidden_rescue_mutations),
            "provenance": dict(self.provenance),
            "directness_rank": self.directness_rank,
            "created_at": self.created_at,
            "objective_hash": self.objective_hash,
        }


@dataclass(frozen=True)
class FirstExperimentCandidateRecord:
    candidate_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    objective_id: str
    scientific_action_core_hash: str
    scientific_identity: Dict[str, str]
    primary_classification: str
    secondary_classifications: Tuple[str, ...]
    classification_rationale: str
    falsification_capable: bool
    confirmatory_only: bool
    birth_evidence_overlap_fraction: float
    independence_profile: Dict[str, str]
    directness_rank: int
    epistemic_alteration_potential: str
    rescue_risk_status: str
    executability_status: str
    executability_detail: str
    experiment_spec: Optional[Dict[str, Any]]
    representation_envelope: Dict[str, Any]
    created_at: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "objective_id": self.objective_id,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "scientific_identity": dict(self.scientific_identity),
            "primary_classification": self.primary_classification,
            "secondary_classifications": list(self.secondary_classifications),
            "classification_rationale": self.classification_rationale,
            "falsification_capable": self.falsification_capable,
            "confirmatory_only": self.confirmatory_only,
            "birth_evidence_overlap_fraction": self.birth_evidence_overlap_fraction,
            "independence_profile": dict(self.independence_profile),
            "directness_rank": self.directness_rank,
            "epistemic_alteration_potential": self.epistemic_alteration_potential,
            "rescue_risk_status": self.rescue_risk_status,
            "executability_status": self.executability_status,
            "executability_detail": self.executability_detail,
            "experiment_spec": self.experiment_spec,
            "representation_envelope": dict(self.representation_envelope),
            "created_at": self.created_at,
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class InitialExperimentPackage:
    package_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    generator_version: str
    selector_version: str
    objectives: Tuple[InitialExperimentObjectiveRecord, ...]
    candidates_considered: Tuple[FirstExperimentCandidateRecord, ...]
    deduplicated_candidates: Tuple[FirstExperimentCandidateRecord, ...]
    rejected: Tuple[Dict[str, str], ...]
    ranking_trace: Tuple[Dict[str, Any], ...]
    disposition: str
    selected_candidate_id: Optional[str]
    selected_experiment_spec: Optional[Dict[str, Any]]
    selection_reason: str
    human_choice_material: bool
    human_choice_reason: str
    execution_status: str
    created_at: str
    package_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "generator_version": self.generator_version,
            "selector_version": self.selector_version,
            "objectives": [o.to_dict() for o in self.objectives],
            "candidates_considered": [c.to_dict() for c in self.candidates_considered],
            "deduplicated_candidates": [c.to_dict() for c in self.deduplicated_candidates],
            "rejected": [dict(r) for r in self.rejected],
            "ranking_trace": [dict(t) for t in self.ranking_trace],
            "disposition": self.disposition,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_experiment_spec": self.selected_experiment_spec,
            "selection_reason": self.selection_reason,
            "human_choice_material": self.human_choice_material,
            "human_choice_reason": self.human_choice_reason,
            "execution_status": self.execution_status,
            "created_at": self.created_at,
            "package_hash": self.package_hash,
        }


def build_objective_record(
    *,
    proposition_id: str,
    proposition_hash: str,
    target_uncertainty: str,
    scientific_vulnerability: str,
    why_first: str,
    outcome_branches: Dict[str, str],
    forbidden_rescue_mutations: Tuple[str, ...],
    provenance: Dict[str, str],
    directness_rank: int,
) -> InitialExperimentObjectiveRecord:
    ts = utc_now_iso()
    oid = new_id("ieo")
    body = {
        "objective_id": oid,
        "record_version": OBJECTIVE_RECORD_VERSION,
        "proposition_id": proposition_id,
        "proposition_hash": proposition_hash,
        "target_uncertainty": target_uncertainty,
        "scientific_vulnerability": scientific_vulnerability,
        "why_first": why_first,
        "outcome_branches": outcome_branches,
        "forbidden_rescue_mutations": list(forbidden_rescue_mutations),
        "provenance": provenance,
        "directness_rank": directness_rank,
    }
    return InitialExperimentObjectiveRecord(
        objective_id=oid,
        record_version=OBJECTIVE_RECORD_VERSION,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        target_uncertainty=target_uncertainty,
        scientific_vulnerability=scientific_vulnerability,
        why_first=why_first,
        outcome_branches=outcome_branches,
        forbidden_rescue_mutations=forbidden_rescue_mutations,
        provenance=provenance,
        directness_rank=directness_rank,
        created_at=ts,
        objective_hash=stable_hash(body),
    )


def build_candidate_record(
    *,
    proposition_id: str,
    proposition_hash: str,
    objective_id: str,
    scientific_action_core_hash: str,
    scientific_identity: Dict[str, str],
    primary_classification: str,
    secondary_classifications: Tuple[str, ...],
    classification_rationale: str,
    falsification_capable: bool,
    confirmatory_only: bool,
    birth_evidence_overlap_fraction: float,
    independence_profile: Dict[str, str],
    directness_rank: int,
    epistemic_alteration_potential: str,
    rescue_risk_status: str,
    executability_status: str,
    executability_detail: str,
    experiment_spec: Optional[Dict[str, Any]],
    representation_envelope: Dict[str, Any],
) -> FirstExperimentCandidateRecord:
    ts = utc_now_iso()
    cid = new_id("fec")
    body = {
        "candidate_id": cid,
        "record_version": CANDIDATE_RECORD_VERSION,
        "proposition_id": proposition_id,
        "proposition_hash": proposition_hash,
        "objective_id": objective_id,
        "scientific_action_core_hash": scientific_action_core_hash,
        "scientific_identity": scientific_identity,
        "primary_classification": primary_classification,
        "secondary_classifications": list(secondary_classifications),
        "classification_rationale": classification_rationale,
        "falsification_capable": falsification_capable,
        "confirmatory_only": confirmatory_only,
        "birth_evidence_overlap_fraction": birth_evidence_overlap_fraction,
        "independence_profile": independence_profile,
        "directness_rank": directness_rank,
        "epistemic_alteration_potential": epistemic_alteration_potential,
        "rescue_risk_status": rescue_risk_status,
        "executability_status": executability_status,
        "executability_detail": executability_detail,
        "experiment_spec": experiment_spec,
        "representation_envelope": representation_envelope,
    }
    return FirstExperimentCandidateRecord(
        candidate_id=cid,
        record_version=CANDIDATE_RECORD_VERSION,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        objective_id=objective_id,
        scientific_action_core_hash=scientific_action_core_hash,
        scientific_identity=scientific_identity,
        primary_classification=primary_classification,
        secondary_classifications=secondary_classifications,
        classification_rationale=classification_rationale,
        falsification_capable=falsification_capable,
        confirmatory_only=confirmatory_only,
        birth_evidence_overlap_fraction=birth_evidence_overlap_fraction,
        independence_profile=independence_profile,
        directness_rank=directness_rank,
        epistemic_alteration_potential=epistemic_alteration_potential,
        rescue_risk_status=rescue_risk_status,
        executability_status=executability_status,
        executability_detail=executability_detail,
        experiment_spec=experiment_spec,
        representation_envelope=representation_envelope,
        created_at=ts,
        record_hash=stable_hash(body),
    )
