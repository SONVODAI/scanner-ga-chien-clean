"""Isolated Rotation Watch V1. No Candidate eligibility, no Edge/Learning writes."""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.intraday_pxv_v1.constants import ACTIONABLE_CONCLUSIONS
from modules.rotation_watch.config import load_watchlist
from modules.rotation_watch.constants import (
    ACT_BUY_READY,
    ACT_HOLD,
    ACT_RISK,
    ACT_SELL_READY,
    ACT_TREND_HOLD,
    ACT_WATCH_LOWER,
    ST_BUY_READY,
    ST_DATA_UNCERTAIN,
    ST_HOLD,
    ST_LOWER_ZONE,
    ST_RISK,
    ST_SELL_READY,
    ST_TREND_HOLD,
    ST_WATCH,
)
from modules.rotation_watch.engine import build_board
from modules.rotation_watch.html import render_html
from modules.rotation_watch.state import default_state_path

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
SESSION = date(2026, 8, 14)

FORBIDDEN_ROTATION_IMPORTS = (
    "eligible_watchlist_symbols",
    "build_research_watchlist",
    "interpret_candidate_session",
    "load_candidate_events",
    "modules.edge_research",
    "modules.learning_insight",
    "modules.learning_t0_capture",
    "live_evidence.jsonl",
    "ACTIONABLE_CONCLUSIONS",
)

PRODUCTION_HASH_PATHS = (
    "modules/edge_research/engine.py",
    "modules/edge_research/ui.py",
    "modules/learning_insight_candidates.py",
    "modules/live_candidate/watchlist.py",
    "modules/intraday_memory/collector.py",
    "decision_engine.py",
    "learning_engine.py",
)


def _ts(hm: str, day: date = SESSION) -> datetime:
    h, m = hm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=VN)


def _bar(symbol: str, hm: str, o: float, h: float, l: float, c: float, v: int) -> dict:
    return {
        "time": _ts(hm),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


def _session_slots(end_hm: str) -> list[str]:
    start = _ts("09:15")
    end = _ts(end_hm)
    out = []
    cur = start
    while cur <= end:
        clock = cur.timetz().replace(tzinfo=None)
        if clock <= datetime.strptime("11:30", "%H:%M").time() or clock >= datetime.strptime("13:00", "%H:%M").time():
            out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=5)
        if cur.strftime("%H:%M") == "11:35":
            cur = _ts("13:00")
    return out


def _fill_session(
    symbol: str,
    end_hm: str,
    *,
    price: float = 11.70,
    volume: int = 1000,
    last: list[tuple[float, float, float, float, int]] | None = None,
) -> list[dict]:
    slots = _session_slots(end_hm)
    override = last or []
    n_keep = len(slots) - len(override)
    rows = []
    for i, hm in enumerate(slots):
        if i >= n_keep:
            o, h, l, c, v = override[i - n_keep]
            rows.append(_bar(symbol, hm, o, h, l, c, v))
        else:
            rows.append(_bar(symbol, hm, price, price + 0.02, price - 0.02, price, volume))
    return rows


def _write_watchlist(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _board(tmp_path: Path, records: list[dict], now: datetime, csv: str | None = None, persist: bool = False, **kwargs):
    watch = _write_watchlist(
        tmp_path / "watchlist.csv",
        csv
        or "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        'TCH,true,11.60,11.90,12.20,12.40,,,"manual rotation watch"\n',
    )
    return build_board(
        now=now,
        watchlist_path=watch,
        injected={"TCH": records},
        persist=persist,
        state_path=tmp_path / "state.json",
        **kwargs,
    )


def test_tch_appears_when_candidate_watchlist_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_LIVE_CANDIDATE_OUT", str(tmp_path / "empty_candidates"))
    (tmp_path / "empty_candidates").mkdir()
    (tmp_path / "empty_candidates" / "dynamic_watchlist.json").write_text("[]", encoding="utf-8")
    recs = _fill_session(
        "TCH",
        "10:35",
        last=[
            (11.68, 11.80, 11.66, 11.78, 2800),
            (11.78, 11.88, 11.76, 11.86, 3000),
        ],
    )
    board = _board(tmp_path, recs, _ts("10:40"))
    assert not board.empty
    assert board.rows[0].symbol == "TCH"
    assert board.rows[0].rotation_state == ST_BUY_READY
    html = render_html(board)
    assert "TCH" in html
    assert "BUY_READY" in html
    assert "data-candidate-required=\"false\"" in html


def test_lower_strengthen_is_buy_ready(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        last=[
            (11.68, 11.80, 11.66, 11.78, 2800),
            (11.78, 11.88, 11.76, 11.86, 3000),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.published_pxv == "STRENGTHEN"
    assert row.rotation_state == ST_BUY_READY
    assert row.suggested_action == ACT_BUY_READY
    assert any("LOWER" in e or "lower" in e for e in row.rotation_evidence)
    assert "STRENGTHEN" in " ".join(row.rotation_evidence)
    assert row.pxv_why


def test_lower_neutral_is_watch_lower_not_buy(tmp_path):
    recs = _fill_session("TCH", "10:35", price=11.70, volume=1000)
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.published_pxv in {"NEUTRAL", "CONFLICT"}
    assert row.rotation_state == ST_LOWER_ZONE
    assert row.suggested_action == ACT_WATCH_LOWER
    assert row.rotation_state != ST_BUY_READY


def test_lower_weaken_is_risk(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        last=[
            (11.82, 11.84, 11.68, 11.70, 2800),
            (11.70, 11.72, 11.62, 11.64, 3200),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.published_pxv == "WEAKEN"
    assert row.rotation_state == ST_RISK
    assert row.suggested_action == ACT_RISK


def test_upper_weaken_is_sell_ready(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        price=12.25,
        last=[
            (12.32, 12.34, 12.22, 12.24, 2800),
            (12.24, 12.26, 12.20, 12.21, 3000),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert 12.20 <= row.current_price <= 12.40
    assert row.published_pxv == "WEAKEN"
    assert row.rotation_state == ST_SELL_READY
    assert row.suggested_action == ACT_SELL_READY


def test_upper_strengthen_with_position_is_hold(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        price=12.25,
        last=[
            (12.22, 12.32, 12.20, 12.30, 2800),
            (12.30, 12.38, 12.28, 12.36, 3000),
        ],
    )
    csv = (
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,12.00,2026-08-12,manual\n"
    )
    row = _board(tmp_path, recs, _ts("10:40"), csv=csv).rows[0]
    assert row.published_pxv == "STRENGTHEN"
    assert row.has_position
    assert row.rotation_state == ST_HOLD
    assert row.suggested_action == ACT_HOLD


def test_first_bar_above_upper_is_not_trend_hold(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        price=12.30,
        last=[
            (12.30, 12.38, 12.28, 12.36, 2800),
            (12.36, 12.55, 12.34, 12.52, 3200),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.current_price > 12.40
    assert row.published_pxv == "STRENGTHEN"
    assert row.rotation_state != ST_TREND_HOLD
    assert any("not confirmed" in e.lower() or "first completed" in e.lower() for e in row.rotation_evidence)


def test_two_closes_above_upper_and_strengthen_is_trend_hold(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        price=12.30,
        last=[
            (12.42, 12.55, 12.40, 12.52, 2800),
            (12.52, 12.62, 12.50, 12.60, 3200),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.current_price > 12.40
    assert row.published_pxv == "STRENGTHEN"
    assert row.rotation_state == ST_TREND_HOLD
    assert row.suggested_action == ACT_TREND_HOLD
    assert any("two completed closes" in e for e in row.rotation_evidence)


def test_stale_and_missing_and_wrong_session_never_buy_or_sell(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        last=[
            (11.68, 11.80, 11.66, 11.78, 2800),
            (11.78, 11.88, 11.76, 11.86, 3000),
        ],
    )
    stale = _board(tmp_path, recs, _ts("11:05")).rows[0]
    assert stale.freshness == "STALE"
    assert stale.rotation_state == ST_DATA_UNCERTAIN
    assert stale.rotation_state not in {ST_BUY_READY, ST_SELL_READY}

    missing = _board(tmp_path, [], _ts("10:40")).rows[0]
    assert missing.rotation_state == ST_DATA_UNCERTAIN
    assert missing.freshness in {"MISSING", "PROVIDER_ERROR", "INVALID"}

    friday = date(2026, 8, 14)
    monday = date(2026, 8, 17)
    recs_fri = _fill_session("TCH", "10:35")
    board = build_board(
        now=datetime(monday.year, monday.month, monday.day, 10, 40, tzinfo=VN),
        watchlist_path=_write_watchlist(
            tmp_path / "wl2.csv",
            "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
            "TCH,true,11.60,11.90,12.20,12.40,,,\n",
        ),
        injected={"TCH": recs_fri},
        persist=False,
    )
    # injected Friday bars are rejected against Monday expected session
    assert board.rows[0].rotation_state == ST_DATA_UNCERTAIN
    assert board.rows[0].rotation_state not in {ST_BUY_READY, ST_SELL_READY}
    del friday


def test_t25_profit_is_never_mechanical_sell(tmp_path):
    recs = _fill_session("TCH", "10:35", price=12.00, volume=1000)
    csv = (
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,11.70,2026-08-12,manual\n"
    )
    row = _board(tmp_path, recs, _ts("10:40"), csv=csv).rows[0]
    assert row.has_position
    assert row.pnl_pct is not None and row.pnl_pct > 0
    assert row.location == "MIDDLE" or (row.current_price and 11.90 < row.current_price < 12.20)
    assert row.rotation_state == ST_HOLD
    assert row.suggested_action == ACT_HOLD
    assert row.rotation_state != ST_SELL_READY
    assert "T+" in row.t25_checkpoint
    assert "not a mechanical sell" in row.t25_checkpoint


def test_csv_disable_remove_and_zone_edit_need_no_python_change(tmp_path):
    recs = _fill_session("TCH", "10:35", price=11.70)
    now = _ts("10:40")
    base = (
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,,,\n"
    )
    assert _board(tmp_path, recs, now, csv=base).rows[0].lower_zone.startswith("11.60")

    disabled = base.replace("TCH,true", "TCH,false")
    board = _board(tmp_path, recs, now, csv=disabled)
    assert board.empty or all(r.symbol != "TCH" for r in board.rows)

    removed = "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
    board = _board(tmp_path, recs, now, csv=removed)
    assert board.empty

    edited = (
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,10.00,10.40,11.00,11.20,,,\n"
    )
    row = _board(tmp_path, recs, now, csv=edited).rows[0]
    assert row.lower_zone.startswith("10.00")
    assert row.upper_zone.startswith("11.00")


def test_actionable_states_include_pxv_and_zone_evidence(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        last=[
            (11.68, 11.80, 11.66, 11.78, 2800),
            (11.78, 11.88, 11.76, 11.86, 3000),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    blob = " ".join(row.rotation_evidence) + " " + row.pxv_why
    assert row.rotation_state == ST_BUY_READY
    assert "STRENGTHEN" in blob
    assert "lower" in blob.lower() or "LOWER" in blob
    assert row.pxv_why


def test_persist_only_under_rotation_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_ROTATION_WATCH_DIR", str(tmp_path / "rotation"))
    recs = _fill_session("TCH", "10:35", price=11.70)
    watch = _write_watchlist(
        tmp_path / "rotation" / "watchlist.csv",
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,,,\n",
    )
    board = build_board(
        now=_ts("10:40"),
        watchlist_path=watch,
        injected={"TCH": recs},
        persist=True,
    )
    state = default_state_path()
    assert state.exists()
    assert "rotation" in str(state)
    text = state.read_text(encoding="utf-8")
    assert "TCH" in text
    assert "current_state" in text
    assert state.parent == tmp_path / "rotation"
    del board


def test_rotation_modules_do_not_import_candidate_eligibility():
    root = REPO / "modules" / "rotation_watch"
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [f"{node.module}.{a.name}" if node.module else a.name for a in node.names]
                if node.module:
                    names.append(node.module)
            else:
                continue
            blob = " ".join(names)
            for banned in FORBIDDEN_ROTATION_IMPORTS:
                assert banned not in blob, f"{path.name} imports {banned}"


def test_actionable_conclusions_unchanged():
    assert ACTIONABLE_CONCLUSIONS == frozenset({"BUY ELITE", "MUA NHỎ / ƯU TIÊN"})


def test_app_hook_isolated_and_production_titles_remain():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "render_rotation_watch_panel" in app
    render_src = Path(
        inspect.getfile(__import__("modules.rotation_watch.render", fromlist=["render_rotation_watch_panel"]))
    ).read_text(encoding="utf-8")
    assert "🔄 ROTATION WATCH" in render_src
    start = app.index("ROTATION WATCH — isolated")
    chunk = app[start : start + 400]
    assert "except Exception" in chunk
    for title in (
        "👑 BUY ELITE - DECISION ENGINE",
        "LIVE CANDIDATE × P×V",
        "render_live_candidate_pxv_panel",
        "render_edge_research_panel",
    ):
        assert title in app


def test_production_semantic_files_unchanged_vs_main():
    """Candidate / Edge / Learning / BUY ELITE engines were not edited this branch."""
    import subprocess

    changed = subprocess.check_output(
        ["git", "diff", "main", "--name-only", "--", *PRODUCTION_HASH_PATHS],
        cwd=REPO,
        text=True,
    ).strip()
    assert changed == "", f"production files unexpectedly changed:\n{changed}"


def test_range_position_can_exceed_100(tmp_path):
    recs = _fill_session(
        "TCH",
        "10:35",
        price=12.30,
        last=[
            (12.42, 12.55, 12.40, 12.52, 2800),
            (12.52, 12.62, 12.50, 12.60, 3200),
        ],
    )
    row = _board(tmp_path, recs, _ts("10:40")).rows[0]
    assert row.range_position_pct is not None
    assert row.range_position_pct > 100


def test_load_repo_watchlist_has_only_tch():
    rows = load_watchlist(REPO / "data" / "rotation_watch" / "watchlist.csv")
    assert [r.symbol for r in rows] == ["TCH"]
    assert rows[0].note == "manual rotation watch"
