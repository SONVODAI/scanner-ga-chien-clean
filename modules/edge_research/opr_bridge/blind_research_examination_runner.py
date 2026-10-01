"""
Phase 3J.11 — Blind research examination runner (researcher path only).

Does NOT import examiner ground truth. Receives panel DataFrame and runs
bounded autonomous lifecycle via existing 3J.10 entry point.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

RUNNER_VERSION = "blind_research_examination_runner_v1_3j11"


@dataclass
class FrozenLifecycleRecord:
    """Research journey frozen before examiner reveal."""

    anonymous_case_id: str
    session_id: Optional[str]
    proposition_id: Optional[str]
    proposition_summary: Optional[Dict[str, Any]]
    lifecycle_outcome: Optional[str]
    termination_reason: Optional[str]
    lifecycle_phase: Optional[str]
    experiments_completed: int
    journey_rows: List[Dict[str, Any]]
    audit: Optional[Dict[str, Any]]
    budget_initial: Dict[str, Any]
    budget_used: Dict[str, Any]
    cumulative_null_ledger: List[Dict[str, Any]]
    dependence_summary: Optional[Dict[str, Any]]
    final_epistemic_state: Optional[str]
    final_decision_kind: Optional[str]
    final_chosen_action: Optional[str]
    final_stop_reason: Optional[str]
    bootstrap_outcome: Optional[str]
    errors: List[str] = field(default_factory=list)
    frozen_at: str = ""
    lifecycle_frozen_hash: str = ""
    runner_version: str = RUNNER_VERSION

    def finalize_hash(self) -> None:
        payload = {
            "anonymous_case_id": self.anonymous_case_id,
            "session_id": self.session_id,
            "proposition_id": self.proposition_id,
            "lifecycle_outcome": self.lifecycle_outcome,
            "termination_reason": self.termination_reason,
            "experiments_completed": self.experiments_completed,
            "final_epistemic_state": self.final_epistemic_state,
            "final_decision_kind": self.final_decision_kind,
            "journey_rows": self.journey_rows,
            "runner_version": self.runner_version,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.lifecycle_frozen_hash = hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anonymous_case_id": self.anonymous_case_id,
            "session_id": self.session_id,
            "proposition_id": self.proposition_id,
            "proposition_summary": self.proposition_summary,
            "lifecycle_outcome": self.lifecycle_outcome,
            "termination_reason": self.termination_reason,
            "lifecycle_phase": self.lifecycle_phase,
            "experiments_completed": self.experiments_completed,
            "journey_rows": list(self.journey_rows),
            "audit": self.audit,
            "budget_initial": dict(self.budget_initial),
            "budget_used": dict(self.budget_used),
            "cumulative_null_ledger": list(self.cumulative_null_ledger),
            "dependence_summary": self.dependence_summary,
            "final_epistemic_state": self.final_epistemic_state,
            "final_decision_kind": self.final_decision_kind,
            "final_chosen_action": self.final_chosen_action,
            "final_stop_reason": self.final_stop_reason,
            "bootstrap_outcome": self.bootstrap_outcome,
            "errors": list(self.errors),
            "frozen_at": self.frozen_at,
            "lifecycle_frozen_hash": self.lifecycle_frozen_hash,
            "runner_version": self.runner_version,
        }


def _extract_proposition_summary(prop: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "proposition_id": prop.get("proposition_id"),
        "scientific_question": prop.get("scientific_question"),
        "observation_horizon": prop.get("observation_horizon"),
        "outcome_field": (prop.get("outcome") or {}).get("field"),
    }


def _build_journey_rows(session_record, iteration_log: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    history = build_experiment_history(session_record) if session_record else []
    rows: List[Dict[str, Any]] = []
    for entry in history:
        interp = entry.interpretation or {}
        epistemic = entry.epistemic_update or {}
        decision = entry.decision or {}
        pkg = entry.package or {}
        exec_env = entry.execution or {}
        row = {
            "ordinal": entry.ordinal,
            "epistemic_state_entering": epistemic.get("prior_epistemic_state") or interp.get("prior_epistemic_state"),
            "decision_entering": None,
            "targeted_null": (pkg.get("target_null") or pkg.get("null_target") or {}).get("null_key"),
            "experiment_identity": pkg.get("experiment_id") or pkg.get("package_id"),
            "population": pkg.get("population") or pkg.get("cohort"),
            "tool": pkg.get("tool") or exec_env.get("tool_name"),
            "dependence_novelty": (interp.get("dependence_assessment") or {}).get("novelty_class"),
            "tool_result_identity": exec_env.get("tool_result_id") or exec_env.get("execution_id"),
            "evidence_direction": (interp.get("evidence_assessment") or {}).get("direction"),
            "evidence_strength": (interp.get("evidence_assessment") or {}).get("strength"),
            "incremental_contribution": (interp.get("incremental_assessment") or {}).get("incremental_strength"),
            "epistemic_state_leaving": epistemic.get("resulting_epistemic_state") or interp.get("resulting_epistemic_state"),
            "decision_leaving": decision.get("decision_kind"),
            "chosen_action": (decision.get("research_decision") or {}).get("chosen_next_action") or decision.get("chosen_next_action"),
            "stop_reason": decision.get("stop_reason"),
            "frozen_contract_id": (entry.frozen_contract or {}).get("contract_id"),
        }
        rows.append(row)
    return rows


def _final_epistemic_state(session_record) -> Optional[str]:
    history = build_experiment_history(session_record) if session_record else []
    if not history:
        return None
    # Prefer last decision-accompanying epistemic state; fall back to last interpretation
    for e in reversed(history):
        if e.epistemic_update and e.epistemic_update.get("resulting_epistemic_state"):
            return e.epistemic_update.get("resulting_epistemic_state")
        if e.interpretation and e.interpretation.get("resulting_epistemic_state"):
            return e.interpretation.get("resulting_epistemic_state")
    return None


def _final_decision(session_record) -> tuple:
    history = build_experiment_history(session_record) if session_record else []
    if not history:
        return None, None, None
    last_dec = None
    for e in reversed(history):
        if e.decision:
            last_dec = e.decision
            break
    if not last_dec:
        return None, None, None
    rd = last_dec.get("research_decision") or {}
    return (
        last_dec.get("decision_kind"),
        rd.get("chosen_next_action") or last_dec.get("chosen_next_action"),
        last_dec.get("stop_reason"),
    )


def run_blind_research_examination(
    panel: pd.DataFrame,
    *,
    anonymous_case_id: str,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    budget: Optional[ResearchBudget] = None,
) -> FrozenLifecycleRecord:
    """
    Run bounded autonomous lifecycle on researcher-visible panel only.
    Returns frozen journey record WITHOUT any ground truth.
    """
    from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso

    budget = budget or ResearchBudget(max_experiment_iterations=2)
    record = FrozenLifecycleRecord(
        anonymous_case_id=anonymous_case_id,
        session_id=None,
        proposition_id=None,
        proposition_summary=None,
        lifecycle_outcome=None,
        termination_reason=None,
        lifecycle_phase=None,
        experiments_completed=0,
        journey_rows=[],
        audit=None,
        budget_initial=budget.to_dict(),
        budget_used={},
        cumulative_null_ledger=[],
        dependence_summary=None,
        final_epistemic_state=None,
        final_decision_kind=None,
        final_chosen_action=None,
        final_stop_reason=None,
        bootstrap_outcome=None,
        frozen_at=utc_now_iso(),
    )

    det = detect_production_opportunity(panel, data_cutoff_date=data_cutoff_date)
    if det.outcome != "OPPORTUNITY_DETECTED" or not det.proposition_record:
        record.lifecycle_outcome = "BOOTSTRAP_SILENT"
        record.termination_reason = det.outcome
        record.bootstrap_outcome = det.outcome
        record.errors.append(f"no_opportunity:{det.outcome}")
        record.finalize_hash()
        return record

    prop = det.proposition_record
    record.proposition_id = prop.get("proposition_id")
    record.proposition_summary = _extract_proposition_summary(prop)

    result = run_bounded_autonomous_research(
        prop,
        panel,
        data_cutoff_date=data_cutoff_date,
        data_dir=data_dir,
        budget=budget,
        bootstrap_new_session=True,
    )

    record.bootstrap_outcome = result.bootstrap_outcome
    if result.session_record:
        record.session_id = result.session_record.session_id
    if result.lifecycle:
        record.lifecycle_outcome = result.lifecycle.outcome
        record.termination_reason = result.lifecycle.termination_reason
        record.lifecycle_phase = result.lifecycle.lifecycle_phase
        record.experiments_completed = result.lifecycle.experiments_completed
        if result.lifecycle.audit:
            audit_d = result.lifecycle.audit.to_dict()
            record.audit = audit_d
            record.budget_used = audit_d.get("budget_used") or {}
            record.cumulative_null_ledger = audit_d.get("cumulative_null_ledger") or []
            record.dependence_summary = audit_d.get("dependence_summary")
        record.journey_rows = _build_journey_rows(
            result.session_record,
            result.lifecycle.iteration_log if result.lifecycle else None,
        )

    record.final_epistemic_state = _final_epistemic_state(result.session_record)
    dk, action, stop = _final_decision(result.session_record)
    record.final_decision_kind = dk
    record.final_chosen_action = action
    record.final_stop_reason = stop
    record.finalize_hash()
    return record


def compute_research_policy_hashes(repo_root: Path) -> Dict[str, str]:
    """Hash frozen research modules before exam — detect post-exam policy mutation."""
    modules = [
        "bounded_lifecycle_controller.py",
        "bounded_lifecycle_records.py",
        "bounded_lifecycle_state.py",
        "production_bounded_lifecycle.py",
        "first_experiment_research_decider.py",
        "second_experiment_research_decider.py",
        "first_experiment_evidence_interpreter.py",
        "second_experiment_evidence_interpreter.py",
        "multi_evidence_accounting.py",
        "production_trigger.py",
        "prioritized_pipeline.py",
        "proposition_synthesizer.py",
    ]
    root = repo_root / "modules/edge_research/opr_bridge"
    out: Dict[str, str] = {}
    for name in modules:
        path = root / name
        if path.exists():
            out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out
