"""
Phase 3K.2 / 3K.5A — CLI entrypoint for scheduled daily runs + labeled recovery.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_policy import resolve_target_trade_date
from modules.production_eod.headless_eod import (
    RUN_CLASS_AUTONOMOUS,
    RUN_CLASS_RECOVERY,
)


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

    headless_eod: dict = {"skipped": True, "reason": "not_attempted"}
    if not args.skip_headless_eod:
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

    panel = build_research_panel(repo_root=repo_root)
    panel_freshness = diagnose_panel_freshness(panel, trade_date, headless_eod=headless_eod)
    data_dir = Path(args.data_dir) if args.data_dir else None
    result = run_production_daily_research(
        panel,
        target_trade_date=trade_date,
        run_mode=args.mode,
        data_dir=data_dir,
        use_run_lock=args.use_lock,
        repo_root=repo_root,
    )
    result["headless_eod"] = headless_eod
    result["panel_freshness"] = panel_freshness
    result["run_provenance"] = {
        "recovery": bool(args.recovery),
        "run_mode": args.mode,
        "autonomy_evidence": headless_eod.get("autonomy_evidence"),
        "headless_run_identity": headless_eod.get("run_identity"),
    }

    disposition = result.get("run", {}).get("run_disposition", "FAILED_CLOSED")
    if result.get("lock_held"):
        print(json.dumps(result.get("lock") or result.get("run"), indent=2, default=str))
        return 10
    exit_map = {
        RunDisposition.SUCCESS.value: 0,
        RunDisposition.SKIPPED_NON_TRADING_DAY.value: 3,
        RunDisposition.WAITING_FOR_DATA.value: 2,
        RunDisposition.PARTIAL_RECOVERABLE.value: 4,
        RunDisposition.FAILED_CLOSED.value: 1,
    }
    # Prefer rich observability payload
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
                "panel_freshness": result.get("panel_freshness"),
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
