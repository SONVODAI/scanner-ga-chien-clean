"""
Isolated contracts for Multi-Family Discovery V2.

Production SEARCH_FEATURES / FEATURE_BUCKETS are imported only as the CONTROL
baseline. This module never writes production ledgers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, FrozenSet, Optional, Tuple

from modules.edge_research.contracts import (
    BASELINE_MIN_N as PRODUCTION_BASELINE_MIN_N,
    CANDIDATE_MIN_N as PRODUCTION_CANDIDATE_MIN_N,
    FEATURE_BUCKETS as PRODUCTION_FEATURE_BUCKETS,
    SEARCH_FEATURES as PRODUCTION_SEARCH_FEATURES,
)

V2_ENGINE_VERSION = "multifamily_discovery_v2.1.0"
V2_REGISTRY_VERSION = "v2_registry_predeclared_buckets_1"
V2_BUCKET_POLICY = (
    "Buckets are frozen before outcome evaluation. RS/RSI buckets copy production "
    "FEATURE_BUCKETS. Non-RS buckets are domain-neutral or copied from existing "
    "earning-learning DNA discretizations. No bucket is chosen to maximize T3/T5/T10."
)
V2_ARTIFACT_DIRNAME = "multifamily_discovery_v2"
REPO_ROOT = Path(__file__).resolve().parents[2]
V2_ARTIFACT_ROOT = REPO_ROOT / "data" / V2_ARTIFACT_DIRNAME

# Same sample guards as production — not retuned from V2 returns.
CANDIDATE_MIN_N = PRODUCTION_CANDIDATE_MIN_N
BASELINE_MIN_N = PRODUCTION_BASELINE_MIN_N
FDR_ALPHA = 0.10
MAX_CANDIDATES_PER_EXPERIMENT = 20
MAX_TEMPLATES_PER_EXPERIMENT = 400
DISCOVERY_FRACTION = 0.70
EMBARGO_TRADING_DAYS = 10

CONTROL_SEARCH_FEATURES: Tuple[str, ...] = tuple(PRODUCTION_SEARCH_FEATURES)
CONTROL_FEATURE_BUCKETS = PRODUCTION_FEATURE_BUCKETS

# Cardinality budget for Phase 5 interaction (not a giant Cartesian product).
INTERACTION_MAX_CROSS_FAMILY_PAIR_TEMPLATES = 120
INTERACTION_ENABLE_THREE_FEATURE = False

PRODUCTION_CODE_PATHS: Tuple[str, ...] = (
    "modules/edge_research/discovery.py",
    "modules/edge_research/challenger.py",
    "modules/edge_research/engine.py",
    "modules/edge_research/ui.py",
    "modules/edge_research/contracts.py",
    "modules/edge_research/adapters.py",
    "modules/earning_learning.py",
    "modules/learning_insight_candidates.py",
    "app.py",
)

PRODUCTION_DATA_GLOBS: Tuple[str, ...] = (
    "data/earning_learning/*.csv",
    "data/earning_learning/*.json",
    "data/edge_research/**",
)

OUTCOME_COLUMNS: FrozenSet[str] = frozenset(
    {
        "t1_return",
        "t2_return",
        "t3_return",
        "t5_return",
        "t10_return",
        "t3_return_pct",
        "t5_return_pct",
        "t10_return_pct",
        "t3_is_win",
        "t5_is_win",
        "t10_is_win",
        "t3_is_leader",
        "t5_is_leader",
        "t10_is_leader",
        "lifecycle_class",
        "flash_winner",
        "slow_burner",
        "gain_accelerating",
        "persistent_win_t5",
        "persistent_win_t10",
    }
)

# Predeclared non-RS buckets (NOT fit on forward returns).
# Volume DNA copy from earning_learning._add_pattern_columns.
VOLUME_RATIO20_BUCKETS: Tuple[Tuple[str, Optional[float], Optional[float], str], ...] = (
    ("vol_le_0.7", None, 0.7, "<="),
    ("vol_0.7_to_1.0", 0.7, 1.0, "range"),
    ("vol_1.0_to_1.2", 1.0, 1.2, "range"),
    ("vol_1.2_to_1.5", 1.2, 1.5, "range"),
    ("vol_gt_1.5", 1.5, None, ">"),
)

# Trend slope DNA copy from earning_learning._add_pattern_columns.
EMA9_MA20_SLOPE_BUCKETS: Tuple[Tuple[str, Optional[float], Optional[float], str], ...] = (
    ("slope_le_-0.2", None, -0.2, "<="),
    ("slope_-0.2_to_0", -0.2, 0.0, "range"),
    ("slope_0_to_0.2", 0.0, 0.2, "range"),
    ("slope_gt_0.2", 0.2, None, ">"),
)

# Domain-neutral distance-from-EMA bands (round numbers, frozen a priori).
DIST_FROM_EMA9_BUCKETS: Tuple[Tuple[str, Optional[float], Optional[float], str], ...] = (
    ("dist_ema9_le_-3", None, -3.0, "<="),
    ("dist_ema9_-3_to_0", -3.0, 0.0, "range"),
    ("dist_ema9_0_to_3", 0.0, 3.0, "range"),
    ("dist_ema9_gt_3", 3.0, None, ">"),
)

OBV_CATEGORIES: Tuple[str, ...] = ("POSITIVE", "NEGATIVE")
HEALTH_GROUP_CATEGORIES: Tuple[str, ...] = (
    "RECOVERING",
    "NEUTRAL",
    "WEAKENING",
    "WEAK",
    "VERY_WEAK",
)

FAMILY_VERDICTS: Tuple[str, ...] = (
    "PROMISING",
    "WEAK",
    "REDUNDANT",
    "INSUFFICIENT_DATA",
    "DEGENERATE",
    "REJECT",
)

NESTED_INCREMENTAL_REDUNDANT_EPS = 0.0  # percentage points vs nested RS-only subset
