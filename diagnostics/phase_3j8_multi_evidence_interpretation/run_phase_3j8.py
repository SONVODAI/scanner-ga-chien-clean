#!/usr/bin/env python3
"""Phase 3J.8 — Multi-evidence interpretation diagnostics."""

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


def run_cf_mei() -> dict:
    from modules.edge_research.opr_bridge.bb_multi_evidence_interpretation_01_fixtures import (
        run_cf_mei_counterfactuals,
    )

    return run_cf_mei_counterfactuals()


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["july 27", "2.352", "expected_state", "directional_answer", "known_answer"]
    hits = []
    for path in sorted(root.glob("second_experiment_*interpret*.py")) + [root / "multi_evidence_accounting.py"]:
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"file": path.name, "token": tok})
    return {"passed": len(hits) == 0, "hits": hits}


def run_regressions() -> dict:
    tests = [
        "tests/test_edge_research_opr_phase_3j8.py",
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
    from modules.edge_research.opr_bridge.production_second_experiment_interpretation import (
        run_production_second_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
        STOP_SECOND_EVIDENCE_INTERPRETED,
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
        session_id="phase-3j8-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="phase-3j8-real-diagnostic",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="phase-3j8-real-diagnostic",
        package_dict=package_dict,
        execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
    )
    ex2 = run_production_second_experiment_execution(
        prop,
        panel,
        session_id="phase-3j8-real-diagnostic",
        package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict,
    )
    env_exec = ex2.execution.envelope
    assert env_exec is not None

    ix2 = run_production_second_experiment_interpretation(
        prop,
        session_id="phase-3j8-real-diagnostic",
        package_dict=sx.design.package.to_dict(),
        execution_dict=env_exec.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    env = ix2.interpretation.envelope if ix2.interpretation else None
    cum = env.cumulative_assessment if env else None
    dep = cum.dependence_accounting if cum else None
    inc = cum.incremental_contribution if cum else None

    return {
        "proposition_id": prop["proposition_id"],
        "experiment_2_objective": sx.design.package.objective.scientific_objective if sx.design else None,
        "target_null": sx.design.package.objective.target_null_key if sx.design else None,
        "frozen_contract_hash": env.frozen_contract_ref.contract_hash if env else None,
        "frozen_contract_ref_hash": env.frozen_contract_ref.ref_hash if env else None,
        "tool_result_hash": env_exec.tool_result_hash,
        "execution_id": env_exec.execution_id,
        "evidence_relevance": env.evidence_assessment.evidence_relevance if env else None,
        "evidence_direction": env.evidence_assessment.evidence_direction if env else None,
        "raw_evidence_strength": inc.raw_evidence_strength if inc else None,
        "row_overlap": dep.row_overlap_fraction if dep else None,
        "question_novelty": dep.question_novelty if dep else None,
        "incremental_strength": inc.incremental_strength if inc else None,
        "incremental_direction": inc.incremental_direction if inc else None,
        "counted_as_independent_replication": dep.counted_as_independent_replication if dep else None,
        "double_counting_blocked": inc.double_counting_blocked if inc else None,
        "cumulative_summary": cum.cumulative_evidence_summary if cum else None,
        "null_ledger": [n.to_dict() for n in cum.cumulative_null_ledger] if cum else [],
        "prior_epistemic_state": env.prior_epistemic_state if env else None,
        "resulting_epistemic_state": env.resulting_epistemic_state if env else None,
        "limitations": list(cum.limitations) if cum else [],
        "research_decision_generated": env.research_decision_generated if env else None,
        "interpretation_id": env.interpretation_id if env else None,
        "stop_boundary": STOP_SECOND_EVIDENCE_INTERPRETED,
        "idempotent_replay": ix2.idempotent_replay,
    }


def main() -> int:
    summary = {
        "phase": "3J.8",
        "branch": "cursor/phase-3j8-multi-evidence-interpretation-aad2",
        "git_head": _git_head(),
        "cf_mei": run_cf_mei(),
        "hidden_answer_audit": run_hidden_answer_audit(),
        "real_diagnostic": run_real_diagnostic(),
        "regressions": run_regressions(),
    }
    _write("01_cf_mei_summary.json", summary["cf_mei"])
    _write("02_hidden_answer_audit.json", summary["hidden_answer_audit"])
    _write("03_real_diagnostic.json", summary["real_diagnostic"])
    _write("04_regression_summary.json", summary["regressions"])
    _write("05_audit_summary.json", {
        "phase": "3J.8",
        "git_head": summary["git_head"],
        "cf_mei_all_passed": summary["cf_mei"].get("all_passed"),
        "hidden_answer_passed": summary["hidden_answer_audit"]["passed"],
        "real_diagnostic_proposition": summary["real_diagnostic"].get("proposition_id"),
        "prior_state": summary["real_diagnostic"].get("prior_epistemic_state"),
        "resulting_state": summary["real_diagnostic"].get("resulting_epistemic_state"),
        "counted_independent": summary["real_diagnostic"].get("counted_as_independent_replication"),
        "stop_boundary": summary["real_diagnostic"].get("stop_boundary"),
        "regression_failures": [
            k for k, v in summary["regressions"].items()
            if v.get("exit_code", 0) != 0 and not v.get("skipped")
        ],
    })
    print(json.dumps(summary["cf_mei"], indent=2))
    failed = [
        k for k, v in summary["regressions"].items()
        if v.get("exit_code", 0) != 0 and not v.get("skipped")
    ]
    if not summary["cf_mei"].get("all_passed") or failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
