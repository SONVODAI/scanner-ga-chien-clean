"""
Phase 3J.3 — First-experiment execution records (instrument layer, no interpretation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

EXECUTOR_VERSION = "first_experiment_executor_v1_3j3"
GATE_VERSION = "first_experiment_execution_gate_v1_3j3"
BINDING_VERSION = "first_experiment_execution_binding_v1_3j3"
ENVELOPE_VERSION = "first_experiment_execution_envelope_v1_3j3"
STOP_FIRST_EXPERIMENT_EXECUTED = "STOP_FIRST_EXPERIMENT_EXECUTED"


class ExecutionEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


class ExecutionOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True)
class ExecutionBindingAudit:
    """Proof that executed question == selected question."""

    scientific_spec_hash: str
    execution_spec_hash: str
    scientific_action_core_hash: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    tool_name: str
    tool_version: str
    inputs: Dict[str, Any]
    binding_notes: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scientific_spec_hash": self.scientific_spec_hash,
            "execution_spec_hash": self.execution_spec_hash,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "observation_horizon": self.observation_horizon,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "inputs": dict(self.inputs),
            "binding_notes": list(self.binding_notes),
        }


@dataclass(frozen=True)
class ExecutionEligibilityResult:
    eligibility: str
    reasons: Tuple[str, ...]
    checks: Dict[str, bool]
    gate_version: str = GATE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligibility": self.eligibility,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "gate_version": self.gate_version,
        }


@dataclass(frozen=True)
class FirstExperimentExecutionEnvelope:
    """
    Auditable ToolResult capture — reports what happened, not scientific verdicts.
    """

    execution_id: str
    record_version: str
    package_id: str
    package_hash: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    selected_candidate_id: str
    scientific_action_core_hash: str
    experiment_content_hash: str
    execution_identity_hash: str
    binding_audit: ExecutionBindingAudit
    tool_result: Dict[str, Any]
    tool_result_hash: str
    raw_quintile_metrics: Optional[Dict[str, Any]]
    panel_provenance_hash: str
    execution_outcome: str
    tool_status: str
    sample_size: int
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]
    executor_version: str
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "record_version": self.record_version,
            "package_id": self.package_id,
            "package_hash": self.package_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "selected_candidate_id": self.selected_candidate_id,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "experiment_content_hash": self.experiment_content_hash,
            "execution_identity_hash": self.execution_identity_hash,
            "binding_audit": self.binding_audit.to_dict(),
            "tool_result": dict(self.tool_result),
            "tool_result_hash": self.tool_result_hash,
            "raw_quintile_metrics": self.raw_quintile_metrics,
            "panel_provenance_hash": self.panel_provenance_hash,
            "execution_outcome": self.execution_outcome,
            "tool_status": self.tool_status,
            "sample_size": self.sample_size,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "executor_version": self.executor_version,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def build_execution_envelope(
    *,
    package_id: str,
    package_hash: str,
    proposition_id: str,
    proposition_hash: str,
    session_id: str,
    selected_candidate_id: str,
    scientific_action_core_hash: str,
    experiment_content_hash: str,
    execution_identity_hash: str,
    binding_audit: ExecutionBindingAudit,
    tool_result: Dict[str, Any],
    tool_result_hash: str,
    raw_quintile_metrics: Optional[Dict[str, Any]],
    panel_provenance_hash: str,
    execution_outcome: str,
    warnings: Tuple[str, ...] = (),
    errors: Tuple[str, ...] = (),
) -> FirstExperimentExecutionEnvelope:
    ts = utc_now_iso()
    eid = new_id("iefx")
    body = {
        "execution_id": eid,
        "package_id": package_id,
        "package_hash": package_hash,
        "experiment_content_hash": experiment_content_hash,
        "execution_identity_hash": execution_identity_hash,
        "tool_result_hash": tool_result_hash,
    }
    return FirstExperimentExecutionEnvelope(
        execution_id=eid,
        record_version=ENVELOPE_VERSION,
        package_id=package_id,
        package_hash=package_hash,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        selected_candidate_id=selected_candidate_id,
        scientific_action_core_hash=scientific_action_core_hash,
        experiment_content_hash=experiment_content_hash,
        execution_identity_hash=execution_identity_hash,
        binding_audit=binding_audit,
        tool_result=tool_result,
        tool_result_hash=tool_result_hash,
        raw_quintile_metrics=raw_quintile_metrics,
        panel_provenance_hash=panel_provenance_hash,
        execution_outcome=execution_outcome,
        tool_status=str(tool_result.get("status", "UNKNOWN")),
        sample_size=int(tool_result.get("sample_size", 0)),
        warnings=warnings,
        errors=errors,
        executor_version=EXECUTOR_VERSION,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
