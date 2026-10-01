#!/usr/bin/env python3
"""Phase 3J.12 — N-experiment research generalization diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_nx() -> dict:
    from modules.edge_research.opr_bridge.bb_n_experiment_generalization_01_fixtures import (
        run_cf_nx_counterfactuals,
    )

    return run_cf_nx_counterfactuals()


def run_ordinal_3_diagnostic() -> dict:
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
    from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

    panel = _anomaly_panel(seed=101)
    det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
    if det.outcome != "OPPORTUNITY_DETECTED":
        return {"passed": False, "reason": det.outcome}

    with tempfile.TemporaryDirectory() as tmp:
        r = run_bounded_autonomous_research(
            det.proposition_record,
            panel,
            data_cutoff_date="2026-02-15",
            data_dir=Path(tmp),
            budget=ResearchBudget(max_experiment_iterations=4),
            bootstrap_new_session=True,
        )

    history = build_experiment_history(r.session_record) if r.session_record else []
    journey = []
    for e in history:
        journey.append(
            {
                "ordinal": e.ordinal,
                "has_package": bool(e.package),
                "has_execution": bool(e.execution),
                "has_interpretation": bool(e.interpretation),
                "has_decision": bool(e.decision),
                "experiment_ordinal": (e.package or {}).get("experiment_ordinal"),
            }
        )

    reached_3_design = any(
        e.ordinal >= 3 and e.package and int((e.package or {}).get("experiment_ordinal", 0)) >= 3
        for e in history
    )
    no_arch_break = not any("architectural_break" in str(x) for x in (r.lifecycle.errors if r.lifecycle else ()))

    return {
        "passed": r.lifecycle is not None and no_arch_break and reached_3_design,
        "reached_experiment_3_design": reached_3_design,
        "experiments_completed": r.lifecycle.experiments_completed if r.lifecycle else 0,
        "outcome": r.lifecycle.outcome if r.lifecycle else None,
        "termination_reason": r.lifecycle.termination_reason if r.lifecycle else None,
        "journey": journey,
    }


def run_blind_longer_budget_comparison() -> dict:
    """Re-run frozen 3J.11 blind suite with max_iterations=4 — diagnostic only."""
    from modules.edge_research.opr_bridge.bb_blind_research_examination_01_fixtures import (
        run_single_blind_case,
    )
    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import (
        ExaminerRevealRecord,
        aggregate_suite_scores,
    )

    registry = json.loads(
        (REPO / "benchmarks/bb_blind_exam_01/zone_b_researcher/case_registry.json").read_text()
    )
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        run_blind_research_examination,
    )

    import sys as _sys

    zone_c = REPO / "benchmarks/bb_blind_exam_01/zone_c_examiner"
    _sys.path.insert(0, str(zone_c))
    from panel_generator import generate_blind_panel_for_seed

    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import reveal_and_score

    cases = []
    reveals = []
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        for case in registry["cases"][:4]:
            panel, gt = generate_blind_panel_for_seed(case["seed"])
            frozen = run_blind_research_examination(
                panel,
                anonymous_case_id=case["anonymous_id"],
                data_cutoff_date=case["cutoff"],
                data_dir=data_dir,
                budget=ResearchBudget(max_experiment_iterations=4),
            )
            reveal = reveal_and_score(
                frozen.to_dict(),
                seed=case["seed"],
                ground_truth=gt.to_dict(),
                reveal_after_hash=frozen.lifecycle_frozen_hash,
            )
            cases.append({"anonymous_id": case["anonymous_id"], "frozen": frozen.to_dict(), "reveal": reveal.to_dict()})
            reveals.append(reveal)

    agg = aggregate_suite_scores(reveals)
    return {"sample_cases": cases, "aggregate": agg, "budget": 4}


def run_regressions() -> dict:
    suites = [
        "tests/test_edge_research_opr_phase_3j12.py",
        "tests/test_edge_research_opr_phase_3j11.py",
        "tests/test_edge_research_opr_phase_3j10.py",
        "tests/test_edge_research_opr_phase_3j9.py",
    ]
    results = {}
    for suite in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q", "--tb=no"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results[suite] = {"passed": proc.returncode == 0, "tail": (proc.stdout or proc.stderr).strip().split("\n")[-1]}
    return {"suites": results, "all_passed": all(r["passed"] for r in results.values())}


def main() -> int:
    cf = run_cf_nx()
    _write("01_cf_nx_summary.json", cf)

    ord3 = run_ordinal_3_diagnostic()
    _write("02_ordinal_3_diagnostic.json", ord3)

    blind_cmp = run_blind_longer_budget_comparison()
    _write("03_blind_longer_budget_comparison.json", blind_cmp)

    regressions = run_regressions()
    _write("04_regression_summary.json", regressions)

    cf_pass = all(v.get("passed") for v in cf.values())
    critical_fp = blind_cmp.get("aggregate", {}).get("critical_false_positive_count", 0)
    summary = {
        "head": _git_head(),
        "phase": "3J.12",
        "stop_boundary": "STOP_N_EXPERIMENT_GENERALIZATION",
        "cf_nx_pass": cf_pass,
        "ordinal_3_diagnostic_pass": ord3.get("passed"),
        "blind_longer_budget_critical_fp": critical_fp,
        "regressions_pass": regressions["all_passed"],
        "phase_pass": cf_pass and ord3.get("passed") and regressions["all_passed"] and critical_fp == 0,
    }
    _write("05_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
