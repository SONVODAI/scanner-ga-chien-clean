"""
Phase 3K.5 — Production daily run file lock (exclusive non-blocking).

Contract:
  --use-lock at the authoritative entrypoint MUST be acquired BEFORE any
  data-producing stage (headless scan, T0, Forecast, A/C/B, ledgers).
  A second --use-lock invocation exits immediately with LOCK_HELD / lock_held
  and must not scan the universe or mutate scientific stores.

  Live holder PID is never stolen via the stale-age heuristic.
  Kernel flock is the primary exclusion; metadata pid is defense in depth.
  Release is idempotent (normal completion, exception, SIGTERM).
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
LOCK_VERSION = "daily_run_lock_v2_timeout_repair"
DEFAULT_STALE_SECONDS = 7200  # 2 hours — only when holder PID is dead or missing

# Process-local hold so release is idempotent across finally + signal + atexit.
_HELD_BY_PATH: Dict[str, Any] = {}


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
    """
    Stale iff the recorded holder is dead (or metadata is unusable).

    A live PID is never stale, even if acquired_at is older than stale_seconds.
    Stealing a live holder's lock is how overlapping writers would be created.
    """
    if meta.get("corrupt"):
        return True
    pid = meta.get("pid")
    if pid:
        try:
            ipid = int(pid)
        except (TypeError, ValueError):
            return True
        if _pid_alive(ipid):
            return False
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
    key = str(path)

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
    except BlockingIOError:
        fh.close()
        meta = _read_lock_metadata(path)
        return None, RunLockResult(
            acquired=False,
            reason="lock_held",
            lock_path=str(path),
            holder_pid=meta.get("pid"),
            holder_run_id=meta.get("run_id"),
        )
    except (ImportError, OSError):
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
    _HELD_BY_PATH[key] = fh
    return fh, RunLockResult(
        acquired=True,
        reason="acquired",
        lock_path=str(path),
        holder_pid=os.getpid(),
        holder_run_id=run_id,
    )


def release_run_lock(fh: Any, *, data_dir: Optional[Path] = None) -> None:
    path = lock_path(data_dir)
    key = str(path)
    _HELD_BY_PATH.pop(key, None)
    if fh is None:
        return
    try:
        import fcntl

        if not getattr(fh, "closed", False):
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        if not getattr(fh, "closed", False):
            fh.close()
    except Exception:
        pass
    try:
        if path.exists():
            meta = _read_lock_metadata(path)
            holder = meta.get("pid")
            if holder is None or int(holder) == os.getpid() or is_lock_stale(meta):
                path.unlink()
    except OSError:
        pass
