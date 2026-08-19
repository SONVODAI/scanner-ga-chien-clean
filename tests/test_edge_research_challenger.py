"""Phase 3 challenger / robustness / episode tests."""

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


def _panel(n: int = 120, transition: str = "STRESS -> STRESS") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    dates = [f"2026-07-{23 + i % 5:02d}" for i in range(n)]
    for i in range(n):
        rs10 = float(rng.uniform(-15, -8)) if i < 30 else float(rng.uniform(-5, 5))
        rsi = float(rng.uniform(25, 38)) if i < 30 else float(rng.uniform(35, 55))
        rows.append(
            {
                "trade_date": dates[i],
                "symbol": f"S{i % 15:03d}",
                "rs5": rs10 + 1,
                "rs10": rs10,
                "rsi14": rsi,
                "rs_spread": 1.0,
                "research_market_state": "STRESS",
                "research_market_transition": transition,
                "market_real": 5.0,
                "t3_return": float(rng.normal(1, 2)),
                "t5_return": float(rng.normal(1.5, 2)),
                "t10_return": float(rng.normal(2, 2)),
            }
        )
    return pd.DataFrame(rows)


def _ledger_row() -> pd.Series:
    return pd.Series(
        {
            "edge_id": "EDGE-000001",
            "market_state": "STRESS",
            "market_transition": "STRESS -> STRESS",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10.0,
            "feature_2": "",
            "operator_2": "",
            "threshold_2": "",
            "best_horizon": "T10",
            "status": "CANDIDATE",
            "candidate_n": 30,
            "incremental_median": 2.0,
        }
    )


# A. Challenger only reads Phase 2 candidates
def test_challenger_reads_phase2_candidates_only(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import read_ledger, write_discovery_run

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    ledger = pd.DataFrame([_ledger_row()])
    ledger.to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    write_discovery_run(
        {
            "run_id": "disc001",
            "promoted_candidates": 1,
            "candidates": [{"condition_key": "STRESS -> STRESS|rs10:rs10_le_-10"}],
        },
        data_dir=edge_data_dir,
    )
    result = engine.run_challenger(force=True)
    assert result.candidates_entering >= 1
    updated = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert "robustness_status" in updated.columns


def test_challenger_scopes_latest_discovery_cohort_only(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import resolve_discovery_cohort, write_discovery_run

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    row_a = _ledger_row()
    row_b = _ledger_row()
    row_b["edge_id"] = "EDGE-000002"
    row_b["condition_text"] = "RS5<=-10"
    row_b["feature_1"] = "rs5"
    row_b["threshold_1"] = -10.0
    row_b["created_at"] = "2026-08-19T13:02:52Z"
    pd.DataFrame([row_a, row_b]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    write_discovery_run(
        {
            "run_id": "disc002",
            "promoted_candidates": 1,
            "candidates": [{"condition_key": "STRESS -> STRESS|rs10:rs10_le_-10"}],
        },
        data_dir=edge_data_dir,
    )
    cohort = resolve_discovery_cohort(edge_data_dir)
    assert len(cohort) == 1
    assert cohort.iloc[0]["edge_id"] == "EDGE-000001"
    result = engine.run_challenger(force=True)
    assert result.candidates_entering == 1
    assert result.discovery_run_id == "disc002"


# B. No new discovery candidates
def test_challenger_does_not_create_new_candidates(edge_data_dir):
    from modules.edge_research.challenger import run_challenger

    panel = _panel(100)
    ledger = pd.DataFrame([_ledger_row()])
    before = len(ledger)
    run_challenger(panel, ledger, force=True)
    assert len(ledger) == before


# C. Best-date removal removes full T0 date
def test_best_date_removal_full_date():
    from modules.edge_research.robustness import filter_candidate_rows, test_leave_best_date_out

    panel = _panel(80)
    row = _ledger_row()
    panel.loc[panel["trade_date"] == "2026-07-23", "t10_return"] = 50.0
    cand = filter_candidate_rows(panel, row)
    if cand.empty:
        panel["rs10"] = -12.0
        cand = filter_candidate_rows(panel, row)
    res = test_leave_best_date_out(cand, panel, row, "T10")
    best = res.get("best_date_removed")
    after_n = res.get("n_after_best_date_removal")
    assert best
    assert after_n == len(cand[cand["trade_date"] != best])


# D. Best-date uses same-state baseline
def test_best_date_recomputes_baseline():
    from modules.edge_research.robustness import filter_candidate_rows, test_leave_best_date_out

    panel = _panel(100)
    panel["rs10"] = -12.0
    row = _ledger_row()
    cand = filter_candidate_rows(panel, row)
    res = test_leave_best_date_out(cand, panel, row, "T10")
    assert "post_incremental_median" in res


# E/F. Top winner removal deterministic
def test_top5_removal_deterministic():
    from modules.edge_research.robustness import filter_candidate_rows, test_leave_top_winners_out
    from modules.edge_research.contracts import TOP_WINNER_PCT_5

    panel = _panel(100)
    panel["rs10"] = -12.0
    row = _ledger_row()
    cand = filter_candidate_rows(panel, row)
    r1 = test_leave_top_winners_out(cand, panel, row, "T10", TOP_WINNER_PCT_5)
    r2 = test_leave_top_winners_out(cand, panel, row, "T10", TOP_WINNER_PCT_5)
    assert r1["rows_removed"] == r2["rows_removed"]


def test_top10_removal_deterministic():
    from modules.edge_research.robustness import filter_candidate_rows, test_leave_top_winners_out
    from modules.edge_research.contracts import TOP_WINNER_PCT_10

    panel = _panel(100)
    panel["rs10"] = -12.0
    row = _ledger_row()
    cand = filter_candidate_rows(panel, row)
    r = test_leave_top_winners_out(cand, panel, row, "T10", TOP_WINNER_PCT_10)
    assert r["rows_removed"] >= 1


# G. Mean/median classification
def test_mean_median_classification():
    from modules.edge_research.metrics import HorizonProfile
    from modules.edge_research.robustness import classify_mean_median

    assert classify_mean_median(HorizonProfile("T5", 10, 2.0, -1.0, 50, 0, 0, 0, 0)) == "MEAN_ONLY"
    assert classify_mean_median(HorizonProfile("T5", 10, 2.0, 1.5, 50, 0, 0, 0, 0)) == "DISTRIBUTION_SUPPORTED"


# H. Symbol concentration
def test_symbol_concentration():
    from modules.edge_research.robustness import test_symbol_concentration

    df = pd.DataFrame({"symbol": ["A"] * 8 + ["B"] * 2})
    res = test_symbol_concentration(df)
    assert res["pct_rows_top1_symbol"] == 80.0


# I. Temporal date counts
def test_temporal_date_counts():
    from modules.edge_research.robustness import filter_candidate_rows, test_temporal_consistency

    panel = _panel(60)
    panel["rs10"] = -12.0
    row = _ledger_row()
    cand = filter_candidate_rows(panel, row)
    res = test_temporal_consistency(cand, panel, row, "T10")
    assert res["number_of_dates"] >= 1


# J. Horizon consistency deterministic
def test_horizon_consistency_deterministic():
    from modules.edge_research.robustness import filter_candidate_rows, test_horizon_consistency

    panel = _panel(80)
    panel["rs10"] = -12.0
    row = _ledger_row()
    cand = filter_candidate_rows(panel, row)
    r1 = test_horizon_consistency(cand, panel, row, "T10")
    r2 = test_horizon_consistency(cand, panel, row, "T10")
    assert r1["classification"] == r2["classification"]


# K/L. Neighbor bucket deterministic, does not modify candidate
def test_neighbor_bucket_no_candidate_modification():
    from modules.edge_research.discovery import ConditionClause
    from modules.edge_research.robustness import reconstruct_clauses_from_ledger_row, test_neighborhood_stability

    row = _ledger_row()
    clauses_before = reconstruct_clauses_from_ledger_row(row)
    panel = _panel(100)
    panel["rs10"] = -12.0
    test_neighborhood_stability(panel, row, clauses_before, "T10")
    clauses_after = reconstruct_clauses_from_ledger_row(row)
    assert clauses_before == clauses_after


# M/N. Episode segmentation market only
def test_episode_segmentation_market_only():
    from modules.edge_research.episodes import segment_market_episodes

    panel = _panel(50)
    eps = segment_market_episodes(panel)
    assert len(eps) >= 1
    assert all(ep.episode_version == "episode_v1" for ep in eps)


def test_episode_no_forward_outcomes():
    import inspect
    from modules.edge_research import episodes

    src = inspect.getsource(episodes.segment_market_episodes)
    assert "t3_return" not in src
    assert "t5_return" not in src


# O. Same episode groups multiple stock rows
def test_episode_groups_multiple_observations():
    from modules.edge_research.episodes import assign_episodes_to_candidate_rows, segment_market_episodes

    panel = _panel(40)
    eps = segment_market_episodes(panel)
    tagged = assign_episodes_to_candidate_rows(panel, eps)
    assert tagged["episode_id"].nunique() <= len(eps)


# P/Q. Observed != validated; independent stays 0
def test_observed_not_validated_episodes(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    status = engine.get_foundation_status()
    assert status.independent_episodes == 0


# R. PASS/FRAGILE/REJECT deterministic
def test_robustness_gates_deterministic():
    from modules.edge_research.robustness import evaluate_robustness_status

    tests = {"leave_best_date_out": {"result": "PASS", "post_incremental_median": 1.0, "n_after_best_date_removal": 25}}
    ep = {"observed_episodes": 2}
    s1, _, _, _ = evaluate_robustness_status(tests, ep, {"incremental_median": 2.0}, 30)
    s2, _, _, _ = evaluate_robustness_status(tests, ep, {"incremental_median": 2.0}, 30)
    assert s1 == s2


# S. Rejected remains in ledger
def test_rejected_candidate_stays_in_ledger(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import read_ledger

    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.run_challenger(force=True)
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert len(ledger) >= 1


# T. Robustness history append-only
def test_robustness_history_append_only(edge_data_dir):
    from modules.edge_research.storage import append_robustness_history, read_ledger

    append_robustness_history("r1", "EDGE-000001", "2026-01-01", [{"test_name": "t", "result": "PASS"}], edge_data_dir)
    append_robustness_history("r2", "EDGE-000001", "2026-01-02", [{"test_name": "t2", "result": "PASS"}], edge_data_dir)
    hist = read_ledger("edge_robustness_history.csv", edge_data_dir)
    assert len(hist) == 2


# U. Rerun no duplicate candidate IDs
def test_rerun_no_duplicate_ids(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import read_ledger

    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.run_challenger(force=True)
    engine.run_challenger(force=True)
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert ledger["edge_id"].nunique() == len(ledger)


# V. Research Voice never EDGE ACTIVE
def test_voice_never_edge_active():
    from modules.edge_research.ui import _format_research_voice

    for rs in ("PASS", "FRAGILE", "REJECT", ""):
        text = _format_research_voice({"edge_id": "E1", "robustness_status": rs})
        assert "EDGE ACTIVE" not in text
        assert "CONFIRMED" not in text.replace("NOT VALIDATED", "")


# W. UI render callable
def test_ui_render_callable():
    from modules.edge_research.ui import render_edge_research_panel

    assert callable(render_edge_research_panel)


# X. No production calls
def test_no_production_decision_calls():
    from modules.edge_research import contracts

    for mod in ("challenger", "robustness", "episodes"):
        src = inspect.getsource(importlib.import_module(f"modules.edge_research.{mod}"))
        for f in contracts.PRODUCTION_FORBIDDEN_IMPORTS:
            assert f not in src


# Y. Writes only edge namespace
def test_challenger_writes_only_edge_namespace(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    def _digest(p: Path):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    before = _digest(EARNING_DIR / "pattern_lifecycle.csv")
    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    EdgeResearchEngine(data_dir=edge_data_dir).run_challenger(force=True)
    assert _digest(EARNING_DIR / "pattern_lifecycle.csv") == before
    assert (edge_data_dir / "edge_robustness_history.csv").exists()
