"""User-owned holdings store. Isolated from Rotation / Camera / Edge / Learning."""

from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.user_holdings import (
    load_holdings_text,
    persist_if_changed,
    save_holdings_text,
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
    assert "persist_if_changed" in src
    assert "render_holdings_editor" in src
    assert "value=load_portfolio()" not in src
    assert "HOLDINGS_WIDGET_KEY" in src


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
