"""
Phase 3J.7 — Controlled second-experiment execution (instrument layer, no interpretation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.first_experiment_execution_binding import (
    bind_frozen_experiment_spec,
    verify_binding_identity,
)
from modules.edge_research.opr_bridge.first_experiment_execution_gate import (
    compute_execution_identity_hash,
    compute_panel_provenance_hash,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    ExecutionEligibility,
    ExecutionOutcome,
    ExecutionEligibilityResult,
    FirstExperimentExecutionEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_execution_tool_resolver import resolve_execution_spec
from modules.edge_research.opr_bridge.first_experiment_executor import (
    FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS,
    envelope_contains_interpretation,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    FirstExperimentResearchDecisionEnvelope,
)
from modules.edge_research.opr_bridge.lifecycle_execution import extract_quintile_metrics, tool_result_hash
from modules.edge_research.opr_bridge.lifecycle_runner import execute_frozen_experiment
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.second_experiment_execution_adapter import second_package_to_initial_package
from modules.edge_research.opr_bridge.second_experiment_execution_gate import validate_second_execution_eligibility
from modules.edge_research.opr_bridge.second_experiment_execution_records import (
    EXECUTOR_VERSION,
    STOP_SECOND_EXPERIMENT_EXECUTED,
    SecondExperimentExecutionEnvelope,
    build_second_execution_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_novelty_audit import NoveltyDecomposition
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry


@dataclass
class SecondExperimentExecutionResult:
    outcome: str
    eligibility: ExecutionEligibilityResult
    envelope: Optional[SecondExperimentExecutionEnvelope]
    package: SecondExperimentPackage
    novelty_decomposition: Optional[NoveltyDecomposition]
    stop_boundary: str
    execution_identity_hash: Optional[str] = None
    substitution_occurred: bool = False
    interpretation_generated: bool = False
    research_decision_generated: bool = False
    errors: tuple = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "eligibility": self.eligibility.to_dict(),
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "package_hash": self.package.package_hash,
            "novelty_decomposition": self.novelty_decomposition.to_dict() if self.novelty_decomposition else None,
            "stop_boundary": self.stop_boundary,
            "execution_identity_hash": self.execution_identity_hash,
            "substitution_occurred": self.substitution_occurred,
            "interpretation_generated": self.interpretation_generated,
            "research_decision_generated": self.research_decision_generated,
            "errors": list(self.errors),
            "executor_version": EXECUTOR_VERSION,
        }


def execute_second_experiment(
    package: SecondExperimentPackage,
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
    first_execution: FirstExperimentExecutionEnvelope,
    session_id: str,
    executability: Optional[ExecutabilityContext] = None,
    existing_envelope: Optional[SecondExperimentExecutionEnvelope] = None,
    registry: Optional[ToolRegistry] = None,
    requested_tool_override: Optional[str] = None,
    binding_mutation: Optional[Dict[str, Any]] = None,
    row_overlap_fraction: Optional[float] = None,
    novelty_decomposition: Optional[NoveltyDecomposition] = None,
) -> SecondExperimentExecutionResult:
    """Execute exactly the frozen second experiment — fail closed on ineligibility."""
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    if executability is None:
        executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff or "2099-01-01")

    eligibility, decomp = validate_second_execution_eligibility(
        package,
        prop,
        panel,
        decision_envelope=decision_envelope,
        executability=executability,
        first_execution=first_execution,
        existing_envelope=existing_envelope,
        novelty_decomposition=novelty_decomposition,
        row_overlap_fraction=row_overlap_fraction,
        requested_tool_override=requested_tool_override,
        binding_mutation=binding_mutation,
    )

    if eligibility.eligibility == ExecutionEligibility.IDEMPOTENT_REPLAY.value and existing_envelope:
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.IDEMPOTENT_REPLAY.value,
            eligibility=eligibility,
            envelope=existing_envelope,
            package=_mark_executed(package),
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            execution_identity_hash=existing_envelope.execution_identity_hash,
        )

    if eligibility.eligibility != ExecutionEligibility.ELIGIBLE.value:
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=eligibility,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            errors=tuple(eligibility.reasons),
        )

    initial = second_package_to_initial_package(package)
    spec, audit, bind_errors = bind_frozen_experiment_spec(initial, mutation=binding_mutation)
    if bind_errors or spec is None or audit is None:
        inelig = ExecutionEligibilityResult(
            ExecutionEligibility.INELIGIBLE.value,
            bind_errors or ("binding_failed",),
            eligibility.checks,
        )
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=inelig,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            errors=tuple(bind_errors),
        )

    identity_ok, identity_errors = verify_binding_identity(audit, initial)
    if not identity_ok:
        inelig = ExecutionEligibilityResult(
            ExecutionEligibility.INELIGIBLE.value,
            identity_errors,
            eligibility.checks,
        )
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=inelig,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            errors=identity_errors,
        )

    panel_hash = compute_panel_provenance_hash(panel, data_cutoff_date=executability.data_cutoff)
    exp_hash = compute_experiment_content_hash(spec)
    exec_id = compute_execution_identity_hash(
        package_hash=package.package_hash,
        experiment_content_hash=exp_hash,
        panel_provenance_hash=panel_hash,
    )

    reg = registry or build_default_tool_registry()
    resolved_spec, alias_notes = resolve_execution_spec(spec, registry=reg)
    if alias_notes and alias_notes[0].startswith("unresolved_tool"):
        fail_elig = ExecutionEligibilityResult(
            ExecutionEligibility.INELIGIBLE.value,
            alias_notes,
            eligibility.checks,
        )
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=fail_elig,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=alias_notes,
        )

    try:
        tool_result = execute_frozen_experiment(resolved_spec, panel, registry=reg)
    except Exception as exc:
        fail_elig = ExecutionEligibilityResult(
            ExecutionEligibility.INELIGIBLE.value,
            (f"tool_execution_exception:{type(exc).__name__}",),
            eligibility.checks,
        )
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.FAILED.value,
            eligibility=fail_elig,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=(str(exc),),
        )

    tr_dict = tool_result.to_dict()
    tr_hash = tool_result_hash(tr_dict)

    part_col = spec.inputs.get("partition_column", "rs_spread")
    out_field = (spec.research_scope or {}).get("outcome_spec", {}).get("field", "t5_return")
    qm = extract_quintile_metrics(panel, spec, partition_column=str(part_col), outcome_field=str(out_field))
    raw_qm = qm.to_dict()

    exec_outcome = (
        ExecutionOutcome.SUCCESS.value if str(tr_dict.get("status")) == "OK" else ExecutionOutcome.FAILED.value
    )

    rd = decision_envelope.research_decision
    envelope = build_second_execution_envelope(
        package_id=package.package_id,
        package_hash=package.package_hash,
        research_decision_id=str(rd.get("decision_id", "")),
        research_decision_hash=str(rd.get("record_hash", "")),
        first_execution_id=first_execution.execution_id,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id=session_id,
        selected_candidate_id=package.selected_candidate_id or "",
        scientific_action_core_hash=audit.scientific_action_core_hash,
        experiment_content_hash=exp_hash,
        execution_identity_hash=exec_id,
        target_null_key=package.objective.target_null_key,
        target_uncertainty=package.objective.target_uncertainty,
        novelty_decomposition=decomp.to_dict() if decomp else {},
        binding_audit=audit,
        tool_result=tr_dict,
        tool_result_hash=tr_hash,
        raw_quintile_metrics=raw_qm,
        panel_provenance_hash=panel_hash,
        execution_outcome=exec_outcome,
        warnings=tuple(tool_result.limitations or ()),
        errors=() if exec_outcome == ExecutionOutcome.SUCCESS.value else (f"tool_status:{tr_dict.get('status')}",),
    )

    if _envelope_contains_interpretation(envelope):
        return SecondExperimentExecutionResult(
            outcome=ExecutionOutcome.FAILED.value,
            eligibility=eligibility,
            envelope=None,
            package=package,
            novelty_decomposition=decomp,
            stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=("envelope_contains_interpretation",),
        )

    return SecondExperimentExecutionResult(
        outcome=exec_outcome,
        eligibility=eligibility,
        envelope=envelope,
        package=_mark_executed(package),
        novelty_decomposition=decomp,
        stop_boundary=STOP_SECOND_EXPERIMENT_EXECUTED,
        execution_identity_hash=exec_id,
        substitution_occurred=requested_tool_override is not None,
        interpretation_generated=False,
        research_decision_generated=False,
    )


def _envelope_contains_interpretation(envelope: SecondExperimentExecutionEnvelope) -> bool:
    blob = str(envelope.to_dict()).lower()
    for key in FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS:
        if key in blob:
            return True
    tr = envelope.tool_result or {}
    for key in FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS:
        if key in tr:
            return True
    return False


def _mark_executed(package: SecondExperimentPackage) -> SecondExperimentPackage:
    from dataclasses import replace

    return replace(package, execution_status="EXECUTED")
