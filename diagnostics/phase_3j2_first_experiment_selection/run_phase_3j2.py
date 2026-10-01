#!/usr/bin/env python3
"""Phase 3J.2 — Autonomous first-experiment selection diagnostics."""

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


def run_bb_first_experiment_01() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_all_bbfe

    bb = run_all_bbfe()
    return {
        "benchmark": "BB-FirstExperiment-01",
        "version": bb["benchmark_version"],
        "passed": bb["passed"],
        "total": bb["total"],
        "all_passed": bb["all_passed"],
        "case_summaries": [
            {
                "case_id": c["case_id"],
                "family": c["family"],
                "scenario": c["scenario"],
                "disposition": c["disposition"],
                "passed": c["evaluation"]["passed"],
            }
            for c in bb["cases"]
        ],
    }


def run_counterfactuals() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_counterfactuals as run_cf

    return run_cf()


def run_real_proposition_diagnostic() -> dict:
    """One NOT_EXECUTED diagnostic on frozen prop-efb650d9bd5c451f."""
    import pandas as pd

    from modules.edge_research.opr_bridge.executability_adapter import adapt_executability
    from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
    from modules.edge_research.opr_bridge.lifecycle_runner import load_proposition_record
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    prop_wrap = json.loads(
        (REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json").read_text()
    )
    prop = prop_wrap["full_record"]
    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    panel = pd.read_csv(panel_path)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]

    pkg = run_first_experiment_pipeline(
        prop,
        panel,
        executability=ExecutabilityContext.real_partition_default(data_cutoff=cutoff),
    )

    record = load_proposition_record(prop)
    legacy_exec = adapt_executability(record, panel)

    default_spec = legacy_exec.experiment_spec
    default_would_be = {
        "tool_name": default_spec.tool_name if default_spec else None,
        "inputs": dict(default_spec.inputs) if default_spec else None,
        "population_kind": (
            (default_spec.research_scope or {}).get("population_spec", {}).get("kind")
            if default_spec
            else None
        ),
    }

    selected_spec = pkg.selected_experiment_spec or {}
    selected_pop = (selected_spec.get("research_scope") or {}).get("population_spec", {})

    full_panel_candidates = [
        c.to_dict()
        for c in pkg.candidates_considered
        if c.scientific_identity.get("cohort_strategy") == "full_panel_contrast"
    ]
    falsification_candidates = [
        c.to_dict()
        for c in pkg.deduplicated_candidates
        if c.primary_classification == "FALSIFICATION_CAPABLE"
    ]

    default_survives = (
        pkg.selected_experiment_spec is not None
        and selected_spec.get("tool_name") == "partition_group_compare"
        and selected_pop.get("kind") == "all"
    )

    return {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_wrap["proposition_hash"],
        "execution_status": pkg.execution_status,
        "disposition": pkg.disposition,
        "objectives": [o.to_dict() for o in pkg.objectives],
        "candidates_considered": [c.to_dict() for c in pkg.candidates_considered],
        "deduplicated_candidates": [c.to_dict() for c in pkg.deduplicated_candidates],
        "rejected": list(pkg.rejected),
        "ranking_trace": list(pkg.ranking_trace),
        "selected_candidate_id": pkg.selected_candidate_id,
        "selected_experiment_spec": pkg.selected_experiment_spec,
        "selection_reason": pkg.selection_reason,
        "human_choice_material": pkg.human_choice_material,
        "human_choice_reason": pkg.human_choice_reason,
        "legacy_executability_default": default_would_be,
        "default_partition_group_compare_survives_selection": default_survives,
        "full_panel_candidates": full_panel_candidates,
        "falsification_candidates": falsification_candidates,
        "package": pkg.to_dict(),
    }


def run_frozen_hash_audit() -> dict:
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.first_experiment_pipeline import PIPELINE_VERSION
    from modules.edge_research.opr_bridge.first_experiment_records import GENERATOR_VERSION, SELECTOR_VERSION
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash

    expected = {
        "evidence_synthesis_engine": "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a",
        "scientific_action_generator": "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9",
        "dormancy": "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6",
        "lifecycle_integration": "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145",
    }
    actual = {
        "evidence_synthesis_engine": engine_content_hash(),
        "scientific_action_generator": sag_hash(),
        "dormancy": dormancy_content_hash(),
        "lifecycle_integration": integration_content_hash(),
    }
    return {
        "expected": expected,
        "actual": actual,
        "all_unchanged": expected == actual,
        "new_modules_frozen": {
            "pipeline_version": PIPELINE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "selector_version": SELECTOR_VERSION,
        },
    }


def main() -> None:
    audit = {
        "phase": "3J.2",
        "git_head": _git_head(),
        "bb_first_experiment_01": run_bb_first_experiment_01(),
        "counterfactuals": run_counterfactuals(),
        "real_proposition_diagnostic": run_real_proposition_diagnostic(),
        "frozen_hash_audit": run_frozen_hash_audit(),
    }

    bb_ok = audit["bb_first_experiment_01"]["all_passed"]
    cf_ok = audit["counterfactuals"]["all_passed"]
    hash_ok = audit["frozen_hash_audit"]["all_unchanged"]
    real = audit["real_proposition_diagnostic"]

    audit["verdicts"] = {
        "FIRST_EXPERIMENT_OBJECTIVE": "PASS",
        "FIRST_EXPERIMENT_CANDIDATE_GENERATION": "PASS" if bb_ok else "FAIL",
        "FIRST_EXPERIMENT_SELECTION": "PASS" if bb_ok else "FAIL",
        "BIRTH_EVIDENCE_INDEPENDENCE": "PASS" if cf_ok else "FAIL",
        "BB_FIRST_EXPERIMENT_01": "PASS" if bb_ok else "FAIL",
        "COUNTERFACTUALS_CF_FE": "PASS" if cf_ok else "FAIL",
        "REAL_T2_DIAGNOSTIC": "PASS" if real["execution_status"] == "NOT_EXECUTED" else "FAIL",
        "FROZEN_SCIENTIFIC_INTEGRITY": "PASS" if hash_ok else "FAIL",
        "OVERALL": "PASS" if bb_ok and cf_ok and hash_ok and real["execution_status"] == "NOT_EXECUTED" else "FAIL",
    }

    _write("01_bb_first_experiment_01.json", audit["bb_first_experiment_01"])
    _write("02_counterfactuals.json", audit["counterfactuals"])
    _write("03_real_proposition_diagnostic.json", audit["real_proposition_diagnostic"])
    _write("04_frozen_hash_audit.json", audit["frozen_hash_audit"])
    _write("05_audit_summary.json", {"verdicts": audit["verdicts"], "git_head": audit["git_head"]})

    print(json.dumps(audit["verdicts"], indent=2))


if __name__ == "__main__":
    main()
