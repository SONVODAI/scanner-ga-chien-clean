"""Research-only constants for Intraday P×V Interpreter V1 Slice 1.

Every numeric cut is a RESEARCH_DEFAULT — not a validated trading threshold.
Do not optimize these against T+n returns.
"""

from __future__ import annotations

MODE_SHADOW = "shadow"
PXV_V1_MODE_DEFAULT = MODE_SHADOW

# Isolated output namespace — never Camera / earning-learning / edge_research.
OUTPUT_DIRNAME = "intraday_pxv_v1"

DATA_TRUSTED = "TRUSTED"
DATA_QUALIFIED = "QUALIFIED"
DATA_LOW = "LOW_CONFIDENCE"
DATA_UNUSABLE = "UNUSABLE"

EV_STRENGTHEN = "STRENGTHEN"
EV_NEUTRAL = "NEUTRAL"
EV_WEAKEN = "WEAKEN"
EV_UNUSABLE = "UNUSABLE"
EV_CONFLICT = "CONFLICT"

TOD_PRELIMINARY = "TOD_PRELIMINARY"
TOD_EARLY = "TOD_EARLY"
TOD_MATURE = "TOD_MATURE_CANDIDATE"

# Same-symbol qualified sessions required for TOD labels.
TOD_EARLY_MIN_SESSIONS = 20
TOD_MATURE_MIN_SESSIONS = 40

# VN cash 5m grid used only to judge completeness vs clock (not a hard bar quota).
SESSION_AM_START = (9, 15)
SESSION_AM_END = (11, 30)
SESSION_PM_START = (13, 0)
SESSION_PM_END = (14, 45)
LUNCH_START = (11, 30)
LUNCH_END = (13, 0)

# --- RESEARCH_DEFAULT (unvalidated) ---
RESEARCH_DEFAULT_EXPANSION_X = 2.0
RESEARCH_DEFAULT_CONTRACTION_X = 0.70
RESEARCH_DEFAULT_PACE_AHEAD_X = 1.5
RESEARCH_DEFAULT_SESSION_MEDIAN_BARS = 6
RESEARCH_DEFAULT_THIN_FRAC = 0.50
RESEARCH_DEFAULT_DOJI_FRAC = 0.90
RESEARCH_DEFAULT_STRUCTURAL_BARS = (16, 18)
RESEARCH_DEFAULT_FIFTEEN_MIN_SEC = 12 * 60
RESEARCH_DEFAULT_CUMULATIVE_LAST_FRAC = 0.85
RESEARCH_DEFAULT_PERSISTENCE_BARS = 2
RESEARCH_DEFAULT_EVAL_START_BAR = 8

# Candidate reconstruction (documented in candidates.py).
ACTIONABLE_CONCLUSIONS = frozenset(
    {
        "BUY ELITE",
        "MUA NHỎ / ƯU TIÊN",
    }
)

FORBIDDEN_SIGNAL_WORDS = (
    "BUY",
    "SELL",
    "MUA",
    "BÁN",
    "BAN ",
)
