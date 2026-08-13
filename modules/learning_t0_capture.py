"""
Immutable T0 observation capture for earning learning.

Preserves first-seen T0 DNA + market context without changing ranking engines.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from modules.earning_learning import (
    FEATURE_VERSION,
    MODULE_VERSION,
    _add_pattern_columns,
    _normalise_symbol,
    _utc_now_iso,
)

PATTERN_ALGORITHM_VERSION = "V4"
DEFAULT_BRAIN_DIR = Path("brain")
T0_FREEZE_FILENAME = "t0_observation_freeze.csv"

T0_FREEZE_EXTRA_COLUMNS = (
    "pattern_key_v2_frozen",
    "pattern_algorithm_version",
    "frozen_at",
)


def _assert_one_row_per_symbol(df: pd.DataFrame, *, label: str) -> None:
    if df.empty or "symbol" not in df.columns:
        return
    counts = df["symbol"].map(_normalise_symbol).value_counts()
    duplicated = counts[counts > 1]
    if not duplicated.empty:
        symbols = ", ".join(duplicated.index.astype(str).tolist()[:5])
        raise ValueError(
            f"{label}: duplicate symbol rows detected ({symbols})"
        )


def build_learning_input_df(
    scan_df: pd.DataFrame,
    *,
    storm_scores: Optional[pd.DataFrame] = None,
    evo_table: Optional[pd.DataFrame] = None,
    leader_brain: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Merge authoritative T0 scores onto scan_df without changing row count.

    Uses raw Storm ``storm_score``, Evolution ``EvoFinal`` → ``evolution_score``,
    and Leader Memory ``leader_score`` — not BUY ELITE weighted scores.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    out = scan_df.copy(deep=True)
    if "symbol" not in out.columns:
        raise ValueError("scan_df must contain a symbol column")

    out["symbol"] = out["symbol"].map(_normalise_symbol)
    base_len = len(out)
    _assert_one_row_per_symbol(out, label="scan_df")

    if storm_scores is not None and not storm_scores.empty:
        scores = storm_scores.copy()
        scores["symbol"] = scores["symbol"].map(_normalise_symbol)
        scores = scores.dropna(subset=["symbol"])
        scores = scores.drop_duplicates(subset=["symbol"], keep="last")
        _assert_one_row_per_symbol(scores, label="storm_scores")
        keep = scores[["symbol", "storm_score"]]
        out = out.drop(columns=["storm_score"], errors="ignore")
        out = out.merge(keep, on="symbol", how="left", validate="one_to_one")

    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo = evo_table.copy()
        evo["symbol"] = evo["symbol"].map(_normalise_symbol)
        if "EvoFinal" not in evo.columns:
            raise ValueError("evo_table must contain EvoFinal")
        evo = evo.drop_duplicates(subset=["symbol"], keep="last")[["symbol", "EvoFinal"]]
        _assert_one_row_per_symbol(evo, label="evo_table")
        out = out.drop(columns=["evolution_score", "EvoFinal"], errors="ignore")
        out = out.merge(evo, on="symbol", how="left", validate="one_to_one")
        out["evolution_score"] = pd.to_numeric(out["EvoFinal"], errors="coerce")
        out = out.drop(columns=["EvoFinal"], errors="ignore")

    if leader_brain is not None and not leader_brain.empty and "symbol" in leader_brain.columns:
        brain = leader_brain.copy()
        brain["symbol"] = brain["symbol"].map(_normalise_symbol)
        if "leader_score" not in brain.columns:
            raise ValueError("leader_brain must contain leader_score")
        brain = brain.drop_duplicates(subset=["symbol"], keep="last")[["symbol", "leader_score"]]
        _assert_one_row_per_symbol(brain, label="leader_brain")
        out = out.drop(columns=["leader_score"], errors="ignore")
        out = out.merge(brain, on="symbol", how="left", validate="one_to_one")

    if len(out) != base_len:
        raise ValueError(
            f"learning_input_df row count changed ({base_len} -> {len(out)})"
        )

    return out.reset_index(drop=True)


def _prepare_freeze_rows(observations: pd.DataFrame) -> pd.DataFrame:
    if observations is None or observations.empty:
        return pd.DataFrame()

    with_patterns = _add_pattern_columns(observations.copy())
    with_patterns["pattern_key_v2_frozen"] = with_patterns.get(
        "pattern_key_v2", with_patterns.get("pattern_key", "")
    ).astype(str)
    with_patterns["pattern_algorithm_version"] = PATTERN_ALGORITHM_VERSION
    with_patterns["frozen_at"] = _utc_now_iso()
    return with_patterns.reset_index(drop=True)


def append_t0_observation_freeze(
    existing: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    brain_dir: Optional[Path] = None,
) -> Tuple[pd.DataFrame, int]:
    """
    Append-only first-write-wins immutable T0 store keyed by observation_id.
    """
    brain_path = brain_dir or DEFAULT_BRAIN_DIR
    brain_path.mkdir(parents=True, exist_ok=True)

    prepared = _prepare_freeze_rows(observations)
    if prepared.empty:
        return (
            existing.copy() if existing is not None else pd.DataFrame(),
            0,
        )

    old = existing.copy() if existing is not None else pd.DataFrame()
    if not old.empty and "observation_id" not in old.columns:
        raise ValueError("existing freeze file missing observation_id")

    existing_ids = set()
    if not old.empty:
        existing_ids = set(old["observation_id"].astype(str))

    to_append = prepared[
        ~prepared["observation_id"].astype(str).isin(existing_ids)
    ].copy()

    if to_append.empty:
        return old.reset_index(drop=True), 0

    combined = pd.concat([old, to_append], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(
        subset=["observation_id"],
        keep="first",
    )
    return combined.reset_index(drop=True), int(len(to_append))


def read_t0_observation_freeze(
    brain_dir: Optional[Path] = None,
) -> pd.DataFrame:
    brain_path = brain_dir or DEFAULT_BRAIN_DIR
    freeze_path = brain_path / T0_FREEZE_FILENAME
    if not freeze_path.exists() or freeze_path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(freeze_path, encoding="utf-8-sig", low_memory=False)


def write_t0_observation_freeze(
    df: pd.DataFrame,
    *,
    brain_dir: Optional[Path] = None,
) -> Path:
    brain_path = brain_dir or DEFAULT_BRAIN_DIR
    brain_path.mkdir(parents=True, exist_ok=True)
    freeze_path = brain_path / T0_FREEZE_FILENAME
    df.to_csv(freeze_path, index=False, encoding="utf-8-sig")
    return freeze_path


def sync_market_score_from_real(
    canonical: pd.DataFrame,
) -> pd.DataFrame:
    """Backward compatibility: market_score mirrors market_real when unset."""
    if canonical is None or canonical.empty:
        return canonical

    out = canonical.copy()
    if "market_real" not in out.columns:
        return out

    real = pd.to_numeric(out["market_real"], errors="coerce")
    if "market_score" not in out.columns:
        out["market_score"] = real
        return out

    score = pd.to_numeric(out["market_score"], errors="coerce")
    out["market_score"] = score.where(score.notna(), real)
    return out


__all__ = [
    "PATTERN_ALGORITHM_VERSION",
    "T0_FREEZE_FILENAME",
    "T0_FREEZE_EXTRA_COLUMNS",
    "append_t0_observation_freeze",
    "build_learning_input_df",
    "read_t0_observation_freeze",
    "sync_market_score_from_real",
    "write_t0_observation_freeze",
]
