"""
Actionable Research Fusion engine.

Read-only consumer of independent evidence families. Writes only
data/actionable_research artifacts. Never mutates edge_memory,
edge_forward_ledger, T0 freeze, Camera, or foreign scientific stores.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.actionable_research.camera import classify_intraday_activity, default_session_cutoff
from modules.actionable_research.contracts import (
    AUTHORITY_LABEL,
    FUSION_SCHEMA_VERSION,
    FUSION_VERSION,
    SESSION_ELIGIBLE,
    SESSION_SKIPPED_NON_TRADING,
    SESSION_UNABLE,
    SKIPPED_NON_TRADING_VI,
    SPEAK_POLICY,
    UNABLE_VI,
)
from modules.actionable_research.edge import (
    assess_edge_for_symbols,
    load_active_edges,
    load_recognition,
)
from modules.actionable_research.foreign import classify_foreign_flow
from modules.actionable_research.interpret import finalize_record, scan_summary, session_surface
from modules.actionable_research.market import load_market_context
from modules.actionable_research.paths import FusionPaths, utc_now_iso
from modules.actionable_research.persist import persist_fusion_artifact
from modules.actionable_research.stock_state import (
    load_canonical_universe,
    load_t0_freeze,
    session_stock_rows,
)
from modules.actionable_research.sweetspot import load_sweetspot_auxiliary
from modules.intraday_memory.timezone_policy import VN_TZ


SKIP_DISPOSITIONS = {
    "SKIPPED_NON_TRADING_DAY",
    SESSION_SKIPPED_NON_TRADING,
}

UNABLE_DISPOSITIONS = {
    "SKIPPED_T0_NOT_READY",
    "WAITING_FOR_DATA",
    "SKIPPED_WAITING_FOR_DATA",
    "LOCK_HELD",
    "SKIPPED_LOCK_HELD",
}


def _calendar_eligibility(trade_date: str) -> Dict[str, Any]:
    try:
        from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
            evaluate_calendar_session_eligibility,
        )

        result = evaluate_calendar_session_eligibility(str(trade_date)[:10])
        return {
            "eligible": bool(result.eligible),
            "disposition": str(result.disposition),
            "reason": str(result.reason),
            "is_holiday": bool(result.is_holiday),
            "is_weekend": bool(result.is_weekend),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "eligible": False,
            "disposition": SESSION_UNABLE,
            "reason": f"calendar_error:{type(exc).__name__}",
            "is_holiday": False,
            "is_weekend": False,
        }


def resolve_session_eligibility(
    trade_date: str,
    *,
    paths: FusionPaths,
    daily_result: Optional[Dict[str, Any]] = None,
    freeze: Optional[pd.DataFrame] = None,
    force_eligible: Optional[bool] = None,
) -> Dict[str, Any]:
    td = str(trade_date)[:10]
    if force_eligible is False:
        return {
            "session_status": SESSION_SKIPPED_NON_TRADING,
            "reason": "CALLER_MARKED_NON_TRADING",
            "eligible": False,
        }
    if daily_result:
        run = daily_result.get("run") if isinstance(daily_result.get("run"), dict) else daily_result
        disp = str(
            (run or {}).get("run_disposition")
            or daily_result.get("run_disposition")
            or daily_result.get("session_status")
            or ""
        )
        skip_reason = str(daily_result.get("skip_reason") or (run or {}).get("failure_or_skip_reason") or "")
        if daily_result.get("lock_held") or disp in {"LOCK_HELD", "SKIPPED_LOCK_HELD"}:
            return {
                "session_status": SESSION_UNABLE,
                "reason": "SKIPPED_LOCK_HELD",
                "eligible": False,
            }
        if disp in SKIP_DISPOSITIONS or skip_reason in SKIP_DISPOSITIONS:
            return {
                "session_status": SESSION_SKIPPED_NON_TRADING,
                "reason": disp or skip_reason or SESSION_SKIPPED_NON_TRADING,
                "eligible": False,
            }
        if disp in UNABLE_DISPOSITIONS or skip_reason in UNABLE_DISPOSITIONS:
            return {
                "session_status": SESSION_UNABLE,
                "reason": disp or skip_reason or SESSION_UNABLE,
                "eligible": False,
            }
        cle = daily_result.get("closed_loop_edge") if isinstance(daily_result.get("closed_loop_edge"), dict) else {}
        cle_skip = str((cle or {}).get("skip_reason") or "")
        if cle_skip in SKIP_DISPOSITIONS:
            return {
                "session_status": SESSION_SKIPPED_NON_TRADING,
                "reason": cle_skip,
                "eligible": False,
            }
        if cle_skip in UNABLE_DISPOSITIONS:
            return {
                "session_status": SESSION_UNABLE,
                "reason": cle_skip,
                "eligible": False,
            }
    if force_eligible is True:
        return {"session_status": SESSION_ELIGIBLE, "reason": "CALLER_FORCE_ELIGIBLE", "eligible": True}

    cal = _calendar_eligibility(td)
    if not cal["eligible"]:
        status = (
            SESSION_SKIPPED_NON_TRADING
            if cal["disposition"] in SKIP_DISPOSITIONS or cal["is_holiday"] or cal["is_weekend"]
            else SESSION_UNABLE
        )
        return {
            "session_status": status,
            "reason": cal["reason"] or cal["disposition"],
            "eligible": False,
        }
    return {
        "session_status": SESSION_ELIGIBLE,
        "reason": cal.get("reason") or "calendar_trading_session",
        "eligible": True,
    }


def _cutoff_iso(cutoff: Optional[datetime | str], trade_date: str) -> str:
    if cutoff is None:
        ts = default_session_cutoff(trade_date)
    elif isinstance(cutoff, datetime):
        ts = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=VN_TZ)
        ts = ts.astimezone(VN_TZ)
    else:
        ts = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=VN_TZ)
        ts = ts.astimezone(VN_TZ)
    return ts.isoformat()


def fuse_session(
    trade_date: str,
    *,
    paths: Optional[FusionPaths] = None,
    cutoff: Optional[datetime | str] = None,
    daily_result: Optional[Dict[str, Any]] = None,
    foreign_frame: Optional[pd.DataFrame] = None,
    persist: bool = True,
    now: Optional[datetime] = None,
    force_eligible: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Build one fusion artifact for an eligible trading session.

    Evidence families are independent: absence of one is UNKNOWN, never a gate.
    """
    paths = paths or FusionPaths()
    td = str(trade_date)[:10]
    freeze = load_t0_freeze(paths)
    eligibility = resolve_session_eligibility(
        td,
        paths=paths,
        daily_result=daily_result,
        freeze=freeze,
        force_eligible=force_eligible,
    )
    generated_at = utc_now_iso(now)

    if not eligibility["eligible"]:
        unable = eligibility["session_status"] == SESSION_UNABLE
        payload = {
            "trade_date": td,
            "session_status": eligibility["session_status"],
            "skip_reason": eligibility["reason"],
            "authority": AUTHORITY_LABEL,
            "research_label": AUTHORITY_LABEL,
            "fusion_version": FUSION_VERSION,
            "schema_version": FUSION_SCHEMA_VERSION,
            "records": [],
            "observations": [],
            "scan": {"scanned_count": 0, "notable_count": 0},
            "speak_policy": SPEAK_POLICY,
            "notable_count": 0,
            "surfaced_symbols": [],
            "headline_vi": UNABLE_VI if unable else SKIPPED_NON_TRADING_VI,
            "no_interest": False,
            "scientific_writes": [],
            "generated_at": generated_at,
            "camera_cutoff_timestamp": None,
            "note": (
                "UNABLE; missing required canonical T0 — not 'nothing noteworthy'."
                if unable
                else "SKIPPED_NON_TRADING_DAY; no new T0 observation and no calendar-day maturity."
            ),
        }
        if persist:
            payload = persist_fusion_artifact(payload, paths=paths, now=now)
        return payload

    universe = load_canonical_universe(paths)
    symbols = list(universe)
    market = load_market_context(td, paths=paths)
    stock_rows = session_stock_rows(td, paths=paths, universe=symbols, freeze=freeze)
    active = load_active_edges(paths)
    recognition = load_recognition(td, paths=paths)
    edge_by_symbol = assess_edge_for_symbols(symbols, active=active, recognition=recognition)
    sweet_by_symbol = load_sweetspot_auxiliary(td, symbols, paths=paths)
    camera = classify_intraday_activity(td, symbols, paths=paths, cutoff=cutoff)
    foreign = classify_foreign_flow(td, symbols, paths=paths, injected=foreign_frame)
    cutoff_iso = camera.get("cutoff") or _cutoff_iso(cutoff, td)

    records: List[Dict[str, Any]] = []
    for stock in stock_rows:
        symbol = stock["symbol"]
        rec: Dict[str, Any] = {
            "trade_date": td,
            "symbol": symbol,
            "market_state": market.get("market_state"),
            "market_transition": market.get("market_transition"),
            "market_trajectory": market.get("market_trajectory"),
            "market_context_source": market.get("market_context_source"),
            "stock_state": stock.get("stock_state"),
            "stock_pattern_labels": stock.get("stock_pattern_labels"),
            "pit_features": stock.get("pit_features"),
            "stock_state_source": stock.get("stock_state_source"),
            "stock_state_source_status": stock.get("stock_state_source_status"),
        }
        rec.update(edge_by_symbol.get(symbol) or {})
        rec.update(sweet_by_symbol.get(symbol) or {})
        cam = (camera.get("by_symbol") or {}).get(symbol) or {}
        rec["camera_data_status"] = cam.get("camera_data_status")
        rec["camera_cutoff_timestamp"] = cam.get("camera_cutoff_timestamp") or cutoff_iso
        rec["activity_status"] = cam.get("activity_status")
        rec["trading_value_status"] = cam.get("trading_value_status")
        rec["volume_acceleration_status"] = cam.get("volume_acceleration_status")
        rec["price_direction"] = cam.get("price_direction") or (cam.get("metrics") or {}).get(
            "price_direction"
        )
        rec["close_location"] = cam.get("close_location") or (cam.get("metrics") or {}).get(
            "close_location"
        )
        rec["camera_metrics"] = cam.get("metrics") or {}
        rec["camera_source"] = cam.get("source")
        rec["camera_provenance"] = cam.get("provenance")
        rec["camera_note"] = cam.get("note")
        ff = (foreign.get("by_symbol") or {}).get(symbol) or {}
        rec["foreign_flow_status"] = ff.get("foreign_flow_status")
        rec["foreign_net_value"] = ff.get("foreign_net_value")
        rec["foreign_net_volume"] = ff.get("foreign_net_volume")
        rec["foreign_buy_value"] = ff.get("foreign_buy_value")
        rec["foreign_sell_value"] = ff.get("foreign_sell_value")
        rec["foreign_source"] = ff.get("source")
        rec["foreign_timing"] = ff.get("timing")
        rec["foreign_data_completeness"] = ff.get("data_completeness")
        rec["foreign_note"] = ff.get("note")
        rec["authority"] = AUTHORITY_LABEL
        rec["generated_at"] = generated_at
        records.append(finalize_record(rec))

    surface = session_surface(records)
    observations = list(surface.get("observations") or [])
    scan = scan_summary(records)
    payload = {
        "trade_date": td,
        "session_status": SESSION_ELIGIBLE,
        "skip_reason": "",
        "authority": AUTHORITY_LABEL,
        "research_label": AUTHORITY_LABEL,
        "speak_policy": SPEAK_POLICY,
        "fusion_version": FUSION_VERSION,
        "schema_version": FUSION_SCHEMA_VERSION,
        "universe_count": len(symbols),
        "scanned_count": scan["scanned_count"],
        "record_count": len(observations),
        "market": market,
        "edge_memory": {
            "source": active.get("source"),
            "source_status": active.get("source_status"),
            "active_count": active.get("active_count"),
            "available": active.get("available"),
        },
        "recognition": {
            "source": recognition.get("source"),
            "source_status": recognition.get("source_status"),
            "available": recognition.get("available"),
        },
        "camera": {
            "feed_status": camera.get("feed_status"),
            "cutoff": cutoff_iso,
            "source": camera.get("source"),
            "cross_section_n": camera.get("cross_section_n"),
            "look_ahead_bars_dropped": camera.get("look_ahead_bars_dropped"),
            "note": (
                "OHLCV only. Derived activity = sum(close*volume). "
                "Not directional money inflow/outflow. No Camera foreign flow."
            ),
        },
        "foreign": {
            "available": foreign.get("available"),
            "timing": foreign.get("timing"),
            "source": foreign.get("source"),
            "completeness": foreign.get("completeness"),
            "cross_section_n": foreign.get("cross_section_n"),
            "camera_intraday_foreign": foreign.get("camera_intraday_foreign"),
            "camera_audit": foreign.get("camera_audit"),
        },
        "camera_cutoff_timestamp": cutoff_iso,
        "scan": scan,
        "observations": observations,
        "records": observations,
        "scientific_writes": [],
        "generated_at": generated_at,
        **surface,
    }
    if persist:
        payload = persist_fusion_artifact(payload, paths=paths, now=now)
    return payload
