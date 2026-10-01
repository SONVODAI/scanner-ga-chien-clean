"""
Phase 3J.9 — Second cumulative research decision records (DecisionRecord #2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    CandidateActionEvaluation,
    SearchAccountingContext,
)

DECIDER_VERSION = "second_experiment_research_decider_v1_3j9"
GATE_VERSION = "second_experiment_research_decision_gate_v1_3j9"
ENVELOPE_VERSION = "second_experiment_research_decision_envelope_v1_3j9"
STOP_SECOND_RESEARCH_DECISION_FROZEN = "STOP_SECOND_RESEARCH_DECISION_FROZEN"


@dataclass(frozen=True)
class SecondExperimentResearchDecisionEnvelope:
    decision_envelope_id: str
    record_version: str
    decision_ordinal: int
    interpretation_id: str
    interpretation_identity_hash: str
    epistemic_update_id: str
    epistemic_update_hash: str
    first_decision_envelope_id: str
    first_decision_hash: str
    first_interpretation_id: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    cumulative_research_state_identity: str
    research_decision: Dict[str, Any]
    decision_kind: str
    stop_reason: Optional[str]
    cumulative_null_ledger: Tuple[Dict[str, Any], ...]
    surviving_nulls: Tuple[str, ...]
    candidate_evaluations: Tuple[CandidateActionEvaluation, ...]
    search_accounting: SearchAccountingContext
    dependence_summary: Dict[str, Any]
    incremental_evidence_summary: Dict[str, Any]
    confirmation_bias_guard_applied: bool
    mechanical_sequencing_blocked: bool
    third_experiment_generated: bool
    third_experiment_executed: bool
    decider_version: str
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_envelope_id": self.decision_envelope_id,
            "record_version": self.record_version,
            "decision_ordinal": self.decision_ordinal,
            "interpretation_id": self.interpretation_id,
            "interpretation_identity_hash": self.interpretation_identity_hash,
            "epistemic_update_id": self.epistemic_update_id,
            "epistemic_update_hash": self.epistemic_update_hash,
            "first_decision_envelope_id": self.first_decision_envelope_id,
            "first_decision_hash": self.first_decision_hash,
            "first_interpretation_id": self.first_interpretation_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "cumulative_research_state_identity": self.cumulative_research_state_identity,
            "research_decision": dict(self.research_decision),
            "decision_kind": self.decision_kind,
            "stop_reason": self.stop_reason,
            "cumulative_null_ledger": list(self.cumulative_null_ledger),
            "surviving_nulls": list(self.surviving_nulls),
            "candidate_evaluations": [c.to_dict() for c in self.candidate_evaluations],
            "search_accounting": self.search_accounting.to_dict(),
            "dependence_summary": dict(self.dependence_summary),
            "incremental_evidence_summary": dict(self.incremental_evidence_summary),
            "confirmation_bias_guard_applied": self.confirmation_bias_guard_applied,
            "mechanical_sequencing_blocked": self.mechanical_sequencing_blocked,
            "third_experiment_generated": self.third_experiment_generated,
            "third_experiment_executed": self.third_experiment_executed,
            "decider_version": self.decider_version,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def compute_second_decision_identity_hash(
    *,
    interpretation_identity_hash: str,
    epistemic_update_hash: str,
    first_decision_hash: str,
    decider_version: str = DECIDER_VERSION,
) -> str:
    return stable_hash(
        {
            "interpretation_identity_hash": interpretation_identity_hash,
            "epistemic_update_hash": epistemic_update_hash,
            "first_decision_hash": first_decision_hash,
            "decision_ordinal": 2,
            "decider_version": decider_version,
        }
    )


def compute_cumulative_research_state_identity(
    *,
    proposition_hash: str,
    resulting_epistemic_state: str,
    second_interpretation_identity_hash: str,
    first_decision_hash: str,
) -> str:
    return stable_hash(
        {
            "proposition_hash": proposition_hash,
            "resulting_epistemic_state": resulting_epistemic_state,
            "second_interpretation_identity_hash": second_interpretation_identity_hash,
            "first_decision_hash": first_decision_hash,
            "decision_ordinal": 2,
        }
    )


def build_second_decision_envelope(
    *,
    interpretation_id: str,
    interpretation_identity_hash: str,
    epistemic_update_id: str,
    epistemic_update_hash: str,
    first_decision_envelope_id: str,
    first_decision_hash: str,
    first_interpretation_id: str,
    proposition_id: str,
    proposition_hash: str,
    session_id: str,
    cumulative_research_state_identity: str,
    research_decision: Dict[str, Any],
    decision_kind: str,
    stop_reason: Optional[str],
    cumulative_null_ledger: Tuple[Dict[str, Any], ...],
    surviving_nulls: Tuple[str, ...],
    candidate_evaluations: Tuple[CandidateActionEvaluation, ...],
    search_accounting: SearchAccountingContext,
    dependence_summary: Dict[str, Any],
    incremental_evidence_summary: Dict[str, Any],
    confirmation_bias_guard_applied: bool,
    mechanical_sequencing_blocked: bool,
) -> SecondExperimentResearchDecisionEnvelope:
    ts = utc_now_iso()
    deid = new_id("iefd2")
    body = {
        "decision_envelope_id": deid,
        "interpretation_identity_hash": interpretation_identity_hash,
        "epistemic_update_hash": epistemic_update_hash,
        "first_decision_hash": first_decision_hash,
        "research_decision_hash": research_decision.get("record_hash"),
        "decider_version": DECIDER_VERSION,
        "decision_ordinal": 2,
    }
    return SecondExperimentResearchDecisionEnvelope(
        decision_envelope_id=deid,
        record_version=ENVELOPE_VERSION,
        decision_ordinal=2,
        interpretation_id=interpretation_id,
        interpretation_identity_hash=interpretation_identity_hash,
        epistemic_update_id=epistemic_update_id,
        epistemic_update_hash=epistemic_update_hash,
        first_decision_envelope_id=first_decision_envelope_id,
        first_decision_hash=first_decision_hash,
        first_interpretation_id=first_interpretation_id,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        cumulative_research_state_identity=cumulative_research_state_identity,
        research_decision=research_decision,
        decision_kind=decision_kind,
        stop_reason=stop_reason,
        cumulative_null_ledger=cumulative_null_ledger,
        surviving_nulls=surviving_nulls,
        candidate_evaluations=candidate_evaluations,
        search_accounting=search_accounting,
        dependence_summary=dependence_summary,
        incremental_evidence_summary=incremental_evidence_summary,
        confirmation_bias_guard_applied=confirmation_bias_guard_applied,
        mechanical_sequencing_blocked=mechanical_sequencing_blocked,
        third_experiment_generated=False,
        third_experiment_executed=False,
        decider_version=DECIDER_VERSION,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
