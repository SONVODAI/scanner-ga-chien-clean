"""Schema constants for Guardian Research Stage A (isolated from production)."""

from __future__ import annotations

SCHEMA_VERSION = "guardian_research.t0.v1"

RECORD_T0 = "guardian_t0_snapshot"

# Classification source — exact production function, never reimplemented here.
CLASSIFICATION_FN = "position_guardian.generate_signal"

# Status of the research snapshot row (not the Guardian signal label).
STATUS_VALID = "VALID"
STATUS_MISSING = "MISSING"

# Required technical inputs before generate_signal may be called.
# Incomplete inputs must not become a fabricated HOLD.
REQUIRED_TECH_FIELDS = ("price", "ema9", "ma20", "obv", "obv_ema9")

# Signal labels are owned by position_guardian; research stores them verbatim.
SIGNAL_FIELD = "signal"
REASON_FIELD = "reason"
SCORE_FIELD = "sell_score"

DEFAULT_HISTORY_DIRNAME = "guardian_research_history"
DEFAULT_SNAPSHOT_FILENAME = "guardian_t0_snapshots.jsonl"
