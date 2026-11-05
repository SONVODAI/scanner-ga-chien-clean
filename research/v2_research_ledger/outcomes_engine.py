"""Stage B1 forward-outcome engine (T+3 / T+5 / T+10 trading sessions).

Requires an explicitly verified VN exchange-session calendar. Never uses
weekday arithmetic or missing symbol prices to infer holidays. Action
states stay distinct from nomination dispositions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Sequence

from research.v2_research_ledger.contract import (
    NOMINATION_REJECTED,
    RESEARCH_FORWARD_HORIZONS,
    STATE_WAIT,
    T0_MISSING,
)
from research.v2_research_ledger.ledger import ResearchLedger
from research.v2_research_ledger.price_book import PriceBook
from research.v2_research_ledger.session_calendar import VerifiedSessionCalendar


def _text(value: object) -> str:
    return str(value or "").strip()


def _t0_session(nomination: Mapping[str, Any]) -> date | None:
    raw = _text(nomination.get("provenance_session"))
    if len(raw) >= 10:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    first = _text(nomination.get("candidate_first_seen_ts"))
    if len(first) >= 10:
        try:
            return date.fromisoformat(first[:10])
        except ValueError:
            return None
    return None


def _latest_action_state(ledger: ResearchLedger, nomination: Mapping[str, Any]) -> str | None:
    """Pick the latest raw action state for this symbol/session, if any."""
    symbol = _text(nomination.get("symbol")).upper()
    session = _text(nomination.get("provenance_session"))
    nom_id = _text(nomination.get("nomination_id"))
    best: tuple[str, str] | None = None
    for raw in ledger.raw_events:
        if _text(raw.get("symbol")).upper() != symbol:
            continue
        prov = _text(raw.get("provenance_session") or raw.get("evaluation_session"))
        origin = _text(raw.get("origin_nomination_id"))
        if origin and nom_id and origin != nom_id:
            continue
        if prov and session and prov != session and not origin:
            continue
        state = _text(raw.get("action_state"))
        observed = _text(raw.get("observed_at") or raw.get("bar_ts"))
        if not state:
            continue
        if best is None or observed >= best[0]:
            best = (observed, state)
    return best[1] if best else None


def nomination_episode(
    nomination: Mapping[str, Any],
    *,
    action_state: str | None = None,
) -> dict[str, Any]:
    """Build a research episode subject from a nomination (not a BUY_READY run)."""
    nom_id = _text(nomination.get("nomination_id"))
    session = _text(nomination.get("provenance_session"))
    return {
        "episode_id": f"nomination|{nom_id}",
        "evaluation_session": session,
        "origin_nomination_id": nom_id,
        "symbol": _text(nomination.get("symbol")).upper(),
        "t0_status": _text(nomination.get("t0_status")) or T0_MISSING,
        "nomination_disposition": _text(nomination.get("disposition")),
        "action_state": action_state,
        "route": "NOMINATION",
        "entry_bar_ts": _text(nomination.get("candidate_first_seen_ts")) or session,
        "entry_close": nomination.get("price_at_first_seen"),
    }


def resolve_target_sessions(
    calendar: VerifiedSessionCalendar,
    origin: date,
    horizons: Sequence[int],
) -> dict[int, date | None]:
    """Map horizon → exchange session, or None when coverage is insufficient."""
    return {int(horizon): calendar.offset(origin, int(horizon)) for horizon in horizons}


def _tally(report: "OutcomeRunReport", written: Sequence[Mapping[str, Any]]) -> None:
    report.outcomes_written += len(written)
    for row in written:
        status = row.get("status")
        if status == "VALID":
            report.matured_valid += 1
        elif status == "PENDING":
            report.pending += 1
        elif status == "MISSING":
            report.missing += 1
        elif status == "BLOCKED":
            report.blocked += 1
        elif status == "UNAVAILABLE":
            report.unavailable += 1


@dataclass
class OutcomeRunReport:
    nominations_considered: int = 0
    outcomes_written: int = 0
    unavailable: int = 0
    matured_valid: int = 0
    pending: int = 0
    missing: int = 0
    blocked: int = 0
    duplicates_skipped: int = 0
    wait_tagged: int = 0
    calendar_blocked: bool = False
    notes: list[str] = field(default_factory=list)


def mature_forward_outcomes(
    ledger: ResearchLedger,
    price_book: PriceBook,
    *,
    as_of: date,
    calendar: VerifiedSessionCalendar | None = None,
    horizons: Sequence[int] = RESEARCH_FORWARD_HORIZONS,
    include_rejected: bool = True,
) -> OutcomeRunReport:
    """Mature T+3/T+5/T+10 outcomes using a verified exchange-session calendar.

    Fail closed when ``calendar`` is omitted. Never infers holidays from
    missing prices or weekday arithmetic. Terminal outcomes stay immutable;
    ``PENDING`` / uncovered rows may mature when a later verified calendar
    extends coverage or prices arrive.
    """
    report = OutcomeRunReport()
    wanted = tuple(int(h) for h in horizons)
    if calendar is None:
        report.calendar_blocked = True
        report.notes.append(
            "B1 outcomes blocked: no verified VN session calendar supplied"
        )
        return report
    if not isinstance(calendar, VerifiedSessionCalendar):
        report.calendar_blocked = True
        report.notes.append(
            "B1 outcomes blocked: calendar must be VerifiedSessionCalendar"
        )
        return report

    for nom in list(ledger.nominations):
        disposition = _text(nom.get("disposition"))
        if disposition == NOMINATION_REJECTED and not include_rejected:
            continue
        report.nominations_considered += 1
        action_state = _latest_action_state(ledger, nom)
        if action_state == STATE_WAIT:
            report.wait_tagged += 1
        episode = nomination_episode(nom, action_state=action_state)
        t0_day = _t0_session(nom)
        eligible = ledger.nomination_forward_eligible(nom)
        missing_t0 = (not eligible) or nom.get("t0_status") == T0_MISSING

        if t0_day is None or not calendar.contains(t0_day):
            # Cannot count T+n without a verified origin session.
            written = ledger.add_outcomes(
                episode if not missing_t0 else {**episode, "t0_status": T0_MISSING},
                as_of=as_of,
                prices={},
                horizons=wanted,
                allow_unavailable=bool(missing_t0),
                target_sessions={h: None for h in wanted},
            )
            _tally(report, written)
            if t0_day is not None:
                report.notes.append(
                    f"calendar missing origin session {t0_day.isoformat()} "
                    f"for {episode['symbol']}"
                )
            continue

        targets = resolve_target_sessions(calendar, t0_day, wanted)

        if missing_t0:
            written = ledger.add_outcomes(
                {**episode, "t0_status": T0_MISSING},
                as_of=as_of,
                prices={},
                horizons=wanted,
                allow_unavailable=True,
                target_sessions=targets,
            )
            _tally(report, written)
            continue

        t0_price = nom.get("price_at_first_seen")
        if t0_price is None:
            written = ledger.add_outcomes(
                {**episode, "t0_status": T0_MISSING},
                as_of=as_of,
                prices={},
                horizons=wanted,
                allow_unavailable=True,
                target_sessions=targets,
            )
            _tally(report, written)
            continue

        known_targets = [day for day in targets.values() if day is not None]
        prices = price_book.observation_map(episode["symbol"], known_targets)
        before_ids = set(ledger._outcome_ids)
        written = ledger.add_outcomes(
            episode,
            as_of=as_of,
            prices=prices,
            horizons=wanted,
            t0_price=float(t0_price),
            allow_unavailable=False,
            target_sessions=targets,
        )
        _tally(report, written)
        if not written:
            expected_ids = {f"{episode['episode_id']}|T+{h}" for h in wanted}
            report.duplicates_skipped += len(expected_ids & before_ids)
    return report
