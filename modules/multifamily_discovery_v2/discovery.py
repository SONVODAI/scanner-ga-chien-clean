"""
Family-scoped V2 discovery. Research-only. Does not persist production ledgers.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.baseline import compute_baseline_profiles
from modules.edge_research.episodes import segment_market_episodes
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
    disjoint_baseline_returns,
    no_edge_outcome_reason,
    screening_statistics_semantics,
    summarize_guardrail_accounting,
    welch_one_sided_pvalue,
)
from modules.multifamily_discovery_v2.clauses import (
    V2Clause,
    apply_clauses,
    canonical_condition_key,
    canonical_condition_text,
    clauses_for_feature,
)
from modules.multifamily_discovery_v2.contracts import (
    CANDIDATE_MIN_N,
    FDR_ALPHA,
    MAX_CANDIDATES_PER_EXPERIMENT,
    MAX_TEMPLATES_PER_EXPERIMENT,
    V2_ENGINE_VERSION,
)
from modules.multifamily_discovery_v2.registry import V2_REGISTRY, eligible_names_for_families


def generate_templates(
    feature_names: Sequence[str],
    *,
    control_family: str = "rs_rsi",
    include_control_pairs: bool = True,
    include_cross_family_pairs: bool = True,
    include_within_new_family_pairs: bool = False,
    enable_three_feature: bool = False,
) -> List[Tuple[V2Clause, ...]]:
    """
    Staged template generation.

    Control pairs stay RS×RS. New families add their singles and RS×family pairs.
    Within-new-family pairs and triples are off unless explicitly enabled.
    """
    features = list(feature_names)
    control = [f for f in features if V2_REGISTRY[f].family == control_family]
    extra = [f for f in features if V2_REGISTRY[f].family != control_family]

    templates: List[Tuple[V2Clause, ...]] = []
    for name in features:
        for clause in clauses_for_feature(name):
            templates.append((clause,))

    if include_control_pairs:
        for f1, f2 in itertools.combinations(control, 2):
            for c1 in clauses_for_feature(f1):
                for c2 in clauses_for_feature(f2):
                    templates.append((c1, c2))

    if include_cross_family_pairs:
        for cf in control:
            for nf in extra:
                for c1 in clauses_for_feature(cf):
                    for c2 in clauses_for_feature(nf):
                        templates.append((c1, c2))
                        if len(templates) > MAX_TEMPLATES_PER_EXPERIMENT:
                            raise RuntimeError(
                                f"Template cardinality exceeds budget "
                                f"{MAX_TEMPLATES_PER_EXPERIMENT}. Refusing to search."
                            )

    if include_within_new_family_pairs:
        for f1, f2 in itertools.combinations(extra, 2):
            for c1 in clauses_for_feature(f1):
                for c2 in clauses_for_feature(f2):
                    templates.append((c1, c2))
                    if len(templates) > MAX_TEMPLATES_PER_EXPERIMENT:
                        raise RuntimeError(
                            f"Template cardinality exceeds budget "
                            f"{MAX_TEMPLATES_PER_EXPERIMENT}. Refusing to search."
                        )

    if enable_three_feature:
        projected = len(templates)
        for combo in itertools.combinations(features, 3):
            prod = 1
            for f in combo:
                prod *= max(1, len(clauses_for_feature(f)))
            projected += prod
            if projected > MAX_TEMPLATES_PER_EXPERIMENT:
                raise RuntimeError(
                    f"Projected 3-feature cardinality {projected} exceeds budget "
                    f"{MAX_TEMPLATES_PER_EXPERIMENT}. Refusing to search."
                )
        for combo in itertools.combinations(features, 3):
            clause_lists = [clauses_for_feature(f) for f in combo]
            for prod in itertools.product(*clause_lists):
                templates.append(tuple(prod))

    if len(templates) > MAX_TEMPLATES_PER_EXPERIMENT:
        raise RuntimeError(
            f"Template cardinality {len(templates)} exceeds budget "
            f"{MAX_TEMPLATES_PER_EXPERIMENT}. Refusing to search."
        )
    return templates


@dataclass
class V2Candidate:
    condition_key: str
    condition_text: str
    clauses: Tuple[V2Clause, ...]
    families: Tuple[str, ...]
    market_state: str
    market_transition: str
    baseline_type: str
    candidate_n: int
    baseline_n: int
    best_horizon: str
    profiles: Dict[str, Any]
    incremental: Dict[str, Optional[float]]
    nested_rs_incremental: Optional[Dict[str, Optional[float]]]
    guardrails: Dict[str, Any] = field(default_factory=dict)

    def ranking_tuple(self) -> Tuple:
        inc = self.incremental
        return (
            inc.get("incremental_median") or -999,
            inc.get("incremental_mean") or -999,
            inc.get("incremental_win_rate") or -999,
            self.candidate_n,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_key": self.condition_key,
            "condition_text": self.condition_text,
            "clauses": [
                {
                    "feature": c.feature,
                    "family": c.family,
                    "datatype": c.datatype,
                    "operator": c.operator,
                    "bucket_id": c.bucket_id,
                    "threshold_lo": c.threshold_lo,
                    "threshold_hi": c.threshold_hi,
                    "category": c.category,
                    "boolean_value": c.boolean_value,
                }
                for c in self.clauses
            ],
            "families": list(self.families),
            "features": [c.feature for c in self.clauses],
            "market_state": self.market_state,
            "market_transition": self.market_transition,
            "baseline_type": self.baseline_type,
            "candidate_n": self.candidate_n,
            "baseline_n": self.baseline_n,
            "best_horizon": self.best_horizon,
            "profiles": self.profiles,
            "incremental": self.incremental,
            "nested_rs_incremental": self.nested_rs_incremental,
            "guardrails": self.guardrails,
        }


def _nested_rs_incremental(
    context_panel: pd.DataFrame,
    clauses: Sequence[V2Clause],
    best_horizon: str,
) -> Optional[Dict[str, Optional[float]]]:
    extra = [c for c in clauses if c.family != "rs_rsi"]
    rs_only = [c for c in clauses if c.family == "rs_rsi"]
    if not extra:
        return None
    if not rs_only:
        return None
    col = RETURN_COLUMNS[best_horizon]
    nested = apply_clauses(context_panel, rs_only)
    full = apply_clauses(context_panel, clauses)
    nested_rets = pd.to_numeric(nested[col], errors="coerce").dropna()
    full_rets = pd.to_numeric(full[col], errors="coerce").dropna()
    if len(nested_rets) < CANDIDATE_MIN_N or len(full_rets) < 2:
        return {
            "nested_rs_n": int(len(nested_rets)),
            "full_n": int(len(full_rets)),
            "incremental_median": None,
            "incremental_mean": None,
            "incremental_win_rate": None,
            "reason": "insufficient_nested_sample",
        }
    nested_prof = compute_horizon_profile(nested_rets, best_horizon)
    full_prof = compute_horizon_profile(full_rets, best_horizon)
    inc = compute_incremental_metrics(full_prof, nested_prof)
    inc["nested_rs_n"] = int(len(nested_rets))
    inc["full_n"] = int(len(full_rets))
    inc["nested_rs_text"] = canonical_condition_text(rs_only)
    return inc


def _evaluate_one(
    panel: pd.DataFrame,
    clauses: Sequence[V2Clause],
    market_transition: str,
    market_state: str,
    *,
    episodes: Sequence[Any],
) -> Tuple[HypothesisTestRecord, Optional[V2Candidate]]:
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
        panel, market_transition=str(market_transition), market_state=str(market_state)
    )
    candidate_rows = apply_clauses(context_panel, clauses)
    record.candidate_n = len(candidate_rows)
    record.baseline_n = baseline.sample_n if baseline.is_valid else 0
    if record.candidate_n < CANDIDATE_MIN_N or not baseline.is_valid:
        record.reject_reason = "insufficient_sample"
        return record, None

    record.eligible_after_basic_filters = True
    candidate_profiles = {}
    baseline_profiles = {}
    for h in HORIZONS:
        col = RETURN_COLUMNS[h]
        matured = candidate_rows[candidate_rows[col].notna()]
        candidate_profiles[h] = compute_horizon_profile(matured[col], h)
        baseline_profiles[h] = baseline.profiles[h]
        inc = compute_incremental_metrics(candidate_profiles[h], baseline_profiles[h])
        raw_signal = has_positive_incremental_evidence(inc)
        base_rets = disjoint_baseline_returns(context_panel, candidate_rows, horizon_col=col)
        p_val = welch_one_sided_pvalue(matured[col], base_rets)
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
    record.concentration = compute_concentration_diagnostics(candidate_rows, horizon=best_h)
    record.correlation_diagnostics = compute_correlation_diagnostics(candidate_rows)
    record.episode_validation = compute_episode_validation(
        candidate_rows, episodes, best_horizon=best_h
    )
    nested = _nested_rs_incremental(context_panel, clauses, best_h)
    families = tuple(sorted({c.family for c in clauses}))
    cand = V2Candidate(
        condition_key=key,
        condition_text=text,
        clauses=tuple(clauses),
        families=families,
        market_state=str(market_state),
        market_transition=str(market_transition),
        baseline_type=baseline.baseline_type,
        candidate_n=record.candidate_n,
        baseline_n=record.baseline_n,
        best_horizon=best_h,
        profiles={
            "candidate": candidate_profiles[best_h].to_dict("candidate"),
            "baseline": baseline_profiles[best_h].to_dict("baseline"),
        },
        incremental=inc,
        nested_rs_incremental=nested,
    )
    return record, cand


def run_v2_discovery(
    panel: pd.DataFrame,
    *,
    families: Sequence[str],
    experiment_id: str,
    demoted: Optional[Sequence[str]] = None,
    include_control_pairs: bool = True,
    include_cross_family_pairs: bool = True,
    include_within_new_family_pairs: bool = False,
    enable_three_feature: bool = False,
    max_candidates: int = MAX_CANDIDATES_PER_EXPERIMENT,
) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    eligible_panel = panel[panel.get("research_market_state", "UNKNOWN") != "UNKNOWN"].copy()
    if eligible_panel.empty:
        return {
            "experiment_id": experiment_id,
            "engine_version": V2_ENGINE_VERSION,
            "timestamp": ts,
            "families": list(families),
            "templates_generated": 0,
            "conditions_tested": 0,
            "candidates": [],
            "accounting": {},
        }

    features = eligible_names_for_families(families, demoted=demoted)
    templates = generate_templates(
        features,
        include_control_pairs=include_control_pairs,
        include_cross_family_pairs=include_cross_family_pairs,
        include_within_new_family_pairs=include_within_new_family_pairs,
        enable_three_feature=enable_three_feature,
    )
    contexts = (
        eligible_panel[["research_market_transition", "research_market_state"]]
        .drop_duplicates()
        .values.tolist()
    )
    episodes = segment_market_episodes(panel)
    hypothesis_records: List[HypothesisTestRecord] = []
    raw_candidates: List[V2Candidate] = []
    seen: set[str] = set()
    tested = 0
    rejected_insufficient = 0
    rejected_no_edge = 0

    for transition, state in contexts:
        for clauses in templates:
            tested += 1
            key = f"{transition}|{canonical_condition_key(clauses)}"
            if key in seen:
                continue
            seen.add(key)
            record, cand = _evaluate_one(
                panel, clauses, str(transition), str(state), episodes=episodes
            )
            hypothesis_records.append(record)
            if not record.eligible_after_basic_filters:
                if record.reject_reason == "insufficient_sample":
                    rejected_insufficient += 1
                else:
                    rejected_no_edge += 1
                continue
            if cand is None:
                rejected_no_edge += 1
                continue
            raw_candidates.append(cand)

    apply_multiple_testing_correction(hypothesis_records, fdr_alpha=FDR_ALPHA)
    fdr_by_key = {r.hypothesis_key: r for r in hypothesis_records}
    survivors: List[V2Candidate] = []
    for cand in raw_candidates:
        rec = fdr_by_key.get(cand.condition_key)
        guard = {
            "raw_signal": rec.raw_signal if rec else False,
            "raw_p_value": rec.raw_p_value if rec else None,
            "raw_q_value": rec.raw_q_value if rec else None,
            "multiple_testing_survives": rec.multiple_testing_survives if rec else False,
            "concentration": rec.concentration if rec else {},
            "episode_validation": rec.episode_validation if rec else {},
            "screening_statistics": screening_statistics_semantics(),
        }
        cand.guardrails = guard
        if rec and rec.multiple_testing_survives:
            rec.selected_as_candidate = True
            survivors.append(cand)

    survivors.sort(key=lambda c: c.ranking_tuple(), reverse=True)
    kept = survivors[:max_candidates]
    accounting = summarize_guardrail_accounting(hypothesis_records)
    return {
        "experiment_id": experiment_id,
        "engine_version": V2_ENGINE_VERSION,
        "timestamp": ts,
        "families": list(families),
        "features_enabled": list(features),
        "clauses_by_feature": {f: len(clauses_for_feature(f)) for f in features},
        "templates_generated": len(templates),
        "market_contexts": len(contexts),
        "conditions_tested": tested,
        "unique_hypotheses": len(seen),
        "rejected_insufficient_sample": rejected_insufficient,
        "rejected_no_incremental_edge": rejected_no_edge,
        "raw_signal_count": len(raw_candidates),
        "fdr_survivors": len(survivors),
        "promoted_candidates": len(kept),
        "enable_three_feature": enable_three_feature,
        "include_within_new_family_pairs": include_within_new_family_pairs,
        "guardrail_accounting": accounting,
        "no_edge_outcome": no_edge_outcome_reason(
            accounting, raw_candidates=len(raw_candidates), fdr_candidates=len(survivors)
        ),
        "candidates": [c.to_dict() for c in kept],
        "all_fdr_survivors": [c.to_dict() for c in survivors],
        "run_id": hashlib.sha256(f"{ts}:{experiment_id}:{len(templates)}".encode()).hexdigest()[:12],
    }
