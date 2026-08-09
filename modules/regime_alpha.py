"""
Regime Alpha Engine — Level 4 learned expected-value score (N2).

Computes RegimeAlphaScore (RAS) from historical pattern/continuation knowledge
conditioned on (stock DNA × market regime).  Standalone module: not wired into
production recommendation paths yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants (Level-4 approved design, with documented corrections)
# ---------------------------------------------------------------------------

NEUTRAL_RAS = 50.0

HORIZON_WEIGHTS: Dict[int, float] = {3: 0.25, 5: 0.45, 10: 0.30}

SAMPLE_MIN = 5
SAMPLE_FULL = 20
MAX_LEARNING_AUTHORITY = 0.85
RECENCY_HALF_LIFE_DAYS = 180.0
RECENCY_FLOOR = 0.5

CONTEXT_AUTHORITY: Dict[str, float] = {
    "EXACT": 1.00,
    "FAMILY": 0.65,
    "GLOBAL_DNA": 0.35,
    "NONE": 0.00,
}

# Shrink RAS toward neutral (50), not toward zero.
RAS_EVIDENCE_DISCOUNT: Dict[str, float] = {
    "EXACT": 1.00,
    "FAMILY": 0.90,
    "GLOBAL_DNA": 0.75,
    "NONE": 0.00,
}

EXACT_MIN_SAMPLES = 5

RowLike = Union[Mapping[str, Any], pd.Series]


@dataclass(frozen=True)
class ContextMatchResult:
    level: str
    market_context_key: str
    stock_pattern_key: str
    pattern_rows_by_horizon: Dict[int, Mapping[str, Any]] = field(default_factory=dict)
    continuation_row: Optional[Mapping[str, Any]] = None
    effective_samples: int = 0
    context_authority: float = 0.0
    ras_evidence_discount: float = 0.0
    matched_context_key: str = ""


@dataclass(frozen=True)
class RegimeAlphaResult:
    regime_alpha_score: float
    regime_alpha_confidence: float
    context_match_level: str
    effective_samples: int
    matched_market_context: str
    horizon_ev: Dict[int, float] = field(default_factory=dict)
    continuation_boost: float = 0.0
    raw_ras_before_discount: float = NEUTRAL_RAS
    technical_prior_score: Optional[float] = None


# ---------------------------------------------------------------------------
# Safe numeric helpers
# ---------------------------------------------------------------------------


def _optional_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Parse float; distinguish missing (None/NaN) from valid 0.0."""
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


def _optional_int(value: Any, default: int = 0) -> int:
    parsed = _optional_float(value, default=None)
    if parsed is None:
        return default
    return int(parsed)


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _winsorize(value: float, low: float, high: float) -> float:
    return _clip(value, low, high)


# ---------------------------------------------------------------------------
# Context family (P2/P4 semantics — forecast + market buckets, ignore breadth)
# ---------------------------------------------------------------------------


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
    """Apply fallback discount: move evidence toward RAS=50, not toward 0."""
    return NEUTRAL_RAS + (score - NEUTRAL_RAS) * discount


# ---------------------------------------------------------------------------
# 1) compute_horizon_ev
# ---------------------------------------------------------------------------


def compute_horizon_ev(
    pattern_row: Optional[RowLike],
    *,
    horizon: Optional[int] = None,
) -> Optional[float]:
    """
    Expected-value sub-score for one horizon row from pattern_knowledge.

    Returns None when the row is missing or has no usable samples — missing
    horizons must not be treated as bad outcomes.
    """
    if pattern_row is None:
        return None

    row = dict(pattern_row)
    samples = _optional_int(row.get("samples"), 0)
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
    # 0.0 is a valid return — only None/NaN/absent key is missing.

    dd = _optional_float(row.get("avg_max_drawdown_pct"))
    worst = _optional_float(row.get("worst_return_pct"))

    win_component = (wlb - NEUTRAL_RAS) / NEUTRAL_RAS

    med_winsor = _winsorize(median_ret, -8.0, 12.0)
    return_component = med_winsor / 12.0

    # Drawdown fields are typically negative percentages; use magnitude as penalty.
    if dd is not None:
        downside_component = _clip(-dd, 0.0, 15.0) / 15.0
    else:
        downside_component = 0.0

    if worst is not None:
        tail_penalty = _clip(-worst, 0.0, 10.0) / 10.0
    else:
        tail_penalty = 0.0

    ev = (
        NEUTRAL_RAS
        + 22.0 * win_component
        + 28.0 * return_component
        - 12.0 * downside_component
        - 8.0 * tail_penalty
    )
    return _clip(ev, 0.0, 100.0)


# ---------------------------------------------------------------------------
# Continuation overlay (applied once after horizon blend — not per horizon)
# ---------------------------------------------------------------------------


def _continuation_boost(continuation_row: Optional[RowLike]) -> float:
    if continuation_row is None:
        return 0.0

    row = dict(continuation_row)
    samples_t10 = _optional_int(row.get("samples_t10"), 0)
    if samples_t10 < 5:
        return 0.0

    boost = 0.0
    score = _optional_float(row.get("continuation_score"))
    lower = _optional_float(row.get("t3_to_t10_lower_bound_pct"))

    if score is not None:
        boost += _clip((score - NEUTRAL_RAS) / NEUTRAL_RAS, -1.0, 1.0) * 6.0
    if lower is not None:
        boost += _clip((lower - NEUTRAL_RAS) / NEUTRAL_RAS, -1.0, 1.0) * 4.0

    return boost


# ---------------------------------------------------------------------------
# 3) resolve_context_match
# ---------------------------------------------------------------------------


def _iter_pattern_rows(
    pattern_knowledge: Optional[pd.DataFrame],
) -> Iterable[Mapping[str, Any]]:
    if pattern_knowledge is None or pattern_knowledge.empty:
        return []
    return (dict(row) for _, row in pattern_knowledge.iterrows())


def _build_pattern_lookup(
    pattern_knowledge: Optional[pd.DataFrame],
) -> Dict[Tuple[str, str, int], Mapping[str, Any]]:
    lookup: Dict[Tuple[str, str, int], Mapping[str, Any]] = {}
    for row in _iter_pattern_rows(pattern_knowledge):
        ctx = str(row.get("market_context_key", ""))
        stock = str(row.get("stock_pattern_key", ""))
        horizon = _optional_int(row.get("horizon"), 0)
        if not stock or horizon <= 0:
            continue
        lookup[(ctx, stock, horizon)] = row
    return lookup


def _build_continuation_lookup(
    continuation_knowledge: Optional[pd.DataFrame],
) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    lookup: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if continuation_knowledge is None or continuation_knowledge.empty:
        return lookup
    for _, row in continuation_knowledge.iterrows():
        ctx = str(row.get("market_context_key", ""))
        stock = str(row.get("stock_pattern_key", ""))
        if stock:
            lookup[(ctx, stock)] = dict(row)
    return lookup


def _collect_horizon_rows_exact(
    lookup: Dict[Tuple[str, str, int], Mapping[str, Any]],
    market_context_key: str,
    stock_pattern_key: str,
) -> Dict[int, Mapping[str, Any]]:
    out: Dict[int, Mapping[str, Any]] = {}
    for horizon in HORIZON_WEIGHTS:
        row = lookup.get((market_context_key, stock_pattern_key, horizon))
        if row is not None and _optional_int(row.get("samples"), 0) > 0:
            out[horizon] = row
    return out


def _collect_horizon_rows_family(
    lookup: Dict[Tuple[str, str, int], Mapping[str, Any]],
    market_context_key: str,
    stock_pattern_key: str,
) -> Dict[int, Mapping[str, Any]]:
    target = market_context_family(market_context_key)
    out: Dict[int, Mapping[str, Any]] = {}
    for horizon in HORIZON_WEIGHTS:
        candidates = [
            row
            for (ctx, stock, h), row in lookup.items()
            if (
                stock == stock_pattern_key
                and h == horizon
                and market_context_family(ctx) == target
                and ctx != market_context_key
            )
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda r: _optional_int(r.get("samples"), 0))
        if _optional_int(best.get("samples"), 0) > 0:
            out[horizon] = best
    return out


def _collect_horizon_rows_global(
    lookup: Dict[Tuple[str, str, int], Mapping[str, Any]],
    stock_pattern_key: str,
) -> Dict[int, Mapping[str, Any]]:
    out: Dict[int, Mapping[str, Any]] = {}
    for horizon in HORIZON_WEIGHTS:
        candidates = [
            row
            for (ctx, stock, h), row in lookup.items()
            if (
                stock == stock_pattern_key
                and h == horizon
                and is_na_market_context(ctx)
            )
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda r: _optional_int(r.get("samples"), 0))
        if _optional_int(best.get("samples"), 0) > 0:
            out[horizon] = best
    return out


def _effective_samples(rows_by_horizon: Dict[int, Mapping[str, Any]]) -> int:
    if not rows_by_horizon:
        return 0
    return max(_optional_int(row.get("samples"), 0) for row in rows_by_horizon.values())


def _latest_last_seen(rows_by_horizon: Dict[int, Mapping[str, Any]]) -> Optional[date]:
    dates: list[date] = []
    for row in rows_by_horizon.values():
        raw = row.get("last_seen")
        if raw is None or (isinstance(raw, float) and math.isnan(raw)):
            continue
        parsed = pd.to_datetime(raw, errors="coerce")
        if pd.notna(parsed):
            dates.append(parsed.date())
    return max(dates) if dates else None


def _lookup_continuation(
    lookup: Dict[Tuple[str, str], Mapping[str, Any]],
    market_context_key: str,
    stock_pattern_key: str,
    level: str,
) -> Tuple[Optional[Mapping[str, Any]], str]:
    if not lookup:
        return None, ""

    exact = lookup.get((market_context_key, stock_pattern_key))
    if exact is not None:
        return exact, "EXACT"

    if level != "FAMILY":
        if level == "GLOBAL_DNA":
            candidates = [
                row
                for (ctx, stock), row in lookup.items()
                if stock == stock_pattern_key and is_na_market_context(ctx)
            ]
            if candidates:
                best = max(
                    candidates,
                    key=lambda r: _optional_int(r.get("samples_t10"), 0),
                )
                return best, "GLOBAL_DNA"
        return None, ""

    target = market_context_family(market_context_key)
    candidates = [
        row
        for (ctx, stock), row in lookup.items()
        if (
            stock == stock_pattern_key
            and market_context_family(ctx) == target
        )
    ]
    if candidates:
        best = max(candidates, key=lambda r: _optional_int(r.get("samples_t10"), 0))
        return best, "FAMILY"

    return None, ""


def resolve_context_match(
    market_context_key: str,
    stock_pattern_key: str,
    pattern_knowledge: Optional[pd.DataFrame] = None,
    continuation_knowledge: Optional[pd.DataFrame] = None,
) -> ContextMatchResult:
    """
    EXACT → FAMILY → GLOBAL_DNA → NONE with P2/P4 family semantics.
    """
    market_context_key = str(market_context_key or "").strip()
    stock_pattern_key = str(stock_pattern_key or "").strip()

    if not stock_pattern_key:
        return ContextMatchResult(
            level="NONE",
            market_context_key=market_context_key,
            stock_pattern_key=stock_pattern_key,
        )

    pattern_lookup = _build_pattern_lookup(pattern_knowledge)
    cont_lookup = _build_continuation_lookup(continuation_knowledge)

    exact_rows = _collect_horizon_rows_exact(
        pattern_lookup, market_context_key, stock_pattern_key
    )
    exact_samples = _effective_samples(exact_rows)
    exact_h5 = exact_rows.get(5)
    exact_h5_n = (
        _optional_int(exact_h5.get("samples"), 0) if exact_h5 is not None else 0
    )

    if exact_h5_n >= EXACT_MIN_SAMPLES or (
        exact_samples >= EXACT_MIN_SAMPLES and exact_rows
    ):
        cont_row, _ = _lookup_continuation(
            cont_lookup, market_context_key, stock_pattern_key, "EXACT"
        )
        return ContextMatchResult(
            level="EXACT",
            market_context_key=market_context_key,
            stock_pattern_key=stock_pattern_key,
            pattern_rows_by_horizon=exact_rows,
            continuation_row=cont_row,
            effective_samples=exact_samples,
            context_authority=CONTEXT_AUTHORITY["EXACT"],
            ras_evidence_discount=RAS_EVIDENCE_DISCOUNT["EXACT"],
            matched_context_key=market_context_key,
        )

    # Partial exact (some horizons) — still EXACT level but lower sample count
    if exact_rows:
        cont_row, _ = _lookup_continuation(
            cont_lookup, market_context_key, stock_pattern_key, "EXACT"
        )
        return ContextMatchResult(
            level="EXACT",
            market_context_key=market_context_key,
            stock_pattern_key=stock_pattern_key,
            pattern_rows_by_horizon=exact_rows,
            continuation_row=cont_row,
            effective_samples=exact_samples,
            context_authority=CONTEXT_AUTHORITY["EXACT"],
            ras_evidence_discount=RAS_EVIDENCE_DISCOUNT["EXACT"],
            matched_context_key=market_context_key,
        )

    family_rows = _collect_horizon_rows_family(
        pattern_lookup, market_context_key, stock_pattern_key
    )
    if family_rows:
        matched_ctx = str(
            family_rows.get(5, next(iter(family_rows.values()))).get(
                "market_context_key", ""
            )
        )
        cont_row, _ = _lookup_continuation(
            cont_lookup, market_context_key, stock_pattern_key, "FAMILY"
        )
        return ContextMatchResult(
            level="FAMILY",
            market_context_key=market_context_key,
            stock_pattern_key=stock_pattern_key,
            pattern_rows_by_horizon=family_rows,
            continuation_row=cont_row,
            effective_samples=_effective_samples(family_rows),
            context_authority=CONTEXT_AUTHORITY["FAMILY"],
            ras_evidence_discount=RAS_EVIDENCE_DISCOUNT["FAMILY"],
            matched_context_key=matched_ctx,
        )

    global_rows = _collect_horizon_rows_global(pattern_lookup, stock_pattern_key)
    if global_rows:
        matched_ctx = str(
            global_rows.get(5, next(iter(global_rows.values()))).get(
                "market_context_key", ""
            )
        )
        cont_row, _ = _lookup_continuation(
            cont_lookup, market_context_key, stock_pattern_key, "GLOBAL_DNA"
        )
        return ContextMatchResult(
            level="GLOBAL_DNA",
            market_context_key=market_context_key,
            stock_pattern_key=stock_pattern_key,
            pattern_rows_by_horizon=global_rows,
            continuation_row=cont_row,
            effective_samples=_effective_samples(global_rows),
            context_authority=CONTEXT_AUTHORITY["GLOBAL_DNA"],
            ras_evidence_discount=RAS_EVIDENCE_DISCOUNT["GLOBAL_DNA"],
            matched_context_key=matched_ctx,
        )

    return ContextMatchResult(
        level="NONE",
        market_context_key=market_context_key,
        stock_pattern_key=stock_pattern_key,
    )


# ---------------------------------------------------------------------------
# 4) compute_alpha_confidence
# ---------------------------------------------------------------------------


def compute_alpha_confidence(
    effective_samples: int,
    context_level: str,
    *,
    last_seen: Optional[Union[date, str, datetime]] = None,
    as_of: Optional[date] = None,
) -> float:
    """
    sample_weight × context_authority × recency, capped at MAX_LEARNING_AUTHORITY.
    """
    if context_level == "NONE" or effective_samples <= 0:
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

    recency = RECENCY_FLOOR
    if last_seen is not None:
        parsed = pd.to_datetime(last_seen, errors="coerce")
        if pd.notna(parsed):
            ref = as_of or date.today()
            days = max(0, (ref - parsed.date()).days)
            recency = max(
                RECENCY_FLOOR,
                math.exp(-days / RECENCY_HALF_LIFE_DAYS),
            )

    confidence = sample_weight * context_auth * recency
    return _clip(confidence, 0.0, MAX_LEARNING_AUTHORITY)


# ---------------------------------------------------------------------------
# 2) compute_regime_alpha_score
# ---------------------------------------------------------------------------


def _blend_horizon_ev(horizon_ev: Dict[int, float]) -> float:
    if not horizon_ev:
        return NEUTRAL_RAS

    weight_sum = sum(HORIZON_WEIGHTS[h] for h in horizon_ev if h in HORIZON_WEIGHTS)
    if weight_sum <= 0:
        return NEUTRAL_RAS

    blended = sum(
        horizon_ev[h] * HORIZON_WEIGHTS[h] for h in horizon_ev if h in HORIZON_WEIGHTS
    ) / weight_sum
    return _clip(blended, 0.0, 100.0)


def compute_regime_alpha_score(
    market_context_key: str,
    stock_pattern_key: str,
    pattern_knowledge: Optional[pd.DataFrame] = None,
    continuation_knowledge: Optional[pd.DataFrame] = None,
    *,
    as_of: Optional[date] = None,
) -> RegimeAlphaResult:
    match = resolve_context_match(
        market_context_key,
        stock_pattern_key,
        pattern_knowledge=pattern_knowledge,
        continuation_knowledge=continuation_knowledge,
    )

    if match.level == "NONE":
        return RegimeAlphaResult(
            regime_alpha_score=NEUTRAL_RAS,
            regime_alpha_confidence=0.0,
            context_match_level="NONE",
            effective_samples=0,
            matched_market_context="",
            raw_ras_before_discount=NEUTRAL_RAS,
        )

    horizon_ev: Dict[int, float] = {}
    for horizon, row in match.pattern_rows_by_horizon.items():
        ev = compute_horizon_ev(row, horizon=horizon)
        if ev is not None:
            horizon_ev[horizon] = ev

    if not horizon_ev:
        return RegimeAlphaResult(
            regime_alpha_score=NEUTRAL_RAS,
            regime_alpha_confidence=0.0,
            context_match_level=match.level,
            effective_samples=match.effective_samples,
            matched_market_context=match.matched_context_key,
            raw_ras_before_discount=NEUTRAL_RAS,
        )

    blended = _blend_horizon_ev(horizon_ev)
    cont_boost = _continuation_boost(match.continuation_row)
    raw_ras = _clip(blended + cont_boost, 0.0, 100.0)
    discounted = shrink_toward_neutral(raw_ras, match.ras_evidence_discount)

    last_seen = _latest_last_seen(match.pattern_rows_by_horizon)
    confidence = compute_alpha_confidence(
        match.effective_samples,
        match.level,
        last_seen=last_seen,
        as_of=as_of,
    )

    return RegimeAlphaResult(
        regime_alpha_score=discounted,
        regime_alpha_confidence=confidence,
        context_match_level=match.level,
        effective_samples=match.effective_samples,
        matched_market_context=match.matched_context_key,
        horizon_ev=horizon_ev,
        continuation_boost=cont_boost,
        raw_ras_before_discount=raw_ras,
    )


# ---------------------------------------------------------------------------
# 5) compute_technical_prior
# ---------------------------------------------------------------------------

_DEFAULT_GROUP_QUALITY: Dict[str, float] = {
    "CP MẠNH": 85.0,
    "GÀ TĂNG TỐC": 80.0,
    "PULL ĐẸP": 78.0,
    "PULL VỪA": 70.0,
    "MUA EARLY": 68.0,
    "MUA BREAK": 72.0,
    "THEO DÕI": 45.0,
}


def _normalize_rsi(rsi: Optional[float]) -> float:
    if rsi is None:
        return NEUTRAL_RAS
    return _clip(100.0 - min(abs(rsi - 62.0) * 2.6, 100.0), 0.0, 100.0)


def _normalize_obv(obv_status: Any) -> float:
    text = str(obv_status or "").strip().upper()
    if text in {"UP", "🟢", "GREEN", "BULL", "TANG"}:
        return 75.0
    if text in {"DOWN", "🔴", "RED", "BEAR", "GIAM"}:
        return 25.0
    return NEUTRAL_RAS


def _normalize_group_quality(group: Any) -> float:
    text = str(group or "").strip().upper()
    if not text:
        return NEUTRAL_RAS
    for key, score in _DEFAULT_GROUP_QUALITY.items():
        if key.upper() in text or text in key.upper():
            return score
    if any(token in text for token in ("YẾU", "YEu", "TRÁNH", "TRANH")):
        return 20.0
    return NEUTRAL_RAS


def compute_technical_prior(
    row: RowLike,
    *,
    pattern_match_score: Optional[float] = None,
) -> float:
    """
    Technical prior (0–100) from leader/brain fields — supporting evidence only.
    """
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

    pms = pattern_match_score
    if pms is None:
        pms = _optional_float(data.get("pattern_match_score"))
    if pms is not None:
        components.append((_clip(pms, 0.0, 100.0), 0.15))

    group = data.get("current_group", data.get("group"))
    components.append((_normalize_group_quality(group), 0.10))

    if not components:
        return NEUTRAL_RAS

    total_w = sum(w for _, w in components)
    return round(sum(v * w for v, w in components) / total_w, 2)


def compute_final_recommendation_score(
    regime_alpha_score: float,
    technical_prior_score: float,
    regime_alpha_confidence: float,
) -> float:
    """Blend helper for future N5 wiring (not used in production yet)."""
    w = _clip(regime_alpha_confidence, 0.0, MAX_LEARNING_AUTHORITY)
    return round((1.0 - w) * technical_prior_score + w * regime_alpha_score, 2)


__all__ = [
    "NEUTRAL_RAS",
    "HORIZON_WEIGHTS",
    "ContextMatchResult",
    "RegimeAlphaResult",
    "compute_horizon_ev",
    "compute_regime_alpha_score",
    "resolve_context_match",
    "compute_alpha_confidence",
    "compute_technical_prior",
    "compute_final_recommendation_score",
    "market_context_family",
    "is_na_market_context",
    "shrink_toward_neutral",
]
