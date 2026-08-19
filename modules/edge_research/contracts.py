"""
Canonical contracts for Edge Research Engine V1 (Phase 0/1).

Research-only fields are NEVER written back to production stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

ENGINE_VERSION = "1.0.0-foundation"
MARKET_LEVEL_CONFIG_VERSION = "market_level_v1_provisional"
MARKET_STATE_CONFIG_VERSION = "market_state_v1_provisional"
SNAPSHOT_POLICY_VERSION = "canonical_market_t0_v1_latest_time"

# Provisional coarse buckets — NOT optimized from forward returns.
MARKET_LEVEL_V1_THRESHOLDS: Tuple[Tuple[str, float], ...] = (
    ("VERY_LOW", 1.0),
    ("LOW", 3.0),
    ("MID", 6.0),
    ("HIGH", float("inf")),
)

RESEARCH_MARKET_STATES: FrozenSet[str] = frozenset(
    {
        "STRESS",
        "EARLY_RECOVERY",
        "BROAD_RECOVERY",
        "MATURE",
        "ROLLOVER",
        "DETERIORATION",
        "UNKNOWN",
    }
)

# Future ledger schemas (header-only until Phase 2+).
EDGE_HYPOTHESIS_LEDGER_COLUMNS: Tuple[str, ...] = (
    "hypothesis_id",
    "created_at",
    "status",
    "market_state",
    "market_transition",
    "stock_condition",
    "horizon",
    "notes",
)

EDGE_EPISODE_REGISTRY_COLUMNS: Tuple[str, ...] = (
    "episode_id",
    "hypothesis_id",
    "t0_date",
    "market_state",
    "symbol_count",
    "status",
)

EDGE_VALIDATION_HISTORY_COLUMNS: Tuple[str, ...] = (
    "validation_id",
    "hypothesis_id",
    "validation_type",
    "result",
    "validated_at",
)

EDGE_MEMORY_COLUMNS: Tuple[str, ...] = (
    "edge_id",
    "hypothesis_id",
    "status",
    "confirmed_at",
    "decayed_at",
    "notes",
)

EDGE_FORWARD_LEDGER_COLUMNS: Tuple[str, ...] = (
    "ledger_id",
    "hypothesis_id",
    "t0_date",
    "symbol",
    "frozen_at",
    "outcome_status",
)

RESEARCH_OBSERVATION_COLUMNS: Tuple[str, ...] = (
    "trade_date",
    "symbol",
    # Market T0 (raw / canonical)
    "market_real",
    "market_forecast",
    "breadth_score",
    "market_snapshot_time",
    "market_snapshot_ambiguous",
    "market_snapshot_count",
    # Research-only market interpretation
    "research_market_level",
    "research_market_trajectory",
    "research_market_state",
    "research_market_transition",
    "mr_t0",
    "mr_t_minus_1",
    "mr_t_minus_2",
    "mr_t_minus_3",
    "delta_mr_1",
    "delta_mr_3",
    "breadth_t0",
    "delta_breadth_1",
    "delta_breadth_3",
    "pct_rs10_negative",
    "pct_rsi_le_40",
    "pct_rs5_positive",
    "median_rs5",
    "median_rs10",
    # Stock T0 features
    "close",
    "rs5",
    "rs10",
    "rsi14",
    "rs_spread",
    # Forward labels ONLY (trading-session semantics)
    "t3_return",
    "t5_return",
    "t10_return",
    "outcome_source",
    "outcome_missing_reason",
)

PRODUCTION_FORBIDDEN_IMPORTS: FrozenSet[str] = frozenset(
    {
        "apply_learning_experience",
        "build_pattern_match",
        "build_buy_elite_decision_engine",
        "build_final_decision",
    }
)


@dataclass(frozen=True)
class ResearchObservation:
    """Canonical T0 research row — features at T0 separated from forward labels."""

    trade_date: str
    symbol: str
    market_real: Optional[float] = None
    market_forecast: Optional[float] = None
    breadth_score: Optional[float] = None
    market_snapshot_time: Optional[str] = None
    market_snapshot_ambiguous: bool = False
    market_snapshot_count: int = 0
    research_market_level: str = "UNKNOWN"
    research_market_trajectory: str = "UNKNOWN"
    research_market_state: str = "UNKNOWN"
    research_market_transition: str = "UNKNOWN"
    mr_t0: Optional[float] = None
    mr_t_minus_1: Optional[float] = None
    mr_t_minus_2: Optional[float] = None
    mr_t_minus_3: Optional[float] = None
    delta_mr_1: Optional[float] = None
    delta_mr_3: Optional[float] = None
    breadth_t0: Optional[float] = None
    delta_breadth_1: Optional[float] = None
    delta_breadth_3: Optional[float] = None
    pct_rs10_negative: Optional[float] = None
    pct_rsi_le_40: Optional[float] = None
    pct_rs5_positive: Optional[float] = None
    median_rs5: Optional[float] = None
    median_rs10: Optional[float] = None
    close: Optional[float] = None
    rs5: Optional[float] = None
    rs10: Optional[float] = None
    rsi14: Optional[float] = None
    rs_spread: Optional[float] = None
    t3_return: Optional[float] = None
    t5_return: Optional[float] = None
    t10_return: Optional[float] = None
    outcome_source: str = "unavailable"
    outcome_missing_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {col: getattr(self, col) for col in RESEARCH_OBSERVATION_COLUMNS}

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "ResearchObservation":
        kwargs = {k: row.get(k) for k in RESEARCH_OBSERVATION_COLUMNS if k in row}
        return cls(**kwargs)  # type: ignore[arg-type]
