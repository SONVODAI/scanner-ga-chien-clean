"""
Phase 3J.9 — Second cumulative research decision (DecisionRecord #2, no Experiment #3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import load_authoritative_contract
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
    NullExplanationState,
)
from modules.edge_research.opr_bridge.first_experiment_research_decider import (
    COHORT_NULL_MAP,
    FIRST_EXPERIMENT_COMPLEXITY_BASE,
    NULL_UNCERTAINTY_MAP,
    _null_objective,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    CandidateActionEvaluation,
    FirstExperimentResearchDecisionEnvelope,
    SearchAccountingContext,
)
from modules.edge_research.opr_bridge.lifecycle_records import (
    EpistemicUpdateRecord,
    EvidenceClass,
    InterpretationResult,
    NextResearchAction,
)
from modules.edge_research.opr_bridge.multi_evidence_accounting import CumulativeEvidenceAssessment
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    build_research_decision,
)
from modules.edge_research.opr_bridge import proposition_experiment_interpreter as _pei
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    SecondExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    DECIDER_VERSION,
    STOP_SECOND_RESEARCH_DECISION_FROZEN,
    build_second_decision_envelope,
    compute_cumulative_research_state_identity,
)
from modules.edge_research.research_search_accounting import (
    HIGH_COMPLEXITY_THRESHOLD,
    HIGH_SEARCH_CARDINALITY_THRESHOLD,
)

STANDARD_NULLS = (
    "episode_artifact",
    "directional_reversal",
    "population_concentration",
    "context_instability",
)
SECOND_EXPERIMENT_COMPLEXITY_INCREMENT = 2.0
OVERLAP_BURDEN_INCREMENT = 2.0
WEAK_INCREMENTAL_BURDEN_INCREMENT = 1.5


@dataclass
class SecondExperimentResearchDecisionResult:
    outcome: str
    envelope: Optional[Any]
    stop_boundary: str
    third_experiment_generated: bool = False
    third_experiment_executed: bool = False
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "stop_boundary": self.stop_boundary,
            "third_experiment_generated": self.third_experiment_generated,
            "third_experiment_executed": self.third_experiment_executed,
            "errors": list(self.errors),
            "decider_version": DECIDER_VERSION,
        }


def _interpretation_from_envelope(envelope: SecondExperimentInterpretationEnvelope) -> InterpretationResult:
    bi = envelope.base_interpretation
    return InterpretationResult(
        evidence_class=EvidenceClass(bi["evidence_class"]),
        metrics_used=dict(bi.get("metrics_used") or {}),
        condition_matched=str(bi.get("condition_matched", "")),
        validity_passed=bool(bi.get("validity_passed", True)),
        validity_failures=tuple(bi.get("validity_failures") or ()),
    )


def _epu_from_envelope(envelope: SecondExperimentInterpretationEnvelope) -> EpistemicUpdateRecord:
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


def _null_state_map(cumulative: CumulativeEvidenceAssessment) -> Dict[str, str]:
    return {entry.null_key: entry.state_after for entry in cumulative.cumulative_null_ledger}


def _surviving_nulls_from_ledger(cumulative: CumulativeEvidenceAssessment) -> Tuple[str, ...]:
    material: List[str] = []
    for entry in cumulative.cumulative_null_ledger:
        if entry.state_after in (
            NullExplanationState.STILL_PLAUSIBLE.value,
            NullExplanationState.WEAKENED.value,
        ):
            material.append(entry.null_key)
    return tuple(sorted(material))


def _still_plausible_nulls(cumulative: CumulativeEvidenceAssessment) -> Tuple[str, ...]:
    return tuple(
        sorted(
            entry.null_key
            for entry in cumulative.cumulative_null_ledger
            if entry.state_after == NullExplanationState.STILL_PLAUSIBLE.value
        )
    )


def _tested_null_keys(
    *,
    first_interpretation: Optional[FirstExperimentInterpretationEnvelope],
    second_interpretation: SecondExperimentInterpretationEnvelope,
) -> Tuple[str, ...]:
    tested: List[str] = []
    if first_interpretation and first_interpretation.evidence_assessment.null_accounting:
        tested.append(first_interpretation.evidence_assessment.null_accounting[0].null_key)
    cohort1 = first_interpretation.evidence_assessment.cohort_strategy if first_interpretation else ""
    mapped1 = COHORT_NULL_MAP.get(cohort1)
    if mapped1 and mapped1 not in tested:
        tested.append(mapped1)
    if second_interpretation.evidence_assessment.null_accounting:
        tested.append(second_interpretation.evidence_assessment.null_accounting[0].null_key)
    cohort2 = second_interpretation.evidence_assessment.cohort_strategy
    mapped2 = COHORT_NULL_MAP.get(cohort2)
    if mapped2 and mapped2 not in tested:
        tested.append(mapped2)
    return tuple(sorted(set(tested)))


def _build_cumulative_search_context(
    *,
    cumulative: CumulativeEvidenceAssessment,
    experiments_attempted: int = 2,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> SearchAccountingContext:
    dep = cumulative.dependence_accounting
    inc = cumulative.incremental_contribution
    complexity = FIRST_EXPERIMENT_COMPLEXITY_BASE + SECOND_EXPERIMENT_COMPLEXITY_INCREMENT
    if dep.row_overlap_fraction >= 0.85:
        complexity += OVERLAP_BURDEN_INCREMENT
    if inc.incremental_strength == "WEAK":
        complexity += WEAK_INCREMENTAL_BURDEN_INCREMENT
    if inc.incremental_strength == "INSUFFICIENT":
        complexity += WEAK_INCREMENTAL_BURDEN_INCREMENT + 1.0
    if complexity_override is not None:
        complexity = complexity_override

    cardinality = cardinality_override if cardinality_override is not None else experiments_attempted
    budget_exhausted = budget_exhausted_override
    if budget_exhausted is None:
        budget_exhausted = (
            complexity >= HIGH_COMPLEXITY_THRESHOLD or cardinality >= HIGH_SEARCH_CARDINALITY_THRESHOLD
        )

    burden = "MODERATE"
    if experiments_attempted >= 2:
        burden = "HIGH" if dep.row_overlap_fraction >= 0.85 or inc.incremental_strength in (
            "WEAK",
            "INSUFFICIENT",
        ) else "MODERATE"
    if budget_exhausted:
        burden = "EXHAUSTED"
    elif experiments_attempted < 2:
        burden = "LOW"

    return SearchAccountingContext(
        experiments_attempted=experiments_attempted,
        search_complexity_score=complexity,
        search_cardinality=cardinality,
        evidence_burden_assessment=burden,
        budget_exhausted=budget_exhausted,
    )


def _independent_replication_earned(
    *,
    cumulative: CumulativeEvidenceAssessment,
    resulting_epistemic_state: str,
    still_plausible: Tuple[str, ...],
) -> bool:
    if resulting_epistemic_state not in ("SUPPORTED", "WEAKENED"):
        return False
    if still_plausible:
        return False
    dep = cumulative.dependence_accounting
    if dep.counted_as_independent_replication:
        return False
    major = {"episode_artifact", "directional_reversal"}
    states = _null_state_map(cumulative)
    major_addressed = all(
        states.get(k) in (NullExplanationState.ADDRESSED.value, NullExplanationState.WEAKENED.value)
        for k in major
        if k in states
    )
    return major_addressed and dep.row_overlap_fraction < 0.50


def _enumerate_cumulative_candidates(
    *,
    assess,
    cumulative: CumulativeEvidenceAssessment,
    first_cohort: str,
    second_cohort: str,
    second_target: str,
    baseline_action: str,
    surviving_nulls: Tuple[str, ...],
    still_plausible: Tuple[str, ...],
    tested_nulls: Tuple[str, ...],
    null_states: Dict[str, str],
    independent_replication_earned: bool,
    resulting_epistemic_state: str,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    ledger_keys = {entry.null_key for entry in cumulative.cumulative_null_ledger}

    for null_key in still_plausible:
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

    for null_key in STANDARD_NULLS:
        if null_key in ledger_keys or null_key in tested_nulls:
            continue
        uncertainty = NULL_UNCERTAINTY_MAP.get(null_key, null_key)
        candidates.append(
            {
                "action_family": "TEST_NEXT_NULL",
                "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
                "scientific_objective": _null_objective(null_key),
                "target_uncertainty": uncertainty,
                "target_null_key": null_key,
                "expected_information_contribution": "MODERATE",
                "independence_requirement": "MEDIUM",
                "information_gain_rank": 2,
            }
        )

    for null_key in surviving_nulls:
        if null_key in still_plausible or null_states.get(null_key) != NullExplanationState.WEAKENED.value:
            continue
        uncertainty = NULL_UNCERTAINTY_MAP.get(null_key, null_key)
        candidates.append(
            {
                "action_family": "TEST_NEXT_NULL",
                "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
                "scientific_objective": _null_objective(null_key),
                "target_uncertainty": uncertainty,
                "target_null_key": null_key,
                "expected_information_contribution": "LOW",
                "independence_requirement": "MEDIUM",
                "information_gain_rank": 6,
            }
        )

    if independent_replication_earned:
        candidates.append(
            {
                "action_family": "SEEK_REPLICATION",
                "mapped_action_code": NextResearchAction.SEEK_REPLICATION.value,
                "scientific_objective": "Independent replication on low-overlap cohort after major nulls addressed",
                "target_uncertainty": second_target,
                "target_null_key": None,
                "expected_information_contribution": "HIGH",
                "independence_requirement": "HIGH",
                "information_gain_rank": 1,
            }
        )
    else:
        candidates.append(
            {
                "action_family": "SEEK_REPLICATION",
                "mapped_action_code": NextResearchAction.SEEK_REPLICATION.value,
                "scientific_objective": "Independent replication of partition contrast on new cohort",
                "target_uncertainty": second_target,
                "target_null_key": None,
                "expected_information_contribution": "LOW",
                "independence_requirement": "HIGH",
                "information_gain_rank": 5,
            }
        )

    candidates.append(
        {
            "action_family": "CONTINUE_FALSIFICATION",
            "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
            "scientific_objective": "Continue falsification per frozen contract mapping",
            "target_uncertainty": second_target,
            "target_null_key": None,
            "expected_information_contribution": "MODERATE",
            "independence_requirement": "MEDIUM",
            "information_gain_rank": 4,
        }
    )

    if baseline_action == NextResearchAction.ABANDON.value or resulting_epistemic_state in (
        "WEAKENED",
        "REJECTED",
    ):
        candidates.append(
            {
                "action_family": "STOP_REJECT",
                "mapped_action_code": NextResearchAction.ABANDON.value,
                "scientific_objective": "Cumulative evidence weakens proposition — abandon further confirmation",
                "target_uncertainty": "none",
                "target_null_key": None,
                "expected_information_contribution": "NONE",
                "independence_requirement": "NONE",
                "information_gain_rank": 0,
            }
        )

    candidates.append(
        {
            "action_family": "STOP_LOW_INCREMENTAL",
            "mapped_action_code": NextResearchAction.HOLD_UNRESOLVED.value,
            "scientific_objective": "Latest experiment added weak incremental evidence — further search not justified",
            "target_uncertainty": "none",
            "target_null_key": None,
            "expected_information_contribution": "NONE",
            "independence_requirement": "NONE",
            "information_gain_rank": 0,
        }
    )

    candidates.append(
        {
            "action_family": "STOP_NO_MATERIAL_NULL",
            "mapped_action_code": NextResearchAction.HOLD_UNRESOLVED.value,
            "scientific_objective": "No material STILL_PLAUSIBLE null remains after cumulative testing",
            "target_uncertainty": "none",
            "target_null_key": None,
            "expected_information_contribution": "NONE",
            "independence_requirement": "NONE",
            "information_gain_rank": 1,
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

    if first_cohort == second_cohort == "full_panel_contrast":
        candidates.append(
            {
                "action_family": "SEEK_EPISODE_DIVERSITY",
                "mapped_action_code": NextResearchAction.SEEK_FALSIFICATION.value,
                "scientific_objective": "Test episode robustness via holdout cohort",
                "target_uncertainty": "episode_robustness",
                "target_null_key": "episode_artifact",
                "expected_information_contribution": "MODERATE",
                "independence_requirement": "HIGH",
                "information_gain_rank": 3,
            }
        )

    return candidates


def _evaluate_cumulative_candidate(
    cand: Dict[str, Any],
    *,
    assess,
    cumulative: CumulativeEvidenceAssessment,
    first_cohort: str,
    second_cohort: str,
    second_target: str,
    evidence_class: EvidenceClass,
    search_ctx: SearchAccountingContext,
    tested_nulls: Tuple[str, ...],
    null_states: Dict[str, str],
    still_plausible: Tuple[str, ...],
    independent_replication_earned: bool,
    first_decision_action: Optional[str],
) -> CandidateActionEvaluation:
    reasons: List[str] = []
    redundancy = 0.0
    admissible = True
    dep = cumulative.dependence_accounting
    inc = cumulative.incremental_contribution
    null_key = cand.get("target_null_key")

    if cand["action_family"] == "SEEK_REPLICATION":
        if not independent_replication_earned:
            reasons.append("independent_replication_not_earned")
            admissible = False
            redundancy = 0.85
        if evidence_class in (EvidenceClass.DISCONFIRMING, EvidenceClass.CONTRADICTORY):
            reasons.append("replication_blocked_after_contradictory_evidence")
            admissible = False
            redundancy = max(redundancy, 0.9)
        if inc.conflict_detected:
            reasons.append("replication_blocked_under_cumulative_conflict")
            admissible = False
            redundancy = max(redundancy, 0.88)
        if dep.row_overlap_fraction >= 0.50:
            reasons.append("high_overlap_blocks_independent_replication")
            admissible = False
            redundancy = max(redundancy, dep.row_overlap_fraction)
        if evidence_class == EvidenceClass.SUPPORTING and inc.incremental_strength in ("WEAK", "INSUFFICIENT"):
            reasons.append("confirmation_addiction_guard_weak_incremental_support")
            admissible = False
            redundancy = max(redundancy, 0.9)
        if not dep.counted_as_independent_replication and dep.sample_dependence_level == "HIGH":
            reasons.append("dependent_support_history_not_replication")
            admissible = False
            redundancy = max(redundancy, 0.88)

    if cand["action_family"] == "TEST_NEXT_NULL" and null_key:
        if null_key in tested_nulls and null_states.get(null_key) in (
            NullExplanationState.WEAKENED.value,
            NullExplanationState.ADDRESSED.value,
        ):
            reasons.append("null_already_materially_addressed_by_cumulative_evidence")
            admissible = False
            redundancy = 0.95
        if null_key not in still_plausible and null_states.get(null_key) == NullExplanationState.WEAKENED.value:
            if inc.incremental_strength in ("WEAK", "INSUFFICIENT") and dep.sample_dependence_level == "HIGH":
                reasons.append("weakened_null_low_incremental_gain")
                admissible = False
                redundancy = max(redundancy, 0.8)
        if null_key == COHORT_NULL_MAP.get(second_cohort) and assess.evidence_relevance == "HIGH":
            reasons.append("null_already_addressed_by_second_experiment")
            admissible = False
            redundancy = 0.92

    if cand["action_family"] == "CONTINUE_FALSIFICATION":
        if not still_plausible and search_ctx.evidence_burden_assessment in ("HIGH", "EXHAUSTED"):
            reasons.append("mechanical_falsification_after_exhausted_major_nulls")
            admissible = False
        if first_decision_action == NextResearchAction.SEEK_FALSIFICATION.value and not still_plausible:
            reasons.append("mechanical_sequencing_decision1_falsification")
            admissible = False

    if cand["action_family"] == "SEEK_EPISODE_DIVERSITY":
        if "episode_artifact" in tested_nulls and null_states.get("episode_artifact") == NullExplanationState.WEAKENED.value:
            reasons.append("episode_null_already_weakened")
            admissible = False
            redundancy = 0.85

    if cand["action_family"] == "STOP_LOW_INCREMENTAL":
        admissible = inc.incremental_strength in ("WEAK", "INSUFFICIENT") or dep.sample_dependence_level == "HIGH"
        if not admissible:
            reasons.append("incremental_evidence_not_weak_enough_for_stop")

    if cand["action_family"] == "STOP_NO_MATERIAL_NULL":
        admissible = len(still_plausible) == 0
        if not admissible:
            reasons.append("still_plausible_nulls_remain")

    if cand["action_family"] == "STOP_NO_INFORMATIVE_ACTION":
        admissible = True

    if cand["action_family"] == "STOP_REJECT":
        if evidence_class != EvidenceClass.DISCONFIRMING and cand["mapped_action_code"] == NextResearchAction.ABANDON.value:
            if search_ctx.evidence_burden_assessment != "EXHAUSTED":
                reasons.append("stop_reject_requires_disconfirming_or_exhausted_burden")
                admissible = False

    if search_ctx.budget_exhausted and cand["action_family"] not in (
        "STOP_NO_INFORMATIVE_ACTION",
        "STOP_REJECT",
        "STOP_BUDGET",
        "STOP_LOW_INCREMENTAL",
        "STOP_NO_MATERIAL_NULL",
    ):
        reasons.append("search_budget_exhausted")
        admissible = False

    return CandidateActionEvaluation(
        action_family=cand["action_family"],
        mapped_action_code=cand["mapped_action_code"],
        scientific_objective=cand["scientific_objective"],
        target_uncertainty=cand["target_uncertainty"],
        target_null_key=null_key,
        expected_information_contribution=cand["expected_information_contribution"],
        independence_requirement=cand["independence_requirement"],
        admissible=admissible,
        rejection_reasons=tuple(reasons),
        redundancy_score=redundancy,
        information_gain_rank=int(cand["information_gain_rank"]),
    )


def _select_cumulative_candidate(
    evaluations: Tuple[CandidateActionEvaluation, ...],
    *,
    baseline_action: str,
    search_ctx: SearchAccountingContext,
    cumulative: CumulativeEvidenceAssessment,
    still_plausible: Tuple[str, ...],
    independent_replication_earned: bool,
) -> Tuple[CandidateActionEvaluation, bool, bool]:
    """Return (selected, confirmation_guard_applied, mechanical_sequencing_blocked)."""
    stop_candidates = [e for e in evaluations if e.admissible and e.action_family.startswith("STOP_")]
    admissible = [e for e in evaluations if e.admissible and not e.action_family.startswith("STOP_")]

    if search_ctx.budget_exhausted:
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
        return stop_budget, True, True

    inc = cumulative.incremental_contribution
    dep = cumulative.dependence_accounting
    confirmation_guard = any("confirmation_addiction_guard" in r for e in evaluations for r in e.rejection_reasons)
    mechanical_blocked = any(
        "mechanical_sequencing" in r for e in evaluations for r in e.rejection_reasons
    )

    if inc.incremental_strength in ("WEAK", "INSUFFICIENT") and dep.sample_dependence_level == "HIGH":
        if not still_plausible:
            for stop_family in ("STOP_LOW_INCREMENTAL", "STOP_NO_MATERIAL_NULL"):
                stop = next((e for e in stop_candidates if e.action_family == stop_family and e.admissible), None)
                if stop:
                    return stop, confirmation_guard, mechanical_blocked

    falsification_targets = [
        e for e in admissible if e.action_family == "TEST_NEXT_NULL" and e.target_null_key in still_plausible
    ]
    if falsification_targets:
        falsification_targets.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
        return falsification_targets[0], confirmation_guard, mechanical_blocked

    repl = [e for e in admissible if e.action_family == "SEEK_REPLICATION"]
    if repl and independent_replication_earned:
        return repl[0], confirmation_guard, mechanical_blocked

    if baseline_action == NextResearchAction.ABANDON.value:
        stop = next((e for e in stop_candidates if e.action_family == "STOP_REJECT"), None)
        if stop and stop.admissible:
            return stop, confirmation_guard, mechanical_blocked

    if not admissible:
        stop = next(e for e in stop_candidates if e.action_family == "STOP_NO_INFORMATIVE_ACTION")
        return stop, confirmation_guard, mechanical_blocked

    if search_ctx.evidence_burden_assessment == "HIGH" and inc.incremental_strength in ("WEAK", "INSUFFICIENT"):
        stop = next(
            (e for e in stop_candidates if e.action_family == "STOP_LOW_INCREMENTAL" and e.admissible),
            None,
        )
        if stop and not still_plausible:
            return stop, confirmation_guard, mechanical_blocked

    admissible.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
    tool_override = admissible[0].action_family == "TEST_NEXT_NULL" and baseline_action == NextResearchAction.SEEK_REPLICATION.value
    return admissible[0], confirmation_guard, tool_override


def decide_second_experiment_research_action(
    prop: Dict[str, Any],
    second_interpretation_envelope: SecondExperimentInterpretationEnvelope,
    first_decision_envelope: FirstExperimentResearchDecisionEnvelope,
    *,
    session_id: str,
    first_interpretation_envelope: Optional[FirstExperimentInterpretationEnvelope] = None,
    search_context_override: Optional[SearchAccountingContext] = None,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> SecondExperimentResearchDecisionResult:
    """
    STOP_SECOND_EVIDENCE_INTERPRETED → cumulative research decision → STOP_SECOND_RESEARCH_DECISION_FROZEN.
    Does NOT generate or execute Experiment #3.
    """
    contract = load_authoritative_contract(second_interpretation_envelope.frozen_contract_ref)
    interpretation = _interpretation_from_envelope(second_interpretation_envelope)
    update = _epu_from_envelope(second_interpretation_envelope)
    assess = second_interpretation_envelope.evidence_assessment
    cumulative = second_interpretation_envelope.cumulative_assessment

    _, transition_key = apply_epistemic_transition(
        contract, interpretation, second_interpretation_envelope.prior_epistemic_state
    )
    baseline_action, baseline_reason, _baseline_rejected = _pei.decide_next_action(
        contract, interpretation, transition_key
    )

    first_cohort = (
        first_interpretation_envelope.evidence_assessment.cohort_strategy
        if first_interpretation_envelope
        else "unknown"
    )
    second_cohort = assess.cohort_strategy if assess else "unknown"
    second_target = assess.target_uncertainty if assess else "unknown"
    null_states = _null_state_map(cumulative)
    surviving_nulls = _surviving_nulls_from_ledger(cumulative)
    still_plausible = _still_plausible_nulls(cumulative)
    tested_nulls = _tested_null_keys(
        first_interpretation=first_interpretation_envelope,
        second_interpretation=second_interpretation_envelope,
    )
    repl_earned = _independent_replication_earned(
        cumulative=cumulative,
        resulting_epistemic_state=second_interpretation_envelope.resulting_epistemic_state,
        still_plausible=still_plausible,
    )

    search_ctx = search_context_override or _build_cumulative_search_context(
        cumulative=cumulative,
        complexity_override=complexity_override,
        cardinality_override=cardinality_override,
        budget_exhausted_override=budget_exhausted_override,
    )

    first_chosen = first_decision_envelope.research_decision.get("chosen_next_action")

    raw_candidates = _enumerate_cumulative_candidates(
        assess=assess,
        cumulative=cumulative,
        first_cohort=first_cohort,
        second_cohort=second_cohort,
        second_target=second_target,
        baseline_action=baseline_action,
        surviving_nulls=surviving_nulls,
        still_plausible=still_plausible,
        tested_nulls=tested_nulls,
        null_states=null_states,
        independent_replication_earned=repl_earned,
        resulting_epistemic_state=second_interpretation_envelope.resulting_epistemic_state,
    )
    evaluations = tuple(
        _evaluate_cumulative_candidate(
            c,
            assess=assess,
            cumulative=cumulative,
            first_cohort=first_cohort,
            second_cohort=second_cohort,
            second_target=second_target,
            evidence_class=interpretation.evidence_class,
            search_ctx=search_ctx,
            tested_nulls=tested_nulls,
            null_states=null_states,
            still_plausible=still_plausible,
            independent_replication_earned=repl_earned,
            first_decision_action=first_chosen,
        )
        for c in raw_candidates
    )

    selected, confirmation_guard, mechanical_blocked = _select_cumulative_candidate(
        evaluations,
        baseline_action=baseline_action,
        search_ctx=search_ctx,
        cumulative=cumulative,
        still_plausible=still_plausible,
        independent_replication_earned=repl_earned,
    )

    is_stop = selected.action_family.startswith("STOP_")
    decision_kind = "STOP" if is_stop else "ACTION"
    stop_reason = selected.action_family if is_stop else None

    chosen_action = selected.mapped_action_code
    if is_stop and selected.action_family == "STOP_BUDGET":
        reason = "Search budget exhausted; cumulative evidence burden too high for further experimentation."
    elif is_stop:
        reason = (
            f"Cumulative research decision: {selected.scientific_objective}. "
            f"Incremental strength={cumulative.incremental_contribution.incremental_strength}; "
            f"sample dependence={cumulative.dependence_accounting.sample_dependence_level}; "
            f"evidence burden={search_ctx.evidence_burden_assessment}."
        )
    else:
        reason = (
            f"{baseline_reason} "
            f"Selected {selected.action_family} targeting {selected.target_uncertainty}"
            + (f" (null={selected.target_null_key})" if selected.target_null_key else "")
            + f"; expected information={selected.expected_information_contribution}; "
            f"incremental strength={cumulative.incremental_contribution.incremental_strength}."
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

    state_identity = compute_cumulative_research_state_identity(
        proposition_hash=second_interpretation_envelope.proposition_hash,
        resulting_epistemic_state=second_interpretation_envelope.resulting_epistemic_state,
        second_interpretation_identity_hash=second_interpretation_envelope.interpretation_identity_hash,
        first_decision_hash=first_decision_envelope.envelope_hash,
    )

    envelope = build_second_decision_envelope(
        interpretation_id=second_interpretation_envelope.interpretation_id,
        interpretation_identity_hash=second_interpretation_envelope.interpretation_identity_hash,
        epistemic_update_id=update.update_id,
        epistemic_update_hash=update.record_hash,
        first_decision_envelope_id=first_decision_envelope.decision_envelope_id,
        first_decision_hash=first_decision_envelope.envelope_hash,
        first_interpretation_id=second_interpretation_envelope.first_interpretation_id,
        proposition_id=second_interpretation_envelope.proposition_id,
        proposition_hash=second_interpretation_envelope.proposition_hash,
        session_id=session_id,
        cumulative_research_state_identity=state_identity,
        research_decision=research_decision.to_dict(),
        decision_kind=decision_kind,
        stop_reason=stop_reason,
        cumulative_null_ledger=tuple(n.to_dict() for n in cumulative.cumulative_null_ledger),
        surviving_nulls=surviving_nulls,
        candidate_evaluations=evaluations,
        search_accounting=search_ctx,
        dependence_summary=cumulative.dependence_accounting.to_dict(),
        incremental_evidence_summary=cumulative.incremental_contribution.to_dict(),
        confirmation_bias_guard_applied=confirmation_guard,
        mechanical_sequencing_blocked=mechanical_blocked,
    )

    return SecondExperimentResearchDecisionResult(
        outcome="DECIDED" if not is_stop else "STOPPED",
        envelope=envelope,
        stop_boundary=STOP_SECOND_RESEARCH_DECISION_FROZEN,
        third_experiment_generated=False,
        third_experiment_executed=False,
    )
