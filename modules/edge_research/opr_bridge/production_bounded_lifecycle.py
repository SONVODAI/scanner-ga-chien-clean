"""
Phase 3J.10 — Production bounded autonomous research lifecycle entry point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bounded_lifecycle_controller import (
    BoundedLifecycleResult,
    run_bounded_lifecycle_loop,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
    LifecyclePhase,
    ResearchBudget,
    STOP_LIFECYCLE_BOUNDED,
    STOP_LIFECYCLE_DESIGN_SILENCE,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_state import (
    build_experiment_history,
    resolve_lifecycle_phase,
    sync_legacy_fields,
)
from modules.edge_research.opr_bridge.production_orchestrator import (
    STOP_PROPOSITION_PERSISTED,
    run_production_opr_cycle,
)
from modules.edge_research.opr_bridge.production_persistence import (
    OprProductionSessionRecord,
    read_opr_session,
    write_opr_session,
)

INTEGRATION_VERSION = "production_bounded_lifecycle_v1_3j10"


@dataclass
class ProductionBoundedLifecycleResult:
    integration_version: str = INTEGRATION_VERSION
    lifecycle: Optional[BoundedLifecycleResult] = None
    session_record: Optional[OprProductionSessionRecord] = None
    stop_boundaries: List[str] = field(default_factory=list)
    bootstrap_outcome: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "lifecycle": self.lifecycle.to_dict() if self.lifecycle else None,
            "session_id": self.session_record.session_id if self.session_record else None,
            "stop_boundaries": list(self.stop_boundaries),
            "bootstrap_outcome": self.bootstrap_outcome,
        }


def run_bounded_autonomous_research(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    session_id: Optional[str] = None,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    budget: Optional[ResearchBudget] = None,
    bootstrap_new_session: bool = False,
) -> ProductionBoundedLifecycleResult:
    """
    Opt-in bounded autonomous research lifecycle.

    When bootstrap_new_session=True, creates proposition session then runs loop.
    When session_id provided, resumes from authoritative persisted state.
    Does NOT activate edge or trading behavior.
    """
    budget = budget or ResearchBudget(max_experiment_iterations=2)
    stop_boundaries: List[str] = []

    if bootstrap_new_session:
        boot = run_production_opr_cycle(
            panel,
            data_cutoff_date=data_cutoff_date,
            data_dir=data_dir,
        )
        if boot.outcome != "SESSION_CREATED" or not boot.session_record:
            return ProductionBoundedLifecycleResult(
                lifecycle=BoundedLifecycleResult(
                    outcome="BOOTSTRAP_FAILED",
                    session_id="",
                    termination_reason=boot.outcome,
                    lifecycle_phase=LifecyclePhase.FAILED_CLOSED,
                    experiments_completed=0,
                ),
                bootstrap_outcome=boot.outcome,
            )
        record = boot.session_record
        stop_boundaries.extend(boot.stop_boundaries)
    elif session_id:
        record = read_opr_session(session_id, data_dir=data_dir)
    else:
        raise ValueError("session_id required unless bootstrap_new_session=True")

    record.bounded_lifecycle_enabled = True
    record.research_budget = budget.to_dict()
    if not record.lifecycle_phase:
        record.lifecycle_phase = LifecyclePhase.PROPOSITION_PERSISTED

    phase, _, _ = resolve_lifecycle_phase(record)
    if phase == LifecyclePhase.STOPPED:
        history = build_experiment_history(record)
        sync_legacy_fields(record, history)
        if STOP_LIFECYCLE_DESIGN_SILENCE in (record.stop_boundaries_reached or []):
            termination_reason = (record.lifecycle_audit or {}).get("termination_reason")
            if not termination_reason:
                for entry in reversed(history):
                    if entry.package and not entry.execution:
                        disposition = str((entry.package or {}).get("disposition") or "")
                        if disposition and disposition != "SELECTED":
                            termination_reason = f"{STOP_LIFECYCLE_DESIGN_SILENCE}:{disposition}"
                            break
                termination_reason = termination_reason or STOP_LIFECYCLE_DESIGN_SILENCE
            lifecycle = BoundedLifecycleResult(
                outcome="DESIGN_SILENCE",
                session_id=record.session_id,
                termination_reason=termination_reason,
                lifecycle_phase=LifecyclePhase.STOPPED,
                experiments_completed=len([e for e in history if e.execution]),
                stop_boundaries=list(record.stop_boundaries_reached),
            )
        else:
            lifecycle = BoundedLifecycleResult(
                outcome="SCIENTIFIC_STOP",
                session_id=record.session_id,
                termination_reason=(history[-1].decision or {}).get("stop_reason", "authoritative_stop")
                if history
                else "authoritative_stop",
                lifecycle_phase=LifecyclePhase.STOPPED,
                experiments_completed=len([e for e in history if e.execution]),
                stop_boundaries=list(record.stop_boundaries_reached),
            )
        stop_boundaries.append(STOP_LIFECYCLE_BOUNDED)
        return ProductionBoundedLifecycleResult(
            lifecycle=lifecycle,
            session_record=record,
            stop_boundaries=stop_boundaries,
            bootstrap_outcome="RESUME_STOP" if not bootstrap_new_session else "SESSION_CREATED",
        )

    lifecycle = run_bounded_lifecycle_loop(
        prop,
        panel,
        record,
        budget=budget,
        data_dir=data_dir,
    )
    stop_boundaries.extend(lifecycle.stop_boundaries)
    updated = read_opr_session(record.session_id, data_dir=data_dir)
    return ProductionBoundedLifecycleResult(
        lifecycle=lifecycle,
        session_record=updated,
        stop_boundaries=stop_boundaries,
        bootstrap_outcome="SESSION_CREATED" if bootstrap_new_session else "RESUMED",
    )


def materialize_session_from_chain(
    record: OprProductionSessionRecord,
    *,
    data_dir: Optional[Path] = None,
) -> OprProductionSessionRecord:
    """Persist experiment history denormalization after manual 3J.2–3J.9 chain."""
    history = build_experiment_history(record)
    sync_legacy_fields(record, history)
    phase, _, _ = resolve_lifecycle_phase(record)
    record.lifecycle_phase = phase
    write_opr_session(record, data_dir=data_dir)
    return record
