"""Read-only clocks for the research board.

File reads only. This module does not import the ledger, the nomination
importer, the evidence importer, or any production writer.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from research.v2_research_ledger.contract import SOURCE_BRAIN_A

FRESH = "FRESH"
STALE_DATA = "STALE_DATA"
UNVERIFIED = "UNVERIFIED"
CLOCK_SCHEMA = "v2_research_ledger_source_clock.v1"

_EVIDENCE_FILES = (
    "live_when_v2_action_evidence.jsonl",
    "post_close_v2_action_evidence.jsonl",
)


def sidecar_identities(path: Path) -> set[str]:
    """Brain A freeze rows and current rows, using each record's own session."""
    document = _sidecar_document(path)
    if document is None:
        return set()
    identities: set[str] = set()
    for record in document.get("rows") or []:
        ident = _identity(record, freeze=False)
        if ident:
            identities.add(ident)
    for record in document.get("freeze_ledger") or []:
        ident = _identity(record, freeze=True)
        if ident:
            identities.add(ident)
    return identities


def sidecar_clock(path: Path) -> dict[str, Any] | None:
    """Document session, observed time, and nomination identity hash."""
    source = Path(path)
    document = _sidecar_document(source)
    if document is None:
        return None
    identities = sidecar_identities(source)
    joined = "\n".join(sorted(identities))
    return {
        "document_session": str(document.get("session") or "") or None,
        "observed_at": str(document.get("observed_at") or "") or None,
        "generated_at": str(document.get("generated_at") or "") or None,
        "identity_count": len(identities),
        "identity_sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
        "bytes": source.stat().st_size,
    }


def evidence_clock(directory: Path) -> dict[str, Any] | None:
    """High-water marks of the two local evidence snapshots."""
    root = Path(directory)
    files: dict[str, Any] = {}
    for name in _EVIDENCE_FILES:
        path = root / name
        if not path.is_file():
            continue
        files[name] = _scan_evidence(path)
    if not files:
        return None
    max_session = ""
    max_bar = ""
    max_observed = ""
    for item in files.values():
        max_session = max(max_session, item["max_session"])
        max_bar = max(max_bar, item["max_bar_ts"])
        max_observed = max(max_observed, item["max_observed_at"])
    return {
        "files": files,
        "max_session": max_session or None,
        "max_bar_ts": max_bar or None,
        "max_observed_at": max_observed or None,
    }


def sweet_clock(path: Path) -> dict[str, Any] | None:
    """Sweetspot observer CSV size and latest t0_date. Return columns are not read."""
    source = Path(path)
    if not source.is_file():
        return None
    latest = ""
    rows = 0
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            latest = max(latest, str(row.get("t0_date") or ""))
    return {
        "bytes": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "rows": rows,
        "max_t0": latest or None,
    }


def divergence(
    stored: Mapping[str, Any] | None,
    *,
    sidecar: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    sweet: Mapping[str, Any] | None = None,
) -> list[str]:
    """Reasons the files on disk are ahead of the stored board clocks."""
    record = stored or {}
    reasons: list[str] = []
    if sidecar and record.get("sidecar_observed_at") and sidecar.get("observed_at"):
        if str(sidecar["observed_at"]) > str(record["sidecar_observed_at"]):
            reasons.append("SIDECAR_OBSERVED_AT_AHEAD")
    if sidecar and record.get("sidecar_identity_sha256") and sidecar.get("identity_sha256"):
        if sidecar["identity_sha256"] != record["sidecar_identity_sha256"]:
            reasons.append("SIDECAR_IDENTITIES_CHANGED")
    stored_files = record.get("evidence_files") or {}
    for name, item in (evidence or {}).get("files", {}).items():
        previous = str((stored_files.get(name) or {}).get("sha256") or "")
        if previous and previous != item.get("sha256"):
            reasons.append(f"EVIDENCE_CHANGED:{name}")
    if sweet and record.get("sweet_sha256") and sweet.get("sha256"):
        if sweet["sha256"] != record["sweet_sha256"]:
            reasons.append("SWEETSPOT_CSV_CHANGED")
    return reasons


def status_for(stored: Mapping[str, Any] | None, reasons: list[str]) -> str:
    if reasons:
        return STALE_DATA
    recorded = str((stored or {}).get("status") or "")
    if recorded in {FRESH, STALE_DATA, UNVERIFIED}:
        return recorded
    return UNVERIFIED


def _sidecar_document(path: Path) -> dict[str, Any] | None:
    source = Path(path)
    if not source.is_file():
        return None
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return None
    return document


def _identity(record: object, *, freeze: bool) -> str | None:
    if not isinstance(record, Mapping):
        return None
    symbol = str(record.get("symbol") or "").strip().upper()
    session = str(record.get("session") or "").strip()
    seen = str(record.get("candidate_first_seen_ts") or "").strip()
    if freeze:
        source = SOURCE_BRAIN_A
    else:
        source = str(record.get("source") or record.get("nomination_source") or "").strip()
    if not source or not symbol or not session or not seen:
        return None
    return f"{source}|{session}|{symbol}|{seen}"


def _scan_evidence(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    max_session = ""
    max_bar = ""
    max_observed = ""
    rows = 0
    with path.open("rb") as handle:
        for raw in handle:
            digest.update(raw)
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            rows += 1
            max_session = max(max_session, str(row.get("session") or ""))
            max_bar = max(max_bar, str(row.get("bar_ts") or ""))
            max_observed = max(max_observed, str(row.get("observed_at") or ""))
    return {
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "rows": rows,
        "max_session": max_session,
        "max_bar_ts": max_bar,
        "max_observed_at": max_observed,
    }
