"""P0 forward market memory tests — missing ≠ 0, PIT derivation, immutability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import pytest

from modules.forecast_research.contract import (
    P0_COMPLETENESS_SOURCE_ERROR,
)
from modules.forecast_research.mdrr import freeze_mdrr_for_date, load_mdrr_table
from modules.forecast_research.p0_daily import (
    build_p0_record,
    collect_p0_for_date,
    derive_avg_turnover_from_p0,
    load_p0_table,
    maybe_collect_p0_after_market_daily,
    persist_p0_record,
    update_forward_only_registry_from_p0,
)
from modules.forecast_research.p0_indicators import indicators_asof, rsi14
from modules.forecast_research.p0_providers import ProviderResult


@dataclass
class MockForeignOK:
    buy: float
    sell: float

    def fetch(self, trade_date: str) -> ProviderResult:
        return ProviderResult(
            ok=True,
            status="OK",
            values={
                "universe_foreign_buy_value": self.buy,
                "universe_foreign_sell_value": self.sell,
                "universe_foreign_net_value": self.buy - self.sell,
                "universe_foreign_buy_volume": 10.0,
                "universe_foreign_sell_volume": 4.0,
                "universe_foreign_net_volume": 6.0,
            },
            meta={
                "provider": "mock",
                "completeness": "COMPLETE",
                "expected_count": 142,
                "observed_count": 142,
                "completeness_ratio": 1.0,
                "units": "VND",
            },
        )


@dataclass
class MockForeignError:
    def fetch(self, trade_date: str) -> ProviderResult:
        return ProviderResult(ok=False, status="SOURCE_ERROR", error="blocked", meta={"provider": "mock"})


@dataclass
class MockForeignMissing:
    def fetch(self, trade_date: str) -> ProviderResult:
        return ProviderResult(ok=False, status="MISSING", error="empty", meta={"provider": "mock"})


@dataclass
class MockHistory:
    df: pd.DataFrame

    def fetch_ohlcv(self, end_date: str, lookback_days: int = 120) -> pd.DataFrame:
        return self.df.copy()


def _write_ems(path: Path, trade_date: str, n: int = 142, price: float = 100.0, volume: float = 1000.0) -> None:
    rows = []
    for i in range(n):
        rows.append(
            {
                "snapshot_date": trade_date,
                "symbol": f"S{i:03d}",
                "price": price + i,
                "volume": volume,
                "group": "CP MẠNH",
                "rsi14": 50,
                "rs5": 1,
                "rs10": 1,
                "obv_status": "🟢",
                "ema9_ma20_slope": 0.1,
                "near_bottom_20_pct": 5,
                "near_bottom_60_pct": 5,
                "dist_high20_pct": -5,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _vni_hist(n: int = 40, end: str = "2026-08-24") -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=n)
    close = pd.Series(np.linspace(1700, 1800, n))
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": close - 5,
            "high": close + 5,
            "low": close - 10,
            "close": close,
            "volume": np.full(n, 1e8),
        }
    )


def test_foreign_buy_sell_net_consistent(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    _write_ems(ems, "2026-08-24")
    pd.DataFrame(
        [{"trade_date": "2026-08-24", "vnindex_volume": 8e8, "vnindex_close": 1788.0}]
    ).to_csv(md, index=False)
    rec = build_p0_record(
        "2026-08-24",
        data_dir=tmp_path / "fr",
        ems_path=ems,
        md_path=md,
        foreign_provider=MockForeignOK(100.0, 40.0),
        history_provider=MockHistory(_vni_hist()),
    )
    assert rec is not None
    assert rec["universe_foreign_buy_value"] == 100.0
    assert rec["universe_foreign_sell_value"] == 40.0
    assert rec["universe_foreign_net_value"] == 60.0
    assert rec["universe_foreign_units"] == "VND"
    assert rec["universe_foreign_scope"] == "EMS_RESEARCH_UNIVERSE_142"
    # Legacy HOSE-SSI fields stay null
    assert rec["foreign_buy_value"] is None


def test_missing_foreign_not_zero(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    _write_ems(ems, "2026-08-24")
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 8e8}]).to_csv(md, index=False)
    for provider in (MockForeignError(), MockForeignMissing()):
        rec = build_p0_record(
            "2026-08-24",
            data_dir=tmp_path / "fr",
            ems_path=ems,
            md_path=md,
            foreign_provider=provider,
            history_provider=MockHistory(_vni_hist()),
        )
        assert rec["universe_foreign_buy_value"] is None
        assert rec["universe_foreign_sell_value"] is None
        assert rec["universe_foreign_net_value"] is None
        assert rec["universe_foreign_buy_value"] != 0
        assert rec["market_turnover_value"] is None  # official market turnover unavailable


def test_missing_turnover_not_zero(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    # board without volume → missing turnover
    pd.DataFrame(
        [{"snapshot_date": "2026-08-24", "symbol": "AAA", "price": 10.0, "group": "CP MẠNH"}]
    ).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 1.0}]).to_csv(md, index=False)
    rec = build_p0_record(
        "2026-08-24",
        data_dir=tmp_path / "fr",
        ems_path=ems,
        md_path=md,
        foreign_provider=MockForeignOK(1, 1),
        history_provider=MockHistory(_vni_hist()),
    )
    assert rec["universe_turnover_value"] is None
    assert rec["universe_turnover_value"] != 0


def test_idempotent_no_duplicate(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "fr"
    _write_ems(ems, "2026-08-24")
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 8e8}]).to_csv(md, index=False)
    kw = dict(
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        foreign_provider=MockForeignOK(10, 3),
        history_provider=MockHistory(_vni_hist()),
    )
    r1 = collect_p0_for_date("2026-08-24", **kw)
    r2 = collect_p0_for_date("2026-08-24", **kw)
    assert r1["written"] and not r2["written"]
    assert r2["reason"] == "ALREADY_PRESENT"
    assert len(load_p0_table(data_dir)) == 1


def test_forward_only_null_before_collection(tmp_path: Path):
    data_dir = tmp_path / "fr"
    path = update_forward_only_registry_from_p0(data_dir=data_dir)
    import json

    reg = json.loads(path.read_text())
    for f in reg["fields"]:
        if f["feature"] in ("foreign_net_flow", "foreign_buy", "foreign_sell"):
            assert f["first_reliable_collection_date"] is None


def test_avg_turnover_pit_only(tmp_path: Path):
    data_dir = tmp_path / "fr"
    # seed prior days
    for i, d in enumerate(["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"]):
        persist_p0_record(
            {
                "trade_date": d,
                "universe_turnover_value": 100.0 * (i + 1),
                "schema_version": "p0_market_memory_v1",
                "completeness_status": "PARTIAL",
                "record_hash": f"h{i}",
                "created_at": "2026-08-24T00:00:00Z",
            },
            data_dir=data_dir,
        )
    # current day value 600; window 5 needs prior 4 + current
    av = derive_avg_turnover_from_p0("2026-08-25", 600.0, data_dir=data_dir)
    # prior persisted: 100,200,300,400,500 then current 600 → last 5 of series including current
    # series from prior dates < 08-25: 100..500 + 600 = 6 values; avg5 = mean(200,300,400,500,600)=400
    assert av["avg_turnover_value_5"] == pytest.approx(400.0)
    assert av["avg_turnover_value_20"] is None  # not enough history


def test_vnindex_tech_no_future_bars():
    closes = pd.Series(np.linspace(100, 150, 60))
    # Truncated asof must equal computing on prefix only
    trunc = indicators_asof(closes, 40)
    prefix_rsi = rsi14(closes.iloc[:41]).iloc[-1]
    assert trunc["vnindex_rsi14"] is not None
    assert trunc["vnindex_rsi14"] == pytest.approx(float(prefix_rsi), rel=1e-9)
    # Extending future bars must not change asof-40 result
    extended = pd.concat([closes, pd.Series([200.0, 210.0])], ignore_index=True)
    trunc2 = indicators_asof(extended, 40)
    assert trunc2["vnindex_rsi14"] == trunc["vnindex_rsi14"]
    assert trunc2["vnindex_macd"] == trunc["vnindex_macd"]


def test_tech_deterministic():
    closes = pd.Series(np.linspace(100, 120, 50))
    a = indicators_asof(closes, 49)
    b = indicators_asof(closes, 49)
    assert a == b


def test_mdrr_immutability_preserved(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "fr"
    _write_ems(ems, "2026-08-24")
    pd.DataFrame(
        [
            {
                "trade_date": "2026-08-24",
                "market_real": 9.6,
                "market_live": 10.1,
                "market_forecast": 3.6,
                "vnindex_volume": 8e8,
                "vnindex_close": 1788,
                "captured_at": "2026-08-24T18:00:00+07:00",
                "daily_snapshot_id": "z",
            }
        ]
    ).to_csv(md, index=False)
    freeze_mdrr_for_date("2026-08-24", data_dir=data_dir, ems_path=ems, md_path=md)
    before = load_mdrr_table(data_dir).copy()
    collect_p0_for_date(
        "2026-08-24",
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        foreign_provider=MockForeignOK(1, 1),
        history_provider=MockHistory(_vni_hist()),
    )
    after = load_mdrr_table(data_dir)
    assert before.equals(after)
    assert "foreign_net_value" not in before.columns or before["foreign_net_flow"].isna().all()


def test_hook_fail_safe(tmp_path: Path, monkeypatch):
    # Prevent real HSX/VCI network from the default cascade
    from modules.forecast_research import p0_daily as p0_daily_mod

    def _fake_collect(trade_date, **kwargs):
        return {"ok": True, "written": False, "reason": "stub"}

    monkeypatch.setattr(p0_daily_mod, "collect_p0_for_date", _fake_collect)
    out = maybe_collect_p0_after_market_daily("2026-08-24", data_dir=tmp_path / "fr")
    assert out.get("ok") is True
    assert out.get("reason") == "stub"


def test_market_first_forecast_edge_surfaces_untouched():
    import modules.market_t0_capture as mtc
    import modules.edge_research  # noqa: F401
    from modules.forecast_research.contract import CONTRACT_VERSION

    assert callable(mtc.capture_market_t0_snapshot)
    assert CONTRACT_VERSION == "forecast_data_contract_v1"


def test_genuine_zero_foreign_allowed(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    _write_ems(ems, "2026-08-24")
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 1.0}]).to_csv(md, index=False)
    rec = build_p0_record(
        "2026-08-24",
        data_dir=tmp_path / "fr",
        ems_path=ems,
        md_path=md,
        foreign_provider=MockForeignOK(0.0, 0.0),
        history_provider=MockHistory(_vni_hist()),
    )
    assert rec["universe_foreign_buy_value"] == 0.0
    assert rec["universe_foreign_sell_value"] == 0.0
    assert rec["universe_foreign_net_value"] == 0.0
