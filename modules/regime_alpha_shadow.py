"""
Regime Alpha shadow audit layer (N3).

Computes TechnicalPrior + RegimeAlpha alongside production AI Recommendation
without changing admission, ranking, Buy Elite, or Final Decision.

Shadow outputs are audit-only and persisted to separate files under brain/.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import pandas as pd

from modules.regime_alpha import (
    NEUTRAL_RAS,
    compute_final_recommendation_score,
    compute_regime_alpha_score,
    compute_technical_prior,
)

logger = logging.getLogger("regime_alpha_shadow")

MODULE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = MODULE_DIR / "brain"
SHADOW_SNAPSHOT_FILE = BRAIN_DIR / "ai_recommendation_shadow.csv"
SHADOW_HISTORY_FILE = BRAIN_DIR / "regime_alpha_shadow_history.csv"

# Minimum confidence before GLOBAL_DNA shadow may lean away from technical prior.
GLOBAL_DNA_MIN_CONFIDENCE = 0.15

CONTEXT_LEVEL_EXPORT: Dict[str, str] = {
    "EXACT": "EXACT_CONTEXT",
    "FAMILY": "FAMILY_CONTEXT",
    "GLOBAL_DNA": "GLOBAL_DNA",
    "NONE": "NONE",
}

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
    "RegimeAlphaScore",
    "RegimeAlphaRawScore",
    "RegimeAlphaDiscountedScore",
    "RegimeAlphaConfidence",
    "RegimeAlphaContextLevel",
    "RegimeAlphaMatchedContext",
    "RegimeAlphaSamples",
    "ShadowFinalScore",
    "ShadowDecision",
    "ShadowReason",
    "updated_at",
)

_SHADOW_RANK_SORT_COLUMNS: Sequence[str] = (
    "ShadowFinalScore",
    "RegimeAlphaConfidence",
    "TechnicalPrior",
    "leader_score",
    "symbol",
)

SHADOW_HISTORY_COLUMNS: Sequence[str] = SHADOW_COLUMNS + (
    "realized_t3_return_pct",
    "realized_t5_return_pct",
    "realized_t10_return_pct",
    "outcome_join_status",
)


@dataclass(frozen=True)
class ShadowAuditRow:
    technical_prior: float
    regime_alpha_score: float
    regime_alpha_raw_score: float
    regime_alpha_discounted_score: float
    regime_alpha_confidence: float
    regime_alpha_context_level: str
    regime_alpha_matched_context: str
    regime_alpha_samples: int
    shadow_final_score: float
    shadow_decision: str
    shadow_reason: str


def _export_context_level(level: str) -> str:
    return CONTEXT_LEVEL_EXPORT.get(str(level or "").strip(), str(level or "NONE"))


def _load_knowledge_cache(
    pattern_knowledge: Optional[pd.DataFrame],
    continuation_knowledge: Optional[pd.DataFrame],
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    pk = pattern_knowledge
    ck = continuation_knowledge
    if pk is None:
        try:
            from modules.earning_learning import get_pattern_knowledge

            pk = get_pattern_knowledge(min_samples=1)
        except Exception:
            logger.exception("Shadow: pattern_knowledge load failed")
            pk = pd.DataFrame()
    if ck is None:
        try:
            from modules.earning_learning import get_continuation_knowledge

            ck = get_continuation_knowledge(min_samples=1)
        except Exception:
            logger.exception("Shadow: continuation_knowledge load failed")
            ck = pd.DataFrame()
    return pk, ck


def _shadow_decision_and_reason(
    *,
    technical_prior: float,
    regime_alpha_score: float,
    confidence: float,
    context_level: str,
    shadow_final_score: float,
) -> tuple[str, str]:
    exported_level = _export_context_level(context_level)
    delta = shadow_final_score - technical_prior

    if context_level == "NONE" or confidence <= 0.0:
        return (
            "TECHNICAL_ONLY",
            "No usable regime-alpha evidence (NONE context or zero confidence).",
        )

    if context_level == "GLOBAL_DNA":
        prefix = (
            "GLOBAL_DNA only — context-free DNA fallback from NA|NA history; "
            "not proof of regime-specific learning. "
        )
        if confidence < GLOBAL_DNA_MIN_CONFIDENCE:
            return (
                "TECHNICAL_ONLY",
                prefix
                + f"Confidence {confidence:.3f} below GLOBAL_DNA floor "
                f"({GLOBAL_DNA_MIN_CONFIDENCE}); technical prior retained.",
            )
        if abs(delta) <= 3.0:
            return (
                "SHADOW_NEUTRAL",
                prefix
                + f"Low-authority GLOBAL_DNA (conf={confidence:.3f}); "
                "shadow does not materially diverge from technical prior.",
            )
        if delta > 3.0:
            return (
                "SHADOW_WATCH_LEARNED",
                prefix
                + f"Marginal GLOBAL_DNA lift (ShadowFinal {shadow_final_score:.1f} "
                f"vs TP {technical_prior:.1f}); observe only.",
            )
        return (
            "SHADOW_WATCH_TECHNICAL",
            prefix
            + f"Marginal GLOBAL_DNA penalty (ShadowFinal {shadow_final_score:.1f} "
            f"vs TP {technical_prior:.1f}); observe only.",
        )

    if context_level == "FAMILY":
        prefix = "FAMILY_CONTEXT — forecast+market bucket fallback (breadth-safe). "
    else:
        prefix = "EXACT_CONTEXT — exact market regime + DNA match. "

    if confidence < 0.15:
        return (
            "TECHNICAL_ONLY",
            prefix + f"Confidence {confidence:.3f} too low for shadow preference.",
        )

    if confidence >= 0.50 and regime_alpha_score >= 58.0 and delta > 5.0:
        return (
            "SHADOW_PREFER_LEARNED",
            prefix
            + f"Strong learned money evidence (RAS={regime_alpha_score:.1f}, "
            f"conf={confidence:.2f}) lifts shadow above technical prior.",
        )

    if confidence >= 0.50 and regime_alpha_score <= 42.0 and delta < -5.0:
        return (
            "SHADOW_PREFER_TECHNICAL",
            prefix
            + f"Weak learned money evidence (RAS={regime_alpha_score:.1f}) "
            "keeps shadow below technical prior.",
        )

    if abs(delta) <= 3.0:
        return (
            "SHADOW_AGREE",
            prefix + "Technical prior and regime alpha broadly agree.",
        )

    if delta > 3.0:
        return (
            "SHADOW_LEAN_LEARNED",
            prefix
            + f"ShadowFinal {shadow_final_score:.1f} > TechnicalPrior {technical_prior:.1f}.",
        )

    return (
        "SHADOW_LEAN_TECHNICAL",
        prefix
        + f"ShadowFinal {shadow_final_score:.1f} < TechnicalPrior {technical_prior:.1f}.",
    )


def compute_shadow_audit(
    *,
    brain_row: Mapping[str, Any],
    experience_row: Mapping[str, Any],
    pattern_match_score: Optional[float] = None,
    pattern_knowledge: Optional[pd.DataFrame] = None,
    continuation_knowledge: Optional[pd.DataFrame] = None,
    as_of: Optional[date] = None,
) -> ShadowAuditRow:
    """Compute shadow audit fields for one admitted recommendation candidate."""
    pk, ck = _load_knowledge_cache(pattern_knowledge, continuation_knowledge)

    market_context_key = str(experience_row.get("market_context_key") or "").strip()
    stock_pattern_key = str(experience_row.get("stock_pattern_key") or "").strip()

    prior_input = dict(brain_row)
    if pattern_match_score is not None:
        prior_input["pattern_match_score"] = pattern_match_score
    technical_prior = compute_technical_prior(prior_input)

    if not stock_pattern_key:
        return ShadowAuditRow(
            technical_prior=technical_prior,
            regime_alpha_score=NEUTRAL_RAS,
            regime_alpha_raw_score=NEUTRAL_RAS,
            regime_alpha_discounted_score=NEUTRAL_RAS,
            regime_alpha_confidence=0.0,
            regime_alpha_context_level="NONE",
            regime_alpha_matched_context="",
            regime_alpha_samples=0,
            shadow_final_score=technical_prior,
            shadow_decision="TECHNICAL_ONLY",
            shadow_reason="Missing stock_pattern_key; regime alpha unavailable.",
        )

    ras_result = compute_regime_alpha_score(
        market_context_key,
        stock_pattern_key,
        pattern_knowledge=pk,
        continuation_knowledge=ck,
        as_of=as_of,
    )

    raw_ras = float(ras_result.raw_ras_before_discount)
    discounted_ras = float(ras_result.regime_alpha_score)
    confidence = float(ras_result.regime_alpha_confidence)
    context_level = _export_context_level(ras_result.context_match_level)

    shadow_final = compute_final_recommendation_score(
        discounted_ras,
        technical_prior,
        confidence,
    )

    decision, reason = _shadow_decision_and_reason(
        technical_prior=technical_prior,
        regime_alpha_score=discounted_ras,
        confidence=confidence,
        context_level=ras_result.context_match_level,
        shadow_final_score=shadow_final,
    )

    return ShadowAuditRow(
        technical_prior=round(technical_prior, 2),
        regime_alpha_score=round(discounted_ras, 4),
        regime_alpha_raw_score=round(raw_ras, 4),
        regime_alpha_discounted_score=round(discounted_ras, 4),
        regime_alpha_confidence=round(confidence, 6),
        regime_alpha_context_level=context_level,
        regime_alpha_matched_context=str(ras_result.matched_market_context or ""),
        regime_alpha_samples=int(ras_result.effective_samples),
        shadow_final_score=round(shadow_final, 2),
        shadow_decision=decision,
        shadow_reason=reason,
    )


def _apply_shadow_rerank(df: pd.DataFrame) -> pd.DataFrame:
    """Sort shadow rows by paper challenger score; assign ShadowRank 1..N."""
    if df is None or df.empty:
        return df

    out = df.copy()
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
    out["ShadowRank"] = range(1, len(out) + 1)
    return out.reindex(columns=list(SHADOW_COLUMNS))


def build_shadow_recommendations(
    production_rec: pd.DataFrame,
    brain: pd.DataFrame,
    experience_df: Optional[pd.DataFrame],
    *,
    session_date: str,
    pattern_knowledge: Optional[pd.DataFrame] = None,
    continuation_knowledge: Optional[pd.DataFrame] = None,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Build shadow audit rows for production candidates with independent ShadowRank.

    Reads production_rec only; never mutates it. Output row order follows
    ShadowRank (ShadowFinalScore DESC + stable tie-breaks).
    """
    if production_rec is None or production_rec.empty:
        return pd.DataFrame(columns=list(SHADOW_COLUMNS))

    brain_by_symbol: Dict[str, Mapping[str, Any]] = {}
    if brain is not None and not brain.empty and "symbol" in brain.columns:
        for _, row in brain.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                brain_by_symbol[sym] = dict(row)

    exp_by_symbol: Dict[str, Mapping[str, Any]] = {}
    if experience_df is not None and not experience_df.empty and "symbol" in experience_df.columns:
        for _, row in experience_df.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                exp_by_symbol[sym] = dict(row)

    pk, ck = _load_knowledge_cache(pattern_knowledge, continuation_knowledge)
    rows = []
    for _, rec_row in production_rec.iterrows():
        symbol = str(rec_row.get("symbol", "")).strip().upper()
        brain_row = brain_by_symbol.get(symbol, {})
        exp_row = exp_by_symbol.get(symbol, {})
        pms = rec_row.get("pattern_match_score")
        audit = compute_shadow_audit(
            brain_row=brain_row,
            experience_row=exp_row,
            pattern_match_score=pms,
            pattern_knowledge=pk,
            continuation_knowledge=ck,
            as_of=as_of,
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
                "market_context_key": exp_row.get("market_context_key", ""),
                "stock_pattern_key": exp_row.get("stock_pattern_key", ""),
                "TechnicalPrior": audit.technical_prior,
                "RegimeAlphaScore": audit.regime_alpha_score,
                "RegimeAlphaRawScore": audit.regime_alpha_raw_score,
                "RegimeAlphaDiscountedScore": audit.regime_alpha_discounted_score,
                "RegimeAlphaConfidence": audit.regime_alpha_confidence,
                "RegimeAlphaContextLevel": audit.regime_alpha_context_level,
                "RegimeAlphaMatchedContext": audit.regime_alpha_matched_context,
                "RegimeAlphaSamples": audit.regime_alpha_samples,
                "ShadowFinalScore": audit.shadow_final_score,
                "ShadowDecision": audit.shadow_decision,
                "ShadowReason": audit.shadow_reason,
                "updated_at": rec_row.get("updated_at", ""),
            }
        )

    return _apply_shadow_rerank(pd.DataFrame(rows, columns=list(SHADOW_COLUMNS)))


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


def _append_shadow_history(snapshot: pd.DataFrame) -> None:
    if snapshot is None or snapshot.empty:
        return

    history_cols = list(SHADOW_HISTORY_COLUMNS)
    if SHADOW_HISTORY_FILE.exists() and SHADOW_HISTORY_FILE.stat().st_size > 0:
        try:
            existing = pd.read_csv(SHADOW_HISTORY_FILE, encoding="utf-8-sig", low_memory=False)
        except Exception:
            existing = pd.DataFrame(columns=history_cols)
    else:
        existing = pd.DataFrame(columns=history_cols)

    for col in history_cols:
        if col not in existing.columns:
            existing[col] = pd.NA
        if col not in snapshot.columns:
            snapshot = snapshot.copy()
            snapshot[col] = pd.NA

    enriched = snapshot.copy()
    for col in ("realized_t3_return_pct", "realized_t5_return_pct", "realized_t10_return_pct"):
        if col not in enriched.columns:
            enriched[col] = pd.NA
    enriched["outcome_join_status"] = "PENDING"

    combined = pd.concat([existing, enriched], ignore_index=True)
    if {"session_date", "symbol"}.issubset(combined.columns):
        combined = combined.drop_duplicates(
            subset=["session_date", "symbol"],
            keep="last",
        )
    _atomic_write_csv(combined[history_cols], SHADOW_HISTORY_FILE)


def persist_shadow_audit(shadow_df: pd.DataFrame) -> None:
    """Write session snapshot + append deduped history (shadow-only files)."""
    if shadow_df is None:
        shadow_df = pd.DataFrame(columns=list(SHADOW_COLUMNS))
    _atomic_write_csv(shadow_df, SHADOW_SNAPSHOT_FILE)
    _append_shadow_history(shadow_df)


def load_shadow_recommendations() -> pd.DataFrame:
    if not SHADOW_SNAPSHOT_FILE.exists() or SHADOW_SNAPSHOT_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=list(SHADOW_COLUMNS))
    try:
        return pd.read_csv(SHADOW_SNAPSHOT_FILE, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame(columns=list(SHADOW_COLUMNS))


def load_shadow_history() -> pd.DataFrame:
    if not SHADOW_HISTORY_FILE.exists() or SHADOW_HISTORY_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=list(SHADOW_HISTORY_COLUMNS))
    try:
        return pd.read_csv(SHADOW_HISTORY_FILE, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame(columns=list(SHADOW_HISTORY_COLUMNS))


__all__ = [
    "SHADOW_COLUMNS",
    "SHADOW_HISTORY_COLUMNS",
    "SHADOW_SNAPSHOT_FILE",
    "SHADOW_HISTORY_FILE",
    "ShadowAuditRow",
    "compute_shadow_audit",
    "build_shadow_recommendations",
    "persist_shadow_audit",
    "load_shadow_recommendations",
    "load_shadow_history",
]
