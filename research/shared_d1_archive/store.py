"""Append-only Shared Research D1 observation store.

Never silently overwrites a prior (symbol, session_date) payload. Identical
re-captures are skipped; conflicting values append a new line and raise a
quality event.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.shared_d1_archive.contract import (
    DEFAULT_HISTORY_DIRNAME,
    FLAG_CONFLICTING_VALUE,
    OBSERVATIONS_FILENAME,
    QUALITY_FILENAME,
    RECORD_QUALITY,
    SCHEMA_OBSERVATION,
)


def default_history_dir(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    return root / "research" / DEFAULT_HISTORY_DIRNAME


def observations_path(directory: Path | None = None) -> Path:
    base = Path(directory) if directory is not None else default_history_dir()
    return base / OBSERVATIONS_FILENAME


def quality_path(directory: Path | None = None) -> Path:
    base = Path(directory) if directory is not None else default_history_dir()
    return base / QUALITY_FILENAME


def _append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def content_fingerprint(record: Mapping[str, Any]) -> str:
    """Hash of symbol/session/OHLCV only (stable across fetch timestamps)."""
    payload = {
        "symbol": str(record.get("symbol") or "").upper(),
        "session_date": str(record.get("session_date") or "")[:10],
        "open": record.get("open"),
        "high": record.get("high"),
        "low": record.get("low"),
        "close": record.get("close"),
        "volume": record.get("volume"),
        "adjustment_status": record.get("adjustment_status"),
        "provider": record.get("provider"),
        "provider_source": record.get("provider_source"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def identity_key(symbol: str, session_date: str) -> str:
    return f"{str(symbol).strip().upper()}|{str(session_date).strip()[:10]}"


@dataclass
class D1ArchiveStore:
    directory: Path
    _observations: list[dict[str, Any]] = field(default_factory=list)
    _by_identity: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _fingerprints: set[str] = field(default_factory=set)
    _quality: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(cls, directory: Path) -> "D1ArchiveStore":
        store = cls(directory=Path(directory))
        for row in load_jsonl(observations_path(store.directory)):
            store._ingest_existing(row)
        store._quality = load_jsonl(quality_path(store.directory))
        return store

    def _ingest_existing(self, row: Mapping[str, Any]) -> None:
        record = dict(row)
        key = identity_key(str(record.get("symbol") or ""), str(record.get("session_date") or ""))
        fp = str(record.get("content_fingerprint") or content_fingerprint(record))
        record["content_fingerprint"] = fp
        self._observations.append(record)
        self._by_identity.setdefault(key, []).append(record)
        self._fingerprints.add(fp)

    @property
    def observations(self) -> list[dict[str, Any]]:
        return list(self._observations)

    @property
    def quality_events(self) -> list[dict[str, Any]]:
        return list(self._quality)

    def versions_for(self, symbol: str, session_date: str) -> list[dict[str, Any]]:
        return list(self._by_identity.get(identity_key(symbol, session_date), []))

    def append_observations(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        fetched_at: str,
    ) -> dict[str, int]:
        """Append new or conflicting observations. Identical content is skipped."""
        counts = {
            "written": 0,
            "duplicates_skipped": 0,
            "conflicts": 0,
            "duplicate_dates_flagged": 0,
        }
        batch: list[dict[str, Any]] = []
        quality_batch: list[dict[str, Any]] = []

        for raw in records:
            if not isinstance(raw, Mapping):
                continue
            record = dict(raw)
            record.setdefault("schema", SCHEMA_OBSERVATION)
            symbol = str(record.get("symbol") or "").strip().upper()
            session = str(record.get("session_date") or "").strip()[:10]
            if not symbol or not session:
                continue
            key = identity_key(symbol, session)
            fp = content_fingerprint(record)
            record["content_fingerprint"] = fp
            record["symbol"] = symbol
            record["session_date"] = session

            existing = self._by_identity.get(key, [])
            if any(str(row.get("content_fingerprint")) == fp for row in existing):
                # Idempotent rerun: keep history untouched, no silent overwrite.
                counts["duplicates_skipped"] += 1
                continue

            if existing:
                # Prior version kept; new conflicting observation appended.
                record.setdefault("quality_flags", [])
                flags = list(record.get("quality_flags") or [])
                if FLAG_CONFLICTING_VALUE not in flags:
                    flags.append(FLAG_CONFLICTING_VALUE)
                record["quality_flags"] = flags
                record["supersedes_fingerprint"] = existing[-1].get("content_fingerprint")
                counts["conflicts"] += 1
                quality_batch.append(
                    {
                        "schema": RECORD_QUALITY,
                        "record_type": RECORD_QUALITY,
                        "flag": FLAG_CONFLICTING_VALUE,
                        "symbol": symbol,
                        "session_date": session,
                        "prior_fingerprint": existing[-1].get("content_fingerprint"),
                        "new_fingerprint": fp,
                        "fetched_at": fetched_at,
                    }
                )

            self._observations.append(record)
            self._by_identity.setdefault(key, []).append(record)
            self._fingerprints.add(fp)
            batch.append(record)
            counts["written"] += 1

        if batch:
            _append_jsonl(observations_path(self.directory), batch)
        if quality_batch:
            self.append_quality_events(quality_batch)
        return counts

    def append_quality_events(self, events: Iterable[Mapping[str, Any]]) -> int:
        batch = [dict(item) for item in events if isinstance(item, Mapping)]
        if not batch:
            return 0
        self._quality.extend(batch)
        _append_jsonl(quality_path(self.directory), batch)
        return len(batch)
