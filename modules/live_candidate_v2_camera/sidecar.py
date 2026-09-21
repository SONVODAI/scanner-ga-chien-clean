"""Brain A ∪ Sweet Brain B nomination → V2 Camera sidecar rows.

Shadow Router chronology via enabled_sources override only.
Does not publish data/live_candidate/dynamic_watchlist.json.
Sweet Brain B is observation-only. Absence of Brain B never blocks Brain A.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from modules.candidate_router.contract import (
    ENABLED_SOURCES,
    NominatedCandidate,
    SymbolProvenance,
    WATCHLIST_COLUMNS,
)
from modules.candidate_router.router import (
    RouteReport,
    dedup_with_provenance,
    route_report,
    to_watchlist_frame,
)
from modules.live_candidate.calendar import as_vn
from modules.live_candidate.contract import has_legal_first_seen
from modules.live_candidate_v2_camera.contract import (
    DEFAULT_SIDECAR_RELPATH,
    MODE,
    PRODUCTION_WATCHLIST_RELPATH,
    SCHEMA_ID,
    SHADOW_V2_ENABLED_SOURCES,
    SLICE,
    SRC_MARKET_AWARE_SWEETSPOT,
)
from modules.live_candidate_v2_nomination.artifact import assert_not_production_watchlist
from modules.live_candidate_v2_nomination.contract import BrainANomination, FreezeRecord
from modules.live_candidate_v2_nomination.nominate import (
    NominationReport,
    from_nominated_candidate,
    nominate_scan_rows,
    to_nominated_candidate,
)
from modules.live_candidate_v2_nomination.sweet_brain_b import BrainBConsult

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIDECAR_PATH = REPO_ROOT / DEFAULT_SIDECAR_RELPATH
PRODUCTION_WATCHLIST = REPO_ROOT / PRODUCTION_WATCHLIST_RELPATH


class SidecarShadowError(RuntimeError):
    """V2 sidecar load/write failure. Not a valid empty universe."""


def shadow_route_v2(
    nominations: Iterable[NominatedCandidate],
    *,
    now: datetime,
    cap: int | None = None,
    enabled_sources: frozenset[str] | None = None,
) -> RouteReport:
    """Shadow-only route. Default enablement is Brain A, never production ENABLED_SOURCES."""
    enabled = SHADOW_V2_ENABLED_SOURCES if enabled_sources is None else enabled_sources
    return route_report(nominations, now=now, cap=cap, enabled_sources=enabled)


def _provenance_entry(
    nom: NominatedCandidate,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source": nom.source,
        "candidate_first_seen_ts": nom.candidate_first_seen_ts,
        "setup": nom.setup or nom.group,
        "group": nom.group or nom.setup,
        "source_action": nom.source_action,
        "source_reason": nom.source_reason,
        "candidate_reason": nom.candidate_reason,
        "status": nom.status,
        "eligible_from": nom.eligible_from,
    }
    if extra:
        reserved = set(entry)
        reserved.add("symbol")
        for key, value in extra.items():
            if key in reserved:
                continue
            entry[key] = value
    return entry


def _extras_by_key(
    extras: Sequence[Mapping[str, Any]] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in extras or ():
        sym = str(raw.get("symbol") or "").strip().upper()
        if not sym:
            continue
        src = str(raw.get("source") or SRC_MARKET_AWARE_SWEETSPOT).strip()
        out[(sym, src)] = dict(raw)
    return out


def _provenance_for(
    nom: BrainANomination,
    by_symbol: Mapping[str, SymbolProvenance],
    extras_by_key: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    extras = extras_by_key or {}
    hit = by_symbol.get(nom.symbol)
    if hit is not None and hit.nominations:
        return [
            _provenance_entry(n, extras.get((n.symbol, n.source)))
            for n in hit.nominations
        ]
    extra = extras.get((nom.symbol, nom.source))
    fallback = {
        "source": nom.source,
        "candidate_first_seen_ts": nom.candidate_first_seen_ts,
        "setup": nom.setup,
        "group": nom.group,
        "source_action": nom.source_action,
        "source_reason": nom.source_reason,
        "candidate_reason": nom.nomination_reason,
        "status": nom.status,
        "eligible_from": nom.eligible_from,
    }
    if extra:
        reserved = set(fallback)
        reserved.add("symbol")
        for key, value in extra.items():
            if key in reserved:
                continue
            fallback[key] = value
    return [fallback]


def sidecar_row_from_nomination(
    nom: BrainANomination,
    *,
    provenance: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = {
        "v2_camera": True,
        "symbol": nom.symbol,
        "session": nom.session,
        "candidate_first_seen_ts": nom.candidate_first_seen_ts,
        "candidate_updated_ts": nom.candidate_updated_ts,
        "eligible_from": nom.eligible_from,
        "source": nom.source,
        "nomination_source": nom.source,
        "status": nom.status,
        "setup": nom.setup,
        "group": nom.group,
        "observation_intent": nom.observation_intent,
        "observation_reference": nom.observation_reference,
        "price_at_first_seen": nom.price_at_first_seen,
        "ema9_at_first_seen": nom.ema9_at_first_seen,
        "breakout_ref_at_first_seen": nom.breakout_ref_at_first_seen,
        "source_action": nom.source_action,
        "source_reason": nom.source_reason,
        "nomination_reason": nom.nomination_reason,
        "candidate_reason": nom.nomination_reason,
        "elite_buy_grade": nom.elite_buy_grade,
        "market_real": nom.market_real,
        "market_permission": nom.market_permission,
        "provenance": list(provenance or []),
        "candidate_is_buy": False,
        "alert_eligible": False,
        "chronology_status": nom.chronology_status,
    }
    if not row["provenance"]:
        row["provenance"] = _provenance_for(nom, {})
    return row


def build_sidecar_rows(
    report: NominationReport,
) -> list[dict[str, Any]]:
    """Canonical V2 nominations as Camera sidecar rows. List provenance, not a score."""
    by_symbol: dict[str, SymbolProvenance] = {}
    if report.route_report is not None:
        by_symbol = {p.symbol: p for p in report.route_report.provenance}
    extras = _extras_by_key(report.brain_b_provenance)
    rows = [
        sidecar_row_from_nomination(
            nom,
            provenance=_provenance_for(nom, by_symbol, extras),
        )
        for nom in report.nominations
    ]
    rows.sort(key=lambda r: (str(r.get("symbol") or ""), str(r.get("candidate_first_seen_ts") or "")))
    return rows


def freeze_record_from_mapping(raw: Mapping[str, Any]) -> FreezeRecord | None:
    session = str(raw.get("session") or "").strip()
    symbol = str(raw.get("symbol") or "").strip().upper()
    first = str(raw.get("candidate_first_seen_ts") or "").strip()
    if not session or not symbol or not has_legal_first_seen(first):
        return None
    return FreezeRecord(
        session=session,
        symbol=symbol,
        candidate_first_seen_ts=first,
        price_at_first_seen=_freeze_num(raw.get("price_at_first_seen")),
        ema9_at_first_seen=_freeze_num(raw.get("ema9_at_first_seen")),
        breakout_ref_at_first_seen=_freeze_num(raw.get("breakout_ref_at_first_seen")),
    )


def _freeze_num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def freeze_records_from_document(doc: Mapping[str, Any]) -> tuple[FreezeRecord, ...]:
    """Recover prior_freeze from a loaded sidecar. Rows backfill if ledger absent."""
    out: dict[tuple[str, str], FreezeRecord] = {}
    ledger = doc.get("freeze_ledger")
    if ledger is not None:
        if not isinstance(ledger, list):
            raise SidecarShadowError("sidecar freeze_ledger is not a list")
        for raw in ledger:
            if not isinstance(raw, Mapping):
                raise SidecarShadowError("sidecar freeze_ledger entry is not an object")
            rec = freeze_record_from_mapping(raw)
            if rec is None:
                continue
            out[(rec.session, rec.symbol)] = rec
    rows = doc.get("rows")
    if isinstance(rows, list):
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            rec = freeze_record_from_mapping(raw)
            if rec is None:
                continue
            out.setdefault((rec.session, rec.symbol), rec)
    return tuple(sorted(out.values(), key=lambda r: (r.session, r.symbol)))


def freeze_ledger_as_dicts(records: Iterable[FreezeRecord] | None) -> list[dict[str, Any]]:
    rows = [
        {
            "session": rec.session,
            "symbol": rec.symbol,
            "candidate_first_seen_ts": rec.candidate_first_seen_ts,
            "price_at_first_seen": rec.price_at_first_seen,
            "ema9_at_first_seen": rec.ema9_at_first_seen,
            "breakout_ref_at_first_seen": rec.breakout_ref_at_first_seen,
        }
        for rec in records or ()
    ]
    rows.sort(key=lambda r: (str(r.get("session") or ""), str(r.get("symbol") or "")))
    return rows


def load_sidecar_document(path: Path) -> dict[str, Any] | None:
    """Return parsed sidecar, None if missing. Corrupt/unreadable raises SidecarShadowError."""
    src = Path(path)
    if not src.exists():
        return None
    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise SidecarShadowError(f"unreadable sidecar: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SidecarShadowError(f"corrupted sidecar JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SidecarShadowError("sidecar is not a JSON object")
    if "rows" not in data or not isinstance(data.get("rows"), list):
        raise SidecarShadowError("sidecar missing rows list")
    return data


def atomic_write_text(path: Path, text: str) -> None:
    """Same-directory temp + flush/fsync + os.replace."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _with_brain_b_meta(
    report: NominationReport,
    brain_b: BrainBConsult | None,
) -> NominationReport:
    if brain_b is None:
        return report
    return NominationReport(
        nominations=report.nominations,
        rejected=report.rejected,
        freeze_ledger=report.freeze_ledger,
        route_report=report.route_report,
        observed_at=report.observed_at,
        market_real=report.market_real,
        market_permission=report.market_permission,
        brain_b_status=brain_b.status,
        brain_b_predecessor=brain_b.predecessor,
        brain_b_reason=brain_b.reason,
        brain_b_provenance=brain_b.provenance,
    )


def build_sidecar_from_scan(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    market_real: object,
    observed_at: datetime,
    prior_freeze: Iterable | None = None,
    early_lab_symbols: Iterable[str] | None = None,
    brain_b: BrainBConsult | None = None,
) -> tuple[NominationReport, list[dict[str, Any]]]:
    """Nominate Brain A, optionally union Sweet Brain B, then shadow-route.

    Default ``brain_b=None`` does not consult Sweet (existing Brain-A-only tests).
    Production Cloud hook always passes a consult. Zero B never blocks A.
    Uses ``shadow_route_v2``. Production ``ENABLED_SOURCES`` unused.
    Sweet is never written to freeze_ledger (Brain A clocks/refs stay Brain A).
    """
    report = nominate_scan_rows(
        rows,
        market_real=market_real,
        observed_at=observed_at,
        prior_freeze=prior_freeze,
        early_lab_symbols=early_lab_symbols,
        route=False,
    )
    now = as_vn(observed_at)
    b_noms = list(brain_b.nominations) if brain_b is not None else []
    all_noms = list(report.nominations) + b_noms
    if not all_noms:
        report = _with_brain_b_meta(report, brain_b)
        return report, build_sidecar_rows(report)

    routed_noms = [to_nominated_candidate(n) for n in all_noms]
    routed = shadow_route_v2(routed_noms, now=now)
    # Canonical V2 row uses SOURCE_PRIORITY over the full union, including
    # not-yet-eligible nominations the eligible router drops. Camera must wait.
    full_prov = tuple(dedup_with_provenance(routed_noms))
    by_key = {(n.symbol, n.source): n for n in all_noms}
    merged: list = []
    for item in full_prov:
        original = by_key[(item.canonical.symbol, item.canonical.source)]
        merged.append(from_nominated_candidate(item.canonical, original))
    merged.sort(key=lambda n: (n.symbol, n.candidate_first_seen_ts))
    combined = RouteReport(
        watchlist=to_watchlist_frame([to_nominated_candidate(n) for n in merged]),
        canonical=tuple(to_nominated_candidate(n) for n in merged),
        provenance=full_prov,
        rejected=routed.rejected,
    )
    report = NominationReport(
        nominations=tuple(merged),
        rejected=report.rejected,
        freeze_ledger=report.freeze_ledger,
        route_report=combined,
        observed_at=report.observed_at,
        market_real=report.market_real,
        market_permission=report.market_permission,
        brain_b_status=brain_b.status if brain_b is not None else "",
        brain_b_predecessor=brain_b.predecessor if brain_b is not None else "",
        brain_b_reason=brain_b.reason if brain_b is not None else "",
        brain_b_provenance=brain_b.provenance if brain_b is not None else (),
    )
    return report, build_sidecar_rows(report)


def build_sidecar_document(
    rows: Sequence[Mapping[str, Any]],
    *,
    observed_at: datetime,
    market_real: object = None,
    market_permission: str = "",
    freeze_ledger: Iterable[FreezeRecord] | None = None,
    generated_at: datetime | None = None,
    session: str | None = None,
    brain_b: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    now = as_vn(observed_at)
    generated = as_vn(generated_at) if generated_at is not None else now
    doc: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "slice": SLICE,
        "mode": MODE,
        "candidate_is_buy": False,
        "alert_eligible": False,
        "router_wired_to_production": False,
        "production_enabled_sources": sorted(ENABLED_SOURCES),
        "shadow_enabled_sources": sorted(SHADOW_V2_ENABLED_SOURCES),
        "watchlist_columns_untouched": list(WATCHLIST_COLUMNS),
        "session": session or now.date().isoformat(),
        "observed_at": now.isoformat(),
        "generated_at": generated.isoformat(),
        "market_real": market_real,
        "market_permission": market_permission,
        "notes": [
            "Candidate != BUY.",
            "Sidecar for Camera observation, not data/live_candidate/dynamic_watchlist.json.",
            "Brain B Sweet is observation-only. OR not AND. Zero B never blocks A.",
            "No GitHub publish in Slice 3A. Local freeze_ledger only.",
            "Frozen refs stay scan units; close_vs_ref is integer VND via normalize_price_to_integer_vnd.",
            "Sweet-only has no EMA9/breakout Camera timing reference.",
        ],
        "freeze_ledger": freeze_ledger_as_dicts(freeze_ledger),
        "rows": [dict(r) for r in rows],
    }
    if brain_b is not None:
        doc["brain_b"] = dict(brain_b)
    return doc


def encode_sidecar_text(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def write_sidecar(
    rows: Sequence[Mapping[str, Any]],
    *,
    observed_at: datetime,
    path: Path | None = None,
    market_real: object = None,
    market_permission: str = "",
    freeze_ledger: Iterable[FreezeRecord] | None = None,
    generated_at: datetime | None = None,
    session: str | None = None,
    brain_b: Mapping[str, Any] | None = None,
) -> Path:
    out = Path(path) if path is not None else DEFAULT_SIDECAR_PATH
    assert_not_production_watchlist(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = build_sidecar_document(
        rows,
        observed_at=observed_at,
        market_real=market_real,
        market_permission=market_permission,
        freeze_ledger=freeze_ledger,
        generated_at=generated_at,
        session=session,
        brain_b=brain_b,
    )
    atomic_write_text(out, encode_sidecar_text(doc))
    return out


def production_watchlist_frame_from_noms(noms: Iterable[NominatedCandidate]):
    """Proof helper: 8-column frame still drops V2 extras."""
    return to_watchlist_frame(noms)
