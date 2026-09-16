"""Brain A nomination → V2 Camera sidecar rows.

Shadow Router chronology via enabled_sources override only.
Does not publish data/live_candidate/dynamic_watchlist.json.
Does not enable Brain B. Absence of Brain B never blocks Brain A.
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
from modules.candidate_router.router import RouteReport, route_report, to_watchlist_frame
from modules.live_candidate.calendar import as_vn
from modules.live_candidate.contract import has_legal_first_seen
from modules.live_candidate_v2_camera.contract import (
    DEFAULT_SIDECAR_RELPATH,
    MODE,
    PRODUCTION_WATCHLIST_RELPATH,
    SCHEMA_ID,
    SHADOW_V2_ENABLED_SOURCES,
    SLICE,
)
from modules.live_candidate_v2_nomination.artifact import assert_not_production_watchlist
from modules.live_candidate_v2_nomination.contract import BrainANomination, FreezeRecord
from modules.live_candidate_v2_nomination.nominate import (
    NominationReport,
    from_nominated_candidate,
    nominate_scan_rows,
    to_nominated_candidate,
)

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


def _provenance_entry(nom: NominatedCandidate) -> dict[str, Any]:
    return {
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


def _provenance_for(
    nom: BrainANomination,
    by_symbol: Mapping[str, SymbolProvenance],
) -> list[dict[str, Any]]:
    hit = by_symbol.get(nom.symbol)
    if hit is not None and hit.nominations:
        return [_provenance_entry(n) for n in hit.nominations]
    return [
        {
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
    ]


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
    """Canonical Brain A nominations as Camera sidecar rows. List provenance, not a score."""
    by_symbol: dict[str, SymbolProvenance] = {}
    if report.route_report is not None:
        by_symbol = {p.symbol: p for p in report.route_report.provenance}
    rows = [
        sidecar_row_from_nomination(
            nom,
            provenance=_provenance_for(nom, by_symbol),
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


def build_sidecar_from_scan(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    market_real: object,
    observed_at: datetime,
    prior_freeze: Iterable | None = None,
    early_lab_symbols: Iterable[str] | None = None,
) -> tuple[NominationReport, list[dict[str, Any]]]:
    """Nominate (Brain A) then shadow-route into sidecar. Brain B is not consulted.

    Uses ``shadow_route_v2`` (Brain A enabled_sources override). Production
    ``ENABLED_SOURCES`` and ``nominate_scan_rows(..., route=True)`` are unused.
    Router NOT_YET_ELIGIBLE drops stay on the sidecar as nominations — Camera
    must still see first_seen/eligible_from so it can wait.
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
    if not report.nominations:
        return report, build_sidecar_rows(report)
    routed = shadow_route_v2(
        [to_nominated_candidate(n) for n in report.nominations],
        now=now,
    )
    by_sym = {n.symbol: n for n in report.nominations}
    merged: list = []
    for canon in routed.canonical:
        merged.append(from_nominated_candidate(canon, by_sym[canon.symbol]))
    kept = {n.symbol for n in merged}
    for nom in report.nominations:
        if nom.symbol not in kept:
            merged.append(nom)
    merged.sort(key=lambda n: (n.symbol, n.candidate_first_seen_ts))
    report = NominationReport(
        nominations=tuple(merged),
        rejected=report.rejected,
        freeze_ledger=report.freeze_ledger,
        route_report=routed,
        observed_at=report.observed_at,
        market_real=report.market_real,
        market_permission=report.market_permission,
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
) -> dict[str, Any]:
    now = as_vn(observed_at)
    generated = as_vn(generated_at) if generated_at is not None else now
    return {
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
            "Brain B is not required. OR not AND.",
            "No GitHub publish in Slice 3A. Local freeze_ledger only.",
            "Frozen refs stay scan units; close_vs_ref is integer VND via normalize_price_to_integer_vnd.",
        ],
        "freeze_ledger": freeze_ledger_as_dicts(freeze_ledger),
        "rows": [dict(r) for r in rows],
    }


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
    )
    atomic_write_text(out, encode_sidecar_text(doc))
    return out


def production_watchlist_frame_from_noms(noms: Iterable[NominatedCandidate]):
    """Proof helper: 8-column frame still drops V2 extras."""
    return to_watchlist_frame(noms)
