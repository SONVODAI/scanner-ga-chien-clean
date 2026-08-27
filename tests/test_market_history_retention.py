"""Destructive-regression tests for Market history retention hardening."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# pattern_manager imports streamlit at module load — stub if absent.
if "streamlit" not in sys.modules:
    st_stub = types.ModuleType("streamlit")
    st_stub.secrets = MagicMock()
    st_stub.secrets.get = MagicMock(return_value=None)
    sys.modules["streamlit"] = st_stub

from modules.durable_csv import (
    assert_date_coverage_not_shrunk,
    atomic_write_csv,
    backup_dir_for,
    durable_replace_csv,
    unique_date10,
)
from modules.forecast_research.mdrr import persist_mdrr_record
from modules.forecast_research.p0_daily import enrich_p0_universe_foreign, persist_p0_record
from modules.forecast_research.t0_persistence import (
    load_outcomes_table,
    load_t0_table,
    persist_outcome_record,
    persist_t0_record,
)
import pattern_manager as pm


def _ph_row(date: str, symbol: str, time: str = "15:10:00", fc: float = 1.0) -> dict:
    return {
        "sample_id": f"{date}_{time}_{symbol}",
        "date": date,
        "time": time,
        "schema_version": "GENESIS_V24",
        "symbol": symbol,
        "market_real": 5.0,
        "market_forecast": fc,
        "market_regime": "TEST",
        "market_phase": None,
        "breadth_score": None,
        "is_ai": False,
        "is_leader": False,
        "is_earning": False,
        "is_final_decision": False,
        "group": "MUA EARLY",
        "price": 10.0,
        "total_score": 1.0,
        "E": 0,
        "R": 0,
        "O": 0,
        "S": 0,
        "RS": 0,
        "V": 0,
        "rsi14": 50.0,
        "ema9_ma20_slope": 0.1,
        "dist_from_ema9_pct": 0.0,
        "obv_status": "🟢",
        "volume": 1000,
        "vol_ma20": 1000,
        "green_2_confirm": False,
        "early_green2": False,
        "early_dry_green2": False,
        "warning": False,
        "rsi_bucket": None,
        "rs_bucket": None,
        "obv_bucket": None,
        "pattern_signature": None,
        "t1_return": None,
        "t3_return": None,
        "t5_return": None,
        "t10_return": None,
        "t1_win": None,
        "t3_win": None,
        "t5_win": None,
        "t10_win": None,
    }


def test_partial_in_memory_ph_update_cannot_erase_old_dates(tmp_path, monkeypatch):
    path = tmp_path / "pattern_history.csv"
    old = pd.DataFrame(
        [
            _ph_row("2026-07-02", "AAA"),
            _ph_row("2026-07-03", "BBB"),
            _ph_row("2026-08-01", "CCC"),
        ]
    )
    old.to_csv(path, index=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pm, "PATTERN_FILE", str(path))
    monkeypatch.setattr(pm, "get_github_token", lambda: None)

    # Incomplete in-memory frame — only today's row
    incomplete = pd.DataFrame([_ph_row("2026-08-24", "DDD")])
    status = pm.write_pattern_history(incomplete, path=str(path))
    assert status == "LOCAL_ONLY"

    saved = pd.read_csv(path)
    dates = unique_date10(saved, "date")
    assert "2026-07-02" in dates
    assert "2026-07-03" in dates
    assert "2026-08-01" in dates
    assert "2026-08-24" in dates
    assert len(dates) == 4


def test_date_coverage_shrink_refused_without_disk_union(tmp_path):
    path = tmp_path / "pattern_history.csv"
    existing = pd.DataFrame(
        [_ph_row("2026-07-02", "AAA"), _ph_row("2026-07-03", "BBB")]
    )
    existing.to_csv(path, index=False)
    proposed = pd.DataFrame([_ph_row("2026-08-24", "ZZZ")])
    reason = assert_date_coverage_not_shrunk(existing, proposed, date_col="date")
    assert reason is not None
    assert "DATE_COVERAGE_SHRINK" in reason

    ok, msg = durable_replace_csv(
        proposed, path, existing=existing, date_col="date", backup=False
    )
    assert ok is False
    assert "REFUSED" in msg
    # Prior file untouched
    still = pd.read_csv(path)
    assert unique_date10(still, "date") == {"2026-07-02", "2026-07-03"}


def test_interrupted_atomic_write_leaves_prior_file(tmp_path, monkeypatch):
    path = tmp_path / "pattern_history.csv"
    prior = pd.DataFrame([_ph_row("2026-07-02", "AAA")])
    prior.to_csv(path, index=False)
    prior_bytes = path.read_bytes()

    def boom(*_a, **_k):
        raise OSError("simulated crash before replace")

    monkeypatch.setattr("modules.durable_csv.os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_csv(pd.DataFrame([_ph_row("2026-08-24", "ZZZ")]), path)

    assert path.read_bytes() == prior_bytes


def test_same_day_ph_update_compatible(tmp_path, monkeypatch):
    path = tmp_path / "pattern_history.csv"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pm, "PATTERN_FILE", str(path))
    monkeypatch.setattr(pm, "get_github_token", lambda: None)

    first = pd.DataFrame([_ph_row("2026-08-24", "AAA", time="10:00:00", fc=1.0)])
    assert pm.write_pattern_history(first, path=str(path)) == "LOCAL_ONLY"
    second = pd.DataFrame([_ph_row("2026-08-24", "AAA", time="15:30:00", fc=2.0)])
    assert pm.write_pattern_history(second, path=str(path)) == "LOCAL_ONLY"

    saved = pd.read_csv(path)
    assert unique_date10(saved, "date") == {"2026-08-24"}
    # Distinct sample_ids preserved (multi-scan same day)
    assert saved["sample_id"].nunique() == 2


def test_ph_backup_created_and_bounded(tmp_path, monkeypatch):
    path = tmp_path / "pattern_history.csv"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pm, "PATTERN_FILE", str(path))
    monkeypatch.setattr(pm, "get_github_token", lambda: None)

    for i, d in enumerate(["2026-07-01", "2026-07-02", "2026-07-03"]):
        df = pd.DataFrame([_ph_row(d, f"S{i}")])
        # seed cumulative via write
        status = pm.write_pattern_history(df, path=str(path))
        assert status == "LOCAL_ONLY"

    bdir = backup_dir_for(path)
    assert bdir.exists()
    backups = list(bdir.glob("pattern_history_*.csv"))
    assert 1 <= len(backups) <= 5


def test_forecast_t0_immutable(tmp_path):
    data_dir = tmp_path / "forecast_research"
    rec = {
        "trade_date": "2026-08-20",
        "market_forecast": 2.0,
        "universe_count": 142,
        "completeness_status": "COMPLETE",
    }
    ok, reason = persist_t0_record(rec, data_dir=data_dir)
    # Integration retains durable_replace_csv + optional GitHub sync suffix (WRITTEN_*).
    assert ok and str(reason).startswith("WRITTEN")
    ok2, reason2 = persist_t0_record({**rec, "market_forecast": 9.9}, data_dir=data_dir)
    assert ok2 is False and reason2 == "ALREADY_FROZEN"
    t0 = load_t0_table(data_dir)
    assert len(t0) == 1
    assert float(t0.iloc[0]["market_forecast"]) == 2.0


def test_mdrr_immutable(tmp_path):
    data_dir = tmp_path / "forecast_research"
    rec = {
        "trade_date": "2026-08-20",
        "market_forecast": 1.5,
        "universe_count": 142,
        "completeness_status": "PARTIAL",
        "schema_version": "minimum_daily_research_record_v1",
    }
    ok, reason = persist_mdrr_record(rec, data_dir=data_dir)
    assert ok and reason == "WRITTEN"
    ok2, reason2 = persist_mdrr_record({**rec, "market_forecast": 0.1}, data_dir=data_dir)
    assert ok2 is False and reason2 == "ALREADY_PRESENT"


def test_p0_dates_not_silently_deleted(tmp_path):
    data_dir = tmp_path / "forecast_research"
    for d in ("2026-08-18", "2026-08-19", "2026-08-20"):
        ok, _ = persist_p0_record(
            {
                "trade_date": d,
                "completeness_status": "PARTIAL",
                "schema_version": "p0_market_memory_v2",
                "universe_foreign_net_value": None,
            },
            data_dir=data_dir,
        )
        assert ok
    # Enrich one row — must keep all dates
    ok, reason = enrich_p0_universe_foreign(
        {
            "trade_date": "2026-08-20",
            "universe_foreign_net_value": 1.0,
            "universe_foreign_completeness": "COMPLETE",
        },
        data_dir=data_dir,
        force=True,
    )
    assert ok and reason == "ENRICHED"
    from modules.forecast_research.p0_daily import load_p0_table

    p0 = load_p0_table(data_dir)
    assert unique_date10(p0, "trade_date") == {
        "2026-08-18",
        "2026-08-19",
        "2026-08-20",
    }


def test_forecast_outcomes_idempotent_by_trade_date_horizon(tmp_path):
    data_dir = tmp_path / "forecast_research"
    rec = {
        "trade_date": "2026-08-10",
        "horizon": 3,
        "xs_mean_return": 0.01,
        "outcome_schema_version": "forecast_outcomes_v1",
    }
    assert persist_outcome_record(rec, data_dir=data_dir)[0] is True
    assert persist_outcome_record({**rec, "xs_mean_return": 0.99}, data_dir=data_dir) == (
        False,
        "ALREADY_PRESENT",
    )
    assert persist_outcome_record({**rec, "horizon": 5}, data_dir=data_dir)[0] is True
    out = load_outcomes_table(data_dir)
    assert len(out) == 2
    assert set(zip(out["trade_date"].astype(str), out["horizon"].astype(int))) == {
        ("2026-08-10", 3),
        ("2026-08-10", 5),
    }


def test_schema_evolution_does_not_delete_old_t0(tmp_path):
    data_dir = tmp_path / "forecast_research"
    persist_t0_record(
        {"trade_date": "2026-08-01", "market_forecast": 1.0, "legacy_only": "x"},
        data_dir=data_dir,
    )
    persist_t0_record(
        {
            "trade_date": "2026-08-02",
            "market_forecast": 2.0,
            "new_column": "y",
            "universe_count": 142,
        },
        data_dir=data_dir,
    )
    t0 = load_t0_table(data_dir)
    assert len(t0) == 2
    assert set(t0["trade_date"].astype(str).str[:10]) == {"2026-08-01", "2026-08-02"}
    # First row still present even if later schema added columns
    assert float(t0[t0.trade_date.astype(str).str[:10] == "2026-08-01"].iloc[0]["market_forecast"]) == 1.0
