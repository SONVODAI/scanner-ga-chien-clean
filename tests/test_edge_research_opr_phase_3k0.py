"""Phase 3K.0 — Production research observation foundation tests."""

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
from modules.edge_research.opr_bridge.bb_production_research_observation_01_fixtures import (
    run_cf_obs_counterfactuals,
)
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_observation_narrative import (
    build_narrative_contract,
    build_ui_contract,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ForwardEvaluationStatus,
    HISTORICAL_REPLAY_TEST,
)
from modules.edge_research.opr_bridge.production_research_observation import (
    run_historical_replay_test,
    run_production_research_observation,
)


def test_cf_obs_counterfactuals():
    cf = run_cf_obs_counterfactuals(REPO)
    assert cf["all_passed"], cf


def test_shadow_authority_flags():
    auth = DEFAULT_SHADOW_AUTHORITY
    assert auth.research_only is True
    assert auth.trading_authority is False
    assert auth.buy_signal is False
    assert auth.sell_signal is False
    assert auth.edge_active is False


def test_historical_replay_temporal_integrity():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        replay = run_historical_replay_test(
            panel,
            data_cutoff_date="2026-08-01",
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    assert replay["test_kind"] == HISTORICAL_REPLAY_TEST
    assert replay["temporal_provenance_established"] is True
    assert replay["counts_as_forward_evidence"] is False
    assert replay["birth_record"] is not None
    horizons = replay["forward_horizons_at_birth"]
    assert all(h["status"] == ForwardEvaluationStatus.PENDING_FUTURE.value for h in horizons)
    assert all(h.get("realized_outcome") is None for h in horizons)


def test_idempotent_observation():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        r1 = run_production_research_observation(
            panel, data_cutoff_date="2026-08-05", data_dir=data_dir, persist=True
        )
        r2 = run_production_research_observation(
            panel, data_cutoff_date="2026-08-05", data_dir=data_dir, persist=True
        )
    assert r1.observation_id == r2.observation_id
    assert r2.idempotent_replay is True


def test_silence_observation_persisted():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        r = run_production_research_observation(
            panel, data_cutoff_date="2026-08-01", data_dir=Path(tmp), persist=True
        )
    assert r.birth_record is not None
    assert r.birth_record.frozen is True
    assert r.birth_record.shadow_authority.research_only is True


def test_narrative_and_ui_contracts():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("No research panel data")
    with tempfile.TemporaryDirectory() as tmp:
        r = run_production_research_observation(
            panel, data_cutoff_date="2026-08-01", data_dir=Path(tmp), persist=True
        )
    birth = r.birth_record
    narrative = build_narrative_contract(birth)
    ui = build_ui_contract(birth)
    assert narrative.narrative_authority == "STRUCTURED_STATE_ONLY"
    assert ui.no_buy_button is True
    assert ui.no_sell_button is True
    assert ui.no_trade_recommendation is True


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in [
        "production_research_observation.py",
        "production_observation_cutoff.py",
        "production_observation_records.py",
    ]:
        blob = (root / name).read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append((name, tok))
    assert not hits


def test_policy_hashes_unchanged_from_3j14():
    frozen_path = (
        REPO
        / "diagnostics/phase_3j14_research_capability_gap_audit/artifacts/00_frozen_policy_hashes.json"
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


def test_3j14a_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j14a.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
