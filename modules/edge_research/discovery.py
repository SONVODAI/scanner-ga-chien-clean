"""
Controlled conditional edge discovery for Edge Research (Phase 2).

Stops at CANDIDATE — no OOS, anti-edge, or production coupling.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.baseline import BaselineResult, compute_baseline_profiles
from modules.edge_research.contracts import (
    BASELINE_MIN_N,
    CANDIDATE_MIN_N,
    CANDIDATE_STATUS_CANDIDATE,
    CANDIDATE_STATUS_INSUFFICIENT_SAMPLE,
    DISCOVERY_CONFIG_VERSION,
    ENGINE_VERSION,
    FEATURE_BUCKETS,
    SEARCH_FEATURES,
)
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
    has_positive_incremental_evidence,
    select_best_horizon,
)
from modules.edge_research.statistical_guardrails import (
    HorizonTestResult,
    HypothesisTestRecord,
    apply_multiple_testing_correction,
    compute_concentration_diagnostics,
    compute_correlation_diagnostics,
    compute_episode_validation,
    compute_search_cardinality,
    disjoint_baseline_returns,
    no_edge_outcome_reason,
    screening_statistics_semantics,
    summarize_guardrail_accounting,
    welch_one_sided_pvalue,
)
from modules.edge_research.episodes import segment_market_episodes

FEATURE_LABELS = {
    "rs5": "RS5",
    "rs10": "RS10",
    "rsi14": "RSI14",
    "rs_spread": "RS_SPREAD",
}


@dataclass(frozen=True)
class ConditionClause:
    feature: str
    operator: str
    threshold_lo: Optional[float]
    threshold_hi: Optional[float]
    bucket_id: str

    def matches(self, row: pd.Series) -> bool:
        val = pd.to_numeric(row.get(self.feature), errors="coerce")
        if pd.isna(val):
            return False
        v = float(val)
        if self.operator == "<=":
            return self.threshold_hi is not None and v <= self.threshold_hi
        if self.operator == ">":
            return self.threshold_lo is not None and v > self.threshold_lo
        if self.operator == "range":
            lo = self.threshold_lo if self.threshold_lo is not None else float("-inf")
            hi = self.threshold_hi if self.threshold_hi is not None else float("inf")
            return lo < v <= hi
        return False

    def to_text(self) -> str:
        label = FEATURE_LABELS.get(self.feature, self.feature.upper())
        if self.operator == "<=":
            return f"{label}<={self.threshold_hi:g}"
        if self.operator == ">":
            return f"{label}>{self.threshold_lo:g}"
        if self.threshold_lo is None:
            return f"{label}<={self.threshold_hi:g}"
        if self.threshold_hi is None:
            return f"{label}>{self.threshold_lo:g}"
        return f"{label}>{self.threshold_lo:g} & {label}<={self.threshold_hi:g}"


@dataclass
class DiscoveryCandidate:
    condition_key: str
    condition_text: str
    clauses: Tuple[ConditionClause, ...]
    market_state: str
    market_transition: str
    baseline_type: str
    candidate_n: int
    baseline_n: int
    best_horizon: str
    profiles: Dict[str, Any]
    incremental: Dict[str, Optional[float]]
    status: str
    discovery_start_date: str
    discovery_end_date: str
    guardrails: Dict[str, Any] = field(default_factory=dict)

    def ranking_tuple(self) -> Tuple:
        inc = self.incremental
        return (
            inc.get("incremental_median") or -999,
            inc.get("incremental_mean") or -999,
            inc.get("incremental_win_rate") or -999,
            -(inc.get("downside_delta_3") or 0),
            self.candidate_n,
        )


@dataclass
class DiscoveryRunResult:
    run_id: str
    timestamp: str
    research_version: str
    discovery_start_date: str
    discovery_end_date: str
    data_quality: Dict[str, Any]
    conditions_tested: int = 0
    rejected_insufficient_sample: int = 0
    rejected_no_incremental_edge: int = 0
    promoted_candidates: int = 0
    candidates: List[DiscoveryCandidate] = field(default_factory=list)
    market_contexts_analyzed: int = 0
    guardrail_accounting: Dict[str, Any] = field(default_factory=dict)
    search_cardinality: Dict[str, Any] = field(default_factory=dict)
    no_edge_outcome: Optional[str] = None
    hypothesis_tests: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "research_version": self.research_version,
            "discovery_start_date": self.discovery_start_date,
            "discovery_end_date": self.discovery_end_date,
            "data_quality": self.data_quality,
            "conditions_tested": self.conditions_tested,
            "rejected_insufficient_sample": self.rejected_insufficient_sample,
            "rejected_no_incremental_edge": self.rejected_no_incremental_edge,
            "promoted_candidates": self.promoted_candidates,
            "market_contexts_analyzed": self.market_contexts_analyzed,
            "guardrail_accounting": self.guardrail_accounting,
            "search_cardinality": self.search_cardinality,
            "no_edge_outcome": self.no_edge_outcome,
            "hypothesis_tests": self.hypothesis_tests,
            "candidates": [
                {
                    "condition_key": c.condition_key,
                    "condition_text": c.condition_text,
                    "market_state": c.market_state,
                    "market_transition": c.market_transition,
                    "baseline_type": c.baseline_type,
                    "candidate_n": c.candidate_n,
                    "baseline_n": c.baseline_n,
                    "best_horizon": c.best_horizon,
                    "profiles": c.profiles,
                    "incremental": c.incremental,
                    "status": c.status,
                    "discovery_start_date": c.discovery_start_date,
                    "discovery_end_date": c.discovery_end_date,
                    "guardrails": c.guardrails,
                }
                for c in self.candidates
            ],
        }


def build_clauses_for_feature(feature: str) -> List[ConditionClause]:
    clauses: List[ConditionClause] = []
    for bucket_id, lo, hi, op in FEATURE_BUCKETS[feature]:
        clauses.append(
            ConditionClause(
                feature=feature,
                operator=op,
                threshold_lo=lo,
                threshold_hi=hi,
                bucket_id=bucket_id,
            )
        )
    return clauses


def canonical_condition_key(clauses: Sequence[ConditionClause]) -> str:
    ordered = sorted(clauses, key=lambda c: (c.feature, c.bucket_id))
    parts = [f"{c.feature}:{c.bucket_id}" for c in ordered]
    return "|".join(parts)


def canonical_condition_text(clauses: Sequence[ConditionClause]) -> str:
    ordered = sorted(clauses, key=lambda c: c.feature)
    return " & ".join(c.to_text() for c in ordered)


def apply_condition(panel: pd.DataFrame, clauses: Sequence[ConditionClause]) -> pd.DataFrame:
    mask = pd.Series(True, index=panel.index)
    for clause in clauses:
        mask &= panel.apply(clause.matches, axis=1)
    return panel[mask]


def compute_data_quality(panel: pd.DataFrame) -> Dict[str, Any]:
    if panel.empty:
        return {
            "total_observations": 0,
            "eligible_observations": 0,
            "valid_market_state_count": 0,
            "unknown_market_state_count": 0,
            "valid_t3_count": 0,
            "valid_t5_count": 0,
            "valid_t10_count": 0,
            "distinct_states": 0,
            "distinct_transitions": 0,
            "market_contexts_with_baseline_n": 0,
            "date_range_start": None,
            "date_range_end": None,
        }

    valid_state = panel["research_market_state"] != "UNKNOWN"
    dates = pd.to_datetime(panel["trade_date"], errors="coerce").dropna()
    transitions = panel["research_market_transition"].dropna().unique()
    ctx_counts = panel.groupby("research_market_transition").size()
    return {
        "total_observations": int(len(panel)),
        "eligible_observations": int(valid_state.sum()),
        "valid_market_state_count": int(valid_state.sum()),
        "unknown_market_state_count": int((~valid_state).sum()),
        "valid_t3_count": int(panel["t3_return"].notna().sum()),
        "valid_t5_count": int(panel["t5_return"].notna().sum()),
        "valid_t10_count": int(panel["t10_return"].notna().sum()),
        "distinct_states": int(panel.loc[valid_state, "research_market_state"].nunique()),
        "distinct_transitions": int(
            panel.loc[valid_state, "research_market_transition"].nunique()
        ),
        "market_contexts_with_baseline_n": int((ctx_counts >= BASELINE_MIN_N).sum()),
        "date_range_start": str(dates.min().date()) if not dates.empty else None,
        "date_range_end": str(dates.max().date()) if not dates.empty else None,
    }


def _generate_condition_sets(
    max_features: int = 2,
    enable_three_feature: bool = False,
) -> List[Tuple[ConditionClause, ...]]:
    single_clauses: List[List[ConditionClause]] = [
        [c] for f in SEARCH_FEATURES for c in build_clauses_for_feature(f)
    ]
    results: List[Tuple[ConditionClause, ...]] = [tuple(c) for c in single_clauses]

    pairs: List[Tuple[ConditionClause, ...]] = []
    for f1, f2 in itertools.combinations(SEARCH_FEATURES, 2):
        for c1 in build_clauses_for_feature(f1):
            for c2 in build_clauses_for_feature(f2):
                pairs.append((c1, c2))
    results.extend(pairs)

    if enable_three_feature and max_features >= 3:
        for combo in itertools.combinations(SEARCH_FEATURES, 3):
            clause_lists = [build_clauses_for_feature(f) for f in combo]
            for prod in itertools.product(*clause_lists):
                results.append(tuple(prod))

    return results


def evaluate_condition_in_context(
    panel: pd.DataFrame,
    clauses: Sequence[ConditionClause],
    market_transition: str,
    market_state: str,
    discovery_start: str,
    discovery_end: str,
) -> Optional[DiscoveryCandidate]:
    context_panel = panel[panel["research_market_transition"] == market_transition]
    if context_panel.empty:
        context_panel = panel[panel["research_market_state"] == market_state]
    if context_panel.empty:
        return None

    baseline = compute_baseline_profiles(
        panel,
        market_transition=market_transition,
        market_state=market_state,
    )
    if not baseline.is_valid:
        return None

    candidate_rows = apply_condition(context_panel, clauses)
    candidate_n = len(candidate_rows)
    if candidate_n < CANDIDATE_MIN_N:
        return None

    candidate_profiles = {}
    baseline_profiles = {}
    for h in HORIZONS:
        col = RETURN_COLUMNS[h]
        matured = candidate_rows[candidate_rows[col].notna()]
        candidate_profiles[h] = compute_horizon_profile(matured[col], h)
        baseline_profiles[h] = baseline.profiles[h]

    best_h = select_best_horizon(candidate_profiles, baseline_profiles)
    if best_h is None:
        return None

    cp = candidate_profiles[best_h]
    bp = baseline_profiles[best_h]
    inc = compute_incremental_metrics(cp, bp)
    if not has_positive_incremental_evidence(inc):
        return None

    key = canonical_condition_key(clauses)
    text = canonical_condition_text(clauses)
    ctx_key = f"{market_transition}|{key}"
    return DiscoveryCandidate(
        condition_key=ctx_key,
        condition_text=text,
        clauses=tuple(clauses),
        market_state=market_state,
        market_transition=market_transition,
        baseline_type=baseline.baseline_type,
        candidate_n=candidate_n,
        baseline_n=baseline.sample_n,
        best_horizon=best_h,
        profiles={
            "candidate": cp.to_dict("candidate"),
            "baseline": bp.to_dict("baseline"),
        },
        incremental=inc,
        status=CANDIDATE_STATUS_CANDIDATE,
        discovery_start_date=discovery_start,
        discovery_end_date=discovery_end,
    )


def _baseline_pool_rows(
    panel: pd.DataFrame,
    market_transition: str,
    market_state: str,
) -> pd.DataFrame:
    ctx = panel[panel["research_market_transition"] == market_transition]
    if ctx.empty:
        ctx = panel[panel["research_market_state"] == market_state]
    return ctx


def _evaluate_hypothesis_record(
    panel: pd.DataFrame,
    clauses: Sequence[ConditionClause],
    market_transition: str,
    market_state: str,
    *,
    episodes: Sequence[Any],
    discovery_start: str,
    discovery_end: str,
) -> Tuple[HypothesisTestRecord, Optional[DiscoveryCandidate]]:
    key = f"{market_transition}|{canonical_condition_key(clauses)}"
    text = canonical_condition_text(clauses)
    record = HypothesisTestRecord(
        hypothesis_key=key,
        market_transition=str(market_transition),
        market_state=str(market_state),
        condition_text=text,
        condition_key=key,
    )

    context_panel = panel[panel["research_market_transition"] == market_transition]
    if context_panel.empty:
        context_panel = panel[panel["research_market_state"] == market_state]
    if context_panel.empty:
        record.reject_reason = "no_context_panel"
        return record, None

    baseline = compute_baseline_profiles(
        panel,
        market_transition=str(market_transition),
        market_state=str(market_state),
    )
    candidate_rows = apply_condition(context_panel, clauses)
    record.candidate_n = len(candidate_rows)
    record.baseline_n = baseline.sample_n if baseline.is_valid else 0

    if record.candidate_n < CANDIDATE_MIN_N or not baseline.is_valid:
        record.reject_reason = "insufficient_sample"
        return record, None

    record.eligible_after_basic_filters = True
    baseline_pool = _baseline_pool_rows(panel, str(market_transition), str(market_state))

    candidate_profiles = {}
    baseline_profiles = {}
    for h in HORIZONS:
        col = RETURN_COLUMNS[h]
        matured = candidate_rows[candidate_rows[col].notna()]
        candidate_profiles[h] = compute_horizon_profile(matured[col], h)
        baseline_profiles[h] = baseline.profiles[h]
        inc = compute_incremental_metrics(candidate_profiles[h], baseline_profiles[h])
        raw_signal = has_positive_incremental_evidence(inc)
        cand_rets = matured[col]
        base_rets = disjoint_baseline_returns(
            baseline_pool,
            candidate_rows,
            horizon_col=col,
        )
        p_val = welch_one_sided_pvalue(cand_rets, base_rets)
        record.horizon_results[h] = HorizonTestResult(
            horizon=h,
            candidate_n=int(candidate_profiles[h].n),
            incremental_median=inc.get("incremental_median"),
            incremental_mean=inc.get("incremental_mean"),
            raw_signal=raw_signal,
            raw_p_value=p_val,
        )

    best_h = select_best_horizon(candidate_profiles, baseline_profiles)
    record.best_horizon = best_h
    record.best_horizon_selected_after_outcomes = True
    if best_h is None:
        record.reject_reason = "no_incremental_edge"
        return record, None

    inc = compute_incremental_metrics(candidate_profiles[best_h], baseline_profiles[best_h])
    record.raw_signal = True
    if best_h in record.horizon_results:
        record.raw_p_value = record.horizon_results[best_h].raw_p_value

    concentration = compute_concentration_diagnostics(candidate_rows, horizon=best_h)
    record.concentration = concentration
    record.correlation_diagnostics = compute_correlation_diagnostics(candidate_rows)
    record.episode_validation = compute_episode_validation(
        candidate_rows,
        episodes,
        best_horizon=best_h,
    )

    fake_row = pd.Series(
        {
            "market_transition": market_transition,
            "market_state": market_state,
            "best_horizon": best_h,
        }
    )
    from modules.edge_research.robustness import test_neighborhood_stability

    record.neighborhood_stability = test_neighborhood_stability(
        panel, fake_row, clauses, best_h
    )

    cand = DiscoveryCandidate(
        condition_key=key,
        condition_text=text,
        clauses=tuple(clauses),
        market_state=str(market_state),
        market_transition=str(market_transition),
        baseline_type=baseline.baseline_type,
        candidate_n=record.candidate_n,
        baseline_n=record.baseline_n,
        best_horizon=best_h,
        profiles={
            "candidate": candidate_profiles[best_h].to_dict("candidate"),
            "baseline": baseline_profiles[best_h].to_dict("baseline"),
            "horizon_results": {
                h: {
                    "incremental_median": record.horizon_results[h].incremental_median,
                    "incremental_mean": record.horizon_results[h].incremental_mean,
                    "raw_signal": record.horizon_results[h].raw_signal,
                    "raw_p_value": record.horizon_results[h].raw_p_value,
                }
                for h in record.horizon_results
            },
        },
        incremental=inc,
        status=CANDIDATE_STATUS_CANDIDATE,
        discovery_start_date=discovery_start,
        discovery_end_date=discovery_end,
    )
    return record, cand


def run_discovery(
    panel: pd.DataFrame,
    *,
    enable_three_feature: bool = False,
    max_candidates: int = 20,
) -> DiscoveryRunResult:
    """Run controlled discovery search; returns ranked candidates."""
    run_id = hashlib.sha256(
        f"{datetime.now(timezone.utc).isoformat()}:{len(panel)}".encode()
    ).hexdigest()[:12]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dq = compute_data_quality(panel)
    start = dq.get("date_range_start") or ""
    end = dq.get("date_range_end") or ""

    result = DiscoveryRunResult(
        run_id=run_id,
        timestamp=ts,
        research_version=DISCOVERY_CONFIG_VERSION,
        discovery_start_date=start or "",
        discovery_end_date=end or "",
        data_quality=dq,
    )

    if panel.empty or dq.get("eligible_observations", 0) == 0:
        return result

    eligible = panel[panel["research_market_state"] != "UNKNOWN"].copy()
    contexts = (
        eligible[["research_market_transition", "research_market_state"]]
        .drop_duplicates()
        .values.tolist()
    )
    result.market_contexts_analyzed = len(contexts)
    result.search_cardinality = compute_search_cardinality(
        n_market_contexts=len(contexts),
        enable_three_feature=enable_three_feature,
    )

    condition_sets = _generate_condition_sets(enable_three_feature=enable_three_feature)
    seen_keys: set[str] = set()
    hypothesis_records: List[HypothesisTestRecord] = []
    raw_candidates: List[DiscoveryCandidate] = []
    episodes = segment_market_episodes(panel)

    for transition, state in contexts:
        for clauses in condition_sets:
            result.conditions_tested += 1
            key = f"{transition}|{canonical_condition_key(clauses)}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            record, cand = _evaluate_hypothesis_record(
                panel,
                clauses,
                str(transition),
                str(state),
                episodes=episodes,
                discovery_start=start,
                discovery_end=end,
            )
            hypothesis_records.append(record)

            if not record.eligible_after_basic_filters:
                if record.reject_reason == "insufficient_sample":
                    result.rejected_insufficient_sample += 1
                elif record.reject_reason == "no_incremental_edge":
                    result.rejected_no_incremental_edge += 1
                continue

            if cand is None:
                result.rejected_no_incremental_edge += 1
                continue

            raw_candidates.append(cand)

    apply_multiple_testing_correction(hypothesis_records)
    result.guardrail_accounting = summarize_guardrail_accounting(hypothesis_records)
    result.hypothesis_tests = [r.to_dict() for r in hypothesis_records]

    fdr_by_key = {r.hypothesis_key: r for r in hypothesis_records}
    survivors: List[DiscoveryCandidate] = []
    for cand in raw_candidates:
        rec = fdr_by_key.get(cand.condition_key)
        guard = {
            "raw_signal": rec.raw_signal if rec else False,
            "raw_p_value": rec.raw_p_value if rec else None,
            "raw_q_value": rec.raw_q_value if rec else None,
            "multiple_testing_survives": rec.multiple_testing_survives if rec else False,
            "concentration": rec.concentration if rec else {},
            "episode_validation": rec.episode_validation if rec else {},
            "neighborhood_stability": rec.neighborhood_stability if rec else {},
            "correlation_diagnostics": rec.correlation_diagnostics if rec else {},
            "horizons_tested": list(HORIZONS),
            "best_horizon_selected_after_outcomes": True,
            "screening_statistics": screening_statistics_semantics(),
        }
        cand.guardrails = guard
        if rec:
            rec.selected_as_candidate = rec.multiple_testing_survives
        if rec and rec.multiple_testing_survives:
            survivors.append(cand)

    survivors.sort(key=lambda c: c.ranking_tuple(), reverse=True)
    result.candidates = survivors[:max_candidates]
    result.promoted_candidates = len(result.candidates)
    result.no_edge_outcome = no_edge_outcome_reason(
        result.guardrail_accounting,
        raw_candidates=len(raw_candidates),
        fdr_candidates=len(survivors),
    )
    return result


def condition_hash(clauses: Sequence[ConditionClause]) -> str:
    return hashlib.sha256(canonical_condition_key(clauses).encode()).hexdigest()[:12]
