#!/usr/bin/env python3
"""Phase 3I.14 — Automatic lifecycle synthesis hook diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import BB_EPISTEMIC_01_CASES, GENERALIZATION_CASES, run_case
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import (
    ACTION_RECORDED_ONLY,
    HOOK_VERSION,
    bootstrap_knowledge_state_from_lineage,
    on_epistemic_update_completed,
    LifecycleKnowledgeState,
)
from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
from modules.edge_research.opr_bridge.synthesis_integration import replay_synthesis_at_cutoff, verify_frozen_engine_integrity

I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I313_T1 = REPO / "diagnostics/phase_3i13_lifecycle_synthesis_integration/artifacts/04_real_t1_replay.json"
I313_T2 = REPO / "diagnostics/phase_3i13_lifecycle_synthesis_integration/artifacts/05_real_t2_replay.json"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit_lifecycle_entry_points() -> Dict[str, Any]:
    return {
        "entry_points": [
            {"path": "lifecycle_runner.run_minimal_lifecycle", "class": "PRODUCTION_LIFECYCLE", "hooked": True},
            {"path": "falsification_execution_runner.run_one_shot_falsification_execution", "class": "RESEARCH_EXECUTION", "hooked": True},
            {"path": "proposition_experiment_interpreter.build_epistemic_update", "class": "PRODUCTION_LIFECYCLE", "hooked": False, "note": "EPU builder only; hook at runner boundary"},
            {"path": "real_ledger_adapter.apply_real_ledger_diagnostic", "class": "DIAGNOSTIC_ONLY", "hooked": False},
            {"path": "synthesis_integration.update_proposition_knowledge_state", "class": "PRODUCTION_LIFECYCLE", "hooked": False, "note": "called by hook"},
            {"path": "bb_epistemic_01_fixtures.run_case", "class": "TEST_ONLY", "hooked": False},
        ],
        "canonical_hook": "lifecycle_synthesis_hook.on_epistemic_update_completed",
    }


def run_bb_regression() -> Dict[str, Any]:
    results = []
    ok = True
    for case in BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES:
        syn, dec = run_case(case)
        passed = syn.synthesized_epistemic_state in case["expected_states"] and dec.chosen_priority_action in case["expected_actions"]
        if not passed:
            ok = False
        results.append({"case_id": case["case_id"], "passed": passed})
    return {"all_passed": ok, "cases": results}


def replay_frozen_hook_t1_t2() -> Dict[str, Any]:
    prop, events = load_real_lifecycle_events()
    lineage = json.loads((I37 / "09_append_only_lineage.json").read_text())

    state = LifecycleKnowledgeState(prop["proposition_id"])
    e1 = events[0]
    _, o1 = on_epistemic_update_completed(
        prop, e1["epistemic_update"], e1["experiment_spec"], e1["experiment_ref"], e1["tool_result_hash"],
        interpretation=e1.get("interpretation"), knowledge_state=state, deterministic_replay=True,
    )

    state2 = bootstrap_knowledge_state_from_lineage(prop, lineage, deterministic_replay=True)
    e2 = events[1]
    _, o2 = on_epistemic_update_completed(
        prop, e2["epistemic_update"], e2["experiment_spec"], e2["experiment_ref"], e2["tool_result_hash"],
        lineage_metadata=e2.get("lineage_metadata"), knowledge_state=state2, deterministic_replay=True,
    )

    ref_t1 = replay_synthesis_at_cutoff(prop, events, 1, deterministic_replay=True)
    ref_t2 = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)

    return {
        "t1": o1.to_dict(),
        "t2": o2.to_dict(),
        "equivalence_3i13": {
            "t1_state": o1.synthesis.synthesized_epistemic_state == ref_t1.synthesis.synthesized_epistemic_state,
            "t1_action": o1.priority.chosen_priority_action == ref_t1.priority.chosen_priority_action,
            "t2_state": o2.synthesis.synthesized_epistemic_state == ref_t2.synthesis.synthesized_epistemic_state,
            "t2_action": o2.priority.chosen_priority_action == ref_t2.priority.chosen_priority_action,
            "t2_relationship": o2.synthesis.relationship_map.get(e2["epistemic_update"]["update_id"]),
        },
        "action_disposition": ACTION_RECORDED_ONLY,
    }


def immediate_vs_multi_decision_audit() -> Dict[str, Any]:
    return {
        "immediate_decision": "ResearchDecisionRecord — single-evidence transition_mapping/decision_mapping (3I.7)",
        "multi_evidence_priority": "ResearchPriorityDecision — body-of-evidence synthesis (3I.12/3I.13)",
        "immediate_still_useful": True,
        "immediate_status": "transitional",
        "conflict_rule": "ResearchPriorityDecision authoritative; immediate must not override",
        "decision_conflict_example": {
            "case": "BE-11 saturated body",
            "immediate_on_supporting": "SEEK_FALSIFICATION",
            "multi_evidence": "HOLD_PROVISIONALLY or HOLD_UNRESOLVED",
            "authoritative": "ResearchPriorityDecision",
        },
    }


def main() -> None:
    engine = verify_frozen_engine_integrity()
    _write("01_lifecycle_entry_point_audit.json", audit_lifecycle_entry_points())
    _write("02_frozen_engine_integrity.json", engine)
    _write("03_bb_regression.json", run_bb_regression())
    replay = replay_frozen_hook_t1_t2()
    _write("04_hook_t1_replay.json", replay["t1"])
    _write("05_hook_t2_replay.json", replay["t2"])
    _write("06_equivalence_3i13.json", replay["equivalence_3i13"])
    _write("07_immediate_vs_multi_decision_audit.json", immediate_vs_multi_decision_audit())

    bb = json.loads((OUT / "03_bb_regression.json").read_text())
    eq = replay["equivalence_3i13"]
    verdict = "AUTOMATIC_SYNTHESIS_HOOK_PASS"
    if not engine["passed"] or not bb["all_passed"] or not all(eq.values()):
        verdict = "AUTOMATIC_SYNTHESIS_HOOK_PARTIAL"

    summary = {
        "phase": "3I.14",
        "hook_version": HOOK_VERSION,
        "git_head": _git_head(),
        "verdict": verdict,
        "engine_hash": engine["current_hash"],
        "bb_regression": bb["all_passed"],
        "t1_t2_equivalent_3i13": eq,
        "action_disposition": ACTION_RECORDED_ONLY,
        "new_experiment_executed": False,
    }
    _write("08_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
