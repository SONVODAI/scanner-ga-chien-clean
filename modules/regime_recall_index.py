"""
Derived historical regime recall index (N3.6).

Rebuilds DNA × T0 market context × realized T3/T5/T10 outcomes from
read-only source files.  Never mutates observations or learning history.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from modules.earning_learning import _add_pattern_columns, _safe_float

logger = logging.getLogger("regime_recall_index")

MODULE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = MODULE_DIR / "data" / "earning_learning"

OBSERVATIONS_FILE = "observations.csv"
LIFECYCLE_FILE = "pattern_lifecycle.csv"
OUTCOMES_FILE = "outcomes.csv"
DECISION_ARCHIVE_FILE = "decision_archive.csv"
RECALL_INDEX_FILE = "regime_recall_index.csv"

REBUILD_VERSION = "1.0.0"
MIN_USABLE_INDEX_ROWS = 100

# Process-local cache: one load/rebuild attempt per resolved data_dir per worker.
_RUNTIME_STATE: Dict[str, Dict[str, Any]] = {}

RECALL_LEVEL_EXACT = "EXACT_CONTEXT"
RECALL_LEVEL_FAMILY = "FAMILY_CONTEXT"
RECALL_LEVEL_GLOBAL = "GLOBAL_DNA"
RECALL_LEVEL_UNUSABLE = "UNUSABLE"

RECALL_INDEX_COLUMNS: Sequence[str] = (
    "recall_id",
    "observation_id",
    "session_date",
    "symbol",
    "stock_pattern_key",
    "market_context_key",
    "recall_level",
    "usable_for_learning",
    "is_weekend",
    "market_score_t0",
    "market_forecast_t0",
    "breadth_t0",
    "market_regime_t0",
    "t3_return_pct",
    "t5_return_pct",
    "t10_return_pct",
    "outcome_status_t3",
    "outcome_status_t5",
    "outcome_status_t10",
    "source_observation_hash",
    "source_lifecycle_hash",
    "source_files",
    "rebuild_version",
    "rebuilt_at",
)


@dataclass(frozen=True)
class RecallAuditSummary:
    total_observations: int = 0
    total_index_rows: int = 0
    weekend_rows: int = 0
    context_free_rows: int = 0
    by_level: Dict[str, int] = field(default_factory=dict)
    t3_ready_by_level: Dict[str, int] = field(default_factory=dict)
    t5_ready_by_level: Dict[str, int] = field(default_factory=dict)
    t10_ready_by_level: Dict[str, int] = field(default_factory=dict)
    groups_n5_by_level: Dict[str, int] = field(default_factory=dict)
    groups_n10_by_level: Dict[str, int] = field(default_factory=dict)
    groups_n20_by_level: Dict[str, int] = field(default_factory=dict)
    archive_key_match_rate: Optional[float] = None
    duplicate_observation_ids: int = 0


def _finite_numeric(value: Any) -> bool:
    parsed = _safe_float(value)
    return math.isfinite(parsed)


def _is_weekend(trade_date: Any) -> bool:
    parsed = pd.to_datetime(trade_date, errors="coerce")
    if pd.isna(parsed):
        return False
    return int(parsed.dayofweek) >= 5


def classify_recall_level(
    *,
    market_score_t0: Any,
    market_forecast_t0: Any,
    breadth_t0: Any,
    market_context_key: str,
    is_weekend: bool,
) -> str:
    """
    Classify recall level from stored T0 fields only — never from outcomes.
    """
    if is_weekend or not _finite_numeric(market_score_t0):
        return RECALL_LEVEL_UNUSABLE

    has_forecast = _finite_numeric(market_forecast_t0)
    has_breadth = _finite_numeric(breadth_t0)
    parts = str(market_context_key or "").split("|")

    if has_forecast and has_breadth and len(parts) == 3 and all(p != "NA" for p in parts):
        return RECALL_LEVEL_EXACT

    if str(market_context_key or "").startswith("NA|NA|"):
        return RECALL_LEVEL_GLOBAL

    if has_forecast and not has_breadth:
        return RECALL_LEVEL_FAMILY

    if "NA" in parts:
        return RECALL_LEVEL_FAMILY

    return RECALL_LEVEL_GLOBAL


def _row_hash(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    payload = {field: row.get(field, "") for field in fields}
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _outcome_status(value: Any) -> str:
    return "READY" if _finite_numeric(value) else "PENDING"


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


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def _lifecycle_outcome_columns(lifecycle: pd.DataFrame) -> pd.DataFrame:
    if lifecycle.empty:
        return pd.DataFrame(
            columns=[
                "observation_id",
                "t3_return_pct",
                "t5_return_pct",
                "t10_return_pct",
            ]
        )
    cols = ["observation_id"]
    for col in ("t3_return_pct", "t5_return_pct", "t10_return_pct"):
        if col in lifecycle.columns:
            cols.append(col)
    out = lifecycle[cols].copy()
    return out.drop_duplicates("observation_id", keep="last")


def build_recall_index(
    observations: pd.DataFrame,
    lifecycle: Optional[pd.DataFrame] = None,
    *,
    rebuild_version: str = REBUILD_VERSION,
    rebuilt_at: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build derived recall index in memory from read-only sources.
    Outcomes are labels only — never used to infer T0 context.
    """
    if observations is None or observations.empty:
        return pd.DataFrame(columns=list(RECALL_INDEX_COLUMNS))

    obs = observations.copy()
    if "observation_id" not in obs.columns:
        raise ValueError("observations must contain observation_id")

    obs = obs.drop_duplicates("observation_id", keep="last")
    keyed = _add_pattern_columns(obs)

    lifecycle = lifecycle if lifecycle is not None else pd.DataFrame()
    life_outcomes = _lifecycle_outcome_columns(lifecycle)

    hash_fields = [
        "observation_id",
        "trade_date",
        "symbol",
        "market_score",
        "market_forecast",
        "breadth",
        "leader_score",
        "rsi14",
    ]
    life_hash_fields = ["observation_id", "t3_return_pct", "t5_return_pct", "t10_return_pct"]

    rows = []
    for idx, row in keyed.iterrows():
        observation_id = str(row.get("observation_id", "")).strip()
        if not observation_id:
            continue

        session_date = pd.to_datetime(row.get("trade_date"), errors="coerce")
        session_str = (
            session_date.strftime("%Y-%m-%d")
            if pd.notna(session_date)
            else str(row.get("trade_date", "")).strip()
        )
        weekend = _is_weekend(row.get("trade_date"))

        market_score_t0 = row.get("market_score")
        market_forecast_t0 = row.get("market_forecast")
        breadth_t0 = row.get("breadth")
        market_context_key = str(row.get("market_context_key", ""))
        stock_pattern_key = str(row.get("stock_pattern_key", ""))

        recall_level = classify_recall_level(
            market_score_t0=market_score_t0,
            market_forecast_t0=market_forecast_t0,
            breadth_t0=breadth_t0,
            market_context_key=market_context_key,
            is_weekend=weekend,
        )
        usable = recall_level != RECALL_LEVEL_UNUSABLE

        life_row = (
            life_outcomes.loc[life_outcomes["observation_id"] == observation_id]
            if not life_outcomes.empty
            else pd.DataFrame()
        )
        if not life_row.empty:
            life_match = life_row.iloc[0]
            t3 = life_match.get("t3_return_pct", np.nan)
            t5 = life_match.get("t5_return_pct", np.nan)
            t10 = life_match.get("t10_return_pct", np.nan)
            life_hash = _row_hash(life_match, life_hash_fields)
        else:
            t3 = t5 = t10 = np.nan
            life_hash = ""

        rows.append(
            {
                "recall_id": observation_id,
                "observation_id": observation_id,
                "session_date": session_str,
                "symbol": str(row.get("symbol", "")).strip(),
                "stock_pattern_key": stock_pattern_key,
                "market_context_key": market_context_key,
                "recall_level": recall_level,
                "usable_for_learning": usable,
                "is_weekend": weekend,
                "market_score_t0": market_score_t0,
                "market_forecast_t0": market_forecast_t0,
                "breadth_t0": breadth_t0,
                "market_regime_t0": row.get("market_regime", ""),
                "t3_return_pct": t3,
                "t5_return_pct": t5,
                "t10_return_pct": t10,
                "outcome_status_t3": _outcome_status(t3),
                "outcome_status_t5": _outcome_status(t5),
                "outcome_status_t10": _outcome_status(t10),
                "source_observation_hash": _row_hash(row, hash_fields),
                "source_lifecycle_hash": life_hash,
                "source_files": f"{OBSERVATIONS_FILE}|{LIFECYCLE_FILE}",
                "rebuild_version": rebuild_version,
                "rebuilt_at": rebuilt_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    index_df = pd.DataFrame(rows, columns=list(RECALL_INDEX_COLUMNS))
    index_df = index_df.sort_values(
        ["session_date", "symbol", "observation_id"],
        kind="stable",
    ).reset_index(drop=True)
    return index_df.drop_duplicates("observation_id", keep="last").reset_index(drop=True)


def summarize_recall_index(index_df: pd.DataFrame) -> RecallAuditSummary:
    if index_df is None or index_df.empty:
        return RecallAuditSummary()

    summary = RecallAuditSummary(
        total_observations=len(index_df),
        total_index_rows=len(index_df),
        weekend_rows=int(index_df["is_weekend"].fillna(False).sum()),
        context_free_rows=int(
            (~index_df["market_score_t0"].map(_finite_numeric)).sum()
        ),
        duplicate_observation_ids=int(
            index_df["observation_id"].duplicated().sum()
        ),
    )

    for level in (
        RECALL_LEVEL_EXACT,
        RECALL_LEVEL_FAMILY,
        RECALL_LEVEL_GLOBAL,
        RECALL_LEVEL_UNUSABLE,
    ):
        sub = index_df[index_df["recall_level"] == level]
        summary.by_level[level] = len(sub)
        summary.t3_ready_by_level[level] = int(
            (sub["outcome_status_t3"] == "READY").sum()
        )
        summary.t5_ready_by_level[level] = int(
            (sub["outcome_status_t5"] == "READY").sum()
        )
        summary.t10_ready_by_level[level] = int(
            (sub["outcome_status_t10"] == "READY").sum()
        )

        usable = sub[sub["usable_for_learning"]]
        if usable.empty:
            summary.groups_n5_by_level[level] = 0
            summary.groups_n10_by_level[level] = 0
            summary.groups_n20_by_level[level] = 0
            continue

        grp = (
            usable.groupby(["stock_pattern_key", "market_context_key"])
            .size()
            .reset_index(name="n")
        )
        summary.groups_n5_by_level[level] = int((grp["n"] >= 5).sum())
        summary.groups_n10_by_level[level] = int((grp["n"] >= 10).sum())
        summary.groups_n20_by_level[level] = int((grp["n"] >= 20).sum())

    return summary


def validate_against_decision_archive(
    index_df: pd.DataFrame,
    archive: pd.DataFrame,
) -> float:
    """Return match rate for rebuilt market_context_key vs decision archive."""
    if index_df.empty or archive.empty:
        return 1.0
    if "observation_id" not in archive.columns or "market_context_key" not in archive.columns:
        return 1.0

    merged = index_df[["observation_id", "market_context_key"]].merge(
        archive[["observation_id", "market_context_key"]].rename(
            columns={"market_context_key": "archive_context_key"}
        ),
        on="observation_id",
        how="inner",
    )
    if merged.empty:
        return 1.0
    matches = (
        merged["market_context_key"].astype(str)
        == merged["archive_context_key"].astype(str)
    )
    return float(matches.mean())


def validate_outcomes_consistency(
    index_df: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> Dict[str, Any]:
    """Cross-check lifecycle labels against outcomes.csv (validation only)."""
    if index_df.empty or outcomes.empty:
        return {"checked": 0, "mismatches": 0}

    t3 = outcomes[outcomes["horizon"] == 3][
        ["observation_id", "return_pct"]
    ].rename(columns={"return_pct": "outcome_t3"})
    merged = index_df.merge(t3, on="observation_id", how="inner")
    if merged.empty:
        return {"checked": 0, "mismatches": 0}

    ready = merged[merged["outcome_status_t3"] == "READY"]
    if ready.empty:
        return {"checked": 0, "mismatches": 0}

    delta = (
        pd.to_numeric(ready["t3_return_pct"], errors="coerce")
        - pd.to_numeric(ready["outcome_t3"], errors="coerce")
    ).abs()
    mismatches = int((delta > 1e-6).sum())
    return {"checked": len(ready), "mismatches": mismatches}


def rebuild_recall_index(
    data_dir: Optional[Path | str] = None,
    *,
    write: bool = True,
) -> tuple[pd.DataFrame, RecallAuditSummary, Dict[str, Any]]:
    """
    Load read-only sources, build index, optionally write derived CSV.
    Idempotent: same inputs → same rows.
    """
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    observations = _load_csv(base / OBSERVATIONS_FILE)
    lifecycle = _load_csv(base / LIFECYCLE_FILE)
    outcomes = _load_csv(base / OUTCOMES_FILE)
    archive = _load_csv(base / DECISION_ARCHIVE_FILE)

    index_df = build_recall_index(observations, lifecycle)
    archive_match = validate_against_decision_archive(index_df, archive)
    rebuilt_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    index_df = index_df.copy()
    index_df["rebuilt_at"] = rebuilt_at
    base_summary = summarize_recall_index(index_df)
    summary = RecallAuditSummary(
        total_observations=base_summary.total_observations,
        total_index_rows=base_summary.total_index_rows,
        weekend_rows=base_summary.weekend_rows,
        context_free_rows=base_summary.context_free_rows,
        by_level=base_summary.by_level,
        t3_ready_by_level=base_summary.t3_ready_by_level,
        t5_ready_by_level=base_summary.t5_ready_by_level,
        t10_ready_by_level=base_summary.t10_ready_by_level,
        groups_n5_by_level=base_summary.groups_n5_by_level,
        groups_n10_by_level=base_summary.groups_n10_by_level,
        groups_n20_by_level=base_summary.groups_n20_by_level,
        archive_key_match_rate=archive_match,
        duplicate_observation_ids=base_summary.duplicate_observation_ids,
    )
    outcome_check = validate_outcomes_consistency(index_df, outcomes)

    if write:
        output_path = base / RECALL_INDEX_FILE
        _atomic_write_csv(index_df, output_path)
        logger.info("Wrote recall index: %s (%s rows)", output_path, len(index_df))

    diagnostics = {
        "archive_key_match_rate": archive_match,
        "outcome_consistency": outcome_check,
        "source_row_counts": {
            "observations": len(observations),
            "lifecycle": len(lifecycle),
            "outcomes": len(outcomes),
        },
    }
    return index_df, summary, diagnostics


def _empty_recall_index() -> pd.DataFrame:
    return pd.DataFrame(columns=list(RECALL_INDEX_COLUMNS))


def _runtime_key(base: Path) -> str:
    return str(base.resolve())


def reset_recall_index_runtime_cache() -> None:
    """Test helper — clears process-local recall index cache."""
    _RUNTIME_STATE.clear()


def _sources_available_for_rebuild(base: Path) -> bool:
    obs = base / OBSERVATIONS_FILE
    life = base / LIFECYCLE_FILE
    return (
        obs.exists()
        and obs.stat().st_size > 0
        and life.exists()
        and life.stat().st_size > 0
    )


def _is_usable_recall_index(df: pd.DataFrame) -> bool:
    if df is None or df.empty or len(df) < MIN_USABLE_INDEX_ROWS:
        return False
    required = {
        "observation_id",
        "recall_level",
        "stock_pattern_key",
        "market_context_key",
        "rebuild_version",
    }
    if not required.issubset(df.columns):
        return False
    versions = df["rebuild_version"].astype(str).unique().tolist()
    return versions == [REBUILD_VERSION]


def _sources_signature(base: Path) -> str:
    """Fingerprint rebuild sources so cache retry tracks availability changes."""
    parts: list[str] = []
    for name in (OBSERVATIONS_FILE, LIFECYCLE_FILE):
        path = base / name
        if path.exists():
            stat = path.stat()
            parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
        else:
            parts.append(f"{name}:missing")
    return "|".join(parts)


def ensure_recall_index(
    data_dir: Optional[Path | str] = None,
    *,
    write: bool = True,
    auto_rebuild: bool = True,
) -> pd.DataFrame:
    """
    Load derived recall index; auto-rebuild once per process when missing or stale.

    Read-only toward historical sources. Derived CSV may be written to data_dir
    when rebuild succeeds (runtime activation for Streamlit Cloud).
    """
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    key = _runtime_key(base)
    state = _RUNTIME_STATE.setdefault(key, {})

    usable = state.get("usable_cache")
    if usable is not None:
        return usable

    path = base / RECALL_INDEX_FILE
    if path.exists() and path.stat().st_size > 0:
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
            if _is_usable_recall_index(df):
                state["usable_cache"] = df
                state.pop("rebuild_exhausted", None)
                state.pop("rebuild_sources_sig", None)
                logger.info("Loaded recall index: %s (%s rows)", path, len(df))
                return df
            logger.warning(
                "Recall index at %s missing/stale (rows=%s); will rebuild if allowed",
                path,
                len(df) if df is not None else 0,
            )
        except Exception:
            logger.exception("Failed reading recall index at %s", path)

    if not auto_rebuild:
        return _empty_recall_index()

    sources_sig = _sources_signature(base)
    sources_ok = _sources_available_for_rebuild(base)

    # Missing sources: return empty without poisoning future retries.
    if not sources_ok:
        logger.info(
            "Recall index unavailable and rebuild sources missing under %s",
            base,
        )
        return _empty_recall_index()

    # Sources present but prior rebuild for this signature already failed: skip loop.
    if state.get("rebuild_exhausted") and state.get("rebuild_sources_sig") == sources_sig:
        return state.get("last_empty") or _empty_recall_index()

    try:
        index_df, summary, _ = rebuild_recall_index(base, write=write)
        if _is_usable_recall_index(index_df):
            state["usable_cache"] = index_df
            state["auto_rebuilt"] = True
            state.pop("rebuild_exhausted", None)
            state.pop("rebuild_sources_sig", None)
            state.pop("last_empty", None)
            logger.info(
                "Auto-rebuilt recall index at %s (%s rows, GLOBAL T3-ready=%s)",
                path,
                summary.total_index_rows,
                summary.t3_ready_by_level.get(RECALL_LEVEL_GLOBAL, 0),
            )
            return index_df
        logger.warning(
            "Auto-rebuild produced unusable recall index (%s rows)",
            len(index_df) if index_df is not None else 0,
        )
    except Exception:
        logger.exception("Auto-rebuild recall index failed for %s", base)

    state["rebuild_exhausted"] = True
    state["rebuild_sources_sig"] = sources_sig
    state["last_empty"] = _empty_recall_index()
    return state["last_empty"]


def load_recall_index(data_dir: Optional[Path | str] = None) -> pd.DataFrame:
    return ensure_recall_index(data_dir, write=True, auto_rebuild=True)


__all__ = [
    "REBUILD_VERSION",
    "RECALL_INDEX_COLUMNS",
    "RECALL_INDEX_FILE",
    "RECALL_LEVEL_EXACT",
    "RECALL_LEVEL_FAMILY",
    "RECALL_LEVEL_GLOBAL",
    "RECALL_LEVEL_UNUSABLE",
    "RecallAuditSummary",
    "build_recall_index",
    "classify_recall_level",
    "ensure_recall_index",
    "load_recall_index",
    "rebuild_recall_index",
    "reset_recall_index_runtime_cache",
    "summarize_recall_index",
    "validate_against_decision_archive",
    "validate_outcomes_consistency",
]
