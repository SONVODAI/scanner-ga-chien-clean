"""Regression tests for Edge Research UI button gating."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.ui import compute_edge_research_button_state


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    return d


def _ledger_row(edge_id: str = "EDGE-000001") -> dict:
    return {
        "edge_id": edge_id,
        "created_at": "2026-08-19T13:02:52Z",
        "discovery_run_id": "disc001",
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
        "discovery_start_date": "2026-07-23",
        "discovery_end_date": "2026-08-14",
    }


def test_case1_no_cohort_valid_history_discovery_enabled_challenger_disabled(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    status = engine.get_foundation_status()

    ui_state = compute_edge_research_button_state(
        coverage_start=status.coverage_start,
        coverage_end=status.coverage_end,
        observation_count=status.observation_count,
        has_valid_cohort=engine.has_valid_discovery_cohort(),
    )

    assert status.observation_count > 0
    assert engine.has_valid_discovery_cohort() is False
    assert ui_state["can_run_discovery"] is True
    assert ui_state["can_run_challenger"] is False


def test_case2_valid_cohort_both_enabled(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import write_discovery_run

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    write_discovery_run(
        {
            "run_id": "disc001",
            "promoted_candidates": 1,
            "candidates": [{"condition_key": "STRESS -> STRESS|rs10:rs10_le_-10"}],
        },
        data_dir=edge_data_dir,
    )

    status = engine.get_foundation_status()
    ui_state = compute_edge_research_button_state(
        coverage_start=status.coverage_start,
        coverage_end=status.coverage_end,
        observation_count=status.observation_count,
        has_valid_cohort=engine.has_valid_discovery_cohort(),
    )

    assert engine.has_valid_discovery_cohort() is True
    assert ui_state["can_run_discovery"] is True
    assert ui_state["can_run_challenger"] is True


def test_case3_insufficient_history_discovery_disabled(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()

    ui_state = compute_edge_research_button_state(
        coverage_start=None,
        coverage_end=None,
        observation_count=0,
        has_valid_cohort=engine.has_valid_discovery_cohort(),
    )

    assert ui_state["can_run_discovery"] is False
    assert ui_state["can_run_challenger"] is False


def test_execution_in_progress_disables_both():
    ui_state = compute_edge_research_button_state(
        coverage_start="2026-07-23",
        coverage_end="2026-08-14",
        observation_count=100,
        has_valid_cohort=True,
        execution_in_progress=True,
    )
    assert ui_state["can_run_discovery"] is False
    assert ui_state["can_run_challenger"] is False


def test_has_valid_cohort_requires_discovery_run_not_ledger_only(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)

    assert engine.has_discovery_candidates() is True
    assert engine.has_valid_discovery_cohort() is False
