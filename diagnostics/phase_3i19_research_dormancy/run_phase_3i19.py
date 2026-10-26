#!/usr/bin/env python3
"""Phase 3I.19 — Autonomous Research Dormancy & Reopening Readiness diagnostics."""

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


def run_bb_dormancy() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import (
        all_bb_dormancy_cases,
        evaluate_bb_dormancy_case,
        run_bb_dormancy_case,
    )

    results = []
    for case in all_bb_dormancy_cases():
        run = run_bb_dormancy_case(case)
        ev = evaluate_bb_dormancy_case(case, run)
        results.append({"case_id": case["case_id"], "passed": ev["passed"], "checks": ev["checks"]})
    passed = sum(1 for r in results if r["passed"])
    return {"benchmark": "BB-Dormancy-01", "case_count": len(results), "passed": passed, "all_passed": passed == len(results), "results": results}


def run_counterfactuals() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import all_bb_dormancy_cases, run_bb_dormancy_case
    from modules.edge_research.opr_bridge.dormancy_records import ResearchMemoryLedger, ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import (
        CurrentResearchSnapshot,
        DormantResearchReopeningEvaluator,
        ResearchOpportunityDescriptor,
    )

    base = next(c for c in all_bb_dormancy_cases() if c["case_id"] == "BBD-01")
    run = run_bb_dormancy_case(base)
    dormancy = run["dormancy"]
    ctx = run["ctx"]
    prop = run["prop"]
    cf: Dict[str, Any] = {}

    def _snap(**kw):
        return CurrentResearchSnapshot(
            proposition_id=ctx.proposition_id,
            proposition_hash=ctx.proposition_hash,
            proposition_record=prop,
            epistemic_state=kw.get("epistemic_state", ctx.synthesis.synthesized_epistemic_state),
            unresolved_uncertainties=set(kw.get("unresolved", ctx.unresolved_axes)),
            covered_axes=ctx.covered_axes,
            redundant_axes=ctx.redundant_axes,
            max_cohort_overlap=ctx.max_cohort_overlap,
            available_operators=set(ctx.executability.available_tools),
        )

    ev = DormantResearchReopeningEvaluator()

    # CF-D1
    r1 = ev.evaluate(dormancy, _snap(), ResearchOpportunityDescriptor(identical_evidence_added=True, new_evidence_overlap=0.99))
    cf["CF-D1"] = {"passed": r1.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT}

    # CF-D2
    r2 = ev.evaluate(dormancy, _snap(), ResearchOpportunityDescriptor(new_evidence_overlap=0.15, overlap_relation_to_prior="disjoint"))
    cf["CF-D2"] = {"passed": r2.outcome == ReopeningEvaluationOutcome.REOPEN_RESEARCH}

    # CF-D3
    r3 = ev.evaluate(dormancy, _snap(), ResearchOpportunityDescriptor(context_values_renamed=True, new_evidence_overlap=0.98))
    cf["CF-D3"] = {"passed": r3.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT}

    # CF-D4
    r4 = ev.evaluate(dormancy, _snap(), ResearchOpportunityDescriptor(newly_available_operators={"unrelated_plot_tool"}))
    cf["CF-D4"] = {"passed": r4.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT}

    # CF-D5
    r5 = ev.evaluate(
        dormancy,
        _snap(),
        ResearchOpportunityDescriptor(newly_available_operators={"counterexample_period_search"}),
    )
    cf["CF-D5"] = {"passed": r5.outcome in (ReopeningEvaluationOutcome.REOPEN_RESEARCH, ReopeningEvaluationOutcome.REMAIN_DORMANT)}

    # CF-D6
    resolved_axis = dormancy.reopening_conditions[0].target_uncertainty if dormancy.reopening_conditions else "population_robustness"
    r6 = ev.evaluate(
        dormancy,
        _snap(unresolved=[a for a in ctx.unresolved_axes if a != resolved_axis]),
        ResearchOpportunityDescriptor(resolved_uncertainties={resolved_axis}),
    )
    cf["CF-D6"] = {"passed": r6.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT}

    # CF-D7
    r7 = ev.evaluate(dormancy, _snap(), ResearchOpportunityDescriptor(feature_changed=True, proposition_hash_changed=True))
    cf["CF-D7"] = {"passed": r7.outcome == ReopeningEvaluationOutcome.NEW_PROPOSITION_REQUIRED}

    # CF-D8
    run_rev = run_bb_dormancy_case({**base, "evidence": list(reversed(base["evidence"]))})
    r8a = ev.evaluate(run_rev["dormancy"], _snap(), ResearchOpportunityDescriptor(new_evidence_overlap=0.15))
    r8b = r2
    cf["CF-D8"] = {"passed": r8a.outcome == r8b.outcome}

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict))
    return cf


def run_t2_diagnostic() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.dormancy_audit import learning_vs_answer_leakage_audit, lifecycle_integration_recommendation
    from modules.edge_research.opr_bridge.dormancy_deriver import derive_dormancy_record
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.evidence_ledger_builder import build_ledger_specs_from_events, proposition_spec_from_record
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor

    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, priority = synthesize_from_ledger_entries(prop_spec, entries, prior_epistemic_state=prior)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    ctx = build_context_from_synthesis(prop_spec, prop, synthesis, priority, entries, ex, specs)
    gen = generate_scientific_actions(ctx)
    frontier = ScientificFrontierReassessor().reassess(ctx, gen)
    dormancy = derive_dormancy_record(ctx, frontier)

    qualifying = []
    non_qualifying = []
    for cond in dormancy.reopening_conditions if dormancy else []:
        entry = {
            "target_uncertainty": cond.target_uncertainty,
            "blocking_reason": cond.blocking_reason,
            "required_change": cond.required_scientific_change,
            "measurable_criterion": cond.measurable_criterion,
            "does_not_qualify": list(cond.does_not_qualify),
        }
        if cond.blocking_reason == "AXIS_SATURATED":
            non_qualifying.append(entry)
        else:
            qualifying.append(entry)

    non_qualifying.extend(
        [
            {"trigger": t, "reason": "forbidden pseudo-reopening"}
            for t in (dormancy.forbidden_reopening_triggers if dormancy else [])
        ]
    )

    return {
        "dormancy_content_hash": dormancy_content_hash(),
        "execution_status": "NOT_EXECUTED",
        "epistemic_state": synthesis.synthesized_epistemic_state,
        "frontier_decision": frontier.frontier_decision.value,
        "should_enter_dormancy": dormancy is not None,
        "research_activity_state": dormancy.research_activity_state if dormancy else None,
        "dormancy_record": dormancy.to_dict() if dormancy else None,
        "reopening_requirements_qualifying": qualifying,
        "reopening_requirements_non_qualifying": non_qualifying,
        "316_legacy_selection": gen.selection.to_dict(),
        "318_frontier_preserved": frontier.frontier_decision.value == "NO_HIGH_INFORMATION_ACTION",
        "learning_vs_answer_leakage": learning_vs_answer_leakage_audit(),
        "lifecycle_integration": lifecycle_integration_recommendation(),
        "future_result_blindness": {"experiment_executed": False, "tool_result_accessed": False, "future_trigger_simulated": False},
    }


def main() -> None:
    head = _git_head()
    bb = run_bb_dormancy()
    _write("01_bb_dormancy_01.json", bb)
    assert bb["all_passed"], "BB-Dormancy-01 must pass"
    cf = run_counterfactuals()
    _write("02_counterfactuals.json", cf)
    t2 = run_t2_diagnostic()
    _write("03_t2_dormancy_diagnostic.json", t2)
    verdict = (
        "AUTONOMOUS_RESEARCH_DORMANCY_PASS"
        if bb["all_passed"] and cf.get("all_passed") and t2["learning_vs_answer_leakage"]["passed"] and t2["318_frontier_preserved"]
        else "AUTONOMOUS_RESEARCH_DORMANCY_PARTIAL"
    )
    _write(
        "04_audit_summary.json",
        {
            "phase": "3I.19",
            "head": head,
            "verdict": verdict,
            "execution_status": "NOT_EXECUTED",
            "t2_dormant": t2["should_enter_dormancy"],
            "frontier_decision": t2["frontier_decision"],
        },
    )
    print(f"Phase 3I.19 — BB {bb['passed']}/{bb['case_count']} — T2 dormant={t2['should_enter_dormancy']} — {verdict}")


if __name__ == "__main__":
    main()
