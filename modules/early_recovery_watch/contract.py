"""EARLY RECOVERY WATCH V1. Research only. Not a buy rule.

Thresholds are locked. They are not learned, tuned, or widened.
"""

from __future__ import annotations

EARLY_RECOVERY_IS_BUY = False
EARLY_RECOVERY_ALERT_ELIGIBLE = False

DATA_MODE_FORWARD = "FORWARD"

# Locked V1 gates. Do not change these values.
DELTA_RS10_MIN = 4.0
RS10_MAX = 2.64
MARKET_REAL_MAX_EXCLUSIVE = 7.0

VOL_CONFIRM_TEXT = "Vol xác nhận"

SCHEMA_EVENT = "early_recovery_watch_event.v1"
SCHEMA_OUTCOME = "early_recovery_watch_outcome.v1"

EVENTS_NAME = "events.jsonl"
REMOTE_DIR = "research/early_recovery_watch"
ENV_DIR = "MRBOT_EARLY_RECOVERY_DIR"

HORIZONS = (3, 5, 10)

WEAK_KINDS = frozenset({"RAT_YEU", "YEU", "YEU_DAN"})
RECOVERY_KIND = "DANG_HOI"

T0_FIELDS = (
    "event_id",
    "symbol",
    "event_date",
    "event_timestamp",
    "t0_price",
    "previous_health",
    "current_health",
    "previous_rs10",
    "current_rs10",
    "delta_rs10",
    "vol_confirm",
    "market_real_t0",
    "previous_observation_id",
    "current_scan_fingerprint",
    "current_captured_at",
    "current_source",
    "data_mode",
)

OUTCOME_FIELDS = ("t3_return_pct", "t5_return_pct", "t10_return_pct")

PANEL_TITLE = "EARLY RECOVERY WATCH — Research only"
EMPTY_MESSAGE = "Chưa có Early Recovery fingerprint phù hợp."
