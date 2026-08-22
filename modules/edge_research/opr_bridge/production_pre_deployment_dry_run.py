"""
Phase 3K.5 — Pre-deployment dry run (NON_FORWARD, never promotable).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.production_calibration_updater import update_calibration_ledger
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research
from modules.edge_research.opr_bridge.production_daily_run_records import PRE_DEPLOYMENT_DRY_RUN
from modules.edge_research.opr_bridge.production_living_research_ui import render_living_research_ui_text_snapshot
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import build_living_research_ui_read_model
from modules.edge_research.opr_bridge.production_operational_health import build_operational_health_artifact

DRY_RUN_VERSION = "pre_deployment_dry_run_v1_3k5"
DRY_RUN_SUBDIR = "pre_deployment_dry_run"


def dry_run_data_dir(base_data_dir: Optional[Path] = None) -> Path:
    from modules.edge_research.storage import resolve_data_dir
    root = resolve_data_dir(base_data_dir) / "production_observations" / DRY_RUN_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_pre_deployment_dry_run(
    panel: pd.DataFrame,
    *,
    target_trade_date: str,
    repo_root: Optional[Path] = None,
    base_data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    End-to-end path in isolated NON_FORWARD namespace.
    Labels all products PRE_DEPLOYMENT_DRY_RUN — never promotable.
    """
    isolated = dry_run_data_dir(base_data_dir)
    result = run_production_daily_research(
        panel,
        target_trade_date=target_trade_date,
        run_mode=PRE_DEPLOYMENT_DRY_RUN,
        data_dir=isolated,
        repo_root=repo_root,
        use_run_lock=True,
    )
    cal = update_calibration_ledger(
        panel=panel,
        as_of_trade_date=target_trade_date,
        run_id=result.get("run", {}).get("run_id", ""),
        run_mode=PRE_DEPLOYMENT_DRY_RUN,
        run_counts_as_forward_evidence=False,
        newly_released_outcome_ids=tuple(result.get("run", {}).get("forward_outcomes_released") or []),
        observation_ids=list(result.get("run", {}).get("observations_reassessed") or [])
        + list(result.get("run", {}).get("observations_born") or []),
        data_dir=isolated,
    )
    ui_model = build_living_research_ui_read_model(trade_date=target_trade_date, data_dir=isolated)
    ui_snapshot = render_living_research_ui_text_snapshot(ui_model, data_dir=isolated)
    health = build_operational_health_artifact(data_dir=isolated)

    return {
        "test_kind": "PRE_DEPLOYMENT_DRY_RUN",
        "version": DRY_RUN_VERSION,
        "label": "NON_FORWARD / PRE_DEPLOYMENT_DRY_RUN — NEVER PROMOTABLE",
        "target_trade_date": target_trade_date,
        "isolated_namespace": str(isolated),
        "run_disposition": result.get("run", {}).get("run_disposition"),
        "counts_as_forward_evidence": False,
        "calibration_updated": cal.get("updated"),
        "calibration_reason": cal.get("reason"),
        "ui_trade_date": ui_model.get("trade_date"),
        "ui_snapshot_preview": ui_snapshot[:1500],
        "health": health,
        "pipeline_stages": {
            "data_ready": result.get("run", {}).get("run_disposition") not in ("WAITING_FOR_DATA", "FAILED_CLOSED"),
            "research": result.get("run") is not None,
            "manifest": result.get("manifest") is not None,
            "calibration": cal.get("updated") is False,  # correctly rejected for non-forward
        },
    }
