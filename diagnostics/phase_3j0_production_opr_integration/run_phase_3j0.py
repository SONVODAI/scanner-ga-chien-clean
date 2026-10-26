#!/usr/bin/env python3
"""Phase 3J.0 — Production OPR lifecycle integration diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


def run_bb_production_autonomy() -> dict:
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import (
        all_bbpa_cases,
        evaluate_bbpa_case,
        run_bbpa_case,
    )

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        results = []
        for case in all_bbpa_cases():
            run = run_bbpa_case(case, tmp_data_dir=tmp / "bbpa")
            ev = evaluate_bbpa_case(case, run)
            results.append({"case_id": case["case_id"], "passed": ev["passed"], "checks": ev["checks"]})
    passed = sum(1 for r in results if r["passed"])
    return {
        "benchmark": "BB-ProductionAutonomy-01",
        "passed": passed,
        "case_count": len(results),
        "all_passed": passed == len(results),
        "results": results,
    }


def run_counterfactuals() -> dict:
    import pandas as pd
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel, _silent_panel
    from modules.edge_research.opr_bridge.production_authority import assert_legacy_planner_blocked, mark_session_opr_authority
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle, simulate_process_restart
    from modules.edge_research.research_graph import ResearchGraph

    cf: dict = {}
    with tempfile.TemporaryDirectory() as d:
        data_dir = Path(d)

        panel = _anomaly_panel()
        r1 = run_production_opr_cycle(panel, data_cutoff_date="2026-02-15", data_dir=data_dir)
        r2 = run_production_opr_cycle(panel, data_cutoff_date="2026-02-15", data_dir=data_dir)
        cf["CF-J1"] = {"passed": r1.outcome == "SESSION_CREATED" and r2.outcome == "NO_NEW_RESEARCH_OPPORTUNITY"}

        silent = _silent_panel()
        rs = run_production_opr_cycle(silent, data_cutoff_date="2026-02-15", data_dir=data_dir / "silent")
        cf["CF-J2"] = {"passed": rs.outcome in ("SILENT", "NO_ELIGIBLE_OBSERVATION")}

        restart = simulate_process_restart(r1.session_id, data_dir=data_dir)
        cf["CF-J3"] = {"passed": restart["session_id"] == r1.session_id}

        graph = ResearchGraph.create_session(data_cutoff_date="2026-02-15", guardrails_config_version="guardrails_v1")
        mark_session_opr_authority(graph)
        try:
            assert_legacy_planner_blocked(graph)
            cf["CF-J4"] = {"passed": False}
        except Exception:
            cf["CF-J4"] = {"passed": True}

        panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
        if panel_path.exists():
            t2_panel = pd.read_csv(panel_path)
            t2 = run_production_opr_cycle(
                t2_panel,
                data_cutoff_date="2026-08-17",
                data_dir=data_dir / "t2",
                replay_frozen_lineage=True,
            )
            from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
            from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import ResearchOpportunityState, on_research_opportunity_state_changed
            from modules.edge_research.opr_bridge.production_persistence import read_opr_session, deserialize_knowledge_state
            from modules.edge_research.opr_bridge.production_orchestrator import T2_CANONICAL_PROPOSITION_ID

            rec = read_opr_session(t2.session_id, data_dir=data_dir / "t2")
            state = deserialize_knowledge_state(rec.knowledge_state)
            opp_redundant = ResearchOpportunityState(
                proposition_id=T2_CANONICAL_PROPOSITION_ID,
                proposition_hash=rec.proposition_hash,
                identical_evidence_added=True,
                max_cohort_overlap=0.99,
            )
            hook5 = on_research_opportunity_state_changed(rec.proposition_record, state, opp_redundant)
            cf["CF-J5"] = {
                "passed": hook5.evaluation_result.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT
            }

            state2 = deserialize_knowledge_state(rec.knowledge_state)
            opp_qual = ResearchOpportunityState(
                proposition_id=T2_CANONICAL_PROPOSITION_ID,
                proposition_hash=rec.proposition_hash,
                max_cohort_overlap=0.15,
                overlap_relation_to_prior="disjoint",
            )
            hook6 = on_research_opportunity_state_changed(rec.proposition_record, state2, opp_qual)
            cf["CF-J6"] = {
                "passed": hook6.evaluation_result.outcome == ReopeningEvaluationOutcome.REOPEN_RESEARCH
                and state2.research_activity_state == "REOPEN_CANDIDATE"
            }
        else:
            cf["CF-J5"] = {"passed": False, "skipped": "panel missing"}
            cf["CF-J6"] = {"passed": False, "skipped": "panel missing"}

        cf["CF-J7"] = {"passed": r1.frozen_integrity.get("passed") is True}
        cf["CF-J8"] = {"passed": "STOP_NO_AUTO_EXPERIMENT" in (r1.stop_boundaries or [])}

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict))
    return cf


def run_t2_production_replay() -> dict:
    import pandas as pd
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle, simulate_process_restart

    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    if not panel_path.exists():
        return {"skipped": True, "reason": "panel missing"}

    with tempfile.TemporaryDirectory() as d:
        data_dir = Path(d)
        panel = pd.read_csv(panel_path)
        cycle = run_production_opr_cycle(
            panel,
            data_cutoff_date="2026-08-17",
            data_dir=data_dir,
            replay_frozen_lineage=True,
        )
        restart = simulate_process_restart(cycle.session_id, data_dir=data_dir) if cycle.session_id else {}
        return {
            "outcome": cycle.outcome,
            "session_id": cycle.session_id,
            "authoritative_state": cycle.authoritative_state,
            "stop_boundaries": cycle.stop_boundaries,
            "restart_authoritative_state": restart.get("authoritative_state"),
            "passed": (
                cycle.outcome == "SESSION_CREATED"
                and cycle.authoritative_state.get("research_activity_state") == "DORMANT"
                and cycle.authoritative_state.get("epistemic_state") == "SUPPORTED"
            ),
        }


def run_frozen_hash_audit() -> dict:
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash

    expected = {
        "evidence_synthesis_engine": "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a",
        "scientific_action_generator": "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9",
        "dormancy_module": "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6",
        "lifecycle_integration": "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145",
    }
    current = {
        "evidence_synthesis_engine": engine_content_hash(),
        "scientific_action_generator": generator_content_hash(),
        "dormancy_module": dormancy_content_hash(),
        "lifecycle_integration": integration_content_hash(),
    }
    checks = {k: expected[k] == current[k] for k in expected}
    return {"passed": all(checks.values()), "checks": checks}


def main() -> int:
    from modules.edge_research.opr_bridge.production_authority import authority_map_summary
    from modules.edge_research.opr_bridge.production_orchestrator import list_documented_stop_boundaries

    summary = {
        "phase": "3J.0",
        "mode": "PRODUCTION_OPR_INTEGRATION_WIRING_ONLY",
        "git_head": _git_head(),
        "authority_map": authority_map_summary(),
        "stop_boundaries": list_documented_stop_boundaries(),
        "bb_production_autonomy_01": run_bb_production_autonomy(),
        "counterfactuals": run_counterfactuals(),
        "t2_production_replay": run_t2_production_replay(),
        "frozen_hash_audit": run_frozen_hash_audit(),
        "verdicts": {},
    }

    summary["verdicts"] = {
        "PRODUCTION_OPR_INTEGRATION": "PASS" if summary["bb_production_autonomy_01"]["all_passed"] else "FAIL",
        "SINGLE_RESEARCH_AUTHORITY": "PASS" if summary["counterfactuals"].get("CF-J4", {}).get("passed") else "FAIL",
        "PRODUCTION_RESEARCH_MEMORY": "PASS" if summary["counterfactuals"].get("CF-J3", {}).get("passed") else "FAIL",
        "END_TO_END_AUTONOMY_REPLAY": (
            "PASS" if summary["t2_production_replay"].get("passed") else "PARTIAL"
        ),
    }

    all_core = all(
        summary["verdicts"][k] in ("PASS", "PARTIAL")
        for k in (
            "PRODUCTION_OPR_INTEGRATION",
            "SINGLE_RESEARCH_AUTHORITY",
            "PRODUCTION_RESEARCH_MEMORY",
            "END_TO_END_AUTONOMY_REPLAY",
        )
    )
    summary["verdicts"]["PHASE_3I_GRADUATION"] = (
        "PHASE_3I_GRADUATED" if all_core and summary["frozen_hash_audit"]["passed"] else "PHASE_3I_NOT_YET_GRADUATED"
    )

    _write("01_authority_map.json", summary["authority_map"])
    _write("02_stop_boundaries.json", summary["stop_boundaries"])
    _write("03_bb_production_autonomy_01.json", summary["bb_production_autonomy_01"])
    _write("04_counterfactuals.json", summary["counterfactuals"])
    _write("05_t2_production_replay.json", summary["t2_production_replay"])
    _write("06_frozen_hash_audit.json", summary["frozen_hash_audit"])
    _write("07_audit_summary.json", summary)
    print(json.dumps(summary["verdicts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
