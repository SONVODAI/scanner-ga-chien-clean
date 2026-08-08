"""
Regime Alpha Engine — learned expected-value score with optional recall index (N2 + N3.7).

Standalone module: not wired into production recommendation paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from modules.earning_learning import _wilson_lower_bound
from modules.regime_recall_index import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_FAMILY,
    RECALL_LEVEL_GLOBAL,
    load_recall_index,
)

NEUTRAL_RAS = 50.0

HORIZON_WEIGHTS: Dict[int, float] = {3: 0.25, 5: 0.45, 10: 0.30}

SAMPLE_MIN = 5
SAMPLE_FULL = 20
MAX_LEARNING_AUTHORITY = 0.85
RECENCY_FLOOR = 0.5

CONTEXT_AUTHORITY: Dict[str, float] = {
    "EXACT_CONTEXT": 1.00,
    "FAMILY_CONTEXT": 0.65,
    "GLOBAL_DNA": 0.35,
    "NO_RECALL_EVIDENCE": 0.00,
}

RAS_EVIDENCE_DISCOUNT: Dict[str, float] = {
    "EXACT_CONTEXT": 1.00,
    "FAMILY_CONTEXT": 0.90,
    "GLOBAL_DNA": 0.75,
    "NO_RECALL_EVIDENCE": 0.00,
}

RECALL_LEVEL_NO_EVIDENCE = "NO_RECALL_EVIDENCE"

RowLike = Union[Mapping[str, Any], pd.Series]


@dataclass(frozen=True)
class RecallEvidenceResult:
    recall_source: str = "NONE"
    recall_level: str = RECALL_LEVEL_NO_EVIDENCE
    recall_samples: int = 0
    recall_t3_samples: int = 0
    recall_t5_samples: int = 0
    recall_t10_samples: int = 0
    recall_mean_t3: Optional[float] = None
    recall_mean_t5: Optional[float] = None
    recall_mean_t10: Optional[float] = None
    recall_win_rate_t3: Optional[float] = None
    recall_win_rate_t5: Optional[float] = None
    recall_win_rate_t10: Optional[float] = None
    recall_confidence: float = 0.0
    recall_alpha: float = NEUTRAL_RAS
    recall_matched_dna: str = ""
    recall_matched_context: str = ""


def _optional_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _winsorize(value: float, low: float, high: float) -> float:
    return _clip(value, low, high)


def market_context_family(market_context_key: str) -> Tuple[str, str]:
    parts = str(market_context_key).split("|")
    if len(parts) >= 3:
        return parts[0], parts[2]
    return str(market_context_key), ""


def is_na_market_context(market_context_key: str) -> bool:
    text = str(market_context_key).strip()
    if not text:
        return True
    parts = text.split("|")
    if len(parts) >= 2 and parts[0] == "NA" and parts[1] == "NA":
        return True
    return text in {"NA", "NA|NA", "NA|NA|NA"}


def shrink_toward_neutral(score: float, discount: float) -> float:
    return NEUTRAL_RAS + (score - NEUTRAL_RAS) * discount


def compute_horizon_ev(pattern_row: Optional[RowLike]) -> Optional[float]:
    if pattern_row is None:
        return None
    row = dict(pattern_row)
    samples = int(_optional_float(row.get("samples"), 0) or 0)
    if samples <= 0:
        return None

    wlb = _optional_float(row.get("win_rate_lower_bound_pct"))
    if wlb is None:
        win_rate = _optional_float(row.get("win_rate_pct"))
        if win_rate is not None:
            wlb = win_rate * 0.85
    if wlb is None:
        return None

    median_ret = _optional_float(row.get("median_return_pct"))
    if median_ret is None:
        return None

    dd = _optional_float(row.get("avg_max_drawdown_pct"))
    worst = _optional_float(row.get("worst_return_pct"))

    win_component = (wlb - NEUTRAL_RAS) / NEUTRAL_RAS
    return_component = _winsorize(median_ret, -8.0, 12.0) / 12.0
    downside_component = _clip(-dd, 0.0, 15.0) / 15.0 if dd is not None else 0.0
    tail_penalty = _clip(-worst, 0.0, 10.0) / 10.0 if worst is not None else 0.0

    ev = (
        NEUTRAL_RAS
        + 22.0 * win_component
        + 28.0 * return_component
        - 12.0 * downside_component
        - 8.0 * tail_penalty
    )
    return _clip(ev, 0.0, 100.0)


def compute_alpha_confidence(effective_samples: int, context_level: str) -> float:
    if context_level == RECALL_LEVEL_NO_EVIDENCE or effective_samples <= 0:
        return 0.0
    if effective_samples < SAMPLE_MIN:
        sample_weight = 0.0
    else:
        sample_weight = _clip(
            (effective_samples - SAMPLE_MIN) / (SAMPLE_FULL - SAMPLE_MIN),
            0.0,
            1.0,
        )
    context_auth = CONTEXT_AUTHORITY.get(context_level, 0.0)
    confidence = sample_weight * context_auth * RECENCY_FLOOR
    return _clip(confidence, 0.0, MAX_LEARNING_AUTHORITY)


def _normalize_rsi(rsi: Optional[float]) -> float:
    if rsi is None:
        return NEUTRAL_RAS
    return _clip(100.0 - min(abs(rsi - 62.0) * 2.6, 100.0), 0.0, 100.0)


def _normalize_obv(obv_status: Any) -> float:
    text = str(obv_status or "").strip().upper()
    if text in {"UP", "GREEN", "BULL", "TANG"}:
        return 75.0
    if text in {"DOWN", "RED", "BEAR", "GIAM"}:
        return 25.0
    return NEUTRAL_RAS


def compute_technical_prior(row: RowLike, *, pattern_match_score: Optional[float] = None) -> float:
    data = dict(row)
    components: list[Tuple[float, float]] = []

    leader = _optional_float(data.get("leader_score"))
    if leader is not None:
        components.append((_clip(leader, 0.0, 100.0), 0.40))

    rsi = _optional_float(data.get("current_rsi14", data.get("rsi14")))
    components.append((_normalize_rsi(rsi), 0.10))

    obv = data.get("current_obv_status", data.get("obv_status"))
    components.append((_normalize_obv(obv), 0.10))

    persistence = _optional_float(data.get("persistence_20_pct"))
    if persistence is not None:
        components.append((_clip(persistence, 0.0, 100.0), 0.10))

    win5 = _optional_float(data.get("winrate_t5_pct"))
    if win5 is not None:
        components.append((_clip(win5, 0.0, 100.0), 0.15))

    pms = pattern_match_score if pattern_match_score is not None else _optional_float(
        data.get("pattern_match_score")
    )
    if pms is not None:
        components.append((_clip(pms, 0.0, 100.0), 0.15))

    group = data.get("current_group", data.get("group"))
    components.append((NEUTRAL_RAS if not group else NEUTRAL_RAS, 0.10))

    if not components:
        return NEUTRAL_RAS
    total_w = sum(w for _, w in components)
    return round(sum(v * w for v, w in components) / total_w, 2)


def filter_recall_learning_pool(recall_index: pd.DataFrame) -> pd.DataFrame:
    if recall_index is None or recall_index.empty:
        return pd.DataFrame()

    df = recall_index.copy()
    usable = df["usable_for_learning"].astype(str).str.lower().isin({"true", "1", "yes"})
    matured = (
        (df.get("outcome_status_t3", pd.Series(dtype=str)) == "READY")
        | (df.get("outcome_status_t5", pd.Series(dtype=str)) == "READY")
        | (df.get("outcome_status_t10", pd.Series(dtype=str)) == "READY")
    )
    return df[usable & matured].copy()


def _wilson_lower_bound_pct(wins: int, samples: int) -> float:
    if samples <= 0:
        return 0.0
    result = _wilson_lower_bound(
        pd.Series([wins], dtype=float),
        pd.Series([samples], dtype=float),
    )
    # earning_learning._wilson_lower_bound already returns percent (0-100).
    return float(result.iloc[0])


def _horizon_stats(rows: pd.DataFrame, return_col: str, status_col: str) -> Dict[str, Any]:
    if rows.empty or return_col not in rows.columns:
        return {"samples": 0, "mean": None, "median": None, "win_rate": None, "worst": None}

    ready = rows[rows.get(status_col, pd.Series(dtype=str)) == "READY"]
    if ready.empty:
        return {"samples": 0, "mean": None, "median": None, "win_rate": None, "worst": None}

    returns = pd.to_numeric(ready[return_col], errors="coerce").dropna()
    if returns.empty:
        return {"samples": 0, "mean": None, "median": None, "win_rate": None, "worst": None}

    wins = int((returns > 0).sum())
    return {
        "samples": len(returns),
        "mean": float(returns.mean()),
        "median": float(returns.median()),
        "win_rate": float(wins / len(returns) * 100.0),
        "worst": float(returns.min()),
        "wlb": _wilson_lower_bound_pct(wins, len(returns)),
    }


def _blend_horizon_ev(horizon_ev: Dict[int, float]) -> float:
    if not horizon_ev:
        return NEUTRAL_RAS
    weight_sum = sum(HORIZON_WEIGHTS[h] for h in horizon_ev if h in HORIZON_WEIGHTS)
    if weight_sum <= 0:
        return NEUTRAL_RAS
    blended = sum(horizon_ev[h] * HORIZON_WEIGHTS[h] for h in horizon_ev) / weight_sum
    return _clip(blended, 0.0, 100.0)


def _resolve_recall_rows(
    pool: pd.DataFrame,
    market_context_key: str,
    stock_pattern_key: str,
) -> Tuple[pd.DataFrame, str, str]:
    if pool.empty or not stock_pattern_key:
        return pd.DataFrame(), RECALL_LEVEL_NO_EVIDENCE, ""

    dna_rows = pool[pool["stock_pattern_key"].astype(str) == str(stock_pattern_key)]
    if dna_rows.empty:
        return pd.DataFrame(), RECALL_LEVEL_NO_EVIDENCE, ""

    exact = dna_rows[
        (dna_rows["market_context_key"].astype(str) == str(market_context_key))
        & (dna_rows["recall_level"].astype(str) == RECALL_LEVEL_EXACT)
    ]
    if not exact.empty:
        ctx = str(exact.iloc[0]["market_context_key"])
        return exact, RECALL_LEVEL_EXACT, ctx

    target_family = market_context_family(market_context_key)
    family = dna_rows[dna_rows["recall_level"].astype(str) == RECALL_LEVEL_FAMILY]
    if not family.empty:
        family = family[
            family["market_context_key"].map(lambda c: market_context_family(str(c)) == target_family)
        ]
    if not family.empty:
        ctx = str(
            family["market_context_key"]
            .value_counts()
            .idxmax()
        )
        return family, RECALL_LEVEL_FAMILY, ctx

    global_rows = dna_rows[dna_rows["recall_level"].astype(str) == RECALL_LEVEL_GLOBAL]
    global_rows = global_rows[
        global_rows["market_context_key"].map(is_na_market_context)
    ]
    if not global_rows.empty:
        ctx = str(
            global_rows["market_context_key"]
            .value_counts()
            .idxmax()
        )
        return global_rows, RECALL_LEVEL_GLOBAL, ctx

    return pd.DataFrame(), RECALL_LEVEL_NO_EVIDENCE, ""


def compute_recall_evidence(
    market_context_key: str,
    stock_pattern_key: str,
    recall_index: Optional[pd.DataFrame] = None,
    *,
    data_dir: Optional[Path | str] = None,
) -> RecallEvidenceResult:
    """
    Compute recall-based alpha from derived historical index (N3.7).
    Never promotes GLOBAL rows into EXACT/FAMILY evidence.
    """
    if recall_index is None:
        recall_index = load_recall_index(data_dir)

    pool = filter_recall_learning_pool(recall_index)
    matched_rows, level, matched_ctx = _resolve_recall_rows(
        pool, market_context_key, stock_pattern_key
    )

    if matched_rows.empty or level == RECALL_LEVEL_NO_EVIDENCE:
        return RecallEvidenceResult()

    t3 = _horizon_stats(matched_rows, "t3_return_pct", "outcome_status_t3")
    t5 = _horizon_stats(matched_rows, "t5_return_pct", "outcome_status_t5")
    t10 = _horizon_stats(matched_rows, "t10_return_pct", "outcome_status_t10")

    horizon_ev: Dict[int, float] = {}
    for horizon, stats in ((3, t3), (5, t5), (10, t10)):
        if stats["samples"] <= 0 or stats["median"] is None:
            continue
        synthetic = {
            "samples": stats["samples"],
            "win_rate_lower_bound_pct": stats["wlb"],
            "median_return_pct": stats["median"],
            "worst_return_pct": stats["worst"],
        }
        ev = compute_horizon_ev(synthetic)
        if ev is not None:
            horizon_ev[horizon] = ev

    raw_alpha = _blend_horizon_ev(horizon_ev)
    discount = RAS_EVIDENCE_DISCOUNT.get(level, 0.0)
    recall_alpha = shrink_toward_neutral(raw_alpha, discount)

    effective_samples = max(t3["samples"], t5["samples"], t10["samples"])
    confidence = compute_alpha_confidence(effective_samples, level)

    return RecallEvidenceResult(
        recall_source="RECALL_INDEX",
        recall_level=level,
        recall_samples=int(len(matched_rows)),
        recall_t3_samples=int(t3["samples"]),
        recall_t5_samples=int(t5["samples"]),
        recall_t10_samples=int(t10["samples"]),
        recall_mean_t3=t3["mean"],
        recall_mean_t5=t5["mean"],
        recall_mean_t10=t10["mean"],
        recall_win_rate_t3=t3["win_rate"],
        recall_win_rate_t5=t5["win_rate"],
        recall_win_rate_t10=t10["win_rate"],
        recall_confidence=round(confidence, 6),
        recall_alpha=round(recall_alpha, 4),
        recall_matched_dna=str(stock_pattern_key),
        recall_matched_context=matched_ctx,
    )


def compute_experience_shadow_score(
    baseline_score: float,
    recall: RecallEvidenceResult,
) -> float:
    """
    Blend production baseline with recall alpha. When recall confidence is zero,
    shadow equals baseline so only evidence-backed experience changes ranking.
    """
    w = _clip(recall.recall_confidence, 0.0, MAX_LEARNING_AUTHORITY)
    if w <= 0.0:
        return round(baseline_score, 4)
    return round((1.0 - w) * baseline_score + w * recall.recall_alpha, 2)


__all__ = [
    "NEUTRAL_RAS",
    "RECALL_LEVEL_NO_EVIDENCE",
    "RecallEvidenceResult",
    "compute_alpha_confidence",
    "compute_experience_shadow_score",
    "compute_horizon_ev",
    "compute_recall_evidence",
    "compute_technical_prior",
    "filter_recall_learning_pool",
    "load_recall_index",
    "market_context_family",
    "shrink_toward_neutral",
]
