"""User-owned holdings store. Isolated from Rotation / Camera / Edge / Learning."""


from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.user_holdings import (
    SCHEMA,
    canonical_positions_text,
    load_holdings_text,
    load_positions,
    persist_if_changed,
    persist_positions_if_changed,
    save_holdings_text,
    save_positions,
)

REPO = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")

FORBIDDEN_IMPORTS = (
    "modules.rotation_watch",
    "modules.edge_research",
    "modules.learning_insight",
    "modules.live_candidate",
    "modules.intraday_memory",
    "decision_engine",
    "learning_engine",
)


def _bind(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_FILE", str(tmp_path / "holdings.txt"))
    monkeypatch.setenv("MRBOT_USER_HOLDINGS_JSON", str(tmp_path / "positions.json"))
    monkeypatch.setattr(
        "modules.user_holdings.LEGACY_LOCAL_PATH",
        tmp_path / "legacy_portfolio_symbols.txt",
    )


def test_save_and_reload_without_trade_date(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    writes = []
    status = save_holdings_text(
        "SSI\nPVD\nBSR",
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert status == "LOCAL_ONLY"
    assert writes == ["SSI\nPVD\nBSR"]
    loaded = load_holdings_text(github_reader=lambda: None)
    assert loaded == "SSI\nPVD\nBSR"
    assert "trade_date" not in loaded
    assert date.today().isoformat() not in loaded


def test_day_rollover_and_new_session_do_not_clear(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    save_holdings_text("CII,TCH", github_writer=lambda _t: "LOCAL_ONLY")
    monday = datetime(2026, 9, 14, 10, 23, tzinfo=VN)
    tuesday = datetime(2026, 9, 15, 9, 40, tzinfo=VN)
    del monday, tuesday  # store is not clock-keyed
    assert load_holdings_text(github_reader=lambda: None) == "CII,TCH"


def test_explicit_edit_and_remove(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    previous, changed, _ = persist_if_changed(
        "SSI",
        "",
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    assert changed is True
    assert previous == "SSI"

    same, changed, _ = persist_if_changed(
        "SSI",
        "SSI",
        github_writer=lambda _t: (_ for _ in ()).throw(AssertionError("must not write")),
    )
    assert changed is False
    assert same == "SSI"

    cleared, changed, _ = persist_if_changed(
        "",
        "SSI",
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    assert changed is True
    assert cleared == ""
    assert load_holdings_text(github_reader=lambda: None) == ""


def test_github_wins_over_local_and_legacy(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    save_holdings_text("LOCAL_ONLY_ROW", github_writer=lambda _t: "LOCAL_ONLY")
    (tmp_path / "legacy_portfolio_symbols.txt").write_text("LEGACY", encoding="utf-8")
    loaded = load_holdings_text(github_reader=lambda: "TCH\nDXG")
    assert loaded == "TCH\nDXG"


def test_empty_github_miss_falls_back_to_local(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    save_holdings_text("NLG", github_writer=lambda _t: "LOCAL_ONLY")
    assert load_holdings_text(github_reader=lambda: None) == "NLG"


def test_holdings_editor_is_immediately_below_rotation_watch():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    rot = app.index("render_rotation_watch_panel()")
    hold = app.index("render_holdings_editor()")
    scan = app.index("run_scan(WATCHLIST)")
    table = app.index("render_guardian(")
    assert rot < hold < scan
    assert hold < table
    assert "include_editor=not st.session_state.get(HOLDINGS_EDITOR_SHOWN_KEY" in app


def test_editor_saves_only_on_change_and_does_not_bind_value():
    src = (REPO / "position_guardian.py").read_text(encoding="utf-8")
    assert "persist_positions_if_changed" in src
    assert "render_holdings_editor" in src
    assert "st.data_editor" in src
    assert "Lưu danh sách nắm giữ" in src
    assert "value=load_portfolio()" not in src
    assert "HOLDINGS_WIDGET_KEY" in src


def test_legacy_symbols_migrate_in_memory_without_writing_json(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    legacy = tmp_path / "legacy_portfolio_symbols.txt"
    legacy.write_text("SSI\nPVD\n", encoding="utf-8")
    json_path = tmp_path / "positions.json"
    loaded = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    assert loaded == [
        {"symbol": "SSI", "entry_price": None, "entry_date": None},
        {"symbol": "PVD", "entry_price": None, "entry_date": None},
    ]
    assert not json_path.exists()
    assert legacy.read_text(encoding="utf-8") == "SSI\nPVD\n"


def test_structured_json_load_save_and_nullable_fields(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    writes = []
    payload = [
        {"symbol": "ssi", "entry_price": 24.5, "entry_date": "2026-09-01"},
        {"symbol": "PVD", "entry_price": None, "entry_date": None},
    ]
    status = save_positions(payload, github_writer=lambda text: writes.append(text) or "LOCAL_ONLY")
    assert status == "LOCAL_ONLY"
    assert len(writes) == 1
    assert SCHEMA in writes[0]
    assert "current_price" not in writes[0]
    assert "Sell Score" not in writes[0]
    loaded = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: "IGNORE")
    assert loaded == [
        {"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"},
        {"symbol": "PVD", "entry_price": None, "entry_date": None},
    ]


def test_add_edit_remove_and_no_write_when_unchanged(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    writes = []
    first, changed, _ = persist_positions_if_changed(
        [{"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"}],
        [],
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert changed is True
    assert first[0]["symbol"] == "SSI"
    assert len(writes) == 1

    same, changed, status = persist_positions_if_changed(
        first,
        first,
        github_writer=lambda _t: (_ for _ in ()).throw(AssertionError("must not write")),
    )
    assert changed is False
    assert status == "UNCHANGED"
    assert same == first
    assert len(writes) == 1

    edited, changed, _ = persist_positions_if_changed(
        [
            {"symbol": "SSI", "entry_price": 25.0, "entry_date": "2026-09-02"},
            {"symbol": "TCH", "entry_price": None, "entry_date": None},
        ],
        first,
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert changed is True
    assert [p["symbol"] for p in edited] == ["SSI", "TCH"]
    assert edited[0]["entry_price"] == 25.0

    removed, changed, _ = persist_positions_if_changed(
        [{"symbol": "TCH", "entry_price": None, "entry_date": None}],
        edited,
        github_writer=lambda text: writes.append(text) or "LOCAL_ONLY",
    )
    assert changed is True
    assert [p["symbol"] for p in removed] == ["TCH"]


def test_explicit_clear_writes_empty_json_and_keeps_legacy_txt(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    legacy = tmp_path / "legacy_portfolio_symbols.txt"
    legacy.write_text("SSI,PVD", encoding="utf-8")
    previous = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    cleared, changed, _ = persist_positions_if_changed(
        [],
        previous,
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    assert changed is True
    assert cleared == []
    json_path = tmp_path / "positions.json"
    assert json_path.exists()
    text = json_path.read_text(encoding="utf-8")
    assert '"positions": []' in text
    assert legacy.read_text(encoding="utf-8") == "SSI,PVD"
    txt = tmp_path / "holdings.txt"
    if txt.exists():
        assert "{" not in txt.read_text(encoding="utf-8")


def test_first_structured_save_writes_json_not_legacy_txt(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    legacy = tmp_path / "legacy_portfolio_symbols.txt"
    legacy.write_text("SSI\nPVD\n", encoding="utf-8")
    txt = tmp_path / "holdings.txt"
    txt.write_text("SSI\nPVD\n", encoding="utf-8")
    persist_positions_if_changed(
        [{"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"}],
        load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None),
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    assert (tmp_path / "positions.json").exists()
    assert legacy.read_text(encoding="utf-8") == "SSI\nPVD\n"
    assert txt.read_text(encoding="utf-8") == "SSI\nPVD\n"
    assert SCHEMA in (tmp_path / "positions.json").read_text(encoding="utf-8")


def test_day_rollover_and_rerun_do_not_clear_positions(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    save_positions(
        [{"symbol": "CII", "entry_price": 18.2, "entry_date": "2026-09-01"}],
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    monday = date(2026, 9, 14)
    tuesday = date(2026, 9, 15)
    del monday, tuesday
    first = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    rerun = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    assert first == rerun
    assert first == [{"symbol": "CII", "entry_price": 18.2, "entry_date": "2026-09-01"}]


def test_symbol_outside_watchlist_remains_persisted(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    save_positions(
        [{"symbol": "ZZZOUTSIDE", "entry_price": 1.0, "entry_date": "2026-09-01"}],
        github_writer=lambda _t: "LOCAL_ONLY",
    )
    loaded = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    assert loaded[0]["symbol"] == "ZZZOUTSIDE"
    app_watchlist = (REPO / "app.py").read_text(encoding="utf-8")
    assert "ZZZOUTSIDE" not in app_watchlist


def test_invalid_json_falls_back_to_legacy_so_holdings_are_not_lost(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    (tmp_path / "positions.json").write_text("{not-json", encoding="utf-8")
    (tmp_path / "legacy_portfolio_symbols.txt").write_text("TCH,DXG", encoding="utf-8")
    loaded = load_positions(json_github_reader=lambda: None, legacy_github_reader=lambda: None)
    assert [p["symbol"] for p in loaded] == ["TCH", "DXG"]


def test_canonical_json_schema():
    text = canonical_positions_text(
        [{"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01", "pnl": 9}]
    )
    assert '"schema": "user_holdings.v1"' in text
    assert "pnl" not in text
    assert "current_price" not in text


def test_store_module_does_not_import_production_engines():
    src = (REPO / "modules" / "user_holdings.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    blob = " ".join(names)
    for banned in FORBIDDEN_IMPORTS:
        assert banned not in blob
        assert banned not in src


def test_rotation_camera_edge_learning_do_not_import_user_holdings():
    paths = [
        *(REPO / "modules" / "rotation_watch").glob("*.py"),
        REPO / "modules" / "intraday_memory" / "runner.py",
        REPO / "modules" / "edge_research" / "artifact_server.py",
        REPO / "decision_engine.py",
        REPO / "learning_engine.py",
    ]
    for path in paths:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        assert "user_holdings" not in src, path.name
        assert "render_holdings_editor" not in src, path.name
