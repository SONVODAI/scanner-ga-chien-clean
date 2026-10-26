#!/usr/bin/env python3
"""Phase 3J.10 — Bounded autonomous research lifecycle diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))

FROZEN_PROP = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"
FROZEN_CONTRACT = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json"
J2_DIAG = REPO / "diagnostics/phase_3j2_first_experiment_selection/artifacts/03_real_proposition_diagnostic.json"
PERSISTED_EXEC = REPO / "diagnostics/phase_3j4_evidence_interpretation/artifacts/05_persisted_3j3_execution_envelope.json"
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_arl() -> dict:
    from modules.edge_research.opr_bridge.bb_bounded_autonomous_lifecycle_01_fixtures import (
        run_cf_arl_counterfactuals,
    )

    return run_cf_arl_counterfactuals()


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["july 27", "2.352", "expected_state", "prop-efb650d9bd5c451f"]
    hits = []
    for path in sorted(root.glob("bounded_lifecycle*.py")) + [
        root / "production_bounded_lifecycle.py",
        root / "bb_bounded_autonomous_lifecycle_01_fixtures.py",
    ]:
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"file": path.name, "token": tok})
    return {"passed": len(hits) == 0, "hits": hits}


def run_stop_resume_diagnostic() -> dict:
    import pandas as pd

    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import (
        materialize_session_from_chain,
        run_bounded_autonomous_research,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
    )
    from modules.edge_research.opr_bridge.production_orchestrator import new_production_session_id
    from modules.edge_research.opr_bridge.production_persistence import (
        OprProductionSessionRecord,
        write_opr_session,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_design import (
        run_production_second_experiment_design,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_execution import (
        run_production_second_experiment_execution,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_interpretation import (
        run_production_second_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_research_decision import (
        run_production_second_experiment_research_decision,
    )

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    execution_dict = json.loads(PERSISTED_EXEC.read_text())
    j2_package = json.loads(J2_DIAG.read_text())["package"]
    hist_contract = json.loads(FROZEN_CONTRACT.read_text())
    package_dict = _package_stub_from_persisted_execution(execution_dict, j2_package)
    frozen_ref = frozen_ref_from_historical_contract_artifact(
        hist_contract,
        package_id=execution_dict["package_id"],
        experiment_content_hash=execution_dict["experiment_content_hash"],
        scientific_action_core_hash=execution_dict["scientific_action_core_hash"],
    )
    panel = pd.read_csv(PANEL)
    session_id = "phase-3j10-stop-resume"

    record = OprProductionSessionRecord(
        session_id=session_id,
        opportunity_identity="stop-resume",
        replay_identity="stop-resume-replay",
        proposition_id=prop["proposition_id"],
        proposition_hash=prop.get("proposition_hash", ""),
        data_cutoff_date="2026-02-15",
        evidence_cutoff_hash="test",
        proposition_record=prop,
        initial_experiment_package=package_dict,
        first_experiment_execution=execution_dict,
        frozen_interpretation_contract=frozen_ref.to_dict(),
    )

    ix = run_production_first_experiment_interpretation(
        prop, session_id=session_id, package_dict=package_dict,
        execution_dict=execution_dict, frozen_contract_dict=frozen_ref.to_dict(),
    )
    dx = run_production_first_experiment_research_decision(
        prop, session_id=session_id, package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    sx = run_production_second_experiment_design(
        prop, panel, session_id=session_id, package_dict=package_dict,
        execution_dict=execution_dict, interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
    )
    ex2 = run_production_second_experiment_execution(
        prop, panel, session_id=session_id, package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), first_execution_dict=execution_dict,
    )
    ix2 = run_production_second_experiment_interpretation(
        prop, session_id=session_id, package_dict=sx.design.package.to_dict(),
        execution_dict=ex2.execution.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    dx2 = run_production_second_experiment_research_decision(
        prop, session_id=session_id,
        second_interpretation_dict=ix2.interpretation.envelope.to_dict(),
        first_decision_dict=dx.decision.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    record.first_experiment_interpretation = ix.interpretation.envelope.to_dict()
    record.first_experiment_research_decision = dx.decision.envelope.to_dict()
    record.second_experiment_package = sx.design.package.to_dict()
    record.second_experiment_execution = ex2.execution.envelope.to_dict()
    record.second_experiment_interpretation = ix2.interpretation.envelope.to_dict()
    record.second_experiment_research_decision = dx2.decision.envelope.to_dict()
    materialize_session_from_chain(record)

    pre = dx2.decision.envelope.to_dict()
    r = run_bounded_autonomous_research(
        prop, panel, session_id=session_id, data_cutoff_date="2026-02-15",
        budget=ResearchBudget(max_experiment_iterations=5),
    )

    return {
        "proposition_id": prop["proposition_id"],
        "pre_resume_decision_kind": pre.get("decision_kind"),
        "pre_resume_stop_reason": pre.get("stop_reason"),
        "pre_resume_chosen_action": (pre.get("research_decision") or {}).get("chosen_next_action"),
        "lifecycle_outcome": r.lifecycle.outcome if r.lifecycle else None,
        "experiments_completed": r.lifecycle.experiments_completed if r.lifecycle else None,
        "experiment_three_generated": any(
            e.get("ordinal", 0) >= 3 for e in (r.session_record.experiment_history or [])
        ) if r.session_record else None,
        "termination_reason": r.lifecycle.termination_reason if r.lifecycle else None,
        "lifecycle_phase": r.session_record.lifecycle_phase if r.session_record else None,
    }


def run_fresh_autonomous_diagnostic() -> dict:
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
    from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

    panel = _anomaly_panel(seed=42)
    det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
    if det.outcome != "OPPORTUNITY_DETECTED":
        return {"skipped": True, "reason": det.outcome}

    r = run_bounded_autonomous_research(
        det.proposition_record,
        panel,
        data_cutoff_date="2026-02-15",
        budget=ResearchBudget(max_experiment_iterations=2),
        bootstrap_new_session=True,
    )

    rows = []
    if r.session_record:
        for entry in build_experiment_history(r.session_record):
            dep = {}
            inc = {}
            if entry.interpretation:
                cum = entry.interpretation.get("cumulative_assessment") or {}
                dep = cum.get("dependence_accounting") or {}
                inc = cum.get("incremental_contribution") or {}
            rows.append(
                {
                    "ordinal": entry.ordinal,
                    "epistemic_in": (entry.interpretation or {}).get("prior_epistemic_state"),
                    "epistemic_out": (entry.interpretation or {}).get("resulting_epistemic_state"),
                    "execution_id": (entry.execution or {}).get("execution_id"),
                    "interpretation_id": (entry.interpretation or {}).get("interpretation_id"),
                    "decision_kind": (entry.decision or {}).get("decision_kind"),
                    "stop_reason": (entry.decision or {}).get("stop_reason"),
                    "row_overlap": dep.get("row_overlap_fraction"),
                    "incremental_strength": inc.get("incremental_strength"),
                }
            )

    return {
        "proposition_id": det.proposition_id,
        "lifecycle_outcome": r.lifecycle.outcome if r.lifecycle else None,
        "termination_reason": r.lifecycle.termination_reason if r.lifecycle else None,
        "experiments_completed": r.lifecycle.experiments_completed if r.lifecycle else None,
        "iteration_log": r.lifecycle.iteration_log if r.lifecycle else [],
        "journey_rows": rows,
        "audit": r.session_record.lifecycle_audit if r.session_record else None,
    }


def run_regressions() -> dict:
    tests = [
        "tests/test_edge_research_opr_phase_3j10.py",
        "tests/test_edge_research_opr_phase_3j9.py",
        "tests/test_edge_research_opr_phase_3j8.py",
        "tests/test_edge_research_opr_phase_3j7.py",
        "tests/test_edge_research_opr_phase_3j6a.py",
        "tests/test_edge_research_opr_phase_3j6.py",
        "tests/test_edge_research_opr_phase_3j5.py",
    ]
    results = {}
    for t in tests:
        path = REPO / t
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "-q", "--tb=no"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results[t] = {"exit_code": proc.returncode, "stdout_tail": proc.stdout[-400:]}
    return results


def main() -> int:
    summary = {
        "phase": "3J.10",
        "branch": _git_branch(),
        "git_head": _git_head(),
        "cf_arl": run_cf_arl(),
        "hidden_answer_audit": run_hidden_answer_audit(),
        "stop_resume_diagnostic": run_stop_resume_diagnostic(),
        "fresh_autonomous_diagnostic": run_fresh_autonomous_diagnostic(),
        "regressions": run_regressions(),
    }
    _write("01_cf_arl_summary.json", summary["cf_arl"])
    _write("02_hidden_answer_audit.json", summary["hidden_answer_audit"])
    _write("03_stop_resume_diagnostic.json", summary["stop_resume_diagnostic"])
    _write("04_fresh_autonomous_diagnostic.json", summary["fresh_autonomous_diagnostic"])
    _write("05_regression_summary.json", summary["regressions"])
    _write("06_audit_summary.json", {
        "phase": "3J.10",
        "branch": summary["branch"],
        "git_head": summary["git_head"],
        "cf_arl_all_passed": summary["cf_arl"].get("all_passed"),
        "stop_resume_outcome": summary["stop_resume_diagnostic"].get("lifecycle_outcome"),
        "experiment_three_generated": summary["stop_resume_diagnostic"].get("experiment_three_generated"),
        "fresh_outcome": summary["fresh_autonomous_diagnostic"].get("lifecycle_outcome"),
        "regression_failures": [
            k for k, v in summary["regressions"].items() if v.get("exit_code", 0) != 0
        ],
    })
    print(json.dumps(summary["stop_resume_diagnostic"], indent=2))
    failed = [k for k, v in summary["regressions"].items() if v.get("exit_code", 0) != 0]
    if not summary["cf_arl"].get("all_passed") or failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
