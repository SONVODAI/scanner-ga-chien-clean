"""GitHub Contents authority for the three forward ledgers.

``brain/*.csv`` stays a local cache. Default loaders refresh that cache from
GitHub when a token is present. An explicit ``ledger_path`` outside the cache
directory never touches GitHub.

A missing GitHub object is not seeded from the cache. The one-time copy is
``modules.forward_ledger_migration``. ``publish_cache`` refuses to create or
update GitHub until that migration report says the authority is ready.

Schemas are not rewritten here — the file bytes are stored and loaded as-is.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from modules.earning_learning import GitHubLocalStorage, _load_github_config

FORWARD_LEDGER_NAMES = (
    "regime_alpha_shadow_ledger.csv",
    "learning_insight_forward_ledger.csv",
    "learning_trajectory_forward_ledger.csv",
)

REMOTE_DIR = "data/earning_learning"
MIGRATION_REPORT_NAME = "forward_ledger_migration_report.json"
MIGRATION_REPORT_SCHEMA = "forward_ledger_migration_v1"


def brain_dir() -> Path:
    override = os.environ.get("MRBOT_BRAIN_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parent.parent / "brain"


def is_default_cache(path: Path) -> bool:
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    return resolved.name in FORWARD_LEDGER_NAMES and resolved.parent == brain_dir().resolve()


def _storage_for(path: Path) -> GitHubLocalStorage:
    return GitHubLocalStorage(path.parent, _load_github_config(REMOTE_DIR))


def _skip_live_github(storage: Optional[GitHubLocalStorage]) -> bool:
    return storage is None and bool(os.environ.get("PYTEST_CURRENT_TEST"))


def migration_report_path() -> Path:
    return brain_dir() / MIGRATION_REPORT_NAME


def report_marks_ready(text: str) -> bool:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema") == MIGRATION_REPORT_SCHEMA
        and payload.get("ready") is True
    )


def authority_ready(*, storage: Optional[GitHubLocalStorage] = None) -> bool:
    """True only after the one-time migration report has been recorded."""
    local = migration_report_path()
    if local.is_file():
        try:
            if report_marks_ready(local.read_text(encoding="utf-8")):
                return True
        except OSError:
            pass
    if storage is None:
        return False
    try:
        payload = storage._github_read(MIGRATION_REPORT_NAME)
    except Exception:
        return False
    if payload is None:
        return False
    return report_marks_ready(payload.text)


def refresh_cache_from_github(path: Path, *, storage: Optional[GitHubLocalStorage] = None) -> str:
    """Replace the cache with the GitHub object. Never uploads on a miss."""
    if not is_default_cache(path):
        return "BYPASS"
    if _skip_live_github(storage):
        return "PYTEST_SKIP"
    store = storage or _storage_for(path)
    if not store.github.enabled:
        return "GITHUB_DISABLED"
    filename = path.name
    try:
        payload = store._github_read(filename)
    except Exception:
        return "GITHUB_READ_FAILED"
    if payload is None:
        return "GITHUB_MISSING"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.text, encoding="utf-8")
    return "GITHUB_WINS"


def publish_cache(path: Path, *, storage: Optional[GitHubLocalStorage] = None) -> str:
    """PUT the cache file after a local first-write. Explicit paths are ignored."""
    if not is_default_cache(path):
        return "BYPASS"
    if _skip_live_github(storage):
        return "PYTEST_SKIP"
    store = storage or _storage_for(path)
    if not store.github.enabled:
        return "GITHUB_DISABLED"
    if not path.exists():
        return "MISSING_CACHE"
    if not authority_ready(storage=store):
        return "AUTHORITY_NOT_READY"
    try:
        store._github_write(
            path.name,
            path.read_text(encoding="utf-8-sig"),
            f"Update forward ledger {path.name}",
        )
    except Exception:
        return "GITHUB_WRITE_FAILED"
    return "PUBLISHED"
