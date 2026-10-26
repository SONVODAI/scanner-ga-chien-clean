"""
Phase 3J.12 — Normalize prior research decisions for generic Experiment #N follow-on.

Bridges first-decision envelopes (research_state_identity) and cumulative follow-on
decisions (cumulative_research_state_identity) into one authoritative view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    FirstExperimentResearchDecisionEnvelope,
    CandidateActionEvaluation,
    SearchAccountingContext,
)


@dataclass(frozen=True)
class NormalizedPriorDecision:
    decision_envelope_id: str
    envelope_hash: str
    decision_ordinal: int
    research_state_identity: str
    research_decision: Dict[str, Any]
    decision_kind: str
    stop_reason: Optional[str]
    proposition_id: str
    proposition_hash: str
    session_id: str
    interpretation_id: str
    interpretation_identity_hash: str
    epistemic_update_id: str
    epistemic_update_hash: str
    birth_decision_envelope_id: str
    birth_decision_hash: str
    birth_interpretation_id: str
    cumulative_null_ledger: Tuple[Dict[str, Any], ...]
    search_accounting: SearchAccountingContext
    prior_decision_hash: str
    candidate_evaluations: Tuple[CandidateActionEvaluation, ...] = ()

    @property
    def is_action(self) -> bool:
        return self.decision_kind == "ACTION"


def _search_from_dict(sa: Dict[str, Any]) -> SearchAccountingContext:
    return SearchAccountingContext(
        experiments_attempted=int(sa.get("experiments_attempted", 1)),
        search_complexity_score=float(sa.get("search_complexity_score", 0.0)),
        search_cardinality=int(sa.get("search_cardinality", 1)),
        evidence_burden_assessment=str(sa.get("evidence_burden_assessment", "MODERATE")),
        budget_exhausted=bool(sa.get("budget_exhausted", False)),
    )


def _evaluations_from_dict(decision_dict: Dict[str, Any]) -> Tuple[CandidateActionEvaluation, ...]:
    return tuple(
        CandidateActionEvaluation(
            action_family=e["action_family"],
            mapped_action_code=e["mapped_action_code"],
            scientific_objective=e["scientific_objective"],
            target_uncertainty=e["target_uncertainty"],
            target_null_key=e.get("target_null_key"),
            expected_information_contribution=e["expected_information_contribution"],
            independence_requirement=e["independence_requirement"],
            admissible=bool(e["admissible"]),
            rejection_reasons=tuple(e.get("rejection_reasons") or ()),
            redundancy_score=float(e.get("redundancy_score", 0.0)),
            information_gain_rank=int(e.get("information_gain_rank", 0)),
        )
        for e in decision_dict.get("candidate_evaluations") or []
    )


def normalize_prior_decision(decision_dict: Dict[str, Any]) -> NormalizedPriorDecision:
    """Parse any frozen decision envelope (ordinal 1 or N>=2) into canonical prior view."""
    ordinal = int(decision_dict.get("decision_ordinal", 1))
    rs_id = decision_dict.get("research_state_identity") or decision_dict.get(
        "cumulative_research_state_identity", ""
    )
    if not rs_id:
        raise ValueError("prior decision missing research_state_identity")

    sa = decision_dict.get("search_accounting") or {}
    birth_dec_id = decision_dict.get("first_decision_envelope_id") or decision_dict.get(
        "decision_envelope_id", ""
    )
    birth_dec_hash = decision_dict.get("first_decision_hash") or decision_dict.get("envelope_hash", "")
    birth_interp_id = decision_dict.get("first_interpretation_id") or decision_dict.get(
        "interpretation_id", ""
    )
    prior_hash = decision_dict.get("envelope_hash", "")

    return NormalizedPriorDecision(
        decision_envelope_id=str(decision_dict["decision_envelope_id"]),
        envelope_hash=str(decision_dict.get("envelope_hash", "")),
        decision_ordinal=ordinal,
        research_state_identity=str(rs_id),
        research_decision=dict(decision_dict.get("research_decision") or {}),
        decision_kind=str(decision_dict.get("decision_kind", "")),
        stop_reason=decision_dict.get("stop_reason"),
        proposition_id=str(decision_dict["proposition_id"]),
        proposition_hash=str(decision_dict["proposition_hash"]),
        session_id=str(decision_dict.get("session_id", "")),
        interpretation_id=str(decision_dict["interpretation_id"]),
        interpretation_identity_hash=str(decision_dict.get("interpretation_identity_hash", "")),
        epistemic_update_id=str(decision_dict.get("epistemic_update_id", "")),
        epistemic_update_hash=str(decision_dict.get("epistemic_update_hash", "")),
        birth_decision_envelope_id=str(birth_dec_id),
        birth_decision_hash=str(birth_dec_hash),
        birth_interpretation_id=str(birth_interp_id),
        cumulative_null_ledger=tuple(decision_dict.get("cumulative_null_ledger") or ()),
        search_accounting=_search_from_dict(sa),
        prior_decision_hash=str(prior_hash),
        candidate_evaluations=_evaluations_from_dict(decision_dict),
    )


def as_first_decision_envelope_view(norm: NormalizedPriorDecision) -> FirstExperimentResearchDecisionEnvelope:
    """Compatibility view for frozen ordinal-2 pipeline entrypoints."""
    return FirstExperimentResearchDecisionEnvelope(
        decision_envelope_id=norm.decision_envelope_id,
        record_version="follow_on_adapter_view_v1_3j12",
        interpretation_id=norm.interpretation_id,
        interpretation_identity_hash=norm.interpretation_identity_hash,
        epistemic_update_id=norm.epistemic_update_id,
        epistemic_update_hash=norm.epistemic_update_hash,
        proposition_id=norm.proposition_id,
        proposition_hash=norm.proposition_hash,
        session_id=norm.session_id,
        research_state_identity=norm.research_state_identity,
        research_decision=dict(norm.research_decision),
        decision_kind=norm.decision_kind,
        stop_reason=norm.stop_reason,
        candidate_evaluations=norm.candidate_evaluations,
        search_accounting=norm.search_accounting,
        surviving_nulls=tuple(
            n.get("null_key", "") for n in norm.cumulative_null_ledger if n.get("null_key")
        ),
        null_addressed_by_first_experiment=None,
        confirmation_bias_guard_applied=False,
        tool_convenience_overridden=False,
        second_experiment_generated=False,
        second_experiment_executed=False,
        decider_version="follow_on_adapter_v1_3j12",
        created_at="",
        envelope_hash=norm.envelope_hash,
    )
