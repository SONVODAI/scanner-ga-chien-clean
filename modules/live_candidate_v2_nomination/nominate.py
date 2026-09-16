"""Brain A nominator: scan rows → SHADOW nominations.

Reuses Candidate Router chronology/provenance objects without production wiring.
Does not publish dynamic_watchlist.json. Does not enable Rotation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from modules.candidate_router.contract import NominatedCandidate
from modules.candidate_router.router import RouteReport, route_report
from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_nomination.contract import (
    SRC_BRAIN_A,
    STATUS_NOMINATED,
    BrainANomination,
    FreezeRecord,
    RejectedRow,
)
from modules.live_candidate_v2_nomination.freeze import (
    chronology_status_for,
    eligible_from_for,
    ledger_map,
    session_of,
    stamp_or_reuse,
)
from modules.live_candidate_v2_nomination.intent import observation_action_reason, observation_intent
from modules.live_candidate_v2_nomination.predicate import (
    as_number,
    elite_buy_grade_of,
    evaluate_nomination,
    market_permission,
    setup_of,
    symbol_of,
)


@dataclass(frozen=True)
class NominationReport:
    nominations: tuple[BrainANomination, ...]
    rejected: tuple[RejectedRow, ...]
    freeze_ledger: tuple[FreezeRecord, ...]
    route_report: RouteReport | None
    observed_at: str
    market_real: float | None
    market_permission: str


def _winprob(row: Mapping[str, Any]) -> float | None:
    return as_number(row.get("WinProb") if "WinProb" in row else row.get("winprob"))


def to_nominated_candidate(nom: BrainANomination) -> NominatedCandidate:
    """Router object for chronology/provenance. Extra Brain A fields stay on nom."""
    return NominatedCandidate(
        symbol=nom.symbol,
        source=nom.source,
        candidate_first_seen_ts=nom.candidate_first_seen_ts,
        candidate_updated_ts=nom.candidate_updated_ts,
        eligible_from=nom.eligible_from,
        session=nom.session,
        status=nom.status,
        candidate_reason=nom.nomination_reason,
        source_state=nom.elite_buy_grade or nom.status,
        source_action=nom.observation_action,
        source_reason=nom.observation_intent,
        group=nom.group,
        setup=nom.setup,
    )


def from_nominated_candidate(
    routed: NominatedCandidate,
    original: BrainANomination,
) -> BrainANomination:
    """Re-attach frozen refs after routing. first_seen/setup/intent must survive."""
    return BrainANomination(
        symbol=routed.symbol,
        session=routed.session,
        setup=routed.setup or routed.group or original.setup,
        group=routed.group or original.group,
        candidate_first_seen_ts=routed.candidate_first_seen_ts,
        candidate_updated_ts=routed.candidate_updated_ts,
        eligible_from=routed.eligible_from,
        chronology_status=original.chronology_status,
        price_at_first_seen=original.price_at_first_seen,
        ema9_at_first_seen=original.ema9_at_first_seen,
        breakout_ref_at_first_seen=original.breakout_ref_at_first_seen,
        nomination_reason=routed.candidate_reason or original.nomination_reason,
        observation_intent=routed.source_reason or original.observation_intent,
        observation_action=routed.source_action or original.observation_action,
        source=routed.source or original.source,
        elite_buy_grade=original.elite_buy_grade,
        market_real=original.market_real,
        market_permission=original.market_permission,
        in_early_lab=original.in_early_lab,
        status=routed.status or original.status,
        qualified_by=original.qualified_by,
    )


def nominate_scan_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    market_real: object,
    observed_at: datetime,
    prior_freeze: Iterable[FreezeRecord] | None = None,
    early_lab_symbols: Iterable[str] | None = None,
    route: bool = True,
) -> NominationReport:
    """Evaluate Brain A nomination. Shadow only. Candidate != BUY."""
    now = as_vn(observed_at)
    now_iso = now.isoformat()
    perm = market_permission(market_real)
    mr = as_number(market_real)
    prior = ledger_map(list(prior_freeze) if prior_freeze is not None else [])
    nominations: list[BrainANomination] = []
    rejected: list[RejectedRow] = []
    ledger = dict(prior)

    for raw in rows or ():
        row = dict(raw)
        symbol = symbol_of(row)
        setup = setup_of(row)
        decision = evaluate_nomination(
            row,
            market_real=market_real,
            early_lab_symbols=early_lab_symbols,
        )
        if not decision.eligible:
            rejected.append(
                RejectedRow(
                    symbol=symbol,
                    setup=setup,
                    reason=decision.reject_reason,
                    elite_buy_grade=decision.elite_buy_grade,
                    winprob=_winprob(row),
                    in_early_lab=decision.in_early_lab,
                )
            )
            continue

        session = session_of(row, now)
        freeze = stamp_or_reuse(
            row,
            symbol=symbol,
            session=session,
            observed_at=now,
            prior=ledger,
        )
        ledger[ (session, symbol) ] = freeze
        action, _reason = observation_action_reason(row)
        elig = eligible_from_for(session, freeze.candidate_first_seen_ts)
        nominations.append(
            BrainANomination(
                symbol=symbol,
                session=session,
                setup=decision.setup,
                group=decision.setup,
                candidate_first_seen_ts=freeze.candidate_first_seen_ts,
                candidate_updated_ts=now_iso,
                eligible_from=elig,
                chronology_status=chronology_status_for(elig, now),
                price_at_first_seen=freeze.price_at_first_seen,
                ema9_at_first_seen=freeze.ema9_at_first_seen,
                breakout_ref_at_first_seen=freeze.breakout_ref_at_first_seen,
                nomination_reason=decision.nomination_reason,
                observation_intent=observation_intent(row),
                observation_action=action,
                source=SRC_BRAIN_A,
                elite_buy_grade=elite_buy_grade_of(row),
                market_real=mr,
                market_permission=perm,
                in_early_lab=decision.in_early_lab,
                status=STATUS_NOMINATED,
                qualified_by=decision.qualified_by,
            )
        )

    nominations.sort(key=lambda n: (n.symbol, n.candidate_first_seen_ts))
    routed_report: RouteReport | None = None
    if route and nominations:
        routed_report = route_report(
            [to_nominated_candidate(n) for n in nominations],
            now=now,
            cap=None,
            enabled_sources=frozenset({SRC_BRAIN_A}),
        )
        by_sym = {n.symbol: n for n in nominations}
        merged: list[BrainANomination] = []
        for routed in routed_report.canonical:
            original = by_sym[routed.symbol]
            merged.append(from_nominated_candidate(routed, original))
        # Keep not-yet-eligible nominations the router dropped; they are still nominations.
        kept_syms = {n.symbol for n in merged}
        for nom in nominations:
            if nom.symbol not in kept_syms:
                merged.append(nom)
        merged.sort(key=lambda n: (n.symbol, n.candidate_first_seen_ts))
        nominations = merged

    freeze_ledger = tuple(sorted(ledger.values(), key=lambda r: (r.session, r.symbol)))
    return NominationReport(
        nominations=tuple(nominations),
        rejected=tuple(rejected),
        freeze_ledger=freeze_ledger,
        route_report=routed_report,
        observed_at=now_iso,
        market_real=mr,
        market_permission=perm,
    )


def nomination_as_dict(nom: BrainANomination) -> dict[str, Any]:
    return asdict(nom)
