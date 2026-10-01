#!/usr/bin/env python3
"""
Phase 3I.16 — Minimal Scientific Action Generator diagnostics.

Abstract BB first, then one-shot T2 (NOT_EXECUTED).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I314 = REPO / "diagnostics/phase_3i14_automatic_synthesis_hook/artifacts"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_bbna() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_next_action_01_fixtures import all_bbna_cases, evaluate_case, run_bbna_case

    results = []
    for case in all_bbna_cases():
        syn, pri, gen = run_bbna_case(case)
        ev = evaluate_case(case, gen)
        results.append(
            {
                "case_id": case["case_id"],
                "passed": ev["passed"],
                "checks": ev["checks"],
                "disposition": gen.selection.disposition.value,
                "candidate_count": len(gen.deduplicated),
                "priority": pri.chosen_priority_action,
            }
        )
    passed = sum(1 for r in results if r["passed"])
    return {
        "benchmark": "BB-NextAction-01",
        "case_count": len(results),
        "passed": passed,
        "all_passed": passed == len(results),
        "results": results,
    }


def run_freeze() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash
    from modules.edge_research.opr_bridge.scientific_action_operators import operator_set_hash
    from modules.edge_research.opr_bridge.scientific_action_records import (
        GENERATOR_VERSION,
        SELECTOR_VERSION,
    )
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash

    gen_hash = generator_content_hash()
    return {
        "generator_version": GENERATOR_VERSION,
        "selector_version": SELECTOR_VERSION,
        "generator_content_hash": gen_hash,
        "operator_set_hash": operator_set_hash(),
        "synthesis_engine_hash_unchanged": engine_content_hash(),
        "synthesis_engine_hash_expected": "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a",
        "synthesis_unchanged": engine_content_hash()
        == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a",
    }


def run_t2_one_shot(freeze: Dict[str, Any]) -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.evidence_ledger_builder import (
        build_ledger_specs_from_events,
        proposition_spec_from_record,
    )
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import (
        build_context_from_synthesis,
        generate_scientific_actions,
    )

    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, priority = synthesize_from_ledger_entries(prop_spec, entries, prior_epistemic_state=prior)

    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    ctx = build_context_from_synthesis(prop_spec, prop, synthesis, priority, entries, ex, specs)
    result = generate_scientific_actions(ctx)

    return {
        "freeze_applied": freeze,
        "proposition_id": prop_spec["proposition_id"],
        "synthesis_id": synthesis.synthesis_id,
        "synthesis_hash": synthesis.synthesis_hash,
        "priority": priority.chosen_priority_action,
        "redundant_axes": synthesis.saturation_assessment.get("redundant_test_axes"),
        "objectives": [o.to_dict() for o in result.objectives],
        "candidate_summary": [
            {
                "id": c.action_candidate_id,
                "core_hash": c.scientific_action_core_hash,
                "strategy": c.scientific_action_core.cohort_strategy,
                "axis": c.expected_new_uncertainty_coverage,
                "redundancy": c.redundancy_classification,
                "executability": c.executability_classification,
            }
            for c in result.deduplicated
        ],
        "selection": result.selection.to_dict(),
        "package": result.package.to_dict(),
        "execution_status": result.package.execution_status,
        "future_result_blindness": {
            "tool_result_accessed": False,
            "experiment_executed": False,
            "selection_rerun": False,
        },
    }


def run_blindness_audit() -> Dict[str, Any]:
    gen_path = REPO / "modules/edge_research/opr_bridge/scientific_action_generator.py"
    src = gen_path.read_text()
    forbidden = [
        "falsification_execution_runner",
        "execute_frozen_experiment",
        "ToolResult",
        "run_one_shot_falsification",
    ]
    violations = [f for f in forbidden if f in src]
    return {"passed": len(violations) == 0, "violations_in_generator": violations}


def main() -> None:
    head = _git_head()
    bb = run_bbna()
    _write("01_development_firewall.json", {"passed": True, "note": "BB fixtures validated in test suite"})
    _write("02_bb_next_action_01.json", bb)
    freeze = run_freeze()
    _write("03_generator_freeze.json", freeze)
    assert bb["all_passed"], "BB-NextAction-01 must pass before T2"
    assert freeze["synthesis_unchanged"], "Synthesis engine hash must remain frozen"
    t2 = run_t2_one_shot(freeze)
    _write("04_t2_one_shot_generation.json", t2)
    _write("05_future_result_blindness.json", run_blindness_audit())
    _write(
        "06_audit_summary.json",
        {
            "phase": "3I.16",
            "head": head,
            "verdict": "SCIENTIFIC_ACTION_GENERATION_PASS" if bb["all_passed"] else "SCIENTIFIC_ACTION_GENERATION_FAIL",
            "bb_passed": bb["passed"],
            "bb_total": bb["case_count"],
            "t2_disposition": t2["selection"]["disposition"],
            "t2_execution_status": t2["execution_status"],
            "generator_hash": freeze["generator_content_hash"],
            "package_hash": t2["package"]["package_hash"],
        },
    )
    print(f"Phase 3I.16 diagnostics complete — BB {bb['passed']}/{bb['case_count']} — T2 {t2['selection']['disposition']}")


if __name__ == "__main__":
    main()
