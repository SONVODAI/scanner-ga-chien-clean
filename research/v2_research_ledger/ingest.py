"""Stage A read-only ingest adapters for the isolated Research Ledger.

Reads existing Brain A nomination-shadow JSON, Sweetspot observer CSV, and
V2 Action evidence/state artifacts. Does not import scanners, collectors,
Live V2, V2 Action evaluators, or production writers. Does not build or
promote a publisher board (Stage B/C).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from research.v2_research_ledger.contract import (
    ACTION_STATES,
    MARKET_CONTEXT_REF_ACTION,
    MARKET_CONTEXT_REF_BRAIN_A_SHADOW,
    MARKET_CONTEXT_REF_SWEETSPOT,
    NOMINATION_ACCEPTED,
    NOMINATION_REJECTED,
    SOURCE_BRAIN_A,
    SOURCE_SWEETSPOT,
    STATE_NO_OBSERVATION,
    STREAM_LIVE_WHEN,
    STREAM_POST_CLOSE,
    T0_MISSING,
    T0_PRESENT,
)
from research.v2_research_ledger.ledger import ResearchLedger


@dataclass
class IngestCounts:
    """How many records were written vs skipped as duplicates."""

    nominations_added: int = 0
    nominations_duplicate: int = 0
    rejected_added: int = 0
    rejected_duplicate: int = 0
    raw_added: int = 0
    raw_duplicate: int = 0
    raw_skipped_invalid: int = 0
    links_added: int = 0
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "IngestCounts") -> "IngestCounts":
        self.nominations_added += other.nominations_added
        self.nominations_duplicate += other.nominations_duplicate
        self.rejected_added += other.rejected_added
        self.rejected_duplicate += other.rejected_duplicate
        self.raw_added += other.raw_added
        self.raw_duplicate += other.raw_duplicate
        self.raw_skipped_invalid += other.raw_skipped_invalid
        self.links_added += other.links_added
        self.notes.extend(other.notes)
        return self


def _text(value: object) -> str:
    return str(value or "").strip()


def _symbol(value: object) -> str:
    return _text(value).upper()


def _opt_num(raw: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in raw or raw.get(key) in (None, ""):
            continue
        try:
            return float(raw[key])
        except (TypeError, ValueError):
            continue
    return None


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _session_from_timestamp(value: object) -> str:
    text = _text(value)
    return text[:10] if len(text) >= 10 else text


def infer_action_stream(path: Path | str | None, explicit: str | None = None) -> str:
    """Map evidence filename → ledger source_stream. Explicit wins."""
    if explicit:
        stream = _text(explicit)
        if stream not in {STREAM_LIVE_WHEN, STREAM_POST_CLOSE}:
            raise ValueError(f"unsupported source_stream {stream}")
        return stream
    name = Path(path or "").name.lower()
    if "live_when" in name:
        return STREAM_LIVE_WHEN
    if "post_close" in name:
        return STREAM_POST_CLOSE
    # Default producer name is v2_action_evidence.jsonl (post-close observe).
    return STREAM_POST_CLOSE


def ingest_brain_a_shadow(
    ledger: ResearchLedger,
    document: Mapping[str, Any] | Path,
) -> IngestCounts:
    """Accepted + rejected Brain A shadow rows → nomination records."""
    doc = _load_json_object(document) if isinstance(document, Path) else dict(document)
    counts = IngestCounts()
    observed_at = _text(doc.get("observed_at") or doc.get("generated_at"))
    doc_session = _session_from_timestamp(observed_at)
    market_real = _opt_num(doc, "market_real")
    market_permission = _text(doc.get("market_permission")) or None
    source = _text(doc.get("source")) or SOURCE_BRAIN_A

    for raw in doc.get("nominations") or []:
        if not isinstance(raw, Mapping):
            continue
        symbol = _symbol(raw.get("symbol"))
        first_seen = _text(raw.get("candidate_first_seen_ts"))
        provenance = _text(raw.get("session")) or doc_session
        if not symbol or not first_seen or not provenance:
            counts.raw_skipped_invalid += 1
            continue
        row_market = _opt_num(raw, "market_real")
        payload = {
            "source": _text(raw.get("source")) or source,
            "provenance_session": provenance,
            "symbol": symbol,
            "setup": _text(raw.get("setup")) or None,
            "group": _text(raw.get("group") or raw.get("setup")) or None,
            "disposition": NOMINATION_ACCEPTED,
            "source_status": _text(raw.get("status")) or None,
            "candidate_first_seen_ts": first_seen,
            "eligible_from": _text(raw.get("eligible_from")) or None,
            "price_at_first_seen": _opt_num(raw, "price_at_first_seen"),
            "ema9_at_first_seen": _opt_num(raw, "ema9_at_first_seen"),
            "breakout_ref_at_first_seen": _opt_num(raw, "breakout_ref_at_first_seen"),
            "market_permission": _text(raw.get("market_permission")) or market_permission,
            "market_real_at_nomination": row_market if row_market is not None else market_real,
            "market_context_source": MARKET_CONTEXT_REF_BRAIN_A_SHADOW,
            "published_document_session": doc_session or None,
            "published_observed_at": observed_at or None,
            "price_source": "brain_a_freeze",
            "adjustment_status": "UNAVAILABLE",
            "is_live_adjusted": False,
            "t0_status": T0_PRESENT,
        }
        added = ledger.add_nomination(payload)
        if added is None:
            counts.nominations_duplicate += 1
        else:
            counts.nominations_added += 1

    for raw in doc.get("rejected") or []:
        if not isinstance(raw, Mapping):
            continue
        symbol = _symbol(raw.get("symbol"))
        reason = _text(raw.get("reason"))
        if not symbol or not reason:
            counts.raw_skipped_invalid += 1
            continue
        provenance = doc_session
        # Rejected shadow rows do not own a Brain A freeze. Never borrow
        # freeze_ledger prices or invent a T0 clock.
        payload = {
            "source": source,
            "provenance_session": provenance,
            "symbol": symbol,
            "setup": _text(raw.get("setup")) or None,
            "group": _text(raw.get("setup")) or None,
            "disposition": NOMINATION_REJECTED,
            "rejection_reason": reason,
            "source_status": reason,
            "t0_status": T0_MISSING,
            "candidate_first_seen_ts": None,
            "eligible_from": None,
            "price_at_first_seen": None,
            "ema9_at_first_seen": None,
            "breakout_ref_at_first_seen": None,
            "market_permission": market_permission,
            "market_real_at_nomination": market_real,
            "market_context_source": MARKET_CONTEXT_REF_BRAIN_A_SHADOW,
            "published_document_session": doc_session or None,
            "published_observed_at": observed_at or None,
            "price_source": None,
            "adjustment_status": "UNAVAILABLE",
            "is_live_adjusted": False,
        }
        added = ledger.add_nomination(payload)
        if added is None:
            counts.rejected_duplicate += 1
        else:
            counts.rejected_added += 1
    return counts


def ingest_sweetspot_observer(
    ledger: ResearchLedger,
    source: Path | Sequence[Mapping[str, Any]],
) -> IngestCounts:
    """Sweetspot observer ledger rows → independent Sweetspot nominations."""
    counts = IngestCounts()
    if isinstance(source, Path):
        with Path(source).open(newline="", encoding="utf-8") as handle:
            rows: Iterable[Mapping[str, Any]] = list(csv.DictReader(handle))
    else:
        rows = source

    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        symbol = _symbol(raw.get("symbol"))
        t0_date = _text(raw.get("t0_date"))
        if not symbol or not t0_date:
            # Context-only rows (empty symbol) are not candidates.
            continue
        created_at = _text(raw.get("created_at"))
        # Daily freeze identity: one accepted row per symbol+t0_date (created_at is audit only).
        first_seen = f"{t0_date}T09:15:00+07:00"
        observer_status = _text(raw.get("observer_status"))
        matched = _text(raw.get("matched_sweetspot"))
        # Preserve non-matched / insufficient rows as REJECTED when status says so.
        rejected_markers = {
            "INSUFFICIENT_CONTEXT_EVIDENCE",
            "REJECTED",
            "NO_MATCH",
            "EXCLUDED",
        }
        is_rejected = observer_status in rejected_markers and not matched
        disposition = NOMINATION_REJECTED if is_rejected else NOMINATION_ACCEPTED
        price_t0 = _opt_num(raw, "price_t0")
        payload: dict[str, Any] = {
            "source": SOURCE_SWEETSPOT,
            "provenance_session": t0_date,
            "symbol": symbol,
            "setup": _text(raw.get("origin_setup") or raw.get("sweetspot_horizon")) or None,
            "group": _text(raw.get("origin_group") or raw.get("origin_setup")) or None,
            "disposition": disposition,
            "source_status": observer_status or None,
            # Accepted rows keep a session clock for identity; price-less ⇒ T0_MISSING.
            "candidate_first_seen_ts": first_seen
            if disposition == NOMINATION_ACCEPTED or price_t0 is not None
            else None,
            "eligible_from": first_seen if price_t0 is not None else None,
            "price_at_first_seen": price_t0,
            "ema9_at_first_seen": _opt_num(raw, "origin_ema9") if price_t0 is not None else None,
            "breakout_ref_at_first_seen": _opt_num(raw, "origin_breakout_ref")
            if price_t0 is not None
            else None,
            "market_permission": None,
            "market_real_at_nomination": _opt_num(raw, "market_real_t0"),
            "market_context_source": _text(raw.get("market_context_key"))
            or MARKET_CONTEXT_REF_SWEETSPOT,
            "published_document_session": t0_date,
            "published_observed_at": created_at or None,
            "price_source": "sweetspot_observer_t0" if price_t0 is not None else None,
            "adjustment_status": "UNAVAILABLE",
            "is_live_adjusted": False,
            "t0_status": T0_PRESENT if price_t0 is not None else T0_MISSING,
        }
        if disposition == NOMINATION_REJECTED:
            payload["rejection_reason"] = observer_status or "SWEETSPOT_REJECTED"
            if price_t0 is None:
                payload["t0_status"] = T0_MISSING
                payload["candidate_first_seen_ts"] = None
                payload["eligible_from"] = None
        added = ledger.add_nomination(payload)
        if disposition == NOMINATION_REJECTED:
            if added is None:
                counts.rejected_duplicate += 1
            else:
                counts.rejected_added += 1
        else:
            if added is None:
                counts.nominations_duplicate += 1
            else:
                counts.nominations_added += 1
    return counts


def _action_payload_from_evidence(
    raw: Mapping[str, Any],
    *,
    source_stream: str,
) -> dict[str, Any] | None:
    symbol = _symbol(raw.get("symbol"))
    bar_ts = _text(raw.get("bar_ts"))
    observed_at = _text(raw.get("observed_at") or raw.get("asof") or bar_ts)
    state = _text(raw.get("action_state") or raw.get("shadow_action"))
    if not symbol or not bar_ts or not observed_at or state not in ACTION_STATES:
        return None
    session = _text(raw.get("session") or raw.get("observation_session"))
    provenance = _text(raw.get("provenance_session") or raw.get("session"))
    market_real = _opt_num(raw, "market_real_at_decision", "market_real")
    return {
        "source_stream": source_stream,
        "symbol": symbol,
        "bar_ts": bar_ts,
        "asof": _text(raw.get("asof")) or None,
        "observed_at": observed_at,
        "action_state": state,
        "action_reason": _text(raw.get("action_reason")) or None,
        "route": _text(raw.get("route")) or "UNKNOWN",
        "setup": _text(raw.get("setup")) or None,
        "group": _text(raw.get("group")) or None,
        "evaluation_session": session or _session_from_timestamp(bar_ts) or None,
        "provenance_session": provenance or session or None,
        "candidate_first_seen_ts": _text(raw.get("candidate_first_seen_ts")) or None,
        "eligible_from": _text(raw.get("eligible_from")) or None,
        "open": _opt_num(raw, "open"),
        "high": _opt_num(raw, "high"),
        "low": _opt_num(raw, "low"),
        "close": _opt_num(raw, "close", "close_canonical", "trigger_price"),
        "volume": _opt_num(raw, "volume"),
        "frozen_reference_kind": _text(
            raw.get("frozen_reference_kind") or raw.get("frozen_ref_kind")
        )
        or None,
        "frozen_reference_value": _opt_num(
            raw, "frozen_reference_value", "frozen_ref_value"
        ),
        "market_permission": _text(raw.get("market_permission")) or None,
        "market_real_at_decision": market_real,
        "market_context_source": MARKET_CONTEXT_REF_ACTION if market_real is not None else None,
        "price_source": _text(raw.get("price_source")) or "v2_action_evidence",
        "adjustment_status": _text(raw.get("adjustment_status")) or "UNAVAILABLE",
        "origin_nomination_id": _text(raw.get("origin_nomination_id")) or None,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
    }


def ingest_v2_action_evidence(
    ledger: ResearchLedger,
    source: Path | Sequence[Mapping[str, Any]],
    *,
    source_stream: str | None = None,
) -> IngestCounts:
    """V2 Action evidence JSONL → raw action events (WAIT / BUY_READY / …)."""
    counts = IngestCounts()
    if isinstance(source, Path):
        stream = infer_action_stream(source, source_stream)
        rows: Sequence[Mapping[str, Any]] = _load_jsonl(source)
    else:
        stream = infer_action_stream(None, source_stream or STREAM_POST_CLOSE)
        rows = source

    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        # Fail closed on production BUY flags — ledger.add_raw_action also rejects.
        payload = _action_payload_from_evidence(raw, source_stream=stream)
        if payload is None:
            counts.raw_skipped_invalid += 1
            continue
        try:
            added = ledger.add_raw_action(payload)
        except ValueError:
            counts.raw_skipped_invalid += 1
            continue
        if added is None:
            counts.raw_duplicate += 1
        else:
            counts.raw_added += 1
    return counts


def ingest_v2_action_state(
    ledger: ResearchLedger,
    document: Mapping[str, Any] | Path,
    *,
    source_stream: str | None = None,
) -> IngestCounts:
    """State document rows → raw events, including NO_OBSERVATION without bars.

    Evidence JSONL only emits completed bars. NO_OBSERVATION / empty-bar WAIT
    rows still appear on ``v2_action_state.json`` and must stay distinct.
    """
    doc = _load_json_object(document) if isinstance(document, Path) else dict(document)
    counts = IngestCounts()
    stream = infer_action_stream(
        document if isinstance(document, Path) else None,
        source_stream or STREAM_POST_CLOSE,
    )
    observed_at = _text(doc.get("observed_at"))
    observation_session = _text(doc.get("session"))

    for raw in doc.get("rows") or []:
        if not isinstance(raw, Mapping):
            continue
        symbol = _symbol(raw.get("symbol"))
        state = _text(raw.get("shadow_action") or raw.get("action_state"))
        if not symbol or state not in ACTION_STATES:
            counts.raw_skipped_invalid += 1
            continue
        bar_ts = _text(
            raw.get("last_legal_bar_ts")
            or raw.get("trigger_bar_ts")
            or raw.get("bar_ts")
        )
        row_observed = _text(raw.get("observed_at")) or observed_at
        if not bar_ts:
            # Preserve NO_OBSERVATION (and similar) without inventing OHLCV.
            if state != STATE_NO_OBSERVATION:
                counts.raw_skipped_invalid += 1
                continue
            if not row_observed:
                counts.raw_skipped_invalid += 1
                continue
            bar_ts = f"NO_BAR|{row_observed}"
        payload = {
            "source_stream": stream,
            "symbol": symbol,
            "bar_ts": bar_ts,
            "asof": bar_ts if not bar_ts.startswith("NO_BAR|") else None,
            "observed_at": row_observed or bar_ts,
            "action_state": state,
            "action_reason": _text(raw.get("action_reason")) or None,
            "route": _text(raw.get("route")) or "UNKNOWN",
            "setup": _text(raw.get("setup")) or None,
            "group": _text(raw.get("group")) or None,
            "evaluation_session": _text(raw.get("observation_session"))
            or observation_session
            or None,
            "provenance_session": _text(raw.get("session")) or observation_session or None,
            "candidate_first_seen_ts": _text(raw.get("candidate_first_seen_ts")) or None,
            "eligible_from": _text(raw.get("eligible_from")) or None,
            "open": None,
            "high": None,
            "low": None,
            "close": _opt_num(raw, "trigger_price", "close_canonical", "close"),
            "volume": None,
            "frozen_reference_kind": _text(raw.get("frozen_ref_kind")) or None,
            "frozen_reference_value": _opt_num(raw, "frozen_ref_value"),
            "market_permission": _text(raw.get("market_permission")) or None,
            "market_real_at_decision": _opt_num(raw, "market_real"),
            "market_context_source": MARKET_CONTEXT_REF_ACTION
            if _opt_num(raw, "market_real") is not None
            else None,
            "price_source": "v2_action_state",
            "adjustment_status": "UNAVAILABLE",
            "origin_nomination_id": None,
            "candidate_is_buy": False,
            "pxv_implies_buy": False,
            "alert_eligible": False,
        }
        try:
            added = ledger.add_raw_action(payload)
        except ValueError:
            counts.raw_skipped_invalid += 1
            continue
        if added is None:
            counts.raw_duplicate += 1
        else:
            counts.raw_added += 1
    return counts


def link_overlapping_sources(ledger: ResearchLedger) -> IngestCounts:
    """Link Brain A ↔ Sweetspot nominations that share symbol + provenance day.

    Provenance sources stay independent records; OVERLAP is an edge only.
    """
    counts = IngestCounts()
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in ledger.nominations:
        if row.get("disposition") == NOMINATION_REJECTED:
            continue
        symbol = _text(row.get("symbol"))
        session = _text(row.get("provenance_session"))
        source = _text(row.get("source"))
        ident = _text(row.get("nomination_id"))
        if not symbol or not session or not ident:
            continue
        key = (symbol, session)
        bucket = by_key.setdefault(key, {})
        bucket[source] = ident
    for bucket in by_key.values():
        left = bucket.get(SOURCE_BRAIN_A)
        right = bucket.get(SOURCE_SWEETSPOT)
        if not left or not right:
            continue
        linked = ledger.link_overlap(left, right)
        if linked is not None:
            counts.links_added += 1
    return counts


def ingest_stage_a(
    ledger: ResearchLedger,
    *,
    brain_a_shadow: Mapping[str, Any] | Path | None = None,
    sweetspot_csv: Path | Sequence[Mapping[str, Any]] | None = None,
    action_evidence: Path | Sequence[Mapping[str, Any]] | None = None,
    action_state: Mapping[str, Any] | Path | None = None,
    action_stream: str | None = None,
    link_overlaps: bool = True,
) -> IngestCounts:
    """Run the Stage A adapters. Safe to call repeatedly (idempotent)."""
    total = IngestCounts()
    if brain_a_shadow is not None:
        total.merge(ingest_brain_a_shadow(ledger, brain_a_shadow))
    if sweetspot_csv is not None:
        total.merge(ingest_sweetspot_observer(ledger, sweetspot_csv))
    if action_evidence is not None:
        total.merge(
            ingest_v2_action_evidence(
                ledger, action_evidence, source_stream=action_stream
            )
        )
    if action_state is not None:
        total.merge(
            ingest_v2_action_state(ledger, action_state, source_stream=action_stream)
        )
    if link_overlaps:
        total.merge(link_overlapping_sources(ledger))
    return total
