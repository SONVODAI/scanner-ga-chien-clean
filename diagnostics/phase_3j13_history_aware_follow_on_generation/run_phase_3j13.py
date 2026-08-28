#!/usr/bin/env python3
"""Phase 3J.13 — History-aware follow-on experiment generation diagnostics."""

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


def run_cf_fg() -> dict:
    from modules.edge_research.opr_bridge.bb_history_aware_follow_on_generation_01_fixtures import (
        run_cf_fg_counterfactuals,
    )

    return run_cf_fg_counterfactuals()


def run_ordinal_ge3_diagnostic() -> dict:
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
    from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

    panel = _anomaly_panel(seed=77)
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
    ord2_dec = next((e.decision for e in history if e.ordinal == 2), None)
    ord3 = next((e for e in history if e.ordinal == 3), None)
    pkg = ord3.package if ord3 else {}

    candidates = (pkg or {}).get("candidates_considered") or []
    rejected = (pkg or {}).get("rejected") or []

    return {
        "passed": ord3 is not None and "follow_on_experiment_generator" in str((pkg or {}).get("generator_version", "")),
        "frozen_decision_ordinal_2": ord2_dec,
        "ord3_package": {
            "disposition": (pkg or {}).get("disposition"),
            "generator_version": (pkg or {}).get("generator_version"),
            "selector_version": (pkg or {}).get("selector_version"),
            "experiment_ordinal": (pkg or {}).get("experiment_ordinal"),
            "selected_candidate_id": (pkg or {}).get("selected_candidate_id"),
            "candidate_count": len(candidates),
            "rejected_count": len(rejected),
        },
        "experiments_completed": r.lifecycle.experiments_completed if r.lifecycle else 0,
        "termination_reason": r.lifecycle.termination_reason if r.lifecycle else None,
        "outcome": r.lifecycle.outcome if r.lifecycle else None,
        "journey": [
            {
                "ordinal": e.ordinal,
                "has_package": bool(e.package),
                "has_execution": bool(e.execution),
                "has_decision": bool(e.decision),
                "experiment_ordinal": (e.package or {}).get("experiment_ordinal"),
                "disposition": (e.package or {}).get("disposition"),
            }
            for e in history
        ],
    }


def run_blind_longer_budget() -> dict:
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.blind_research_examination_runner import run_blind_research_examination
    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import (
        aggregate_suite_scores,
        reveal_and_score,
    )

    registry = json.loads(
        (REPO / "benchmarks/bb_blind_exam_01/zone_b_researcher/case_registry.json").read_text()
    )
    zone_c = REPO / "benchmarks/bb_blind_exam_01/zone_c_examiner"
    sys.path.insert(0, str(zone_c))
    from panel_generator import generate_blind_panel_for_seed

    reveals = []
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        for case in registry["cases"]:
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
            reveals.append(reveal)

    agg = aggregate_suite_scores(reveals)
    return {"aggregate": agg, "budget": 4, "case_count": len(reveals)}


def run_regressions() -> dict:
    suites = [
        "tests/test_edge_research_opr_phase_3j13.py::test_cf_fg_counterfactuals",
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


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = [
        "blind-a",
        "blind-b",
        "blind-c",
        "ground_truth_manifest",
        "seed_to_blind_class",
        "july 27",
        "known_market_edge",
    ]
    modules = [
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_history_context.py",
        "follow_on_experiment_selector.py",
        "second_experiment_pipeline.py",
    ]
    hits = []
    for name in modules:
        blob = (root / name).read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"module": name, "token": tok})
    return {"passed": not hits, "hits": hits}


def main() -> int:
    cf = run_cf_fg()
    _write("01_cf_fg_summary.json", cf)

    ord_diag = run_ordinal_ge3_diagnostic()
    _write("02_ordinal_ge3_diagnostic.json", ord_diag)

    blind = run_blind_longer_budget()
    _write("03_blind_longer_budget_comparison.json", blind)

    regressions = run_regressions()
    _write("04_regression_summary.json", regressions)

    audit = run_hidden_answer_audit()
    _write("05_hidden_answer_audit.json", audit)

    cf_pass = all(v.get("passed") for v in cf.values())
    critical_fp = blind.get("aggregate", {}).get("critical_false_positive_count", 0)
    summary = {
        "head": _git_head(),
        "phase": "3J.13",
        "stop_boundary": "STOP_HISTORY_AWARE_FOLLOW_ON_GENERATION",
        "cf_fg_pass": cf_pass,
        "ordinal_ge3_diagnostic_pass": ord_diag.get("passed"),
        "blind_critical_fp": critical_fp,
        "hidden_answer_audit_pass": audit.get("passed"),
        "regressions_pass": regressions["all_passed"],
        "phase_pass": cf_pass and ord_diag.get("passed") and regressions["all_passed"] and critical_fp == 0 and audit.get("passed"),
    }
    _write("06_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
