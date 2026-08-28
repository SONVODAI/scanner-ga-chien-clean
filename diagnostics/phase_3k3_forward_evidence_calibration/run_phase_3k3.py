#!/usr/bin/env python3
"""Phase 3K.3 — Forward evidence & calibration ledger diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


def _run_regressions(tests: list[str]) -> dict:
    results = []
    for t in tests:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", t, "-q", "--tb=line"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results.append({"test": t, "passed": proc.returncode == 0, "output": (proc.stdout + proc.stderr)[-2000:]})
    return {"all_passed": all(r["passed"] for r in results), "results": results}


def main() -> int:
    from modules.edge_research.adapters import build_research_panel
    from modules.edge_research.opr_bridge.bb_forward_evidence_calibration_01_fixtures import run_cf_cal_counterfactuals
    from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
    from modules.edge_research.opr_bridge.production_calibration_self_knowledge import build_self_knowledge_read_model
    from modules.edge_research.opr_bridge.production_calibration_simulation import run_calibration_mechanics_simulation
    from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit

    policy = {"frozen_at_head": _git_head(), "policy_hashes": compute_research_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy)

    cf = run_cf_cal_counterfactuals(REPO)
    _write("01_cf_cal_summary.json", cf)

    panel = build_research_panel()
    sim = {"error": "empty_panel"}
    self_knowledge = build_self_knowledge_read_model()
    if not panel.empty:
        dates = sorted(panel["trade_date"].astype(str).unique())
        with tempfile.TemporaryDirectory() as tmp:
            sim = run_calibration_mechanics_simulation(
                panel,
                num_sessions=min(12, len(dates)),
                data_dir=Path(tmp),
                repo_root=REPO,
            )
            self_knowledge = build_self_knowledge_read_model(data_dir=Path(tmp))
    _write("02_calibration_mechanics_simulation.json", sim)
    _write("03_self_knowledge_read_model.json", self_knowledge)

    trading_iso = run_trading_isolation_audit(REPO)
    _write("04_trading_isolation_audit.json", trading_iso)

    full_regressions = _run_regressions([
        "tests/test_edge_research_opr_phase_3k3.py",
        "tests/test_edge_research_opr_phase_3k2.py::test_cf_run_counterfactuals",
        "tests/test_edge_research_opr_phase_3k1.py::test_cf_live_counterfactuals",
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
        "phase": "3K.3",
        "stop_boundary": "STOP_FORWARD_EVIDENCE_CALIBRATION_READY",
        "cf_cal_pass": cf.get("all_passed"),
        "simulation_backfill_rejected": sim.get("all_backfill_rejected_from_forward_ledger"),
        "forward_ledger_entry_count": sim.get("forward_ledger_entry_count"),
        "idempotent_rebuild": sim.get("idempotent_rebuild"),
        "trading_isolation_pass": trading_iso.get("passed"),
        "self_knowledge_no_buy_sell": self_knowledge.get("no_buy_sell"),
        "regressions_pass": full_regressions.get("all_passed"),
        "phase_pass": (
            cf.get("all_passed")
            and sim.get("all_backfill_rejected_from_forward_ledger") is True
            and sim.get("forward_ledger_entry_count") == 0
            and sim.get("idempotent_rebuild") is True
            and trading_iso.get("passed")
            and self_knowledge.get("no_buy_sell") is True
            and full_regressions.get("all_passed")
        ),
    }
    _write("06_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
