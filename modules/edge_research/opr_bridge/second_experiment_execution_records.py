"""
Phase 3J.7 — Second-experiment execution records (ToolResult #2, no interpretation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_execution_records import ExecutionBindingAudit

EXECUTOR_VERSION = "second_experiment_executor_v1_3j7"
GATE_VERSION = "second_experiment_execution_gate_v1_3j7"
ENVELOPE_VERSION = "second_experiment_execution_envelope_v1_3j7"
STOP_SECOND_EXPERIMENT_EXECUTED = "STOP_SECOND_EXPERIMENT_EXECUTED"


@dataclass(frozen=True)
class SecondExperimentExecutionEnvelope:
    """Auditable ToolResult #2 — measurement only, no researcher judgment."""

    execution_id: str
    record_version: str
    experiment_ordinal: int
    package_id: str
    package_hash: str
    research_decision_id: str
    research_decision_hash: str
    first_execution_id: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    selected_candidate_id: str
    scientific_action_core_hash: str
    experiment_content_hash: str
    execution_identity_hash: str
    target_null_key: str
    target_uncertainty: str
    novelty_decomposition: Dict[str, Any]
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
    interpretation_generated: bool
    research_decision_generated: bool
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "record_version": self.record_version,
            "experiment_ordinal": self.experiment_ordinal,
            "package_id": self.package_id,
            "package_hash": self.package_hash,
            "research_decision_id": self.research_decision_id,
            "research_decision_hash": self.research_decision_hash,
            "first_execution_id": self.first_execution_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "selected_candidate_id": self.selected_candidate_id,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "experiment_content_hash": self.experiment_content_hash,
            "execution_identity_hash": self.execution_identity_hash,
            "target_null_key": self.target_null_key,
            "target_uncertainty": self.target_uncertainty,
            "novelty_decomposition": dict(self.novelty_decomposition),
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
            "interpretation_generated": self.interpretation_generated,
            "research_decision_generated": self.research_decision_generated,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def build_second_execution_envelope(
    *,
    package_id: str,
    package_hash: str,
    research_decision_id: str,
    research_decision_hash: str,
    first_execution_id: str,
    proposition_id: str,
    proposition_hash: str,
    session_id: str,
    selected_candidate_id: str,
    scientific_action_core_hash: str,
    experiment_content_hash: str,
    execution_identity_hash: str,
    target_null_key: str,
    target_uncertainty: str,
    novelty_decomposition: Dict[str, Any],
    binding_audit: ExecutionBindingAudit,
    tool_result: Dict[str, Any],
    tool_result_hash: str,
    raw_quintile_metrics: Optional[Dict[str, Any]],
    panel_provenance_hash: str,
    execution_outcome: str,
    warnings: Tuple[str, ...] = (),
    errors: Tuple[str, ...] = (),
) -> SecondExperimentExecutionEnvelope:
    ts = utc_now_iso()
    eid = new_id("sefx")
    body = {
        "execution_id": eid,
        "experiment_ordinal": 2,
        "package_id": package_id,
        "package_hash": package_hash,
        "execution_identity_hash": execution_identity_hash,
        "tool_result_hash": tool_result_hash,
    }
    return SecondExperimentExecutionEnvelope(
        execution_id=eid,
        record_version=ENVELOPE_VERSION,
        experiment_ordinal=2,
        package_id=package_id,
        package_hash=package_hash,
        research_decision_id=research_decision_id,
        research_decision_hash=research_decision_hash,
        first_execution_id=first_execution_id,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        selected_candidate_id=selected_candidate_id,
        scientific_action_core_hash=scientific_action_core_hash,
        experiment_content_hash=experiment_content_hash,
        execution_identity_hash=execution_identity_hash,
        target_null_key=target_null_key,
        target_uncertainty=target_uncertainty,
        novelty_decomposition=dict(novelty_decomposition),
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
        interpretation_generated=False,
        research_decision_generated=False,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
