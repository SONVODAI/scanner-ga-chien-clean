"""
Forecast Memory × production daily orchestration integration tests.

Proves unattended timer path can preserve research memory without Streamlit,
with MDT0 gate and idempotent retry semantics.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (  # noqa: E402
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (  # noqa: E402
    BACKFILL_NON_FORWARD,
)
from modules.edge_research.opr_bridge.production_scheduling_contract import (  # noqa: E402
    build_scheduling_contract,
)
from modules.forecast_research.contract import COMPLETENESS_WAITING, EXPECTED_UNIVERSE_SIZE
from modules.forecast_research.daily_entrypoint import maybe_freeze_after_market_daily
from modules.forecast_research.production_daily_integration import (
    STAGE_WAITING,
    assess_mdt0_readiness,
    run_forecast_memory_daily_stage,
)
from modules.forecast_research.t0_persistence import load_outcomes_table, load_t0_table


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


def _write_ems(path: Path, trade_date: str, n: int = 142) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _synth_board(n, trade_date).to_csv(path, index=False)


def _write_mdt0(path: Path, trade_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "daily_snapshot_id": f"md-{trade_date}",
                "market_real": 7.0,
                "market_live": 6.5,
                "market_forecast": 4.0,
                "vnindex_close": 1200.0,
                "vnindex_open": 1190.0,
                "vnindex_high": 1210.0,
                "vnindex_low": 1185.0,
                "vnindex_volume": 1e9,
                "captured_at": f"{trade_date}T18:05:00+07:00",
            }
        ]
    ).to_csv(path, index=False)


def _mini_panel(dates: list[str], *, symbols: int = 8) -> pd.DataFrame:
    rows = []
    for d in dates:
        for i in range(symbols):
            rows.append(
                {
                    "trade_date": d,
                    "symbol": f"S{i:03d}",
                    "rs_spread": float(i - symbols / 2),
                    "t3_return": 0.01 * (i % 3 - 1),
                    "t5_return": 0.01 * (i % 5 - 2),
                    "t10_return": 0.01 * (i % 7 - 3),
                }
            )
    return pd.DataFrame(rows)


def _repo_layout(tmp: Path, trade_date: str, *, with_mdt0: bool) -> Path:
    ems = tmp / "data" / "earning_money_snapshots.csv"
    md = tmp / "data" / "earning_learning" / "market_daily_t0.csv"
    _write_ems(ems, trade_date)
    if with_mdt0:
        _write_mdt0(md, trade_date)
    (tmp / "data" / "forecast_research").mkdir(parents=True, exist_ok=True)
    return tmp


@pytest.fixture(autouse=True)
def _fast_p0_collect(monkeypatch):
    """Avoid live HSX/VCI network calls during integration tests."""

    def _fake(trade_date: str, *, data_dir=None):
        from modules.forecast_research.p0_daily import collect_p0_for_date

        return collect_p0_for_date(
            trade_date,
            data_dir=data_dir,
            collect_foreign=False,
        )

    monkeypatch.setattr(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        lambda trade_date, data_dir=None: _fake(trade_date, data_dir=data_dir),
    )


def test_mdt0_gate_missing_returns_waiting_no_t0(tmp_path: Path):
    repo = _repo_layout(tmp_path, "2026-08-24", with_mdt0=False)
    ems = repo / "data" / "earning_money_snapshots.csv"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    data_dir = repo / "data" / "forecast_research"

    ready, reason = assess_mdt0_readiness("2026-08-24", md_path=md)
    assert not ready
    assert reason == "canonical_mdt0_missing"

    stage = run_forecast_memory_daily_stage(
        "2026-08-24",
        data_dir=data_dir,
        ems_path=ems,
        md_path=md,
        require_mdt0=True,
    )
    assert stage["stage_disposition"] == STAGE_WAITING
    assert stage["forecast_t0"]["skipped"] is True
    assert load_t0_table(data_dir).empty


def test_mdt0_retry_succeeds_when_mdt0_appears(tmp_path: Path):
    trade_date = "2026-08-24"
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=False)
    ems = repo / "data" / "earning_money_snapshots.csv"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    data_dir = repo / "data" / "forecast_research"

    s1 = run_forecast_memory_daily_stage(
        trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
    )
    assert s1["stage_disposition"] == STAGE_WAITING
    assert load_t0_table(data_dir).empty

    _write_mdt0(md, trade_date)
    s2 = run_forecast_memory_daily_stage(
        trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
    )
    assert s2["stage_disposition"] == "SUCCESS"
    assert s2["forecast_t0"]["written"] is True
    t0 = load_t0_table(data_dir)
    assert len(t0) == 1
    assert int(t0.iloc[0]["universe_count"]) == EXPECTED_UNIVERSE_SIZE


def test_orchestrator_attaches_forecast_memory_without_streamlit(tmp_path: Path):
    trade_date = "2026-01-15"
    dates = [f"2026-01-{d:02d}" for d in range(1, 16)]
    panel = _mini_panel(dates)
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=True)
    edge_dir = tmp_path / "edge"

    result = run_production_daily_research(
        panel,
        target_trade_date=trade_date,
        run_mode=BACKFILL_NON_FORWARD,
        data_dir=edge_dir,
        repo_root=repo,
    )
    assert "forecast_memory" in result
    fm = result["forecast_memory"]
    assert fm.get("stage") == "forecast_memory"
    assert fm.get("stage_disposition") in ("SUCCESS", STAGE_WAITING)
    if fm.get("stage_disposition") == "SUCCESS":
        assert fm["forecast_t0"]["ok"] is True


def test_waiting_edge_run_still_retries_forecast_when_mdt0_later(tmp_path: Path):
    trade_date = "2026-01-15"
    early_dates = [f"2026-01-{d:02d}" for d in range(1, 11)]
    full_dates = [f"2026-01-{d:02d}" for d in range(1, 16)]
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=False)
    edge_dir = tmp_path / "edge"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    forecast_dir = repo / "data" / "forecast_research"

    r1 = run_production_daily_research(
        _mini_panel(early_dates),
        target_trade_date=trade_date,
        run_mode=BACKFILL_NON_FORWARD,
        data_dir=edge_dir,
        repo_root=repo,
    )
    assert r1["run"]["run_disposition"] == "WAITING_FOR_DATA"
    assert r1["forecast_memory"]["stage_disposition"] == STAGE_WAITING
    assert load_t0_table(forecast_dir).empty

    _write_mdt0(md, trade_date)
    r2 = run_production_daily_research(
        _mini_panel(full_dates),
        target_trade_date=trade_date,
        run_mode=BACKFILL_NON_FORWARD,
        data_dir=edge_dir,
        repo_root=repo,
    )
    assert r2["run"]["run_disposition"] == "SUCCESS"
    assert r2["forecast_memory"]["stage_disposition"] == "SUCCESS"
    assert len(load_t0_table(forecast_dir)) == 1


def test_streamlit_and_timer_paths_no_duplicate_t0(tmp_path: Path):
    trade_date = "2026-08-24"
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=True)
    ems = repo / "data" / "earning_money_snapshots.csv"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    data_dir = repo / "data" / "forecast_research"

    s1 = run_forecast_memory_daily_stage(
        trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
    )
    assert s1["forecast_t0"]["written"] is True

    hook = maybe_freeze_after_market_daily(trade_date, data_dir=data_dir, require_mdt0=False)
    assert hook["reason"] == "ALREADY_FROZEN"
    assert len(load_t0_table(data_dir)) == 1


def test_mdrr_p0_outcomes_idempotent_on_rerun(tmp_path: Path):
    trade_date = "2026-08-24"
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=True)
    ems = repo / "data" / "earning_money_snapshots.csv"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    data_dir = repo / "data" / "forecast_research"

    with patch(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        return_value={"ok": True, "written": True, "reason": "WRITTEN"},
    ):
        s1 = run_forecast_memory_daily_stage(
            trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
        )
        assert s1["mdrr"]["reason"] in ("WRITTEN", "ALREADY_PRESENT")

        s2 = run_forecast_memory_daily_stage(
            trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
        )
        assert s2["forecast_t0"]["reason"] == "ALREADY_FROZEN"
        assert s2["mdrr"]["reason"] == "ALREADY_PRESENT"
        assert load_t0_table(data_dir)["trade_date"].astype(str).str[:10].duplicated().sum() == 0


def test_p0_failure_does_not_block_t0_mdrr(tmp_path: Path):
    trade_date = "2026-08-24"
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=True)
    ems = repo / "data" / "earning_money_snapshots.csv"
    md = repo / "data" / "earning_learning" / "market_daily_t0.csv"
    data_dir = repo / "data" / "forecast_research"

    with patch(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        side_effect=RuntimeError("foreign_provider_down"),
    ):
        stage = run_forecast_memory_daily_stage(
            trade_date, data_dir=data_dir, ems_path=ems, md_path=md, require_mdt0=True
        )
    assert stage["forecast_t0"]["written"] is True
    assert stage["mdrr"]["ok"] is True
    assert "p0_hook_error" in str(stage["p0_market_memory"].get("reason", ""))


def test_p0_failure_does_not_crash_edge_orchestrator(tmp_path: Path):
    trade_date = "2026-01-15"
    dates = [f"2026-01-{d:02d}" for d in range(1, 16)]
    repo = _repo_layout(tmp_path, trade_date, with_mdt0=True)
    edge_dir = tmp_path / "edge"

    with patch(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        side_effect=RuntimeError("foreign_boom"),
    ):
        result = run_production_daily_research(
            _mini_panel(dates),
            target_trade_date=trade_date,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=edge_dir,
            repo_root=repo,
        )
    assert result["run"]["run_disposition"] == "SUCCESS"
    assert result["forecast_memory"]["forecast_t0"]["written"] is True
    assert "p0_hook_error" in str(result["forecast_memory"]["p0_market_memory"].get("reason", ""))


def test_no_second_forecast_timer_in_systemd():
    timer_files = list((REPO / "deploy" / "systemd").glob("*.timer"))
    names = {p.name for p in timer_files}
    assert "mrbot-daily-research.timer" in names
    assert not any("forecast" in n.lower() for n in names)


def test_scheduling_contract_unchanged_exit_codes():
    contract = build_scheduling_contract()
    assert contract["systemd_timer_unit"] == "mrbot-daily-research.timer"
    assert contract["exit_codes"]["2"] == "WAITING_FOR_DATA"
    assert contract["exit_codes"]["0"] == "SUCCESS or idempotent replay"


def test_import_smoke():
    from modules.forecast_research import contract  # noqa: F401
    from modules.forecast_research.p0_universe_foreign import UniverseForeignFlowCascade  # noqa: F401
    from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (  # noqa: F401
        run_production_daily_research,
    )

    assert UniverseForeignFlowCascade is not None
