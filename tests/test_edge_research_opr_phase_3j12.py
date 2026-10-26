"""Phase 3J.12 — N-experiment research generalization tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_n_experiment_generalization_01_fixtures import (
    run_cf_nx_counterfactuals,
)
from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity


def test_cf_nx_counterfactuals():
    cf = run_cf_nx_counterfactuals()
    failed = [k for k, v in cf.items() if not v.get("passed")]
    assert not failed, f"CF-NX failures: {failed}"


def test_no_architectural_break_at_ordinal_3():
    panel = _anomaly_panel(seed=77)
    det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
    if det.outcome != "OPPORTUNITY_DETECTED":
        pytest.skip("No opportunity")
    with tempfile.TemporaryDirectory() as tmp:
        r = run_bounded_autonomous_research(
            det.proposition_record,
            panel,
            data_cutoff_date="2026-02-15",
            data_dir=Path(tmp),
            budget=ResearchBudget(max_experiment_iterations=3),
            bootstrap_new_session=True,
        )
    assert r.lifecycle is not None
    assert r.lifecycle.outcome != "FAILED_CLOSED" or "architectural_break" not in str(r.lifecycle.errors)
    history = build_experiment_history(r.session_record)
    assert len([e for e in history if e.execution]) >= 2


def test_research_modules_no_blind_class_leakage():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["blind-a", "blind-b", "seed_to_blind_class", "ground_truth_manifest"]
    hits = []
    for name in [
        "follow_on_experiment_core.py",
        "follow_on_experiment_interpreter.py",
        "follow_on_research_decision_adapter.py",
        "bounded_lifecycle_controller.py",
    ]:
        blob = (root / name).read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append((name, tok))
    assert not hits


def test_3j10_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j10.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j11_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j11.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
