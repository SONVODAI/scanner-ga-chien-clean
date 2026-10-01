"""Isolated post-freeze forward panel store (does not rewrite historical freeze)."""

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
    sha256_file,
)
from modules.foreign_flow_history.schema import CANONICAL_COLUMNS, SCHEMA_VERSION
from modules.foreign_flow_history.store import merge_canonical_frames, rows_to_dataframe

DEFAULT_CONFIRMATION_ROOT = Path("data/foreign_flow_confirmation")
LAST_IN_SAMPLE = "2026-08-24"
FORWARD_SCHEMA_VERSION = "ff_confirmation_forward_panel_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(root: Optional[Path | str] = None) -> Path:
    return Path(root) if root is not None else DEFAULT_CONFIRMATION_ROOT


def forward_panel_dir(root: Optional[Path | str] = None) -> Path:
    return resolve_root(root) / "forward_panel" / "by_symbol"


def forward_manifests_dir(root: Optional[Path | str] = None) -> Path:
    return resolve_root(root) / "manifests"


def forward_checkpoint_path(root: Optional[Path | str] = None) -> Path:
    return forward_manifests_dir(root) / "forward_ingest_checkpoint.json"


def forward_symbol_path(symbol: str, root: Optional[Path | str] = None) -> Path:
    return forward_panel_dir(root) / f"{str(symbol).strip().upper()}.csv"


def ensure_forward_dirs(root: Optional[Path | str] = None) -> None:
    for d in (
        forward_panel_dir(root),
        forward_manifests_dir(root),
        resolve_root(root) / "events",
        resolve_root(root) / "outcomes",
        resolve_root(root) / "baselines",
        resolve_root(root) / "status",
        resolve_root(root) / "dq_rejects",
    ):
        d.mkdir(parents=True, exist_ok=True)


def atomic_write_json(payload: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent))
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


def load_forward_checkpoint(root: Optional[Path | str] = None) -> Dict[str, Any]:
    path = forward_checkpoint_path(root)
    if not path.exists():
        return {
            "schema_version": FORWARD_SCHEMA_VERSION,
            "last_in_sample": LAST_IN_SAMPLE,
            "dates": {},
            "updated_at": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad checkpoint")
        data.setdefault("dates", {})
        return data
    except Exception:
        return {
            "schema_version": FORWARD_SCHEMA_VERSION,
            "last_in_sample": LAST_IN_SAMPLE,
            "dates": {},
            "updated_at": None,
        }


def save_forward_checkpoint(checkpoint: Dict[str, Any], root: Optional[Path | str] = None) -> None:
    checkpoint = dict(checkpoint)
    checkpoint["schema_version"] = FORWARD_SCHEMA_VERSION
    checkpoint["last_in_sample"] = LAST_IN_SAMPLE
    checkpoint["updated_at"] = utc_now_iso()
    atomic_write_json(checkpoint, forward_checkpoint_path(root))


def read_forward_symbol(symbol: str, root: Optional[Path | str] = None) -> pd.DataFrame:
    path = forward_symbol_path(symbol, root)
    if not path.exists() or path.stat().st_size <= 1:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    df = pd.read_csv(path, low_memory=False)
    return merge_canonical_frames(None, rows_to_dataframe(df.to_dict(orient="records")))


def validate_forward_row(row: Dict[str, Any], *, trade_date: str) -> Tuple[bool, str]:
    td = str(row.get("trade_date") or "")[:10]
    if not td:
        return False, "missing_trade_date"
    if td <= LAST_IN_SAMPLE:
        return False, "pre_freeze_row_forbidden_in_forward_panel"
    if td != str(trade_date)[:10]:
        return False, f"wrong_date:{td}!=expected:{trade_date}"
    if td > utc_now_iso()[:10]:
        return False, "future_row_forbidden"
    return True, "ok"


def append_forward_rows(
    symbol: str,
    rows: Sequence[Dict[str, Any]],
    *,
    trade_date: str,
    root: Optional[Path | str] = None,
    backup: bool = True,
) -> Tuple[bool, str, int]:
    """
    Idempotent append of exact-date forward rows for one symbol.
    First-write-wins; never shrinks date coverage; never writes freeze history.
    """
    ensure_forward_dirs(root)
    accepted: List[Dict[str, Any]] = []
    for row in rows:
        ok, reason = validate_forward_row(row, trade_date=trade_date)
        if not ok:
            return False, f"REJECTED_{reason}", 0
        accepted.append(dict(row))

    if not accepted:
        return False, "NO_ROWS", 0

    path = forward_symbol_path(symbol, root)
    existing = read_forward_symbol(symbol, root)
    incoming = rows_to_dataframe(accepted)
    proposed = merge_canonical_frames(existing, incoming)
    shrink = assert_date_coverage_not_shrunk(existing, proposed, date_col="trade_date")
    if shrink:
        return False, f"REFUSED_{shrink}", int(len(existing))

    if backup and path.exists():
        create_bounded_backup(path, keep=5)

    try:
        atomic_write_csv(proposed, path)
    except Exception as exc:  # noqa: BLE001
        return False, f"WRITE_FAILED:{exc}", int(len(existing))

    return True, "WRITTEN_ATOMIC", int(len(proposed))


def latest_forward_trade_date(root: Optional[Path | str] = None) -> Optional[str]:
    d = forward_panel_dir(root)
    if not d.exists():
        return None
    latest = None
    for path in d.glob("*.csv"):
        try:
            df = pd.read_csv(path, usecols=["trade_date"])
        except Exception:
            continue
        if df.empty:
            continue
        m = str(df["trade_date"].astype(str).max())[:10]
        if latest is None or m > latest:
            latest = m
    return latest


def list_forward_symbols(root: Optional[Path | str] = None) -> List[str]:
    d = forward_panel_dir(root)
    if not d.exists():
        return []
    return sorted(p.stem.upper() for p in d.glob("*.csv"))
