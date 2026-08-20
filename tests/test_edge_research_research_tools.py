"""Tests for PATCH 3B deterministic research toolbox."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.contracts import DATE_CONCENTRATION_SEVERE, SYMBOL_CONCENTRATION_SEVERE
from modules.edge_research.discovery import ConditionClause, build_clauses_for_feature
from modules.edge_research.feature_builder import build_t0_feature_matrix
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    StructuredResearchObservation,
    compute_experiment_content_hash,
    compute_result_hash,
)
from modules.edge_research.research_tools import (
    OBS_DATE_BROAD,
    OBS_DATE_CONCENTRATED,
    OBS_EPISODE_INSUFFICIENT,
    OBS_EXTREME_WINNER_SENSITIVE,
    OBS_HORIZON_HETEROGENEOUS,
    OBS_MARKET_HETEROGENEOUS,
    OBS_NEIGHBORHOOD_STABLE,
    OBS_NEIGHBORHOOD_UNSTABLE,
    OBS_NO_CLEAR_DIFFERENCE,
    OBS_NO_VARIATION,
    OBS_SYMBOL_BROAD,
    OBS_SYMBOL_CONCENTRATED,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    PartitionGroupCompareTool,
    ResearchToolExecutionError,
    ToolRegistry,
    ToolStatus,
    apply_research_cutoff,
    build_default_tool_registry,
    compute_tool_input_hash,
    execute_research_experiment,
)
from modules.edge_research.storage import write_research_graph, read_research_graph

CUTOFF = "2026-08-20"
SCOPE = {}


def _target_dates(t0: str, horizon_days: int) -> dict:
    t0_ts = pd.Timestamp(t0)
    return {
        "t3_target_date": (t0_ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        "t5_target_date": (t0_ts + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        "t10_target_date": (t0_ts + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    }


def _row(
    *,
    trade_date: str,
    symbol: str,
    t5_return: float,
    t3_return: float | None = None,
    t10_return: float | None = None,
    group: str = "A",
    rs10: float = 0.0,
    market_state: str = "EARLY_RECOVERY",
    market_transition: str = "STRESS -> EARLY_RECOVERY",
    mature: bool = True,
) -> dict:
    t3 = t3_return if t3_return is not None else t5_return
    t10 = t10_return if t10_return is not None else t5_return
    targets = _target_dates(trade_date, 10)
    if not mature:
        # Target dates beyond cutoff so returns should be excluded
        targets = {
            "t3_target_date": "2026-09-01",
            "t5_target_date": "2026-09-05",
            "t10_target_date": "2026-09-10",
        }
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "partition_group": group,
        "rs5": rs10,
        "rs10": rs10,
        "rsi14": 35.0,
        "rs_spread": 0.0,
        "research_market_state": market_state,
        "research_market_transition": market_transition,
        "t3_return": t3,
        "t5_return": t5_return,
        "t10_return": t10,
        **targets,
    }


def _panel(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _broad_panel(n_dates: int = 5, per_date: int = 2) -> pd.DataFrame:
    rows = []
    for d in range(n_dates):
        for s in range(per_date):
            rows.append(
                _row(
                    trade_date=f"2026-08-{d + 1:02d}",
                    symbol=f"S{s:02d}",
                    t5_return=1.0 + 0.1 * s,
                    group="A" if s == 0 else "B",
                )
            )
    return _panel(rows)


def _execute(tool_name: str, panel: pd.DataFrame, inputs: dict, scope: dict | None = None):
    registry = build_default_tool_registry()
    tool = registry.get(tool_name)
    return tool.execute(
        panel,
        inputs=inputs,
        research_scope=scope or SCOPE,
        data_cutoff_date=CUTOFF,
    )


# --- TOOL CONTRACT ---


def test_registry_lists_tools_deterministically():
    reg = build_default_tool_registry()
    names1 = [(m.tool_name, m.tool_version) for m in reg.list_tools()]
    names2 = [(m.tool_name, m.tool_version) for m in reg.list_tools()]
    assert names1 == names2
    assert len(names1) == 9


def test_unknown_tool_rejected():
    reg = build_default_tool_registry()
    with pytest.raises(KeyError, match="Unknown research tool"):
        reg.get("nonexistent_tool")


def test_conflicting_duplicate_registration_rejected():
    reg = ToolRegistry()
    tool = PartitionGroupCompareTool()
    reg.register(tool)
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        reg.register(tool)


def test_tool_metadata_serializable():
    reg = build_default_tool_registry()
    payload = reg.metadata_dicts()
    text = json.dumps(payload, sort_keys=True)
    reloaded = json.loads(text)
    assert len(reloaded) == 9
    assert all("tool_name" in m and "input_schema" in m for m in reloaded)


def test_common_result_envelope_deterministic():
    panel = _broad_panel()
    r1 = _execute("date_decomposition", panel, {"horizon": "T5"})
    r2 = _execute("date_decomposition", panel, {"horizon": "T5"})
    assert r1.input_hash == r2.input_hash
    assert r1.to_dict() == r2.to_dict()


# --- PARTITION ---


def test_partition_explicit_groups_returns_correct_statistics():
    panel = _panel(
        [
            _row(trade_date="2026-08-01", symbol="S0", t5_return=1.0, group="A"),
            _row(trade_date="2026-08-02", symbol="S1", t5_return=1.0, group="A"),
            _row(trade_date="2026-08-03", symbol="S2", t5_return=5.0, group="B"),
            _row(trade_date="2026-08-04", symbol="S3", t5_return=5.0, group="B"),
        ]
    )
    result = _execute(
        "partition_group_compare",
        panel,
        {"partition_column": "partition_group", "partition_type": "categorical", "horizon": "T5"},
    )
    assert result.status == ToolStatus.OK
    assert result.groups["A"]["n"] == 2
    assert result.groups["A"]["median"] == pytest.approx(1.0)
    assert result.groups["B"]["median"] == pytest.approx(5.0)


def test_partition_numeric_explicit_bins():
    panel = _panel(
        [
            _row(trade_date="2026-08-01", symbol="S0", t5_return=1.0, rs10=-8.0),
            _row(trade_date="2026-08-02", symbol="S1", t5_return=1.0, rs10=-7.0),
            _row(trade_date="2026-08-03", symbol="S2", t5_return=4.0, rs10=2.0),
            _row(trade_date="2026-08-04", symbol="S3", t5_return=4.0, rs10=3.0),
        ]
    )
    bins = [
        {"lo": None, "hi": -5.0, "label": "low"},
        {"lo": -5.0, "hi": None, "label": "high"},
    ]
    result = _execute(
        "partition_group_compare",
        panel,
        {
            "partition_column": "rs10",
            "partition_type": "numeric_bins",
            "bins": bins,
            "horizon": "T5",
        },
    )
    assert result.groups["low"]["median"] == pytest.approx(1.0)
    assert result.groups["high"]["median"] == pytest.approx(4.0)


def test_partition_does_not_optimize_boundaries():
    panel = _broad_panel()
    bins_a = [{"lo": None, "hi": 0.0, "label": "neg"}, {"lo": 0.0, "hi": None, "label": "pos"}]
    bins_b = [{"lo": None, "hi": -5.0, "label": "neg"}, {"lo": -5.0, "hi": None, "label": "pos"}]
    r_a = _execute(
        "partition_group_compare",
        panel,
        {"partition_column": "rs10", "partition_type": "numeric_bins", "bins": bins_a, "horizon": "T5"},
    )
    r_b = _execute(
        "partition_group_compare",
        panel,
        {"partition_column": "rs10", "partition_type": "numeric_bins", "bins": bins_b, "horizon": "T5"},
    )
    assert r_a.input_hash != r_b.input_hash


# --- DATE ---


def test_date_broad_distribution():
    panel = _broad_panel(n_dates=5, per_date=2)
    result = _execute("date_decomposition", panel, {"horizon": "T5"})
    codes = [o.code for o in result.structured_observations]
    assert OBS_DATE_BROAD in codes
    assert result.metrics["unique_t0_dates"] == 5


def test_date_single_date_concentration():
    rows = [
        _row(trade_date="2026-08-01", symbol=f"S{i}", t5_return=1.0 + i * 0.1)
        for i in range(10)
    ]
    result = _execute("date_decomposition", _panel(rows), {"horizon": "T5"})
    assert result.metrics["largest_date_share"] == pytest.approx(1.0)
    codes = [o.code for o in result.structured_observations]
    assert OBS_DATE_CONCENTRATED in codes
    assert result.metrics["largest_date_share"] >= DATE_CONCENTRATION_SEVERE


# --- SYMBOL ---


def test_symbol_broad_distribution():
    rows = []
    for i in range(5):
        rows.append(
            _row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=1.0)
        )
    result = _execute("symbol_decomposition", _panel(rows), {"horizon": "T5"})
    codes = [o.code for o in result.structured_observations]
    assert OBS_SYMBOL_BROAD in codes


def test_symbol_single_symbol_concentration():
    rows = [
        _row(trade_date=f"2026-08-{i+1:02d}", symbol="DOM", t5_return=1.0)
        for i in range(10)
    ]
    result = _execute("symbol_decomposition", _panel(rows), {"horizon": "T5"})
    assert result.metrics["largest_symbol_share"] == pytest.approx(1.0)
    codes = [o.code for o in result.structured_observations]
    assert OBS_SYMBOL_CONCENTRATED in codes
    assert result.metrics["largest_symbol_share"] >= SYMBOL_CONCENTRATION_SEVERE


# --- EPISODE ---


def test_episode_multi_episode_result():
    rows = []
    transitions = ["A -> B", "A -> B", "C -> D", "C -> D", "C -> D"]
    for i, trans in enumerate(transitions):
        rows.append(
            _row(
                trade_date=f"2026-08-{i+1:02d}",
                symbol=f"S{i}",
                t5_return=2.0 if i < 2 else -1.0,
                market_transition=trans,
            )
        )
    result = _execute("episode_decomposition", _panel(rows), {"horizon": "T5"})
    assert "observed_episodes" in result.metrics or "episode_consistency" in result.metrics


def test_episode_single_episode_limitation():
    rows = [
        _row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=1.0)
        for i in range(3)
    ]
    result = _execute("episode_decomposition", _panel(rows), {"horizon": "T5"})
    codes = [o.code for o in result.structured_observations]
    assert OBS_EPISODE_INSUFFICIENT in codes or result.status == ToolStatus.INSUFFICIENT_DATA


# --- MARKET ---


def test_market_conditioning_returns_requested_states():
    rows = []
    for i in range(6):
        state = "EARLY_RECOVERY" if i < 3 else "LATE_CYCLE"
        rows.append(
            _row(
                trade_date=f"2026-08-{i+1:02d}",
                symbol=f"S{i}",
                t5_return=2.0 if state == "EARLY_RECOVERY" else -1.0,
                market_state=state,
            )
        )
    result = _execute(
        "market_conditioning",
        _panel(rows),
        {
            "horizon": "T5",
            "partition_by": "research_market_state",
            "states_or_transitions": ["EARLY_RECOVERY", "LATE_CYCLE"],
        },
    )
    assert "EARLY_RECOVERY" in result.groups
    assert "LATE_CYCLE" in result.groups
    assert len(result.groups) == 2


def test_market_conditioning_does_not_select_best_state_only():
    rows = []
    for i in range(6):
        state = "EARLY_RECOVERY" if i < 3 else "LATE_CYCLE"
        rows.append(
            _row(
                trade_date=f"2026-08-{i+1:02d}",
                symbol=f"S{i}",
                t5_return=5.0 if state == "EARLY_RECOVERY" else -2.0,
                market_state=state,
            )
        )
    result = _execute(
        "market_conditioning",
        _panel(rows),
        {"horizon": "T5", "partition_by": "research_market_state"},
    )
    assert len(result.groups) >= 2
    assert any(g["median"] is not None and g["median"] < 0 for g in result.groups.values())


# --- HORIZON ---


def test_horizon_comparison_returns_all_requested():
    rows = [
        _row(
            trade_date=f"2026-08-{i+1:02d}",
            symbol=f"S{i}",
            t3_return=1.0,
            t5_return=2.0,
            t10_return=-1.0,
        )
        for i in range(5)
    ]
    result = _execute(
        "horizon_comparison",
        _panel(rows),
        {"horizons": ["T3", "T5", "T10"]},
    )
    assert set(result.groups.keys()) == {"T3", "T5", "T10"}


def test_horizon_comparison_does_not_hide_negative_horizon():
    rows = [
        _row(
            trade_date="2026-08-01",
            symbol="S0",
            t3_return=5.0,
            t5_return=-3.0,
            t10_return=-4.0,
        ),
        _row(
            trade_date="2026-08-02",
            symbol="S1",
            t3_return=5.0,
            t5_return=-3.0,
            t10_return=-4.0,
        ),
        _row(
            trade_date="2026-08-03",
            symbol="S2",
            t3_return=5.0,
            t5_return=-3.0,
            t10_return=-4.0,
        ),
    ]
    result = _execute("horizon_comparison", _panel(rows), {"horizons": ["T3", "T5", "T10"]})
    assert result.groups["T5"]["cohort_median"] < 0
    codes = [o.code for o in result.structured_observations]
    assert OBS_HORIZON_HETEROGENEOUS in codes


# --- SENSITIVITY ---


def test_sensitivity_extreme_winner_detected():
    rows = [
        _row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=-0.1)
        for i in range(9)
    ]
    rows.append(_row(trade_date="2026-08-10", symbol="S9", t5_return=100.0))
    result = _execute(
        "sensitivity_analysis",
        _panel(rows),
        {"horizon": "T5", "tests": ["remove_largest_positive"]},
    )
    codes = [o.code for o in result.structured_observations]
    assert OBS_EXTREME_WINNER_SENSITIVE in codes
    assert result.metrics["fragile"] is True


def test_sensitivity_leave_one_date_out():
    rows = []
    for d in range(5):
        for s in range(2):
            rows.append(
                _row(
                    trade_date=f"2026-08-{d+1:02d}",
                    symbol=f"S{d}{s}",
                    t5_return=2.0,
                )
            )
    result = _execute(
        "sensitivity_analysis",
        _panel(rows),
        {"horizon": "T5", "tests": ["leave_one_date"]},
    )
    assert "leave_one_date" in result.groups
    assert len(result.groups["leave_one_date"]["medians"]) == 5


def test_sensitivity_leave_one_symbol_out():
    rows = [
        _row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=2.0)
        for i in range(5)
    ]
    result = _execute(
        "sensitivity_analysis",
        _panel(rows),
        {"horizon": "T5", "tests": ["leave_one_symbol"]},
    )
    assert "leave_one_symbol" in result.groups
    assert len(result.groups["leave_one_symbol"]["medians"]) == 5


# --- NEIGHBORHOOD ---


def _neighborhood_panel(isolated: bool) -> pd.DataFrame:
    rows = []
    for i in range(80):
        rs10 = -7.0 if (i < 25 and isolated) else float(i % 3)
        rows.append(
            {
                "trade_date": f"2026-07-{23 + (i % 5):02d}",
                "symbol": f"S{i:03d}",
                "rs5": rs10,
                "rs10": rs10,
                "rsi14": 35.0,
                "rs_spread": 0.0,
                "research_market_state": "EARLY_RECOVERY",
                "research_market_transition": "STRESS -> EARLY_RECOVERY",
                "t3_return": 3.0 if -10 < rs10 <= -5 else 0.0,
                "t5_return": 3.0 if -10 < rs10 <= -5 else 0.0,
                "t10_return": 3.0 if -10 < rs10 <= -5 else 0.0,
                **_target_dates(f"2026-07-{23 + (i % 5):02d}", 10),
            }
        )
    return pd.DataFrame(rows)


def test_neighborhood_stable():
    from modules.edge_research.robustness import test_neighborhood_stability

    rows = []
    for i in range(80):
        rs10 = -8.0 if i < 40 else float((i % 5) - 2)
        rows.append(
            {
                "trade_date": f"2026-07-{23 + (i % 5):02d}",
                "symbol": f"S{i:03d}",
                "rs5": rs10 + 1,
                "rs10": rs10,
                "rsi14": 35.0,
                "rs_spread": 1.0,
                "research_market_state": "EARLY_RECOVERY",
                "research_market_transition": "STRESS -> EARLY_RECOVERY",
                "t3_return": 2.0 if rs10 <= -5 else 0.1,
                "t5_return": 2.0 if rs10 <= -5 else 0.1,
                "t10_return": 2.0 if rs10 <= -5 else 0.1,
                **_target_dates(f"2026-07-{23 + (i % 5):02d}", 10),
            }
        )
    panel = pd.DataFrame(rows)
    clause = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    row = pd.Series(
        {
            "market_transition": "STRESS -> EARLY_RECOVERY",
            "market_state": "EARLY_RECOVERY",
            "best_horizon": "T5",
        }
    )
    expected = test_neighborhood_stability(panel, row, [clause], "T5")
    result = _execute(
        "neighborhood_stability",
        panel,
        {
            "horizon": "T5",
            "condition_clauses": [
                {
                    "feature": clause.feature,
                    "operator": clause.operator,
                    "threshold_lo": clause.threshold_lo,
                    "threshold_hi": clause.threshold_hi,
                    "bucket_id": clause.bucket_id,
                }
            ],
        },
    )
    assert result.metrics.get("stability") == expected["stability"]
    if expected["stability"] == "BROAD_STABLE":
        codes = [o.code for o in result.structured_observations]
        assert OBS_NEIGHBORHOOD_STABLE in codes


def test_neighborhood_isolated_bucket_unstable():
    panel = _neighborhood_panel(isolated=True)
    clause = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    result = _execute(
        "neighborhood_stability",
        panel,
        {
            "horizon": "T5",
            "condition_clauses": [
                {
                    "feature": clause.feature,
                    "operator": clause.operator,
                    "threshold_lo": clause.threshold_lo,
                    "threshold_hi": clause.threshold_hi,
                    "bucket_id": clause.bucket_id,
                }
            ],
        },
    )
    codes = [o.code for o in result.structured_observations]
    assert OBS_NEIGHBORHOOD_UNSTABLE in codes or result.metrics.get("stability") in (
        "ISOLATED_BUCKET",
        "BOUNDARY_SENSITIVE",
    )


def test_neighborhood_no_threshold_optimization():
    panel = _neighborhood_panel(isolated=True)
    clause = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    inputs = {
        "horizon": "T5",
        "condition_clauses": [
            {
                "feature": clause.feature,
                "operator": clause.operator,
                "threshold_lo": clause.threshold_lo,
                "threshold_hi": clause.threshold_hi,
                "bucket_id": clause.bucket_id,
            }
        ],
    }
    r1 = _execute("neighborhood_stability", panel, inputs)
    r2 = _execute("neighborhood_stability", panel, inputs)
    assert r1.metrics == r2.metrics
    assert "optimized_threshold" not in str(r1.metrics)


# --- TRAJECTORY ---


def _trajectory_history() -> pd.DataFrame:
    rows = []
    for day, rs10 in enumerate([10.0, 12.0, 11.0, 15.0, 20.0], start=1):
        rows.append(
            {
                "trade_date": f"2026-08-0{day}",
                "symbol": "AAA",
                "price": 100.0 + day,
                "rs5": day,
                "rs10": rs10,
                "rsi14": 40.0 + day,
                "rs_spread": day - rs10,
                "rsi_slope": float(day),
                "volume_ratio20": 1.0,
                "health_score": 50.0,
                "health_group": "G1",
                "obv_status": "UP",
                "health_rank": 1.0,
                "group_rank": 1.0,
                "t3_return": 1.0 if rs10 < 15 else 5.0,
                "t5_return": 1.0 if rs10 < 15 else 5.0,
                "t10_return": 1.0 if rs10 < 15 else 5.0,
                **_target_dates(f"2026-08-0{day}", 10),
            }
        )
    return pd.DataFrame(rows)


def test_trajectory_explicit_temporal_feature():
    panel = _trajectory_history()
    bins = [{"lo": None, "hi": 2.0, "label": "low_delta"}, {"lo": 2.0, "hi": None, "label": "high_delta"}]
    result = _execute(
        "trajectory_partition_compare",
        panel,
        {
            "temporal_feature": "rs10_delta_3",
            "bins": bins,
            "horizon": "T5",
        },
    )
    assert result.status in (ToolStatus.OK, ToolStatus.NO_VARIATION)
    assert result.metrics["temporal_feature"] == "rs10_delta_3"


def test_trajectory_does_not_choose_feature():
    panel = _trajectory_history()
    with pytest.raises(KeyError):
        _execute(
            "trajectory_partition_compare",
            panel,
            {"bins": [{"lo": None, "hi": 0, "label": "x"}], "horizon": "T5"},
        )


def test_trajectory_future_rows_do_not_change_prior_features():
    hist = _trajectory_history()
    bins = [{"lo": None, "hi": 0.0, "label": "neg"}, {"lo": 0.0, "hi": None, "label": "pos"}]
    baseline = _execute(
        "trajectory_partition_compare",
        hist,
        {"temporal_feature": "rs10_delta_3", "bins": bins, "horizon": "T5"},
    )
    future = hist.copy()
    future = pd.concat(
        [
            future,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-09-15",
                        "symbol": "AAA",
                        "price": 1e6,
                        "rs5": 1e6,
                        "rs10": 1e6,
                        "rsi14": 1e6,
                        "rs_spread": 0.0,
                        "rsi_slope": 1e6,
                        "volume_ratio20": 1.0,
                        "health_score": 1e6,
                        "health_group": "FUTURE",
                        "obv_status": "UP",
                        "health_rank": 1.0,
                        "group_rank": 1.0,
                        "t3_return": 999.0,
                        "t5_return": 999.0,
                        "t10_return": 999.0,
                        **_target_dates("2026-09-15", 10),
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    extended = _execute(
        "trajectory_partition_compare",
        future,
        {"temporal_feature": "rs10_delta_3", "bins": bins, "horizon": "T5"},
    )
    assert baseline.input_hash == extended.input_hash
    assert baseline.groups == extended.groups


# --- CUTOFF / LEAKAGE ---


def test_rows_after_session_cutoff_unavailable():
    rows = [
        _row(trade_date="2026-08-19", symbol="S0", t5_return=1.0),
        _row(trade_date="2026-08-25", symbol="S1", t5_return=99.0),
    ]
    filtered, diag = apply_research_cutoff(_panel(rows), "2026-08-20")
    assert diag["rows_excluded_after_t0_cutoff"] == 1
    assert len(filtered) == 1


def test_forward_outcome_not_matured_unavailable():
    rows = [_row(trade_date="2026-08-15", symbol="S0", t5_return=5.0, mature=False)]
    filtered, diag = apply_research_cutoff(_panel(rows), "2026-08-20", horizon="T5")
    assert diag.get("rows_excluded_immature_T5", 0) >= 1
    assert pd.isna(filtered.iloc[0]["t5_return"])


def test_matured_outcome_allowed():
    rows = [_row(trade_date="2026-08-01", symbol="S0", t5_return=2.5, mature=True)]
    filtered, _ = apply_research_cutoff(_panel(rows), "2026-08-20", horizon="T5")
    assert filtered.iloc[0]["t5_return"] == pytest.approx(2.5)


def test_experiment_spec_cutoff_mismatch_rejected():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-20")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Date concentration?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    spec = ExperimentSpec(
        tool_name="date_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date="2026-08-01",
    )
    with pytest.raises(Exception):
        g.add_experiment(question_node_id=qid, spec=spec)


def test_source_panel_remains_unchanged():
    panel = _broad_panel()
    snapshot = panel.copy(deep=True)
    _execute("date_decomposition", panel, {"horizon": "T5"})
    pd.testing.assert_frame_equal(panel, snapshot)


# --- GRAPH BRIDGE ---


def test_graph_experiment_executes_one_tool():
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Observed cohort lift", node_id="O1")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Is effect date-concentrated?",
        rationale=QuestionRationale(reason_code="FOLLOW_UP", prior_node_id=oid),
        node_id="Q1",
    )
    spec = ExperimentSpec(
        tool_name="date_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    eid = g.add_experiment(question_node_id=qid, spec=spec, node_id="E1")
    panel = _broad_panel()
    registry = build_default_tool_registry()
    result = execute_research_experiment(g, eid, registry, panel)
    assert result.status == ToolStatus.OK
    assert len(result.structured_observations) >= 1


def test_graph_result_attaches_immutably():
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="symbol_decomposition",
            tool_version="v1",
            inputs={"horizon": "T5"},
            research_scope={},
            data_cutoff_date=CUTOFF,
        ),
    )
    execute_research_experiment(g, eid, build_default_tool_registry(), _broad_panel())
    node = g.get_node(eid)
    assert node.experiment_result is not None
    assert node.experiment_result.finalized is True
    with pytest.raises(Exception):
        g.attach_experiment_result(eid, metrics={"mutated": True})


def test_graph_structured_observations_persist():
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="date_decomposition",
            tool_version="v1",
            inputs={"horizon": "T5"},
            research_scope={},
            data_cutoff_date=CUTOFF,
        ),
    )
    execute_research_experiment(g, eid, build_default_tool_registry(), _broad_panel())
    obs = g.get_node(eid).experiment_result.observations
    assert len(obs) >= 1
    assert all(isinstance(o, StructuredResearchObservation) for o in obs)


def test_graph_duplicate_execution_blocked():
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    spec = ExperimentSpec(
        tool_name="date_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    eid = g.add_experiment(question_node_id=qid, spec=spec)
    registry = build_default_tool_registry()
    execute_research_experiment(g, eid, registry, _broad_panel())
    with pytest.raises(ResearchToolExecutionError, match="finalized result"):
        execute_research_experiment(g, eid, registry, _broad_panel())


def test_graph_serialize_reload_retains_tool_result_lineage(tmp_path: Path):
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Cohort anomaly", node_id="O1")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Date concentration?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
        node_id="Q1",
    )
    spec = ExperimentSpec(
        tool_name="date_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    eid = g.add_experiment(question_node_id=qid, spec=spec, node_id="E1")
    execute_research_experiment(g, eid, build_default_tool_registry(), _broad_panel())

    path = write_research_graph(g, data_dir=tmp_path / "edge_research")
    reloaded = read_research_graph(g.session.research_session_id, data_dir=tmp_path / "edge_research")

    exp = reloaded.get_node("E1")
    assert exp.experiment_spec.tool_name == "date_decomposition"
    assert exp.experiment_spec.tool_version == "v1"
    assert exp.experiment_spec.inputs == {"horizon": "T5"}
    assert exp.experiment_spec.data_cutoff_date == CUTOFF
    assert exp.experiment_result is not None
    assert exp.experiment_result.result_hash
    assert len(exp.experiment_result.observations) >= 1
    lineage = reloaded.reconstruct_lineage("E1")
    assert [n.node_id for n in lineage] == ["O1", "Q1", "E1"]


# --- SEMANTICS ---


def test_no_tool_returns_buy_sell_edge_active():
    forbidden = {"BUY", "SELL", "EDGE_ACTIVE", "EDGE FOUND", "BULLISH", "BEARISH", "STRONG_BUY"}
    reg = build_default_tool_registry()
    panel = _broad_panel()
    for meta in reg.list_tools():
        result = reg.get(meta.tool_name).execute(
            panel,
            inputs=_default_inputs(meta.tool_name),
            research_scope={},
            data_cutoff_date=CUTOFF,
        )
        blob = json.dumps(result.to_dict())
        blob_upper = blob.upper()
        for word in forbidden:
            assert word not in blob_upper, f"{meta.tool_name} output contained {word}"
        obs_codes = [o.code.upper() for o in result.structured_observations]
        for word in forbidden:
            assert word not in obs_codes, f"{meta.tool_name} observation contained {word}"


def _default_inputs(tool_name: str) -> dict:
    if tool_name == "partition_group_compare":
        return {
            "partition_column": "partition_group",
            "partition_type": "categorical",
            "horizon": "T5",
        }
    if tool_name == "market_conditioning":
        return {"horizon": "T5", "partition_by": "research_market_state"}
    if tool_name == "horizon_comparison":
        return {"horizons": ["T3", "T5", "T10"]}
    if tool_name == "sensitivity_analysis":
        return {"horizon": "T5", "tests": ["leave_one_date"]}
    if tool_name == "neighborhood_stability":
        clause = build_clauses_for_feature("rs10")[0]
        return {
            "horizon": "T5",
            "condition_clauses": [
                {
                    "feature": clause.feature,
                    "operator": clause.operator,
                    "threshold_lo": clause.threshold_lo,
                    "threshold_hi": clause.threshold_hi,
                    "bucket_id": clause.bucket_id,
                }
            ],
        }
    if tool_name == "trajectory_partition_compare":
        return {
            "temporal_feature": "rs10_delta_3",
            "bins": [{"lo": None, "hi": 0, "label": "a"}, {"lo": 0, "hi": None, "label": "b"}],
            "horizon": "T5",
        }
    return {"horizon": "T5"}


def test_no_clear_difference_is_valid():
    rows = [
        _row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=1.0, group="A")
        for i in range(3)
    ] + [
        _row(trade_date=f"2026-08-{i+4:02d}", symbol=f"S{i+3}", t5_return=1.005, group="B")
        for i in range(3)
    ]
    result = _execute(
        "partition_group_compare",
        _panel(rows),
        {"partition_column": "partition_group", "partition_type": "categorical", "horizon": "T5"},
    )
    codes = [o.code for o in result.structured_observations]
    assert OBS_NO_CLEAR_DIFFERENCE in codes or OBS_NO_VARIATION in codes


def test_no_planner_or_next_action_selection():
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="date_decomposition",
            tool_version="v1",
            inputs={"horizon": "T5"},
            research_scope={},
            data_cutoff_date=CUTOFF,
        ),
    )
    execute_research_experiment(g, eid, build_default_tool_registry(), _broad_panel())
    exp = g.get_node(eid)
    assert exp.candidate_next_actions == []
    assert len(g.list_open_branches()) >= 1


# --- ACCEPTANCE SCENARIO (Task M) ---


def test_acceptance_o1_q1_e1_tool_composability(tmp_path: Path):
    """O1 -> Q1 -> E1 with tool result; manual E2 with different tool."""
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF)
    oid = g.add_root_observation(
        description="Cohort shows elevated T5 median",
        source_metrics={"median_t5": 2.1},
        node_id="O1",
    )
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Is the effect broadly distributed across dates?",
        rationale=QuestionRationale(
            reason_code="UNEXPLAINED_MAGNITUDE",
            prior_node_id=oid,
            evidence_summary={"median_t5": 2.1},
        ),
        node_id="Q1",
    )
    e1_spec = ExperimentSpec(
        tool_name="date_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    e1 = g.add_experiment(question_node_id=qid, spec=e1_spec, node_id="E1")
    panel = _broad_panel()
    e1_result = execute_research_experiment(g, e1, build_default_tool_registry(), panel)

    assert g.get_node(qid).question_text.startswith("Is the effect")
    assert g.get_node(e1).experiment_spec == e1_spec
    assert e1_result.tool_name == "date_decomposition"
    assert e1_result.tool_version == "v1"
    assert e1_result.data_cutoff_date == CUTOFF
    assert e1_result.input_hash == compute_tool_input_hash(
        "date_decomposition", "v1", {"horizon": "T5"}, {}, CUTOFF
    )
    assert len(e1_result.structured_observations) >= 1

    write_research_graph(g, data_dir=tmp_path / "edge_research")
    reloaded = read_research_graph(g.session.research_session_id, data_dir=tmp_path / "edge_research")
    e1_node = reloaded.get_node("E1")
    assert e1_node.experiment_result.result_hash == compute_result_hash(
        e1_node.experiment_result.metrics
    )

    # Manual E2 — different tool, explicitly specified (not auto-chosen from E1)
    q2 = g.spawn_question(
        parent_node_ids=[e1],
        question_text="Is effect symbol-concentrated?",
        rationale=QuestionRationale(reason_code="MANUAL_FOLLOW_UP", prior_node_id=e1),
        node_id="Q2",
    )
    e2_spec = ExperimentSpec(
        tool_name="symbol_decomposition",
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    e2 = g.add_experiment(question_node_id=q2, spec=e2_spec, node_id="E2")
    e2_result = execute_research_experiment(g, e2, build_default_tool_registry(), panel)
    assert e2_result.tool_name == "symbol_decomposition"
    assert e2_result.tool_name != e1_result.tool_name
