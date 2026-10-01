"""
Prospective OOS evaluator (Phase A).

Evaluates a FROZEN hypothesis only:
- strict post-cutoff trading-session embargo
- frozen best_horizon only (no reselection)
- same-context baseline encoded by the frozen claim
- leakage hard-fails the evaluation
- insufficient n / missing context → INCONCLUSIVE, never ACTIVE
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from modules.edge_research.contracts import (
    BASELINE_TYPE_INSUFFICIENT,
    BASELINE_TYPE_SAME_STATE,
    BASELINE_TYPE_SAME_TRANSITION,
    OOS_MODE_HOLDOUT_SPLIT,
    OOS_MODE_PROSPECTIVE_AFTER_FREEZE,
    OOS_STATUS_ABORTED_LEAKAGE,
    OOS_STATUS_FAIL,
    OOS_STATUS_INCONCLUSIVE,
    OOS_STATUS_PASS,
    OOS_STATUS_PENDING,
)
from modules.edge_research.discovery import ConditionClause, apply_condition
from modules.edge_research.episodes import segment_market_episodes, summarize_candidate_episodes
from modules.edge_research.hypothesis import FrozenHypothesisSpec, ScientificStatus
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
    has_positive_incremental_evidence,
    select_best_horizon,
)
from modules.edge_research.oos import (
    OOSLeakageError,
    assert_prospective_oos_panel,
    unique_trading_sessions,
)
from modules.edge_research.oos_policy import (
    OOS_BASELINE_MIN_N,
    OOS_CANDIDATE_MIN_N,
    OOS_EMBARGO_TRADING_SESSIONS,
    oos_policy_snapshot,
)
from modules.edge_research.storage import ensure_storage, read_ledger, resolve_data_dir


def clauses_from_frozen_spec(spec: FrozenHypothesisSpec) -> Sequence[ConditionClause]:
    clauses: List[ConditionClause] = []
    for raw in spec.feature_clauses:
        if not isinstance(raw, dict):
            continue
        feature = str(raw.get("feature", "")).strip()
        if not feature:
            continue
        clauses.append(
            ConditionClause(
                feature=feature,
                operator=str(raw.get("operator", "")),
                threshold_lo=raw.get("threshold_lo"),
                threshold_hi=raw.get("threshold_hi"),
                bucket_id=str(raw.get("bucket_id") or f"{feature}_frozen"),
            )
        )
    return tuple(clauses)


def compute_frozen_context_baseline(
    panel: pd.DataFrame,
    spec: FrozenHypothesisSpec,
    *,
    min_n: int = OOS_BASELINE_MIN_N,
):
    """
    Same-context baseline according to the frozen claim.

    SAME_TRANSITION stays SAME_TRANSITION; we do not silently fall back to
    SAME_STATE during OOS (that would test a different claim). Missing context
    or insufficient n is the caller's INCONCLUSIVE path.
    """
    from modules.edge_research.baseline import BaselineResult, _filter_context, _matured_mask
    from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS, compute_horizon_profile

    claimed = str(spec.baseline_type or BASELINE_TYPE_SAME_TRANSITION)
    profiles: Dict[str, Any] = {}

    if claimed == BASELINE_TYPE_SAME_TRANSITION:
        ctx = _filter_context(panel, transition=spec.market_transition)
        if len(ctx) < min_n:
            for h in HORIZONS:
                profiles[h] = compute_horizon_profile(pd.Series(dtype=float), h)
            return BaselineResult(
                baseline_type=BASELINE_TYPE_INSUFFICIENT,
                market_transition=spec.market_transition,
                market_state=spec.market_state,
                profiles=profiles,
                sample_n=int(len(ctx)),
            )
        for h in HORIZONS:
            col = RETURN_COLUMNS[h]
            matured = ctx[_matured_mask(ctx, col)] if col in ctx.columns else ctx.iloc[0:0]
            profiles[h] = compute_horizon_profile(matured[col] if not matured.empty else pd.Series(dtype=float), h)
        return BaselineResult(
            baseline_type=BASELINE_TYPE_SAME_TRANSITION,
            market_transition=spec.market_transition,
            market_state=spec.market_state,
            profiles=profiles,
            sample_n=int(len(ctx)),
        )

    ctx = _filter_context(panel, state=spec.market_state)
    if len(ctx) < min_n:
        for h in HORIZONS:
            profiles[h] = compute_horizon_profile(pd.Series(dtype=float), h)
        return BaselineResult(
            baseline_type=BASELINE_TYPE_INSUFFICIENT,
            market_transition=spec.market_transition,
            market_state=spec.market_state,
            profiles=profiles,
            sample_n=int(len(ctx)),
        )
    for h in HORIZONS:
        col = RETURN_COLUMNS[h]
        matured = ctx[_matured_mask(ctx, col)] if col in ctx.columns else ctx.iloc[0:0]
        profiles[h] = compute_horizon_profile(matured[col] if not matured.empty else pd.Series(dtype=float), h)
    return BaselineResult(
        baseline_type=BASELINE_TYPE_SAME_STATE,
        market_transition=spec.market_transition,
        market_state=spec.market_state,
        profiles=profiles,
        sample_n=int(len(ctx)),
    )


def _context_panel(panel: pd.DataFrame, spec: FrozenHypothesisSpec) -> pd.DataFrame:
    claimed = str(spec.baseline_type or BASELINE_TYPE_SAME_TRANSITION)
    if claimed == BASELINE_TYPE_SAME_STATE:
        if "research_market_state" not in panel.columns:
            return panel.iloc[0:0]
        return panel[panel["research_market_state"] == spec.market_state]
    if "research_market_transition" not in panel.columns:
        return panel.iloc[0:0]
    return panel[panel["research_market_transition"] == spec.market_transition]


@dataclass
class OOSEvaluation:
    hypothesis_id: str
    edge_id: str
    result: str
    reason: str
    evaluated_at: str
    spec_hash: str
    best_horizon: str
    oos_start: str = ""
    oos_end: str = ""
    candidate_n: int = 0
    baseline_n: int = 0
    candidate_mean: Optional[float] = None
    candidate_median: Optional[float] = None
    candidate_win_rate: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_median: Optional[float] = None
    baseline_win_rate: Optional[float] = None
    incremental_mean: Optional[float] = None
    incremental_median: Optional[float] = None
    incremental_win_rate: Optional[float] = None
    baseline_type: str = ""
    market_episode_count: int = 0
    concentration_json: str = ""
    threshold_policy_version: str = ""
    embargo_trading_sessions: int = OOS_EMBARGO_TRADING_SESSIONS
    data_cutoff_date: str = ""
    leakage_check: str = "PASS"
    policy: Dict[str, Any] = field(default_factory=dict)
    horizon_reselection_attempted: bool = False
    selected_horizon_if_allowed: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "edge_id": self.edge_id,
            "result": self.result,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at,
            "spec_hash": self.spec_hash,
            "best_horizon": self.best_horizon,
            "oos_start": self.oos_start,
            "oos_end": self.oos_end,
            "candidate_n": self.candidate_n,
            "baseline_n": self.baseline_n,
            "candidate_mean": self.candidate_mean,
            "candidate_median": self.candidate_median,
            "candidate_win_rate": self.candidate_win_rate,
            "baseline_mean": self.baseline_mean,
            "baseline_median": self.baseline_median,
            "baseline_win_rate": self.baseline_win_rate,
            "incremental_mean": self.incremental_mean,
            "incremental_median": self.incremental_median,
            "incremental_win_rate": self.incremental_win_rate,
            "baseline_type": self.baseline_type,
            "market_episode_count": self.market_episode_count,
            "concentration_json": self.concentration_json,
            "threshold_policy_version": self.threshold_policy_version,
            "embargo_trading_sessions": self.embargo_trading_sessions,
            "data_cutoff_date": self.data_cutoff_date,
            "leakage_check": self.leakage_check,
            "policy": self.policy,
            "horizon_reselection_attempted": self.horizon_reselection_attempted,
            "selected_horizon_if_allowed": self.selected_horizon_if_allowed,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_span(panel: pd.DataFrame) -> tuple[str, str]:
    if panel is None or panel.empty or "trade_date" not in panel.columns:
        return "", ""
    dates = pd.to_datetime(panel["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return "", ""
    return str(dates.min().date()), str(dates.max().date())


def evaluate_frozen_hypothesis_oos(
    spec: FrozenHypothesisSpec,
    panel: pd.DataFrame,
    *,
    policy: Optional[Dict[str, Any]] = None,
    evaluated_at: Optional[str] = None,
) -> OOSEvaluation:
    """
    Evaluate one frozen hypothesis on prospective unseen sessions.

    Never mutates spec. Never reselects best_horizon. Leakage raises OOSLeakageError.
    """
    policy = policy or oos_policy_snapshot()
    ts = evaluated_at or _iso_now()
    horizon = str(spec.best_horizon)
    if horizon not in HORIZONS:
        raise OOSLeakageError(f"Frozen best_horizon {horizon!r} is not a supported horizon")

    allow_holdout = spec.oos_mode == OOS_MODE_HOLDOUT_SPLIT and bool(spec.holdout_applied)
    oos_panel = assert_prospective_oos_panel(
        panel=panel,
        data_cutoff_date=spec.data_cutoff_date,
        embargo_trading_sessions=int(spec.embargo_trading_sessions or OOS_EMBARGO_TRADING_SESSIONS),
        oos_mode=spec.oos_mode or OOS_MODE_PROSPECTIVE_AFTER_FREEZE,
        allow_holdout=allow_holdout,
    )
    oos_start, oos_end = _date_span(oos_panel)

    base = OOSEvaluation(
        hypothesis_id=spec.hypothesis_id,
        edge_id=spec.edge_id,
        result=OOS_STATUS_INCONCLUSIVE,
        reason="",
        evaluated_at=ts,
        spec_hash=spec.spec_hash,
        best_horizon=horizon,
        oos_start=oos_start,
        oos_end=oos_end,
        threshold_policy_version=str(policy.get("threshold_policy_version", "")),
        embargo_trading_sessions=int(spec.embargo_trading_sessions or OOS_EMBARGO_TRADING_SESSIONS),
        data_cutoff_date=spec.data_cutoff_date,
        leakage_check="PASS",
        policy=policy,
        baseline_type=spec.baseline_type,
    )

    if oos_panel.empty:
        base.reason = "no_unseen_sessions_after_embargo"
        return base

    context = _context_panel(oos_panel, spec)
    if context.empty:
        base.reason = "oos_required_market_context_absent"
        return base

    clauses = clauses_from_frozen_spec(spec)
    if not clauses:
        base.reason = "frozen_spec_has_no_clauses"
        return base

    candidate_rows = apply_condition(context, clauses)
    col = RETURN_COLUMNS[horizon]
    matured = candidate_rows[candidate_rows[col].notna()] if not candidate_rows.empty and col in candidate_rows.columns else candidate_rows.iloc[0:0]
    base.candidate_n = int(len(matured))

    baseline = compute_frozen_context_baseline(oos_panel, spec, min_n=int(policy.get("oos_baseline_min_n", OOS_BASELINE_MIN_N)))
    base.baseline_n = int(baseline.sample_n)
    base.baseline_type = baseline.baseline_type

    cand_min = int(policy.get("oos_candidate_min_n", OOS_CANDIDATE_MIN_N))
    base_min = int(policy.get("oos_baseline_min_n", OOS_BASELINE_MIN_N))

    episodes = segment_market_episodes(oos_panel) if not oos_panel.empty else []
    if not candidate_rows.empty:
        ep_sum = summarize_candidate_episodes(candidate_rows, episodes, best_horizon=horizon)
        base.market_episode_count = int(ep_sum.get("observed_episodes") or 0)
        base.concentration_json = json.dumps(
            {
                "observed_episodes": ep_sum.get("observed_episodes"),
                "positive_episodes": ep_sum.get("positive_episodes"),
                "negative_episodes": ep_sum.get("negative_episodes"),
            },
            ensure_ascii=False,
        )

    # Horizon reselection is computed only as a diagnostic and NEVER used.
    if not candidate_rows.empty:
        cand_profiles = {}
        base_profiles = {}
        for h in HORIZONS:
            hcol = RETURN_COLUMNS[h]
            h_matured = candidate_rows[candidate_rows[hcol].notna()] if hcol in candidate_rows.columns else candidate_rows.iloc[0:0]
            cand_profiles[h] = compute_horizon_profile(h_matured[hcol] if not h_matured.empty else pd.Series(dtype=float), h)
            base_profiles[h] = baseline.profiles.get(h, compute_horizon_profile(pd.Series(dtype=float), h))
        would_select = select_best_horizon(cand_profiles, base_profiles)
        base.horizon_reselection_attempted = False
        base.selected_horizon_if_allowed = would_select

    if context.empty or base.baseline_type == BASELINE_TYPE_INSUFFICIENT or base.baseline_n < base_min:
        base.result = OOS_STATUS_INCONCLUSIVE
        base.reason = "oos_context_or_baseline_insufficient"
        return base

    if base.candidate_n < cand_min:
        base.result = OOS_STATUS_INCONCLUSIVE
        base.reason = "oos_candidate_n_insufficient"
        return base

    cp = compute_horizon_profile(matured[col], horizon)
    bp = baseline.profiles.get(horizon, compute_horizon_profile(pd.Series(dtype=float), horizon))
    inc = compute_incremental_metrics(cp, bp)
    base.candidate_mean = cp.mean_return
    base.candidate_median = cp.median_return
    base.candidate_win_rate = cp.win_rate_gt_0
    base.baseline_mean = bp.mean_return
    base.baseline_median = bp.median_return
    base.baseline_win_rate = bp.win_rate_gt_0
    base.incremental_mean = inc.get("incremental_mean")
    base.incremental_median = inc.get("incremental_median")
    base.incremental_win_rate = inc.get("incremental_win_rate")

    if has_positive_incremental_evidence(inc):
        base.result = OOS_STATUS_PASS
        base.reason = "positive_incremental_edge_vs_same_context_baseline"
        return base

    base.result = OOS_STATUS_FAIL
    base.reason = "adequate_sample_without_positive_incremental_evidence"
    return base


def append_validation_history(
    evaluation: OOSEvaluation,
    *,
    data_dir: Optional[Path] = None,
) -> str:
    """
    Append-only OOS audit row. Never mutates a previous result into a different past.
    Idempotent on (hypothesis_id, spec_hash, oos_start, oos_end, result, candidate_n, baseline_n).
    """
    root = ensure_storage(data_dir)
    history = read_ledger("edge_validation_history.csv", data_dir=root)
    seq = 1
    if not history.empty and "hypothesis_id" in history.columns:
        prior = history[history["hypothesis_id"].astype(str) == evaluation.hypothesis_id]
        seq = int(len(prior)) + 1

    fingerprint = {
        "hypothesis_id": evaluation.hypothesis_id,
        "spec_hash": evaluation.spec_hash,
        "oos_start": evaluation.oos_start,
        "oos_end": evaluation.oos_end,
        "result": evaluation.result,
        "candidate_n": evaluation.candidate_n,
        "baseline_n": evaluation.baseline_n,
        "incremental_median": evaluation.incremental_median,
    }
    validation_id = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    if not history.empty and "validation_id" in history.columns:
        if (history["validation_id"].astype(str) == validation_id).any():
            return validation_id

    row = {
        "validation_id": validation_id,
        "hypothesis_id": evaluation.hypothesis_id,
        "validation_type": "PROSPECTIVE_OOS",
        "result": evaluation.result,
        "validated_at": evaluation.evaluated_at,
        "edge_id": evaluation.edge_id,
        "evaluated_at": evaluation.evaluated_at,
        "evaluation_seq": seq,
        "oos_start": evaluation.oos_start,
        "oos_end": evaluation.oos_end,
        "candidate_n": evaluation.candidate_n,
        "baseline_n": evaluation.baseline_n,
        "candidate_mean": evaluation.candidate_mean,
        "candidate_median": evaluation.candidate_median,
        "candidate_win_rate": evaluation.candidate_win_rate,
        "baseline_mean": evaluation.baseline_mean,
        "baseline_median": evaluation.baseline_median,
        "baseline_win_rate": evaluation.baseline_win_rate,
        "incremental_mean": evaluation.incremental_mean,
        "incremental_median": evaluation.incremental_median,
        "incremental_win_rate": evaluation.incremental_win_rate,
        "best_horizon": evaluation.best_horizon,
        "baseline_type": evaluation.baseline_type,
        "market_episode_count": evaluation.market_episode_count,
        "concentration_json": evaluation.concentration_json,
        "threshold_policy_version": evaluation.threshold_policy_version,
        "frozen_spec_hash": evaluation.spec_hash,
        "embargo_trading_sessions": evaluation.embargo_trading_sessions,
        "data_cutoff_date": evaluation.data_cutoff_date,
        "leakage_check": evaluation.leakage_check,
        "reason": evaluation.reason,
    }
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history.to_csv(root / "edge_validation_history.csv", index=False)
    return validation_id


def _update_ledger_oos_status(edge_id: str, evaluation: OOSEvaluation, data_dir: Path) -> None:
    path = data_dir / "edge_hypothesis_ledger.csv"
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=data_dir)
    if ledger.empty:
        return
    mask = ledger["edge_id"].astype(str) == str(edge_id)
    if not mask.any() and "hypothesis_id" in ledger.columns:
        mask = ledger["hypothesis_id"].astype(str) == evaluation.hypothesis_id
    if not mask.any():
        return
    ledger.loc[mask, "oos_status"] = evaluation.result
    status_map = {
        OOS_STATUS_PASS: ScientificStatus.OOS_PASS.value,
        OOS_STATUS_FAIL: ScientificStatus.OOS_FAIL.value,
        OOS_STATUS_INCONCLUSIVE: ScientificStatus.OOS_INCONCLUSIVE.value,
        OOS_STATUS_PENDING: ScientificStatus.OOS_PENDING.value,
        OOS_STATUS_ABORTED_LEAKAGE: ScientificStatus.OOS_PENDING.value,
    }
    ledger.loc[mask, "scientific_status"] = status_map.get(evaluation.result, evaluation.result)
    ledger.to_csv(path, index=False)


def evaluate_all_frozen_oos(
    panel: pd.DataFrame,
    *,
    data_dir: Optional[Path] = None,
) -> List[OOSEvaluation]:
    """Evaluate every frozen spec that is pending or previously INCONCLUSIVE."""
    from modules.edge_research.freeze import load_all_frozen_specs

    root = ensure_storage(data_dir)
    specs = load_all_frozen_specs(root)
    evaluations: List[OOSEvaluation] = []
    for spec in specs:
        try:
            ev = evaluate_frozen_hypothesis_oos(spec, panel)
        except OOSLeakageError as exc:
            ev = OOSEvaluation(
                hypothesis_id=spec.hypothesis_id,
                edge_id=spec.edge_id,
                result=OOS_STATUS_ABORTED_LEAKAGE,
                reason=str(exc),
                evaluated_at=_iso_now(),
                spec_hash=spec.spec_hash,
                best_horizon=spec.best_horizon,
                leakage_check="FAIL",
                data_cutoff_date=spec.data_cutoff_date,
                policy=oos_policy_snapshot(),
                threshold_policy_version=oos_policy_snapshot()["threshold_policy_version"],
            )
        append_validation_history(ev, data_dir=root)
        if ev.result != OOS_STATUS_ABORTED_LEAKAGE:
            _update_ledger_oos_status(spec.edge_id, ev, root)
        evaluations.append(ev)
    return evaluations
