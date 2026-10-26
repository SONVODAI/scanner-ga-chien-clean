#!/usr/bin/env python3
"""Phase 3K.5 — LIVE_FORWARD production readiness diagnostics."""

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
    path = OUT / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


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
    from modules.edge_research.opr_bridge.bb_live_forward_production_readiness_01_fixtures import run_cf_ready_counterfactuals
    from modules.edge_research.opr_bridge.production_day0_smoke import run_day0_smoke
    from modules.edge_research.opr_bridge.production_pre_deployment_dry_run import run_pre_deployment_dry_run
    from modules.edge_research.opr_bridge.production_readiness_audit import run_full_production_readiness_audit
    from modules.edge_research.opr_bridge.production_timezone_audit import derive_vn_trade_date

    audit = run_full_production_readiness_audit(REPO)
    _write("00_full_readiness_audit.json", audit)
    _write("01_readiness_matrix.json", audit.get("readiness_matrix", {}))

    cf = run_cf_ready_counterfactuals(REPO)
    _write("02_cf_ready_summary.json", cf)

    panel = build_research_panel()
    dry = smoke = {"error": "empty_panel"}
    if not panel.empty:
        import pandas as pd
        target = str(pd.to_datetime(panel["trade_date"]).max().date())
        dry = run_pre_deployment_dry_run(panel, target_trade_date=target, repo_root=REPO)
        smoke = run_day0_smoke(panel, target_trade_date=target, repo_root=REPO)
    _write("03_pre_deployment_dry_run.json", dry)
    _write("04_day0_smoke.json", smoke)

    regressions = _run_regressions([
        "tests/test_edge_research_opr_phase_3k5.py",
        "tests/test_edge_research_opr_phase_3k4.py::test_ui_read_model_fixtures",
        "tests/test_edge_research_opr_phase_3k3.py::test_cf_cal_counterfactuals",
        "tests/test_edge_research_opr_phase_3k2.py::test_cf_run_counterfactuals",
        "tests/test_edge_research_opr_phase_3k1.py::test_cf_live_counterfactuals",
        "tests/test_edge_research_opr_phase_3k0.py",
        "tests/test_edge_research_opr_phase_3j14a.py",
        "tests/test_edge_research_opr_phase_3j10.py::test_cf_arl1_arl12_pass",
    ])
    _write("05_regression_summary.json", regressions)

    summary = {
        "head": _git_head(),
        "phase": "3K.5",
        "stop_boundary": "STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED",
        "vn_trade_date": derive_vn_trade_date(),
        "cf_ready_pass": cf.get("all_passed"),
        "dry_run_non_forward": dry.get("counts_as_forward_evidence") is False if isinstance(dry, dict) else False,
        "day0_smoke_non_forward": smoke.get("counts_as_forward_evidence") is False if isinstance(smoke, dict) else False,
        "live_forward_activated": False,
        "genesis_exists": audit.get("genesis_exists") is False,
        "readiness_matrix": audit.get("readiness_matrix", {}).get("matrix"),
        "any_fail": audit.get("readiness_matrix", {}).get("any_fail"),
        "deployment_recommendation": audit.get("deployment_recommendation"),
        "regressions_pass": regressions.get("all_passed"),
        "phase_pass": (
            cf.get("all_passed")
            and not audit.get("readiness_matrix", {}).get("any_fail")
            and dry.get("counts_as_forward_evidence") is False
            and smoke.get("counts_as_forward_evidence") is False
            and audit.get("live_forward_activated") is False
            and regressions.get("all_passed")
        ),
    }
    _write("06_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
