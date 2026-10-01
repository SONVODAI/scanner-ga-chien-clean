"""
Phase 3J.0 — BB-ProductionAutonomy-01 abstract integration benchmark.

Tests production wiring behaviors independent of the real T2 proposition naming.
Uses dev panels only — no hidden benchmark phenomena.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel, inject_dispersion_anomaly
from modules.edge_research.opr_bridge.production_authority import (
    OprLegacyPlannerBlockedError,
    assert_legacy_planner_blocked,
    mark_session_opr_authority,
)
from modules.edge_research.opr_bridge.production_orchestrator import (
    STOP_NO_AUTO_EXPERIMENT,
    STOP_PROPOSITION_PERSISTED,
    run_production_opr_cycle,
    simulate_process_restart,
)
from modules.edge_research.opr_bridge.production_trigger import (
    compute_opportunity_identity,
    detect_production_opportunity,
)
from modules.edge_research.research_graph import ResearchGraph

BENCHMARK_VERSION = "bb_production_autonomy_01_v1_3j0"


def _silent_panel(seed: int = 99) -> pd.DataFrame:
    """Panel with no dispersion anomaly — legitimate silence (flat monotonic quintiles)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    symbols = [f"S{i:03d}" for i in range(30)]
    rows = []
    for day in range(25):
        date = f"2026-01-{day + 1:02d}"
        for sym in symbols:
            rs = float(rng.normal(0, 2))
            rows.append(
                {
                    "trade_date": date,
                    "symbol": sym,
                    "rs_spread": rs,
                    "t5_return": rs * 0.01,
                    "t3_return": rs * 0.01,
                    "t10_return": rs * 0.01,
                }
            )
    return pd.DataFrame(rows)


def _anomaly_panel(seed: int = 42) -> pd.DataFrame:
    """Dev panel with injected cross-sectional anomaly (abstract case family: flux-tier-dispersion)."""
    base = build_extended_dev_panel(
        pd.DataFrame({"trade_date": [], "symbol": [], "rs_spread": [], "t5_return": []}),
        n_dates=30,
        symbols_per_date=40,
        seed=seed,
    )
    return inject_dispersion_anomaly(base, focal_date="2026-01-30", seed=seed + 7)


def all_bbpa_cases() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "BBPA-01-autonomous-session-start",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_outcome": "SESSION_CREATED",
            "expect_stop": STOP_PROPOSITION_PERSISTED,
        },
        {
            "case_id": "BBPA-02-legitimate-silence",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _silent_panel,
            "cutoff": "2026-02-15",
            "expect_outcome_in": ("SILENT", "NO_ELIGIBLE_OBSERVATION"),
        },
        {
            "case_id": "BBPA-03-deterministic-opportunity-identity",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_deterministic": True,
        },
        {
            "case_id": "BBPA-04-duplicate-suppression",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_second_outcome": "NO_NEW_RESEARCH_OPPORTUNITY",
        },
        {
            "case_id": "BBPA-05-persistence-restart",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_restart": True,
        },
        {
            "case_id": "BBPA-06-authority-conflict",
            "family": "integration_authority",
            "expect_legacy_blocked": True,
        },
        {
            "case_id": "BBPA-07-stop-boundary-enforcement",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_stop": STOP_NO_AUTO_EXPERIMENT,
        },
        {
            "case_id": "BBPA-08-failure-isolation",
            "family": "flux_tier_dispersion_abstract",
            "panel_fn": _anomaly_panel,
            "cutoff": "2026-02-15",
            "expect_frozen_integrity": True,
        },
    ]


def run_bbpa_case(case: Dict[str, Any], *, tmp_data_dir: Path) -> Dict[str, Any]:
    case_id = case["case_id"]
    result: Dict[str, Any] = {"case_id": case_id, "benchmark_version": BENCHMARK_VERSION}

    if case_id == "BBPA-06-authority-conflict":
        graph = ResearchGraph.create_session(
            data_cutoff_date="2026-02-15",
            guardrails_config_version="guardrails_v1",
        )
        mark_session_opr_authority(graph)
        try:
            assert_legacy_planner_blocked(graph)
            result["legacy_blocked"] = False
        except OprLegacyPlannerBlockedError:
            result["legacy_blocked"] = True
        return result

    panel_fn = case["panel_fn"]
    panel = panel_fn()
    cutoff = case["cutoff"]
    data_dir = tmp_data_dir / case_id
    data_dir.mkdir(parents=True, exist_ok=True)

    if case_id == "BBPA-03-deterministic-opportunity-identity":
        d1 = detect_production_opportunity(panel, data_cutoff_date=cutoff)
        d2 = detect_production_opportunity(panel, data_cutoff_date=cutoff)
        result["identity_stable"] = (
            d1.opportunity_identity == d2.opportunity_identity
            and d1.opportunity_identity is not None
        )
        return result

    cycle1 = run_production_opr_cycle(panel, data_cutoff_date=cutoff, data_dir=data_dir)
    result["outcome"] = cycle1.outcome
    result["session_id"] = cycle1.session_id
    result["stop_boundaries"] = cycle1.stop_boundaries
    result["frozen_integrity"] = cycle1.frozen_integrity

    if case.get("expect_second_outcome"):
        cycle2 = run_production_opr_cycle(panel, data_cutoff_date=cutoff, data_dir=data_dir)
        result["second_outcome"] = cycle2.outcome
        result["idempotent_skip"] = cycle2.idempotent_skip

    if case.get("expect_restart") and cycle1.session_id:
        restart = simulate_process_restart(cycle1.session_id, data_dir=data_dir)
        result["restart"] = restart

    return result


def evaluate_bbpa_case(case: Dict[str, Any], run: Dict[str, Any]) -> Dict[str, Any]:
    checks: Dict[str, bool] = {}
    case_id = case["case_id"]

    if case_id == "BBPA-01-autonomous-session-start":
        checks["session_created"] = run.get("outcome") == case["expect_outcome"]
        checks["stop_boundary"] = case["expect_stop"] in (run.get("stop_boundaries") or [])
    elif case_id == "BBPA-02-legitimate-silence":
        checks["silent"] = run.get("outcome") in case["expect_outcome_in"]
    elif case_id == "BBPA-03-deterministic-opportunity-identity":
        checks["deterministic"] = run.get("identity_stable") is True
    elif case_id == "BBPA-04-duplicate-suppression":
        checks["first_created"] = run.get("outcome") == "SESSION_CREATED"
        checks["second_suppressed"] = run.get("second_outcome") == case["expect_second_outcome"]
        checks["idempotent"] = run.get("idempotent_skip") is True
    elif case_id == "BBPA-05-persistence-restart":
        checks["created"] = run.get("outcome") == "SESSION_CREATED"
        restart = run.get("restart") or {}
        checks["reconstructed"] = restart.get("session_id") == run.get("session_id")
        checks["has_auth_state"] = bool(restart.get("authoritative_state"))
    elif case_id == "BBPA-06-authority-conflict":
        checks["legacy_blocked"] = run.get("legacy_blocked") is True
    elif case_id == "BBPA-07-stop-boundary-enforcement":
        checks["stop_present"] = case["expect_stop"] in (run.get("stop_boundaries") or [])
    elif case_id == "BBPA-08-failure-isolation":
        fi = run.get("frozen_integrity") or {}
        checks["frozen_integrity"] = fi.get("passed") is True

    passed = all(checks.values()) if checks else False
    return {"case_id": case_id, "passed": passed, "checks": checks}
