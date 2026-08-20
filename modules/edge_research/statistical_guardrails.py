"""
Scientific search guardrails for Edge Research (PATCH 2A).

Multiple-testing screening, concentration diagnostics, and hypothesis accounting.
Adds validation capability — not investment rules.

IMPORTANT: Welch/BH outputs are discovery-screening statistics only. They do NOT
constitute formal independent-sample inferential evidence under the actual
dependence structure (see screening_statistics_semantics()).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from modules.edge_research.contracts import (
    CANDIDATE_MIN_N,
    DATE_CONCENTRATION_SEVERE,
    GUARDRAILS_CONFIG_VERSION,
    SYMBOL_CONCENTRATION_SEVERE,
)
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
    has_positive_incremental_evidence,
)

# Conservative descriptive thresholds — NOT tuned to preserve existing candidates.
MIN_UNIQUE_DATES_FOR_STABILITY = 3
MIN_UNIQUE_SYMBOLS_FOR_STABILITY = 3
MIN_OBSERVED_EPISODES_FOR_REPLICATION = 2
EPISODE_CONSISTENCY_MIN_POSITIVE_SHARE = 0.5

# Documented semantics for Welch/BH — not formal inferential claims.
P_VALUE_INTERPRETATION = "SCREENING_ONLY_NOT_FORMAL_INFERENCE"
INDEPENDENCE_ASSUMPTION = "NOT_ASSUMED"
READY_FOR_OOS_MEANING = (
    "Survived current in-sample screening strongly enough to deserve frozen "
    "evaluation on unseen OOS data. RESEARCH ONLY — not a validated edge."
)


def screening_statistics_semantics() -> Dict[str, Any]:
    """
    Canonical metadata describing what Welch/BH outputs do and do NOT mean.

    Welch t-tests and BH-FDR are used as a conservative pragmatic screen against
    data-mining luck across many hypotheses. They are NOT treated as valid
    independent-sample p-values under cross-sectional, temporal, or overlapping-
    horizon dependence, nor as proof that an edge exists.
    """
    return {
        "p_value_interpretation": P_VALUE_INTERPRETATION,
        "independence_assumption": INDEPENDENCE_ASSUMPTION,
        "formal_inferential_validity": False,
        "multiple_testing_role": "DISCOVERY_SCREENING_GUARD",
        "fdr_survival_implies_validated_edge": False,
        "formal_edge_validation_requires_oos": True,
        "candidate_rows_subset_of_baseline_pool": True,
        "screening_baseline_is_disjoint_complement": True,
        "ready_for_oos_meaning": READY_FOR_OOS_MEANING,
        "known_dependence_sources": [
            "same_day_cross_sectional_observations",
            "repeated_symbols_across_nearby_t0_dates",
            "overlapping_t3_t5_t10_forward_windows",
            "candidate_subset_of_same_context_baseline_for_profiles",
        ],
        "note": (
            "Screening p-values compare candidate returns to a disjoint same-context "
            "non-candidate complement. Residual dependence remains; OOS is required."
        ),
    }


def disjoint_baseline_returns(
    baseline_pool: pd.DataFrame,
    candidate_rows: pd.DataFrame,
    *,
    horizon_col: str,
) -> pd.Series:
    """Matured forward returns for same-context rows outside the candidate set."""
    matured = baseline_pool[pd.to_numeric(baseline_pool[horizon_col], errors="coerce").notna()]
    if matured.empty:
        return pd.Series(dtype=float)
    if candidate_rows.empty:
        return pd.to_numeric(matured[horizon_col], errors="coerce").dropna()
    complement = matured.drop(index=candidate_rows.index, errors="ignore")
    return pd.to_numeric(complement[horizon_col], errors="coerce").dropna()


@dataclass
class HorizonTestResult:
    horizon: str
    candidate_n: int
    incremental_median: Optional[float]
    incremental_mean: Optional[float]
    raw_signal: bool
    raw_p_value: Optional[float]
    raw_q_value: Optional[float] = None
    multiple_testing_survives: bool = False


@dataclass
class HypothesisTestRecord:
    hypothesis_key: str
    market_transition: str
    market_state: str
    condition_text: str
    condition_key: str
    hypotheses_tested: bool = True
    eligible_after_basic_filters: bool = False
    reject_reason: str = ""
    candidate_n: int = 0
    baseline_n: int = 0
    horizons_tested: Tuple[str, ...] = field(default_factory=lambda: HORIZONS)
    horizon_results: Dict[str, HorizonTestResult] = field(default_factory=dict)
    best_horizon: Optional[str] = None
    best_horizon_selected_after_outcomes: bool = True
    raw_signal: bool = False
    raw_p_value: Optional[float] = None
    raw_q_value: Optional[float] = None
    multiple_testing_survives: bool = False
    selected_as_candidate: bool = False
    concentration: Dict[str, Any] = field(default_factory=dict)
    episode_validation: Dict[str, Any] = field(default_factory=dict)
    neighborhood_stability: Dict[str, Any] = field(default_factory=dict)
    correlation_diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_key": self.hypothesis_key,
            "market_transition": self.market_transition,
            "market_state": self.market_state,
            "condition_text": self.condition_text,
            "condition_key": self.condition_key,
            "hypotheses_tested": self.hypotheses_tested,
            "eligible_after_basic_filters": self.eligible_after_basic_filters,
            "reject_reason": self.reject_reason,
            "candidate_n": self.candidate_n,
            "baseline_n": self.baseline_n,
            "horizons_tested": list(self.horizons_tested),
            "horizon_results": {
                h: {
                    "horizon": r.horizon,
                    "candidate_n": r.candidate_n,
                    "incremental_median": r.incremental_median,
                    "incremental_mean": r.incremental_mean,
                    "raw_signal": r.raw_signal,
                    "raw_p_value": r.raw_p_value,
                    "raw_q_value": r.raw_q_value,
                    "multiple_testing_survives": r.multiple_testing_survives,
                }
                for h, r in self.horizon_results.items()
            },
            "best_horizon": self.best_horizon,
            "best_horizon_selected_after_outcomes": self.best_horizon_selected_after_outcomes,
            "raw_signal": self.raw_signal,
            "raw_p_value": self.raw_p_value,
            "raw_q_value": self.raw_q_value,
            "multiple_testing_survives": self.multiple_testing_survives,
            "selected_as_candidate": self.selected_as_candidate,
            "concentration": self.concentration,
            "episode_validation": self.episode_validation,
            "neighborhood_stability": self.neighborhood_stability,
            "correlation_diagnostics": self.correlation_diagnostics,
        }


def compute_search_cardinality(
    *,
    n_market_contexts: int,
    enable_three_feature: bool = False,
) -> Dict[str, int]:
    """Document hypothesis-search cardinality for audit."""
    from modules.edge_research.contracts import FEATURE_BUCKETS, SEARCH_FEATURES
    import itertools

    single = sum(len(FEATURE_BUCKETS[f]) for f in SEARCH_FEATURES)
    pairs = 0
    for f1, f2 in itertools.combinations(SEARCH_FEATURES, 2):
        pairs += len(FEATURE_BUCKETS[f1]) * len(FEATURE_BUCKETS[f2])
    triples = 0
    if enable_three_feature:
        for combo in itertools.combinations(SEARCH_FEATURES, 3):
            lists = [FEATURE_BUCKETS[f] for f in combo]
            prod = 1
            for lst in lists:
                prod *= len(lst)
            triples += prod
    templates_per_context = single + pairs + triples
    condition_tests = n_market_contexts * templates_per_context
    return {
        "searchable_features": len(SEARCH_FEATURES),
        "condition_templates_per_context": templates_per_context,
        "market_contexts": n_market_contexts,
        "hypotheses_tested_total_upper_bound": condition_tests,
        "horizon_multiplier": len(HORIZONS),
        "horizon_level_tests_upper_bound": condition_tests * len(HORIZONS),
    }


def welch_one_sided_pvalue(candidate_returns: pd.Series, baseline_returns: pd.Series) -> Optional[float]:
    """
    One-sided Welch t-test: candidate > baseline (screening statistic only).

    NOT a formal inferential p-value under dependent/correlated observations.
    Used with BH-FDR as a pragmatic multiple-comparison screen during Discovery.
    """
    c = pd.to_numeric(candidate_returns, errors="coerce").dropna()
    b = pd.to_numeric(baseline_returns, errors="coerce").dropna()
    if len(c) < 2 or len(b) < 2:
        return None
    try:
        result = stats.ttest_ind(c, b, equal_var=False, alternative="greater")
        p = float(result.pvalue)
        if math.isnan(p):
            return None
        return p
    except Exception:
        return None


def benjamini_hochberg(p_values: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    """Return adjusted q-values keyed by hypothesis id. Conservative BH-FDR."""
    if not p_values:
        return {}
    items = sorted(p_values, key=lambda x: x[1])
    m = len(items)
    q_map: Dict[str, float] = {}
    prev_q = 1.0
    for rank, (key, p) in enumerate(reversed(items), start=1):
        i = m - rank + 1
        q = min(prev_q, p * m / i)
        prev_q = q
        q_map[key] = q
    # Forward pass for monotonicity
    sorted_keys = [k for k, _ in items]
    running_min = 1.0
    for key in reversed(sorted_keys):
        running_min = min(running_min, q_map.get(key, 1.0))
        q_map[key] = running_min
    return q_map


def compute_concentration_diagnostics(
    candidate_rows: pd.DataFrame,
    *,
    horizon: str,
) -> Dict[str, Any]:
    """Descriptive concentration diagnostics — no favorable thresholds."""
    if candidate_rows.empty:
        return {
            "unique_t0_dates": 0,
            "unique_symbols": 0,
            "largest_date_share": None,
            "largest_symbol_share": None,
            "largest_date_positive_pnl_share": None,
            "leave_one_date_out_survives": None,
            "leave_one_symbol_out_survives": None,
            "leave_largest_winner_out_survives": None,
            "concentration_flags": [],
        }

    col = RETURN_COLUMNS.get(horizon, "t5_return")
    matured = candidate_rows[candidate_rows[col].notna()].copy()
    n = len(matured)
    flags: List[str] = []

    date_counts = matured.groupby("trade_date").size()
    symbol_counts = matured.groupby("symbol").size()
    unique_dates = int(date_counts.shape[0])
    unique_symbols = int(symbol_counts.shape[0])
    largest_date_share = float(date_counts.max() / n) if n else None
    largest_symbol_share = float(symbol_counts.max() / n) if n else None

    if largest_date_share is not None and largest_date_share >= DATE_CONCENTRATION_SEVERE:
        flags.append("DATE_CONCENTRATED")
    if largest_symbol_share is not None and largest_symbol_share >= SYMBOL_CONCENTRATION_SEVERE:
        flags.append("SYMBOL_CONCENTRATED")
    if unique_dates < MIN_UNIQUE_DATES_FOR_STABILITY:
        flags.append("LOW_DATE_DIVERSITY")
    if unique_symbols < MIN_UNIQUE_SYMBOLS_FOR_STABILITY:
        flags.append("LOW_SYMBOL_DIVERSITY")

    largest_date_positive_pnl_share = None
    rets = pd.to_numeric(matured[col], errors="coerce")
    positive_total = float(rets[rets > 0].sum()) if rets.notna().any() else 0.0
    if positive_total > 0 and not date_counts.empty:
        best_date = str(date_counts.idxmax())
        best_date_sum = float(
            pd.to_numeric(matured.loc[matured["trade_date"] == best_date, col], errors="coerce")
            .fillna(0)
            .clip(lower=0)
            .sum()
        )
        largest_date_positive_pnl_share = best_date_sum / positive_total

    leave_one_date_out_survives = None
    if unique_dates >= 2 and n >= CANDIDATE_MIN_N:
        medians = []
        for d in date_counts.index:
            subset = matured[matured["trade_date"] != d]
            if len(subset) >= CANDIDATE_MIN_N - 1:
                medians.append(float(pd.to_numeric(subset[col], errors="coerce").median()))
        if medians:
            leave_one_date_out_survives = all(m > 0 for m in medians)

    leave_one_symbol_out_survives = None
    if unique_symbols >= 2 and n >= CANDIDATE_MIN_N:
        medians = []
        for sym in symbol_counts.index:
            subset = matured[matured["symbol"] != sym]
            if len(subset) >= max(5, n - symbol_counts.max()):
                medians.append(float(pd.to_numeric(subset[col], errors="coerce").median()))
        if medians:
            leave_one_symbol_out_survives = all(m > 0 for m in medians)

    leave_largest_winner_out_survives = None
    if n >= 3:
        top_idx = rets.idxmax()
        if top_idx in matured.index:
            trimmed = matured.drop(index=top_idx)
            if len(trimmed) >= 2:
                leave_largest_winner_out_survives = float(pd.to_numeric(trimmed[col], errors="coerce").median()) > 0

    return {
        "unique_t0_dates": unique_dates,
        "unique_symbols": unique_symbols,
        "largest_date_share": largest_date_share,
        "largest_symbol_share": largest_symbol_share,
        "largest_date_positive_pnl_share": largest_date_positive_pnl_share,
        "leave_one_date_out_survives": leave_one_date_out_survives,
        "leave_one_symbol_out_survives": leave_one_symbol_out_survives,
        "leave_largest_winner_out_survives": leave_largest_winner_out_survives,
        "concentration_flags": flags,
    }


def compute_correlation_diagnostics(candidate_rows: pd.DataFrame) -> Dict[str, Any]:
    """Diagnostics for repeated/correlated observations — not independence claims."""
    if candidate_rows.empty:
        return {
            "same_day_cross_sectional_rows": 0,
            "max_symbol_repeat_count": 0,
            "mean_symbol_repeat_count": 0.0,
            "overlapping_forward_windows_likely": True,
            "independence_assumption": "NOT_ASSUMED",
        }

    sym_counts = candidate_rows.groupby("symbol").size()
    day_counts = candidate_rows.groupby("trade_date").size()
    return {
        "same_day_cross_sectional_rows": int((day_counts > 1).sum()),
        "max_symbol_repeat_count": int(sym_counts.max()),
        "mean_symbol_repeat_count": float(sym_counts.mean()),
        "overlapping_forward_windows_likely": True,
        "independence_assumption": "NOT_ASSUMED",
        "note": "T3/T5/T10 forward windows may overlap for nearby entry dates; "
        "same-day rows are cross-sectional, not independent confirmations.",
    }


def compute_episode_validation(
    candidate_rows: pd.DataFrame,
    episodes: Sequence[Any],
    *,
    best_horizon: str,
    baseline_median_by_episode: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Episode-aware validation using incremental median by episode where possible."""
    from modules.edge_research.episodes import assign_episodes_to_candidate_rows
    from modules.edge_research.metrics import RETURN_COLUMNS

    col = RETURN_COLUMNS.get(best_horizon, "t5_return")
    if candidate_rows.empty:
        return {
            "observed_episode_count": 0,
            "positive_episode_count": 0,
            "negative_episode_count": 0,
            "mixed_episode_count": 0,
            "episode_consistency": "INSUFFICIENT",
            "episode_incremental_details": [],
        }

    tagged = assign_episodes_to_candidate_rows(candidate_rows, episodes)
    episode_ids = [e for e in tagged["episode_id"].unique() if e != "UNKNOWN_EPISODE"]
    positive = negative = mixed = 0
    details: List[Dict[str, Any]] = []

    for eid in episode_ids:
        ep_rows = tagged[tagged["episode_id"] == eid]
        rets = pd.to_numeric(ep_rows[col], errors="coerce").dropna()
        if rets.empty:
            classification = "INSUFFICIENT"
        else:
            med = float(rets.median())
            baseline_med = (baseline_median_by_episode or {}).get(eid)
            if baseline_med is not None:
                inc = med - baseline_med
            else:
                inc = med
            if inc > 0.5:
                classification = "POSITIVE"
                positive += 1
            elif inc < -0.5:
                classification = "NEGATIVE"
                negative += 1
            else:
                classification = "MIXED"
                mixed += 1
        details.append(
            {
                "episode_id": eid,
                "observations": len(ep_rows),
                "classification": classification,
            }
        )

    observed = len(episode_ids)
    if observed < MIN_OBSERVED_EPISODES_FOR_REPLICATION:
        consistency = "INSUFFICIENT_EPISODES"
    elif positive >= 1 and negative == 0:
        consistency = "CONSISTENT_POSITIVE"
    elif positive == 0 and negative >= 1:
        consistency = "CONSISTENT_NEGATIVE"
    elif positive > 0 and negative > 0:
        pos_share = positive / max(observed, 1)
        consistency = (
            "REPLICATED"
            if pos_share >= EPISODE_CONSISTENCY_MIN_POSITIVE_SHARE
            else "INCONSISTENT"
        )
    else:
        consistency = "MIXED"

    return {
        "observed_episode_count": observed,
        "positive_episode_count": positive,
        "negative_episode_count": negative,
        "mixed_episode_count": mixed,
        "episode_consistency": consistency,
        "episode_incremental_details": details,
    }


def apply_multiple_testing_correction(
    records: Sequence[HypothesisTestRecord],
    *,
    fdr_alpha: float = 0.10,
) -> None:
    """
    Benjamini-Hochberg screening across horizon-level Welch statistics in the family.

    Mutates records in place; preserves raw screening p-values. BH q-values rank
    screening statistics for conservative discovery filtering — they do NOT establish
    FDR control under dependent observations and must not be read as edge validation.
    """
    p_entries: List[Tuple[str, float]] = []
    for rec in records:
        if not rec.eligible_after_basic_filters:
            continue
        for h, hr in rec.horizon_results.items():
            if hr.raw_p_value is not None:
                p_entries.append((f"{rec.hypothesis_key}|{h}", hr.raw_p_value))

    q_map = benjamini_hochberg(p_entries)

    for rec in records:
        if not rec.eligible_after_basic_filters:
            rec.multiple_testing_survives = False
            continue
        for h, hr in rec.horizon_results.items():
            key = f"{rec.hypothesis_key}|{h}"
            hr.raw_q_value = q_map.get(key)
            hr.multiple_testing_survives = (
                hr.raw_q_value is not None and hr.raw_q_value <= fdr_alpha and hr.raw_signal
            )
        if rec.best_horizon and rec.best_horizon in rec.horizon_results:
            best = rec.horizon_results[rec.best_horizon]
            rec.raw_q_value = best.raw_q_value
            rec.multiple_testing_survives = best.multiple_testing_survives
        else:
            rec.multiple_testing_survives = False


def summarize_guardrail_accounting(records: Sequence[HypothesisTestRecord]) -> Dict[str, Any]:
    tested = [r for r in records if r.hypotheses_tested]
    eligible = [r for r in tested if r.eligible_after_basic_filters]
    raw_signal = [r for r in eligible if r.raw_signal]
    fdr_survivors = [r for r in eligible if r.multiple_testing_survives]
    selected = [r for r in records if r.selected_as_candidate]
    return {
        "guardrails_config_version": GUARDRAILS_CONFIG_VERSION,
        "hypotheses_tested_total": len(tested),
        "hypotheses_eligible_after_basic_filters": len(eligible),
        "hypotheses_raw_signal": len(raw_signal),
        "hypotheses_multiple_testing_survivors": len(fdr_survivors),
        "hypotheses_selected_as_candidates": len(selected),
        "horizon_level_tests_with_pvalue": sum(
            1
            for r in eligible
            for hr in r.horizon_results.values()
            if hr.raw_p_value is not None
        ),
        "fdr_method": "benjamini_hochberg",
        "fdr_alpha": 0.10,
        "p_value_method": "welch_one_sided_ttest_disjoint_complement",
        **screening_statistics_semantics(),
    }


def evaluate_concentration_fragility(concentration: Dict[str, Any]) -> bool:
    """Return True if concentration diagnostics indicate fragility."""
    flags = concentration.get("concentration_flags") or []
    if flags:
        return True
    if concentration.get("leave_one_date_out_survives") is False:
        return True
    if concentration.get("leave_largest_winner_out_survives") is False:
        return True
    return False


def no_edge_outcome_reason(
    accounting: Dict[str, Any],
    *,
    raw_candidates: int,
    fdr_candidates: int,
) -> Optional[str]:
    if raw_candidates == 0:
        return "NO_EDGE_FOUND"
    if fdr_candidates == 0 and raw_candidates > 0:
        return "NO_EDGE_FOUND_AFTER_MULTIPLE_TESTING"
    return None
