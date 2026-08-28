"""
Closed-loop Edge Research (A → C → B) owned by the existing daily pipeline.

Not a second scheduler. Never mutates canonical T0, Forecast, or OPR
dispositions. Failures surface as UNABLE/FAILED on this nested payload only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.contracts import ASSESSMENT_UNABLE_TO_ASSESS

SKIP_NON_TRADING_DAY = "SKIPPED_NON_TRADING_DAY"
SKIP_T0_NOT_READY = "SKIPPED_T0_NOT_READY"
SKIP_GENESIS_BLOCKED = "SKIPPED_GENESIS_BLOCKED"
SKIP_LOCK_HELD = "SKIPPED_LOCK_HELD"
SKIP_WAITING_FOR_DATA = "SKIPPED_WAITING_FOR_DATA"


def freeze_contains_session(trade_date: str, *, repo_root: Optional[Path] = None) -> bool:
    if not trade_date:
        return False
    try:
        from modules.edge_research.adapters import load_t0_observation_freeze

        freeze = load_t0_observation_freeze(repo_root=repo_root)
    except Exception:
        return False
    if freeze is None or freeze.empty or "trade_date" not in freeze.columns:
        return False
    target = str(trade_date)[:10]
    return bool((freeze["trade_date"].astype(str).str[:10] == target).any())


def _skipped(reason: str, trade_date: str) -> Dict[str, Any]:
    return {
        "trade_date": trade_date,
        "ran_science": False,
        "system_status": "SKIPPED",
        "skip_reason": reason,
        "assessment_state": "",
        "assessment_reason": "",
        "order": ["qualification", "continuous_learning", "recognition", "shadow"],
        "errors": [],
    }


def run_closed_loop_edge_after_daily(
    *,
    target_trade_date: str,
    daily_result: Dict[str, Any],
    repo_root: Path,
    data_dir: Optional[Path] = None,
    panel: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run Phase A → C → B only after canonical T0 for target_trade_date is present.

    Never raises. Never changes daily_result['run']['run_disposition'].
    """
    td = str(target_trade_date or "")[:10]
    try:
        if daily_result.get("genesis_blocked"):
            return _skipped(SKIP_GENESIS_BLOCKED, td)
        if daily_result.get("lock_held"):
            return _skipped(SKIP_LOCK_HELD, td)
        run = daily_result.get("run") or {}
        disp = str(run.get("run_disposition") or "")
        if disp == "SKIPPED_NON_TRADING_DAY":
            return _skipped(SKIP_NON_TRADING_DAY, td)
        if disp == "WAITING_FOR_DATA":
            return _skipped(SKIP_WAITING_FOR_DATA, td)
        if not freeze_contains_session(td, repo_root=repo_root):
            return _skipped(SKIP_T0_NOT_READY, td)

        freeze_df = None
        try:
            from modules.edge_research.adapters import load_t0_observation_freeze

            freeze_df = load_t0_observation_freeze(repo_root=repo_root)
        except Exception:
            freeze_df = None

        from modules.edge_research.eod_cycle import run_edge_research_eod_cycle
        from modules.production_stage_telemetry import emit_stage_end, emit_stage_start

        t_abc = emit_stage_start("closed_loop_abc", trade_date=td)
        result = run_edge_research_eod_cycle(
            trade_date=td,
            data_dir=data_dir,
            freeze_df=freeze_df,
            panel=panel,
        )
        result["ran_science"] = True
        result["skip_reason"] = ""
        rec = result.get("recognition") or {}
        if not result.get("assessment_state"):
            result["assessment_state"] = rec.get("assessment_state") or ""
        if not result.get("assessment_reason"):
            result["assessment_reason"] = rec.get("reason") or ""
        emit_stage_end(
            "closed_loop_abc",
            started_monotonic=t_abc,
            disposition=str(result.get("assessment_state") or result.get("system_status") or "UNKNOWN"),
            reason=result.get("assessment_reason"),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        return {
            "trade_date": td,
            "ran_science": False,
            "system_status": "FAILED",
            "skip_reason": "",
            "assessment_state": ASSESSMENT_UNABLE_TO_ASSESS,
            "assessment_reason": "MATCHER_EXCEPTION",
            "failure_detail": f"{type(exc).__name__}: {exc}",
            "errors": [str(exc)],
            "order": ["qualification", "continuous_learning", "recognition", "shadow"],
        }
