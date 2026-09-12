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
    ):
        src = (REPO / rel).read_text(encoding="utf-8")
        assert "yfinance" not in src
        assert "fetch_live_price" not in src
        assert "stock_historical_data" not in src
