"""Durable per-symbol canonical store for HSX foreign-flow history."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from modules.durable_csv import (
    assert_date_coverage_not_shrunk,
    atomic_write_csv,
    create_bounded_backup,
    sha256_file,  # re-exported for callers
)
from modules.foreign_flow_history.schema import CANONICAL_COLUMNS, DEFAULT_DATA_ROOT, SCHEMA_VERSION


OUTCOME_FORBIDDEN_COLUMNS = {
    "t1_return",
    "t3_return",
    "t5_return",
    "t10_return",
    "t20_return",
    "mfe",
    "mae",
    "forward_return",
    "label",
    "y_true",
    "outcome",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(root: Optional[Path | str] = None) -> Path:
    return Path(root) if root is not None else Path(DEFAULT_DATA_ROOT)


def raw_dir(root: Optional[Path | str] = None) -> Path:
    return resolve_root(root) / "raw"


def canonical_dir(root: Optional[Path | str] = None) -> Path:
    return resolve_root(root) / "canonical" / "by_symbol"


def manifests_dir(root: Optional[Path | str] = None) -> Path:
    return resolve_root(root) / "manifests"


def symbol_canonical_path(symbol: str, root: Optional[Path | str] = None) -> Path:
    return canonical_dir(root) / f"{str(symbol).strip().upper()}.csv"


def symbol_raw_path(symbol: str, root: Optional[Path | str] = None) -> Path:
    return raw_dir(root) / f"{str(symbol).strip().upper()}.jsonl"


def checkpoint_path(root: Optional[Path | str] = None) -> Path:
    return manifests_dir(root) / "backfill_checkpoint.json"


def ensure_dirs(root: Optional[Path | str] = None) -> None:
    for d in (raw_dir(root), canonical_dir(root), manifests_dir(root)):
        d.mkdir(parents=True, exist_ok=True)


def load_checkpoint(root: Optional[Path | str] = None) -> Dict[str, Any]:
    path = checkpoint_path(root)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "symbols": {}, "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"schema_version": SCHEMA_VERSION, "symbols": {}, "updated_at": None}
        data.setdefault("symbols", {})
        return data
    except Exception:
        return {"schema_version": SCHEMA_VERSION, "symbols": {}, "updated_at": None}


def atomic_write_json(payload: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def save_checkpoint(checkpoint: Dict[str, Any], root: Optional[Path | str] = None) -> None:
    checkpoint = dict(checkpoint)
    checkpoint["schema_version"] = SCHEMA_VERSION
    checkpoint["updated_at"] = utc_now_iso()
    atomic_write_json(checkpoint, checkpoint_path(root))


def append_raw_pages(
    symbol: str,
    pages: Sequence[Dict[str, Any]],
    *,
    root: Optional[Path | str] = None,
    fetched_at: Optional[str] = None,
) -> Path:
    """Append raw provider page payloads as JSONL (one object per page)."""
    ensure_dirs(root)
    path = symbol_raw_path(symbol, root)
    stamp = fetched_at or utc_now_iso()
    with path.open("a", encoding="utf-8") as fh:
        for i, page in enumerate(pages):
            rec = {
                "symbol": str(symbol).strip().upper(),
                "fetched_at": stamp,
                "page_ordinal": i,
                "payload": page,
            }
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return path


def rows_to_dataframe(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    # Drop any accidental outcome columns
    bad = [c for c in df.columns if c.lower() in OUTCOME_FORBIDDEN_COLUMNS]
    if bad:
        df = df.drop(columns=bad)
    df = df[CANONICAL_COLUMNS]
    return df


def merge_canonical_frames(
    existing: Optional[pd.DataFrame],
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    """
    First-write-wins on (trade_date, symbol). Never shrink historical dates.
    Prefer existing row when key collision (immutability).
    """
    if existing is None or existing.empty:
        base = incoming.copy()
    elif incoming is None or incoming.empty:
        base = existing.copy()
    else:
        for frame in (existing, incoming):
            if "trade_date" not in frame.columns or "symbol" not in frame.columns:
                raise ValueError("canonical frames require trade_date and symbol")
        ex = existing.copy()
        inc = incoming.copy()
        ex["_key"] = ex["trade_date"].astype(str) + "|" + ex["symbol"].astype(str).str.upper()
        inc["_key"] = inc["trade_date"].astype(str) + "|" + inc["symbol"].astype(str).str.upper()
        # Keep existing first so drop_duplicates keeps first-write-wins
        base = pd.concat([ex, inc], ignore_index=True)
        base = base.drop_duplicates(subset=["_key"], keep="first")
        base = base.drop(columns=["_key"])

    if base.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    for col in CANONICAL_COLUMNS:
        if col not in base.columns:
            base[col] = None
    # Refuse outcome contamination
    bad = [c for c in base.columns if c.lower() in OUTCOME_FORBIDDEN_COLUMNS]
    if bad:
        base = base.drop(columns=bad)
    base = base[CANONICAL_COLUMNS]
    base = base.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return base


def read_symbol_canonical(symbol: str, root: Optional[Path | str] = None) -> pd.DataFrame:
    path = symbol_canonical_path(symbol, root)
    if not path.exists() or path.stat().st_size <= 1:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    df = pd.read_csv(path, low_memory=False)
    return merge_canonical_frames(None, rows_to_dataframe(df.to_dict(orient="records")))


def write_symbol_canonical(
    symbol: str,
    rows: Sequence[Dict[str, Any]],
    *,
    root: Optional[Path | str] = None,
    backup: bool = True,
) -> Tuple[bool, str, int]:
    """
    Merge incoming rows into per-symbol canonical CSV with durability guards.
    Returns (ok, status, n_rows_after).
    """
    ensure_dirs(root)
    path = symbol_canonical_path(symbol, root)
    existing = read_symbol_canonical(symbol, root)
    incoming = rows_to_dataframe(rows)
    proposed = merge_canonical_frames(existing, incoming)

    # Thinner data guard: refuse if fewer unique dates after merge than before
    # (merge should never shrink; this catches bugs)
    shrink = assert_date_coverage_not_shrunk(existing, proposed, date_col="trade_date")
    if shrink:
        return False, f"REFUSED_{shrink}", int(len(existing))

    # Also refuse overwrite with fewer total rows when same date set but thinner
    # (e.g. dropping OHLC columns via bad merge) — covered by column schema enforce.
    if backup and path.exists():
        create_bounded_backup(path, keep=5)

    try:
        atomic_write_csv(proposed, path)
    except Exception as exc:  # noqa: BLE001
        return False, f"WRITE_FAILED:{exc}", int(len(existing))

    return True, "WRITTEN_ATOMIC", int(len(proposed))


def symbol_coverage_summary(symbol: str, root: Optional[Path | str] = None) -> Dict[str, Any]:
    df = read_symbol_canonical(symbol, root)
    path = symbol_canonical_path(symbol, root)
    if df.empty:
        return {
            "symbol": str(symbol).upper(),
            "n_rows": 0,
            "first_trade_date": None,
            "last_trade_date": None,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
    dates = sorted(df["trade_date"].astype(str).unique().tolist())
    return {
        "symbol": str(symbol).upper(),
        "n_rows": int(len(df)),
        "first_trade_date": dates[0],
        "last_trade_date": dates[-1],
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def list_completed_symbols(root: Optional[Path | str] = None) -> List[str]:
    cp = load_checkpoint(root)
    out = []
    for sym, meta in (cp.get("symbols") or {}).items():
        if isinstance(meta, dict) and meta.get("status") == "completed":
            out.append(str(sym).upper())
    return sorted(set(out))


__all__ = [
    "OUTCOME_FORBIDDEN_COLUMNS",
    "append_raw_pages",
    "canonical_dir",
    "checkpoint_path",
    "ensure_dirs",
    "list_completed_symbols",
    "load_checkpoint",
    "merge_canonical_frames",
    "read_symbol_canonical",
    "rows_to_dataframe",
    "save_checkpoint",
    "symbol_canonical_path",
    "symbol_coverage_summary",
    "symbol_raw_path",
    "write_symbol_canonical",
]
