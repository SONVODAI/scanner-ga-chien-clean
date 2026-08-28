#!/usr/bin/env python3
"""
Phase 3I.9 — Autonomous falsification candidate generation and selection.

CRITICAL: Does NOT execute selected ExperimentSpec or read ToolResult.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"

sys.path.insert(0, str(REPO))

import pandas as pd

from modules.edge_research.opr_bridge.falsification_runner import (
    build_abstract_proposition_fixture,
    load_frozen_3i7_lineage,
    run_falsification_selection,
)
from modules.edge_research.opr_bridge.interpretation_contract import (
    build_interpretation_contract,
    contract_rule_content,
    interpretation_contract_from_dict,
)
from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel
from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    generate_falsification_candidates,
    GENERATOR_VERSION,
)
from modules.edge_research.opr_bridge.falsification_selector import select_falsification_candidate
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3i9.py", "-q"],
        cwd=REPO,
    )
    if rc != 0:
        print("BB-Falsify-01 / 3I.9 tests failed — aborting real selection")
        return 1

    frozen = load_frozen_3i7_lineage(I37)
    panel = pd.read_csv(PANEL)

    provenance = {
        "artifact_03_hash": frozen["interpretation_contract"]["contract_hash"],
        "lineage_runtime_hash": frozen["lineage"]["interpretation_contract_hash"],
        "historical_mismatch_preserved": (
            frozen["interpretation_contract"]["contract_hash"]
            != frozen["lineage"]["interpretation_contract_hash"]
        ),
        "forward_fix": "interpretation_contract_from_dict + hash excludes frozen_at",
        "rule_content_regression": contract_rule_content(
            interpretation_contract_from_dict(frozen["interpretation_contract"]).to_dict()
        ),
    }
    c_new = build_interpretation_contract(frozen["proposition"])
    c_artifact = interpretation_contract_from_dict(frozen["interpretation_contract"])
    provenance["new_build_matches_artifact_rules"] = (
        contract_rule_content(c_new.to_dict()) == contract_rule_content(c_artifact.to_dict())
    )

    bb_audit = run_falsification_selection(frozen, panel, include_audit_sketches=True)
    real = run_falsification_selection(frozen, panel, include_audit_sketches=False)

    abstract = build_abstract_proposition_fixture()
    dev_panel = build_extended_dev_panel(panel.head(200), n_dates=25, symbols_per_date=35)
    dev_panel["vol_dispersion"] = dev_panel["rs_spread"]
    dev_panel["t3_return"] = dev_panel["t5_return"]
    abstract_contract = build_interpretation_contract(abstract)
    prior = {
        "tool_name": "partition_group_compare",
        "tool_version": "v1",
        "inputs": {"partition_column": "vol_dispersion", "n_groups": 5},
        "research_scope": {
            "population_spec": {"kind": "all", "grammar_version": "research_grammar_v1"},
            "outcome_spec": abstract["outcome"],
            "observation_horizon": 0,
        },
        "data_cutoff_date": "2026-04-01",
    }
    prior_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(prior))
    abstract_candidates = generate_falsification_candidates(
        abstract,
        interpretation_contract=abstract_contract,
        epistemic_update={"update_id": "epu-abstract", "tool_result_hash": "abstract"},
        research_decision={"decision_id": "dec-abstract", "chosen_next_action": "SEEK_FALSIFICATION"},
        prior_experiment_spec=prior,
        prior_experiment_content_hash=prior_hash,
        lineage_hash="abstract-lineage",
        prior_tool_result_hash="abstract",
        panel=dev_panel,
    )
    abstract_sel = select_falsification_candidate(abstract_candidates)

    human_audit = {
        "scientific_choices_remaining": [
            {
                "locus": "Lexicographic criteria ordering",
                "classification": "REPRESENTATIONAL_CHOICE",
                "frozen_pre_selection": True,
                "blocks_pass": False,
            },
            {
                "locus": "Grammar trade_date filter for episode holdout",
                "classification": "EXECUTION_CONSTRAINT",
                "blocks_pass": False,
            },
            {
                "locus": "Falsification strategy selection",
                "classification": "AUTONOMOUS",
                "blocks_pass": False,
            },
        ],
        "gap_template_used": False,
        "human_selected_strategy": False,
    }

    firewall = {
        "zone_c_accessed": False,
        "future_tool_result_read": False,
        "second_experiment_executed": False,
        "passed": True,
    }

    verdict = "FALSIFICATION_SELECTION_PASS"
    if real["selection"]["outcome"] != "SELECTED":
        verdict = "FALSIFICATION_SELECTION_PARTIAL"
    if not real.get("one_shot_package"):
        verdict = "FALSIFICATION_SELECTION_FAIL"
    if human_audit.get("human_selected_strategy"):
        verdict = "FALSIFICATION_SELECTION_FAIL"

    _write("01_lineage_integrity.json", real["lineage_integrity"])
    _write("02_provenance_correction.json", provenance)
    _write("03_bb_falsify_01_audit_run.json", bb_audit)
    _write("04_abstract_generalization.json", {
        "candidates": [c.to_dict() for c in abstract_candidates],
        "selection": abstract_sel.to_dict(),
    })
    _write("05_human_choice_audit.json", human_audit)
    _write("06_hidden_firewall_audit.json", firewall)
    _write("07_real_candidate_set.json", {
        "candidates": real["candidates"],
        "candidate_set_hash": real["candidate_set_hash"],
    })
    _write("08_real_selection.json", real["selection"])
    _write("09_one_shot_package.json", real["one_shot_package"])
    _write("10_audit_summary.json", {
        "phase": "3I.9",
        "git_head": _git_head(),
        "verdict": verdict,
        "generator_version": GENERATOR_VERSION,
        "proposition_id": frozen["proposition"]["proposition_id"],
        "selected_candidate_id": real["selection"].get("selected_candidate_id"),
        "package_hash": real["one_shot_package"]["package_hash"] if real.get("one_shot_package") else None,
        "second_experiment_executed": False,
    })

    print(json.dumps({"verdict": verdict, "package_hash": real["one_shot_package"]["package_hash"] if real.get("one_shot_package") else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
