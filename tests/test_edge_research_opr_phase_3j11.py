"""Phase 3J.11 — Blind autonomous research examination tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_blind_research_examination_01_fixtures import (
    assert_bbbr_firewall,
    run_cf_br_counterfactuals,
    run_single_blind_case,
)
from modules.edge_research.opr_bridge.blind_research_examination_runner import (
    compute_research_policy_hashes,
    run_blind_research_examination,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget


def test_cf_br_counterfactuals():
    cf = run_cf_br_counterfactuals()
    failed = [k for k, v in cf.items() if not v.get("passed")]
    assert not failed, f"CF-BR failures: {failed}"


def test_research_runner_firewall():
    src = (REPO / "modules/edge_research/opr_bridge/blind_research_examination_runner.py").read_text()
    for tok in ("BLIND-A", "ground_truth", "seed_to_blind_class", "true_direction"):
        assert tok not in src


def test_hidden_answer_audit_research_modules():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["blind-a", "ground_truth", "seed_to_blind_class"]
    hits = []
    for path in root.glob("blind_research*.py"):
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append((path.name, tok))
    assert not hits


def test_policy_hash_frozen():
    hashes = compute_research_policy_hashes(REPO)
    assert len(hashes) >= 8
    assert all(len(h) == 64 for h in hashes.values())


def test_blind_case_runs_and_freezes():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_single_blind_case(
            anonymous_id="CASE-0401",
            seed=401,
            data_dir=Path(tmp),
        )
    assert result["frozen"]["lifecycle_frozen_hash"]
    assert len(result["frozen"]["lifecycle_frozen_hash"]) == 64
    assert result["reveal"]["reveal_order_valid"]
    assert_bbbr_firewall(result["frozen"])


def test_reveal_before_freeze_invalid():
    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import reveal_and_score

    reveal = reveal_and_score(
        {"anonymous_case_id": "X", "lifecycle_frozen_hash": "", "final_epistemic_state": "UNRESOLVED"},
        seed=401,
        ground_truth={"mechanism": "test"},
        reveal_after_hash="expected_but_missing",
    )
    assert not reveal.reveal_order_valid


def test_examiner_not_imported_by_lifecycle_controller():
    src = (REPO / "modules/edge_research/opr_bridge/bounded_lifecycle_controller.py").read_text()
    assert "bb_blind_exam" not in src
    assert "lifecycle_examiner" not in src
    assert "panel_generator" not in src


def test_3j10_regression_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j10.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
