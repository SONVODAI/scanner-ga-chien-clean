#!/usr/bin/env python3
"""Phase 3I.20 — Dormancy lifecycle integration diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_bb_dormancy_regression() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import all_bb_dormancy_cases, evaluate_bb_dormancy_case, run_bb_dormancy_case

    results = []
    for case in all_bb_dormancy_cases():
        run = run_bb_dormancy_case(case)
        ev = evaluate_bb_dormancy_case(case, run)
        results.append({"case_id": case["case_id"], "passed": ev["passed"]})
    passed = sum(1 for r in results if r["passed"])
    return {"benchmark": "BB-Dormancy-01-regression", "passed": passed, "case_count": len(results), "all_passed": passed == len(results)}


def run_bb_lifecycle() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_dormancy_lifecycle_01_fixtures import all_bbdl_cases, evaluate_bbdl_case, run_bbdl_case

    results = []
    for case in all_bbdl_cases():
        run = run_bbdl_case(case)
        ev = evaluate_bbdl_case(case, run)
        results.append({"case_id": case["case_id"], "passed": ev["passed"], "checks": ev["checks"]})
    passed = sum(1 for r in results if r["passed"])
    return {"benchmark": "BB-DormancyLifecycle-01", "passed": passed, "case_count": len(results), "all_passed": passed == len(results), "results": results}


def run_counterfactuals() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_dormancy_lifecycle_01_fixtures import all_bbdl_cases, run_bbdl_case, _bootstrap_state, _opportunity_from_spec
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import ResearchOpportunityState, on_research_opportunity_state_changed, run_post_synthesis_frontier_pipeline
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor
    from modules.edge_research.opr_bridge.scientific_action_generator import generate_scientific_actions

    base = next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-01")
    prop, state, pipeline, outcome = _bootstrap_state(base)
    cf: Dict[str, Any] = {}

    # CF-L1: dormancy auto-created on exhaustion; skipped when frontier has actionable selection
    cf["CF-L1"] = {
        "passed": state.is_dormant()
        and pipeline.frontier.frontier_decision.value == "NO_HIGH_INFORMATION_ACTION"
        and len(state.dormancy_history) >= 1,
    }
    from modules.edge_research.opr_bridge.frontier_records import FrontierDecision
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import on_scientific_frontier_completed, build_action_context_from_lifecycle
    from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import LifecycleKnowledgeState
    from dataclasses import replace

    state_skip = LifecycleKnowledgeState(prop["proposition_id"])
    state_skip.synthesis_history = list(state.synthesis_history)
    state_skip.priority_history = list(state.priority_history)
    state_skip.evidence_events = list(state.evidence_events)
    state_skip._abstract_evidence_specs = base["evidence"]
    ctx = build_action_context_from_lifecycle(prop, state_skip, evidence_specs=base["evidence"])
    frontier_selected = replace(
        pipeline.frontier,
        frontier_decision=FrontierDecision.SELECTED_NON_COHORT_ACTION,
    )
    hook_skip = on_scientific_frontier_completed(prop, state_skip, frontier_selected, ctx)
    cf["CF-L1"]["skip_when_selected"] = hook_skip.status == "SKIPPED" and len(state_skip.dormancy_history) == 0
    cf["CF-L1"]["passed"] = cf["CF-L1"]["passed"] and cf["CF-L1"]["skip_when_selected"]

    # CF-L2: epistemic separate from dormancy
    cf["CF-L2"] = {"passed": pipeline.epistemic_state == "SUPPORTED" and state.research_activity_state == "DORMANT"}

    # CF-L3/C4/C5 via BBDL cases
    r7 = run_bbdl_case(next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-07"))
    r9 = run_bbdl_case(next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-09"))
    cf["CF-L3"] = {"passed": r9.get("reopening") == "REMAIN_DORMANT"}
    cf["CF-L4"] = {"passed": r7.get("reopening") == "REOPEN_RESEARCH"}

    r8 = run_bbdl_case(next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-08"))
    cf["CF-L5"] = {"passed": r8.get("reopening") == "REOPEN_RESEARCH"}

    r10 = run_bbdl_case(next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-10"))
    cf["CF-L6"] = {"passed": r10.get("reopening") == "NEW_PROPOSITION_REQUIRED"}

    opp = ResearchOpportunityState(proposition_id="wrong", proposition_hash=prop["proposition_hash"])
    hook = on_research_opportunity_state_changed(prop, state, opp, evidence_specs=base["evidence"])
    cf["CF-L7"] = {"passed": hook.status == "FAILED"}

    r18 = run_bbdl_case(next(c for c in all_bbdl_cases() if c["case_id"] == "BBDL-18"))
    cf["CF-L8"] = {"passed": r18["state"].is_dormant()}

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict))
    return cf


def run_t2_replay() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.dormancy_audit import learning_vs_answer_leakage_audit, lifecycle_integration_leakage_audit
    from modules.edge_research.opr_bridge.evidence_ledger_builder import build_ledger_specs_from_events
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import (
        ResearchOpportunityState,
        integration_content_hash,
        on_research_opportunity_state_changed,
        reconstruct_authoritative_state,
        run_post_synthesis_frontier_pipeline,
        verify_frozen_scientific_integrity,
    )
    from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import LifecycleKnowledgeState, on_epistemic_update_completed
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome

    prop, events = load_real_lifecycle_events()
    state = LifecycleKnowledgeState(prop["proposition_id"])

    for event in events:
        state, outcome = on_epistemic_update_completed(
            prop,
            event["epistemic_update"],
            event.get("experiment_spec", {}),
            event.get("experiment_ref", ""),
            event.get("tool_result_hash", ""),
            knowledge_state=state,
            deterministic_replay=True,
        )

    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    last_outcome = state.outcomes[-1]
    pipeline = run_post_synthesis_frontier_pipeline(prop, state, last_outcome, executability=ex)

    auth = reconstruct_authoritative_state(state)

    # Synthetic opportunity demonstrations (abstract, not future market)
    dormancy = state.latest_dormancy()
    prop_hash = prop.get("proposition_hash") or dormancy.get("proposition_hash", "")
    syn_demo: Dict[str, Any] = {}

    opp_a = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash=prop_hash, max_cohort_overlap=0.99, additional_row_count=500)
    r_a = on_research_opportunity_state_changed(prop, state, opp_a)
    syn_demo["A_redundant_data"] = r_a.evaluation_result.outcome.value if r_a.evaluation_result else r_a.status

    state_b = LifecycleKnowledgeState(prop["proposition_id"])
    for k, v in state.__dict__.items():
        if k != "proposition_id":
            setattr(state_b, k, v if not isinstance(v, list) else list(v))
    state_b.reopening_history = list(state.reopening_history)
    state_b._opportunity_hashes_seen = list(state._opportunity_hashes_seen)

    opp_b = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash=prop_hash, max_cohort_overlap=0.15, overlap_relation_to_prior="disjoint")
    r_b = on_research_opportunity_state_changed(prop, state_b, opp_b)
    syn_demo["B_independent_structure"] = r_b.evaluation_result.outcome.value if r_b.evaluation_result else r_b.status

    opp_c = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash=prop_hash, newly_available_operators={"counterexample_period_search"})
    r_c = on_research_opportunity_state_changed(prop, state_b, opp_c)
    syn_demo["C_relevant_capability"] = r_c.evaluation_result.outcome.value if r_c.evaluation_result else r_c.status

    opp_d = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash=prop_hash, newly_available_operators={"unrelated_visualization"})
    r_d = on_research_opportunity_state_changed(prop, state_b, opp_d)
    syn_demo["D_irrelevant_capability"] = r_d.evaluation_result.outcome.value if r_d.evaluation_result else r_d.status

    opp_e = ResearchOpportunityState(proposition_id=prop["proposition_id"], proposition_hash=prop_hash, feature_changed=True, proposition_hash_changed=True)
    r_e = on_research_opportunity_state_changed(prop, state_b, opp_e)
    syn_demo["E_semantic_drift"] = r_e.evaluation_result.outcome.value if r_e.evaluation_result else r_e.status

    integrity = verify_frozen_scientific_integrity()

    return {
        "execution_status": "NOT_EXECUTED",
        "frozen_integrity": integrity,
        "integration_content_hash": integration_content_hash(),
        "epistemic_state": auth.get("epistemic_state"),
        "frontier_decision": auth.get("frontier_decision"),
        "research_activity_state": auth.get("research_activity_state"),
        "dormancy_hash": auth.get("dormancy_hash"),
        "reopening_conditions_count": auth.get("reopening_conditions_count"),
        "authoritative_state": auth,
        "pipeline": pipeline.to_dict(),
        "synthetic_opportunity_demos": syn_demo,
        "learning_vs_answer_leakage": learning_vs_answer_leakage_audit(),
        "lifecycle_integration_leakage": lifecycle_integration_leakage_audit(),
        "future_result_blindness": {"experiment_executed": False, "tool_result_accessed": False},
    }


def main() -> None:
    head = _git_head()
    bb19 = run_bb_dormancy_regression()
    _write("01_bb_dormancy_01_regression.json", bb19)
    bb20 = run_bb_lifecycle()
    _write("02_bb_dormancy_lifecycle_01.json", bb20)
    cf = run_counterfactuals()
    _write("03_counterfactuals.json", cf)
    assert bb19["all_passed"] and bb20["all_passed"], "Benchmarks must pass"
    t2 = run_t2_replay()
    _write("04_t2_lifecycle_replay.json", t2)
    verdict = (
        "DORMANCY_LIFECYCLE_INTEGRATION_PASS"
        if bb19["all_passed"]
        and bb20["all_passed"]
        and cf.get("all_passed")
        and t2["frozen_integrity"]["passed"]
        and t2["epistemic_state"] == "SUPPORTED"
        and t2["frontier_decision"] == "NO_HIGH_INFORMATION_ACTION"
        and t2["research_activity_state"] == "DORMANT"
        and t2["lifecycle_integration_leakage"]["passed"]
        else "DORMANCY_LIFECYCLE_INTEGRATION_PARTIAL"
    )
    _write("05_audit_summary.json", {"phase": "3I.20", "head": head, "verdict": verdict, "execution_status": "NOT_EXECUTED"})
    print(f"Phase 3I.20 — BB19 {bb19['passed']}/{bb19['case_count']} — BB20 {bb20['passed']}/{bb20['case_count']} — T2 {t2['research_activity_state']} — {verdict}")


if __name__ == "__main__":
    main()
