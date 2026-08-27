"""
Phase 3J.1 — BB-FirstExperiment-01 benchmark design (pre-registered, audit-only).

Abstract cases spanning multiple proposition families. NOT wired to production selector.
Evaluated against current mechanism inventory in readiness audit.
"""

from __future__ import annotations

from typing import Any, Dict, List

BENCHMARK_VERSION = "bb_first_experiment_01_design_v1_3j1"
FIREWALL_FORBIDDEN = frozenset(
    {"rs_spread", "t5_return", "prop-efb650d9bd5c451f", "zone_c", "hidden_phenomenon"}
)


def all_bbfe_cases() -> List[Dict[str, Any]]:
    """20 pre-registered adversarial cases — design specifications only."""
    return [
        {"case_id": "BBFE-01", "family": "flux_tier_dispersion", "scenario": "obvious_direct_test", "expect": "DIRECT_INITIAL_TEST may win if independent"},
        {"case_id": "BBFE-02", "family": "flux_tier_dispersion", "scenario": "confirmatory_only_lure", "expect": "CONFIRMATORY_ONLY rejected"},
        {"case_id": "BBFE-03", "family": "delta_yield_gate", "scenario": "same_evidence_different_tool", "expect": "same scientific identity"},
        {"case_id": "BBFE-04", "family": "flux_tier_dispersion", "scenario": "birth_evidence_duplication", "expect": "REDUNDANT_WITH_BIRTH_EVIDENCE rejected"},
        {"case_id": "BBFE-05", "family": "context_gate_modulation", "scenario": "independent_cohort", "expect": "independence HIGH"},
        {"case_id": "BBFE-06", "family": "context_gate_modulation", "scenario": "non_independent_cohort", "expect": "overlap penalty"},
        {"case_id": "BBFE-07", "family": "delta_yield_gate", "scenario": "rescue_by_horizon_mutation", "expect": "RESCUE_MUTATION or NEW_PROPOSITION_REQUIRED"},
        {"case_id": "BBFE-08", "family": "flux_tier_dispersion", "scenario": "rescue_by_population_narrowing", "expect": "RESCUE_MUTATION rejected"},
        {"case_id": "BBFE-09", "family": "modulation_axis", "scenario": "outcome_mutation", "expect": "NEW_PROPOSITION_REQUIRED"},
        {"case_id": "BBFE-10", "family": "flux_tier_dispersion", "scenario": "representation_only_candidate", "expect": "REPRESENTATION_ONLY rejected"},
        {"case_id": "BBFE-11", "family": "delta_yield_gate", "scenario": "two_equivalent_tools", "expect": "single scientific winner"},
        {"case_id": "BBFE-12", "family": "context_gate_modulation", "scenario": "invalid_evidence_path", "expect": "NON_INFORMATIVE or reject"},
        {"case_id": "BBFE-13", "family": "modulation_axis", "scenario": "non_executable_best_idea", "expect": "NOT_EXECUTABLE or AMBIGUOUS_FIRST_EXPERIMENT"},
        {"case_id": "BBFE-14", "family": "flux_tier_dispersion", "scenario": "ambiguous_tie", "expect": "AMBIGUOUS_FIRST_EXPERIMENT"},
        {"case_id": "BBFE-15", "family": "delta_yield_gate", "scenario": "valid_silence", "expect": "NO_HIGH_INFORMATION_FIRST_EXPERIMENT"},
        {"case_id": "BBFE-16", "family": "flux_tier_dispersion", "scenario": "proposition_fully_encoded_by_birth", "expect": "NO_HIGH_INFORMATION_FIRST_EXPERIMENT"},
        {"case_id": "BBFE-17", "family": "context_gate_modulation", "scenario": "counterexample_capable_test", "expect": "FALSIFICATION_CAPABLE preferred"},
        {"case_id": "BBFE-18", "family": "modulation_axis", "scenario": "candidate_order_perturbation", "expect": "winner invariant"},
        {"case_id": "BBFE-19", "family": "delta_yield_gate", "scenario": "tool_order_perturbation", "expect": "winner invariant"},
        {"case_id": "BBFE-20", "family": "volatility_surface_skew", "scenario": "abstract_family_not_dispersion_return", "expect": "objective from proposition structure"},
    ]


def assert_bbfe_firewall(case: Dict[str, Any]) -> Dict[str, Any]:
    blob = str(case).lower()
    violations = [t for t in FIREWALL_FORBIDDEN if t in blob and t not in ("rs_spread", "t5_return")]
    return {"passed": len(violations) == 0, "violations": violations}
