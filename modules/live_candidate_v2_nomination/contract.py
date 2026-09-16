"""Brain A nomination contract — Slice 1, SHADOW ONLY.

Candidate != BUY. Nomination allocates Camera attention, not a trade.
This module does not publish data/live_candidate/dynamic_watchlist.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Pass-through source id. Not added to candidate_router ENABLED_SOURCES.
SRC_BRAIN_A = "brain_a_scan_setup"

SCHEMA_ID = "live_candidate_v2_brain_a_nomination_shadow_v1"
SLICE = 1
MODE = "SHADOW_ONLY"

# Exact existing classify_group labels. Do not invent new buckets.
PRIMARY_SETUPS = frozenset({"PULL ĐẸP", "PULL VỪA", "MUA BREAK", "CP MẠNH"})
SECONDARY_SETUP = "MUA EARLY"
RESERVED_SETUPS = frozenset({"GÀ TĂNG TỐC"})
EXCLUDED_SETUPS = frozenset({"THEO DÕI", "TÍCH LŨY"})

# Existing Elite KẾT LUẬN strings. Metadata only — never a nomination gate.
ELITE_BUY_GRADES = frozenset({"BUY ELITE", "MUA NHỎ / ƯU TIÊN"})
MARKET_WEAK_CONCLUSION = "WATCHLIST - MARKET YẾU"
HARD_BAD_CONCLUSION = "LOẠI - TRỤC XẤU"
WATCHLIST_CONCLUSIONS = frozenset({"WATCHLIST", MARKET_WEAK_CONCLUSION})

STATUS_NOMINATED = "NOMINATED"
CHRONOLOGY_ELIGIBLE = "ELIGIBLE"
CHRONOLOGY_NOT_YET_ELIGIBLE = "NOT_YET_ELIGIBLE"

REJECT_MISSING_SYMBOL = "MISSING_SYMBOL"
REJECT_MARKET_WEAK = "MARKET_WEAK"
REJECT_HARD_BAD = "HARD_BAD"
REJECT_SETUP_RESERVED = "SETUP_RESERVED_SLICE1"
REJECT_SETUP_EXCLUDED = "SETUP_EXCLUDED"
REJECT_BARE_MUA_EARLY = "BARE_MUA_EARLY"
REJECT_ELITE_GRADE_ALONE = "ELITE_GRADE_ALONE"
REJECT_WATCHLIST_ALONE = "WATCHLIST_ALONE"
REJECT_WINPROB_ALONE = "WINPROB_ALONE"
REJECT_NOT_IN_UNIVERSE = "NOT_IN_UNIVERSE"

MARKET_PERMISSION_OK = "OK"
MARKET_PERMISSION_WEAK = MARKET_WEAK_CONCLUSION

PRODUCTION_WATCHLIST_RELPATH = "data/live_candidate/dynamic_watchlist.json"
DEFAULT_SHADOW_RELPATH = "research/live_candidate_v2_nomination_shadow/nominations.json"

QUALIFIED_BY_PRIMARY = "PRIMARY"
QUALIFIED_BY_EARLY_LAB = "IN_EARLY_LAB"
QUALIFIED_BY_TEST_EARLY = "TEST EARLY"


@dataclass(frozen=True)
class FrozenRefs:
    price_at_first_seen: float | None
    ema9_at_first_seen: float | None
    breakout_ref_at_first_seen: float | None


@dataclass(frozen=True)
class FreezeRecord:
    session: str
    symbol: str
    candidate_first_seen_ts: str
    price_at_first_seen: float | None
    ema9_at_first_seen: float | None
    breakout_ref_at_first_seen: float | None


@dataclass(frozen=True)
class BrainANomination:
    """Human-auditable Camera nomination. Not a BUY ticket."""

    symbol: str
    session: str
    setup: str
    group: str
    candidate_first_seen_ts: str
    candidate_updated_ts: str
    eligible_from: str
    chronology_status: str
    price_at_first_seen: float | None
    ema9_at_first_seen: float | None
    breakout_ref_at_first_seen: float | None
    nomination_reason: str
    observation_intent: str
    observation_action: str
    source: str = SRC_BRAIN_A
    elite_buy_grade: str = ""
    market_real: float | None = None
    market_permission: str = ""
    in_early_lab: bool = False
    status: str = STATUS_NOMINATED
    qualified_by: str = ""


@dataclass(frozen=True)
class RejectedRow:
    symbol: str
    setup: str
    reason: str
    elite_buy_grade: str = ""
    winprob: float | None = None
    in_early_lab: bool = False
    extra: dict = field(default_factory=dict)
