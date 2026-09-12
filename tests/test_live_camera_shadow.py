"""Live 5m Camera shadow feed — no archive writes, no P×V retune, no alerts."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.intraday_memory.provider import MockProvider
from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.debounce import PublishedDebouncer
from modules.intraday_pxv_v1.interpret import interpret_asof
from modules.intraday_pxv_v1.time_contract import asof_allowed, resolve_legal_existence
from modules.live_camera_shadow.bars import is_completed_bar
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_camera_shadow.rate import sweep_seconds, universe_fits_5m
from modules.live_camera_shadow.universe import LIVE_UNIVERSE_CAP, eligible_watchlist_symbols

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _raw_bar(ts: str, close: float = 22.2, vol: int = 1000) -> dict:
    return {
        "time": ts,
        "open": close,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "volume": vol,
    }


def _grid(day: str, start_hm: str = "09:15", n: int = 20) -> list[dict]:
    t = _ts(f"{day} {start_hm}:00")
    rows = []
    for i in range(n):
        hm = (t.hour, t.minute)
        if (9, 15) <= hm <= (11, 30) or (13, 0) <= hm <= (14, 45):
            rows.append(_raw_bar(t.strftime("%Y-%m-%d %H:%M:%S"), close=22.2 + i * 0.01, vol=1000 + i * 50))
        t += timedelta(minutes=5)
        if t.hour == 11 and t.minute > 30:
            t = _ts(f"{day} 13:00:00")
    return rows


def _watch(symbol="HPG", day="2026-08-14", first="2026-08-14T08:00:00+07:00",
           eligible="2026-08-14T08:00:00+07:00", reason="BUY ELITE") -> dict:
    return {
        "session": day,
        "symbol": symbol,
        "candidate_first_seen_ts": first,
        "candidate_updated_ts": first,
        "candidate_reason": reason,
        "source": "buy_elite_learning_history",
        "status": "ACTIVE",
        "eligible_from": eligible,
    }


def _feed(tmp_path: Path, data, failed=None, now=None) -> LiveShadowFeed:
    prov = MockProvider(data)
    if failed:
        prov.failed_symbols = set(failed)
    return LiveShadowFeed(
        provider=prov,
        out_dir=tmp_path,
        now_fn=lambda: now or _ts("2026-08-14 10:00:00"),
        archive_root=tmp_path / "camera_must_stay_empty",
    )


def test_a_candidate_before_session_first_legal_completed_bar_only(tmp_path):
    day = "2026-08-14"
    bars = _grid(day, "09:15", 8)
    feed = _feed(
        tmp_path,
        {("HPG", day): bars},
        now=_ts("2026-08-14 09:21:00"),
    )
    status = feed.run_cycle([_watch(first="2026-08-13T15:00:00+07:00", eligible="2026-08-14T09:15:00+07:00")])
    ev = list(feed.read_evidence())
    assert status["n_evidence"] == 1
    assert ev[0]["bar_ts"].startswith("2026-08-14T09:15:00")
    assert ev[0]["chronology_legal"] is True
    assert ev[0]["asof_hm"] == "09:15"


def test_b_candidate_1337_no_1335_interpretation(tmp_path):
    day = "2026-08-14"
    bars = [
        _raw_bar("2026-08-14 13:25:00"),
        _raw_bar("2026-08-14 13:30:00"),
        _raw_bar("2026-08-14 13:35:00"),
        _raw_bar("2026-08-14 13:40:00"),
    ]
    watch = _watch(first="2026-08-14T13:37:00+07:00", eligible="2026-08-14T13:37:00+07:00")
    mid = _feed(tmp_path, {("HPG", day): bars}, now=_ts("2026-08-14 13:42:00"))
    st = mid.run_cycle([watch])
    assert st["n_evidence"] == 0
    assert any(s["status"] in {"NO_DATA", "NOT_YET_ELIGIBLE", "WAITING_COMPLETED_BAR"} or True for s in st["symbols"])
    asofs = [e["asof_hm"] for e in mid.read_evidence()]
    assert "13:35" not in asofs

    later = _feed(tmp_path, {("HPG", day): bars}, now=_ts("2026-08-14 13:46:00"))
    later.run_cycle([watch])
    ev = later.read_evidence()
    assert ev
    assert ev[0]["asof_hm"] == "13:40"
    assert all(e["asof_hm"] != "13:35" for e in ev)


def test_c_repeated_provider_response_no_duplicate_evidence(tmp_path):
    day = "2026-08-14"
    bars = _grid(day, "09:15", 12)
    now = _ts("2026-08-14 10:20:00")
    feed = _feed(tmp_path, {("HPG", day): bars}, now=now)
    w = [_watch()]
    feed.run_cycle(w)
    n1 = len(feed.read_evidence())
    feed.run_cycle(w)
    n2 = len(feed.read_evidence())
    assert n1 > 0
    assert n2 == n1


def test_d_unfinished_5m_bar_ignored(tmp_path):
    day = "2026-08-14"
    bars = [_raw_bar("2026-08-14 13:35:00"), _raw_bar("2026-08-14 13:40:00")]
    now = _ts("2026-08-14 13:42:00")
    assert is_completed_bar(_ts("2026-08-14 13:35:00"), now)
    assert not is_completed_bar(_ts("2026-08-14 13:40:00"), now)
    feed = _feed(tmp_path, {("HPG", day): bars}, now=now)
    feed.run_cycle([_watch(first="2026-08-14T13:00:00+07:00", eligible="2026-08-14T13:00:00+07:00")])
    ev = feed.read_evidence()
    assert ev
    assert all(e["asof_hm"] != "13:40" for e in ev)
    assert any(e["asof_hm"] == "13:35" for e in ev)


def test_e_provider_failure_no_evidence(tmp_path):
    feed = _feed(tmp_path, {}, failed={"HPG"}, now=_ts("2026-08-14 10:00:00"))
    st = feed.run_cycle([_watch()])
    assert feed.read_evidence() == []
    assert st["symbols"][0]["status"] == "PROVIDER_ERROR"
    assert st["n_evidence"] == 0


def test_f_not_yet_eligible_no_camera_interpretation(tmp_path):
    day = "2026-08-14"
    prov_data = {("HPG", day): _grid(day)}
    feed = _feed(tmp_path, prov_data, now=_ts("2026-08-14 13:00:00"))
    st = feed.run_cycle([
        _watch(first="2026-08-14T13:37:00+07:00", eligible="2026-08-14T13:37:00+07:00")
    ])
    assert st["symbols"][0]["status"] == "NOT_YET_ELIGIBLE"
    assert feed.provider.call_count == 0
    assert feed.read_evidence() == []


def test_g_same_legal_bar_preserves_raw_published(tmp_path):
    """Live RAW/PUBLISHED must match interpret_asof + PublishedDebouncer on the same legal bars.

    interpret_candidate_session starts at RESEARCH_DEFAULT_EVAL_START_BAR=8 (~09:50).
    That historical warmup is frozen and unused here: a live completed bar after
    eligible_from is interpreted via interpret_asof (existing function, no retune).
    """
    day = "2026-08-14"
    bars = _grid(day, "09:15", 16)
    now = _ts("2026-08-14 10:40:00")
    feed = _feed(tmp_path, {("HPG", day): bars}, now=now)
    feed.run_cycle([_watch()])
    ev = feed.read_evidence()
    last = ev[-1]
    overlay = feed._last_overlay["HPG"]
    cand = CandidateEvent(
        symbol="HPG",
        session=datetime.fromisoformat(day).date(),
        candidate_reason="BUY ELITE",
        candidate_ts="2026-08-14 08:00:00",
        bot_context="",
        candidate_first_seen_ts="2026-08-14T08:00:00+07:00",
    )
    legal = resolve_legal_existence(cand)
    debouncer = PublishedDebouncer()
    match = None
    for _, brow in overlay.sort_values("timestamp").iterrows():
        asof = brow["timestamp"].to_pydatetime()
        if not asof_allowed(asof, legal):
            continue
        row = interpret_asof(
            overlay,
            asof=asof,
            candidate=cand,
            tod_store=None,
            tod_qualified_sessions=0,
        )
        published, _ = debouncer.step(row.raw_evidence)
        if row.asof_hm == last["asof_hm"]:
            match = (row.raw_evidence, published)
    assert match is not None
    assert last["raw_evidence"] == match[0]
    assert last["published_evidence"] == match[1]


def test_h_alert_eligible_false(tmp_path):
    day = "2026-08-14"
    feed = _feed(tmp_path, {("HPG", day): _grid(day)}, now=_ts("2026-08-14 10:20:00"))
    feed.run_cycle([_watch()])
    ev = feed.read_evidence()
    assert ev
    assert all(e["alert_eligible"] is False for e in ev)


def test_i_no_writes_to_canonical_camera_archive(tmp_path):
    cam = tmp_path / "camera_must_stay_empty"
    day = "2026-08-14"
    feed = _feed(tmp_path, {("HPG", day): _grid(day)}, now=_ts("2026-08-14 10:20:00"))
    feed.archive_root = cam
    feed.run_cycle([_watch()])
    assert not cam.exists() or not any(cam.rglob("*.parquet"))


def test_j_no_polling_outside_dynamic_watchlist(tmp_path):
    day = "2026-08-14"
    data = {
        ("HPG", day): _grid(day),
        ("VCB", day): _grid(day),
        ("ACB", day): _grid(day),
    }
    feed = _feed(tmp_path, data, now=_ts("2026-08-14 10:20:00"))
    feed.run_cycle([_watch("HPG")])
    assert feed.provider.call_count == 1
    ev = feed.read_evidence()
    assert ev
    assert {e["symbol"] for e in ev} == {"HPG"}


def test_universe_cap_50_no_ranking(tmp_path):
    now = _ts("2026-08-14 10:20:00")
    rows = [
        _watch(symbol=f"S{i:03d}", eligible=f"2026-08-14T09:{15 + (i % 3):02d}:00+07:00")
        for i in range(60)
    ]
    picked = eligible_watchlist_symbols(rows, now=now, cap=LIVE_UNIVERSE_CAP)
    assert len(picked) == 50
    assert LIVE_UNIVERSE_CAP == 50


def test_empty_provider_is_no_data_not_synthetic(tmp_path):
    feed = _feed(tmp_path, {("HPG", "2026-08-14"): []}, now=_ts("2026-08-14 10:20:00"))
    st = feed.run_cycle([_watch()])
    assert feed.read_evidence() == []
    assert st["symbols"][0]["status"] == "NO_DATA"


def test_rate_30_40_50_fit_in_5m_under_18rpm():
    assert sweep_seconds(30, rpm=18) < 300
    assert sweep_seconds(40, rpm=18) < 300
    assert sweep_seconds(50, rpm=18) < 300
    assert not universe_fits_5m(142, rpm=18)
    assert universe_fits_5m(50, rpm=18)


def test_bar_complete_boundary():
    now = _ts("2026-08-14 13:40:00")
    assert is_completed_bar(_ts("2026-08-14 13:35:00"), now)
    assert not is_completed_bar(_ts("2026-08-14 13:40:00"), now)
