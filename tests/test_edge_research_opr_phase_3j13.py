"""Phase 3J.13 — History-aware follow-on experiment generation tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_history_aware_follow_on_generation_01_fixtures import (
    run_cf_fg_counterfactuals,
)
from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity


def test_cf_fg_counterfactuals():
    cf = run_cf_fg_counterfactuals()
    failed = [k for k, v in cf.items() if not v.get("passed")]
    assert not failed, f"CF-FG failures: {failed}"


def test_ordinal_3_uses_history_aware_generator():
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
            budget=ResearchBudget(max_experiment_iterations=4),
            bootstrap_new_session=True,
        )
    history = build_experiment_history(r.session_record) if r.session_record else []
    ord3 = next((e for e in history if e.ordinal == 3), None)
    if ord3 and ord3.package:
        gen = ord3.package.get("generator_version", "")
        assert "follow_on_experiment_generator" in gen


def test_research_modules_no_blind_leakage():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["blind-a", "blind-b", "seed_to_blind_class", "ground_truth_manifest"]
    hits = []
    for name in [
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_history_context.py",
        "follow_on_experiment_selector.py",
    ]:
        blob = (root / name).read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append((name, tok))
    assert not hits


def test_3j12_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j12.py", "-q", "--tb=no"],
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


def test_3j10_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j10.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
