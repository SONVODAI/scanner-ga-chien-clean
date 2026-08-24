"""
Phase 3I.12 — BB-Epistemic-01 abstract benchmark fixtures.

DEVELOPMENT FIREWALL: No rs_spread, t5_return, or current proposition metrics.
Abstract feature/outcome names only until engine freeze.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Firewall: forbidden tokens in abstract fixtures
FORBIDDEN_TOKENS = frozenset({"rs_spread", "t5_return", "prop-efb650d9bd5c451f", "6106", "5964"})


def assert_development_firewall(spec: Dict[str, Any]) -> None:
    """Raise if fixture contains real-proposition leakage."""
    import json

    blob = json.dumps(spec, default=lambda o: list(o) if isinstance(o, set) else str(o)).lower()
    for tok in FORBIDDEN_TOKENS:
        if tok.lower() in blob:
            raise ValueError(f"Development firewall violation: forbidden token '{tok}' in fixture")


def _prop(
    prop_id: str,
    ptype: str = "partition_contrast",
) -> Dict[str, Any]:
    return {
        "proposition_id": prop_id,
        "proposition_hash": f"abstract_{prop_id}",
        "proposition_type": ptype,
        "feature": "flux_index" if ptype == "partition_contrast" else "context_gate",
        "outcome": "delta_yield",
    }


def _ev(
    eid: str,
    cls: str,
    *,
    axis: str = "directional_effect_full_universe",
    pop: str = "full_universe",
    scope: str = "all_episodes",
    overlap: float = 0.0,
    magnitude: str = "strong",
    direction: str = "positive",
    validity: str = "VALID",
    falsify: bool = False,
    tool: str = "tier_compare",
    feature: str = "flux_index",
    outcome: str = "delta_yield",
    horizon: str = "H3",
    exp_hash: str | None = None,
) -> Dict[str, Any]:
    return {
        "evidence_id": eid,
        "experiment_id": eid,
        "experiment_content_hash": exp_hash or f"hash_{eid}",
        "evidence_class": cls,
        "validity": validity,
        "feature_semantics": feature,
        "population_semantics": pop,
        "outcome_semantics": outcome,
        "horizon": "H3",
        "cohort_episode_scope": scope,
        "data_cutoff": "2019-06-01",
        "sample_size": 500,
        "effect_direction": direction,
        "effect_magnitude": magnitude,
        "measurement_tool": tool,
        "uncertainty_axis_tested": axis,
        "falsification_intent": falsify,
        "cohort_overlap_ratio": overlap,
    }


# --- Proposition family A: continuous feature → forward outcome (partition-style) ---
PROP_PARTITION = _prop("prop-abstract-partition-A")


# --- Proposition family B: context modulation → outcome ---
PROP_CONTEXT = _prop("prop-abstract-context-B", ptype="context_modulation")


BB_EPISTEMIC_01_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "BE-01",
        "name": "one_support_only",
        "proposition": PROP_PARTITION,
        "prior_state": "HYPOTHESIS",
        "evidence": [_ev("e1", "SUPPORTING")],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "SEEK_REPLICATION"},
    },
    {
        "case_id": "BE-02",
        "name": "two_correlated_supports",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", axis="directional_effect_full_universe"),
            _ev("e2", "SUPPORTING", axis="directional_effect_full_universe", overlap=0.95, exp_hash="hash_e2"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
        "must_not": {"confidence_upgrade_by_count"},
    },
    {
        "case_id": "BE-03",
        "name": "two_independent_supports",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", axis="directional_effect_full_universe"),
            _ev(
                "e2",
                "SUPPORTING",
                axis="episode_robustness",
                pop="holdout_episodes",
                scope="holdout_exclude_focal",
                overlap=0.2,
                exp_hash="hash_e2_ind",
            ),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
    },
    {
        "case_id": "BE-04",
        "name": "support_weak_disconfirm",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev("e2", "DISCONFIRMING", magnitude="weak", overlap=0.3, exp_hash="hash_e2"),
        ],
        "expected_states": {"WEAKENED", "CONFLICTED"},
        "expected_actions": {"SEEK_REPLICATION", "SEEK_FALSIFICATION", "SEEK_CONTRADICTION_RESOLUTION"},
    },
    {
        "case_id": "BE-05",
        "name": "support_strong_independent_disconfirm",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev(
                "e2",
                "DISCONFIRMING",
                magnitude="strong",
                overlap=0.15,
                axis="directional_effect_full_universe",
                pop="independent_holdout",
                scope="independent_cohort",
                exp_hash="hash_e2_strong",
            ),
        ],
        "expected_states": {"FALSIFIED", "CONFLICTED", "WEAKENED"},
        "expected_actions": {"ABANDON", "SEEK_CONTRADICTION_RESOLUTION", "SEEK_REPLICATION"},
    },
    {
        "case_id": "BE-06",
        "name": "representation_only_support",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", tool="tier_compare"),
            _ev("e2", "SUPPORTING", tool="quantile_compare", overlap=1.0, exp_hash="hash_e2_repr"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
        "must_not": {"saturation_by_representation_count"},
    },
    {
        "case_id": "BE-07",
        "name": "conflicting_independent",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", magnitude="strong"),
            _ev(
                "e2",
                "DISCONFIRMING",
                magnitude="strong",
                overlap=0.1,
                pop="independent_holdout",
                scope="independent_cohort",
                exp_hash="hash_e2_conf",
            ),
        ],
        "expected_states": {"CONFLICTED", "FALSIFIED"},
        "expected_actions": {"SEEK_CONTRADICTION_RESOLUTION", "ABANDON", "SEEK_REPLICATION"},
    },
    {
        "case_id": "BE-08",
        "name": "invalid_disconfirmation",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev("e2", "DISCONFIRMING", validity="INVALID", exp_hash="hash_e2_inv"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
    },
    {
        "case_id": "BE-09",
        "name": "non_informative_repetition",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev("e2", "NON_INFORMATIVE", overlap=0.9, exp_hash="hash_e2_ni"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_UNRESOLVED", "HOLD_PROVISIONALLY"},
    },
    {
        "case_id": "BE-10",
        "name": "supports_major_dimension_untouched",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", axis="directional_effect_full_universe"),
            _ev("e2", "SUPPORTING", axis="directional_effect_full_universe", overlap=0.92, exp_hash="hash_e2"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
        "expect_unresolved_includes": {"horizon_robustness", "counterexample_exposure"},
    },
    {
        "case_id": "BE-11",
        "name": "saturation_no_contradiction",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", axis="directional_effect_full_universe"),
            _ev("e2", "SUPPORTING", axis="episode_robustness", overlap=0.2, pop="holdout", scope="holdout", exp_hash="h2"),
            _ev("e3", "SUPPORTING", axis="horizon_robustness", overlap=0.1, horizon="H5", exp_hash="h3"),
            _ev("e4", "SUPPORTING", axis="population_robustness", overlap=0.15, pop="subset_a", exp_hash="h4"),
            _ev("e5", "SUPPORTING", axis="temporal_regime_robustness", overlap=0.1, scope="regime_b", exp_hash="h5"),
            _ev("e6", "SUPPORTING", axis="measurement_robustness", overlap=0.1, tool="alt_tier", exp_hash="h6"),
            _ev("e7", "SUPPORTING", axis="counterexample_exposure", overlap=0.05, falsify=True, exp_hash="h7"),
            _ev("e8", "SUPPORTING", axis="regime_context_robustness", overlap=0.1, scope="regime_c", exp_hash="h8"),
            _ev("e9", "SUPPORTING", axis="effect_stability", overlap=0.08, scope="stability_window", exp_hash="h9"),
            _ev("e10", "SUPPORTING", axis="concentration_dominance", overlap=0.08, scope="concentration_audit", exp_hash="h10"),
            _ev("e11", "SUPPORTING", axis="alternative_explanation_exposure", overlap=0.08, scope="alt_explanation", exp_hash="h11"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"},
        "expected_saturation": {"HIGH", "PARTIAL"},
    },
    {
        "case_id": "BE-12",
        "name": "unresolved_contradiction",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", magnitude="strong"),
            _ev(
                "e2",
                "DISCONFIRMING",
                magnitude="strong",
                overlap=0.12,
                pop="independent_holdout",
                exp_hash="h2",
            ),
        ],
        "expected_states": {"CONFLICTED", "FALSIFIED"},
        "expected_actions": {"SEEK_CONTRADICTION_RESOLUTION", "ABANDON"},
    },
    {
        "case_id": "BE-13",
        "name": "no_executable_high_info",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", overlap=0.98, exp_hash="h2"),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"HOLD_PROVISIONALLY", "HOLD_UNRESOLVED", "SEEK_FALSIFICATION"},
        "executable_high_info_override": [],
    },
    {
        "case_id": "BE-14",
        "name": "falsified_then_support",
        "proposition": PROP_PARTITION,
        "prior_state": "FALSIFIED",
        "evidence": [
            _ev("e1", "DISCONFIRMING", magnitude="strong"),
            _ev("e2", "SUPPORTING", overlap=0.2, exp_hash="h2"),
        ],
        "expected_states": {"FALSIFIED"},
        "expected_actions": {"ABANDON"},
    },
    {
        "case_id": "BE-15",
        "name": "narrow_after_contradiction_temptation",
        "proposition": PROP_PARTITION,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING"),
            _ev(
                "e2",
                "DISCONFIRMING",
                magnitude="strong",
                overlap=0.1,
                pop="narrow_slice",
                scope="cherry_picked_subset",
                exp_hash="h2",
            ),
        ],
        "expected_states": {"CONFLICTED", "FALSIFIED", "WEAKENED"},
        "expected_actions": {"SEEK_CONTRADICTION_RESOLUTION", "ABANDON", "SEEK_REPLICATION"},
        "must_not": {"proposition_mutation", "FORK"},
    },
]


GENERALIZATION_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "GEN-A",
        "name": "context_modulation_support",
        "proposition": PROP_CONTEXT,
        "prior_state": "HYPOTHESIS",
        "evidence": [
            _ev(
                "e1",
                "SUPPORTING",
                feature="context_gate",
                outcome="delta_yield",
                axis="context_modulation_direction",
            ),
        ],
        "expected_states": {"SUPPORTED"},
        "expected_actions": {"SEEK_FALSIFICATION", "SEEK_REPLICATION"},
    },
    {
        "case_id": "GEN-B",
        "name": "context_modulation_conflict",
        "proposition": PROP_CONTEXT,
        "prior_state": "SUPPORTED",
        "evidence": [
            _ev("e1", "SUPPORTING", feature="context_gate", axis="context_modulation_direction"),
            _ev(
                "e2",
                "DISCONFIRMING",
                feature="context_gate",
                axis="context_modulation_direction",
                magnitude="strong",
                overlap=0.1,
                exp_hash="h2",
            ),
        ],
        "expected_states": {"CONFLICTED", "FALSIFIED"},
        "expected_actions": {"SEEK_CONTRADICTION_RESOLUTION", "ABANDON"},
    },
]


def all_bb_cases() -> List[Dict[str, Any]]:
    cases = BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES
    for c in cases:
        assert_development_firewall(c)
    return cases


def run_case(case: Dict[str, Any]) -> Tuple[Any, Any]:
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence

    return synthesize_evidence(
        case["proposition"],
        case["evidence"],
        prior_epistemic_state=case["prior_state"],
    )
