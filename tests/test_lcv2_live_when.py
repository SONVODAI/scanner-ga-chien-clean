"""Live V2 WHEN universe, schedule, lunch, lock, and archive isolation.

Does not claim a historical BUY_READY. Does not call KBS.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.intraday_memory.provider import MockProvider
from modules.live_camera_shadow.bars import (
    classify_stale,
    classify_stale_ignoring_lunch,
)
from modules.live_camera_shadow.cycle_lock import REASON_ALREADY_RUNNING, LiveWhenLock
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_camera_shadow.rate import GUEST_RPM, LIVE_UNIVERSE_CAP
from modules.live_camera_shadow.when_schedule import (
    is_live_when_window,
    live_when_fire_clocks,
)
from modules.intraday_pxv_v1.constants import EV_STRENGTHEN
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    REASON_CHRONOLOGY_PRE_ELIGIBLE,
    REASON_MANH_BUY_READY,
    REASON_PULL_BUY_READY,
    REASON_SESSION_RESET,
    REASON_UNFINISHED,
    STATE_BUY_READY,
)
from modules.live_candidate_v2_action.state import (
    evaluate_shadow_action,
    evaluation_trading_session,
)
from tests.test_lcv2_action_layer_shadow import _bar, _nom
from modules.live_candidate_v2_action.live_universe import (
    ACTIONABLE_LIVE_SETUPS,
    document_rows_for_live_when,
    select_actionable_v2,
)
from modules.live_candidate_v2_action.universe import current_session_v2_rows
from modules.live_candidate_v2_action.ui import (
    VALIDATION_TITLE,
    historical_buy_ready_rows,
    render_v2_shadow_action_panel,
)
from modules.live_candidate_v2_camera.observe import pxv_implies_buy

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
DAY = "2026-09-23"


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=VN)


def _row(
    symbol: str,
    setup: str,
    *,
    session: str = "2026-09-22",
    eligible: str = "2026-09-23T09:15:00+07:00",
    first: str = "2026-09-22T15:22:00+07:00",
    source: str = "brain_a_scan_setup",
    ema9: float | None = 100.0,
    breakout: float | None = 110.0,
) -> dict:
    return {
        "symbol": symbol,
        "session": session,
        "setup": setup,
        "group": setup,
        "source": source,
        "nomination_source": source,
        "candidate_first_seen_ts": first,
        "candidate_updated_ts": first,
        "eligible_from": eligible,
        "ema9_at_first_seen": ema9,
        "breakout_ref_at_first_seen": breakout,
        "price_at_first_seen": ema9,
        "observation_reference": "EMA9" if setup != "MUA BREAK" else "BREAKOUT_REF",
        "observation_intent": "WATCH_NOMINATED_SETUP",
        "source_action": "",
        "source_reason": "",
        "elite_buy_grade": "",
        "market_permission": "OK",
        "provenance": [{"source": source, "setup": setup}],
        "candidate_is_buy": False,
        "alert_eligible": False,
        "v2_camera": True,
    }


def _doc(rows: list[dict], session: str = DAY) -> dict:
    return {
        "schema": "live_candidate_v2_camera_sidecar_v1",
        "slice": 2,
        "mode": "SHADOW_ONLY",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
        "session": session,
        "generated_at": f"{session}T09:22:00+07:00",
        "observed_at": f"{session}T09:22:00+07:00",
        "freeze_ledger": [],
        "rows": rows,
    }


def _raw_bar(ts: str, close: float = 22.2, vol: int = 1000) -> dict:
    return {
        "time": ts,
        "open": close,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "volume": vol,
    }


class _St:
    def __init__(self) -> None:
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.frames: list[list] = []

    def markdown(self, text: str) -> None:
        self.markdowns.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def dataframe(self, rows, **kwargs) -> None:
        self.frames.append(list(rows))


def test_actionable_routes_only():
    rows = [
        _row("AAA", "PULL ĐẸP"),
        _row("BBB", "PULL VỪA"),
        _row("CCC", "CP MẠNH"),
        _row("DDD", "MUA BREAK"),
        _row("EEE", "MUA EARLY"),
        _row("FFF", "", source="market_aware_sweetspot"),
        _row("GGG", "THEO DÕI", source="buy_elite_learning_history"),
    ]
    selected = select_actionable_v2(rows, now=_ts(f"{DAY} 09:20:45"))
    assert {rec["symbol"] for rec in selected.fetch} == {"AAA", "BBB", "CCC", "DDD"}
    assert ACTIONABLE_LIVE_SETUPS == {"PULL ĐẸP", "PULL VỪA", "CP MẠNH", "MUA BREAK"}
    assert selected.fetch[0]["ema9_at_first_seen"] == 100.0
    assert selected.fetch[0]["provenance"]


def test_scan_date_brain_a_enters_after_eligible_from():
    """2026-09-23 document, Brain A row still stamped session 2026-09-22."""
    doc = _doc([_row("BVH", "PULL VỪA")])
    rows, reason = document_rows_for_live_when(doc, session=DAY)
    assert reason == ""
    assert rows[0]["session"] == "2026-09-22"
    # Post-close observer still requires row.session == today. Live WHEN must not.
    assert current_session_v2_rows(rows, DAY) == []
    before = select_actionable_v2(rows, now=_ts(f"{DAY} 09:10:00"))
    assert before.fetch == []
    assert before.not_yet[0]["symbol"] == "BVH"
    after = select_actionable_v2(rows, now=_ts(f"{DAY} 09:20:45"))
    assert [rec["symbol"] for rec in after.fetch] == ["BVH"]
    assert after.fetch[0]["eligible_from"].startswith(f"{DAY}T09:15")


def test_not_yet_eligible_is_not_fetched(tmp_path):
    provider = MockProvider({})
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: _ts(f"{DAY} 09:20:45"),
        archive_root=tmp_path / "archive",
    )
    status = feed.run_v2_when_cycle(
        sidecar_rows=[_row("BVH", "PULL VỪA", eligible=f"{DAY}T09:30:00+07:00")],
    )
    assert provider.call_count == 0
    assert status["kbs_polled"] is False
    assert status["fetched_symbols"] == []
    assert status["candidate_is_buy"] is False


def test_unfinished_bar_does_not_enter_evidence(tmp_path):
    now = _ts(f"{DAY} 09:20:45")
    provider = MockProvider({("BVH", DAY): [_raw_bar(f"{DAY} 09:20:00")]})
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: now,
        archive_root=tmp_path / "archive",
    )
    status = feed.run_v2_when_cycle(sidecar_rows=[_row("BVH", "PULL VỪA")])
    assert provider.call_count == 1
    assert feed.read_evidence() == []
    assert all(item.get("shadow_action") != STATE_BUY_READY for item in status["symbols"])
    state = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert state["rows"][0]["shadow_action"] != STATE_BUY_READY
    assert state["candidate_is_buy"] is False
    assert state["pxv_implies_buy"] is False
    assert state["alert_eligible"] is False


def test_lunch_gap_is_not_stale_and_afternoon_bar_evaluates(tmp_path):
    morning = _ts(f"{DAY} 11:25:00")
    at_1130 = _ts(f"{DAY} 11:30:00")
    at_1300 = _ts(f"{DAY} 13:00:00")
    at_1305 = _ts(f"{DAY} 13:05:45")
    assert classify_stale(morning, at_1305) is True
    assert classify_stale_ignoring_lunch(morning, at_1130) is False
    assert classify_stale_ignoring_lunch(morning, at_1300) is False
    assert classify_stale_ignoring_lunch(morning, at_1305) is False
    # Missing late-morning bars are still stale after lunch is removed.
    assert classify_stale_ignoring_lunch(_ts(f"{DAY} 10:00:00"), at_1305) is True

    provider = MockProvider(
        {
            ("BVH", DAY): [
                _raw_bar(f"{DAY} 11:25:00"),
                _raw_bar(f"{DAY} 13:00:00", close=22.4),
            ]
        }
    )
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: at_1305,
        archive_root=tmp_path / "archive",
    )
    status = feed.run_v2_when_cycle(sidecar_rows=[_row("BVH", "PULL VỪA")])
    assert status["symbols"][0]["status"] != "STALE_BAR"
    evidence = feed.read_evidence()
    assert any(str(row.get("bar_ts") or "").startswith(f"{DAY}T13:00") for row in evidence)
    assert all(row.get("pxv_implies_buy") is False for row in evidence)


def test_empty_universe_clears_current_rows(tmp_path):
    action_dir = tmp_path / "v2_action"
    action_dir.mkdir()
    prior = {
        "schema": "live_candidate_v2_action_state.v1",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "session": DAY,
        "observed_at": f"{DAY}T14:13:00+07:00",
        "rows": [
            {
                "symbol": "BVH",
                "setup": "PULL VỪA",
                "shadow_action": "WAIT",
                "action_state": "WAIT",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            },
            {
                "symbol": "HPG",
                "setup": "PULL VỪA",
                "shadow_action": STATE_BUY_READY,
                "action_state": STATE_BUY_READY,
                "trigger_bar_ts": f"{DAY}T10:00:00+07:00",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            },
        ],
    }
    (action_dir / "v2_action_state.json").write_text(json.dumps(prior), encoding="utf-8")
    feed = LiveShadowFeed(
        provider=MockProvider({}),
        out_dir=tmp_path,
        now_fn=lambda: _ts(f"{DAY} 14:33:45"),
        archive_root=tmp_path / "archive",
        action_out_dir=action_dir,
    )
    sweet = _row("AGR", "", source="market_aware_sweetspot", session=DAY)
    early = _row("MSH", "MUA EARLY")
    status = feed.run_v2_when_cycle(sidecar_rows=[sweet, early])
    assert status["published_empty"] is True
    assert status["kbs_polled"] is False
    current = json.loads((action_dir / "v2_action_state.json").read_text(encoding="utf-8"))
    assert current["rows"] == []
    assert current["actionable_universe_empty"] is True
    assert {rec["symbol"] for rec in current["historical_buy_ready"]} == {"HPG"}
    assert historical_buy_ready_rows(current)[0]["symbol"] == "HPG"

    fresh = _St()
    render_v2_shadow_action_panel(current, st_module=fresh)
    assert any("rows=0" in cap for cap in fresh.captions)
    assert VALIDATION_TITLE not in "\n".join(fresh.markdowns)
    assert all("BVH" not in str(frame) for frame in fresh.frames)

    current["observed_at"] = f"{DAY}T14:00:00+07:00"
    (action_dir / "v2_action_state.json").write_text(json.dumps(current), encoding="utf-8")
    stale = _St()
    render_v2_shadow_action_panel(
        None,
        st_module=stale,
        artifact_dir=action_dir,
        now=_ts(f"{DAY} 14:33:45"),
    )
    assert any(VALIDATION_TITLE in line for line in stale.markdowns)
    assert all("BVH" not in str(frame) for frame in stale.frames)


def _quiet_bars() -> list[dict]:
    """Three completed bars. Equal volume stays NORMAL; close sits above EMA9."""
    rows = []
    for hm in ("09:15", "09:20", "09:25"):
        rows.append(
            {
                "time": f"{DAY} {hm}:00",
                "open": 27.15,
                "high": 27.30,
                "low": 27.10,
                "close": 27.20,
                "volume": 1000,
            }
        )
    return rows


def _below_ref_bars() -> list[dict]:
    rows = []
    for hm in ("09:15", "09:20", "09:25"):
        rows.append(
            {
                "time": f"{DAY} {hm}:00",
                "open": 20.05,
                "high": 20.15,
                "low": 19.90,
                "close": 20.00,
                "volume": 1000,
            }
        )
    return rows


def _feed(tmp_path, provider, now: datetime) -> LiveShadowFeed:
    return LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: now,
        archive_root=tmp_path / "archive",
        action_out_dir=tmp_path / "v2_action",
    )


def test_departed_buy_ready_is_historical_only(tmp_path):
    """Cycle N mints SHADOW BUY_READY. Cycle N+1 drops that symbol."""
    clock = {"now": _ts(f"{DAY} 09:30:45")}
    provider = MockProvider({("BVH", DAY): _quiet_bars(), ("HPG", DAY): _below_ref_bars()})
    feed = _feed(tmp_path, provider, clock["now"])
    feed.now_fn = lambda: clock["now"]
    bvh = _row("BVH", "PULL VỪA", session=DAY, first=f"{DAY}T09:00:00+07:00", ema9=27.0, breakout=28.0)
    hpg = _row("HPG", "PULL ĐẸP", session=DAY, first=f"{DAY}T09:00:00+07:00", ema9=27.0, breakout=28.0)
    first = feed.run_v2_when_cycle(sidecar_rows=[bvh, hpg])
    state = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    by_symbol = {rec["symbol"]: rec for rec in state["rows"]}
    assert by_symbol["BVH"]["shadow_action"] == STATE_BUY_READY
    assert by_symbol["HPG"]["shadow_action"] != STATE_BUY_READY
    assert first["candidate_is_buy"] is False

    clock["now"] = _ts(f"{DAY} 09:35:45")
    second = feed.run_v2_when_cycle(sidecar_rows=[hpg])
    current = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert second["published_empty"] is False
    assert [rec["symbol"] for rec in current["rows"]] == ["HPG"]
    assert all(rec["shadow_action"] != STATE_BUY_READY for rec in current["rows"])
    ready = current["historical_buy_ready"]
    assert [rec["symbol"] for rec in ready] == ["BVH"]
    kept = ready[0]
    assert kept["shadow_action"] == STATE_BUY_READY
    assert kept["trigger_bar_ts"]
    assert kept["trigger_price"] == 27200
    assert kept["source"] == "brain_a_scan_setup"
    assert kept["setup"] == "PULL VỪA"
    assert kept["frozen_ref_kind"] == "EMA9"
    assert kept["frozen_ref_value"] == 27.0
    assert kept["published_evidence"]
    assert kept["volume_expansion_state"] in {"NORMAL", "CONTRACTION"}
    assert kept["market_permission"] == "OK"
    assert kept["action_reason"]
    assert kept["candidate_is_buy"] is False
    assert kept["pxv_implies_buy"] is False
    assert kept["alert_eligible"] is False
    assert current["candidate_is_buy"] is False
    assert current["pxv_implies_buy"] is False
    assert current["alert_eligible"] is False

    fresh = _St()
    render_v2_shadow_action_panel(current, st_module=fresh)
    assert VALIDATION_TITLE not in "\n".join(fresh.markdowns)
    assert all("BVH" not in str(frame) for frame in fresh.frames)

    current["observed_at"] = f"{DAY}T09:00:00+07:00"
    (tmp_path / "v2_action" / "v2_action_state.json").write_text(json.dumps(current), encoding="utf-8")
    stale = _St()
    render_v2_shadow_action_panel(
        None,
        st_module=stale,
        artifact_dir=tmp_path / "v2_action",
        now=clock["now"],
    )
    assert any(VALIDATION_TITLE in line for line in stale.markdowns)
    table = stale.frames[0]
    assert table[0]["Symbol"] == "BVH"
    assert table[0]["Source"] == "brain_a_scan_setup"
    assert table[0]["Setup"] == "PULL VỪA"
    assert str(table[0]["Trigger time"])
    assert table[0]["Trigger price"] == 27200
    assert "EMA9" in str(table[0]["Frozen ref"])
    assert "NORMAL" in str(table[0]["Volume/P×V evidence"]) or "CONTRACTION" in str(table[0]["Volume/P×V evidence"])
    assert table[0]["Market permission"] == "OK"
    assert table[0]["Reason"]
    assert all(row.get("Symbol") != "HPG" for row in table)


def test_departed_wait_is_not_historical_validation(tmp_path):
    clock = {"now": _ts(f"{DAY} 09:30:45")}
    provider = MockProvider({("STB", DAY): _below_ref_bars()})
    feed = _feed(tmp_path, provider, clock["now"])
    feed.now_fn = lambda: clock["now"]
    stb = _row("STB", "PULL VỪA", session=DAY, first=f"{DAY}T09:00:00+07:00", ema9=27.0, breakout=28.0)
    feed.run_v2_when_cycle(sidecar_rows=[stb])
    state = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert state["rows"][0]["symbol"] == "STB"
    assert state["rows"][0]["shadow_action"] == "WAIT"

    clock["now"] = _ts(f"{DAY} 09:35:45")
    sweet = _row("AGR", "", source="market_aware_sweetspot", session=DAY)
    status = feed.run_v2_when_cycle(sidecar_rows=[sweet])
    current = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert status["published_empty"] is True
    assert current["rows"] == []
    assert current.get("historical_buy_ready") == []
    assert historical_buy_ready_rows(current) == []
    assert "STB" not in json.dumps(current["rows"])


def test_overlap_lock_skips_second_cycle(tmp_path):
    held = LiveWhenLock(tmp_path)
    assert held.acquire() is True
    provider = MockProvider({})
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: _ts(f"{DAY} 09:20:45"),
    )
    status = feed.run_v2_when_cycle(sidecar_rows=[_row("BVH", "PULL VỪA")])
    assert status["reason"] == REASON_ALREADY_RUNNING
    assert status["exit_code"] == 75
    assert provider.call_count == 0
    assert status["kbs_polled"] is False
    held.release()


def test_permissions_stay_false():
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
    assert pxv_implies_buy("STRENGTHEN") is False


def test_live_path_does_not_write_camera_archive(tmp_path, monkeypatch):
    archive = tmp_path / "intraday_memory"
    archive.mkdir()

    def _boom(*_args, **_kwargs):
        raise AssertionError("upsert_session must not run")

    monkeypatch.setattr("modules.intraday_memory.storage.upsert_session", _boom)
    provider = MockProvider({("BVH", DAY): [_raw_bar(f"{DAY} 09:15:00")]})
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path / "shadow",
        now_fn=lambda: _ts(f"{DAY} 09:20:45"),
        archive_root=archive,
    )
    feed.run_v2_when_cycle(sidecar_rows=[_row("BVH", "PULL VỪA")])
    assert list(archive.rglob("*")) == []
    assert not (archive / "canonical").exists()


def test_snapshot_is_not_reread_mid_sweep(tmp_path):
    rows = [_row("BVH", "PULL VỪA")]
    seen: list[str] = []

    class _Provider:
        def fetch_session(self, symbol, session_date):
            rows.append(_row("ADDED", "CP MẠNH"))
            seen.append(symbol)
            return [_raw_bar(f"{DAY} 09:15:00")]

    feed = LiveShadowFeed(
        provider=_Provider(),
        out_dir=tmp_path,
        now_fn=lambda: _ts(f"{DAY} 09:20:45"),
        archive_root=tmp_path / "archive",
    )
    feed.run_v2_when_cycle(sidecar_rows=rows)
    assert seen == ["BVH"]


def test_schedule_matches_timer_and_skips_lunch():
    clocks = live_when_fire_clocks()
    assert clocks[0] == (9, 20, 45)
    assert (11, 30, 45) in clocks
    assert (13, 5, 45) in clocks
    assert clocks[-1] == (14, 50, 45)
    assert all(not (h == 12 or (h == 11 and m > 30) or (h == 14 and m > 50)) for h, m, _s in clocks)
    text = (REPO / "deploy/systemd/mrbot-v2-live-when.timer").read_text(encoding="utf-8")
    expanded: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        if not line.startswith("OnCalendar="):
            continue
        hms = line.split()[-2] if line.endswith("Asia/Ho_Chi_Minh") else line.split("=", 1)[1].split()[-1]
        hour_s, minute_s, second_s = hms.split(":")
        for hour in hour_s.split(","):
            for minute in minute_s.split(","):
                for second in second_s.split(","):
                    expanded.append((int(hour), int(minute), int(second)))
    assert tuple(sorted(expanded)) == tuple(sorted(clocks))
    assert "mrbot-intraday-collect" not in text
    assert is_live_when_window(_ts(f"{DAY} 09:20:45")) is True
    assert is_live_when_window(_ts(f"{DAY} 12:00:00")) is False
    assert is_live_when_window(_ts(f"{DAY} 14:55:00")) is False
    assert is_live_when_window(_ts(f"{DAY} 18:40:00")) is False
    service = (REPO / "deploy/systemd/mrbot-v2-live-when.service").read_text(encoding="utf-8")
    assert "--live --v2-when" in service
    assert "intraday_memory" not in service
    assert "upsert_session" not in service


def test_outside_window_does_not_poll(tmp_path):
    provider = MockProvider({})
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=tmp_path,
        now_fn=lambda: _ts(f"{DAY} 12:10:00"),
    )
    status = feed.run_v2_when_cycle(sidecar_rows=[_row("BVH", "PULL VỪA")])
    assert status["reason"] == "OUTSIDE_LIVE_WINDOW"
    assert provider.call_count == 0


def test_replay_2026_09_23_universe_counts_only():
    """Selector replay of the audited sidecar chronology. No 5m bars."""

    def book(pull: int, manh: int, break_: int, early: int, sweet: int) -> list[dict]:
        rows = []
        n = 0
        for count, setup, source in (
            (pull, "PULL VỪA", "brain_a_scan_setup"),
            (manh, "CP MẠNH", "brain_a_scan_setup"),
            (break_, "MUA BREAK", "brain_a_scan_setup"),
            (early, "MUA EARLY", "brain_a_scan_setup"),
            (sweet, "", "market_aware_sweetspot"),
        ):
            for _ in range(count):
                n += 1
                rows.append(
                    _row(
                        f"S{n:02d}",
                        setup,
                        source=source,
                        session="2026-09-22" if source == "brain_a_scan_setup" else DAY,
                    )
                )
        return rows

    cases = [
        ("2026-09-23T06:18:43+07:00", 9, 7, 1, 29, 0, 0),
        ("2026-09-23T09:22:33+07:00", 9, 7, 1, 28, 8, 17),
        ("2026-09-23T09:42:55+07:00", 8, 8, 2, 31, 7, 18),
        ("2026-09-23T10:05:26+07:00", 11, 6, 3, 27, 7, 20),
        ("2026-09-23T10:26:28+07:00", 12, 7, 3, 30, 7, 22),
        ("2026-09-23T10:27:31+07:00", 12, 8, 3, 29, 7, 23),
        ("2026-09-23T14:12:56+07:00", 11, 6, 2, 24, 8, 19),
        ("2026-09-23T14:13:28+07:00", 11, 6, 2, 24, 8, 19),
        ("2026-09-23T14:33:17+07:00", 0, 0, 0, 0, 8, 0),
    ]
    for observed, pull, manh, break_, early, sweet, expect_fetch in cases:
        selected = select_actionable_v2(book(pull, manh, break_, early, sweet), now=_ts(observed))
        assert len(selected.fetch) == expect_fetch
        assert selected.n_actionable == pull + manh + break_
        assert len(selected.fetch) <= LIVE_UNIVERSE_CAP
        assert len(selected.fetch) * (60.0 / GUEST_RPM) < 300
    assert 17 <= 23 <= LIVE_UNIVERSE_CAP


def _rollover_nom(setup: str = "PULL VỪA", *, symbol: str = "BVH"):
    """Scan date D, first_seen after D cash close, eligible at D+1 09:15."""
    kwargs = dict(
        symbol=symbol,
        session="2026-09-22",
        first="2026-09-22T15:22:00+07:00",
        eligible="2026-09-23T09:15:00+07:00",
        ema9=27.1,
        market="OK",
    )
    if setup == "MUA BREAK":
        kwargs.update(ema9=None, breakout=27.0, ref="BREAKOUT_REF")
    return _nom(setup, **kwargs)


def _pull_pair(day: str, hms=("09:15", "09:20")):
    return [
        _bar(hms[0], day=day, close_vs_ref=20, vol_state="CONTRACTION"),
        _bar(hms[1], day=day, close_vs_ref=40, vol_state="NORMAL"),
    ]


def _manh_pair(day: str):
    return [
        _bar(
            "09:15",
            day=day,
            close_vs_ref=50,
            published="NEUTRAL",
            vol_state="EXPANSION",
            pxv="CONFIRMING",
        ),
        _bar(
            "09:20",
            day=day,
            close_vs_ref=80,
            published=EV_STRENGTHEN,
            vol_state="EXPANSION",
            pxv="CONFIRMING",
        ),
    ]


def _break_pair(day: str):
    return [
        _bar(
            "09:15",
            day=day,
            close_vs_ref=30,
            published="NEUTRAL",
            ref_state="BREAKOUT_REF",
            ref_kind="BREAKOUT_REF",
        ),
        _bar(
            "09:20",
            day=day,
            close_vs_ref=60,
            published=EV_STRENGTHEN,
            ref_state="BREAKOUT_REF",
            ref_kind="BREAKOUT_REF",
        ),
    ]


def test_rollover_pull_uses_eligible_from_trading_date():
    nom = _rollover_nom("PULL VỪA")
    assert nom.session == "2026-09-22"
    assert evaluation_trading_session(nom) == "2026-09-23"
    prior = evaluate_shadow_action(
        nom,
        _pull_pair("2026-09-22", ("14:30", "14:40")),
    )
    assert prior.action_state != STATE_BUY_READY
    assert prior.n_legal_bars == 0
    before_open = evaluate_shadow_action(
        nom,
        [_bar("09:10", day=DAY, close_vs_ref=20, vol_state="NORMAL")],
    )
    assert before_open.action_state != STATE_BUY_READY
    assert REASON_CHRONOLOGY_PRE_ELIGIBLE in before_open.notes
    unfinished = evaluate_shadow_action(
        nom,
        [_bar("09:20", day=DAY, close_vs_ref=40, vol_state="NORMAL", unfinished=True, completed=False)],
    )
    assert unfinished.action_state != STATE_BUY_READY
    assert REASON_UNFINISHED in unfinished.notes
    ready = evaluate_shadow_action(nom, _pull_pair(DAY))
    assert ready.action_state == STATE_BUY_READY
    assert ready.action_reason == REASON_PULL_BUY_READY
    assert ready.n_legal_bars == 2
    assert ready.session == "2026-09-22"
    assert ready.candidate_is_buy is False
    assert ready.pxv_implies_buy is False
    assert ready.alert_eligible is False


def test_rollover_manh_and_break_keep_existing_confirmation():
    manh = evaluate_shadow_action(_rollover_nom("CP MẠNH"), _manh_pair(DAY))
    assert manh.action_state == STATE_BUY_READY
    assert manh.action_reason == REASON_MANH_BUY_READY
    assert manh.candidate_is_buy is False
    blocked = evaluate_shadow_action(_rollover_nom("CP MẠNH"), _manh_pair("2026-09-22"))
    assert blocked.action_state != STATE_BUY_READY
    assert blocked.n_legal_bars == 0

    brk = evaluate_shadow_action(_rollover_nom("MUA BREAK"), _break_pair(DAY))
    assert brk.action_state == STATE_BUY_READY
    assert brk.action_reason == REASON_MANH_BUY_READY
    assert brk.session == "2026-09-22"
    assert brk.pxv_implies_buy is False
    assert brk.alert_eligible is False


def test_same_day_evaluation_session_matches_provenance():
    nom = _nom(session=DAY, first=f"{DAY}T09:00:00+07:00", eligible=f"{DAY}T09:00:00+07:00")
    assert evaluation_trading_session(nom) == DAY
    assert evaluation_trading_session(nom) == nom.session
    ready = evaluate_shadow_action(nom, _pull_pair(DAY))
    assert ready.action_state == STATE_BUY_READY
    assert ready.action_reason == REASON_PULL_BUY_READY
    next_day = evaluate_shadow_action(nom, _pull_pair("2026-09-24"))
    assert next_day.action_state != STATE_BUY_READY
    assert REASON_SESSION_RESET in next_day.notes
    assert next_day.n_legal_bars == 0


def test_rollover_does_not_accept_other_sessions():
    nom = _rollover_nom()
    older = evaluate_shadow_action(nom, _pull_pair("2026-09-21", ("10:00", "10:05")))
    assert older.n_legal_bars == 0
    assert older.action_state != STATE_BUY_READY
    scan_day = evaluate_shadow_action(nom, _pull_pair("2026-09-22", ("10:00", "10:05")))
    assert scan_day.n_legal_bars == 0
    future = evaluate_shadow_action(nom, _pull_pair("2026-09-24"))
    assert future.n_legal_bars == 0
    assert REASON_SESSION_RESET in future.notes
    unfinished = evaluate_shadow_action(
        nom,
        [
            *_pull_pair(DAY),
            _bar("09:25", day=DAY, close_vs_ref=40, vol_state="NORMAL", unfinished=True, completed=False),
        ],
    )
    assert unfinished.action_state == STATE_BUY_READY
    assert unfinished.n_legal_bars == 2
    assert REASON_UNFINISHED in unfinished.notes


def test_rollover_live_buy_ready_is_retained_when_symbol_leaves(tmp_path):
    clock = {"now": _ts(f"{DAY} 09:30:45")}
    provider = MockProvider({("BVH", DAY): _quiet_bars()})
    feed = _feed(tmp_path, provider, clock["now"])
    feed.now_fn = lambda: clock["now"]
    row = _row(
        "BVH",
        "PULL VỪA",
        session="2026-09-22",
        first="2026-09-22T15:22:00+07:00",
        eligible=f"{DAY}T09:15:00+07:00",
        ema9=27.0,
        breakout=28.0,
    )
    feed.run_v2_when_cycle(sidecar_rows=[row])
    state = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert state["rows"][0]["shadow_action"] == STATE_BUY_READY
    assert state["rows"][0]["session"] == "2026-09-22"
    assert state["rows"][0]["candidate_is_buy"] is False
    assert state["rows"][0]["pxv_implies_buy"] is False
    assert state["rows"][0]["alert_eligible"] is False
    trigger = state["rows"][0]["trigger_bar_ts"]
    price = state["rows"][0]["trigger_price"]

    clock["now"] = _ts(f"{DAY} 09:35:45")
    sweet = _row("AGR", "", source="market_aware_sweetspot", session=DAY)
    status = feed.run_v2_when_cycle(sidecar_rows=[sweet])
    current = json.loads((tmp_path / "v2_action" / "v2_action_state.json").read_text(encoding="utf-8"))
    assert status["published_empty"] is True
    assert current["rows"] == []
    kept = current["historical_buy_ready"][0]
    assert kept["symbol"] == "BVH"
    assert kept["shadow_action"] == STATE_BUY_READY
    assert kept["trigger_bar_ts"] == trigger
    assert kept["trigger_price"] == price
    assert kept["source"] == "brain_a_scan_setup"
    assert kept["setup"] == "PULL VỪA"
    assert kept["session"] == "2026-09-22"
    assert kept["candidate_is_buy"] is False
    assert kept["pxv_implies_buy"] is False
    assert kept["alert_eligible"] is False


def test_post_close_selector_still_drops_scan_date_rows():
    row = _row("BVH", "PULL VỪA", session="2026-09-22", eligible=f"{DAY}T09:15:00+07:00")
    assert current_session_v2_rows([row], DAY) == []
    kept, _ = document_rows_for_live_when(_doc([row]), session=DAY)
    assert kept[0]["session"] == "2026-09-22"


def test_state_machine_module_was_not_rewritten_for_live_when():
    source = (REPO / "modules/live_candidate_v2_action/state.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "evaluate_shadow_action" for node in tree.body
    )
    assert "ACTIONABLE_LIVE_SETUPS" not in source
    assert "classify_stale_ignoring_lunch" not in source
