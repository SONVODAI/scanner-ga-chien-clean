"""
Phase 3K.5A — EOD completeness gate audit (authoritative contract enforced).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.adapters import MARKET_T0_SNAPSHOT_PATH
from modules.edge_research.opr_bridge.production_data_readiness_gate import verify_data_readiness
from modules.edge_research.opr_bridge.production_eod_completeness import verify_eod_completeness

EOD_AUDIT_VERSION = "eod_completeness_audit_v2_3k5a"


def audit_eod_completeness_gate(
    panel: pd.DataFrame,
    target_trade_date: str,
) -> Dict[str, Any]:
    """
    Audit authoritative EOD completeness contract vs readiness gate integration.
    """
    readiness = verify_data_readiness(
        panel, target_trade_date, require_authoritative_eod=True
    )
    eod = verify_eod_completeness(panel, target_trade_date)
    gaps: List[str] = []
    if not eod.complete:
        gaps.append(eod.reason)
    if not readiness.eod_completeness_established:
        gaps.append("readiness_gate_eod_not_established")

    sub = panel[panel["trade_date"].astype(str) == str(target_trade_date)] if not panel.empty else pd.DataFrame()
    universe_n = len(sub["symbol"].unique()) if not sub.empty and "symbol" in sub.columns else 0

    sufficient = eod.complete and readiness.eod_completeness_established

    return {
        "version": EOD_AUDIT_VERSION,
        "target_trade_date": target_trade_date,
        "readiness_result": readiness.to_dict(),
        "eod_completeness": eod.to_dict(),
        "signals_checked": [
            "t0_observation_freeze_rows_for_session",
            "frozen_at_present",
            "freeze_panel_row_alignment",
            "no_duplicate_freeze_ids",
            "no_source_mutation_after_freeze",
            "market_t0_AFTER_CLOSE",
        ],
        "gaps": gaps,
        "target_row_count": len(sub),
        "target_universe_size": universe_n,
        "market_t0_snapshot_exists": MARKET_T0_SNAPSHOT_PATH.exists(),
        "production_gate_sufficient_for_live_forward": sufficient,
        "verdict": "PASS" if sufficient else "FAIL",
        "prerequisite": None if sufficient else (
            "Authoritative EOD freeze evidence required before LIVE_FORWARD. "
            "Verify earning_learning pipeline completed for target session."
        ),
    }
