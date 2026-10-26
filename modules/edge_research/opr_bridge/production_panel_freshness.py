"""
Panel freshness diagnostics for production daily research entrypoint.

Read-only — compares headless EOD outcome vs research panel session coverage.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    evaluate_trading_session_eligibility,
    extract_panel_trading_sessions,
)


def diagnose_panel_freshness(
    panel: pd.DataFrame,
    target_trade_date: str,
    *,
    headless_eod: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Explain whether the panel includes target_trade_date after headless EOD.

    target_date_not_in_panel_sessions occurs when stock T0 sources (observations +
    t0_observation_freeze overlay) lack rows for the session — typically because
    headless EOD did not complete update_learning for that date.
    """
    sessions = extract_panel_trading_sessions(panel)
    panel_max = sessions[-1] if sessions else None
    eligibility = evaluate_trading_session_eligibility(panel, target_trade_date)
    headless = headless_eod or {}
    el = (headless.get("artifacts") or {}).get("earning_learning") or {}

    return {
        "target_trade_date": target_trade_date,
        "panel_row_count": int(len(panel)),
        "panel_session_count": len(sessions),
        "panel_min_trade_date": sessions[0] if sessions else None,
        "panel_max_trade_date": panel_max,
        "target_in_panel_sessions": target_trade_date in sessions,
        "eligibility_disposition": eligibility.disposition,
        "eligibility_reason": eligibility.reason,
        "headless_stage_disposition": headless.get("stage_disposition"),
        "headless_ok": headless.get("ok"),
        "headless_observations_added": el.get("observations_added"),
        "headless_t0_freeze_added": el.get("t0_freeze_added"),
        "likely_cause": _infer_cause(
            target_trade_date=target_trade_date,
            target_in_panel=target_trade_date in sessions,
            panel_max=panel_max,
            headless=headless,
        ),
    }


def _infer_cause(
    *,
    target_trade_date: str,
    target_in_panel: bool,
    panel_max: Optional[str],
    headless: Dict[str, Any],
) -> str:
    if target_in_panel:
        return "panel_includes_target"
    stage = headless.get("stage_disposition")
    if stage and stage not in ("SUCCESS", "skipped"):
        return "headless_eod_did_not_publish_t0_rows_for_target"
    if panel_max and panel_max < target_trade_date:
        return "panel_source_stale_vs_target"
    return "target_date_not_in_panel_sessions"
