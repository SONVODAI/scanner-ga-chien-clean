"""Rotation Watch vocabulary. P×V labels stay in the frozen interpreter."""

from __future__ import annotations

# Rotation states (second-layer machine). Not P×V outputs.
ST_DATA_UNCERTAIN = "DATA_UNCERTAIN"
ST_WATCH = "WATCH"
ST_LOWER_ZONE = "LOWER_ZONE"
ST_BUY_READY = "BUY_READY"
ST_HOLD = "HOLD"
ST_UPPER_ZONE = "UPPER_ZONE"
ST_SELL_READY = "SELL_READY"
ST_TREND_HOLD = "TREND_HOLD"
ST_RISK = "RISK"

# Human-facing suggested actions (stable English codes).
ACT_WAIT = "WAIT"
ACT_WATCH_LOWER = "WATCH LOWER"
ACT_BUY_READY = "BUY READY"
ACT_HOLD = "HOLD"
ACT_WATCH_UPPER = "WATCH UPPER"
ACT_SELL_READY = "SELL READY"
ACT_TREND_HOLD = "TREND HOLD"
ACT_RISK = "RISK / REVIEW"

# Price location vs configured zones. No extra proximity pad.
LOC_BELOW_LOWER = "BELOW_LOWER"
LOC_LOWER = "LOWER"
LOC_MIDDLE = "MIDDLE"
LOC_UPPER = "UPPER"
LOC_ABOVE_UPPER = "ABOVE_UPPER"

# Data source ids — never silently substitute daily/Yahoo.
SOURCE_KBS = "vnstock4_kbs"
SOURCE_LABEL_KBS = "Camera KBS 5m (vnstock4 Quote source=KBS)"
SOURCE_INJECTED = "injected"
SOURCE_LABEL_INJECTED = "injected test bars"
SOURCE_UNAVAILABLE = "unavailable"

# Freshness labels (Rotation clock, reusing completed-bar + stale helpers).
FRESH_LIVE = "LIVE"
FRESH_STALE = "STALE"
FRESH_LUNCH_HOLD = "LUNCH_HOLD"
FRESH_SESSION_CLOSED = "SESSION_CLOSED"
FRESH_MISSING = "MISSING"
FRESH_WRONG_SESSION = "WRONG_SESSION"
FRESH_INVALID = "INVALID"
FRESH_PROVIDER_ERROR = "PROVIDER_ERROR"
FRESH_UNFINISHED_ONLY = "UNFINISHED_ONLY"

ACTIONABLE_STATES = frozenset({ST_BUY_READY, ST_SELL_READY, ST_TREND_HOLD, ST_RISK})

STATE_TO_ACTION = {
    ST_DATA_UNCERTAIN: ACT_WAIT,
    ST_WATCH: ACT_WAIT,
    ST_LOWER_ZONE: ACT_WATCH_LOWER,
    ST_BUY_READY: ACT_BUY_READY,
    ST_HOLD: ACT_HOLD,
    ST_UPPER_ZONE: ACT_WATCH_UPPER,
    ST_SELL_READY: ACT_SELL_READY,
    ST_TREND_HOLD: ACT_TREND_HOLD,
    ST_RISK: ACT_RISK,
}

SCHEMA_STATE = "rotation_watch_state.v1"
WATCHLIST_NAME = "watchlist.csv"
STATE_NAME = "state.json"
ENV_WATCHLIST = "MRBOT_ROTATION_WATCHLIST"
ENV_DIR = "MRBOT_ROTATION_WATCH_DIR"

# T+2.5 is a caption checkpoint only (trading days from entry to session).
T25_MIN_SESSIONS = 2
