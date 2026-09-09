"""Focused Slice 1 tests for audit-discovered dangerous cases."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.archive import overlay_session
from modules.intraday_pxv_v1.candidates import CandidateEvent, load_candidate_events
from modules.intraday_pxv_v1.constants import (
    DATA_QUALIFIED,
    DATA_UNUSABLE,
    EV_NEUTRAL,
    EV_STRENGTHEN,
    EV_UNUSABLE,
    EV_WEAKEN,
)
from modules.intraday_pxv_v1.evidence import decide_evidence
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PXV, FAM_TOD_RVOL, compute_features
from modules.intraday_pxv_v1.gate import GATE_CUMULATIVE, GATE_INTERVAL, GATE_STRUCTURAL, GATE_THIN, evaluate_gate
from modules.intraday_pxv_v1.interpret import interpret_asof
from modules.intraday_pxv_v1.message import render_message


def _ts(day: str, hm: str) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN_TZ)


def _bar(symbol: str, ts: datetime, o, h, l, c, v, qf="ok"):
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
        "quality_flag": qf,
    }


def _session_grid(day: str, symbol: str, *, vol=1000, up=True, n=46, step_min=5):
    start = _ts(day, "09:15")
    rows = []
    i = 0
    t = start
    end = _ts(day, "14:45")
    while t <= end and i < n:
        hm = (t.hour, t.minute)
        if (9, 15) <= hm <= (11, 30) or (13, 0) <= hm <= (14, 45):
            o = 20000
            c = 20100 if up else 19900
            rows.append(_bar(symbol, t, o, max(o, c) + 50, min(o, c) - 50, c, vol))
            i += 1
        t += timedelta(minutes=step_min)
        if t.hour == 11 and t.minute > 30 and t.hour < 13:
            t = _ts(day, "13:00")
    return rows


def _write_session(root: Path, day: str, rows: list[dict], quarantine: list[dict] | None = None):
    sess = date.fromisoformat(day)
    part = (
        root
        / "canonical"
        / f"year={sess.year}"
        / f"month={sess.month:02d}"
        / f"session_date={sess.isoformat()}"
    )
    part.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(part / "bars.parquet", index=False)
    if quarantine:
        qdir = part / "quarantine"
        qdir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(quarantine).to_parquet(qdir / "changed_20260904_073000.parquet", index=False)


def _cand(symbol="HPG", day="2026-08-14", reason="MUA NHỎ / ƯU TIÊN") -> CandidateEvent:
    return CandidateEvent(
        symbol=symbol,
        session=date.fromisoformat(day),
        candidate_reason=reason,
        candidate_ts=f"{day} 15:05:00",
        bot_context="PULL VỪA",
    )


def _gate_and_features(rows, asof, **kwargs):
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(VN_TZ)
    df["overlay_applied"] = kwargs.pop("overlay_applied", False)
    gate = evaluate_gate(df, asof=asof, tod_qualified_sessions=kwargs.pop("tod_n", 5))
    feats = compute_features(
        df,
        gate,
        asof=asof,
        tod_rvol_baseline=kwargs.pop("rvol_base", 1000.0),
        tod_pace_baseline=kwargs.pop("pace_base", 20000.0),
    )
    return df, gate, feats


def test_interval_volume_session_is_qualified_not_trusted_when_tod_immature():
    rows = _session_grid("2026-08-14", "HPG", vol=1000, up=True)
    asof = rows[-1]["timestamp"]
    _, gate, feats = _gate_and_features(rows, asof, tod_n=5)
    assert gate.volume_kind == GATE_INTERVAL
    assert gate.data_state == DATA_QUALIFIED
    assert gate.data_state != "TRUSTED"
    assert FAM_EXPANSION in feats
    assert FAM_TOD_RVOL in feats
    assert feats[FAM_TOD_RVOL]["confidence"] == "LOW_CONFIDENCE"
    assert feats[FAM_TOD_RVOL]["tod_maturity"] == "TOD_PRELIMINARY"


def test_cumulative_like_volume_omits_increment_families():
    day = "2026-08-14"
    base = _session_grid(day, "PVD", vol=100, up=True)
    # last bar carries almost all volume
    base[-1]["volume"] = 50_000
    asof = base[-1]["timestamp"]
    _, gate, feats = _gate_and_features(base, asof)
    assert gate.volume_kind == GATE_CUMULATIVE
    assert FAM_EXPANSION not in feats
    assert FAM_PXV not in feats
    assert FAM_TOD_RVOL not in feats
    assert "volume_expansion" not in feats


def test_dgc_structural_unusable_no_features():
    day = "2026-08-14"
    rows = []
    t = _ts(day, "09:15")
    for _ in range(17):
        rows.append(_bar("DGC", t, 90000, 90000, 90000, 90000, 12000))
        t += timedelta(minutes=15)
        if t.hour == 11 and t.minute > 15:
            t = _ts(day, "13:00")
    asof = rows[-1]["timestamp"]
    df, gate, feats = _gate_and_features(rows, asof)
    assert gate.gate_reason == GATE_STRUCTURAL
    assert gate.data_state == DATA_UNUSABLE
    assert feats == {}
    ev = decide_evidence(gate, feats, thesis_long=True)
    assert ev.evidence == EV_UNUSABLE
    msg = render_message(
        symbol="DGC", asof_hm="14:45", candidate_reason="MUA NHỎ / ƯU TIÊN",
        gate=gate, features=feats, evidence=ev,
    )
    assert "UNUSABLE" in msg
    assert "STRUCTURAL" in msg


def test_thin_session_unusable():
    day = "2026-08-14"
    rows = _session_grid(day, "MML", vol=100, n=8)
    asof = rows[-1]["timestamp"]
    # only 8 bars but asof is last of those 8 early bars — make asof late so expected is large
    late = _ts(day, "14:45")
    rows[-1]["timestamp"] = late
    _, gate, feats = _gate_and_features(rows, late)
    assert gate.gate_reason == GATE_THIN
    assert gate.data_state == DATA_UNUSABLE
    assert feats == {}


def test_stale_canonical_uses_latest_quarantine_overlay(tmp_path: Path):
    day = "2026-09-04"
    canon = _session_grid(day, "HPG", vol=100, up=True)
    revised = [dict(r) for r in canon]
    for r in revised:
        r["volume"] = 5000
    _write_session(tmp_path, day, canon, quarantine=revised)
    ov = overlay_session(tmp_path, date.fromisoformat(day))
    hpg = ov[ov["symbol"] == "HPG"]
    assert bool(hpg["overlay_applied"].iloc[0]) is True
    assert int(hpg["volume"].iloc[0]) == 5000
    assert (hpg["bar_source"] == "revised_quarantine").all()
    gate = evaluate_gate(hpg, tod_qualified_sessions=5)
    assert "STALE_FIRST_WRITE" in gate.gate_reason
    assert gate.overlay_applied is True
    assert gate.data_state != "TRUSTED"


def test_missing_data_unavailable():
    gate = evaluate_gate(pd.DataFrame(), tod_qualified_sessions=0)
    assert gate.data_state == DATA_UNUSABLE
    assert gate.gate_reason == "UNAVAILABLE"
    feats = compute_features(pd.DataFrame(), gate, asof=_ts("2026-08-14", "14:45"),
                             tod_rvol_baseline=1, tod_pace_baseline=1)
    assert feats == {}


def test_quality_flag_ok_is_not_trusted():
    rows = _session_grid("2026-08-14", "VCB", vol=800)
    _, gate, _ = _gate_and_features(rows, rows[-1]["timestamp"], tod_n=5)
    assert (pd.DataFrame(rows)["quality_flag"] == "ok").all()
    assert gate.data_state != "TRUSTED"
    assert "quality_flag=ok_not_sufficient" in gate.notes


def test_strengthen_and_weaken_and_no_zero_fill():
    rows = _session_grid("2026-08-14", "HPG", vol=1000, up=True)
    # last bar huge up volume
    rows[-1]["volume"] = 8000
    rows[-1]["close"] = 20500
    rows[-1]["high"] = 20600
    asof = rows[-1]["timestamp"]
    df, gate, feats = _gate_and_features(rows, asof)
    ev = decide_evidence(gate, feats, thesis_long=True)
    assert ev.evidence == EV_STRENGTHEN
    assert FAM_EXPANSION in feats

    # weak: up on dry volume
    rows2 = _session_grid("2026-08-14", "HPG", vol=2000, up=True)
    rows2[-1]["volume"] = 200
    rows2[-1]["close"] = 20500
    rows2[-1]["high"] = 20600
    df2, gate2, feats2 = _gate_and_features(rows2, rows2[-1]["timestamp"])
    ev2 = decide_evidence(gate2, feats2, thesis_long=True)
    assert ev2.evidence == EV_WEAKEN

    # cumulative must not invent expansion=0
    rows3 = [dict(r) for r in rows]
    for r in rows3[:-1]:
        r["volume"] = 10
    rows3[-1]["volume"] = 80_000
    _, gate3, feats3 = _gate_and_features(rows3, rows3[-1]["timestamp"])
    assert gate3.volume_kind == GATE_CUMULATIVE
    assert FAM_EXPANSION not in feats3
    assert "volume_expansion" not in feats3


def test_message_has_no_trade_verbs_except_passthrough_reason():
    rows = _session_grid("2026-08-14", "HPG", vol=1000)
    asof = rows[-1]["timestamp"]
    df, gate, feats = _gate_and_features(rows, asof)
    ev = decide_evidence(gate, feats, thesis_long=True)
    reason = "MUA NHỎ / ƯU TIÊN"
    msg = render_message(symbol="HPG", asof_hm="14:45", candidate_reason=reason, gate=gate, features=feats, evidence=ev)
    body = msg.replace(reason, "")
    assert "BUY" not in body
    assert "SELL" not in body
    assert "not a trade instruction" in msg
    assert reason in msg


def test_alert_eligible_always_false():
    rows = _session_grid("2026-08-14", "HPG", vol=1000)
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(VN_TZ)
    df["overlay_applied"] = False
    df["bar_source"] = "canonical"
    row = interpret_asof(
        df,
        asof=rows[-1]["timestamp"],
        candidate=_cand(),
        tod_store=None,
        tod_qualified_sessions=5,
    )
    assert row.alert_eligible is False


def test_candidate_loader_does_not_invent_or_use_watchlist(tmp_path: Path):
    p = tmp_path / "buy_elite_learning_history.csv"
    pd.DataFrame(
        [
            {"date": "2026-08-14", "time": "15:05:00", "symbol": "HPG",
             "conclusion": "BUY ELITE", "group": "PULL VỪA"},
            {"date": "2026-08-14", "time": "15:05:00", "symbol": "AAA",
             "conclusion": "WATCHLIST", "group": "THEO DÕI"},
        ]
    ).to_csv(p, index=False)
    ev = load_candidate_events(p, sessions=[date(2026, 8, 14)])
    assert [e.symbol for e in ev] == ["HPG"]
    assert ev[0].candidate_reason == "BUY ELITE"


def test_missing_candidate_file_is_empty(tmp_path: Path):
    assert load_candidate_events(tmp_path / "nope.csv") == []


def test_no_production_writes(tmp_path: Path):
    cam = tmp_path / "intraday_memory"
    day = "2026-08-14"
    _write_session(cam, day, _session_grid(day, "HPG"))
    before = {p: p.stat().st_mtime_ns for p in cam.rglob("*") if p.is_file()}
    overlay_session(cam, date.fromisoformat(day))
    after = {p: p.stat().st_mtime_ns for p in cam.rglob("*") if p.is_file()}
    assert before == after
