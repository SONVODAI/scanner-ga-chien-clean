"""Isolation and scientific-safety tests for Multi-Family Discovery V2."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from modules.edge_research.contracts import SEARCH_FEATURES
from modules.edge_research.discovery import apply_condition, build_clauses_for_feature
from modules.multifamily_discovery_v2.clauses import V2Clause, apply_clauses, clauses_for_feature
from modules.multifamily_discovery_v2.contracts import OUTCOME_COLUMNS
from modules.multifamily_discovery_v2.discovery import generate_templates
from modules.multifamily_discovery_v2.feature_audit import audit_feature_frame
from modules.multifamily_discovery_v2.panel import build_v2_panel
from modules.multifamily_discovery_v2.registry import V2_REGISTRY, eligible_names_for_families


def _tiny_lifecycle() -> pd.DataFrame:
    rows = []
    for i in range(6):
        rows.append(
            {
                "trade_date": f"2026-08-0{i+1}",
                "symbol": "AAA",
                "price": 10 + i,
                "rs5": -12 + i,
                "rs10": -11 + i,
                "rsi14": 28 + i,
                "rs_spread": 1.0,
                "obv_status": "🟢" if i % 2 == 0 else "🔴",
                "obv": 1000 + i,
                "obv_ema9": 990,
                "volume": 100,
                "vol_ma20": 80,
                "volume_ratio20": 0.5 + i * 0.2,
                "dryup": False,
                "ema9": 10,
                "ma20": 11,
                "ema9_ma20_slope": -0.3 + i * 0.1,
                "dist_from_ema9_pct": -4 + i,
                "health_group": "🌱 ĐANG HỒI",
                "health_score": 50,
                "green2": False,
                "early": False,
                "pull": False,
                "t3_return_pct": 9.99,
            }
        )
    return pd.DataFrame(rows)


def test_production_search_features_untouched():
    assert SEARCH_FEATURES == ("rs10", "rsi14", "rs5", "rs_spread")


def test_control_template_cardinality_matches_production():
    names = eligible_names_for_families(("rs_rsi",))
    templates = generate_templates(names, include_cross_family_pairs=False)
    assert len(templates) == 154


def test_v2_numeric_mask_matches_production_condition_clause():
    panel = pd.DataFrame({"rs10": [-12.0, -8.0, 1.0, 6.0], "rsi14": [25, 35, 45, 70]})
    prod = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_le_-10"][0]
    v2 = [c for c in clauses_for_feature("rs10") if c.bucket_id == "rs10_le_-10"][0]
    prod_idx = set(apply_condition(panel, [prod]).index)
    v2_idx = set(apply_clauses(panel, [v2]).index)
    assert prod_idx == v2_idx


def test_categorical_and_boolean_clauses_match():
    panel = pd.DataFrame(
        {
            "obv_status": ["POSITIVE", "NEGATIVE", ""],
            "dryup": [True, False, pd.NA],
        }
    )
    obv = V2Clause(
        feature="obv_status",
        family="obv",
        datatype="categorical",
        operator="==",
        bucket_id="obv_POSITIVE",
        category="POSITIVE",
    )
    dry = V2Clause(
        feature="dryup",
        family="volume",
        datatype="boolean",
        operator="==",
        bucket_id="dryup_True",
        boolean_value=True,
    )
    assert list(apply_clauses(panel, [obv])["obv_status"]) == ["POSITIVE"]
    matched = apply_clauses(panel, [dry])
    assert len(matched) == 1
    assert bool(matched.iloc[0]["dryup"]) is True


def test_missing_categorical_does_not_match():
    panel = pd.DataFrame({"obv_status": ["", "POSITIVE"]})
    pos = [c for c in clauses_for_feature("obv_status") if c.category == "POSITIVE"][0]
    assert len(apply_clauses(panel, [pos])) == 1


def test_v2_panel_keeps_non_rs_and_excludes_lifecycle_returns_as_features():
    panel = build_v2_panel(lifecycle=_tiny_lifecycle())
    assert "obv_status" in panel.columns
    assert "volume_ratio20" in panel.columns
    assert "ema9_ma20_slope" in panel.columns
    assert "health_group" in panel.columns
    for col in OUTCOME_COLUMNS:
        if col in {"t3_return", "t5_return", "t10_return"}:
            continue
        assert col not in panel.columns
    assert set(panel["obv_status"].unique()) <= {"POSITIVE", "NEGATIVE", ""}


def test_audit_flags_degenerate_booleans():
    frame = _tiny_lifecycle()
    audit = audit_feature_frame(frame)
    by_name = {r["field"]: r for r in audit["features"]}
    assert by_name["green2"]["degenerate"] is True
    assert by_name["rs5"]["degenerate"] is False


def test_registry_does_not_auto_enable_temporal_or_absolute_levels():
    assert V2_REGISTRY["obv"].search_eligible is False
    assert V2_REGISTRY["volume"].search_eligible is False
    assert V2_REGISTRY["ema9"].search_eligible is False
    assert V2_REGISTRY["leader_score"].search_eligible is False
    assert V2_REGISTRY["group"].search_eligible is False


def test_cardinality_budget_refuses_all_family_cross_search():
    names = eligible_names_for_families(("rs_rsi", "obv", "volume", "trend", "health_group"))
    with pytest.raises(RuntimeError, match="exceeds budget"):
        generate_templates(
            names,
            include_cross_family_pairs=True,
            include_within_new_family_pairs=True,
            enable_three_feature=False,
        )


def test_v2_experiments_do_not_call_production_engine():
    import modules.multifamily_discovery_v2.experiments as exp

    src = inspect.getsource(exp)
    assert "EdgeResearchEngine" not in src
    assert "run_challenger" not in src
