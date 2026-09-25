"""Research data foundation: previous close and Market Context retention."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
)
from modules.live_candidate_v2_nomination.contract import REJECT_MARKET_WEAK
from modules.live_candidate_v2_nomination.predicate import evaluate_nomination
from modules.research_market_context.contract import (
    market_context_asof_eligible,
    previous_close_date_eligible,
)
from modules.research_market_context.market_context import (
    append_market_context,
    load_market_context,
    scan_fingerprint,
    try_append_market_context,
)
from modules.research_market_context.previous_close import (
    archive_previous_close,
    integer_vnd_from_d1,
    load_previous_close,
    select_canonical_previous_close,
    try_archive_previous_close,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
SESSION = date(2026, 9, 25)


def _bars(*pairs: tuple[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp(day) for day, _ in pairs],
            "close": [price for _, price in pairs],
        }
    )


def _scan(rows: list[tuple[str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"symbol": symbol, "price": price, "group": group} for symbol, price, group in rows]
    )


def test_previous_close_skips_same_day_bar():
    bars = _bars(("2026-09-24", 22000), ("2026-09-25", 23000))
    selected = select_canonical_previous_close(bars, session_date=SESSION)
    assert selected["previous_close"] == 22000
    assert selected["previous_close_date"] == "2026-09-24"
    assert selected["status"] == "ok"
    assert selected["last_d1_date"] == "2026-09-25"
    assert selected["last_d1_close_before_injection"] == 23000
    assert selected["previous_close_date"] < SESSION.isoformat()
    assert not previous_close_date_eligible(SESSION, SESSION)


def test_previous_close_uses_latest_bar_before_session():
    bars = _bars(("2026-09-18", 21000), ("2026-09-23", 22100), ("2026-09-24", 22200))
    selected = select_canonical_previous_close(bars, session_date=SESSION)
    assert selected["previous_close"] == 22200
    assert selected["previous_close_date"] == "2026-09-24"


def test_missing_history_does_not_fabricate_or_raise(tmp_path: Path):
    path = tmp_path / "previous_close.jsonl"
    result = try_archive_previous_close(
        symbol="HPG",
        daily_bars=pd.DataFrame(),
        session_date=SESSION,
        path=path,
    )
    assert result["ok"] is True
    assert result["written"] is False
    assert result["row"]["previous_close"] is None
    assert result["row"]["status"] == "missing"
    assert not path.exists()


def test_stale_history_keeps_the_close_and_marks_status(tmp_path: Path):
    bars = _bars(("2026-08-01", 20000))
    result = archive_previous_close(
        symbol="HPG",
        daily_bars=bars,
        session_date=SESSION,
        captured_at=datetime(2026, 9, 25, 9, 20, tzinfo=VN),
        path=tmp_path / "previous_close.jsonl",
    )
    assert result["written"] is True
    assert result["row"]["status"] == "stale"
    assert result["row"]["previous_close"] == 20000
    assert result["row"]["previous_close_date"] == "2026-08-01"


def test_d1_price_stays_integer_vnd_and_is_not_scaled_by_1000():
    assert integer_vnd_from_d1(22200) == 22200
    assert integer_vnd_from_d1(22200.4) == 22200
    assert integer_vnd_from_d1(22200.4) != 22_200_400


def test_duplicate_session_symbol_does_not_add_a_second_row(tmp_path: Path):
    path = tmp_path / "previous_close.jsonl"
    bars = _bars(("2026-09-24", 22200), ("2026-09-25", 23000))
    first = archive_previous_close(symbol="hpg", daily_bars=bars, session_date=SESSION, path=path)
    other = _bars(("2026-09-24", 11111), ("2026-09-25", 33333))
    second = archive_previous_close(symbol="HPG", daily_bars=other, session_date=SESSION, path=path)
    rows = load_previous_close(path)
    assert first["written"] is True
    assert second["written"] is False
    assert second["reason"] == "duplicate"
    assert len(rows) == 1
    assert rows[0]["previous_close"] == 22200
    assert rows[0]["price_unit"] == "integer_vnd"
    assert rows[0]["source"] == "vnstock_d1_bar_before_session"


def test_identical_market_context_rerun_is_not_appended(tmp_path: Path):
    path = tmp_path / "market_context.jsonl"
    scan = _scan([("HPG", 22200, "PULL ĐẸP")])
    kwargs = dict(
        trade_date=SESSION,
        market_real=4.2,
        market_live=3.1,
        market_forecast=5.0,
        market_regime="WEAK",
        source="streamlit_scan",
        scan_df=scan,
        path=path,
    )
    first = append_market_context(captured_at=datetime(2026, 9, 25, 9, 16, tzinfo=VN), **kwargs)
    second = append_market_context(captured_at=datetime(2026, 9, 25, 9, 18, tzinfo=VN), **kwargs)
    assert first["written"] is True
    assert second["written"] is False
    assert len(load_market_context(path)) == 1


def test_real_change_and_fingerprint_change_and_close_transitions(tmp_path: Path):
    path = tmp_path / "market_context.jsonl"
    base = dict(
        trade_date=SESSION,
        market_live=3.0,
        market_forecast=5.0,
        market_regime="WEAK",
        source="streamlit_scan",
        path=path,
    )
    scan = _scan([("HPG", 22200, "PULL ĐẸP")])
    t0 = datetime(2026, 9, 25, 9, 16, tzinfo=VN)
    t1 = datetime(2026, 9, 25, 9, 16, 5, tzinfo=VN)
    first = append_market_context(market_real=4.2, scan_df=scan, captured_at=t0, **base)
    changed_real = append_market_context(market_real=4.8, scan_df=scan, captured_at=t1, **base)
    changed_fp = append_market_context(
        market_real=4.8,
        scan_df=_scan([("HPG", 22200, "PULL ĐẸP"), ("FPT", 90000, "CP MẠNH")]),
        captured_at=datetime(2026, 9, 25, 9, 16, 10, tzinfo=VN),
        **base,
    )
    third = append_market_context(
        market_real=5.1,
        scan_df=scan,
        captured_at=datetime(2026, 9, 25, 9, 16, 12, tzinfo=VN),
        **base,
    )
    rows = load_market_context(path)
    assert first["written"] and changed_real["written"] and changed_fp["written"] and third["written"]
    assert [row["market_real"] for row in rows] == [4.2, 4.8, 4.8, 5.1]
    assert rows[2]["scan_fingerprint"] != rows[1]["scan_fingerprint"]


def test_fingerprint_ignores_row_order():
    left = _scan([("FPT", 90000, "CP MẠNH"), ("HPG", 22200, "PULL ĐẸP")])
    right = _scan([("HPG", 22200.0, "PULL ĐẸP"), ("FPT", 90000, "CP MẠNH")])
    assert scan_fingerprint(left) == scan_fingerprint(right)


def test_research_writer_failure_does_not_escape(tmp_path: Path):
    blocked = tmp_path / "not-a-file"
    blocked.mkdir()
    result = try_append_market_context(
        trade_date=SESSION,
        market_real=4.2,
        market_live=3.0,
        market_forecast=5.0,
        market_regime="WEAK",
        source="streamlit_scan",
        scan_df=_scan([("HPG", 1, "PULL ĐẸP")]),
        path=blocked,
    )
    close_result = try_archive_previous_close(
        symbol="HPG",
        daily_bars=_bars(("2026-09-24", 22200)),
        session_date=SESSION,
        path=blocked,
    )
    assert result["ok"] is False
    assert close_result["ok"] is False

    def production_caller() -> float:
        try_append_market_context(
            trade_date=SESSION,
            market_real=4.2,
            market_live=3.0,
            market_forecast=5.0,
            market_regime="WEAK",
            source="streamlit_scan",
            scan_df=_scan([("HPG", 1, "PULL ĐẸP")]),
            path=blocked,
        )
        return 4.2

    assert production_caller() == 4.2


def test_asof_contract_uses_bar_completion():
    start = datetime(2026, 9, 25, 9, 15, tzinfo=VN)
    at_completion = datetime(2026, 9, 25, 9, 20, tzinfo=VN)
    after = datetime(2026, 9, 25, 9, 20, 1, tzinfo=VN)
    assert market_context_asof_eligible(at_completion, start) is True
    assert market_context_asof_eligible(datetime(2026, 9, 25, 9, 19, tzinfo=VN), start) is True
    assert market_context_asof_eligible(after, start) is False


def test_same_day_d1_cannot_be_previous_close():
    only_today = _bars(("2026-09-25", 23000.4))
    selected = select_canonical_previous_close(only_today, session_date=SESSION)
    assert selected["previous_close"] is None
    assert selected["previous_close_date"] is None
    assert selected["status"] == "missing"
    assert selected["last_d1_close_before_injection"] == 23000
    assert previous_close_date_eligible(date(2026, 9, 25), SESSION) is False
    assert previous_close_date_eligible(date(2026, 9, 24), SESSION) is True


def test_market_weak_still_rejects_brain_a_nomination():
    decision = evaluate_nomination(
        {"symbol": "HPG", "group": "PULL ĐẸP"},
        market_real=5.5,
    )
    assert decision.eligible is False
    assert decision.reject_reason == REJECT_MARKET_WEAK


def test_action_permissions_stay_closed():
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False


def test_production_decision_modules_do_not_import_the_archive():
    untouched = [
        "modules/live_candidate_v2_nomination/predicate.py",
        "modules/live_candidate_v2_nomination/nominate.py",
        "modules/live_candidate_v2_nomination/freeze.py",
        "modules/live_candidate_v2_camera/sidecar.py",
        "modules/live_candidate_v2_action/state.py",
        "modules/live_candidate_v2_action/live_universe.py",
        "modules/live_camera_shadow/feed.py",
        "modules/candidate_router/router.py",
        "modules/candidate_router/contract.py",
        "modules/intraday_memory/schema.py",
        "modules/intraday_memory/storage.py",
        "modules/intraday_memory/collector.py",
        "modules/intraday_memory/normalize.py",
    ]
    for rel in untouched:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "research_market_context" not in text


def test_market_real_function_is_not_the_writer():
    source = (REPO / "app.py").read_text(encoding="utf-8")
    start = source.index("def calc_market_real")
    end = source.index("def calc_market_live")
    assert "research_market_context" not in source[start:end]
    buy = source.index("def buy_recommendation")
    buy_end = source.index("def build_buy_table")
    assert "research_market_context" not in source[buy:buy_end]
