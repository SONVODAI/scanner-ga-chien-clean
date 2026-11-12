"""Incremental ingest into the committed research row store.

The store is the git directory ``research/v2_research_ledger/durable/``.
This module does not write to a container temp disk, does not call git,
and does not push. A completed run publishes one manifest with ``os.replace``.
A second run on the same source bytes leaves those files unchanged.

Commit the durable directory yourself, and only these paths:

    research/v2_research_ledger/durable/identities.jsonl
    research/v2_research_ledger/durable/links.jsonl
    research/v2_research_ledger/durable/conflicts.jsonl
    research/v2_research_ledger/durable/manifest.json

Do not ``git add`` the lock file. Do not ``git push`` from this module.
Do not stage Guardian, V2 Action, the sidecar, or the approximate view.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from research.v2_research_ledger.durable_store import MANIFEST_NAME, DurableRowStore
from research.v2_research_ledger.ingest_rows import ingest_sources

LOCK_NAME = ".ingest.lock"
COMMIT_PATHS = (
    "research/v2_research_ledger/durable/identities.jsonl",
    "research/v2_research_ledger/durable/links.jsonl",
    "research/v2_research_ledger/durable/conflicts.jsonl",
    "research/v2_research_ledger/durable/manifest.json",
)


def commit_process_text() -> str:
    """Operator steps. This function does not run them."""
    lines = "\n".join(f"git add -- {path}" for path in COMMIT_PATHS)
    return (
        "Commit only the durable directory after a completed ingest. "
        "Do not git push from this tool.\n"
        f"{lines}\n"
        "git commit -m \"Append research ledger identities and nomination links\"\n"
        "Do not stage .ingest.lock, the sidecar, Guardian, V2 Action, or T+ files."
    )


@contextmanager
def exclusive_ingest_lock(directory: Path) -> Iterator[None]:
    """One writer at a time. The lock is released when the process exits."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / LOCK_NAME).open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def incremental_ingest(
    directory: Path,
    *,
    sidecar_path: Path | None,
    sweet_csv: Path | None,
    evidence_dir: Path | None,
) -> dict[str, Any]:
    """Load the store, append missing rows, and publish one consistent manifest."""
    with exclusive_ingest_lock(directory):
        store = DurableRowStore(directory)
        before_ids = set(store.identities)
        before_links = set(store.links)
        before_seals = {ident: dict(row.get("sealed") or {}) for ident, row in store.identities.items()}
        ingested = ingest_sources(
            store,
            sidecar_path=sidecar_path,
            sweet_csv=sweet_csv,
            evidence_dir=evidence_dir,
        )
        for ident, sealed in before_seals.items():
            if store.identities[ident].get("sealed") != sealed:
                raise RuntimeError(f"sealed identity changed: {ident}")
        manifest = _stable_manifest(store, ingested)
        coverage = _coverage(store, sidecar_path)
        sidecar = manifest.get("sidecar")
        if isinstance(sidecar, dict) and coverage.get("status") == "PRESENT":
            sidecar["linked_current_rows"] = coverage["current_rows"] - len(coverage["missing_link"]) - len(coverage["missing_identity"])
        _publish_manifest(store, manifest)
        return {
            "conflict_ids": [row.get("subject_id") for row in store.conflicts],
            "conflicts": len(store.conflicts),
            "coverage": coverage,
            "identity_count": len(store.identities),
            "inserted_identities": sorted(set(store.identities) - before_ids),
            "inserted_links": sorted(set(store.links) - before_links),
            "link_count": len(store.links),
            "manifest": manifest,
            "run_counts": ingested.get("counts"),
            "sealed_identities_unchanged": True,
        }


def _stable_manifest(store: DurableRowStore, ingested: dict[str, Any]) -> dict[str, Any]:
    """Manifest fields that stay the same when a second run adds nothing."""
    return {
        "action_evidence": ingested.get("action_evidence"),
        "approximate_view_modified": False,
        "conflict_count": len(store.conflicts),
        "final_buy_enabled": False,
        "historical_row_panel": ingested.get("historical_row_panel"),
        "identity_count": len(store.identities),
        "link_count": len(store.links),
        "schema_records": ingested.get("schema_records"),
        "sidecar": ingested.get("sidecar"),
        "sweetspot": ingested.get("sweetspot"),
        "t_plus_recomputed": False,
    }


def _publish_manifest(store: DurableRowStore, manifest: dict[str, Any]) -> None:
    """Replace the manifest only as a complete document. Remove a leftover partial file."""
    partial = store.directory / f".{MANIFEST_NAME}.partial"
    store.write_manifest(manifest)
    if partial.exists():
        partial.unlink()
    published = json.loads((store.directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    if published.get("identity_count") != len(store.identities) or published.get("link_count") != len(store.links):
        raise RuntimeError("published manifest does not match the store")
    _fsync_directory(store.directory)


def _coverage(store: DurableRowStore, sidecar_path: Path | None) -> dict[str, Any]:
    """Separate a rotating current-row list from a missing sealed identity."""
    if sidecar_path is None or not Path(sidecar_path).is_file():
        return {"status": "MISSING"}
    document = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    rows = document.get("rows") if isinstance(document.get("rows"), list) else []
    current = []
    missing_link = []
    missing_identity = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        ident = (
            f"sidecar|{str(raw.get('session') or '')[:10]}|"
            f"{str(raw.get('symbol') or '').strip().upper()}|"
            f"{raw.get('candidate_first_seen_ts') or ''}"
        )
        current.append(ident)
        if ident not in store.identities:
            missing_identity.append(ident)
        elif f"nomination|{ident}" not in store.links:
            missing_link.append(ident)
    nomination_links = [link_id for link_id in store.links if str(link_id).startswith("nomination|")]
    rotating = sorted(set(nomination_links) - {f"nomination|{ident}" for ident in current})
    return {
        "current_rows": len(current),
        "missing_identity": missing_identity,
        "missing_link": missing_link,
        "rotating_links_not_in_current_rows": rotating,
        "status": "PRESENT",
    }


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
