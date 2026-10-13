"""Durable Follow-up Watch candidate registry.

Atomic local JSON writes. Optional GitHub mirror via earning_learning storage.
Never rewrites historical ledger lines. Restart-safe.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from modules.live_candidate_v2_followup.contract import (
    ENV_FOLLOWUP_DIR,
    REGISTRY_NAME,
    REMOTE_DIR,
    SCHEMA_REGISTRY,
    STATUS_ACTIVE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def registry_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_FOLLOWUP_DIR, "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / REMOTE_DIR


def registry_path(directory: Path | None = None) -> Path:
    return registry_dir(directory) / REGISTRY_NAME


def candidate_key(symbol: str, source: str, original_session: str) -> str:
    return (
        f"{str(symbol).strip().upper()}|"
        f"{str(source).strip()}|"
        f"{str(original_session).strip()[:10]}"
    )


def empty_registry() -> dict[str, Any]:
    return {
        "schema": SCHEMA_REGISTRY,
        "updated_at": "",
        "candidates": {},
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=str(path.parent),
        encoding="utf-8",
        suffix=".tmp",
    ) as tmp:
        tmp.write(text)
        temp_name = tmp.name
    os.replace(temp_name, path)


def load_registry(directory: Path | None = None) -> dict[str, Any]:
    path = registry_path(directory)
    if not path.exists():
        return empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_registry()
    if not isinstance(data, dict):
        return empty_registry()
    candidates = data.get("candidates")
    if not isinstance(candidates, dict):
        data["candidates"] = {}
    data.setdefault("schema", SCHEMA_REGISTRY)
    return data


def save_registry(registry: Mapping[str, Any], directory: Path | None = None) -> Path:
    path = registry_path(directory)
    payload = dict(registry)
    payload["schema"] = SCHEMA_REGISTRY
    payload["updated_at"] = _utc_now()
    if not isinstance(payload.get("candidates"), dict):
        payload["candidates"] = {}
    _atomic_write_json(path, payload)
    _maybe_mirror_github(path)
    return path


def _maybe_mirror_github(local_path: Path) -> None:
    """Best-effort durable mirror. Failures never raise to callers."""
    try:
        from modules.earning_learning import (
            DEFAULT_GITHUB_BRANCH,
            DEFAULT_GITHUB_OWNER,
            DEFAULT_GITHUB_REPO,
            GitHubConfig,
            GitHubLocalStorage,
            _secret_or_env,
        )

        token = _secret_or_env("GITHUB_TOKEN")
        if not token:
            return
        storage = GitHubLocalStorage(
            local_path.parent,
            GitHubConfig(
                token=token,
                owner=_secret_or_env("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER)
                or DEFAULT_GITHUB_OWNER,
                repo=_secret_or_env("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO)
                or DEFAULT_GITHUB_REPO,
                branch=_secret_or_env("GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH)
                or DEFAULT_GITHUB_BRANCH,
                remote_dir=REMOTE_DIR,
            ),
        )
        storage.write_text(
            REGISTRY_NAME,
            local_path.read_text(encoding="utf-8"),
            commit_message=f"Mr.BOT followup registry {_utc_now()}",
        )
    except Exception:
        return


def upsert_candidate(
    registry: dict[str, Any],
    *,
    symbol: str,
    source: str,
    original_session: str,
    fields: Mapping[str, Any],
) -> str:
    key = candidate_key(symbol, source, original_session)
    candidates = registry.setdefault("candidates", {})
    existing = dict(candidates.get(key) or {})
    if not existing:
        existing = {
            "candidate_key": key,
            "symbol": str(symbol).strip().upper(),
            "source": str(source).strip(),
            "original_session": str(original_session)[:10],
            "first_seen": fields.get("first_seen") or "",
            "status": STATUS_ACTIVE,
            "status_history": [],
        }
    for field, value in fields.items():
        if field == "status_history":
            continue
        existing[field] = value
    candidates[key] = existing
    return key


def append_status_history(
    candidate: dict[str, Any],
    *,
    session: str,
    status: str,
    reason: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    history = list(candidate.get("status_history") or [])
    row = {
        "session": str(session)[:10],
        "status": status,
        "reason": reason,
        "at": _utc_now(),
    }
    if extra:
        row.update(dict(extra))
    history.append(row)
    candidate["status_history"] = history


def active_candidates(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in (registry.get("candidates") or {}).values():
        if not isinstance(raw, dict):
            continue
        if str(raw.get("status") or "") == STATUS_ACTIVE:
            out.append(dict(raw))
    out.sort(
        key=lambda r: (
            str(r.get("original_session") or ""),
            str(r.get("symbol") or ""),
            str(r.get("source") or ""),
        )
    )
    return out


__all__ = [
    "active_candidates",
    "append_status_history",
    "candidate_key",
    "empty_registry",
    "load_registry",
    "registry_dir",
    "registry_path",
    "save_registry",
    "upsert_candidate",
]
