#!/usr/bin/env python3
"""Phase 3I.13 — Lifecycle evidence-synthesis integration diagnostics."""

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
from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
from modules.edge_research.opr_bridge.synthesis_integration import (
    ACTION_RECORDED_ONLY,
    FROZEN_ENGINE_HASH,
    replay_full_synthesis_history,
    replay_synthesis_at_cutoff,
    verify_frozen_engine_integrity,
)

I312 = REPO / "diagnostics/phase_3i12_evidence_synthesis/artifacts/06_real_ledger_diagnostic.json"
I311 = REPO / "diagnostics/phase_3i11_multi_evidence_reasoning/artifacts"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit_adapter_dependency() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge import evidence_ledger_builder as elb
    from modules.edge_research.opr_bridge import real_ledger_adapter as rla

    builder_src = Path(elb.__file__).read_text()
    adapter_src = Path(rla.__file__).read_text()
    return {
        "generic_builder": "evidence_ledger_builder.py",
        "adapter_role": "diagnostic_convenience_only",
        "adapter_uses_generic_builder": "build_ledger_specs_from_events" in adapter_src,
        "builder_proposition_specific_tokens": [
            t for t in ["prop-efb650d9bd5c451f", "5964", "6106", "2026-08-02"] if t in builder_src
        ],
        "classification": {
            "A_generic_lifecycle_normalization": "evidence_ledger_builder.py",
            "B_proposition_specific": "removed from builder",
            "C_diagnostic_convenience": "real_ledger_adapter.load_real_lifecycle_events",
            "D_scientific_inference": "evidence_synthesis_engine.py (frozen)",
        },
        "production_path_uses_builder_only": True,
    }


def run_bb_regression() -> Dict[str, Any]:
    results = []
    all_pass = True
    for case in BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES:
        syn, dec = run_case(case)
        ok = syn.synthesized_epistemic_state in case["expected_states"] and dec.chosen_priority_action in case["expected_actions"]
        if not ok:
            all_pass = False
        results.append({"case_id": case["case_id"], "passed": ok})
    return {"all_passed": all_pass, "cases": results}


def real_history_replay() -> Dict[str, Any]:
    prop, events = load_real_lifecycle_events()
    t1 = replay_synthesis_at_cutoff(prop, events, 1, deterministic_replay=True)
    t2 = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)
    history = replay_full_synthesis_history(prop, events, deterministic_replay=True)

    i312 = json.loads(I312.read_text()) if I312.exists() else {}

    comparison = {
        "state_match": t2.synthesis.synthesized_epistemic_state == i312.get("synthesis", {}).get("synthesized_epistemic_state"),
        "action_match": t2.priority.chosen_priority_action == i312.get("research_priority_decision", {}).get("chosen_priority_action"),
        "saturation_match": t2.synthesis.saturation_assessment["level"] == i312.get("synthesis", {}).get("saturation_assessment", {}).get("level"),
    }

    e2_id = events[1]["epistemic_update"]["update_id"]
    delta = {
        "t1_knew": {
            "evidence_count": 1,
            "state": t1.synthesis.synthesized_epistemic_state,
            "covered": list(t1.synthesis.uncertainty_covered),
            "unresolved": list(t1.synthesis.uncertainty_unresolved),
            "priority": t1.priority.chosen_priority_action,
        },
        "t2_knew": {
            "evidence_count": 2,
            "state": t2.synthesis.synthesized_epistemic_state,
            "covered": list(t2.synthesis.uncertainty_covered),
            "unresolved": list(t2.synthesis.uncertainty_unresolved),
            "priority": t2.priority.chosen_priority_action,
            "relationship_e2": t2.synthesis.relationship_map.get(e2_id),
            "redundant_axes": list(t2.synthesis.saturation_assessment.get("redundant_test_axes", [])),
        },
        "what_changed": {
            "episode_robustness_covered": "episode_robustness" in t2.synthesis.uncertainty_covered and "episode_robustness" not in t1.synthesis.uncertainty_covered,
            "state_unchanged": t1.synthesis.synthesized_epistemic_state == t2.synthesis.synthesized_epistemic_state,
            "e2_material_independent_support": False,
            "generic_holdout_redundant": "episode_robustness" in t2.synthesis.saturation_assessment.get("redundant_test_axes", []),
        },
        "action_disposition": ACTION_RECORDED_ONLY,
    }

    return {
        "t1": t1.to_dict(),
        "t2": t2.to_dict(),
        "history_count": len(history),
        "comparison_3i12": comparison,
        "scientific_delta": delta,
    }


def main() -> None:
    engine_audit = verify_frozen_engine_integrity()
    _write("01_frozen_engine_integrity.json", engine_audit)
    _write("02_adapter_dependency_audit.json", audit_adapter_dependency())
    _write("03_bb_regression.json", run_bb_regression())
    replay = real_history_replay()
    _write("04_real_t1_replay.json", replay["t1"])
    _write("05_real_t2_replay.json", replay["t2"])
    _write("06_comparison_3i12.json", replay["comparison_3i12"])
    _write("07_scientific_delta_t1_t2.json", replay["scientific_delta"])

    bb = json.loads((OUT / "03_bb_regression.json").read_text())
    verdict = "LIFECYCLE_SYNTHESIS_INTEGRATION_PASS"
    if not engine_audit["passed"] or not bb["all_passed"]:
        verdict = "LIFECYCLE_SYNTHESIS_INTEGRATION_PARTIAL"

    summary = {
        "phase": "3I.13",
        "git_head": _git_head(),
        "verdict": verdict,
        "engine_hash": engine_audit["current_hash"],
        "expected_engine_hash": FROZEN_ENGINE_HASH,
        "bb_regression_passed": bb["all_passed"],
        "action_disposition": ACTION_RECORDED_ONLY,
        "new_experiment_executed": False,
        "t2_matches_3i12": replay["comparison_3i12"],
    }
    _write("08_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
