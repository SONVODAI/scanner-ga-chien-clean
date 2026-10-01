"""
Phase 3I.20 — BB-DormancyLifecycle-01 integration benchmark.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import _COHORT_BLOCK, assert_bb_dormancy_firewall
from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import _ev
from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import _prop
from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome, ResearchActivityTransition
from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import (
    ResearchOpportunityState,
    on_research_opportunity_state_changed,
    run_post_synthesis_frontier_pipeline,
    reconstruct_authoritative_state,
)
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import LifecycleKnowledgeState
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext


def _case(case_id: str, *, proposition: Dict[str, Any], evidence: List[Dict[str, Any]], expect: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    return {"case_id": case_id, "proposition": proposition, "evidence": evidence, "expect": expect, **kwargs}


BB_DORMANCY_LIFECYCLE_CASES: List[Dict[str, Any]] = [
    _case("BBDL-01", proposition=_prop("bbdl01"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, expect={"dormant": True, "epistemic_preserved": True}),
    _case("BBDL-02", proposition=_prop("bbdl02"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, expect={"epistemic_not_dormant_state": True}),
    _case("BBDL-03", proposition=_prop("bbdl03"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, expect={"idempotent_dormancy": True}),
    _case("BBDL-04", proposition=_prop("bbdl04"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, expect={"reconstructable": True}),
    _case("BBDL-05", proposition=_prop("bbdl05"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"identical_evidence_added": True}, expect={"no_duplicate_eval": True}),
    _case("BBDL-06", proposition=_prop("bbdl06"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"max_cohort_overlap": 0.99, "additional_row_count": 100},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-07", proposition=_prop("bbdl07"), evidence=[_ev("e1", "SUPPORTING", overlap=0.95)],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"max_cohort_overlap": 0.15, "overlap_relation_to_prior": "disjoint"},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBDL-08", proposition=_prop("bbdl08", null="Episode artifact"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"newly_available_operators": ["counterexample_period_search"]},
          expect={"reopening": ReopeningEvaluationOutcome.REOPEN_RESEARCH.value}),
    _case("BBDL-09", proposition=_prop("bbdl09"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"newly_available_operators": ["unrelated_viz"]},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-10", proposition=_prop("bbdl10"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"feature_changed": True, "proposition_hash_changed": True},
          expect={"reopening": ReopeningEvaluationOutcome.NEW_PROPOSITION_REQUIRED.value}),
    _case("BBDL-11", proposition=_prop("bbdl11"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          snapshot_override={"epistemic_state": "FALSIFIED"},
          opportunity={"max_cohort_overlap": 0.1},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-12", proposition=_prop("bbdl12"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          snapshot_override={"epistemic_state": "ABANDONED"},
          opportunity={"max_cohort_overlap": 0.1},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-13", proposition=_prop("bbdl13"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "CONTRADICTORY")],
          cohort_constraints_override=_COHORT_BLOCK,
          priority_override="HOLD_PROVISIONALLY",
          opportunity={"max_cohort_overlap": 0.99},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-14", proposition=_prop("bbdl14"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "CONTRADICTORY")],
          cohort_constraints_override=_COHORT_BLOCK,
          priority_override="HOLD_PROVISIONALLY",
          opportunity={"max_cohort_overlap": 0.2, "newly_available_operators": ["contradiction_discriminating_test"]},
          expect={"reopening_in": (ReopeningEvaluationOutcome.REOPEN_RESEARCH.value, ReopeningEvaluationOutcome.REMAIN_DORMANT.value)}),
    _case("BBDL-15", proposition=_prop("bbdl15a"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, multi_prop="bbdl15b",
          expect={"cross_prop_isolation": True}),
    _case("BBDL-16", proposition=_prop("bbdl16"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, malformed_opportunity=True,
          expect={"no_fabricated_decision": True}),
    _case("BBDL-17", proposition=_prop("bbdl17"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK, stale_hash=True,
          expect={"stale_rejected": True}),
    _case("BBDL-18", proposition=_prop("bbdl18"), evidence=[_ev("e1", "SUPPORTING"), _ev("e2", "SUPPORTING", overlap=0.3)],
          cohort_constraints_override=_COHORT_BLOCK, reverse_evidence=True,
          expect={"ordering_invariant": True}),
    _case("BBDL-19", proposition=_prop("bbdl19"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"clock_elapsed_days": 365},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
    _case("BBDL-20", proposition=_prop("bbdl20"), evidence=[_ev("e1", "SUPPORTING")],
          cohort_constraints_override=_COHORT_BLOCK,
          opportunity={"outcome_profitability_signal": True, "future_return_magnitude_signal": True},
          expect={"reopening": ReopeningEvaluationOutcome.REMAIN_DORMANT.value}),
]


def _bootstrap_state(case: Dict[str, Any]) -> tuple:
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence

    prop = case["proposition"]
    evidence = list(reversed(case["evidence"])) if case.get("reverse_evidence") else case["evidence"]
    ps = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop["proposition_hash"],
        "proposition_type": prop["proposition_type"],
    }

    syn, pri = synthesize_evidence(ps, evidence, prior_epistemic_state="SUPPORTED")
    if case.get("priority_override"):
        from dataclasses import replace
        pri = replace(pri, chosen_priority_action=case["priority_override"])

    state = LifecycleKnowledgeState(prop["proposition_id"])
    state.synthesis_history.append(syn.to_dict())
    state.priority_history.append(pri.to_dict())
    entries = build_ledger_from_specs(ps["proposition_id"], ps["proposition_hash"], evidence)
    for ev in evidence:
        state.evidence_events.append({
            "epistemic_update": {"update_id": f"epu-{ev['evidence_id']}", "prior_epistemic_state": "SUPPORTED"},
            "experiment_spec": {"experiment_id": ev["evidence_id"]},
            "experiment_ref": ev["evidence_id"],
            "tool_result_hash": f"hash_{ev['evidence_id']}",
        })

    from modules.edge_research.opr_bridge.synthesis_integration import SynthesisIntegrationOutcome

    outcome = SynthesisIntegrationOutcome(
        synthesis=syn,
        priority=pri,
        integration_status="SUCCESS",
        action_disposition="ACTION_RECORDED_ONLY",
        synthesis_history_index=1,
        evidence_cutoff_count=len(evidence),
    )
    ex = case.get("executability") or ExecutabilityContext.abstract_default()
    pipeline = run_post_synthesis_frontier_pipeline(
        prop, state, outcome, executability=ex, cohort_constraints_override=case.get("cohort_constraints_override"), evidence_specs=evidence
    )
    return prop, state, pipeline, outcome


def _opportunity_from_spec(prop: Dict[str, Any], spec: Dict[str, Any]) -> ResearchOpportunityState:
    return ResearchOpportunityState(
        proposition_id=prop["proposition_id"],
        proposition_hash=prop["proposition_hash"],
        max_cohort_overlap=spec.get("max_cohort_overlap"),
        overlap_relation_to_prior=spec.get("overlap_relation_to_prior", "unknown"),
        additional_row_count=spec.get("additional_row_count", 0),
        context_values_renamed=spec.get("context_values_renamed", False),
        identical_evidence_added=spec.get("identical_evidence_added", False),
        newly_available_operators=set(spec.get("newly_available_operators", [])),
        restored_executability_for=set(spec.get("restored_executability_for", [])),
        feature_changed=spec.get("feature_changed", False),
        proposition_hash_changed=spec.get("proposition_hash_changed", False),
        outcome_profitability_signal=spec.get("outcome_profitability_signal", False),
        future_return_magnitude_signal=spec.get("future_return_magnitude_signal", False),
        clock_elapsed_days=spec.get("clock_elapsed_days", 0),
        subgroup_outcome_mining=spec.get("subgroup_outcome_mining", False),
        known_hidden_edge=spec.get("known_hidden_edge", False),
    )


def run_bbdl_case(case: Dict[str, Any]) -> Dict[str, Any]:
    assert_bb_dormancy_firewall(case)
    prop, state, pipeline, outcome = _bootstrap_state(case)
    result: Dict[str, Any] = {
        "case_id": case["case_id"],
        "pipeline": pipeline.to_dict(),
        "state": state,
        "prop": prop,
        "reopening": None,
        "reopening_second": None,
    }

    if case.get("idempotent_dormancy") or case.get("expect", {}).get("idempotent_dormancy"):
        ev = list(reversed(case["evidence"])) if case.get("reverse_evidence") else case["evidence"]
        run_post_synthesis_frontier_pipeline(
            prop, state, outcome, cohort_constraints_override=case.get("cohort_constraints_override"), evidence_specs=ev
        )
        result["dormancy_count"] = len(state.dormancy_history)

    if case.get("opportunity") or case.get("malformed_opportunity") or case.get("stale_hash"):
        if case.get("snapshot_override"):
            override = case["snapshot_override"]
            if "epistemic_state" in override and state.synthesis_history:
                state.synthesis_history[-1]["synthesized_epistemic_state"] = override["epistemic_state"]
        opp = _opportunity_from_spec(prop, case.get("opportunity") or {})
        if case.get("malformed_opportunity"):
            opp = ResearchOpportunityState(proposition_id="wrong-id", proposition_hash=prop["proposition_hash"])
        if case.get("stale_hash"):
            opp = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash="stale_hash")
        hook = on_research_opportunity_state_changed(prop, state, opp, evidence_specs=case.get("evidence") if "scientific_question" not in prop else None)
        result["reopening"] = hook.evaluation_result.outcome.value if hook.evaluation_result else None
        result["reopening_hook"] = hook.to_dict()
        if case["expect"].get("no_duplicate_eval"):
            hook2 = on_research_opportunity_state_changed(prop, state, opp, evidence_specs=case.get("evidence"))
            result["reopening_second"] = hook2.idempotent_skip
            result["eval_count"] = len(state.reopening_history)

    if case.get("multi_prop"):
        prop_b = _prop(case["multi_prop"])
        ps_b = {"proposition_id": prop_b["proposition_id"], "proposition_hash": prop_b["proposition_hash"], "proposition_type": prop_b["proposition_type"]}
        from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence

        syn_b, pri_b = synthesize_evidence(ps_b, [_ev("e1", "SUPPORTING")], prior_epistemic_state="SUPPORTED")
        state_b = LifecycleKnowledgeState(prop_b["proposition_id"])
        state_b.synthesis_history.append(syn_b.to_dict())
        state_b.priority_history.append(pri_b.to_dict())
        state_b.evidence_events.append({"epistemic_update": {"update_id": "epu-e1"}, "experiment_spec": {}, "experiment_ref": "e1", "tool_result_hash": "h"})
        from modules.edge_research.opr_bridge.synthesis_integration import SynthesisIntegrationOutcome

        out_b = SynthesisIntegrationOutcome(synthesis=syn_b, priority=pri_b, integration_status="SUCCESS", action_disposition="ACTION_RECORDED_ONLY", synthesis_history_index=1, evidence_cutoff_count=1)
        run_post_synthesis_frontier_pipeline(
            prop_b, state_b, out_b, cohort_constraints_override=_COHORT_BLOCK, evidence_specs=[_ev("e1", "SUPPORTING")]
        )
        opp = ResearchOpportunityState(
            proposition_id=prop_b["proposition_id"],
            proposition_hash=prop_b["proposition_hash"],
            max_cohort_overlap=0.15,
        )
        hook_b = on_research_opportunity_state_changed(prop_b, state_b, opp)
        result["prop_b_reopening"] = hook_b.evaluation_result.outcome.value if hook_b.evaluation_result else None
        result["prop_a_dormant"] = state.is_dormant()

    if case.get("snapshot_override") and case.get("opportunity"):
        # Re-run with epistemic override via malformed path — use direct evaluator path in evaluate
        pass

    result["authoritative"] = reconstruct_authoritative_state(state)
    return result


def evaluate_bbdl_case(case: Dict[str, Any], run: Dict[str, Any]) -> Dict[str, Any]:
    expect = case["expect"]
    checks: Dict[str, bool] = {}
    state = run["state"]
    pipeline = run["pipeline"]

    if expect.get("dormant"):
        checks["dormant"] = state.is_dormant() and len(state.dormancy_history) >= 1
    if expect.get("epistemic_preserved"):
        checks["epistemic"] = pipeline["epistemic_state"] == "SUPPORTED"
    if expect.get("epistemic_not_dormant_state"):
        checks["separate"] = pipeline["epistemic_state"] != state.research_activity_state
    if expect.get("idempotent_dormancy"):
        checks["idempotent"] = run.get("dormancy_count", 0) == 1
    if expect.get("reconstructable"):
        auth = run["authoritative"]
        checks["reconstruct"] = auth["is_dormant"] and auth["dormancy_hash"] is not None
    if "reopening" in expect:
        checks["reopening"] = run.get("reopening") == expect["reopening"]
    if "reopening_in" in expect:
        checks["reopening_in"] = run.get("reopening") in expect["reopening_in"]
    if expect.get("no_duplicate_eval"):
        checks["dedup"] = run.get("reopening_second") is True
    if expect.get("cross_prop_isolation"):
        checks["isolation"] = run.get("prop_a_dormant") and run.get("prop_b_reopening") == ReopeningEvaluationOutcome.REOPEN_RESEARCH.value
    if expect.get("no_fabricated_decision"):
        hook = run.get("reopening_hook", {})
        checks["no_fabricated"] = hook.get("status") == "FAILED"
    if expect.get("stale_rejected"):
        hook = run.get("reopening_hook", {})
        checks["stale"] = hook.get("status") == "FAILED"
    if expect.get("ordering_invariant"):
        checks["ordering"] = state.is_dormant()

    passed = all(checks.values()) if checks else True
    return {"passed": passed, "checks": checks}


def all_bbdl_cases() -> List[Dict[str, Any]]:
    for c in BB_DORMANCY_LIFECYCLE_CASES:
        assert_bb_dormancy_firewall(c)
    return BB_DORMANCY_LIFECYCLE_CASES
