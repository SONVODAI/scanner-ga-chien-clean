"""Phase 3K.5 — LIVE_FORWARD production readiness audit tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.bb_live_forward_production_readiness_01_fixtures import (
    run_cf_ready_counterfactuals,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    DAY_0_SMOKE,
    PRE_DEPLOYMENT_DRY_RUN,
    STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED,
)
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_readiness_audit import run_full_production_readiness_audit
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract


def test_cf_ready_counterfactuals():
    cf = run_cf_ready_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_stop_boundary_constant():
    assert STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED == "STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED"


def test_full_readiness_audit():
    audit = run_full_production_readiness_audit(REPO)
    assert audit["live_forward_activated"] is False
    assert audit["genesis_exists"] is False
    assert "readiness_matrix" in audit
    assert not audit["readiness_matrix"].get("any_fail"), audit["readiness_matrix"]


def test_scheduling_not_activated():
    contract = build_scheduling_contract()
    assert contract["activated"] is False
    assert contract["cron_installed"] is False


def test_new_run_modes_non_forward():
    from modules.edge_research.opr_bridge.production_daily_run_records import mode_counts_as_forward_evidence
    assert mode_counts_as_forward_evidence(DAY_0_SMOKE) is False
    assert mode_counts_as_forward_evidence(PRE_DEPLOYMENT_DRY_RUN) is False


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit
    assert "production_readiness_audit.py" in audit.get("modules_audited", [])


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in ["production_readiness_audit.py", "production_live_forward_genesis.py"]:
        path = root / name
        if path.exists():
            blob = path.read_text(encoding="utf-8").lower()
            for tok in forbidden:
                if tok in blob:
                    hits.append((name, tok))
    assert not hits


def test_3k4_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k4.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k3_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k3.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k2_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k2.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k1_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k1.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k0_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k0.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
