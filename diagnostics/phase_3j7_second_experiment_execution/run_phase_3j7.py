#!/usr/bin/env python3
"""Phase 3J.7 — Second-experiment execution diagnostics."""

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


def run_cf_se() -> dict:
    from modules.edge_research.opr_bridge.bb_second_experiment_execution_01_fixtures import (
        run_cf_se_counterfactuals,
    )

    return run_cf_se_counterfactuals()


def run_regressions() -> dict:
    tests = [
        "tests/test_edge_research_opr_phase_3j7.py",
        "tests/test_edge_research_opr_phase_3j6a.py",
        "tests/test_edge_research_opr_phase_3j6.py",
        "tests/test_edge_research_opr_phase_3j5.py",
        "tests/test_edge_research_opr_phase_3j4.py",
        "tests/test_edge_research_opr_phase_3j3.py",
        "tests/test_edge_research_opr_phase_3j2.py",
    ]
    results = {}
    for t in tests:
        path = REPO / t
        if not path.exists():
            results[t] = {"skipped": True}
            continue
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "-q", "--tb=no"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results[t] = {"exit_code": proc.returncode, "stdout_tail": proc.stdout[-500:]}
    return results


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = [
        "july 27", "july_27", "expected_outcome", "known_answer",
        "prop_wins", "prop_loses", "directional_answer",
    ]
    hits = []
    for path in sorted(root.glob("second_experiment_execution*.py")) + [
        root / "second_experiment_executor.py",
        root / "production_second_experiment_execution.py",
        root / "bb_second_experiment_execution_01_fixtures.py",
    ]:
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"file": path.name, "token": tok})
    return {"passed": len(hits) == 0, "hits": hits}


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
    from modules.edge_research.opr_bridge.production_second_experiment_execution import (
        run_production_second_experiment_execution,
    )
    from modules.edge_research.opr_bridge.second_experiment_execution_records import (
        STOP_SECOND_EXPERIMENT_EXECUTED,
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
        session_id="phase-3j7-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="phase-3j7-real-diagnostic",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    dec_env = dx.decision.envelope
    rd = dec_env.research_decision if dec_env else {}

    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="phase-3j7-real-diagnostic",
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

    ex2 = run_production_second_experiment_execution(
        prop,
        panel,
        session_id="phase-3j7-real-diagnostic",
        package_dict=pkg.to_dict() if pkg else {},
        decision_dict=dec_env.to_dict() if dec_env else {},
        first_execution_dict=execution_dict,
    )
    env = ex2.execution.envelope if ex2.execution else None
    audit = env.binding_audit if env else None
    spec = pkg.selected_experiment_spec if pkg else {}
    scope = (spec or {}).get("research_scope") or {}
    nd = env.novelty_decomposition if env else {}

    return {
        "proposition_id": prop["proposition_id"],
        "research_decision_id": rd.get("decision_id"),
        "research_decision_hash": rd.get("record_hash"),
        "second_experiment_package_id": pkg.package_id if pkg else None,
        "second_experiment_package_hash": pkg.package_hash if pkg else None,
        "scientific_action_core_hash": selected.scientific_action_core_hash if selected else None,
        "target_null": obj.target_null_key if obj else None,
        "target_uncertainty": obj.target_uncertainty if obj else None,
        "novelty_decomposition": nd,
        "population_spec": scope.get("population_spec"),
        "outcome_spec": scope.get("outcome_spec"),
        "horizon": scope.get("observation_horizon"),
        "tool": (spec or {}).get("tool_name"),
        "binding_audit": audit.to_dict() if audit else None,
        "eligibility": ex2.execution.eligibility.to_dict() if ex2.execution else None,
        "execution_status": ex2.execution.outcome if ex2.execution else None,
        "tool_result_identity": env.tool_result_hash if env else None,
        "execution_envelope_id": env.execution_id if env else None,
        "execution_identity_hash": env.execution_identity_hash if env else None,
        "sample_size": env.sample_size if env else None,
        "raw_quintile_metrics": env.raw_quintile_metrics if env else None,
        "tool_result_status": env.tool_status if env else None,
        "provenance": {
            "panel_provenance_hash": env.panel_provenance_hash if env else None,
            "package_hash": env.package_hash if env else None,
        },
        "scientific_identity_survived": ex2.execution.substitution_occurred is False if ex2.execution else None,
        "substitution_occurred": ex2.execution.substitution_occurred if ex2.execution else None,
        "interpretation_occurred": ex2.execution.interpretation_generated if ex2.execution else None,
        "research_decision_occurred": ex2.execution.research_decision_generated if ex2.execution else None,
        "stop_boundary": STOP_SECOND_EXPERIMENT_EXECUTED,
        "idempotent_replay": ex2.idempotent_replay,
    }


def main() -> int:
    summary = {
        "phase": "3J.7",
        "branch": "cursor/phase-3j7-second-experiment-execution-aad2",
        "git_head": _git_head(),
        "cf_se": run_cf_se(),
        "hidden_answer_audit": run_hidden_answer_audit(),
        "real_diagnostic": run_real_diagnostic(),
        "regressions": run_regressions(),
    }
    _write("01_cf_se_summary.json", summary["cf_se"])
    _write("02_hidden_answer_audit.json", summary["hidden_answer_audit"])
    _write("03_real_diagnostic.json", summary["real_diagnostic"])
    _write("04_regression_summary.json", summary["regressions"])
    _write("05_audit_summary.json", {
        "phase": "3J.7",
        "git_head": summary["git_head"],
        "cf_se_all_passed": summary["cf_se"].get("all_passed"),
        "hidden_answer_passed": summary["hidden_answer_audit"]["passed"],
        "real_diagnostic_proposition": summary["real_diagnostic"].get("proposition_id"),
        "execution_status": summary["real_diagnostic"].get("execution_status"),
        "stop_boundary": summary["real_diagnostic"].get("stop_boundary"),
        "regression_failures": [
            k for k, v in summary["regressions"].items()
            if v.get("exit_code", 0) != 0 and not v.get("skipped")
        ],
    })
    print(json.dumps(summary["cf_se"], indent=2))
    regress_fail = summary["regressions"]
    failed = [k for k, v in regress_fail.items() if v.get("exit_code", 0) != 0 and not v.get("skipped")]
    if not summary["cf_se"].get("all_passed") or failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
