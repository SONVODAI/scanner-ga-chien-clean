"""
Phase 3K.2 / 3K.5A — CLI entrypoint for scheduled daily runs + labeled recovery.

Authoritative production command:
  python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint
      --derive-vn-date --mode LIVE_FORWARD --use-lock

--use-lock is acquired BEFORE headless EOD and every other data-producing stage.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_panel_freshness import diagnose_panel_freshness
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    DAY_0_SMOKE,
    LIVE_FORWARD,
    PRE_DEPLOYMENT_DRY_RUN,
    RECOVERY_MANUAL_REMEDIATION,
    RunDisposition,
)
from modules.edge_research.opr_bridge.production_run_lock import acquire_run_lock, release_run_lock
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_policy import resolve_target_trade_date
from modules.production_eod.headless_eod import (
    RUN_CLASS_AUTONOMOUS,
    RUN_CLASS_RECOVERY,
)
from modules.production_stage_telemetry import emit_stage_end, emit_stage_start

LOCK_HELD_EXIT = 10

# Process-global lock/receipt context for SIGTERM / atexit (systemd TimeoutStop).
_LOCK_CTX: Dict[str, Any] = {
    "fh": None,
    "data_dir": None,
    "repo_root": None,
    "trade_date": None,
    "headless_eod": None,
    "edge_result": None,
    "panel_freshness": None,
    "run_provenance": None,
    "released": False,
}


def _release_entrypoint_lock() -> None:
    if _LOCK_CTX.get("released"):
        return
    fh = _LOCK_CTX.get("fh")
    _LOCK_CTX["fh"] = None
    _LOCK_CTX["released"] = True
    if fh is None:
        return
    try:
        release_run_lock(fh, data_dir=_LOCK_CTX.get("data_dir"))
    except Exception:
        pass


def _write_terminated_receipt(reason: str, stage: str) -> None:
    td = _LOCK_CTX.get("trade_date")
    if not td:
        return
    try:
        from modules.production_daily_receipt import write_incomplete_pipeline_receipt

        write_incomplete_pipeline_receipt(
            td,
            repo_root=_LOCK_CTX.get("repo_root"),
            edge_data_dir=_LOCK_CTX.get("data_dir"),
            headless_eod=_LOCK_CTX.get("headless_eod"),
            edge_result=_LOCK_CTX.get("edge_result"),
            panel_freshness=_LOCK_CTX.get("panel_freshness"),
            run_provenance=_LOCK_CTX.get("run_provenance"),
            termination_reason=reason,
            stage=stage,
        )
    except Exception:
        pass


def _install_termination_handlers() -> None:
    def _handler(signum: int, _frame: Any) -> None:
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            sig_name = str(signum)
        print(
            f"[STAGE_END] stage=pipeline disposition=PIPELINE_TERMINATED signal={sig_name}",
            flush=True,
        )
        _write_terminated_receipt(
            reason=f"PIPELINE_TERMINATED_BEFORE_COMPLETE:{sig_name}",
            stage="pipeline_wall_clock",
        )
        _release_entrypoint_lock()
        raise SystemExit(1)

    try:
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
    except (ValueError, OSError):
        pass
    atexit.register(_release_entrypoint_lock)


def _lock_held_payload(lock_result: Any, trade_date: str) -> Dict[str, Any]:
    payload = lock_result.to_dict() if hasattr(lock_result, "to_dict") else dict(lock_result)
    payload.update(
        {
            "run_disposition": "LOCK_HELD",
            "failure_or_skip_reason": payload.get("reason") or "lock_held",
            "target_trade_date": trade_date,
            "data_producing_work": False,
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production daily research run (3K.2/3K.5A)")
    parser.add_argument(
        "--trade-date",
        default=None,
        help="Target VN trading session date YYYY-MM-DD (default: derive from VN calendar)",
    )
    parser.add_argument(
        "--derive-vn-date",
        action="store_true",
        help="Explicitly derive target from Asia/Ho_Chi_Minh (default when --trade-date omitted)",
    )
    parser.add_argument(
        "--mode",
        default=BACKFILL_NON_FORWARD,
        choices=[
            BACKFILL_NON_FORWARD,
            LIVE_FORWARD,
            "HISTORICAL_REPLAY_TEST",
            DAY_0_SMOKE,
            PRE_DEPLOYMENT_DRY_RUN,
            RECOVERY_MANUAL_REMEDIATION,
        ],
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--use-lock", action="store_true", help="Acquire exclusive run lock")
    parser.add_argument("--scheduling-contract", action="store_true")
    parser.add_argument(
        "--skip-headless-eod",
        action="store_true",
        help="Skip headless EOD board/EMS/MDT0/EL stage (tests / emergency)",
    )
    parser.add_argument(
        "--recovery",
        action="store_true",
        help=(
            "Label this execution as RECOVERY_MANUAL_REMEDIATION (not autonomous evidence). "
            "Preserves prior autonomous headless_eod_status.json FAIL evidence."
        ),
    )
    args = parser.parse_args(argv)

    if args.scheduling_contract:
        print(json.dumps(build_scheduling_contract(), indent=2))
        return 0

    if args.recovery and args.mode == BACKFILL_NON_FORWARD:
        args.mode = RECOVERY_MANUAL_REMEDIATION
    if args.mode == RECOVERY_MANUAL_REMEDIATION:
        args.recovery = True

    trade_date = resolve_target_trade_date(args.trade_date)
    repo_root = Path(__file__).resolve().parents[3]
    data_dir: Optional[Path] = Path(args.data_dir) if args.data_dir else None
    _LOCK_CTX.update(
        {
            "data_dir": data_dir,
            "repo_root": repo_root,
            "trade_date": trade_date,
            "released": False,
            "fh": None,
        }
    )

    pipeline_t0 = emit_stage_start("daily_pipeline", trade_date=trade_date, mode=args.mode)

    # Exclusive lock BEFORE any data-producing stage (including headless 142-scan).
    if args.use_lock:
        run_id = f"entrypoint-{trade_date}-{os.getpid()}"
        lock_fh, lock_result = acquire_run_lock(run_id=run_id, data_dir=data_dir)
        if not lock_result.acquired:
            emit_stage_end(
                "daily_pipeline",
                started_monotonic=pipeline_t0,
                disposition="LOCK_HELD",
                reason=lock_result.reason,
                holder_pid=lock_result.holder_pid,
            )
            print(json.dumps(_lock_held_payload(lock_result, trade_date), indent=2, default=str))
            return LOCK_HELD_EXIT
        _LOCK_CTX["fh"] = lock_fh
        _LOCK_CTX["released"] = False
        _install_termination_handlers()

    try:
        return _run_pipeline(
            args=args,
            trade_date=trade_date,
            repo_root=repo_root,
            data_dir=data_dir,
            pipeline_started=pipeline_t0,
        )
    finally:
        _release_entrypoint_lock()


def _run_pipeline(
    *,
    args: argparse.Namespace,
    trade_date: str,
    repo_root: Path,
    data_dir: Optional[Path],
    pipeline_started: float,
) -> int:
    headless_eod: dict = {"skipped": True, "reason": "not_attempted"}
    if not args.skip_headless_eod:
        t_he = emit_stage_start("headless_eod", trade_date=trade_date)
        try:
            from modules.production_eod.headless_eod import run_headless_eod

            headless_eod = run_headless_eod(
                trade_date,
                repo_root=repo_root,
                run_class=RUN_CLASS_RECOVERY if args.recovery else RUN_CLASS_AUTONOMOUS,
                preserve_autonomy_status=bool(args.recovery),
            )
        except Exception as exc:  # noqa: BLE001
            headless_eod = {
                "ok": False,
                "skipped": False,
                "reason": f"headless_eod_error:{type(exc).__name__}:{exc}",
                "stage_disposition": "FAILED",
                "run_class": RUN_CLASS_RECOVERY if args.recovery else RUN_CLASS_AUTONOMOUS,
                "autonomy_evidence": (
                    "RECOVERY_NOT_AUTONOMOUS_EVIDENCE"
                    if args.recovery
                    else "AUTONOMOUS_PRODUCTION"
                ),
            }
        emit_stage_end(
            "headless_eod",
            started_monotonic=t_he,
            disposition=str(headless_eod.get("stage_disposition") or "UNKNOWN"),
            reason=headless_eod.get("reason"),
            source_rows=headless_eod.get("source_rows"),
        )
    _LOCK_CTX["headless_eod"] = headless_eod

    t_panel = emit_stage_start("research_panel", trade_date=trade_date)
    panel = build_research_panel(repo_root=repo_root)
    panel_freshness = diagnose_panel_freshness(panel, trade_date, headless_eod=headless_eod)
    emit_stage_end(
        "research_panel",
        started_monotonic=t_panel,
        disposition="READY" if panel_freshness.get("target_in_panel_sessions") else "WAITING",
    )
    _LOCK_CTX["panel_freshness"] = panel_freshness

    reuse_forecast = None
    fm_from_headless = headless_eod.get("forecast_memory")
    if isinstance(fm_from_headless, dict) and fm_from_headless and not fm_from_headless.get("skipped"):
        reuse_forecast = fm_from_headless

    t_opr = emit_stage_start("opr_living_research", trade_date=trade_date)
    # Lock already held at entrypoint; do not re-acquire (would self-block).
    result = run_production_daily_research(
        panel,
        target_trade_date=trade_date,
        run_mode=args.mode,
        data_dir=data_dir,
        use_run_lock=False,
        repo_root=repo_root,
        reuse_forecast_memory=reuse_forecast,
    )
    result["headless_eod"] = headless_eod
    result["panel_freshness"] = panel_freshness
    result["run_provenance"] = {
        "recovery": bool(args.recovery),
        "run_mode": args.mode,
        "autonomy_evidence": headless_eod.get("autonomy_evidence"),
        "headless_run_identity": headless_eod.get("run_identity"),
    }
    _LOCK_CTX["edge_result"] = result
    _LOCK_CTX["run_provenance"] = result["run_provenance"]
    emit_stage_end(
        "opr_living_research",
        started_monotonic=t_opr,
        disposition=str((result.get("run") or {}).get("run_disposition") or "UNKNOWN"),
        forecast_reused=bool(reuse_forecast),
        closed_loop=(result.get("closed_loop_edge") or {}).get("assessment_state")
        or (result.get("closed_loop_edge") or {}).get("skip_reason"),
    )

    # Observability-only daily receipt — never changes research outcomes.
    receipt_info: dict = {"ok": False, "skipped": True}
    t_receipt = emit_stage_start("daily_receipt", trade_date=trade_date)
    try:
        from modules.production_daily_receipt import write_receipt_from_run

        receipt_info = write_receipt_from_run(
            trade_date,
            repo_root=repo_root,
            edge_data_dir=data_dir,
            headless_eod=headless_eod,
            edge_result=result,
            panel_freshness=panel_freshness,
            run_provenance=result.get("run_provenance"),
        )
        result["daily_pipeline_receipt"] = receipt_info
    except Exception as exc:  # noqa: BLE001
        receipt_info = {"ok": False, "error": f"receipt_hook:{type(exc).__name__}:{exc}"}
        result["daily_pipeline_receipt"] = receipt_info
    emit_stage_end(
        "daily_receipt",
        started_monotonic=t_receipt,
        disposition="OK" if receipt_info.get("ok") else "FAILED",
        closed_loop_complete=(receipt_info.get("receipt") or {}).get("closed_loop_complete"),
        overall=(receipt_info.get("receipt") or {}).get("overall"),
    )

    # Fail-safe Streamlit Cloud sync of production_observations (observability only).
    t_sync = emit_stage_start("production_observations_sync")
    try:
        from modules.edge_research.production_observations_sync import (
            publish_production_observations_durable,
        )

        result["production_observations_sync"] = publish_production_observations_durable(
            data_dir=data_dir
        )
    except Exception as sync_exc:  # noqa: BLE001
        result["production_observations_sync"] = {
            "ok": False,
            "error": f"sync_hook:{type(sync_exc).__name__}:{sync_exc}",
        }
    emit_stage_end(
        "production_observations_sync",
        started_monotonic=t_sync,
        disposition="OK" if (result.get("production_observations_sync") or {}).get("ok") else "FAILED",
    )

    disposition = result.get("run", {}).get("run_disposition", "FAILED_CLOSED")
    if result.get("lock_held"):
        emit_stage_end("daily_pipeline", started_monotonic=pipeline_started, disposition="LOCK_HELD")
        print(json.dumps(result.get("lock") or result.get("run"), indent=2, default=str))
        return LOCK_HELD_EXIT
    exit_map = {
        RunDisposition.SUCCESS.value: 0,
        RunDisposition.SKIPPED_NON_TRADING_DAY.value: 3,
        RunDisposition.WAITING_FOR_DATA.value: 2,
        RunDisposition.PARTIAL_RECOVERABLE.value: 4,
        RunDisposition.FAILED_CLOSED.value: 1,
    }
    emit_stage_end(
        "daily_pipeline",
        started_monotonic=pipeline_started,
        disposition=str(disposition),
        closed_loop_complete=(receipt_info.get("receipt") or {}).get("closed_loop_complete"),
    )
    print(
        json.dumps(
            {
                "run": result.get("manifest") or result.get("run"),
                "run_provenance": result.get("run_provenance"),
                "headless_eod": {
                    "stage_disposition": headless_eod.get("stage_disposition"),
                    "reason": headless_eod.get("reason"),
                    "source_rows": headless_eod.get("source_rows"),
                    "run_class": headless_eod.get("run_class"),
                    "run_identity": headless_eod.get("run_identity"),
                    "autonomy_evidence": headless_eod.get("autonomy_evidence"),
                    "trading_day_probe_status": headless_eod.get("trading_day_probe_status"),
                    "artifacts": {
                        k: (v if not isinstance(v, dict) else {ik: v.get(ik) for ik in list(v)[:8]})
                        for k, v in (headless_eod.get("artifacts") or {}).items()
                    },
                },
                "forecast_memory": (result.get("forecast_memory") or {}).get("stage_disposition"),
                "forecast_memory_reused_from_headless": bool(reuse_forecast),
                "closed_loop_edge": {
                    "ran_science": (result.get("closed_loop_edge") or {}).get("ran_science"),
                    "system_status": (result.get("closed_loop_edge") or {}).get("system_status"),
                    "assessment_state": (result.get("closed_loop_edge") or {}).get("assessment_state"),
                    "assessment_reason": (result.get("closed_loop_edge") or {}).get("assessment_reason"),
                    "skip_reason": (result.get("closed_loop_edge") or {}).get("skip_reason"),
                },
                "panel_freshness": result.get("panel_freshness"),
                "daily_pipeline_receipt": {
                    "ok": receipt_info.get("ok"),
                    "path": receipt_info.get("path"),
                    "overall": (receipt_info.get("receipt") or {}).get("overall"),
                    "first_failed_stage": (receipt_info.get("receipt") or {}).get("first_failed_stage"),
                    "reason": (receipt_info.get("receipt") or {}).get("reason"),
                    "closed_loop_complete": (receipt_info.get("receipt") or {}).get("closed_loop_complete"),
                    "closed_loop_status": (receipt_info.get("receipt") or {}).get("closed_loop_status"),
                    "pipeline_complete": (receipt_info.get("receipt") or {}).get("pipeline_complete"),
                },
            },
            indent=2,
            default=str,
        )
    )
    # Probe failures should exit non-zero even if Edge disposition is WAITING.
    if headless_eod.get("stage_disposition") == "TRADING_DAY_PROBE_FAILED":
        return 1
    return exit_map.get(disposition, 1)


if __name__ == "__main__":
    raise SystemExit(main())
