#!/usr/bin/env python3
"""Phase 3J.11 — Blind autonomous research examination diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))

CASE_REGISTRY = REPO / "benchmarks/bb_blind_exam_01/zone_b_researcher/case_registry.json"
ZONE_C = REPO / "benchmarks/bb_blind_exam_01/zone_c_examiner"


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


def freeze_policy_hashes() -> dict:
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        compute_research_policy_hashes,
    )

    hashes = compute_research_policy_hashes(REPO)
    return {"frozen_at_head": _git_head(), "policy_hashes": hashes}


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    research_modules = [
        "blind_research_examination_runner.py",
        "bounded_lifecycle_controller.py",
        "bounded_lifecycle_records.py",
        "bounded_lifecycle_state.py",
        "production_bounded_lifecycle.py",
        "production_trigger.py",
        "first_experiment_research_decider.py",
        "second_experiment_research_decider.py",
    ]
    forbidden = [
        "blind-a",
        "blind-b",
        "blind-c",
        "blind-d",
        "blind-e",
        "blind-f",
        "ground_truth",
        "true_direction",
        "july 27",
        "2.352",
        "prop-efb650d9bd5c451f",
        "seed_to_blind_class",
        "artifact_or_confound",
    ]
    hits = []
    for name in research_modules:
        path = root / name
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"file": name, "token": tok})
    return {"passed": len(hits) == 0, "hits": hits}


def run_cf_br() -> dict:
    from modules.edge_research.opr_bridge.bb_blind_research_examination_01_fixtures import (
        run_cf_br_counterfactuals,
    )

    return run_cf_br_counterfactuals()


def run_blind_examination_suite() -> dict:
    from modules.edge_research.opr_bridge.bb_blind_research_examination_01_fixtures import (
        run_single_blind_case,
    )
    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import (
        aggregate_suite_scores,
    )

    registry = json.loads(CASE_REGISTRY.read_text(encoding="utf-8"))
    cases_out = []
    reveals = []

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        for case in registry["cases"]:
            result = run_single_blind_case(
                anonymous_id=case["anonymous_id"],
                seed=case["seed"],
                cutoff=case["cutoff"],
                data_dir=data_dir,
            )
            cases_out.append(
                {
                    "anonymous_id": case["anonymous_id"],
                    "seed": case["seed"],
                    "journey": result["frozen"],
                    "reveal": result["reveal"],
                }
            )
            from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import (
                ExaminerRevealRecord,
            )

            reveals.append(ExaminerRevealRecord(**{
                k: result["reveal"][k]
                for k in ExaminerRevealRecord.__dataclass_fields__
                if k in result["reveal"]
            }))

    agg = aggregate_suite_scores(reveals)
    journey_table = []
    for c in cases_out:
        frozen = c["journey"]
        for row in frozen.get("journey_rows", []):
            journey_table.append({"anonymous_id": c["anonymous_id"], **row})
        if not frozen.get("journey_rows"):
            journey_table.append(
                {
                    "anonymous_id": c["anonymous_id"],
                    "ordinal": 0,
                    "lifecycle_outcome": frozen.get("lifecycle_outcome"),
                    "termination_reason": frozen.get("termination_reason"),
                    "final_epistemic_state": frozen.get("final_epistemic_state"),
                }
            )

    return {
        "cases": cases_out,
        "journey_table": journey_table,
        "aggregate": agg,
    }


def run_regressions() -> dict:
    suites = [
        "tests/test_edge_research_opr_phase_3j11.py",
        "tests/test_edge_research_opr_phase_3j10.py",
        "tests/test_edge_research_opr_phase_3j9.py",
        "tests/test_edge_research_opr_phase_3j8.py",
    ]
    results = {}
    for suite in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q", "--tb=no"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results[suite] = {
            "exit_code": proc.returncode,
            "passed": proc.returncode == 0,
            "tail": proc.stdout.strip().split("\n")[-1] if proc.stdout else proc.stderr[-200:],
        }
    return {"suites": results, "all_passed": all(r["passed"] for r in results.values())}


def main() -> int:
    # Generate ground truth manifest (Zone C examiner-only)
    sys.path.insert(0, str(ZONE_C))
    from panel_generator import write_ground_truth_manifest

    write_ground_truth_manifest(ZONE_C / "ground_truth_manifest.json")

    policy = freeze_policy_hashes()
    _write("00_frozen_policy_hashes.json", policy)

    hidden = run_hidden_answer_audit()
    _write("01_hidden_answer_audit.json", hidden)

    cf = run_cf_br()
    _write("02_cf_br_summary.json", cf)
    cf_pass = all(v.get("passed", False) for v in cf.values())

    exam = run_blind_examination_suite()
    _write("03_blind_examination_cases.json", exam["cases"])
    _write("04_journey_table.json", exam["journey_table"])
    _write("05_aggregate_scores.json", exam["aggregate"])

    regressions = run_regressions()
    _write("06_regression_summary.json", regressions)

    exam_integrity_pass = hidden["passed"] and cf_pass
    scientific_pass = exam["aggregate"].get("scientific_behavior_pass", False)
    phase_pass = exam_integrity_pass and scientific_pass and regressions["all_passed"]

    summary = {
        "branch": _git_branch(),
        "head": _git_head(),
        "phase": "3J.11",
        "stop_boundary": "STOP_BLIND_EXAMINATION_COMPLETE",
        "exam_integrity_pass": exam_integrity_pass,
        "scientific_behavior_pass": scientific_pass,
        "regressions_pass": regressions["all_passed"],
        "phase_pass": phase_pass,
        "case_count": exam["aggregate"].get("case_count", 0),
        "critical_false_positives": exam["aggregate"].get("critical_false_positive_count", 0),
    }
    _write("07_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if phase_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
