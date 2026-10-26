"""
Phase 3J.3 — Controlled first-experiment execution (instrument layer, no interpretation).
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
    validate_execution_eligibility,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    EXECUTOR_VERSION,
    STOP_FIRST_EXPERIMENT_EXECUTED,
    ExecutionEligibility,
    ExecutionOutcome,
    ExecutionBindingAudit,
    ExecutionEligibilityResult,
    FirstExperimentExecutionEnvelope,
    build_execution_envelope,
)
from modules.edge_research.opr_bridge.first_experiment_records import (
    InitialExperimentPackage,
    PackageExecutionStatus,
)
from modules.edge_research.opr_bridge.lifecycle_execution import extract_quintile_metrics, tool_result_hash
from modules.edge_research.opr_bridge.lifecycle_runner import execute_frozen_experiment
from modules.edge_research.opr_bridge.first_experiment_execution_tool_resolver import resolve_execution_spec
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry

FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS = frozenset(
    {
        "hypothesis_verdict",
        "edge_confirmed",
        "hypothesis_rejected",
        "promising",
        "proceed",
        "stop_research",
        "buy",
        "sell",
        "next_experiment",
        "scientific_conclusion",
        "researcher_judgment",
    }
)


@dataclass
class FirstExperimentExecutionResult:
    outcome: str
    eligibility: ExecutionEligibilityResult
    envelope: Optional[FirstExperimentExecutionEnvelope]
    binding_audit: Optional[ExecutionBindingAudit]
    package: InitialExperimentPackage
    stop_boundary: str
    execution_identity_hash: Optional[str] = None
    substitution_occurred: bool = False
    errors: tuple = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "eligibility": self.eligibility.to_dict(),
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "binding_audit": self.binding_audit.to_dict() if self.binding_audit else None,
            "package_hash": self.package.package_hash,
            "stop_boundary": self.stop_boundary,
            "execution_identity_hash": self.execution_identity_hash,
            "substitution_occurred": self.substitution_occurred,
            "errors": list(self.errors),
            "executor_version": EXECUTOR_VERSION,
        }


def envelope_contains_interpretation(envelope: FirstExperimentExecutionEnvelope) -> bool:
    """CF-EX7: execution layer must not add researcher judgment."""
    blob = str(envelope.to_dict()).lower()
    for key in FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS:
        if key in blob:
            return True
    tr = envelope.tool_result or {}
    for key in FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS:
        if key in tr:
            return True
    return False


def execute_first_experiment(
    package: InitialExperimentPackage,
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    session_id: str,
    executability: Optional[ExecutabilityContext] = None,
    existing_envelope: Optional[FirstExperimentExecutionEnvelope] = None,
    registry: Optional[ToolRegistry] = None,
    requested_tool_override: Optional[str] = None,
    binding_mutation: Optional[Dict[str, Any]] = None,
    partition_column: Optional[str] = None,
    outcome_field: Optional[str] = None,
) -> FirstExperimentExecutionResult:
    """
    Execute exactly the frozen first experiment — fail closed on ineligibility.
    """
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    if executability is None:
        executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff or "2099-01-01")

    eligibility = validate_execution_eligibility(
        package,
        prop,
        panel,
        executability=executability,
        existing_envelope=existing_envelope,
        requested_tool_override=requested_tool_override,
        binding_mutation=binding_mutation,
    )

    if eligibility.eligibility == ExecutionEligibility.IDEMPOTENT_REPLAY.value and existing_envelope:
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.IDEMPOTENT_REPLAY.value,
            eligibility=eligibility,
            envelope=existing_envelope,
            binding_audit=existing_envelope.binding_audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            execution_identity_hash=existing_envelope.execution_identity_hash,
            substitution_occurred=False,
        )

    if eligibility.eligibility != ExecutionEligibility.ELIGIBLE.value:
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=eligibility,
            envelope=None,
            binding_audit=None,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            errors=tuple(eligibility.reasons),
        )

    spec, audit, bind_errors = bind_frozen_experiment_spec(package, mutation=binding_mutation)
    if bind_errors or spec is None or audit is None:
        inelig = ExecutionEligibilityResult(
            eligibility=ExecutionEligibility.INELIGIBLE.value,
            reasons=bind_errors or ("binding_failed",),
            checks=eligibility.checks,
        )
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=inelig,
            envelope=None,
            binding_audit=audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            errors=tuple(bind_errors),
        )

    identity_ok, identity_errors = verify_binding_identity(audit, package)
    if not identity_ok:
        inelig = ExecutionEligibilityResult(
            eligibility=ExecutionEligibility.INELIGIBLE.value,
            reasons=identity_errors,
            checks=eligibility.checks,
        )
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=inelig,
            envelope=None,
            binding_audit=audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
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
            eligibility=ExecutionEligibility.INELIGIBLE.value,
            reasons=alias_notes,
            checks=eligibility.checks,
        )
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.NOT_ATTEMPTED.value,
            eligibility=fail_elig,
            envelope=None,
            binding_audit=audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=alias_notes,
        )

    try:
        tool_result = execute_frozen_experiment(resolved_spec, panel, registry=reg)
    except Exception as exc:
        fail_elig = ExecutionEligibilityResult(
            eligibility=ExecutionEligibility.INELIGIBLE.value,
            reasons=(f"tool_execution_exception:{type(exc).__name__}",),
            checks=eligibility.checks,
        )
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.FAILED.value,
            eligibility=fail_elig,
            envelope=None,
            binding_audit=audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=(str(exc),),
        )

    tr_dict = tool_result.to_dict()
    tr_hash = tool_result_hash(tr_dict)

    part_col = partition_column or spec.inputs.get("partition_column", "rs_spread")
    out_field = outcome_field or (spec.research_scope or {}).get("outcome_spec", {}).get("field", "t5_return")
    qm = extract_quintile_metrics(panel, spec, partition_column=str(part_col), outcome_field=str(out_field))
    raw_qm = qm.to_dict()

    exec_outcome = (
        ExecutionOutcome.SUCCESS.value
        if str(tr_dict.get("status")) == "OK"
        else ExecutionOutcome.FAILED.value
    )

    envelope = build_execution_envelope(
        package_id=package.package_id,
        package_hash=package.package_hash,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id=session_id,
        selected_candidate_id=package.selected_candidate_id or "",
        scientific_action_core_hash=audit.scientific_action_core_hash,
        experiment_content_hash=exp_hash,
        execution_identity_hash=exec_id,
        binding_audit=audit,
        tool_result=tr_dict,
        tool_result_hash=tr_hash,
        raw_quintile_metrics=raw_qm,
        panel_provenance_hash=panel_hash,
        execution_outcome=exec_outcome,
        warnings=tuple(tool_result.limitations or ()),
        errors=() if exec_outcome == ExecutionOutcome.SUCCESS.value else (f"tool_status:{tr_dict.get('status')}",),
    )

    if envelope_contains_interpretation(envelope):
        return FirstExperimentExecutionResult(
            outcome=ExecutionOutcome.FAILED.value,
            eligibility=eligibility,
            envelope=None,
            binding_audit=audit,
            package=package,
            stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
            execution_identity_hash=exec_id,
            errors=("envelope_contains_interpretation",),
        )

    executed_package = _mark_package_executed(package)

    return FirstExperimentExecutionResult(
        outcome=exec_outcome,
        eligibility=eligibility,
        envelope=envelope,
        binding_audit=audit,
        package=executed_package,
        stop_boundary=STOP_FIRST_EXPERIMENT_EXECUTED,
        execution_identity_hash=exec_id,
        substitution_occurred=requested_tool_override is not None,
    )


def _mark_package_executed(package: InitialExperimentPackage) -> InitialExperimentPackage:
    return InitialExperimentPackage(
        package_id=package.package_id,
        record_version=package.record_version,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        generator_version=package.generator_version,
        selector_version=package.selector_version,
        objectives=package.objectives,
        candidates_considered=package.candidates_considered,
        deduplicated_candidates=package.deduplicated_candidates,
        rejected=package.rejected,
        ranking_trace=package.ranking_trace,
        disposition=package.disposition,
        selected_candidate_id=package.selected_candidate_id,
        selected_experiment_spec=package.selected_experiment_spec,
        selection_reason=package.selection_reason,
        human_choice_material=package.human_choice_material,
        human_choice_reason=package.human_choice_reason,
        execution_status="EXECUTED",
        created_at=package.created_at,
        package_hash=package.package_hash,
    )
