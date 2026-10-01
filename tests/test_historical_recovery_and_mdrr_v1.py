"""Tests for historical FC recovery + MDRR V1 (no model training)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.forecast_research.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_WAITING,
    FORBIDDEN_OUTCOME_COLUMNS,
    QUALITY_LEAKAGE_RISK_SOURCE,
    QUALITY_NOT_PROVABLY_PIT_SAFE,
    QUALITY_PIT_RECONSTRUCTABLE,
    QUALITY_PIT_SAFE_COMPLETE,
)
from modules.forecast_research.historical_recovery import (
    assert_no_forbidden_outcome_fields,
    build_historical_record_for_date,
    is_weekday_session,
    load_historical_core,
    persist_historical_record,
    recover_all_historical,
    resolve_root_ph_fc,
)
from modules.forecast_research.mdrr import (
    build_mdrr_record,
    default_forward_only_registry,
    freeze_mdrr_for_date,
    load_mdrr_table,
    persist_mdrr_record,
    write_forward_only_registry,
)
from modules.forecast_research.t0_persistence import persist_t0_record
from modules.forecast_research.daily_entrypoint import freeze_trade_date


def test_no_fabricated_missing_live(tmp_path: Path):
    # buy_elite style minimal source without LIVE
    be = tmp_path / "be.csv"
    pd.DataFrame(
        [
            {"date": "2026-06-25", "time": "15:10:00", "symbol": "AAA", "market_forecast": 1.2, "market_real": 5.0},
            {"date": "2026-06-25", "time": "15:10:00", "symbol": "BBB", "market_forecast": 1.2, "market_real": 5.0},
        ]
    ).to_csv(be, index=False)
    # empty other sources
    empty_csv = tmp_path / "empty.csv"
    pd.DataFrame({"date": [], "market_forecast": []}).to_csv(empty_csv, index=False)
    ems = tmp_path / "ems.csv"
    pd.DataFrame({"snapshot_date": [], "symbol": [], "market_forecast": []}).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame({"trade_date": [], "market_forecast": []}).to_csv(md, index=False)

    rec = build_historical_record_for_date(
        "2026-06-25",
        root_ph=empty_csv,
        buy_elite=be,
        el_ph=empty_csv,
        ems=ems,
        mdt0=md,
        freeze=empty_csv,
    )
    assert rec is not None
    assert rec["fc"] == 1.2
    assert rec["market_real"] == 5.0
    assert rec["market_live"] is None
    assert rec["quality_tier"] == QUALITY_NOT_PROVABLY_PIT_SAFE


def test_multi_fc_ambiguity_without_post_close():
    day = pd.DataFrame(
        {
            "time": ["09:00:00", "10:00:00", "11:00:00"],
            "market_forecast": [1.0, 2.0, 3.0],
            "market_real": [5.0, 5.0, 5.0],
            "symbol": ["A", "B", "C"],
        }
    )
    resolved = resolve_root_ph_fc(day)
    assert resolved["fc_ambiguous"] is True
    assert resolved["fc"] is None
    assert len(resolved["fc_candidates"]) == 3


def test_multi_fc_last_post_close_rule():
    day = pd.DataFrame(
        {
            "time": ["09:30:00", "14:00:00", "15:10:00", "16:00:00"],
            "market_forecast": [1.0, 2.0, 3.5, 3.5],
            "market_real": [5.0, 5.0, 6.0, 6.0],
            "symbol": ["A", "B", "C", "D"],
        }
    )
    resolved = resolve_root_ph_fc(day)
    assert resolved["fc_ambiguous"] is False
    assert resolved["fc"] == 3.5
    assert resolved["snapshot_asof_time"] == "16:00:00"


def test_weekend_not_session():
    assert is_weekday_session("2026-08-09") is False  # Sunday
    assert is_weekday_session("2026-08-10") is True
    assert build_historical_record_for_date("2026-08-09") is None


def test_leakage_columns_never_enter_features():
    day = pd.DataFrame(
        {
            "date": ["2026-07-02"] * 3,
            "time": ["15:30:00"] * 3,
            "symbol": ["A", "B", "C"],
            "market_forecast": [1.4, 1.4, 1.4],
            "market_real": [6.9, 6.9, 6.9],
            "group": ["CP MẠNH", "THEO DÕI", "MUA BREAK"],
            "t3_return": [0.1, 0.2, 0.3],
            "t5_return": [0.1, 0.2, 0.3],
            "t10_win": [1, 0, 1],
        }
    )
    path = Path("/tmp/ph_leak.csv")
    day.to_csv(path, index=False)
    empty = Path("/tmp/empty_hist.csv")
    pd.DataFrame({"date": [], "market_forecast": []}).to_csv(empty, index=False)
    ems = Path("/tmp/ems_empty.csv")
    pd.DataFrame({"snapshot_date": [], "symbol": []}).to_csv(ems, index=False)
    md = Path("/tmp/md_empty.csv")
    pd.DataFrame({"trade_date": []}).to_csv(md, index=False)
    rec = build_historical_record_for_date(
        "2026-07-02",
        root_ph=path,
        buy_elite=empty,
        el_ph=empty,
        ems=ems,
        mdt0=md,
        freeze=empty,
    )
    assert rec is not None
    for col in FORBIDDEN_OUTCOME_COLUMNS:
        assert col not in rec
    assert rec["source_carries_leakage_columns"] is True
    assert rec["quality_tier"] == QUALITY_LEAKAGE_RISK_SOURCE
    assert_no_forbidden_outcome_fields(rec)


def test_recovery_deterministic_idempotent(tmp_path: Path):
    be = tmp_path / "be.csv"
    pd.DataFrame(
        [
            {"date": "2026-06-30", "time": "15:00:00", "symbol": "AAA", "market_forecast": 1.5, "market_real": 6.5},
        ]
    ).to_csv(be, index=False)
    empty = tmp_path / "empty.csv"
    pd.DataFrame({"date": []}).to_csv(empty, index=False)
    ems = tmp_path / "ems.csv"
    pd.DataFrame({"snapshot_date": [], "symbol": []}).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame({"trade_date": []}).to_csv(md, index=False)

    a = build_historical_record_for_date(
        "2026-06-30", root_ph=empty, buy_elite=be, el_ph=empty, ems=ems, mdt0=md, freeze=empty
    )
    b = build_historical_record_for_date(
        "2026-06-30", root_ph=empty, buy_elite=be, el_ph=empty, ems=ems, mdt0=md, freeze=empty
    )
    assert a["record_hash"] == b["record_hash"]
    data_dir = tmp_path / "fr"
    ok1, _ = persist_historical_record(a, data_dir=data_dir)
    ok2, reason = persist_historical_record(b, data_dir=data_dir)
    assert ok1 and not ok2 and reason == "ALREADY_PRESENT"
    assert len(load_historical_core(data_dir)) == 1


def test_quality_survives_persistence(tmp_path: Path):
    rec = {
        "trade_date": "2026-08-13",
        "fc": 1.7,
        "market_real": 7.0,
        "market_live": 8.6,
        "quality_tier": QUALITY_PIT_SAFE_COMPLETE,
        "fc_ambiguous": False,
        "fc_candidates_json": "[]",
        "reconstruction_method": "canonical_mdt0_copy",
        "primary_source": "market_daily_t0",
        "source_files_json": "[]",
        "source_hashes_json": "{}",
        "source_carries_leakage_columns": False,
        "schema_version": "historical_market_core_v1",
        "created_at": "2026-08-24T00:00:00Z",
        "record_hash": "abc",
        "universe_count": 142,
        "expected_universe_size": 142,
    }
    data_dir = tmp_path / "fr"
    persist_historical_record(rec, data_dir=data_dir)
    loaded = load_historical_core(data_dir)
    assert loaded.iloc[0]["quality_tier"] == QUALITY_PIT_SAFE_COMPLETE


def test_mdrr_no_future_outcomes(tmp_path: Path):
    # Build from empty → waiting
    ems = tmp_path / "ems.csv"
    pd.DataFrame({"snapshot_date": [], "symbol": []}).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame({"trade_date": []}).to_csv(md, index=False)
    rec, status = build_mdrr_record("2026-08-24", ems_path=ems, md_path=md)
    assert rec is None
    assert status == COMPLETENESS_WAITING

    # Synthetic complete-ish board
    rows = []
    groups = ["THEO DÕI", "CP MẠNH", "GÀ TĂNG TỐC", "MUA BREAK"]
    for i in range(142):
        rows.append(
            {
                "snapshot_date": "2026-08-24",
                "symbol": f"S{i:03d}",
                "group": groups[i % 4],
                "price": 100 + i,
                "rsi14": 50,
                "rs5": 1,
                "rs10": 1,
                "obv_status": "🟢",
                "ema9_ma20_slope": 0.1,
                "near_bottom_20_pct": 5,
                "near_bottom_60_pct": 5,
                "dist_high20_pct": -5,
                "market_real": 9.6,
                "market_live": 10.1,
                "market_forecast": 3.6,
            }
        )
    pd.DataFrame(rows).to_csv(ems, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-08-24",
                "market_real": 9.6,
                "market_live": 10.1,
                "market_forecast": 3.6,
                "vnindex_close": 1200,
                "captured_at": "2026-08-24T18:05:00+07:00",
                "daily_snapshot_id": "x",
            }
        ]
    ).to_csv(md, index=False)
    rec, status = build_mdrr_record("2026-08-24", ems_path=ems, md_path=md)
    assert status == COMPLETENESS_COMPLETE
    assert rec is not None
    for col in FORBIDDEN_OUTCOME_COLUMNS:
        assert col not in rec
    assert rec["outcomes_embedded"] is False
    assert rec["camera_coupled"] is False
    assert rec["foreign_net_flow"] is None
    assert rec["market_adv"] is None


def test_mdrr_immutable_idempotent(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    rows = [
        {
            "snapshot_date": "2026-08-21",
            "symbol": f"S{i:03d}",
            "group": "CP MẠNH",
            "price": 100,
            "rsi14": 55,
            "rs5": 1,
            "rs10": 1,
            "obv_status": "🟢",
            "ema9_ma20_slope": 0.1,
            "near_bottom_20_pct": 5,
            "near_bottom_60_pct": 5,
            "dist_high20_pct": -5,
            "market_real": 9.0,
            "market_live": 9.6,
            "market_forecast": 3.8,
        }
        for i in range(142)
    ]
    pd.DataFrame(rows).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-08-21",
                "market_real": 9.0,
                "market_live": 9.6,
                "market_forecast": 3.8,
                "captured_at": "2026-08-21T18:00:00+07:00",
                "daily_snapshot_id": "y",
            }
        ]
    ).to_csv(md, index=False)
    data_dir = tmp_path / "fr"
    r1 = freeze_mdrr_for_date("2026-08-21", data_dir=data_dir, ems_path=ems, md_path=md)
    r2 = freeze_mdrr_for_date("2026-08-21", data_dir=data_dir, ems_path=ems, md_path=md)
    assert r1["written"] and not r2["written"]
    assert r2["reason"] == "ALREADY_PRESENT"
    assert len(load_mdrr_table(data_dir)) == 1


def test_partial_waiting_gates(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    # partial universe
    rows = [
        {
            "snapshot_date": "2026-08-20",
            "symbol": f"S{i:03d}",
            "group": "THEO DÕI",
            "price": 100,
            "rsi14": 40,
            "rs5": 0,
            "rs10": 0,
            "obv_status": "🔴",
            "ema9_ma20_slope": -0.1,
            "near_bottom_20_pct": 1,
            "near_bottom_60_pct": 2,
            "dist_high20_pct": -10,
        }
        for i in range(50)
    ]
    pd.DataFrame(rows).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame({"trade_date": []}).to_csv(md, index=False)
    rec, status = build_mdrr_record("2026-08-20", ems_path=ems, md_path=md)
    assert status == COMPLETENESS_PARTIAL
    assert rec["universe_count"] == 50


def test_forward_only_not_fake_backfilled(tmp_path: Path):
    reg = default_forward_only_registry()
    for f in reg["fields"]:
        assert f["historical_backfill_availability"] is False or f["historical_backfill_availability"] == "partial via t0_observation_freeze sector"
        if f["feature"] in {"foreign_net_flow", "market_adv", "market_turnover"}:
            assert f["first_reliable_collection_date"] is None
            assert f["reconstruction_policy"].startswith("DO_NOT") or "DERIVE_LATER" in f["reconstruction_policy"]
    path = write_forward_only_registry(tmp_path / "fr")
    assert path.exists()


def test_outcomes_remain_separate_layer():
    from modules.forecast_research.contract import OUTCOMES_FILE, T0_FILE, MDRR_FILE, HISTORICAL_CORE_FILE

    assert OUTCOMES_FILE != T0_FILE
    assert OUTCOMES_FILE != MDRR_FILE
    assert OUTCOMES_FILE != HISTORICAL_CORE_FILE


def test_forecast_contract_unchanged_import():
    from modules.forecast_research.contract import CONTRACT_VERSION, EXPECTED_UNIVERSE_SIZE

    assert CONTRACT_VERSION == "forecast_data_contract_v1"
    assert EXPECTED_UNIVERSE_SIZE == 142


def test_market_first_and_edge_untouched_surface():
    # Import surfaces still exist; this task must not rewrite them.
    import modules.market_t0_capture as mtc

    assert callable(mtc.capture_market_t0_snapshot)
    # Edge research package import must still succeed
    import modules.edge_research  # noqa: F401


def test_camera_decoupled_in_mdrr(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    pd.DataFrame(
        [
            {
                "snapshot_date": "2026-08-19",
                "symbol": "AAA",
                "group": "CP MẠNH",
                "price": 1,
                "rsi14": 50,
                "rs5": 1,
                "rs10": 1,
                "obv_status": "🟢",
                "ema9_ma20_slope": 0.1,
                "near_bottom_20_pct": 5,
                "near_bottom_60_pct": 5,
                "dist_high20_pct": -5,
            }
        ]
    ).to_csv(ems, index=False)
    md = tmp_path / "md.csv"
    pd.DataFrame({"trade_date": []}).to_csv(md, index=False)
    rec, _ = build_mdrr_record("2026-08-19", ems_path=ems, md_path=md)
    assert rec["camera_coupled"] is False
