"""LIVE uses production generate_signal and cannot become a sealed snapshot."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from position_guardian import SIGNAL_HOLD, SIGNAL_SELL, SIGNAL_WARNING, generate_signal, row_color
from research.guardian_research.contract import GENERATE_SIGNAL_SHA256, PRODUCTION_TO_RESEARCH
from research.guardian_research.live import evaluate_live, live_board
from research.guardian_research.panel import (
    CLASS_STYLE,
    LIVE_ROW_STYLE,
    _style_live_board,
    render_guardian_research_panel,
)
from research.guardian_research.snapshot import SnapshotExists, build_snapshot, read_snapshot, write_snapshot
from research.guardian_research.universe import load_tracked_symbols

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = "2026-11-10"
WHEN = datetime(2026, 11, 10, 10, 15, tzinfo=VN)


def _frame(rows):
    return pd.DataFrame(rows)


def _row(symbol, price, ema9, ma20, obv, obv_ema9, day=SESSION):
    return {
        "symbol": symbol,
        "date": day,
        "price": price,
        "ema9": ema9,
        "ma20": ma20,
        "obv": obv,
        "obv_ema9": obv_ema9,
    }


def _contrast_ratio(background: str, foreground: str) -> float:
    def channel(value: str) -> float:
        number = int(value, 16) / 255
        if number <= 0.04045:
            return number / 12.92
        return ((number + 0.055) / 1.055) ** 2.4

    def luminance(color: str) -> float:
        hex_color = color.lstrip("#")
        red, green, blue = (channel(hex_color[index:index + 2]) for index in (0, 2, 4))
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    light = max(luminance(background), luminance(foreground))
    dark = min(luminance(background), luminance(foreground))
    return (light + 0.05) / (dark + 0.05)


def _styled_rule(css: str, row: int, col: int) -> str:
    compact = re.sub(r"\s+", "", css).lower()
    rule = re.search(rf"(?:^|[^0-9])row{row}_col{col}(?![0-9])[^{{]*\{{([^}}]+)\}}", compact)
    assert rule is not None
    return rule.group(1)


def _declaration(rule: str, prop: str) -> str:
    match = re.search(rf"(?:^|{{|;){prop}:([^;}}]+)", rule)
    assert match is not None
    return match.group(1)


def _assert_live_contrast(board: pd.DataFrame, css: str) -> None:
    expected = {
        "HOLD": ("#ddffdd", "#1b4332"),
        "WATCH": ("#fff2cc", "#7f6000"),
        "SELL": ("#c8102e", "#ffffff"),
        "UNAVAILABLE": ("#d9d9d9", "#333333"),
    }
    for label, (background, foreground) in expected.items():
        assert _contrast_ratio(background, foreground) >= 4.5
        assert f"background-color:{background}" in LIVE_ROW_STYLE[label].replace(" ", "").lower()
        assert f"color:{foreground}" in LIVE_ROW_STYLE[label].replace(" ", "").lower()
    for index, label in enumerate(board["Classification"]):
        background, foreground = expected[label]
        for col in range(len(board.columns)):
            rule = _styled_rule(css, index, col)
            assert _declaration(rule, "background-color") == background
            assert _declaration(rule, "color") == foreground
            assert _contrast_ratio(background, foreground) >= 4.5


def test_live_matches_generate_signal_for_each_group():
    cases = (
        ("HPG", 30, 25, 20, 100, 50),
        ("SSI", 20, 25, 20, 100, 50),
        ("VCB", 30, 22, 24, 100, 50),
        ("FPT", 30, 22, 24, 10, 50),
    )
    frame = _frame([_row(*case) for case in cases])
    live = evaluate_live(frame, symbols=tuple(case[0] for case in cases), evaluated_at=WHEN)
    assert live["schema"] == "guardian_research_live.v1"
    assert live["scan_session"] == SESSION
    assert live["evaluated_at"] == WHEN.isoformat()
    assert live["fresh_count"] == 4
    assert live["portfolio_decision"] is False
    assert live["classification_version"].endswith(GENERATE_SIGNAL_SHA256)
    by_symbol = {row["symbol"]: row for row in live["rows"]}
    for symbol, price, ema9, ma20, obv, obv_ema9 in cases:
        signal, reason, score = generate_signal(
            pd.Series({"price": price, "ema9": ema9, "ma20": ma20, "obv": obv, "obv_ema9": obv_ema9})
        )
        row = by_symbol[symbol]
        assert row["classification"] == PRODUCTION_TO_RESEARCH[signal]
        assert row["score"] == score
        assert row["reason"] == reason
        assert row["freshness"] == "FRESH"
    labels = {row["classification"] for row in live["rows"]}
    assert labels == {"HOLD", "WATCH", "SELL"}
    assert by_symbol["HPG"]["score"] == 0
    assert by_symbol["SSI"]["score"] == 40
    assert by_symbol["VCB"]["score"] == 60
    assert by_symbol["FPT"]["score"] == 80
    board = live_board(live)
    assert list(board["Classification"]) == ["HOLD", "WATCH", "SELL", "SELL"]


def test_live_marks_missing_and_stale_rows_and_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = _frame(
        [
            _row("HPG", 30, 25, 20, 100, 50, day="2026-11-10"),
            _row("SSI", 20, 25, 20, 100, 50, day="2026-11-06"),
            {"symbol": "VCB", "date": SESSION, "price": None, "ema9": 1, "ma20": 1, "obv": 1, "obv_ema9": 1},
        ]
    )
    live = evaluate_live(frame, symbols=("HPG", "SSI", "VCB", "FPT"), evaluated_at=WHEN)
    by_symbol = {row["symbol"]: row for row in live["rows"]}
    assert live["mixed_session"] is True
    assert live["scan_session"] is None
    assert by_symbol["HPG"]["freshness"] == "STALE"
    assert by_symbol["HPG"]["classification"] == "HOLD"
    assert by_symbol["SSI"]["freshness"] == "STALE"
    vcb_signal, vcb_reason, vcb_score = generate_signal(
        pd.Series({"price": None, "ema9": 1, "ma20": 1, "obv": 1, "obv_ema9": 1})
    )
    assert by_symbol["VCB"]["classification"] == PRODUCTION_TO_RESEARCH[vcb_signal]
    assert by_symbol["VCB"]["reason"] == vcb_reason
    assert by_symbol["VCB"]["score"] == vcb_score
    assert by_symbol["VCB"]["freshness"] == "STALE"
    assert by_symbol["VCB"]["live_adjusted"] is False
    assert by_symbol["VCB"]["quote_observed_at"] is None
    assert by_symbol["FPT"]["freshness"] == "MISSING"
    assert by_symbol["FPT"]["reason"] == "SYMBOL_ABSENT"
    assert list(tmp_path.rglob("*.json")) == []
    source = Path(__file__).resolve().parents[1].joinpath("research", "guardian_research", "live.py").read_text(encoding="utf-8")
    assert "write_snapshot" not in source
    assert "sessions" not in source


def test_live_uses_the_same_scan_row_as_position_guardian(tmp_path: Path):
    """A previous daily bar with a real quote still follows generate_signal."""
    row = _row("hpg", 20, 25, 20, 100, 50, day="2026-11-09")
    row["is_live_adjusted"] = True
    row["live_ts"] = "2026-11-10 10:00:00+07:00"
    row["live_source"] = "YF_15M"
    before = Path("data/guardian_research/sessions/2026-11-06.json").read_bytes()
    live = evaluate_live(_frame([row]), symbols=("HPG", "FPT"), evaluated_at=WHEN)
    signal, reason, score = generate_signal(pd.Series(row))
    got = next(item for item in live["rows"] if item["symbol"] == "HPG")
    assert got["classification"] == PRODUCTION_TO_RESEARCH[signal] == "WATCH"
    assert got["reason"] == reason
    assert got["score"] == score
    assert got["production_signal"] == signal
    assert got["input_session"] == "2026-11-09"
    assert got["live_adjusted"] is True
    assert got["quote_observed_at"] == "2026-11-10 10:00:00+07:00"
    assert live["scan_session"] == "2026-11-09"
    assert live["live_adjusted_count"] == 1
    assert live["quoted_count"] == 1
    assert live["evaluated_at"] == WHEN.isoformat()
    absent = next(item for item in live["rows"] if item["symbol"] == "FPT")
    assert absent["classification"] == "UNAVAILABLE"
    assert absent["quote_observed_at"] is None
    board = live_board(live)
    assert list(board["Classification"]) == ["WATCH", "UNAVAILABLE"]
    assert list(board["Symbol"]) == ["HPG", "FPT"]
    assert board.loc[board["Symbol"] == "HPG", "Quote"].iloc[0] == "2026-11-10 10:00:00+07:00"
    assert board.loc[board["Symbol"] == "FPT", "Quote"].iloc[0] == ""
    assert Path("data/guardian_research/sessions/2026-11-06.json").read_bytes() == before
    assert list(tmp_path.rglob("*.json")) == []


def test_live_row_color_covers_the_whole_row_and_keeps_grouping():
    hold = _row("HPG", 30, 25, 20, 100, 50)
    watch = _row("SSI", 20, 25, 20, 100, 50)
    sell = _row("FPT", 30, 22, 24, 10, 50)
    daily = _row("VCB", 30, 25, 20, 100, 50)
    daily["is_live_adjusted"] = False
    frame = _frame([sell, hold, watch, daily])
    live = evaluate_live(frame, symbols=("FPT", "HPG", "SSI", "VCB", "ACV"), evaluated_at=WHEN)
    board = live_board(live)
    assert list(board["Classification"]) == ["HOLD", "HOLD", "WATCH", "SELL", "UNAVAILABLE"]
    assert list(board["Symbol"]) == ["HPG", "VCB", "SSI", "FPT", "ACV"]
    assert list(board.columns) == [
        "Classification",
        "Symbol",
        "Price",
        "Score",
        "Freshness",
        "Live",
        "Quote",
        "Reason",
        "Input session",
    ]
    assert board.loc[board["Symbol"] == "VCB", "Live"].iloc[0] == ""
    assert board.loc[board["Symbol"] == "VCB", "Quote"].iloc[0] == ""
    assert board.loc[board["Symbol"] == "ACV", "Quote"].iloc[0] == ""
    hold_bg = row_color(pd.Series({"Trạng thái": SIGNAL_HOLD}))[0].replace(" ", "")
    watch_bg = row_color(pd.Series({"Trạng thái": SIGNAL_WARNING}))[0].replace(" ", "")
    sell_bg = row_color(pd.Series({"Trạng thái": SIGNAL_SELL}))[0].replace(" ", "")
    assert hold_bg == "background-color:#ddffdd"
    assert watch_bg == "background-color:#fff6cc"
    assert sell_bg == "background-color:#ffd9d9"
    assert LIVE_ROW_STYLE["HOLD"].replace(" ", "").startswith(hold_bg)
    assert LIVE_ROW_STYLE["WATCH"] == CLASS_STYLE["WATCH"]
    assert "background-color:#fff2cc" in LIVE_ROW_STYLE["WATCH"].replace(" ", "")
    assert sell_bg not in LIVE_ROW_STYLE["SELL"].replace(" ", "")
    assert "#f4cccc" not in LIVE_ROW_STYLE["SELL"]
    assert CLASS_STYLE == {
        "HOLD": "background-color:#d9ead3;color:#1b4332;font-weight:700",
        "WATCH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
        "SELL": "background-color:#f4cccc;color:#990000;font-weight:700",
        "UNAVAILABLE": "background-color:#d9d9d9;color:#333333;font-weight:700",
    }
    styled = _style_live_board(board)
    pd.testing.assert_frame_equal(styled.data, board)
    _assert_live_contrast(board, styled.to_html().split("</style>", 1)[0])
    from streamlit.elements.lib.pandas_styler_utils import marshall_styler
    from streamlit.proto.ArrowData_pb2 import ArrowData

    proto = ArrowData()
    marshall_styler(proto, styled, "live")
    _assert_live_contrast(board, proto.styler.styles)


def test_live_colors_keep_the_143_symbol_fixture(tmp_path: Path):
    """Styling reads the sealed scan inputs and does not rewrite them."""
    source = Path("data/guardian_research/sessions/2026-11-06.json")
    before = source.read_bytes()
    document = json.loads(before)
    tracked = load_tracked_symbols()
    by_symbol = {row["symbol"]: row for row in document["rows"]}
    assert document["tracked_count"] == 143
    assert len(by_symbol) == 143
    assert set(by_symbol) == set(tracked)
    frame = _frame(
        [
            {
                "symbol": symbol,
                "date": by_symbol[symbol]["freshness"]["input_session"],
                "price": by_symbol[symbol]["inputs"]["price"],
                "ema9": by_symbol[symbol]["inputs"]["ema9"],
                "ma20": by_symbol[symbol]["inputs"]["ma20"],
                "obv": by_symbol[symbol]["inputs"]["obv"],
                "obv_ema9": by_symbol[symbol]["inputs"]["obv_ema9"],
            }
            for symbol in tracked
        ]
    )
    live = evaluate_live(frame, symbols=tracked, evaluated_at=WHEN)
    board = live_board(live)
    expected_symbols = [
        symbol
        for label in ("HOLD", "WATCH", "SELL", "UNAVAILABLE")
        for symbol in tracked
        if by_symbol[symbol]["classification"] == label
    ]
    assert list(board["Symbol"]) == expected_symbols
    assert list(board["Classification"]) == [by_symbol[symbol]["classification"] for symbol in expected_symbols]
    assert [int(score) for score in board["Score"]] == [int(by_symbol[symbol]["score"]) for symbol in expected_symbols]
    assert list(board["Reason"]) == [by_symbol[symbol]["reason"] for symbol in expected_symbols]
    assert list(board["Price"]) == [by_symbol[symbol]["inputs"]["price"] for symbol in expected_symbols]
    ranks = {"HOLD": 0, "WATCH": 1, "SELL": 2, "UNAVAILABLE": 3}
    order = [ranks[label] for label in board["Classification"]]
    assert order == sorted(order)
    assert list(dict.fromkeys(board["Classification"])) == ["HOLD", "WATCH", "SELL"]
    assert [int((board["Classification"] == label).sum()) for label in ("HOLD", "WATCH", "SELL", "UNAVAILABLE")] == [57, 8, 78, 0]
    styled = _style_live_board(board)
    pd.testing.assert_frame_equal(styled.data, board)
    _assert_live_contrast(board, styled.to_html().split("</style>", 1)[0])
    from streamlit.elements.lib.pandas_styler_utils import marshall_styler
    from streamlit.proto.ArrowData_pb2 import ArrowData

    proto = ArrowData()
    marshall_styler(proto, styled, "fixture")
    _assert_live_contrast(board, proto.styler.styles)
    assert source.read_bytes() == before
    assert list(tmp_path.rglob("*.json")) == []


def test_shipped_snapshot_cannot_be_overwritten(tmp_path: Path):
    source = Path("data/guardian_research/sessions/2026-11-06.json")
    before = source.read_bytes()
    original = read_snapshot(source)
    assert original["session"] == "2026-11-06"
    assert original["observation_origin"] == "CONTEMPORANEOUS"
    assert original["tracked_count"] == 143
    assert len(original["rows"]) == 143
    (tmp_path / "sessions").mkdir()
    stored = tmp_path / "sessions" / "2026-11-06.json"
    stored.write_bytes(before)
    replacement = build_snapshot("2026-11-06", observations={}, symbols=("HPG",))
    try:
        write_snapshot(tmp_path, replacement)
    except SnapshotExists:
        refused = True
    else:
        refused = False
    assert refused
    assert stored.read_bytes() == before
    assert source.read_bytes() == before
    reread = json.loads(source.read_text(encoding="utf-8"))
    assert reread["content_sha256"] == original["content_sha256"]


def test_panel_keeps_live_apart_from_the_sealed_session(tmp_path: Path, monkeypatch):
    from research.guardian_research.pipeline import capture_from_close_payload

    payload = {
        "ok": True,
        "status": "READY",
        "source": "close_scan",
        "trade_date": "2026-11-06",
        "market_real": 6.5,
        "trading_today": True,
        "trading_reason": "VNINDEX có giao dịch hôm nay: 2026-11-06",
        "observed_at": "2026-11-06T19:05:00+07:00",
        "scan_df": _frame([_row("HPG", 30, 25, 20, 100, 50, day="2026-11-06")]),
        "scan_coverage": {"requested": ["HPG"], "returned": ["HPG"], "absent": [], "errors": []},
    }
    sealed = capture_from_close_payload(
        payload,
        now=datetime(2026, 11, 6, 19, 30, tzinfo=VN),
        root=tmp_path,
        symbols=("HPG",),
    )
    assert sealed["status"] == "created"
    before = Path(sealed["path"]).read_bytes()
    import streamlit as st

    headings = []
    expanders = []
    metrics = []
    monkeypatch.setattr(st, "markdown", lambda text, **_kwargs: headings.append(str(text)))
    monkeypatch.setattr(st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(st, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(st, "dataframe", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(st, "expander", lambda label, **kwargs: expanders.append((str(label), kwargs.get("expanded"))) or _Expander())
    monkeypatch.setattr(st, "columns", lambda count: [_Metric(metrics) for _ in range(count)])
    shown = render_guardian_research_panel(
        _frame([_row("HPG", 20, 25, 20, 100, 50)]),
        99,
        WHEN,
        root=tmp_path,
    )
    assert shown["session"] == "2026-11-06"
    assert shown["rows"][0]["classification"] == "HOLD"
    assert headings[1] == "## 🟢 GUARDIAN RESEARCH LIVE"
    assert not any(heading.startswith("## 🛡️") for heading in headings)
    assert expanders == [("Sealed T0 snapshot 2026-11-06 — not the live board", False)]
    assert metrics[:4] == [("HOLD", 0), ("WATCH", 1), ("SELL", 0), ("UNAVAILABLE", 142)]
    assert ("HOLD", 1) in metrics[4:]
    assert Path(sealed["path"]).read_bytes() == before
    assert list(tmp_path.joinpath("sessions").glob("*.json")) == [Path(sealed["path"])]


def test_guardian_research_section_follows_position_guardian():
    app = Path("app.py").read_text(encoding="utf-8")
    panel = Path("research/guardian_research/panel.py").read_text(encoding="utf-8")
    guardian = app.index("render_guardian(")
    research = app.index("render_guardian_research_panel(")
    market = app.index("# MARKET FIRST", guardian)
    assert app.count("render_guardian(") == 1
    assert app.count("render_guardian_research_panel(") == 1
    assert guardian < research < market
    assert "render_earning_money_board(" not in app[guardian:research]
    body = panel[panel.index("def render_guardian_research_panel"):panel.index("def _render_live")]
    assert body.index("_render_live(") < body.index("_render_sealed(") < body.index("_render_outcomes(")
    sealed = panel[panel.index("def _render_sealed"):panel.index("def _count_classes")]
    assert "_render_forward(" in sealed


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Metric:
    def __init__(self, sink=None):
        self._sink = sink

    def metric(self, label, value, *_args, **_kwargs):
        if self._sink is not None:
            self._sink.append((str(label), int(value)))
        return None
