"""
Immutable T0 observation capture for earning learning.

Preserves first-seen T0 DNA + market context without changing ranking engines.
"""

from __future__ import annotations

import math
from datetime import time
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
CANONICAL_CLOSE = time(18, 0)
FREEZE_INPUTS = ("price", "ema9", "ma20", "obv", "obv_ema9")


class FreezeConflict(RuntimeError):
    """The remote freeze changed. The stale full file must not be uploaded."""

T0_FREEZE_EXTRA_COLUMNS = (
    "pattern_key_v2_frozen",
    "pattern_algorithm_version",
    "frozen_at",
    "guardian_witness_source",
    "guardian_witness_bar_session",
    "guardian_witness_provenance",
    "guardian_witness_sha256",
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


def qualify_t0_freeze_batch(
    existing: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    witness_probe=None,
    frozen_at: Optional[str] = None,
    expected_symbols: Optional[Tuple[str, ...]] = None,
) -> Tuple[pd.DataFrame, int, str]:
    """Return ``(frame, added, reason)`` without deleting stored rows.

    A new batch is stored only when it is one complete, consistent set: one
    session, one ``market_real``, the declared symbols, a timezone-aware
    ``frozen_at`` at or after 18:00 ICT on that session, and a verified
    VNINDEX witness. A failed witness stores nothing. Overlapping ids are
    not rewritten.
    """
    old = existing.copy() if existing is not None else pd.DataFrame()
    if not old.empty and "observation_id" not in old.columns:
        raise ValueError("existing freeze file missing observation_id")
    prepared = _prepare_freeze_rows(observations)
    if frozen_at is not None and not prepared.empty:
        prepared["frozen_at"] = frozen_at
    if prepared.empty:
        return old.reset_index(drop=True), 0, "UNCHANGED"
    reason = _batch_reason(prepared, expected_symbols)
    if reason:
        return old.reset_index(drop=True), 0, reason
    existing_ids = set(old["observation_id"].astype(str)) if not old.empty else set()
    new_ids = [str(value) for value in prepared["observation_id"]]
    overlap = [value for value in new_ids if value in existing_ids]
    if overlap:
        if len(overlap) == len(new_ids):
            return old.reset_index(drop=True), 0, "UNCHANGED"
        return old.reset_index(drop=True), 0, "PARTIAL_OVERLAP"

    from research.guardian_research.freeze_witness import WITNESS_COLUMNS, stamp_new_freeze_rows

    stamped = stamp_new_freeze_rows(prepared, probe=witness_probe)
    if any(not _cell(value) for column in WITNESS_COLUMNS for value in stamped[column]):
        return old.reset_index(drop=True), 0, "WITNESS_ABSENT"
    combined = pd.concat([old, stamped], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["observation_id"], keep="first")
    return combined.reset_index(drop=True), int(len(stamped)), "APPENDED"


def append_t0_observation_freeze(
    existing: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    brain_dir: Optional[Path] = None,
    witness_probe=None,
    frozen_at: Optional[str] = None,
    expected_symbols: Optional[Tuple[str, ...]] = None,
) -> Tuple[pd.DataFrame, int]:
    """Append-only first-write-wins store keyed by ``observation_id``.

    Stored rows are never restamped or replaced. A batch that fails the
    clock, witness, or completeness gate adds zero rows.
    """
    brain_path = brain_dir or DEFAULT_BRAIN_DIR
    brain_path.mkdir(parents=True, exist_ok=True)
    frame, added, _reason = qualify_t0_freeze_batch(
        existing,
        observations,
        witness_probe=witness_probe,
        frozen_at=frozen_at,
        expected_symbols=expected_symbols,
    )
    return frame, added


def commit_qualified_freeze(
    storage: Any,
    observations: pd.DataFrame,
    *,
    expected_symbols: Optional[Tuple[str, ...]] = None,
    witness_probe=None,
    frozen_at: Optional[str] = None,
    attempts: int = 3,
) -> dict:
    """Write one qualified batch. A 409/422 rereads and reconciles.

    The shared learning CSV writer is not used. A conflict never uploads the
    stale full file. Existing observation ids are preserved.
    """
    from modules.earning_learning import T0_FREEZE_FILE, _csv_to_text, _text_to_csv

    filename = T0_FREEZE_FILE
    github = bool(getattr(getattr(storage, "github", None), "enabled", False))
    last_existing = pd.DataFrame()
    for _attempt in range(max(1, int(attempts))):
        text, sha = _read_cas(storage, filename, github)
        existing = _text_to_csv(text) if text else pd.DataFrame()
        last_existing = existing
        merged, added, reason = qualify_t0_freeze_batch(
            existing,
            observations,
            witness_probe=witness_probe,
            frozen_at=frozen_at,
            expected_symbols=expected_symbols,
        )
        if reason != "APPENDED":
            return {
                "ok": reason == "UNCHANGED",
                "added": 0,
                "reason": reason,
                "frame": merged,
            }
        payload = _csv_to_text(merged)
        message = _freeze_commit_message(merged, existing, added)
        try:
            _write_cas(storage, filename, payload, sha, message, github)
        except FreezeConflict:
            continue
        confirmed_text, _confirmed_sha = _read_cas(storage, filename, github)
        confirmed = _text_to_csv(confirmed_text) if confirmed_text else pd.DataFrame()
        if _rows_preserved(existing, confirmed) and _new_ids_present(merged, existing, confirmed):
            if github:
                _refresh_local(storage, filename, confirmed_text or "")
            return {
                "ok": True,
                "added": added,
                "reason": "APPENDED",
                "frame": confirmed,
            }
    return {
        "ok": False,
        "added": 0,
        "reason": "FREEZE_CONFLICT",
        "frame": last_existing,
    }


def _batch_reason(
    prepared: pd.DataFrame,
    expected_symbols: Optional[Tuple[str, ...]],
) -> Optional[str]:
    if "observation_id" not in prepared.columns or "trade_date" not in prepared.columns:
        return "INCOMPLETE_BATCH"
    identities = [_cell(value) for value in prepared["observation_id"]]
    if not identities or any(not value for value in identities) or len(set(identities)) != len(identities):
        return "DUPLICATE_BATCH"
    symbols = [_symbol(value) for value in prepared["symbol"]]
    if not symbols or any(not value for value in symbols) or len(set(symbols)) != len(symbols):
        return "DUPLICATE_BATCH"
    sessions = {_session(value) for value in prepared["trade_date"]}
    if len(sessions) != 1 or "" in sessions:
        return "INCONSISTENT_BATCH"
    session = next(iter(sessions))
    frozen_values = {_cell(value) for value in prepared["frozen_at"]}
    if len(frozen_values) != 1 or "" in frozen_values:
        return "INCONSISTENT_BATCH"
    if _clock_reason(next(iter(frozen_values)), session):
        return "CLOCK_REJECTED"
    if expected_symbols is not None:
        expected = tuple(_symbol(value) for value in expected_symbols if _symbol(value))
        if set(symbols) != set(expected) or len(expected) != len(set(expected)):
            return "INCOMPLETE_BATCH"
    from research.guardian_research.indicators import finite_number

    for column in FREEZE_INPUTS:
        if column not in prepared.columns:
            return "INCOMPLETE_BATCH"
        if any(finite_number(value) is None for value in prepared[column]):
            return "INCOMPLETE_BATCH"
    if "market_real" not in prepared.columns:
        return "INCONSISTENT_BATCH"
    markets = {finite_number(value) for value in prepared["market_real"]}
    if len(markets) != 1 or None in markets:
        return "INCONSISTENT_BATCH"
    return None


def _clock_reason(frozen_at: str, session: str) -> Optional[str]:
    parsed = pd.to_datetime(frozen_at, errors="coerce")
    if pd.isna(parsed) or getattr(parsed, "tzinfo", None) is None:
        return "CLOCK_REJECTED"
    local = parsed.tz_convert("Asia/Ho_Chi_Minh")
    if local.strftime("%Y-%m-%d") != session:
        return "CLOCK_REJECTED"
    if int(local.weekday()) >= 5 or local.time() < CANONICAL_CLOSE:
        return "CLOCK_REJECTED"
    return None


def _read_cas(storage: Any, filename: str, github: bool) -> Tuple[Optional[str], Optional[str]]:
    if github:
        return storage.read_content_cas(filename)
    from modules.earning_learning import _read_local_text

    text = _read_local_text(storage._local_path(filename))
    if text is None:
        return None, None
    return text, _content_sha(text)


def _write_cas(
    storage: Any,
    filename: str,
    text: str,
    sha: Optional[str],
    message: str,
    github: bool,
) -> None:
    if github:
        storage.write_content_cas_once(filename, text, sha, message)
        return
    from modules.earning_learning import _atomic_write_text, _read_local_text

    path = storage._local_path(filename)
    current = _read_local_text(path)
    current_sha = _content_sha(current) if current is not None else None
    if current_sha != sha:
        raise FreezeConflict("local freeze changed")
    _atomic_write_text(text, path)


def _refresh_local(storage: Any, filename: str, text: str) -> None:
    from modules.earning_learning import _atomic_write_text

    _atomic_write_text(text, storage._local_path(filename))


def _content_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _freeze_commit_message(merged: pd.DataFrame, existing: pd.DataFrame, added: int) -> str:
    existing_ids = set(existing["observation_id"].astype(str)) if not existing.empty and "observation_id" in existing.columns else set()
    new_rows = merged[~merged["observation_id"].astype(str).isin(existing_ids)]
    session = ""
    if not new_rows.empty and "trade_date" in new_rows.columns:
        session = _session(new_rows["trade_date"].iloc[0])
    return f"Mr.BOT append T0 observation freeze {session} +{added}"


def _rows_preserved(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    if before is None or before.empty:
        return True
    if after is None or after.empty or "observation_id" not in after.columns:
        return False
    from research.guardian_research.freeze_witness import canonical_number

    protected = ("symbol", "trade_date", "frozen_at", "market_real", *FREEZE_INPUTS)
    indexed = after.set_index(after["observation_id"].astype(str), drop=False)
    for _, row in before.iterrows():
        identity = _cell(row.get("observation_id"))
        if identity not in indexed.index:
            return False
        stored = indexed.loc[identity]
        if isinstance(stored, pd.DataFrame):
            stored = stored.iloc[0]
        for column in protected:
            if column not in before.columns:
                continue
            if not _same_cell(row.get(column), stored.get(column), canonical_number):
                return False
    return True


def _new_ids_present(merged: pd.DataFrame, existing: pd.DataFrame, confirmed: pd.DataFrame) -> bool:
    if confirmed is None or confirmed.empty or "observation_id" not in confirmed.columns:
        return False
    existing_ids = set(existing["observation_id"].astype(str)) if not existing.empty and "observation_id" in existing.columns else set()
    wanted = set(merged["observation_id"].astype(str)) - existing_ids
    found = set(confirmed["observation_id"].astype(str))
    return wanted.issubset(found)


def _same_cell(left, right, canonical_number) -> bool:
    left_number = canonical_number(left)
    right_number = canonical_number(right)
    if left_number is not None or right_number is not None:
        return left_number == right_number
    return _cell(left) == _cell(right)


def _session(value) -> str:
    text = _cell(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return ""


def _symbol(value) -> str:
    return _cell(value).upper()


def _cell(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


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
    "FreezeConflict",
    "append_t0_observation_freeze",
    "build_learning_input_df",
    "commit_qualified_freeze",
    "qualify_t0_freeze_batch",
    "read_t0_observation_freeze",
    "sync_market_score_from_real",
    "write_t0_observation_freeze",
]
