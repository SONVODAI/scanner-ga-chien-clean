"""Copy existing sidecar and SweetSpot rows into the durable store.

This module does not read Guardian sessions, does not evaluate V2 Action,
and does not compute T+ returns. A missing source is recorded as missing.
Rows are not invented to replace it.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from research.v2_research_ledger.contract import SOURCE_BRAIN_A, SOURCE_SWEETSPOT
from research.v2_research_ledger.durable_store import (
    CONFLICT,
    INSERTED,
    SCHEMA,
    UNCHANGED,
    DurableRowStore,
    canonical_number,
)

BRAIN_A_FREEZE_BASIS = "sidecar_freeze_ledger_brain_a_contract"
SWEET_BASIS = "sweetspot_observer_ledger"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
NOMINATED = "NOMINATED"
DECISION_UNAVAILABLE = "DECISION_UNAVAILABLE"
ACTION_EVIDENCE_FILES = (
    "live_when_v2_action_evidence.jsonl",
    "post_close_v2_action_evidence.jsonl",
)


def ingest_sources(
    store: DurableRowStore,
    *,
    sidecar_path: Path | None,
    sweet_csv: Path | None,
    evidence_dir: Path | None,
) -> dict[str, Any]:
    """Insert identities once. A second call with the same sealed fields does not append."""
    counts = {INSERTED: 0, UNCHANGED: 0, CONFLICT: 0}
    sidecar_status = _ingest_sidecar(store, sidecar_path, counts)
    sweet_status = _ingest_sweetspot(store, sweet_csv, counts)
    evidence_status = _evidence_status(evidence_dir)
    manifest = {
        "action_evidence": evidence_status,
        "approximate_view_modified": False,
        "conflict_count": len(store.conflicts),
        "counts": counts,
        "final_buy_enabled": False,
        "historical_row_panel": {
            "detail": "The 1055-row research panel file is not in the repository.",
            "status": "UNAVAILABLE",
        },
        "identity_count": len(store.identities),
        "link_count": len(store.links),
        "schema_records": SCHEMA,
        "sidecar": sidecar_status,
        "sweetspot": sweet_status,
        "t_plus_recomputed": False,
    }
    store.write_manifest(manifest)
    return manifest


def _ingest_sidecar(store: DurableRowStore, path: Path | None, counts: dict[str, int]) -> dict[str, Any]:
    if path is None or not Path(path).is_file():
        return {"path": str(path) if path else "", "status": "MISSING"}
    source = Path(path)
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return {"path": _display_path(source), "sha256": _sha256(source), "status": "UNREADABLE"}
    freeze = document.get("freeze_ledger") if isinstance(document.get("freeze_ledger"), list) else []
    rows = document.get("rows") if isinstance(document.get("rows"), list) else []
    freeze_keys: dict[tuple[str, str, str], str] = {}
    for raw in freeze:
        if not isinstance(raw, dict):
            continue
        record = _freeze_identity(raw, source)
        if record is None:
            continue
        result = store.put_identity(record)
        counts[result] = counts.get(result, 0) + 1
        freeze_keys[(record["t0_date"], record["symbol"], record["candidate_first_seen_ts"])] = record["identity_id"]
    linked = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = (
            str(raw.get("session") or "")[:10],
            str(raw.get("symbol") or "").strip().upper(),
            str(raw.get("candidate_first_seen_ts") or ""),
        )
        existing = freeze_keys.get(key) or _stored_sidecar_identity(store, key)
        if existing:
            if _link_matches_sealed_price(store, existing, raw):
                result = store.put_link(_nomination_link(existing, raw, document))
                counts[result] = counts.get(result, 0) + 1
                if result in {INSERTED, UNCHANGED}:
                    linked += 1
            else:
                sealed = store.identities[existing].get("sealed")
                store.record_conflict(
                    f"nomination|{existing}",
                    "LINK_PRICE_DIFFERS_FROM_SEALED_T0",
                    sealed,
                    {"t0_price": canonical_number(raw.get("price_at_first_seen"))},
                )
                counts[CONFLICT] = counts.get(CONFLICT, 0) + 1
            continue
        record = _row_identity(raw, document, source)
        if record is None:
            continue
        result = store.put_identity(record)
        counts[result] = counts.get(result, 0) + 1
    return {
        "freeze_rows": len(freeze),
        "linked_current_rows": linked,
        "path": _display_path(source),
        "sha256": _sha256(source),
        "status": "PRESENT",
    }


def _stored_sidecar_identity(store: DurableRowStore, key: tuple[str, str, str]) -> str | None:
    """Use an identity already sealed in the store. Do not invent one from the ticker."""
    session, symbol, seen = key
    if not session or not symbol or not seen:
        return None
    candidate = f"sidecar|{session}|{symbol}|{seen}"
    if candidate in store.identities:
        return candidate
    return None


def _link_matches_sealed_price(store: DurableRowStore, identity_id: str, raw: Mapping[str, Any]) -> bool:
    sealed = store.identities[identity_id].get("sealed")
    if not isinstance(sealed, dict):
        return False
    return canonical_number(raw.get("price_at_first_seen")) == sealed.get("t0_price")


def _ingest_sweetspot(store: DurableRowStore, path: Path | None, counts: dict[str, int]) -> dict[str, Any]:
    if path is None or not Path(path).is_file():
        return {"path": str(path) if path else "", "status": "MISSING"}
    source = Path(path)
    written = 0
    with source.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            record = _sweet_identity(raw, source)
            if record is None:
                continue
            result = store.put_identity(record)
            counts[result] = counts.get(result, 0) + 1
            written += 1
    return {"path": _display_path(source), "rows": written, "sha256": _sha256(source), "status": "PRESENT"}


def _evidence_status(directory: Path | None) -> dict[str, Any]:
    if directory is None:
        return {"status": "MISSING"}
    root = Path(directory)
    found = [name for name in ACTION_EVIDENCE_FILES if (root / name).is_file()]
    if not found:
        return {"path": _display_path(root), "status": "MISSING"}
    return {
        "detail": "Files are present and were not interpreted into action states.",
        "files": found,
        "path": _display_path(root),
        "status": "PRESENT_NOT_INTERPRETED",
    }


def _freeze_identity(raw: Mapping[str, Any], source: Path) -> dict[str, Any] | None:
    session = str(raw.get("session") or "")[:10]
    symbol = str(raw.get("symbol") or "").strip().upper()
    seen = str(raw.get("candidate_first_seen_ts") or "")
    if not session or not symbol or not seen:
        return None
    return {
        "attribution_basis": BRAIN_A_FREEZE_BASIS,
        "breakout_ref_at_first_seen": canonical_number(raw.get("breakout_ref_at_first_seen")),
        "candidate_first_seen_ts": seen,
        "created_at": None,
        "decision": DECISION_UNAVAILABLE,
        "decision_detail": None,
        "ema9_at_first_seen": canonical_number(raw.get("ema9_at_first_seen")),
        "identity_id": f"sidecar|{session}|{symbol}|{seen}",
        "market_real": None,
        "observer_status": None,
        "origin_file": _display_path(source),
        "origin_sha256": _sha256(source),
        "record_role": "sidecar_identity",
        "schema": SCHEMA,
        "setup": None,
        "source_attribution": SOURCE_BRAIN_A,
        "source_field": None,
        "symbol": symbol,
        "t0_date": session,
        "t0_price": canonical_number(raw.get("price_at_first_seen")),
    }


def _row_identity(raw: Mapping[str, Any], document: Mapping[str, Any], source: Path) -> dict[str, Any] | None:
    session = str(raw.get("session") or "")[:10]
    symbol = str(raw.get("symbol") or "").strip().upper()
    seen = str(raw.get("candidate_first_seen_ts") or "")
    source_field = str(raw.get("source") or "").strip()
    if not session or not symbol or not seen or not source_field:
        return None
    status = str(raw.get("status") or "").strip()
    return {
        "attribution_basis": "sidecar_row_source_field",
        "breakout_ref_at_first_seen": canonical_number(raw.get("breakout_ref_at_first_seen")),
        "candidate_first_seen_ts": seen,
        "created_at": None,
        "decision": status or DECISION_UNAVAILABLE,
        "decision_detail": status or None,
        "document_observed_at": str(document.get("observed_at") or "") or None,
        "document_session": str(document.get("session") or "")[:10] or None,
        "ema9_at_first_seen": canonical_number(raw.get("ema9_at_first_seen")),
        "identity_id": f"sidecar|{session}|{symbol}|{seen}",
        "market_real": canonical_number(raw.get("market_real")),
        "observer_status": None,
        "origin_file": _display_path(source),
        "origin_sha256": _sha256(source),
        "record_role": "sidecar_identity",
        "schema": SCHEMA,
        "setup": str(raw.get("setup") or "") or None,
        "source_attribution": source_field,
        "source_field": source_field,
        "symbol": symbol,
        "t0_date": session,
        "t0_price": canonical_number(raw.get("price_at_first_seen")),
    }


def _nomination_link(identity_id: str, raw: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "breakout_ref_at_first_seen": canonical_number(raw.get("breakout_ref_at_first_seen")),
        "document_observed_at": str(document.get("observed_at") or "") or None,
        "document_session": str(document.get("session") or "")[:10] or None,
        "ema9_at_first_seen": canonical_number(raw.get("ema9_at_first_seen")),
        "eligible_from": str(raw.get("eligible_from") or "") or None,
        "identity_id": identity_id,
        "link_id": f"nomination|{identity_id}",
        "schema": SCHEMA,
        "setup": str(raw.get("setup") or "") or None,
        "source_field": str(raw.get("source") or "").strip() or None,
        "status": str(raw.get("status") or "").strip() or None,
        "t0_price": canonical_number(raw.get("price_at_first_seen")),
    }


def _sweet_identity(raw: Mapping[str, str], source: Path) -> dict[str, Any] | None:
    observer_id = str(raw.get("observer_id") or "").strip()
    session = str(raw.get("t0_date") or "")[:10]
    created = str(raw.get("created_at") or "").strip()
    if not observer_id or not session or not created:
        return None
    status = str(raw.get("observer_status") or "").strip()
    if status == "OBSERVE":
        decision = ACCEPTED
    elif status:
        decision = REJECTED
    else:
        decision = DECISION_UNAVAILABLE
    symbol = str(raw.get("symbol") or "").strip().upper()
    return {
        "attribution_basis": SWEET_BASIS,
        "breakout_ref_at_first_seen": canonical_number(raw.get("origin_breakout_ref")),
        "candidate_first_seen_ts": created,
        "created_at": created,
        "decision": decision,
        "decision_detail": status or None,
        "ema9_at_first_seen": canonical_number(raw.get("origin_ema9")),
        "identity_id": f"sweet|{observer_id}",
        "market_real": canonical_number(raw.get("market_real_t0")),
        "observer_status": status or None,
        "origin_file": _display_path(source),
        "origin_sha256": _sha256(source),
        "record_role": "sweetspot_identity",
        "schema": SCHEMA,
        "setup": str(raw.get("origin_setup") or "") or None,
        "source_attribution": SOURCE_SWEETSPOT,
        "source_field": SOURCE_SWEETSPOT,
        "symbol": symbol,
        "t0_date": session,
        "t0_price": canonical_number(raw.get("price_t0")),
    }


def _evidence_dir_default() -> Path:
    return Path(__file__).resolve().parent / "evidence"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    text = str(path)
    marker = "research/"
    if marker in text:
        return text[text.index(marker):]
    marker = "data/"
    if marker in text:
        return text[text.index(marker):]
    return path.name
