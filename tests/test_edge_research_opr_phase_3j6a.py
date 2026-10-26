"""Phase 3J.6A — Scientific novelty audit tests."""

from __future__ import annotations

from modules.edge_research.opr_bridge.second_experiment_novelty_audit import (
    classify_counterfactual_case,
    decompose_novelty,
)


def _base_spec(*, population_kind: str = "all", pop_values=None):
    pop = {"kind": population_kind, "grammar_version": "research_grammar_v1"}
    if pop_values:
        pop = {"kind": "filter", "field": "trade_date", "operator": "not_in", "values": pop_values, "grammar_version": "research_grammar_v1"}
    return {
        "tool_name": "partition_group_compare",
        "inputs": {"partition_column": "rs_spread", "n_groups": 5},
        "research_scope": {
            "population_spec": pop,
            "outcome_spec": {"kind": "compare", "field": "t5_return", "operator": ">", "value": 0.0, "grammar_version": "research_grammar_v1"},
            "observation_horizon": 0,
        },
    }


def _identity(*, uncertainty: str, cohort: str, gain: str = "falsify", consequence: str = "falsify_x"):
    return {
        "objective_target_uncertainty": uncertainty,
        "cohort_strategy": cohort,
        "contrast_relation": "partition_quintile_contrast",
        "information_gain_type": gain,
        "expected_epistemic_consequence_type": consequence,
    }


def test_case_a_high_rows_new_contrast_admissible():
    d = decompose_novelty(
        first_spec=_base_spec(pop_values=["2026-08-02"]),
        first_identity=_identity(uncertainty="episode_robustness", cohort="counterexample_period_search", consequence="falsify_episode_robustness"),
        first_target_null="episode_artifact",
        first_target_uncertainty="episode_robustness",
        second_spec=_base_spec(),
        second_identity=_identity(uncertainty="directional_effect_full_universe", cohort="full_panel_contrast", consequence="falsify_directional_effect_full_universe"),
        second_target_null="directional_reversal",
        second_target_uncertainty="directional_effect_full_universe",
        row_overlap_fraction=0.977,
        first_row_count=6106,
        second_row_count=6248,
    )
    assert d.null_target_overlap == 0.0
    assert d.coarse_redundancy_interpretation == "HIGH_SAMPLE_REUSE_NEW_QUESTION"
    assert classify_counterfactual_case(row_overlap=0.977, null_target_overlap=0.0, scientific_question_overlap=0.0) == "A_HIGH_ROWS_NEW_CONTRAST_ADMISSIBLE"


def test_case_b_high_rows_same_contrast_reject():
    spec = _base_spec()
    ident = _identity(uncertainty="directional_effect_full_universe", cohort="full_panel_contrast", consequence="falsify_directional_effect_full_universe")
    d = decompose_novelty(
        first_spec=spec,
        first_identity=ident,
        first_target_null="directional_reversal",
        first_target_uncertainty="directional_effect_full_universe",
        second_spec=spec,
        second_identity=ident,
        second_target_null="directional_reversal",
        second_target_uncertainty="directional_effect_full_universe",
        row_overlap_fraction=0.977,
    )
    assert d.coarse_redundancy_interpretation == "SCIENTIFIC_REDUNDANCY"
    assert classify_counterfactual_case(row_overlap=0.977, null_target_overlap=1.0, scientific_question_overlap=1.0) == "B_HIGH_ROWS_SAME_CONTRAST_REJECT"


def test_case_c_low_rows_wrong_null_context():
    assert classify_counterfactual_case(row_overlap=0.10, null_target_overlap=0.0, scientific_question_overlap=0.0) == "C_LOW_ROWS_WRONG_QUESTION_CONTEXT"
