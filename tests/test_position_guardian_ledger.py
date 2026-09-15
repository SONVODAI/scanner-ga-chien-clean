"""Guardian presentation joins the user ledger. generate_signal must stay identical."""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]

# Frozen SHA-256 of generate_signal() as of origin/main before this ledger change.
GENERATE_SIGNAL_SHA256 = (
    "ee644fc098fc01c6c4a4f54bedcefe892e1beb26b085552f3c7a9929b4c5dd4f"
)


def _extract_generate_signal(src: str) -> str:
    match = re.search(
        r"def generate_signal\(row\):.*?(?=\n# =+\n# SELL SCORE COLOR)",
        src,
        re.S,
    )
    assert match, "generate_signal not found"
    return match.group(0)


def test_generate_signal_source_is_unchanged():
    src = (REPO / "position_guardian.py").read_text(encoding="utf-8")
    body = _extract_generate_signal(src)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == GENERATE_SIGNAL_SHA256
    assert "cut-loss" not in body.lower()
    assert "3%" not in body
    assert "profit" not in body.lower()
    assert "entry_price" not in body
    assert "holding_days" not in body
    assert "pnl" not in body.lower()


def test_generate_signal_rules_are_identical():
    pg = _import_position_guardian()
    hold = pd.Series(
        {"price": 26.0, "ema9": 25.0, "ma20": 24.0, "obv": 1000, "obv_ema9": 900}
    )
    warn = pd.Series(
        {"price": 24.0, "ema9": 25.0, "ma20": 24.0, "obv": 1000, "obv_ema9": 900}
    )
    sell = pd.Series(
        {"price": 24.0, "ema9": 23.0, "ma20": 24.0, "obv": 1100, "obv_ema9": 900}
    )
    sell_obv = pd.Series(
        {"price": 24.0, "ema9": 23.0, "ma20": 24.0, "obv": 800, "obv_ema9": 900}
    )

    assert pg.generate_signal(hold) == (pg.SIGNAL_HOLD, "Xu hướng khỏe", 0)
    assert pg.generate_signal(warn) == (pg.SIGNAL_WARNING, "Giá dưới EMA9", 40)
    assert pg.generate_signal(sell) == (pg.SIGNAL_SELL, "EMA9 dưới MA20", 60)
    assert pg.generate_signal(sell_obv) == (
        pg.SIGNAL_SELL,
        "EMA9 dưới MA20 + OBV xác nhận",
        80,
    )


def _stub_streamlit():
    if "streamlit" in sys.modules:
        return
    st = ModuleType("streamlit")

    def _noop(*_a, **_k):
        return None

    class _Col:
        def metric(self, *_a, **_k):
            return None

    class _Columns:
        TextColumn = staticmethod(lambda *_a, **_k: None)
        NumberColumn = staticmethod(lambda *_a, **_k: None)
        DateColumn = staticmethod(lambda *_a, **_k: None)

    st.markdown = _noop
    st.subheader = _noop
    st.caption = _noop
    st.button = lambda *_a, **_k: False
    st.success = _noop
    st.info = _noop
    st.dataframe = _noop
    st.columns = lambda n: [_Col() for _ in range(n)]
    st.session_state = {}
    st.secrets = {}
    st.column_config = _Columns()
    st.data_editor = lambda frame, **_k: frame
    sys.modules["streamlit"] = st


def _import_position_guardian():
    _stub_streamlit()
    sys.path.insert(0, str(REPO))
    import position_guardian as pg

    return pg


def test_build_position_table_joins_ledger_and_does_not_drop_unscanned():
    pg = _import_position_guardian()
    positions = [
        {"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"},
        {"symbol": "ZZZOUTSIDE", "entry_price": 10.0, "entry_date": "2026-09-10"},
        {"symbol": "PVD", "entry_price": None, "entry_date": None},
    ]
    scan_df = pd.DataFrame(
        [
            {
                "symbol": "SSI",
                "price": 26.95,
                "ema9": 26.0,
                "ma20": 25.0,
                "obv": 1_200_000,
                "obv_ema9": 1_000_000,
            },
            {
                "symbol": "PVD",
                "price": 24.0,
                "ema9": 25.0,
                "ma20": 24.5,
                "obv": 800,
                "obv_ema9": 900,
            },
        ]
    )
    table = pg.build_position_table(scan_df, positions, today=date(2026, 9, 14))
    assert list(table["Mã"]) == ["SSI", "ZZZOUTSIDE", "PVD"]
    ssi = table.iloc[0]
    assert ssi["Giá vốn"] == "24.50"
    assert ssi["Ngày mua"] == "2026-09-01"
    assert ssi["Giá hiện tại"] == "26.95"
    assert ssi["P/L %"] == "10.00%"
    assert ssi["Số ngày giữ"] == "13"
    assert ssi["EMA9"] == "26.00"
    assert ssi["MA20"] == "25.00"
    assert "1,200,000" in str(ssi["OBV"]).replace(",", ",")
    assert ssi["Trạng thái"] == pg.SIGNAL_HOLD
    assert ssi["Lý do"] == "Xu hướng khỏe"

    outside = table.iloc[1]
    assert outside["Giá vốn"] == "10.00"
    assert outside["Ngày mua"] == "2026-09-10"
    assert outside["Giá hiện tại"] == pg.MISSING
    assert outside["P/L %"] == pg.MISSING
    assert outside["Số ngày giữ"] == "4"
    assert outside["EMA9"] == pg.MISSING
    assert outside["MA20"] == pg.MISSING
    assert outside["OBV"] == pg.MISSING
    assert outside["Sell Score"] == pg.MISSING
    assert outside["Trạng thái"] == pg.MISSING
    assert outside["Lý do"] == pg.MISSING

    pvd = table.iloc[2]
    assert pvd["Giá vốn"] == pg.MISSING
    assert pvd["Ngày mua"] == pg.MISSING
    assert pvd["P/L %"] == pg.MISSING
    assert pvd["Số ngày giữ"] == pg.MISSING
    assert pvd["Trạng thái"] == pg.SIGNAL_WARNING


def test_missing_cost_and_date_are_emdash_not_zero():
    pg = _import_position_guardian()
    positions = [{"symbol": "SSI", "entry_price": None, "entry_date": None}]
    scan_df = pd.DataFrame(
        [
            {
                "symbol": "SSI",
                "price": 26.0,
                "ema9": 25.0,
                "ma20": 24.0,
                "obv": 1,
                "obv_ema9": 1,
            }
        ]
    )
    table = pg.build_position_table(scan_df, positions, today=date(2026, 9, 14))
    row = table.iloc[0]
    assert row["Giá vốn"] == pg.MISSING
    assert row["Ngày mua"] == pg.MISSING
    assert row["P/L %"] == pg.MISSING
    assert row["Số ngày giữ"] == pg.MISSING
    assert "0.00%" not in str(row["P/L %"])
    assert str(row["Số ngày giữ"]) != "0"


def test_pnl_and_holding_days_formulas():
    from modules.user_holdings import holding_days, pnl_pct

    assert pnl_pct(26.95, 24.5) == pytest.approx(10.0)
    assert pnl_pct(24.5, 24.5) == pytest.approx(0.0)
    assert pnl_pct(None, 24.5) is None
    assert pnl_pct(26.95, None) is None
    assert pnl_pct(26.95, 0) is None
    # 2026-09-15 production units: integer VND, not thousands.
    assert pnl_pct(19100, 18800) == pytest.approx(1.5957446808510638)
    assert pnl_pct(70300, 72500) == pytest.approx(-3.0344827586206895)
    assert holding_days("2026-09-01", today=date(2026, 9, 14)) == 13
    assert holding_days(None, today=date(2026, 9, 14)) is None
    assert holding_days("", today=date(2026, 9, 14)) is None


def test_pvd_mwg_unit_normalized_pnl_display():
    pg = _import_position_guardian()
    from modules.user_holdings import pnl_pct

    assert pg.fmt_pnl(pnl_pct(19100, 18800)) == "1.60%"
    assert pg.fmt_pnl(pnl_pct(70300, 72500)) == "-3.03%"
    table = pg.build_position_table(
        pd.DataFrame(
            [
                {
                    "symbol": "PVD",
                    "price": 19100,
                    "ema9": 19000,
                    "ma20": 18500,
                    "obv": 1,
                    "obv_ema9": 1,
                },
                {
                    "symbol": "MWG",
                    "price": 70300,
                    "ema9": 70000,
                    "ma20": 71000,
                    "obv": 800,
                    "obv_ema9": 900,
                },
            ]
        ),
        [
            {"symbol": "PVD", "entry_price": 18800.0, "entry_date": "2026-09-08"},
            {"symbol": "MWG", "entry_price": 72500.0, "entry_date": "2026-09-08"},
        ],
        today=date(2026, 9, 15),
    )
    assert list(table["Mã"]) == ["PVD", "MWG"]
    assert table.iloc[0]["Giá vốn"] == "18,800.00"
    assert table.iloc[0]["Giá hiện tại"] == "19,100.00"
    assert table.iloc[0]["P/L %"] == "1.60%"
    assert table.iloc[0]["Số ngày giữ"] == "7"
    assert table.iloc[1]["Giá vốn"] == "72,500.00"
    assert table.iloc[1]["Giá hiện tại"] == "70,300.00"
    assert table.iloc[1]["P/L %"] == "-3.03%"
    assert table.iloc[1]["Trạng thái"] == pg.SIGNAL_SELL
    assert table.iloc[1]["Lý do"] == "EMA9 dưới MA20 + OBV xác nhận"


def test_empty_portfolio_renders_safely(tmp_path, monkeypatch):
    from modules.user_holdings import save_positions

    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    monkeypatch.setattr("modules.user_holdings.LEGACY_LOCAL_PATH", tmp_path / "legacy.txt")
    save_positions([], github_writer=lambda _t: "LOCAL_ONLY")
    pg = _import_position_guardian()
    infos = []
    import streamlit as st

    st.info = lambda *a, **_k: infos.append(a[0] if a else "")
    pg.render_guardian(pd.DataFrame(), include_editor=False)
    assert infos == ["Chưa có cổ phiếu đang nắm giữ."]


def test_guardian_table_failure_does_not_raise(tmp_path, monkeypatch):
    from modules.user_holdings import save_positions

    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    monkeypatch.setattr("modules.user_holdings.LEGACY_LOCAL_PATH", tmp_path / "legacy.txt")
    save_positions(
        [{"symbol": "PVD", "entry_price": 18800.0, "entry_date": "2026-09-08"}],
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    pg = _import_position_guardian()
    captions = []
    import streamlit as st

    st.caption = lambda *a, **_k: captions.append(a[0] if a else "")
    monkeypatch.setattr(
        pg,
        "build_position_table",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("table boom")),
    )
    pg.render_guardian(
        pd.DataFrame([{"symbol": "PVD", "price": 19100, "ema9": 1, "ma20": 1, "obv": 1, "obv_ema9": 1}]),
        include_editor=False,
    )
    assert any("Guardian table skipped" in str(c) for c in captions)


def test_unmatched_row_color_is_not_hold_green():
    pg = _import_position_guardian()
    colors = pg.row_color(pd.Series({"Trạng thái": pg.MISSING, "Mã": "ZZZ"}))
    assert colors[0] == "background-color:#f3f4f6"


def test_editor_does_not_fetch_market_or_run_scan():
    src = (REPO / "position_guardian.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "render_holdings_editor":
            fn = ast.get_source_segment(src, node)
            break
    assert fn is not None
    blob = fn.lower()
    assert "run_scan" not in blob
    assert "yfinance" not in blob
    assert "yahoo" not in blob
    assert "kbs" not in blob
    assert "analyze_symbol" not in blob
    assert "build_indicators" not in blob
    assert "st.data_editor" in fn
    assert "commit_editor_positions" in fn
    assert "parse_editor_frame" in fn
    assert "DateColumn" not in fn
    assert "DD/MM/YYYY" in fn


def test_guardian_table_stays_after_scan_and_editor_below_rotation():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    rot = app.index("render_rotation_watch_panel()")
    scan = app.index("scan_df = run_scan(WATCHLIST)")
    table = app.index("render_guardian(")
    market = app.index("# MARKET FIRST", table)
    learning = app.rindex("render_bot_learning_insight()")
    assert rot < scan < table < market < learning
    assert app.count("render_guardian(") == 1
    between_rot_scan = app[rot:scan]
    assert "render_guardian" not in between_rot_scan
    assert "render_holdings_editor()" not in between_rot_scan
    after_market = app[market:]
    assert "render_guardian(" not in after_market


def test_date_column_uses_dd_mm_yyyy_user_format():
    src = (REPO / "position_guardian.py").read_text(encoding="utf-8")
    pg = _import_position_guardian()
    assert pg.ENTRY_DATE_COLUMN_FORMAT == "DD/MM/YYYY"
    assert "st.column_config.TextColumn" in src
    assert "st.column_config.DateColumn" not in src
    assert "Ví dụ: 10/09/2026" in src
    frame = pg._positions_to_editor_frame(
        [
            {"symbol": "PVD", "entry_price": None, "entry_date": "2026-09-10"},
            {"symbol": "SSI", "entry_price": None, "entry_date": None},
        ]
    )
    assert list(frame["Ngày mua"]) == ["10/09/2026", ""]
    assert pg.format_entry_date_display("2026-09-10") == "10/09/2026"
    assert pg.format_entry_date_display(None) == ""
    assert pg.format_entry_date_display(date(2026, 10, 9)) == "09/10/2026"


def test_iso_json_storage_remains_yyyy_mm_dd():
    from modules.user_holdings import SCHEMA, canonical_positions_text

    text = canonical_positions_text(
        [{"symbol": "PVD", "entry_price": None, "entry_date": "2026-09-10"}]
    )
    assert f'"schema": "{SCHEMA}"' in text
    assert '"entry_date": "2026-09-10"' in text
    assert "10/09/2026" not in text
    assert "09/10/2026" not in text


def test_strict_dd_mm_yyyy_parser_and_iso_roundtrip():
    pg = _import_position_guardian()
    assert pg.parse_editor_entry_date("10/09/2026") == ("2026-09-10", False)
    assert pg.parse_editor_entry_date("01/02/2026") == ("2026-02-01", False)
    assert pg.parse_editor_entry_date("") == (None, False)
    assert pg.parse_editor_entry_date(None) == (None, False)
    assert pg.parse_editor_entry_date("9/10/2026") == (None, True)
    assert pg.parse_editor_entry_date("2026-09-10") == (None, True)
    assert pg.parse_editor_entry_date("09-10-2026") == (None, True)
    assert pg.parse_editor_entry_date("10.09.2026") == (None, True)
    assert pg.parse_editor_entry_date("09/31/2026") == (None, True)
    assert pg.parse_editor_entry_date("abc") == (None, True)
    assert pg.parse_editor_entry_date("01/02/2026")[0] != "2026-01-02"


def test_invalid_editor_date_blocks_entire_save(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    pg = _import_position_guardian()
    writes = []
    frame = pd.DataFrame(
        [
            {"Mã": "SSI", "Giá vốn": 24.5, "Ngày mua": "01/09/2026"},
            {"Mã": "PVD", "Giá vốn": None, "Ngày mua": "9/10/2026"},
        ]
    )
    incoming, parse_errors = pg.parse_editor_frame(frame)
    saved, changed, status, errors = pg.commit_editor_positions(
        incoming,
        [{"symbol": "SSI", "entry_price": None, "entry_date": None}],
        today=date(2026, 9, 14),
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
        parse_errors=parse_errors,
    )
    assert changed is False
    assert status == "INVALID_DATE"
    assert errors == [
        "Ngày mua của PVD không hợp lệ. Vui lòng nhập theo DD/MM/YYYY, ví dụ 10/09/2026."
    ]
    assert writes == []
    assert not (tmp_path / "positions.json").exists()
    iso_input = pd.DataFrame(
        [{"Mã": "PVD", "Giá vốn": None, "Ngày mua": "2026-09-10"}]
    )
    _, iso_errors = pg.parse_editor_frame(iso_input)
    assert iso_errors


def test_valid_dd_mm_save_persists_iso_and_rejects_future(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    pg = _import_position_guardian()
    writes = []
    frame = pd.DataFrame(
        [{"Mã": "PVD", "Giá vốn": None, "Ngày mua": "10/09/2026"}]
    )
    incoming, parse_errors = pg.parse_editor_frame(frame)
    assert parse_errors == []
    assert incoming == [{"symbol": "PVD", "entry_price": None, "entry_date": "2026-09-10"}]
    saved, changed, status, errors = pg.commit_editor_positions(
        incoming,
        [],
        today=date(2026, 9, 14),
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
        parse_errors=parse_errors,
    )
    assert errors == []
    assert changed is True
    assert saved[0]["entry_date"] == "2026-09-10"
    assert '"entry_date": "2026-09-10"' in writes[0]
    assert "10/09/2026" not in writes[0]

    writes.clear()
    future_frame = pd.DataFrame(
        [{"Mã": "PVD", "Giá vốn": None, "Ngày mua": "09/10/2026"}]
    )
    incoming, parse_errors = pg.parse_editor_frame(future_frame)
    assert incoming[0]["entry_date"] == "2026-10-09"
    saved, changed, status, errors = pg.commit_editor_positions(
        incoming,
        [],
        today=date(2026, 9, 14),
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
        parse_errors=parse_errors,
    )
    assert changed is False
    assert status == "FUTURE_DATE"
    assert errors == [
        "Ngày mua của PVD (09/10/2026) nằm trong tương lai. Vui lòng kiểm tra lại."
    ]
    assert writes == []


def test_today_accepted_future_rejected_null_allowed():
    pg = _import_position_guardian()
    today = date(2026, 9, 14)
    assert (
        pg.future_entry_date_messages(
            [{"symbol": "SSI", "entry_price": None, "entry_date": "2026-09-14"}],
            today=today,
        )
        == []
    )
    assert (
        pg.future_entry_date_messages(
            [{"symbol": "SSI", "entry_price": None, "entry_date": None}],
            today=today,
        )
        == []
    )
    msgs = pg.future_entry_date_messages(
        [{"symbol": "PVD", "entry_price": None, "entry_date": "2026-10-09"}],
        today=today,
    )
    assert msgs == [
        "Ngày mua của PVD (09/10/2026) nằm trong tương lai. Vui lòng kiểm tra lại."
    ]


def test_future_date_blocks_entire_save_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    pg = _import_position_guardian()
    writes = []
    durable = [{"symbol": "SSI", "entry_price": None, "entry_date": None}]
    incoming = [
        {"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"},
        {"symbol": "PVD", "entry_price": None, "entry_date": "2026-10-09"},
    ]
    saved, changed, status, errors = pg.commit_editor_positions(
        incoming,
        durable,
        today=date(2026, 9, 14),
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert changed is False
    assert status == "FUTURE_DATE"
    assert errors == [
        "Ngày mua của PVD (09/10/2026) nằm trong tương lai. Vui lòng kiểm tra lại."
    ]
    assert saved == durable
    assert writes == []
    assert not (tmp_path / "positions.json").exists()


def test_today_save_persists_iso_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    pg = _import_position_guardian()
    writes = []
    saved, changed, status, errors = pg.commit_editor_positions(
        [{"symbol": "PVD", "entry_price": None, "entry_date": "2026-09-14"}],
        [],
        today=date(2026, 9, 14),
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert errors == []
    assert changed is True
    assert status == "LOCAL_ONLY"
    assert saved == [{"symbol": "PVD", "entry_price": None, "entry_date": "2026-09-14"}]
    assert '"entry_date": "2026-09-14"' in writes[0]
    assert "14/09/2026" not in writes[0]
