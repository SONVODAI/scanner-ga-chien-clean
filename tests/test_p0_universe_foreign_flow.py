"""Universe-142 foreign flow — HSX primary, VCI fallback, membership-asof."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest

from modules.forecast_research.contract import (
    P0_COMPLETENESS_COMPLETE,
    P0_COMPLETENESS_PARTIAL,
    P0_UNIVERSE_FOREIGN_SCOPE,
)
from modules.forecast_research.p0_daily import build_p0_record, collect_p0_for_date, load_p0_table
from modules.forecast_research.p0_universe_foreign import (
    HsXUniverseForeignProvider,
    UniverseForeignFlowCascade,
    VciUniverseForeignProvider,
    aggregate_symbol_rows,
    ems_universe_symbols,
    parse_hsx_foreign_payload,
    row_for_exact_date,
)


def _ts(day: str) -> int:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def _hsx_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"data": {"list": rows}, "success": True}


def _sym_row(day: str, buy: float, sell: float, buy_vol: float = 1.0, sell_vol: float = 1.0) -> Dict[str, Any]:
    return {
        "reportDate": _ts(day),
        "mainBuyerForeignValue": buy,
        "mainSellerForeignValue": sell,
        "bigLotBuyerForeignValue": 0.0,
        "bigLotSellerForeignValue": 0.0,
        "mainBuyerForeignVolume": buy_vol,
        "mainSellerForeignVolume": sell_vol,
        "bigLotBuyerForeignVolume": 0.0,
        "bigLotSellerForeignVolume": 0.0,
    }


def _write_ems(path: Path, trade_date: str, symbols: List[str]) -> None:
    rows = [{"snapshot_date": trade_date, "symbol": s, "price": 10.0, "volume": 100.0, "group": "CP MẠNH"} for s in symbols]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_parse_hsx_units_vnd_and_net():
    payload = _hsx_payload([_sym_row("2026-08-24", 53104069800.0, 22934880000.0)])
    rows = parse_hsx_foreign_payload(payload)
    assert len(rows) == 1
    assert rows[0]["report_date"] == "2026-08-24"
    assert rows[0]["units"] == "VND"
    assert rows[0]["foreign_net_value"] == pytest.approx(53104069800.0 - 22934880000.0)


def test_wrong_date_rejected():
    rows = parse_hsx_foreign_payload(_hsx_payload([_sym_row("2026-08-21", 100.0, 40.0)]))
    assert row_for_exact_date(rows, "2026-08-24") is None
    agg = aggregate_symbol_rows(
        "2026-08-24",
        ["AAA"],
        {"AAA": rows},
        source="hsx_official_foreign",
    )
    assert agg.values["universe_foreign_net_value"] is None
    assert agg.meta["completeness"] != P0_COMPLETENESS_COMPLETE


def test_membership_asof_from_ems(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    _write_ems(ems, "2026-08-20", ["AAA", "BBB"])
    _write_ems_append = pd.read_csv(ems)
    extra = pd.DataFrame(
        [{"snapshot_date": "2026-08-21", "symbol": s, "price": 1.0, "volume": 1.0, "group": "CP MẠNH"} for s in ["AAA", "BBB", "CCC"]]
    )
    pd.concat([_write_ems_append, extra], ignore_index=True).to_csv(ems, index=False)
    assert ems_universe_symbols("2026-08-20", ems_path=ems) == ["AAA", "BBB"]
    assert ems_universe_symbols("2026-08-21", ems_path=ems) == ["AAA", "BBB", "CCC"]
    assert ems_universe_symbols("2026-08-22", ems_path=ems) == []


def test_incomplete_cannot_be_complete():
    per = {
        "AAA": parse_hsx_foreign_payload(_hsx_payload([_sym_row("2026-08-24", 100.0, 40.0)])),
        "BBB": [],  # missing
    }
    agg = aggregate_symbol_rows("2026-08-24", ["AAA", "BBB"], per, source="hsx")
    assert agg.ok
    assert agg.meta["completeness"] == P0_COMPLETENESS_PARTIAL
    assert agg.meta["observed_count"] == 1
    assert agg.meta["expected_count"] == 2
    assert "BBB" in agg.meta["missing_symbols"]
    assert agg.values["universe_foreign_net_value"] == pytest.approx(60.0)


def test_complete_requires_all_symbols():
    per = {
        "AAA": parse_hsx_foreign_payload(_hsx_payload([_sym_row("2026-08-24", 100.0, 40.0)])),
        "BBB": parse_hsx_foreign_payload(_hsx_payload([_sym_row("2026-08-24", 10.0, 5.0)])),
    }
    agg = aggregate_symbol_rows("2026-08-24", ["AAA", "BBB"], per, source="hsx")
    assert agg.meta["completeness"] == P0_COMPLETENESS_COMPLETE
    assert agg.values["universe_foreign_buy_value"] == 110.0
    assert agg.values["universe_foreign_sell_value"] == 45.0
    assert agg.values["universe_foreign_net_value"] == 65.0


def test_hsx_provider_fixture(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    symbols = ["AAA", "BBB"]
    _write_ems(ems, "2026-08-24", symbols)

    def get_json(url: str) -> Dict[str, Any]:
        sym = url.rstrip("/").split("/")[-1].split("?")[0]
        return _hsx_payload([_sym_row("2026-08-24", 1000.0 if sym == "AAA" else 200.0, 100.0)])

    provider = HsXUniverseForeignProvider(ems_path=ems, get_json=get_json, sleep_s=0.0)
    out = provider.fetch("2026-08-24")
    assert out.ok
    assert out.meta["completeness"] == P0_COMPLETENESS_COMPLETE
    assert out.meta["scope"] == P0_UNIVERSE_FOREIGN_SCOPE
    assert out.meta["units"] == "VND"
    assert out.values["universe_foreign_net_value"] == pytest.approx((1000 - 100) + (200 - 100))


def test_vci_rejects_historical_session(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    _write_ems(ems, "2026-08-20", ["AAA"])

    def board(symbols: List[str]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "listing_symbol": "AAA",
                    "listing_trading_date": "2026-08-24",  # live board is today-ish, not 08-20
                    "match_foreign_buy_value": 100.0,
                    "match_foreign_sell_value": 40.0,
                }
            ]
        )

    vci = VciUniverseForeignProvider(ems_path=ems, price_board_fn=board, session_today="2026-08-24")
    out = vci.fetch("2026-08-20")
    assert not out.ok
    assert "vci_session_date_mismatch" in (out.error or "")
    assert out.values.get("universe_foreign_net_value") in (None, {})


def test_vci_forward_only_ok(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    _write_ems(ems, "2026-08-24", ["AAA", "BBB"])

    def board(symbols: List[str]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "listing_symbol": s,
                    "listing_trading_date": "2026-08-24",
                    "match_foreign_buy_value": 50.0,
                    "match_foreign_sell_value": 20.0,
                    "match_foreign_buy_volume": 1.0,
                    "match_foreign_sell_volume": 1.0,
                }
                for s in symbols
            ]
        )

    vci = VciUniverseForeignProvider(ems_path=ems, price_board_fn=board, session_today="2026-08-24")
    out = vci.fetch("2026-08-24")
    assert out.ok
    assert out.meta["historical_capability"] == "FORWARD_ONLY"
    assert out.meta["completeness"] == P0_COMPLETENESS_COMPLETE
    assert out.values["universe_foreign_net_value"] == pytest.approx(60.0)


def test_cascade_hsx_then_vci(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    _write_ems(ems, "2026-08-24", ["AAA"])

    def get_json(_url: str) -> Dict[str, Any]:
        raise RuntimeError("hsx_down")

    def board(symbols: List[str]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "listing_symbol": "AAA",
                    "listing_trading_date": "2026-08-24",
                    "match_foreign_buy_value": 80.0,
                    "match_foreign_sell_value": 30.0,
                }
            ]
        )

    cascade = UniverseForeignFlowCascade(
        hsx=HsXUniverseForeignProvider(ems_path=ems, get_json=get_json, sleep_s=0.0),
        vci=VciUniverseForeignProvider(ems_path=ems, price_board_fn=board, session_today="2026-08-24"),
        enable_cross_check=False,
    )
    out = cascade.fetch("2026-08-24")
    assert out.ok
    assert out.meta.get("source_hierarchy") == "VCI_FALLBACK"
    assert out.values["universe_foreign_net_value"] == 50.0


def test_missing_never_zero_and_provenance(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    _write_ems(ems, "2026-08-24", [f"S{i:03d}" for i in range(142)])
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 1e8}]).to_csv(md, index=False)

    def get_json(_url: str) -> Dict[str, Any]:
        return _hsx_payload([])  # no rows

    cascade = UniverseForeignFlowCascade(
        hsx=HsXUniverseForeignProvider(ems_path=ems, get_json=get_json, sleep_s=0.0),
        vci=VciUniverseForeignProvider(
            ems_path=ems,
            price_board_fn=lambda _s: pd.DataFrame(),
            session_today="2026-08-24",
        ),
        enable_cross_check=False,
    )
    rec = build_p0_record(
        "2026-08-24",
        data_dir=tmp_path / "fr",
        ems_path=ems,
        md_path=md,
        foreign_provider=cascade,
    )
    assert rec["universe_foreign_net_value"] is None
    assert rec["universe_foreign_net_value"] != 0
    prov = json.loads(rec["provenance_json"])
    assert "universe_foreign" in prov


def test_enrichment_idempotent(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "fr"
    _write_ems(ems, "2026-08-24", ["AAA", "BBB"])
    pd.DataFrame([{"trade_date": "2026-08-24", "vnindex_volume": 1e8}]).to_csv(md, index=False)

    # First write without foreign
    def empty_json(_url: str) -> Dict[str, Any]:
        return _hsx_payload([])

    cascade_empty = UniverseForeignFlowCascade(
        hsx=HsXUniverseForeignProvider(ems_path=ems, get_json=empty_json, sleep_s=0.0),
        vci=VciUniverseForeignProvider(ems_path=ems, price_board_fn=lambda _s: pd.DataFrame(), session_today="2026-08-24"),
        enable_cross_check=False,
    )
    r1 = collect_p0_for_date(
        "2026-08-24",
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        foreign_provider=cascade_empty,
        collect_foreign=True,
    )
    assert r1["written"]
    assert pd.isna(load_p0_table(data_dir).iloc[0].get("universe_foreign_net_value"))

    def ok_json(url: str) -> Dict[str, Any]:
        return _hsx_payload([_sym_row("2026-08-24", 100.0, 40.0)])

    cascade_ok = UniverseForeignFlowCascade(
        hsx=HsXUniverseForeignProvider(ems_path=ems, get_json=ok_json, sleep_s=0.0),
        vci=VciUniverseForeignProvider(ems_path=ems, price_board_fn=lambda _s: pd.DataFrame(), session_today="2026-08-24"),
        enable_cross_check=False,
    )
    r2 = collect_p0_for_date(
        "2026-08-24",
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        foreign_provider=cascade_ok,
    )
    assert r2["reason"] == "ENRICHED"
    assert r2["written"]
    table = load_p0_table(data_dir)
    assert len(table) == 1
    assert table.iloc[0]["universe_foreign_net_value"] == pytest.approx(120.0)  # 2 symbols × 60

    r3 = collect_p0_for_date(
        "2026-08-24",
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        foreign_provider=cascade_ok,
    )
    assert r3["reason"] == "ALREADY_PRESENT"
    assert not r3["written"]
