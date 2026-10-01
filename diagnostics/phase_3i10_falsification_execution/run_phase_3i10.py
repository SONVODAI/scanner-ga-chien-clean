#!/usr/bin/env python3
"""
Phase 3I.10 — One-shot autonomous falsification execution.

CRITICAL: Executes exactly once from frozen 3I.9 package. No regeneration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I39 = REPO / "diagnostics/phase_3i9_falsification_selection/artifacts"
PACKAGE_PATH = I39 / "09_one_shot_package.json"
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"

sys.path.insert(0, str(REPO))

import pandas as pd

from modules.edge_research.opr_bridge.falsification_execution_runner import (
    EXECUTION_VERSION,
    EXPECTED_PACKAGE_HASH,
    load_one_shot_package,
    run_one_shot_falsification_execution,
)


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _trim_raw_tool_result(raw: dict | None) -> dict | None:
    if not raw:
        return raw
    out = dict(raw)
    if "raw" in out and isinstance(out["raw"], dict):
        inner = dict(out["raw"])
        if "groups" in inner and len(str(inner["groups"])) > 2000:
            inner["groups"] = {"truncated": True, "keys": list(inner["groups"].keys())[:10]}
        out["raw"] = inner
    return out


def main() -> int:
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3i10.py", "-q"],
        cwd=REPO,
    )
    if rc != 0:
        print("Pre-execution tests failed — aborting")
        return 1

    package = load_one_shot_package(PACKAGE_PATH)
    proposition = json.loads((I37 / "02_frozen_proposition.json").read_text())["full_record"]
    prior_update = json.loads((I37 / "07_epistemic_update.json").read_text())
    prior_decision = json.loads((I37 / "08_research_decision.json").read_text())
    candidate = json.loads((I39 / "07_real_candidate_set.json").read_text())["candidates"][0]
    lineage = json.loads((I37 / "09_append_only_lineage.json").read_text())
    contract = json.loads((I37 / "03_interpretation_contract.json").read_text())
    panel = pd.read_csv(PANEL)

    result = run_one_shot_falsification_execution(
        package,
        proposition=proposition,
        prior_epistemic_update=prior_update,
        prior_research_decision=prior_decision,
        candidate_record=candidate,
        lineage=lineage,
        interpretation_contract_dict=contract,
        panel=panel,
    )

    _write("01_package_integrity.json", result.get("integrity", {}))
    _write("02_raw_tool_result.json", _trim_raw_tool_result(result.get("raw_tool_result")))
    _write("03_interpretation.json", result.get("interpretation"))
    _write("04_transition_audit.json", result.get("transition_audit"))
    _write("05_epistemic_update.json", result.get("epistemic_update"))
    _write("06_research_decision.json", result.get("research_decision"))
    _write("07_independence_audit.json", {
        "pre_execution": result.get("independence_audit"),
        "operational_post_execution": result.get("operational_independence_audit"),
    })
    _write("08_proposition_audit.json", result.get("proposition_audit"))
    _write("09_package_audit.json", result.get("package_audit"))
    _write("10_firewall_audit.json", result.get("firewall_audit"))
    _write("11_append_lineage.json", result.get("append_lineage"))
    _write("12_audit_summary.json", {
        "phase": "3I.10",
        "execution_version": EXECUTION_VERSION,
        "git_head": _git_head(),
        "expected_package_hash": EXPECTED_PACKAGE_HASH,
        "package_hash": package.get("package_hash"),
        "verdict": result.get("verdict"),
        "executed": result.get("executed", False),
        "evidence_class": result.get("evidence_class"),
        "prior_state": result.get("prior_state"),
        "resulting_state": result.get("resulting_state"),
        "execution_id": result.get("execution_id"),
        "one_shot_execution_count": result.get("one_shot_proof", {}).get("execution_count", 0),
    })

    print(json.dumps({
        "verdict": result.get("verdict"),
        "evidence_class": result.get("evidence_class"),
        "prior_state": result.get("prior_state"),
        "resulting_state": result.get("resulting_state"),
    }, indent=2))
    return 0 if result.get("verdict") != "PACKAGE_INTEGRITY_FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
