"""Flock for one live V2 WHEN cycle.

Separate from the Camera archive lock at
``{intraday_memory}/.collector.lock``. This file lives under the live-shadow
output directory and never touches ``/var/lib/mrbot/intraday_memory``.
"""

from __future__ import annotations

import fcntl
import os
from datetime import datetime
from pathlib import Path

from modules.live_candidate.calendar import as_vn

LOCK_NAME = ".v2_live_when.lock"
EXIT_ALREADY_RUNNING = 75
REASON_ALREADY_RUNNING = "LIVE_WHEN_ALREADY_RUNNING"


class LiveWhenLock:
    """Non-blocking exclusive lock. The holder keeps the fd open."""

    def __init__(self, directory: Path) -> None:
        self.path = Path(directory) / LOCK_NAME
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started={as_vn(datetime.now()).isoformat()}\n")
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "LiveWhenLock":
        if not self.acquire():
            raise BlockingIOError(REASON_ALREADY_RUNNING)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
