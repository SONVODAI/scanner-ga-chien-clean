"""Append-only row store for V2 research identities.

Records live in JSONL files under an explicit directory. A new process
reloads those files. The first sealed T0 for an identity is kept. A later
ingest with the same identity and the same sealed fields is a no-op. A later
ingest that would change sealed fields is recorded as a conflict and does
not rewrite the identity.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "v2_research_row_store.v1"
MANIFEST_SCHEMA = "v2_research_row_store_manifest.v1"
IDENTITY_NAME = "identities.jsonl"
LINK_NAME = "links.jsonl"
CONFLICT_NAME = "conflicts.jsonl"
MANIFEST_NAME = "manifest.json"

SIDECAR_SEAL_FIELDS = (
    "t0_date",
    "symbol",
    "candidate_first_seen_ts",
    "t0_price",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
    "source_attribution",
)
SWEET_SEAL_FIELDS = (
    "t0_date",
    "symbol",
    "created_at",
    "t0_price",
    "observer_status",
    "decision",
    "market_real",
    "source_attribution",
)
LINK_SEAL_FIELDS = (
    "identity_id",
    "source_field",
    "status",
    "setup",
    "t0_price",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
)

INSERTED = "inserted"
UNCHANGED = "unchanged"
CONFLICT = "conflict"


def canonical_number(value: object) -> object:
    """Keep a JSON number stable. Blank stays absent. Numeric text stays a number."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    if number.is_integer():
        return int(number)
    return number


def seal_payload(record: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: canonical_number(record.get(key)) if key.endswith("price") or key in {"ema9_at_first_seen", "breakout_ref_at_first_seen", "market_real", "t0_price"} else record.get(key) for key in fields}


def _stable(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


class DurableRowStore:
    """Disk-backed identities. The directory is the store. Memory is only a cache of that directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.identities: dict[str, dict[str, Any]] = {}
        self.links: dict[str, dict[str, Any]] = {}
        self.conflicts: list[dict[str, Any]] = []
        self._conflict_ids: set[str] = set()
        self.load()

    def load(self) -> None:
        """Replace the cache from disk. Missing files are an empty store, not default rows."""
        self.identities = {}
        self.links = {}
        self.conflicts = []
        self._conflict_ids = set()
        for row in _read_jsonl(self.directory / IDENTITY_NAME):
            ident = str(row.get("identity_id") or "")
            if ident and ident not in self.identities:
                self.identities[ident] = row
        for row in _read_jsonl(self.directory / LINK_NAME):
            ident = str(row.get("link_id") or "")
            if ident and ident not in self.links:
                self.links[ident] = row
        for row in _read_jsonl(self.directory / CONFLICT_NAME):
            self.conflicts.append(row)
            marker = str(row.get("conflict_id") or "")
            if marker:
                self._conflict_ids.add(marker)

    def put_identity(self, record: Mapping[str, Any]) -> str:
        ident = str(record.get("identity_id") or "")
        if not ident:
            raise ValueError("identity_id is required")
        fields = SWEET_SEAL_FIELDS if record.get("record_role") == "sweetspot_identity" else SIDECAR_SEAL_FIELDS
        offered = seal_payload(record, fields)
        current = self.identities.get(ident)
        if current is None:
            stored = dict(record)
            stored["sealed"] = offered
            self._append(IDENTITY_NAME, stored)
            self.identities[ident] = stored
            return INSERTED
        if current.get("sealed") == offered:
            return UNCHANGED
        self._record_conflict(ident, "T0_IMMUTABLE", current.get("sealed"), offered)
        return CONFLICT

    def put_link(self, record: Mapping[str, Any]) -> str:
        ident = str(record.get("link_id") or "")
        if not ident:
            raise ValueError("link_id is required")
        offered = seal_payload(record, LINK_SEAL_FIELDS)
        current = self.links.get(ident)
        if current is None:
            stored = dict(record)
            stored["sealed"] = offered
            self._append(LINK_NAME, stored)
            self.links[ident] = stored
            return INSERTED
        if current.get("sealed") == offered:
            return UNCHANGED
        self._record_conflict(ident, "LINK_SEAL_IMMUTABLE", current.get("sealed"), offered)
        return CONFLICT

    def write_manifest(self, manifest: Mapping[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        body = dict(manifest)
        body["schema"] = MANIFEST_SCHEMA
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        target = self.directory / MANIFEST_NAME
        partial = target.with_name(f".{MANIFEST_NAME}.partial")
        partial.write_text(payload, encoding="utf-8")
        os.replace(partial, target)

    def read_manifest(self) -> dict[str, Any] | None:
        path = self.directory / MANIFEST_NAME
        if not path.is_file():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("schema") != MANIFEST_SCHEMA:
            return None
        return loaded

    def _record_conflict(self, subject_id: str, reason: str, kept: object, offered: object) -> None:
        conflict_id = hashlib.sha256(_stable({"offered": offered, "reason": reason, "subject": subject_id}).encode("utf-8")).hexdigest()
        if conflict_id in self._conflict_ids:
            return
        row = {
            "conflict_id": conflict_id,
            "kept": kept,
            "offered": offered,
            "reason": reason,
            "schema": SCHEMA,
            "subject_id": subject_id,
        }
        self._append(CONFLICT_NAME, row)
        self.conflicts.append(row)
        self._conflict_ids.add(conflict_id)

    def _append(self, name: str, row: Mapping[str, Any]) -> None:
        path = self.directory / name
        self.directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows
