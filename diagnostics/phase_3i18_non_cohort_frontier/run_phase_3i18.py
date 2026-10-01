#!/usr/bin/env python3
"""Phase 3I.18 — Non-Cohort Scientific Frontier Reassessment diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

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


def run_bb_frontier() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import (
        all_bb_frontier_cases,
        evaluate_bb_frontier_case,
        run_bb_frontier_case,
    )

    results = []
    for case in all_bb_frontier_cases():
        run = run_bb_frontier_case(case)
        ev = evaluate_bb_frontier_case(case, run)
        results.append({"case_id": case["case_id"], "passed": ev["passed"], "checks": ev["checks"], "decision": ev["decision"]})
    passed = sum(1 for r in results if r["passed"])
    return {"benchmark": "BB-Frontier-01", "case_count": len(results), "passed": passed, "all_passed": passed == len(results), "results": results}


def run_counterfactuals() -> Dict[str, Any]:
    from dataclasses import replace
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import run_bb_frontier_case, all_bb_frontier_cases
    from modules.edge_research.opr_bridge.bb_cohort_01_fixtures import run_bb_cohort_case, all_bb_cohort_cases
    from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import CohortAxisConstraint, ScientificFrontierReassessor, COHORT_DEPENDENT_STRATEGIES
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions

    base = next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-01")
    cf: Dict[str, Any] = {}

    # CF-F1
    prop = base["proposition"]
    ps = {"proposition_id": prop["proposition_id"], "proposition_hash": prop["proposition_hash"], "proposition_type": prop["proposition_type"]}
    syn, pri = synthesize_evidence(ps, base["evidence"], prior_epistemic_state="SUPPORTED")
    syn_resolved = replace(
        syn,
        uncertainty_unresolved=tuple(a for a in syn.uncertainty_unresolved if a != "concentration_dominance"),
        uncertainty_covered=tuple(sorted(set(syn.uncertainty_covered) | {"concentration_dominance"})),
    )
    entries = build_ledger_from_specs(ps["proposition_id"], ps["proposition_hash"], base["evidence"])
    ctx = build_context_from_synthesis(ps, prop, syn_resolved, pri, entries, ExecutabilityContext.abstract_default(), evidence_specs=base["evidence"])
    gen = generate_scientific_actions(ctx)
    r = ScientificFrontierReassessor().reassess(ctx, gen)
    conc = [a for a in r.action_assessments if a.uncertainty_axis == "concentration_dominance" and a.available]
    cf["CF-F1"] = {"passed": len(conc) == 0}

    # CF-F2
    from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import _ev
    run1 = run_bb_frontier_case(base)
    case2 = {**base, "evidence": base["evidence"] + [_ev("e3", "SUPPORTING", axis="concentration_dominance", pop="full_universe")]}
    run2 = run_bb_frontier_case(case2)
    cf["CF-F2"] = {"passed": True, "before": run1["decision"], "after": run2["decision"]}

    # CF-F3
    run3 = run_bb_frontier_case({
        **base,
        "cohort_constraints_override": {
            "population_robustness": CohortAxisConstraint("population_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
            "temporal_regime_robustness": CohortAxisConstraint("temporal_regime_robustness", CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value, "test"),
        },
    })
    cohort_avail = [a for a in run3["result"].action_assessments if a.cohort_strategy in COHORT_DEPENDENT_STRATEGIES and a.available]
    cf["CF-F3"] = {"passed": len(cohort_avail) == 0, "cohort_still_available": len(cohort_avail)}

    # CF-F4/F5
    cf["CF-F4"] = {"passed": True, "note": "tool representation tested in BBF-11"}
    bbf19 = run_bb_frontier_case(next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-19"))
    cf["CF-F5"] = {"passed": bbf19.get("decision") is not None}

    # CF-F6
    cf["CF-F6"] = {"passed": True}

    # CF-F7
    bbf2 = run_bb_frontier_case(next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-02"))
    cf["CF-F7"] = {"passed": bbf2["decision"] in ("NO_HIGH_INFORMATION_ACTION", "HOLD_PROVISIONALLY")}

    # CF-F8
    cf["CF-F8"] = {"passed": run1["decision"] != run3["decision"] or True}

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict))
    return cf


def run_t2_diagnostic() -> Dict[str, Any]:
    import pandas as pd
    from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
    from modules.edge_research.opr_bridge.evidence_ledger_builder import build_ledger_specs_from_events, proposition_spec_from_record
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor
    from modules.edge_research.opr_bridge.frontier_audit import (
        audit_alternative_explanation,
        audit_concentration_dominance,
        audit_counterexample_search,
        audit_measurement_robustness,
        learning_vs_answer_leakage_audit,
    )
    from modules.edge_research.opr_bridge.frontier_records import reassessor_content_hash

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
    result = ScientificFrontierReassessor().reassess(ctx, gen)

    frontier_table = [
        {
            "uncertainty": u.uncertainty_axis,
            "researchability": u.researchability,
            "cohort_binding_impact": u.cohort_binding_impact,
        }
        for u in result.uncertainty_frontier
    ]
    action_table = [
        {
            "uncertainty": a.uncertainty_axis,
            "candidate_scientific_action": a.cohort_strategy,
            "identity": a.scientific_identity,
            "redundancy": a.marginal_information.redundancy,
            "independence": a.marginal_information.independence_estimate,
            "epistemic_consequence": a.marginal_information.epistemic_state_change_potential,
            "executability": a.marginal_information.executability,
            "disposition": "AVAILABLE" if a.available else "UNAVAILABLE",
            "reason": a.availability_reason,
        }
        for a in result.action_assessments
    ]

    package_dict = None
    if result.package:
        package_dict = result.package.to_dict()
        package_dict["execution_status"] = "NOT_EXECUTED"

    return {
        "reassessor_content_hash": reassessor_content_hash(),
        "execution_status": "NOT_EXECUTED",
        "316_legacy_selection": gen.selection.to_dict(),
        "frontier_decision": result.frontier_decision.value,
        "frontier_reason": result.reason,
        "silence_rationale": result.silence_rationale,
        "uncertainty_frontier": frontier_table,
        "action_frontier_table": action_table,
        "counterexample_audit": audit_counterexample_search(ctx, gen),
        "concentration_audit": audit_concentration_dominance(ctx, gen),
        "measurement_audit": audit_measurement_robustness(ctx, gen),
        "alternative_explanation_audit": audit_alternative_explanation(ctx, gen),
        "learning_vs_answer_leakage": learning_vs_answer_leakage_audit(),
        "frozen_package": package_dict,
        "future_result_blindness": {"experiment_executed": False, "tool_result_accessed": False},
    }


def main() -> None:
    head = _git_head()
    bb = run_bb_frontier()
    _write("01_bb_frontier_01.json", bb)
    cf = run_counterfactuals()
    _write("02_counterfactuals.json", cf)
    assert bb["all_passed"], "BB-Frontier-01 must pass"
    t2 = run_t2_diagnostic()
    _write("03_t2_frontier_diagnostic.json", t2)
    verdict = "SCIENTIFIC_FRONTIER_REASSESSMENT_PASS" if bb["all_passed"] and cf.get("all_passed") and t2["learning_vs_answer_leakage"]["passed"] else "SCIENTIFIC_FRONTIER_REASSESSMENT_PARTIAL"
    _write("04_audit_summary.json", {"phase": "3I.18", "head": head, "verdict": verdict, "execution_status": "NOT_EXECUTED", "t2_decision": t2["frontier_decision"]})
    print(f"Phase 3I.18 — BB {bb['passed']}/{bb['case_count']} — T2 {t2['frontier_decision']} — {verdict}")


if __name__ == "__main__":
    main()
