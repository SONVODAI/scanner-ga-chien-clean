"""Isolated Brain A nomination layer (LIVE CANDIDATE V2 Slice 1, SHADOW ONLY).

Does not publish dynamic_watchlist.json.
Does not wire Candidate Router into production.
Does not change Rotation / P×V / Elite math / GROUP_RANK / NAV / BUY-SELL.
"""

from modules.live_candidate_v2_nomination.artifact import (
    DEFAULT_SHADOW_PATH,
    PRODUCTION_WATCHLIST,
    build_shadow_document,
    write_shadow_artifact,
)
from modules.live_candidate_v2_nomination.contract import (
    PRIMARY_SETUPS,
    SRC_BRAIN_A,
    BrainANomination,
)
from modules.live_candidate_v2_nomination.nominate import (
    NominationReport,
    nominate_scan_rows,
    to_nominated_candidate,
)
from modules.live_candidate_v2_nomination.predicate import evaluate_nomination

__all__ = [
    "DEFAULT_SHADOW_PATH",
    "PRIMARY_SETUPS",
    "PRODUCTION_WATCHLIST",
    "SRC_BRAIN_A",
    "BrainANomination",
    "NominationReport",
    "build_shadow_document",
    "evaluate_nomination",
    "nominate_scan_rows",
    "to_nominated_candidate",
    "write_shadow_artifact",
]
