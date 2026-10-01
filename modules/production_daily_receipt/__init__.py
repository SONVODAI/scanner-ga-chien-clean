"""
Daily production pipeline receipt — observability only.

Canonical path: data/production_daily_receipts/YYYY-MM-DD.json

Fail-safe: never raises into the research pipeline. Never changes research
decisions, thresholds, or frozen evidence. Anti-peeking: Foreign Flow fields
are counts/status only (no performance metrics).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root

logger = logging.getLogger(__name__)

RECEIPT_VERSION = "production_daily_receipt_v1"
RECEIPTS_DIRNAME = "production_daily_receipts"

OVERALL_PASS = "PASS"
OVERALL_FAIL = "FAIL"
OVERALL_WAITING = "WAITING"
OVERALL_SKIPPED = "SKIPPED"


def receipts_root(repo_root: Optional[Path] = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    return root / "data" / RECEIPTS_DIRNAME


def receipt_path(trade_date: str, *, repo_root: Optional[Path] = None) -> Path:
    return receipts_root(repo_root) / f"{str(trade_date)[:10]}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_date_rows(
    path: Path,
    trade_date: str,
    *,
    date_col_candidates: tuple[str, ...] = ("trade_date", "snapshot_date", "date"),
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "exists": path.exists(),
        "status": "MISSING",
        "rows": 0,
        "unique_symbols": None,
        "path": str(path),
    }
    if not path.exists():
        return out
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:  # noqa: BLE001
        out["status"] = f"READ_ERROR:{type(exc).__name__}"
        return out
    col = next((c for c in date_col_candidates if c in df.columns), None)
    if col is None:
        out["status"] = "NO_DATE_COL"
        out["rows"] = int(len(df))
        return out
    s = df[col].astype(str).str[:10]
    mask = s == str(trade_date)[:10]
    n = int(mask.sum())
    out["rows"] = n
    if "symbol" in df.columns:
        out["unique_symbols"] = int(df.loc[mask, "symbol"].nunique())
    out["status"] = "PRESENT" if n > 0 else "ABSENT_FOR_DATE"
    return out


def _session_voice_info(trade_date: str, *, edge_data_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        from modules.edge_research.opr_bridge.production_living_observation_persistence import (
            session_voice_path,
        )

        path = session_voice_path(str(trade_date)[:10], edge_data_dir)
        exists = path.exists()
        voice_id = None
        if exists:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                voice_id = payload.get("observation_id") or payload.get("assessment_id")
            except Exception:  # noqa: BLE001
                voice_id = "UNREADABLE"
        return {
            "exists": exists,
            "artifact_path": str(path),
            "artifact_id": voice_id,
            "status": "PRESENT" if exists else "ABSENT",
        }
    except Exception as exc:  # noqa: BLE001
        return {"exists": False, "status": f"ERROR:{type(exc).__name__}", "reason": str(exc)}


def build_daily_pipeline_receipt(
    trade_date: str,
    *,
    repo_root: Optional[Path] = None,
    edge_data_dir: Optional[Path] = None,
    headless_eod: Optional[Dict[str, Any]] = None,
    edge_result: Optional[Dict[str, Any]] = None,
    panel_freshness: Optional[Dict[str, Any]] = None,
    run_provenance: Optional[Dict[str, Any]] = None,
    scheduler_identity: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a factual receipt from runtime artifacts + orchestrator outputs.

    Never invents success. Never peeks Foreign Flow performance fields.
    """
    td = str(trade_date)[:10]
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    headless = headless_eod or {}
    edge = edge_result or {}
    run = edge.get("run") or {}
    manifest = edge.get("manifest") or {}
    freshness = panel_freshness or {}
    provenance = run_provenance or {}
    fm = edge.get("forecast_memory") or headless.get("artifacts", {}).get("forecast_memory") or {}

    el = root / "data" / "earning_learning"
    ems = _count_date_rows(root / "data" / "earning_money_snapshots.csv", td, date_col_candidates=("snapshot_date", "trade_date"))
    mdt0 = _count_date_rows(el / "market_daily_t0.csv", td)
    obs = _count_date_rows(el / "observations.csv", td)
    freeze = _count_date_rows(el / "t0_observation_freeze.csv", td)

    he_arts = headless.get("artifacts") or {}
    el_art = he_arts.get("earning_learning") or {}

    stock_t0 = {
        "observations_rows": obs.get("rows"),
        "observations_symbols": obs.get("unique_symbols"),
        "observations_status": obs.get("status"),
        "freeze_rows": freeze.get("rows"),
        "freeze_symbols": freeze.get("unique_symbols"),
        "freeze_status": freeze.get("status"),
        "headless_observations_added": el_art.get("observations_added"),
        "headless_t0_freeze_added": el_art.get("t0_freeze_added"),
    }

    panel_contains = bool(freshness.get("target_in_panel_sessions"))
    if freshness.get("target_in_panel_sessions") is None:
        # Fallback: derive from stock T0 presence (panel source).
        panel_contains = bool(
            (obs.get("rows") or 0) > 0 or (freeze.get("rows") or 0) > 0
        )

    voice = _session_voice_info(td, edge_data_dir=edge_data_dir)
    canon = resolve_production_runs_root(edge_data_dir)
    edge_disp = run.get("run_disposition") or "UNKNOWN"
    edge_reason = run.get("failure_or_skip_reason")

    ff_status: Dict[str, Any] = {"status": "UNKNOWN"}
    try:
        ff_payload = fm.get("ff_confirmation_forward") if isinstance(fm, dict) else None
        if ff_payload is None and isinstance(he_arts.get("forecast_memory"), dict):
            ff_payload = (he_arts.get("forecast_memory") or {}).get("ff_confirmation_forward")
        if isinstance(ff_payload, dict):
            # Counts-only / anti-peeking: keep disposition keys only.
            ff_status = {
                "status": ff_payload.get("stage") or ff_payload.get("reason") or (
                    "OK" if ff_payload.get("ok") else "SKIPPED_OR_FAIL"
                ),
                "ok": bool(ff_payload.get("ok")) if "ok" in ff_payload else None,
                "written": ff_payload.get("written"),
                "skipped": ff_payload.get("skipped"),
                "reason": ff_payload.get("reason"),
                "anti_peeking": True,
            }
        else:
            ff_status = {"status": "NOT_IN_RESULT", "anti_peeking": True}
    except Exception as exc:  # noqa: BLE001
        ff_status = {"status": f"ERROR:{type(exc).__name__}", "anti_peeking": True}

    fm_status = {
        "status": (
            fm.get("stage_disposition")
            or fm.get("reason")
            or ("PRESENT" if isinstance(fm, dict) and fm else "UNKNOWN")
        ),
        "ok": fm.get("ok") if isinstance(fm, dict) else None,
        "reason": fm.get("reason") if isinstance(fm, dict) else None,
    }

    he_status = headless.get("stage_disposition") or headless.get("reason") or "UNKNOWN"
    recovery = bool(provenance.get("recovery"))
    autonomous = (not recovery) and (
        headless.get("autonomy_evidence") in (None, "AUTONOMOUS_PRODUCTION")
        or headless.get("run_class") == "AUTONOMOUS"
        or provenance.get("autonomy_evidence") == "AUTONOMOUS_PRODUCTION"
    )

    overall, first_failed, reason = _classify_overall(
        he_status=str(he_status),
        he_reason=str(headless.get("reason") or ""),
        edge_disp=str(edge_disp),
        edge_reason=str(edge_reason or ""),
        panel_contains=panel_contains,
        stock_t0=stock_t0,
        voice_exists=bool(voice.get("exists")),
        ems_rows=int(ems.get("rows") or 0),
        mdt0_rows=int(mdt0.get("rows") or 0),
    )

    ui_latest = None
    try:
        from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
            build_living_research_ui_read_model,
        )

        rm = build_living_research_ui_read_model(trade_date=td, data_dir=edge_data_dir)
        ui_latest = rm.get("trade_date") or (rm.get("health") or {}).get("latest_successful_research_date")
    except Exception:  # noqa: BLE001
        ui_latest = None

    return {
        "receipt_version": RECEIPT_VERSION,
        "trade_date": td,
        "generated_at": _utc_now(),
        "scheduler_run_identity": scheduler_identity or headless.get("run_identity"),
        "headless_eod": {
            "status": he_status,
            "source_provider": "vnstock_legacy_scanner_core",
            "rows": headless.get("source_rows"),
            "symbols": headless.get("source_rows"),
            "universe_ok": headless.get("universe_ok"),
            "artifact_timestamp": headless.get("completed_at") or headless.get("started_at"),
            "trading_day_probe_status": headless.get("trading_day_probe_status"),
            "reason": headless.get("reason"),
            "run_class": headless.get("run_class"),
        },
        "ems": ems,
        "market_daily_t0": mdt0,
        "forecast_memory": fm_status,
        "foreign_flow_confirmation": ff_status,
        "stock_t0": stock_t0,
        "edge_panel": {
            "contains_trade_date": panel_contains,
            "panel_max_trade_date": freshness.get("panel_max_trade_date"),
            "likely_cause": freshness.get("likely_cause"),
        },
        "edge_research": {
            "disposition": edge_disp,
            "run_id": run.get("run_id") or manifest.get("run_id"),
            "failure_or_skip_reason": edge_reason,
            "discovery_count": manifest.get("discovery_count"),
            "bot_spoke_today": manifest.get("bot_spoke_today"),
            "silence_or_no_discovery": manifest.get("silence_or_no_discovery"),
            "idempotent_replay": edge.get("idempotent_replay"),
        },
        "closed_loop_edge": {
            "ran_science": (edge.get("closed_loop_edge") or {}).get("ran_science"),
            "system_status": (edge.get("closed_loop_edge") or {}).get("system_status"),
            "assessment_state": (edge.get("closed_loop_edge") or {}).get("assessment_state"),
            "assessment_reason": (edge.get("closed_loop_edge") or {}).get("assessment_reason"),
            "skip_reason": (edge.get("closed_loop_edge") or {}).get("skip_reason"),
            "order": (edge.get("closed_loop_edge") or {}).get("order"),
        },
        "daily_market_voice": voice,
        "ui_read_model": {
            "canonical_root": str(canon),
            "edge_data_dir": str(resolve_data_dir(edge_data_dir)),
            "latest_trade_date_visible": ui_latest,
        },
        "automation": {
            "streamlit_required": False,
            "manual_recovery_used": recovery,
            "autonomous": bool(autonomous) and not recovery,
            "run_mode": provenance.get("run_mode") or run.get("run_mode"),
        },
        "overall": overall,
        "first_failed_stage": first_failed,
        "reason": reason,
    }


def _classify_overall(
    *,
    he_status: str,
    he_reason: str,
    edge_disp: str,
    edge_reason: str,
    panel_contains: bool,
    stock_t0: Dict[str, Any],
    voice_exists: bool,
    ems_rows: int,
    mdt0_rows: int,
) -> tuple[str, Optional[str], str]:
    if "TRADING_DAY_PROBE_FAILED" in he_status or he_status == "TRADING_DAY_PROBE_FAILED":
        return OVERALL_FAIL, "trading_day_probe", he_reason or he_status

    # Genuine non-trading skip (never conflate with probe failure — handled above).
    if edge_disp == "SKIPPED_NON_TRADING_DAY" or he_status == "SKIPPED_NON_TRADING_DAY":
        return OVERALL_SKIPPED, None, edge_reason or he_reason or "non_trading_day"

    if edge_disp == "WAITING_FOR_DATA":
        stage = "edge_panel" if edge_reason == "target_date_not_in_panel_sessions" else "edge_data_readiness"
        if (stock_t0.get("observations_rows") or 0) == 0 and (stock_t0.get("freeze_rows") or 0) == 0:
            stage = "stock_t0"
        return OVERALL_WAITING, stage, edge_reason or "waiting_for_data"

    if he_status in ("WAITING_FOR_DATA", "FAILED") and edge_disp not in ("SUCCESS",):
        return (
            OVERALL_WAITING if he_status == "WAITING_FOR_DATA" else OVERALL_FAIL,
            "headless_eod",
            he_reason or he_status,
        )

    if edge_disp == "SUCCESS":
        if not panel_contains:
            return OVERALL_FAIL, "edge_panel", "success_but_panel_missing_trade_date"
        if (stock_t0.get("observations_rows") or 0) <= 0 and (stock_t0.get("freeze_rows") or 0) <= 0:
            return OVERALL_FAIL, "stock_t0", "success_but_stock_t0_missing"
        if ems_rows <= 0 or mdt0_rows <= 0:
            return OVERALL_FAIL, "canonical_eod", "success_but_ems_or_mdt0_missing"
        if not voice_exists:
            return OVERALL_FAIL, "daily_market_voice", "success_but_session_voice_missing"
        # Headless may be skipped in emergency/tests if artifacts already present.
        return OVERALL_PASS, None, "autonomous_daily_pipeline_complete"

    if edge_disp in ("FAILED_CLOSED", "PARTIAL_RECOVERABLE", "LOCK_HELD"):
        return OVERALL_FAIL, "edge_research", edge_reason or edge_disp

    return OVERALL_FAIL, "unknown", f"unclassified he={he_status} edge={edge_disp}"


def persist_daily_pipeline_receipt(
    receipt: Dict[str, Any],
    *,
    repo_root: Optional[Path] = None,
) -> Optional[Path]:
    """Write receipt atomically. Never raises."""
    try:
        td = str(receipt.get("trade_date") or "")[:10]
        if not td:
            return None
        path = receipt_path(td, repo_root=repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily pipeline receipt persist failed safely: %s", exc)
        return None


def write_receipt_from_run(
    trade_date: str,
    *,
    repo_root: Optional[Path] = None,
    edge_data_dir: Optional[Path] = None,
    headless_eod: Optional[Dict[str, Any]] = None,
    edge_result: Optional[Dict[str, Any]] = None,
    panel_freshness: Optional[Dict[str, Any]] = None,
    run_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build + persist receipt. Fail-safe: returns {ok:False,...} on error; never raises.
    """
    try:
        receipt = build_daily_pipeline_receipt(
            trade_date,
            repo_root=repo_root,
            edge_data_dir=edge_data_dir,
            headless_eod=headless_eod,
            edge_result=edge_result,
            panel_freshness=panel_freshness,
            run_provenance=run_provenance,
        )
        path = persist_daily_pipeline_receipt(receipt, repo_root=repo_root)
        return {"ok": path is not None, "path": str(path) if path else None, "receipt": receipt}
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily pipeline receipt failed safely: %s", exc)
        return {
            "ok": False,
            "path": None,
            "error": f"{type(exc).__name__}:{exc}",
            "receipt": None,
        }
