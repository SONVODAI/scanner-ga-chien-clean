"""Last BUY READY is history. Current state and suggested action stay live."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from modules.rotation_watch.constants import (
    ACT_BUY_READY,
    ACT_RISK,
    ACT_WAIT,
    ACT_WATCH_LOWER,
    SCHEMA_STATE,
    ST_BUY_READY,
    ST_LOWER_ZONE,
    ST_RISK,
    ST_WATCH,
)
from modules.rotation_watch.engine import _decide_state, build_board
from modules.rotation_watch.html import render_html
from modules.rotation_watch.runner import run_cycle
from modules.rotation_watch.state import apply_transitions, load_state
from modules.rotation_watch.view import build_panel, display_table, format_last_buy_ready

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = date(2026, 8, 14)
STAMP_EXAMPLE = "2026-09-17T13:15:00+07:00"


def _ts(hm: str, day: date = SESSION) -> datetime:
    h, m = hm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=VN)


def _bar(symbol: str, hm: str, o: float, h: float, l: float, c: float, v: int, day: date) -> dict:
    return {"time": _ts(hm, day), "open": o, "high": h, "low": l, "close": c, "volume": v}


def _fill_session(
    symbol: str,
    end_hm: str,
    *,
    day: date = SESSION,
    price: float = 11.70,
    volume: int = 1000,
    last: list[tuple[float, float, float, float, int]] | None = None,
) -> list[dict]:
    start = _ts("09:15", day)
    end = _ts(end_hm, day)
    slots: list[str] = []
    cur = start
    while cur <= end:
        clock = cur.timetz().replace(tzinfo=None)
        if clock <= datetime.strptime("11:30", "%H:%M").time() or clock >= datetime.strptime("13:00", "%H:%M").time():
            slots.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=5)
        if cur.strftime("%H:%M") == "11:35":
            cur = _ts("13:00", day)
    override = last or []
    n_keep = len(slots) - len(override)
    rows = []
    for i, hm in enumerate(slots):
        if i >= n_keep:
            o, h, l, c, v = override[i - n_keep]
            rows.append(_bar(symbol, hm, o, h, l, c, v, day))
        else:
            rows.append(_bar(symbol, hm, price, price + 0.02, price - 0.02, price, volume, day))
    return rows


def _strengthen(symbol: str, end_hm: str, *, day: date = SESSION, close: float = 11.86) -> list[dict]:
    prev = round(close - 0.08, 2)
    return _fill_session(
        symbol,
        end_hm,
        day=day,
        last=[
            (11.68, 11.80, 11.66, prev, 2800),
            (prev, close + 0.02, prev - 0.02, close, 3000),
        ],
    )


def _watchlist(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,,,\n",
        encoding="utf-8",
    )
    return path


def _board(tmp_path: Path, records: list[dict], now: datetime):
    return build_board(
        now=now,
        watchlist_path=_watchlist(tmp_path / "watchlist.csv"),
        injected={"TCH": records},
        persist=True,
        state_path=tmp_path / "state.json",
    )


def _saved(tmp_path: Path) -> dict:
    return load_state(tmp_path / "state.json")["symbols"]["TCH"]


def _row(**kwargs) -> SimpleNamespace:
    data = {
        "symbol": "TCH",
        "rotation_state": ST_WATCH,
        "current_price": None,
        "location": "",
        "published_pxv": "",
        "pxv_why": "",
        "published_why": "",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_buy_logic_table_is_unchanged():
    assert (
        _decide_state(
            location="LOWER",
            published="STRENGTHEN",
            has_position=False,
            hold_above=False,
        )
        == ST_BUY_READY
    )
    assert (
        _decide_state(
            location="LOWER",
            published="NEUTRAL",
            has_position=False,
            hold_above=False,
        )
        == ST_LOWER_ZONE
    )
    assert (
        _decide_state(
            location="BELOW_LOWER",
            published="STRENGTHEN",
            has_position=False,
            hold_above=False,
        )
        == ST_WATCH
    )


def test_lower_buy_ready_then_lower_keeps_timestamp(tmp_path):
    lower = _board(tmp_path, _fill_session("TCH", "10:35"), _ts("10:40"))
    assert lower.rows[0].rotation_state == ST_LOWER_ZONE
    assert "last_buy_ready" not in _saved(tmp_path)

    buy = _board(tmp_path, _strengthen("TCH", "10:40"), _ts("10:45"))
    entry = buy.rows[0]
    assert entry.rotation_state == ST_BUY_READY
    assert entry.suggested_action == ACT_BUY_READY
    stored = entry.last_buy_ready
    assert stored["symbol"] == "TCH"
    assert stored["last_buy_ready_at"] == _ts("10:45").isoformat()
    assert stored["price"] == entry.current_price
    assert stored["location"] == "LOWER"
    assert stored["published_pxv"] == "STRENGTHEN"
    assert stored["reason"]
    assert stored["reason"] in {entry.pxv_why, entry.published_why}

    left = _board(tmp_path, _fill_session("TCH", "10:45"), _ts("10:50"))
    row = left.rows[0]
    assert row.rotation_state == ST_LOWER_ZONE
    assert row.suggested_action == ACT_WATCH_LOWER
    assert row.last_buy_ready["last_buy_ready_at"] == stored["last_buy_ready_at"]
    assert row.last_buy_ready["price"] == stored["price"]
    assert row.last_buy_ready["reason"] == stored["reason"]
    assert load_state(tmp_path / "state.json")["schema"] == SCHEMA_STATE

    panel = build_panel(now=_ts("10:50"), sources=left.as_dict())
    view = panel["rows"][0]
    assert view["suggested_action"] == ACT_WATCH_LOWER
    assert view["last_session_state"] == ST_LOWER_ZONE
    assert format_last_buy_ready(view) == "Last BUY READY: 2026-08-14 10:45"
    assert display_table(panel).loc[0, "History"] == "Last BUY READY: 2026-08-14 10:45"
    assert display_table(panel).loc[0, "Suggested Action"] == ACT_WATCH_LOWER
    html = render_html(panel)
    assert '<td class="history">Last BUY READY: 2026-08-14 10:45</td>' in html
    assert '<th>History</th>' in html
    assert "<th>Last BUY READY</th>" not in html
    assert 'class="BUY_READY"' not in html
    assert ">BUY READY<" not in html


def test_newer_buy_ready_replaces_older(tmp_path):
    _board(tmp_path, _fill_session("TCH", "10:35"), _ts("10:40"))
    first = _board(tmp_path, _strengthen("TCH", "10:40"), _ts("10:45"))
    first_at = first.rows[0].last_buy_ready["last_buy_ready_at"]
    _board(tmp_path, _fill_session("TCH", "10:45"), _ts("10:50"))
    second = _board(tmp_path, _strengthen("TCH", "10:50", close=11.80), _ts("10:55"))
    saved = second.rows[0].last_buy_ready
    assert saved["last_buy_ready_at"] == _ts("10:55").isoformat()
    assert saved["last_buy_ready_at"] != first_at
    assert saved["price"] == second.rows[0].current_price
    assert second.rows[0].rotation_state == ST_BUY_READY


def test_staying_in_buy_ready_does_not_refresh_timestamp(tmp_path):
    _board(tmp_path, _fill_session("TCH", "10:35"), _ts("10:40"))
    first = _board(tmp_path, _strengthen("TCH", "10:40"), _ts("10:45"))
    stamp = first.rows[0].last_buy_ready["last_buy_ready_at"]
    price = first.rows[0].last_buy_ready["price"]
    stayed = _board(tmp_path, _strengthen("TCH", "10:45", close=11.80), _ts("10:50"))
    assert stayed.rows[0].rotation_state == ST_BUY_READY
    assert stayed.rows[0].last_buy_ready["last_buy_ready_at"] == stamp
    assert stayed.rows[0].last_buy_ready["price"] == price


def test_symbol_that_never_entered_buy_ready_has_empty_history(tmp_path):
    board = _board(tmp_path, _fill_session("TCH", "10:35"), _ts("10:40"))
    assert board.rows[0].rotation_state == ST_LOWER_ZONE
    assert board.rows[0].last_buy_ready == {}
    assert "last_buy_ready" not in _saved(tmp_path)
    panel = build_panel(now=_ts("10:40"), sources=board.as_dict())
    assert format_last_buy_ready(panel["rows"][0]) == ""
    assert display_table(panel).loc[0, "History"] == ""
    html = render_html(panel)
    assert "BUY READY" not in html
    assert "<th>History</th>" in html


def test_wait_risk_watch_do_not_create_last_buy_ready(tmp_path):
    below = _board(tmp_path, _fill_session("TCH", "10:35", price=11.50), _ts("10:40"))
    assert below.rows[0].rotation_state == ST_WATCH
    assert below.rows[0].suggested_action == ACT_WAIT
    risk = _board(
        tmp_path,
        _fill_session(
            "TCH",
            "10:40",
            last=[
                (11.82, 11.84, 11.68, 11.70, 2800),
                (11.70, 11.72, 11.62, 11.64, 3200),
            ],
        ),
        _ts("10:45"),
    )
    assert risk.rows[0].rotation_state == ST_RISK
    assert risk.rows[0].suggested_action == ACT_RISK
    middle = _board(tmp_path, _fill_session("TCH", "10:45", price=12.00), _ts("10:50"))
    assert middle.rows[0].rotation_state == ST_WATCH
    assert middle.rows[0].suggested_action == ACT_WAIT
    assert "last_buy_ready" not in _saved(tmp_path)
    assert format_last_buy_ready(middle.rows[0].as_dict()) == ""


def test_reload_keeps_last_buy_ready(tmp_path):
    watch = _watchlist(tmp_path / "watchlist.csv")
    state = tmp_path / "state.json"
    common = {
        "watchlist_path": watch,
        "board_path": tmp_path / "board.json",
        "status_path": tmp_path / "status.json",
        "state_path": state,
    }
    run_cycle(now=_ts("10:40"), injected={"TCH": _fill_session("TCH", "10:35")}, **common)
    run_cycle(now=_ts("10:45"), injected={"TCH": _strengthen("TCH", "10:40")}, **common)
    run_cycle(now=_ts("10:50"), injected={"TCH": _fill_session("TCH", "10:45")}, **common)
    stamp = _saved(tmp_path)["last_buy_ready"]["last_buy_ready_at"]
    assert stamp == _ts("10:45").isoformat()

    reloaded = load_state(state)
    assert reloaded["schema"] == SCHEMA_STATE
    assert reloaded["symbols"]["TCH"]["current_state"] == ST_LOWER_ZONE
    assert reloaded["symbols"]["TCH"]["last_buy_ready"]["last_buy_ready_at"] == stamp

    run_cycle(now=_ts("10:55"), injected={"TCH": _fill_session("TCH", "10:50")}, **common)
    assert _saved(tmp_path)["current_state"] == ST_LOWER_ZONE
    assert _saved(tmp_path)["last_buy_ready"]["last_buy_ready_at"] == stamp
    board = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    art = board["rows"][0]
    assert art["last_session_state"] == ST_LOWER_ZONE
    assert art["suggested_action"] == ACT_WATCH_LOWER
    assert art["last_buy_ready"]["last_buy_ready_at"] == stamp


def test_new_day_and_weekend_keep_last_buy_ready(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA_STATE,
                "updated_at": STAMP_EXAMPLE,
                "symbols": {
                    "TCH": {
                        "previous_state": ST_LOWER_ZONE,
                        "current_state": ST_BUY_READY,
                        "first_entered_at": STAMP_EXAMPLE,
                        "latest_transition_at": STAMP_EXAMPLE,
                        "transitions": [
                            {
                                "from": ST_LOWER_ZONE,
                                "to": ST_BUY_READY,
                                "at": STAMP_EXAMPLE,
                                "alert_worthy": True,
                            }
                        ],
                        "last_buy_ready": {
                            "symbol": "TCH",
                            "last_buy_ready_at": STAMP_EXAMPLE,
                            "price": 11.86,
                            "location": "LOWER",
                            "published_pxv": "STRENGTHEN",
                            "reason": "captured on the entry cycle",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    friday = date(2026, 9, 18)
    friday_now = _ts("10:40", friday)
    left = _board(tmp_path, _fill_session("TCH", "10:35", day=friday), friday_now)
    assert left.rows[0].rotation_state == ST_LOWER_ZONE
    assert left.rows[0].suggested_action == ACT_WATCH_LOWER
    assert left.rows[0].last_buy_ready["last_buy_ready_at"] == STAMP_EXAMPLE
    assert left.rows[0].last_buy_ready["price"] == 11.86

    closed = build_panel(now=_ts("15:00", friday), sources=left.as_dict())
    assert closed["rows"][0]["suggested_action"] == ACT_WAIT
    assert closed["rows"][0]["last_session_state"] == ST_LOWER_ZONE
    assert format_last_buy_ready(closed["rows"][0]) == "Last BUY READY: 2026-09-17 13:15"
    html = render_html(closed)
    assert '<td class="history">Last BUY READY: 2026-09-17 13:15</td>' in html
    assert 'class="BUY_READY"' not in html
    assert ">BUY READY<" not in html

    saturday = _board(
        tmp_path,
        _fill_session("TCH", "10:35", day=friday),
        datetime(2026, 9, 19, 10, 0, tzinfo=VN),
    )
    assert saturday.rows[0].last_buy_ready["last_buy_ready_at"] == STAMP_EXAMPLE
    assert _saved(tmp_path)["last_buy_ready"]["reason"] == "captured on the entry cycle"


def test_backfill_uses_latest_retained_transition_timestamp_only(tmp_path):
    older = "2026-08-14T09:30:00+07:00"
    newer = "2026-08-14T10:45:00+07:00"
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA_STATE,
                "symbols": {
                    "TCH": {
                        "previous_state": ST_BUY_READY,
                        "current_state": ST_LOWER_ZONE,
                        "first_entered_at": newer,
                        "latest_transition_at": "2026-08-14T10:50:00+07:00",
                        "transitions": [
                            {"from": ST_WATCH, "to": ST_BUY_READY, "at": older, "alert_worthy": True},
                            {"from": ST_LOWER_ZONE, "to": ST_BUY_READY, "at": newer, "alert_worthy": True},
                            {
                                "from": ST_BUY_READY,
                                "to": ST_LOWER_ZONE,
                                "at": "2026-08-14T10:50:00+07:00",
                                "alert_worthy": False,
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    apply_transitions([_row(rotation_state=ST_LOWER_ZONE)], now=_ts("10:55"), path=state_path)
    saved = load_state(state_path)["symbols"]["TCH"]["last_buy_ready"]
    assert saved == {"symbol": "TCH", "last_buy_ready_at": newer}
    assert "price" not in saved
    assert "location" not in saved
    assert "published_pxv" not in saved
    assert "reason" not in saved


def test_dropped_transitions_are_not_invented(tmp_path):
    transitions = [
        {
            "from": ST_WATCH,
            "to": ST_RISK,
            "at": f"2026-08-14T09:{i:02d}:00+07:00",
            "alert_worthy": False,
        }
        for i in range(50)
    ]
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA_STATE,
                "symbols": {
                    "TCH": {
                        "current_state": ST_RISK,
                        "previous_state": ST_WATCH,
                        "first_entered_at": transitions[-1]["at"],
                        "latest_transition_at": transitions[-1]["at"],
                        "transitions": transitions,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    apply_transitions([_row(rotation_state=ST_WATCH)], now=_ts("10:40"), path=state_path)
    saved = load_state(state_path)["symbols"]["TCH"]
    assert "last_buy_ready" not in saved
    assert len(saved["transitions"]) == 50


def test_transition_cap_does_not_delete_stored_history(tmp_path):
    stamp = "2026-08-14T09:20:00+07:00"
    transitions = [
        {
            "from": ST_WATCH,
            "to": ST_LOWER_ZONE,
            "at": f"2026-08-13T09:{i:02d}:00+07:00",
            "alert_worthy": False,
        }
        for i in range(50)
    ]
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA_STATE,
                "symbols": {
                    "TCH": {
                        "current_state": ST_LOWER_ZONE,
                        "previous_state": ST_WATCH,
                        "first_entered_at": stamp,
                        "latest_transition_at": stamp,
                        "transitions": transitions,
                        "last_buy_ready": {"symbol": "TCH", "last_buy_ready_at": stamp},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    apply_transitions([_row(rotation_state=ST_WATCH)], now=_ts("10:40"), path=state_path)
    saved = load_state(state_path)["symbols"]["TCH"]
    assert len(saved["transitions"]) == 50
    assert all(item["to"] != ST_BUY_READY for item in saved["transitions"])
    assert saved["last_buy_ready"] == {"symbol": "TCH", "last_buy_ready_at": stamp}


def test_entry_omits_fields_the_cycle_does_not_have(tmp_path):
    state_path = tmp_path / "state.json"
    apply_transitions(
        [
            _row(
                rotation_state=ST_BUY_READY,
                current_price=None,
                location="",
                published_pxv="",
                pxv_why="",
                published_why="published only",
            )
        ],
        now=_ts("10:45"),
        path=state_path,
    )
    saved = load_state(state_path)["symbols"]["TCH"]["last_buy_ready"]
    assert saved["symbol"] == "TCH"
    assert saved["last_buy_ready_at"] == _ts("10:45").isoformat()
    assert saved["reason"] == "published only"
    assert "price" not in saved
    assert "location" not in saved
    assert "published_pxv" not in saved


def test_history_caption_is_not_the_current_action():
    from modules.rotation_watch.render import render_rotation_watch_panel

    class _CM:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _FakeSt:
        def __init__(self, checkbox_force=None):
            self.expanders: list[str] = []
            self.captions: list[str] = []
            self.tables: list[object] = []
            self.checkbox_force = checkbox_force

        def expander(self, title, **kwargs):
            self.expanders.append(str(title))
            return _CM()

        def columns(self, n):
            return [_CM() for _ in range(int(n))]

        def checkbox(self, label, value=False, **kwargs):
            if self.checkbox_force is None:
                return bool(value)
            return bool(self.checkbox_force)

        def caption(self, msg, **kwargs):
            self.captions.append(str(msg))

        def metric(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def dataframe(self, data, **kwargs):
            self.tables.append(data)

        def markdown(self, *args, **kwargs):
            return None

        def write(self, *args, **kwargs):
            return None

    row = {
        "symbol": "TCH",
        "current_price": 11.7,
        "location": "LOWER",
        "lower_zone": "11.60–11.90",
        "upper_zone": "12.20–12.40",
        "range_position_pct": 12.5,
        "last_session_state": ST_LOWER_ZONE,
        "last_session_action": ACT_WATCH_LOWER,
        "suggested_action": ACT_WATCH_LOWER,
        "rotation_state": ST_LOWER_ZONE,
        "raw_pxv": "NEUTRAL",
        "published_pxv": "NEUTRAL",
        "pxv_why": "flat",
        "last_bar_ts": "2026-09-18T10:35:00+07:00",
        "freshness": "LIVE",
        "rotation_evidence": ["in lower zone"],
        "actionable": True,
        "last_buy_ready": {
            "symbol": "TCH",
            "last_buy_ready_at": STAMP_EXAMPLE,
        },
    }
    board = {
        "empty": False,
        "observed_at": "2026-09-18T10:40:00+07:00",
        "session_phase": "LIVE",
        "rows": [row],
    }
    hidden = _FakeSt()
    render_rotation_watch_panel(board=board, st_module=hidden)
    assert hidden.expanders == ["🔄 ROTATION WATCH"]
    assert hidden.tables[0].loc[0, "History"] == "Last BUY READY: 2026-09-17 13:15"
    assert hidden.tables[0].loc[0, "Suggested Action"] == ACT_WATCH_LOWER
    assert hidden.tables[0].loc[0, "Last-session State"] == ST_LOWER_ZONE
    assert not any(cap.startswith("Last BUY READY:") for cap in hidden.captions)

    shown = _FakeSt(checkbox_force=True)
    render_rotation_watch_panel(board=board, st_module=shown)
    assert "TCH · last LOWER_ZONE · now WATCH LOWER" in shown.expanders
    assert "Last BUY READY: 2026-09-17 13:15" in shown.captions
    assert not any("now BUY READY" in title for title in shown.expanders)
