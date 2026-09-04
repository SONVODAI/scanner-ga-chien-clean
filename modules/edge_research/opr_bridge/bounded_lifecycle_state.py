"""
Phase 3J.10 — Bounded lifecycle state resolution and experiment history.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
    ExperimentHistoryEntry,
    LifecyclePhase,
    ResearchBudget,
    is_authoritative_scientific_stop,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    STOP_FIRST_EXPERIMENT_EXECUTED,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    STOP_FIRST_EVIDENCE_INTERPRETED,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    STOP_RESEARCH_DECISION_FROZEN,
)
from modules.edge_research.opr_bridge.production_persistence import OprProductionSessionRecord
from modules.edge_research.opr_bridge.second_experiment_execution_records import (
    STOP_SECOND_EXPERIMENT_EXECUTED,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    STOP_SECOND_EVIDENCE_INTERPRETED,
)
from modules.edge_research.opr_bridge.second_experiment_records import (
    STOP_SECOND_EXPERIMENT_DESIGNED,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    STOP_SECOND_RESEARCH_DECISION_FROZEN,
)


def build_experiment_history(record: OprProductionSessionRecord) -> List[ExperimentHistoryEntry]:
    if record.experiment_history:
        return [ExperimentHistoryEntry.from_dict(e) for e in record.experiment_history]

    history: List[ExperimentHistoryEntry] = []
    if record.initial_experiment_package or record.first_experiment_execution:
        e1 = ExperimentHistoryEntry(ordinal=1)
        e1.package = record.initial_experiment_package
        e1.frozen_contract = record.frozen_interpretation_contract
        e1.execution = record.first_experiment_execution
        e1.interpretation = record.first_experiment_interpretation
        e1.epistemic_update = record.first_experiment_epistemic_update
        e1.decision = record.first_experiment_research_decision
        history.append(e1)

    if (
        record.second_experiment_package
        or record.second_experiment_execution
        or record.second_experiment_interpretation
    ):
        e2 = ExperimentHistoryEntry(ordinal=2)
        e2.package = record.second_experiment_package
        e2.frozen_contract = record.frozen_second_interpretation_contract
        e2.execution = record.second_experiment_execution
        e2.interpretation = record.second_experiment_interpretation
        e2.epistemic_update = record.second_experiment_epistemic_update
        e2.decision = record.second_experiment_research_decision
        history.append(e2)

    for extra in record.experiment_history or []:
        if int(extra.get("ordinal", 0)) > 2:
            history.append(ExperimentHistoryEntry.from_dict(extra))

    return history


def sync_legacy_fields(record: OprProductionSessionRecord, history: List[ExperimentHistoryEntry]) -> None:
    """Keep first_*/second_* denormalized views for 3J.0–3J.9 backward compatibility."""
    for entry in history:
        if entry.ordinal == 1:
            record.initial_experiment_package = entry.package
            record.frozen_interpretation_contract = entry.frozen_contract
            record.first_experiment_execution = entry.execution
            record.first_experiment_interpretation = entry.interpretation
            record.first_experiment_epistemic_update = entry.epistemic_update
            record.first_experiment_research_decision = entry.decision
        elif entry.ordinal == 2:
            record.second_experiment_package = entry.package
            record.frozen_second_interpretation_contract = entry.frozen_contract
            record.second_experiment_execution = entry.execution
            record.second_experiment_interpretation = entry.interpretation
            record.second_experiment_epistemic_update = entry.epistemic_update
            record.second_experiment_research_decision = entry.decision

    record.experiment_history = [e.to_dict() for e in history]
    record.experiments_completed = len([e for e in history if e.execution])


def _entry_for_ordinal(history: List[ExperimentHistoryEntry], ordinal: int) -> Optional[ExperimentHistoryEntry]:
    for e in history:
        if e.ordinal == ordinal:
            return e
    return None


def resolve_lifecycle_phase(
    record: OprProductionSessionRecord,
) -> Tuple[str, int, Optional[ExperimentHistoryEntry]]:
    """
    Return (phase, active_ordinal, entry) for the next lifecycle action.
    active_ordinal is the experiment ordinal currently in progress or last completed.
    """
    if record.lifecycle_phase in (
        LifecyclePhase.STOPPED,
        LifecyclePhase.BUDGET_EXHAUSTED,
        LifecyclePhase.FAILED_CLOSED,
    ):
        return record.lifecycle_phase, record.experiments_completed, None

    history = build_experiment_history(record)
    if not history and not record.initial_experiment_package:
        return LifecyclePhase.PROPOSITION_PERSISTED, 0, None

    completed = [e for e in history if e.decision]
    if completed:
        last = max(completed, key=lambda e: e.ordinal)
        if is_authoritative_scientific_stop(last.decision):
            return LifecyclePhase.STOPPED, last.ordinal, last

    in_progress = [e for e in history if not e.decision]
    if in_progress:
        current = max(in_progress, key=lambda e: e.ordinal)
    elif history:
        last_decided = max([e for e in history if e.decision], key=lambda e: e.ordinal, default=None)
        if last_decided and not is_authoritative_scientific_stop(last_decided.decision):
            return LifecyclePhase.RESEARCH_DECISION_FROZEN, last_decided.ordinal, last_decided
        current = max(history, key=lambda e: e.ordinal)
    else:
        return LifecyclePhase.PROPOSITION_PERSISTED, 0, None

    ordinal = current.ordinal
    if not current.package and ordinal == 1:
        return LifecyclePhase.PROPOSITION_PERSISTED, 0, current
    if current.package and not current.execution:
        return LifecyclePhase.EXPERIMENT_DESIGNED, ordinal, current
    if current.execution and not current.interpretation:
        return LifecyclePhase.EXPERIMENT_EXECUTED, ordinal, current
    if current.interpretation and not current.decision:
        return LifecyclePhase.EVIDENCE_INTERPRETED, ordinal, current
    if current.decision:
        if is_authoritative_scientific_stop(current.decision):
            return LifecyclePhase.STOPPED, ordinal, current
        return LifecyclePhase.RESEARCH_DECISION_FROZEN, ordinal, current

    return LifecyclePhase.PROPOSITION_PERSISTED, ordinal, current


def execution_succeeded(execution: Optional[Dict[str, Any]]) -> bool:
    """True iff an experiment execution completed successfully enough to require consumption."""
    if not execution:
        return False
    outcome = str(execution.get("execution_outcome") or "").upper()
    if outcome in {"FAILED", "FAIL", "ERROR", "NOT_ATTEMPTED"}:
        return False
    return True


def experiment_started(entry: ExperimentHistoryEntry) -> bool:
    """An experiment has started once it is designed or executed."""
    return bool(entry.package or entry.execution)


def scientific_consumption_complete(entry: ExperimentHistoryEntry) -> bool:
    """Interpretation + epistemic update + research decision all persisted."""
    return bool(entry.interpretation and entry.epistemic_update and entry.decision)


def unconsumed_successful_experiments(
    history: List[ExperimentHistoryEntry],
) -> List[ExperimentHistoryEntry]:
    """Successfully executed experiments still missing interpretation/update/decision."""
    return [
        e
        for e in history
        if execution_succeeded(e.execution) and not scientific_consumption_complete(e)
    ]


def in_flight_started_experiments(
    history: List[ExperimentHistoryEntry],
) -> List[ExperimentHistoryEntry]:
    """Started experiments that have not finished scientific consumption or typed failure."""
    inflight: List[ExperimentHistoryEntry] = []
    for entry in history:
        if not experiment_started(entry):
            continue
        if scientific_consumption_complete(entry):
            continue
        if entry.execution and not execution_succeeded(entry.execution):
            continue
        inflight.append(entry)
    return inflight


def start_budget_reached(budget: ResearchBudget, history: List[ExperimentHistoryEntry]) -> bool:
    """max_experiment_iterations limits how many experiments may START, not consumption."""
    started = len([e for e in history if experiment_started(e)])
    return started >= budget.max_experiment_iterations


def budget_exhausted(budget: ResearchBudget, record: OprProductionSessionRecord) -> bool:
    """
    True only when another experiment may not START and no in-flight experiment
    still requires scientific consumption.

    Start-budget exhaustion must not skip interpretation / epistemic update /
    research decision for an experiment that already executed successfully.
    """
    history = build_experiment_history(record)
    if in_flight_started_experiments(history):
        return False
    if start_budget_reached(budget, history):
        return True
    failures = sum(1 for e in history if e.execution and e.execution.get("execution_outcome") == "FAILED")
    if failures > budget.max_execution_failures:
        return True
    last_decision = None
    for e in reversed(history):
        if e.decision:
            last_decision = e.decision
            break
    if last_decision:
        sa = last_decision.get("search_accounting") or {}
        if float(sa.get("search_complexity_score", 0)) >= budget.max_search_complexity:
            return True
        if int(sa.get("search_cardinality", 0)) >= budget.max_search_cardinality:
            return True
    return False


def latest_cumulative_null_ledger(record: OprProductionSessionRecord) -> List[Dict[str, Any]]:
    history = build_experiment_history(record)
    for e in reversed(history):
        if e.decision and e.decision.get("cumulative_null_ledger"):
            return list(e.decision["cumulative_null_ledger"])
        if e.interpretation:
            cum = (e.interpretation.get("cumulative_assessment") or {}).get("cumulative_null_ledger")
            if cum:
                return list(cum)
        if e.interpretation and e.interpretation.get("evidence_assessment"):
            na = e.interpretation["evidence_assessment"].get("null_accounting")
            if na:
                return list(na)
    return []


def stop_boundary_for_stage(ordinal: int, stage: str) -> str:
    if ordinal == 1:
        return {
            "executed": STOP_FIRST_EXPERIMENT_EXECUTED,
            "interpreted": STOP_FIRST_EVIDENCE_INTERPRETED,
            "decided": STOP_RESEARCH_DECISION_FROZEN,
        }.get(stage, STOP_FIRST_EXPERIMENT_EXECUTED)
    if ordinal == 2:
        return {
            "designed": STOP_SECOND_EXPERIMENT_DESIGNED,
            "executed": STOP_SECOND_EXPERIMENT_EXECUTED,
            "interpreted": STOP_SECOND_EVIDENCE_INTERPRETED,
            "decided": STOP_SECOND_RESEARCH_DECISION_FROZEN,
        }.get(stage, STOP_SECOND_EXPERIMENT_DESIGNED)
    return f"STOP_EXPERIMENT_{ordinal}_{stage.upper()}"
