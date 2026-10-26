#!/usr/bin/env python3
"""Phase 3K.4 — Living Research UI diagnostics."""

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
    from modules.edge_research.opr_bridge.bb_living_research_ui_01_fixtures import (
        generate_ui_preview_snapshots,
        run_ui_read_model_fixtures,
    )
    from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
    from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit

    policy = {"frozen_at_head": _git_head(), "policy_hashes": compute_research_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy)

    fx = run_ui_read_model_fixtures(REPO)
    _write("01_ui_fixture_summary.json", fx)

    preview = generate_ui_preview_snapshots(REPO)
    _write("02_ui_preview_normal_day.txt", preview["previews"].get("normal_speaking_day", ""))
    _write("03_ui_preview_no_discovery.txt", preview["previews"].get("no_discovery_day", ""))
    _write("04_ui_preview_metadata.json", {
        k: v for k, v in preview["previews"].items()
        if k not in ("normal_speaking_day", "no_discovery_day")
    })

    trading_iso = run_trading_isolation_audit(REPO)
    _write("05_trading_isolation_audit.json", trading_iso)

    insight_recommendation = {
        "existing_panel": "render_bot_learning_insight() in app.py",
        "recommendation": "RETAIN_AS_LEGACY",
        "rationale": (
            "BOT Learning Insight summarizes aggregate T3/T5/T10 lifecycle learning from data/earning_learning/. "
            "Living Research UI surfaces daily production research voice from 3K.0–3K.3 persisted records. "
            "Different questions, different authority. Legacy panel now labeled explicitly; no contradictory opinions "
            "without authority explanation."
        ),
        "action_taken": "Added legacy caption to BOT Learning Insight pointing users to Living Research UI",
    }
    _write("06_insight_panel_recommendation.json", insight_recommendation)

    full_regressions = _run_regressions([
        "tests/test_edge_research_opr_phase_3k4.py",
        "tests/test_edge_research_opr_phase_3k3.py::test_cf_cal_counterfactuals",
        "tests/test_edge_research_opr_phase_3k2.py::test_cf_run_counterfactuals",
        "tests/test_edge_research_opr_phase_3k1.py::test_cf_live_counterfactuals",
        "tests/test_edge_research_opr_phase_3k0.py",
        "tests/test_edge_research_opr_phase_3j14a.py",
        "tests/test_edge_research_opr_phase_3j10.py::test_cf_arl1_arl12_pass",
    ])
    _write("07_regression_summary.json", full_regressions)

    summary = {
        "head": _git_head(),
        "phase": "3K.4",
        "stop_boundary": "STOP_LIVING_RESEARCH_UI_READY",
        "ui_fixtures_pass": fx.get("all_passed"),
        "preview_generated": bool(preview.get("previews", {}).get("normal_speaking_day")),
        "preview_not_live_forward": preview["previews"].get("counts_as_forward_evidence") is False,
        "trading_isolation_pass": trading_iso.get("passed"),
        "insight_recommendation": insight_recommendation["recommendation"],
        "regressions_pass": full_regressions.get("all_passed"),
        "phase_pass": (
            fx.get("all_passed")
            and preview.get("fixtures_pass")
            and trading_iso.get("passed")
            and full_regressions.get("all_passed")
        ),
    }
    _write("08_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
