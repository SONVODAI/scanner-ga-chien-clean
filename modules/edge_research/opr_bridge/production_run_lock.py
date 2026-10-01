"""
Phase 3K.5 — Production daily run file lock (exclusive non-blocking).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.storage import resolve_data_dir

LOCK_FILENAME = "daily_run.lock"
LOCK_VERSION = "daily_run_lock_v1_3k5"
DEFAULT_STALE_SECONDS = 7200  # 2 hours


@dataclass(frozen=True)
class RunLockResult:
    acquired: bool
    reason: str
    lock_path: str
    holder_pid: Optional[int] = None
    holder_run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acquired": self.acquired,
            "reason": self.reason,
            "lock_path": self.lock_path,
            "holder_pid": self.holder_pid,
            "holder_run_id": self.holder_run_id,
        }


def lock_path(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir) / "production_observations"
    root.mkdir(parents=True, exist_ok=True)
    return root / LOCK_FILENAME


def read_lock_metadata(path: Path) -> Dict[str, Any]:
    """Read lock file metadata (for health/audit)."""
    return _read_lock_metadata(path)


def _read_lock_metadata(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"corrupt": True}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_lock_stale(meta: Dict[str, Any], *, stale_seconds: int = DEFAULT_STALE_SECONDS) -> bool:
    if meta.get("corrupt"):
        return True
    pid = meta.get("pid")
    if pid and not _pid_alive(int(pid)):
        return True
    acquired_at = meta.get("acquired_at")
    if acquired_at:
        try:
            ts = datetime.fromisoformat(str(acquired_at).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            if age > stale_seconds:
                return True
        except Exception:
            return True
    return False


def acquire_run_lock(
    *,
    run_id: str,
    data_dir: Optional[Path] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> Tuple[Optional[Any], RunLockResult]:
    """
    Acquire exclusive non-blocking lock. Returns (file_handle, result).
  file_handle must be kept open until release_run_lock().
    """
    path = lock_path(data_dir)
    if path.exists():
        meta = _read_lock_metadata(path)
        if not is_lock_stale(meta, stale_seconds=stale_seconds):
            return None, RunLockResult(
                acquired=False,
                reason="lock_held",
                lock_path=str(path),
                holder_pid=meta.get("pid"),
                holder_run_id=meta.get("run_id"),
            )
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return None, RunLockResult(
                acquired=False,
                reason="stale_lock_unlink_failed",
                lock_path=str(path),
                holder_pid=meta.get("pid"),
                holder_run_id=meta.get("run_id"),
            )

    fh = path.open("w", encoding="utf-8")
    try:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (ImportError, BlockingIOError, OSError):
        fh.close()
        meta = _read_lock_metadata(path)
        return None, RunLockResult(
            acquired=False,
            reason="lock_contention",
            lock_path=str(path),
            holder_pid=meta.get("pid"),
            holder_run_id=meta.get("run_id"),
        )

    meta = {
        "version": LOCK_VERSION,
        "pid": os.getpid(),
        "run_id": run_id,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(meta, indent=2))
    fh.flush()
    return fh, RunLockResult(acquired=True, reason="acquired", lock_path=str(path))


def release_run_lock(fh: Any, *, data_dir: Optional[Path] = None) -> None:
    path = lock_path(data_dir)
    try:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
