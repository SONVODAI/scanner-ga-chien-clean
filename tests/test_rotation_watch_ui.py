"""Read-only Rotation Watch UI. No KBS, no vnstock 4, no interpreter."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

UI_MODULES = (
    REPO / "modules" / "rotation_watch" / "render.py",
    REPO / "modules" / "rotation_watch" / "read.py",
    REPO / "modules" / "rotation_watch" / "view.py",
    REPO / "modules" / "rotation_watch" / "html.py",
    REPO / "modules" / "rotation_watch" / "artifact_get.py",
)

FORBIDDEN = (
    "KBSProvider",
    "intraday_memory.provider",
    "vnstock",
    "yfinance",
    "fetch_live_price",
    "stock_historical_data",
    "interpret_completed_bars",
    "decide_evidence",
    "evaluate_gate",
    "interpret_asof",
    "interpret_candidate_session",
    "eligible_watchlist_symbols",
    "build_research_watchlist",
    "live_evidence.jsonl",
    "modules.edge_research",
    "modules.rotation_watch.engine",
    "modules.rotation_watch.data",
    "modules.rotation_watch.pxv",
    "modules.rotation_watch.runner",
    "modules.rotation_watch.publish",
    "get_live_shadow_bytes",
    "live_evidence.jsonl",
)


def _import_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.append(mod)
            names.extend(f"{mod}.{a.name}" if mod else a.name for a in node.names)
    return names


def test_ui_modules_do_not_import_kbs_or_interpreter():
    for path in UI_MODULES:
        names = " ".join(_import_names(path))
        src = path.read_text(encoding="utf-8")
        for banned in FORBIDDEN:
            assert banned not in names, f"{path.name} imports {banned}"
            if banned in {"vnstock", "yfinance", "KBSProvider"}:
                assert banned not in src, f"{path.name} mentions {banned}"


def test_ui_package_init_does_not_load_engine():
    init = (REPO / "modules" / "rotation_watch" / "__init__.py").read_text(encoding="utf-8")
    assert "engine" not in init
    assert "KBSProvider" not in init


def test_ui_import_works_without_vnstock():
    import importlib.util

    from modules.rotation_watch.html import render_html
    from modules.rotation_watch.render import render_rotation_watch_panel
    from modules.rotation_watch.view import build_panel

    assert render_rotation_watch_panel is not None
    panel = build_panel(now=__import__("datetime").datetime(2026, 8, 14, 10, 40, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Ho_Chi_Minh")), artifact_path=Path("/tmp/no-rotation-board.json"))
    html = render_html(panel)
    assert "WAIT" in html
    assert importlib.util.find_spec("vnstock") is None


def test_no_yahoo_or_daily_fallback_in_ui_or_session():
    for rel in (
        "modules/rotation_watch/render.py",
        "modules/rotation_watch/view.py",
        "modules/rotation_watch/read.py",
        "modules/rotation_watch/session.py",
        "modules/rotation_watch/artifact_get.py",
    ):
        src = (REPO / rel).read_text(encoding="utf-8")
        assert "yfinance" not in src
        assert "fetch_live_price" not in src
        assert "stock_historical_data" not in src


def test_range_position_display_is_one_decimal_percent():
    from modules.rotation_watch.html import render_html
    from modules.rotation_watch.view import display_table, format_range_position_pct

    assert format_range_position_pct(12.500000) == "12.5%"
    assert format_range_position_pct(50) == "50.0%"
    assert format_range_position_pct(100) == "100.0%"
    assert format_range_position_pct(-15) == "-15.0%"
    assert format_range_position_pct(135) == "135.0%"
    assert format_range_position_pct(None) == ""

    raw = 12.500000
    panel = {
        "rows": [
            {
                "symbol": "TCH",
                "current_price": 11.70,
                "location": "LOWER",
                "range_position_pct": raw,
                "last_session_state": "LOWER_ZONE",
                "suggested_action": "WAIT",
            }
        ]
    }
    table = display_table(panel)
    assert table.loc[0, "Range Position %"] == "12.5%"
    html = render_html(panel)
    assert "12.5%" in html
    assert "12.500000" not in html
    assert panel["rows"][0]["range_position_pct"] == raw


class _CM:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSt:
    def __init__(self, *, checkbox_force=None):
        self.expanders: list[str] = []
        self.checkbox_calls: list[tuple[str, bool]] = []
        self.tables: list[object] = []
        self.captions: list[str] = []
        self.markdowns: list[str] = []
        self.writes: list[str] = []
        self.checkbox_force = checkbox_force

    def expander(self, title, **kwargs):
        self.expanders.append(str(title))
        return _CM()

    def columns(self, n):
        return [_CM() for _ in range(int(n))]

    def checkbox(self, label, value=False, **kwargs):
        self.checkbox_calls.append((str(label), bool(value)))
        if self.checkbox_force is None:
            return bool(value)
        return bool(self.checkbox_force)

    def caption(self, msg, **kwargs):
        self.captions.append(str(msg))

    def metric(self, *a, **kwargs):
        return None

    def warning(self, msg, **kwargs):
        return None

    def info(self, msg, **kwargs):
        return None

    def dataframe(self, data, **kwargs):
        self.tables.append(data)

    def markdown(self, msg, **kwargs):
        self.markdowns.append(str(msg))

    def write(self, msg, **kwargs):
        self.writes.append(str(msg))


def _detail_board():
    return {
        "empty": False,
        "observed_at": "2026-08-14T10:40:00+07:00",
        "session_phase": "LIVE",
        "transport": {},
        "rows": [
            {
                "symbol": "CII",
                "current_price": 12.3,
                "location": "MIDDLE",
                "lower_zone": 11.0,
                "upper_zone": 14.0,
                "range_position_pct": 40.0,
                "last_session_state": "DATA_UNCERTAIN",
                "suggested_action": "WAIT",
                "raw_pxv": "NEUTRAL",
                "published_pxv": "NEUTRAL",
                "pxv_why": "no confirming P×V",
                "last_bar_ts": "2026-08-14T10:35:00+07:00",
                "freshness": "STALE",
                "rotation_evidence": ["DATA_UNCERTAIN: stale artifact"],
                "actionable": False,
            },
            {
                "symbol": "TCH",
                "current_price": 11.7,
                "location": "LOWER",
                "lower_zone": 11.0,
                "upper_zone": 13.0,
                "range_position_pct": 12.5,
                "last_session_state": "LOWER_ZONE",
                "suggested_action": "WATCH LOWER",
                "raw_pxv": "NEUTRAL",
                "published_pxv": "NEUTRAL",
                "pxv_why": "",
                "last_bar_ts": "2026-08-14T10:35:00+07:00",
                "freshness": "LIVE",
                "rotation_evidence": ["in lower zone"],
                "actionable": True,
            },
        ],
    }


def test_show_rotation_details_defaults_off_and_skips_symbol_cards():
    from modules.rotation_watch.render import (
        DETAILS_TOGGLE_LABEL,
        render_rotation_watch_panel,
    )

    st = _FakeSt()
    panel = render_rotation_watch_panel(board=_detail_board(), st_module=st)
    assert st.checkbox_calls == [(DETAILS_TOGGLE_LABEL, False)]
    assert st.expanders == ["🔄 ROTATION WATCH"]
    assert not any(" · last " in title for title in st.expanders)
    assert st.tables
    assert list(st.tables[0]["Symbol"]) == ["CII", "TCH"]
    assert panel["rows"][0]["symbol"] == "CII"
    assert "Rotation evidence" not in st.markdowns


def test_show_rotation_details_on_renders_existing_symbol_cards():
    from modules.rotation_watch.render import (
        DETAILS_TOGGLE_LABEL,
        render_rotation_watch_panel,
    )

    st = _FakeSt(checkbox_force=True)
    render_rotation_watch_panel(board=_detail_board(), st_module=st)
    assert st.checkbox_calls == [(DETAILS_TOGGLE_LABEL, False)]
    assert st.expanders[0] == "🔄 ROTATION WATCH"
    assert "CII · last DATA_UNCERTAIN · now WAIT" in st.expanders
    assert "TCH · last LOWER_ZONE · now WATCH LOWER" in st.expanders
    assert st.tables
    assert list(st.tables[0]["Symbol"]) == ["CII", "TCH"]
    assert "**Rotation evidence**" in st.markdowns
    assert any("Raw P×V" in w for w in st.writes)


def test_details_toggle_does_not_call_build_panel_twice(monkeypatch):
    import modules.rotation_watch.render as render_mod

    calls: list[int] = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("details must reuse the already-built panel")

    monkeypatch.setattr(render_mod, "build_panel", boom)
    board = _detail_board()
    render_mod.render_rotation_watch_panel(board=board, st_module=_FakeSt())
    render_mod.render_rotation_watch_panel(
        board=board, st_module=_FakeSt(checkbox_force=True)
    )
    assert calls == []


def test_render_source_has_one_build_panel_and_gated_detail_loop():
    src = (REPO / "modules" / "rotation_watch" / "render.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "render_rotation_watch_panel":
            fn = node
            break
    assert fn is not None
    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_panel"
    ]
    assert len(calls) == 1
    assert "load_panel_sources" not in src
    assert 'st.checkbox(DETAILS_TOGGLE_LABEL, value=False)' in src
    assert "if not show_details:" in src
    loop_i = src.index("for row in panel.get(\"rows\") or []:")
    gate_i = src.index("if not show_details:")
    table_i = src.index("table = display_table(panel)")
    assert table_i < gate_i < loop_i
