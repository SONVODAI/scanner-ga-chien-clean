"""
Phase 3I.19 — BB-Dormancy-01 abstract benchmark.

Pre-registered expected dormancy / reopening classifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import FORBIDDEN_TOKENS, _ev
from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import assert_bb_frontier_firewall, _prop
from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
from modules.edge_research.opr_bridge.dormancy_deriver import derive_dormancy_record, should_enter_dormancy
from modules.edge_research.opr_bridge.dormancy_records import ResearchActivityState, ReopeningEvaluationOutcome
from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import (
    CurrentResearchSnapshot,
    DormantResearchReopeningEvaluator,
    ResearchOpportunityDescriptor,
)
from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.opr_bridge.frontier_records import FrontierDecision
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
from modules.edge_research.opr_bridge.scientific_frontier_reassessor import CohortAxisConstraint, ScientificFrontierReassessor

BB_DORMANCY_FORBIDDEN = FORBIDDEN_TOKENS | frozenset({"NORMAL", "STRESS", "2026-08-02", "t5_return", "rs_spread"})


def assert_bb_dormancy_firewall(spec: Dict[str, Any]) -> None:
    import json

    blob = json.dumps(spec, default=str).lower()
    for tok in BB_DORMANCY_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-Dormancy firewall: {tok}")


def _case(case_id: str, *, proposition: Dict[str, Any], evidence: List[Dict[str, Any]], expect: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    return {"case_id": case_id, "proposition": proposition, "evidence": evidence, "expect": expect, **kwargs}


_COHORT_BLOCK = {
    "population_robustness": CohortAxisConstraint("population_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
    "temporal_regime_robustness": CohortAxisConstraint("temporal_regime_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
}

BB_DORMANCY_01_CASES: List[Dict[str, Any]] = [
    _case("BBD-01", proposition=_prop("bbd01"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          expect={"enters_dormancy": True, "activity_state": ResearchActivityState.DORMANT.value}),
    _case("BBD-02", proposition=_prop("bbd02"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"identical_evidence_added": True},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-03", proposition=_prop("bbd03"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"additional_row_count": 500, "new_evidence_overlap": 0.99},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-04", proposition=_prop("bbd04"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"new_evidence_overlap": 0.2, "overlap_relation_to_prior": "disjoint"},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBD-05", proposition=_prop("bbd05"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"context_values_renamed": True, "new_evidence_overlap": 0.98},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-06", proposition=_prop("bbd06"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"newly_available_operators": {"renamed_tier_compare"}},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-07", proposition=_prop("bbd07", null="Episode artifact"),
          evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"newly_available_operators": {"counterexample_period_search"}},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBD-08", proposition=_prop("bbd08"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"newly_available_operators": {"unrelated_visualization_tool"}},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-09", proposition=_prop("bbd09"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"feature_changed": True, "proposition_hash_changed": True},
          expect={"reopening": ReopeningEvaluationOutcome.NEW_PROPOSITION_REQUIRED.value}),
    _case("BBD-10", proposition=_prop("bbd10"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          snapshot_override={"epistemic_state": "FALSIFIED"},
          opportunity={"new_evidence_overlap": 0.2},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-11", proposition=_prop("bbd11"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "CONTRADICTORY", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          priority_override="HOLD_PROVISIONALLY",
          snapshot_override={"epistemic_state": "CONFLICTED"},
          opportunity={"new_evidence_overlap": 0.2},
          expect={"reopening_in": (ReopeningEvaluationOutcome.REOPEN_RESEARCH.value, ReopeningEvaluationOutcome.REMAIN_DORMANT.value)}),
    _case("BBD-12", proposition=_prop("bbd12"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"restored_executability_for": {"concentration_decomposition"}},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBD-13", proposition=_prop("bbd13"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "SUPPORTING", axis="episode_robustness")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"identical_evidence_added": True},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-14", proposition=_prop("bbd14"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"new_evidence_overlap": 0.15, "overlap_relation_to_prior": "complement"},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBD-15", proposition=_prop("bbd15"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"clock_elapsed_days": 365},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-16", proposition=_prop("bbd16"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"known_hidden_edge": True, "outcome_profitability_signal": True},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-17", proposition=_prop("bbd17"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"future_return_magnitude_signal": True, "subgroup_outcome_mining": True},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-18", proposition=_prop("bbd18"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"new_evidence_overlap": 0.2, "trigger_source": "dup"},
          expect={"reopening_first": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value, "reopening_second": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBD-19", proposition=_prop("bbd19"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"new_evidence_overlap": 0.25, "newly_available_operators": {"concentration_decomposition"}},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value, "multiple_conditions": True}),
    _case("BBD-20", proposition={**_prop("bbd20"), "proposition_type": "context_modulation", "feature": "context_gate"},
          evidence=[_ev("e1", "SUPPORTING", feature="context_gate")],
          cohort_constraints_override=_COHORT_BLOCK,
          expect={"enters_dormancy": True}),
]


def _build_ctx(case: Dict[str, Any]):
    prop = case["proposition"]
    ps = {"proposition_id": prop["proposition_id"], "proposition_hash": prop["proposition_hash"], "proposition_type": prop["proposition_type"]}
    syn, pri = synthesize_evidence(ps, case["evidence"], prior_epistemic_state=case.get("prior_epistemic", "SUPPORTED"))
    if case.get("priority_override"):
        from dataclasses import replace
        pri = replace(pri, chosen_priority_action=case["priority_override"])
    entries = build_ledger_from_specs(ps["proposition_id"], ps["proposition_hash"], case["evidence"])
    ex = case.get("executability") or ExecutabilityContext.abstract_default()
    ctx = build_context_from_synthesis(ps, prop, syn, pri, entries, ex, evidence_specs=case["evidence"])
    return ctx, ps, prop


def run_bb_dormancy_case(case: Dict[str, Any]) -> Dict[str, Any]:
    assert_bb_dormancy_firewall(case)
    ctx, ps, prop = _build_ctx(case)
    gen = generate_scientific_actions(ctx)
    cohort_override = case.get("cohort_constraints_override")
    frontier = ScientificFrontierReassessor().reassess(ctx, gen, cohort_constraints_override=cohort_override)
    dormancy = derive_dormancy_record(ctx, frontier)

    result: Dict[str, Any] = {
        "case_id": case["case_id"],
        "frontier_decision": frontier.frontier_decision.value,
        "dormancy": dormancy,
        "ctx": ctx,
        "prop": prop,
    }

    if dormancy and case.get("opportunity") is not None:
        opp_spec = case["opportunity"]
        snap_override = case.get("snapshot_override", {})
        snapshot = CurrentResearchSnapshot(
            proposition_id=ctx.proposition_id,
            proposition_hash=ctx.proposition_hash,
            proposition_record=prop,
            epistemic_state=snap_override.get("epistemic_state", ctx.synthesis.synthesized_epistemic_state),
            unresolved_uncertainties=set(ctx.unresolved_axes),
            covered_axes=ctx.covered_axes,
            redundant_axes=ctx.redundant_axes,
            max_cohort_overlap=ctx.max_cohort_overlap,
            available_operators=set(ctx.executability.available_tools),
        )
        opportunity = ResearchOpportunityDescriptor(
            new_evidence_overlap=opp_spec.get("new_evidence_overlap"),
            overlap_relation_to_prior=opp_spec.get("overlap_relation_to_prior", "unknown"),
            additional_row_count=opp_spec.get("additional_row_count", 0),
            context_values_renamed=opp_spec.get("context_values_renamed", False),
            identical_evidence_added=opp_spec.get("identical_evidence_added", False),
            newly_available_operators=set(opp_spec.get("newly_available_operators", [])),
            restored_executability_for=set(opp_spec.get("restored_executability_for", [])),
            proposition_hash_changed=opp_spec.get("proposition_hash_changed", False),
            feature_changed=opp_spec.get("feature_changed", False),
            outcome_changed=opp_spec.get("outcome_changed", False),
            horizon_changed=opp_spec.get("horizon_changed", False),
            population_claim_changed=opp_spec.get("population_claim_changed", False),
            outcome_profitability_signal=opp_spec.get("outcome_profitability_signal", False),
            future_return_magnitude_signal=opp_spec.get("future_return_magnitude_signal", False),
            zone_c_match=opp_spec.get("zone_c_match", False),
            human_review_request=opp_spec.get("human_review_request", False),
            subgroup_outcome_mining=opp_spec.get("subgroup_outcome_mining", False),
            known_hidden_edge=opp_spec.get("known_hidden_edge", False),
            clock_elapsed_days=opp_spec.get("clock_elapsed_days", 0),
            resolved_uncertainties=set(opp_spec.get("resolved_uncertainties", [])),
            trigger_source=opp_spec.get("trigger_source", case["case_id"]),
        )
        evaluator = DormantResearchReopeningEvaluator()
        reopen = evaluator.evaluate(dormancy, snapshot, opportunity)
        result["reopening"] = reopen.outcome.value
        result["reopening_rationale"] = reopen.rationale

        if case["expect"].get("reopening_second") is not None:
            from modules.edge_research.opr_bridge.dormancy_records import ResearchMemoryLedger

            memory = ResearchMemoryLedger()
            memory.append_evaluation(reopen)
            reopen2 = evaluator.evaluate(dormancy, snapshot, opportunity, memory=memory)
            result["reopening_second"] = reopen2.outcome.value

    return result


def evaluate_bb_dormancy_case(case: Dict[str, Any], run: Dict[str, Any]) -> Dict[str, Any]:
    expect = case["expect"]
    checks: Dict[str, bool] = {}

    if expect.get("enters_dormancy"):
        checks["dormancy_created"] = run["dormancy"] is not None
        checks["should_enter"] = should_enter_dormancy(run["frontier_decision"])
    if "activity_state" in expect:
        checks["activity_state"] = run["dormancy"] and run["dormancy"].research_activity_state == expect["activity_state"]
    if "reopening" in expect:
        checks["reopening"] = run.get("reopening") == expect["reopening"]
    if "reopening_in" in expect:
        checks["reopening_in"] = run.get("reopening") in expect["reopening_in"]
    if "reopening_first" in expect:
        checks["reopening_first"] = run.get("reopening") == expect["reopening_first"]
    if "reopening_second" in expect:
        checks["reopening_second"] = run.get("reopening_second") == expect["reopening_second"]
    if expect.get("multiple_conditions"):
        dormancy = run.get("dormancy")
        checks["multiple_conditions"] = dormancy is not None and len(dormancy.reopening_conditions) >= 2

    passed = all(checks.values()) if checks else True
    return {"passed": passed, "checks": checks}


def all_bb_dormancy_cases() -> List[Dict[str, Any]]:
    for c in BB_DORMANCY_01_CASES:
        assert_bb_dormancy_firewall(c)
    return BB_DORMANCY_01_CASES
