#!/usr/bin/env python3
"""Phase 3J.4 — Evidence interpretation diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_int() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import run_cf_int_counterfactuals

    return run_cf_int_counterfactuals()


def run_real_diagnostic() -> dict:
    import pandas as pd

    from modules.edge_research.opr_bridge.production_first_experiment_execution import (
        run_production_first_experiment_execution,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )

    prop = json.loads(
        (REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json").read_text()
    )["full_record"]
    panel = pd.read_csv(REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]

    fx = run_production_first_experiment_execution(
        prop, panel, session_id="phase-3j4-real-diagnostic", data_cutoff_date=cutoff
    )
    ix = run_production_first_experiment_interpretation(
        prop,
        session_id="phase-3j4-real-diagnostic",
        package_dict=fx.package_dict or {},
        execution_dict=fx.execution.envelope.to_dict() if fx.execution and fx.execution.envelope else {},
        frozen_contract_dict=fx.frozen_contract_ref,
    )
    env = ix.interpretation.envelope if ix.interpretation else None
    assess = env.evidence_assessment.to_dict() if env else {}
    return {
        "proposition_id": prop["proposition_id"],
        "package_id": (fx.package_dict or {}).get("package_id"),
        "selected_candidate_id": (fx.package_dict or {}).get("selected_candidate_id"),
        "scientific_objective": assess.get("experiment_intent_summary"),
        "frozen_contract_hash": env.frozen_contract_ref.contract_hash if env else None,
        "tool_result_hash": env.tool_result_hash if env else None,
        "evidence_relevance": assess.get("evidence_relevance"),
        "evidence_direction": assess.get("evidence_direction"),
        "evidence_strength": assess.get("evidence_strength"),
        "null_accounting": assess.get("null_accounting"),
        "other_nulls_still_alive": assess.get("other_nulls_still_alive"),
        "prior_epistemic_state": env.prior_epistemic_state if env else None,
        "resulting_epistemic_state": env.resulting_epistemic_state if env else None,
        "limitations": assess.get("limitations"),
        "tool_semantic_labels_ignored": assess.get("tool_semantic_labels_ignored"),
        "interpretation_outcome": ix.interpretation.outcome if ix.interpretation else None,
        "research_decision_generated": ix.interpretation.research_decision_generated if ix.interpretation else None,
        "stop_boundary": ix.interpretation.stop_boundary if ix.interpretation else None,
        "epistemic_update_id": (env.epistemic_update or {}).get("update_id") if env else None,
    }


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
    cf = run_cf_int()
    real = run_real_diagnostic()
    frozen = run_frozen_hash_audit()
    _write("01_cf_int_results.json", cf)
    _write("02_real_proposition_diagnostic.json", real)
    _write("03_frozen_hash_audit.json", frozen)
    _write(
        "04_audit_summary.json",
        {
            "git_head": _git_head(),
            "phase": "3J.4",
            "cf_int_all_passed": cf.get("all_passed"),
            "frozen_hashes_unchanged": frozen.get("unchanged"),
            "real_interpretation_outcome": real.get("interpretation_outcome"),
            "stop_boundary": real.get("stop_boundary"),
        },
    )
    print(json.dumps({"cf": cf["all_passed"], "frozen": frozen["unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
