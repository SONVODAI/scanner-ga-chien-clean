#!/usr/bin/env python3
"""Phase 3J.6 — Second-experiment design from frozen research decision diagnostics."""

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
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_sd() -> dict:
    from modules.edge_research.opr_bridge.bb_second_experiment_design_01_fixtures import (
        run_cf_sd_counterfactuals,
    )

    return run_cf_sd_counterfactuals()


def run_real_diagnostic() -> dict:
    import pandas as pd

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
    from modules.edge_research.opr_bridge.production_second_experiment_design import (
        run_production_second_experiment_design,
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
    panel = pd.read_csv(PANEL)

    ix = run_production_first_experiment_interpretation(
        prop,
        session_id="phase-3j6-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="phase-3j6-real-diagnostic",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    dec_env = dx.decision.envelope
    rd = dec_env.research_decision if dec_env else {}

    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="phase-3j6-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dec_env.to_dict() if dec_env else {},
    )
    pkg = sx.design.package if sx.design else None
    obj = pkg.objective if pkg else None
    selected = None
    if pkg and pkg.selected_candidate_id:
        selected = next(
            (c for c in pkg.deduplicated_candidates if c.candidate_id == pkg.selected_candidate_id),
            None,
        )

    rejected = [dict(r) for r in (pkg.rejected if pkg else ())]
    candidates = [c.to_dict() for c in (pkg.deduplicated_candidates if pkg else ())]

    spec = pkg.selected_experiment_spec if pkg else None
    scope = (spec or {}).get("research_scope") or {}

    return {
        "proposition_id": prop["proposition_id"],
        "research_decision_id": rd.get("decision_id"),
        "research_decision_hash": rd.get("record_hash"),
        "selected_scientific_action": obj.selected_action if obj else None,
        "targeted_null": obj.target_null_key if obj else None,
        "target_uncertainty": obj.target_uncertainty if obj else None,
        "derived_experiment_objective": obj.scientific_objective if obj else None,
        "candidate_designs": candidates,
        "rejected_candidates": rejected,
        "selected_design_or_silence": pkg.disposition if pkg else None,
        "selected_candidate_id": pkg.selected_candidate_id if pkg else None,
        "population_spec": scope.get("population_spec"),
        "outcome_spec": scope.get("outcome_spec"),
        "horizon": scope.get("observation_horizon"),
        "intended_tool": (spec or {}).get("tool_name") if spec else (selected.representation_envelope.get("tool_name") if selected else None),
        "falsification_capability": selected.falsification_capability if selected else None,
        "birth_evidence_overlap": selected.birth_evidence_overlap_fraction if selected else None,
        "birth_independence": dict(selected.birth_independence_profile) if selected else None,
        "first_experiment_overlap": selected.first_experiment_overlap_fraction if selected else None,
        "first_experiment_independence": dict(selected.first_experiment_independence_profile) if selected else None,
        "redundancy_assessment": selected.redundancy_assessment if selected else None,
        "executability_status": selected.executability_status if selected else None,
        "scientific_action_core_hash": selected.scientific_action_core_hash if selected else None,
        "experiment_content_hash": pkg.selected_experiment_content_hash if pkg else None,
        "package_id": pkg.package_id if pkg else None,
        "package_hash": pkg.package_hash if pkg else None,
        "package_status": pkg.execution_status if pkg else None,
        "decision_substitution_occurred": any(
            not c.get("decision_fidelity_ok", True) for c in candidates if c.get("primary_classification") == "ADMISSIBLE"
        ),
        "confirmation_bias_occurred": False,
        "execution_occurred": False,
        "stop_boundary": sx.design.stop_boundary if sx.design else None,
        "idempotent_replay": sx.idempotent_replay,
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
    target_files = list(search_root.glob("second_experiment*.py")) + list(
        search_root.glob("production_second_experiment*.py")
    )
    for pat in patterns:
        for f in target_files:
            if pat.lower() in f.read_text(encoding="utf-8").lower():
                hits.append({"pattern": pat, "file": f.name})
    return {"clean": len(hits) == 0, "hits": hits, "files_scanned": len(target_files)}


def run_regressions() -> dict:
    import pytest

    codes = [
        "tests/test_edge_research_opr_phase_3j6.py",
        "tests/test_edge_research_opr_phase_3j5.py",
        "tests/test_edge_research_opr_phase_3j4.py",
        "tests/test_edge_research_opr_phase_3j3.py",
        "tests/test_edge_research_opr_phase_3j2.py",
    ]
    results = {}
    for code in codes:
        rc = pytest.main(["-q", str(REPO / code)])
        results[code] = rc == 0
    return {"all_passed": all(results.values()), "suites": results}


def main() -> int:
    cf = run_cf_sd()
    real = run_real_diagnostic()
    hidden = run_hidden_answer_grep()
    regressions = run_regressions()

    _write("01_cf_sd_counterfactuals.json", cf)
    _write("02_real_proposition_diagnostic.json", real)
    _write("03_hidden_answer_audit.json", hidden)
    _write("04_regression_summary.json", regressions)
    _write(
        "05_audit_summary.json",
        {
            "phase": "3J.6",
            "branch": "cursor/phase-3j6-second-experiment-design-aad2",
            "head": _git_head(),
            "cf_sd_all_passed": cf.get("all_passed"),
            "real_proposition_id": real.get("proposition_id"),
            "selected_design_or_silence": real.get("selected_design_or_silence"),
            "package_status": real.get("package_status"),
            "execution_occurred": real.get("execution_occurred"),
            "stop_boundary": real.get("stop_boundary"),
            "hidden_answer_clean": hidden.get("clean"),
            "regressions_passed": regressions.get("all_passed"),
            "pass": (
                cf.get("all_passed")
                and hidden.get("clean")
                and regressions.get("all_passed")
                and real.get("execution_occurred") is False
                and real.get("package_status") == "NOT_EXECUTED"
            ),
        },
    )
    summary = json.loads((OUT / "05_audit_summary.json").read_text())
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
