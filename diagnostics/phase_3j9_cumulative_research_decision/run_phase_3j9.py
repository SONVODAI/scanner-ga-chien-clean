#!/usr/bin/env python3
"""Phase 3J.9 — Cumulative research decision #2 diagnostics."""

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


def _git_branch() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_cf_cd() -> dict:
    from modules.edge_research.opr_bridge.bb_cumulative_research_decision_01_fixtures import (
        run_cf_cd_counterfactuals,
    )

    return run_cf_cd_counterfactuals()


def run_hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = [
        "july 27",
        "2.352",
        "expected_state",
        "directional_answer",
        "known_answer",
        "prop-efb650d9bd5c451f",
    ]
    hits = []
    patterns = list(root.glob("second_experiment_research*.py")) + [
        root / "production_second_experiment_research_decision.py",
        root / "bb_cumulative_research_decision_01_fixtures.py",
    ]
    for path in patterns:
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"file": path.name, "token": tok})
    return {"passed": len(hits) == 0, "hits": hits}


def run_regressions() -> dict:
    tests = [
        "tests/test_edge_research_opr_phase_3j9.py",
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
    from modules.edge_research.opr_bridge.production_second_experiment_research_decision import (
        run_production_second_experiment_research_decision,
    )
    from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
        STOP_SECOND_RESEARCH_DECISION_FROZEN,
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
        prop, session_id="phase-3j9-real-diagnostic",
        package_dict=package_dict, execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
    )
    dx = run_production_first_experiment_research_decision(
        prop, session_id="phase-3j9-real-diagnostic",
        package_dict=package_dict, interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    sx = run_production_second_experiment_design(
        prop, panel, session_id="phase-3j9-real-diagnostic",
        package_dict=package_dict, execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
    )
    ex2 = run_production_second_experiment_execution(
        prop, panel, session_id="phase-3j9-real-diagnostic",
        package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict,
    )
    ix2 = run_production_second_experiment_interpretation(
        prop, session_id="phase-3j9-real-diagnostic",
        package_dict=sx.design.package.to_dict(),
        execution_dict=ex2.execution.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
    )
    dx2 = run_production_second_experiment_research_decision(
        prop, session_id="phase-3j9-real-diagnostic",
        second_interpretation_dict=ix2.interpretation.envelope.to_dict(),
        first_decision_dict=dx.decision.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
    )

    env = dx2.decision.envelope
    cum_env = ix2.interpretation.envelope.cumulative_assessment if ix2.interpretation else None
    dep = cum_env.dependence_accounting if cum_env else None
    inc = cum_env.incremental_contribution if cum_env else None

    rejected = [
        {
            "action_family": e["action_family"] if isinstance(e, dict) else e.action_family,
            "rejection_reasons": e.get("rejection_reasons") if isinstance(e, dict) else list(e.rejection_reasons),
        }
        for e in (env.candidate_evaluations if env else [])
        if (e.get("admissible") if isinstance(e, dict) else e.admissible) is False
    ]

    return {
        "proposition_id": prop["proposition_id"],
        "resulting_epistemic_state": ix2.interpretation.envelope.resulting_epistemic_state if ix2.interpretation else None,
        "null_ledger": [n.to_dict() for n in cum_env.cumulative_null_ledger] if cum_env else [],
        "evidence_1_contribution": cum_env.per_experiment_assessments[0] if cum_env else None,
        "evidence_2_raw_strength": inc.raw_evidence_strength if inc else None,
        "evidence_2_incremental_strength": inc.incremental_strength if inc else None,
        "row_overlap": dep.row_overlap_fraction if dep else None,
        "counted_as_independent_replication": dep.counted_as_independent_replication if dep else None,
        "search_accounting": env.search_accounting.to_dict() if env else None,
        "surviving_nulls": list(env.surviving_nulls) if env else [],
        "candidate_action_families": [
            e.action_family if hasattr(e, "action_family") else e["action_family"]
            for e in (env.candidate_evaluations if env else [])
        ],
        "rejected_actions": rejected,
        "decision_kind": env.decision_kind if env else None,
        "stop_reason": env.stop_reason if env else None,
        "chosen_next_action": env.research_decision.get("chosen_next_action") if env else None,
        "confirmation_bias_guard_applied": env.confirmation_bias_guard_applied if env else None,
        "mechanical_sequencing_blocked": env.mechanical_sequencing_blocked if env else None,
        "third_experiment_generated": env.third_experiment_generated if env else None,
        "decision_envelope_id": env.decision_envelope_id if env else None,
        "decision_ordinal": env.decision_ordinal if env else None,
        "stop_boundary": STOP_SECOND_RESEARCH_DECISION_FROZEN,
        "idempotent_replay": dx2.idempotent_replay,
    }


def main() -> int:
    summary = {
        "phase": "3J.9",
        "branch": _git_branch(),
        "git_head": _git_head(),
        "cf_cd": run_cf_cd(),
        "hidden_answer_audit": run_hidden_answer_audit(),
        "real_diagnostic": run_real_diagnostic(),
        "regressions": run_regressions(),
    }
    _write("01_cf_cd_summary.json", summary["cf_cd"])
    _write("02_hidden_answer_audit.json", summary["hidden_answer_audit"])
    _write("03_real_diagnostic.json", summary["real_diagnostic"])
    _write("04_regression_summary.json", summary["regressions"])
    _write("05_audit_summary.json", {
        "phase": "3J.9",
        "branch": summary["branch"],
        "git_head": summary["git_head"],
        "cf_cd_all_passed": summary["cf_cd"].get("all_passed"),
        "hidden_answer_passed": summary["hidden_answer_audit"]["passed"],
        "real_diagnostic_proposition": summary["real_diagnostic"].get("proposition_id"),
        "decision_kind": summary["real_diagnostic"].get("decision_kind"),
        "chosen_next_action": summary["real_diagnostic"].get("chosen_next_action"),
        "stop_boundary": summary["real_diagnostic"].get("stop_boundary"),
        "third_experiment_generated": summary["real_diagnostic"].get("third_experiment_generated"),
        "regression_failures": [
            k for k, v in summary["regressions"].items()
            if v.get("exit_code", 0) != 0 and not v.get("skipped")
        ],
    })
    print(json.dumps(summary["real_diagnostic"], indent=2))
    failed = [
        k for k, v in summary["regressions"].items()
        if v.get("exit_code", 0) != 0 and not v.get("skipped")
    ]
    if not summary["cf_cd"].get("all_passed") or failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
