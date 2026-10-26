"""
Phase 3K.3 — Historical calibration mechanics simulation (NON_FORWARD only).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_calibration_engine import build_calibration_snapshot
from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import (
    list_ledger_entries,
    list_snapshots,
    persist_calibration_snapshot,
)
from modules.edge_research.opr_bridge.production_calibration_updater import update_calibration_ledger
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    HISTORICAL_REPLAY_TEST,
    LIVE_FORWARD,
)
from modules.edge_research.opr_bridge.production_calibration_records import STOP_FORWARD_EVIDENCE_CALIBRATION_READY
from modules.edge_research.opr_bridge.production_forward_evidence_eligibility import reject_backfill_as_forward_evidence
from modules.edge_research.opr_bridge.production_trading_session_eligibility import extract_panel_trading_sessions


def run_calibration_mechanics_simulation(
    panel: pd.DataFrame,
    *,
    num_sessions: int = 12,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Sequential simulation verifying calibration mechanics — all evidence NON_FORWARD.
    """
    sessions = extract_panel_trading_sessions(panel)
    if not sessions:
        return {"error": "no_sessions", "counts_as_forward_evidence": False}

    replay_dates = sessions[:num_sessions]
    backfill_rejected = []
    daily_runs = []

    for d in replay_dates:
        result = run_production_daily_research(
            panel,
            target_trade_date=d,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=repo_root,
        )
        daily_runs.append({"date": d, "disposition": result.get("run", {}).get("run_disposition")})
        cal = update_calibration_ledger(
            panel=panel,
            as_of_trade_date=d,
            run_id=result.get("run", {}).get("run_id", ""),
            run_mode=BACKFILL_NON_FORWARD,
            run_counts_as_forward_evidence=False,
            newly_released_outcome_ids=tuple(result.get("run", {}).get("forward_outcomes_released") or []),
            observation_ids=list(result.get("run", {}).get("observations_reassessed") or [])
            + list(result.get("run", {}).get("observations_born") or []),
            data_dir=data_dir,
        )
        rejected, reason = reject_backfill_as_forward_evidence(BACKFILL_NON_FORWARD)
        backfill_rejected.append({"date": d, "rejected": not rejected, "reason": reason, "cal_updated": cal.get("updated")})

    forward_entries = list_ledger_entries(data_dir=data_dir, forward_only=True)
    all_snapshots = list_snapshots(data_dir=data_dir)

    # Idempotent rebuild check
    first_count = len(forward_entries)
    for d in replay_dates[-2:]:
        result = run_production_daily_research(
            panel, target_trade_date=d, run_mode=BACKFILL_NON_FORWARD, data_dir=data_dir, repo_root=repo_root
        )
        update_calibration_ledger(
            panel=panel,
            as_of_trade_date=d,
            run_id=result.get("run", {}).get("run_id", ""),
            run_mode=BACKFILL_NON_FORWARD,
            run_counts_as_forward_evidence=False,
            data_dir=data_dir,
        )
    second_count = len(list_ledger_entries(data_dir=data_dir, forward_only=True))

    return {
        "test_kind": "CALIBRATION_MECHANICS_SIMULATION",
        "replay_dates": replay_dates,
        "num_sessions": len(replay_dates),
        "daily_runs": daily_runs,
        "backfill_rejection_checks": backfill_rejected,
        "forward_ledger_entry_count": len(forward_entries),
        "all_backfill_rejected_from_forward_ledger": all(r.get("rejected") for r in backfill_rejected),
        "snapshot_count": len(all_snapshots),
        "idempotent_rebuild": first_count == second_count,
        "counts_as_forward_evidence": False,
        "stop_boundary": STOP_FORWARD_EVIDENCE_CALIBRATION_READY,
    }


def run_live_forward_mechanics_fixture(
    panel: pd.DataFrame,
    *,
    target_trade_date: str,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create LIVE_FORWARD run in isolated temp dir for ledger mechanics verification."""
    result = run_production_daily_research(
        panel,
        target_trade_date=target_trade_date,
        run_mode=LIVE_FORWARD,
        data_dir=data_dir,
        repo_root=repo_root,
    )
    cal = update_calibration_ledger(
        panel=panel,
        as_of_trade_date=target_trade_date,
        run_id=result.get("run", {}).get("run_id", ""),
        run_mode=LIVE_FORWARD,
        run_counts_as_forward_evidence=True,
        newly_released_outcome_ids=tuple(result.get("run", {}).get("forward_outcomes_released") or []),
        observation_ids=list(result.get("run", {}).get("observations_reassessed") or [])
        + list(result.get("run", {}).get("observations_born") or []),
        data_dir=data_dir,
    )
    return {"run": result, "calibration": cal, "counts_as_forward_evidence": True}
