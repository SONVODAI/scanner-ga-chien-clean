"""
Forecast V2 Phase FC-1 — research harness contract.

Research-only. No production Market First / trading coupling.
Does not redefine legacy market_forecast semantics.
"""

from __future__ import annotations

from typing import Dict, Final, Tuple

FC1_VERSION: Final = "forecast_v2_fc1_v1"
FC1_PIT_SCHEMA_VERSION: Final = "fc1_pit_features_v1"
FC1_LABEL_SCHEMA_VERSION: Final = "fc1_labels_v1"
FC1_WALKFORWARD_SCHEMA_VERSION: Final = "fc1_walkforward_v1"

HORIZONS: Final[Tuple[int, ...]] = (3, 5, 10)
EXPECTED_UNIVERSE_SIZE: Final = 142

# Research accumulation gates (not statistical guarantees).
GATE_T3_DATES: Final = 40
GATE_T5_DATES: Final = 30
GATE_T10_DATES: Final = 20
GATE_MIN_SWITCHES: Final = 8

# Binary research targets — fixed a priori (FC-0); do not retune on sample.
FAVORABLE_MEDIAN_THRESHOLD: Final = 0.0
BROAD_FAVORABLE_SHARE: Final = 0.55

# Walk-forward / baseline minimum train sizes.
MIN_TRAIN_UNCONDITIONAL: Final = 5
MIN_TRAIN_REGRESSION: Final = 8
MIN_SPEARMAN_N: Final = 8
MIN_CALIBRATION_N: Final = 20

PROVENANCE_PIT_SAFE: Final = "PIT_SAFE"
PROVENANCE_SAFE_RECONSTRUCTABLE: Final = "SAFE_RECONSTRUCTABLE"
PROVENANCE_EXCLUDED: Final = "EXCLUDED"

COMPLETENESS_COMPLETE: Final = "COMPLETE"
COMPLETENESS_PARTIAL: Final = "PARTIAL"
COMPLETENESS_INSUFFICIENT: Final = "INSUFFICIENT"

INSUFFICIENT_EVIDENCE: Final = "INSUFFICIENT_EVIDENCE"

# Forbidden outcome / lifecycle columns in T0 feature matrices.
# Prefer exact names + explicit prefixes to avoid false positives
# (e.g. vnindex_daily_return_pct is a legal PIT feature).
FORBIDDEN_FEATURE_EXACT: Final[Tuple[str, ...]] = (
    "lifecycle_class",
    "persistent_win",
    "flash_winner",
    "slow_burner",
    "gain_accelerating",
    "completed_horizons",
    "max_gain_pct",
    "max_drawdown_pct",
    "is_win",
    "is_leader",
    "target_price",
    "target_date",
    "return_pct",
    "xs_mean_return",
    "xs_median_return",
    "xs_positive_share",
    "xs_gt_3pct_share",
    "xs_gt_5pct_share",
    "xs_lt_minus3pct_share",
    "mfe",
    "mae",
    "universe_mfe",
    "universe_mae",
    "vni_return",
    "favorable_median",
    "broad_favorable",
    "label_up",
    "label_down",
    "label_strong_up",
    "label_recover_weak",
    "label_fail_strong",
)
FORBIDDEN_FEATURE_PREFIXES: Final[Tuple[str, ...]] = (
    "t3_",
    "t5_",
    "t10_",
    "xs_",
)
# Back-compat alias used by tests / docs.
FORBIDDEN_FEATURE_SUBSTRINGS: Final[Tuple[str, ...]] = FORBIDDEN_FEATURE_EXACT + FORBIDDEN_FEATURE_PREFIXES

GROUPS: Final[Tuple[str, ...]] = (
    "THEO DÕI",
    "TÍCH LŨY",
    "MUA EARLY",
    "PULL VỪA",
    "PULL ĐẸP",
    "MUA BREAK",
    "CP MẠNH",
    "GÀ TĂNG TỐC",
)

# Canonical FC-1 PIT feature registry: name -> provenance.
# SAFE_RECONSTRUCTABLE only when values are rebuilt from same-day board without future info
# and explicitly tagged (never silently mixed into PIT_SAFE evaluation sets).
FEATURE_REGISTRY: Final[Dict[str, str]] = {
    # Market state
    "market_real": PROVENANCE_PIT_SAFE,
    "market_live": PROVENANCE_PIT_SAFE,
    "market_forecast": PROVENANCE_PIT_SAFE,  # legacy FC as feature only
    "breadth_score": PROVENANCE_PIT_SAFE,
    "vnindex_daily_return_pct": PROVENANCE_PIT_SAFE,
    "market_regime": PROVENANCE_PIT_SAFE,
    # Universe composition shares
    "share_THEO_DOI": PROVENANCE_PIT_SAFE,
    "share_TICH_LUY": PROVENANCE_PIT_SAFE,
    "share_MUA_EARLY": PROVENANCE_PIT_SAFE,
    "share_PULL_VUA": PROVENANCE_PIT_SAFE,
    "share_PULL_DEP": PROVENANCE_PIT_SAFE,
    "share_MUA_BREAK": PROVENANCE_PIT_SAFE,
    "share_CP_MANH": PROVENANCE_PIT_SAFE,
    "share_GA_TANG_TOC": PROVENANCE_PIT_SAFE,
    # Cross-sectional technicals
    "rsi40_share": PROVENANCE_PIT_SAFE,
    "rsi50_share": PROVENANCE_PIT_SAFE,
    "rsi60_share": PROVENANCE_PIT_SAFE,
    "med_rsi14": PROVENANCE_PIT_SAFE,
    "obv_green_share": PROVENANCE_PIT_SAFE,
    "slope_pos_share": PROVENANCE_PIT_SAFE,
    "mean_rs5": PROVENANCE_PIT_SAFE,
    "mean_rs10": PROVENANCE_PIT_SAFE,
    "pos_rs5_share": PROVENANCE_PIT_SAFE,
    "pos_rs10_share": PROVENANCE_PIT_SAFE,
    "rs5_dispersion": PROVENANCE_PIT_SAFE,
    "near_low20_share": PROVENANCE_PIT_SAFE,
    "near_low60_share": PROVENANCE_PIT_SAFE,
    "near_high20_share": PROVENANCE_PIT_SAFE,
    "lead_conc_top10": PROVENANCE_PIT_SAFE,
    # Safe lagged frozen history (prior T0 rows only; runner fills with past-only rule)
    "market_real_lag1": PROVENANCE_PIT_SAFE,
    "market_forecast_lag1": PROVENANCE_PIT_SAFE,
    "rsi50_share_lag1": PROVENANCE_PIT_SAFE,
    "obv_green_share_lag1": PROVENANCE_PIT_SAFE,
}

PIT_SAFE_FEATURES: Final[Tuple[str, ...]] = tuple(
    k for k, v in FEATURE_REGISTRY.items() if v == PROVENANCE_PIT_SAFE
)

GROUP_SHARE_MAP: Final[Dict[str, str]] = {
    "THEO DÕI": "share_THEO_DOI",
    "TÍCH LŨY": "share_TICH_LUY",
    "MUA EARLY": "share_MUA_EARLY",
    "PULL VỪA": "share_PULL_VUA",
    "PULL ĐẸP": "share_PULL_DEP",
    "MUA BREAK": "share_MUA_BREAK",
    "CP MẠNH": "share_CP_MANH",
    "GÀ TĂNG TỐC": "share_GA_TANG_TOC",
}

DEFAULT_DATA_DIR_NAME: Final = "forecast_research"
FC1_SUBDIR: Final = "fc1"
