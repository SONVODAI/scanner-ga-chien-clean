"""Copy minimum Rotation UI artifacts into the isolated VPS store.

Never writes Camera archive, Candidate live-shadow, Edge bundle, state.json,
or watchlist.csv. Sidecar-only — Streamlit UI must not import this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from modules.rotation_watch.constants import (
    BOARD_NAME,
    ENV_STORE,
    FORBIDDEN_CAMERA_ARCHIVE,
    FORBIDDEN_EDGE_DURABLE,
    FORBIDDEN_LIVE_SHADOW_STORE,
    STATUS_NAME,
    TRANSPORT_ERROR,
    VPS_ROTATION_STORE,
)

ALLOWED_ROTATION_FILES = (BOARD_NAME, STATUS_NAME)
FORBIDDEN_PUBLISH_NAMES = frozenset({"state.json", "watchlist.csv"})
FORBIDDEN_DEST_PREFIXES = (
    FORBIDDEN_CAMERA_ARCHIVE,
    FORBIDDEN_LIVE_SHADOW_STORE,
    FORBIDDEN_EDGE_DURABLE,
)


def default_rotation_store() -> Path:
    raw = os.environ.get(ENV_STORE, "").strip()
    if raw:
        return Path(raw)
    return Path(VPS_ROTATION_STORE)


def resolve_rotation_store(explicit: Path | None = None) -> Path | None:
    """Only auto-use the VPS default when env is set or a path is injected.

    Unit tests without env skip the copy so they never touch /var/lib/mrbot.
    The --live runner passes the isolated default explicitly.
    """
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_STORE, "").strip()
    if raw:
        return Path(raw)
    return None


def _forbidden_dest(dest_dir: Path) -> bool:
    dest_s = str(dest_dir.resolve()) if dest_dir.exists() or dest_dir.parent.exists() else str(dest_dir)
    dest_s = dest_s.rstrip("/")
    for prefix in FORBIDDEN_DEST_PREFIXES:
        if dest_s == prefix or dest_s.startswith(prefix + "/"):
            return True
    return False


def _atomic_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(src.read_bytes())
    os.replace(tmp, dest)


def publish_rotation_artifacts(
    src_dir: Path,
    dest_dir: Path,
) -> dict[str, Any]:
    """Copy only board.json + status.json. Exact bytes. Atomic replace."""
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)
    if _forbidden_dest(dest_dir):
        return {
            "ok": False,
            "status": TRANSPORT_ERROR,
            "detail": "refusing Camera / Candidate / Edge store path",
            "copied": [],
        }
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "status": TRANSPORT_ERROR,
            "detail": f"mkdir failed: {exc}",
            "copied": [],
        }
    copied: list[str] = []
    for name in ALLOWED_ROTATION_FILES:
        if name in FORBIDDEN_PUBLISH_NAMES:
            return {
                "ok": False,
                "status": TRANSPORT_ERROR,
                "detail": f"refusing {name}",
                "copied": copied,
            }
        src = src_dir / name
        if not src.exists():
            return {
                "ok": False,
                "status": TRANSPORT_ERROR,
                "detail": f"missing {name}",
                "copied": copied,
            }
        dest = dest_dir / name
        try:
            _atomic_copy(src, dest)
        except OSError as exc:
            return {
                "ok": False,
                "status": TRANSPORT_ERROR,
                "detail": f"copy {name} failed: {exc}",
                "copied": copied,
            }
        copied.append(name)
    return {
        "ok": True,
        "status": "OK",
        "detail": "",
        "copied": copied,
        "dest": str(dest_dir),
    }
