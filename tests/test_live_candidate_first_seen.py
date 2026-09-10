"""LIVE candidate first-seen + research Dynamic Watchlist. No Camera / P×V / alerts."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate.calendar import cash_session_end, next_trading_session_open
from modules.live_candidate.persist import apply_immutable_first_seen
from modules.live_candidate.watchlist import (
    CANONICAL_EMPTY_JSON,
    build_research_watchlist,
    encode_watchlist_text,
    persist_research_watchlist,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _row(day: str, symbol: str, conclusion: str, **extra) -> dict:
    rec = {
        "date": day,
        "time": extra.pop("time", "10:00:00"),
        "symbol": symbol,
        "conclusion": conclusion,
        "winprob": extra.pop("winprob", 80.0),
        "elite_score": extra.pop("elite_score", 70.0),
        "group": extra.pop("group", "PULL VỪA"),
    }
    rec.update(extra)
    return rec


def test_a_first_actionable_write_stamps_first_seen():
    now = _ts("2026-08-14 10:05:00")
    incoming = pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")])
    out = apply_immutable_first_seen(pd.DataFrame(), incoming, observed_at=now)
    assert len(out) == 1
    assert out.iloc[0]["candidate_first_seen_ts"] == now.isoformat()
    assert out.iloc[0]["candidate_updated_ts"] == now.isoformat()


def test_b_second_actionable_preserves_first_seen_updates_updated():
    t0 = _ts("2026-08-14 10:05:00")
    t1 = _ts("2026-08-14 13:20:00")
    first = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "MUA NHỎ / ƯU TIÊN")]),
        observed_at=t0,
    )
    second = apply_immutable_first_seen(
        first,
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE", winprob=90.0)]),
        observed_at=t1,
    )
    hit = second[second["symbol"] == "HPG"]
    assert len(hit) == 1
    assert hit.iloc[0]["candidate_first_seen_ts"] == t0.isoformat()
    assert hit.iloc[0]["candidate_updated_ts"] == t1.isoformat()
    assert hit.iloc[0]["conclusion"] == "BUY ELITE"


def test_c_same_symbol_next_session_gets_new_first_seen():
    t0 = _ts("2026-08-14 10:05:00")
    t1 = _ts("2026-08-17 09:20:00")
    d0 = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=t0,
    )
    d1 = apply_immutable_first_seen(
        d0,
        pd.DataFrame([_row("2026-08-17", "HPG", "BUY ELITE")]),
        observed_at=t1,
    )
    a = d1[d1["date"].astype(str) == "2026-08-14"].iloc[0]
    b = d1[d1["date"].astype(str) == "2026-08-17"].iloc[0]
    assert a["candidate_first_seen_ts"] == t0.isoformat()
    assert b["candidate_first_seen_ts"] == t1.isoformat()
    assert a["candidate_first_seen_ts"] != b["candidate_first_seen_ts"]


def test_d_missing_first_seen_is_never_invented():
    prior = pd.DataFrame(
        [_row("2026-06-29", "ACB", "MUA NHỎ / ƯU TIÊN", time="22:30:23")]
    )
    assert "candidate_first_seen_ts" not in prior.columns
    out = apply_immutable_first_seen(
        prior,
        pd.DataFrame([_row("2026-08-14", "HPG", "WATCHLIST")]),
        observed_at=_ts("2026-08-14 10:00:00"),
    )
    acb = out[out["symbol"] == "ACB"].iloc[0]
    assert not str(acb.get("candidate_first_seen_ts") or "").strip()
    wl = build_research_watchlist(out, now=_ts("2026-08-14 10:00:00"))
    assert "ACB" not in set(wl["symbol"]) if len(wl) else True


def test_actionable_to_non_actionable_preserves_first_seen():
    t0 = _ts("2026-08-14 10:05:00")
    t1 = _ts("2026-08-14 11:00:00")
    first = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=t0,
    )
    later = apply_immutable_first_seen(
        first,
        pd.DataFrame([_row("2026-08-14", "HPG", "WATCHLIST")]),
        observed_at=t1,
    )
    hit = later[later["symbol"] == "HPG"].iloc[0]
    assert hit["candidate_first_seen_ts"] == t0.isoformat()
    assert hit["conclusion"] == "WATCHLIST"
    wl = build_research_watchlist(later, now=t1)
    assert list(wl["symbol"]) == ["HPG"]
    assert wl.iloc[0]["status"] == "HELD"


def test_non_actionable_then_actionable_same_session_stamps_now():
    t0 = _ts("2026-08-14 10:00:00")
    t1 = _ts("2026-08-14 11:30:00")
    first = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "WATCHLIST")]),
        observed_at=t0,
    )
    assert not str(first.iloc[0].get("candidate_first_seen_ts") or "").strip()
    second = apply_immutable_first_seen(
        first,
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=t1,
    )
    assert second.iloc[0]["candidate_first_seen_ts"] == t1.isoformat()


def test_e_after_close_eligible_next_trading_session():
    friday = _ts("2026-08-14 15:41:00")
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "VCB", "MUA NHỎ / ƯU TIÊN")]),
        observed_at=friday,
    )
    assert cash_session_end(friday.date()) < friday
    eligible = next_trading_session_open(friday.date())
    assert eligible == _ts("2026-08-17 09:15:00")
    wl_friday = build_research_watchlist(hist, now=friday)
    assert wl_friday.empty
    wl_monday = build_research_watchlist(hist, now=eligible)
    assert list(wl_monday["symbol"]) == ["VCB"]
    assert pd.Timestamp(wl_monday.iloc[0]["eligible_from"]) == pd.Timestamp(eligible)


def test_f_watchlist_never_exposes_before_eligible_from():
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=_ts("2026-08-14 13:00:00"),
    )
    early = build_research_watchlist(hist, now=_ts("2026-08-14 12:59:00"))
    assert early.empty
    on_time = build_research_watchlist(hist, now=_ts("2026-08-14 13:00:00"))
    assert list(on_time["symbol"]) == ["HPG"]
    assert on_time.iloc[0]["eligible_from"].startswith("2026-08-14T13:00:00")


def test_g_scoring_and_conclusion_unchanged():
    prior = pd.DataFrame(
        [_row("2026-08-14", "AAA", "WATCHLIST", winprob=55.0, elite_score=40.0)]
    )
    incoming = pd.DataFrame(
        [
            _row("2026-08-14", "HPG", "BUY ELITE", winprob=88.0, elite_score=91.0),
            _row("2026-08-14", "AAA", "MUA NHỎ / ƯU TIÊN", winprob=76.0, elite_score=66.0),
        ]
    )
    out = apply_immutable_first_seen(prior, incoming, observed_at=_ts("2026-08-14 10:05:00"))
    hpg = out[out["symbol"] == "HPG"].iloc[0]
    aaa = out[out["symbol"] == "AAA"].iloc[0]
    assert hpg["conclusion"] == "BUY ELITE"
    assert float(hpg["winprob"]) == 88.0
    assert float(hpg["elite_score"]) == 91.0
    assert aaa["conclusion"] == "MUA NHỎ / ƯU TIÊN"
    assert float(aaa["winprob"]) == 76.0
    assert float(aaa["elite_score"]) == 66.0


def test_restart_persists_first_seen_across_reload(tmp_path):
    t0 = _ts("2026-08-14 10:05:00")
    t1 = _ts("2026-08-14 14:00:00")
    live = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=t0,
    )
    path = tmp_path / "hist.csv"
    live.to_csv(path, index=False)
    reloaded = pd.read_csv(path)
    again = apply_immutable_first_seen(
        reloaded,
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE", winprob=82.0)]),
        observed_at=t1,
    )
    assert again.iloc[0]["candidate_first_seen_ts"] == t0.isoformat()
    assert again.iloc[0]["candidate_updated_ts"] == t1.isoformat()


def test_watchlist_required_fields_and_no_trade_verbs_as_actions():
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    wl = build_research_watchlist(hist, now=_ts("2026-08-14 10:05:00"))
    for col in (
        "session",
        "symbol",
        "candidate_first_seen_ts",
        "candidate_updated_ts",
        "candidate_reason",
        "source",
        "status",
        "eligible_from",
    ):
        assert col in wl.columns
    assert wl.iloc[0]["source"] == "buy_elite_learning_history"
    assert wl.iloc[0]["status"] == "ACTIVE"
    assert "buy_action" not in wl.columns
    assert "sell_action" not in wl.columns


def test_empty_history_persists_canonical_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_LIVE_CANDIDATE_OUT", str(tmp_path))
    path = persist_research_watchlist(pd.DataFrame(), observed_at=_ts("2026-08-14 10:05:00"))
    raw = path.read_text(encoding="utf-8")
    assert raw == CANONICAL_EMPTY_JSON
    assert encode_watchlist_text(pd.DataFrame()) == CANONICAL_EMPTY_JSON
    assert __import__("json").loads(raw) == []


def test_persist_and_publish_empty_does_not_invent_rows(tmp_path):
    from modules.live_shadow_transport.watchlist_bus import persist_and_publish_research_watchlist

    published: list[str] = []

    def writer(path: str, text: str, message: str) -> str:
        published.append(text)
        assert path == "data/live_candidate/dynamic_watchlist.json"
        assert "HPG" not in text
        return "GITHUB_OK"

    path, result = persist_and_publish_research_watchlist(
        pd.DataFrame(),
        observed_at=_ts("2026-08-14 10:05:00"),
        out_dir=tmp_path,
        publisher=writer,
        skip_if_unchanged=False,
    )
    assert result.ok is True
    assert __import__("json").loads(path.read_text(encoding="utf-8")) == []
    assert __import__("json").loads(published[0]) == []
    assert published[0].strip() == "[]"


def test_persist_watchlist_writes_only_research_out(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_LIVE_CANDIDATE_OUT", str(tmp_path))
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    path = persist_research_watchlist(hist, observed_at=_ts("2026-08-14 10:05:00"))
    assert path.parent == tmp_path
    assert path.exists()
    snap = pd.read_json(path)
    assert list(snap["symbol"]) == ["HPG"]
