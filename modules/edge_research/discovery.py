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

    condition_sets = _generate_condition_sets(enable_three_feature=enable_three_feature)
    seen_keys: set[str] = set()
    candidates: List[DiscoveryCandidate] = []

    for transition, state in contexts:
        for clauses in condition_sets:
            result.conditions_tested += 1
            key = f"{transition}|{canonical_condition_key(clauses)}"
            if key in seen_keys:
                continue

            context_panel = eligible[eligible["research_market_transition"] == transition]
            candidate_rows = apply_condition(context_panel, clauses)
            baseline = compute_baseline_profiles(
                panel,
                market_transition=str(transition),
                market_state=str(state),
            )

            if len(candidate_rows) < CANDIDATE_MIN_N:
                result.rejected_insufficient_sample += 1
                continue
            if not baseline.is_valid:
                result.rejected_insufficient_sample += 1
                continue

            cand = evaluate_condition_in_context(
                panel,
                clauses,
                str(transition),
                str(state),
                start,
                end,
            )
            if cand is None:
                result.rejected_no_incremental_edge += 1
                continue

            seen_keys.add(key)
            candidates.append(cand)

    candidates.sort(key=lambda c: c.ranking_tuple(), reverse=True)
    result.candidates = candidates[:max_candidates]
    result.promoted_candidates = len(result.candidates)
    return result


def condition_hash(clauses: Sequence[ConditionClause]) -> str:
    return hashlib.sha256(canonical_condition_key(clauses).encode()).hexdigest()[:12]
