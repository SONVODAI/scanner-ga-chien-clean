"""
Phase 3K.5 — EOD completeness gate audit (honest gap reporting).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.adapters import MARKET_T0_SNAPSHOT_PATH
from modules.edge_research.opr_bridge.production_data_readiness_gate import verify_data_readiness

EOD_AUDIT_VERSION = "eod_completeness_audit_v1_3k5"


def audit_eod_completeness_gate(
    panel: pd.DataFrame,
    target_trade_date: str,
) -> Dict[str, Any]:
    """
    Audit what the readiness gate actually proves vs what production needs.
    Does NOT invent weak heuristics — reports gaps explicitly.
    """
    readiness = verify_data_readiness(panel, target_trade_date)
    gaps: List[str] = []
    signals_checked: List[str] = []

    signals_checked.append("panel_non_empty")
    signals_checked.append("session_eligibility")
    signals_checked.append("source_max_trade_date >= target")
    signals_checked.append("temporal_provenance_validation")
    signals_checked.append("rows_for_target_date >= 1")

    gaps.append("no_18h_vn_post_eod_timestamp_check")
    gaps.append("no_t0_observation_freeze_csv_verification")
    gaps.append("no_session_slot_AFTER_CLOSE_requirement")
    gaps.append("no_universe_coverage_threshold")
    gaps.append("no_producer_completion_marker")
    gaps.append("market_context_missing_does_not_block_ready")

    sub = panel[panel["trade_date"].astype(str) == str(target_trade_date)] if not panel.empty else pd.DataFrame()
    universe_n = len(sub["symbol"].unique()) if not sub.empty and "symbol" in sub.columns else 0

    t0_exists = MARKET_T0_SNAPSHOT_PATH.exists()

    return {
        "version": EOD_AUDIT_VERSION,
        "target_trade_date": target_trade_date,
        "readiness_result": readiness.to_dict(),
        "signals_checked": signals_checked,
        "gaps": gaps,
        "target_row_count": len(sub),
        "target_universe_size": universe_n,
        "market_t0_snapshot_exists": t0_exists,
        "production_gate_sufficient_for_live_forward": False,
        "verdict": "PASS_WITH_PREREQUISITE",
        "prerequisite": (
            "Before LIVE_FORWARD Day 1, manually verify EOD collection complete "
            "(>= 18:00 Asia/Ho_Chi_Minh) and universe coverage acceptable. "
            "Automated gate proves row-presence and provenance only."
        ),
    }
