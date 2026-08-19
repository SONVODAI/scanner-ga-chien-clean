"""Safety and foundation tests for Edge Research Engine V1 (Phase 0/1)."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EARNING_DIR = REPO_ROOT / "data" / "earning_learning"


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    return d


@pytest.fixture
def earning_digests():
    files = [
        "pattern_lifecycle.csv",
        "verified_decisions.csv",
        "observations.csv",
        "pattern_knowledge.csv",
        "continuation_knowledge.csv",
    ]
    return {f: _digest(EARNING_DIR / f) for f in files}


# A. Independent import
def test_edge_research_imports_independently():
    pkg = importlib.import_module("modules.edge_research")
    assert pkg.ENGINE_VERSION
    assert pkg.EdgeResearchEngine is not None


# B. Storage writes only to edge_research
def test_storage_writes_only_edge_namespace(edge_data_dir):
    from modules.edge_research.storage import ensure_storage, write_status

    root = ensure_storage(edge_data_dir)
    assert root == edge_data_dir
    assert (edge_data_dir / "edge_hypothesis_ledger.csv").exists()
    assert (edge_data_dir / "engine_status.json").exists()
    write_status({"last_research_event": "NONE"}, data_dir=edge_data_dir)
    assert not (EARNING_DIR / "engine_status.json").exists()


# C. Learning files not mutated
def test_learning_files_not_mutated_by_engine_run(edge_data_dir, earning_digests):
    from modules.edge_research.adapters import earning_learning_digests
    from modules.edge_research.engine import EdgeResearchEngine

    before = earning_learning_digests()
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    engine.get_foundation_status()
    engine.build_panel(start="2026-07-23", end="2026-07-30")
    after = earning_learning_digests()
    assert before == after


# D. No production decision functions called
def test_engine_does_not_call_production_decision_functions():
    from modules.edge_research import contracts, engine

    engine_src = inspect.getsource(engine)
    contracts_src = inspect.getsource(contracts)
    for forbidden in contracts.PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in engine_src
    adapter_src = inspect.getsource(importlib.import_module("modules.edge_research.adapters"))
    for forbidden in contracts.PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in adapter_src


# E. T0 features do not use forward labels in adapter
def test_t0_features_do_not_use_lifecycle_forward_columns(edge_data_dir):
    from modules.edge_research.adapters import build_research_panel

    lifecycle = pd.DataFrame(
        {
            "trade_date": ["2026-07-23", "2026-07-24"],
            "symbol": ["AAA", "AAA"],
            "price": [100.0, 200.0],
            "rs5": [1.0, 2.0],
            "rs10": [0.5, 1.5],
            "rsi14": [40.0, 45.0],
            "t3_return_pct": [999.0, 888.0],
            "t5_return_pct": [777.0, 666.0],
            "t10_return_pct": [555.0, 444.0],
        }
    )
    panel = build_research_panel(
        lifecycle=lifecycle,
        start="2026-07-23",
        end="2026-07-24",
    )
    assert panel["t3_return"].isna().all()
    assert panel["outcome_source"].eq("unavailable").all()
    assert (panel["rs5"] == lifecycle["rs5"]).all()


# F. Trading-session T3/T5/T10 semantics
def test_trading_session_outcomes_not_observation_rows():
    from modules.edge_research.outcomes import compute_trading_session_outcomes

    # 10 trading sessions; T0 at index 0; T3 should be index 3 (4th session)
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    ohlcv = pd.DataFrame({"date": dates, "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]})
    res = compute_trading_session_outcomes(ohlcv, pd.Timestamp("2026-06-01"), horizons=(3, 5, 10))
    assert res["outcome_source"] == "ohlcv_trading_sessions"
    assert res["t3_return"] == pytest.approx(3.0)
    assert res["t5_return"] == pytest.approx(5.0)
    assert res["t10_return"] is None or pd.isna(res["t10_return"])


def test_trading_session_differs_from_observation_row_semantics():
    from modules.edge_research.outcomes import compute_trading_session_outcomes

    dates = pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-10"])
    ohlcv = pd.DataFrame({"date": dates, "close": [100, 110, 120, 200]})
    res = compute_trading_session_outcomes(ohlcv, pd.Timestamp("2026-06-01"), horizons=(3,))
    # Observation-row +3 would hit 2026-06-03 close 120 (+20%)
    # Trading-session +3 would need 4th session (2026-06-10) close 200 (+100%)
    assert res["t3_return"] == pytest.approx(100.0)


# G. Multiple market snapshots deterministic / ambiguous
def test_multiple_market_snapshots_ambiguous():
    from modules.edge_research.market_state import RawMarketSnapshot, select_canonical_market_snapshot

    snaps = [
        RawMarketSnapshot("2026-07-23", "09:00:00", 0.6, 0.0),
        RawMarketSnapshot("2026-07-23", "18:00:00", 1.1, 0.0),
    ]
    canon = select_canonical_market_snapshot(snaps)
    assert canon.ambiguous is True
    assert canon.market_real == 1.1
    assert canon.time == "18:00:00"


def test_market_state_unknown_when_ambiguous():
    from modules.edge_research.market_state import derive_research_market_state

    assert derive_research_market_state("LOW", "IMPROVING", ambiguous=True) == "UNKNOWN"


# H. Research state separate from production
def test_research_fields_not_in_production_regime():
    from modules.edge_research.contracts import RESEARCH_OBSERVATION_COLUMNS

    assert "research_market_state" in RESEARCH_OBSERVATION_COLUMNS
    assert "elite_regime" not in RESEARCH_OBSERVATION_COLUMNS


# I. Empty memory — no fake edges
def test_empty_hypothesis_ledger(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import count_ledger_rows

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    status = engine.get_foundation_status()
    assert status.hypotheses == 0
    assert status.validated_edges == 0
    assert count_ledger_rows("edge_hypothesis_ledger.csv", edge_data_dir) == 0


# J. UI renders zero-edge state (smoke — no streamlit runtime)
def test_ui_render_callable():
    from modules.edge_research.ui import render_edge_research_panel

    assert callable(render_edge_research_panel)


# RS definitions
def test_rs_definitions_match_mrboot():
    from modules.edge_research.indicators import calc_rs10, calc_rs5

    close = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110], dtype=float)
    rs5 = calc_rs5(close)
    rs10 = calc_rs10(close)
    assert rs5.iloc[-1] == pytest.approx((110 / 105 - 1) * 100)
    assert rs10.iloc[-1] == pytest.approx((110 / 100 - 1) * 100)


# Anti-leakage: market enrichment uses only <= T0
def test_market_enrichment_no_future_dates():
    from modules.edge_research.market_state import enrich_date_with_market_research

    ms = pd.DataFrame(
        {
            "date": ["2026-07-22", "2026-07-23"],
            "market_real": [0.6, 1.1],
            "market_forecast": [0.0, 0.0],
            "breadth_score": [30, 40],
            "ambiguous": [False, True],
        }
    )
    state_hist: dict = {}
    fields = enrich_date_with_market_research(
        "2026-07-23",
        ms,
        pd.DataFrame({"rs10": [-6], "rs5": [1], "rsi14": [38]}),
        state_hist,
    )
    assert fields["research_market_state"] == "UNKNOWN"
    assert fields["mr_t_minus_1"] == pytest.approx(0.6)
