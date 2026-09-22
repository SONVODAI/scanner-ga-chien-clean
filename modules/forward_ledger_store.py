"""GitHub Contents authority for the three forward ledgers.

``brain/*.csv`` stays a local cache. Default loaders refresh that cache from
GitHub when a token is present. An explicit ``ledger_path`` outside the cache
directory never touches GitHub.

Seed once: if GitHub has no object and the local cache exists, upload the
cache. After that, GitHub wins. Rows are not merged.

Schemas are not rewritten here — the file bytes are stored and loaded as-is.
"""

from __future__ import annotations

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


def refresh_cache_from_github(path: Path, *, storage: Optional[GitHubLocalStorage] = None) -> str:
    """Replace the cache with the GitHub object, or seed GitHub from the cache."""
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
        if path.exists() and path.stat().st_size > 0:
            try:
                text = path.read_text(encoding="utf-8-sig")
                store._github_write(
                    filename,
                    text,
                    f"Seed forward ledger {filename} from local cache",
                )
                return "SEEDED"
            except Exception:
                return "SEED_FAILED"
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
    try:
        store._github_write(
            path.name,
            path.read_text(encoding="utf-8-sig"),
            f"Update forward ledger {path.name}",
        )
    except Exception:
        return "GITHUB_WRITE_FAILED"
    return "PUBLISHED"
