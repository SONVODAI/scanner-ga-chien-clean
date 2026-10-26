#!/usr/bin/env python3
"""Phase 3J.3 — First-experiment execution diagnostics."""

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


def run_bbfex() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_all_bbfex

    return run_all_bbfex()


def run_counterfactuals() -> dict:
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_cf_ex_counterfactuals

    return run_cf_ex_counterfactuals()


def run_real_proposition_diagnostic() -> dict:
    import pandas as pd

    from modules.edge_research.opr_bridge.production_first_experiment_execution import (
        run_production_first_experiment_execution,
    )

    prop_wrap = json.loads(
        (REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json").read_text()
    )
    prop = prop_wrap["full_record"]
    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    panel = pd.read_csv(panel_path)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]

    fx = run_production_first_experiment_execution(
        prop,
        panel,
        session_id="phase-3j3-real-diagnostic",
        data_cutoff_date=cutoff,
    )
    pkg = fx.package_dict or {}
    exec_d = fx.execution.to_dict() if fx.execution else {}
    env = exec_d.get("envelope") or {}
    audit = env.get("binding_audit") or {}
    sel_spec = pkg.get("selected_experiment_spec") or {}

    return {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": pkg.get("proposition_hash"),
        "package_id": pkg.get("package_id"),
        "package_hash": pkg.get("package_hash"),
        "selected_candidate_id": pkg.get("selected_candidate_id"),
        "scientific_objective": prop.get("scientific_question"),
        "population": audit.get("population_spec"),
        "outcome_horizon": {
            "outcome": audit.get("outcome_spec"),
            "horizon": audit.get("observation_horizon"),
        },
        "selected_tool": audit.get("tool_name"),
        "binding_summary": {
            "scientific_spec_hash": audit.get("scientific_spec_hash"),
            "execution_spec_hash": audit.get("execution_spec_hash"),
            "scientific_action_core_hash": audit.get("scientific_action_core_hash"),
            "inputs": audit.get("inputs"),
            "binding_notes": audit.get("binding_notes"),
        },
        "eligibility": exec_d.get("eligibility"),
        "execution_status": exec_d.get("outcome"),
        "tool_result_identity": env.get("tool_result_hash"),
        "execution_identity_hash": env.get("execution_identity_hash"),
        "sample_size": env.get("sample_size"),
        "provenance": {
            "panel_provenance_hash": env.get("panel_provenance_hash"),
            "package_hash": env.get("package_hash"),
        },
        "scientific_action_identity_survived": audit.get("scientific_action_core_hash")
        == env.get("scientific_action_core_hash"),
        "fallback_or_substitution": exec_d.get("substitution_occurred", False),
        "stop_boundary": exec_d.get("stop_boundary"),
        "selected_experiment_spec_tool": sel_spec.get("tool_name"),
    }


def run_hidden_answer_grep() -> dict:
    import subprocess

    patterns = [
        "2026-08-02",
        "zone_c",
        "hidden_phenomenon",
        "july 27",
        "episode.holdout",
        "prop-efb650d9bd5c451f",
    ]
    hits = []
    search_root = REPO / "modules/edge_research/opr_bridge"
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
                    if "first_experiment_execution" in line or "production_first_experiment" in line:
                        hits.append({"pattern": pat, "file": line})
        except subprocess.CalledProcessError:
            pass
    return {"suspicious_hits_in_3j3_modules": hits, "clean": len(hits) == 0}


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
    bbfex = run_bbfex()
    cf = run_counterfactuals()
    real = run_real_proposition_diagnostic()
    grep = run_hidden_answer_grep()
    frozen = run_frozen_hash_audit()

    _write("01_bbfex_results.json", bbfex)
    _write("02_counterfactuals.json", cf)
    _write("03_real_proposition_diagnostic.json", real)
    _write("04_hidden_answer_grep.json", grep)
    _write("05_frozen_hash_audit.json", frozen)
    _write(
        "06_audit_summary.json",
        {
            "git_head": _git_head(),
            "phase": "3J.3",
            "bbfex_all_passed": bbfex.get("all_passed"),
            "cf_ex_all_passed": cf.get("all_passed"),
            "frozen_hashes_unchanged": frozen.get("unchanged"),
            "hidden_answer_clean": grep.get("clean"),
            "real_diagnostic_execution_status": real.get("execution_status"),
            "stop_boundary": real.get("stop_boundary"),
        },
    )
    print(json.dumps({"bbfex": bbfex["all_passed"], "cf": cf["all_passed"], "frozen": frozen["unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
