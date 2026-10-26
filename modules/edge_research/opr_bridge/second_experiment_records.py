"""
Phase 3J.6 — Second-experiment design records (NOT_EXECUTED, no ToolResult).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

OBJECTIVE_RECORD_VERSION = "second_experiment_objective_v1_3j6"
CANDIDATE_RECORD_VERSION = "second_experiment_candidate_v1_3j6"
PACKAGE_RECORD_VERSION = "second_experiment_package_v1_3j6"
GENERATOR_VERSION = "second_experiment_generator_v1_3j6"
SELECTOR_VERSION = "second_experiment_selector_lex_v1_3j6"
DESIGN_VERSION = "second_experiment_design_v1_3j6"
STOP_SECOND_EXPERIMENT_DESIGNED = "STOP_SECOND_EXPERIMENT_DESIGNED"


class SecondExperimentDisposition(str, Enum):
    SELECTED = "SELECTED"
    NO_FAITHFUL_SECOND_EXPERIMENT = "NO_FAITHFUL_SECOND_EXPERIMENT"
    AMBIGUOUS_SECOND_EXPERIMENT = "AMBIGUOUS_SECOND_EXPERIMENT"
    DECISION_STOPPED = "DECISION_STOPPED"


@dataclass(frozen=True)
class SecondExperimentObjectiveRecord:
    objective_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    research_decision_id: str
    research_decision_hash: str
    selected_action: str
    target_uncertainty: str
    target_null_key: str
    scientific_objective: str
    why_this_design: str
    created_at: str
    objective_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "research_decision_id": self.research_decision_id,
            "research_decision_hash": self.research_decision_hash,
            "selected_action": self.selected_action,
            "target_uncertainty": self.target_uncertainty,
            "target_null_key": self.target_null_key,
            "scientific_objective": self.scientific_objective,
            "why_this_design": self.why_this_design,
            "created_at": self.created_at,
            "objective_hash": self.objective_hash,
        }


@dataclass(frozen=True)
class SecondExperimentCandidateRecord:
    candidate_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    objective_id: str
    scientific_action_core_hash: str
    scientific_identity: Dict[str, str]
    target_null_key: str
    target_uncertainty: str
    scientific_objective: str
    falsification_rationale: str
    informative_observation: str
    cannot_establish: str
    primary_classification: str
    falsification_capable: bool
    birth_evidence_overlap_fraction: float
    first_experiment_overlap_fraction: float
    birth_independence_profile: Dict[str, str]
    first_experiment_independence_profile: Dict[str, str]
    redundancy_assessment: str
    falsification_capability: str
    executability_status: str
    executability_detail: str
    experiment_spec: Optional[Dict[str, Any]]
    representation_envelope: Dict[str, Any]
    experiment_content_hash: str
    content_hash_differs_from_first: bool
    decision_fidelity_ok: bool
    rejection_reasons: Tuple[str, ...]
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
            "target_null_key": self.target_null_key,
            "target_uncertainty": self.target_uncertainty,
            "scientific_objective": self.scientific_objective,
            "falsification_rationale": self.falsification_rationale,
            "informative_observation": self.informative_observation,
            "cannot_establish": self.cannot_establish,
            "primary_classification": self.primary_classification,
            "falsification_capable": self.falsification_capable,
            "birth_evidence_overlap_fraction": self.birth_evidence_overlap_fraction,
            "first_experiment_overlap_fraction": self.first_experiment_overlap_fraction,
            "birth_independence_profile": dict(self.birth_independence_profile),
            "first_experiment_independence_profile": dict(self.first_experiment_independence_profile),
            "redundancy_assessment": self.redundancy_assessment,
            "falsification_capability": self.falsification_capability,
            "executability_status": self.executability_status,
            "executability_detail": self.executability_detail,
            "experiment_spec": self.experiment_spec,
            "representation_envelope": dict(self.representation_envelope),
            "experiment_content_hash": self.experiment_content_hash,
            "content_hash_differs_from_first": self.content_hash_differs_from_first,
            "decision_fidelity_ok": self.decision_fidelity_ok,
            "rejection_reasons": list(self.rejection_reasons),
            "created_at": self.created_at,
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class SecondExperimentPackage:
    package_id: str
    record_version: str
    experiment_ordinal: int
    proposition_id: str
    proposition_hash: str
    epistemic_update_id: str
    epistemic_update_hash: str
    research_decision_id: str
    research_decision_hash: str
    research_state_identity: str
    first_package_id: str
    first_package_hash: str
    first_execution_id: str
    first_execution_identity_hash: str
    generator_version: str
    selector_version: str
    design_version: str
    objective: SecondExperimentObjectiveRecord
    candidates_considered: Tuple[SecondExperimentCandidateRecord, ...]
    deduplicated_candidates: Tuple[SecondExperimentCandidateRecord, ...]
    rejected: Tuple[Dict[str, str], ...]
    ranking_trace: Tuple[Dict[str, str], ...]
    disposition: str
    selected_candidate_id: Optional[str]
    selected_experiment_spec: Optional[Dict[str, Any]]
    selected_experiment_content_hash: Optional[str]
    selection_reason: str
    execution_status: str
    created_at: str
    package_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "record_version": self.record_version,
            "experiment_ordinal": self.experiment_ordinal,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "epistemic_update_id": self.epistemic_update_id,
            "epistemic_update_hash": self.epistemic_update_hash,
            "research_decision_id": self.research_decision_id,
            "research_decision_hash": self.research_decision_hash,
            "research_state_identity": self.research_state_identity,
            "first_package_id": self.first_package_id,
            "first_package_hash": self.first_package_hash,
            "first_execution_id": self.first_execution_id,
            "first_execution_identity_hash": self.first_execution_identity_hash,
            "generator_version": self.generator_version,
            "selector_version": self.selector_version,
            "design_version": self.design_version,
            "objective": self.objective.to_dict(),
            "candidates_considered": [c.to_dict() for c in self.candidates_considered],
            "deduplicated_candidates": [c.to_dict() for c in self.deduplicated_candidates],
            "rejected": [dict(r) for r in self.rejected],
            "ranking_trace": [dict(t) for t in self.ranking_trace],
            "disposition": self.disposition,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_experiment_spec": self.selected_experiment_spec,
            "selected_experiment_content_hash": self.selected_experiment_content_hash,
            "selection_reason": self.selection_reason,
            "execution_status": self.execution_status,
            "created_at": self.created_at,
            "package_hash": self.package_hash,
        }


def build_candidate_record(**kwargs) -> SecondExperimentCandidateRecord:
    ts = utc_now_iso()
    cid = new_id("sec")
    body = {k: v for k, v in kwargs.items() if k not in ("created_at", "record_hash", "candidate_id")}
    body["candidate_id"] = cid
    body["record_version"] = CANDIDATE_RECORD_VERSION
    return SecondExperimentCandidateRecord(
        candidate_id=cid,
        record_version=CANDIDATE_RECORD_VERSION,
        created_at=ts,
        record_hash=stable_hash(body),
        **{k: v for k, v in kwargs.items() if k not in ("candidate_id", "record_version", "created_at", "record_hash")},
    )
