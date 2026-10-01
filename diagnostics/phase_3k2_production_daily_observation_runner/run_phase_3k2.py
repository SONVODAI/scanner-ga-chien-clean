#!/usr/bin/env python3
"""Phase 3K.2 — Production daily observation runner diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    from modules.edge_research.adapters import build_research_panel
    from modules.edge_research.opr_bridge.bb_production_daily_run_01_fixtures import run_cf_run_counterfactuals
    from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
    from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_simulation_15_sessions
    from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
    from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract

    policy = {"frozen_at_head": _git_head(), "policy_hashes": compute_research_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy)

    cf = run_cf_run_counterfactuals(REPO)
    _write("01_cf_run_summary.json", cf)

    panel = build_research_panel()
    import tempfile

    sim = {"error": "empty_panel"}
    if not panel.empty:
        dates = sorted(panel["trade_date"].astype(str).unique())
        with tempfile.TemporaryDirectory() as tmp:
            sim = run_production_simulation_15_sessions(
                panel,
                start_trade_date=dates[0],
                num_sessions=15,
                data_dir=Path(tmp),
                repo_root=REPO,
            )
    _write("02_production_simulation_15_sessions.json", sim)

    scheduling = build_scheduling_contract()
    _write("03_scheduling_contract.json", scheduling)

    trading_iso = run_trading_isolation_audit(REPO)
    _write("04_trading_isolation_audit.json", trading_iso)

    regressions = _run_regressions(["tests/test_edge_research_opr_phase_3k2.py::test_cf_run_counterfactuals"])
    full_regressions = _run_regressions([
        "tests/test_edge_research_opr_phase_3k2.py",
        "tests/test_edge_research_opr_phase_3k1.py",
        "tests/test_edge_research_opr_phase_3k0.py",
        "tests/test_edge_research_opr_phase_3j14a.py",
        "tests/test_edge_research_opr_phase_3j14.py::test_cf_cg_counterfactuals",
        "tests/test_edge_research_opr_phase_3j13.py::test_cf_fg_counterfactuals",
        "tests/test_edge_research_opr_phase_3j12.py::test_cf_nx_counterfactuals",
        "tests/test_edge_research_opr_phase_3j11.py::test_cf_br_counterfactuals",
        "tests/test_edge_research_opr_phase_3j10.py::test_cf_arl1_arl12_pass",
    ])
    _write("05_regression_summary.json", full_regressions)

    summary = {
        "head": _git_head(),
        "phase": "3K.2",
        "stop_boundary": "STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY",
        "cf_run_pass": cf.get("all_passed"),
        "simulation_sessions": sim.get("num_sessions"),
        "counts_as_forward_evidence": sim.get("counts_as_forward_evidence"),
        "duplicate_idempotent": sim.get("duplicate_invocation_idempotent"),
        "scheduling_activated": scheduling.get("activated"),
        "trading_isolation_pass": trading_iso.get("passed"),
        "regressions_pass": full_regressions.get("all_passed"),
        "phase_pass": (
            cf.get("all_passed")
            and (sim.get("num_sessions") or 0) >= 15
            and sim.get("counts_as_forward_evidence") is False
            and not scheduling.get("activated")
            and trading_iso.get("passed")
            and full_regressions.get("all_passed")
        ),
    }
    _write("06_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


def _run_regressions(suites: list) -> dict:
    results = {}
    for suite in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q", "--tb=no"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results[suite] = {"passed": proc.returncode == 0, "tail": (proc.stdout or proc.stderr).strip().split("\n")[-1]}
    return {"suites": results, "all_passed": all(r["passed"] for r in results.values())}


if __name__ == "__main__":
    raise SystemExit(main())
