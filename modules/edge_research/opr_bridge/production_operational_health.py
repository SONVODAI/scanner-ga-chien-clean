"""
Phase 3K.5 — Operational health / readiness artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import list_ledger_entries, list_snapshots
from modules.edge_research.opr_bridge.production_daily_run_persistence import load_run_index, lookup_run_for_date
from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists, load_genesis
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import build_living_research_ui_read_model
from modules.edge_research.opr_bridge.production_run_lock import acquire_run_lock, is_lock_stale, lock_path, read_lock_metadata, release_run_lock

OPERATIONAL_HEALTH_VERSION = "operational_health_v1_3k5"


def build_operational_health_artifact(*, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Compact artifact answering operational health questions."""
    index = load_run_index(data_dir)
    runs = list(index.get("runs", {}).values())
    successful = [r for r in runs if r.get("run_disposition") == "SUCCESS"]
    latest_success = max(successful, key=lambda r: r.get("target_trade_date", "")) if successful else None
    waiting = [r for r in runs if r.get("run_disposition") == "WAITING_FOR_DATA"]
    failed = [r for r in runs if r.get("run_disposition") in ("FAILED_CLOSED", "PARTIAL_RECOVERABLE")]

    live_runs = [r for r in runs if r.get("run_mode") == LIVE_FORWARD]
    genesis = load_genesis(data_dir)
    ui = build_living_research_ui_read_model(data_dir=data_dir)

    lock_meta = read_lock_metadata(lock_path(data_dir))
    lock_active = bool(lock_meta) and not is_lock_stale(lock_meta)

    latest_run = lookup_run_for_date(
        latest_success["target_trade_date"], latest_success.get("run_mode", ""), data_dir=data_dir
    ) if latest_success else None

    return {
        "version": OPERATIONAL_HEALTH_VERSION,
        "runner_started_today": latest_success is not None,
        "latest_successful_research_date": latest_success.get("target_trade_date") if latest_success else None,
        "latest_run_id": latest_success.get("run_id") if latest_success else None,
        "latest_run_mode": latest_success.get("run_mode") if latest_success else None,
        "data_ready_last_run": latest_success is not None,
        "research_completed": latest_success is not None,
        "birth_records_persisted": bool(latest_run and latest_run.observations_born) if latest_run else False,
        "observations_reassessed": bool(latest_run and latest_run.observations_reassessed) if latest_run else False,
        "outcomes_released": bool(latest_run and latest_run.forward_outcomes_released) if latest_run else False,
        "calibration_ledger_entries": len(list_ledger_entries(data_dir=data_dir, forward_only=True)),
        "calibration_snapshots": len(list_snapshots(data_dir=data_dir)),
        "summary_completed": bool(latest_run and latest_run.daily_summary_id) if latest_run else False,
        "manifest_available": latest_success is not None,
        "ui_reading_latest": ui.get("trade_date") == (latest_success or {}).get("target_trade_date"),
        "system_stale": ui.get("trade_date") != (latest_success or {}).get("target_trade_date") if latest_success else True,
        "waiting_for_data_runs": len(waiting),
        "failed_runs": len(failed),
        "live_forward_runs": len(live_runs),
        "genesis_exists": genesis_exists(data_dir),
        "genesis_first_eligible": genesis.first_eligible_trade_date if genesis else None,
        "lock_active": lock_active,
        "lock_holder": lock_meta.get("run_id") if lock_active else None,
        "fail_closed_events": len(failed) + len(waiting),
        "shadow_authority": {"research_only": True, "trading_authority": False, "edge_active": False},
    }
