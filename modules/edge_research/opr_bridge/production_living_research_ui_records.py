"""
Phase 3K.4 — Living Research UI record types and constants.
"""

from __future__ import annotations

LIVING_RESEARCH_UI_VERSION = "living_research_ui_v1_3k4"
STOP_LIVING_RESEARCH_UI_READY = "STOP_LIVING_RESEARCH_UI_READY"

FORBIDDEN_UI_TERMS = frozenset({
    "BUY",
    "SELL",
    "STRONG BUY",
    "STRONG SELL",
    "ENTRY",
    "TARGET PRICE",
    "STOP LOSS",
    "EDGE ACTIVE",
    "EDGE_ACTIVE",
    "BUYABLE",
    "PROFITABLE",
})

AUTHORITY_BADGE_RESEARCH_ONLY = "RESEARCH ONLY"
RUN_MODE_LABELS = {
    "LIVE_FORWARD": "LIVE_FORWARD — forward evidence có thể tính",
    "BACKFILL_NON_FORWARD": "BACKFILL — không phải forward evidence thật",
    "HISTORICAL_REPLAY_TEST": "HISTORICAL REPLAY — mô phỏng, không phải forward evidence thật",
}
