"""Candidate Router: source gate, chronology checks, dedup, priority, cap.

Offline / shadow foundation. Does not publish, does not write Elite history,
does not manufacture timestamps.

Source priority picks a canonical nomination per symbol. Losing accepted
nominations remain on SymbolProvenance.nominations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

import pandas as pd

from modules.candidate_router.contract import (
    DEFAULT_SOURCE_PRIORITY,
    ENABLED_SOURCES,
    NominatedCandidate,
    REJECT_CHRONOLOGY_BACKWARD,
    REJECT_ILLEGAL_ELIGIBLE_FROM,
    REJECT_ILLEGAL_FIRST_SEEN,
    REJECT_MISSING_ELIGIBLE_FROM,
    REJECT_MISSING_FIRST_SEEN,
    REJECT_MISSING_SESSION,
    REJECT_MISSING_SYMBOL,
    REJECT_NOT_YET_ELIGIBLE,
    REJECT_SOURCE_NOT_ENABLED,
    RejectedNomination,
    SOURCE_PRIORITY,
    SymbolProvenance,
    WATCHLIST_COLUMNS,
    pass_through_meta,
)
from modules.candidate_router.elite import nominations_from_buy_elite_history
from modules.live_candidate.calendar import as_vn
from modules.live_candidate.contract import has_legal_first_seen


@dataclass
class RouteReport:
    """Internal routed result. `watchlist` stays the 8-column consumer snapshot."""

    watchlist: pd.DataFrame
    canonical: tuple[NominatedCandidate, ...]
    provenance: tuple[SymbolProvenance, ...]
    rejected: tuple[RejectedNomination, ...]


def _parse_ts(raw: object) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")
    return ts


def source_priority(source: str) -> int:
    return int(SOURCE_PRIORITY.get(str(source or ""), DEFAULT_SOURCE_PRIORITY))


def classify_nominations(
    nominations: Iterable[NominatedCandidate],
    *,
    now: datetime,
    enabled_sources: frozenset[str] | None = None,
) -> tuple[list[NominatedCandidate], list[RejectedNomination]]:
    """Reject illegal rows. Never fills clocks. Never invents group/setup."""
    enabled = ENABLED_SOURCES if enabled_sources is None else enabled_sources
    now_ts = pd.Timestamp(as_vn(now))
    accepted: list[NominatedCandidate] = []
    rejected: list[RejectedNomination] = []
    for raw in nominations or ():
        nom = replace(
            raw,
            symbol=str(raw.symbol or "").strip().upper(),
            source=str(raw.source or "").strip(),
            session=str(raw.session or "").strip(),
            candidate_first_seen_ts=str(raw.candidate_first_seen_ts or "").strip(),
            candidate_updated_ts=str(raw.candidate_updated_ts or "").strip(),
            eligible_from=str(raw.eligible_from or "").strip(),
            group=pass_through_meta(raw.group),
            setup=pass_through_meta(raw.setup),
            source_state=pass_through_meta(raw.source_state),
            source_action=pass_through_meta(raw.source_action),
            source_reason=pass_through_meta(raw.source_reason),
            candidate_reason=str(raw.candidate_reason or "").strip(),
        )
        if nom.source not in enabled:
            rejected.append(RejectedNomination(nom, REJECT_SOURCE_NOT_ENABLED))
            continue
        if not nom.symbol:
            rejected.append(RejectedNomination(nom, REJECT_MISSING_SYMBOL))
            continue
        if not nom.session:
            rejected.append(RejectedNomination(nom, REJECT_MISSING_SESSION))
            continue
        if not has_legal_first_seen(nom.candidate_first_seen_ts):
            rejected.append(RejectedNomination(nom, REJECT_MISSING_FIRST_SEEN))
            continue
        first = _parse_ts(nom.candidate_first_seen_ts)
        if first is None:
            rejected.append(RejectedNomination(nom, REJECT_ILLEGAL_FIRST_SEEN))
            continue
        if not has_legal_first_seen(nom.eligible_from):
            rejected.append(RejectedNomination(nom, REJECT_MISSING_ELIGIBLE_FROM))
            continue
        elig = _parse_ts(nom.eligible_from)
        if elig is None:
            rejected.append(RejectedNomination(nom, REJECT_ILLEGAL_ELIGIBLE_FROM))
            continue
        if elig < first:
            rejected.append(RejectedNomination(nom, REJECT_CHRONOLOGY_BACKWARD))
            continue
        if now_ts < elig:
            rejected.append(RejectedNomination(nom, REJECT_NOT_YET_ELIGIBLE))
            continue
        accepted.append(nom)
    return accepted, rejected


def _first_seen_key(nom: NominatedCandidate) -> str:
    first = _parse_ts(nom.candidate_first_seen_ts)
    return "" if first is None else first.isoformat()


def _updated_key(nom: NominatedCandidate) -> str:
    ts = _parse_ts(nom.candidate_updated_ts)
    return "" if ts is None else ts.isoformat()


def _dedup_sort_key(nom: NominatedCandidate) -> tuple:
    """Ascending; last row per symbol is the canonical winner.

    Winner: highest source priority (lowest integer), then latest first_seen
    (chronology cannot move backward), then latest updated_ts, then stable ids.
    """
    return (
        nom.symbol,
        -source_priority(nom.source),
        _first_seen_key(nom),
        _updated_key(nom),
        nom.source,
        nom.eligible_from,
        nom.status,
        nom.group,
        nom.setup,
    )


def dedup_with_provenance(noms: Iterable[NominatedCandidate]) -> list[SymbolProvenance]:
    """Canonical winner per symbol; all accepted competitors stay inspectable."""
    by_symbol: dict[str, list[NominatedCandidate]] = {}
    for nom in noms:
        by_symbol.setdefault(nom.symbol, []).append(nom)
    out: list[SymbolProvenance] = []
    for symbol in sorted(by_symbol):
        competitors = sorted(by_symbol[symbol], key=_dedup_sort_key)
        winner = competitors[-1]
        rest = tuple(competitors[:-1])
        out.append(
            SymbolProvenance(
                symbol=symbol,
                canonical=winner,
                nominations=(winner,) + rest,
            )
        )
    return out


def dedup_nominations(noms: Iterable[NominatedCandidate]) -> list[NominatedCandidate]:
    return [item.canonical for item in dedup_with_provenance(noms)]


def apply_universe_cap(
    noms: Iterable[NominatedCandidate],
    *,
    cap: int | None,
) -> list[NominatedCandidate]:
    """Optional Camera-style trim. cap=None is the Candidate Router default."""
    rows = list(noms)
    if cap is None:
        return sorted(rows, key=lambda n: (n.symbol, n.candidate_first_seen_ts))
    ranked = sorted(rows, key=lambda n: (n.eligible_from, n.symbol))
    return ranked[: max(0, int(cap))]


def to_watchlist_frame(noms: Iterable[NominatedCandidate]) -> pd.DataFrame:
    """Production-compatible 8 columns. group/setup stay on NominatedCandidate only."""
    rows = [
        {
            "session": n.session,
            "symbol": n.symbol,
            "candidate_first_seen_ts": n.candidate_first_seen_ts,
            "candidate_updated_ts": n.candidate_updated_ts,
            "candidate_reason": n.candidate_reason,
            "source": n.source,
            "status": n.status,
            "eligible_from": n.eligible_from,
        }
        for n in noms
    ]
    if not rows:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    return pd.DataFrame(rows, columns=WATCHLIST_COLUMNS)


def route_report(
    nominations: Iterable[NominatedCandidate],
    *,
    now: datetime,
    cap: int | None = None,
    enabled_sources: frozenset[str] | None = None,
) -> RouteReport:
    """Route with inspectable provenance. Default cap=None (no discovery cap)."""
    accepted, rejected = classify_nominations(
        nominations,
        now=now,
        enabled_sources=enabled_sources,
    )
    provenance = tuple(dedup_with_provenance(accepted))
    winners = [item.canonical for item in provenance]
    canonical = tuple(apply_universe_cap(winners, cap=cap))
    return RouteReport(
        watchlist=to_watchlist_frame(canonical),
        canonical=canonical,
        provenance=provenance,
        rejected=tuple(rejected),
    )


def route_candidates(
    nominations: Iterable[NominatedCandidate],
    *,
    now: datetime,
    cap: int | None = None,
    enabled_sources: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Dedup / priority / optional cap. Output columns match the live Candidate watchlist."""
    return route_report(
        nominations,
        now=now,
        cap=cap,
        enabled_sources=enabled_sources,
    ).watchlist


def build_routed_report(
    history: pd.DataFrame | None,
    *,
    now: datetime,
    cap: int | None = None,
) -> RouteReport:
    """Slice 1 Elite-only report. Does not publish. Default cap=None."""
    noms = nominations_from_buy_elite_history(history, now=now)
    return route_report(noms, now=now, cap=cap)


def build_routed_watchlist(
    history: pd.DataFrame | None,
    *,
    now: datetime,
    cap: int | None = None,
) -> pd.DataFrame:
    """Slice 1 Elite-only routed watchlist. Does not publish.

    cap=None (default): same membership/order as the current Elite watchlist.
    Passing an integer is an optional later Camera poll trim, not discovery.
    """
    return build_routed_report(history, now=now, cap=cap).watchlist


__all__ = [
    "RouteReport",
    "apply_universe_cap",
    "build_routed_report",
    "build_routed_watchlist",
    "classify_nominations",
    "dedup_nominations",
    "dedup_with_provenance",
    "route_candidates",
    "route_report",
    "to_watchlist_frame",
]
