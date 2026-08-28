"""
Bounded durable CSV helpers for Market history retention.

Atomic replace + optional bounded backups. No schema invention, no Forecast coupling.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

import pandas as pd

DEFAULT_BACKUP_KEEP = 5


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def unique_date10(df: Optional[pd.DataFrame], date_col: str = "date") -> Set[str]:
    if df is None or df.empty or date_col not in df.columns:
        return set()
    s = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    return set(s.dropna().astype(str).tolist())


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_dir_for(path: Path) -> Path:
    return path.parent / f".{path.stem}_backups"


def create_bounded_backup(
    path: Path,
    *,
    keep: int = DEFAULT_BACKUP_KEEP,
) -> Tuple[str, Optional[Path]]:
    """
    Copy existing file into a bounded local backup folder with hash manifest.
    Returns (status, backup_path).
    """
    path = Path(path)
    if not path.exists() or path.stat().st_size <= 1:
        return "NO_EXISTING", None

    folder = backup_dir_for(path)
    folder.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(path) or "unknown"
    stamp = _utc_stamp()
    backup_path = folder / f"{path.stem}_{stamp}_{digest[:12]}{path.suffix}"
    shutil.copy2(path, backup_path)

    manifest = {
        "source": str(path),
        "backup": str(backup_path.name),
        "created_at_utc": stamp,
        "sha256": digest,
        "bytes": path.stat().st_size,
    }
    (folder / f"{backup_path.stem}.manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    backups = sorted(
        folder.glob(f"{path.stem}_*{path.suffix}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
        man = old.with_name(old.stem + ".manifest.json")
        if man.exists():
            try:
                man.unlink()
            except OSError:
                pass

    return "BACKUP_OK", backup_path


def atomic_write_csv(df: pd.DataFrame, path: Path, *, encoding: str = "utf-8") -> None:
    """
    Write DataFrame to CSV via temp file + os.replace (same filesystem).
    Failed/interrupted write leaves the prior file intact.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            df.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())

        check = pd.read_csv(temp_path, encoding=encoding, low_memory=False)
        if len(check) != len(df):
            raise IOError(
                f"temp CSV verify failed: expected_rows={len(df)} actual={len(check)}"
            )

        os.replace(temp_path, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def assert_date_coverage_not_shrunk(
    existing: Optional[pd.DataFrame],
    proposed: pd.DataFrame,
    *,
    date_col: str,
) -> Optional[str]:
    """
    Fail-closed guard: refuse if proposed write would drop historical dates.
    Returns None if OK, else reason string.
    """
    before = unique_date10(existing, date_col)
    after = unique_date10(proposed, date_col)
    missing = before - after
    if missing:
        sample = ",".join(sorted(missing)[:8])
        return f"DATE_COVERAGE_SHRINK missing={sample} count={len(missing)}"
    return None


def durable_replace_csv(
    proposed: pd.DataFrame,
    path: Path,
    *,
    existing: Optional[pd.DataFrame] = None,
    date_col: Optional[str] = None,
    backup: bool = True,
    keep: int = DEFAULT_BACKUP_KEEP,
    encoding: str = "utf-8",
) -> Tuple[bool, str]:
    """
    Backup (optional) + date-coverage guard + atomic replace.
    """
    path = Path(path)
    if existing is None and path.exists() and path.stat().st_size > 1 and date_col:
        try:
            existing = pd.read_csv(path, low_memory=False)
        except Exception as exc:  # noqa: BLE001
            return False, f"REFUSED_EXISTING_UNREADABLE:{exc}"

    if date_col:
        reason = assert_date_coverage_not_shrunk(existing, proposed, date_col=date_col)
        if reason:
            return False, f"REFUSED_{reason}"

    if backup:
        create_bounded_backup(path, keep=keep)

    try:
        atomic_write_csv(proposed, path, encoding=encoding)
    except Exception as exc:  # noqa: BLE001
        return False, f"WRITE_FAILED:{exc}"
    return True, "WRITTEN_ATOMIC"
