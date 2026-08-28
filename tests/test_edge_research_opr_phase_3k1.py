"""Phase 3K.1 — Living research observation & daily assessment tests."""

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
from modules.edge_research.opr_bridge.bb_living_research_observation_01_fixtures import (
    run_cf_live_counterfactuals,
)
from modules.edge_research.opr_bridge.production_living_observation_records import (
    HISTORICAL_MULTI_DAY_REPLAY,
    STOP_LIVING_RESEARCH_OBSERVATION_READY,
    DEFAULT_SHADOW_AUTHORITY,
)
from modules.edge_research.opr_bridge.production_living_read_model import (
    build_full_read_model,
    build_today_read_model,
)
from modules.edge_research.opr_bridge.production_living_research_observation import (
    run_daily_living_assessment,
    run_historical_multi_day_replay,
)
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_research_observation import run_production_research_observation


def test_cf_live_counterfactuals():
    cf = run_cf_live_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_stop_boundary_constant():
    assert STOP_LIVING_RESEARCH_OBSERVATION_READY == "STOP_LIVING_RESEARCH_OBSERVATION_READY"


def test_shadow_authority_on_assessment():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        birth = run_production_research_observation(
            panel, data_cutoff_date="2026-08-01", data_dir=data_dir, persist=True
        )
        result = run_daily_living_assessment(
            panel,
            assessment_trade_date="2026-08-01",
            observation_ids=[birth.observation_id],
            data_dir=data_dir,
        )
    assert result["summary"] is not None
    auth = result["summary"]["shadow_authority"]
    assert auth["research_only"] is True
    assert auth["trading_authority"] is False


def test_historical_multi_day_replay():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    dates = sorted(panel["trade_date"].astype(str).unique())
    if len(dates) < 10:
        pytest.skip("Insufficient trading days")
    with tempfile.TemporaryDirectory() as tmp:
        replay = run_historical_multi_day_replay(
            panel,
            start_trade_date=dates[0],
            num_trading_days=10,
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert replay["test_kind"] == HISTORICAL_MULTI_DAY_REPLAY
    assert replay["counts_as_forward_evidence"] is False
    assert replay["num_days"] >= 10
    demos = replay["demonstrations"]
    assert demos["unchanged_belief_days"] or demos["changed_assessment_days"] or replay["num_days"] >= 10


def test_daily_assessment_idempotent():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        birth = run_production_research_observation(
            panel, data_cutoff_date="2026-08-05", data_dir=data_dir, persist=True
        )
        r1 = run_daily_living_assessment(
            panel, assessment_trade_date="2026-08-05", observation_ids=[birth.observation_id], data_dir=data_dir
        )
        r2 = run_daily_living_assessment(
            panel, assessment_trade_date="2026-08-05", observation_ids=[birth.observation_id], data_dir=data_dir
        )
    assert r1["idempotent_keys"] == r2["idempotent_keys"]


def test_read_model_contract():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        birth = run_production_research_observation(
            panel, data_cutoff_date="2026-08-01", data_dir=data_dir, persist=True
        )
        run_daily_living_assessment(
            panel, assessment_trade_date="2026-08-01", observation_ids=[birth.observation_id], data_dir=data_dir
        )
        today = build_today_read_model(trade_date="2026-08-01", data_dir=data_dir)
        full = build_full_read_model(
            trade_date="2026-08-01", observation_ids=[birth.observation_id], data_dir=data_dir
        )
    assert today["section"] == "TODAY"
    assert "daily_voices" in today
    assert full["today"]["section"] == "TODAY"
    assert full["history"]["section"] == "HISTORY"


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in [
        "production_living_research_observation.py",
        "production_daily_assessment.py",
        "production_daily_voice.py",
    ]:
        path = root / name
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append((name, tok))
    assert not hits


def test_policy_hashes_unchanged_from_3j14():
    frozen_path = (
        REPO / "diagnostics/phase_3j14_research_capability_gap_audit/artifacts/00_frozen_policy_hashes.json"
    )
    if not frozen_path.exists():
        pytest.skip("3J.14 frozen hashes unavailable")
    frozen = json.loads(frozen_path.read_text())["policy_hashes"]
    root = REPO / "modules/edge_research/opr_bridge"
    unchanged = [
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_selector.py",
        "production_trigger.py",
        "first_experiment_research_decider.py",
    ]
    for name in unchanged:
        path = root / name
        if path.exists() and name in frozen:
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            assert h == frozen[name], f"unexpected hash change: {name}"


def test_3k0_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k0.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j14a_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j14a.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
