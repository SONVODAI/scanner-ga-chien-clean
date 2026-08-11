"""
Evolution Trajectory Memory — independent research layer.

Builds coarse multi-day group trajectory features from group_evolution_history.csv,
links them to matured T3/T5/T10 outcomes, and exposes separate evidence for
Learning Insight. Does NOT feed Shadow, Baseline, or production ranking.
"""

from __future__ import annotations

import logging
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("learning_trajectory_memory")

MODULE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = MODULE_DIR / "brain"
DATA_DIR = MODULE_DIR / "data" / "earning_learning"

EVOLUTION_HISTORY_FILE = MODULE_DIR / "group_evolution_history.csv"
LIFECYCLE_FILE = DATA_DIR / "pattern_lifecycle.csv"
TRAJECTORY_KNOWLEDGE_FILE = DATA_DIR / "trajectory_knowledge.csv"
TRAJECTORY_LEDGER_FILE = BRAIN_DIR / "learning_trajectory_forward_ledger.csv"

TRAJECTORY_MIN_SAMPLES_QUALIFIED = 15
TRAJECTORY_SAMPLE_FULL = 30
TRAJECTORY_WILSON_Z = 1.2815515655446004

TRAJECTORY_EVIDENCE_QUALIFIED = "QUALIFIED"
TRAJECTORY_EVIDENCE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
TRAJECTORY_EVIDENCE_NONE = "NO_EVIDENCE"

LEDGER_VERSION = "1.0.0"
EVAL_MODE_FORWARD_FROZEN = "FORWARD_FROZEN"
EVAL_MODE_RECONSTRUCTED_AUDIT = "RECONSTRUCTED_AUDIT"

GROUP_RANK: Dict[str, int] = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,
    "PULL VỪA": 3,
    "PULL ĐẸP": 4,
    "MUA BREAK": 5,
    "CP MẠNH": 6,
    "GÀ TĂNG TỐC": 7,
}

TERMINAL_BUCKET: Dict[str, str] = {
    "THEO DÕI": "WATCH",
    "TÍCH LŨY": "ACCUM",
    "MUA EARLY": "EARLY",
    "PULL VỪA": "PULL_MID",
    "PULL ĐẸP": "PULL_GOOD",
    "MUA BREAK": "BREAK",
    "CP MẠNH": "STRONG",
    "GÀ TĂNG TỐC": "ACCEL",
}

TRAJECTORY_KNOWLEDGE_COLUMNS: Sequence[str] = (
    "TrajectoryPattern",
    "TrajectoryContext",
    "TrajectorySamplesT3",
    "TrajectorySamplesT5",
    "TrajectorySamplesT10",
    "TrajectoryWinRateT3",
    "TrajectoryWinRateT5",
    "TrajectoryWinRateT10",
    "TrajectoryMeanT3",
    "TrajectoryMeanT5",
    "TrajectoryMeanT10",
    "TrajectoryWinRateLowerBoundT5",
    "TrajectoryConfidence",
    "TrajectoryEvidenceStatus",
    "first_seen",
    "last_seen",
    "updated_at",
    "module_version",
)

TRAJECTORY_LEDGER_BASE_COLUMNS: Sequence[str] = (
    "session_date",
    "symbol",
    "TrajectoryPattern",
    "TrajectoryContext",
    "path_last_3",
    "path_last_5",
    "path_last_10",
    "transition_count",
    "upward_transitions",
    "downward_transitions",
    "sessions_in_current_group",
    "unique_groups_window",
    "behavior_class",
    "progression_speed",
    "TrajectoryScore",
    "TrajectoryEvidenceStatus",
    "TrajectoryReason",
    "TrajectorySamplesT5",
    "TrajectoryWinRateT5",
    "frozen_at",
    "ledger_version",
    "evaluation_mode",
)

TRAJECTORY_LEDGER_COLUMNS: Sequence[str] = tuple(
    dict.fromkeys(list(TRAJECTORY_LEDGER_BASE_COLUMNS) + ["snapshot_id", "observation_id"])
)

TRAJECTORY_IMMUTABLE_T0_FIELDS: Sequence[str] = (
    "snapshot_id",
    "session_date",
    "symbol",
    "TrajectoryPattern",
    "TrajectoryContext",
    "path_last_3",
    "path_last_5",
    "path_last_10",
    "transition_count",
    "upward_transitions",
    "downward_transitions",
    "sessions_in_current_group",
    "unique_groups_window",
    "behavior_class",
    "progression_speed",
    "TrajectoryScore",
    "TrajectoryEvidenceStatus",
    "TrajectoryReason",
    "TrajectorySamplesT5",
    "TrajectoryWinRateT5",
    "frozen_at",
    "ledger_version",
    "evaluation_mode",
)


@dataclass(frozen=True)
class TrajectoryFeatures:
    trajectory_pattern: str
    path_last_3: str
    path_last_5: str
    path_last_10: str
    transition_count: int
    upward_transitions: int
    downward_transitions: int
    sessions_in_current_group: int
    unique_groups_window: int
    behavior_class: str
    progression_speed: float
    t0_group: str
    terminal_bucket: str


@dataclass(frozen=True)
class TrajectoryEvidenceResult:
    trajectory_score: float
    trajectory_pattern: str
    trajectory_context: str
    trajectory_evidence_status: str
    trajectory_reason: str
    trajectory_samples_t3: int = 0
    trajectory_samples_t5: int = 0
    trajectory_samples_t10: int = 0
    trajectory_win_rate_t3: Optional[float] = None
    trajectory_win_rate_t5: Optional[float] = None
    trajectory_win_rate_t10: Optional[float] = None
    trajectory_mean_t3: Optional[float] = None
    trajectory_mean_t5: Optional[float] = None
    trajectory_mean_t10: Optional[float] = None
    trajectory_confidence: float = 0.0
    features: Optional[TrajectoryFeatures] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _compress_path(groups: Sequence[str]) -> str:
    if not groups:
        return ""
    out: List[str] = []
    for g in groups:
        bucket = TERMINAL_BUCKET.get(str(g), str(g))
        if not out or out[-1] != bucket:
            out.append(bucket)
    return ">".join(out)


def _wilson_lower_bound(wins: float, n: float, z: float = TRAJECTORY_WILSON_Z) -> float:
    if n <= 0:
        return float("nan")
    p = wins / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return (centre - margin) / denom * 100.0


def _sample_confidence(samples: int, *, minimum: int, full: int) -> float:
    if samples < minimum:
        return 0.0
    return _clip((samples - minimum) / max(1, full - minimum), 0.0, 1.0)


def classify_behavior_class(
    ranks: Sequence[int],
    groups: Sequence[str],
) -> str:
    if len(groups) < 2:
        return "FRESH"

    transitions = sum(1 for i in range(1, len(groups)) if groups[i] != groups[i - 1])
    unique_groups = len(set(groups))
    rank_steps = [abs(ranks[i] - ranks[i - 1]) for i in range(1, len(ranks)) if ranks[i] != ranks[i - 1]]
    max_step = max(rank_steps) if rank_steps else 0
    net_rank = ranks[-1] - ranks[0]

    if unique_groups == 1:
        return "STABLE"
    if transitions >= 3 or unique_groups >= 4:
        return "CHURN"
    if max_step >= 2:
        return "JUMP"
    if net_rank >= 2:
        return "CLIMB"
    if net_rank <= -2:
        return "FALL"

    early_buckets = {TERMINAL_BUCKET.get(g, g) for g in groups[: max(1, len(groups) // 2)]}
    terminal_bucket = TERMINAL_BUCKET.get(groups[-1], groups[-1])
    if early_buckets <= {"WATCH", "ACCUM"} and terminal_bucket in {"EARLY", "PULL_MID", "PULL_GOOD", "STRONG", "BREAK", "ACCEL"}:
        return "SETUP_ENTRY"

    peak = max(ranks)
    if ranks[-1] < peak - 1:
        return "REGRESSION"

    return "MIXED"


def compute_progression_speed(ranks: Sequence[int]) -> float:
    if len(ranks) < 2:
        return 0.0
    return float(ranks[-1] - ranks[0]) / float(len(ranks) - 1)


def build_trajectory_features_from_history(
    history: pd.DataFrame,
    *,
    t0_date: Any,
) -> Optional[TrajectoryFeatures]:
    """
    Build trajectory features using only rows with date <= t0_date.
    Does not use Persistence / evolution / recent_change / EvoFinal formulas.
    """
    if history is None or history.empty:
        return None

    df = history.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    t0 = pd.to_datetime(t0_date, errors="coerce")
    if pd.isna(t0):
        return None
    t0 = t0.date()

    df = df.dropna(subset=["date", "group"])
    df = df[df["date"] <= t0].sort_values("date")
    if df.empty:
        return None

    t0_row = df.iloc[-1]
    t0_group = str(t0_row["group"]).strip()
    terminal_bucket = TERMINAL_BUCKET.get(t0_group, "OTHER")

    window = df.tail(10)
    groups = [str(g).strip() for g in window["group"].tolist()]
    ranks = [GROUP_RANK.get(g, 0) for g in groups]

    path10_groups = groups
    path5_groups = groups[-5:] if len(groups) >= 5 else groups
    path3_groups = groups[-3:] if len(groups) >= 3 else groups

    transition_count = sum(
        1 for i in range(1, len(groups)) if groups[i] != groups[i - 1]
    )
    upward = sum(1 for i in range(1, len(ranks)) if ranks[i] > ranks[i - 1])
    downward = sum(1 for i in range(1, len(ranks)) if ranks[i] < ranks[i - 1])

    sessions_in_current = 1
    for g in reversed(groups[:-1]):
        if g == t0_group:
            sessions_in_current += 1
        else:
            break

    behavior = classify_behavior_class(ranks, groups)
    trajectory_pattern = f"{terminal_bucket}_{behavior}"
    speed = compute_progression_speed(ranks)

    return TrajectoryFeatures(
        trajectory_pattern=trajectory_pattern,
        path_last_3=_compress_path(path3_groups),
        path_last_5=_compress_path(path5_groups),
        path_last_10=_compress_path(path10_groups),
        transition_count=int(transition_count),
        upward_transitions=int(upward),
        downward_transitions=int(downward),
        sessions_in_current_group=int(sessions_in_current),
        unique_groups_window=int(len(set(groups))),
        behavior_class=behavior,
        progression_speed=round(speed, 4),
        t0_group=t0_group,
        terminal_bucket=terminal_bucket,
    )


def load_evolution_history(path: Path = EVOLUTION_HISTORY_FILE) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    return df


def load_trajectory_knowledge(
    path: Path = TRAJECTORY_KNOWLEDGE_FILE,
    *,
    min_samples: int = 1,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(TRAJECTORY_KNOWLEDGE_COLUMNS))
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if df.empty:
        return df
    for col in ("TrajectorySamplesT3", "TrajectorySamplesT5", "TrajectorySamplesT10"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if min_samples > 1 and "TrajectorySamplesT5" in df.columns:
        df = df[df["TrajectorySamplesT5"] >= min_samples].copy()
    return df.reset_index(drop=True)


def _trajectory_knowledge_lookup(
    knowledge_df: pd.DataFrame,
) -> Dict[Tuple[str, str], pd.Series]:
    lookup: Dict[Tuple[str, str], pd.Series] = {}
    if knowledge_df is None or knowledge_df.empty:
        return lookup
    for _, row in knowledge_df.iterrows():
        pattern = str(row.get("TrajectoryPattern", "")).strip()
        context = str(row.get("TrajectoryContext", "")).strip()
        if pattern:
            lookup[(pattern, context)] = row
    return lookup


def lookup_trajectory_knowledge_row(
    lookup: Mapping[Tuple[str, str], Any],
    trajectory_pattern: str,
    trajectory_context: str,
) -> Tuple[Optional[Mapping[str, Any]], str]:
    pattern = str(trajectory_pattern or "").strip()
    context = str(trajectory_context or "").strip()
    if not pattern:
        return None, "NO_TRAJECTORY"

    exact = lookup.get((pattern, context))
    if exact is not None:
        return dict(exact), "EXACT_CONTEXT"

    if context:
        parts = context.split("|")
        if len(parts) >= 2:
            family = "|".join(parts[:2])
            for (pat, ctx), row in lookup.items():
                if pat == pattern and ctx.startswith(family):
                    return dict(row), "FAMILY_CONTEXT"

    global_row = lookup.get((pattern, "NA|NA|NA"))
    if global_row is not None:
        return dict(global_row), "GLOBAL_TRAJECTORY"

    for (pat, _ctx), row in lookup.items():
        if pat == pattern:
            return dict(row), "PATTERN_ONLY"

    return None, "NO_TRAJECTORY"


def classify_trajectory_evidence_status(
    *,
    knowledge_row: Optional[Mapping[str, Any]],
    confidence: float,
) -> str:
    if knowledge_row is None:
        return TRAJECTORY_EVIDENCE_NONE
    samples_t5 = int(_safe_float(knowledge_row.get("TrajectorySamplesT5"), 0) or 0)
    if confidence > 0.0 and samples_t5 >= TRAJECTORY_MIN_SAMPLES_QUALIFIED:
        return TRAJECTORY_EVIDENCE_QUALIFIED
    if samples_t5 > 0:
        return TRAJECTORY_EVIDENCE_INSUFFICIENT
    return TRAJECTORY_EVIDENCE_NONE


def compute_trajectory_evidence(
    *,
    features: Optional[TrajectoryFeatures],
    trajectory_context: str,
    knowledge_row: Optional[Mapping[str, Any]] = None,
    match_mode: str = "",
) -> TrajectoryEvidenceResult:
    if features is None:
        return TrajectoryEvidenceResult(
            trajectory_score=50.0,
            trajectory_pattern="",
            trajectory_context=str(trajectory_context or ""),
            trajectory_evidence_status=TRAJECTORY_EVIDENCE_NONE,
            trajectory_reason="No evolution history available for trajectory research.",
            features=None,
        )

    samples_t3 = int(_safe_float(knowledge_row.get("TrajectorySamplesT3"), 0) or 0) if knowledge_row else 0
    samples_t5 = int(_safe_float(knowledge_row.get("TrajectorySamplesT5"), 0) or 0) if knowledge_row else 0
    samples_t10 = int(_safe_float(knowledge_row.get("TrajectorySamplesT10"), 0) or 0) if knowledge_row else 0

    wr_t3 = _safe_float(knowledge_row.get("TrajectoryWinRateT3")) if knowledge_row else float("nan")
    wr_t5 = _safe_float(knowledge_row.get("TrajectoryWinRateT5")) if knowledge_row else float("nan")
    wr_t10 = _safe_float(knowledge_row.get("TrajectoryWinRateT10")) if knowledge_row else float("nan")
    mean_t3 = _safe_float(knowledge_row.get("TrajectoryMeanT3")) if knowledge_row else float("nan")
    mean_t5 = _safe_float(knowledge_row.get("TrajectoryMeanT5")) if knowledge_row else float("nan")
    mean_t10 = _safe_float(knowledge_row.get("TrajectoryMeanT10")) if knowledge_row else float("nan")

    lower_t5 = _safe_float(knowledge_row.get("TrajectoryWinRateLowerBoundT5")) if knowledge_row else float("nan")
    if not math.isfinite(lower_t5) and math.isfinite(wr_t5):
        wins = wr_t5 / 100.0 * samples_t5 if samples_t5 > 0 else 0.0
        lower_t5 = _wilson_lower_bound(wins, float(samples_t5))

    confidence = _sample_confidence(
        samples_t5,
        minimum=TRAJECTORY_MIN_SAMPLES_QUALIFIED,
        full=TRAJECTORY_SAMPLE_FULL,
    )
    if knowledge_row is not None:
        stored_conf = _safe_float(knowledge_row.get("TrajectoryConfidence"))
        if math.isfinite(stored_conf):
            confidence = min(confidence, stored_conf)

    status = classify_trajectory_evidence_status(
        knowledge_row=knowledge_row,
        confidence=confidence,
    )

    evidence = lower_t5 if math.isfinite(lower_t5) else (
        wr_t5 * 0.85 if math.isfinite(wr_t5) else 50.0
    )
    if status != TRAJECTORY_EVIDENCE_QUALIFIED:
        score = 50.0
    else:
        score = 50.0 + (float(evidence) - 50.0) * confidence

    if status == TRAJECTORY_EVIDENCE_QUALIFIED:
        reason = (
            f"Trajectory {features.trajectory_pattern} n={samples_t5} "
            f"wr~{evidence:.0f} ({match_mode.lower() or 'matched'})."
        )
    elif status == TRAJECTORY_EVIDENCE_INSUFFICIENT:
        reason = (
            f"Trajectory pattern {features.trajectory_pattern} seen but "
            f"insufficient samples (n={samples_t5})."
        )
    else:
        reason = f"Trajectory {features.trajectory_pattern}; no historical evidence yet."

    return TrajectoryEvidenceResult(
        trajectory_score=round(_clip(score, 0.0, 100.0), 4),
        trajectory_pattern=features.trajectory_pattern,
        trajectory_context=str(trajectory_context or ""),
        trajectory_evidence_status=status,
        trajectory_reason=reason,
        trajectory_samples_t3=samples_t3,
        trajectory_samples_t5=samples_t5,
        trajectory_samples_t10=samples_t10,
        trajectory_win_rate_t3=float(wr_t3) if math.isfinite(wr_t3) else None,
        trajectory_win_rate_t5=float(wr_t5) if math.isfinite(wr_t5) else None,
        trajectory_win_rate_t10=float(wr_t10) if math.isfinite(wr_t10) else None,
        trajectory_mean_t3=float(mean_t3) if math.isfinite(mean_t3) else None,
        trajectory_mean_t5=float(mean_t5) if math.isfinite(mean_t5) else None,
        trajectory_mean_t10=float(mean_t10) if math.isfinite(mean_t10) else None,
        trajectory_confidence=round(confidence, 4),
        features=features,
    )


def build_trajectory_observation_rows(
    evolution_df: Optional[pd.DataFrame] = None,
    lifecycle_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Join evolution history at T0 to matured lifecycle outcomes (no leakage)."""
    evo = evolution_df if evolution_df is not None else load_evolution_history()
    if evo.empty:
        return pd.DataFrame()

    evo = evo.copy()
    evo["symbol"] = evo["symbol"].astype(str).str.strip().str.upper()
    evo["date"] = pd.to_datetime(evo["date"], errors="coerce").dt.date

    if lifecycle_df is None:
        if not LIFECYCLE_FILE.exists():
            return pd.DataFrame()
        lifecycle_df = pd.read_csv(LIFECYCLE_FILE, encoding="utf-8-sig", low_memory=False)

    lc = lifecycle_df.copy()
    lc["trade_date"] = pd.to_datetime(lc["trade_date"], errors="coerce").dt.date
    lc["symbol"] = lc["symbol"].astype(str).str.strip().str.upper()

    if "market_context_key" not in lc.columns:
        lc["market_context_key"] = "NA|NA|NA"
    else:
        lc["market_context_key"] = lc["market_context_key"].fillna("NA|NA|NA").astype(str)

    sym_hist = {
        s: g.sort_values("date")
        for s, g in evo.groupby("symbol")
    }

    rows: List[Dict[str, Any]] = []
    for _, lc_row in lc.iterrows():
        sym = lc_row["symbol"]
        t0 = lc_row["trade_date"]
        if sym not in sym_hist or pd.isna(t0):
            continue

        hist = sym_hist[sym].copy()
        features = build_trajectory_features_from_history(hist, t0_date=t0)
        if features is None:
            continue

        rows.append(
            {
                "symbol": sym,
                "trade_date": t0,
                "TrajectoryPattern": features.trajectory_pattern,
                "TrajectoryContext": lc_row["market_context_key"],
                "path_last_3": features.path_last_3,
                "path_last_5": features.path_last_5,
                "path_last_10": features.path_last_10,
                "transition_count": features.transition_count,
                "upward_transitions": features.upward_transitions,
                "downward_transitions": features.downward_transitions,
                "sessions_in_current_group": features.sessions_in_current_group,
                "unique_groups_window": features.unique_groups_window,
                "behavior_class": features.behavior_class,
                "progression_speed": features.progression_speed,
                "t3_return_pct": _safe_float(lc_row.get("t3_return_pct")),
                "t5_return_pct": _safe_float(lc_row.get("t5_return_pct")),
                "t10_return_pct": _safe_float(lc_row.get("t10_return_pct")),
                "t3_is_win": lc_row.get("t3_is_win"),
                "t5_is_win": lc_row.get("t5_is_win"),
                "t10_is_win": lc_row.get("t10_is_win"),
                "stock_pattern_key": lc_row.get("stock_pattern_key", ""),
                "market_regime": lc_row.get("market_regime", ""),
            }
        )

    return pd.DataFrame(rows)


def build_trajectory_knowledge(
    observation_rows: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    obs = observation_rows if observation_rows is not None else build_trajectory_observation_rows()
    if obs.empty:
        return pd.DataFrame(columns=list(TRAJECTORY_KNOWLEDGE_COLUMNS))

    rows: List[Dict[str, Any]] = []
    grouped = obs.groupby(["TrajectoryPattern", "TrajectoryContext"], dropna=False)

    for (pattern, context), g in grouped:
        def _agg_horizon(ret_col: str, win_col: str) -> Tuple[int, Optional[float], Optional[float], float]:
            sub = g[g[ret_col].apply(lambda x: math.isfinite(_safe_float(x)))]
            n = len(sub)
            if n == 0:
                return 0, None, None, 0.0
            wins = sub[win_col].apply(lambda x: str(x).lower() in {"true", "1", "yes"}).sum()
            wr = float(wins) / n * 100.0
            mean_ret = float(pd.to_numeric(sub[ret_col], errors="coerce").mean())
            return n, wr, mean_ret, float(wins)

        n3, wr3, mean3, wins3 = _agg_horizon("t3_return_pct", "t3_is_win")
        n5, wr5, mean5, wins5 = _agg_horizon("t5_return_pct", "t5_is_win")
        n10, wr10, mean10, wins10 = _agg_horizon("t10_return_pct", "t10_is_win")

        lower_t5 = _wilson_lower_bound(wins5, float(n5)) if n5 > 0 else float("nan")
        confidence = _sample_confidence(
            n5,
            minimum=TRAJECTORY_MIN_SAMPLES_QUALIFIED,
            full=TRAJECTORY_SAMPLE_FULL,
        )
        status = classify_trajectory_evidence_status(
            knowledge_row={"TrajectorySamplesT5": n5},
            confidence=confidence,
        )

        rows.append(
            {
                "TrajectoryPattern": pattern,
                "TrajectoryContext": context,
                "TrajectorySamplesT3": n3,
                "TrajectorySamplesT5": n5,
                "TrajectorySamplesT10": n10,
                "TrajectoryWinRateT3": wr3,
                "TrajectoryWinRateT5": wr5,
                "TrajectoryWinRateT10": wr10,
                "TrajectoryMeanT3": mean3,
                "TrajectoryMeanT5": mean5,
                "TrajectoryMeanT10": mean10,
                "TrajectoryWinRateLowerBoundT5": lower_t5 if math.isfinite(lower_t5) else None,
                "TrajectoryConfidence": round(confidence, 4),
                "TrajectoryEvidenceStatus": status,
                "first_seen": g["trade_date"].min(),
                "last_seen": g["trade_date"].max(),
                "updated_at": _utc_now_iso(),
                "module_version": "1.0.0",
            }
        )

    out = pd.DataFrame(rows, columns=list(TRAJECTORY_KNOWLEDGE_COLUMNS))
    return out.sort_values(
        ["TrajectorySamplesT5", "TrajectoryWinRateLowerBoundT5"],
        ascending=[False, False],
        kind="stable",
    ).reset_index(drop=True)


def persist_trajectory_knowledge(df: pd.DataFrame, path: Path = TRAJECTORY_KNOWLEDGE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_csv(df, path)


def rebuild_trajectory_knowledge() -> pd.DataFrame:
    obs = build_trajectory_observation_rows()
    knowledge = build_trajectory_knowledge(obs)
    persist_trajectory_knowledge(knowledge)
    logger.info(
        "Rebuilt trajectory knowledge: %s observations -> %s patterns",
        len(obs),
        len(knowledge),
    )
    return knowledge


def resolve_trajectory_evidence_for_symbol(
    symbol: str,
    session_date: str,
    *,
    market_context_key: str,
    evolution_df: Optional[pd.DataFrame] = None,
    knowledge_df: Optional[pd.DataFrame] = None,
) -> TrajectoryEvidenceResult:
    evo = evolution_df if evolution_df is not None else load_evolution_history()
    knowledge = knowledge_df if knowledge_df is not None else load_trajectory_knowledge(min_samples=1)

    sym = str(symbol or "").strip().upper()
    if not sym or evo.empty:
        return compute_trajectory_evidence(
            features=None,
            trajectory_context=market_context_key,
        )

    hist = evo[evo["symbol"].astype(str).str.upper() == sym].copy()
    features = build_trajectory_features_from_history(hist, t0_date=session_date)
    lookup = _trajectory_knowledge_lookup(knowledge)
    row, mode = lookup_trajectory_knowledge_row(
        lookup,
        features.trajectory_pattern if features else "",
        market_context_key,
    )
    return compute_trajectory_evidence(
        features=features,
        trajectory_context=market_context_key,
        knowledge_row=row,
        match_mode=mode,
    )


def make_snapshot_id(session_date: str, symbol: str) -> str:
    payload = f"{session_date}|{symbol}".encode("utf-8")
    import hashlib

    return hashlib.sha256(payload).hexdigest()[:16]


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


def _normalize_key(session_date: Any, symbol: Any) -> Tuple[str, str]:
    return str(session_date).strip(), str(symbol).strip().upper()


def load_trajectory_forward_ledger(
    *,
    evaluation_mode: Optional[str] = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = TRAJECTORY_LEDGER_FILE,
) -> pd.DataFrame:
    if not ledger_path.exists():
        return pd.DataFrame(columns=list(TRAJECTORY_LEDGER_COLUMNS))
    ledger = pd.read_csv(ledger_path, encoding="utf-8-sig", low_memory=False)
    if ledger.empty or evaluation_mode is None:
        return ledger
    return ledger[ledger["evaluation_mode"].astype(str) == evaluation_mode].copy()


def freeze_trajectory_t0_ledger(
    rows: pd.DataFrame,
    *,
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = TRAJECTORY_LEDGER_FILE,
) -> pd.DataFrame:
    ledger = load_trajectory_forward_ledger(evaluation_mode=None, ledger_path=ledger_path)
    if rows is None or rows.empty:
        return ledger

    existing_forward: Dict[Tuple[str, str], pd.Series] = {}
    if not ledger.empty:
        forward = ledger[ledger["evaluation_mode"] == EVAL_MODE_FORWARD_FROZEN]
        for _, existing in forward.iterrows():
            key = _normalize_key(existing["session_date"], existing["symbol"])
            existing_forward[key] = existing

    new_rows: List[Dict[str, Any]] = []
    frozen_at = _utc_now_iso()
    for _, row in rows.iterrows():
        session_date, symbol = _normalize_key(row.get("session_date"), row.get("symbol"))
        key = (session_date, symbol)
        if evaluation_mode == EVAL_MODE_FORWARD_FROZEN and key in existing_forward:
            continue

        out = {col: row.get(col, np.nan) for col in TRAJECTORY_LEDGER_BASE_COLUMNS}
        out.update(
            {
                "session_date": session_date,
                "symbol": symbol,
                "snapshot_id": make_snapshot_id(session_date, symbol),
                "observation_id": row.get("observation_id", ""),
                "frozen_at": frozen_at,
                "ledger_version": LEDGER_VERSION,
                "evaluation_mode": evaluation_mode,
            }
        )
        new_rows.append(out)

    if new_rows:
        ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
        ledger = ledger.drop_duplicates(
            subset=["session_date", "symbol", "evaluation_mode"],
            keep="first",
        )
        _atomic_write_csv(ledger, ledger_path)

    return ledger


def build_trajectory_forward_rows_for_session(
    candidate_df: pd.DataFrame,
    *,
    session_date: str,
    evolution_df: Optional[pd.DataFrame] = None,
    knowledge_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build immutable T0 trajectory ledger rows for a session."""
    if candidate_df is None or candidate_df.empty:
        return pd.DataFrame(columns=list(TRAJECTORY_LEDGER_COLUMNS))

    evo = evolution_df if evolution_df is not None else load_evolution_history()
    knowledge = knowledge_df if knowledge_df is not None else load_trajectory_knowledge(min_samples=1)
    rows: List[Dict[str, Any]] = []

    for _, rec in candidate_df.iterrows():
        symbol = str(rec.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        market_context_key = str(rec.get("market_context_key", "NA|NA|NA"))
        trajectory = resolve_trajectory_evidence_for_symbol(
            symbol,
            session_date,
            market_context_key=market_context_key,
            evolution_df=evo,
            knowledge_df=knowledge,
        )
        feat = trajectory.features
        rows.append(
            {
                "session_date": session_date,
                "symbol": symbol,
                "TrajectoryPattern": trajectory.trajectory_pattern,
                "TrajectoryContext": trajectory.trajectory_context,
                "path_last_3": feat.path_last_3 if feat else "",
                "path_last_5": feat.path_last_5 if feat else "",
                "path_last_10": feat.path_last_10 if feat else "",
                "transition_count": feat.transition_count if feat else 0,
                "upward_transitions": feat.upward_transitions if feat else 0,
                "downward_transitions": feat.downward_transitions if feat else 0,
                "sessions_in_current_group": feat.sessions_in_current_group if feat else 0,
                "unique_groups_window": feat.unique_groups_window if feat else 0,
                "behavior_class": feat.behavior_class if feat else "",
                "progression_speed": feat.progression_speed if feat else 0.0,
                "TrajectoryScore": trajectory.trajectory_score,
                "TrajectoryEvidenceStatus": trajectory.trajectory_evidence_status,
                "TrajectoryReason": trajectory.trajectory_reason,
                "TrajectorySamplesT5": trajectory.trajectory_samples_t5,
                "TrajectoryWinRateT5": trajectory.trajectory_win_rate_t5,
            }
        )

    return pd.DataFrame(rows, columns=list(TRAJECTORY_LEDGER_COLUMNS))


def run_trajectory_validation_report(
    observation_rows: Optional[pd.DataFrame] = None,
    knowledge_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Research validation before any scoring integration.
    Answers predictive lift, coverage, regime stability, and double-counting checks.
    """
    obs = observation_rows if observation_rows is not None else build_trajectory_observation_rows()
    knowledge = knowledge_df if knowledge_df is not None else build_trajectory_knowledge(obs)

    report: Dict[str, Any] = {
        "observation_rows": len(obs),
        "knowledge_rows": len(knowledge),
        "qualified_knowledge_rows": 0,
        "qualified_coverage_pct": 0.0,
        "templates": sorted(obs["TrajectoryPattern"].dropna().unique().tolist()) if not obs.empty else [],
        "template_counts": {},
        "horizon_stats": {},
        "lift_dna_vs_trajectory": {},
        "regime_stability": {},
        "double_counting_audit": {},
    }

    if obs.empty:
        return report

    report["template_counts"] = (
        obs["TrajectoryPattern"].value_counts().head(20).astype(int).to_dict()
    )

    if not knowledge.empty and "TrajectoryEvidenceStatus" in knowledge.columns:
        qualified = knowledge[
            knowledge["TrajectoryEvidenceStatus"].astype(str) == TRAJECTORY_EVIDENCE_QUALIFIED
        ]
        report["qualified_knowledge_rows"] = len(qualified)
        report["qualified_coverage_pct"] = round(
            len(qualified) / max(1, len(knowledge)) * 100.0,
            2,
        )

    for h, ret_col, win_col in (
        ("T3", "t3_return_pct", "t3_is_win"),
        ("T5", "t5_return_pct", "t5_is_win"),
        ("T10", "t10_return_pct", "t10_is_win"),
    ):
        sub = obs[obs[ret_col].apply(lambda x: math.isfinite(_safe_float(x)))]
        if sub.empty:
            continue
        wins = sub[win_col].apply(lambda x: str(x).lower() in {"true", "1", "yes"})
        report["horizon_stats"][h] = {
            "n": len(sub),
            "mean_return": round(float(pd.to_numeric(sub[ret_col], errors="coerce").mean()), 4),
            "win_rate_pct": round(float(wins.mean() * 100.0), 2),
        }

    # A/B: DNA-only (stock_pattern_key) vs DNA + TrajectoryPattern
    if "stock_pattern_key" in obs.columns:
        dna_means = obs.groupby("stock_pattern_key")["t5_return_pct"].mean()
        combo_means = obs.groupby(["stock_pattern_key", "TrajectoryPattern"])["t5_return_pct"].mean()
        dna_only_spread = float(dna_means.max() - dna_means.min()) if len(dna_means) > 1 else 0.0
        combo_spread = float(combo_means.max() - combo_means.min()) if len(combo_means) > 1 else 0.0
        report["lift_dna_vs_trajectory"] = {
            "dna_group_count": int(dna_means.shape[0]),
            "dna_trajectory_group_count": int(combo_means.shape[0]),
            "dna_only_mean_spread_t5": round(dna_only_spread, 4),
            "dna_plus_trajectory_mean_spread_t5": round(combo_spread, 4),
            "trajectory_adds_granularity": combo_means.shape[0] > dna_means.shape[0],
        }

    if "market_regime" in obs.columns:
        regime_stats = {}
        for regime, g in obs.groupby("market_regime"):
            sub = g[g["t5_return_pct"].apply(lambda x: math.isfinite(_safe_float(x)))]
            if len(sub) < 10:
                continue
            by_pat = sub.groupby("TrajectoryPattern")["t5_return_pct"].mean()
            if len(by_pat) < 2:
                continue
            regime_stats[str(regime)] = {
                "n": len(sub),
                "pattern_count": int(by_pat.shape[0]),
                "best_pattern": str(by_pat.idxmax()),
                "worst_pattern": str(by_pat.idxmin()),
                "spread_pp": round(float(by_pat.max() - by_pat.min()), 4),
            }
        report["regime_stability"] = regime_stats

    # Double-counting: our features vs production evolution summaries (different formulas)
    report["double_counting_audit"] = {
        "uses_persistence_field": False,
        "uses_evolution_field": False,
        "uses_recent_change_field": False,
        "uses_evofinal_field": False,
        "uses_storm_dna_accel": False,
        "uses_storm_obv_accel": False,
        "feature_semantics": "behavior_class and progression_speed use 10d window; not same as 5d Persistence/evolution",
        "production_overlap_risk": "LOW for Insight research; Storm/EvoFinal still consume same CSV operationally",
    }

    return report


__all__ = [
    "TRAJECTORY_EVIDENCE_INSUFFICIENT",
    "TRAJECTORY_EVIDENCE_NONE",
    "TRAJECTORY_EVIDENCE_QUALIFIED",
    "TRAJECTORY_IMMUTABLE_T0_FIELDS",
    "TRAJECTORY_KNOWLEDGE_COLUMNS",
    "TRAJECTORY_KNOWLEDGE_FILE",
    "TRAJECTORY_LEDGER_FILE",
    "TrajectoryEvidenceResult",
    "TrajectoryFeatures",
    "build_trajectory_features_from_history",
    "build_trajectory_knowledge",
    "build_trajectory_observation_rows",
    "classify_trajectory_evidence_status",
    "compute_trajectory_evidence",
    "freeze_trajectory_t0_ledger",
    "load_evolution_history",
    "load_trajectory_forward_ledger",
    "load_trajectory_knowledge",
    "lookup_trajectory_knowledge_row",
    "rebuild_trajectory_knowledge",
    "resolve_trajectory_evidence_for_symbol",
    "run_trajectory_validation_report",
    "build_trajectory_forward_rows_for_session",
]
