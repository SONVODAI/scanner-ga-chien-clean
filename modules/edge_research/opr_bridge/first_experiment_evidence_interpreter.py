"""
Phase 3J.4 — Intent-aware first-experiment evidence interpretation (no research decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import load_authoritative_contract
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.first_experiment_interpretation_gate import (
    InterpretationEligibilityResult,
    validate_interpretation_eligibility,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    INTERPRETER_VERSION,
    STOP_FIRST_EVIDENCE_INTERPRETED,
    EvidenceDirection,
    EvidenceRelevance,
    EvidenceStrength,
    FirstExperimentInterpretationEnvelope,
    FrozenInterpretationContractRef,
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
    NullExplanationState,
    build_interpretation_envelope,
    compute_interpretation_identity_hash,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.falsification_records import VulnerabilityKind
from modules.edge_research.opr_bridge.falsification_candidate_generator import derive_proposition_vulnerabilities
from modules.edge_research.opr_bridge.lifecycle_records import EvidenceClass, QuintileMetrics
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    build_epistemic_update,
    interpret_experiment_evidence,
)
from modules.edge_research.research_tools import ToolResult, ToolStatus

TOOL_SEMANTIC_CONTAMINATION_KEYS = frozenset(
    {
        "confirmed",
        "significant",
        "winner",
        "edge_confirmed",
        "hypothesis_rejected",
        "proceed",
        "buy",
        "sell",
        "p_value",
        "alpha",
    }
)

COHORT_INTENT = {
    "episode_holdout_excluding_motivating": {
        "target_uncertainty": "episode_robustness",
        "intent": "Does the effect survive evidence independent of the motivating episode?",
        "null_key": "episode_artifact",
    },
    "counterexample_period_search": {
        "target_uncertainty": "episode_robustness",
        "intent": "Does the effect survive excluding motivating periods?",
        "null_key": "episode_artifact",
    },
    "independent_replication_cohort": {
        "target_uncertainty": "episode_robustness",
        "intent": "Does the effect replicate on an independent cohort?",
        "null_key": "episode_artifact",
    },
    "full_panel_contrast": {
        "target_uncertainty": "directional_effect_full_universe",
        "intent": "Does the directional commitment hold on the full panel?",
        "null_key": "directional_reversal",
    },
    "contradiction_discriminating_test": {
        "target_uncertainty": "directional_effect_full_universe",
        "intent": "Does evidence discriminate between competing explanations?",
        "null_key": "directional_reversal",
    },
}


@dataclass
class FirstExperimentInterpretationResult:
    outcome: str
    eligibility: InterpretationEligibilityResult
    envelope: Optional[FirstExperimentInterpretationEnvelope]
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


def _find_selected_candidate(package: InitialExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def _tool_result_from_envelope(envelope: FirstExperimentExecutionEnvelope) -> ToolResult:
    tr = envelope.tool_result
    status = ToolStatus(tr.get("status", "INVALID_INPUT"))
    obs = tuple()
    return ToolResult(
        tool_name=str(tr.get("tool_name", "")),
        tool_version=str(tr.get("tool_version", "v1")),
        data_cutoff_date=str(tr.get("data_cutoff_date", "")),
        input_hash=str(tr.get("input_hash", "")),
        sample_size=int(tr.get("sample_size", 0)),
        status=status,
        metrics=dict(tr.get("metrics") or {}),
        groups=dict(tr.get("groups") or {}),
        diagnostics=dict(tr.get("diagnostics") or {}),
        limitations=list(tr.get("limitations") or []),
        structured_observations=obs,
    )


def _quintile_from_envelope(envelope: FirstExperimentExecutionEnvelope) -> QuintileMetrics:
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


def _collect_tool_semantic_labels(tool_result: ToolResult) -> Tuple[str, ...]:
    found: List[str] = []
    blob = {**tool_result.metrics, **tool_result.diagnostics, **tool_result.groups}
    for key in blob:
        if any(tok in str(key).lower() for tok in TOOL_SEMANTIC_CONTAMINATION_KEYS):
            found.append(str(key))
    for lim in tool_result.limitations:
        low = lim.lower()
        if any(tok in low for tok in ("confirmed", "significant", "winner", "reject null")):
            found.append(lim[:80])
    return tuple(found)


def _other_nulls_alive(prop: Dict[str, Any], tested_null_key: str) -> Tuple[str, ...]:
    mapping = {
        "episode_artifact": VulnerabilityKind.EPISODE_INSTABILITY.value,
        "directional_reversal": VulnerabilityKind.DIRECTIONAL_REVERSAL.value,
        "population_concentration": VulnerabilityKind.POPULATION_CONCENTRATION.value,
        "context_instability": VulnerabilityKind.CONTEXT_INSTABILITY.value,
    }
    alive = []
    vulns = derive_proposition_vulnerabilities(prop)
    for key, kind in mapping.items():
        if key == tested_null_key:
            continue
        if any(v.kind.value == kind for v in vulns):
            alive.append(key)
    return tuple(alive)


def _assess_intent_aware_evidence(
    prop: Dict[str, Any],
    package: InitialExperimentPackage,
    interpretation,
    *,
    tool_result: ToolResult,
    execution_outcome: str,
) -> IntentAwareEvidenceAssessment:
    candidate = _find_selected_candidate(package)
    cohort = "unknown"
    target = "unknown"
    intent = "Scientific objective derived from selected experiment"
    birth_overlap = 0.0
    if candidate:
        cohort = candidate.scientific_identity.get("cohort_strategy", "unknown")
        birth_overlap = candidate.birth_evidence_overlap_fraction
        meta = COHORT_INTENT.get(cohort, {})
        target = meta.get("target_uncertainty", "unknown")
        intent = meta.get("intent", intent)
        for obj in package.objectives:
            if obj.objective_id == candidate.objective_id:
                target = obj.target_uncertainty
                break

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
            other_nulls_still_alive=_other_nulls_alive(prop, COHORT_INTENT.get(cohort, {}).get("null_key", "")),
            null_accounting=(),
            base_evidence_class=ec.value,
            condition_matched=interpretation.condition_matched,
            limitations=tuple(limitations),
            tool_semantic_labels_ignored=_collect_tool_semantic_labels(tool_result),
        )

    relevance = EvidenceRelevance.HIGH.value
    if cohort == "full_panel_contrast" and birth_overlap >= 0.85:
        relevance = EvidenceRelevance.PARTIAL.value
        limitations.append("high_birth_evidence_overlap_reduces_independence")

    null_key = COHORT_INTENT.get(cohort, {}).get("null_key", "unknown")
    prop_null = prop.get("null_competing_explanation", "")
    if cohort == "full_panel_contrast" and "episode" in prop_null.lower():
        relevance = EvidenceRelevance.LOW.value
        limitations.append("full_panel_does_not_address_episode_null")

    direction = EvidenceDirection.UNKNOWN.value
    if ec == EvidenceClass.SUPPORTING:
        direction = EvidenceDirection.SUPPORTS.value
    elif ec in (EvidenceClass.DISCONFIRMING, EvidenceClass.CONTRADICTORY):
        direction = EvidenceDirection.WEAKENS.value if ec == EvidenceClass.DISCONFIRMING else EvidenceDirection.CONTRADICTS.value
    elif ec == EvidenceClass.NON_INFORMATIVE:
        direction = EvidenceDirection.NEUTRAL.value
    elif ec == EvidenceClass.INVALID:
        direction = EvidenceDirection.UNKNOWN.value

    strength = EvidenceStrength.UNKNOWN.value
    spread = interpretation.metrics_used.get("quintile_mean_spread", 0.0)
    if ec == EvidenceClass.INVALID:
        strength = EvidenceStrength.INSUFFICIENT.value
    elif ec == EvidenceClass.NON_INFORMATIVE:
        strength = EvidenceStrength.WEAK.value
    elif relevance == EvidenceRelevance.LOW.value:
        strength = EvidenceStrength.INSUFFICIENT.value
    elif relevance == EvidenceRelevance.PARTIAL.value:
        strength = EvidenceStrength.WEAK.value if spread < 0.5 else EvidenceStrength.MODERATE.value
    elif ec == EvidenceClass.DISCONFIRMING and interpretation.metrics_used.get("falsify_strength") == "STRONG":
        strength = EvidenceStrength.STRONG.value
    elif ec == EvidenceClass.SUPPORTING:
        strength = EvidenceStrength.MODERATE.value if spread >= 0.5 else EvidenceStrength.WEAK.value
    else:
        strength = EvidenceStrength.MODERATE.value

    remaining: List[str] = [prop.get("scientific_question", "")]
    if relevance != EvidenceRelevance.HIGH.value:
        remaining.append("experiment_intent_partially_addressed")
    for alive in _other_nulls_alive(prop, null_key):
        remaining.append(f"unresolved_null:{alive}")

    null_state_before = NullExplanationState.STILL_PLAUSIBLE.value
    null_state_after = NullExplanationState.UNKNOWN.value
    null_rationale = "Not evaluated"
    if ec == EvidenceClass.INVALID:
        null_state_after = NullExplanationState.NOT_TESTED.value
        null_rationale = "Invalid evidence — null not tested"
    elif relevance == EvidenceRelevance.LOW.value:
        null_state_after = NullExplanationState.NOT_TESTED.value
        null_rationale = "Experiment design does not address this null"
    elif ec == EvidenceClass.SUPPORTING and relevance == EvidenceRelevance.HIGH.value:
        null_state_after = NullExplanationState.WEAKENED.value
        null_rationale = "Independent cohort supports directional commitment — episode artifact less plausible"
    elif ec in (EvidenceClass.DISCONFIRMING, EvidenceClass.CONTRADICTORY) and relevance in (
        EvidenceRelevance.HIGH.value,
        EvidenceRelevance.PARTIAL.value,
    ):
        null_state_after = (
            NullExplanationState.ADDRESSED.value
            if ec == EvidenceClass.DISCONFIRMING and interpretation.metrics_used.get("falsify_strength") == "STRONG"
            else NullExplanationState.WEAKENED.value
        )
        null_rationale = "Falsification-oriented evidence under intended test"
    elif ec == EvidenceClass.NON_INFORMATIVE:
        null_state_after = NullExplanationState.STILL_PLAUSIBLE.value
        null_rationale = "Non-informative under frozen contract — null remains plausible"
    else:
        null_state_after = NullExplanationState.STILL_PLAUSIBLE.value
        null_rationale = "Evidence insufficient to resolve null"

    null_acct = (
        NullExplanationAccounting(
            null_explanation_text=prop_null[:200] if prop_null else "unknown",
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


def interpret_first_experiment_evidence(
    prop: Dict[str, Any],
    package: InitialExperimentPackage,
    execution_envelope: FirstExperimentExecutionEnvelope,
    frozen_contract_ref: FrozenInterpretationContractRef,
    *,
    session_id: str,
    prior_epistemic_state: Optional[str] = None,
    existing_interpretation: Optional[FirstExperimentInterpretationEnvelope] = None,
    alternate_contract_hash: Optional[str] = None,
) -> FirstExperimentInterpretationResult:
    """
    Interpret faithfully executed first experiment under frozen pre-result contract.
    Does NOT call decide_next_action or on_epistemic_update_completed.
    """
    eligibility = validate_interpretation_eligibility(
        prop=prop,
        package=package,
        execution_envelope=execution_envelope,
        frozen_contract_ref=frozen_contract_ref,
        existing_interpretation=existing_interpretation,
        alternate_contract_hash=alternate_contract_hash,
    )

    if eligibility.idempotent_replay and existing_interpretation:
        return FirstExperimentInterpretationResult(
            outcome="IDEMPOTENT_REPLAY",
            eligibility=eligibility,
            envelope=existing_interpretation,
            stop_boundary=STOP_FIRST_EVIDENCE_INTERPRETED,
        )

    if not eligibility.eligible:
        return FirstExperimentInterpretationResult(
            outcome="NOT_ATTEMPTED",
            eligibility=eligibility,
            envelope=None,
            stop_boundary=STOP_FIRST_EVIDENCE_INTERPRETED,
            errors=tuple(eligibility.reasons),
        )

    contract = load_authoritative_contract(frozen_contract_ref)
    tool_result = _tool_result_from_envelope(execution_envelope)
    quintile_metrics = _quintile_from_envelope(execution_envelope)
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")

    interpretation = interpret_experiment_evidence(
        contract, tool_result, quintile_metrics, expected_cutoff=cutoff or tool_result.data_cutoff_date
    )

    assessment = _assess_intent_aware_evidence(
        prop,
        package,
        interpretation,
        tool_result=tool_result,
        execution_outcome=execution_envelope.execution_outcome,
    )

    prior = prior_epistemic_state or prop.get("epistemic_status", "HYPOTHESIS")
    resulting, _transition_key = apply_epistemic_transition(contract, interpretation, prior)

    unresolved = "; ".join(assessment.remaining_uncertainty[:3])
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

    interp_id = compute_interpretation_identity_hash(
        contract_hash=frozen_contract_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
    )

    envelope = build_interpretation_envelope(
        execution_id=execution_envelope.execution_id,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        package_id=package.package_id,
        package_hash=package.package_hash,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id=session_id,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        frozen_contract_ref=frozen_contract_ref,
        base_interpretation=interpretation.to_dict(),
        evidence_assessment=assessment,
        epistemic_update=update_dict,
        prior_epistemic_state=prior,
        resulting_epistemic_state=resulting,
        interpretation_identity_hash=interp_id,
    )

    return FirstExperimentInterpretationResult(
        outcome="INTERPRETED",
        eligibility=eligibility,
        envelope=envelope,
        stop_boundary=STOP_FIRST_EVIDENCE_INTERPRETED,
        research_decision_generated=False,
        synthesis_invoked=False,
    )
