"""
Regime Alpha shadow audit with historical recall experience (N3 + N3.7).

Shadow-only — never modifies production ranking or admission.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.earning_learning import (
    _continuation_knowledge_lookup,
    _decision_rows_for_pattern_keys,
    _lookup_continuation_row,
    _lookup_pattern_row,
    _pattern_knowledge_lookup,
    _safe_float as _el_safe_float,
    get_continuation_knowledge,
    get_pattern_knowledge,
)
from modules.regime_alpha import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_FAMILY,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_NO_EVIDENCE,
    compute_pure_baseline_score,
    compute_recall_evidence,
    compute_shadow_final_score,
    compute_technical_prior,
    load_recall_index,
)

logger = logging.getLogger("regime_alpha_shadow")

MODULE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = MODULE_DIR / "brain"
SHADOW_SNAPSHOT_FILE = BRAIN_DIR / "ai_recommendation_shadow.csv"
SHADOW_COMPARISON_FILE = BRAIN_DIR / "regime_alpha_shadow_comparison.csv"

SHADOW_COLUMNS: Sequence[str] = (
    "session_date",
    "rank",
    "ProductionRank",
    "ShadowRank",
    "symbol",
    "recommendation",
    "leader_score",
    "market_context_key",
    "stock_pattern_key",
    "TechnicalPrior",
    "BaselineScore",
    "BaselineRank",
    "PureBaselineScore",
    "ShadowFinalScore",
    "ShadowExperienceScore",
    "ShadowExperienceRank",
    "PatternKnowledgeAdj",
    "ContinuationAdj",
    "HorizonAdj",
    "RecallComponent",
    "LearnedWinRate",
    "ContinuationScore",
    "ExperienceSamples",
    "MatchedPattern",
    "MatchedMarketContext",
    "ContextMatchMode",
    "ScoreDelta",
    "RankDelta",
    "ShadowMovement",
    "RecallSource",
    "RecallLevel",
    "RecallSamples",
    "RecallT3Samples",
    "RecallT5Samples",
    "RecallT10Samples",
    "RecallMeanT3",
    "RecallMeanT5",
    "RecallMeanT10",
    "RecallWinRateT3",
    "RecallWinRateT5",
    "RecallWinRateT10",
    "RecallConfidence",
    "RecallAlpha",
    "RecallMatchedDNA",
    "RecallMatchedContext",
    "ShadowReason",
    "updated_at",
)

_SHADOW_RANK_SORT_COLUMNS: Sequence[str] = (
    "ShadowFinalScore",
    "RecallConfidence",
    "BaselineScore",
    "leader_score",
    "symbol",
)


@dataclass(frozen=True)
class ShadowComparisonSummary:
    candidates: int = 0
    with_recall_evidence: int = 0
    exact_count: int = 0
    family_count: int = 0
    global_count: int = 0
    promoted: int = 0
    demoted: int = 0
    unchanged: int = 0
    top5_overlap: int = 0
    top10_overlap: int = 0
    avg_t3_promoted: Optional[float] = None
    avg_t3_demoted: Optional[float] = None


def _load_shadow_knowledge_lookups() -> Tuple[Dict, Dict]:
    try:
        pattern_df = get_pattern_knowledge(min_samples=1)
    except Exception:
        pattern_df = pd.DataFrame()
    try:
        continuation_df = get_continuation_knowledge(min_samples=1)
    except Exception:
        continuation_df = pd.DataFrame()
    return _pattern_knowledge_lookup(pattern_df), _continuation_knowledge_lookup(
        continuation_df
    )


def _shadow_knowledge_rows(
    stock_pattern_key: str,
    market_context_key: str,
    pattern_lookup: Mapping,
    continuation_lookup: Mapping,
) -> Tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]], str, str]:
    pattern_row, pattern_mode = _lookup_pattern_row(
        pattern_lookup,
        market_context_key,
        stock_pattern_key,
        preferred_horizon=5,
        fallback_horizon=10,
    )
    continuation_row, continuation_mode = _lookup_continuation_row(
        continuation_lookup,
        market_context_key,
        stock_pattern_key,
    )
    match_mode = pattern_mode or continuation_mode or ""
    matched_pattern = ""
    if pattern_row is not None:
        matched_pattern = str(pattern_row.get("pattern_key", ""))
    matched_context = market_context_key
    if pattern_row is not None and pattern_row.get("market_context_key"):
        matched_context = str(pattern_row.get("market_context_key"))
    elif continuation_row is not None and continuation_row.get("market_context_key"):
        matched_context = str(continuation_row.get("market_context_key"))
    return pattern_row, continuation_row, matched_pattern, match_mode


def _movement(baseline_rank: int, shadow_rank: int) -> str:
    if shadow_rank < baseline_rank:
        return "PROMOTED"
    if shadow_rank > baseline_rank:
        return "DEMOTED"
    return "UNCHANGED"


def _shadow_reason(
    recall_level: str,
    recall_confidence: float,
    score_delta: float,
    *,
    pattern_adj: float = 0.0,
    continuation_adj: float = 0.0,
    horizon_adj: float = 0.0,
) -> str:
    parts: list[str] = []
    if abs(pattern_adj) >= 0.5:
        parts.append(f"pattern {pattern_adj:+.1f}")
    if abs(continuation_adj) >= 0.5:
        parts.append(f"continuation {continuation_adj:+.1f}")
    if abs(horizon_adj) >= 0.5:
        parts.append(f"horizon {horizon_adj:+.1f}")
    if recall_level != RECALL_LEVEL_NO_EVIDENCE and recall_confidence > 0:
        if recall_level == RECALL_LEVEL_GLOBAL:
            parts.append("GLOBAL_DNA recall")
        elif recall_level == RECALL_LEVEL_FAMILY:
            parts.append("FAMILY recall")
        elif recall_level == RECALL_LEVEL_EXACT:
            parts.append("EXACT recall")

    if not parts:
        return "No strong learning evidence; shadow follows pure baseline."

    detail = ", ".join(parts)
    if abs(score_delta) <= 1.0:
        return f"Learning signals present ({detail}) but net score delta is minimal."
    direction = "raises" if score_delta > 0 else "lowers"
    return f"Shadow {direction} score by {abs(score_delta):.1f} via {detail}."


def _canonical_pattern_keys_for_shadow_row(
    symbol: str,
    brain_row: Mapping[str, Any],
    rec_row: Mapping[str, Any],
    exp_row: Mapping[str, Any],
    *,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
    breadth: Optional[Any] = None,
    brain_df: Optional[pd.DataFrame] = None,
) -> tuple[str, str]:
    """Derive stock/market DNA keys via the same canonical path as historical observations."""
    merged = {**dict(brain_row), **dict(rec_row), **dict(exp_row)}
    merged["symbol"] = symbol
    if "leader_score" not in exp_row:
        merged.pop("leader_score", None)
    frame = pd.DataFrame([merged])
    mr = _el_safe_float(market_real)
    mf = _el_safe_float(market_forecast)
    bw = _el_safe_float(breadth)
    keyed = _decision_rows_for_pattern_keys(
        frame,
        market_real=mr,
        market_forecast=mf,
        breadth=bw if np.isfinite(bw) else None,
        brain_df=brain_df,
    )
    if keyed.empty:
        return (
            str(exp_row.get("stock_pattern_key", "")),
            str(exp_row.get("market_context_key", "")),
        )
    row = keyed.iloc[0]
    return (
        str(row.get("stock_pattern_key", "")),
        str(row.get("market_context_key", "")),
    )


def _apply_shadow_experience_rerank(shadow_df: pd.DataFrame) -> pd.DataFrame:
    """Assign deterministic shadow ranks from ShadowFinalScore."""
    if shadow_df is None or shadow_df.empty:
        return shadow_df

    out = shadow_df.copy()
    if "ProductionRank" not in out.columns:
        out["ProductionRank"] = out.get("rank", pd.NA)
    out["ProductionRank"] = out["ProductionRank"].where(
        out["ProductionRank"].notna(),
        out.get("rank", pd.NA),
    )

    if "ShadowFinalScore" not in out.columns:
        out["ShadowFinalScore"] = out.get("ShadowExperienceScore", np.nan)
    if "ShadowExperienceScore" not in out.columns:
        out["ShadowExperienceScore"] = out["ShadowFinalScore"]
    else:
        out["ShadowExperienceScore"] = out["ShadowFinalScore"]

    if "PureBaselineScore" not in out.columns:
        out["PureBaselineScore"] = out.get("BaselineScore", np.nan)
    out["BaselineScore"] = out["PureBaselineScore"]

    out["BaselineRank"] = (
        pd.to_numeric(out["BaselineScore"], errors="coerce")
        .rank(method="first", ascending=False)
        .astype(int)
    )

    for col in _SHADOW_RANK_SORT_COLUMNS:
        if col == "symbol":
            out[col] = out[col].astype(str).str.strip().str.upper()
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.sort_values(
        by=list(_SHADOW_RANK_SORT_COLUMNS),
        ascending=[False, False, False, False, True],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    out["ShadowExperienceRank"] = range(1, len(out) + 1)
    out["ShadowRank"] = out["ShadowExperienceRank"]
    out["ScoreDelta"] = (
        pd.to_numeric(out["ShadowFinalScore"], errors="coerce")
        - pd.to_numeric(out["BaselineScore"], errors="coerce")
    ).round(4)
    out["RankDelta"] = out["BaselineRank"] - out["ShadowExperienceRank"]
    out["ShadowMovement"] = out.apply(
        lambda r: _movement(int(r["BaselineRank"]), int(r["ShadowExperienceRank"])),
        axis=1,
    )

    out = out.sort_values(
        ["ShadowExperienceRank", "symbol"],
        kind="stable",
    ).reset_index(drop=True)
    return out.reindex(columns=list(SHADOW_COLUMNS))


def build_shadow_candidate_universe(
    brain: pd.DataFrame,
    patterns: pd.DataFrame,
    production_rec: pd.DataFrame,
    *,
    max_candidates: int = 250,
) -> pd.DataFrame:
    """
    Shadow-only candidate pool: all actionable brain symbols, preferring production
    rec rows when present. Allows outsiders to enter Shadow Top 10.
    """
    from leader_memory import RECOMMENDATION_COLUMNS, _best_pattern, _clean_text, _normalize_symbol

    if brain is None or brain.empty:
        return production_rec.copy() if production_rec is not None else pd.DataFrame()

    prod_by_symbol: Dict[str, Mapping[str, Any]] = {}
    if production_rec is not None and not production_rec.empty:
        for _, row in production_rec.iterrows():
            sym = _normalize_symbol(row.get("symbol"))
            if sym:
                prod_by_symbol[sym] = dict(row)

    rows: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for _, item in brain.iterrows():
        action = _clean_text(item.get("recommendation"))
        if action in {"TRÁNH / CHỜ PHỤC HỒI", "CHƯA HÀNH ĐỘNG"}:
            continue
        symbol = _normalize_symbol(item.get("symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)

        if symbol in prod_by_symbol:
            rows.append(dict(prod_by_symbol[symbol]))
            continue

        match_score, pattern_id = _best_pattern(item.get("feature_signature"), patterns)
        rows.append(
            {
                "symbol": item.get("symbol"),
                "recommendation": action,
                "confidence_score": item.get("confidence_score"),
                "leader_score": item.get("leader_score"),
                "leader_level": item.get("leader_level"),
                "current_group": item.get("current_group"),
                "current_price": item.get("current_price"),
                "current_rs5": item.get("current_rs5"),
                "current_rs10": item.get("current_rs10"),
                "current_rsi14": item.get("current_rsi14"),
                "current_obv_status": item.get("current_obv_status"),
                "winrate_t5_pct": item.get("winrate_t5_pct"),
                "avg_return_t5_pct": item.get("avg_return_t5_pct"),
                "pattern_match_score": match_score,
                "matched_pattern_id": pattern_id,
                "reason": _clean_text(item.get("recommendation_reason")),
                "updated_at": item.get("updated_at", ""),
                "rank": np.nan,
                "ProductionRank": np.nan,
            }
        )

    if not rows:
        return production_rec.copy() if production_rec is not None else pd.DataFrame(
            columns=list(RECOMMENDATION_COLUMNS)
        )

    universe = pd.DataFrame(rows)
    universe["_pure_rank_score"] = universe.apply(
        lambda r: compute_pure_baseline_score(dict(r)),
        axis=1,
    )
    universe = (
        universe.sort_values(
            ["_pure_rank_score", "leader_score", "symbol"],
            ascending=[False, False, True],
            kind="stable",
        )
        .head(max(1, int(max_candidates)))
        .drop(columns=["_pure_rank_score"])
        .reset_index(drop=True)
    )

    for col in RECOMMENDATION_COLUMNS:
        if col not in universe.columns:
            universe[col] = np.nan

    return universe.reindex(columns=list(RECOMMENDATION_COLUMNS))


def build_shadow_with_recall(
    production_rec: pd.DataFrame,
    brain: pd.DataFrame,
    experience_df: Optional[pd.DataFrame],
    *,
    session_date: str,
    recall_index: Optional[pd.DataFrame] = None,
    baseline_rank_scores: Optional[pd.DataFrame] = None,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
    breadth: Optional[Any] = None,
) -> pd.DataFrame:
    """
    Build shadow audit rows: pure baseline control vs ShadowFinalScore challenger.
    """
    if production_rec is None or production_rec.empty:
        return pd.DataFrame(columns=list(SHADOW_COLUMNS))

    if recall_index is None:
        recall_index = load_recall_index()

    pattern_lookup, continuation_lookup = _load_shadow_knowledge_lookups()

    brain_by_symbol: Dict[str, Mapping[str, Any]] = {}
    if brain is not None and not brain.empty:
        for _, row in brain.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                brain_by_symbol[sym] = dict(row)

    exp_by_symbol: Dict[str, Mapping[str, Any]] = {}
    if experience_df is not None and not experience_df.empty:
        for _, row in experience_df.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                exp_by_symbol[sym] = dict(row)

    pure_baseline_scores: Dict[str, float] = {}
    if baseline_rank_scores is not None and not baseline_rank_scores.empty:
        for _, row in baseline_rank_scores.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                pure_baseline_scores[sym] = float(row.get("_rank_score", 0))

    rows = []
    for _, rec_row in production_rec.iterrows():
        symbol = str(rec_row.get("symbol", "")).strip().upper()
        brain_row = brain_by_symbol.get(symbol, {})
        exp_row = exp_by_symbol.get(symbol, {})
        exp_stock_key = str(exp_row.get("stock_pattern_key", ""))
        exp_market_key = str(exp_row.get("market_context_key", ""))
        if exp_stock_key and "|NA|" not in exp_stock_key:
            stock_pattern_key = exp_stock_key
            market_context_key = exp_market_key
        else:
            stock_pattern_key, market_context_key = _canonical_pattern_keys_for_shadow_row(
                symbol,
                brain_row,
                dict(rec_row),
                exp_row,
                market_real=market_real,
                market_forecast=market_forecast,
                breadth=breadth,
                brain_df=brain,
            )

        pattern_row, continuation_row, matched_pattern, match_mode = (
            _shadow_knowledge_rows(
                stock_pattern_key,
                market_context_key,
                pattern_lookup,
                continuation_lookup,
            )
        )

        technical_prior = compute_technical_prior(
            {**brain_row, **dict(rec_row)},
            pattern_match_score=rec_row.get("pattern_match_score"),
        )
        recall = compute_recall_evidence(
            market_context_key,
            stock_pattern_key,
            recall_index=recall_index,
        )

        pure_baseline = pure_baseline_scores.get(symbol)
        if pure_baseline is None:
            pure_baseline = compute_pure_baseline_score(dict(rec_row))

        shadow_result = compute_shadow_final_score(
            pure_baseline,
            recall,
            pattern_row=pattern_row,
            continuation_row=continuation_row,
            matched_pattern=matched_pattern or str(exp_row.get("MatchedPattern", "")),
            matched_market_context=market_context_key,
            context_match_mode=match_mode or str(exp_row.get("ContextMatchMode", "")),
        )

        score_delta = round(
            shadow_result.shadow_final_score - shadow_result.pure_baseline_score,
            4,
        )
        production_rank = rec_row.get("rank")

        rows.append(
            {
                "session_date": session_date,
                "rank": production_rank,
                "ProductionRank": production_rank,
                "symbol": rec_row.get("symbol"),
                "recommendation": rec_row.get("recommendation"),
                "leader_score": rec_row.get("leader_score"),
                "market_context_key": market_context_key,
                "stock_pattern_key": stock_pattern_key,
                "TechnicalPrior": technical_prior,
                "BaselineScore": shadow_result.pure_baseline_score,
                "BaselineRank": np.nan,
                "PureBaselineScore": shadow_result.pure_baseline_score,
                "ShadowFinalScore": shadow_result.shadow_final_score,
                "ShadowExperienceScore": shadow_result.shadow_final_score,
                "ShadowExperienceRank": np.nan,
                "ShadowRank": np.nan,
                "PatternKnowledgeAdj": shadow_result.pattern_adjustment,
                "ContinuationAdj": shadow_result.continuation_adjustment,
                "HorizonAdj": shadow_result.horizon_adjustment,
                "RecallComponent": shadow_result.recall_component,
                "LearnedWinRate": shadow_result.learned_win_rate,
                "ContinuationScore": shadow_result.continuation_score,
                "ExperienceSamples": shadow_result.experience_samples,
                "MatchedPattern": shadow_result.matched_pattern,
                "MatchedMarketContext": shadow_result.matched_market_context,
                "ContextMatchMode": shadow_result.context_match_mode,
                "ScoreDelta": score_delta,
                "RankDelta": np.nan,
                "ShadowMovement": "",
                "RecallSource": recall.recall_source,
                "RecallLevel": recall.recall_level,
                "RecallSamples": recall.recall_samples,
                "RecallT3Samples": recall.recall_t3_samples,
                "RecallT5Samples": recall.recall_t5_samples,
                "RecallT10Samples": recall.recall_t10_samples,
                "RecallMeanT3": recall.recall_mean_t3,
                "RecallMeanT5": recall.recall_mean_t5,
                "RecallMeanT10": recall.recall_mean_t10,
                "RecallWinRateT3": recall.recall_win_rate_t3,
                "RecallWinRateT5": recall.recall_win_rate_t5,
                "RecallWinRateT10": recall.recall_win_rate_t10,
                "RecallConfidence": recall.recall_confidence,
                "RecallAlpha": recall.recall_alpha,
                "RecallMatchedDNA": recall.recall_matched_dna,
                "RecallMatchedContext": recall.recall_matched_context,
                "ShadowReason": _shadow_reason(
                    recall.recall_level,
                    recall.recall_confidence,
                    score_delta,
                    pattern_adj=shadow_result.pattern_adjustment,
                    continuation_adj=shadow_result.continuation_adjustment,
                    horizon_adj=shadow_result.horizon_adjustment,
                ),
                "updated_at": rec_row.get("updated_at", ""),
            }
        )

    shadow_df = pd.DataFrame(rows, columns=list(SHADOW_COLUMNS))
    return _apply_shadow_experience_rerank(shadow_df)


def summarize_shadow_comparison(
    shadow_df: pd.DataFrame,
    recall_index: Optional[pd.DataFrame] = None,
) -> ShadowComparisonSummary:
    if shadow_df is None or shadow_df.empty:
        return ShadowComparisonSummary()

    with_evidence = shadow_df[shadow_df["RecallLevel"] != RECALL_LEVEL_NO_EVIDENCE]
    promoted = shadow_df[shadow_df["ShadowMovement"] == "PROMOTED"]
    demoted = shadow_df[shadow_df["ShadowMovement"] == "DEMOTED"]

    recall_index = recall_index if recall_index is not None else load_recall_index()
    promoted_t3 = []
    demoted_t3 = []
    if not recall_index.empty and "symbol" in recall_index.columns:
        hist = recall_index[
            recall_index["usable_for_learning"].astype(str).str.lower().isin(
                {"true", "1", "yes"}
            )
        ]
        for _, row in promoted.iterrows():
            dna = str(row.get("RecallMatchedDNA", ""))
            ctx = str(row.get("RecallMatchedContext", ""))
            sub = hist[
                (hist["stock_pattern_key"].astype(str) == dna)
                & (hist["market_context_key"].astype(str) == ctx)
                & (hist["outcome_status_t3"] == "READY")
            ]
            if not sub.empty:
                promoted_t3.extend(pd.to_numeric(sub["t3_return_pct"], errors="coerce").dropna())
        for _, row in demoted.iterrows():
            dna = str(row.get("RecallMatchedDNA", ""))
            ctx = str(row.get("RecallMatchedContext", ""))
            sub = hist[
                (hist["stock_pattern_key"].astype(str) == dna)
                & (hist["market_context_key"].astype(str) == ctx)
                & (hist["outcome_status_t3"] == "READY")
            ]
            if not sub.empty:
                demoted_t3.extend(pd.to_numeric(sub["t3_return_pct"], errors="coerce").dropna())

    baseline_top5 = set(
        shadow_df.nsmallest(5, "BaselineRank")["symbol"].astype(str)
    )
    shadow_top5 = set(
        shadow_df.nsmallest(5, "ShadowExperienceRank")["symbol"].astype(str)
    )
    baseline_top10 = set(
        shadow_df.nsmallest(10, "BaselineRank")["symbol"].astype(str)
    )
    shadow_top10 = set(
        shadow_df.nsmallest(10, "ShadowExperienceRank")["symbol"].astype(str)
    )

    return ShadowComparisonSummary(
        candidates=len(shadow_df),
        with_recall_evidence=len(with_evidence),
        exact_count=int((shadow_df["RecallLevel"] == RECALL_LEVEL_EXACT).sum()),
        family_count=int((shadow_df["RecallLevel"] == RECALL_LEVEL_FAMILY).sum()),
        global_count=int((shadow_df["RecallLevel"] == RECALL_LEVEL_GLOBAL).sum()),
        promoted=len(promoted),
        demoted=len(demoted),
        unchanged=int((shadow_df["ShadowMovement"] == "UNCHANGED").sum()),
        top5_overlap=len(baseline_top5 & shadow_top5),
        top10_overlap=len(baseline_top10 & shadow_top10),
        avg_t3_promoted=float(np.mean(promoted_t3)) if promoted_t3 else None,
        avg_t3_demoted=float(np.mean(demoted_t3)) if demoted_t3 else None,
    )


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=str(path.parent),
        encoding="utf-8-sig",
        newline="",
        suffix=".tmp",
    ) as tmp:
        temp_name = tmp.name
    try:
        df.to_csv(temp_name, index=False, encoding="utf-8-sig")
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def persist_shadow_audit(
    shadow_df: pd.DataFrame,
    comparison_summary: Optional[ShadowComparisonSummary] = None,
    *,
    evaluation_mode: str = "FORWARD_FROZEN",
    freeze_ledger: bool = False,
    mature_outcomes: bool = False,
) -> None:
    if shadow_df is None:
        shadow_df = pd.DataFrame(columns=list(SHADOW_COLUMNS))

    _atomic_write_csv(shadow_df, SHADOW_SNAPSHOT_FILE)

    if freeze_ledger:
        from modules.regime_alpha_forward_eval import (
            EVAL_MODE_FORWARD_FROZEN,
            freeze_t0_ledger,
            mature_forward_outcomes,
        )

        mode = evaluation_mode or EVAL_MODE_FORWARD_FROZEN
        freeze_t0_ledger(shadow_df, evaluation_mode=mode)
        if mature_outcomes and mode == EVAL_MODE_FORWARD_FROZEN:
            mature_forward_outcomes()

    if comparison_summary is not None:
        summary_df = pd.DataFrame([comparison_summary.__dict__])
        _atomic_write_csv(summary_df, SHADOW_COMPARISON_FILE)


def load_shadow_recommendations() -> pd.DataFrame:
    if not SHADOW_SNAPSHOT_FILE.exists():
        return pd.DataFrame(columns=list(SHADOW_COLUMNS))
    df = pd.read_csv(SHADOW_SNAPSHOT_FILE, encoding="utf-8-sig", low_memory=False)
    if "ShadowFinalScore" not in df.columns and "ShadowExperienceScore" in df.columns:
        df["ShadowFinalScore"] = df["ShadowExperienceScore"]
    if "PureBaselineScore" not in df.columns and "BaselineScore" in df.columns:
        df["PureBaselineScore"] = df["BaselineScore"]
    return df


__all__ = [
    "SHADOW_COLUMNS",
    "ShadowComparisonSummary",
    "build_shadow_candidate_universe",
    "build_shadow_with_recall",
    "load_shadow_recommendations",
    "persist_shadow_audit",
    "summarize_shadow_comparison",
]
