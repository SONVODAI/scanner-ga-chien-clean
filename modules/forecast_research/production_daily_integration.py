"""
Production daily orchestration hook for Forecast Memory.

Streamlit-independent fail-safe stage gated on canonical market_daily_t0 (MDT0).
Does not alter Edge OPR disposition or Market First authority.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modules.forecast_research.contract import COMPLETENESS_WAITING, CONTRACT_VERSION
from modules.forecast_research.daily_entrypoint import freeze_trade_date
from modules.forecast_research.outcome_maturity import mature_all_outcomes
from modules.forecast_research.t0_builder import DEFAULT_EMS, DEFAULT_MDT0, load_market_daily
from modules.forecast_research.t0_persistence import resolve_forecast_data_dir, write_status

logger = logging.getLogger(__name__)

STAGE_SUCCESS = "SUCCESS"
STAGE_WAITING = "WAITING_FOR_DATA"
STAGE_FAILED = "FAILED"


def assess_mdt0_readiness(
    trade_date: str,
    *,
    md_path: Path = DEFAULT_MDT0,
) -> Tuple[bool, str]:
    """
    Require canonical market_daily_t0 row for trade_date before unattended freeze.
    Prevents irreversible EMS-only PARTIAL Forecast T0 when MDT0 is absent.
    """
    trade_date = str(trade_date)[:10]
    md = load_market_daily(md_path, trade_date)
    if md is None:
        return False, "canonical_mdt0_missing"
    return True, "mdt0_present"


def _waiting_stage(trade_date: str, gate_reason: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "trade_date": trade_date,
        "stage": "forecast_memory",
        "stage_disposition": STAGE_WAITING,
        "reason": gate_reason,
        "mdt0_gate": {"ready": False, "reason": gate_reason},
        "forecast_t0": {
            "ok": False,
            "written": False,
            "reason": COMPLETENESS_WAITING,
            "skipped": True,
        },
        "maturity": {"skipped": True, "reason": "mdt0_gate"},
        "mdrr": {"skipped": True, "reason": "mdt0_gate"},
        "historical_core": {"skipped": True, "reason": "mdt0_gate"},
        "p0_market_memory": {"skipped": True, "reason": "mdt0_gate"},
        "ff_confirmation_forward": {"skipped": True, "reason": "mdt0_gate"},
    }


def run_forecast_memory_daily_stage(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    require_mdt0: bool = True,
    mature: bool = True,
    write_pipeline_status: bool = True,
) -> Dict[str, Any]:
    """
    Isolated Forecast Memory stage for production daily orchestration.

    Never raises — failures are captured in stage_disposition / reason.
    """
    trade_date = str(trade_date)[:10]
    root = resolve_forecast_data_dir(data_dir)

    try:
        if require_mdt0:
            ready, gate_reason = assess_mdt0_readiness(trade_date, md_path=md_path)
            if not ready:
                return _waiting_stage(trade_date, gate_reason)

        gate = {"ready": True, "reason": "mdt0_present"} if require_mdt0 else {"ready": True, "reason": "gate_disabled"}

        freeze = freeze_trade_date(trade_date, data_dir=root, ems_path=ems_path, md_path=md_path)

        maturity: Dict[str, Any] = {"skipped": True}
        if mature:
            try:
                maturity = mature_all_outcomes(data_dir=root, ems_path=ems_path, md_path=md_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Forecast outcome maturity failed safely: %s", exc)
                maturity = {"ok": False, "reason": f"maturity_error:{exc}"}

        mdrr: Dict[str, Any] = {"skipped": True}
        try:
            from modules.forecast_research.mdrr import maybe_write_mdrr_after_market_daily

            mdrr = maybe_write_mdrr_after_market_daily(trade_date, data_dir=root)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MDRR hook failed safely: %s", exc)
            mdrr = {"ok": False, "reason": f"mdrr_hook_error:{exc}"}

        hist: Dict[str, Any] = {"skipped": True}
        try:
            from modules.forecast_research.historical_recovery import (
                build_historical_record_for_date,
                persist_historical_record,
            )

            rec = build_historical_record_for_date(trade_date, ems=ems_path, mdt0=md_path)
            if rec is not None:
                ok, reason = persist_historical_record(rec, data_dir=root)
                hist = {
                    "ok": True,
                    "written": ok,
                    "reason": reason,
                    "quality_tier": rec.get("quality_tier"),
                }
            else:
                hist = {"ok": False, "written": False, "reason": "no_evidence"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Historical core hook failed safely: %s", exc)
            hist = {"ok": False, "reason": f"hist_hook_error:{exc}"}

        p0: Dict[str, Any] = {"skipped": True}
        t_p0 = None
        try:
            from modules.forecast_research.p0_daily import maybe_collect_p0_after_market_daily
            from modules.production_stage_telemetry import emit_stage_end, emit_stage_start, io_fields

            t_p0 = emit_stage_start("p0_universe_foreign", trade_date=trade_date)
            p0 = maybe_collect_p0_after_market_daily(trade_date, data_dir=root)
        except Exception as exc:  # noqa: BLE001
            logger.warning("P0 hook failed safely: %s", exc)
            p0 = {"ok": False, "written": False, "reason": f"p0_hook_error:{exc}"}
        if t_p0 is not None:
            from modules.production_stage_telemetry import emit_stage_end, io_fields

            emit_stage_end(
                "p0_universe_foreign",
                started_monotonic=t_p0,
                disposition=str(p0.get("reason") or ("OK" if p0.get("ok") else "FAILED")),
                **io_fields(p0.get("io_summary")),
            )

        # Isolated Foreign Flow confirmation forward-panel ingest (fail-safe).
        # OPTIONAL enrichment — must not block A→C→B. Bounded I/O.
        ff_conf: Dict[str, Any] = {"skipped": True}
        t_ff = None
        try:
            from modules.foreign_flow_confirmation.daily import (
                maybe_run_ff_confirmation_after_market_daily,
            )
            from modules.production_stage_telemetry import emit_stage_end, emit_stage_start, io_fields

            t_ff = emit_stage_start("ff_confirmation_forward", trade_date=trade_date)
            ff_conf = maybe_run_ff_confirmation_after_market_daily(trade_date)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FF confirmation forward hook failed safely: %s", exc)
            ff_conf = {
                "ok": False,
                "written": False,
                "reason": f"ff_confirmation_hook_error:{exc}",
            }
        if t_ff is not None:
            from modules.production_stage_telemetry import emit_stage_end, io_fields

            ingest = ff_conf.get("ingest") if isinstance(ff_conf, dict) else None
            emit_stage_end(
                "ff_confirmation_forward",
                started_monotonic=t_ff,
                disposition=str(ff_conf.get("reason") or ("OK" if ff_conf.get("ok") else "FAILED")),
                **io_fields(ingest if isinstance(ingest, dict) else ff_conf.get("io_summary")),
            )

        stage_disposition = STAGE_SUCCESS
        if not freeze.get("ok") and freeze.get("reason") == COMPLETENESS_WAITING:
            stage_disposition = STAGE_WAITING

        payload: Dict[str, Any] = {
            "ok": bool(freeze.get("ok")) or freeze.get("reason") == "ALREADY_FROZEN",
            "trade_date": trade_date,
            "stage": "forecast_memory",
            "stage_disposition": stage_disposition,
            "reason": freeze.get("reason"),
            "contract_version": CONTRACT_VERSION,
            "data_dir": str(root),
            "mdt0_gate": gate,
            "forecast_t0": freeze,
            "maturity": maturity,
            "mdrr": mdrr,
            "historical_core": hist,
            "p0_market_memory": p0,
            "ff_confirmation_forward": ff_conf,
            "written": bool(freeze.get("written")),
            "completeness_status": freeze.get("completeness_status"),
        }

        if write_pipeline_status:
            write_status(
                {
                    "contract_version": CONTRACT_VERSION,
                    "data_dir": str(root),
                    "source": "production_daily_integration",
                    "stage": payload,
                },
                data_dir=root,
            )

        return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("Forecast Memory daily stage failed safely: %s", exc)
        return {
            "ok": False,
            "trade_date": trade_date,
            "stage": "forecast_memory",
            "stage_disposition": STAGE_FAILED,
            "reason": f"stage_error:{exc}",
            "mdt0_gate": {"ready": False, "reason": f"stage_error:{exc}"},
        }


def attach_forecast_memory_to_daily_run_result(
    result: Dict[str, Any],
    *,
    target_trade_date: str,
    repo_root: Path,
    edge_data_dir: Optional[Path] = None,
    reuse_forecast_memory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append Forecast Memory stage to a production daily run result dict.

    Skipped when another run holds the exclusive lock (avoid racing Edge phases).
    """
    if result.get("lock_held"):
        out = dict(result)
        out["forecast_memory"] = {
            "skipped": True,
            "reason": "edge_run_lock_held",
            "stage": "forecast_memory",
        }
        return out

    if reuse_forecast_memory:
        out = dict(result)
        reused = dict(reuse_forecast_memory)
        reused["reused_from_headless_eod"] = True
        out["forecast_memory"] = reused
        run_id = (result.get("run") or {}).get("run_id")
        if run_id and edge_data_dir is not None:
            try:
                from modules.edge_research.opr_bridge.production_daily_run_persistence import persist_phase_marker
                from modules.edge_research.opr_bridge.production_daily_run_records import RunPhase

                persist_phase_marker(
                    run_id,
                    RunPhase.FORECAST_MEMORY_COMPLETED.value,
                    data_dir=edge_data_dir,
                    extra={
                        "stage_disposition": reused.get("stage_disposition"),
                        "forecast_t0_reason": (reused.get("forecast_t0") or {}).get("reason"),
                        "reused_from_headless_eod": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Forecast Memory phase marker failed safely: %s", exc)
        return out

    forecast_dir = repo_root / "data" / "forecast_research"
    md_path = repo_root / "data" / "earning_learning" / "market_daily_t0.csv"
    ems_path = repo_root / "data" / "earning_money_snapshots.csv"
    stage = run_forecast_memory_daily_stage(
        target_trade_date,
        data_dir=forecast_dir,
        ems_path=ems_path,
        md_path=md_path,
        require_mdt0=True,
    )

    out = dict(result)
    out["forecast_memory"] = stage

    run_id = (result.get("run") or {}).get("run_id")
    if run_id and edge_data_dir is not None:
        try:
            from modules.edge_research.opr_bridge.production_daily_run_persistence import persist_phase_marker
            from modules.edge_research.opr_bridge.production_daily_run_records import RunPhase

            persist_phase_marker(
                run_id,
                RunPhase.FORECAST_MEMORY_COMPLETED.value,
                data_dir=edge_data_dir,
                extra={
                    "stage_disposition": stage.get("stage_disposition"),
                    "forecast_t0_reason": (stage.get("forecast_t0") or {}).get("reason"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Forecast Memory phase marker failed safely: %s", exc)

    return out
