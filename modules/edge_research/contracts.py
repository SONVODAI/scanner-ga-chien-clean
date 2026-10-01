"""
Canonical contracts for Edge Research Engine V1 (Phase 0/1).

Research-only fields are NEVER written back to production stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

ENGINE_VERSION = "5.0.0-future-recognition"
GUARDRAILS_CONFIG_VERSION = "guardrails_v1"
DISCOVERY_CONFIG_VERSION = "discovery_v1"
ROBUSTNESS_CONFIG_VERSION = "robustness_v1"
EPISODE_CONFIG_VERSION = "episode_v1"
FEATURE_BUCKET_CONFIG_VERSION = "feature_buckets_v1"
MARKET_LEVEL_CONFIG_VERSION = "market_level_v1_provisional"
MARKET_STATE_CONFIG_VERSION = "market_state_v1_provisional"
SNAPSHOT_POLICY_VERSION = "canonical_market_t0_v2_eod_preferred"
FROZEN_SPEC_SCHEMA_VERSION = "frozen_hypothesis_spec_v2"
OOS_POLICY_VERSION = "oos_policy_v1_conservative"

# Phase 2 sample guards — research defaults, NOT optimized from returns.
CANDIDATE_MIN_N = 20
BASELINE_MIN_N = 50

BASELINE_TYPE_SAME_TRANSITION = "SAME_TRANSITION"
BASELINE_TYPE_SAME_STATE = "SAME_STATE"
BASELINE_TYPE_INSUFFICIENT = "INSUFFICIENT"

CANDIDATE_STATUS_DISCOVERY = "DISCOVERY"
CANDIDATE_STATUS_CANDIDATE = "CANDIDATE"
CANDIDATE_STATUS_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

ROBUSTNESS_PASS = "PASS"
ROBUSTNESS_FRAGILE = "FRAGILE"
ROBUSTNESS_REJECT = "REJECT"

OOS_STATUS_NOT_TESTED = "NOT_TESTED"
OOS_STATUS_PENDING = "OOS_PENDING"
OOS_STATUS_PASS = "OOS_PASS"
OOS_STATUS_FAIL = "OOS_FAIL"
OOS_STATUS_INCONCLUSIVE = "OOS_INCONCLUSIVE"
OOS_STATUS_ABORTED_LEAKAGE = "EVALUATION_ABORTED_LEAKAGE"

FREEZE_ELIGIBLE = "ELIGIBLE"
FREEZE_HISTORICAL_ONLY = "HISTORICAL_ONLY"
FREEZE_NON_FREEZABLE = "NON_FREEZABLE"
FREEZE_FRAGILE = "FRAGILE_NOT_ELIGIBLE"
FREEZE_REJECT = "REJECT_NOT_ELIGIBLE"
FREEZE_CHALLENGER_PENDING = "CHALLENGER_PENDING"

OOS_MODE_HOLDOUT_SPLIT = "HOLDOUT_SPLIT"
OOS_MODE_PROSPECTIVE_AFTER_FREEZE = "PROSPECTIVE_AFTER_FREEZE"

EDGE_MEMORY_STATUS_ACTIVE = "ACTIVE"
EDGE_MEMORY_STATUS_INACTIVE = "INACTIVE"

FROZEN_SPECS_DIRNAME = "frozen_specs"
FUTURE_RECOGNITION_VERSION = "future_recognition_v1"

ASSESSMENT_QUALIFIED_MATCH_FOUND = "QUALIFIED_MATCH_FOUND"
ASSESSMENT_NO_QUALIFIED_MATCH = "NO_QUALIFIED_MATCH"
ASSESSMENT_UNABLE_TO_ASSESS = "UNABLE_TO_ASSESS"

CONTEXT_COMPATIBLE = "COMPATIBLE"
CONTEXT_INCOMPATIBLE = "INCOMPATIBLE"
CONTEXT_UNKNOWN = "UNKNOWN"

FORWARD_OUTCOME_PENDING = "PENDING"

REASON_NO_ACTIVE_EDGE_AVAILABLE = "NO_ACTIVE_EDGE_AVAILABLE"

# Fixed robustness thresholds — NOT optimized from returns.
DATE_CONCENTRATION_SEVERE = 0.50
SYMBOL_CONCENTRATION_SEVERE = 0.40
TOP_WINNER_PCT_5 = 0.05
TOP_WINNER_PCT_10 = 0.10
EPISODE_DATE_GAP_MAX = 7  # calendar days between trading dates in same episode

# Coarse feature buckets — NOT tuned from forward outcomes.
FEATURE_BUCKETS: Dict[str, Tuple[Tuple[str, Optional[float], Optional[float], str], ...]] = {
    "rs5": (
        ("rs5_le_-10", None, -10.0, "<="),
        ("rs5_-10_to_-5", -10.0, -5.0, "range"),
        ("rs5_-5_to_0", -5.0, 0.0, "range"),
        ("rs5_0_to_5", 0.0, 5.0, "range"),
        ("rs5_gt_5", 5.0, None, ">"),
    ),
    "rs10": (
        ("rs10_le_-10", None, -10.0, "<="),
        ("rs10_-10_to_-5", -10.0, -5.0, "range"),
        ("rs10_-5_to_0", -5.0, 0.0, "range"),
        ("rs10_0_to_5", 0.0, 5.0, "range"),
        ("rs10_gt_5", 5.0, None, ">"),
    ),
    "rsi14": (
        ("rsi14_le_30", None, 30.0, "<="),
        ("rsi14_30_to_40", 30.0, 40.0, "range"),
        ("rsi14_40_to_50", 40.0, 50.0, "range"),
        ("rsi14_50_to_60", 50.0, 60.0, "range"),
        ("rsi14_gt_60", 60.0, None, ">"),
    ),
    "rs_spread": (
        ("rs_spread_le_-5", None, -5.0, "<="),
        ("rs_spread_-5_to_0", -5.0, 0.0, "range"),
        ("rs_spread_0_to_5", 0.0, 5.0, "range"),
        ("rs_spread_gt_5", 5.0, None, ">"),
    ),
}

SEARCH_FEATURES: Tuple[str, ...] = ("rs10", "rsi14", "rs5", "rs_spread")

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

EDGE_HYPOTHESIS_LEDGER_COLUMNS: Tuple[str, ...] = (
    "edge_id",
    "created_at",
    "discovery_run_id",
    "research_version",
    "market_state",
    "market_transition",
    "baseline_type",
    "condition_text",
    "feature_1",
    "operator_1",
    "threshold_1",
    "feature_2",
    "operator_2",
    "threshold_2",
    "candidate_n",
    "baseline_n",
    "best_horizon",
    "candidate_mean",
    "baseline_mean",
    "incremental_mean",
    "candidate_median",
    "baseline_median",
    "incremental_median",
    "candidate_win_rate",
    "baseline_win_rate",
    "incremental_win_rate",
    "candidate_downside_3",
    "baseline_downside_3",
    "candidate_downside_5",
    "baseline_downside_5",
    "status",
    "discovery_start_date",
    "discovery_end_date",
    "oos_status",
    "notes",
    "robustness_status",
    "robustness_run_id",
    "observed_episodes",
    "positive_episodes",
    "negative_episodes",
    "mixed_episodes",
    "date_count",
    "unique_symbol_count",
    "fragility_flags",
    "rejection_reasons",
    "main_fragility_flag",
    # Phase A additive scientific lifecycle (backward-compatible)
    "condition_key",
    "feature_clauses_json",
    "scientific_status",
    "hypothesis_id",
    "frozen_spec_path",
    "frozen_spec_hash",
    "freeze_eligibility",
    "oos_mode",
    "challenger_run_id",
)

DISCOVERY_RUN_COLUMNS: Tuple[str, ...] = (
    "run_id",
    "timestamp",
    "research_version",
    "discovery_start_date",
    "discovery_end_date",
    "observation_count",
    "eligible_observation_count",
    "valid_market_state_count",
    "unknown_market_state_count",
    "valid_t3_count",
    "valid_t5_count",
    "valid_t10_count",
    "distinct_states",
    "distinct_transitions",
    "market_contexts_analyzed",
    "conditions_tested",
    "rejected_insufficient_sample",
    "rejected_no_incremental_edge",
    "promoted_candidates",
)

EDGE_EPISODE_REGISTRY_COLUMNS: Tuple[str, ...] = (
    "episode_id",
    "episode_version",
    "start_date",
    "end_date",
    "start_state",
    "end_state",
    "transition_sequence",
    "min_market_real",
    "max_market_real",
    "number_of_trading_dates",
    "candidate_edge_id",
    "candidate_observations_in_episode",
    "candidate_best_horizon",
    "candidate_incremental_median",
    "candidate_incremental_mean",
    "candidate_incremental_wr",
    "episode_result",
)

EDGE_ROBUSTNESS_HISTORY_COLUMNS: Tuple[str, ...] = (
    "run_id",
    "edge_id",
    "timestamp",
    "test_name",
    "test_version",
    "pre_n",
    "post_n",
    "pre_incremental_median",
    "post_incremental_median",
    "pre_incremental_mean",
    "post_incremental_mean",
    "pre_incremental_wr",
    "post_incremental_wr",
    "result",
    "reason",
)

CHALLENGER_RUN_COLUMNS: Tuple[str, ...] = (
    "run_id",
    "timestamp",
    "robustness_config_version",
    "episode_config_version",
    "discovery_run_id",
    "candidate_ledger_hash",
    "ledger_hash",
    "report_status",
    "superseded_by",
    "superseded_reason",
    "dataset_start",
    "dataset_end",
    "candidates_entering",
    "candidates_entered",
    "robustness_pass",
    "robustness_fragile",
    "robustness_reject",
    "episodes_segmented",
    "episodes_unknown",
)

EDGE_VALIDATION_HISTORY_COLUMNS: Tuple[str, ...] = (
    "validation_id",
    "hypothesis_id",
    "validation_type",
    "result",
    "validated_at",
    # Phase A additive OOS audit fields
    "edge_id",
    "evaluated_at",
    "evaluation_seq",
    "oos_start",
    "oos_end",
    "candidate_n",
    "baseline_n",
    "candidate_mean",
    "candidate_median",
    "candidate_win_rate",
    "baseline_mean",
    "baseline_median",
    "baseline_win_rate",
    "incremental_mean",
    "incremental_median",
    "incremental_win_rate",
    "best_horizon",
    "baseline_type",
    "market_episode_count",
    "concentration_json",
    "threshold_policy_version",
    "frozen_spec_hash",
    "embargo_trading_sessions",
    "data_cutoff_date",
    "leakage_check",
    "reason",
)

EDGE_MEMORY_COLUMNS: Tuple[str, ...] = (
    "edge_id",
    "hypothesis_id",
    "status",
    "confirmed_at",
    "decayed_at",
    "notes",
    # Phase A additive ACTIVE memory fields for future matcher (Phase B)
    "spec_path",
    "spec_hash",
    "market_state",
    "market_transition",
    "baseline_type",
    "feature_clauses_json",
    "condition_key",
    "condition_text",
    "best_horizon",
    "feature_bucket_config_version",
    "market_state_config_version",
    "activated_at",
    "oos_result",
    "oos_candidate_n",
    "oos_baseline_n",
    "oos_incremental_median",
    "oos_incremental_mean",
    "oos_incremental_win_rate",
    "oos_evaluated_at",
    "episode_count",
    "concentration_notes",
    "forward_matches",
    "forward_matured",
    "forward_hits",
)

EDGE_FORWARD_LEDGER_COLUMNS: Tuple[str, ...] = (
    "ledger_id",
    "hypothesis_id",
    "t0_date",
    "symbol",
    "frozen_at",
    "outcome_status",
    # Phase B additive birth fields
    "edge_id",
    "t0_trade_date",
    "born_at",
    "spec_path",
    "spec_hash",
    "spec_schema_version",
    "feature_bucket_config_version",
    "market_state_config_version",
    "market_state_t0",
    "market_transition_t0",
    "context_verdict",
    "context_reason",
    "stock_feature_values_json",
    "matched_clauses_json",
    "condition_key",
    "condition_text",
    "best_horizon",
    "active_status_at_birth",
    "oos_evidence_json",
    "universe_count",
    "universe_hash",
    "pit_artifact",
    "pit_artifact_hash",
    "assessment_run_id",
    "selection_reason",
    "selection_reason_vi",
    "research_label",
)

EDGE_SESSION_ASSESSMENT_COLUMNS: Tuple[str, ...] = (
    "trade_date",
    "run_id",
    "started_at",
    "completed_at",
    "assessment_state",
    "reason",
    "t0_source_status",
    "universe_count",
    "universe_hash",
    "active_edge_count",
    "edges_loaded_ok",
    "edges_uninterpretable",
    "edges_context_compatible",
    "edges_context_incompatible",
    "edges_context_unknown",
    "stock_edge_evaluations",
    "qualified_match_count",
    "new_birth_count",
    "duplicate_skip_count",
    "matcher_version",
    "spec_schema_version",
    "pit_artifact",
    "failure_detail",
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
