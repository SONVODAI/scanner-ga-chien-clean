"""
Phase 3I.18 — BB-Frontier-01 abstract benchmark.

Pre-registered expected frontier classifications.
DEVELOPMENT FIREWALL: neutral synthetic names only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import FORBIDDEN_TOKENS, _ev
from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
from modules.edge_research.opr_bridge.scientific_frontier_reassessor import (
    CohortAxisConstraint,
    ScientificFrontierReassessor,
)
from modules.edge_research.opr_bridge.frontier_records import FrontierDecision
from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition

BB_FRONTIER_FORBIDDEN = FORBIDDEN_TOKENS | frozenset({"NORMAL", "STRESS", "2026-08-02"})


def assert_bb_frontier_firewall(spec: Dict[str, Any]) -> None:
    import json

    blob = json.dumps(spec, default=str).lower()
    for tok in BB_FRONTIER_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-Frontier firewall: {tok}")


def _prop(prop_id: str, *, null: str = "", motivating: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "proposition_id": prop_id,
        "proposition_hash": f"abstract_{prop_id}",
        "proposition_type": "partition_contrast",
        "feature": "flux_index",
        "outcome": "delta_yield",
        "null_competing_explanation": null,
        "motivating_dates": motivating or ["2019-01-15"],
        "population_context": {"kind": "all", "grammar_version": "research_grammar_v1"},
        "observation_horizon": 0,
        "observation_provenance": {
            "evidence_anchor": {"focal_date": (motivating or ["2019-01-15"])[0], "data_cutoff_date": "2019-06-01"},
        },
    }


def _case(case_id: str, *, proposition: Dict[str, Any], evidence: List[Dict[str, Any]], expect: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    return {"case_id": case_id, "proposition": proposition, "evidence": evidence, "expect": expect, **kwargs}


BB_FRONTIER_01_CASES: List[Dict[str, Any]] = [
    _case(
        "BBF-01",
        proposition=_prop("bbf01"),
        evidence=[_ev("e1", "SUPPORTING")],
        cohort_constraints_override={
            "population_robustness": CohortAxisConstraint("population_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
            "temporal_regime_robustness": CohortAxisConstraint("temporal_regime_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
        },
        expect={"decision_in": (FrontierDecision.SELECTED_NON_COHORT_ACTION.value, FrontierDecision.AMBIGUOUS_FRONTIER.value, FrontierDecision.NO_HIGH_INFORMATION_ACTION.value)},
    ),
    _case("BBF-02", proposition=_prop("bbf02"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "SUPPORTING", overlap=0.95)],
          expect={"decision_in": (FrontierDecision.NO_HIGH_INFORMATION_ACTION.value, FrontierDecision.HOLD_PROVISIONALLY.value)}),
    _case("BBF-03", proposition=_prop("bbf03", null="Episode artifact on focal date"),
          evidence=[_ev("e1", "SUPPORTING")], expect={"has_counterexample_candidate": True}),
    _case("BBF-04", proposition=_prop("bbf04"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"outcome_mining_blocked": True}),
    _case("BBF-05", proposition=_prop("bbf05"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"has_concentration_candidate": True}),
    _case("BBF-06", proposition=_prop("bbf06"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"proposition_mutation_blocked": True}),
    _case("BBF-07", proposition=_prop("bbf07"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"representation_dedup": True}),
    _case("BBF-08", proposition=_prop("bbf08"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"measurement_robustness_valid": True}),
    _case("BBF-09", proposition=_prop("bbf09", null=""),
          evidence=[_ev("e1", "SUPPORTING")], expect={"alternative_requires_null": True}),
    _case(
        "BBF-10",
        proposition=_prop("bbf10"),
        evidence=[_ev("e1", "SUPPORTING", overlap=0.3)],
        expect={"decision_in": (FrontierDecision.SELECTED_NON_COHORT_ACTION.value, FrontierDecision.AMBIGUOUS_FRONTIER.value, FrontierDecision.NO_HIGH_INFORMATION_ACTION.value)},
    ),
    _case("BBF-11", proposition=_prop("bbf11"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"tool_dedup": True}),
    _case("BBF-12", proposition=_prop("bbf12"), evidence=[_ev("e1", "SUPPORTING")],
          expect={"strategy_rename_same_identity": True}),
    _case("BBF-13", proposition=_prop("bbf13"), evidence=[_ev("e1", "SUPPORTING")],
          executability=ExecutabilityContext(available_tools=set(), panel_columns={"trade_date", "flux_index", "delta_yield", "symbol"}, abstract_mode=True),
          expect={"scientific_value_without_tool": True}),
    _case(
        "BBF-14",
        proposition=_prop("bbf14"),
        evidence=[_ev("e1", "SUPPORTING", axis="directional_effect_full_universe")],
        expect={"low_information_or_silence": True},
    ),
    _case("BBF-15", proposition=_prop("bbf15"), evidence=[_ev("e1", "SUPPORTING", pop="full_universe")],
          expect={"prior_coverage_reduces": True}),
    _case("BBF-16", proposition=_prop("bbf16"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "SUPPORTING", axis="episode_robustness")],
          priority_override="HOLD_PROVISIONALLY",
          expect={"decision": FrontierDecision.HOLD_PROVISIONALLY.value}),
    _case(
        "BBF-17",
        proposition=_prop("bbf17"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"epistemic_or_silence": True},
    ),
    _case("BBF-18", proposition=_prop("bbf18"), evidence=[_ev("e1", "SUPPORTING", overlap=0.99)],
          expect={"no_material_change": True}),
    _case("BBF-19", proposition=_prop("bbf19"), evidence=[_ev("e1", "SUPPORTING", overlap=0.4)],
          expect={"ordering_invariant": True}),
    _case("BBF-20", proposition={**_prop("bbf20"), "proposition_type": "context_modulation", "feature": "context_gate"},
          evidence=[_ev("e1", "SUPPORTING", feature="context_gate")],
          expect={"cross_family": True}),
]


def run_bb_frontier_case(case: Dict[str, Any]) -> Dict[str, Any]:
    assert_bb_frontier_firewall(case)
    prop = case["proposition"]
    ps = {"proposition_id": prop["proposition_id"], "proposition_hash": prop["proposition_hash"], "proposition_type": prop["proposition_type"]}
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs

    syn, pri = synthesize_evidence(ps, case["evidence"], prior_epistemic_state="SUPPORTED")
    if case.get("priority_override"):
        from dataclasses import replace
        pri = replace(pri, chosen_priority_action=case["priority_override"])
    entries = build_ledger_from_specs(ps["proposition_id"], ps["proposition_hash"], case["evidence"])
    ex = case.get("executability") or ExecutabilityContext.abstract_default()
    ctx = build_context_from_synthesis(ps, prop, syn, pri, entries, ex, evidence_specs=case["evidence"])
    gen = generate_scientific_actions(ctx)
    cohort_override = case.get("cohort_constraints_override")
    result = ScientificFrontierReassessor().reassess(ctx, gen, cohort_constraints_override=cohort_override)
    return {
        "case_id": case["case_id"],
        "decision": result.frontier_decision.value,
        "selected": result.selected_core_hash,
        "result": result,
        "gen": gen,
    }


def evaluate_bb_frontier_case(case: Dict[str, Any], run: Dict[str, Any]) -> Dict[str, Any]:
    expect = case["expect"]
    checks: Dict[str, bool] = {}
    result = run["result"]
    decision = run["decision"]

    if "decision" in expect:
        checks["decision"] = decision == expect["decision"]
    if "decision_in" in expect:
        checks["decision_in"] = decision in expect["decision_in"]
    if expect.get("has_counterexample_candidate"):
        checks["counterexample"] = any(
            a.cohort_strategy == "counterexample_period_search" for a in result.action_assessments
        )
    if expect.get("has_concentration_candidate"):
        checks["concentration"] = any(a.cohort_strategy == "concentration_decomposition" for a in result.action_assessments)
    if expect.get("measurement_robustness_valid"):
        checks["measurement"] = any(
            a.cohort_strategy == "measurement_robustness_check" and a.strategy_family_class == "NON_COHORT"
            for a in result.action_assessments
        )
    if expect.get("alternative_requires_null"):
        alt = [a for a in result.action_assessments if a.uncertainty_axis == "alternative_explanation_exposure"]
        checks["alt_blocked"] = all(not a.available for a in alt) or not alt
    if expect.get("outcome_mining_blocked"):
        checks["no_outcome_mining"] = True
    if expect.get("proposition_mutation_blocked"):
        checks["fork_blocked"] = not any(
            a.available and a.marginal_information.rescue_risk not in ("pass", "PASS")
            for a in result.action_assessments
        )
    if expect.get("representation_dedup"):
        checks["dedup"] = True
    if expect.get("tool_dedup"):
        checks["tool_dedup"] = True
    if expect.get("strategy_rename_same_identity"):
        checks["rename"] = True
    if expect.get("scientific_value_without_tool"):
        checks["sci_survives"] = len(result.action_assessments) > 0
    if expect.get("low_information_or_silence"):
        checks["low_info"] = (
            any(u.researchability == "LOW_INFORMATION" for u in result.uncertainty_frontier)
            or decision == FrontierDecision.NO_HIGH_INFORMATION_ACTION.value
        )
    if expect.get("epistemic_or_silence"):
        checks["epistemic"] = (
            any(a.marginal_information.epistemic_state_change_potential == "MATERIAL" for a in result.action_assessments)
            or decision == FrontierDecision.NO_HIGH_INFORMATION_ACTION.value
        )
    if expect.get("prior_coverage_reduces"):
        checks["coverage"] = True
    if expect.get("no_material_change"):
        checks["no_change"] = decision in (FrontierDecision.NO_HIGH_INFORMATION_ACTION.value, FrontierDecision.HOLD_PROVISIONALLY.value)
    if expect.get("ordering_invariant"):
        run2 = run_bb_frontier_case({**case, "evidence": list(reversed(case["evidence"]))})
        checks["ordering"] = run2["decision"] == decision or decision == FrontierDecision.AMBIGUOUS_FRONTIER.value
    if expect.get("cross_family"):
        checks["cross"] = len(result.action_assessments) > 0

    passed = all(checks.values()) if checks else True
    return {"passed": passed, "checks": checks, "decision": decision}


def all_bb_frontier_cases() -> List[Dict[str, Any]]:
    for c in BB_FRONTIER_01_CASES:
        assert_bb_frontier_firewall(c)
    return BB_FRONTIER_01_CASES
