"""
Phase 3J.12 — Generic Experiment #N follow-on scientific core (ordinal >= 3).

Ordinal 2 remains frozen via production_second_experiment_* modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.bounded_lifecycle_records import ExperimentHistoryEntry
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import (
    envelope_from_dict as first_envelope_from_dict,
    package_from_dict as first_package_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.follow_on_experiment_records import (
    GENERALIZATION_VERSION,
    compute_follow_on_decision_identity_hash,
    compute_follow_on_interpretation_identity_hash,
    compute_follow_on_research_state_identity,
    stop_boundary_for_follow_on_ordinal,
)
from modules.edge_research.opr_bridge.follow_on_research_decision_adapter import (
    NormalizedPriorDecision,
    as_first_decision_envelope_view,
    normalize_prior_decision,
)
from modules.edge_research.opr_bridge.second_experiment_design_gate import compute_design_identity_hash
from modules.edge_research.opr_bridge.second_experiment_design_persistence import (
    lookup_package_by_design_identity,
    package_from_dict,
    persist_second_experiment_package,
)
from modules.edge_research.opr_bridge.second_experiment_execution_persistence import (
    envelope_from_dict as second_envelope_from_dict,
    lookup_second_execution_by_identity,
    persist_second_execution_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_executor import execute_second_experiment
from modules.edge_research.opr_bridge.second_experiment_interpretation_persistence import (
    lookup_second_interpretation_by_identity,
    persist_second_interpretation_envelope,
    second_interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    INTERPRETER_VERSION,
    build_second_interpretation_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_pipeline import (
    SecondExperimentDesignResult,
    run_second_experiment_design_pipeline,
)
from modules.edge_research.opr_bridge.second_experiment_research_decider import (
    SecondExperimentResearchDecisionResult,
    decide_second_experiment_research_action,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_persistence import (
    lookup_decision_by_identity,
    persist_decision_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    DECIDER_VERSION,
    build_second_decision_envelope,
)


def _birth_entry(history: List[ExperimentHistoryEntry]) -> ExperimentHistoryEntry:
    for e in history:
        if e.ordinal == 1:
            return e
    raise ValueError("missing birth experiment in history")


def _prior_entry(history: List[ExperimentHistoryEntry], ordinal: int) -> ExperimentHistoryEntry:
    for e in history:
        if e.ordinal == ordinal - 1:
            return e
    raise ValueError(f"missing prior experiment ordinal {ordinal - 1}")


def _interpretation_envelope_from_history_entry(entry: ExperimentHistoryEntry):
    if not entry.interpretation:
        raise ValueError(f"missing interpretation at ordinal {entry.ordinal}")
    exp_ord = int(entry.interpretation.get("experiment_ordinal", entry.ordinal))
    if exp_ord >= 2:
        return second_interpretation_envelope_from_dict(entry.interpretation)
    return interpretation_envelope_from_dict(entry.interpretation)


def run_follow_on_design(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    experiment_ordinal: int,
    history: List[ExperimentHistoryEntry],
    session_id: str,
    data_dir: Optional[Path] = None,
) -> SecondExperimentDesignResult:
    if experiment_ordinal < 3:
        raise ValueError("follow_on_design requires experiment_ordinal >= 3")

    birth = _birth_entry(history)
    prior = _prior_entry(history, experiment_ordinal)
    if not prior.decision:
        return SecondExperimentDesignResult(
            outcome="NOT_ATTEMPTED",
            package=None,
            stop_boundary=stop_boundary_for_follow_on_ordinal(experiment_ordinal, "designed"),
            errors=("missing_prior_decision",),
        )

    norm = normalize_prior_decision(prior.decision)
    if not norm.is_action:
        return SecondExperimentDesignResult(
            outcome="NOT_ATTEMPTED",
            package=None,
            stop_boundary=stop_boundary_for_follow_on_ordinal(experiment_ordinal, "designed"),
            errors=("prior_decision_not_action",),
        )

    decision_view = as_first_decision_envelope_view(norm)
    prior_interp = _interpretation_envelope_from_history_entry(prior)
    first_package = first_package_from_dict(birth.package or {})
    first_execution = first_envelope_from_dict(birth.execution or {})

    rd = norm.research_decision
    design_id = compute_design_identity_hash(
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=norm.research_state_identity,
    )
    cached = lookup_package_by_design_identity(design_id, data_dir=data_dir)
    if cached and cached.experiment_ordinal == experiment_ordinal:
        return SecondExperimentDesignResult(
            outcome="IDEMPOTENT_REPLAY",
            package=cached,
            stop_boundary=stop_boundary_for_follow_on_ordinal(experiment_ordinal, "designed"),
            idempotent_replay=True,
        )

    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    result = run_second_experiment_design_pipeline(
        prop,
        panel,
        first_package=first_package,
        first_execution=first_execution,
        interpretation_envelope=prior_interp,
        decision_envelope=decision_view,
        executability=ExecutabilityContext.real_partition_default(data_cutoff=cutoff),
        existing_package=None,
        experiment_ordinal=experiment_ordinal,
    )
    if result.package:
        persist_second_experiment_package(result.package, data_dir=data_dir)
    return result


def run_follow_on_execute(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    experiment_ordinal: int,
    history: List[ExperimentHistoryEntry],
    package_dict: Dict[str, Any],
    session_id: str,
    data_dir: Optional[Path] = None,
) -> Any:
    if experiment_ordinal < 3:
        raise ValueError("follow_on_execute requires experiment_ordinal >= 3")

    birth = _birth_entry(history)
    prior = _prior_entry(history, experiment_ordinal)
    package = package_from_dict(package_dict)
    norm = normalize_prior_decision(prior.decision or {})
    decision_view = as_first_decision_envelope_view(norm)
    first_execution = first_envelope_from_dict(birth.execution or {})

    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)

    result = execute_second_experiment(
        package,
        prop,
        panel,
        decision_envelope=decision_view,
        first_execution=first_execution,
        session_id=session_id,
        executability=executability,
        expected_ordinal=experiment_ordinal,
    )
    if result.envelope and result.outcome != "IDEMPOTENT_REPLAY":
        persist_second_execution_envelope(result.envelope, data_dir=data_dir)
    return result


def run_follow_on_interpret(
    prop: Dict[str, Any],
    *,
    experiment_ordinal: int,
    history: List[ExperimentHistoryEntry],
    package_dict: Dict[str, Any],
    execution_dict: Dict[str, Any],
    session_id: str,
    data_dir: Optional[Path] = None,
) -> Any:
    from modules.edge_research.opr_bridge.follow_on_experiment_interpreter import (
        interpret_follow_on_experiment_evidence,
    )

    if experiment_ordinal < 3:
        raise ValueError("follow_on_interpret requires experiment_ordinal >= 3")

    birth = _birth_entry(history)
    prior = _prior_entry(history, experiment_ordinal)
    package = package_from_dict(package_dict)
    execution_envelope = second_envelope_from_dict(execution_dict)

    prior_interpretations = []
    prior_assessments = []
    prior_exec_metas = []
    initial_null_ledger = ()

    for e in sorted(history, key=lambda x: x.ordinal):
        if e.ordinal >= experiment_ordinal or not e.interpretation:
            continue
        interp_env = _interpretation_envelope_from_history_entry(e)
        prior_interpretations.append(interp_env)
        prior_assessments.append(interp_env.evidence_assessment)
        if e.execution:
            ex = second_envelope_from_dict(e.execution) if e.ordinal >= 2 else None
            if ex:
                prior_exec_metas.append(
                    {
                        "execution_id": ex.execution_id,
                        "experiment_content_hash": ex.experiment_content_hash,
                        "epistemic_update_id": interp_env.epistemic_update.get("update_id", ""),
                        "tool_result": ex.tool_result,
                        "cohort_overlap": float(
                            (ex.novelty_decomposition or {}).get("ROW_OVERLAP", 0.0)
                        ),
                    }
                )
        if e.ordinal == 1 and interp_env.evidence_assessment.null_accounting:
            initial_null_ledger = tuple(interp_env.evidence_assessment.null_accounting)

    prior_interp = _interpretation_envelope_from_history_entry(prior)
    frozen_ref = freeze_interpretation_contract_pre_result(
        prop,
        package_id=package.package_id,
        experiment_content_hash=execution_envelope.experiment_content_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        freeze_point=f"PRE_RESULT_EXPERIMENT_{experiment_ordinal}",
    )

    interp_id = compute_follow_on_interpretation_identity_hash(
        contract_hash=frozen_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        prior_interpretation_id=prior_interp.interpretation_id,
        experiment_ordinal=experiment_ordinal,
        interpreter_version=INTERPRETER_VERSION,
    )
    cached = lookup_second_interpretation_by_identity(interp_id, data_dir=data_dir)

    birth_interp = interpretation_envelope_from_dict(birth.interpretation or {})

    result = interpret_follow_on_experiment_evidence(
        prop,
        package,
        execution_envelope,
        prior_interpretations=tuple(prior_interpretations),
        prior_assessments=tuple(prior_assessments),
        prior_execution_metas=tuple(prior_exec_metas),
        initial_null_ledger=initial_null_ledger,
        immediate_prior_interpretation=prior_interp,
        birth_interpretation=birth_interp,
        birth_interpretation_id=birth.interpretation.get("interpretation_id", "") if birth.interpretation else "",
        birth_execution_id=birth.execution.get("execution_id", "") if birth.execution else "",
        frozen_ref=frozen_ref,
        session_id=session_id,
        experiment_ordinal=experiment_ordinal,
        existing_interpretation=cached,
    )
    if result.envelope and result.outcome != "IDEMPOTENT_REPLAY":
        persist_second_interpretation_envelope(result.envelope, data_dir=data_dir)
    return result


def run_follow_on_decide(
    prop: Dict[str, Any],
    *,
    experiment_ordinal: int,
    history: List[ExperimentHistoryEntry],
    interpretation_dict: Dict[str, Any],
    session_id: str,
    data_dir: Optional[Path] = None,
) -> SecondExperimentResearchDecisionResult:
    if experiment_ordinal < 3:
        raise ValueError("follow_on_decide requires experiment_ordinal >= 3")

    birth = _birth_entry(history)
    prior = _prior_entry(history, experiment_ordinal)
    current_interp = second_interpretation_envelope_from_dict(interpretation_dict)
    norm_prior = normalize_prior_decision(prior.decision or {})
    birth_decision = normalize_prior_decision(birth.decision or {})
    birth_dec_view = as_first_decision_envelope_view(birth_decision)
    birth_interp = interpretation_envelope_from_dict(birth.interpretation or {})

    epu = current_interp.epistemic_update or {}
    decision_id = compute_follow_on_decision_identity_hash(
        interpretation_identity_hash=current_interp.interpretation_identity_hash,
        epistemic_update_hash=str(epu.get("record_hash", "")),
        prior_decision_hash=norm_prior.envelope_hash,
        decision_ordinal=experiment_ordinal,
        decider_version=DECIDER_VERSION,
    )
    cached = lookup_decision_by_identity(decision_id, data_dir=data_dir)
    if cached and int(cached.decision_ordinal) == experiment_ordinal:
        return SecondExperimentResearchDecisionResult(
            outcome="IDEMPOTENT_REPLAY",
            envelope=cached,
            stop_boundary=stop_boundary_for_follow_on_ordinal(experiment_ordinal, "decided"),
        )

    result = decide_second_experiment_research_action(
        prop,
        current_interp,
        birth_dec_view,
        session_id=session_id,
        first_interpretation_envelope=birth_interp,
        complexity_override=norm_prior.search_accounting.search_complexity_score + 2.0,
        cardinality_override=norm_prior.search_accounting.search_cardinality + 1,
    )

    if result.envelope:
        state_id = compute_follow_on_research_state_identity(
            proposition_hash=current_interp.proposition_hash,
            resulting_epistemic_state=current_interp.resulting_epistemic_state,
            interpretation_identity_hash=current_interp.interpretation_identity_hash,
            prior_decision_hash=norm_prior.envelope_hash,
            decision_ordinal=experiment_ordinal,
        )
        rebuilt = build_second_decision_envelope(
            interpretation_id=result.envelope.interpretation_id,
            interpretation_identity_hash=result.envelope.interpretation_identity_hash,
            epistemic_update_id=result.envelope.epistemic_update_id,
            epistemic_update_hash=result.envelope.epistemic_update_hash,
            first_decision_envelope_id=result.envelope.first_decision_envelope_id,
            first_decision_hash=result.envelope.first_decision_hash,
            first_interpretation_id=result.envelope.first_interpretation_id,
            proposition_id=result.envelope.proposition_id,
            proposition_hash=result.envelope.proposition_hash,
            session_id=session_id,
            cumulative_research_state_identity=state_id,
            research_decision=result.envelope.research_decision,
            decision_kind=result.envelope.decision_kind,
            stop_reason=result.envelope.stop_reason,
            cumulative_null_ledger=result.envelope.cumulative_null_ledger,
            surviving_nulls=result.envelope.surviving_nulls,
            candidate_evaluations=result.envelope.candidate_evaluations,
            search_accounting=result.envelope.search_accounting,
            dependence_summary=result.envelope.dependence_summary,
            incremental_evidence_summary=result.envelope.incremental_evidence_summary,
            confirmation_bias_guard_applied=result.envelope.confirmation_bias_guard_applied,
            mechanical_sequencing_blocked=result.envelope.mechanical_sequencing_blocked,
            decision_ordinal=experiment_ordinal,
        )
        persist_decision_envelope(rebuilt, data_dir=data_dir)
        return SecondExperimentResearchDecisionResult(
            outcome=result.outcome,
            envelope=rebuilt,
            stop_boundary=stop_boundary_for_follow_on_ordinal(experiment_ordinal, "decided"),
        )
    return result
