"""App-level render-path regression: Edge panel must surface autonomous daily first."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.autonomous_daily_edge_ui import (
    AUTONOMOUS_DAILY_SECTION,
    HISTORICAL_CHALLENGER_SECTION,
    build_autonomous_daily_edge_ui_view,
    render_autonomous_daily_edge_text_snapshot,
)
from modules.edge_research.ui import render_edge_research_panel
from tests.test_edge_research_autonomous_daily_ui import _plant_session, _plant_stale_challenger


def test_app_py_calls_render_edge_research_panel():
    src = (REPO / "app.py").read_text(encoding="utf-8")
    assert "from modules.edge_research.ui import render_edge_research_panel" in src
    assert "render_edge_research_panel(" in src


def test_render_edge_research_panel_source_orders_autonomous_before_challenger():
    src = inspect.getsource(render_edge_research_panel)
    auto_render_idx = src.index("render_autonomous_daily_edge_block")
    hist_heading_idx = src.index('f"### {HISTORICAL_CHALLENGER_SECTION')
    challenger_voice_idx = src.index("Challenger candidate voice (historical)")
    assert auto_render_idx < hist_heading_idx < challenger_voice_idx
    assert 'expander("Research Voice"' not in src
    # Opening the panel must not itself call discovery/challenger run helpers
    # before autonomous view construction.
    assert "engine.run_discovery" not in src.split("build_autonomous_daily_edge_ui_view")[0]


def test_app_render_path_snapshot_shows_autonomous_not_old_challenger_voice(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _plant_session(
        edge,
        trade_date="2026-08-27",
        run_id="pdrun-6dd458c5a406a6ec",
        discovery_count=1,
        q1="Hôm nay (2026-08-27) — nhật ký research session. Có 1 observation mới được sinh hôm nay.",
    )
    _plant_stale_challenger(edge)

    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    snap = render_autonomous_daily_edge_text_snapshot(view)

    # Exact public failure mode must fail this assertion if still present:
    assert "CHALLENGER / RESEARCH ONLY" not in snap.split(HISTORICAL_CHALLENGER_SECTION)[0]
    assert AUTONOMOUS_DAILY_SECTION in snap
    assert "Session: 2026-08-27" in snap
    assert "Run: SUCCESS" in snap
    assert "Discovery today: 1" in snap
    assert "SESSION_MARKET_VOICE" in snap
    assert "EDGE-000001" not in snap
    assert "RESEARCH ONLY — NOT VALIDATED" not in snap
    assert view["requires_streamlit_action"] is False


def test_main_tree_contract_autonomous_module_importable_without_opr_bridge_living_ui():
    """Streamlit main may lack living UI panel; autonomous module must still import."""
    mod = ast.parse((REPO / "modules/edge_research/autonomous_daily_edge_ui.py").read_text())
    imports = []
    for n in ast.walk(mod):
        if isinstance(n, ast.ImportFrom) and n.module:
            imports.append(n.module)
    assert "modules.edge_research.opr_bridge.production_living_research_ui_read_model" not in imports
    assert "modules.edge_research.storage" in imports
