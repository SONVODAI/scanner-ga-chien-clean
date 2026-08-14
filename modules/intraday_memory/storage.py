"""
Immutable Parquet storage for 5-minute intraday memory.

Layout:
  {data_root}/canonical/
    year=YYYY/month=MM/session_date=YYYY-MM-DD/
      bars.parquet

Idempotent on (symbol, timestamp). Atomic writes via temp file + os.replace.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.intraday_memory.schema import CANONICAL_COLUMNS, CanonicalBar
from modules.intraday_memory.timezone_policy import VN_TZ

# Reconciliation policy (V1A minimal):
# - New bars: inserted
# - Existing identical bars: kept (existing wins for collected_at if same OHLCV)
# - Changed bars: stored in quarantine/ for audit; canonical NOT silently overwritten
RECONCILE_POLICY = "quarantine_on_change"


def _partition_dir(data_root: Path, session_date: date) -> Path:
    return (
        data_root
        / "canonical"
        / f"year={session_date.year}"
        / f"month={session_date.month:02d}"
        / f"session_date={session_date.isoformat()}"
    )


def _session_parquet_path(data_root: Path, session_date: date) -> Path:
    return _partition_dir(data_root, session_date) / "bars.parquet"


def _quarantine_dir(data_root: Path, session_date: date) -> Path:
    return _partition_dir(data_root, session_date) / "quarantine"


def bars_to_dataframe(bars: list[CanonicalBar]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=list(CANONICAL_COLUMNS))

    rows = [bar.as_dict() for bar in bars]
    df = pd.DataFrame(rows)
    # Ensure timezone-aware timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(VN_TZ)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(VN_TZ)
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=False)
    if df["collected_at"].dt.tz is None:
        df["collected_at"] = df["collected_at"].dt.tz_localize(VN_TZ)
    else:
        df["collected_at"] = df["collected_at"].dt.tz_convert(VN_TZ)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype("int64")
    df["symbol"] = df["symbol"].astype(str)
    df["source"] = df["source"].astype(str)
    df["quality_flag"] = df["quality_flag"].astype(str)
    return df[list(CANONICAL_COLUMNS)]


def load_session(data_root: Path, session_date: date) -> pd.DataFrame:
    path = _session_parquet_path(data_root, session_date)
    if not path.exists():
        return pd.DataFrame(columns=list(CANONICAL_COLUMNS))
    df = pd.read_parquet(path)
    return df.reindex(columns=list(CANONICAL_COLUMNS))


def _bar_key(row: pd.Series) -> tuple[str, datetime]:
    ts = row["timestamp"]
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    return (str(row["symbol"]), ts)


def _bars_equal(a: pd.Series, b: pd.Series) -> bool:
    for col in ("open", "high", "low", "close", "volume"):
        if int(a[col]) != int(b[col]):
            return False
    return True


from dataclasses import dataclass


@dataclass
class UpsertResult:
    new: int = 0
    existing: int = 0
    changed: int = 0
    duplicate_count: int = 0
    quarantined: list[dict[str, Any]] | None = None


def upsert_session(
    data_root: Path,
    session_date: date,
    new_bars: list[CanonicalBar],
    *,
    reconcile: bool = False,
) -> UpsertResult:
    """
    Idempotent merge of bars into session partition.

    Natural key: (symbol, timestamp).
    Running twice with identical data produces zero new rows.
    """
    result = UpsertResult(quarantined=[])
    path = _session_parquet_path(data_root, session_date)
    existing = load_session(data_root, session_date)

    incoming = bars_to_dataframe(new_bars)
    if incoming.empty and existing.empty:
        return result

    if existing.empty:
        merged = incoming.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        result.new = len(merged)
        _atomic_write_parquet(merged, path)
        return result

    if incoming.empty:
        result.existing = len(existing)
        return result

    # Build index on existing
    existing = existing.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    existing_keys = {
        (str(r["symbol"]), pd.Timestamp(r["timestamp"]).to_pydatetime()): i
        for i, r in existing.iterrows()
    }

    rows_to_add: list[dict[str, Any]] = []
    for _, row in incoming.iterrows():
        key = (
            str(row["symbol"]),
            pd.Timestamp(row["timestamp"]).to_pydatetime(),
        )
        if key not in existing_keys:
            rows_to_add.append(row.to_dict())
            result.new += 1
        else:
            idx = existing_keys[key]
            ex_row = existing.loc[idx]
            if _bars_equal(row, ex_row):
                result.existing += 1
            else:
                result.changed += 1
                if reconcile:
                    # Quarantine the new provider version for audit
                    qrec = row.to_dict()
                    qrec["_reconcile_note"] = "provider_value_differs"
                    qrec["_existing_open"] = int(ex_row["open"])
                    qrec["_existing_close"] = int(ex_row["close"])
                    result.quarantined.append(qrec)
                # V1A policy: do NOT silently overwrite canonical
                result.existing += 1

    if rows_to_add:
        add_df = pd.DataFrame(rows_to_add)
        merged = pd.concat([existing, add_df], ignore_index=True)
    else:
        merged = existing

    merged = merged.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    result.duplicate_count = max(0, len(incoming) - result.new - result.existing - result.changed)

    _atomic_write_parquet(merged, path)

    if result.quarantined:
        _write_quarantine(data_root, session_date, result.quarantined)

    return result


def _write_quarantine(
    data_root: Path, session_date: date, records: list[dict[str, Any]]
) -> None:
    qdir = _quarantine_dir(data_root, session_date)
    qdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(VN_TZ).strftime("%Y%m%d_%H%M%S")
    qpath = qdir / f"changed_{stamp}.parquet"
    df = pd.DataFrame(records)
    _atomic_write_parquet(df, qpath)


def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".bars_", suffix=".parquet.tmp", dir=str(path.parent)
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        df.to_parquet(temp_path, index=False, engine="pyarrow")
        # Verify readable
        check = pd.read_parquet(temp_path)
        if len(check) != len(df):
            raise IOError(f"Parquet verify failed: {len(check)} != {len(df)}")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def query_session_symbols(data_root: Path, session_date: date) -> list[str]:
    df = load_session(data_root, session_date)
    if df.empty:
        return []
    return sorted(df["symbol"].unique().tolist())


def compare_sessions(
    stored: pd.DataFrame,
    incoming: pd.DataFrame,
) -> dict[str, Any]:
    """Compare stored vs incoming for reconciliation reporting."""
    if stored.empty:
        return {
            "missing_in_stored": len(incoming),
            "missing_in_incoming": 0,
            "changed": 0,
            "stable": 0,
        }

    stored_keys = {
        (str(r["symbol"]), pd.Timestamp(r["timestamp"]).isoformat()): r
        for _, r in stored.iterrows()
    }
    incoming_keys = {
        (str(r["symbol"]), pd.Timestamp(r["timestamp"]).isoformat()): r
        for _, r in incoming.iterrows()
    }

    missing_in_stored = set(incoming_keys) - set(stored_keys)
    missing_in_incoming = set(stored_keys) - set(incoming_keys)
    changed = 0
    stable = 0
    for key in set(stored_keys) & set(incoming_keys):
        if _bars_equal(stored_keys[key], incoming_keys[key]):
            stable += 1
        else:
            changed += 1

    return {
        "missing_in_stored": len(missing_in_stored),
        "missing_in_incoming": len(missing_in_incoming),
        "changed": changed,
        "stable": stable,
        "missing_stored_keys": list(missing_in_stored)[:20],
        "missing_incoming_keys": list(missing_in_incoming)[:20],
    }
