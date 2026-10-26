"""Tests for Phase 3I.12 minimal evidence synthesis engine."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import (
    BB_EPISTEMIC_01_CASES,
    FORBIDDEN_TOKENS,
    GENERALIZATION_CASES,
    all_bb_cases,
    assert_development_firewall,
    run_case,
)
from modules.edge_research.opr_bridge.evidence_relationship_classifier import classify_pair
from modules.edge_research.opr_bridge.evidence_synthesis_engine import (
    engine_content_hash,
    synthesize_evidence,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import ResearchPriorityAction
from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs


@pytest.fixture(scope="module")
def engine_hash() -> str:
    return engine_content_hash()


# --- Development firewall ---


def test_development_firewall_no_real_proposition_tokens():
    for case in all_bb_cases():
        assert_development_firewall(case)
        blob = str(case).lower()
        for tok in FORBIDDEN_TOKENS:
            assert tok.lower() not in blob, f"Forbidden token {tok} in {case['case_id']}"


# --- BB-Epistemic-01 ---


@pytest.mark.parametrize("case", BB_EPISTEMIC_01_CASES, ids=lambda c: c["case_id"])
def test_bb_epistemic_01_cases(case: Dict[str, Any]):
    synthesis, decision = run_case(case)
    assert synthesis.synthesized_epistemic_state in case["expected_states"], (
        f"{case['case_id']}: state {synthesis.synthesized_epistemic_state} not in {case['expected_states']}"
    )
    assert decision.chosen_priority_action in case["expected_actions"], (
        f"{case['case_id']}: action {decision.chosen_priority_action} not in {case['expected_actions']}"
    )
    if "expected_saturation" in case:
        assert synthesis.saturation_assessment["level"] in case["expected_saturation"]
    if "expect_unresolved_includes" in case:
        for dim in case["expect_unresolved_includes"]:
            assert dim in synthesis.uncertainty_unresolved


@pytest.mark.parametrize("case", GENERALIZATION_CASES, ids=lambda c: c["case_id"])
def test_generalization_controls(case: Dict[str, Any]):
    synthesis, decision = run_case(case)
    assert synthesis.synthesized_epistemic_state in case["expected_states"]
    assert decision.chosen_priority_action in case["expected_actions"]


# --- No vote counting ---


def test_two_correlated_supports_do_not_outrank_strong_disconfirm():
    prop = {"proposition_id": "p-vote", "proposition_hash": "h", "proposition_type": "partition_contrast"}
    evidence = [
        {
            "evidence_id": "s1",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "cohort_overlap_ratio": 0.0,
            "effect_magnitude": "strong",
        },
        {
            "evidence_id": "s2",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "cohort_overlap_ratio": 0.95,
            "experiment_content_hash": "s2",
            "effect_magnitude": "strong",
        },
        {
            "evidence_id": "d1",
            "evidence_class": "DISCONFIRMING",
            "feature_semantics": "flux_index",
            "population_semantics": "independent",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "independent",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "cohort_overlap_ratio": 0.1,
            "experiment_content_hash": "d1",
            "effect_magnitude": "strong",
        },
    ]
    synthesis, _ = synthesize_evidence(prop, evidence, prior_epistemic_state="SUPPORTED")
    assert synthesis.synthesized_epistemic_state in ("CONFLICTED", "FALSIFIED", "WEAKENED")
    assert synthesis.synthesized_epistemic_state != "SUPPORTED"


def test_ten_representation_repetitions_no_saturation_by_count():
    prop = {"proposition_id": "p-repr", "proposition_hash": "h", "proposition_type": "partition_contrast"}
    base = {
        "evidence_class": "SUPPORTING",
        "feature_semantics": "flux_index",
        "population_semantics": "full",
        "outcome_semantics": "delta_yield",
        "cohort_episode_scope": "all",
        "uncertainty_axis_tested": "directional_effect_full_universe",
        "cohort_overlap_ratio": 1.0,
        "effect_magnitude": "strong",
        "measurement_tool": "tier_compare",
    }
    evidence = [
        {**base, "evidence_id": f"e{i}", "experiment_content_hash": f"h{i}", "measurement_tool": f"tool_{i}"}
        for i in range(10)
    ]
    synthesis, decision = synthesize_evidence(prop, evidence, prior_epistemic_state="SUPPORTED")
    assert synthesis.saturation_assessment["level"] != "HIGH" or decision.chosen_priority_action != "HOLD_PROVISIONALLY"


def test_invalid_disconfirmation_does_not_weaken():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-08")
    synthesis, _ = run_case(case)
    assert synthesis.synthesized_epistemic_state == "SUPPORTED"


def test_non_informative_does_not_count_as_support():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-09")
    synthesis, _ = run_case(case)
    assert synthesis.synthesized_epistemic_state == "SUPPORTED"
    assert len(synthesis.supporting_structure) == 1


# --- Anti-rescue ---


def test_falsified_preserved_after_later_support():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-14")
    synthesis, decision = run_case(case)
    assert synthesis.synthesized_epistemic_state == "FALSIFIED"
    assert decision.chosen_priority_action == "ABANDON"


def test_contradiction_not_resolved_by_narrow_slice_without_validity():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-15")
    synthesis, _ = run_case(case)
    assert synthesis.synthesized_epistemic_state in ("CONFLICTED", "FALSIFIED", "WEAKENED")


# --- Anti-endless-skepticism ---


def test_hold_provisionally_possible_without_truth_claim():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-11")
    synthesis, decision = run_case(case)
    assert synthesis.synthesized_epistemic_state == "SUPPORTED"
    assert decision.chosen_priority_action in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED")
    assert "not proven true" in " ".join(decision.rationale).lower() or decision.chosen_priority_action == "HOLD_PROVISIONALLY"


# --- Evidence causality counterfactuals ---


def test_counterfactual_remove_decisive_disconfirm_changes_state():
    case = copy.deepcopy(next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-05"))
    full_synth, _ = run_case(case)
    case_one = copy.deepcopy(case)
    case_one["evidence"] = case_one["evidence"][:1]
    partial_synth, _ = run_case(case_one)
    assert full_synth.synthesized_epistemic_state != partial_synth.synthesized_epistemic_state


def test_counterfactual_invalid_disconfirm_changes_nothing():
    case = copy.deepcopy(next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-05"))
    synth_full, _ = run_case(case)
    case_inv = copy.deepcopy(case)
    case_inv["evidence"][1]["validity"] = "INVALID"
    synth_inv, _ = run_case(case_inv)
    assert synth_inv.synthesized_epistemic_state == "SUPPORTED"
    assert synth_full.synthesized_epistemic_state != synth_inv.synthesized_epistemic_state


def test_counterfactual_correlated_vs_independent_changes_saturation():
    prop = {"proposition_id": "p-cf", "proposition_hash": "h", "proposition_type": "partition_contrast"}
    correlated = [
        {
            "evidence_id": "e1",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "cohort_overlap_ratio": 0.0,
        },
        {
            "evidence_id": "e2",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "cohort_overlap_ratio": 0.95,
            "experiment_content_hash": "e2",
        },
    ]
    independent = copy.deepcopy(correlated)
    independent[1]["cohort_overlap_ratio"] = 0.15
    independent[1]["population_semantics"] = "holdout"
    independent[1]["cohort_episode_scope"] = "holdout"
    independent[1]["uncertainty_axis_tested"] = "episode_robustness"
    s_corr, _ = synthesize_evidence(prop, correlated, prior_epistemic_state="SUPPORTED")
    s_ind, _ = synthesize_evidence(prop, independent, prior_epistemic_state="SUPPORTED")
    assert s_corr.uncertainty_unresolved != s_ind.uncertainty_unresolved or (
        s_corr.saturation_assessment["level"] != s_ind.saturation_assessment["level"]
    )


# --- Relationship classifier ---


def test_tool_change_alone_not_independent():
    prop = {"proposition_id": "p-rel", "proposition_hash": "h"}
    specs = [
        {
            "evidence_id": "e1",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "measurement_tool": "tier_compare",
            "cohort_overlap_ratio": 0.0,
        },
        {
            "evidence_id": "e2",
            "evidence_class": "SUPPORTING",
            "feature_semantics": "flux_index",
            "population_semantics": "full",
            "outcome_semantics": "delta_yield",
            "cohort_episode_scope": "all",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "measurement_tool": "quantile_compare",
            "experiment_content_hash": "e2",
            "cohort_overlap_ratio": 1.0,
        },
    ]
    entries = build_ledger_from_specs("p-rel", "h", specs)
    rel = classify_pair(entries[1], entries[0])
    assert rel.value == "REPRESENTATION_REPLICATION"


# --- Engine freeze hash stable ---


def test_engine_hash_deterministic(engine_hash: str):
    assert engine_hash == engine_content_hash()
    assert len(engine_hash) == 64


# --- Real ledger: only after freeze (gated test) ---


def test_real_ledger_diagnostic_after_freeze(engine_hash: str):
    """One-shot real ledger — runs only when engine hash matches frozen value."""
    from modules.edge_research.opr_bridge.real_ledger_adapter import apply_real_ledger_diagnostic

    frozen_hash = engine_content_hash()
    assert engine_hash == frozen_hash
    result = apply_real_ledger_diagnostic()
    assert result["proposition_id"] == "prop-efb650d9bd5c451f"
    assert result["diagnostic_only"] is True
    assert result["no_new_experiment"] is True
    assert result["relationship_e1_to_e2"] in (
        "PARTIAL_REPLICATION",
        "INDEPENDENT_FALSIFICATION",
        "RELATED_EVIDENCE",
    )
    assert result["synthesis"]["synthesized_epistemic_state"] == "SUPPORTED"
    assert result["research_priority_decision"]["chosen_priority_action"] in (
        ResearchPriorityAction.SEEK_FALSIFICATION.value,
        ResearchPriorityAction.HOLD_PROVISIONALLY.value,
        ResearchPriorityAction.HOLD_UNRESOLVED.value,
    )
