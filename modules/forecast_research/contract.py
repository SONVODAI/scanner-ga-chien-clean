"""
Forecast Data Contract V1 — research data infrastructure only.

Reuses existing PIT sources (earning_money_snapshots, market_daily_t0).
Does NOT train models, change Market First scores, or couple to Edge Research authority.
"""

from __future__ import annotations

CONTRACT_VERSION = "forecast_data_contract_v1"
FEATURE_SCHEMA_VERSION = "forecast_t0_features_v1"
OUTCOME_SCHEMA_VERSION = "forecast_outcomes_v1"
EXPECTED_UNIVERSE_SIZE = 142

# Trading-session horizons (not calendar days).
OUTCOME_HORIZONS = (3, 5, 10)

# Classification thresholds (versioned; continuous outcomes remain authoritative).
THRESHOLDS_VERSION = "forecast_label_thresholds_v1"
STRONG_UP_PCT = 1.0
DOWN_PCT = -1.0
RECOVER_WEAK_REAL = 6.0
RECOVER_WEAK_XS_T5 = 1.5
FAIL_STRONG_REAL = 8.0
FAIL_STRONG_XS_T5 = -1.0

GROUPS = (
    "THEO DÕI",
    "TÍCH LŨY",
    "MUA EARLY",
    "PULL VỪA",
    "PULL ĐẸP",
    "MUA BREAK",
    "CP MẠNH",
    "GÀ TĂNG TỐC",
)

COMPLETENESS_COMPLETE = "COMPLETE"
COMPLETENESS_PARTIAL = "PARTIAL"
COMPLETENESS_INVALID = "INVALID"
COMPLETENESS_WAITING = "WAITING_FOR_DATA"

# MFE/MAE semantics (locked for V1):
# Equal-weight synthetic universe: each session's mean of per-symbol close-to-close
# returns among symbols present on consecutive board snapshots; path MFE/MAE is
# max/min of cumulative EW level from T0 to Th (trading sessions).
MFE_MAE_BASIS = "equal_weight_universe_path"

DEFAULT_DATA_DIR_NAME = "forecast_research"
T0_FILE = "forecast_t0_daily.csv"
OUTCOMES_FILE = "forecast_outcomes.csv"
STATUS_FILE = "forecast_pipeline_status.json"
MATRIX_FILE = "feature_availability_matrix.json"
