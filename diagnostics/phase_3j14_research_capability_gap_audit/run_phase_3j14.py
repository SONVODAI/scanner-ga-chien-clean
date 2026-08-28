#!/usr/bin/env python3
"""Phase 3J.14 — Research capability gap & process-integrity audit diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))


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


def main() -> int:
    from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.bb_capability_gap_audit_01_fixtures import (
        run_cf_cg_counterfactuals,
    )
    from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.capability_gap_auditor import (
        freeze_policy_hashes,
        run_full_capability_gap_audit,
    )

    policy_hashes = {"frozen_at_head": _git_head(), "policy_hashes": freeze_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy_hashes)

    cf = run_cf_cg_counterfactuals(REPO)
    _write("01_cf_cg_summary.json", cf)

    audit = run_full_capability_gap_audit(REPO)
    _write("02_process_integrity_delta.json", audit["process_integrity_delta"])
    _write("03_longer_journey_safety.json", audit["longer_journey_safety"])
    _write("04_false_positive_restraint.json", audit["false_positive_restraint"])
    _write("05_toolbox_coverage_map.json", audit["toolbox_coverage_map"])
    _write("06_ordinal_ge3_silence_audits.json", audit["ordinal_ge3_silence_audits"])

    hidden = _hidden_answer_audit()
    _write("07_hidden_answer_audit.json", hidden)

    regressions = _run_regressions()
    _write("08_regression_summary.json", regressions)

    cf_pass = all(v.get("passed") for v in cf.values())
    pi = audit["process_integrity_delta"]
    summary = {
        "head": _git_head(),
        "branch": _git_branch(),
        "phase": "3J.14",
        "stop_boundary": "STOP_RESEARCH_CAPABILITY_GAP_AUDITED",
        "cf_cg_pass": cf_pass,
        "avg_process_integrity_baseline": pi.get("avg_original_process_integrity"),
        "avg_process_integrity_longer_budget": pi.get("avg_new_process_integrity"),
        "process_integrity_changed_cases": pi.get("changed_case_count"),
        "critical_false_positives": audit["false_positive_restraint"].get("critical_false_positive_count"),
        "silence_audit_count": len(audit["ordinal_ge3_silence_audits"]),
        "hidden_answer_audit_pass": hidden.get("passed"),
        "regressions_pass": regressions.get("all_passed"),
        "phase_pass": cf_pass and hidden.get("passed") and regressions.get("all_passed"),
    }
    _write("09_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


def _hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    exam_root = REPO / "benchmarks/bb_capability_gap_audit_01"
    research_modules = [
        "blind_research_examination_runner.py",
        "bounded_lifecycle_controller.py",
        "bounded_lifecycle_records.py",
        "bounded_lifecycle_state.py",
        "production_bounded_lifecycle.py",
        "production_trigger.py",
        "first_experiment_research_decider.py",
        "second_experiment_research_decider.py",
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_history_context.py",
        "follow_on_experiment_selector.py",
        "second_experiment_pipeline.py",
        "second_experiment_candidates.py",
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
                hits.append({"module": name, "token": tok})
    return {"passed": not hits, "hits": hits, "examiner_zone_isolated": exam_root.exists()}


def _run_regressions() -> dict:
    suites = [
        "tests/test_edge_research_opr_phase_3j14.py",
        "tests/test_edge_research_opr_phase_3j13.py::test_cf_fg_counterfactuals",
        "tests/test_edge_research_opr_phase_3j12.py::test_cf_nx_counterfactuals",
        "tests/test_edge_research_opr_phase_3j11.py::test_cf_br_counterfactuals",
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


if __name__ == "__main__":
    raise SystemExit(main())
