"""Guardian Research contract. Research labels are not portfolio orders."""

from __future__ import annotations

SCHEMA = "guardian_research_snapshot.v1"

# Frozen SHA-256 of position_guardian.generate_signal, same bytes as the ledger test.
GENERATE_SIGNAL_SHA256 = (
    "ee644fc098fc01c6c4a4f54bedcefe892e1beb26b085552f3c7a9929b4c5dd4f"
)

# Production analyze_symbol refuses a daily frame shorter than this before indicators.
MINIMUM_DAILY_BARS = 40

# Production scan row rounding applied before Guardian sees the row.
PRICE_DIGITS = 0
EMA_MA_DIGITS = 2
OBV_DIGITS = 0

CLASS_HOLD = "HOLD"
CLASS_WATCH = "WATCH"
CLASS_SELL = "SELL"
CLASS_UNAVAILABLE = "UNAVAILABLE"
CLASSIFICATIONS = frozenset({CLASS_HOLD, CLASS_WATCH, CLASS_SELL, CLASS_UNAVAILABLE})

# Research names for the production signals. WATCH is production SIGNAL_WARNING.
PRODUCTION_TO_RESEARCH = {
    "🟢 GIỮ": CLASS_HOLD,
    "🟡 CẢNH BÁO": CLASS_WATCH,
    "🔴 BÁN": CLASS_SELL,
}

SCOPE_MARKET_TECHNICAL = "market_technical"

FORWARD_HORIZONS = (1, 3, 5, 10, 15, 20)
FORWARD_UNVERIFIED = "UNVERIFIED"
FORWARD_PENDING = "PENDING"
FORWARD_REASON = "PRICE_PROVENANCE_ABSENT"
# Horizons count exchange sessions. Weekday arithmetic is not this calendar.
FORWARD_CALENDAR = "trading_sessions"
FORWARD_OUTCOMES = (
    "return_pct",
    "drawdown_pct",
    "missed_rally_pct",
    "time_to_recovery_sessions",
)

SCAN_COLUMNS = ("symbol", "price", "ema9", "ma20", "obv", "obv_ema9", "date")


def unverified_forward() -> dict:
    """Reserve outcome slots. No price is read and no outcome is calculated."""
    pending = {"status": FORWARD_PENDING}
    pending.update({name: None for name in FORWARD_OUTCOMES})
    return {
        "status": FORWARD_UNVERIFIED,
        "reason": FORWARD_REASON,
        "calendar": FORWARD_CALENDAR,
        "horizons": {f"T+{horizon}": dict(pending) for horizon in FORWARD_HORIZONS},
    }
