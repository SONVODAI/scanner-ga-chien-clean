"""Append-only Early Recovery events with a GitHub text mirror.

The mirror uses GitHubLocalStorage. It does not upsert Earning snapshots
or observations. Existing event JSON lines are never rewritten; new records
are appended.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from modules.earning_learning import (
    DEFAULT_GITHUB_BRANCH,
    DEFAULT_GITHUB_OWNER,
    DEFAULT_GITHUB_REPO,
    GitHubConfig,
    GitHubLocalStorage,
    StorageReadResult,
    StorageWriteResult,
    _secret_or_env,
)
from modules.early_recovery_watch.contract import (
    ENV_DIR,
    EVENTS_NAME,
    OUTCOME_FIELDS,
    REMOTE_DIR,
    SCHEMA_OUTCOME,
    T0_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TextMirror(Protocol):
    def read_text(self, filename: str) -> StorageReadResult:
        ...

    def write_text(
        self,
        filename: str,
        text: str,
        *,
        commit_message: str,
    ) -> StorageWriteResult:
        ...


def watch_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_DIR, "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / "research" / "early_recovery_watch"


def events_path(directory: Path | None = None) -> Path:
    return watch_dir(directory) / EVENTS_NAME


def github_mirror_path() -> str:
    """Durable path inside the configured GitHub repo. Not an Earning table."""
    return f"{REMOTE_DIR}/{EVENTS_NAME}"


def github_config() -> GitHubConfig:
    owner = _secret_or_env("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER) or DEFAULT_GITHUB_OWNER
    repo = _secret_or_env("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO) or DEFAULT_GITHUB_REPO
    branch = _secret_or_env("GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH) or DEFAULT_GITHUB_BRANCH
    return GitHubConfig(
        token=_secret_or_env("GITHUB_TOKEN"),
        owner=owner,
        repo=repo,
        branch=branch,
        remote_dir=REMOTE_DIR,
    )


def build_storage(directory: Path | None = None) -> GitHubLocalStorage:
    return GitHubLocalStorage(watch_dir(directory), github_config())


def _parse_lines(text: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _raw_lines(text: str | None) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    return lines


def merge_texts(*parts: str | None) -> str:
    """Union of JSONL texts. The first copy of an event_id keeps T0."""
    seen: set[str] = set()
    event_ids: set[str] = set()
    kept: list[str] = []
    for part in parts:
        for line in _raw_lines(part):
            if line in seen:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if item.get("record_type") == "event":
                event_id = str(item.get("event_id") or "")
                if not event_id or event_id in event_ids:
                    continue
                event_ids.add(event_id)
            seen.add(line)
            kept.append(line)
    if not kept:
        return ""
    return "\n".join(kept) + "\n"


def materialize(text: str | None) -> list[dict[str, Any]]:
    """First event line is T0. Later outcome lines may fill only return fields."""
    events: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in _parse_lines(text):
        event_id = str(item.get("event_id") or "")
        if not event_id:
            continue
        if item.get("record_type") == "event":
            if event_id in events:
                continue
            frozen = dict(item)
            for field in OUTCOME_FIELDS:
                frozen.setdefault(field, None)
            events[event_id] = frozen
            order.append(event_id)
            continue
        if item.get("record_type") != "outcome":
            continue
        event = events.get(event_id)
        if event is None:
            continue
        for field in OUTCOME_FIELDS:
            if item.get(field) is not None:
                event[field] = item[field]
    return [events[event_id] for event_id in order]


def _outcome_signature(event: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(event.get(field) for field in OUTCOME_FIELDS)


def append_new_records(
    existing_text: str | None,
    new_events: Sequence[Mapping[str, Any]],
    outcome_updates: Sequence[Mapping[str, Any]],
) -> tuple[str, int]:
    """Return the full JSONL and how many lines were appended.

    A second event with an existing event_id is dropped. T0 bytes already
    in ``existing_text`` stay as they were.
    """
    base = merge_texts(existing_text)
    known = {event["event_id"]: event for event in materialize(base)}
    extra: list[str] = []
    for event in new_events:
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in known:
            continue
        extra.append(json.dumps(dict(event), ensure_ascii=False))
        known[event_id] = dict(event)
    materialized = materialize(base + ("\n".join(extra) + "\n" if extra else ""))
    by_id = {event["event_id"]: event for event in materialized}
    for update in outcome_updates:
        event_id = str(update.get("event_id") or "")
        current = by_id.get(event_id)
        if current is None:
            continue
        proposed = dict(current)
        changed = False
        for field in OUTCOME_FIELDS:
            if field in update and update[field] is not None and proposed.get(field) != update[field]:
                proposed[field] = update[field]
                changed = True
        if not changed:
            continue
        record = {
            "record_type": "outcome",
            "schema": SCHEMA_OUTCOME,
            "event_id": event_id,
            **{field: proposed.get(field) for field in OUTCOME_FIELDS},
        }
        extra.append(json.dumps(record, ensure_ascii=False))
        by_id[event_id] = proposed
    if not extra:
        return base, 0
    suffix = "\n".join(extra) + "\n"
    if base and not base.endswith("\n"):
        base += "\n"
    return base + suffix, len(extra)


def t0_snapshot(event: Mapping[str, Any]) -> dict[str, Any]:
    return {field: event.get(field) for field in T0_FIELDS}


def load_merged_text(storage: TextMirror, directory: Path) -> str:
    local_path = directory / EVENTS_NAME
    local_text = ""
    if local_path.exists():
        local_text = local_path.read_text(encoding="utf-8")
    remote = storage.read_text(EVENTS_NAME)
    return merge_texts(remote.text, local_text)


def save_text(storage: TextMirror, text: str, *, message: str) -> StorageWriteResult:
    return storage.write_text(EVENTS_NAME, text, commit_message=message)
