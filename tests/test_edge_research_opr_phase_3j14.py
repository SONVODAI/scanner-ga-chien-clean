"""Phase 3J.14 — Research capability gap & process-integrity audit tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.bb_capability_gap_audit_01_fixtures import (
    run_cf_cg_counterfactuals,
)


def test_cf_cg_counterfactuals():
    cf = run_cf_cg_counterfactuals(REPO)
    failed = [k for k, v in cf.items() if not v.get("passed")]
    assert not failed, f"CF-CG failures: {failed}"


def test_examiner_zone_not_in_research_imports():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["bb_capability_gap_audit", "capability_probe", "seed_to_blind_class"]
    hits = []
    for path in root.glob("*.py"):
        if path.name.startswith("bb_"):
            continue
        blob = path.read_text(encoding="utf-8")
        for tok in forbidden:
            if tok in blob:
                hits.append((path.name, tok))
    assert not hits


def test_silence_classifier_justified_episode():
    from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.silence_classifier import classify_silence

    result = classify_silence(
        package={
            "disposition": "NO_FAITHFUL_EXPERIMENT",
            "objective": {
                "target_null_key": "episode_artifact",
                "target_uncertainty": "episode_robustness",
                "selected_action": "SEEK_FALSIFICATION",
            },
            "candidates_considered": [
                {
                    "target_null_key": "episode_artifact",
                    "scientific_identity": {"cohort_strategy": "episode_holdout_excluding_motivating"},
                    "primary_classification": "INADMISSIBLE",
                    "rejection_reasons": ["previously_rejected_core_hash"],
                }
            ],
        },
        prior_packages=[
            {
                "objective": {"target_null_key": "episode_artifact"},
                "selected_candidate_id": "x",
                "deduplicated_candidates": [
                    {
                        "candidate_id": "x",
                        "scientific_identity": {"cohort_strategy": "episode_holdout_excluding_motivating"},
                        "primary_classification": "ADMISSIBLE",
                    }
                ],
            }
        ],
    )
    assert result["classification"] in ("JUSTIFIED_SCIENTIFIC_SILENCE", "REDUNDANCY_STOP")


def test_3j13_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j13.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
