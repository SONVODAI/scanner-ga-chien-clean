#!/usr/bin/env python3
"""Phase 3K.0 — Production research observation foundation diagnostics."""

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
        "production_research_observation.py",
        "production_observation_records.py",
        "production_observation_cutoff.py",
        "production_observation_persistence.py",
        "production_observation_narrative.py",
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
    from modules.edge_research.opr_bridge.bb_production_research_observation_01_fixtures import (
        run_cf_obs_counterfactuals,
    )
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        compute_research_policy_hashes,
    )
    from modules.edge_research.opr_bridge.production_observation_isolation import (
        run_trading_isolation_audit,
    )
    from modules.edge_research.opr_bridge.production_observation_narrative import (
        build_narrative_contract,
        build_ui_contract,
        render_minimal_narrative_preview,
    )
    from modules.edge_research.opr_bridge.production_research_observation import (
        run_historical_replay_test,
    )

    policy_hashes = {"frozen_at_head": _git_head(), "policy_hashes": compute_research_policy_hashes(REPO)}
    _write("00_frozen_policy_hashes.json", policy_hashes)

    cf = run_cf_obs_counterfactuals(REPO)
    _write("01_cf_obs_summary.json", cf)

    panel = build_research_panel()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        replay = run_historical_replay_test(
            panel,
            data_cutoff_date="2026-08-01",
            data_dir=Path(tmp),
            repo_root=REPO,
        )
    _write("02_historical_replay_test.json", replay)

    if replay.get("birth_record"):
        from modules.edge_research.opr_bridge.production_observation_persistence import (
            _birth_from_dict,
        )

        birth = _birth_from_dict(replay["birth_record"])
        narrative = build_narrative_contract(birth)
        ui = build_ui_contract(birth)
        preview = render_minimal_narrative_preview(narrative)
        _write(
            "03_narrative_and_ui_contracts.json",
            {
                "narrative_contract": narrative.to_dict(),
                "ui_contract": ui.to_dict(),
                "presentation_preview": preview,
            },
        )

    trading_iso = run_trading_isolation_audit(REPO)
    _write("04_trading_isolation_audit.json", trading_iso)

    hidden = _hidden_answer_audit()
    _write("05_hidden_answer_audit.json", hidden)

    regressions = _run_regressions()
    _write("06_regression_summary.json", regressions)

    summary = {
        "head": _git_head(),
        "phase": "3K.0",
        "stop_boundary": "STOP_PRODUCTION_RESEARCH_OBSERVATION_FOUNDATION",
        "cf_obs_pass": cf.get("all_passed"),
        "historical_replay_temporal_integrity": replay.get("temporal_provenance_established"),
        "counts_as_forward_evidence": replay.get("counts_as_forward_evidence"),
        "observation_id": replay.get("observation_id"),
        "trading_isolation_pass": trading_iso.get("passed"),
        "hidden_answer_audit_pass": hidden.get("passed"),
        "regressions_pass": regressions.get("all_passed"),
        "phase_pass": (
            cf.get("all_passed")
            and replay.get("temporal_provenance_established")
            and replay.get("counts_as_forward_evidence") is False
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
