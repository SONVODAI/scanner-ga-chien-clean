"""Isolated Candidate Router foundation (Slice 1, Elite-only, shadow).

Does not publish dynamic_watchlist.json. Does not change BUY ELITE persist.
Does not enable live-shadow, Telegram, or systemd.
"""

from modules.candidate_router.contract import (
    ENABLED_SOURCES,
    NominatedCandidate,
    SOURCE_PRIORITY,
    SRC_BUY_ELITE,
    SRC_HOF,
    SRC_LEARNING_INSIGHT,
    SRC_ROTATION,
    UNIVERSE_CAP,
    WATCHLIST_COLUMNS,
)
from modules.candidate_router.elite import nominations_from_buy_elite_history
from modules.candidate_router.router import build_routed_watchlist, route_candidates

__all__ = [
    "ENABLED_SOURCES",
    "NominatedCandidate",
    "SOURCE_PRIORITY",
    "SRC_BUY_ELITE",
    "SRC_HOF",
    "SRC_LEARNING_INSIGHT",
    "SRC_ROTATION",
    "UNIVERSE_CAP",
    "WATCHLIST_COLUMNS",
    "build_routed_watchlist",
    "nominations_from_buy_elite_history",
    "route_candidates",
]
