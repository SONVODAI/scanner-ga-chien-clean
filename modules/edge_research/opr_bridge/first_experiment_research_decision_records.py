"""
Phase 3J.5 — First-experiment research decision records (decision only, no execution).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

DECIDER_VERSION = "first_experiment_research_decider_v1_3j5"
GATE_VERSION = "first_experiment_research_decision_gate_v1_3j5"
ENVELOPE_VERSION = "first_experiment_research_decision_envelope_v1_3j5"
STOP_RESEARCH_DECISION_FROZEN = "STOP_RESEARCH_DECISION_FROZEN"


@dataclass(frozen=True)
class SearchAccountingContext:
    experiments_attempted: int
    search_complexity_score: float
    search_cardinality: int
    evidence_burden_assessment: str
    budget_exhausted: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiments_attempted": self.experiments_attempted,
            "search_complexity_score": self.search_complexity_score,
            "search_cardinality": self.search_cardinality,
            "evidence_burden_assessment": self.evidence_burden_assessment,
            "budget_exhausted": self.budget_exhausted,
        }


@dataclass(frozen=True)
class CandidateActionEvaluation:
    action_family: str
    mapped_action_code: str
    scientific_objective: str
    target_uncertainty: str
    target_null_key: Optional[str]
    expected_information_contribution: str
    independence_requirement: str
    admissible: bool
    rejection_reasons: Tuple[str, ...]
    redundancy_score: float
    information_gain_rank: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_family": self.action_family,
            "mapped_action_code": self.mapped_action_code,
            "scientific_objective": self.scientific_objective,
            "target_uncertainty": self.target_uncertainty,
            "target_null_key": self.target_null_key,
            "expected_information_contribution": self.expected_information_contribution,
            "independence_requirement": self.independence_requirement,
            "admissible": self.admissible,
            "rejection_reasons": list(self.rejection_reasons),
            "redundancy_score": self.redundancy_score,
            "information_gain_rank": self.information_gain_rank,
        }


@dataclass(frozen=True)
class FirstExperimentResearchDecisionEnvelope:
    decision_envelope_id: str
    record_version: str
    interpretation_id: str
    interpretation_identity_hash: str
    epistemic_update_id: str
    epistemic_update_hash: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    research_state_identity: str
    research_decision: Dict[str, Any]
    decision_kind: str
    stop_reason: Optional[str]
    surviving_nulls: Tuple[str, ...]
    null_addressed_by_first_experiment: Optional[str]
    candidate_evaluations: Tuple[CandidateActionEvaluation, ...]
    search_accounting: SearchAccountingContext
    confirmation_bias_guard_applied: bool
    tool_convenience_overridden: bool
    second_experiment_generated: bool
    second_experiment_executed: bool
    decider_version: str
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_envelope_id": self.decision_envelope_id,
            "record_version": self.record_version,
            "interpretation_id": self.interpretation_id,
            "interpretation_identity_hash": self.interpretation_identity_hash,
            "epistemic_update_id": self.epistemic_update_id,
            "epistemic_update_hash": self.epistemic_update_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "research_state_identity": self.research_state_identity,
            "research_decision": dict(self.research_decision),
            "decision_kind": self.decision_kind,
            "stop_reason": self.stop_reason,
            "surviving_nulls": list(self.surviving_nulls),
            "null_addressed_by_first_experiment": self.null_addressed_by_first_experiment,
            "candidate_evaluations": [c.to_dict() for c in self.candidate_evaluations],
            "search_accounting": self.search_accounting.to_dict(),
            "confirmation_bias_guard_applied": self.confirmation_bias_guard_applied,
            "tool_convenience_overridden": self.tool_convenience_overridden,
            "second_experiment_generated": self.second_experiment_generated,
            "second_experiment_executed": self.second_experiment_executed,
            "decider_version": self.decider_version,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def compute_decision_identity_hash(
    *,
    interpretation_identity_hash: str,
    epistemic_update_hash: str,
    decider_version: str = DECIDER_VERSION,
) -> str:
    return stable_hash(
        {
            "interpretation_identity_hash": interpretation_identity_hash,
            "epistemic_update_hash": epistemic_update_hash,
            "decider_version": decider_version,
        }
    )


def compute_research_state_identity(
    *,
    proposition_hash: str,
    resulting_epistemic_state: str,
    interpretation_identity_hash: str,
) -> str:
    return stable_hash(
        {
            "proposition_hash": proposition_hash,
            "resulting_epistemic_state": resulting_epistemic_state,
            "interpretation_identity_hash": interpretation_identity_hash,
        }
    )


def build_decision_envelope(
    *,
    interpretation_id: str,
    interpretation_identity_hash: str,
    epistemic_update_id: str,
    epistemic_update_hash: str,
    proposition_id: str,
    proposition_hash: str,
    session_id: str,
    research_state_identity: str,
    research_decision: Dict[str, Any],
    decision_kind: str,
    stop_reason: Optional[str],
    surviving_nulls: Tuple[str, ...],
    null_addressed_by_first_experiment: Optional[str],
    candidate_evaluations: Tuple[CandidateActionEvaluation, ...],
    search_accounting: SearchAccountingContext,
    confirmation_bias_guard_applied: bool,
    tool_convenience_overridden: bool,
) -> FirstExperimentResearchDecisionEnvelope:
    ts = utc_now_iso()
    deid = new_id("iefd")
    body = {
        "decision_envelope_id": deid,
        "interpretation_identity_hash": interpretation_identity_hash,
        "epistemic_update_hash": epistemic_update_hash,
        "research_decision_hash": research_decision.get("record_hash"),
        "decider_version": DECIDER_VERSION,
    }
    return FirstExperimentResearchDecisionEnvelope(
        decision_envelope_id=deid,
        record_version=ENVELOPE_VERSION,
        interpretation_id=interpretation_id,
        interpretation_identity_hash=interpretation_identity_hash,
        epistemic_update_id=epistemic_update_id,
        epistemic_update_hash=epistemic_update_hash,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        research_state_identity=research_state_identity,
        research_decision=research_decision,
        decision_kind=decision_kind,
        stop_reason=stop_reason,
        surviving_nulls=surviving_nulls,
        null_addressed_by_first_experiment=null_addressed_by_first_experiment,
        candidate_evaluations=candidate_evaluations,
        search_accounting=search_accounting,
        confirmation_bias_guard_applied=confirmation_bias_guard_applied,
        tool_convenience_overridden=tool_convenience_overridden,
        second_experiment_generated=False,
        second_experiment_executed=False,
        decider_version=DECIDER_VERSION,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
