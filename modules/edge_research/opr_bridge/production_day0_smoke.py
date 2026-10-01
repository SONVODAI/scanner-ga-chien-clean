"""
Phase 3K.5 — DAY_0_SMOKE mode (production plumbing verification, never forward evidence).
Phase 3K.5A — hardened calendar / timezone / EOD / backup-readiness path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import list_ledger_entries
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research
from modules.edge_research.opr_bridge.production_daily_run_records import DAY_0_SMOKE
from modules.edge_research.opr_bridge.production_data_readiness_gate import verify_data_readiness
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import build_living_research_ui_read_model
from modules.edge_research.opr_bridge.production_observation_cutoff import truncate_panel_at_cutoff
from modules.edge_research.opr_bridge.production_observation_persistence import load_observation_index
from modules.edge_research.adapters import EARNING_LEARNING_DIR
from modules.edge_research.opr_bridge.production_backup import load_latest_backup_metadata
from modules.edge_research.opr_bridge.production_operational_health import build_operational_health_artifact
from modules.edge_research.opr_bridge.production_timezone_policy import derive_vn_trade_date
from modules.edge_research.opr_bridge.production_run_lock import acquire_run_lock, release_run_lock
from modules.edge_research.storage import resolve_data_dir

DAY0_SMOKE_SUBDIR = "day0_smoke_namespace"
DAY0_SMOKE_VERSION = "day0_smoke_v2_3k5a"


def day0_smoke_data_dir(base_data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(base_data_dir) / "production_observations" / DAY0_SMOKE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_day0_smoke(
    panel: pd.DataFrame,
    *,
    target_trade_date: str,
    repo_root: Optional[Path] = None,
    base_data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Verify production plumbing in isolated namespace.
    Never counts as LIVE_FORWARD. Never contaminates calibration ledger.
    """
    isolated = day0_smoke_data_dir(base_data_dir)
    readiness = verify_data_readiness(
        panel,
        target_trade_date,
        require_authoritative_eod=True,
        require_calendar=True,
        eod_data_root=EARNING_LEARNING_DIR,
    )
    truncated, cutoff_diag = truncate_panel_at_cutoff(panel, target_trade_date) if not panel.empty else (panel, {})

    lock_fh = None
    lock_result = None
    run_result: Dict[str, Any] = {"skipped": True, "reason": "readiness_failed"}
    if readiness.ready:
        lock_fh, lock_result = acquire_run_lock(run_id=f"day0-smoke-{target_trade_date}", data_dir=isolated)
        if lock_result.acquired:
            try:
                run_result = run_production_daily_research(
                    panel,
                    target_trade_date=target_trade_date,
                    run_mode=DAY_0_SMOKE,
                    data_dir=isolated,
                    repo_root=repo_root,
                    use_run_lock=False,
                )
            finally:
                if lock_fh:
                    release_run_lock(lock_fh, data_dir=isolated)

    main_ledger = list_ledger_entries(data_dir=base_data_dir, forward_only=True)
    smoke_ledger = list_ledger_entries(data_dir=isolated, forward_only=True)
    ui_model = build_living_research_ui_read_model(trade_date=target_trade_date, data_dir=isolated)
    health = build_operational_health_artifact(data_dir=isolated, panel=panel, target_trade_date=target_trade_date)
    backup_meta = load_latest_backup_metadata(data_dir=isolated)

    return {
        "test_kind": "DAY_0_SMOKE",
        "version": DAY0_SMOKE_VERSION,
        "target_trade_date": target_trade_date,
        "vn_trading_session_date": derive_vn_trade_date(),
        "isolated_namespace": str(isolated),
        "readiness": readiness.to_dict(),
        "operational_health": health,
        "backup_readiness": backup_meta,
        "cutoff_diag": cutoff_diag,
        "lock": lock_result.to_dict() if lock_result else None,
        "run": run_result,
        "counts_as_forward_evidence": False,
        "main_calibration_contaminated": len(smoke_ledger) > 0 and any(
            e.run_mode == DAY_0_SMOKE for e in main_ledger
        ),
        "smoke_observation_count": len(load_observation_index(isolated).get("observations", {})),
        "ui_available": ui_model.get("trade_date") is not None or ui_model.get("failure_state") is not None,
        "promotable": False,
    }
