"""Forecast Data Contract V1 — data infrastructure tests (no model training)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.forecast_research.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_WAITING,
    EXPECTED_UNIVERSE_SIZE,
    MFE_MAE_BASIS,
    OUTCOME_HORIZONS,
)
from modules.forecast_research.daily_entrypoint import (
    freeze_trade_date,
    maybe_freeze_after_market_daily,
    run_daily_pipeline,
)
from modules.forecast_research.outcome_maturity import build_outcome_record, mature_all_outcomes
from modules.forecast_research.t0_builder import build_forecast_t0_record, build_t0_features_from_board
from modules.forecast_research.t0_persistence import load_outcomes_table, load_t0_table, persist_t0_record


def _synth_board(n: int, trade_date: str, price_base: float = 100.0) -> pd.DataFrame:
    groups = [
        "THEO DÕI",
        "TÍCH LŨY",
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "MUA BREAK",
        "CP MẠNH",
        "GÀ TĂNG TỐC",
    ]
    rows = []
    for i in range(n):
        rows.append(
            {
                "snapshot_date": trade_date,
                "symbol": f"S{i:03d}",
                "price": price_base * (1.0 + 0.001 * i),
                "group": groups[i % len(groups)],
                "rsi14": 35 + (i % 40),
                "rs5": (i % 11) - 5,
                "rs10": (i % 9) - 4,
                "obv_status": "🟢" if i % 2 == 0 else "🔴",
                "ema9_ma20_slope": 0.1 if i % 3 == 0 else -0.1,
                "near_bottom_20_pct": 1.0 if i % 5 == 0 else 10.0,
                "near_bottom_60_pct": 2.0 if i % 7 == 0 else 20.0,
                "dist_high20_pct": -1.0 if i % 6 == 0 else -15.0,
                "market_real": 7.0,
                "market_live": 6.5,
                "market_forecast": 4.0,
            }
        )
    return pd.DataFrame(rows)


def _write_ems(path: Path, dates_prices: list[tuple[str, float]], n: int = 142) -> None:
    frames = [_synth_board(n, d, price_base=p) for d, p in dates_prices]
    pd.concat(frames, ignore_index=True).to_csv(path, index=False)


def _write_mdt0(path: Path, dates: list[str]) -> None:
    rows = []
    for d in dates:
        rows.append(
            {
                "trade_date": d,
                "daily_snapshot_id": f"md-{d}",
                "market_real": 7.0,
                "market_live": 6.5,
                "market_forecast": 4.0,
                "vnindex_close": 1200.0,
                "vnindex_open": 1190.0,
                "vnindex_high": 1210.0,
                "vnindex_low": 1185.0,
                "vnindex_volume": 1e9,
                "captured_at": f"{d}T18:05:00+07:00",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_complete_142_t0_freeze(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    dates = [f"2026-08-{d:02d}" for d in range(1, 12)]
    _write_ems(ems, [(d, 100 + i) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    r = freeze_trade_date(dates[0], data_dir=data_dir, ems_path=ems, md_path=md)
    assert r["ok"] and r["written"]
    assert r["completeness_status"] == COMPLETENESS_COMPLETE
    assert r["universe_count"] == EXPECTED_UNIVERSE_SIZE


def test_immutable_t0_no_overwrite(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    _write_ems(ems, [("2026-08-01", 100.0)], n=142)
    _write_mdt0(md, ["2026-08-01"])
    r1 = freeze_trade_date("2026-08-01", data_dir=data_dir, ems_path=ems, md_path=md)
    assert r1["written"]
    hash1 = r1["feature_hash"]
    # mutate source board
    _write_ems(ems, [("2026-08-01", 200.0)], n=142)
    r2 = freeze_trade_date("2026-08-01", data_dir=data_dir, ems_path=ems, md_path=md)
    assert r2["ok"] and not r2["written"]
    assert r2["reason"] == "ALREADY_FROZEN"
    t0 = load_t0_table(data_dir)
    assert len(t0) == 1
    assert str(t0.iloc[0]["feature_hash"]) == hash1


def test_no_future_leakage_in_t0_features(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    dates = [f"2026-08-{d:02d}" for d in range(1, 6)]
    _write_ems(ems, [(d, 100 + i * 5) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    # Build day-1 with empty history — trajectories nan
    rec, status = build_forecast_t0_record(dates[0], ems_path=ems, md_path=md, prior_t0_history=None)
    assert status == COMPLETENESS_COMPLETE
    assert rec is not None
    assert pd.isna(rec["market_forecast_d1"])
    # Outcome fields must not exist on T0
    for bad in ("xs_mean_return", "mfe", "mae", "label_up", "vni_return"):
        assert bad not in rec


def test_trading_session_maturity_t3_t5_t10(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    # 11 trading sessions
    dates = [f"2026-08-{d:02d}" for d in range(1, 12)]
    _write_ems(ems, [(d, 100 + i) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    for d in dates:
        freeze_trade_date(d, data_dir=data_dir, ems_path=ems, md_path=md)
    out = mature_all_outcomes(data_dir=data_dir, ems_path=ems, md_path=md)
    assert out["written"] > 0
    outcomes = load_outcomes_table(data_dir)
    # First date should have T3, T5, T10
    first = outcomes[outcomes["trade_date"].astype(str) == dates[0]]
    assert set(int(x) for x in first["horizon"]) == set(OUTCOME_HORIZONS)
    assert first.iloc[0]["mfe_mae_basis"] == MFE_MAE_BASIS
    # Last date should have no outcomes yet
    last = outcomes[outcomes["trade_date"].astype(str) == dates[-1]]
    assert last.empty


def test_idempotent_maturity_rerun(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    dates = [f"2026-08-{d:02d}" for d in range(1, 12)]
    _write_ems(ems, [(d, 100 + i) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    for d in dates:
        freeze_trade_date(d, data_dir=data_dir, ems_path=ems, md_path=md)
    a = mature_all_outcomes(data_dir=data_dir, ems_path=ems, md_path=md)
    n1 = len(load_outcomes_table(data_dir))
    b = mature_all_outcomes(data_dir=data_dir, ems_path=ems, md_path=md)
    n2 = len(load_outcomes_table(data_dir))
    assert n1 == n2
    assert b["written"] == 0
    assert a["written"] > 0


def test_incomplete_partial_and_waiting(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    _write_ems(ems, [("2026-08-01", 100.0)], n=50)
    # no MDT0
    r = freeze_trade_date("2026-08-01", data_dir=data_dir, ems_path=ems, md_path=md)
    assert r["ok"] and r["written"]
    assert r["completeness_status"] == COMPLETENESS_PARTIAL
    assert r["universe_count"] == 50
    # waiting: no sources for date
    w = freeze_trade_date("2099-01-01", data_dir=data_dir, ems_path=ems, md_path=md)
    assert not w["written"]
    assert w["reason"] == COMPLETENESS_WAITING


def test_outcomes_do_not_mutate_t0(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    dates = [f"2026-08-{d:02d}" for d in range(1, 8)]
    _write_ems(ems, [(d, 100 + i) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    for d in dates:
        freeze_trade_date(d, data_dir=data_dir, ems_path=ems, md_path=md)
    before = load_t0_table(data_dir).copy()
    mature_all_outcomes(data_dir=data_dir, ems_path=ems, md_path=md)
    after = load_t0_table(data_dir)
    assert list(before.columns) == list(after.columns)
    assert before.equals(after)


def test_hook_fail_safe_and_streamlit_independent(tmp_path: Path):
    # Streamlit independence: run_daily_pipeline is a CLI callable
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    data_dir = tmp_path / "forecast"
    dates = [f"2026-08-{d:02d}" for d in range(1, 6)]
    _write_ems(ems, [(d, 100 + i) for i, d in enumerate(dates)], n=142)
    _write_mdt0(md, dates)
    status = run_daily_pipeline(
        trade_date=None,
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        mature=True,
        write_matrix=True,
    )
    assert status["freeze"]["written"] == len(dates)
    # hook never raises even with bad dir handled internally
    bad = maybe_freeze_after_market_daily("2026-08-01", data_dir=data_dir)
    assert bad["ok"] is True
    assert bad["written"] is False  # already frozen


def test_provenance_hash_stable_for_same_features(tmp_path: Path):
    ems = tmp_path / "ems.csv"
    md = tmp_path / "md.csv"
    _write_ems(ems, [("2026-08-01", 100.0)], n=142)
    _write_mdt0(md, ["2026-08-01"])
    a, _ = build_forecast_t0_record("2026-08-01", ems_path=ems, md_path=md)
    b, _ = build_forecast_t0_record("2026-08-01", ems_path=ems, md_path=md)
    assert a["feature_hash"] == b["feature_hash"]


def test_market_t0_capture_exports_hook_path():
    """Ensure capture module still imports after Forecast hook wiring."""
    import modules.market_t0_capture as mtc

    assert callable(mtc.capture_market_t0_snapshot)
    assert callable(mtc._persist_canonical_daily_t0)
