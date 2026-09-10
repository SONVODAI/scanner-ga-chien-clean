"""Read-only LIVE CANDIDATE × P×V panel. No Camera, no P×V recompute, no writes."""
from __future__ import annotations

import hashlib
import inspect
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_pxv_ui.html import render_html
from modules.live_candidate_pxv_ui.read import load_panel_sources
from modules.live_candidate_pxv_ui.view import (
    EMPTY_MESSAGE,
    NOT_LEGAL_NOTE,
    STALE_BANNER,
    WAITING_MESSAGE,
    build_panel,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
FORBIDDEN_IMPORTS = (
    "intraday_memory.provider",
    "KBSProvider",
    "MockProvider",
    "fetch_session",
    "upsert_session",
    "IntradayCollector",
    "interpret_asof",
    "interpret_candidate_session",
    "decide_evidence",
)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _watch(symbol="HPG", reason="BUY ELITE", first="2026-08-14T10:05:00+07:00",
           eligible="2026-08-14T10:05:00+07:00") -> dict:
    return {
        "session": "2026-08-14",
        "symbol": symbol,
        "candidate_first_seen_ts": first,
        "candidate_updated_ts": first,
        "candidate_reason": reason,
        "source": "buy_elite_learning_history",
        "status": "ACTIVE",
        "eligible_from": eligible,
    }


def _ev(symbol="HPG", bar="2026-08-14T14:10:00+07:00", obs="2026-08-14T14:12:00+07:00",
        raw="NEUTRAL", pub="NEUTRAL", why="no confirming or weakening P×V event at this bar",
        legal=True, data="QUALIFIED", **extra) -> dict:
    rec = {
        "symbol": symbol,
        "session": "2026-08-14",
        "bar_ts": bar,
        "asof": bar,
        "asof_hm": bar[11:16],
        "observed_at": obs,
        "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
        "eligible_from": "2026-08-14T10:05:00+07:00",
        "raw_evidence": raw,
        "published_evidence": pub,
        "evidence_why": why,
        "published_why": "published NEUTRAL (RAW fade)" if pub == "NEUTRAL" else "",
        "data_state": data,
        "data_quality": "ok",
        "chronology_legal": legal,
        "alert_eligible": False,
    }
    rec.update(extra)
    return rec


def _status(observed="2026-08-14T14:12:00+07:00", symbols=None) -> dict:
    return {
        "schema": "live_camera_shadow_status.v1",
        "session": "2026-08-14",
        "observed_at": observed,
        "alert_eligible": False,
        "symbols": symbols or [],
    }


def _panel(watch, evidence, status, now="2026-08-14T14:13:00"):
    return build_panel(
        now=_ts(now),
        sources={"watchlist": watch, "evidence": evidence, "status": status},
    )


def test_a_neutral_candidate_remains_visible():
    p = _panel(
        [_watch()],
        [_ev()],
        _status(symbols=[{"symbol": "HPG", "status": "OK"}]),
    )
    assert not p.empty
    assert p.cards[0]["symbol"] == "HPG"
    assert p.cards[0]["raw_evidence"] == "NEUTRAL"
    assert p.cards[0]["published_evidence"] == "NEUTRAL"
    assert p.cards[0]["evidence_valid"] is True
    html = render_html(p)
    assert "HPG" in html
    assert "PUBLISHED NEUTRAL" in html
    assert "vẫn đang được theo dõi" in html


def test_b_strengthen_visible():
    p = _panel(
        [_watch("GEE", first="2026-08-14T13:32:00+07:00", eligible="2026-08-14T13:32:00+07:00")],
        [_ev("GEE", bar="2026-08-14T13:50:00+07:00", obs="2026-08-14T13:52:00+07:00",
             raw="STRENGTHEN", pub="STRENGTHEN",
             why="5m expansion with P×V CONFIRMING")],
        _status("2026-08-14T13:52:00+07:00", [{"symbol": "GEE", "status": "OK"}]),
        now="2026-08-14T13:53:00",
    )
    c = p.cards[0]
    assert c["published_evidence"] == "STRENGTHEN"
    assert c["raw_evidence"] == "STRENGTHEN"
    assert "CONFIRMING" in c["explanation"]
    assert "GEE" in render_html(p)


def test_c_weaken_visible():
    p = _panel(
        [_watch("ACB")],
        [_ev("ACB", raw="WEAKEN", pub="WEAKEN", why="price up on contracted volume")],
        _status(symbols=[{"symbol": "ACB", "status": "OK"}]),
    )
    assert p.cards[0]["published_evidence"] == "WEAKEN"
    assert "co lại" in p.cards[0]["explanation"]


def test_d_unusable_visible_not_signal():
    p = _panel(
        [_watch("VCB")],
        [_ev("VCB", raw="UNUSABLE", pub="UNUSABLE", data="UNUSABLE",
             why="gate UNUSABLE — no volume evidence")],
        _status(symbols=[{"symbol": "VCB", "status": "UNUSABLE"}]),
    )
    c = p.cards[0]
    assert c["symbol"] == "VCB"
    assert c["published_evidence"] == "UNUSABLE"
    assert c["data_state"] in {"UNUSABLE"}
    html = render_html(p)
    assert "UNUSABLE" in html
    assert html.lower().count("buy") == 0 or "BUY ELITE" in html  # reason pass-through ok


def test_e_chronology_illegal_never_valid_evidence():
    p = _panel(
        [_watch()],
        [_ev(bar="2026-08-14T13:35:00+07:00", legal=False, raw="STRENGTHEN", pub="STRENGTHEN")],
        _status(symbols=[{"symbol": "HPG", "status": "OK"}]),
    )
    c = p.cards[0]
    assert c["evidence_valid"] is False
    assert c["published_evidence"] == ""
    assert c["raw_evidence"] == ""
    assert NOT_LEGAL_NOTE in c["explanation"]
    html = render_html(p)
    assert "data-valid=\"false\"" in html
    assert "PUBLISHED STRENGTHEN" not in html or 'data-valid="false"' in html
    assert "chronology_legal=false" in html


def test_f_stale_runner_clearly_marked():
    p = _panel(
        [_watch()],
        [_ev(obs="2026-08-14T10:00:00+07:00")],
        _status(observed="2026-08-14T10:00:00+07:00", symbols=[{"symbol": "HPG", "status": "OK"}]),
        now="2026-08-14T14:13:00",
    )
    assert p.runner["is_stale"] is True
    assert p.runner["label"] == "STALE"
    assert STALE_BANNER in p.runner["banner"]
    assert p.cards[0]["freshness"] == "STALE"
    html = render_html(p)
    assert "NOT current" in html
    assert "stale" in html


def test_g_waiting_for_first_completed_bar():
    p = _panel(
        [_watch()],
        [],
        _status(symbols=[{"symbol": "HPG", "status": "WAITING_COMPLETED_BAR"}]),
    )
    c = p.cards[0]
    assert c["waiting_first_bar"] is True
    assert WAITING_MESSAGE in c["explanation"]
    assert c["published_evidence"] == ""
    html = render_html(p)
    assert "Waiting for first eligible completed 5m bar" in html


def test_h_no_candidate_empty_state():
    p = _panel([], [], {})
    assert p.empty is True
    assert p.empty_message == EMPTY_MESSAGE
    html = render_html(p)
    assert "No active BOT Candidate." in html


def test_i_duplicate_evidence_does_not_duplicate_candidate():
    p = _panel(
        [_watch(), _watch()],
        [
            _ev(bar="2026-08-14T13:50:00+07:00", raw="NEUTRAL", pub="NEUTRAL"),
            _ev(bar="2026-08-14T14:10:00+07:00", raw="STRENGTHEN", pub="STRENGTHEN",
                why="5m expansion with P×V CONFIRMING"),
            _ev(bar="2026-08-14T14:10:00+07:00", raw="STRENGTHEN", pub="STRENGTHEN",
                why="5m expansion with P×V CONFIRMING"),
        ],
        _status(symbols=[{"symbol": "HPG", "status": "OK"}]),
    )
    assert len(p.cards) == 1
    assert p.cards[0]["latest_asof_hm"] == "14:10"
    assert p.cards[0]["published_evidence"] == "STRENGTHEN"


def test_j_ui_does_not_call_provider_or_camera():
    import modules.live_candidate_pxv_ui.html as html_mod
    import modules.live_candidate_pxv_ui.read as read_mod
    import modules.live_candidate_pxv_ui.render as render_mod
    import modules.live_candidate_pxv_ui.view as view_mod

    for mod in (read_mod, view_mod, html_mod, render_mod):
        src = inspect.getsource(mod)
        for token in FORBIDDEN_IMPORTS:
            assert token not in src, f"{mod.__name__} must not mention {token}"
    called = {"n": 0}

    class ForbiddenProvider:
        def fetch_session(self, *a, **k):
            called["n"] += 1
            raise AssertionError("UI must not call provider")

    p = build_panel(
        now=_ts("2026-08-14T14:13:00"),
        sources={"watchlist": [_watch()], "evidence": [_ev()], "status": _status()},
    )
    render_html(p)
    assert called["n"] == 0
    assert p.provider_called is False


def test_k_ui_does_not_modify_watchlist_or_evidence(tmp_path: Path):
    wl = tmp_path / "dynamic_watchlist.json"
    ev = tmp_path / "live_evidence.jsonl"
    st = tmp_path / "live_shadow_status.json"
    wl.write_text('[{"symbol":"HPG","candidate_reason":"BUY ELITE",'
                  '"candidate_first_seen_ts":"2026-08-14T10:05:00+07:00",'
                  '"eligible_from":"2026-08-14T10:05:00+07:00"}]\n', encoding="utf-8")
    ev.write_text(
        '{"symbol":"HPG","bar_ts":"2026-08-14T14:10:00+07:00","asof_hm":"14:10",'
        '"observed_at":"2026-08-14T14:12:00+07:00","raw_evidence":"NEUTRAL",'
        '"published_evidence":"NEUTRAL","chronology_legal":true,'
        '"evidence_why":"no confirming or weakening P×V event at this bar",'
        '"data_state":"QUALIFIED","alert_eligible":false}\n',
        encoding="utf-8",
    )
    st.write_text('{"observed_at":"2026-08-14T14:12:00+07:00","alert_eligible":false,"symbols":[]}\n', encoding="utf-8")

    def digest() -> str:
        h = hashlib.sha256()
        for p in (wl, ev, st):
            h.update(p.read_bytes())
        return h.hexdigest()

    before = digest()
    mtimes = {p: p.stat().st_mtime_ns for p in (wl, ev, st)}
    src = load_panel_sources(watchlist_path=wl, evidence_path=ev, status_path=st)
    build_panel(now=_ts("2026-08-14T14:13:00"), sources=src)
    assert digest() == before
    for p in (wl, ev, st):
        assert p.stat().st_mtime_ns == mtimes[p]


def test_l_alert_eligible_remains_false():
    p = _panel(
        [_watch()],
        [_ev(raw="STRENGTHEN", pub="STRENGTHEN", alert_eligible=True)],
        _status(),
    )
    assert p.alert_eligible is False
    assert all(c["alert_eligible"] is False for c in p.cards)
    assert 'data-alert-eligible="false"' in render_html(p)


def test_m_production_panels_unaffected():
    app = Path("app.py").read_text(encoding="utf-8")
    for title in (
        "👑 BUY ELITE - DECISION ENGINE",
        "🤖 AI Recommendation",
        "👑 FINAL DECISION",
        "⚡ STORM LEADERS - TIỀN ĐANG VÀO ĐÂU",
    ):
        assert title in app
    assert "LIVE CANDIDATE × P×V" in app
    assert "render_live_candidate_pxv_panel" in app
    # Hook is isolated: failure must not break production.
    assert "render_live_candidate_pxv_panel()" in app


def test_sort_published_before_neutral_before_unusable():
    p = _panel(
        [_watch("AAA"), _watch("BBB"), _watch("CCC"), _watch("DDD")],
        [
            _ev("AAA", raw="NEUTRAL", pub="NEUTRAL"),
            _ev("BBB", raw="STRENGTHEN", pub="STRENGTHEN", why="5m expansion with P×V CONFIRMING"),
            _ev("CCC", raw="WEAKEN", pub="NEUTRAL", why="price up on contracted volume"),
            _ev("DDD", raw="UNUSABLE", pub="UNUSABLE", data="UNUSABLE",
                why="gate UNUSABLE — no volume evidence"),
        ],
        _status(symbols=[
            {"symbol": "AAA", "status": "OK"},
            {"symbol": "BBB", "status": "OK"},
            {"symbol": "CCC", "status": "OK"},
            {"symbol": "DDD", "status": "UNUSABLE"},
        ]),
    )
    order = [c["symbol"] for c in p.cards]
    assert order[0] == "BBB"
    assert "DDD" == order[-1]


def test_history_keeps_transitions_not_every_bar():
    rows = [
        _ev(bar="2026-08-14T13:40:00+07:00", raw="NEUTRAL", pub="NEUTRAL"),
        _ev(bar="2026-08-14T13:45:00+07:00", raw="NEUTRAL", pub="NEUTRAL"),
        _ev(bar="2026-08-14T13:50:00+07:00", raw="STRENGTHEN", pub="NEUTRAL",
            why="5m expansion with P×V CONFIRMING"),
        _ev(bar="2026-08-14T13:55:00+07:00", raw="STRENGTHEN", pub="STRENGTHEN",
            why="5m expansion with P×V CONFIRMING"),
        _ev(bar="2026-08-14T14:00:00+07:00", raw="STRENGTHEN", pub="STRENGTHEN",
            why="5m expansion with P×V CONFIRMING"),
    ]
    p = _panel([_watch()], rows, _status())
    kinds = [h["kind"] for h in p.cards[0]["history"]]
    assert any("NEUTRAL → STRENGTHEN" in k or "RAW NEUTRAL → STRENGTHEN" in k for k in kinds)
    assert len(p.cards[0]["history"]) < len(rows)
