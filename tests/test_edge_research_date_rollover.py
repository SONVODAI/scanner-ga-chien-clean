"""
Automatic Edge Research date rollover.

Proves the next trading day is selected from the VN calendar + ledger,
not by hard-coding a date or silently keeping the last SUCCESS.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_research_rollover import (
    resolve_research_rollover_target,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
    offset_trading_sessions,
)
from modules.edge_research.storage import resolve_production_runs_root

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _vn(date_str: str, hour: int, minute: int = 0) -> datetime:
    y, m, d = (int(p) for p in date_str.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=VN_TZ)


def _plant_index_run(edge: Path, *, trade_date: str, run_id: str, disposition: str) -> None:
    prod = resolve_production_runs_root(edge)
    prod.mkdir(parents=True, exist_ok=True)
    index_path = prod / "daily_run_index.json"
    index = {"runs": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index["runs"][run_id] = {
        "run_id": run_id,
        "target_trade_date": trade_date,
        "run_disposition": disposition,
        "run_mode": LIVE_FORWARD,
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")


def test_calendar_treats_sep_7_and_8_2026_as_eligible_vn_sessions():
    assert evaluate_calendar_session_eligibility("2026-09-07").eligible is True
    assert evaluate_calendar_session_eligibility("2026-09-08").eligible is True
    assert offset_trading_sessions("2026-09-08", -1) == "2026-09-07"


def test_catch_up_previous_eligible_session_when_no_terminal_run(tmp_path: Path):
    edge = tmp_path / "edge_research"
    _plant_index_run(edge, trade_date="2026-09-04", run_id="pdrun-0904", disposition="SUCCESS")

    target = resolve_research_rollover_target(
        now=_vn("2026-09-08", 11),
        data_dir=edge,
        run_mode=LIVE_FORWARD,
    )
    assert target.catch_up is True
    assert target.target_trade_date == "2026-09-07"
    assert target.vn_calendar_date == "2026-09-08"
    assert target.reason == "catch_up_previous_eligible_session"


def test_after_previous_success_next_timer_targets_current_vn_date(tmp_path: Path):
    edge = tmp_path / "edge_research"
    _plant_index_run(edge, trade_date="2026-09-07", run_id="pdrun-0907", disposition="SUCCESS")

    morning = resolve_research_rollover_target(
        now=_vn("2026-09-08", 11),
        data_dir=edge,
        run_mode=LIVE_FORWARD,
    )
    assert morning.catch_up is False
    assert morning.target_trade_date == "2026-09-08"

    late = resolve_research_rollover_target(
        now=_vn("2026-09-08", 23, 35),
        data_dir=edge,
        run_mode=LIVE_FORWARD,
    )
    assert late.target_trade_date == "2026-09-08"
    assert late.reason == "vn_calendar_today"


def test_waiting_previous_session_is_not_terminal_and_is_caught_up(tmp_path: Path):
    edge = tmp_path / "edge_research"
    _plant_index_run(
        edge, trade_date="2026-09-07", run_id="pdrun-0907-wait", disposition="WAITING_FOR_DATA"
    )
    target = resolve_research_rollover_target(
        now=_vn("2026-09-08", 18, 35),
        data_dir=edge,
        run_mode=LIVE_FORWARD,
    )
    assert target.target_trade_date == "2026-09-07"
    assert target.catch_up is True


def test_explicit_trade_date_is_not_overridden_by_catch_up(tmp_path: Path):
    edge = tmp_path / "edge_research"
    target = resolve_research_rollover_target(
        "2026-09-08",
        now=_vn("2026-09-08", 11),
        data_dir=edge,
        run_mode=LIVE_FORWARD,
    )
    assert target.target_trade_date == "2026-09-08"
    assert target.catch_up is False
    assert target.reason == "explicit_trade_date"


def test_timer_includes_post_t0_2335_slot():
    timer = (REPO / "deploy/systemd/mrbot-daily-research.timer").read_text(encoding="utf-8")
    assert "23:35:00 Asia/Ho_Chi_Minh" in timer
    assert timer.count("OnCalendar=") == 4
