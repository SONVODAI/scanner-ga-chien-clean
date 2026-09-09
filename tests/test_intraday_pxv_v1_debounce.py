"""Slice 1C published-evidence debounce — no Camera writes, no T+n."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.debounce import publish_sequence
from modules.intraday_pxv_v1.examine import apply_debounce_columns, compare_raw_published, examine, load_ledger
from modules.intraday_pxv_v1.interpret import interpret_candidate_session


def test_one_raw_strengthen_stays_unpublished():
    assert publish_sequence(["STRENGTHEN", "NEUTRAL"]) == ["NEUTRAL", "NEUTRAL"]


def test_two_raw_strengthen_publishes_on_second_bar():
    assert publish_sequence(["STRENGTHEN", "STRENGTHEN"]) == ["NEUTRAL", "STRENGTHEN"]


def test_single_raw_neutral_fades_published():
    seq = publish_sequence(["STRENGTHEN", "STRENGTHEN", "NEUTRAL"])
    assert seq == ["NEUTRAL", "STRENGTHEN", "NEUTRAL"]


def test_reverse_requires_two_consecutive_opposite():
    seq = publish_sequence(
        ["STRENGTHEN", "STRENGTHEN", "WEAKEN", "WEAKEN"]
    )
    assert seq == ["NEUTRAL", "STRENGTHEN", "STRENGTHEN", "WEAKEN"]


def test_single_opposite_does_not_reverse_or_fade():
    # rule 5 is NEUTRAL only; one RAW WEAKEN while published S stays S
    seq = publish_sequence(["STRENGTHEN", "STRENGTHEN", "WEAKEN", "STRENGTHEN"])
    assert seq[2] == "STRENGTHEN"
    assert seq[3] == "STRENGTHEN"


def test_unusable_is_authoritative():
    seq = publish_sequence(["STRENGTHEN", "STRENGTHEN", "UNUSABLE", "STRENGTHEN", "STRENGTHEN"])
    assert seq[2] == "UNUSABLE"
    assert seq[3] == "NEUTRAL"
    assert seq[4] == "STRENGTHEN"


def test_conflict_fades_like_neutral():
    seq = publish_sequence(["STRENGTHEN", "STRENGTHEN", "CONFLICT"])
    assert seq == ["NEUTRAL", "STRENGTHEN", "NEUTRAL"]


def test_weaken_symmetric():
    assert publish_sequence(["WEAKEN", "WEAKEN", "NEUTRAL"]) == ["NEUTRAL", "WEAKEN", "NEUTRAL"]
    assert publish_sequence(["WEAKEN", "WEAKEN", "STRENGTHEN", "STRENGTHEN"]) == [
        "NEUTRAL",
        "WEAKEN",
        "WEAKEN",
        "STRENGTHEN",
    ]


def _ts(day: str, hm: str) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN_TZ)


def _bar(symbol, ts, o, h, l, c, v):
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


def _grid(day, symbol, vols_and_dir):
    t = _ts(day, "09:15")
    rows = []
    for vol, up in vols_and_dir:
        o = 20000
        c = 20200 if up else 19800
        rows.append(_bar(symbol, t, o, max(o, c) + 50, min(o, c) - 50, c, vol))
        t += timedelta(minutes=5)
        if t.hour == 11 and t.minute > 30:
            t = _ts(day, "13:00")
    return pd.DataFrame(rows)


def _cand(symbol="HPG", day="2026-08-14"):
    return CandidateEvent(
        symbol=symbol,
        session=date.fromisoformat(day),
        candidate_reason="MUA NHỎ / ƯU TIÊN",
        candidate_ts=f"{day} 15:05:00",
        bot_context="PULL VỪA",
    )


def test_interpreter_session_keeps_raw_and_published(tmp_path: Path):
    day = "2026-08-14"
    # 10 quiet, 1 spike (raw S unpublished), 2 spikes (publish S), fade
    dirs = [(1000, True)] * 10 + [(4000, True), (1000, True), (4000, True), (4000, True), (1000, True)]
    overlay = _grid(day, "HPG", dirs)
    rows = interpret_candidate_session(overlay, _cand(), None, 5)
    assert all(r.alert_eligible is False for r in rows)
    raw = [r.raw_evidence for r in rows]
    pub = [r.published_evidence for r in rows]
    assert "STRENGTHEN" in raw
    # first isolated spike must not publish
    first_s = raw.index("STRENGTHEN")
    assert pub[first_s] == "NEUTRAL"
    # two consecutive raw S publish on the second
    assert any(p == "STRENGTHEN" for p in pub)
    assert all(r.evidence == r.published_evidence for r in rows)
    assert {r.ledger_version for r in rows} == {"pxv_v1_slice1c_debounce"}


def test_dgc_structural_no_published_sw():
    day = "2026-08-14"
    t = _ts(day, "09:15")
    rows = []
    for _ in range(17):
        rows.append(_bar("DGC", t, 90000, 90000, 90000, 90000, 12000))
        t += timedelta(minutes=15)
        if t.hour == 11 and t.minute > 15:
            t = _ts(day, "13:00")
    overlay = pd.DataFrame(rows)
    out = interpret_candidate_session(overlay, _cand("DGC"), None, 0)
    assert all(r.raw_evidence == "UNUSABLE" for r in out)
    assert all(r.published_evidence == "UNUSABLE" for r in out)
    assert all(r.alert_eligible is False for r in out)


def test_apply_debounce_and_compare(tmp_path: Path):
    day = "2026-08-28"
    t0 = datetime(2026, 8, 28, 9, 30, tzinfo=VN_TZ)
    recs = []
    # many 1-bar raw S, plus a 3-bar raw S, plus DGC unusable
    labels = (
        ["STRENGTHEN", "NEUTRAL"] * 6
        + ["STRENGTHEN", "STRENGTHEN", "STRENGTHEN", "NEUTRAL"]
    )
    for i, ev in enumerate(labels):
        recs.append(
            {
                "symbol": "GMD",
                "session": day,
                "asof": (t0 + timedelta(minutes=5 * i)).isoformat(),
                "asof_hm": (t0 + timedelta(minutes=5 * i)).strftime("%H:%M"),
                "candidate_reason": "MUA NHỎ / ƯU TIÊN",
                "data_state": "QUALIFIED",
                "gate_reason": "INTERVAL+TOD_IMMATURE",
                "tod_maturity": "TOD_PRELIMINARY",
                "overlay_applied": False,
                "evidence": ev,
                "raw_evidence": ev,
                "would_be_alert": False,
                "alert_eligible": False,
                "features": {},
            }
        )
    recs.append(
        {
            "symbol": "DGC",
            "session": day,
            "asof": t0.isoformat(),
            "asof_hm": "09:30",
            "candidate_reason": "MUA NHỎ / ƯU TIÊN",
            "data_state": "UNUSABLE",
            "gate_reason": "STRUCTURAL",
            "tod_maturity": "TOD_PRELIMINARY",
            "overlay_applied": False,
            "evidence": "UNUSABLE",
            "raw_evidence": "UNUSABLE",
            "would_be_alert": False,
            "alert_eligible": False,
            "features": {},
        }
    )
    ledger = tmp_path / "shadow_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    df = apply_debounce_columns(load_ledger(ledger))
    assert int(df["alert_eligible"].sum()) == 0
    cmp = compare_raw_published(df, str(ledger))
    assert cmp["checks"]["alert_eligible_true_count"] == 0
    assert cmp["checks"]["dgc_published_sw"] is False
    raw_sw = next(r["raw"] for r in cmp["comparison_table"] if r["metric"] == "sw_runs")
    pub_sw = next(r["published"] for r in cmp["comparison_table"] if r["metric"] == "sw_runs")
    assert pub_sw < raw_sw
    assert cmp["gmd_2026_08_28"]["missing"] is False
    assert "STRENGTHEN" in set(df["published_evidence"])


def test_debounce_verdict_predeclared():
    from modules.intraday_pxv_v1.examine import debounce_verdict

    raw = {"sw_runs": 967, "1_bar": 814, "direct_opposite_reversals": 122}
    # identity: published runs = raw persist>=2, mostly 1 published bar
    pub = {"sw_runs": 153, "1_bar": 126, "direct_opposite_reversals": 20}
    timing = {"09:15-10:00": 14, "10:00-11:30": 46, "13:00-14:00": 74, "14:00-close": 19}
    v = debounce_verdict(raw, pub, timing)
    assert v["verdict"] == "DEBOUNCE_PARTIAL"
    gone = debounce_verdict(raw, {"sw_runs": 3, "1_bar": 1, "direct_opposite_reversals": 0}, timing)
    assert gone["verdict"] == "DEBOUNCE_INEFFECTIVE"
    good = debounce_verdict(
        raw,
        {"sw_runs": 80, "1_bar": 20, "direct_opposite_reversals": 5},
        {"09:15-10:00": 10, "10:00-11:30": 30, "13:00-14:00": 30, "14:00-close": 10},
    )
    assert good["verdict"] == "DEBOUNCE_EFFECTIVE"


def test_examiner_default_uses_evidence_column(tmp_path: Path):
    day = "2026-08-14"
    t0 = datetime(2026, 8, 14, 9, 30, tzinfo=VN_TZ)
    rows = []
    for i, ev in enumerate(["STRENGTHEN", "STRENGTHEN", "NEUTRAL"]):
        rows.append(
            {
                "symbol": "HPG",
                "session": day,
                "asof": (t0 + timedelta(minutes=5 * i)).isoformat(),
                "asof_hm": (t0 + timedelta(minutes=5 * i)).strftime("%H:%M"),
                "candidate_reason": "MUA NHỎ / ƯU TIÊN",
                "data_state": "QUALIFIED",
                "gate_reason": "INTERVAL",
                "tod_maturity": "TOD_PRELIMINARY",
                "overlay_applied": False,
                "evidence": ev,
                "would_be_alert": i == 1,
                "alert_eligible": False,
                "features": {},
            }
        )
    ledger = tmp_path / "l.jsonl"
    with ledger.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    result = examine(ledger, None)
    assert result["persistence"]["sw_runs"] == 1
    assert result["persistence"]["ge_2_bars"] == 1
