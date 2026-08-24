"""
CLI / callable entry for Forecast Data Contract daily freeze + maturity.

Streamlit-independent. Safe to run after EOD sources exist.
Does not train models or touch Edge Research authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.forecast_research.contract import CONTRACT_VERSION, EXPECTED_UNIVERSE_SIZE
from modules.forecast_research.feature_matrix import build_feature_availability_matrix, write_feature_matrix
from modules.forecast_research.outcome_maturity import list_board_trading_dates, mature_all_outcomes
from modules.forecast_research.t0_builder import DEFAULT_EMS, DEFAULT_MDT0, build_forecast_t0_record
from modules.forecast_research.t0_persistence import (
    load_t0_table,
    persist_t0_record,
    resolve_forecast_data_dir,
    write_status,
)


def freeze_trade_date(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
) -> Dict[str, Any]:
    trade_date = str(trade_date)[:10]
    prior = load_t0_table(data_dir)
    if not prior.empty and "trade_date" in prior.columns:
        hit = prior[prior["trade_date"].astype(str).str[:10] == trade_date]
        if not hit.empty:
            row = hit.iloc[-1]
            return {
                "ok": True,
                "trade_date": trade_date,
                "written": False,
                "reason": "ALREADY_FROZEN",
                "completeness_status": row.get("completeness_status"),
                "universe_count": row.get("universe_count"),
                "feature_hash": row.get("feature_hash"),
                "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
            }
    record, completeness = build_forecast_t0_record(
        trade_date,
        ems_path=ems_path,
        md_path=md_path,
        prior_t0_history=prior if not prior.empty else None,
    )
    if record is None:
        return {
            "ok": False,
            "trade_date": trade_date,
            "written": False,
            "reason": completeness,
        }
    written, reason = persist_t0_record(record, data_dir=data_dir)
    return {
        "ok": True,
        "trade_date": trade_date,
        "written": written,
        "reason": reason,
        "completeness_status": record.get("completeness_status"),
        "universe_count": record.get("universe_count"),
        "feature_hash": record.get("feature_hash"),
        "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
    }


def freeze_available_dates(
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
) -> Dict[str, Any]:
    dates = list_board_trading_dates(ems_path)
    results = [freeze_trade_date(d, data_dir=data_dir, ems_path=ems_path, md_path=md_path) for d in dates]
    return {
        "ok": True,
        "n_dates": len(dates),
        "written": sum(1 for r in results if r.get("written")),
        "results": results,
    }


def run_daily_pipeline(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    mature: bool = True,
    write_matrix: bool = True,
) -> Dict[str, Any]:
    root = resolve_forecast_data_dir(data_dir)
    freeze_result: Dict[str, Any]
    if trade_date:
        freeze_result = freeze_trade_date(trade_date, data_dir=root, ems_path=ems_path, md_path=md_path)
    else:
        freeze_result = freeze_available_dates(data_dir=root, ems_path=ems_path, md_path=md_path)

    mature_result = mature_all_outcomes(data_dir=root, ems_path=ems_path, md_path=md_path) if mature else {"skipped": True}
    matrix_path = None
    if write_matrix:
        matrix_path = str(write_feature_matrix(root / "feature_availability_matrix.json"))

    status = {
        "contract_version": CONTRACT_VERSION,
        "data_dir": str(root),
        "freeze": freeze_result,
        "maturity": mature_result,
        "feature_matrix_path": matrix_path,
    }
    write_status(status, data_dir=root)
    return status


def maybe_freeze_after_market_daily(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    mature: bool = True,
) -> Dict[str, Any]:
    """
    Fail-safe hook for market_t0_capture after canonical daily T0 write.
    Never raises into Market First / trading path.
    Idempotent: ALREADY_FROZEN still counts as ok; maturity is append-only.
    Also writes MDRR + refreshes historical core for the date (fail-safe).
    """
    try:
        freeze = freeze_trade_date(trade_date, data_dir=data_dir)
        maturity: Dict[str, Any] = {"skipped": True}
        if mature:
            maturity = mature_all_outcomes(data_dir=data_dir)
        mdrr: Dict[str, Any] = {"skipped": True}
        hist: Dict[str, Any] = {"skipped": True}
        try:
            from modules.forecast_research.mdrr import maybe_write_mdrr_after_market_daily

            mdrr = maybe_write_mdrr_after_market_daily(trade_date, data_dir=data_dir)
        except Exception as exc:  # noqa: BLE001
            mdrr = {"ok": False, "reason": f"mdrr_hook_error:{exc}"}
        try:
            from modules.forecast_research.historical_recovery import (
                build_historical_record_for_date,
                persist_historical_record,
            )

            rec = build_historical_record_for_date(trade_date)
            if rec is not None:
                ok, reason = persist_historical_record(rec, data_dir=data_dir)
                hist = {"ok": True, "written": ok, "reason": reason, "quality_tier": rec.get("quality_tier")}
            else:
                hist = {"ok": False, "written": False, "reason": "no_evidence"}
        except Exception as exc:  # noqa: BLE001
            hist = {"ok": False, "reason": f"hist_hook_error:{exc}"}
        return {
            "ok": bool(freeze.get("ok")),
            "written": bool(freeze.get("written")),
            "reason": freeze.get("reason"),
            "completeness_status": freeze.get("completeness_status"),
            "maturity": maturity,
            "mdrr": mdrr,
            "historical_core": hist,
        }
    except Exception as exc:  # noqa: BLE001 — observer must not break capture
        return {"ok": False, "written": False, "reason": f"hook_error:{exc}"}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Forecast Data Contract V1 daily freeze/maturity")
    parser.add_argument("--trade-date", default=None, help="YYYY-MM-DD; default=backfill all EMS dates")
    parser.add_argument("--data-dir", default=None, help="Override data/forecast_research")
    parser.add_argument("--no-mature", action="store_true")
    parser.add_argument("--matrix-only", action="store_true")
    parser.add_argument("--recover-historical", action="store_true", help="Run historical market core recovery")
    parser.add_argument("--mdrr-backfill", action="store_true", help="Backfill MDRR from EMS dates")
    parser.add_argument("--all-research-memory", action="store_true", help="T0 freeze + mature + MDRR + historical")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else None
    if args.matrix_only:
        path = write_feature_matrix(
            (data_dir or resolve_forecast_data_dir()) / "feature_availability_matrix.json"
        )
        print(json.dumps({"matrix": str(path), **build_feature_availability_matrix()}, indent=2, default=str)[:2000])
        return 0

    payload: Dict[str, Any] = {}

    if args.recover_historical and not args.all_research_memory:
        from modules.forecast_research.historical_recovery import recover_all_historical

        payload = recover_all_historical(data_dir=data_dir)
        print(json.dumps(payload, indent=2, default=str)[:12000])
        return 0 if payload.get("ok") else 1

    if args.mdrr_backfill and not args.all_research_memory:
        from modules.forecast_research.mdrr import run_mdrr_backfill, write_forward_only_registry

        payload = run_mdrr_backfill(data_dir=data_dir)
        write_forward_only_registry(data_dir)
        print(json.dumps(payload, indent=2, default=str)[:12000])
        return 0

    result = run_daily_pipeline(
        trade_date=args.trade_date,
        data_dir=data_dir,
        mature=not args.no_mature,
    )
    if args.all_research_memory:
        from modules.forecast_research.historical_recovery import recover_all_historical
        from modules.forecast_research.mdrr import run_mdrr_backfill, write_forward_only_registry

        result["historical"] = recover_all_historical(data_dir=data_dir)
        result["mdrr"] = run_mdrr_backfill(data_dir=data_dir)
        write_forward_only_registry(data_dir)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("freeze", {}).get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
