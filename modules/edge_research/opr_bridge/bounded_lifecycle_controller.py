"""
Phase 3J.10 — Bounded autonomous research lifecycle controller.

Composes proven 3J.2–3J.9 production stages into a resumable loop.
Does NOT replace scientific gates, contracts, or decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
    CONTROLLER_VERSION,
    BoundedLifecycleAuditRecord,
    ExperimentHistoryEntry,
    LifecyclePhase,
    ResearchBudget,
    STOP_LIFECYCLE_BOUNDED,
    STOP_LIFECYCLE_BUDGET_EXHAUSTED,
    STOP_LIFECYCLE_DESIGN_SILENCE,
    STOP_LIFECYCLE_FAIL_CLOSED,
    STOP_LIFECYCLE_SCIENTIFIC_STOP,
    is_authoritative_scientific_stop,
    new_lifecycle_run_id,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_state import (
    build_experiment_history,
    budget_exhausted,
    latest_cumulative_null_ledger,
    resolve_lifecycle_phase,
    stop_boundary_for_stage,
    sync_legacy_fields,
)
from modules.edge_research.opr_bridge.production_persistence import (
    OprProductionSessionRecord,
    write_opr_session,
)


@dataclass
class BoundedLifecycleResult:
    outcome: str
    session_id: str
    termination_reason: str
    lifecycle_phase: str
    experiments_completed: int
    stop_boundaries: List[str] = field(default_factory=list)
    audit: Optional[BoundedLifecycleAuditRecord] = None
    iteration_log: List[Dict[str, Any]] = field(default_factory=list)
    errors: Tuple[str, ...] = ()
    controller_version: str = CONTROLLER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "session_id": self.session_id,
            "termination_reason": self.termination_reason,
            "lifecycle_phase": self.lifecycle_phase,
            "experiments_completed": self.experiments_completed,
            "stop_boundaries": list(self.stop_boundaries),
            "audit": self.audit.to_dict() if self.audit else None,
            "iteration_log": list(self.iteration_log),
            "errors": list(self.errors),
            "controller_version": self.controller_version,
        }


def _ensure_history_entry(history: List[ExperimentHistoryEntry], ordinal: int) -> ExperimentHistoryEntry:
    for e in history:
        if e.ordinal == ordinal:
            return e
    entry = ExperimentHistoryEntry(ordinal=ordinal)
    history.append(entry)
    history.sort(key=lambda x: x.ordinal)
    return entry


def _append_boundary(record: OprProductionSessionRecord, boundary: str) -> None:
    if boundary not in record.stop_boundaries_reached:
        record.stop_boundaries_reached.append(boundary)


def _log_iteration(
    log: List[Dict[str, Any]],
    *,
    ordinal: int,
    stage: str,
    phase_in: str,
    phase_out: str,
    outcome: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    log.append(
        {
            "ordinal": ordinal,
            "stage": stage,
            "phase_in": phase_in,
            "phase_out": phase_out,
            "outcome": outcome,
            "detail": detail or {},
        }
    )


def _package_disposition(package: Optional[Dict[str, Any]]) -> str:
    return str((package or {}).get("disposition") or "")


def _is_execution_eligible_package(package: Optional[Dict[str, Any]]) -> bool:
    """Execution may occur only when the persisted design disposition is SELECTED."""
    return _package_disposition(package) == "SELECTED"


def _design_silence_termination_reason(disposition: str) -> str:
    return f"{STOP_LIFECYCLE_DESIGN_SILENCE}:{disposition or 'UNKNOWN_DISPOSITION'}"


def _is_design_silence_termination(record: OprProductionSessionRecord) -> bool:
    return STOP_LIFECYCLE_DESIGN_SILENCE in (record.stop_boundaries_reached or [])


def _finalize_design_silence(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    record: OprProductionSessionRecord,
    history: List[ExperimentHistoryEntry],
    entry: ExperimentHistoryEntry,
    budget: ResearchBudget,
    *,
    run_id: str,
    start_phase: str,
    stop_boundaries: List[str],
    iteration_log: List[Dict[str, Any]],
    phase_in: str,
    data_dir: Optional[Path],
) -> BoundedLifecycleResult:
    disposition = _package_disposition(entry.package)
    termination_reason = _design_silence_termination_reason(disposition)
    entry.stop_boundaries.append(STOP_LIFECYCLE_DESIGN_SILENCE)
    _append_boundary(record, STOP_LIFECYCLE_DESIGN_SILENCE)
    _append_boundary(record, STOP_LIFECYCLE_BOUNDED)
    record.lifecycle_phase = LifecyclePhase.STOPPED
    sync_legacy_fields(record, history)
    write_opr_session(record, data_dir=data_dir)
    _log_iteration(
        iteration_log,
        ordinal=entry.ordinal,
        stage="design_silence_stop",
        phase_in=phase_in,
        phase_out=LifecyclePhase.STOPPED,
        outcome="design_silence",
        detail={"disposition": disposition, "termination_reason": termination_reason},
    )
    audit = _build_audit(
        record,
        history,
        budget,
        run_id=run_id,
        start_phase=start_phase,
        end_phase=LifecyclePhase.STOPPED,
        termination_reason=termination_reason,
    )
    record.lifecycle_audit = audit.to_dict()
    write_opr_session(record, data_dir=data_dir)
    experiments_completed = len([e for e in history if e.execution])
    return BoundedLifecycleResult(
        outcome="DESIGN_SILENCE",
        session_id=record.session_id,
        termination_reason=termination_reason,
        lifecycle_phase=LifecyclePhase.STOPPED,
        experiments_completed=experiments_completed,
        stop_boundaries=stop_boundaries + [STOP_LIFECYCLE_DESIGN_SILENCE, STOP_LIFECYCLE_BOUNDED],
        audit=audit,
        iteration_log=iteration_log,
    )


def _run_ordinal1_execute(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    record: OprProductionSessionRecord,
    entry: ExperimentHistoryEntry,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    from modules.edge_research.opr_bridge.production_first_experiment_execution import (
        run_production_first_experiment_execution,
    )

    fx = run_production_first_experiment_execution(
        prop,
        panel,
        session_id=record.session_id,
        data_cutoff_date=record.data_cutoff_date,
        data_dir=data_dir,
    )
    if not fx.execution or not fx.execution.envelope:
        return False, "first_experiment_execution_failed"
    entry.package = fx.package_dict
    entry.execution = fx.execution.envelope.to_dict()
    entry.frozen_contract = fx.frozen_contract_ref
    boundary = stop_boundary_for_stage(1, "executed")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _run_ordinal1_interpret(
    prop: Dict[str, Any],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )

    ix = run_production_first_experiment_interpretation(
        prop,
        session_id=record.session_id,
        package_dict=entry.package or {},
        execution_dict=entry.execution or {},
        frozen_contract_dict=entry.frozen_contract or {},
        data_dir=data_dir,
    )
    if not ix.interpretation or not ix.interpretation.envelope:
        return False, "first_experiment_interpretation_failed"
    entry.interpretation = ix.interpretation.envelope.to_dict()
    entry.epistemic_update = ix.interpretation.envelope.epistemic_update
    boundary = stop_boundary_for_stage(1, "interpreted")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _run_ordinal1_decide(
    prop: Dict[str, Any],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
    )

    dx = run_production_first_experiment_research_decision(
        prop,
        session_id=record.session_id,
        package_dict=entry.package or {},
        interpretation_dict=entry.interpretation or {},
        data_dir=data_dir,
    )
    if not dx.decision or not dx.decision.envelope:
        return False, "first_experiment_decision_failed"
    entry.decision = dx.decision.envelope.to_dict()
    boundary = stop_boundary_for_stage(1, "decided")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


ARCHITECTURAL_MAX_FOLLOW_ON_ORDINAL = None  # 3J.12: generic N support; ordinal 2 frozen via production_second_*


def _run_follow_on_design(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    history: List[ExperimentHistoryEntry],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    if entry.ordinal >= 3:
        from modules.edge_research.opr_bridge.follow_on_experiment_core import run_follow_on_design

        sx = run_follow_on_design(
            prop,
            panel,
            experiment_ordinal=entry.ordinal,
            history=history,
            session_id=record.session_id,
            data_dir=data_dir,
        )
        if not sx.package:
            return False, f"experiment_{entry.ordinal}_design_failed"
        entry.package = sx.package.to_dict()
        boundary = stop_boundary_for_stage(entry.ordinal, "designed")
        entry.stop_boundaries.append(boundary)
        _append_boundary(record, boundary)
        return True, None

    from modules.edge_research.opr_bridge.production_second_experiment_design import (
        run_production_second_experiment_design,
    )

    birth = _ensure_history_entry(history, 1)
    prior = max([e for e in history if e.ordinal < entry.ordinal and e.decision], key=lambda e: e.ordinal)
    prior_interp = _ensure_history_entry(history, prior.ordinal)

    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id=record.session_id,
        package_dict=birth.package or {},
        execution_dict=birth.execution or {},
        interpretation_dict=prior_interp.interpretation or birth.interpretation or {},
        decision_dict=prior.decision or {},
        data_dir=data_dir,
    )
    if not sx.design or not sx.design.package:
        return False, f"experiment_{entry.ordinal}_design_failed"
    entry.package = sx.design.package.to_dict()
    boundary = stop_boundary_for_stage(entry.ordinal, "designed")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _run_follow_on_execute(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    history: List[ExperimentHistoryEntry],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    if entry.ordinal >= 3:
        from modules.edge_research.opr_bridge.follow_on_experiment_core import run_follow_on_execute

        ex = run_follow_on_execute(
            prop,
            panel,
            experiment_ordinal=entry.ordinal,
            history=history,
            package_dict=entry.package or {},
            session_id=record.session_id,
            data_dir=data_dir,
        )
        if not ex.envelope:
            return False, f"experiment_{entry.ordinal}_execution_failed"
        entry.execution = ex.envelope.to_dict()
        boundary = stop_boundary_for_stage(entry.ordinal, "executed")
        entry.stop_boundaries.append(boundary)
        _append_boundary(record, boundary)
        return True, None

    from modules.edge_research.opr_bridge.production_second_experiment_execution import (
        run_production_second_experiment_execution,
    )

    birth = _ensure_history_entry(history, 1)
    prior_dec = max([e for e in history if e.ordinal < entry.ordinal and e.decision], key=lambda e: e.ordinal)

    ex = run_production_second_experiment_execution(
        prop,
        panel,
        session_id=record.session_id,
        package_dict=entry.package or {},
        decision_dict=prior_dec.decision or {},
        first_execution_dict=birth.execution or {},
        data_dir=data_dir,
    )
    if not ex.execution or not ex.execution.envelope:
        return False, f"experiment_{entry.ordinal}_execution_failed"
    entry.execution = ex.execution.envelope.to_dict()
    boundary = stop_boundary_for_stage(entry.ordinal, "executed")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _run_follow_on_interpret(
    prop: Dict[str, Any],
    history: List[ExperimentHistoryEntry],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    if entry.ordinal >= 3:
        from modules.edge_research.opr_bridge.follow_on_experiment_core import run_follow_on_interpret

        ix = run_follow_on_interpret(
            prop,
            experiment_ordinal=entry.ordinal,
            history=history,
            package_dict=entry.package or {},
            execution_dict=entry.execution or {},
            session_id=record.session_id,
            data_dir=data_dir,
        )
        if not ix.envelope:
            return False, f"experiment_{entry.ordinal}_interpretation_failed"
        entry.interpretation = ix.envelope.to_dict()
        entry.epistemic_update = ix.envelope.epistemic_update
        boundary = stop_boundary_for_stage(entry.ordinal, "interpreted")
        entry.stop_boundaries.append(boundary)
        _append_boundary(record, boundary)
        return True, None

    from modules.edge_research.opr_bridge.production_second_experiment_interpretation import (
        run_production_second_experiment_interpretation,
    )

    birth = _ensure_history_entry(history, 1)
    ix = run_production_second_experiment_interpretation(
        prop,
        session_id=record.session_id,
        package_dict=entry.package or {},
        execution_dict=entry.execution or {},
        first_interpretation_dict=birth.interpretation or {},
        frozen_contract_dict=entry.frozen_contract,
        data_dir=data_dir,
    )
    if not ix.interpretation or not ix.interpretation.envelope:
        return False, f"experiment_{entry.ordinal}_interpretation_failed"
    entry.interpretation = ix.interpretation.envelope.to_dict()
    entry.epistemic_update = ix.interpretation.envelope.epistemic_update
    if ix.frozen_contract_ref:
        entry.frozen_contract = ix.frozen_contract_ref
    boundary = stop_boundary_for_stage(entry.ordinal, "interpreted")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _run_follow_on_decide(
    prop: Dict[str, Any],
    history: List[ExperimentHistoryEntry],
    entry: ExperimentHistoryEntry,
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    if entry.ordinal >= 3:
        from modules.edge_research.opr_bridge.follow_on_experiment_core import run_follow_on_decide

        dx = run_follow_on_decide(
            prop,
            experiment_ordinal=entry.ordinal,
            history=history,
            interpretation_dict=entry.interpretation or {},
            session_id=record.session_id,
            data_dir=data_dir,
        )
        if not dx.envelope:
            return False, f"experiment_{entry.ordinal}_decision_failed"
        entry.decision = dx.envelope.to_dict()
        boundary = stop_boundary_for_stage(entry.ordinal, "decided")
        entry.stop_boundaries.append(boundary)
        _append_boundary(record, boundary)
        return True, None

    from modules.edge_research.opr_bridge.production_second_experiment_research_decision import (
        run_production_second_experiment_research_decision,
    )

    birth = _ensure_history_entry(history, 1)
    first_dec = _ensure_history_entry(history, 1).decision
    if not first_dec:
        return False, "missing_first_decision_for_cumulative_decide"

    dx = run_production_second_experiment_research_decision(
        prop,
        session_id=record.session_id,
        second_interpretation_dict=entry.interpretation or {},
        first_decision_dict=first_dec,
        first_interpretation_dict=birth.interpretation,
        data_dir=data_dir,
    )
    if not dx.decision or not dx.decision.envelope:
        return False, f"experiment_{entry.ordinal}_decision_failed"
    entry.decision = dx.decision.envelope.to_dict()
    boundary = stop_boundary_for_stage(entry.ordinal, "decided")
    entry.stop_boundaries.append(boundary)
    _append_boundary(record, boundary)
    return True, None


def _build_audit(
    record: OprProductionSessionRecord,
    history: List[ExperimentHistoryEntry],
    budget: ResearchBudget,
    *,
    run_id: str,
    start_phase: str,
    end_phase: str,
    termination_reason: str,
) -> BoundedLifecycleAuditRecord:
    tool_ids = [e.execution.get("execution_id", "") for e in history if e.execution]
    interp_ids = [e.interpretation.get("interpretation_id", "") for e in history if e.interpretation]
    decision_ids = [e.decision.get("decision_envelope_id", "") for e in history if e.decision]
    package_ids = [
        (e.package or {}).get("package_id", "") for e in history if e.package
    ]
    dep_summary: Dict[str, Any] = {}
    for e in reversed(history):
        if e.interpretation and e.interpretation.get("cumulative_assessment"):
            dep_summary = e.interpretation["cumulative_assessment"].get("dependence_accounting") or {}
            break

    audit = BoundedLifecycleAuditRecord(
        lifecycle_run_id=run_id,
        proposition_id=record.proposition_id,
        proposition_hash=record.proposition_hash,
        session_id=record.session_id,
        start_phase=start_phase,
        end_phase=end_phase,
        termination_reason=termination_reason,
        budget_initial=budget.to_dict(),
        budget_used={
            "experiments_completed": len([e for e in history if e.execution]),
            "max_iterations": budget.max_experiment_iterations,
        },
        experiment_count=len([e for e in history if e.execution]),
        experiment_identities=[x for x in package_ids if x],
        tool_result_identities=[x for x in tool_ids if x],
        interpretation_identities=[x for x in interp_ids if x],
        decision_identities=[x for x in decision_ids if x],
        cumulative_null_ledger=latest_cumulative_null_ledger(record),
        dependence_summary=dep_summary,
    )
    audit.finalize_hash()
    return audit


def run_bounded_lifecycle_loop(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    record: OprProductionSessionRecord,
    *,
    budget: Optional[ResearchBudget] = None,
    data_dir: Optional[Path] = None,
    max_steps: int = 24,
) -> BoundedLifecycleResult:
    """
    Autonomous bounded research loop over existing production stages.
    Resumes from latest authoritative persisted artifact in session record.
    """
    budget = budget or ResearchBudget.from_dict(record.research_budget or {})
    run_id = record.lifecycle_run_id or new_lifecycle_run_id()
    record.lifecycle_run_id = run_id
    record.bounded_lifecycle_enabled = True
    record.research_budget = budget.to_dict()

    start_phase, _, _ = resolve_lifecycle_phase(record)
    history = build_experiment_history(record)
    iteration_log: List[Dict[str, Any]] = []
    stop_boundaries = list(record.stop_boundaries_reached)

    for _step in range(max_steps):
        phase, ordinal, entry = resolve_lifecycle_phase(record)

        if phase == LifecyclePhase.STOPPED:
            if _is_design_silence_termination(record):
                termination_reason = next(
                    (
                        b
                        for b in reversed(record.stop_boundaries_reached or [])
                        if str(b).startswith(f"{STOP_LIFECYCLE_DESIGN_SILENCE}:")
                    ),
                    STOP_LIFECYCLE_DESIGN_SILENCE,
                )
                if termination_reason == STOP_LIFECYCLE_DESIGN_SILENCE:
                    for entry in reversed(history):
                        if entry.package and not entry.execution:
                            disposition = _package_disposition(entry.package)
                            if disposition and disposition != "SELECTED":
                                termination_reason = _design_silence_termination_reason(disposition)
                                break
                audit = _build_audit(
                    record,
                    history,
                    budget,
                    run_id=run_id,
                    start_phase=start_phase,
                    end_phase=LifecyclePhase.STOPPED,
                    termination_reason=termination_reason,
                )
                record.lifecycle_audit = audit.to_dict()
                write_opr_session(record, data_dir=data_dir)
                return BoundedLifecycleResult(
                    outcome="DESIGN_SILENCE",
                    session_id=record.session_id,
                    termination_reason=termination_reason,
                    lifecycle_phase=LifecyclePhase.STOPPED,
                    experiments_completed=len([e for e in history if e.execution]),
                    stop_boundaries=list(record.stop_boundaries_reached),
                    audit=audit,
                    iteration_log=iteration_log,
                )

            last = max([e for e in history if e.decision], key=lambda e: e.ordinal, default=None)
            stop_reason = (last.decision or {}).get("stop_reason", "scientific_stop") if last else "scientific_stop"
            record.lifecycle_phase = LifecyclePhase.STOPPED
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            audit = _build_audit(
                record, history, budget,
                run_id=run_id, start_phase=start_phase,
                end_phase=LifecyclePhase.STOPPED,
                termination_reason=STOP_LIFECYCLE_SCIENTIFIC_STOP,
            )
            record.lifecycle_audit = audit.to_dict()
            write_opr_session(record, data_dir=data_dir)
            _append_boundary(record, STOP_LIFECYCLE_SCIENTIFIC_STOP)
            _append_boundary(record, STOP_LIFECYCLE_BOUNDED)
            return BoundedLifecycleResult(
                outcome="SCIENTIFIC_STOP",
                session_id=record.session_id,
                termination_reason=stop_reason,
                lifecycle_phase=LifecyclePhase.STOPPED,
                experiments_completed=len([e for e in history if e.execution]),
                stop_boundaries=stop_boundaries + [STOP_LIFECYCLE_SCIENTIFIC_STOP, STOP_LIFECYCLE_BOUNDED],
                audit=audit,
                iteration_log=iteration_log,
            )

        if budget_exhausted(budget, record):
            record.lifecycle_phase = LifecyclePhase.BUDGET_EXHAUSTED
            sync_legacy_fields(record, history)
            audit = _build_audit(
                record, history, budget,
                run_id=run_id, start_phase=start_phase,
                end_phase=LifecyclePhase.BUDGET_EXHAUSTED,
                termination_reason=STOP_LIFECYCLE_BUDGET_EXHAUSTED,
            )
            record.lifecycle_audit = audit.to_dict()
            write_opr_session(record, data_dir=data_dir)
            _append_boundary(record, STOP_LIFECYCLE_BUDGET_EXHAUSTED)
            _append_boundary(record, STOP_LIFECYCLE_BOUNDED)
            return BoundedLifecycleResult(
                outcome="BUDGET_EXHAUSTED",
                session_id=record.session_id,
                termination_reason=STOP_LIFECYCLE_BUDGET_EXHAUSTED,
                lifecycle_phase=LifecyclePhase.BUDGET_EXHAUSTED,
                experiments_completed=len([e for e in history if e.execution]),
                stop_boundaries=stop_boundaries + [STOP_LIFECYCLE_BUDGET_EXHAUSTED, STOP_LIFECYCLE_BOUNDED],
                audit=audit,
                iteration_log=iteration_log,
            )

        if phase == LifecyclePhase.PROPOSITION_PERSISTED:
            entry = _ensure_history_entry(history, 1)
            ok, err = _run_ordinal1_execute(prop, panel, record, entry, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=1, stage="execute", phase_in=phase, phase_out="EXECUTED", outcome="ok" if ok else err or "fail")
            if not ok:
                record.lifecycle_phase = LifecyclePhase.FAILED_CLOSED
                sync_legacy_fields(record, history)
                write_opr_session(record, data_dir=data_dir)
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=0,
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.EXPERIMENT_EXECUTED and ordinal == 1:
            entry = _ensure_history_entry(history, 1)
            ok, err = _run_ordinal1_interpret(prop, entry, record, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=1, stage="interpret", phase_in=phase, phase_out="INTERPRETED", outcome="ok" if ok else err or "fail")
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=1,
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.EVIDENCE_INTERPRETED and ordinal == 1:
            entry = _ensure_history_entry(history, 1)
            ok, err = _run_ordinal1_decide(prop, entry, record, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=1, stage="decide", phase_in=phase, phase_out="DECIDED", outcome="ok" if ok else err or "fail")
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=1,
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            if is_authoritative_scientific_stop(entry.decision):
                record.lifecycle_phase = LifecyclePhase.STOPPED
                sync_legacy_fields(record, history)
                write_opr_session(record, data_dir=data_dir)
                continue
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.RESEARCH_DECISION_FROZEN:
            last = entry or max(history, key=lambda e: e.ordinal)
            if is_authoritative_scientific_stop(last.decision):
                record.lifecycle_phase = LifecyclePhase.STOPPED
                sync_legacy_fields(record, history)
                write_opr_session(record, data_dir=data_dir)
                continue
            next_ordinal = last.ordinal + 1
            if next_ordinal > budget.max_experiment_iterations:
                record.lifecycle_phase = LifecyclePhase.BUDGET_EXHAUSTED
                sync_legacy_fields(record, history)
                write_opr_session(record, data_dir=data_dir)
                continue
            entry = _ensure_history_entry(history, next_ordinal)
            ok, err = _run_follow_on_design(prop, panel, history, entry, record, data_dir=data_dir)
            _log_iteration(
                iteration_log,
                ordinal=next_ordinal,
                stage="design",
                phase_in=phase,
                phase_out="DESIGNED",
                outcome="ok" if ok else err or "fail",
            )
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=len([e for e in history if e.execution]),
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.EXPERIMENT_DESIGNED and ordinal >= 2:
            entry = _ensure_history_entry(history, ordinal)
            if not _is_execution_eligible_package(entry.package):
                return _finalize_design_silence(
                    prop,
                    panel,
                    record,
                    history,
                    entry,
                    budget,
                    run_id=run_id,
                    start_phase=start_phase,
                    stop_boundaries=stop_boundaries,
                    iteration_log=iteration_log,
                    phase_in=phase,
                    data_dir=data_dir,
                )
            ok, err = _run_follow_on_execute(prop, panel, history, entry, record, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=ordinal, stage="execute", phase_in=phase, phase_out="EXECUTED", outcome="ok" if ok else err or "fail")
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=len([e for e in history if e.execution]),
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.EXPERIMENT_EXECUTED and ordinal >= 2:
            entry = _ensure_history_entry(history, ordinal)
            ok, err = _run_follow_on_interpret(prop, history, entry, record, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=ordinal, stage="interpret", phase_in=phase, phase_out="INTERPRETED", outcome="ok" if ok else err or "fail")
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=len([e for e in history if e.execution]),
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        if phase == LifecyclePhase.EVIDENCE_INTERPRETED and ordinal >= 2:
            entry = _ensure_history_entry(history, ordinal)
            ok, err = _run_follow_on_decide(prop, history, entry, record, data_dir=data_dir)
            _log_iteration(iteration_log, ordinal=ordinal, stage="decide", phase_in=phase, phase_out="DECIDED", outcome="ok" if ok else err or "fail")
            if not ok:
                return BoundedLifecycleResult(
                    outcome="FAILED_CLOSED",
                    session_id=record.session_id,
                    termination_reason=err or STOP_LIFECYCLE_FAIL_CLOSED,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=len([e for e in history if e.execution]),
                    errors=(err or STOP_LIFECYCLE_FAIL_CLOSED,),
                    iteration_log=iteration_log,
                )
            if is_authoritative_scientific_stop(entry.decision):
                record.lifecycle_phase = LifecyclePhase.STOPPED
            sync_legacy_fields(record, history)
            write_opr_session(record, data_dir=data_dir)
            continue

        break

    record.lifecycle_phase = LifecyclePhase.FAILED_CLOSED
    sync_legacy_fields(record, history)
    write_opr_session(record, data_dir=data_dir)
    return BoundedLifecycleResult(
        outcome="FAILED_CLOSED",
        session_id=record.session_id,
        termination_reason="lifecycle_step_limit_exceeded",
        lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
        experiments_completed=len([e for e in history if e.execution]),
        errors=("lifecycle_step_limit_exceeded",),
        iteration_log=iteration_log,
    )
