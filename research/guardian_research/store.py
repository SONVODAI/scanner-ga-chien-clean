"""Immutable daily Guardian T0 snapshot store (research only).

Append-only JSONL. Identity ``(session_date, symbol)`` is first-write-wins.
Never overwrites historical rows. Separate from production Guardian and the
V2 Research Ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.guardian_research.contract import (
    DEFAULT_HISTORY_DIRNAME,
    DEFAULT_SNAPSHOT_FILENAME,
    RECORD_T0,
    SCHEMA_VERSION,
)


def default_history_dir(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "research" / DEFAULT_HISTORY_DIRNAME


def default_snapshot_path(directory: Path | None = None) -> Path:
    base = Path(directory) if directory is not None else default_history_dir()
    return base / DEFAULT_SNAPSHOT_FILENAME


def snapshot_identity(session_date: str, symbol: str) -> str:
    return f"{str(session_date).strip()[:10]}|{str(symbol).strip().upper()}"


def _append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_snapshots(path: Path) -> list[dict[str, Any]]:
    """Load all snapshot lines. Corrupt lines are skipped."""
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


@dataclass
class GuardianT0Store:
    """First-write-wins store keyed by session_date + symbol."""

    path: Path
    _rows: list[dict[str, Any]] = field(default_factory=list)
    _ids: set[str] = field(default_factory=set)

    @classmethod
    def open(cls, path: Path) -> "GuardianT0Store":
        store = cls(path=Path(path))
        for row in load_snapshots(store.path):
            ident = str(row.get("snapshot_id") or "")
            if not ident:
                session = str(row.get("session_date") or "")
                symbol = str(row.get("symbol") or "")
                ident = snapshot_identity(session, symbol)
            if ident in store._ids:
                continue
            store._ids.add(ident)
            store._rows.append(row)
        return store

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def has(self, session_date: str, symbol: str) -> bool:
        return snapshot_identity(session_date, symbol) in self._ids

    def get(self, session_date: str, symbol: str) -> dict[str, Any] | None:
        ident = snapshot_identity(session_date, symbol)
        for row in self._rows:
            if str(row.get("snapshot_id") or "") == ident:
                return dict(row)
        return None

    def append_new(self, records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Persist only identities not already stored. Existing rows stay untouched."""
        written: list[dict[str, Any]] = []
        batch: list[dict[str, Any]] = []
        for raw in records:
            if not isinstance(raw, Mapping):
                continue
            record = dict(raw)
            record.setdefault("record_type", RECORD_T0)
            record.setdefault("schema", SCHEMA_VERSION)
            ident = str(record.get("snapshot_id") or "")
            if not ident:
                ident = snapshot_identity(
                    str(record.get("session_date") or ""),
                    str(record.get("symbol") or ""),
                )
                record["snapshot_id"] = ident
            if not ident or ident in self._ids:
                continue
            self._ids.add(ident)
            self._rows.append(record)
            batch.append(record)
            written.append(record)
        if batch:
            _append_jsonl(self.path, batch)
        return written
