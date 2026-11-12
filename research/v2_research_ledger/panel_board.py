"""Read-only board projected from the durable row store.

Horizon cells are not calculated. The historical 1,055-row panel is not
filled in from later files.
"""

from __future__ import annotations

from typing import Any

from research.v2_research_ledger.contract import HORIZONS, SOURCE_BRAIN_A, SOURCE_SWEETSPOT
from research.v2_research_ledger.durable_store import DurableRowStore

HORIZON_STATUS = "UNAVAILABLE_NOT_RECOMPUTED"
PANEL_SCHEMA = "v2_research_row_panel.v1"
RESEARCH_DECISIONS = frozenset({"ACCEPTED", "REJECTED", "NOMINATED"})


def load_row_panel(store: DurableRowStore) -> dict[str, Any] | None:
    """Return the panel document, or None when the store has not been created."""
    manifest = store.read_manifest()
    if manifest is None:
        return None
    rows = [_panel_row(row, store) for row in store.identities.values()]
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
    reasons.append("UNAVAILABLE:row_horizons")
    by_source: dict[str, int] = {}
    for row in rows:
        label = str(row.get("source") or "")
        by_source[label] = by_source.get(label, 0) + 1
    return {
        "as_of": None,
        "coverage": {
            "by_source": by_source,
            "deduped_research_observations": len(deduped),
            "rows": len(rows),
            "sidecar_identities": sidecar_identities,
        },
        "freshness": {
            "reasons": reasons,
            "source_health": health,
            "status": "UNVERIFIED",
        },
        "historical_approximate_view": "preserved_not_recomputed",
        "historical_row_panel": "UNAVAILABLE",
        "price_book": "absent",
        "rows": rows,
        "schema": PANEL_SCHEMA,
        "source_updated_at": None,
        "t_plus_recomputed": False,
    }


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


def _panel_row(record: dict[str, Any], store: DurableRowStore) -> dict[str, Any]:
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
    horizons = {f"T+{step}": {"return_pct": None, "status": HORIZON_STATUS} for step in HORIZONS}
    return {
        "action_state": "NO_OBSERVATION",
        "age_sessions": None,
        "candidate_first_seen_ts": seen or None,
        "decision": record.get("decision"),
        "horizons": horizons,
        "lifecycle": "STORED",
        "market_real": record.get("market_real"),
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
