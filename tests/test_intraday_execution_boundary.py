"""Clock gate for research below the Daily Report boundary.

Required pins:
  09:30 weekday → LOCKED
  12:00 weekday → LOCKED (lunch stays locked)
  14:55 weekday → LOCKED (close buffer)
  15:10+        → ENABLED

Weekends stay enabled: the current app runs the full page on Saturday
and Sunday, and there is no exchange holiday calendar to consult.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.intraday_execution_boundary import (
    RESEARCH_LOCK_START,
    RESEARCH_UNLOCK_AT,
    research_below_boundary_locked,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
# Tuesday.
WEEKDAY = datetime(2026, 9, 22, tzinfo=VN)


def _at(hour: int, minute: int, second: int = 0, *, day: datetime = WEEKDAY) -> datetime:
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def test_required_clock_pins():
    assert research_below_boundary_locked(_at(9, 30)) is True
    assert research_below_boundary_locked(_at(12, 0)) is True
    assert research_below_boundary_locked(_at(14, 55)) is True
    assert research_below_boundary_locked(_at(15, 10)) is False
    assert research_below_boundary_locked(_at(15, 11)) is False
    assert research_below_boundary_locked(_at(18, 0)) is False


def test_lock_window_edges_include_lunch_and_close_buffer():
    assert RESEARCH_LOCK_START.hour == 9 and RESEARCH_LOCK_START.minute == 15
    assert RESEARCH_UNLOCK_AT.hour == 15 and RESEARCH_UNLOCK_AT.minute == 10
    assert research_below_boundary_locked(_at(9, 14, 59)) is False
    assert research_below_boundary_locked(_at(9, 15)) is True
    assert research_below_boundary_locked(_at(11, 30)) is True
    assert research_below_boundary_locked(_at(13, 0)) is True
    assert research_below_boundary_locked(_at(14, 50)) is True
    assert research_below_boundary_locked(_at(15, 9, 59)) is True


def test_weekend_keeps_current_full_page_execution():
    """Audit: non-trading weekends currently run every below-boundary engine.

    The gate must not invent a weekend lock. Saturday/Sunday stay enabled
    even inside the weekday clock window.
    """
    saturday = datetime(2026, 9, 26, 9, 30, tzinfo=VN)
    sunday_lunch = datetime(2026, 9, 27, 12, 0, tzinfo=VN)
    sunday_buffer = datetime(2026, 9, 27, 14, 55, tzinfo=VN)
    assert saturday.weekday() == 5
    assert research_below_boundary_locked(saturday) is False
    assert research_below_boundary_locked(sunday_lunch) is False
    assert research_below_boundary_locked(sunday_buffer) is False


def test_naive_datetime_is_vietnam_wall_time():
    assert research_below_boundary_locked(datetime(2026, 9, 22, 9, 30)) is True
    assert research_below_boundary_locked(datetime(2026, 9, 22, 15, 10)) is False


def test_locked_stop_does_not_execute_following_code():
    """The app pattern must abort before any later engine call."""
    executed: list[str] = []

    class _St:
        @staticmethod
        def caption(message: str) -> None:
            executed.append(f"caption:{message}")

        @staticmethod
        def stop() -> None:
            executed.append("stop")
            raise SystemExit

    namespace = {
        "research_below_boundary_locked": research_below_boundary_locked,
        "vn_now": lambda: _at(9, 30),
        "st": _St,
        "executed": executed,
    }
    script = """
if research_below_boundary_locked(vn_now()):
    st.caption("locked")
    st.stop()
executed.append("run_experience_engine")
executed.append("capture_market_t0_snapshot")
"""
    try:
        exec(script, namespace)
    except SystemExit:
        pass
    assert executed == ["caption:locked", "stop"]
    assert "run_experience_engine" not in executed


def test_unlocked_path_runs_following_code():
    executed: list[str] = []

    class _St:
        @staticmethod
        def caption(message: str) -> None:
            raise AssertionError(message)

        @staticmethod
        def stop() -> None:
            raise AssertionError("stop")

    namespace = {
        "research_below_boundary_locked": research_below_boundary_locked,
        "vn_now": lambda: _at(15, 10),
        "st": _St,
        "executed": executed,
    }
    script = """
if research_below_boundary_locked(vn_now()):
    st.caption("locked")
    st.stop()
executed.append("run_experience_engine")
"""
    exec(script, namespace)
    assert executed == ["run_experience_engine"]


def _call_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            names.append(func.attr)
    return names


def test_app_gate_is_a_single_stop_after_daily_report():
    """Heavy research stays textually after st.stop(); it is not wrapped in a hide-only branch."""
    src = (REPO / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    gates = [
        node
        for node in tree.body
        if isinstance(node, ast.If) and "research_below_boundary_locked" in _call_names(node.test)
    ]
    assert len(gates) == 1
    gate = gates[0]
    assert gate.orelse == []
    body_calls = []
    for stmt in gate.body:
        body_calls.extend(_call_names(stmt))
    assert body_calls == ["caption", "stop"]

    gate_at = src.index("if research_below_boundary_locked(")
    daily_at = src.index("process_and_render_daily_summary(")
    experience_at = src.index("run_experience_engine(")
    assert daily_at < gate_at < experience_at
    assert src.count("research_below_boundary_locked(") == 1

    below = (
        "run_experience_engine",
        "capture_market_t0_snapshot",
        "finalize_session_forward_shadow",
        "update_learning",
        "mature_forward_outcomes",
        "freeze_daily_observer_if_eligible",
        "mature_observer_outcomes",
        "run_buy_elite_learning_cycle",
        "run_v21_brain_cycle",
        "run_brain_optimizer",
        "render_sweetspot_research_panel",
        "render_market_aware_sweetspot_observer_panel",
        "show_leader_brain",
        "update_memory",
    )
    after_lines = "\n".join(src.splitlines()[gate.end_lineno :])
    for name in below:
        assert name in after_lines, name
        assert name not in "\n".join(src.splitlines()[gate.lineno - 1 : gate.end_lineno])

    above_lines = "\n".join(src.splitlines()[: gate.lineno - 1])
    for name in (
        "render_live_candidate_v2_panel",
        "render_v2_shadow_action_panel",
        "render_rotation_watch_panel",
        "render_guardian",
        "render_edge_research_panel",
        "render_earning_money_board",
        "process_and_render_daily_summary",
    ):
        assert name in above_lines

    # Second leader-memory update is below the gate; the V2 prep update stays above.
    assert above_lines.count("update_memory(") == 1
    assert after_lines.count("update_memory(") == 1
    assert "st.stop()" in "\n".join(src.splitlines()[gate.lineno - 1 : gate.end_lineno])
