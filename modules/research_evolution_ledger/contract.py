"""Evolution Observer V1 contract. Collection only. Not a trading rule.

The ledger copies raw scan fields that already exist. It does not score,
classify a recovery, nominate, or read a research archive back into production.

A later research reader may attach Market Context only when, after both
clocks are converted to Asia/Ho_Chi_Minh:

    context.captured_at <= evolution.captured_at

for the same trade_date and source, preferring the row whose
scan_fingerprint matches. A later context row is not eligible.
"""

from __future__ import annotations

from datetime import datetime

from modules.live_candidate.calendar import as_vn
from modules.research_market_context.contract import SOURCE_CLOSE_SCAN, SOURCE_STREAMLIT_SCAN

LEDGER_NAME = "evolution_ledger.jsonl"
STATUS_OK = "ok"

# Observed scan columns, in file order. Missing columns stay null.
OBSERVED_FIELDS: tuple[str, ...] = (
    "price",
    "group",
    "group_rank",
    "evolution_health_group",
    "evolution_health_score",
    "evolution_health_rank",
    "rs5",
    "rs10",
    "rsi14",
    "rsi_slope",
    "obv_status",
    "ema9",
    "ma20",
    "ema9_ma20_slope",
    "ema9_ma20_slope_change",
    "dist_from_ema9_pct",
    "volume",
    "vol_ma20",
    "dryup_ratio_5",
    "dryup_ratio_10",
    "near_bottom_20_pct",
    "near_bottom_60_pct",
    "dist_high20_pct",
    "green_2_confirm",
    "early_green2",
    "early_dry_green2",
    "pull_label",
    "total_score",
    "E",
    "R",
    "O",
    "S",
    "RS",
    "V",
    "is_live_adjusted",
)

TEXT_FIELDS = frozenset({
    "group",
    "evolution_health_group",
    "obv_status",
    "green_2_confirm",
    "early_green2",
    "early_dry_green2",
    "pull_label",
})

BOOL_FIELDS = frozenset({"is_live_adjusted"})

PROVENANCE_FIELDS: tuple[str, ...] = (
    "trade_date",
    "captured_at",
    "session_slot",
    "symbol",
    "source",
    "status",
    "scan_fingerprint",
    "state_hash",
)


def evolution_context_asof_eligible(
    context_captured_at: datetime,
    evolution_captured_at: datetime,
) -> bool:
    """True when the market-context row was already known at the evolution row."""
    return as_vn(context_captured_at) <= as_vn(evolution_captured_at)


__all__ = [
    "BOOL_FIELDS",
    "LEDGER_NAME",
    "OBSERVED_FIELDS",
    "PROVENANCE_FIELDS",
    "SOURCE_CLOSE_SCAN",
    "SOURCE_STREAMLIT_SCAN",
    "STATUS_OK",
    "TEXT_FIELDS",
    "evolution_context_asof_eligible",
]
