"""
Learning Insight Candidates — independent research ranking engine.

Scores live symbols by successful historical DNA/pattern evidence in the
current market context. Does NOT use ShadowFinalScore or Shadow ranking.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from modules.earning_learning import (
    _continuation_knowledge_lookup,
    _decision_rows_for_pattern_keys,
    _lookup_continuation_row,
    _lookup_pattern_row,
    _pattern_knowledge_lookup,
    _safe_float,
    get_continuation_knowledge,
    get_pattern_knowledge,
)

logger = logging.getLogger("learning_insight_candidates")

MODULE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = MODULE_DIR / "brain"
INSIGHT_CANDIDATES_FILE = BRAIN_DIR / "learning_insight_candidates.csv"

INSIGHT_MIN_PATTERN_SAMPLES = 5
INSIGHT_MIN_CONTINUATION_SAMPLES = 5
INSIGHT_SAMPLE_FULL = 20

CONTEXT_AUTHORITY: Dict[str, float] = {
    "EXACT_CONTEXT": 1.00,
    "FAMILY_CONTEXT": 0.70,
    "GLOBAL_DNA": 0.35,
    "NO_PATTERN_MATCH": 0.15,
}

INSIGHT_COLUMNS: Sequence[str] = (
    "session_date",
    "InsightRank",
    "symbol",
    "recommendation",
    "leader_score",
    "stock_pattern_key",
    "market_context_key",
    "InsightCandidateScore",
    "PatternKnowledgeScore",
    "ContinuationKnowledgeScore",
    "ContextAuthority",
    "ExperienceSamples",
    "LearnedWinRate",
    "ContinuationScore",
    "MatchedPattern",
    "MatchedMarketContext",
    "ContextMatchMode",
    "PatternWinRateT3",
    "PatternWinRateT5",
    "PatternWinRateT10",
    "ContinuationT3ToT5Rate",
    "ContinuationT3ToT10Rate",
    "InsightReason",
    "updated_at",
)


@dataclass(frozen=True)
class InsightCandidateResult:
    insight_candidate_score: float
    pattern_knowledge_score: float
    continuation_knowledge_score: float
    context_authority: float
    experience_samples: int = 0
    learned_win_rate: Optional[float] = None
    continuation_score: Optional[float] = None
    matched_pattern: str = ""
    matched_market_context: str = ""
    context_match_mode: str = ""
    pattern_win_rate_t3: Optional[float] = None
    pattern_win_rate_t5: Optional[float] = None
    pattern_win_rate_t10: Optional[float] = None
    continuation_t3_to_t5_rate: Optional[float] = None
    continuation_t3_to_t10_rate: Optional[float] = None
    insight_reason: str = ""


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _sample_confidence(samples: int, *, minimum: int, full: int) -> float:
    if samples < minimum:
        return 0.0
    return _clip((samples - minimum) / max(1, full - minimum), 0.0, 1.0)


def _pattern_horizon_win_rate(
    pattern_lookup: Mapping,
    market_context_key: str,
    stock_pattern_key: str,
    horizon: int,
) -> Optional[float]:
    row, _ = _lookup_pattern_row(
        pattern_lookup,
        market_context_key,
        stock_pattern_key,
        preferred_horizon=horizon,
        fallback_horizon=horizon,
    )
    if row is None:
        return None
    win_rate = _safe_float(row.get("win_rate_pct"))
    return float(win_rate) if np.isfinite(win_rate) else None


def compute_insight_candidate_score(
    *,
    pattern_row: Optional[Mapping[str, Any]],
    continuation_row: Optional[Mapping[str, Any]],
    context_match_mode: str = "",
    pattern_win_rate_t3: Optional[float] = None,
    pattern_win_rate_t5: Optional[float] = None,
    pattern_win_rate_t10: Optional[float] = None,
) -> InsightCandidateResult:
    """
    Research-only score from pattern + continuation knowledge in context.
    Independent from ShadowFinalScore and production ranking.
    """
    mode = str(context_match_mode or "NO_PATTERN_MATCH")
    context_auth = CONTEXT_AUTHORITY.get(mode, CONTEXT_AUTHORITY["NO_PATTERN_MATCH"])

    pattern_evidence = 50.0
    samples = 0
    learned_wr: Optional[float] = None
    if pattern_row is not None:
        samples = int(_safe_float(pattern_row.get("samples")) or 0)
        wr_raw = _safe_float(pattern_row.get("win_rate_pct"))
        learned_wr = float(wr_raw) if np.isfinite(wr_raw) else None
        lower = _safe_float(pattern_row.get("win_rate_lower_bound_pct"))
        evidence = lower if np.isfinite(lower) else (
            learned_wr * 0.85 if np.isfinite(learned_wr) else np.nan
        )
        if np.isfinite(evidence) and samples >= INSIGHT_MIN_PATTERN_SAMPLES:
            pattern_evidence = float(evidence)

    continuation_evidence = 50.0
    cont_score_val: Optional[float] = None
    samples_t10 = 0
    t3_t5_rate: Optional[float] = None
    t3_t10_rate: Optional[float] = None
    if continuation_row is not None:
        samples_t10 = int(_safe_float(continuation_row.get("samples_t10")) or 0)
        cont_score_val = _safe_float(continuation_row.get("continuation_score"))
        t3_t5_rate = _safe_float(continuation_row.get("t3_to_t5_rate_pct"))
        t3_t10_rate = _safe_float(continuation_row.get("t3_to_t10_rate_pct"))
        if np.isfinite(cont_score_val) and samples_t10 >= INSIGHT_MIN_CONTINUATION_SAMPLES:
            continuation_evidence = float(cont_score_val)

    pattern_conf = _sample_confidence(
        samples, minimum=INSIGHT_MIN_PATTERN_SAMPLES, full=INSIGHT_SAMPLE_FULL
    )
    cont_conf = _sample_confidence(
        samples_t10,
        minimum=INSIGHT_MIN_CONTINUATION_SAMPLES,
        full=INSIGHT_SAMPLE_FULL,
    )

    effective_conf = max(pattern_conf, cont_conf) * context_auth
    if effective_conf <= 0.0:
        final_score = 50.0
    else:
        blended = 0.50 * pattern_evidence + 0.50 * continuation_evidence
        final_score = 50.0 + (blended - 50.0) * effective_conf

    reasons: list[str] = []
    if pattern_conf > 0 and samples >= INSIGHT_MIN_PATTERN_SAMPLES:
        reasons.append(f"pattern n={samples} wr~{pattern_evidence:.0f}")
    if cont_conf > 0 and samples_t10 >= INSIGHT_MIN_CONTINUATION_SAMPLES:
        reasons.append(f"continuation n={samples_t10} score~{continuation_evidence:.0f}")
    if mode:
        reasons.append(mode.lower())
    if not reasons:
        reason = "Insufficient DNA/context evidence for insight ranking."
    else:
        reason = "Insight evidence: " + ", ".join(reasons) + "."

    matched_pattern = ""
    matched_context = ""
    if pattern_row is not None:
        matched_pattern = str(pattern_row.get("pattern_key", ""))
        matched_context = str(pattern_row.get("market_context_key", ""))
    elif continuation_row is not None:
        matched_context = str(continuation_row.get("market_context_key", ""))

    return InsightCandidateResult(
        insight_candidate_score=round(_clip(final_score, 0.0, 100.0), 4),
        pattern_knowledge_score=round(pattern_evidence, 4),
        continuation_knowledge_score=round(continuation_evidence, 4),
        context_authority=round(context_auth, 4),
        experience_samples=max(samples, samples_t10),
        learned_win_rate=learned_wr,
        continuation_score=cont_score_val if cont_score_val is not None and np.isfinite(cont_score_val) else None,
        matched_pattern=matched_pattern,
        matched_market_context=matched_context,
        context_match_mode=mode,
        pattern_win_rate_t3=pattern_win_rate_t3,
        pattern_win_rate_t5=pattern_win_rate_t5,
        pattern_win_rate_t10=pattern_win_rate_t10,
        continuation_t3_to_t5_rate=t3_t5_rate if t3_t5_rate is not None and np.isfinite(t3_t5_rate) else None,
        continuation_t3_to_t10_rate=t3_t10_rate if t3_t10_rate is not None and np.isfinite(t3_t10_rate) else None,
        insight_reason=reason,
    )


def _load_insight_knowledge() -> tuple[Dict, Dict]:
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


def build_learning_insight_candidates(
    candidate_df: pd.DataFrame,
    brain: pd.DataFrame,
    *,
    session_date: str,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
    breadth: Optional[Any] = None,
) -> pd.DataFrame:
    """Rank research candidates from insight DNA/context logic only."""
    if candidate_df is None or candidate_df.empty:
        return pd.DataFrame(columns=list(INSIGHT_COLUMNS))

    pattern_lookup, continuation_lookup = _load_insight_knowledge()
    rows: list[Dict[str, Any]] = []

    for _, rec_row in candidate_df.iterrows():
        symbol = str(rec_row.get("symbol", "")).strip().upper()
        if not symbol:
            continue

        frame = pd.DataFrame([dict(rec_row)])
        frame["symbol"] = symbol
        mr = _safe_float(market_real)
        mf = _safe_float(market_forecast)
        bw = _safe_float(breadth)
        keyed = _decision_rows_for_pattern_keys(
            frame,
            market_real=mr if np.isfinite(mr) else np.nan,
            market_forecast=mf if np.isfinite(mf) else np.nan,
            breadth=bw if np.isfinite(bw) else None,
            brain_df=brain,
        )
        if keyed.empty:
            stock_pattern_key = ""
            market_context_key = ""
        else:
            key_row = keyed.iloc[0]
            stock_pattern_key = str(key_row.get("stock_pattern_key", ""))
            market_context_key = str(key_row.get("market_context_key", ""))

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
        match_mode = pattern_mode or continuation_mode or "NO_PATTERN_MATCH"

        wr_t3 = _pattern_horizon_win_rate(
            pattern_lookup, market_context_key, stock_pattern_key, 3
        )
        wr_t5 = _pattern_horizon_win_rate(
            pattern_lookup, market_context_key, stock_pattern_key, 5
        )
        wr_t10 = _pattern_horizon_win_rate(
            pattern_lookup, market_context_key, stock_pattern_key, 10
        )

        insight = compute_insight_candidate_score(
            pattern_row=dict(pattern_row) if pattern_row is not None else None,
            continuation_row=dict(continuation_row) if continuation_row is not None else None,
            context_match_mode=match_mode,
            pattern_win_rate_t3=wr_t3,
            pattern_win_rate_t5=wr_t5,
            pattern_win_rate_t10=wr_t10,
        )

        rows.append(
            {
                "session_date": session_date,
                "InsightRank": np.nan,
                "symbol": rec_row.get("symbol"),
                "recommendation": rec_row.get("recommendation"),
                "leader_score": rec_row.get("leader_score"),
                "stock_pattern_key": stock_pattern_key,
                "market_context_key": market_context_key,
                "InsightCandidateScore": insight.insight_candidate_score,
                "PatternKnowledgeScore": insight.pattern_knowledge_score,
                "ContinuationKnowledgeScore": insight.continuation_knowledge_score,
                "ContextAuthority": insight.context_authority,
                "ExperienceSamples": insight.experience_samples,
                "LearnedWinRate": insight.learned_win_rate,
                "ContinuationScore": insight.continuation_score,
                "MatchedPattern": insight.matched_pattern,
                "MatchedMarketContext": insight.matched_market_context,
                "ContextMatchMode": insight.context_match_mode,
                "PatternWinRateT3": insight.pattern_win_rate_t3,
                "PatternWinRateT5": insight.pattern_win_rate_t5,
                "PatternWinRateT10": insight.pattern_win_rate_t10,
                "ContinuationT3ToT5Rate": insight.continuation_t3_to_t5_rate,
                "ContinuationT3ToT10Rate": insight.continuation_t3_to_t10_rate,
                "InsightReason": insight.insight_reason,
                "updated_at": rec_row.get("updated_at", ""),
            }
        )

    out = pd.DataFrame(rows, columns=list(INSIGHT_COLUMNS))
    if out.empty:
        return out

    out = out.sort_values(
        ["InsightCandidateScore", "ExperienceSamples", "leader_score", "symbol"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    out["InsightRank"] = range(1, len(out) + 1)
    return out


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


def persist_learning_insight_candidates(df: pd.DataFrame) -> None:
    if df is None:
        df = pd.DataFrame(columns=list(INSIGHT_COLUMNS))
    _atomic_write_csv(df, INSIGHT_CANDIDATES_FILE)


def load_learning_insight_candidates() -> pd.DataFrame:
    if not INSIGHT_CANDIDATES_FILE.exists():
        return pd.DataFrame(columns=list(INSIGHT_COLUMNS))
    return pd.read_csv(INSIGHT_CANDIDATES_FILE, encoding="utf-8-sig", low_memory=False)


__all__ = [
    "INSIGHT_COLUMNS",
    "INSIGHT_CANDIDATES_FILE",
    "InsightCandidateResult",
    "build_learning_insight_candidates",
    "compute_insight_candidate_score",
    "load_learning_insight_candidates",
    "persist_learning_insight_candidates",
]
