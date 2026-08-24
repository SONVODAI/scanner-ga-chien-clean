"""Phase 3K.2 — Production daily observation runner tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.bb_production_daily_run_01_fixtures import run_cf_run_counterfactuals
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
    run_production_simulation_15_sessions,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    HISTORICAL_REPLAY_TEST,
    STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
)
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract


def test_cf_run_counterfactuals():
    cf = run_cf_run_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_stop_boundary_constant():
    assert STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY == "STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY"


def test_daily_run_success():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    with tempfile.TemporaryDirectory() as tmp:
        result = run_production_daily_research(
            panel,
            target_trade_date=dates[0],
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert result["run"]["run_disposition"] == "SUCCESS"
    assert result["run"]["shadow_authority"]["research_only"] is True
    assert result["counts_as_forward_evidence"] is False


def test_daily_run_idempotent():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        run_production_daily_research(
            panel, target_trade_date=dates[5], run_mode=BACKFILL_NON_FORWARD, data_dir=data_dir, repo_root=REPO
        )
        r2 = run_production_daily_research(
            panel, target_trade_date=dates[5], run_mode=BACKFILL_NON_FORWARD, data_dir=data_dir, repo_root=REPO
        )
    assert r2["idempotent_replay"] is True


def test_simulation_15_sessions():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    if len(dates) < 15:
        pytest.skip("Insufficient sessions")
    with tempfile.TemporaryDirectory() as tmp:
        sim = run_production_simulation_15_sessions(
            panel,
            start_trade_date=dates[0],
            num_sessions=15,
            run_mode=HISTORICAL_REPLAY_TEST,
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert sim["num_sessions"] >= 15
    assert sim["counts_as_forward_evidence"] is False
    assert sim["duplicate_invocation_idempotent"] is True


def test_scheduling_contract_not_activated():
    contract = build_scheduling_contract()
    assert contract["activated"] is False
    assert contract["cron_installed"] is False
    assert contract["systemd_timer_installed"] is False


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in [
        "production_daily_run_orchestrator.py",
        "production_daily_run_records.py",
    ]:
        path = root / name
        if path.exists():
            blob = path.read_text(encoding="utf-8").lower()
            for tok in forbidden:
                if tok in blob:
                    hits.append((name, tok))
    assert not hits


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
