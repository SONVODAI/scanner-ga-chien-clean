#!/usr/bin/env python3
"""
Phase 3I.12 — Minimal Evidence Synthesis Engine.

Order: abstract BB-Epistemic-01 → freeze → one-shot real ledger diagnostic.
No new market experiment.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import (
    BB_EPISTEMIC_01_CASES,
    GENERALIZATION_CASES,
    all_bb_cases,
    assert_development_firewall,
    run_case,
)
from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.real_ledger_adapter import apply_real_ledger_diagnostic

I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I310 = REPO / "diagnostics/phase_3i10_falsification_execution/artifacts"
I311 = REPO / "diagnostics/phase_3i11_multi_evidence_reasoning/artifacts"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit_development_firewall() -> Dict[str, Any]:
    violations = []
    for case in all_bb_cases():
        try:
            assert_development_firewall(case)
        except ValueError as exc:
            violations.append({"case_id": case["case_id"], "error": str(exc)})
    return {
        "forbidden_tokens": list({"rs_spread", "t5_return", "prop-efb650d9bd5c451f"}),
        "cases_checked": len(all_bb_cases()),
        "violations": violations,
        "passed": len(violations) == 0,
    }


def audit_lineage_integrity() -> Dict[str, Any]:
    lineage = json.loads((I311 / "01_lineage_integrity.json").read_text())
    prop_wrap = json.loads((I37 / "02_frozen_proposition.json").read_text())
    prop_hash = proposition_content_hash(prop_wrap["full_record"])
    return {
        **lineage,
        "proposition_hash_reverified": prop_hash == prop_wrap["proposition_hash"],
        "passed": lineage.get("passed") and prop_hash == prop_wrap["proposition_hash"],
    }


def run_bb_epistemic_01() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    all_pass = True
    for case in BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES:
        synthesis, decision = run_case(case)
        state_ok = synthesis.synthesized_epistemic_state in case["expected_states"]
        action_ok = decision.chosen_priority_action in case["expected_actions"]
        passed = state_ok and action_ok
        if not passed:
            all_pass = False
        results.append(
            {
                "case_id": case["case_id"],
                "name": case["name"],
                "synthesized_state": synthesis.synthesized_epistemic_state,
                "expected_states": list(case["expected_states"]),
                "chosen_action": decision.chosen_priority_action,
                "expected_actions": list(case["expected_actions"]),
                "saturation": synthesis.saturation_assessment["level"],
                "passed": passed,
            }
        )
    return {"cases": results, "all_passed": all_pass, "case_count": len(results)}


def run_counterfactual_audit() -> Dict[str, Any]:
    import copy

    tests = []
    # Remove decisive disconfirm
    case5 = copy.deepcopy(next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-05"))
    full, _ = run_case(case5)
    partial_case = copy.deepcopy(case5)
    partial_case["evidence"] = partial_case["evidence"][:1]
    partial, _ = run_case(partial_case)
    tests.append(
        {
            "name": "remove_decisive_disconfirm",
            "full_state": full.synthesized_epistemic_state,
            "partial_state": partial.synthesized_epistemic_state,
            "changed": full.synthesized_epistemic_state != partial.synthesized_epistemic_state,
            "passed": full.synthesized_epistemic_state != partial.synthesized_epistemic_state,
        }
    )
    # Invalid disconfirm
    inv_case = copy.deepcopy(case5)
    inv_case["evidence"][1]["validity"] = "INVALID"
    inv, _ = run_case(inv_case)
    tests.append(
        {
            "name": "invalid_disconfirm_no_weaken",
            "state": inv.synthesized_epistemic_state,
            "passed": inv.synthesized_epistemic_state == "SUPPORTED",
        }
    )
    return {"tests": tests, "all_passed": all(t.get("passed") for t in tests)}


def freeze_engine() -> Dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "engine_version": "evidence_synthesis_v1_3i12",
        "engine_content_hash": engine_content_hash(),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "bb_epistemic_01_required": True,
        "real_ledger_gated": True,
    }


def compare_with_3i11_audit(real_result: Dict[str, Any]) -> Dict[str, Any]:
    audit_311 = json.loads((I311 / "15_current_proposition_diagnostic.json").read_text())
    synth = real_result["synthesis"]
    decision = real_result["research_priority_decision"]
    agreements = []
    disagreements = []
    checks = [
        ("relationship", real_result.get("relationship_e1_to_e2"), audit_311.get("relationship_e1_to_e2", "").split()[0]),
        ("generic_holdout_redundant", decision.get("chosen_priority_action") in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED") or "redundant" in " ".join(decision.get("rationale", [])).lower(), audit_311.get("another_generic_holdout_redundant")),
        ("synthesized_state", synth.get("synthesized_epistemic_state"), "SUPPORTED"),
        ("hold_provisionally", decision.get("chosen_priority_action") == "HOLD_PROVISIONALLY", audit_311.get("hold_provisionally_justified_yet")),
    ]
    for name, engine_val, audit_val in checks:
        if name == "relationship":
            engine_base = str(engine_val).split("_")[0] if engine_val else ""
            audit_base = str(audit_val).split()[0] if audit_val else ""
            if engine_val == "PARTIAL_REPLICATION" and "PARTIAL" in str(audit_val):
                agreements.append(name)
            elif engine_val == audit_val:
                agreements.append(name)
            else:
                disagreements.append({"field": name, "engine": engine_val, "audit_311": audit_val})
        elif name == "hold_provisionally":
            if engine_val == audit_val:
                agreements.append(name)
            else:
                disagreements.append({"field": name, "engine": engine_val, "audit_311": audit_val, "note": "Expected — engine independent"})
        elif engine_val == audit_val:
            agreements.append(name)
        else:
            disagreements.append({"field": name, "engine": engine_val, "audit_311": audit_val})
    return {"agreements": agreements, "disagreements": disagreements, "no_retuning": True}


def main() -> None:
    _write("01_development_firewall.json", audit_development_firewall())
    _write("02_lineage_integrity.json", audit_lineage_integrity())
    _write("03_bb_epistemic_01_results.json", run_bb_epistemic_01())
    _write("04_counterfactual_audit.json", run_counterfactual_audit())
    freeze = freeze_engine()
    _write("05_engine_freeze.json", freeze)

    # One-shot real ledger — only after freeze record written
    real = apply_real_ledger_diagnostic()
    _write("06_real_ledger_diagnostic.json", real)
    _write("07_comparison_3i11_audit.json", compare_with_3i11_audit(real))

    bb = json.loads((OUT / "03_bb_epistemic_01_results.json").read_text())
    cf = json.loads((OUT / "04_counterfactual_audit.json").read_text())
    fw = json.loads((OUT / "01_development_firewall.json").read_text())

    verdict = "EVIDENCE_SYNTHESIS_PASS"
    if not bb["all_passed"] or not cf["all_passed"] or not fw["passed"]:
        verdict = "EVIDENCE_SYNTHESIS_PARTIAL"

    summary = {
        "phase": "3I.12",
        "mode": "IMPLEMENT_ABSTRACT_FIRST",
        "git_head": _git_head(),
        "verdict": verdict,
        "engine_hash": freeze["engine_content_hash"],
        "bb_all_passed": bb["all_passed"],
        "counterfactual_passed": cf["all_passed"],
        "firewall_passed": fw["passed"],
        "real_ledger_applied": True,
        "new_experiment_executed": False,
        "synthesized_state_real": real["synthesis"]["synthesized_epistemic_state"],
        "priority_action_real": real["research_priority_decision"]["chosen_priority_action"],
    }
    _write("08_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
