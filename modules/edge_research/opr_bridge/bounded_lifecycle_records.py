"""
Phase 3J.10 — Bounded autonomous research lifecycle records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

LIFECYCLE_VERSION = "bounded_autonomous_lifecycle_v1_3j10"
CONTROLLER_VERSION = "bounded_lifecycle_controller_v1_3j14a"

STOP_LIFECYCLE_BOUNDED = "STOP_LIFECYCLE_BOUNDED"
STOP_LIFECYCLE_SCIENTIFIC_STOP = "STOP_LIFECYCLE_SCIENTIFIC_STOP"
STOP_LIFECYCLE_BUDGET_EXHAUSTED = "STOP_LIFECYCLE_BUDGET_EXHAUSTED"
STOP_LIFECYCLE_FAIL_CLOSED = "STOP_LIFECYCLE_FAIL_CLOSED"
STOP_LIFECYCLE_DESIGN_SILENCE = "STOP_LIFECYCLE_DESIGN_SILENCE"

# Authoritative scientific STOP reasons from research deciders (3J.5 / 3J.9).
SCIENTIFIC_STOP_FAMILIES = frozenset(
    {
        "STOP_LOW_INCREMENTAL",
        "STOP_NO_MATERIAL_NULL",
        "STOP_NO_INFORMATIVE_ACTION",
        "STOP_BUDGET",
        "STOP_REJECT",
    }
)


class LifecyclePhase:
    PROPOSITION_PERSISTED = "PROPOSITION_PERSISTED"
    EXPERIMENT_DESIGNED = "EXPERIMENT_DESIGNED"
    EXPERIMENT_EXECUTED = "EXPERIMENT_EXECUTED"
    EVIDENCE_INTERPRETED = "EVIDENCE_INTERPRETED"
    RESEARCH_DECISION_FROZEN = "RESEARCH_DECISION_FROZEN"
    STOPPED = "STOPPED"
    FAILED_CLOSED = "FAILED_CLOSED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class ResearchBudget:
    """Conservative bounded autonomy limits."""

    max_experiment_iterations: int = 2
    max_search_complexity: float = 15.0
    max_search_cardinality: int = 20
    max_execution_failures: int = 1
    max_redundancy_burden: float = 0.95

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_experiment_iterations": self.max_experiment_iterations,
            "max_search_complexity": self.max_search_complexity,
            "max_search_cardinality": self.max_search_cardinality,
            "max_execution_failures": self.max_execution_failures,
            "max_redundancy_burden": self.max_redundancy_burden,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchBudget":
        return cls(
            max_experiment_iterations=int(payload.get("max_experiment_iterations", 2)),
            max_search_complexity=float(payload.get("max_search_complexity", 15.0)),
            max_search_cardinality=int(payload.get("max_search_cardinality", 20)),
            max_execution_failures=int(payload.get("max_execution_failures", 1)),
            max_redundancy_burden=float(payload.get("max_redundancy_burden", 0.95)),
        )


@dataclass
class ExperimentHistoryEntry:
    ordinal: int
    package: Optional[Dict[str, Any]] = None
    frozen_contract: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None
    interpretation: Optional[Dict[str, Any]] = None
    epistemic_update: Optional[Dict[str, Any]] = None
    decision: Optional[Dict[str, Any]] = None
    stop_boundaries: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "package": self.package,
            "frozen_contract": self.frozen_contract,
            "execution": self.execution,
            "interpretation": self.interpretation,
            "epistemic_update": self.epistemic_update,
            "decision": self.decision,
            "stop_boundaries": list(self.stop_boundaries),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExperimentHistoryEntry":
        return cls(
            ordinal=int(payload["ordinal"]),
            package=payload.get("package"),
            frozen_contract=payload.get("frozen_contract"),
            execution=payload.get("execution"),
            interpretation=payload.get("interpretation"),
            epistemic_update=payload.get("epistemic_update"),
            decision=payload.get("decision"),
            stop_boundaries=list(payload.get("stop_boundaries") or []),
        )


@dataclass
class BoundedLifecycleAuditRecord:
    lifecycle_run_id: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    start_phase: str
    end_phase: str
    termination_reason: str
    budget_initial: Dict[str, Any]
    budget_used: Dict[str, Any]
    experiment_count: int
    experiment_identities: List[str]
    tool_result_identities: List[str]
    interpretation_identities: List[str]
    decision_identities: List[str]
    cumulative_null_ledger: List[Dict[str, Any]]
    dependence_summary: Dict[str, Any]
    failures: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    controller_version: str = CONTROLLER_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    audit_hash: str = ""

    def finalize_hash(self) -> None:
        self.audit_hash = stable_hash(
            {
                "lifecycle_run_id": self.lifecycle_run_id,
                "proposition_hash": self.proposition_hash,
                "termination_reason": self.termination_reason,
                "experiment_count": self.experiment_count,
                "controller_version": self.controller_version,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lifecycle_run_id": self.lifecycle_run_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "start_phase": self.start_phase,
            "end_phase": self.end_phase,
            "termination_reason": self.termination_reason,
            "budget_initial": dict(self.budget_initial),
            "budget_used": dict(self.budget_used),
            "experiment_count": self.experiment_count,
            "experiment_identities": list(self.experiment_identities),
            "tool_result_identities": list(self.tool_result_identities),
            "interpretation_identities": list(self.interpretation_identities),
            "decision_identities": list(self.decision_identities),
            "cumulative_null_ledger": list(self.cumulative_null_ledger),
            "dependence_summary": dict(self.dependence_summary),
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "controller_version": self.controller_version,
            "created_at": self.created_at,
            "audit_hash": self.audit_hash,
        }


def new_lifecycle_run_id() -> str:
    return new_id("blc")


def is_authoritative_scientific_stop(decision: Optional[Dict[str, Any]]) -> bool:
    if not decision:
        return False
    if str(decision.get("decision_kind", "")).upper() == "STOP":
        return True
    stop_reason = decision.get("stop_reason")
    if stop_reason and stop_reason in SCIENTIFIC_STOP_FAMILIES:
        return True
    rd = decision.get("research_decision") or {}
    if rd.get("chosen_next_action") == "HOLD_UNRESOLVED" and stop_reason:
        return True
    return False
