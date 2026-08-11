"""
Immutable forward-evaluation ledger for Regime Alpha shadow (N3.7B + N3.7C).

Preserves T0 baseline vs experience-shadow decisions, then attaches matured
T3/T5/T10 outcomes without ever recomputing the original decision fields.

N3.7C: FORWARD_FROZEN ledger rows are written only via finalize_forward_shadow_snapshot()
after the canonical trading-session gate — not during ordinary update_memory reruns.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.regime_alpha import market_context_family, load_recall_index
from modules.regime_alpha_shadow import SHADOW_COLUMNS, build_shadow_with_recall
from modules.regime_recall_index import _is_weekend

logger = logging.getLogger("regime_alpha_forward_eval")

MODULE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = MODULE_DIR / "brain"
DATA_DIR = MODULE_DIR / "data" / "earning_learning"

LEDGER_FILE = BRAIN_DIR / "regime_alpha_shadow_ledger.csv"
OUTCOMES_FILE = BRAIN_DIR / "regime_alpha_forward_outcomes.csv"
LIFECYCLE_FILE = DATA_DIR / "pattern_lifecycle.csv"

LEDGER_VERSION = "1.0.0"
OUTCOME_VERSION = "1.0.0"

EVAL_MODE_FORWARD_FROZEN = "FORWARD_FROZEN"
EVAL_MODE_RECONSTRUCTED_AUDIT = "RECONSTRUCTED_AUDIT"

REGIME_LABEL_GLOBAL = "CONTEXT_FREE_PRIOR"

IMMUTABLE_T0_FIELDS: Sequence[str] = (
    "snapshot_id",
    "session_date",
    "symbol",
    "PureBaselineScore",
    "BaselineScore",
    "BaselineRank",
    "ShadowFinalScore",
    "ShadowExperienceScore",
    "ShadowExperienceRank",
    "ProductionRank",
    "RankDelta",
    "ScoreDelta",
    "ShadowMovement",
    "PatternKnowledgeAdj",
    "ContinuationAdj",
    "HorizonAdj",
    "RecallComponent",
    "TechnicalPrior",
    "stock_pattern_key",
    "market_context_key",
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
    "movement_class",
    "frozen_at",
    "ledger_version",
    "evaluation_mode",
)

LEDGER_EXTRA_COLUMNS: Sequence[str] = (
    "snapshot_id",
    "frozen_at",
    "ledger_version",
    "evaluation_mode",
    "movement_class",
    "observation_id",
)

LEDGER_COLUMNS: Sequence[str] = tuple(
    dict.fromkeys(list(SHADOW_COLUMNS) + list(LEDGER_EXTRA_COLUMNS))
)

OUTCOME_COLUMNS: Sequence[str] = (
    "session_date",
    "symbol",
    "snapshot_id",
    "observation_id",
    "ActualT3Return",
    "ActualT5Return",
    "ActualT10Return",
    "outcome_status_t3",
    "outcome_status_t5",
    "outcome_status_t10",
    "matured_at_t3",
    "matured_at_t5",
    "matured_at_t10",
    "corporate_action_flag",
    "outcome_version",
)

CORPORATE_ACTION_SUSPECT_THRESHOLD_PCT = 25.0


@dataclass(frozen=True)
class ScorecardSlice:
    label: str
    n: int = 0
    win_rate_t3: Optional[float] = None
    mean_t3: Optional[float] = None
    median_t3: Optional[float] = None
    win_rate_t5: Optional[float] = None
    mean_t5: Optional[float] = None
    median_t5: Optional[float] = None
    win_rate_t10: Optional[float] = None
    mean_t10: Optional[float] = None
    median_t10: Optional[float] = None
    bad_pick_rate_t3: Optional[float] = None
    worst_return_t3: Optional[float] = None
    avg_rank_winners_t3: Optional[float] = None
    avg_rank_losers_t3: Optional[float] = None


@dataclass(frozen=True)
class ForwardScorecard:
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN
    sessions: int = 0
    candidates: int = 0
    baseline_top5: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("baseline_top5"))
    baseline_top10: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("baseline_top10"))
    baseline_top20: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("baseline_top20"))
    shadow_top5: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("shadow_top5"))
    shadow_top10: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("shadow_top10"))
    shadow_top20: ScorecardSlice = field(default_factory=lambda: ScorecardSlice("shadow_top20"))
    production_top5: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("production_top5")
    )
    production_top10: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("production_top10")
    )
    production_top20: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("production_top20")
    )
    learning_lift_top10_mean_t3: Optional[float] = None
    cohort_active_promoted: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("ACTIVE_PROMOTED")
    )
    cohort_active_demoted: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("ACTIVE_DEMOTED")
    )
    cohort_passive_moved: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("PASSIVE_MOVED")
    )
    cohort_unchanged: ScorecardSlice = field(
        default_factory=lambda: ScorecardSlice("UNCHANGED")
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _load_csv(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=list(columns))
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    for col in columns:
        if col not in df.columns:
            df[col] = np.nan
    return df[list(columns)]


def make_snapshot_id(session_date: str, symbol: str) -> str:
    """Deterministic T0 identity for joins — stable across reruns."""
    payload = f"{str(session_date).strip()}|{str(symbol).strip().upper()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _normalize_key(session_date: Any, symbol: Any) -> Tuple[str, str]:
    return str(session_date).strip(), str(symbol).strip().upper()


def classify_movement_class(row: Mapping[str, Any]) -> str:
    score_delta = float(pd.to_numeric(row.get("ScoreDelta"), errors="coerce") or 0)
    movement = str(row.get("ShadowMovement", "")).strip().upper()
    learning_active = (
        abs(float(pd.to_numeric(row.get("PatternKnowledgeAdj"), errors="coerce") or 0)) > 0.01
        or abs(float(pd.to_numeric(row.get("ContinuationAdj"), errors="coerce") or 0)) > 0.01
        or abs(float(pd.to_numeric(row.get("HorizonAdj"), errors="coerce") or 0)) > 0.01
        or float(pd.to_numeric(row.get("RecallConfidence"), errors="coerce") or 0) > 0
    )
    if learning_active and score_delta > 0.01:
        return "ACTIVE_PROMOTED"
    if learning_active and score_delta < -0.01:
        return "ACTIVE_DEMOTED"
    if movement in {"PROMOTED", "DEMOTED"}:
        return "PASSIVE_MOVED"
    return "UNCHANGED"


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _outcome_status_from_value(value: Any) -> str:
    return "READY" if _finite_or_none(value) is not None else "PENDING"


def _corporate_action_flag(
    t3: Optional[float],
    t5: Optional[float],
    t10: Optional[float],
) -> str:
    """Flag suspected mechanical anomalies — never adjust returns here."""
    for label, val in (("T3", t3), ("T5", t5), ("T10", t10)):
        if val is not None and abs(val) >= CORPORATE_ACTION_SUSPECT_THRESHOLD_PCT:
            return f"SUSPECT_EXTREME_{label}"
    return ""


def _lookup_observation_ids(
    ledger_rows: pd.DataFrame,
    observations: Optional[pd.DataFrame] = None,
) -> Dict[Tuple[str, str], str]:
    if observations is None:
        obs_path = DATA_DIR / "observations.csv"
        if not obs_path.exists():
            return {}
        observations = pd.read_csv(obs_path, encoding="utf-8-sig", low_memory=False)

    if observations.empty or "observation_id" not in observations.columns:
        return {}

    obs = observations.copy()
    obs["trade_date"] = pd.to_datetime(obs["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    obs["symbol"] = obs["symbol"].astype(str).str.strip().str.upper()
    lookup: Dict[Tuple[str, str], str] = {}
    for _, row in obs.iterrows():
        key = (str(row.get("trade_date", "")).strip(), str(row.get("symbol", "")).strip())
        oid = str(row.get("observation_id", "")).strip()
        if key[0] and key[1] and oid:
            lookup[key] = oid
    return lookup


def _prepare_ledger_row(
    row: Mapping[str, Any],
    *,
    evaluation_mode: str,
    observation_id: str = "",
    frozen_at: Optional[str] = None,
) -> Dict[str, Any]:
    session_date, symbol = _normalize_key(row.get("session_date"), row.get("symbol"))
    out = {col: row.get(col, np.nan) for col in SHADOW_COLUMNS}
    out.update(
        {
            "session_date": session_date,
            "symbol": symbol,
            "snapshot_id": make_snapshot_id(session_date, symbol),
            "frozen_at": frozen_at or _utc_now_iso(),
            "ledger_version": LEDGER_VERSION,
            "evaluation_mode": evaluation_mode,
            "movement_class": classify_movement_class(row),
            "observation_id": observation_id,
        }
    )
    return out


def freeze_t0_ledger(
    shadow_df: pd.DataFrame,
    *,
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = LEDGER_FILE,
    observations: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Upsert T0 rows by (session_date, symbol).

    FORWARD_FROZEN rows are immutable after first write — reruns do not overwrite
    T0 evidence or scores. RECONSTRUCTED_AUDIT rows are stored separately by mode
    and never overwrite FORWARD_FROZEN rows.
    """
    ledger = _load_csv(ledger_path, LEDGER_COLUMNS)
    if shadow_df is None or shadow_df.empty:
        return ledger

    obs_lookup = _lookup_observation_ids(shadow_df, observations)
    existing_forward: Dict[Tuple[str, str], pd.Series] = {}
    if not ledger.empty:
        forward = ledger[ledger["evaluation_mode"] == EVAL_MODE_FORWARD_FROZEN]
        for _, existing in forward.iterrows():
            key = _normalize_key(existing["session_date"], existing["symbol"])
            existing_forward[key] = existing

    new_rows: List[Dict[str, Any]] = []
    for _, row in shadow_df.iterrows():
        session_date, symbol = _normalize_key(row.get("session_date"), row.get("symbol"))
        key = (session_date, symbol)

        if evaluation_mode == EVAL_MODE_FORWARD_FROZEN and key in existing_forward:
            continue

        if evaluation_mode == EVAL_MODE_RECONSTRUCTED_AUDIT:
            prior = ledger[
                (ledger["session_date"].astype(str) == session_date)
                & (ledger["symbol"].astype(str).str.upper() == symbol)
                & (ledger["evaluation_mode"] == EVAL_MODE_RECONSTRUCTED_AUDIT)
            ]
            if not prior.empty:
                continue

        obs_id = obs_lookup.get(key, "")
        new_rows.append(
            _prepare_ledger_row(
                row,
                evaluation_mode=evaluation_mode,
                observation_id=obs_id,
            )
        )

    if new_rows:
        ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
        ledger = ledger.drop_duplicates(
            subset=["session_date", "symbol", "evaluation_mode"],
            keep="first",
        )
        _atomic_write_csv(ledger, ledger_path)

    return ledger


def load_forward_ledger(
    *,
    evaluation_mode: Optional[str] = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = LEDGER_FILE,
) -> pd.DataFrame:
    ledger = _load_csv(ledger_path, LEDGER_COLUMNS)
    if ledger.empty or evaluation_mode is None:
        return ledger
    return ledger[ledger["evaluation_mode"] == evaluation_mode].copy()


def _load_lifecycle(path: Path = LIFECYCLE_FILE) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def _lifecycle_lookup(lifecycle: pd.DataFrame) -> Dict[Tuple[str, str], pd.Series]:
    if lifecycle.empty:
        return {}
    life = lifecycle.copy()
    date_col = "trade_date" if "trade_date" in life.columns else "entry_date"
    life["_session"] = pd.to_datetime(life[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    life["_symbol"] = life["symbol"].astype(str).str.strip().str.upper()
    lookup: Dict[Tuple[str, str], pd.Series] = {}
    for _, row in life.iterrows():
        key = (str(row.get("_session", "")).strip(), str(row.get("_symbol", "")).strip())
        if key[0] and key[1]:
            lookup[key] = row
    return lookup


def _status_or_pending(value: Any) -> str:
    if value is None:
        return "PENDING"
    try:
        if pd.isna(value):
            return "PENDING"
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none"}:
        return "PENDING"
    return text


def mature_forward_outcomes(
    *,
    ledger_path: Path = LEDGER_FILE,
    outcomes_path: Path = OUTCOMES_FILE,
    lifecycle: Optional[pd.DataFrame] = None,
    lifecycle_path: Path = LIFECYCLE_FILE,
) -> pd.DataFrame:
    """
    Attach matured T3/T5/T10 to frozen decisions.

    Only the outcome table is updated. T0 ledger rows remain unchanged.
    Horizons mature independently.
    """
    ledger = load_forward_ledger(evaluation_mode=EVAL_MODE_FORWARD_FROZEN, ledger_path=ledger_path)
    outcomes = _load_csv(outcomes_path, OUTCOME_COLUMNS)

    if ledger.empty:
        return outcomes

    if lifecycle is None:
        lifecycle = _load_lifecycle(lifecycle_path)
    life_by_key = _lifecycle_lookup(lifecycle)

    existing: Dict[str, pd.Series] = {}
    if not outcomes.empty:
        for _, row in outcomes.iterrows():
            existing[str(row.get("snapshot_id", ""))] = row

    now = _utc_now_iso()
    updated_rows: List[Dict[str, Any]] = []

    for _, led in ledger.iterrows():
        session_date, symbol = _normalize_key(led["session_date"], led["symbol"])
        snapshot_id = str(led.get("snapshot_id", "")) or make_snapshot_id(session_date, symbol)
        key = (session_date, symbol)
        life = life_by_key.get(key)

        base = existing.get(snapshot_id, pd.Series(dtype=object)).to_dict()
        row = {col: base.get(col, np.nan) for col in OUTCOME_COLUMNS}
        row.update(
            {
                "session_date": session_date,
                "symbol": symbol,
                "snapshot_id": snapshot_id,
                "observation_id": str(led.get("observation_id", "") or (life.get("observation_id", "") if life is not None else "")),
                "outcome_version": OUTCOME_VERSION,
            }
        )

        t3 = _finite_or_none(life.get("t3_return_pct")) if life is not None else None
        t5 = _finite_or_none(life.get("t5_return_pct")) if life is not None else None
        t10 = _finite_or_none(life.get("t10_return_pct")) if life is not None else None

        prev_t3_status = _status_or_pending(row.get("outcome_status_t3"))
        prev_t5_status = _status_or_pending(row.get("outcome_status_t5"))
        prev_t10_status = _status_or_pending(row.get("outcome_status_t10"))

        if t3 is not None:
            if prev_t3_status != "READY" or pd.isna(row.get("ActualT3Return")):
                row["ActualT3Return"] = t3
                row["outcome_status_t3"] = "READY"
                if not row.get("matured_at_t3"):
                    row["matured_at_t3"] = now
        else:
            row["outcome_status_t3"] = prev_t3_status

        if t5 is not None:
            if prev_t5_status != "READY" or pd.isna(row.get("ActualT5Return")):
                row["ActualT5Return"] = t5
                row["outcome_status_t5"] = "READY"
                if not row.get("matured_at_t5"):
                    row["matured_at_t5"] = now
        else:
            row["outcome_status_t5"] = prev_t5_status

        if t10 is not None:
            if prev_t10_status != "READY" or pd.isna(row.get("ActualT10Return")):
                row["ActualT10Return"] = t10
                row["outcome_status_t10"] = "READY"
                if not row.get("matured_at_t10"):
                    row["matured_at_t10"] = now
        else:
            row["outcome_status_t10"] = prev_t10_status

        flag = _corporate_action_flag(
            _finite_or_none(row.get("ActualT3Return")),
            _finite_or_none(row.get("ActualT5Return")),
            _finite_or_none(row.get("ActualT10Return")),
        )
        if flag:
            row["corporate_action_flag"] = flag
        elif pd.isna(row.get("corporate_action_flag")):
            row["corporate_action_flag"] = ""

        updated_rows.append(row)

    if updated_rows:
        outcomes = pd.DataFrame(updated_rows, columns=list(OUTCOME_COLUMNS))
        outcomes = outcomes.drop_duplicates(subset=["snapshot_id"], keep="last")
        _atomic_write_csv(outcomes, outcomes_path)

    return outcomes


def load_forward_outcomes(path: Path = OUTCOMES_FILE) -> pd.DataFrame:
    return _load_csv(path, OUTCOME_COLUMNS)


def _joined_forward_frame(
    *,
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = LEDGER_FILE,
    outcomes_path: Path = OUTCOMES_FILE,
) -> pd.DataFrame:
    ledger = load_forward_ledger(evaluation_mode=evaluation_mode, ledger_path=ledger_path)
    outcomes = load_forward_outcomes(outcomes_path)
    if ledger.empty:
        return pd.DataFrame()
    if outcomes.empty:
        return ledger.copy()
    return ledger.merge(outcomes, on=["session_date", "symbol", "snapshot_id"], how="left")


def _horizon_metrics(
    df: pd.DataFrame,
    return_col: str,
    status_col: str,
    rank_col: str,
) -> Dict[str, Optional[float]]:
    if df.empty:
        return {
            "n": 0,
            "win_rate": None,
            "mean": None,
            "median": None,
            "bad_pick_rate": None,
            "worst": None,
            "avg_rank_winners": None,
            "avg_rank_losers": None,
        }

    ready = df[df.get(status_col, pd.Series(dtype=str)).astype(str) == "READY"].copy()
    if ready.empty:
        return {
            "n": 0,
            "win_rate": None,
            "mean": None,
            "median": None,
            "bad_pick_rate": None,
            "worst": None,
            "avg_rank_winners": None,
            "avg_rank_losers": None,
        }

    ready["_ret"] = pd.to_numeric(ready[return_col], errors="coerce")
    ready = ready[ready["_ret"].notna()]
    if ready.empty:
        return {
            "n": 0,
            "win_rate": None,
            "mean": None,
            "median": None,
            "bad_pick_rate": None,
            "worst": None,
            "avg_rank_winners": None,
            "avg_rank_losers": None,
        }

    rets = ready["_ret"]
    ranks = pd.to_numeric(ready[rank_col], errors="coerce")
    winners = rets > 0
    losers = rets <= 0
    return {
        "n": int(len(rets)),
        "win_rate": float(winners.mean() * 100.0) if len(rets) else None,
        "mean": float(rets.mean()) if len(rets) else None,
        "median": float(rets.median()) if len(rets) else None,
        "bad_pick_rate": float((rets < -3.0).mean() * 100.0) if len(rets) else None,
        "worst": float(rets.min()) if len(rets) else None,
        "avg_rank_winners": float(ranks[winners].mean()) if winners.any() else None,
        "avg_rank_losers": float(ranks[losers].mean()) if losers.any() else None,
    }


def _build_slice(label: str, df: pd.DataFrame, rank_col: str) -> ScorecardSlice:
    t3 = _horizon_metrics(df, "ActualT3Return", "outcome_status_t3", rank_col)
    t5 = _horizon_metrics(df, "ActualT5Return", "outcome_status_t5", rank_col)
    t10 = _horizon_metrics(df, "ActualT10Return", "outcome_status_t10", rank_col)
    return ScorecardSlice(
        label=label,
        n=t3["n"],
        win_rate_t3=t3["win_rate"],
        mean_t3=t3["mean"],
        median_t3=t3["median"],
        win_rate_t5=t5["win_rate"],
        mean_t5=t5["mean"],
        median_t5=t5["median"],
        win_rate_t10=t10["win_rate"],
        mean_t10=t10["mean"],
        median_t10=t10["median"],
        bad_pick_rate_t3=t3["bad_pick_rate"],
        worst_return_t3=t3["worst"],
        avg_rank_winners_t3=t3["avg_rank_winners"],
        avg_rank_losers_t3=t3["avg_rank_losers"],
    )


def _top_n_by_session(df: pd.DataFrame, rank_col: str, n: int) -> pd.DataFrame:
    if df.empty:
        return df
    parts = []
    for _, group in df.groupby("session_date", sort=False):
        parts.append(group.nsmallest(n, rank_col))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def evaluate_forward_scorecard(
    *,
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = LEDGER_FILE,
    outcomes_path: Path = OUTCOMES_FILE,
    top_ns: Sequence[int] = (5, 10, 20),
) -> ForwardScorecard:
    """Read-only scorecard over frozen T0 ranks and matured outcomes."""
    joined = _joined_forward_frame(
        evaluation_mode=evaluation_mode,
        ledger_path=ledger_path,
        outcomes_path=outcomes_path,
    )
    if joined.empty:
        return ForwardScorecard(evaluation_mode=evaluation_mode)

    baseline_slices: Dict[int, ScorecardSlice] = {}
    shadow_slices: Dict[int, ScorecardSlice] = {}
    production_slices: Dict[int, ScorecardSlice] = {}
    for n in top_ns:
        baseline_slices[n] = _build_slice(
            f"baseline_top{n}",
            _top_n_by_session(joined, "BaselineRank", n),
            "BaselineRank",
        )
        shadow_rank_col = (
            "ShadowExperienceRank"
            if "ShadowExperienceRank" in joined.columns
            else "ShadowRank"
        )
        shadow_slices[n] = _build_slice(
            f"shadow_top{n}",
            _top_n_by_session(joined, shadow_rank_col, n),
            shadow_rank_col,
        )
        if "ProductionRank" in joined.columns:
            prod = joined[joined["ProductionRank"].notna()].copy()
            if not prod.empty:
                production_slices[n] = _build_slice(
                    f"production_top{n}",
                    _top_n_by_session(prod, "ProductionRank", n),
                    "ProductionRank",
                )

    cohorts = {
        "ACTIVE_PROMOTED": joined[joined["movement_class"] == "ACTIVE_PROMOTED"],
        "ACTIVE_DEMOTED": joined[joined["movement_class"] == "ACTIVE_DEMOTED"],
        "PASSIVE_MOVED": joined[joined["movement_class"] == "PASSIVE_MOVED"],
        "UNCHANGED": joined[joined["movement_class"] == "UNCHANGED"],
    }

    lift = None
    if (
        baseline_slices.get(10)
        and shadow_slices.get(10)
        and baseline_slices[10].mean_t3 is not None
        and shadow_slices[10].mean_t3 is not None
    ):
        lift = shadow_slices[10].mean_t3 - baseline_slices[10].mean_t3

    return ForwardScorecard(
        evaluation_mode=evaluation_mode,
        sessions=int(joined["session_date"].nunique()),
        candidates=len(joined),
        baseline_top5=baseline_slices.get(5, ScorecardSlice("baseline_top5")),
        baseline_top10=baseline_slices.get(10, ScorecardSlice("baseline_top10")),
        baseline_top20=baseline_slices.get(20, ScorecardSlice("baseline_top20")),
        shadow_top5=shadow_slices.get(5, ScorecardSlice("shadow_top5")),
        shadow_top10=shadow_slices.get(10, ScorecardSlice("shadow_top10")),
        shadow_top20=shadow_slices.get(20, ScorecardSlice("shadow_top20")),
        production_top5=production_slices.get(5, ScorecardSlice("production_top5")),
        production_top10=production_slices.get(10, ScorecardSlice("production_top10")),
        production_top20=production_slices.get(20, ScorecardSlice("production_top20")),
        learning_lift_top10_mean_t3=lift,
        cohort_active_promoted=_build_slice(
            "ACTIVE_PROMOTED", cohorts["ACTIVE_PROMOTED"], "ShadowExperienceRank"
        ),
        cohort_active_demoted=_build_slice(
            "ACTIVE_DEMOTED", cohorts["ACTIVE_DEMOTED"], "ShadowExperienceRank"
        ),
        cohort_passive_moved=_build_slice(
            "PASSIVE_MOVED", cohorts["PASSIVE_MOVED"], "ShadowExperienceRank"
        ),
        cohort_unchanged=_build_slice(
            "UNCHANGED", cohorts["UNCHANGED"], "BaselineRank"
        ),
    )


def evaluate_regime_scorecard(
    *,
    market_context_key: Optional[str] = None,
    evaluation_mode: str = EVAL_MODE_FORWARD_FROZEN,
    ledger_path: Path = LEDGER_FILE,
    outcomes_path: Path = OUTCOMES_FILE,
    top_n: int = 10,
) -> Dict[str, Any]:
    """
    Regime-grouped scorecard. GLOBAL_DNA rows are labeled CONTEXT_FREE_PRIOR.
    """
    joined = _joined_forward_frame(
        evaluation_mode=evaluation_mode,
        ledger_path=ledger_path,
        outcomes_path=outcomes_path,
    )
    if joined.empty:
        return {"regime_label": "", "baseline": None, "shadow": None, "learning_lift_mean_t3": None}

    if market_context_key:
        sub = joined[joined["market_context_key"].astype(str) == str(market_context_key)]
        regime_label = str(market_context_key)
    else:
        sub = joined.copy()
        regime_label = "ALL_FORWARD"

    if sub.empty:
        return {"regime_label": regime_label, "baseline": None, "shadow": None, "learning_lift_mean_t3": None}

    recall_levels = sub["RecallLevel"].astype(str).unique().tolist()
    if recall_levels == ["GLOBAL_DNA"] or (
        len(recall_levels) == 1 and "GLOBAL" in recall_levels[0]
    ):
        regime_label = f"{regime_label}|{REGIME_LABEL_GLOBAL}"

    baseline = _build_slice(
        f"baseline_top{top_n}",
        _top_n_by_session(sub, "BaselineRank", top_n),
        "BaselineRank",
    )
    shadow = _build_slice(
        f"shadow_top{top_n}",
        _top_n_by_session(sub, "ShadowExperienceRank", top_n),
        "ShadowExperienceRank",
    )
    lift = None
    if baseline.mean_t3 is not None and shadow.mean_t3 is not None:
        lift = shadow.mean_t3 - baseline.mean_t3

    return {
        "regime_label": regime_label,
        "market_context_family": market_context_family(str(sub.iloc[0]["market_context_key"]))
        if market_context_key
        else None,
        "sessions": int(sub["session_date"].nunique()),
        "candidates": len(sub),
        "baseline": baseline,
        "shadow": shadow,
        "learning_lift_mean_t3": lift,
    }


def is_trading_session_valid(
    session_date: str,
    *,
    market_real: Optional[float] = None,
    trading_today: Optional[bool] = None,
) -> Tuple[bool, str]:
    """
    Reuse existing validity rules: weekend guard + VN trading gate + market context.
    """
    if _is_weekend(session_date):
        return False, "weekend_session"
    if trading_today is False:
        return False, "non_trading_day"
    if market_real is None:
        return False, "missing_market_score"
    try:
        if not math.isfinite(float(market_real)):
            return False, "missing_market_score"
    except (TypeError, ValueError):
        return False, "missing_market_score"
    return True, "ok"


def finalize_forward_shadow_snapshot(
    *,
    session_date: str,
    trading_today: Optional[bool] = None,
    market_real: Optional[float] = None,
    market_forecast: Optional[float] = None,
    breadth: Optional[float] = None,
    ledger_path: Path = LEDGER_FILE,
    outcomes_path: Path = OUTCOMES_FILE,
) -> Dict[str, Any]:
    """
    Canonical end-of-pipeline freeze for genuine forward evidence.

    Reads the persisted recommendation/brain state produced by update_memory(),
    builds shadow audit rows, and upserts immutable FORWARD_FROZEN ledger rows.
    Idempotent per (session_date, symbol).
    """
    session_date = str(session_date).strip()
    valid, reason = is_trading_session_valid(
        session_date,
        market_real=market_real,
        trading_today=trading_today,
    )
    if not valid:
        logger.info("Skip forward shadow finalize for %s: %s", session_date, reason)
        return {"ok": False, "reason": reason, "frozen_rows": 0}

    from leader_memory import (
        BRAIN_COLUMNS,
        BRAIN_FILE,
        HISTORY_COLUMNS,
        HISTORY_FILE,
        _build_experience_frame,
        _latest_session_experience_snapshot,
        _load_config,
        _normalize_session_date,
        _safe_read_csv,
        load_pattern_library,
        load_recommendations,
    )
    from modules.regime_alpha_shadow import build_shadow_candidate_universe

    rec = load_recommendations()
    if rec is None or rec.empty:
        return {"ok": False, "reason": "empty_recommendations", "frozen_rows": 0}

    brain = _safe_read_csv(BRAIN_FILE, BRAIN_COLUMNS)
    patterns = load_pattern_library()
    config = _load_config()
    shadow_candidates = build_shadow_candidate_universe(
        brain,
        patterns,
        rec,
        max_candidates=int(config.get("max_shadow_candidate_rows", 250)),
    )
    history = _safe_read_csv(HISTORY_FILE, HISTORY_COLUMNS)
    snapshot = _latest_session_experience_snapshot(history)
    if not snapshot.empty and "session_date" in snapshot.columns:
        snap_dates = snapshot["session_date"].astype(str).str.strip()
        snapshot = snapshot[snap_dates == _normalize_session_date(session_date)]
    experience_df = _build_experience_frame(
        snapshot,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
        brain=brain,
        history=history,
        session_date=session_date,
    )

    shadow_df = build_shadow_with_recall(
        shadow_candidates,
        brain,
        experience_df if experience_df is not None and not experience_df.empty else None,
        session_date=_normalize_session_date(session_date),
    )
    if shadow_df.empty:
        return {"ok": False, "reason": "empty_shadow", "frozen_rows": 0}

    before = load_forward_ledger(evaluation_mode=EVAL_MODE_FORWARD_FROZEN, ledger_path=ledger_path)
    before_count = len(before)

    freeze_t0_ledger(
        shadow_df,
        evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
        ledger_path=ledger_path,
    )
    mature_forward_outcomes(ledger_path=ledger_path, outcomes_path=outcomes_path)

    after = load_forward_ledger(evaluation_mode=EVAL_MODE_FORWARD_FROZEN, ledger_path=ledger_path)
    session_rows = after[after["session_date"].astype(str) == session_date]
    return {
        "ok": True,
        "reason": "frozen",
        "session_date": session_date,
        "frozen_rows": len(session_rows),
        "new_rows": max(0, len(after) - before_count),
    }


__all__ = [
    "EVAL_MODE_FORWARD_FROZEN",
    "EVAL_MODE_RECONSTRUCTED_AUDIT",
    "LEDGER_COLUMNS",
    "LEDGER_FILE",
    "OUTCOME_COLUMNS",
    "OUTCOMES_FILE",
    "REGIME_LABEL_GLOBAL",
    "ForwardScorecard",
    "ScorecardSlice",
    "classify_movement_class",
    "evaluate_forward_scorecard",
    "evaluate_regime_scorecard",
    "finalize_forward_shadow_snapshot",
    "freeze_t0_ledger",
    "is_trading_session_valid",
    "load_forward_ledger",
    "load_forward_outcomes",
    "make_snapshot_id",
    "mature_forward_outcomes",
]
