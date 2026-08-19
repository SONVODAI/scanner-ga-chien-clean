"""Regression tests for Edge Research UI button gating and busy lifecycle."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.ui import (
    EDGE_UI_DIAG_BUILD,
    challenger_disabled_caption,
    compute_edge_research_button_state,
    discovery_disabled_caption,
    execution_in_progress_from_session,
    format_edge_ui_diagnostic_line,
    normalize_edge_research_busy_session,
    recover_legacy_edge_research_busy,
    run_with_edge_research_busy_guard,
)


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


def _ui_state(
    *,
    coverage_start="2026-07-23",
    coverage_end="2026-08-14",
    observation_count=2982,
    has_valid_cohort=False,
    session_state=None,
):
    session_state = session_state or {}
    return compute_edge_research_button_state(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        observation_count=observation_count,
        has_valid_cohort=has_valid_cohort,
        execution_in_progress=execution_in_progress_from_session(session_state),
    )


# CASE 1 — fresh session + valid coverage + no cohort + busy absent
def test_case1_no_cohort_valid_history_discovery_enabled_challenger_disabled(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    status = engine.get_foundation_status()
    session_state: dict = {}

    ui_state = _ui_state(
        coverage_start=status.coverage_start,
        coverage_end=status.coverage_end,
        observation_count=status.observation_count,
        has_valid_cohort=engine.has_valid_discovery_cohort(),
        session_state=session_state,
    )

    assert status.observation_count > 0
    assert engine.has_valid_discovery_cohort() is False
    assert "edge_research_busy" not in session_state
    assert ui_state["can_run_discovery"] is True
    assert ui_state["can_run_challenger"] is False


# CASE 2 — busy=False
def test_case2_busy_false_discovery_enabled():
    ui_state = _ui_state(session_state={"edge_research_busy": False})
    assert ui_state["can_run_discovery"] is True


# CASE 3 — busy="False" must NOT be treated as busy
def test_case3_string_false_not_treated_as_busy():
    session_state = {"edge_research_busy": "False"}
    assert execution_in_progress_from_session(session_state) is False
    ui_state = _ui_state(session_state=session_state)
    assert ui_state["can_run_discovery"] is True
    normalize_edge_research_busy_session(session_state)
    assert session_state["edge_research_busy"] is False


# CASE 4 — busy=True disables both during legitimate execution
def test_case4_busy_true_disables_both():
    ui_state = _ui_state(
        has_valid_cohort=True,
        session_state={"edge_research_busy": True},
    )
    assert ui_state["can_run_discovery"] is False
    assert ui_state["can_run_challenger"] is False
    assert discovery_disabled_caption(ui_state) == "Research run in progress..."
    assert (
        challenger_disabled_caption(ui_state, has_valid_cohort=True)
        == "Research run in progress..."
    )


# CASE 5 — discovery raises => busy cleared
def test_case5_discovery_raises_clears_busy():
    session_state: dict = {}

    def _boom():
        raise RuntimeError("discovery failed")

    with pytest.raises(RuntimeError, match="discovery failed"):
        run_with_edge_research_busy_guard(session_state, _boom)

    assert session_state["edge_research_busy"] is False
    assert execution_in_progress_from_session(session_state) is False


# CASE 6 — challenger raises => busy cleared
def test_case6_challenger_raises_clears_busy():
    session_state: dict = {}

    def _boom():
        raise ValueError("challenger failed")

    with pytest.raises(ValueError, match="challenger failed"):
        run_with_edge_research_busy_guard(session_state, _boom)

    assert session_state["edge_research_busy"] is False


# CASE 7 — successful discovery => busy returns False
def test_case7_successful_discovery_clears_busy():
    session_state: dict = {}
    result = run_with_edge_research_busy_guard(session_state, lambda: {"promoted_candidates": 3})
    assert result["promoted_candidates"] == 3
    assert session_state["edge_research_busy"] is False


# CASE 8 — successful challenger => busy returns False
def test_case8_successful_challenger_clears_busy():
    session_state: dict = {}

    class _Result:
        run_id = "abc"
        robustness_pass = 1
        robustness_fragile = 0
        robustness_reject = 0

    result = run_with_edge_research_busy_guard(session_state, lambda: _Result())
    assert result.run_id == "abc"
    assert session_state["edge_research_busy"] is False


def test_valid_cohort_both_enabled(edge_data_dir):
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
    ui_state = _ui_state(
        coverage_start=status.coverage_start,
        coverage_end=status.coverage_end,
        observation_count=status.observation_count,
        has_valid_cohort=engine.has_valid_discovery_cohort(),
    )

    assert engine.has_valid_discovery_cohort() is True
    assert ui_state["can_run_discovery"] is True
    assert ui_state["can_run_challenger"] is True


def test_insufficient_history_discovery_disabled(edge_data_dir):
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
    assert discovery_disabled_caption(ui_state) == "Historical research coverage required."
    assert (
        challenger_disabled_caption(ui_state, has_valid_cohort=False) == "Run discovery first."
    )


def test_has_valid_cohort_requires_discovery_run_not_ledger_only(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    pd.DataFrame([_ledger_row()]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)

    assert engine.has_discovery_candidates() is True
    assert engine.has_valid_discovery_cohort() is False


def test_legacy_busy_recovery_one_time_only():
    session_state = {"edge_research_busy": True}

    recover_legacy_edge_research_busy(session_state)
    assert session_state["edge_research_busy"] is False
    assert session_state["_edge_research_busy_strict_v"] == 1

    session_state["edge_research_busy"] = True
    recover_legacy_edge_research_busy(session_state)
    assert session_state["edge_research_busy"] is True


def test_challenger_caption_without_cohort():
    ui_state = _ui_state(has_valid_cohort=False)
    assert ui_state["can_run_challenger"] is False
    assert (
        challenger_disabled_caption(ui_state, has_valid_cohort=False) == "Run discovery first."
    )


def _capture_pre_button_gating(
    *,
    session_state: dict,
    coverage_start,
    coverage_end,
    observation_count: int,
    has_valid_cohort: bool,
):
    """Mirror render_edge_research_panel values immediately before st.button."""
    recover_legacy_edge_research_busy(session_state)
    execution_in_progress = execution_in_progress_from_session(session_state)
    ui_state = compute_edge_research_button_state(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        observation_count=observation_count,
        has_valid_cohort=has_valid_cohort,
        execution_in_progress=execution_in_progress,
    )
    if "edge_research_busy" in session_state:
        raw_busy = session_state["edge_research_busy"]
        raw_busy_type = type(raw_busy).__name__
    else:
        raw_busy = "<MISSING>"
        raw_busy_type = "missing"
    strict_v = session_state.get("_edge_research_busy_strict_v", "<MISSING>")
    discovery_caption = discovery_disabled_caption(ui_state)
    challenger_caption = challenger_disabled_caption(
        ui_state,
        has_valid_cohort=has_valid_cohort,
    )
    discovery_disabled = not ui_state["can_run_discovery"]
    challenger_disabled = not ui_state["can_run_challenger"]
    diagnostic_line = format_edge_ui_diagnostic_line(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        observation_count=observation_count,
        raw_busy=raw_busy,
        raw_busy_type=raw_busy_type,
        strict_v=strict_v,
        execution_in_progress=execution_in_progress,
        has_valid_cohort=has_valid_cohort,
        ui_state=ui_state,
        discovery_caption=discovery_caption,
        challenger_caption=challenger_caption,
    )
    return {
        "ui_state": ui_state,
        "discovery_disabled": discovery_disabled,
        "challenger_disabled": challenger_disabled,
        "diagnostic_line": diagnostic_line,
    }


def test_edge_ui_diagnostic_matches_button_gating_state(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    status = engine.get_foundation_status()
    has_valid_cohort = engine.has_valid_discovery_cohort()

    snapshot = _capture_pre_button_gating(
        session_state={},
        coverage_start=status.coverage_start,
        coverage_end=status.coverage_end,
        observation_count=status.observation_count,
        has_valid_cohort=has_valid_cohort,
    )
    line = snapshot["diagnostic_line"]
    ui_state = snapshot["ui_state"]

    assert EDGE_UI_DIAG_BUILD == "EDGE_UI_DIAG_V1"
    assert f"build={EDGE_UI_DIAG_BUILD}" in line
    assert f"discovery_disabled={snapshot['discovery_disabled']}" in line
    assert f"challenger_disabled={snapshot['challenger_disabled']}" in line
    assert snapshot["discovery_disabled"] is (not ui_state["can_run_discovery"])
    assert snapshot["challenger_disabled"] is (not ui_state["can_run_challenger"])
    assert f"can_run_discovery={ui_state['can_run_discovery']}" in line
    assert f"can_run_challenger={ui_state['can_run_challenger']}" in line
    assert f"discovery_caption={discovery_disabled_caption(ui_state)!r}" in line
    assert (
        f"challenger_caption="
        f"{challenger_disabled_caption(ui_state, has_valid_cohort=has_valid_cohort)!r}"
        in line
    )


def test_edge_ui_diagnostic_reflects_same_busy_gating_as_buttons():
    session_state = {"edge_research_busy": "False"}
    snapshot = _capture_pre_button_gating(
        session_state=session_state,
        coverage_start="2026-07-23",
        coverage_end="2026-08-14",
        observation_count=2982,
        has_valid_cohort=False,
    )

    assert snapshot["discovery_disabled"] is False
    assert "raw_busy=False" in snapshot["diagnostic_line"]
    assert "execution_in_progress=False" in snapshot["diagnostic_line"]
