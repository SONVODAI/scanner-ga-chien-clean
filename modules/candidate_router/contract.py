"""Nominated Candidate contract for the isolated Candidate Router.

Slice 1: BUY ELITE is the only enabled input. Rotation / HOF / Learning Insight
source ids are reserved so a later adapter can be added without changing Elite
decision logic. This module does not stamp clocks and does not write history.

`group` / `setup` are pass-through source metadata. The router never infers
them from candidate_reason or Elite conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.live_candidate.contract import SOURCE as ELITE_SOURCE

# Camera poll budget (modules.live_camera_shadow.rate.LIVE_UNIVERSE_CAP).
# NOT the Candidate Router discovery cap. Router default cap is None.
UNIVERSE_CAP = 50

SRC_BUY_ELITE = ELITE_SOURCE
SRC_ROTATION = "rotation_watch"
SRC_HOF = "hall_of_fame"
SRC_LEARNING_INSIGHT = "learning_insight"

# Slice 1 gate. Future adapters must not be added here until their chronology
# contract is live. Direction: source artifact → downstream adapter → router.
ENABLED_SOURCES = frozenset({SRC_BUY_ELITE})

# Lower integer = higher priority. Unused sources stay listed so a later
# Rotation adapter can plug in without inventing a second priority table.
# Priority selects the canonical nomination; it must not erase losing provenance.
SOURCE_PRIORITY = {
    SRC_BUY_ELITE: 0,
    SRC_ROTATION: 10,
    SRC_HOF: 20,
    SRC_LEARNING_INSIGHT: 30,
}
DEFAULT_SOURCE_PRIORITY = 1000

WATCHLIST_COLUMNS = [
    "session",
    "symbol",
    "candidate_first_seen_ts",
    "candidate_updated_ts",
    "candidate_reason",
    "source",
    "status",
    "eligible_from",
]

REJECT_MISSING_SYMBOL = "MISSING_SYMBOL"
REJECT_MISSING_SESSION = "MISSING_SESSION"
REJECT_MISSING_FIRST_SEEN = "MISSING_FIRST_SEEN"
REJECT_ILLEGAL_FIRST_SEEN = "ILLEGAL_FIRST_SEEN"
REJECT_MISSING_ELIGIBLE_FROM = "MISSING_ELIGIBLE_FROM"
REJECT_ILLEGAL_ELIGIBLE_FROM = "ILLEGAL_ELIGIBLE_FROM"
REJECT_SOURCE_NOT_ENABLED = "SOURCE_NOT_ENABLED"
REJECT_CHRONOLOGY_BACKWARD = "CHRONOLOGY_BACKWARD"
REJECT_NOT_YET_ELIGIBLE = "NOT_YET_ELIGIBLE"


def pass_through_meta(value: object) -> str:
    """Keep source text. Empty / NaN → ''. Never invent a label."""
    s = str(value or "").strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return ""
    return s


@dataclass(frozen=True)
class NominatedCandidate:
    """Explicit source contract. Timestamps are opaque source strings.

    The router never fills candidate_first_seen_ts, eligible_from, or
    candidate_updated_ts from `now`, CSV mtime, or session open/close.

    group: Elite history `group` (e.g. PULL ĐẸP) when the source record has it.
    setup: only if the source record already has a distinct `setup` field.
    candidate_reason: Elite conclusion (BUY ELITE / MUA NHỎ / …), not group.
    """

    symbol: str
    source: str
    candidate_first_seen_ts: str
    eligible_from: str
    session: str
    candidate_updated_ts: str = ""
    status: str = ""
    candidate_reason: str = ""
    source_state: str = ""
    source_action: str = ""
    source_reason: str = ""
    group: str = ""
    setup: str = ""


@dataclass(frozen=True)
class RejectedNomination:
    nomination: NominatedCandidate
    reason: str


@dataclass(frozen=True)
class SymbolProvenance:
    """Inspectable per-symbol evidence after routing.

    `canonical` is the compatibility winner. `nominations` includes the winner
    first, then every other accepted competitor. Source priority must not drop
    losing source / reason / state / group / first_seen.
    """

    symbol: str
    canonical: NominatedCandidate
    nominations: tuple[NominatedCandidate, ...]
