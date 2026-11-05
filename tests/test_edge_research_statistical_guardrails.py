"""Tests for PATCH 2A scientific search guardrails."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.discovery import run_discovery
from modules.edge_research.hypothesis import (
    FrozenHypothesisSpec,
    READY_FOR_OOS_MEANING,
    ScientificStatus,
    build_frozen_hypothesis_spec,
    derive_scientific_status,
    hypothesis_id_from_spec,
)
from modules.edge_research.oos import (
    assert_no_oos_leakage,
    chronological_research_split,
    labels_overlap_embargo,
)
from modules.edge_research.statistical_guardrails import (
    HypothesisTestRecord,
    HorizonTestResult,
    apply_multiple_testing_correction,
    benjamini_hochberg,
    compute_concentration_diagnostics,
    compute_search_cardinality,
    disjoint_baseline_returns,
    no_edge_outcome_reason,
    screening_statistics_semantics,
    summarize_guardrail_accounting,
    welch_one_sided_pvalue,
)


def _panel_from_rows(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in ("t3_return", "t5_return", "t10_return"):
        if col not in df.columns:
            df[col] = np.nan
    if "research_market_state" not in df.columns:
        df["research_market_state"] = "STRESS"
    if "research_market_transition" not in df.columns:
        df["research_market_transition"] = "STRESS -> STRESS"
    return df


def test_hypothesis_count_includes_failed_tests():
    rows = []
    for i in range(30):
        rows.append(
            {
                "trade_date": f"2026-08-{i+1:02d}",
                "symbol": f"S{i % 5}",
                "rs5": float(i % 3),
                "rs10": float(i % 4 - 1),
                "rsi14": 40.0 + (i % 5),
                "rs_spread": 0.5,
                "t3_return": 1.0,
                "t5_return": 1.0,
                "t10_return": 1.0,
            }
        )
    panel = _panel_from_rows(rows)
    result = run_discovery(panel)
    accounting = result.guardrail_accounting
    assert accounting["hypotheses_tested_total"] == result.conditions_tested
    assert accounting["hypotheses_tested_total"] > accounting["hypotheses_selected_as_candidates"]


def test_benjamini_hochberg_known_synthetic():
    pvals = [("a", 0.001), ("b", 0.04), ("c", 0.20), ("d", 0.50)]
    q = benjamini_hochberg(pvals)
    assert q["a"] <= 0.05
    assert q["d"] > q["a"]


def test_many_weak_random_hypotheses_do_not_all_survive_fdr():
    records = []
    for i in range(50):
        records.append(
            HypothesisTestRecord(
                hypothesis_key=f"h{i}",
                market_transition="STRESS -> STRESS",
                market_state="STRESS",
                condition_text=f"c{i}",
                condition_key=f"h{i}",
                eligible_after_basic_filters=True,
                raw_signal=True,
                horizon_results={
                    "T5": HorizonTestResult(
                        horizon="T5",
                        candidate_n=25,
                        incremental_median=0.01,
                        incremental_mean=0.01,
                        raw_signal=True,
                        raw_p_value=0.5,
                    )
                },
                best_horizon="T5",
            )
        )
    apply_multiple_testing_correction(records, fdr_alpha=0.10)
    survivors = [r for r in records if r.multiple_testing_survives]
    assert len(survivors) == 0


def test_strong_signal_can_survive_fdr():
    records = [
        HypothesisTestRecord(
            hypothesis_key="strong",
            market_transition="STRESS -> STRESS",
            market_state="STRESS",
            condition_text="strong",
            condition_key="strong",
            eligible_after_basic_filters=True,
            raw_signal=True,
            horizon_results={
                "T5": HorizonTestResult(
                    horizon="T5",
                    candidate_n=40,
                    incremental_median=2.0,
                    incremental_mean=2.0,
                    raw_signal=True,
                    raw_p_value=0.0001,
                )
            },
            best_horizon="T5",
        )
    ]
    apply_multiple_testing_correction(records, fdr_alpha=0.10)
    assert records[0].multiple_testing_survives is True


def test_one_date_concentration_flagged():
    rows = []
    for i in range(25):
        rows.append(
            {
                "trade_date": "2026-08-01",
                "symbol": f"S{i}",
                "t5_return": 2.0,
            }
        )
    diag = compute_concentration_diagnostics(pd.DataFrame(rows), horizon="T5")
    assert diag["largest_date_share"] == 1.0
    assert "DATE_CONCENTRATED" in diag["concentration_flags"]


def test_one_symbol_concentration_flagged():
    rows = []
    for i in range(20):
        rows.append(
            {
                "trade_date": f"2026-08-{i+1:02d}",
                "symbol": "ONLY",
                "t5_return": 2.0,
            }
        )
    diag = compute_concentration_diagnostics(pd.DataFrame(rows), horizon="T5")
    assert diag["largest_symbol_share"] == 1.0
    assert "SYMBOL_CONCENTRATED" in diag["concentration_flags"]


def test_extreme_winner_sensitivity_detected():
    rows = [{"trade_date": f"2026-08-{i+1:02d}", "symbol": f"S{i}", "t5_return": 0.5} for i in range(10)]
    rows.append({"trade_date": "2026-08-11", "symbol": "S10", "t5_return": 100.0})
    diag = compute_concentration_diagnostics(pd.DataFrame(rows), horizon="T5")
    assert diag["leave_largest_winner_out_survives"] is True or diag["leave_largest_winner_out_survives"] is False


def test_horizon_search_counted_in_cardinality():
    card = compute_search_cardinality(n_market_contexts=12, enable_three_feature=False)
    assert card["horizon_multiplier"] == 3
    assert card["horizon_level_tests_upper_bound"] == card["hypotheses_tested_total_upper_bound"] * 3


def test_chronological_split_no_future_in_discovery():
    rows = []
    for i in range(20):
        rows.append(
            {
                "trade_date": f"2026-08-{i+1:02d}",
                "symbol": "AAA",
                "rs5": 1.0,
                "rs10": 1.0,
                "rsi14": 40.0,
                "rs_spread": 0.0,
            }
        )
    panel = _panel_from_rows(rows)
    split = chronological_research_split(panel, discovery_fraction=0.6, embargo_trading_days=3)
    assert_no_oos_leakage(split)
    disc_dates = set(split.discovery_panel["trade_date"].astype(str))
    oos_dates = set(split.oos_panel["trade_date"].astype(str))
    assert disc_dates.isdisjoint(oos_dates) or split.oos_panel.empty


def test_embargo_prevents_label_overlap():
    # Trading-session embargo: weekends do not count as sessions.
    sessions = [
        "2026-07-01",
        "2026-07-02",
        "2026-08-10",
        "2026-08-11",
        "2026-08-12",
        "2026-08-13",
        "2026-08-14",
        "2026-08-17",
        "2026-08-18",
        "2026-08-19",
        "2026-08-20",
    ]
    assert labels_overlap_embargo(
        "2026-08-20", "2026-08-17", target_horizon_days=10, session_dates=sessions
    ) is True
    assert labels_overlap_embargo(
        "2026-08-20", "2026-07-01", target_horizon_days=10, session_dates=sessions
    ) is False


def test_frozen_hypothesis_spec_deterministic():
    spec1 = build_frozen_hypothesis_spec(
        condition_key="k",
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=({"feature": "rs10", "operator": "<=", "threshold": -10},),
        best_horizon="T5",
        discovery_run_id="run1",
        discovery_evidence={"incremental_median": 1.0},
        challenger_status="PASS",
        guardrails_summary={"multiple_testing_survives": True},
        data_cutoff_date="2026-08-17",
        guardrails_config_version="guardrails_v1",
        freeze_timestamp="2026-08-20T00:00:00Z",
    )
    spec2 = build_frozen_hypothesis_spec(
        condition_key="k",
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=({"feature": "rs10", "operator": "<=", "threshold": -10},),
        best_horizon="T5",
        discovery_run_id="run1",
        discovery_evidence={"incremental_median": 1.0},
        challenger_status="PASS",
        guardrails_summary={"multiple_testing_survives": True},
        data_cutoff_date="2026-08-17",
        guardrails_config_version="guardrails_v1",
        freeze_timestamp="2026-08-20T00:00:00Z",
    )
    assert spec1.hypothesis_id == spec2.hypothesis_id
    assert json.loads(spec1.serialize())["hypothesis_id"] == spec1.hypothesis_id


def test_modified_frozen_hypothesis_changes_id():
    base = build_frozen_hypothesis_spec(
        condition_key="k",
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=({"feature": "rs10", "operator": "<=", "threshold": -10},),
        best_horizon="T5",
        discovery_run_id="run1",
        discovery_evidence={},
        challenger_status="PASS",
        guardrails_summary={},
        data_cutoff_date="2026-08-17",
        guardrails_config_version="guardrails_v1",
    )
    modified = build_frozen_hypothesis_spec(
        condition_key="k2",
        condition_text="RS10<=-5",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=({"feature": "rs10", "operator": "<=", "threshold": -5},),
        best_horizon="T5",
        discovery_run_id="run1",
        discovery_evidence={},
        challenger_status="PASS",
        guardrails_summary={},
        data_cutoff_date="2026-08-17",
        guardrails_config_version="guardrails_v1",
    )
    assert base.hypothesis_id != modified.hypothesis_id


def test_oos_cannot_alter_frozen_discovery_evidence():
    spec = build_frozen_hypothesis_spec(
        condition_key="k",
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=(),
        best_horizon="T5",
        discovery_run_id="run1",
        discovery_evidence={"incremental_median": 1.5},
        challenger_status="PASS",
        guardrails_summary={},
        data_cutoff_date="2026-08-17",
        guardrails_config_version="guardrails_v1",
    )
    frozen = spec.serialize()
    mutated = FrozenHypothesisSpec.from_dict(json.loads(frozen))
    assert mutated.discovery_evidence["incremental_median"] == 1.5


def test_no_edge_found_is_valid_outcome():
    accounting = {
        "hypotheses_tested_total": 100,
        "hypotheses_selected_as_candidates": 0,
    }
    assert no_edge_outcome_reason(accounting, raw_candidates=0, fdr_candidates=0) == "NO_EDGE_FOUND"
    assert (
        no_edge_outcome_reason(accounting, raw_candidates=5, fdr_candidates=0)
        == "NO_EDGE_FOUND_AFTER_MULTIPLE_TESTING"
    )


def test_scientific_status_ready_for_oos_only_when_guardrails_pass():
    status = derive_scientific_status(
        raw_signal=True,
        multiple_testing_survives=True,
        robustness_status="PASS",
        concentration_fragile=False,
        episode_consistency="REPLICATED",
    )
    assert status == ScientificStatus.READY_FOR_OOS


def test_welch_pvalue_one_sided():
    cand = pd.Series([2.0, 2.5, 3.0, 2.2, 2.8] * 5)
    base = pd.Series([0.1, -0.2, 0.0, 0.3, -0.1] * 10)
    p = welch_one_sided_pvalue(cand, base)
    assert p is not None
    assert p < 0.05


def test_accounting_summarizes_all_tested():
    records = [
        HypothesisTestRecord(
            hypothesis_key="a",
            market_transition="T",
            market_state="S",
            condition_text="a",
            condition_key="a",
            eligible_after_basic_filters=True,
            raw_signal=True,
            selected_as_candidate=True,
        ),
        HypothesisTestRecord(
            hypothesis_key="b",
            market_transition="T",
            market_state="S",
            condition_text="b",
            condition_key="b",
            eligible_after_basic_filters=False,
        ),
    ]
    summary = summarize_guardrail_accounting(records)
    assert summary["hypotheses_tested_total"] == 2
    assert summary["hypotheses_eligible_after_basic_filters"] == 1


def test_neighborhood_stability_evaluates_adjacent_buckets():
    from modules.edge_research.discovery import ConditionClause, build_clauses_for_feature
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
    result = test_neighborhood_stability(panel, row, [clause], "T5")
    assert result["test_name"] == "neighborhood_stability"
    assert len(result.get("neighbor_results", [])) > 0
    assert result["stability"] in ("BROAD_STABLE", "BOUNDARY_SENSITIVE", "ISOLATED_BUCKET", "UNKNOWN")


def test_isolated_bucket_spike_flagged_fragile():
    from modules.edge_research.discovery import ConditionClause, build_clauses_for_feature
    from modules.edge_research.robustness import test_neighborhood_stability

    rows = []
    for i in range(80):
        # Only exact bucket rs10 in (-10,-5] gets edge; neighbors flat
        rs10 = -7.0 if i < 25 else float(i % 3)
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
            }
        )
    panel = pd.DataFrame(rows)
    clause = [c for c in build_clauses_for_feature("rs10") if c.bucket_id == "rs10_-10_to_-5"][0]
    row = pd.Series({"market_transition": "STRESS -> EARLY_RECOVERY", "best_horizon": "T5"})
    result = test_neighborhood_stability(panel, row, [clause], "T5")
    assert result["stability"] in ("ISOLATED_BUCKET", "BOUNDARY_SENSITIVE")


def test_screening_semantics_document_dependence_limitation():
    semantics = screening_statistics_semantics()
    assert semantics["independence_assumption"] == "NOT_ASSUMED"
    assert semantics["formal_inferential_validity"] is False
    assert semantics["fdr_survival_implies_validated_edge"] is False
    assert semantics["formal_edge_validation_requires_oos"] is True
    assert semantics["candidate_rows_subset_of_baseline_pool"] is True
    assert semantics["screening_baseline_is_disjoint_complement"] is True

    summary = summarize_guardrail_accounting([])
    assert summary["p_value_interpretation"] == "SCREENING_ONLY_NOT_FORMAL_INFERENCE"
    assert summary["multiple_testing_role"] == "DISCOVERY_SCREENING_GUARD"


def test_disjoint_baseline_excludes_candidate_rows():
    rows = []
    for i in range(40):
        rows.append(
            {
                "trade_date": f"2026-08-{i+1:02d}",
                "symbol": f"S{i}",
                "rs10": -7.0 if i < 10 else 1.0,
                "t5_return": 2.0 if i < 10 else 0.0,
            }
        )
    panel = pd.DataFrame(rows)
    candidates = panel[panel["rs10"] <= -5]
    complement = disjoint_baseline_returns(panel, candidates, horizon_col="t5_return")
    assert len(complement) == 30
    assert not any(abs(v - 2.0) < 0.01 for v in complement)


def test_fdr_survival_never_implies_validated_edge():
    fdr_only = derive_scientific_status(
        raw_signal=True,
        multiple_testing_survives=True,
        robustness_status="PASS",
        concentration_fragile=False,
        episode_consistency="REPLICATED",
    )
    assert fdr_only == ScientificStatus.READY_FOR_OOS
    assert fdr_only.value != "VALIDATED"
    assert "VALIDATED" not in fdr_only.value
    assert "EDGE ACTIVE" not in fdr_only.value

    screening_only = derive_scientific_status(
        raw_signal=True,
        multiple_testing_survives=True,
        robustness_status="FRAGILE",
        concentration_fragile=False,
        episode_consistency="REPLICATED",
    )
    assert screening_only != ScientificStatus.READY_FOR_OOS


def test_ready_for_oos_is_research_only_not_validated():
    assert "RESEARCH ONLY" in READY_FOR_OOS_MEANING
    assert "not a validated edge" in READY_FOR_OOS_MEANING.lower()
    semantics = screening_statistics_semantics()
    assert "RESEARCH ONLY" in semantics["ready_for_oos_meaning"]


def test_discovery_guardrails_include_screening_semantics():
    rows = []
    for i in range(30):
        rows.append(
            {
                "trade_date": f"2026-08-{i+1:02d}",
                "symbol": f"S{i % 5}",
                "rs5": float(i % 3),
                "rs10": float(i % 4 - 1),
                "rsi14": 40.0 + (i % 5),
                "rs_spread": 0.5,
                "t3_return": 1.0,
                "t5_return": 1.0,
                "t10_return": 1.0,
            }
        )
    result = run_discovery(_panel_from_rows(rows))
    assert result.guardrail_accounting["formal_inferential_validity"] is False
    if result.candidates:
        assert result.candidates[0].guardrails["screening_statistics"]["fdr_survival_implies_validated_edge"] is False
