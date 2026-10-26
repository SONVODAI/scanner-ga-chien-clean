#!/usr/bin/env python3
"""Phase 3K.1 — Living research observation & daily assessment diagnostics."""

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


def _hidden_answer_audit() -> dict:
    root = REPO / "modules/edge_research/opr_bridge"
    modules = [
        "production_living_research_observation.py",
        "production_daily_assessment.py",
        "production_daily_voice.py",
        "production_forward_outcome_evaluator.py",
        "production_living_observation_records.py",
    ]
    forbidden = ["blind-a", "blind-b", "ground_truth", "seed_to_blind_class", "true_direction"]
    hits = []
    for name in modules:
        path = root / name
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in blob:
                hits.append({"module": name, "token": tok})
    return {"passed": not hits, "hits": hits}


def main() -> int:
    from modules.edge_research.adapters import build_research_panel
    from modules.edge_research.opr_bridge.bb_living_research_observation_01_fixtures import (
        run_cf_live_counterfactuals,
    )
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        compute_research_policy_hashes,
    )
    from modules.edge_research.opr_bridge.production_living_read_model import build_full_read_model
    from modules.edge_research.opr_bridge.production_living_research_observation import (
        run_historical_multi_day_replay,
    )
    from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit

    policy_hashes = {"frozen_at_head": _git_head(), "policy_hashes": compute_research_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy_hashes)

    cf = run_cf_live_counterfactuals(REPO)
    _write("01_cf_live_summary.json", cf)

    panel = build_research_panel()
    import tempfile

    replay = {"error": "empty_panel"}
    read_model = {"error": "empty_panel"}
    if not panel.empty:
        dates = sorted(panel["trade_date"].astype(str).unique())
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            replay = run_historical_multi_day_replay(
                panel,
                start_trade_date=dates[0],
                num_trading_days=min(10, len(dates)),
                data_dir=data_dir,
                repo_root=REPO,
            )
            read_model = build_full_read_model(
                trade_date=dates[0],
                observation_ids=[replay.get("observation_id")],
                data_dir=data_dir,
            )
    _write("02_historical_multi_day_replay.json", replay)
    _write("03_read_model_contract.json", read_model)

    trading_iso = run_trading_isolation_audit(REPO)
    _write("04_trading_isolation_audit.json", trading_iso)

    hidden = _hidden_answer_audit()
    _write("05_hidden_answer_audit.json", hidden)

    regressions = _run_regressions()
    _write("06_regression_summary.json", regressions)

    summary = {
        "head": _git_head(),
        "phase": "3K.1",
        "stop_boundary": "STOP_LIVING_RESEARCH_OBSERVATION_READY",
        "cf_live_pass": cf.get("all_passed"),
        "historical_replay_days": replay.get("num_days"),
        "counts_as_forward_evidence": replay.get("counts_as_forward_evidence"),
        "demonstrations": replay.get("demonstrations"),
        "trading_isolation_pass": trading_iso.get("passed"),
        "hidden_answer_audit_pass": hidden.get("passed"),
        "regressions_pass": regressions.get("all_passed"),
        "phase_pass": (
            cf.get("all_passed")
            and replay.get("counts_as_forward_evidence") is False
            and (replay.get("num_days") or 0) >= 10
            and trading_iso.get("passed")
            and hidden.get("passed")
            and regressions.get("all_passed")
        ),
    }
    _write("07_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["phase_pass"] else 1


def _run_regressions() -> dict:
    suites = [
        "tests/test_edge_research_opr_phase_3k1.py",
        "tests/test_edge_research_opr_phase_3k0.py",
        "tests/test_edge_research_opr_phase_3j14a.py",
        "tests/test_edge_research_opr_phase_3j14.py::test_cf_cg_counterfactuals",
        "tests/test_edge_research_opr_phase_3j13.py::test_cf_fg_counterfactuals",
        "tests/test_edge_research_opr_phase_3j12.py::test_cf_nx_counterfactuals",
        "tests/test_edge_research_opr_phase_3j11.py::test_cf_br_counterfactuals",
        "tests/test_edge_research_opr_phase_3j10.py::test_cf_arl1_arl12_pass",
    ]
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
