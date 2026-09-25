"""Evolution Observer V1: append-only raw-state collection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
)
from modules.live_candidate_v2_nomination.contract import REJECT_MARKET_WEAK
from modules.live_candidate_v2_nomination.predicate import evaluate_nomination
from modules.research_evolution_ledger.contract import (
    OBSERVED_FIELDS,
    SOURCE_CLOSE_SCAN,
    SOURCE_STREAMLIT_SCAN,
    evolution_context_asof_eligible,
)
from modules.research_evolution_ledger.ledger import (
    append_evolution_ledger,
    load_evolution_ledger,
    state_hash,
    try_append_evolution_ledger,
)
from modules.research_market_context.market_context import (
    append_market_context,
    load_market_context,
    scan_fingerprint,
)

REPO = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
DAY = "2026-09-25"
MORNING = datetime(2026, 9, 25, 10, 0, tzinfo=VN)
LATER = datetime(2026, 9, 25, 10, 5, tzinfo=VN)
CLOSE = datetime(2026, 9, 25, 14, 50, tzinfo=VN)

FORBIDDEN = {
    "evolution_action",
    "behavior_class",
    "TrajectoryScore",
    "is_leader",
    "market_real",
    "market_live",
    "market_forecast",
    "t3_return",
    "t5_return",
    "t10_return",
}


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(symbol: str, **overrides) -> dict:
    base = {
        "symbol": symbol,
        "price": 22000,
        "group": "THEO DÕI",
        "group_rank": 0,
        "evolution_health_group": "🔴 YẾU",
        "evolution_health_score": 42.0,
        "evolution_health_rank": 2,
        "rs5": -1.5,
        "rs10": -2.0,
        "rsi14": 38.0,
        "rsi_slope": -0.4,
        "obv_status": "🔴",
        "ema9": 22100.0,
        "ma20": 23000.0,
        "ema9_ma20_slope": -1.2,
        "ema9_ma20_slope_change": -0.3,
        "dist_from_ema9_pct": -0.45,
        "volume": 100000,
        "vol_ma20": 120000,
        "dryup_ratio_5": 0.8,
        "dryup_ratio_10": 0.9,
        "near_bottom_20_pct": 3.0,
        "near_bottom_60_pct": 8.0,
        "dist_high20_pct": -12.0,
        "green_2_confirm": "",
        "early_green2": "",
        "early_dry_green2": "",
        "pull_label": "PULL XẤU",
        "total_score": 3,
        "E": 0,
        "R": 0,
        "O": 1,
        "S": 0,
        "RS": 1,
        "V": 1,
        "is_live_adjusted": True,
    }
    base.update(overrides)
    return base


def _append(path: Path, frame: pd.DataFrame, *, source=SOURCE_STREAMLIT_SCAN, when=MORNING):
    return append_evolution_ledger(
        trade_date=DAY,
        source=source,
        scan_df=frame,
        captured_at=when,
        path=path,
    )


def test_full_universe_keeps_weak_and_strong(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    original = _frame([
        _row("YEU", evolution_health_group="⛔ RẤT YẾU", group="THEO DÕI", price=10000),
        _row("MANH", evolution_health_group="🌱 ĐANG HỒI", group="GÀ TĂNG TỐC", price=50000, group_rank=7),
    ])
    before = original.copy(deep=True)
    result = _append(path, original)
    assert result["appended"] == 2
    stored = load_evolution_ledger(path)
    assert [row["symbol"] for row in stored] == ["YEU", "MANH"]
    assert stored[0]["evolution_health_group"] == "⛔ RẤT YẾU"
    assert stored[1]["group"] == "GÀ TĂNG TỐC"
    assert set(stored[0]) & FORBIDDEN == set()
    pd.testing.assert_frame_equal(original, before)


def test_identical_state_does_not_append(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    frame = _frame([_row("GEE")])
    assert _append(path, frame)["appended"] == 1
    second = _append(path, frame, when=LATER)
    assert second["written"] is False
    assert second["reason"] == "unchanged"
    assert len(load_evolution_ledger(path)) == 1


def test_one_changed_field_appends_and_keeps_history(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    _append(path, _frame([_row("GEE", price=22000)]))
    _append(path, _frame([_row("GEE", price=22100)]), when=LATER)
    _append(path, _frame([_row("GEE", price=22300)]), when=CLOSE)
    stored = load_evolution_ledger(path)
    assert [row["price"] for row in stored] == [22000, 22100, 22300]
    assert [row["captured_at"] for row in stored] == [
        MORNING.isoformat(),
        LATER.isoformat(),
        CLOSE.isoformat(),
    ]
    assert stored[0]["session_slot"] == "MORNING"
    assert stored[2]["session_slot"] == "CLOSE"


def test_symbols_dedupe_independently(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    _append(path, _frame([_row("AAA", price=10), _row("BBB", price=20)]))
    result = _append(
        path,
        _frame([_row("AAA", price=10), _row("BBB", price=21)]),
        when=LATER,
    )
    assert result["appended"] == 1
    stored = load_evolution_ledger(path)
    assert [row["symbol"] for row in stored] == ["AAA", "BBB", "BBB"]
    assert [row["price"] for row in stored if row["symbol"] == "AAA"] == [10]


def test_close_scan_coexists_with_same_state(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    frame = _frame([_row("GEE")])
    _append(path, frame, source=SOURCE_STREAMLIT_SCAN, when=MORNING)
    closed = _append(path, frame, source=SOURCE_CLOSE_SCAN, when=CLOSE)
    assert closed["appended"] == 1
    again = _append(path, frame, source=SOURCE_CLOSE_SCAN, when=CLOSE)
    assert again["appended"] == 0
    stored = load_evolution_ledger(path)
    assert [(row["source"], row["symbol"]) for row in stored] == [
        (SOURCE_STREAMLIT_SCAN, "GEE"),
        (SOURCE_CLOSE_SCAN, "GEE"),
    ]


def test_fingerprint_and_provenance_are_stored(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    frame = _frame([_row("HPG", price=25000, group="PULL ĐẸP")])
    result = _append(path, frame)
    stored = load_evolution_ledger(path)[0]
    assert stored["scan_fingerprint"] == scan_fingerprint(frame) == result["scan_fingerprint"]
    assert stored["source"] == SOURCE_STREAMLIT_SCAN
    assert stored["captured_at"] == MORNING.isoformat()
    assert stored["status"] == "ok"
    assert stored["state_hash"]


def test_fingerprint_change_without_symbol_state_change_does_not_rewrite(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    _append(path, _frame([_row("AAA", price=10)]))
    _append(path, _frame([_row("AAA", price=10), _row("BBB", price=20)]), when=LATER)
    stored = load_evolution_ledger(path)
    aaa = [row for row in stored if row["symbol"] == "AAA"]
    assert len(aaa) == 1
    assert aaa[0]["captured_at"] == MORNING.isoformat()


def test_missing_optional_field_is_null_and_blank_symbol_is_skipped(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    frame = pd.DataFrame([
        {"symbol": "GEE", "price": 22000, "group": "THEO DÕI"},
        {"symbol": "  ", "price": 1, "group": "CP MẠNH"},
    ])
    result = try_append_evolution_ledger(
        trade_date=DAY,
        source=SOURCE_STREAMLIT_SCAN,
        scan_df=frame,
        captured_at=MORNING,
        path=path,
    )
    assert result["ok"] is True
    assert result["appended"] == 1
    stored = load_evolution_ledger(path)[0]
    assert stored["rs5"] is None
    assert stored["evolution_health_score"] is None
    assert stored["price"] == 22000
    assert "evolution_action" not in stored
    for column in OBSERVED_FIELDS:
        assert column in stored


def test_malformed_tail_does_not_escape(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    path.write_text('{"trade_date":"2026-09-25","broken":', encoding="utf-8")
    result = try_append_evolution_ledger(
        trade_date=DAY,
        source=SOURCE_STREAMLIT_SCAN,
        scan_df=_frame([_row("GEE")]),
        captured_at=MORNING,
        path=path,
    )
    assert result["ok"] is True
    assert result["appended"] == 1
    stored = load_evolution_ledger(path)
    assert len(stored) == 1
    assert stored[0]["symbol"] == "GEE"
    text = path.read_text(encoding="utf-8")
    assert "\n{" in text or text.strip().endswith("}")


def test_write_failure_does_not_escape(tmp_path: Path):
    blocked = tmp_path / "not-a-file"
    blocked.mkdir()

    def production_caller() -> str:
        outcome = try_append_evolution_ledger(
            trade_date=DAY,
            source=SOURCE_STREAMLIT_SCAN,
            scan_df=_frame([_row("GEE")]),
            captured_at=MORNING,
            path=blocked,
        )
        assert outcome["ok"] is False
        assert outcome["reason"] == "write_failed"
        return "scan-continues"

    assert production_caller() == "scan-continues"


def test_asof_join_rejects_later_context():
    context = datetime(2026, 9, 25, 10, 6, tzinfo=VN)
    evolution = datetime(2026, 9, 25, 10, 5, tzinfo=VN)
    assert evolution_context_asof_eligible(evolution, context) is True
    assert evolution_context_asof_eligible(context, evolution) is False
    assert evolution_context_asof_eligible(evolution, evolution) is True


def test_market_weak_still_rejects_and_permissions_stay_closed():
    decision = evaluate_nomination(
        {"symbol": "HPG", "group": "PULL ĐẸP"},
        market_real=5.5,
    )
    assert decision.eligible is False
    assert decision.reject_reason == REJECT_MARKET_WEAK
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False


def test_two_states_keep_distinct_vietnam_timestamps(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    first_at = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)  # 10:00 VN
    second_at = datetime(2026, 9, 25, 10, 5, tzinfo=VN)
    _append(path, _frame([_row("GEE", price=22000)]), source=SOURCE_STREAMLIT_SCAN, when=first_at)
    _append(
        path,
        _frame([_row("GEE", price=22100)]),
        source=SOURCE_STREAMLIT_SCAN,
        when=second_at,
    )
    stored = load_evolution_ledger(path)
    stamps = [datetime.fromisoformat(row["captured_at"]) for row in stored]
    assert [stamp.tzinfo is not None and stamp.utcoffset() == timedelta(hours=7) for stamp in stamps] == [
        True,
        True,
    ]
    assert stamps[0] < stamps[1]
    assert stamps[0].hour == 10 and stamps[1].hour == 10
    assert stamps[0].minute == 0 and stamps[1].minute == 5
    assert stored[0]["source"] == stored[1]["source"] == SOURCE_STREAMLIT_SCAN


def test_default_clock_is_vietnam_not_naive_utc(tmp_path: Path, monkeypatch):
    path = tmp_path / "evolution_ledger.jsonl"
    fixed = datetime(2026, 9, 25, 20, 2, tzinfo=VN)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return datetime(2026, 9, 25, 13, 2)  # naive UTC, must not be used
            return fixed.astimezone(tz)

    monkeypatch.setattr(
        "modules.research_evolution_ledger.ledger.datetime",
        _FixedDateTime,
    )
    append_evolution_ledger(
        trade_date=DAY,
        source=SOURCE_CLOSE_SCAN,
        scan_df=_frame([_row("GEE")]),
        path=path,
    )
    stamp = datetime.fromisoformat(load_evolution_ledger(path)[0]["captured_at"])
    assert stamp == fixed
    assert stamp.utcoffset() == timedelta(hours=7)


def test_state_hash_ignores_representation(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    python_row = _row("GEE", price=22200, rs5=1.5, rsi14=None, pull_label="")
    numpy_row = _row(
        "GEE",
        price=np.float64(22200.0),
        rs5=np.float64(1.5),
        rsi14=np.float64("nan"),
        pull_label="  ",
        is_live_adjusted=np.bool_(True),
    )
    wide = pd.DataFrame([python_row])
    reordered = pd.DataFrame([numpy_row])[list(reversed(wide.columns))]
    first = _append(path, wide)
    second = _append(path, reordered, when=LATER)
    assert first["appended"] == 1
    assert second["appended"] == 0
    assert len(load_evolution_ledger(path)) == 1


def test_missing_blank_and_null_are_one_state_until_a_real_value(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    missing = pd.DataFrame([{"symbol": "GEE", "price": 22200, "group": "THEO DÕI"}])
    blank = pd.DataFrame([{
        "symbol": "GEE",
        "price": 22200.0,
        "group": "THEO DÕI",
        "rs5": np.nan,
        "pull_label": "",
        "rsi14": pd.NA,
        "evolution_health_score": None,
    }])
    assert _append(path, missing)["appended"] == 1
    assert _append(path, blank, when=LATER)["appended"] == 0
    filled = blank.copy()
    filled["rs5"] = 1.25
    assert _append(path, filled, when=CLOSE)["appended"] == 1
    stored = load_evolution_ledger(path)
    assert [row["rs5"] for row in stored] == [None, 1.25]
    assert stored[0]["state_hash"] != stored[1]["state_hash"]


def test_same_scan_fingerprint_as_market_context(tmp_path: Path):
    frame = _frame([
        _row("YEU", price=10000, group="THEO DÕI"),
        _row("MANH", price=50000, group="GÀ TĂNG TỐC"),
    ]).sample(frac=1, random_state=1).reset_index(drop=True)
    market_path = tmp_path / "market_context.jsonl"
    evo_path = tmp_path / "evolution_ledger.jsonl"
    market = append_market_context(
        trade_date=DAY,
        market_real=5.5,
        market_live=4.0,
        market_forecast=6.0,
        market_regime="WEAK",
        source=SOURCE_STREAMLIT_SCAN,
        scan_df=frame,
        captured_at=MORNING,
        path=market_path,
    )
    evolution = _append(evo_path, frame)
    market_fp = load_market_context(market_path)[0]["scan_fingerprint"]
    evo_fp = load_evolution_ledger(evo_path)[0]["scan_fingerprint"]
    assert market["row"]["scan_fingerprint"] == market_fp == evo_fp == evolution["scan_fingerprint"]
    assert {row["scan_fingerprint"] for row in load_evolution_ledger(evo_path)} == {market_fp}

    app = (REPO / "app.py").read_text(encoding="utf-8")
    block = app[app.index("try_append_market_context("):app.index("evo_saved_df, evo_save_status")]
    assert "try_append_evolution_ledger(" in block
    assert not any(line.strip().startswith("scan_df ") for line in block.splitlines())


def test_malformed_tail_does_not_repeat_an_existing_state(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    _append(path, _frame([_row("GEE", price=22000)]))
    with path.open("ab") as handle:
        handle.write(b'{"trade_date":"2026-09-25","symbol":"GEE","broken"')
    first = _append(path, _frame([_row("GEE", price=22000)]), when=LATER)
    second = _append(path, _frame([_row("GEE", price=22000)]), when=CLOSE)
    assert first["appended"] == 0
    assert second["appended"] == 0
    gee = [row for row in load_evolution_ledger(path) if row["symbol"] == "GEE"]
    assert len(gee) == 1
    assert gee[0]["price"] == 22000


def test_glued_truncated_tail_recovers_once(tmp_path: Path):
    path = tmp_path / "evolution_ledger.jsonl"
    _append(path, _frame([_row("GEE", price=22000)]))
    text = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text(text + '{"truncated"', encoding="utf-8")
    assert load_evolution_ledger(path) == []
    recovered = _append(path, _frame([_row("GEE", price=22000)]), when=LATER)
    repeated = _append(path, _frame([_row("GEE", price=22000)]), when=CLOSE)
    assert recovered["appended"] == 1
    assert repeated["appended"] == 0
    assert len(load_evolution_ledger(path)) == 1


def test_close_scan_observer_failure_stays_downstream(tmp_path: Path, monkeypatch):
    from modules.close_session_scan import build_close_scan_inputs
    from tests.test_close_session_scan import _patched_api

    monkeypatch.setenv("MRBOT_MARKET_CONTEXT_DIR", str(tmp_path / "market"))
    monkeypatch.setenv("MRBOT_EVOLUTION_LEDGER_DIR", str(tmp_path / "evolution"))

    def _boom(**_kwargs):
        raise RuntimeError("evolution ledger unavailable")

    monkeypatch.setattr(
        "modules.research_evolution_ledger.ledger.try_append_evolution_ledger",
        _boom,
    )
    result = build_close_scan_inputs(
        now=datetime(2026, 9, 22, 18, 30, tzinfo=VN),
        symbols=["AAA"],
        api=_patched_api(),
    )
    assert result["ok"] is True
    assert result["status"] == "READY"
    assert result["market_real"] is not None
    assert list(result["scan_df"]["symbol"]) == ["AAA"]
    market_file = tmp_path / "market" / "market_context.jsonl"
    assert market_file.exists() and market_file.stat().st_size > 0
    assert not (tmp_path / "evolution" / "evolution_ledger.jsonl").exists()


def test_writer_does_not_call_providers_or_scoring():
    source = (REPO / "modules/research_evolution_ledger/ledger.py").read_text(encoding="utf-8")
    for banned in (
        "vnstock",
        "calc_market_real",
        "add_evolution_health",
        "download_symbol_data",
        "load_market_context",
        "market_context.jsonl",
        "evolution_action",
    ):
        assert banned not in source


def test_decision_modules_do_not_import_the_ledger():
    untouched = [
        "modules/live_candidate_v2_nomination/predicate.py",
        "modules/live_candidate_v2_nomination/nominate.py",
        "modules/live_candidate_v2_nomination/freeze.py",
        "modules/live_candidate_v2_nomination/sweet_brain_b.py",
        "modules/live_candidate_v2_camera/sidecar.py",
        "modules/live_candidate_v2_action/state.py",
        "modules/live_candidate_v2_action/live_universe.py",
        "modules/live_camera_shadow/feed.py",
        "modules/candidate_router/router.py",
        "modules/candidate_router/contract.py",
        "modules/earning_learning.py",
        "modules/evolution_health.py",
        "modules/market_aware_sweetspot_observer.py",
        "modules/rotation_watch/engine.py",
        "modules/intraday_memory/collector.py",
        "position_guardian.py",
    ]
    for rel in untouched:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "research_evolution_ledger" not in text

    app = (REPO / "app.py").read_text(encoding="utf-8")
    for start, end in (
        ("def analyze_symbol", "def run_scan"),
        ("def calc_market_real", "def calc_market_live"),
        ("def buy_recommendation", "def build_buy_table"),
    ):
        assert "research_evolution_ledger" not in app[app.index(start):app.index(end)]

    close = (REPO / "modules/close_session_scan.py").read_text(encoding="utf-8")
    failed = close.index('"status": "CLOSE_SCAN_FAILED"')
    writer = close.index("try_append_evolution_ledger")
    ready = close.index('"status": "READY"')
    assert failed < writer < ready
