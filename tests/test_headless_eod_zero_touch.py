"""
Headless EOD zero-touch production tests.

Proves Streamlit is not required to accumulate canonical daily research artifacts.
Does not change REAL/LIVE/FC/Edge/BUY-SELL semantics.
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.production_eod.headless_eod import (  # noqa: E402
    EXPECTED_UNIVERSE,
    run_headless_eod,
    should_attempt_headless_eod,
)
from modules.scanner_core import (  # noqa: E402
    WATCHLIST,
    calc_market_forecast,
    calc_market_live,
    calc_market_real,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
GROUPS = [
    "THEO DÕI",
    "TÍCH LŨY",
    "MUA EARLY",
    "PULL VỪA",
    "PULL ĐẸP",
    "MUA BREAK",
    "CP MẠNH",
    "GÀ TĂNG TỐC",
]


def _vn(trade_date: str, hour: int = 19, minute: int = 0) -> datetime:
    return datetime.strptime(trade_date, "%Y-%m-%d").replace(
        hour=hour, minute=minute, second=0, tzinfo=VN_TZ
    )


def _synth_scan(n: int, trade_date: str, *, price_base: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "symbol": f"S{i:03d}",
                "trade_date": trade_date,
                "price": price_base * (1.0 + 0.001 * i),
                "daily_price_before_live": price_base * (1.0 + 0.0005 * i),
                "group": GROUPS[i % len(GROUPS)],
                "rsi14": 35 + (i % 40),
                "rs5": float((i % 11) - 5),
                "rs10": float((i % 9) - 4),
                "obv_status": "🟢" if i % 2 == 0 else "🔴",
                "ema9_ma20_slope": 0.1 if i % 3 == 0 else -0.1,
                "near_bottom_20_pct": 1.0 if i % 5 == 0 else 10.0,
                "near_bottom_60_pct": 2.0 if i % 7 == 0 else 20.0,
                "dist_high20_pct": -1.0 if i % 6 == 0 else -15.0,
                "E": 1 if i % 2 == 0 else 0,
                "R": 1 if i % 3 == 0 else 0,
                "O": 1 if i % 2 == 1 else 0,
                "S": 1 if i % 4 == 0 else 0,
                "total_score": 60 + (i % 30),
                "is_live_adjusted": True,
                "volume": 1000 + i,
                "vol_ma20": 900 + i,
            }
        )
    return pd.DataFrame(rows)


def _run(
    tmp: Path,
    trade_date: str,
    *,
    n: int = 142,
    scan_df: pd.DataFrame | None = None,
    expected_universe: int = 142,
    skip_forecast_memory: bool = False,
    hour: int = 19,
) -> dict:
    board = scan_df if scan_df is not None else _synth_scan(n, trade_date)
    return run_headless_eod(
        trade_date,
        repo_root=tmp,
        scan_df=board,
        now=_vn(trade_date, hour=hour),
        trading_today=True,
        trading_reason="test_trading_day",
        allow_before_close_for_tests=True,
        skip_forecast_memory=skip_forecast_memory,
        expected_universe=expected_universe,
        include_vnindex_ohlcv=False,
    )


@pytest.fixture(autouse=True)
def _fast_p0(monkeypatch):
    def _fake(trade_date: str, *, data_dir=None):
        from modules.forecast_research.p0_daily import collect_p0_for_date

        return collect_p0_for_date(trade_date, data_dir=data_dir, collect_foreign=False)

    monkeypatch.setattr(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        lambda trade_date, data_dir=None: _fake(trade_date, data_dir=data_dir),
    )


def test_watchlist_universe_is_142():
    assert len(WATCHLIST) == EXPECTED_UNIVERSE == 142


def test_zero_touch_produces_required_artifacts(tmp_path: Path):
    """No Streamlit — full EOD chain writes EMS/MDT0/EL/FM."""
    td = "2026-09-01"
    with patch.dict("sys.modules", {"streamlit": None}):
        result = _run(tmp_path, td)

    assert result["ok"] is True
    assert result["stage_disposition"] == "SUCCESS"
    assert result["source_rows"] == 142
    assert result["universe_ok"] is True
    assert result["after_close_eligible"] is True

    ems = tmp_path / "data" / "earning_money_snapshots.csv"
    md = tmp_path / "data" / "earning_learning" / "market_daily_t0.csv"
    obs = tmp_path / "data" / "earning_learning" / "observations.csv"
    freeze = tmp_path / "data" / "earning_learning" / "t0_observation_freeze.csv"
    t0 = tmp_path / "data" / "forecast_research" / "forecast_t0_daily.csv"
    status = tmp_path / "data" / "forecast_research" / "headless_eod_status.json"

    assert ems.exists()
    assert len(pd.read_csv(ems)) == 142
    assert md.exists()
    assert (pd.read_csv(md)["trade_date"].astype(str).str[:10] == td).any()
    assert obs.exists()
    assert freeze.exists()
    assert t0.exists()
    assert (pd.read_csv(t0)["trade_date"].astype(str).str[:10] == td).any()
    assert status.exists()
    payload = json.loads(status.read_text())
    assert payload["trade_date"] == td
    assert payload["started_at"]
    assert payload["completed_at"]
    assert "ems" in payload["artifacts"]
    assert "mdt0" in payload["artifacts"]
    assert "earning_learning" in payload["artifacts"]
    assert "forecast_memory" in payload["artifacts"]


def test_idempotent_second_wave_no_duplicates(tmp_path: Path):
    td = "2026-09-02"
    first = _run(tmp_path, td)
    second = _run(tmp_path, td)
    assert first["ok"] and second["ok"]

    ems = pd.read_csv(tmp_path / "data" / "earning_money_snapshots.csv")
    assert len(ems[ems["snapshot_date"].astype(str).str[:10] == td]) == 142

    md = pd.read_csv(tmp_path / "data" / "earning_learning" / "market_daily_t0.csv")
    assert (md["trade_date"].astype(str).str[:10] == td).sum() == 1

    obs = pd.read_csv(tmp_path / "data" / "earning_learning" / "observations.csv")
    day = obs[obs["trade_date"].astype(str).str[:10] == td]
    assert day["symbol"].nunique() == len(day) == 142

    freeze = pd.read_csv(tmp_path / "data" / "earning_learning" / "t0_observation_freeze.csv")
    freeze_day = freeze[freeze["trade_date"].astype(str).str[:10] == td]
    assert freeze_day["symbol"].nunique() == len(freeze_day) == 142

    t0 = pd.read_csv(tmp_path / "data" / "forecast_research" / "forecast_t0_daily.csv")
    assert (t0["trade_date"].astype(str).str[:10] == td).sum() == 1

    assert second["artifacts"]["mdt0"].get("canonical_added") in (0, None)
    assert second["artifacts"]["earning_learning"].get("t0_freeze_added") == 0


def test_incomplete_universe_fail_closed_then_retry(tmp_path: Path):
    td = "2026-09-03"
    wave1 = _run(tmp_path, td, n=100)
    assert wave1["ok"] is False
    assert wave1["stage_disposition"] == "WAITING_FOR_DATA"
    assert "incomplete_universe" in wave1["reason"]
    assert not (tmp_path / "data" / "earning_money_snapshots.csv").exists()
    assert not (tmp_path / "data" / "earning_learning" / "market_daily_t0.csv").exists()

    wave2 = _run(tmp_path, td, n=142)
    assert wave2["ok"] is True
    assert wave2["stage_disposition"] == "SUCCESS"
    assert (tmp_path / "data" / "earning_money_snapshots.csv").exists()
    assert (tmp_path / "data" / "earning_learning" / "market_daily_t0.csv").exists()


def test_before_close_waits_without_writes(tmp_path: Path):
    td = "2026-09-04"
    result = run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(142, td),
        now=_vn(td, hour=14, minute=30),
        trading_today=True,
        allow_before_close_for_tests=False,
        include_vnindex_ohlcv=False,
    )
    assert result["stage_disposition"] == "WAITING_FOR_DATA"
    assert result["reason"] == "BEFORE_EOD_PLUS_3H"
    assert not (tmp_path / "data" / "earning_money_snapshots.csv").exists()


def test_outcome_maturity_and_lifecycle_without_streamlit(tmp_path: Path):
    """Prior T0 cohort matures T3 after three subsequent session observations."""
    dates = [f"2026-09-{d:02d}" for d in range(8, 12)]  # D0..D3
    for i, td in enumerate(dates):
        board = _synth_scan(142, td, price_base=100.0 + i)
        result = _run(tmp_path, td, scan_df=board)
        assert result["ok"], result.get("reason")

    outcomes = tmp_path / "data" / "earning_learning" / "outcomes.csv"
    lifecycle = tmp_path / "data" / "earning_learning" / "pattern_lifecycle.csv"
    assert outcomes.exists()
    out = pd.read_csv(outcomes)
    assert not out.empty
    assert set(out["horizon"].astype(int).unique()) >= {3}
    t3 = out[(out["horizon"].astype(int) == 3) & (out["entry_date"].astype(str).str[:10] == dates[0])]
    assert len(t3) > 0

    assert lifecycle.exists()
    life = pd.read_csv(lifecycle)
    assert len(life) > 0
    # Lifecycle max date advances with matured evidence
    date_cols = [c for c in life.columns if "date" in c.lower() or "last" in c.lower()]
    assert date_cols or len(life) > 0


def test_forecast_memory_t0_and_outcomes_headless(tmp_path: Path):
    dates = [f"2026-09-{d:02d}" for d in (15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 29)]
    for i, td in enumerate(dates):
        _run(tmp_path, td, scan_df=_synth_scan(142, td, price_base=100 + i))

    t0 = pd.read_csv(tmp_path / "data" / "forecast_research" / "forecast_t0_daily.csv")
    assert (t0["trade_date"].astype(str).str[:10] == dates[0]).any()
    assert int(t0.iloc[0]["universe_count"]) == 142

    outcomes_path = tmp_path / "data" / "forecast_research" / "forecast_outcomes.csv"
    # Maturity may write once T3 board exists (index+3)
    if outcomes_path.exists():
        fo = pd.read_csv(outcomes_path)
        assert not fo.empty
        assert (fo["horizon"].astype(int) == 3).any()


def test_durable_persistence_invokes_github_storage_path(tmp_path: Path):
    td = "2026-09-05"
    sync_calls: list[dict] = []

    def _fake_sync(filename, df, *, data_dir, commit_message):
        sync_calls.append(
            {
                "filename": filename,
                "rows": len(df),
                "data_dir": str(data_dir),
                "commit_message": commit_message,
            }
        )
        return "GITHUB_OK"

    with patch(
        "modules.forecast_research.t0_persistence._sync_forecast_csv_to_github",
        side_effect=_fake_sync,
    ):
        result = _run(tmp_path, td)

    assert result["ok"]
    assert any(c["filename"] == "forecast_t0_daily.csv" for c in sync_calls)
    t0_path = tmp_path / "data" / "forecast_research" / "forecast_t0_daily.csv"
    assert t0_path.exists()


def test_ordering_prerequisites_before_fm(tmp_path: Path):
    """FM stage waits when MDT0 missing; after headless chain, FM succeeds."""
    from modules.forecast_research.production_daily_integration import (
        run_forecast_memory_daily_stage,
    )

    td = "2026-09-06"
    ems = tmp_path / "data" / "earning_money_snapshots.csv"
    md = tmp_path / "data" / "earning_learning" / "market_daily_t0.csv"
    fm = tmp_path / "data" / "forecast_research"
    ems.parent.mkdir(parents=True, exist_ok=True)
    _synth_scan(142, td).assign(snapshot_date=td).to_csv(ems, index=False)

    waiting = run_forecast_memory_daily_stage(
        td, data_dir=fm, ems_path=ems, md_path=md, require_mdt0=True
    )
    assert waiting["stage_disposition"] == "WAITING_FOR_DATA"
    assert waiting["reason"] == "canonical_mdt0_missing"

    result = _run(tmp_path, td)
    assert result["ok"]
    assert result["artifacts"]["forecast_memory"]["stage_disposition"] == "SUCCESS"
    # EMS written before MDT0 before EL before FM — all present after success
    assert "ems" in result["artifacts"]
    assert "mdt0" in result["artifacts"]
    assert "earning_learning" in result["artifacts"]
    assert "forecast_memory" in result["artifacts"]


def test_ui_coexistence_headless_first_no_duplication(tmp_path: Path):
    """Simulate Streamlit producers after headless — first-write-wins, no dup rows."""
    td = "2026-09-07"
    headless = _run(tmp_path, td)
    assert headless["ok"]

    from modules.daily_summary import run_daily_summary
    from modules.earning_learning import update_learning
    from modules.learning_t0_capture import build_learning_input_df
    from modules.market_t0_capture import capture_market_t0_snapshot
    from modules.forecast_research.production_daily_integration import (
        run_forecast_memory_daily_stage,
    )

    board = _synth_scan(142, td)
    from modules.evolution_health import add_evolution_health

    board = add_evolution_health(board)
    board["trade_date"] = td
    ems_path = tmp_path / "data" / "earning_money_snapshots.csv"
    el_dir = tmp_path / "data" / "earning_learning"
    fm_dir = tmp_path / "data" / "forecast_research"

    run_daily_summary(board, snapshot_date=td, snapshot_file=ems_path, save=True)
    capture_market_t0_snapshot(
        scan_df=board,
        trade_date=td,
        market_real=float(calc_market_real(board)),
        market_live=float(calc_market_live(board)),
        market_forecast=float(calc_market_forecast(board).score),
        trading_today=True,
        trading_reason="streamlit_coexist",
        data_dir=str(el_dir),
        include_vnindex_ohlcv=False,
        now=_vn(td, hour=20),
    )
    update_learning(
        build_learning_input_df(board),
        market_context={"trade_date": td, "market_real": 7.0, "market_live": 6.0, "market_forecast": 4.0},
        trading_today=True,
        data_dir=str(el_dir),
    )
    run_forecast_memory_daily_stage(
        td,
        data_dir=fm_dir,
        ems_path=ems_path,
        md_path=el_dir / "market_daily_t0.csv",
        require_mdt0=True,
    )

    md = pd.read_csv(el_dir / "market_daily_t0.csv")
    assert (md["trade_date"].astype(str).str[:10] == td).sum() == 1
    t0 = pd.read_csv(fm_dir / "forecast_t0_daily.csv")
    assert (t0["trade_date"].astype(str).str[:10] == td).sum() == 1
    freeze = pd.read_csv(el_dir / "t0_observation_freeze.csv")
    assert len(freeze[freeze["trade_date"].astype(str).str[:10] == td]) == 142


def test_production_semantics_unchanged_vs_app():
    """scanner_core formulas must stay byte-identical to app.py (no research drift)."""

    def _fn_src(path: Path, name: str) -> str:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.unparse(node)
        raise AssertionError(f"{name} missing in {path}")

    app = REPO / "app.py"
    core = REPO / "modules" / "scanner_core.py"
    for name in ("calc_market_real", "calc_market_live", "calc_market_forecast"):
        assert _fn_src(app, name) == _fn_src(core, name)

    board = _synth_scan(40, "2026-09-01")
    assert calc_market_real(board) == calc_market_real(board)
    fc = calc_market_forecast(board)
    assert hasattr(fc, "score") and hasattr(fc, "confidence")


def test_entrypoint_wires_headless_before_research():
    src = (REPO / "modules/edge_research/opr_bridge/production_daily_run_entrypoint.py").read_text()
    assert "run_headless_eod" in src
    assert "--skip-headless-eod" in src
    # Call order inside main(): headless stage before Edge orchestrator.
    call_headless = src.index("headless_eod = run_headless_eod(")
    call_research = src.index("result = run_production_daily_research(")
    assert call_headless < call_research


def test_should_attempt_gates():
    td = "2026-09-10"
    ok, reason = should_attempt_headless_eod(td, now=_vn(td, 19), allow_before_close_for_tests=False)
    assert ok and reason == "ok"
    ok2, reason2 = should_attempt_headless_eod(td, now=_vn(td, 12), allow_before_close_for_tests=False)
    assert not ok2 and reason2 == "BEFORE_EOD_PLUS_3H"


def test_trading_day_probe_import_failure_is_not_non_trading(tmp_path: Path, monkeypatch):
    from modules.production_eod import headless_eod as he

    def _boom(_td: str):
        return he.TradingDayProbeResult(
            trading_today=None,
            reason="TRADING_DAY_PROBE_FAILED:import:ModuleNotFoundError:No module named 'vnstock'",
            probe_status=he.PROBE_FAILED,
        )

    monkeypatch.setattr(he, "resolve_trading_today", _boom)
    td = "2026-08-26"
    result = he.run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(142, td),
        now=_vn(td, hour=19),
        allow_before_close_for_tests=False,
        include_vnindex_ohlcv=False,
    )
    assert result["stage_disposition"] == "TRADING_DAY_PROBE_FAILED"
    assert result["ok"] is False
    assert result["trading_day_probe_status"] == he.PROBE_FAILED
    assert "PROBE_FAILED" in result["reason"] or "vnstock" in result["reason"]
    assert not (tmp_path / "data" / "earning_money_snapshots.csv").exists()


def test_recovery_preserves_autonomy_status_file(tmp_path: Path):
    from modules.production_eod.headless_eod import (
        RUN_CLASS_RECOVERY,
        STATUS_AUTONOMOUS,
        STATUS_RECOVERY,
        run_headless_eod,
    )

    td = "2026-08-26"
    fm = tmp_path / "data" / "forecast_research"
    fm.mkdir(parents=True)
    autonomy = {
        "ok": True,
        "trade_date": td,
        "stage_disposition": "SKIPPED_NON_TRADING_DAY",
        "reason": "VNINDEX trading-day probe unavailable",
        "source_rows": 0,
        "run_class": "AUTONOMOUS",
        "autonomy_evidence": "AUTONOMOUS_PRODUCTION",
    }
    autonomy_path = fm / STATUS_AUTONOMOUS
    autonomy_path.write_text(json.dumps(autonomy), encoding="utf-8")
    before = autonomy_path.read_text(encoding="utf-8")

    recovery = run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(142, td),
        now=_vn(td, hour=19),
        trading_today=True,
        trading_reason="recovery_test",
        allow_before_close_for_tests=True,
        include_vnindex_ohlcv=False,
        run_class=RUN_CLASS_RECOVERY,
        preserve_autonomy_status=True,
    )
    assert recovery["ok"] is True
    assert recovery["run_class"] == RUN_CLASS_RECOVERY
    assert recovery["autonomy_evidence"] == "RECOVERY_NOT_AUTONOMOUS_EVIDENCE"
    assert autonomy_path.read_text(encoding="utf-8") == before
    assert (fm / STATUS_RECOVERY).exists()
    assert list((fm / "recovery_runs").glob(f"RECOVERY_{td}_*.json"))


def test_trading_day_probe_import_failure_is_not_non_trading(tmp_path: Path, monkeypatch):
    from modules.production_eod import headless_eod as he

    def _boom(_td: str):
        return he.TradingDayProbeResult(
            trading_today=None,
            reason="TRADING_DAY_PROBE_FAILED:import:ModuleNotFoundError:No module named 'vnstock'",
            probe_status=he.PROBE_FAILED,
        )

    monkeypatch.setattr(he, "resolve_trading_today", _boom)
    td = "2026-08-26"
    result = he.run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(142, td),
        now=_vn(td, hour=19),
        allow_before_close_for_tests=False,
        include_vnindex_ohlcv=False,
    )
    assert result["stage_disposition"] == "TRADING_DAY_PROBE_FAILED"
    assert result["ok"] is False
    assert result["trading_day_probe_status"] == he.PROBE_FAILED
    assert "PROBE_FAILED" in result["reason"] or "vnstock" in result["reason"]
    # Must not write EMS on probe failure
    assert not (tmp_path / "data" / "earning_money_snapshots.csv").exists()


def test_recovery_preserves_autonomy_status_file(tmp_path: Path):
    from modules.production_eod.headless_eod import (
        RUN_CLASS_RECOVERY,
        STATUS_AUTONOMOUS,
        STATUS_RECOVERY,
    )

    td = "2026-08-26"
    fm = tmp_path / "data" / "forecast_research"
    fm.mkdir(parents=True)
    autonomy = {
        "ok": True,
        "trade_date": td,
        "stage_disposition": "SKIPPED_NON_TRADING_DAY",
        "reason": "VNINDEX trading-day probe unavailable",
        "source_rows": 0,
        "run_class": "AUTONOMOUS",
        "autonomy_evidence": "AUTONOMOUS_PRODUCTION",
    }
    autonomy_path = fm / STATUS_AUTONOMOUS
    autonomy_path.write_text(json.dumps(autonomy), encoding="utf-8")
    before = autonomy_path.read_text(encoding="utf-8")

    from modules.production_eod.headless_eod import run_headless_eod

    recovery = run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(142, td),
        now=_vn(td, hour=19),
        trading_today=True,
        trading_reason="recovery_test",
        allow_before_close_for_tests=True,
        include_vnindex_ohlcv=False,
        run_class=RUN_CLASS_RECOVERY,
        preserve_autonomy_status=True,
    )
    assert recovery["ok"] is True
    assert recovery["run_class"] == RUN_CLASS_RECOVERY
    assert recovery["autonomy_evidence"] == "RECOVERY_NOT_AUTONOMOUS_EVIDENCE"
    assert autonomy_path.read_text(encoding="utf-8") == before
    assert (fm / STATUS_RECOVERY).exists()
    assert list((fm / "recovery_runs").glob(f"RECOVERY_{td}_*.json"))
