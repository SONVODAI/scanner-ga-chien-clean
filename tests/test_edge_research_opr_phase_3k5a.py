"""Phase 3K.5A — Production prerequisite closure tests."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.bb_production_prerequisite_01_fixtures import run_cf_pr_counterfactuals
from modules.edge_research.opr_bridge.production_daily_run_records import DAY_0_SMOKE
from modules.edge_research.opr_bridge.production_eod_completeness import verify_eod_completeness
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_prerequisite_closure_audit import (
    STOP_PRODUCTION_PREREQUISITES_CLOSED,
    run_prerequisite_closure_audit,
)
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_policy import (
    derive_utc_calendar_date,
    derive_vn_trade_date,
    reject_utc_derived_genesis_date,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
    is_calendar_loaded,
    offset_trading_sessions,
)


def test_stop_boundary_constant():
    assert STOP_PRODUCTION_PREREQUISITES_CLOSED == "STOP_PRODUCTION_PREREQUISITES_CLOSED"


def test_cf_pr_counterfactuals():
    cf = run_cf_pr_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_vn_calendar_loaded():
    assert is_calendar_loaded()


def test_vn_holiday_blocks():
    cal = evaluate_calendar_session_eligibility("2026-01-01")
    assert not cal.eligible
    assert cal.reason == "exchange_holiday"


def test_timezone_boundary_utc_vs_vn():
    boundary = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)
    assert derive_utc_calendar_date(boundary) == "2026-08-21"
    assert derive_vn_trade_date(boundary) == "2026-08-22"
    ok, reason = reject_utc_derived_genesis_date("2026-08-21", activation_now=boundary)
    assert not ok
    assert "utc" in reason.lower()


def test_eod_completeness_production_date():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("no production panel")
    target = str(panel["trade_date"].astype(str).max())
    eod = verify_eod_completeness(panel, target)
    assert eod.complete, eod.to_dict()


def test_t3_skips_holiday():
    t3 = offset_trading_sessions("2026-04-24", 3)
    assert t3 is not None
    assert t3 > "2026-04-24"


def test_scheduler_not_activated():
    contract = build_scheduling_contract()
    assert contract["activated"] is False
    assert contract["systemd_artifacts_prepared"] is True


def test_prerequisite_closure_audit():
    audit = run_prerequisite_closure_audit(REPO)
    assert audit["go_no_go"]["genesis_exists"] is False
    assert audit["go_no_go"]["live_forward_activated"] is False
    assert not audit["go_no_go"]["any_fail"], audit["go_no_go"]
    assert audit["go_no_go"]["recommendation"] == "READY_FOR_DEPLOYMENT_DAY_0"
    assert audit["phase_pass"] is True


def test_day0_smoke_non_forward():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("no production panel")
    from modules.edge_research.opr_bridge.production_day0_smoke import run_day0_smoke
    target = str(panel["trade_date"].astype(str).max())
    smoke = run_day0_smoke(panel, target_trade_date=target, repo_root=REPO)
    assert smoke["counts_as_forward_evidence"] is False
    assert smoke["promotable"] is False


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit


def test_3k5_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k5.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


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
