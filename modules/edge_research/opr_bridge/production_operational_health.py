"""
Phase 3K.5A — Operational health / readiness artifact (hardened prerequisites).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.adapters import EARNING_LEARNING_DIR
from modules.edge_research.opr_bridge.production_backup import load_latest_backup_metadata
from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import list_ledger_entries, list_snapshots
from modules.edge_research.opr_bridge.production_daily_run_persistence import load_run_index, lookup_run_for_date
from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_eod_completeness import verify_eod_completeness
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists, load_genesis
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import build_living_research_ui_read_model
from modules.edge_research.opr_bridge.production_run_lock import is_lock_stale, lock_path, read_lock_metadata
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_policy import derive_vn_trade_date
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    calendar_identity,
    evaluate_calendar_session_eligibility,
)

OPERATIONAL_HEALTH_VERSION = "operational_health_v2_3k5a"


def _scheduler_artifact_status() -> Dict[str, Any]:
    contract = build_scheduling_contract()
    return {
        "artifacts_prepared": contract.get("systemd_artifacts_prepared", False),
        "timer_installed": contract.get("systemd_timer_installed", False),
        "activated": contract.get("activated", False),
        "service_unit": contract.get("systemd_service_unit"),
        "timer_unit": contract.get("systemd_timer_unit"),
    }


def build_operational_health_artifact(
    *,
    data_dir: Optional[Path] = None,
    panel=None,
    target_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Compact artifact answering operational health questions — no false healthy state."""
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

    vn_target = target_trade_date or derive_vn_trade_date()
    cal = evaluate_calendar_session_eligibility(vn_target)
    eod = None
    if panel is not None:
        eod = verify_eod_completeness(panel, vn_target, data_root=EARNING_LEARNING_DIR)

    backup_meta = load_latest_backup_metadata(data_dir=data_dir)
    scheduler = _scheduler_artifact_status()

    latest_run = lookup_run_for_date(
        latest_success["target_trade_date"], latest_success.get("run_mode", ""), data_dir=data_dir
    ) if latest_success else None

    prerequisites_ok = (
        cal.eligible
        and (eod.complete if eod else False)
        and not lock_active
        and scheduler.get("activated") is False
    )

    return {
        "version": OPERATIONAL_HEALTH_VERSION,
        "healthy": prerequisites_ok and genesis is not None if live_runs else prerequisites_ok,
        "vn_trading_session_date": vn_target,
        "calendar_eligibility": cal.to_dict(),
        "calendar_identity": calendar_identity().to_dict(),
        "eod_completeness": eod.to_dict() if eod else None,
        "source_data_root": str(EARNING_LEARNING_DIR),
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
        "ui_freshness_trade_date": ui.get("trade_date"),
        "system_stale": ui.get("trade_date") != (latest_success or {}).get("target_trade_date") if latest_success else True,
        "waiting_for_data_runs": len(waiting),
        "failed_runs": len(failed),
        "live_forward_runs": len(live_runs),
        "live_forward_authority_active": len(live_runs) > 0 and genesis_exists(data_dir),
        "genesis_exists": genesis_exists(data_dir),
        "genesis_first_eligible": genesis.first_eligible_trade_date if genesis else None,
        "lock_active": lock_active,
        "lock_holder": lock_meta.get("run_id") if lock_active else None,
        "scheduler": scheduler,
        "latest_backup": backup_meta,
        "backup_integrity_ok": (backup_meta or {}).get("integrity_ok"),
        "fail_closed_events": len(failed) + len(waiting),
        "shadow_authority": {"research_only": True, "trading_authority": False, "edge_active": False},
    }
