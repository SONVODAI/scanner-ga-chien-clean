"""Stage B1 price book + verified session calendar + T+3/5/10 outcomes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from research.v2_research_ledger.contract import (
    ADJUSTMENT_EXPLICIT_UNADJUSTED,
    NOMINATION_ACCEPTED,
    NOMINATION_REJECTED,
    SOURCE_BRAIN_A,
    STATE_WAIT,
    STATUS_MISSING,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    STATUS_VALID,
    T0_MISSING,
    T0_PRESENT,
)
from research.v2_research_ledger.ingest import ingest_brain_a_shadow, ingest_v2_action_state
from research.v2_research_ledger.ledger import ResearchLedger
from research.v2_research_ledger.outcomes_engine import mature_forward_outcomes
from research.v2_research_ledger.price_book import (
    PriceBook,
    load_price_book_from_daily_rows,
    load_price_book_from_previous_close,
)
from research.v2_research_ledger.session_calendar import (
    SessionCalendarError,
    VerifiedSessionCalendar,
    build_verified_session_calendar,
    load_verified_session_calendar,
)


# ---------------------------------------------------------------------------
# Explicitly labeled SYNTHETIC verified sessions (test fixtures only).
# Not a production VN holiday calendar. Holidays are omitted from the index.
# ---------------------------------------------------------------------------
# T0 = 2026-08-14 (Fri)
# SYNTHETIC_HOLIDAY_STANDIN = 2026-08-19 (Wed) — omitted from sessions
# Sessions after T0:
#   T+1 2026-08-17 Mon
#   T+2 2026-08-18 Tue
#   T+3 2026-08-20 Thu   (skips synthetic holiday 08-19)
#   T+4 2026-08-21 Fri
#   T+5 2026-08-24 Mon
#   T+6 2026-08-25 Tue
#   T+7 2026-08-26 Wed
#   T+8 2026-08-27 Thu
#   T+9 2026-08-28 Fri
#   T+10 2026-08-31 Mon
SYNTHETIC_VERIFIED_SESSIONS = (
    "2026-08-14",  # T0
    "2026-08-17",
    "2026-08-18",
    # 2026-08-19 deliberately absent — labeled SYNTHETIC_HOLIDAY_STANDIN
    "2026-08-20",
    "2026-08-21",
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
    "2026-08-27",
    "2026-08-28",
    "2026-08-31",
)

SYNTHETIC_CALENDAR_SOURCE = "test_fixture_synthetic_vn_sessions"
SYNTHETIC_CALENDAR_PROVENANCE = (
    "explicitly_labeled_synthetic_sessions_for_unit_tests;"
    "not_a_production_vn_exchange_calendar;"
    "holiday_standin=2026-08-19"
)


def _synthetic_calendar(
    *,
    through: str = "2026-08-31",
    sessions: tuple[str, ...] = SYNTHETIC_VERIFIED_SESSIONS,
) -> VerifiedSessionCalendar:
    return build_verified_session_calendar(
        sessions,
        source=SYNTHETIC_CALENDAR_SOURCE,
        provenance=SYNTHETIC_CALENDAR_PROVENANCE,
        verified_through=through,
    )


def _accepted_nom(**overrides):
    base = {
        "source": SOURCE_BRAIN_A,
        "provenance_session": "2026-08-14",
        "symbol": "HPG",
        "setup": "PULL ĐẸP",
        "disposition": NOMINATION_ACCEPTED,
        "t0_status": T0_PRESENT,
        "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
        "eligible_from": "2026-08-14T10:05:00+07:00",
        "price_at_first_seen": 100.0,
        "ema9_at_first_seen": 99.0,
        "breakout_ref_at_first_seen": 101.0,
        "market_real_at_nomination": 7.0,
        "market_context_source": "test",
        "published_observed_at": "2026-08-14T10:05:00+07:00",
        "price_source": "brain_a_freeze",
        "adjustment_status": "UNAVAILABLE",
        "is_live_adjusted": False,
    }
    base.update(overrides)
    return base


def _book_for_hpg() -> PriceBook:
    """Closes on synthetic verified T+3 / T+5 / T+10 sessions after holiday gap."""
    book = PriceBook()
    closes = {
        "2026-08-20": 103.0,  # T+3 (after SYNTHETIC_HOLIDAY_STANDIN)
        "2026-08-24": 105.0,  # T+5
        "2026-08-31": 110.0,  # T+10
    }
    for day, close in closes.items():
        book.put(
            symbol="HPG",
            session=day,
            close=close,
            price_source="vnstock_d1_bar_before_session",
        )
    return book


def test_synthetic_calendar_skips_labeled_holiday_and_requires_coverage():
    cal = _synthetic_calendar()
    assert cal.offset(date(2026, 8, 14), 3) == date(2026, 8, 20)
    assert cal.offset(date(2026, 8, 14), 5) == date(2026, 8, 24)
    assert cal.offset(date(2026, 8, 14), 10) == date(2026, 8, 31)
    assert not cal.contains("2026-08-19")  # SYNTHETIC_HOLIDAY_STANDIN
    # Truncated verified_through: T+10 session listed but not verified → None
    short = _synthetic_calendar(through="2026-08-24")
    assert short.offset(date(2026, 8, 14), 5) == date(2026, 8, 24)
    assert short.offset(date(2026, 8, 14), 10) is None


def test_calendar_loader_refuses_unverified_document(tmp_path: Path):
    path = tmp_path / "cal.json"
    path.write_text(
        json.dumps(
            {
                "schema": "v2_research_session_calendar.v1",
                "verified": False,
                "source": "x",
                "provenance": "y",
                "sessions": ["2026-08-14"],
                "verified_through": "2026-08-14",
            }
        ),
        encoding="utf-8",
    )
    try:
        load_verified_session_calendar(path)
        assert False, "expected SessionCalendarError"
    except SessionCalendarError as exc:
        assert "verified=true" in str(exc)


def test_price_book_loads_previous_close_archive(tmp_path: Path):
    path = tmp_path / "previous_close.jsonl"
    rows = [
        {
            "symbol": "hpg",
            "session_date": "2026-08-20",
            "previous_close": 103000,
            "previous_close_date": "2026-08-19",
            "source": "vnstock_d1_bar_before_session",
            "price_unit": "integer_vnd",
            "status": "ok",
        },
        {
            "symbol": "HPG",
            "session_date": "2026-08-22",
            "previous_close": 105000,
            "previous_close_date": "2026-08-21",
            "source": "vnstock_d1_bar_before_session",
            "status": "stale",
        },
        {
            "symbol": "HPG",
            "session_date": "2026-08-18",
            "previous_close": None,
            "previous_close_date": None,
            "status": "missing",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    book = load_price_book_from_previous_close(path)
    assert book.get("HPG", "2026-08-19")["price"] == 103000
    assert book.get("HPG", "2026-08-21")["price"] == 105000
    assert book.get("HPG", "2026-08-18") is None


def test_price_book_rejects_live_adjusted_rows():
    book = load_price_book_from_daily_rows(
        [
            {
                "symbol": "HPG",
                "date": "2026-08-20",
                "close": 103.0,
                "adjustment_status": ADJUSTMENT_EXPLICIT_UNADJUSTED,
                "is_live_adjusted": False,
                "price_source": "test",
            },
            {
                "symbol": "HPG",
                "date": "2026-08-24",
                "close": 999.0,
                "adjustment_status": ADJUSTMENT_EXPLICIT_UNADJUSTED,
                "is_live_adjusted": True,
                "price_source": "test",
            },
        ]
    )
    assert book.get("HPG", "2026-08-20") is not None
    assert book.get("HPG", "2026-08-24") is None


def test_outcomes_blocked_without_verified_calendar():
    ledger = ResearchLedger()
    ledger.add_nomination(_accepted_nom())
    report = mature_forward_outcomes(
        ledger, _book_for_hpg(), as_of=date(2026, 8, 31)
    )
    assert report.calendar_blocked is True
    assert report.outcomes_written == 0
    assert ledger.outcomes == []
    assert any("no verified VN session calendar" in n for n in report.notes)


def test_mature_outcomes_uses_synthetic_sessions_not_weekdays():
    ledger = ResearchLedger()
    assert ledger.add_nomination(_accepted_nom()) is not None
    t0_price = 100.0
    report = mature_forward_outcomes(
        ledger,
        _book_for_hpg(),
        as_of=date(2026, 8, 31),
        calendar=_synthetic_calendar(),
    )
    assert report.matured_valid == 3
    by_h = {r["horizon"]: r for r in ledger.outcomes}
    # T+3 is 2026-08-20 (holiday stand-in 08-19 skipped), NOT weekday 08-19.
    assert by_h["T+3"]["status"] == STATUS_VALID
    assert by_h["T+3"]["target_session"] == "2026-08-20"
    assert by_h["T+5"]["target_session"] == "2026-08-24"
    assert by_h["T+10"]["target_session"] == "2026-08-31"
    assert by_h["T+3"]["price"] == 103.0
    assert abs(by_h["T+3"]["return_value"] - ((103.0 / t0_price) - 1.0)) < 1e-12
    assert abs(by_h["T+3"]["return_pct"] - 3.0) < 1e-9
    assert abs(by_h["T+5"]["return_pct"] - 5.0) < 1e-9
    assert abs(by_h["T+10"]["return_pct"] - 10.0) < 1e-9
    nom = ledger.nominations[0]
    assert nom["price_at_first_seen"] == 100.0
    assert nom["candidate_first_seen_ts"] == "2026-08-14T10:05:00+07:00"
    assert nom["source"] == SOURCE_BRAIN_A
    assert by_h["T+3"]["nomination_disposition"] == NOMINATION_ACCEPTED
    assert by_h["T+3"]["t0_status"] == T0_PRESENT


def test_no_lookahead_pending_then_matures_idempotently():
    ledger = ResearchLedger()
    ledger.add_nomination(_accepted_nom())
    book = _book_for_hpg()
    cal = _synthetic_calendar()
    early = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 15), calendar=cal
    )
    assert early.pending == 3
    assert all(r["status"] == STATUS_PENDING for r in ledger.outcomes)
    assert all(r["return_value"] is None for r in ledger.outcomes)

    mid = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 20), calendar=cal
    )
    by_h = {r["horizon"]: r for r in ledger.outcomes}
    assert by_h["T+3"]["status"] == STATUS_VALID
    assert by_h["T+5"]["status"] == STATUS_PENDING
    assert by_h["T+10"]["status"] == STATUS_PENDING
    assert mid.matured_valid == 1

    again = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 20), calendar=cal
    )
    assert again.matured_valid == 0
    assert len(ledger.outcomes) == 3
    assert by_h["T+3"]["price"] == 103.0


def test_missing_symbol_price_on_verified_session_is_missing_not_holiday():
    """Verified session day with no book row → MISSING (never treated as holiday)."""
    ledger = ResearchLedger()
    ledger.add_nomination(_accepted_nom())
    book = PriceBook()
    # T+3 session present in calendar but price absent for this symbol.
    book.put(symbol="HPG", session="2026-08-24", close=105.0, price_source="vnstock_d1")
    book.put(symbol="HPG", session="2026-08-31", close=110.0, price_source="vnstock_d1")
    report = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 31), calendar=_synthetic_calendar()
    )
    by_h = {r["horizon"]: r for r in ledger.outcomes}
    assert by_h["T+3"]["target_session"] == "2026-08-20"
    assert by_h["T+3"]["status"] == STATUS_MISSING
    assert by_h["T+3"]["price"] is None
    assert by_h["T+3"]["return_value"] is None
    assert by_h["T+5"]["status"] == STATUS_VALID
    assert by_h["T+10"]["status"] == STATUS_VALID
    assert report.missing == 1
    assert report.matured_valid == 2


def test_uncovered_horizon_stays_pending_until_calendar_extends():
    ledger = ResearchLedger()
    ledger.add_nomination(_accepted_nom())
    book = _book_for_hpg()
    # Verified only through T+5; T+10 listed but not verified_through.
    short = build_verified_session_calendar(
        SYNTHETIC_VERIFIED_SESSIONS[:6],  # through 2026-08-24
        source=SYNTHETIC_CALENDAR_SOURCE,
        provenance=SYNTHETIC_CALENDAR_PROVENANCE + ";coverage=through_t5_only",
        verified_through="2026-08-24",
    )
    report = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 31), calendar=short
    )
    by_h = {r["horizon"]: r for r in ledger.outcomes}
    assert by_h["T+3"]["status"] == STATUS_VALID
    assert by_h["T+5"]["status"] == STATUS_VALID
    assert by_h["T+10"]["status"] == STATUS_PENDING
    assert by_h["T+10"]["calendar_status"] == "COVERAGE_PENDING"
    assert by_h["T+10"]["target_session"].startswith("UNCOVERED|")
    assert report.pending == 1
    assert report.matured_valid == 2

    # Extend calendar; T+10 matures. Finalized T+3/T+5 untouched.
    full = _synthetic_calendar()
    later = mature_forward_outcomes(
        ledger, book, as_of=date(2026, 8, 31), calendar=full
    )
    by_h = {r["horizon"]: r for r in ledger.outcomes}
    assert by_h["T+3"]["status"] == STATUS_VALID
    assert by_h["T+3"]["price"] == 103.0
    assert by_h["T+5"]["price"] == 105.0
    assert by_h["T+10"]["status"] == STATUS_VALID
    assert by_h["T+10"]["target_session"] == "2026-08-31"
    assert later.matured_valid == 1
    # Immutable T0 preserved.
    assert ledger.nominations[0]["price_at_first_seen"] == 100.0


def test_t0_missing_rejected_writes_unavailable_never_return():
    ledger = ResearchLedger()
    shadow = {
        "source": SOURCE_BRAIN_A,
        "observed_at": "2026-08-14T10:05:00+07:00",
        "market_real": 7.0,
        "nominations": [],
        "rejected": [{"symbol": "AAA", "setup": "X", "reason": "SETUP_EXCLUDED"}],
        "freeze_ledger": [],
    }
    ingest_brain_a_shadow(ledger, shadow)
    rejected = ledger.nominations[0]
    assert rejected["t0_status"] == T0_MISSING
    report = mature_forward_outcomes(
        ledger,
        PriceBook(),
        as_of=date(2026, 8, 31),
        include_rejected=True,
        calendar=_synthetic_calendar(),
    )
    assert report.unavailable == 3
    assert all(r["status"] == STATUS_UNAVAILABLE for r in ledger.outcomes)
    assert all(r["return_value"] is None for r in ledger.outcomes)
    assert all(r["nomination_disposition"] == NOMINATION_REJECTED for r in ledger.outcomes)
    again = mature_forward_outcomes(
        ledger,
        PriceBook(),
        as_of=date(2026, 8, 31),
        include_rejected=True,
        calendar=_synthetic_calendar(),
    )
    assert again.outcomes_written == 0
    assert len(ledger.outcomes) == 3


def test_wait_action_state_tagged_distinct_from_disposition():
    ledger = ResearchLedger()
    ledger.add_nomination(_accepted_nom())
    ingest_v2_action_state(
        ledger,
        {
            "session": "2026-08-14",
            "observed_at": "2026-08-14T10:20:00+07:00",
            "rows": [
                {
                    "symbol": "HPG",
                    "session": "2026-08-14",
                    "observation_session": "2026-08-14",
                    "shadow_action": STATE_WAIT,
                    "action_reason": "WAITING",
                    "last_legal_bar_ts": "2026-08-14T10:15:00+07:00",
                    "route": "PULL ĐẸP",
                    "setup": "PULL ĐẸP",
                    "candidate_is_buy": False,
                    "pxv_implies_buy": False,
                    "alert_eligible": False,
                }
            ],
        },
        source_stream="post_close",
    )
    report = mature_forward_outcomes(
        ledger,
        _book_for_hpg(),
        as_of=date(2026, 8, 31),
        calendar=_synthetic_calendar(),
    )
    assert report.wait_tagged == 1
    assert report.matured_valid == 3
    for row in ledger.outcomes:
        assert row["nomination_disposition"] == NOMINATION_ACCEPTED
        assert row["action_state"] == STATE_WAIT
        assert row["nomination_disposition"] != row["action_state"]


def test_outcomes_engine_and_calendar_stay_isolated_from_production():
    root = Path(__file__).resolve().parents[1] / "research" / "v2_research_ledger"
    for name in ("price_book.py", "outcomes_engine.py", "session_calendar.py"):
        text = (root / name).read_text(encoding="utf-8")
        for forbidden in (
            "modules.live_candidate_v2",
            "modules.live_camera_shadow",
            "modules.position_guardian",
            "modules.market_aware_sweetspot_observer",
            "publish_serving",
            "export_once",
            "add_weekdays",
        ):
            assert forbidden not in text, f"{name} must not reference {forbidden}"
