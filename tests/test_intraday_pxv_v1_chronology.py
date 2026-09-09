"""Chronology gate + LIVE Candidate time contract. No threshold/debounce retune."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.candidates import CandidateEvent, load_candidate_events
from modules.intraday_pxv_v1.chronology import chronology_clean_ledger
from modules.intraday_pxv_v1.constants import (
    OVERLAY_TRUTH_CANONICAL,
    OVERLAY_TRUTH_RETROSPECTIVE,
    PROVENANCE_FIRST_SEEN,
    PROVENANCE_MISSING,
    PROVENANCE_SAVE_CLOCK,
)
from modules.intraday_pxv_v1.interpret import interpret_asof, interpret_candidate_session
from modules.intraday_pxv_v1.time_contract import (
    cash_session_end,
    resolve_legal_existence,
)


def _ts(day: str, hm: str) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN_TZ)


def _bar(symbol, ts, o=20000, h=20100, l=19900, c=20050, v=1000):
    return {
        "symbol": symbol,
        "timestamp": ts,
        "session_date": ts.date(),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "source": "test",
        "collected_at": ts,
        "quality_flag": "ok",
        "overlay_applied": False,
        "bar_source": "canonical",
    }


def _grid(day: str, symbol: str, n: int = 46) -> pd.DataFrame:
    t = _ts(day, "09:15")
    end = _ts(day, "14:45")
    rows = []
    i = 0
    while t <= end and i < n:
        hm = (t.hour, t.minute)
        if (9, 15) <= hm <= (11, 30) or (13, 0) <= hm <= (14, 45):
            rows.append(_bar(symbol, t, v=1000 + 10 * i))
            i += 1
        t += timedelta(minutes=5)
        if t.hour == 11 and t.minute > 30 and t.hour < 13:
            t = _ts(day, "13:00")
    return pd.DataFrame(rows)


def _cand(
    symbol="HPG",
    day="2026-08-14",
    *,
    candidate_ts=None,
    first_seen="",
    updated="",
) -> CandidateEvent:
    return CandidateEvent(
        symbol=symbol,
        session=date.fromisoformat(day),
        candidate_reason="MUA NHỎ / ƯU TIÊN",
        candidate_ts=f"{day} 15:05:00" if candidate_ts is None else candidate_ts,
        bot_context="PULL VỪA",
        candidate_first_seen_ts=first_seen,
        candidate_updated_ts=updated,
    )


def test_date_only_timestamp_is_not_legally_usable():
    c = _cand(candidate_ts="2026-08-14", first_seen="")
    legal = resolve_legal_existence(c)
    assert legal.provenance == PROVENANCE_MISSING
    assert legal.gate_ts is None
    assert legal.same_day_intraday_eligible is False
    assert interpret_candidate_session(_grid("2026-08-14", "HPG"), c, None, 5) == []


def test_missing_timestamp_emits_no_rows():
    c = _cand(candidate_ts="", first_seen="")
    legal = resolve_legal_existence(c)
    assert legal.provenance == PROVENANCE_MISSING
    assert interpret_candidate_session(_grid("2026-08-14", "HPG"), c, None, 5) == []


def test_after_close_save_clock_emits_no_same_day_intraday():
    c = _cand(candidate_ts="2026-08-14 15:05:00", first_seen="")
    legal = resolve_legal_existence(c)
    assert legal.provenance == PROVENANCE_SAVE_CLOCK
    assert legal.first_seen_ts is None
    assert legal.same_day_intraday_eligible is False
    assert legal.next_session_open_eligible is True
    assert legal.gate_ts == datetime.fromisoformat("2026-08-14 15:05:00").replace(tzinfo=VN_TZ)
    rows = interpret_candidate_session(_grid("2026-08-14", "HPG"), c, None, 5)
    assert rows == []


def test_empty_overlay_does_not_invent_midnight_row():
    c = _cand(first_seen="2026-08-14 10:00:00")
    assert interpret_candidate_session(pd.DataFrame(), c, None, 5) == []


def test_lunch_first_seen_drops_am_keeps_pm():
    day = "2026-08-28"
    c = _cand("GMD", day, candidate_ts=f"{day} 12:45:55", first_seen="")
    legal = resolve_legal_existence(c)
    assert legal.provenance == PROVENANCE_SAVE_CLOCK
    assert legal.same_day_intraday_eligible is True
    overlay = _grid(day, "GMD")
    rows = interpret_candidate_session(overlay, c, None, 5)
    assert rows
    asofs = [pd.Timestamp(r.asof) for r in rows]
    gate = datetime.fromisoformat(f"{day} 12:45:55").replace(tzinfo=VN_TZ)
    assert all(a >= pd.Timestamp(gate) for a in asofs)
    assert all(r.asof_hm >= "13:00" for r in rows)
    assert not any(r.asof_hm < "12:45" for r in rows)


def test_first_seen_wins_over_later_save_clock():
    day = "2026-08-14"
    c = _cand(
        candidate_ts=f"{day} 21:00:00",
        first_seen=f"{day} 10:30:00",
        updated=f"{day} 21:00:00",
    )
    legal = resolve_legal_existence(c)
    assert legal.provenance == PROVENANCE_FIRST_SEEN
    assert legal.first_seen_ts.strftime("%H:%M") == "10:30"
    assert legal.updated_ts.strftime("%H:%M") == "21:00"
    rows = interpret_candidate_session(_grid(day, "HPG"), c, None, 5)
    assert rows
    assert all(pd.Timestamp(r.asof) >= pd.Timestamp(legal.gate_ts) for r in rows)
    assert all(r.candidate_time_provenance == PROVENANCE_FIRST_SEEN for r in rows)
    assert min(r.asof_hm for r in rows) >= "10:30"


def test_asof_never_before_first_seen():
    day = "2026-08-14"
    c = _cand(first_seen=f"{day} 13:00:00", candidate_ts=f"{day} 13:00:00")
    rows = interpret_candidate_session(_grid(day, "HPG"), c, None, 5)
    assert rows
    assert min(r.asof_hm for r in rows) >= "13:00"
    assert all(r.asof_hm != "09:50" for r in rows)


def test_legal_bar_pxv_unchanged_vs_interpret_asof():
    """Chronology only drops illegal as-of inputs. Same legal bar → same RAW."""
    day = "2026-08-14"
    overlay = _grid(day, "HPG")
    c = _cand(first_seen=f"{day} 13:00:00", candidate_ts=f"{day} 13:00:00")
    rows = interpret_candidate_session(overlay, c, None, 5)
    target = next(r for r in rows if r.asof_hm == "13:15")
    asof = overlay[overlay["timestamp"].dt.strftime("%H:%M") == "13:15"].iloc[0]["timestamp"]
    direct = interpret_asof(
        overlay, asof=asof.to_pydatetime(), candidate=c, tod_store=None, tod_qualified_sessions=5
    )
    assert target.raw_evidence == direct.raw_evidence
    assert target.features == direct.features
    assert target.data_state == direct.data_state


def test_after_close_is_next_session_eligible_not_same_day():
    end = cash_session_end(date(2026, 8, 14))
    assert end.hour == 14 and end.minute == 45
    c = _cand(candidate_ts="2026-08-14 22:30:23")
    legal = resolve_legal_existence(c)
    assert legal.gate_ts > end
    assert legal.next_session_open_eligible is True
    assert legal.same_day_intraday_eligible is False


def test_loader_does_not_treat_time_as_first_seen(tmp_path: Path):
    p = tmp_path / "buy_elite_learning_history.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-08-14",
                "time": "15:05:00",
                "symbol": "HPG",
                "conclusion": "BUY ELITE",
                "group": "PULL VỪA",
            }
        ]
    ).to_csv(p, index=False)
    ev = load_candidate_events(p, sessions=[date(2026, 8, 14)])
    assert ev[0].candidate_ts == "2026-08-14 15:05:00"
    assert ev[0].candidate_first_seen_ts == ""
    legal = resolve_legal_existence(ev[0])
    assert legal.provenance == PROVENANCE_SAVE_CLOCK
    assert legal.first_seen_ts is None


def test_loader_reads_immutable_first_seen_column(tmp_path: Path):
    p = tmp_path / "buy_elite_learning_history.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-08-14",
                "time": "21:00:00",
                "symbol": "HPG",
                "conclusion": "BUY ELITE",
                "group": "PULL VỪA",
                "candidate_first_seen_ts": "2026-08-14 10:05:00",
                "candidate_updated_ts": "2026-08-14 21:00:00",
            }
        ]
    ).to_csv(p, index=False)
    ev = load_candidate_events(p, sessions=[date(2026, 8, 14)])
    assert ev[0].candidate_first_seen_ts.startswith("2026-08-14 10:05")
    legal = resolve_legal_existence(ev[0])
    assert legal.provenance == PROVENANCE_FIRST_SEEN
    assert legal.first_seen_ts.strftime("%H:%M") == "10:05"


def test_overlay_labeled_retrospective_not_live_asof():
    day = "2026-08-14"
    overlay = _grid(day, "HPG")
    overlay["overlay_applied"] = True
    overlay["bar_source"] = "revised_quarantine"
    c = _cand(first_seen=f"{day} 13:00:00", candidate_ts=f"{day} 13:00:00")
    rows = interpret_candidate_session(overlay, c, None, 5)
    assert rows
    assert all(r.overlay_truth_class == OVERLAY_TRUTH_RETROSPECTIVE for r in rows)


def test_canonical_overlay_truth_class():
    day = "2026-08-14"
    overlay = _grid(day, "HPG")
    c = _cand(first_seen=f"{day} 13:00:00", candidate_ts=f"{day} 13:00:00")
    rows = interpret_candidate_session(overlay, c, None, 5)
    assert all(r.overlay_truth_class == OVERLAY_TRUTH_CANONICAL for r in rows)


def test_chronology_clean_ledger_redebitounces_from_legal_start():
    day = "2026-08-28"
    t0 = _ts(day, "09:50")
    recs = []
    labels = ["STRENGTHEN", "STRENGTHEN", "NEUTRAL"] + ["NEUTRAL"] * 3
    times = [t0 + timedelta(minutes=5 * i) for i in range(len(labels))]
    # last three are PM
    times = [
        _ts(day, "09:50"),
        _ts(day, "09:55"),
        _ts(day, "10:00"),
        _ts(day, "13:00"),
        _ts(day, "13:05"),
        _ts(day, "13:10"),
    ]
    labels = ["STRENGTHEN", "STRENGTHEN", "NEUTRAL", "STRENGTHEN", "STRENGTHEN", "NEUTRAL"]
    for t, ev in zip(times, labels):
        recs.append(
            {
                "symbol": "GMD",
                "session": day,
                "asof": t.isoformat(),
                "asof_hm": t.strftime("%H:%M"),
                "candidate_ts": f"{day} 12:45:55",
                "candidate_first_seen_ts": "",
                "raw_evidence": ev,
                "evidence": ev,
                "published_evidence": ev,
                "alert_eligible": False,
                "data_state": "QUALIFIED",
                "tod_maturity": "TOD_PRELIMINARY",
                "overlay_applied": True,
                "features": {},
            }
        )
    df = pd.DataFrame(recs)
    clean, stats = chronology_clean_ledger(df)
    assert stats["rows_removed_illegal"] == 3
    assert stats["events_removed_after_close"] == 0
    assert list(clean["asof_hm"]) == ["13:00", "13:05", "13:10"]
    # re-debounce from legal start: first PM S unpublished, second publishes
    assert list(clean["published_evidence"]) == ["NEUTRAL", "STRENGTHEN", "NEUTRAL"]
    assert int(clean["alert_eligible"].sum()) == 0


def test_chronology_clean_drops_after_close_session_entirely():
    day = "2026-06-29"
    recs = []
    for hm, ev in (("09:50", "STRENGTHEN"), ("13:00", "STRENGTHEN"), ("14:45", "NEUTRAL")):
        t = _ts(day, hm)
        recs.append(
            {
                "symbol": "ACB",
                "session": day,
                "asof": t.isoformat(),
                "asof_hm": hm,
                "candidate_ts": f"{day} 22:30:23",
                "raw_evidence": ev,
                "evidence": ev,
                "published_evidence": ev,
                "alert_eligible": False,
                "data_state": "QUALIFIED",
                "tod_maturity": "TOD_PRELIMINARY",
                "overlay_applied": False,
                "features": {},
            }
        )
    clean, stats = chronology_clean_ledger(pd.DataFrame(recs))
    assert clean.empty
    assert stats["rows_removed_illegal"] == 3
    assert stats["events_removed_after_close"] == 1
    assert stats["events_next_session_open_eligible"] == 1
