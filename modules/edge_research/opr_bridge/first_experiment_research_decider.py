"""
Phase 3J.5 — First-experiment research decision (no experiment generation/execution).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import load_authoritative_contract
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    DECIDER_VERSION,
    STOP_RESEARCH_DECISION_FROZEN,
    CandidateActionEvaluation,
    SearchAccountingContext,
    build_decision_envelope,
    compute_research_state_identity,
)
from modules.edge_research.opr_bridge.lifecycle_records import (
    EpistemicUpdateRecord,
    EvidenceClass,
    InterpretationResult,
    NextResearchAction,
)
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    build_research_decision,
    decide_next_action,
)
from modules.edge_research.research_search_accounting import (
    HIGH_COMPLEXITY_THRESHOLD,
    HIGH_SEARCH_CARDINALITY_THRESHOLD,
)

NULL_UNCERTAINTY_MAP = {
    "episode_artifact": "episode_robustness",
    "directional_reversal": "directional_effect_full_universe",
    "population_concentration": "population_generalization",
    "context_instability": "context_stability",
}

COHORT_NULL_MAP = {
    "counterexample_period_search": "episode_artifact",
    "episode_holdout_excluding_motivating": "episode_artifact",
    "independent_replication_cohort": "episode_artifact",
    "full_panel_contrast": "directional_reversal",
    "contradiction_discriminating_test": "directional_reversal",
}

FIRST_EXPERIMENT_COMPLEXITY_BASE = 3.0


@dataclass
class FirstExperimentResearchDecisionResult:
    outcome: str
    envelope: Optional[Any]
    stop_boundary: str
    experiment_generated: bool = False
    experiment_executed: bool = False
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "stop_boundary": self.stop_boundary,
            "experiment_generated": self.experiment_generated,
            "experiment_executed": self.experiment_executed,
            "errors": list(self.errors),
            "decider_version": DECIDER_VERSION,
        }


def _interpretation_from_envelope(envelope: FirstExperimentInterpretationEnvelope) -> InterpretationResult:
    bi = envelope.base_interpretation
    return InterpretationResult(
        evidence_class=EvidenceClass(bi["evidence_class"]),
        metrics_used=dict(bi.get("metrics_used") or {}),
        condition_matched=str(bi.get("condition_matched", "")),
        validity_passed=bool(bi.get("validity_passed", True)),
        validity_failures=tuple(bi.get("validity_failures") or ()),
    )


def _epu_from_envelope(envelope: FirstExperimentInterpretationEnvelope) -> EpistemicUpdateRecord:
    epu = envelope.epistemic_update
    return EpistemicUpdateRecord(
        update_id=str(epu["update_id"]),
        proposition_id=str(epu["proposition_id"]),
        prior_epistemic_state=str(epu["prior_epistemic_state"]),
        resulting_epistemic_state=str(epu["resulting_epistemic_state"]),
        evidence_class=str(epu["evidence_class"]),
        experiment_ref=str(epu.get("experiment_ref", envelope.execution_id)),
        tool_result_hash=str(epu["tool_result_hash"]),
        metrics_used=dict(epu.get("metrics_used") or {}),
        condition_matched=str(epu.get("condition_matched", "")),
        unresolved_uncertainty=str(epu.get("unresolved_uncertainty", "")),
        created_at=str(epu["created_at"]),
        lifecycle_version=str(epu.get("lifecycle_version", "")),
        record_hash=str(epu["record_hash"]),
    )


def _find_selected_candidate(package: InitialExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def _build_search_context(
    *,
    experiments_attempted: int = 1,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> SearchAccountingContext:
    complexity = complexity_override if complexity_override is not None else FIRST_EXPERIMENT_COMPLEXITY_BASE
    cardinality = cardinality_override if cardinality_override is not None else experiments_attempted
    budget_exhausted = budget_exhausted_override
    if budget_exhausted is None:
        budget_exhausted = (
            complexity >= HIGH_COMPLEXITY_THRESHOLD or cardinality >= HIGH_SEARCH_CARDINALITY_THRESHOLD
        )
    if budget_exhausted:
        burden = "EXHAUSTED"
    elif experiments_attempted >= 1:
        burden = "MODERATE"
    else:
        burden = "LOW"
    return SearchAccountingContext(
        experiments_attempted=experiments_attempted,
        search_complexity_score=complexity,
        search_cardinality=cardinality,
        evidence_burden_assessment=burden,
        budget_exhausted=budget_exhausted,
    )


def _null_objective(null_key: str) -> str:
    objectives = {
        "episode_artifact": "Test whether effect survives independent of motivating episode",
        "directional_reversal": "Test whether directional commitment holds on independent cohort",
        "population_concentration": "Test whether effect generalizes beyond concentrated subpopulation",
        "context_instability": "Test whether effect is stable across market contexts",
    }
    return objectives.get(null_key, f"Discriminate unresolved null: {null_key}")


def _enumerate_candidates(
    *,
    prop: Dict[str, Any],
    assess,
    first_cohort: str,
    first_target: str,
    baseline_action: str,
    surviving_nulls: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for null_key in surviving_nulls:
        uncertainty = NULL_UNCERTAINTY_MAP.get(null_key, null_key)
        candidates.append(
            {
                "action_family": "TEST_NEXT_NULL",
                "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
                "scientific_objective": _null_objective(null_key),
                "target_uncertainty": uncertainty,
                "target_null_key": null_key,
                "expected_information_contribution": "HIGH",
                "independence_requirement": "HIGH",
                "information_gain_rank": 0,
            }
        )

    candidates.append(
        {
            "action_family": "CONTINUE_FALSIFICATION",
            "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
            "scientific_objective": "Continue falsification per frozen contract mapping",
            "target_uncertainty": first_target,
            "target_null_key": None,
            "expected_information_contribution": "MODERATE",
            "independence_requirement": "MEDIUM",
            "information_gain_rank": 1,
        }
    )

    candidates.append(
        {
            "action_family": "SEEK_REPLICATION",
            "mapped_action_code": NextResearchAction.SEEK_REPLICATION.value,
            "scientific_objective": "Independent replication of partition contrast on new cohort",
            "target_uncertainty": first_target,
            "target_null_key": None,
            "expected_information_contribution": "LOW",
            "independence_requirement": "HIGH",
            "information_gain_rank": 3,
        }
    )

    if baseline_action == NextResearchAction.ABANDON.value:
        candidates.append(
            {
                "action_family": "STOP_REJECT",
                "mapped_action_code": NextResearchAction.ABANDON.value,
                "scientific_objective": "Proposition contradicted strongly enough to abandon",
                "target_uncertainty": "none",
                "target_null_key": None,
                "expected_information_contribution": "NONE",
                "independence_requirement": "NONE",
                "information_gain_rank": 0,
            }
        )

    candidates.append(
        {
            "action_family": "STOP_NO_INFORMATIVE_ACTION",
            "mapped_action_code": NextResearchAction.HOLD_UNRESOLVED.value,
            "scientific_objective": "No admissible informative next action",
            "target_uncertainty": "none",
            "target_null_key": None,
            "expected_information_contribution": "NONE",
            "independence_requirement": "NONE",
            "information_gain_rank": 99,
        }
    )

    if first_cohort == "full_panel_contrast":
        candidates.append(
            {
                "action_family": "SEEK_EPISODE_DIVERSITY",
                "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
                "scientific_objective": "Test episode robustness via holdout cohort",
                "target_uncertainty": "episode_robustness",
                "target_null_key": "episode_artifact",
                "expected_information_contribution": "HIGH",
                "independence_requirement": "HIGH",
                "information_gain_rank": 0,
            }
        )

    return candidates


def _evaluate_candidate(
    cand: Dict[str, Any],
    *,
    assess,
    first_cohort: str,
    first_target: str,
    evidence_class: EvidenceClass,
    search_ctx: SearchAccountingContext,
) -> CandidateActionEvaluation:
    reasons: List[str] = []
    redundancy = 0.0
    admissible = True

    if cand["action_family"] == "SEEK_REPLICATION":
        if evidence_class == EvidenceClass.SUPPORTING:
            if cand["target_uncertainty"] == first_target:
                reasons.append("confirmation_addiction_guard_supportive_same_uncertainty")
                admissible = False
                redundancy = 0.9
        if cand["target_uncertainty"] == first_target and first_cohort in (
            "counterexample_period_search",
            "episode_holdout_excluding_motivating",
        ):
            reasons.append("redundant_with_first_experiment_cohort")
            admissible = False
            redundancy = max(redundancy, 0.85)

    if cand["action_family"] == "TEST_NEXT_NULL":
        null_key = cand.get("target_null_key")
        addressed = COHORT_NULL_MAP.get(first_cohort)
        if null_key == addressed and assess.evidence_relevance == "HIGH":
            reasons.append("null_already_materially_addressed_by_first_experiment")
            admissible = False
            redundancy = 0.95

    if cand["action_family"] in ("CONTINUE_FALSIFICATION", "SEEK_REPLICATION"):
        if cand["target_uncertainty"] == first_target and first_cohort == "full_panel_contrast":
            if cand["action_family"] == "SEEK_REPLICATION":
                reasons.append("replicates_first_experiment_population")
                admissible = False
                redundancy = 0.8

    if cand["action_family"] == "STOP_NO_INFORMATIVE_ACTION":
        admissible = True

    if cand["action_family"] == "STOP_REJECT" and evidence_class != EvidenceClass.DISCONFIRMING:
        reasons.append("stop_reject_requires_disconfirming_evidence")
        admissible = False

    if search_ctx.budget_exhausted and cand["action_family"] not in (
        "STOP_NO_INFORMATIVE_ACTION",
        "STOP_REJECT",
        "STOP_BUDGET",
    ):
        reasons.append("search_budget_exhausted")
        admissible = False

    return CandidateActionEvaluation(
        action_family=cand["action_family"],
        mapped_action_code=cand["mapped_action_code"],
        scientific_objective=cand["scientific_objective"],
        target_uncertainty=cand["target_uncertainty"],
        target_null_key=cand.get("target_null_key"),
        expected_information_contribution=cand["expected_information_contribution"],
        independence_requirement=cand["independence_requirement"],
        admissible=admissible,
        rejection_reasons=tuple(reasons),
        redundancy_score=redundancy,
        information_gain_rank=int(cand["information_gain_rank"]),
    )


def _select_candidate(
    evaluations: Tuple[CandidateActionEvaluation, ...],
    *,
    baseline_action: str,
    search_ctx: SearchAccountingContext,
) -> Tuple[CandidateActionEvaluation, bool, bool]:
    """Return (selected, confirmation_guard_applied, tool_convenience_overridden)."""
    admissible = [e for e in evaluations if e.admissible and e.action_family != "STOP_NO_INFORMATIVE_ACTION"]

    if search_ctx.budget_exhausted:
        stop = next(e for e in evaluations if e.action_family == "STOP_NO_INFORMATIVE_ACTION")
        stop_budget = CandidateActionEvaluation(
            action_family="STOP_BUDGET",
            mapped_action_code=NextResearchAction.HOLD_UNRESOLVED.value,
            scientific_objective="Search budget exhausted — no further experimentation justified",
            target_uncertainty="none",
            target_null_key=None,
            expected_information_contribution="NONE",
            independence_requirement="NONE",
            admissible=True,
            rejection_reasons=(),
            redundancy_score=0.0,
            information_gain_rank=0,
        )
        return stop_budget, True, False

    if not admissible:
        stop = next(e for e in evaluations if e.action_family == "STOP_NO_INFORMATIVE_ACTION")
        return stop, True, False

    falsification_targets = [e for e in admissible if e.action_family == "TEST_NEXT_NULL"]
    if falsification_targets:
        falsification_targets.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
        selected = falsification_targets[0]
        confirmation_guard = any(
            "confirmation_addiction_guard" in r for e in evaluations for r in e.rejection_reasons
        )
        tool_override = selected.action_family == "TEST_NEXT_NULL" and baseline_action == NextResearchAction.SEEK_REPLICATION.value
        return selected, confirmation_guard, tool_override

    if baseline_action == NextResearchAction.ABANDON.value:
        stop = next((e for e in admissible if e.action_family == "STOP_REJECT"), admissible[0])
        return stop, False, False

    baseline_matches = [e for e in admissible if e.mapped_action_code == baseline_action]
    if baseline_matches:
        baseline_matches.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
        return baseline_matches[0], False, False

    admissible.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
    return admissible[0], False, False


def decide_first_experiment_research_action(
    prop: Dict[str, Any],
    package: InitialExperimentPackage,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    *,
    session_id: str,
    search_context_override: Optional[SearchAccountingContext] = None,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> FirstExperimentResearchDecisionResult:
    """
    STOP_FIRST_EVIDENCE_INTERPRETED → research decision → STOP_RESEARCH_DECISION_FROZEN.
    Does NOT generate or execute a second experiment.
    """
    contract = load_authoritative_contract(interpretation_envelope.frozen_contract_ref)
    interpretation = _interpretation_from_envelope(interpretation_envelope)
    update = _epu_from_envelope(interpretation_envelope)
    assess = interpretation_envelope.evidence_assessment

    _, transition_key = apply_epistemic_transition(
        contract, interpretation, interpretation_envelope.prior_epistemic_state
    )
    baseline_action, baseline_reason, baseline_rejected = decide_next_action(
        contract, interpretation, transition_key
    )

    candidate = _find_selected_candidate(package)
    first_cohort = assess.cohort_strategy if assess else "unknown"
    first_target = assess.target_uncertainty if assess else "unknown"
    surviving_nulls = tuple(assess.other_nulls_still_alive or ())
    null_addressed = None
    if assess.null_accounting:
        null_addressed = assess.null_accounting[0].null_key

    search_ctx = search_context_override or _build_search_context(
        complexity_override=complexity_override,
        cardinality_override=cardinality_override,
        budget_exhausted_override=budget_exhausted_override,
    )

    raw_candidates = _enumerate_candidates(
        prop=prop,
        assess=assess,
        first_cohort=first_cohort,
        first_target=first_target,
        baseline_action=baseline_action,
        surviving_nulls=surviving_nulls,
    )
    evaluations = tuple(
        _evaluate_candidate(
            c,
            assess=assess,
            first_cohort=first_cohort,
            first_target=first_target,
            evidence_class=interpretation.evidence_class,
            search_ctx=search_ctx,
        )
        for c in raw_candidates
    )

    selected, confirmation_guard, tool_override = _select_candidate(
        evaluations,
        baseline_action=baseline_action,
        search_ctx=search_ctx,
    )

    is_stop = selected.action_family.startswith("STOP_")
    decision_kind = "STOP" if is_stop else "ACTION"
    stop_reason = selected.action_family if is_stop else None

    chosen_action = selected.mapped_action_code
    if is_stop and selected.action_family == "STOP_BUDGET":
        reason = "Search budget exhausted; no further experimentation justified without new evidence burden relief."
    elif is_stop:
        reason = f"No admissible informative next action: {', '.join(selected.rejection_reasons) or 'all candidates rejected'}"
    else:
        reason = (
            f"{baseline_reason} "
            f"Selected {selected.action_family} targeting {selected.target_uncertainty}"
            + (f" (null={selected.target_null_key})" if selected.target_null_key else "")
            + f"; expected information={selected.expected_information_contribution}."
        )

    rejected = [
        {
            "action_code": e.mapped_action_code,
            "action_family": e.action_family,
            "scientific_justification": e.scientific_objective,
            "rejection_reasons": list(e.rejection_reasons),
        }
        for e in evaluations
        if not e.admissible or e.action_family != selected.action_family
    ]

    research_decision = build_research_decision(
        prop,
        contract,
        interpretation,
        update,
        chosen_action=chosen_action,
        reason=reason,
        rejected=rejected,
    )

    state_identity = compute_research_state_identity(
        proposition_hash=interpretation_envelope.proposition_hash,
        resulting_epistemic_state=interpretation_envelope.resulting_epistemic_state,
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
    )

    envelope = build_decision_envelope(
        interpretation_id=interpretation_envelope.interpretation_id,
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
        epistemic_update_id=update.update_id,
        epistemic_update_hash=update.record_hash,
        proposition_id=interpretation_envelope.proposition_id,
        proposition_hash=interpretation_envelope.proposition_hash,
        session_id=session_id,
        research_state_identity=state_identity,
        research_decision=research_decision.to_dict(),
        decision_kind=decision_kind,
        stop_reason=stop_reason,
        surviving_nulls=surviving_nulls,
        null_addressed_by_first_experiment=null_addressed,
        candidate_evaluations=evaluations,
        search_accounting=search_ctx,
        confirmation_bias_guard_applied=confirmation_guard,
        tool_convenience_overridden=tool_override,
    )

    return FirstExperimentResearchDecisionResult(
        outcome="DECIDED" if not is_stop else "STOPPED",
        envelope=envelope,
        stop_boundary=STOP_RESEARCH_DECISION_FROZEN,
        experiment_generated=False,
        experiment_executed=False,
    )
