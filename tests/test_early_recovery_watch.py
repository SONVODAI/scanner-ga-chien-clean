"""EARLY RECOVERY WATCH V1. Forward qualification only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.earning_learning import StorageReadResult, StorageWriteResult
from modules.early_recovery_watch.contract import (
    DELTA_RS10_MIN,
    EARLY_RECOVERY_ALERT_ELIGIBLE,
    EARLY_RECOVERY_IS_BUY,
    EMPTY_MESSAGE,
    MARKET_REAL_MAX_EXCLUSIVE,
    PANEL_TITLE,
    RS10_MAX,
)
from modules.early_recovery_watch.observe import qualifies_v1
from modules.early_recovery_watch.panel import render_early_recovery_watch
from modules.early_recovery_watch.service import run_watch, scorecard
from modules.early_recovery_watch.store import github_mirror_path, materialize
from modules.research_evolution_ledger.ledger import append_evolution_ledger, load_evolution_ledger
from modules.research_market_context.contract import SOURCE_STREAMLIT_SCAN

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
WEAK = "🔴 YẾU"
VERY_WEAK = "⛔ RẤT YẾU"
FADING = "⚠️ YẾU DẦN"
NEUTRAL = "🟡 TRUNG TÍNH"
RECOVERY = "🌱 ĐANG HỒI"
VOL = "Xu hướng lên + Vol xác nhận"
NO_VOL = "Xu hướng lên + Vol chưa xác nhận"


def _row(symbol, health, rs10, price, reason=VOL, rs5=0.4, rsi14=46.0):
    return {
        "symbol": symbol,
        "price": price,
        "group": "THEO DÕI",
        "evolution_health_group": health,
        "rs10": rs10,
        "rs5": rs5,
        "rsi14": rsi14,
        "evolution_reason": reason,
    }


def _append(path: Path, rows: list[dict], when: datetime) -> None:
    append_evolution_ledger(
        trade_date=when.date().isoformat(),
        source=SOURCE_STREAMLIT_SCAN,
        scan_df=pd.DataFrame(rows),
        captured_at=when,
        path=path,
    )


def _watch(evo: Path, directory: Path, rows: list[dict], when: datetime, market_real=5.0, storage=None):
    _append(evo, rows, when)
    return run_watch(
        scan_df=pd.DataFrame(rows),
        market_real=market_real,
        trade_date=when.date(),
        evolution_path=evo,
        directory=directory,
        storage=storage,
        market_live=6.1,
        market_forecast=1.1,
        market_regime="🔴 MÙA ĐÔNG",
        breadth=31.0,
        market_status="🔴 THỊ TRƯỜNG YẾU",
        market_action="⛔ Không nên vào tiền",
    )


class _Column:
    def __init__(self, parent):
        self.parent = parent

    def metric(self, label, value):
        self.parent.lines.append(f"{label}={value}")


class _Streamlit:
    def __init__(self):
        self.lines: list[str] = []

    def markdown(self, text):
        self.lines.append(text)

    def caption(self, text):
        self.lines.append(text)

    def columns(self, count):
        return [_Column(self) for _ in range(count)]

    def dataframe(self, *_args, **_kwargs):
        self.lines.append("TABLE")


class _Mirror:
    def __init__(self, directory: Path):
        self.directory = directory
        self.remote: str | None = None
        self.writes = 0

    def read_text(self, filename: str) -> StorageReadResult:
        path = self.directory / filename
        if self.remote is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.remote, encoding="utf-8")
            return StorageReadResult(text=self.remote, source="GITHUB")
        if path.exists():
            return StorageReadResult(text=path.read_text(encoding="utf-8"), source="LOCAL")
        return StorageReadResult(text=None, source="NONE")

    def write_text(self, filename: str, text: str, *, commit_message: str) -> StorageWriteResult:
        del commit_message
        path = self.directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.remote = text
        self.writes += 1
        return StorageWriteResult(local_ok=True, github_ok=True, github_status="GITHUB_OK")


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    evo = tmp_path / "evolution_ledger.jsonl"
    watch = tmp_path / "watch"
    watch.mkdir()
    return evo, watch


def test_thresholds_are_locked():
    assert DELTA_RS10_MIN == 4.0
    assert RS10_MAX == 2.64
    assert MARKET_REAL_MAX_EXCLUSIVE == 7.0


def test_safety_constants_remain_false():
    assert EARLY_RECOVERY_IS_BUY is False
    assert EARLY_RECOVERY_ALERT_ELIGIBLE is False


def test_weak_to_recovery_qualifies_for_each_weak_label(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    for offset, health in enumerate((WEAK, VERY_WEAK, FADING)):
        symbol = f"A{offset}"
        previous = start + timedelta(minutes=offset)
        current = previous + timedelta(minutes=30)
        _append(evo, [_row(symbol, health, -1.36, 10000)], previous)
        result = _watch(
            evo,
            watch,
            [_row(symbol, RECOVERY, 2.64, 10100)],
            current,
            market_real=6.9,
        )
        matched = [event for event in result["events"] if event["symbol"] == symbol]
        assert len(matched) == 1
        event = matched[0]
        assert event["data_mode"] == "FORWARD"
        assert event["vol_confirm"] is True
        assert event["delta_rs10"] == 4.0
        assert event["current_rs10"] == 2.64
        assert event["market_real_t0"] == 6.9
        assert event["early_recovery_is_buy"] is False
        assert event["alert_eligible"] is False
        assert event["market_regime"] == "🔴 MÙA ĐÔNG"
        assert event["rs5"] == 0.4
        assert event["t3_return_pct"] is None


def test_neutral_to_recovery_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", NEUTRAL, -2.0, 10000)], start)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], start + timedelta(hours=1))
    assert result["events"] == []


def test_recovery_to_recovery_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", RECOVERY, -2.0, 10000)], start)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], start + timedelta(hours=1))
    assert result["events"] == []


def test_delta_rs10_below_4_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    # Current RS10 stays inside the locked cap so only the delta gate fails.
    _append(evo, [_row("AAA", WEAK, -1.0, 10000)], start)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.64, 10100)], start + timedelta(hours=1))
    assert result["events"] == []
    assert qualifies_v1(
        previous_health=WEAK,
        current_health=RECOVERY,
        previous_rs10=-1.0,
        current_rs10=2.64,
        evolution_reason=VOL,
        market_real=5.0,
    ) is False


def test_rs10_above_2_64_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.65, 10100)], start + timedelta(hours=1))
    assert result["events"] == []


def test_missing_volume_confirmation_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    result = _watch(
        evo,
        watch,
        [_row("AAA", RECOVERY, 2.0, 10100, reason=NO_VOL)],
        start + timedelta(hours=1),
    )
    assert result["events"] == []


def test_market_real_at_least_7_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    result = _watch(
        evo,
        watch,
        [_row("AAA", RECOVERY, 2.0, 10100)],
        start + timedelta(hours=1),
        market_real=7.0,
    )
    assert result["events"] == []


def test_missing_previous_evolution_line_does_not_qualify(tmp_path):
    evo, watch = _paths(tmp_path)
    when = datetime(2026, 9, 28, 11, 0, tzinfo=VN)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], when)
    assert result["events"] == []


def test_current_scan_is_not_the_previous_observation(tmp_path):
    evo, watch = _paths(tmp_path)
    previous_at = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    current_at = datetime(2026, 9, 28, 11, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], previous_at)
    result = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], current_at)
    assert len(result["events"]) == 1
    event = result["events"][0]
    ledger = load_evolution_ledger(evo)
    current_line = [line for line in ledger if "ĐANG HỒI" in line["evolution_health_group"]][-1]
    weak_line = [line for line in ledger if line["evolution_health_group"] == WEAK][-1]
    assert event["previous_captured_at"] == weak_line["captured_at"]
    assert event["previous_captured_at"] != current_line["captured_at"]
    assert event["current_captured_at"] == current_line["captured_at"]
    assert event["current_scan_fingerprint"] == current_line["scan_fingerprint"]
    assert "YẾU" in event["previous_health"]
    assert "ĐANG HỒI" in event["current_health"]


def test_identical_rerun_does_not_duplicate_event(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    current = start + timedelta(hours=1)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    first = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], current)
    second = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], current + timedelta(minutes=5))
    assert len(first["created"]) == 1
    assert second["created"] == []
    assert len(second["events"]) == 1
    assert second["events"][0]["event_id"] == first["events"][0]["event_id"]


def test_later_weak_to_recovery_episode_creates_a_new_event(tmp_path):
    evo, watch = _paths(tmp_path)
    day1 = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], day1)
    first = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10100)], day1 + timedelta(hours=1))
    day2 = datetime(2026, 9, 29, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10050)], day2)
    second = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 10200)], day2 + timedelta(hours=1))
    assert len(second["events"]) == 2
    assert len({event["event_id"] for event in second["events"]}) == 2
    assert second["events"][1]["event_id"] != first["events"][0]["event_id"]
    assert second["view"]["scorecard"]["independent_signal_days"] == 2


def test_t0_fields_remain_immutable(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    first = _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 100.0)], start + timedelta(hours=1), market_real=5.0)
    original = dict(first["events"][0])
    path = watch / "events.jsonl"
    forged = dict(original)
    forged["t0_price"] = 1.0
    forged["market_real_t0"] = 0.1
    forged["previous_rs10"] = 99
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(forged, ensure_ascii=False) + "\n", encoding="utf-8")
    later = datetime(2026, 9, 29, 11, 0, tzinfo=VN)
    _append(evo, [_row("AAA", RECOVERY, 2.2, 999.0)], later)
    again = run_watch(
        scan_df=pd.DataFrame([_row("AAA", RECOVERY, 2.2, 999.0)]),
        market_real=1.0,
        trade_date=later.date(),
        evolution_path=evo,
        directory=watch,
        market_regime="🟡 TRUNG TÍNH",
    )
    kept = [event for event in again["events"] if event["event_id"] == original["event_id"]]
    assert len(kept) == 1
    assert kept[0]["t0_price"] == original["t0_price"]
    assert kept[0]["market_real_t0"] == original["market_real_t0"]
    assert kept[0]["previous_rs10"] == original["previous_rs10"]
    assert kept[0]["current_rs10"] == original["current_rs10"]
    assert kept[0]["delta_rs10"] == original["delta_rs10"]
    assert kept[0]["previous_health"] == original["previous_health"]
    assert kept[0]["event_timestamp"] == original["event_timestamp"]


def test_immature_outcomes_remain_pending(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 100)], start)
    _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 100)], start + timedelta(hours=1))
    for extra, price in ((1, 110), (2, 120)):
        when = datetime(2026, 9, 28, 10, 0, tzinfo=VN) + timedelta(days=extra)
        _append(evo, [_row("AAA", RECOVERY, 2.0, price)], when)
    result = run_watch(
        scan_df=pd.DataFrame([_row("AAA", RECOVERY, 2.0, 100)]),
        market_real=5.0,
        trade_date=start.date(),
        evolution_path=evo,
        directory=watch,
    )
    event = result["events"][0]
    assert event["t3_return_pct"] is None
    assert event["t5_return_pct"] is None
    assert event["t10_return_pct"] is None
    assert result["view"]["scorecard"]["mature_t3_n"] == 0
    assert result["view"]["scorecard"]["t3_winrate"] is None


def test_outcome_uses_frozen_t0_price(tmp_path):
    evo, watch = _paths(tmp_path)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 100)], start)
    _watch(evo, watch, [_row("AAA", RECOVERY, 2.0, 100)], start + timedelta(hours=1))
    for extra, price in enumerate((110, 120, 130, 140, 150), start=1):
        when = datetime(2026, 9, 28, 10, 0, tzinfo=VN) + timedelta(days=extra)
        _append(evo, [_row("AAA", RECOVERY, 1.0, price)], when)
    result = run_watch(
        scan_df=pd.DataFrame([_row("AAA", RECOVERY, 2.0, 100)]),
        market_real=5.0,
        trade_date=start.date(),
        evolution_path=evo,
        directory=watch,
    )
    event = result["events"][0]
    # Later stored sessions are 110, 120, 130, 140, 150.
    # T3 is the 3rd of those prices; T5 is the 5th. T10 is still pending.
    assert event["t0_price"] == 100
    assert event["t3_return_pct"] == (130 / 100 - 1) * 100
    assert event["t5_return_pct"] == (150 / 100 - 1) * 100
    assert event["t10_return_pct"] is None


def test_independent_signal_days_count_dates_not_symbols(tmp_path):
    evo, watch = _paths(tmp_path)
    day1_prev = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    day1_now = day1_prev + timedelta(hours=1)
    _append(
        evo,
        [_row("AAA", WEAK, -2, 100), _row("BBB", VERY_WEAK, -3, 200)],
        day1_prev,
    )
    first = _watch(
        evo,
        watch,
        [_row("AAA", RECOVERY, 2.0, 100), _row("BBB", RECOVERY, 1.5, 200)],
        day1_now,
    )
    assert first["view"]["scorecard"]["events"] == 2
    assert first["view"]["scorecard"]["independent_signal_days"] == 1
    day2_prev = datetime(2026, 9, 29, 10, 0, tzinfo=VN)
    _append(evo, [_row("CCC", FADING, -2, 300)], day2_prev)
    second = _watch(evo, watch, [_row("CCC", RECOVERY, 2.0, 300)], day2_prev + timedelta(hours=1))
    card = second["view"]["scorecard"]
    assert card["events"] == 3
    assert card["independent_signal_days"] == 2
    assert scorecard(second["events"])["independent_signal_days"] == 2


def test_zero_candidate_panel_stays_visible(tmp_path):
    evo, watch = _paths(tmp_path)
    result = run_watch(
        scan_df=pd.DataFrame(),
        market_real=5.0,
        trade_date="2026-09-28",
        evolution_path=evo,
        directory=watch,
    )
    assert result["view"]["visible"] is True
    assert result["view"]["title"] == PANEL_TITLE
    assert result["view"]["empty_message"] == EMPTY_MESSAGE
    assert result["view"]["scorecard"]["events"] == 0
    assert result["view"]["scorecard"]["t3_winrate"] is None
    screen = _Streamlit()
    render_early_recovery_watch(
        scan_df=pd.DataFrame(),
        market_real=5.0,
        trade_date="2026-09-28",
        evolution_path=evo,
        directory=watch,
        streamlit_module=screen,
    )
    rendered = "\n".join(screen.lines)
    assert PANEL_TITLE in rendered
    assert EMPTY_MESSAGE in rendered
    assert "T3 Winrate=—" in rendered


def test_durable_mirror_round_trip_restores_frozen_event(tmp_path):
    evo, watch = _paths(tmp_path)
    mirror = _Mirror(watch)
    start = datetime(2026, 9, 28, 10, 0, tzinfo=VN)
    _append(evo, [_row("AAA", WEAK, -2.0, 10000)], start)
    first = _watch(
        evo,
        watch,
        [_row("AAA", RECOVERY, 2.0, 10100)],
        start + timedelta(hours=1),
        storage=mirror,
    )
    assert mirror.remote is not None
    assert github_mirror_path() == "research/early_recovery_watch/events.jsonl"
    assert "earning_money_snapshots" not in github_mirror_path()
    assert "observations.csv" not in github_mirror_path()
    original = first["events"][0]
    (watch / "events.jsonl").unlink()
    restored = run_watch(
        scan_df=pd.DataFrame([_row("AAA", RECOVERY, 2.0, 10100)]),
        market_real=9.0,
        trade_date=start.date(),
        evolution_path=evo,
        directory=watch,
        storage=mirror,
    )
    assert len(restored["events"]) == 1
    assert restored["events"][0]["event_id"] == original["event_id"]
    assert restored["events"][0]["t0_price"] == original["t0_price"]
    assert restored["events"][0]["market_real_t0"] == original["market_real_t0"]
    assert materialize(mirror.remote)[0]["t0_price"] == original["t0_price"]


def test_panel_is_above_earning_board_and_does_not_read_mutable_earning_files():
    source = (REPO / "app.py").read_text(encoding="utf-8")
    watch_at = source.index("render_early_recovery_watch(")
    board_at = source.index("render_earning_money_board(")
    assert watch_at < board_at
    package = REPO / "modules" / "early_recovery_watch"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "earning_money_snapshots" not in combined
    assert "observations.csv" not in combined
