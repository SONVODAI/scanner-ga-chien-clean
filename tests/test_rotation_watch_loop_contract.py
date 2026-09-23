"""Production entry point must import the loop lock and still publish Last BUY READY."""

from __future__ import annotations

import ast
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.rotation_watch.runner import (
    DEFAULT_RPM,
    LOOP_LOCK_NAME,
    acquire_loop_lock,
    loop_may_refresh,
    release_loop_lock,
    run_cycle,
    seconds_until_next_completed_bar,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "run_rotation_watch.py"
VN = ZoneInfo("Asia/Ho_Chi_Minh")

PRODUCTION_RUNNER_IMPORTS = {
    "DEFAULT_RPM",
    "acquire_loop_lock",
    "loop_may_refresh",
    "release_loop_lock",
    "run_cycle",
    "seconds_until_next_completed_bar",
}


def _production_import_names() -> set[str]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "modules.rotation_watch.runner":
            continue
        found.update(alias.name for alias in node.names)
    return found


def test_script_imports_match_production_contract():
    assert _production_import_names() == PRODUCTION_RUNNER_IMPORTS
    assert DEFAULT_RPM == 18
    assert callable(acquire_loop_lock)
    assert callable(loop_may_refresh)
    assert callable(release_loop_lock)
    assert callable(run_cycle)
    assert callable(seconds_until_next_completed_bar)


def test_dry_run_entry_point_imports_loop_lock():
    """The failure mode was ImportError at process start, before any cycle."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DRY RUN: refusing KBS" in proc.stderr
    assert "ImportError" not in proc.stderr
    assert "acquire_loop_lock" not in proc.stderr


def test_loop_lock_is_exclusive(tmp_path):
    first = acquire_loop_lock(tmp_path)
    assert first is not None
    assert (tmp_path / LOOP_LOCK_NAME).exists()
    second = acquire_loop_lock(tmp_path)
    assert second is None
    release_loop_lock(first)
    third = acquire_loop_lock(tmp_path)
    assert third is not None
    release_loop_lock(third)


def test_loop_may_refresh_only_during_live_session():
    live = datetime(2026, 8, 14, 10, 40, tzinfo=VN)
    lunch = datetime(2026, 8, 14, 11, 45, tzinfo=VN)
    closed = datetime(2026, 8, 14, 14, 50, tzinfo=VN)
    weekend = datetime(2026, 8, 15, 10, 0, tzinfo=VN)
    assert loop_may_refresh(live)[0] is True
    lunch_ok, lunch_why = loop_may_refresh(lunch)
    assert lunch_ok is False
    assert "LUNCH_HOLD" in lunch_why
    assert loop_may_refresh(closed)[0] is False
    weekend_ok, weekend_why = loop_may_refresh(weekend)
    assert weekend_ok is False
    assert "WEEKEND" in weekend_why


def test_direct_cycle_still_copies_last_buy_ready(tmp_path):
    """--loop may skip persist. A direct cycle still publishes history."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rotation_last_buy_ready_helpers",
        REPO / "tests" / "test_rotation_last_buy_ready.py",
    )
    helpers = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(helpers)
    _fill_session = helpers._fill_session
    _strengthen = helpers._strengthen
    _ts = helpers._ts
    _watchlist = helpers._watchlist

    watch = _watchlist(tmp_path / "watchlist.csv")
    common = {
        "watchlist_path": watch,
        "board_path": tmp_path / "board.json",
        "status_path": tmp_path / "status.json",
        "state_path": tmp_path / "state.json",
    }
    run_cycle(now=_ts("10:40"), injected={"TCH": _fill_session("TCH", "10:35")}, **common)
    run_cycle(now=_ts("10:45"), injected={"TCH": _strengthen("TCH", "10:40")}, **common)
    run_cycle(now=_ts("10:50"), injected={"TCH": _fill_session("TCH", "10:45")}, **common)
    import json

    board = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    row = board["rows"][0]
    assert row["last_session_state"] == "LOWER_ZONE"
    assert row["suggested_action"] == "WATCH LOWER"
    assert row["last_buy_ready"]["last_buy_ready_at"] == _ts("10:45").isoformat()
