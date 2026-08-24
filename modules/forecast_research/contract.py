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

# --- Historical Market Core (separate from Forecast T0 contract) ---
HISTORICAL_CORE_SCHEMA_VERSION = "historical_market_core_v1"
HISTORICAL_CORE_FILE = "historical_market_core.csv"
HISTORICAL_CORE_STATUS_FILE = "historical_recovery_status.json"

# Quality tiers for historical recovery (explicit; never silently upgrade).
QUALITY_PIT_SAFE_COMPLETE = "PIT_SAFE_COMPLETE"
QUALITY_PIT_SAFE_PARTIAL = "PIT_SAFE_PARTIAL"
QUALITY_PIT_RECONSTRUCTABLE = "PIT_RECONSTRUCTABLE"
QUALITY_NOT_PROVABLY_PIT_SAFE = "NOT_PROVABLY_PIT_SAFE"
QUALITY_LEAKAGE_RISK_SOURCE = "LEAKAGE_RISK_SOURCE"

# Root pattern_history FC selection when multiple intraday values exist.
# Prefer last scan with clock time >= 15:00 VN (market close reference).
# This is reconstructable, never silently promoted to PIT_SAFE.
ROOT_PH_FC_RULE = "last_post_close_scan_ge_15_00"

# --- Minimum Daily Research Record V1 ---
MDRR_SCHEMA_VERSION = "minimum_daily_research_record_v1"
MDRR_FILE = "mdrr_daily.csv"
MDRR_STATUS_FILE = "mdrr_pipeline_status.json"
FORWARD_ONLY_REGISTRY_FILE = "forward_only_feature_registry.json"

# --- P0 Forward Market Memory ---
# v2: universe_foreign_* (EMS 142 VALUE via HSX/VCI); legacy foreign_* HOSE-SSI fields retained as NULL.
P0_SCHEMA_VERSION = "p0_market_memory_v2"
P0_DAILY_FILE = "p0_market_daily.csv"
P0_STATUS_FILE = "p0_market_pipeline_status.json"
P0_COMPLETENESS_COMPLETE = "COMPLETE"
P0_COMPLETENESS_PARTIAL = "PARTIAL"
P0_COMPLETENESS_WAITING = "WAITING"
P0_COMPLETENESS_SOURCE_ERROR = "SOURCE_ERROR"

# Legacy SSI HOSE heatmap scope (retired as preferred path; kept for provenance clarity).
P0_FOREIGN_SCOPE_DEFAULT = "HOSE"
# Universe turnover = sum(price * volume) over EMS board (research 142), not official exchange total.
P0_UNIVERSE_TURNOVER_SCOPE = "EMS_RESEARCH_UNIVERSE_142"
# Universe foreign flow = Σ EMS-membership-asof foreign VALUE (VND). NOT HOSE-wide / VNINDEX.
P0_UNIVERSE_FOREIGN_SCOPE = "EMS_RESEARCH_UNIVERSE_142"
# VNINDEX volume from index OHLCV provider (not VND market turnover).
P0_VNINDEX_VOLUME_SCOPE = "VNINDEX_INDEX_VOLUME"


# Outcome columns that must never enter T0 / historical core / MDRR feature bodies.
FORBIDDEN_OUTCOME_COLUMNS = (
    "t1_return",
    "t3_return",
    "t5_return",
    "t10_return",
    "t1_win",
    "t3_win",
    "t5_win",
    "t10_win",
    "xs_mean_return",
    "mfe",
    "mae",
    "label_up",
    "label_strong_up",
    "label_down",
    "vni_return",
)
