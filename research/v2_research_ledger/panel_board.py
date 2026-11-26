"""Read-only board projected from the durable row store.

A verified derived generation can fill horizon cells. A missing or invalid
generation leaves them UNAVAILABLE_NOT_RECOMPUTED. The historical 1,055-row
panel is not filled in from later files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from research.v2_research_ledger.contract import HORIZONS, SOURCE_BRAIN_A, SOURCE_SWEETSPOT
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.forward_outcomes import (
    FALLBACK_STATUS,
    ForwardBuildError,
    attachable_outcomes,
    display_horizon,
    file_hashes,
    population_for,
)

HORIZON_STATUS = "UNAVAILABLE_NOT_RECOMPUTED"
PANEL_SCHEMA = "v2_research_row_panel.v1"
RESEARCH_DECISIONS = frozenset({"ACCEPTED", "REJECTED", "NOMINATED"})


def load_row_panel(store: DurableRowStore, *, outcomes_root: Any = None) -> dict[str, Any] | None:
    """Return the panel document, or None when the store has not been created."""
    manifest = store.read_manifest()
    if manifest is None:
        return None
    attached = attachable_outcomes(store.directory, outcomes_root)
    by_outcome = {str(row.get("identity_id") or ""): row for row in (attached or {}).get("rows") or []}
    rows = [_panel_row(row, store, by_outcome.get(str(row.get("identity_id") or ""))) for row in store.identities.values()]
    rows.sort(key=lambda item: (str(item.get("t0_date") or ""), str(item.get("symbol") or ""), str(item.get("row_id") or "")))
    deduped = deduped_research_observations(store)
    sidecar_identities = sum(1 for row in store.identities.values() if row.get("record_role") == "sidecar_identity")
    health = {
        "action_evidence": {"status": (manifest.get("action_evidence") or {}).get("status") or "MISSING"},
        "historical_row_panel": {"status": "UNAVAILABLE"},
        "sidecar": {"status": (manifest.get("sidecar") or {}).get("status") or "MISSING"},
        "sweetspot": {"status": (manifest.get("sweetspot") or {}).get("status") or "MISSING"},
    }
    reasons = []
    for name, item in health.items():
        status = item["status"]
        if status == "MISSING":
            reasons.append(f"MISSING_SOURCE:{name}")
        elif status == "UNAVAILABLE":
            reasons.append(f"UNAVAILABLE:{name}")
        elif status == "PRESENT_NOT_INTERPRETED":
            reasons.append(f"PRESENT_NOT_INTERPRETED:{name}")
    if attached is None:
        reasons.append("UNAVAILABLE:row_horizons")
    else:
        reasons.append("ATTACHED:forward_outcomes")
    freshness = _freshness(store, manifest, attached, reasons)
    by_source: dict[str, int] = {}
    for row in rows:
        label = str(row.get("source") or "")
        by_source[label] = by_source.get(label, 0) + 1
    return {
        "as_of": freshness.get("latest_measured_session") if freshness.get("fingerprint_matches") is True else None,
        "coverage": {
            "by_source": by_source,
            "deduped_research_observations": len(deduped),
            "rows": len(rows),
            "sidecar_identities": sidecar_identities,
        },
        "freshness": freshness,
        "forward_outcomes": {
            "as_of": None if attached is None else attached.get("as_of"),
            "calculation_version": None if attached is None else attached.get("calculation_version"),
            "reference_sha256": None if attached is None else attached.get("reference_sha256"),
            "status": FALLBACK_STATUS if attached is None else "attached",
        },
        "historical_approximate_view": "preserved_not_recomputed",
        "historical_row_panel": "UNAVAILABLE",
        "price_book": "absent" if attached is None else "APPROX_LAST_5M_CLOSE",
        "rows": rows,
        "schema": PANEL_SCHEMA,
        "source_updated_at": freshness.get("source_updated_at") if freshness.get("fingerprint_matches") is True else None,
        "t_plus_recomputed": False,
    }


def _freshness(
    store: DurableRowStore,
    manifest: dict[str, Any],
    attached: dict[str, Any] | None,
    reasons: list[str],
) -> dict[str, Any]:
    """Clocks come from the attached generation. A missing field stays missing."""
    if attached is None:
        return {"fingerprint_matches": False, "reasons": reasons, "source_health": _health(manifest), "status": "UNVERIFIED"}
    try:
        fingerprint_matches = attached.get("ledger_hashes") == file_hashes(store.directory)
    except (OSError, UnicodeError):
        fingerprint_matches = False
    if not fingerprint_matches:
        reasons.append("FINGERPRINT_MISMATCH")
        return {"fingerprint_matches": False, "reasons": reasons, "source_health": _health(manifest), "status": "UNVERIFIED"}
    source_state = _source_state(manifest, store.directory)
    if source_state == "MATCHED":
        status = "VERIFIED"
    elif source_state == "LATE":
        status = "LATE"
        reasons.append("SOURCE_LATE")
    else:
        status = "MISSING"
        reasons.append("SOURCE_EVIDENCE_MISSING")
    sealed = [str(row.get("t0_date") or "") for row in attached.get("rows") or [] if isinstance(row, dict) and row.get("t0_date")]
    return {
        "artifact_generated_at": attached.get("artifact_generated_at") or None,
        "fingerprint_matches": True,
        "latest_measured_session": attached.get("as_of") or None,
        "latest_sealed_t0": max(sealed) if sealed else None,
        "latest_t0": max(sealed) if sealed else None,
        "reasons": reasons,
        "source_health": _health(manifest),
        "source_updated_at": attached.get("source_updated_at") or None,
        "status": status,
    }


def _health(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "action_evidence": {"status": (manifest.get("action_evidence") or {}).get("status") or "MISSING"},
        "historical_row_panel": {"status": "UNAVAILABLE"},
        "sidecar": {"status": (manifest.get("sidecar") or {}).get("status") or "MISSING"},
        "sweetspot": {"status": (manifest.get("sweetspot") or {}).get("status") or "MISSING"},
    }


def _source_state(manifest: dict[str, Any], store_dir: Path) -> str:
    """MATCHED when both source files still have the sealed hashes. Otherwise LATE or MISSING."""
    for key in ("sidecar", "sweetspot"):
        block = manifest.get(key) if isinstance(manifest.get(key), dict) else {}
        recorded = str(block.get("sha256") or "")
        relative = str(block.get("path") or "")
        if not recorded or not relative:
            return "MISSING"
        found = _source_file(store_dir, relative)
        if found is None:
            return "MISSING"
        if _sha256_file(found) != recorded:
            return "LATE"
    return "MATCHED"


def _source_file(store_dir: Path, relative: str) -> Path | None:
    parts = Path(relative).parts
    if not relative or relative.startswith("/") or ".." in parts:
        return None
    for root in (store_dir, *store_dir.parents):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deduped_research_observations(store: DurableRowStore) -> dict[tuple[str, str, str], dict[str, Any]]:
    """One observation per explicit source, symbol, and T0 date.

    Sidecar freeze rows with no explicit decision stay identities only.
    Two identities with different decisions on the same key stay stored and
    the observation is marked STATE_CONFLICT.
    """
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in store.identities.values():
        qualified = _qualified(record, store)
        if qualified is None:
            continue
        source, symbol, session = qualified
        if not symbol or not session:
            continue
        grouped.setdefault((source, symbol, session), []).append(record)
    chosen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, records in grouped.items():
        records.sort(key=lambda item: (str(item.get("candidate_first_seen_ts") or ""), str(item.get("identity_id") or "")))
        decisions = {str(item.get("decision") or "") for item in records}
        representative = dict(records[0])
        if len(decisions) > 1:
            representative["decision"] = "STATE_CONFLICT"
        representative["duplicate_identity_ids"] = [str(item["identity_id"]) for item in records[1:]]
        chosen[key] = representative
    return chosen


def _qualified(record: dict[str, Any], store: DurableRowStore) -> tuple[str, str, str] | None:
    decision = str(record.get("decision") or "")
    source = str(record.get("source_field") or "")
    if record.get("record_role") == "sweetspot_identity" and decision in RESEARCH_DECISIONS and source == SOURCE_SWEETSPOT:
        return source, str(record.get("symbol") or ""), str(record.get("t0_date") or "")
    if source and decision in RESEARCH_DECISIONS:
        return source, str(record.get("symbol") or ""), str(record.get("t0_date") or "")
    link = store.links.get(f"nomination|{record.get('identity_id')}")
    if link and str(link.get("source_field") or "") and str(link.get("status") or "") in RESEARCH_DECISIONS | {"NOMINATED"}:
        return str(link["source_field"]), str(record.get("symbol") or ""), str(record.get("t0_date") or "")
    if link and str(link.get("status") or "") == "NOMINATED":
        return SOURCE_BRAIN_A, str(record.get("symbol") or ""), str(record.get("t0_date") or "")
    return None


def _panel_row(record: dict[str, Any], store: DurableRowStore, outcome: dict[str, Any] | None) -> dict[str, Any]:
    source_field = record.get("source_field")
    flags = [f"decision={record.get('decision') or 'DECISION_UNAVAILABLE'}"]
    if record.get("decision_detail") and record.get("decision_detail") != record.get("decision"):
        flags.append(f"decision_detail={record.get('decision_detail')}")
    if source_field:
        source = str(source_field)
    else:
        source = "sidecar_freeze"
        flags.append("SOURCE_FIELD_ABSENT")
        flags.append(f"ATTRIBUTION={record.get('source_attribution') or ''}")
        flags.append(f"BASIS={record.get('attribution_basis') or ''}")
    seen = str(record.get("candidate_first_seen_ts") or "")
    session = str(record.get("t0_date") or "")
    if seen and session and not seen.startswith(session):
        flags.append("PROVENANCE_DATE_DIFFERS")
    if not record.get("symbol"):
        flags.append("SYMBOL_ABSENT")
    flags.append("ACTION_EVIDENCE_MISSING")
    link = store.links.get(f"nomination|{record.get('identity_id')}")
    if link:
        flags.append(f"nomination_status={link.get('status') or ''}")
    try:
        population = population_for(record, store.links)
    except ForwardBuildError:
        population = "unknown"
    outcome_horizons = outcome.get("horizons") if isinstance(outcome, dict) else None
    if isinstance(outcome_horizons, dict):
        horizons = {f"T+{step}": display_horizon(outcome_horizons.get(f"T+{step}") or {}) for step in HORIZONS}
    else:
        horizons = {f"T+{step}": {"return_pct": None, "status": HORIZON_STATUS} for step in HORIZONS}
    return {
        "action_state": "NO_OBSERVATION",
        "age_sessions": None,
        "candidate_first_seen_ts": seen or None,
        "decision": record.get("decision"),
        "horizons": horizons,
        "lifecycle": "STORED",
        "market_real": record.get("market_real"),
        "population": population,
        "quality_status": ";".join(flags),
        "record_role": record.get("record_role"),
        "row_id": record.get("identity_id"),
        "setup": record.get("setup"),
        "source": source,
        "symbol": record.get("symbol") or "",
        "t0_date": session,
        "t0_price": record.get("t0_price"),
        "t0_price_provenance": record.get("origin_file"),
    }
