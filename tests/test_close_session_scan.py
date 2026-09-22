"""Headless close scan uses the production definitions and the same session D."""

from __future__ import annotations

import inspect
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modules.close_session_scan import (
    APP_PATH,
    build_close_scan_inputs,
    load_production_scan_api,
)
from modules.evolution_health import get_earning_money_board
from modules.market_aware_sweetspot_observer import _normalize_universe
from modules.market_t0_capture import build_market_t0_row
from modules.post_close_finalize import (
    BEFORE_CANONICAL_WINDOW,
    SAME_DAY_WINDOW_CLOSED,
    run_post_close_finalize,
)
from tests.test_post_close_finalize import _handoff

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2025-06-01", periods=80)
    close = np.linspace(20, 30, 80)
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.2,
        "high": close + 0.4,
        "low": close - 0.5,
        "close": close,
        "volume": np.full(80, 100_000.0),
    })


def _patched_api():
    api = load_production_scan_api()
    raw = _ohlcv()
    api["download_symbol_data"] = lambda symbol: raw.copy()
    api["fetch_live_price"] = lambda symbol: {
        "price": np.nan,
        "volume": np.nan,
        "source": "NO_DATA",
        "ts": "",
    }
    api["is_vnindex_trading_today"] = lambda: (True, "fixture")
    return api


def test_loader_executes_app_definitions_without_importing_the_page():
    source = (APP_PATH.parent / "modules" / "close_session_scan.py").read_text(encoding="utf-8")
    assert "import app" not in source
    assert "e_ratio * 3.0" not in source
    assert "session_handoff" not in source
    api = load_production_scan_api()
    assert api["calc_market_real"].__code__.co_filename.endswith("app.py")
    assert "handoff" not in inspect.signature(build_close_scan_inputs).parameters


def test_close_scan_feeds_market_t0_and_sweetspot_for_the_same_session():
    api = _patched_api()
    evening = datetime(2026, 9, 22, 18, 30, tzinfo=VN)
    retry = datetime(2026, 9, 22, 20, 30, tzinfo=VN)
    first = build_close_scan_inputs(now=evening, symbols=["AAA"], api=api)
    second = build_close_scan_inputs(now=retry, symbols=["AAA"], api=api)
    assert first["ok"] is True and second["ok"] is True
    assert first["trade_date"] == second["trade_date"] == "2026-09-22"
    assert first["source"] == "close_scan"
    for column in ("symbol", "price", "rs5", "rs10", "rsi14", "group"):
        assert column in first["scan_df"].columns

    board = get_earning_money_board(first["scan_df"])
    universe = _normalize_universe(board)
    assert universe["symbol"].iloc[0] == "AAA"
    row = build_market_t0_row(
        scan_df=first["scan_df"],
        trade_date=first["trade_date"],
        market_real=first["market_real"],
        market_live=first["market_live"],
        market_forecast=first["market_forecast"],
        market_forecast_text=first["market_forecast_text"],
        market_confidence=first["market_confidence"],
        market_status=first["market_status"],
        market_action=first["market_action"],
        market_regime=first["market_regime"],
        market_regime_note=first["market_regime_note"],
        rsi_breadth_report=first["rsi_breadth_report"],
        trading_today=first["trading_today"],
        trading_reason=first["trading_reason"],
        include_vnindex_ohlcv=False,
        now=evening,
    )
    assert row["trade_date"] == "2026-09-22"
    assert row["market_real"] == first["market_real"]


def test_empty_close_scan_does_not_call_writers(monkeypatch):
    api = _patched_api()
    api["download_symbol_data"] = lambda symbol: pd.DataFrame()

    def writers(*_args, **_kwargs):
        raise AssertionError("close writers ran on an empty scan")

    monkeypatch.setattr("modules.post_close_finalize._run_close_writers", writers)
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_forward",
        lambda *a, **k: {"ok": True, "status": "FROZEN", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_buy_elite",
        lambda *a, **k: {"status": "APPENDED", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_learning",
        lambda *a, **k: {"status": "UPDATED", "source": "session_handoff_v1"},
    )
    payload = build_close_scan_inputs(
        now=datetime(2026, 9, 22, 18, 30, tzinfo=VN),
        symbols=["AAA"],
        api=api,
    )
    assert payload["status"] == "CLOSE_SCAN_EMPTY"
    monkeypatch.setattr(
        "modules.close_session_scan.build_close_scan_inputs",
        lambda **_kwargs: payload,
    )
    report = run_post_close_finalize(
        now=datetime(2026, 9, 22, 18, 30, tzinfo=VN),
        handoff=_handoff(),
        mature=False,
    )
    assert report["steps"]["market_t0"]["status"] == "CLOSE_SCAN_EMPTY"
    assert report["steps"]["sweetspot"]["status"] == "CLOSE_SCAN_EMPTY"
    assert report["steps"]["forward_shadow"]["source"] == "session_handoff_v1"


def test_retry_uses_the_same_session_d(monkeypatch):
    clocks = []

    def builder(*, now=None, symbols=None, api=None):
        clocks.append(now)
        return {
            "ok": True,
            "status": "READY",
            "trade_date": "from-clock",
            "scan_df": pd.DataFrame([{"symbol": "CLOSE_ONLY", "price": 1}]),
            "market_real": 1,
        }

    seen = []

    def writers(payload, *, trade_date, now, data_dir=None):
        seen.append(trade_date)
        assert payload["scan_df"]["symbol"].iloc[0] == "CLOSE_ONLY"
        return {"status": "CAPTURED", "source": "close_scan"}, {"status": "FROZEN", "source": "close_scan"}

    monkeypatch.setattr("modules.close_session_scan.build_close_scan_inputs", builder)
    monkeypatch.setattr("modules.post_close_finalize._run_close_writers", writers)
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_forward",
        lambda *a, **k: {"ok": True, "status": "FROZEN", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_buy_elite",
        lambda *a, **k: {"status": "APPENDED", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_learning",
        lambda *a, **k: {"status": "UPDATED", "source": "session_handoff_v1"},
    )
    for hour, minute in ((18, 30), (20, 30)):
        run_post_close_finalize(
            now=datetime(2026, 9, 22, hour, minute, tzinfo=VN),
            handoff=_handoff(),
            mature=False,
        )
    assert [clock.strftime("%Y-%m-%d %H:%M") for clock in clocks] == [
        "2026-09-22 18:30",
        "2026-09-22 20:30",
    ]
    assert seen == ["2026-09-22", "2026-09-22"]


def test_close_scan_stays_inside_the_canonical_window(monkeypatch):
    def builder(**_kwargs):
        raise AssertionError("close scan built outside the window")

    monkeypatch.setattr("modules.close_session_scan.build_close_scan_inputs", builder)
    early = run_post_close_finalize(
        now=datetime(2026, 9, 22, 17, 59, tzinfo=VN),
        mature=False,
    )
    later = run_post_close_finalize(
        now=datetime(2026, 9, 23, 18, 30, tzinfo=VN),
        session_date="2026-09-22",
        mature=False,
    )
    assert early["steps"]["market_t0"]["status"] == BEFORE_CANONICAL_WINDOW
    assert early["close_scan_calls"] == 0
    assert later["steps"]["sweetspot"]["status"] == SAME_DAY_WINDOW_CLOSED
    assert later["close_scan_calls"] == 0


def test_schedule_stays_disabled_until_migration_is_ready(monkeypatch, capsys):
    from modules.post_close_finalize import main

    called = []
    monkeypatch.setattr(
        "modules.post_close_finalize.run_post_close_finalize",
        lambda: called.append("ran") or {"status": "RAN"},
    )
    monkeypatch.delenv("POST_CLOSE_RESEARCH_ENABLED", raising=False)
    main()
    assert "SCHEDULE_DISABLED" in capsys.readouterr().out
    assert called == []

    monkeypatch.setenv("POST_CLOSE_RESEARCH_ENABLED", "true")
    monkeypatch.setattr("modules.forward_ledger_store.authority_ready", lambda **_kwargs: False)
    main()
    assert "AUTHORITY_NOT_READY" in capsys.readouterr().out
    assert called == []

    monkeypatch.setattr("modules.forward_ledger_store.authority_ready", lambda **_kwargs: True)
    main()
    assert '"status": "RAN"' in capsys.readouterr().out
    assert called == ["ran"]
