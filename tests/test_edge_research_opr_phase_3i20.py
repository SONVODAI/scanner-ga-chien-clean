"""Phase 3I.20 — Dormancy lifecycle integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_integration_module_exists():
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import (
        on_scientific_frontier_completed,
        on_research_opportunity_state_changed,
    )

    assert on_scientific_frontier_completed is not None
    assert on_research_opportunity_state_changed is not None


def test_lifecycle_integration_leakage():
    from modules.edge_research.opr_bridge.dormancy_audit import lifecycle_integration_leakage_audit

    audit = lifecycle_integration_leakage_audit()
    assert audit["passed"], audit


@pytest.mark.parametrize(
    "case",
    __import__(
        "modules.edge_research.opr_bridge.bb_dormancy_01_fixtures",
        fromlist=["all_bb_dormancy_cases"],
    ).all_bb_dormancy_cases(),
    ids=lambda c: c["case_id"],
)
def test_bb_dormancy_01_regression(case):
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import evaluate_bb_dormancy_case, run_bb_dormancy_case

    run = run_bb_dormancy_case(case)
    ev = evaluate_bb_dormancy_case(case, run)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


@pytest.mark.parametrize(
    "case",
    __import__(
        "modules.edge_research.opr_bridge.bb_dormancy_lifecycle_01_fixtures",
        fromlist=["all_bbdl_cases"],
    ).all_bbdl_cases(),
    ids=lambda c: c["case_id"],
)
def test_bb_dormancy_lifecycle_01(case):
    from modules.edge_research.opr_bridge.bb_dormancy_lifecycle_01_fixtures import evaluate_bbdl_case, run_bbdl_case

    run = run_bbdl_case(case)
    ev = evaluate_bbdl_case(case, run)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


def test_epistemic_separate_from_activity():
    from modules.edge_research.opr_bridge.bb_dormancy_lifecycle_01_fixtures import all_bbdl_cases, run_bbdl_case

    case = next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-01")
    run = run_bbdl_case(case)
    assert run["pipeline"]["epistemic_state"] == "SUPPORTED"
    assert run["state"].research_activity_state == "DORMANT"


def test_t2_lifecycle_replay_frozen():
    diag = REPO / "diagnostics/phase_3i20_dormancy_lifecycle/artifacts/04_t2_lifecycle_replay.json"
    if not diag.exists():
        pytest.skip("Run diagnostics/phase_3i20_dormancy_lifecycle/run_phase_3i20.py first")
    payload = json.loads(diag.read_text())
    assert payload["execution_status"] == "NOT_EXECUTED"
    assert payload["epistemic_state"] == "SUPPORTED"
    assert payload["frontier_decision"] == "NO_HIGH_INFORMATION_ACTION"
    assert payload["research_activity_state"] == "DORMANT"
    assert payload["frozen_integrity"]["passed"] is True
