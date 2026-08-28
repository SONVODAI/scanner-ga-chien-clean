"""
Phase 3J.12 — Generic Experiment #N cumulative evidence interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import load_authoritative_contract
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    COHORT_INTENT,
    _collect_tool_semantic_labels,
    _other_nulls_alive,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FrozenInterpretationContractRef,
    IntentAwareEvidenceAssessment,
)
from modules.edge_research.opr_bridge.multi_evidence_accounting import (
    apply_incremental_epistemic_transition,
    build_rolling_cumulative_assessment,
)
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    build_epistemic_update,
    interpret_experiment_evidence,
)
from modules.edge_research.opr_bridge.second_experiment_evidence_interpreter import (
    SecondExperimentInterpretationResult,
    _assess_second_experiment_intent,
    _find_selected_candidate,
    _quintile_from_envelope,
    _tool_result_from_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_execution_records import (
    SecondExperimentExecutionEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_gate import (
    validate_second_interpretation_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    INTERPRETER_VERSION,
    STOP_SECOND_EVIDENCE_INTERPRETED,
    SecondExperimentInterpretationEnvelope,
    build_second_interpretation_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage


def interpret_follow_on_experiment_evidence(
    prop: Dict[str, Any],
    package: SecondExperimentPackage,
    execution_envelope: SecondExperimentExecutionEnvelope,
    *,
    prior_interpretations: Tuple[Any, ...],
    prior_assessments: Tuple[IntentAwareEvidenceAssessment, ...],
    prior_execution_metas: Tuple[Dict[str, Any], ...],
    initial_null_ledger: Tuple[Any, ...],
    immediate_prior_interpretation: Any,
    birth_interpretation: Any,
    birth_interpretation_id: str,
    birth_execution_id: str,
    frozen_ref: FrozenInterpretationContractRef,
    session_id: str,
    experiment_ordinal: int,
    existing_interpretation: Optional[SecondExperimentInterpretationEnvelope] = None,
) -> SecondExperimentInterpretationResult:
    eligibility = validate_second_interpretation_eligibility(
        prop=prop,
        package=package,
        execution_envelope=execution_envelope,
        first_interpretation=birth_interpretation,
        frozen_contract_ref=frozen_ref,
        existing_interpretation=existing_interpretation,
        expected_ordinal=experiment_ordinal,
    )

    if existing_interpretation and eligibility.idempotent_replay:
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

    contract = load_authoritative_contract(frozen_ref)
    tool_result = _tool_result_from_envelope(execution_envelope)
    quintile_metrics = _quintile_from_envelope(execution_envelope)
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")

    interpretation = interpret_experiment_evidence(
        contract, tool_result, quintile_metrics, expected_cutoff=cutoff or tool_result.data_cutoff_date
    )

    target_null = package.objective.target_null_key
    latest_assessment = _assess_second_experiment_intent(
        prop,
        package,
        interpretation,
        tool_result=tool_result,
        execution_outcome=execution_envelope.execution_outcome,
        target_null_key=target_null,
    )

    tr_meta = {
        **execution_envelope.tool_result,
        "tool_name": execution_envelope.binding_audit.tool_name,
        "sample_size": execution_envelope.sample_size,
        "data_cutoff_date": cutoff,
    }
    latest_exec_meta = {
        "execution_id": execution_envelope.execution_id,
        "experiment_content_hash": execution_envelope.experiment_content_hash,
        "epistemic_update_id": "",
        "tool_result": tr_meta,
        "cohort_overlap": float((execution_envelope.novelty_decomposition or {}).get("ROW_OVERLAP", 0.0)),
    }

    cumulative = build_rolling_cumulative_assessment(
        prior_assessments=prior_assessments,
        prior_interpretations=tuple(
            p.base_interpretation if hasattr(p, "base_interpretation") else p.to_dict()
            for p in prior_interpretations
        ),
        prior_execution_metas=prior_execution_metas,
        latest_assessment=latest_assessment,
        latest_interpretation=interpretation.to_dict(),
        latest_execution_meta=latest_exec_meta,
        novelty_decomposition=execution_envelope.novelty_decomposition or {},
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        initial_null_ledger=initial_null_ledger,
        experiment_ordinal=experiment_ordinal,
    )

    prior_state = immediate_prior_interpretation.resulting_epistemic_state
    resulting, _transition_key = apply_incremental_epistemic_transition(
        prior_state,
        interpretation.to_dict(),
        cumulative.incremental_contribution,
        tested_null_key=target_null,
    )

    unresolved = "; ".join(latest_assessment.remaining_uncertainty[:3])
    update = build_epistemic_update(
        prop,
        contract,
        interpretation,
        experiment_ref=execution_envelope.execution_id,
        tool_result_hash=execution_envelope.tool_result_hash,
        prior_state=prior_state,
        resulting_state=resulting,
    )
    update_dict = update.to_dict()
    update_dict["unresolved_uncertainty"] = unresolved
    update_dict["experiment_ordinal"] = experiment_ordinal
    update_dict["multi_evidence"] = {
        "dependence": cumulative.dependence_accounting.to_dict(),
        "incremental": cumulative.incremental_contribution.to_dict(),
        "cumulative_summary": cumulative.cumulative_evidence_summary,
        "prior_interpretation_id": immediate_prior_interpretation.interpretation_id,
        "experiment_ordinal": experiment_ordinal,
    }

    from modules.edge_research.opr_bridge.follow_on_experiment_records import (
        compute_follow_on_interpretation_identity_hash,
    )

    interp_id = compute_follow_on_interpretation_identity_hash(
        contract_hash=frozen_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        prior_interpretation_id=immediate_prior_interpretation.interpretation_id,
        experiment_ordinal=experiment_ordinal,
        interpreter_version=INTERPRETER_VERSION,
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
        first_interpretation_id=birth_interpretation_id,
        first_execution_id=birth_execution_id,
        frozen_contract_ref=frozen_ref,
        base_interpretation=interpretation.to_dict(),
        evidence_assessment=latest_assessment,
        cumulative_assessment=cumulative,
        epistemic_update=update_dict,
        prior_epistemic_state=prior_state,
        resulting_epistemic_state=resulting,
        interpretation_identity_hash=interp_id,
        experiment_ordinal=experiment_ordinal,
    )

    return SecondExperimentInterpretationResult(
        outcome="INTERPRETED",
        eligibility=eligibility,
        envelope=envelope,
        stop_boundary=STOP_SECOND_EVIDENCE_INTERPRETED,
    )
