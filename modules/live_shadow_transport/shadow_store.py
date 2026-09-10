"""Copy minimum live-shadow UI artifacts into the isolated VPS store.

Never writes /var/lib/mrbot/intraday_memory. Never writes Edge bundle.tar.gz.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from modules.live_shadow_transport.contract import (
    ENV_SHADOW_STORE,
    EVIDENCE_NAME,
    EVIDENCE_TRANSPORT_ERROR,
    FORBIDDEN_CAMERA_ARCHIVE,
    STATUS_NAME,
    VPS_SHADOW_STORE,
)

ALLOWED_SHADOW_FILES = (EVIDENCE_NAME, STATUS_NAME)


def default_shadow_store() -> Path:
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return Path(VPS_SHADOW_STORE)


def resolve_shadow_store(explicit: Path | None = None) -> Path | None:
    """Only auto-use the VPS default when env is set or a path is injected.

    Unit tests without env skip the copy so they never touch /var/lib/mrbot.
    The --live runner passes the isolated default explicitly.
    """
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return None


def publish_shadow_artifacts(
    src_dir: Path,
    dest_dir: Path,
) -> dict[str, Any]:
    """Copy only live_evidence.jsonl + live_shadow_status.json. Exact bytes."""
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)
    dest_s = str(dest_dir.resolve()) if dest_dir.exists() or dest_dir.parent.exists() else str(dest_dir)
    if dest_s.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest_s == FORBIDDEN_CAMERA_ARCHIVE:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": "refusing Camera archive path",
            "copied": [],
        }
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": f"mkdir failed: {exc}",
            "copied": [],
        }
    copied: list[str] = []
    for name in ALLOWED_SHADOW_FILES:
        src = src_dir / name
        if not src.exists():
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
                "detail": f"missing {name}",
                "copied": copied,
            }
        dest = dest_dir / name
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
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
