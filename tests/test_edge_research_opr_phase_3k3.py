"""Phase 3K.3 — Forward evidence & calibration ledger tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.bb_forward_evidence_calibration_01_fixtures import (
    run_cf_cal_counterfactuals,
)
from modules.edge_research.opr_bridge.production_calibration_records import (
    STOP_FORWARD_EVIDENCE_CALIBRATION_READY,
    ClaimMaturity,
    derive_claim_maturity,
)
from modules.edge_research.opr_bridge.production_calibration_self_knowledge import build_self_knowledge_read_model
from modules.edge_research.opr_bridge.production_calibration_simulation import (
    run_calibration_mechanics_simulation,
    run_live_forward_mechanics_fixture,
)
from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit


def test_cf_cal_counterfactuals():
    cf = run_cf_cal_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_stop_boundary_constant():
    assert STOP_FORWARD_EVIDENCE_CALIBRATION_READY == "STOP_FORWARD_EVIDENCE_CALIBRATION_READY"


def test_claim_maturity_labels():
    assert derive_claim_maturity(0) == ClaimMaturity.NO_FORWARD_EVIDENCE.value
    assert derive_claim_maturity(1) == ClaimMaturity.IMMATURE.value
    assert derive_claim_maturity(3) == ClaimMaturity.EARLY_SAMPLE.value
    assert derive_claim_maturity(6) == ClaimMaturity.ACCUMULATING.value
    assert derive_claim_maturity(15) == ClaimMaturity.REVIEWABLE.value


def test_calibration_mechanics_simulation():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    if len(dates) < 12:
        pytest.skip("Insufficient sessions")
    with tempfile.TemporaryDirectory() as tmp:
        sim = run_calibration_mechanics_simulation(
            panel,
            num_sessions=12,
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert sim.get("all_backfill_rejected_from_forward_ledger") is True
    assert sim.get("forward_ledger_entry_count") == 0
    assert sim.get("idempotent_rebuild") is True
    assert sim.get("counts_as_forward_evidence") is False


def test_self_knowledge_read_model():
    with tempfile.TemporaryDirectory() as tmp:
        model = build_self_knowledge_read_model(data_dir=Path(tmp))
    assert model["no_profitability_claim"] is True
    assert model["no_buy_sell"] is True
    assert model["shadow_authority"]["trading_authority"] is False
    assert model["shadow_authority"]["edge_active"] is False
    assert any("NO_FORWARD_EVIDENCE" in s or "no authoritative" in s.lower() for s in model["statements"])


def test_live_forward_mechanics_fixture():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    with tempfile.TemporaryDirectory() as tmp:
        result = run_live_forward_mechanics_fixture(
            panel,
            target_trade_date=dates[0],
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert result["counts_as_forward_evidence"] is True
    assert result["run"]["counts_as_forward_evidence"] is True


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in [
        "production_calibration_engine.py",
        "production_calibration_updater.py",
        "production_calibration_records.py",
    ]:
        path = root / name
        if path.exists():
            blob = path.read_text(encoding="utf-8").lower()
            for tok in forbidden:
                if tok in blob:
                    hits.append((name, tok))
    assert not hits


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
