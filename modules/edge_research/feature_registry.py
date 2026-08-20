"""
Searchable-feature registry foundation for Edge Research.

PATCH 1: metadata only — temporal features are constructed but not yet
eligible for Discovery search until a future patch enables them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Mapping, Optional, Sequence, Tuple


class FeatureKind(str, Enum):
    NUMERIC_LEVEL = "numeric_level"
    NUMERIC_LAG = "numeric_lag"
    NUMERIC_DELTA = "numeric_delta"
    NUMERIC_SLOPE = "numeric_slope"
    NUMERIC_ACCEL = "numeric_accel"
    CATEGORICAL_LEVEL = "categorical_level"
    CATEGORICAL_PRIOR = "categorical_prior"
    CATEGORICAL_TRANSITION = "categorical_transition"
    RANK_LEVEL = "rank_level"
    RANK_LAG = "rank_lag"
    RANK_DELTA = "rank_delta"


# Legitimate T0 stock measurements sourced from pattern_lifecycle.csv.
# Measurements only — no directional investment meaning attached.
STOCK_NUMERIC_LEVEL_FEATURES: Tuple[str, ...] = (
    "rs5",
    "rs10",
    "rsi14",
    "rs_spread",
    "close",
    "rsi_slope",
    "volume_ratio20",
    "health_score",
)

STOCK_CATEGORICAL_LEVEL_FEATURES: Tuple[str, ...] = (
    "health_group",
    "obv_status",
)

# Cross-sectional ranks persisted at T0 (same trade_date snapshot semantics).
STOCK_RANK_LEVEL_FEATURES: Tuple[str, ...] = (
    "health_rank",
    "group_rank",
)

CANONICAL_STOCK_HISTORY_SOURCE = "pattern_lifecycle.csv"

# PATCH 1: existing Discovery search features remain the only search-eligible set.
LEGACY_SEARCH_FEATURES: FrozenSet[str] = frozenset({"rs10", "rsi14", "rs5", "rs_spread"})

# Columns that must never enter T0 feature construction (outcome / forward leakage).
PROHIBITED_FEATURE_COLUMN_EXACT: FrozenSet[str] = frozenset(
    {
        "t1_return",
        "t2_return",
        "t3_return",
        "t5_return",
        "t10_return",
        "t3_return_pct",
        "t5_return_pct",
        "t10_return_pct",
        "t3_target_date",
        "t5_target_date",
        "t10_target_date",
        "t3_target_price",
        "t5_target_price",
        "t10_target_price",
        "t3_max_gain_pct",
        "t5_max_gain_pct",
        "t10_max_gain_pct",
        "t3_max_drawdown_pct",
        "t5_max_drawdown_pct",
        "t10_max_drawdown_pct",
        "t3_is_win",
        "t5_is_win",
        "t10_is_win",
        "t3_is_leader",
        "t5_is_leader",
        "t10_is_leader",
        "t3_to_t5_delta_pct",
        "t5_to_t10_delta_pct",
        "t3_to_t10_delta_pct",
        "persistent_win_t5",
        "persistent_win_t10",
        "flash_winner",
        "slow_burner",
        "gain_accelerating",
        "lifecycle_class",
        "completed_horizons",
        "outcome_source",
        "outcome_missing_reason",
    }
)

PROHIBITED_FEATURE_COLUMN_PREFIXES: Tuple[str, ...] = (
    "t1_",
    "t2_",
    "forward_",
    "future_",
    "target_",
    "realized_",
)

PROHIBITED_FEATURE_COLUMN_SUBSTRINGS: Tuple[str, ...] = (
    "_return",
    "_outcome",
    "_future",
    "_forward",
)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    kind: FeatureKind
    source_column: str
    temporal: bool
    search_eligible: bool
    t0_safe: bool = True
    description: str = ""


def is_prohibited_feature_column(name: str) -> bool:
    normalized = str(name).strip().lower()
    if not normalized:
        return True
    if normalized in PROHIBITED_FEATURE_COLUMN_EXACT:
        return True
    for prefix in PROHIBITED_FEATURE_COLUMN_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for substring in PROHIBITED_FEATURE_COLUMN_SUBSTRINGS:
        if substring in normalized:
            return True
    return False


def validate_feature_columns(columns: Sequence[str]) -> None:
    """Reject prohibited outcome/forward columns from a proposed feature column list."""
    prohibited = [col for col in columns if is_prohibited_feature_column(col)]
    if prohibited:
        raise ValueError(
            "Prohibited outcome/forward columns in feature set: "
            + ", ".join(sorted(prohibited))
        )


def validate_feature_source_columns(columns: Mapping[str, object]) -> None:
    """Backward-compatible alias — validates an explicit column name iterable."""
    validate_feature_columns(list(columns))


class FeatureRegistry:
    """In-memory registry populated by the T0 feature matrix builder."""

    def __init__(self) -> None:
        self._specs: Dict[str, FeatureSpec] = {}

    def register(self, spec: FeatureSpec) -> None:
        if is_prohibited_feature_column(spec.name):
            raise ValueError(f"Cannot register prohibited feature: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> Optional[FeatureSpec]:
        return self._specs.get(name)

    def all_specs(self) -> Tuple[FeatureSpec, ...]:
        return tuple(self._specs[name] for name in sorted(self._specs))

    def search_eligible_names(self) -> Tuple[str, ...]:
        return tuple(
            spec.name for spec in self.all_specs() if spec.search_eligible
        )

    def to_dict(self) -> Dict[str, Dict[str, object]]:
        return {
            spec.name: {
                "kind": spec.kind.value,
                "source_column": spec.source_column,
                "temporal": spec.temporal,
                "search_eligible": spec.search_eligible,
                "t0_safe": spec.t0_safe,
                "description": spec.description,
            }
            for spec in self.all_specs()
        }
