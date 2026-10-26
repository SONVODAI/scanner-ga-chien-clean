#!/usr/bin/env python3
"""Phase 3J.5 — Research decision after first evidence diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))

FROZEN_PROP = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"
FROZEN_CONTRACT = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json"
J2_DIAG = REPO / "diagnostics/phase_3j2_first_experiment_selection/artifacts/03_real_proposition_diagnostic.json"
PERSISTED_EXEC = REPO / "diagnostics/phase_3j4_evidence_interpretation/artifacts/05_persisted_3j3_execution_envelope.json"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_rd() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_research_decision_01_fixtures import (
        run_cf_rd_counterfactuals,
    )

    return run_cf_rd_counterfactuals()


def run_real_diagnostic() -> dict:
    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
    )

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    execution_dict = json.loads(PERSISTED_EXEC.read_text())
    j2_package = json.loads(J2_DIAG.read_text())["package"]
    hist_contract = json.loads(FROZEN_CONTRACT.read_text())
    package_dict = _package_stub_from_persisted_execution(execution_dict, j2_package)
    frozen_ref = frozen_ref_from_historical_contract_artifact(
        hist_contract,
        package_id=execution_dict["package_id"],
        experiment_content_hash=execution_dict["experiment_content_hash"],
        scientific_action_core_hash=execution_dict["scientific_action_core_hash"],
    )

    ix = run_production_first_experiment_interpretation(
        prop,
        session_id="phase-3j5-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
    )
    env = ix.interpretation.envelope if ix.interpretation else None
    assess = env.evidence_assessment.to_dict() if env else {}

    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="phase-3j5-real-diagnostic",
        package_dict=package_dict,
        interpretation_dict=env.to_dict() if env else {},
    )
    dec_env = dx.decision.envelope if dx.decision else None
    rd = dec_env.research_decision if dec_env else {}

    admissible = [e.to_dict() for e in dec_env.candidate_evaluations if e.admissible] if dec_env else []
    rejected = [e.to_dict() for e in dec_env.candidate_evaluations if not e.admissible] if dec_env else []
    selected_eval = next(
        (e.to_dict() for e in dec_env.candidate_evaluations if e.admissible and e.action_family.startswith("TEST_")),
        None,
    ) if dec_env else None
    if dec_env and not selected_eval:
        selected_eval = next((e.to_dict() for e in dec_env.candidate_evaluations if e.admissible), None)

    return {
        "proposition_id": prop["proposition_id"],
        "current_epistemic_state": env.resulting_epistemic_state if env else None,
        "null_addressed_by_first_experiment": dec_env.null_addressed_by_first_experiment if dec_env else None,
        "surviving_null_explanations": list(dec_env.surviving_nulls) if dec_env else [],
        "interpretation_summary": {
            "evidence_relevance": assess.get("evidence_relevance"),
            "evidence_direction": assess.get("evidence_direction"),
            "evidence_strength": assess.get("evidence_strength"),
        },
        "search_accounting": dec_env.search_accounting.to_dict() if dec_env else None,
        "admissible_candidates": admissible,
        "rejected_candidates": rejected,
        "selected_next_action": rd.get("chosen_next_action"),
        "decision_kind": dec_env.decision_kind if dec_env else None,
        "stop_reason": dec_env.stop_reason if dec_env else None,
        "scientific_uncertainty_targeted": selected_eval.get("target_uncertainty") if selected_eval else None,
        "target_null_key": selected_eval.get("target_null_key") if selected_eval else None,
        "expected_information_contribution": selected_eval.get("expected_information_contribution") if selected_eval else None,
        "confirmation_bias_guard_applied": dec_env.confirmation_bias_guard_applied if dec_env else None,
        "tool_convenience_overridden": dec_env.tool_convenience_overridden if dec_env else None,
        "second_experiment_generated": dec_env.second_experiment_generated if dec_env else None,
        "second_experiment_executed": dec_env.second_experiment_executed if dec_env else None,
        "decision_rationale": rd.get("reason"),
        "decision_id": rd.get("decision_id"),
        "epistemic_update_id": rd.get("epistemic_update_id"),
        "stop_boundary": dx.decision.stop_boundary if dx.decision else None,
    }


def run_hidden_answer_grep() -> dict:
    patterns = [
        "2026-08-02",
        "zone_c",
        "hidden_phenomenon",
        "july 27",
        "prop-efb650d9bd5c451f",
    ]
    hits = []
    search_root = REPO / "modules/edge_research/opr_bridge"
    module_globs = (
        "first_experiment_research*.py",
        "production_first_experiment_research*.py",
    )
    target_files = []
    for pat in module_globs:
        target_files.extend(search_root.glob(pat))

    for pat in patterns:
        try:
            out = subprocess.check_output(
                ["rg", "-l", pat, str(search_root)],
                cwd=REPO,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                for line in out.splitlines():
                    name = Path(line).name
                    if any(name == t.name for t in target_files):
                        hits.append({"pattern": pat, "file": line})
        except subprocess.CalledProcessError:
            pass
    return {"suspicious_hits_in_3j5_modules": hits, "clean": len(hits) == 0}


def run_frozen_hash_audit() -> dict:
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    expected = {
        "engine": "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a",
        "sag": "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9",
        "dormancy": "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6",
        "integration": "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145",
    }
    actual = {
        "engine": engine_content_hash(),
        "sag": sag_hash(),
        "dormancy": dormancy_content_hash(),
        "integration": integration_content_hash(),
    }
    return {"expected": expected, "actual": actual, "unchanged": expected == actual}


def main() -> None:
    cf = run_cf_rd()
    real = run_real_diagnostic()
    grep = run_hidden_answer_grep()
    frozen = run_frozen_hash_audit()

    _write("01_cf_rd_results.json", cf)
    _write("02_real_proposition_diagnostic.json", real)
    _write("03_hidden_answer_grep.json", grep)
    _write("04_frozen_hash_audit.json", frozen)
    _write(
        "05_audit_summary.json",
        {
            "git_head": _git_head(),
            "phase": "3J.5",
            "cf_rd_all_passed": cf.get("all_passed"),
            "frozen_hashes_unchanged": frozen.get("unchanged"),
            "hidden_answer_clean": grep.get("clean"),
            "real_decision_outcome": real.get("decision_kind"),
            "selected_next_action": real.get("selected_next_action"),
            "stop_boundary": real.get("stop_boundary"),
            "second_experiment_generated": real.get("second_experiment_generated"),
        },
    )
    print(json.dumps({"cf": cf["all_passed"], "frozen": frozen["unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
