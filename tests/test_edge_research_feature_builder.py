"""Tests for leakage-safe T0 feature matrix builder (PATCH 1)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.feature_builder import (
    build_t0_feature_matrix,
    get_matrix_registry,
    load_canonical_stock_history,
)
from modules.edge_research.feature_registry import (
    FeatureKind,
    FeatureRegistry,
    is_prohibited_feature_column,
    validate_feature_columns,
)


def _synthetic_history() -> pd.DataFrame:
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
                "volume_ratio20": 1.0 + day * 0.1,
                "health_score": 50.0 + day,
                "health_group": f"G{day % 2}",
                "obv_status": "UP" if day % 2 else "DOWN",
                "health_rank": float(day),
                "group_rank": float(10 - day),
            }
        )
    rows.append(
        {
            "trade_date": "2026-08-01",
            "symbol": "BBB",
            "price": 50.0,
            "rs5": 1.0,
            "rs10": 2.0,
            "rsi14": 30.0,
            "rs_spread": -1.0,
            "rsi_slope": 0.5,
            "volume_ratio20": 0.9,
            "health_score": 40.0,
            "health_group": "G0",
            "obv_status": "FLAT",
            "health_rank": 5.0,
            "group_rank": 8.0,
        }
    )
    return pd.DataFrame(rows)


def test_lag_1_uses_exactly_prior_snapshot():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-03")].iloc[0]
    assert row["rs10"] == 11.0
    assert row["rs10_lag_1"] == 12.0
    assert row["rs10_lag_2"] == 10.0


def test_lag_3_uses_exactly_third_prior_snapshot():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-05")].iloc[0]
    assert row["rs10"] == 20.0
    # Third prior snapshot for AAA on 2026-08-05 is 2026-08-02 (rs10=12.0).
    assert row["rs10_lag_3"] == 12.0


def test_lag_cannot_read_future_date():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    first = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-01")].iloc[0]
    assert pd.isna(first["rs10_lag_1"])
    mid = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-03")].iloc[0]
    assert mid["rs10_lag_1"] == 12.0
    assert mid["rs10_lag_1"] != mid["rs10"]
    later = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-04")].iloc[0]
    assert later["rs10_lag_1"] == 11.0
    assert later["rs10_lag_1"] != 20.0


def test_missing_prior_history_remains_missing():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    first = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-01")].iloc[0]
    assert pd.isna(first["rs10_lag_1"])
    assert pd.isna(first["rs10_lag_2"])
    assert pd.isna(first["rs10_lag_3"])
    assert pd.isna(first["rs10_delta_1"])


def test_delta_values_mathematically_correct():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-04")].iloc[0]
    assert row["rs10_delta_1"] == pytest.approx(15.0 - 11.0)
    assert row["rs10_delta_3"] == pytest.approx(15.0 - 10.0)


def test_slope_uses_only_trailing_leq_t0_observations():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-04")].iloc[0]
    expected = float(np.polyfit([0, 1, 2, 3], [10.0, 12.0, 11.0, 15.0], 1)[0])
    assert row["rs10_slope_3"] == pytest.approx(expected)


def test_categorical_transition_prior_to_current():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-03")].iloc[0]
    assert row["health_group"] == "G1"
    assert row["health_group_prior"] == "G0"
    assert row["health_group_transition"] == "G0 -> G1"


def test_duplicate_symbol_date_handled_deterministically():
    hist = _synthetic_history()
    dup = pd.concat(
        [
            hist,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-08-03",
                        "symbol": "AAA",
                        "price": 999.0,
                        "rs5": 99.0,
                        "rs10": 99.0,
                        "rsi14": 99.0,
                        "rs_spread": 0.0,
                        "rsi_slope": 9.0,
                        "volume_ratio20": 9.0,
                        "health_score": 99.0,
                        "health_group": "GX",
                        "obv_status": "UP",
                        "health_rank": 99.0,
                        "group_rank": 99.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    matrix = build_t0_feature_matrix(dup)
    row = matrix[(matrix["symbol"] == "AAA") & (matrix["trade_date"] == "2026-08-03")].iloc[0]
    assert row["rs10"] == 99.0


def test_unsorted_input_matches_sorted_input():
    hist = _synthetic_history()
    shuffled = hist.sample(frac=1.0, random_state=7).reset_index(drop=True)
    sorted_matrix = build_t0_feature_matrix(hist)
    unsorted_matrix = build_t0_feature_matrix(shuffled)
    merged = sorted_matrix.merge(
        unsorted_matrix,
        on=["trade_date", "symbol"],
        suffixes=("_sorted", "_unsorted"),
    )
    feature_cols = [c for c in sorted_matrix.columns if c not in ("trade_date", "symbol")]
    for col in feature_cols:
        left = merged[f"{col}_sorted"]
        right = merged[f"{col}_unsorted"]
        if pd.api.types.is_numeric_dtype(left):
            assert np.allclose(left, right, equal_nan=True)
        else:
            assert left.astype(str).tolist() == right.astype(str).tolist()


def test_prohibited_forward_columns_cannot_enter_feature_matrix():
    assert is_prohibited_feature_column("t3_return")
    assert is_prohibited_feature_column("t10_return_pct")
    assert is_prohibited_feature_column("forward_return")
    with pytest.raises(ValueError, match="Prohibited"):
        validate_feature_columns(["rs10", "t5_return"])


def test_extreme_future_rows_do_not_change_earlier_t0_features():
    hist = _synthetic_history()
    cutoff = "2026-08-03"
    baseline = build_t0_feature_matrix(hist)
    baseline_slice = baseline[baseline["trade_date"] <= cutoff].copy()

    future_rows = []
    for offset in range(1, 21):
        future_rows.append(
            {
                "trade_date": f"2026-09-{offset:02d}",
                "symbol": "AAA",
                "price": 1e6,
                "rs5": 1e6,
                "rs10": 1e6,
                "rsi14": 1e6,
                "rs_spread": 1e6,
                "rsi_slope": 1e6,
                "volume_ratio20": 1e6,
                "health_score": 1e6,
                "health_group": "FUTURE",
                "obv_status": "FUTURE",
                "health_rank": 1e6,
                "group_rank": 1e6,
            }
        )
    extended = pd.concat([hist, pd.DataFrame(future_rows)], ignore_index=True)
    rebuilt = build_t0_feature_matrix(extended)
    rebuilt_slice = rebuilt[rebuilt["trade_date"] <= cutoff].copy()

    feature_cols = [c for c in baseline_slice.columns if c not in ("trade_date", "symbol")]
    baseline_slice = baseline_slice.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    rebuilt_slice = rebuilt_slice.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    for col in feature_cols:
        b = baseline_slice[col]
        r = rebuilt_slice[col]
        if pd.api.types.is_numeric_dtype(b):
            assert np.allclose(b, r, equal_nan=True), f"Leak detected in column {col}"
        else:
            assert b.astype(str).tolist() == r.astype(str).tolist(), f"Leak detected in {col}"


def test_forward_labels_remain_separate_from_feature_matrix():
    hist = _synthetic_history()
    hist_with_outcome = hist.copy()
    hist_with_outcome["t3_return_pct"] = 999.0
    matrix = build_t0_feature_matrix(hist_with_outcome)
    assert "t3_return_pct" not in matrix.columns
    assert "t3_return" not in matrix.columns

    panel = build_research_panel(
        lifecycle=hist_with_outcome.assign(entry_date=hist_with_outcome["trade_date"])
    )
    assert "t3_return" in panel.columns
    assert "t3_return" not in matrix.columns


def test_feature_registry_metadata_populated():
    hist = _synthetic_history()
    matrix = build_t0_feature_matrix(hist)
    registry = get_matrix_registry(matrix)
    specs = registry.all_specs()
    assert len(specs) > 0
    rs10 = registry.get("rs10")
    assert rs10 is not None
    assert rs10.kind == FeatureKind.NUMERIC_LEVEL
    assert rs10.search_eligible is True
    lag = registry.get("rs10_lag_1")
    assert lag is not None
    assert lag.temporal is True
    assert lag.search_eligible is False


def test_load_canonical_stock_history_deduplicates():
    hist = _synthetic_history()
    loaded = load_canonical_stock_history(hist)
    assert loaded.duplicated(subset=["trade_date", "symbol"]).sum() == 0


def test_registry_distinguishes_numeric_and_categorical():
    registry = FeatureRegistry()
    hist = _synthetic_history()
    build_t0_feature_matrix(hist, registry=registry)
    assert registry.get("health_group").kind == FeatureKind.CATEGORICAL_LEVEL
    assert registry.get("health_group_transition").kind == FeatureKind.CATEGORICAL_TRANSITION
    assert registry.get("health_rank").kind == FeatureKind.RANK_LEVEL


def test_existing_research_panel_unchanged_with_synthetic_lifecycle():
    from modules.edge_research.contracts import RESEARCH_OBSERVATION_COLUMNS

    hist = _synthetic_history()
    panel = build_research_panel(lifecycle=hist.assign(entry_date=hist["trade_date"]))
    assert list(panel.columns) == list(RESEARCH_OBSERVATION_COLUMNS)
