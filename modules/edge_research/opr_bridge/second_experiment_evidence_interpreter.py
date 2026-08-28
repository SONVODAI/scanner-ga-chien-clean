"""
Phase 3J.8 — Cumulative second-experiment evidence interpretation (no research decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import load_authoritative_contract
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    COHORT_INTENT,
    _collect_tool_semantic_labels,
    _other_nulls_alive,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    EvidenceDirection,
    EvidenceRelevance,
    EvidenceStrength,
    FirstExperimentInterpretationEnvelope,
    FrozenInterpretationContractRef,
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
    NullExplanationState,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.lifecycle_records import EvidenceClass, QuintileMetrics
from modules.edge_research.opr_bridge.multi_evidence_accounting import (
    apply_incremental_epistemic_transition,
    build_cumulative_assessment,
)
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    build_epistemic_update,
    interpret_experiment_evidence,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage
from modules.edge_research.opr_bridge.second_experiment_interpretation_gate import (
    SecondInterpretationEligibilityResult,
    validate_second_interpretation_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    INTERPRETER_VERSION,
    STOP_SECOND_EVIDENCE_INTERPRETED,
    SecondExperimentInterpretationEnvelope,
    build_second_interpretation_envelope,
    compute_second_interpretation_identity_hash,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage
from modules.edge_research.research_tools import ToolResult, ToolStatus


@dataclass
class SecondExperimentInterpretationResult:
    outcome: str
    eligibility: SecondInterpretationEligibilityResult
    envelope: Optional[SecondExperimentInterpretationEnvelope]
    stop_boundary: str
    research_decision_generated: bool = False
    synthesis_invoked: bool = False
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "eligibility": self.eligibility.to_dict(),
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "stop_boundary": self.stop_boundary,
            "research_decision_generated": self.research_decision_generated,
            "synthesis_invoked": self.synthesis_invoked,
            "errors": list(self.errors),
            "interpreter_version": INTERPRETER_VERSION,
        }


def _tool_result_from_envelope(envelope: SecondExperimentExecutionEnvelope) -> ToolResult:
    tr = envelope.tool_result
    return ToolResult(
        tool_name=str(tr.get("tool_name", "")),
        tool_version=str(tr.get("tool_version", "v1")),
        data_cutoff_date=str(tr.get("data_cutoff_date", "")),
        input_hash=str(tr.get("input_hash", "")),
        sample_size=int(tr.get("sample_size", 0)),
        status=ToolStatus(tr.get("status", "INVALID_INPUT")),
        metrics=dict(tr.get("metrics") or {}),
        groups=dict(tr.get("groups") or {}),
        diagnostics=dict(tr.get("diagnostics") or {}),
        limitations=list(tr.get("limitations") or []),
        structured_observations=(),
    )


def _quintile_from_envelope(envelope: SecondExperimentExecutionEnvelope) -> QuintileMetrics:
    qm = envelope.raw_quintile_metrics or {}
    return QuintileMetrics(
        quintile_means=tuple(qm.get("quintile_means") or ()),
        quintile_ns=tuple(qm.get("quintile_ns") or ()),
        low_quintile_mean=float(qm.get("low_quintile_mean", 0.0)),
        high_quintile_mean=float(qm.get("high_quintile_mean", 0.0)),
        quintile_mean_spread=float(qm.get("quintile_mean_spread", 0.0)),
        low_high_delta=float(qm.get("low_high_delta", 0.0)),
        sample_size=int(qm.get("sample_size", envelope.sample_size)),
    )


def _find_selected_candidate(package: SecondExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def _assess_second_experiment_intent(
    prop: Dict[str, Any],
    package: SecondExperimentPackage,
    interpretation,
    *,
    tool_result: ToolResult,
    execution_outcome: str,
    target_null_key: str,
) -> IntentAwareEvidenceAssessment:
    candidate = _find_selected_candidate(package)
    cohort = "full_panel_contrast"
    target = package.objective.target_uncertainty
    intent = package.objective.scientific_objective or "Does the directional commitment hold on the full panel?"
    if candidate:
        cohort = candidate.scientific_identity.get("cohort_strategy", cohort)
        meta = COHORT_INTENT.get(cohort, {})
        target = meta.get("target_uncertainty", target)
        intent = meta.get("intent", intent)

    ec = interpretation.evidence_class
    limitations: List[str] = list(tool_result.limitations or ())

    if execution_outcome != "SUCCESS" or tool_result.status != ToolStatus.OK:
        return IntentAwareEvidenceAssessment(
            experiment_intent_summary=intent,
            cohort_strategy=cohort,
            target_uncertainty=target,
            evidence_relevance=EvidenceRelevance.NOT_ADDRESSED.value,
            evidence_direction=EvidenceDirection.UNKNOWN.value,
            evidence_strength=EvidenceStrength.INSUFFICIENT.value,
            remaining_uncertainty=(prop.get("scientific_question", ""), "execution_or_validity_failure"),
            other_nulls_still_alive=_other_nulls_alive(prop, target_null_key),
            null_accounting=(),
            base_evidence_class=ec.value,
            condition_matched=interpretation.condition_matched,
            limitations=tuple(limitations),
            tool_semantic_labels_ignored=_collect_tool_semantic_labels(tool_result),
        )

    relevance = EvidenceRelevance.HIGH.value
    null_key = target_null_key or COHORT_INTENT.get(cohort, {}).get("null_key", "directional_reversal")
    prop_null = prop.get("null_competing_explanation", "")

    direction = EvidenceDirection.UNKNOWN.value
    if ec == EvidenceClass.SUPPORTING:
        direction = EvidenceDirection.SUPPORTS.value
    elif ec in (EvidenceClass.DISCONFIRMING, EvidenceClass.CONTRADICTORY):
        direction = (
            EvidenceDirection.WEAKENS.value
            if ec == EvidenceClass.DISCONFIRMING
            else EvidenceDirection.CONTRADICTS.value
        )
    elif ec == EvidenceClass.NON_INFORMATIVE:
        direction = EvidenceDirection.NEUTRAL.value

    strength = EvidenceStrength.UNKNOWN.value
    spread = interpretation.metrics_used.get("quintile_mean_spread", 0.0)
    if ec == EvidenceClass.INVALID:
        strength = EvidenceStrength.INSUFFICIENT.value
    elif ec == EvidenceClass.NON_INFORMATIVE:
        strength = EvidenceStrength.WEAK.value
    elif ec == EvidenceClass.DISCONFIRMING and interpretation.metrics_used.get("falsify_strength") == "STRONG":
        strength = EvidenceStrength.STRONG.value
    elif ec == EvidenceClass.SUPPORTING:
        strength = EvidenceStrength.MODERATE.value if spread >= 0.5 else EvidenceStrength.WEAK.value
    else:
        strength = EvidenceStrength.MODERATE.value

    remaining: List[str] = [f"target_null:{null_key}"]
    for alive in _other_nulls_alive(prop, null_key):
        remaining.append(f"unresolved_null:{alive}")

    null_state_before = NullExplanationState.STILL_PLAUSIBLE.value
    null_state_after = NullExplanationState.UNKNOWN.value
    null_rationale = "Not evaluated"
    if ec == EvidenceClass.INVALID:
        null_state_after = NullExplanationState.NOT_TESTED.value
        null_rationale = "Invalid evidence — null not tested"
    elif ec == EvidenceClass.SUPPORTING and relevance == EvidenceRelevance.HIGH.value:
        null_state_after = NullExplanationState.WEAKENED.value
        null_rationale = "Directional commitment holds on full panel — directional_reversal less plausible"
    elif ec in (EvidenceClass.DISCONFIRMING, EvidenceClass.CONTRADICTORY):
        null_state_after = (
            NullExplanationState.ADDRESSED.value
            if ec == EvidenceClass.DISCONFIRMING and interpretation.metrics_used.get("falsify_strength") == "STRONG"
            else NullExplanationState.WEAKENED.value
        )
        null_rationale = "Falsification-oriented evidence under directional_reversal test"
    elif ec == EvidenceClass.NON_INFORMATIVE:
        null_state_after = NullExplanationState.STILL_PLAUSIBLE.value
        null_rationale = "Non-informative under frozen contract — null remains plausible"
    else:
        null_state_after = NullExplanationState.STILL_PLAUSIBLE.value
        null_rationale = "Evidence insufficient to resolve null"

    null_acct = (
        NullExplanationAccounting(
            null_explanation_text=prop_null[:200] if prop_null else null_key,
            null_key=null_key,
            state_before=null_state_before,
            state_after=null_state_after,
            rationale=null_rationale,
        ),
    )

    return IntentAwareEvidenceAssessment(
        experiment_intent_summary=intent,
        cohort_strategy=cohort,
        target_uncertainty=target,
        evidence_relevance=relevance,
        evidence_direction=direction,
        evidence_strength=strength,
        remaining_uncertainty=tuple(remaining),
        other_nulls_still_alive=_other_nulls_alive(prop, null_key),
        null_accounting=null_acct,
        base_evidence_class=ec.value,
        condition_matched=interpretation.condition_matched,
        limitations=tuple(limitations),
        tool_semantic_labels_ignored=_collect_tool_semantic_labels(tool_result),
    )


def interpret_second_experiment_evidence(
    prop: Dict[str, Any],
    package: SecondExperimentPackage,
    execution_envelope: SecondExperimentExecutionEnvelope,
    first_interpretation: FirstExperimentInterpretationEnvelope,
    frozen_contract_ref: FrozenInterpretationContractRef,
    *,
    session_id: str,
    existing_interpretation: Optional[SecondExperimentInterpretationEnvelope] = None,
    alternate_contract_hash: Optional[str] = None,
) -> SecondExperimentInterpretationResult:
    """
    Interpret ToolResult #2 in cumulative research history context.
    Does NOT call decide_next_action or design Experiment #3.
    """
    eligibility = validate_second_interpretation_eligibility(
        prop=prop,
        package=package,
        execution_envelope=execution_envelope,
        first_interpretation=first_interpretation,
        frozen_contract_ref=frozen_contract_ref,
        existing_interpretation=existing_interpretation,
        alternate_contract_hash=alternate_contract_hash,
    )

    if eligibility.idempotent_replay and existing_interpretation:
        return SecondExperimentInterpretationResult(
            outcome="IDEMPOTENT_REPLAY",
            eligibility=eligibility,
            envelope=existing_interpretation,
            stop_boundary=STOP_SECOND_EVIDENCE_INTERPRETED,
        )

    if not eligibility.eligible:
        return SecondExperimentInterpretationResult(
            outcome="NOT_ATTEMPTED",
            eligibility=eligibility,
            envelope=None,
            stop_boundary=STOP_SECOND_EVIDENCE_INTERPRETED,
            errors=tuple(eligibility.reasons),
        )

    contract = load_authoritative_contract(frozen_contract_ref)
    tool_result = _tool_result_from_envelope(execution_envelope)
    quintile_metrics = _quintile_from_envelope(execution_envelope)
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")

    interpretation = interpret_experiment_evidence(
        contract, tool_result, quintile_metrics, expected_cutoff=cutoff or tool_result.data_cutoff_date
    )

    target_null = package.objective.target_null_key
    second_assessment = _assess_second_experiment_intent(
        prop,
        package,
        interpretation,
        tool_result=tool_result,
        execution_outcome=execution_envelope.execution_outcome,
        target_null_key=target_null,
    )

    first_assessment = first_interpretation.evidence_assessment
    first_null_ledger = tuple(first_assessment.null_accounting)

    tr_meta = {
        **execution_envelope.tool_result,
        "tool_name": execution_envelope.binding_audit.tool_name,
        "sample_size": execution_envelope.sample_size,
        "data_cutoff_date": cutoff,
    }
    first_exec_meta = {
        "execution_id": first_interpretation.execution_id,
        "experiment_content_hash": first_interpretation.scientific_action_core_hash,
        "epistemic_update_id": first_interpretation.epistemic_update.get("update_id", ""),
        "tool_result": {
            "tool_name": first_interpretation.base_interpretation.get("tool_name", ""),
            "sample_size": first_interpretation.epistemic_update.get("metrics_used", {}).get("sample_size", 0),
            "data_cutoff_date": cutoff,
        },
    }

    cumulative = build_cumulative_assessment(
        first_assessment=first_assessment,
        first_interpretation=first_interpretation.base_interpretation,
        first_execution_meta=first_exec_meta,
        second_assessment=second_assessment,
        second_interpretation=interpretation.to_dict(),
        second_execution_meta={
            "execution_id": execution_envelope.execution_id,
            "experiment_content_hash": execution_envelope.experiment_content_hash,
            "tool_result": tr_meta,
        },
        novelty_decomposition=execution_envelope.novelty_decomposition,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        first_null_ledger=first_null_ledger,
    )

    prior = first_interpretation.resulting_epistemic_state
    resulting, _transition_key = apply_incremental_epistemic_transition(
        prior,
        interpretation.to_dict(),
        cumulative.incremental_contribution,
        tested_null_key=target_null,
    )

    unresolved = "; ".join(second_assessment.remaining_uncertainty[:3])
    update = build_epistemic_update(
        prop,
        contract,
        interpretation,
        experiment_ref=execution_envelope.execution_id,
        tool_result_hash=execution_envelope.tool_result_hash,
        prior_state=prior,
        resulting_state=resulting,
    )
    update_dict = update.to_dict()
    update_dict["unresolved_uncertainty"] = unresolved
    update_dict["experiment_ordinal"] = 2
    update_dict["multi_evidence"] = {
        "dependence": cumulative.dependence_accounting.to_dict(),
        "incremental": cumulative.incremental_contribution.to_dict(),
        "cumulative_summary": cumulative.cumulative_evidence_summary,
        "first_interpretation_id": first_interpretation.interpretation_id,
    }

    interp_id = compute_second_interpretation_identity_hash(
        contract_hash=frozen_contract_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        first_interpretation_id=first_interpretation.interpretation_id,
    )

    envelope = build_second_interpretation_envelope(
        execution_id=execution_envelope.execution_id,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        package_id=package.package_id,
        package_hash=package.package_hash,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id=session_id,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        first_interpretation_id=first_interpretation.interpretation_id,
        first_execution_id=first_interpretation.execution_id,
        frozen_contract_ref=frozen_contract_ref,
        base_interpretation=interpretation.to_dict(),
        evidence_assessment=second_assessment,
        cumulative_assessment=cumulative,
        epistemic_update=update_dict,
        prior_epistemic_state=prior,
        resulting_epistemic_state=resulting,
        interpretation_identity_hash=interp_id,
    )

    return SecondExperimentInterpretationResult(
        outcome="INTERPRETED",
        eligibility=eligibility,
        envelope=envelope,
        stop_boundary=STOP_SECOND_EVIDENCE_INTERPRETED,
        research_decision_generated=False,
        synthesis_invoked=False,
    )
