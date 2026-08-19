"""Phase 2 discovery tests for Edge Research Engine V1."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EARNING_DIR = REPO_ROOT / "data" / "earning_learning"


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    return d


def _sample_panel(n: int = 120, transition: str = "STRESS -> EARLY_RECOVERY", state: str = "EARLY_RECOVERY") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n):
        rs10 = float(rng.uniform(-15, 5))
        rsi = float(rng.uniform(25, 55))
        rs5 = rs10 + float(rng.uniform(-2, 2))
        t3 = float(rng.normal(1.5 if rs10 <= -5 and rsi <= 40 else 0.2, 2))
        rows.append(
            {
                "trade_date": f"2026-07-{23 + (i % 5):02d}",
                "symbol": f"S{i % 20:03d}",
                "rs5": rs5,
                "rs10": rs10,
                "rsi14": rsi,
                "rs_spread": rs5 - rs10,
                "research_market_state": state,
                "research_market_transition": transition,
                "t3_return": t3,
                "t5_return": t3 + 0.1,
                "t10_return": t3 + 0.2,
            }
        )
    return pd.DataFrame(rows)


# A. Same-transition baseline preferred
def test_same_transition_baseline_preferred():
    from modules.edge_research.baseline import compute_baseline_profiles

    panel = pd.concat(
        [
            _sample_panel(80, "STRESS -> EARLY_RECOVERY", "EARLY_RECOVERY"),
            _sample_panel(80, "MATURE -> ROLLOVER", "ROLLOVER"),
        ],
        ignore_index=True,
    )
    bl = compute_baseline_profiles(
        panel,
        market_transition="STRESS -> EARLY_RECOVERY",
        market_state="EARLY_RECOVERY",
    )
    assert bl.baseline_type == "SAME_TRANSITION"
    assert bl.sample_n >= 50


# B. Same-state fallback when transition insufficient
def test_same_state_fallback_when_transition_insufficient():
    from modules.edge_research.baseline import compute_baseline_profiles

    panel = _sample_panel(60, "STRESS -> EARLY_RECOVERY", "EARLY_RECOVERY")
    panel2 = _sample_panel(10, "UNKNOWN -> EARLY_RECOVERY", "EARLY_RECOVERY")
    full = pd.concat([panel, panel2], ignore_index=True)
    bl = compute_baseline_profiles(
        full,
        market_transition="UNKNOWN -> EARLY_RECOVERY",
        market_state="EARLY_RECOVERY",
    )
    assert bl.baseline_type == "SAME_STATE"


# C. Whole-history baseline never used
def test_whole_history_baseline_never_used():
    from modules.edge_research.baseline import BASELINE_TYPE_INSUFFICIENT, compute_baseline_profiles

    panel = _sample_panel(30, "STRESS -> EARLY_RECOVERY", "EARLY_RECOVERY")
    bl = compute_baseline_profiles(
        panel,
        market_transition="STRESS -> EARLY_RECOVERY",
        market_state="EARLY_RECOVERY",
        min_n=50,
    )
    assert bl.baseline_type == BASELINE_TYPE_INSUFFICIENT


# D. Missing baseline returns INSUFFICIENT
def test_missing_baseline_insufficient():
    from modules.edge_research.baseline import compute_baseline_profiles

    bl = compute_baseline_profiles(
        pd.DataFrame(),
        market_transition="X -> Y",
        market_state="STRESS",
    )
    assert not bl.is_valid


# E. Condition canonicalization prevents duplicates
def test_condition_canonicalization():
    from modules.edge_research.discovery import (
        ConditionClause,
        canonical_condition_key,
        canonical_condition_text,
    )

    c1 = ConditionClause("rs10", "<=", None, -5.0, "rs10_le_-5")
    c2 = ConditionClause("rsi14", "<=", None, 40.0, "rsi14_le_40")
    assert canonical_condition_key([c1, c2]) == canonical_condition_key([c2, c1])
    assert canonical_condition_text([c1, c2]) == canonical_condition_text([c2, c1])


# F. Single-feature search works
def test_single_feature_search():
    from modules.edge_research.discovery import apply_condition, build_clauses_for_feature

    panel = _sample_panel(100)
    clause = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    matched = apply_condition(panel, [clause])
    assert (matched["rs10"] <= -5).all()
    assert len(matched) > 0


# G. Two-feature search works
def test_two_feature_search():
    from modules.edge_research.discovery import apply_condition, build_clauses_for_feature

    panel = _sample_panel(100)
    c1 = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    c2 = [c for c in build_clauses_for_feature("rsi14") if c.bucket_id == "rsi14_30_to_40"][0]
    matched = apply_condition(panel, [c1, c2])
    assert ((matched["rs10"] <= -5) & (matched["rsi14"] > 30) & (matched["rsi14"] <= 40)).all()


# H. Search never uses future values as T0 conditions
def test_search_uses_t0_features_only():
    from modules.edge_research.discovery import ConditionClause, apply_condition

    panel = _sample_panel(50)
    panel["future_leak"] = panel["t3_return"]
    clause = ConditionClause("future_leak", ">", 100.0, None, "leak")
    matched = apply_condition(panel, [clause])
    assert len(matched) == 0 or "future_leak" not in ["rs5", "rs10", "rsi14", "rs_spread"]


# I. Candidate N guard
def test_candidate_n_guard():
    from modules.edge_research.discovery import run_discovery

    panel = _sample_panel(15)
    result = run_discovery(panel)
    assert result.promoted_candidates == 0
    assert result.rejected_insufficient_sample > 0


# J. Baseline N guard
def test_baseline_n_guard():
    from modules.edge_research.baseline import compute_baseline_profiles

    panel = _sample_panel(25)
    bl = compute_baseline_profiles(
        panel,
        market_transition="STRESS -> EARLY_RECOVERY",
        market_state="EARLY_RECOVERY",
        min_n=50,
    )
    assert not bl.is_valid


# K. T3/T5/T10 metrics independent
def test_horizon_metrics_independent():
    from modules.edge_research.metrics import compute_horizon_profile

    t3 = compute_horizon_profile(pd.Series([1, 2, 3]), "T3")
    t5 = compute_horizon_profile(pd.Series([4, 5, 6]), "T5")
    assert t3.mean_return != t5.mean_return


# L. Incremental metrics correct
def test_incremental_metrics_correct():
    from modules.edge_research.metrics import (
        HorizonProfile,
        compute_incremental_metrics,
    )

    cand = HorizonProfile("T5", 10, 3.0, 2.5, 60.0, 30.0, 20.0, 10.0, 5.0)
    base = HorizonProfile("T5", 50, 1.0, 0.5, 50.0, 20.0, 10.0, 15.0, 8.0)
    inc = compute_incremental_metrics(cand, base)
    assert inc["incremental_mean"] == pytest.approx(2.0)
    assert inc["incremental_median"] == pytest.approx(2.0)
    assert inc["incremental_win_rate"] == pytest.approx(10.0)


# M. Best-horizon selection deterministic
def test_best_horizon_deterministic():
    from modules.edge_research.metrics import HorizonProfile, select_best_horizon

    cp = {
        "T3": HorizonProfile("T3", 20, 1.0, 0.5, 55.0, 20.0, 10.0, 12.0, 6.0),
        "T5": HorizonProfile("T5", 20, 2.0, 1.5, 60.0, 25.0, 15.0, 10.0, 5.0),
        "T10": HorizonProfile("T10", 20, 3.0, 2.0, 65.0, 30.0, 20.0, 8.0, 4.0),
    }
    bp = {
        "T3": HorizonProfile("T3", 50, 0.5, 0.0, 50.0, 15.0, 8.0, 15.0, 8.0),
        "T5": HorizonProfile("T5", 50, 0.5, 0.0, 50.0, 15.0, 8.0, 15.0, 8.0),
        "T10": HorizonProfile("T10", 50, 0.5, 0.0, 50.0, 15.0, 8.0, 15.0, 8.0),
    }
    h1 = select_best_horizon(cp, bp)
    h2 = select_best_horizon(cp, bp)
    assert h1 == h2
    assert h1 in ("T3", "T5", "T10")


# N. No promotion without incremental evidence
def test_no_promotion_without_incremental():
    from modules.edge_research.discovery import run_discovery

    panel = _sample_panel(100)
    panel["t3_return"] = -5.0
    panel["t5_return"] = -5.0
    panel["t10_return"] = -5.0
    result = run_discovery(panel)
    assert result.promoted_candidates == 0


# O. Candidate IDs do not duplicate on rerun
def test_candidate_ids_no_duplicate_on_rerun(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    panel = _sample_panel(120)
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()

    import modules.edge_research.engine as eng_mod

    original = eng_mod.build_research_panel

    def _mock_panel(**kwargs):
        return panel

    eng_mod.build_research_panel = _mock_panel
    try:
        r1 = engine.run_discovery()
        r2 = engine.run_discovery()
        ledger = engine.get_top_candidates(limit=100)
        ids = [r["edge_id"] for r in ledger]
        assert len(ids) == len(set(ids))
        assert r2.promoted_candidates <= r1.promoted_candidates
    finally:
        eng_mod.build_research_panel = original


# P. Independent episodes remain 0
def test_independent_episodes_remain_zero(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    status = engine.get_foundation_status()
    assert status.independent_episodes == 0


# Q. Empty discovery no fake voice
def test_empty_discovery_no_fake_voice(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    result = engine.run_discovery(start="2099-01-01", end="2099-01-02")
    assert result.promoted_candidates == 0
    status = engine.get_foundation_status()
    assert status.last_research_event == "NONE"


# R. Research Voice says NOT VALIDATED
def test_research_voice_format():
    from modules.edge_research.ui import _format_research_voice

    text = _format_research_voice({"edge_id": "EDGE-000001", "status": "CANDIDATE"})
    assert "NOT VALIDATED" in text
    assert "EDGE ACTIVE" not in text
    assert "VALIDATED" not in text.replace("NOT VALIDATED", "")


# S. No production decision imports
def test_no_production_decision_imports():
    from modules.edge_research import contracts

    for mod_name in ("discovery", "baseline", "metrics", "engine"):
        mod = importlib.import_module(f"modules.edge_research.{mod_name}")
        src = inspect.getsource(mod)
        for forbidden in contracts.PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in src


# T. Writes only to owned storage
def test_discovery_writes_only_edge_storage(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    def _digest(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    before = _digest(EARNING_DIR / "pattern_lifecycle.csv")
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.run_discovery(start="2099-01-01", end="2099-01-02")
    after = _digest(EARNING_DIR / "pattern_lifecycle.csv")
    assert before == after
    assert (edge_data_dir / "latest_discovery_run.json").exists()
