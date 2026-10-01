#!/usr/bin/env python3
"""Phase 3K.5A diagnostic runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_production_prerequisite_01_fixtures import run_cf_pr_counterfactuals
from modules.edge_research.opr_bridge.production_prerequisite_closure_audit import run_prerequisite_closure_audit


def _head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    cf = run_cf_pr_counterfactuals(REPO)
    audit = run_prerequisite_closure_audit(REPO)

    (OUT / "00_prerequisite_closure_audit.json").write_text(
        json.dumps(audit, indent=2, default=str), encoding="utf-8"
    )
    (OUT / "01_go_no_go_matrix.json").write_text(
        json.dumps(audit["go_no_go"], indent=2, default=str), encoding="utf-8"
    )
    (OUT / "02_cf_pr_summary.json").write_text(json.dumps(cf, indent=2, default=str), encoding="utf-8")
    (OUT / "03_day0_smoke.json").write_text(
        json.dumps(audit.get("day0_smoke", {}), indent=2, default=str), encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k5a.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    regressions = {
        "passed": proc.returncode == 0,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }
    (OUT / "04_regression_summary.json").write_text(json.dumps(regressions, indent=2), encoding="utf-8")

    summary = {
        "head": _head(),
        "phase": "3K.5A",
        "stop_boundary": "STOP_PRODUCTION_PREREQUISITES_CLOSED",
        "cf_pr_pass": cf["all_passed"],
        "go_no_go": audit["go_no_go"]["matrix"],
        "recommendation": audit["go_no_go"]["recommendation"],
        "any_fail": audit["go_no_go"]["any_fail"],
        "regressions_pass": regressions["passed"],
        "live_forward_activated": False,
        "genesis_exists": audit["go_no_go"]["genesis_exists"],
        "scheduler_activated": False,
        "phase_pass": (
            cf["all_passed"]
            and not audit["go_no_go"]["any_fail"]
            and regressions["passed"]
            and audit["go_no_go"]["recommendation"] == "READY_FOR_DEPLOYMENT_DAY_0"
        ),
    }
    (OUT / "05_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
