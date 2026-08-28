"""Deterministic tests for daily pipeline lock, I/O bounds, and ABC receipt truthfulness."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.closed_loop_daily_hook import (
    SKIP_LOCK_HELD,
    SKIP_NON_TRADING_DAY,
    SKIP_T0_NOT_READY,
    run_closed_loop_edge_after_daily,
)
from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)
from modules.edge_research.opr_bridge.production_daily_run_entrypoint import LOCK_HELD_EXIT, main
from modules.edge_research.opr_bridge.production_run_lock import (
    acquire_run_lock,
    is_lock_stale,
    lock_path,
    release_run_lock,
)
from modules.foreign_flow_confirmation.daily import ingest_trade_date
from modules.foreign_flow_history.hsx_client import ProviderTransientError, fetch_with_retries
from modules.forecast_research.p0_universe_foreign import HsXUniverseForeignProvider
from modules.production_daily_receipt import (
    OVERALL_FAIL,
    PIPELINE_TERMINATED,
    build_daily_pipeline_receipt,
    write_incomplete_pipeline_receipt,
)
from modules.production_io_bounds import (
    HSX_MAX_RETRIES,
    P0_UNIVERSE_FOREIGN_STAGE_BUDGET_SEC,
    expected_runtime_envelope,
)
from tests.test_p0_universe_foreign_flow import _write_ems

REPO = Path(__file__).resolve().parents[1]


def test_systemd_timeout_is_safety_ceiling_not_one_hour():
    svc = (REPO / "deploy/systemd/mrbot-daily-research.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=5400" in svc
    assert "TimeoutStartSec=3600" not in svc
    env = expected_runtime_envelope()
    assert env["systemd_safety_timeout_sec"] == 5400
    assert env["hard_upper_bound_sec"] < env["systemd_safety_timeout_sec"]
    assert env["degraded_provider_expected_sec"] <= env["hard_upper_bound_sec"]
    assert P0_UNIVERSE_FOREIGN_STAGE_BUDGET_SEC == 480.0


def test_lock_live_pid_never_stale():
    meta = {"pid": os.getpid(), "acquired_at": "2000-01-01T00:00:00+00:00"}
    assert is_lock_stale(meta, stale_seconds=1) is False
    dead = {"pid": 999999999, "acquired_at": "2000-01-01T00:00:00+00:00"}
    assert is_lock_stale(dead) is True


def test_lock_contention_second_use_lock_exits_before_any_work(tmp_path, monkeypatch):
    data_dir = tmp_path / "edge"
    fh, res = acquire_run_lock(run_id="holder", data_dir=data_dir)
    assert res.acquired is True
    called: list[str] = []

    def _mark(name):
        def _inner(*_a, **_k):
            called.append(name)
            raise AssertionError(f"{name} must not run while lock is held")

        return _inner

    monkeypatch.setattr("modules.production_eod.headless_eod.run_headless_eod", _mark("headless"))
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.build_research_panel",
        _mark("panel"),
    )
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.run_production_daily_research",
        _mark("opr"),
    )
    try:
        rc = main(
            [
                "--trade-date",
                "2026-08-28",
                "--mode",
                "LIVE_FORWARD",
                "--use-lock",
                "--data-dir",
                str(data_dir),
            ]
        )
        assert rc == LOCK_HELD_EXIT
        assert called == []
    finally:
        release_run_lock(fh, data_dir=data_dir)


def test_lock_cleanup_on_normal_completion(tmp_path, monkeypatch):
    data_dir = tmp_path / "edge"
    monkeypatch.setattr(
        "modules.production_eod.headless_eod.run_headless_eod",
        lambda *a, **k: {
            "ok": True,
            "skipped": True,
            "reason": "test_stub",
            "stage_disposition": "SUCCESS",
            "forecast_memory": {"skipped": True, "reason": "test_stub"},
        },
    )
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.build_research_panel",
        lambda **k: pd.DataFrame({"trade_date": ["2026-08-28"], "symbol": ["AAA"]}),
    )
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.diagnose_panel_freshness",
        lambda *a, **k: {"target_in_panel_sessions": True},
    )
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.run_production_daily_research",
        lambda *a, **k: {
            "run": {"run_disposition": "SUCCESS"},
            "closed_loop_edge": {
                "ran_science": True,
                "system_status": "SUCCESS",
                "assessment_state": ASSESSMENT_NO_QUALIFIED_MATCH,
                "assessment_reason": REASON_NO_ACTIVE_EDGE_AVAILABLE,
            },
        },
    )
    monkeypatch.setattr(
        "modules.production_daily_receipt.write_receipt_from_run",
        lambda *a, **k: {"ok": True, "receipt": {"overall": "PASS", "closed_loop_complete": True}},
    )
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.publish_production_observations_durable",
        lambda **k: {"ok": True, "skipped": True},
    )
    rc = main(
        [
            "--trade-date",
            "2026-08-28",
            "--mode",
            "BACKFILL_NON_FORWARD",
            "--use-lock",
            "--data-dir",
            str(data_dir),
        ]
    )
    assert rc == 0
    assert not lock_path(data_dir).exists()


def test_lock_cleanup_on_exception(tmp_path, monkeypatch):
    data_dir = tmp_path / "edge"

    def _boom(*_a, **_k):
        raise RuntimeError("panel boom")

    monkeypatch.setattr(
        "modules.production_eod.headless_eod.run_headless_eod",
        lambda *a, **k: {"ok": True, "stage_disposition": "SUCCESS", "skipped": False},
    )
    monkeypatch.setattr(
        "modules.edge_research.opr_bridge.production_daily_run_entrypoint.build_research_panel",
        _boom,
    )
    with pytest.raises(RuntimeError, match="panel boom"):
        main(
            [
                "--trade-date",
                "2026-08-28",
                "--mode",
                "BACKFILL_NON_FORWARD",
                "--use-lock",
                "--data-dir",
                str(data_dir),
                "--skip-headless-eod",
            ]
        )
    assert not lock_path(data_dir).exists()


def test_lock_cleanup_on_sigterm_handler(tmp_path):
    from modules.edge_research.opr_bridge import production_daily_run_entrypoint as ep

    data_dir = tmp_path / "edge"
    fh, res = acquire_run_lock(run_id="term-test", data_dir=data_dir)
    assert res.acquired
    ep._LOCK_CTX.update(
        {
            "fh": fh,
            "data_dir": data_dir,
            "repo_root": tmp_path,
            "trade_date": "2026-08-28",
            "released": False,
            "headless_eod": {"stage_disposition": "SUCCESS"},
            "edge_result": None,
        }
    )
    ep._write_terminated_receipt("PIPELINE_TERMINATED_BEFORE_COMPLETE:SIGTERM", "pipeline_wall_clock")
    ep._release_entrypoint_lock()
    assert not lock_path(data_dir).exists()
    receipt_path = tmp_path / "data" / "production_daily_receipts" / "2026-08-28.json"
    assert receipt_path.exists()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["overall"] == OVERALL_FAIL
    assert payload["pipeline_terminated"] is True
    assert payload["closed_loop_complete"] is False
    assert payload["reason"] == "PIPELINE_TERMINATED_BEFORE_COMPLETE:SIGTERM"
    assert payload["closed_loop_edge"]["ran_science"] is False
    assert payload["closed_loop_edge"].get("assessment_state") != ASSESSMENT_NO_QUALIFIED_MATCH


def test_slow_hsx_provider_respects_stage_budget(tmp_path):
    ems = tmp_path / "ems.csv"
    symbols = [f"S{i:03d}" for i in range(20)]
    _write_ems(ems, "2026-08-28", symbols)
    clock = {"t": 0.0}

    def time_fn() -> float:
        return clock["t"]

    calls: list[str] = []

    def get_json(url: str):
        calls.append(url)
        clock["t"] += 10.0
        raise TimeoutError("Read timed out")

    provider = HsXUniverseForeignProvider(
        ems_path=ems,
        get_json=get_json,
        sleep_s=0.0,
        stage_budget_sec=25.0,
        time_fn=time_fn,
    )
    result = provider.fetch("2026-08-28")
    io = result.meta["io_summary"]
    assert io["budget_exhausted"] is True
    assert io["target"] == 20
    assert len(calls) <= 3
    assert io["skipped"] >= 17
    assert io["elapsed_s"] <= 30.0
    assert result.values.get("universe_foreign_net_value") is None


def test_fetch_with_retries_is_bounded():
    sleeps: list[float] = []

    def opener(_req, timeout):
        raise ProviderTransientError("simulated timeout")

    with pytest.raises(ProviderTransientError):
        fetch_with_retries(
            "https://api.hsx.vn/x",
            timeout_sec=8.0,
            max_retries=HSX_MAX_RETRIES,
            backoff_base_sec=1.0,
            opener=opener,
            sleeper=sleeps.append,
        )
    assert HSX_MAX_RETRIES == 1
    assert len(sleeps) == 1
    assert sleeps[0] == 1.0


def test_ff_ingest_stage_budget_stops_without_hanging(tmp_path):
    clock = {"t": 0.0}

    def time_fn() -> float:
        return clock["t"]

    calls: list[str] = []

    def fetch_fn(symbol, trade_date, **_k):
        calls.append(str(symbol))
        clock["t"] += 8.0
        return {"ok": False, "reason": "provider_transient", "errors": ["Read timed out"], "rows": []}

    out = ingest_trade_date(
        "2026-08-28",
        confirmation_root=tmp_path / "ff",
        symbols=["AAA", "ACB", "VNM", "FPT", "HPG", "VIC", "MSN", "VCB"],
        fetch_fn=fetch_fn,
        stage_budget_sec=20.0,
        time_fn=time_fn,
    )
    assert out["budget_exhausted"] is True
    assert len(calls) <= 3
    assert out["n_skipped_budget"] >= 5
    assert out["reason"] == "stage_budget_exhausted"
    assert out["elapsed_s"] <= 24.0


def test_optional_ff_failure_does_not_kill_abc(tmp_path, monkeypatch):
    from modules.edge_research.storage import ensure_storage

    edge = tmp_path / "edge"
    edge.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
    repo = tmp_path / "repo"
    el = repo / "data" / "earning_learning"
    el.mkdir(parents=True)
    pd.DataFrame(
        {
            "trade_date": ["2026-01-15"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
            "market_real": 4.0,
        }
    ).to_csv(el / "t0_observation_freeze.csv", index=False)
    ensure_storage(edge)
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-01-15",
        daily_result={
            "run": {"run_disposition": "SUCCESS"},
            "forecast_memory": {
                "ok": True,
                "ff_confirmation_forward": {"ok": False, "reason": "provider_transient"},
                "p0_market_memory": {"ok": False, "reason": "all_symbol_fetches_failed"},
            },
        },
        repo_root=repo,
        data_dir=edge,
    )
    assert out["ran_science"] is True
    assert out["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert out["assessment_reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE


def test_required_missing_t0_is_unable_or_skip_not_no_match(tmp_path, monkeypatch):
    edge = tmp_path / "edge"
    edge.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
    repo = tmp_path / "repo"
    (repo / "data" / "earning_learning").mkdir(parents=True)
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-08-28",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge,
    )
    assert out["ran_science"] is False
    assert out["skip_reason"] == SKIP_T0_NOT_READY
    assert out.get("assessment_state") != ASSESSMENT_NO_QUALIFIED_MATCH


def test_abc_order_and_no_active_and_non_trading(tmp_path, monkeypatch):
    from modules.edge_research.storage import ensure_storage, read_ledger

    edge = tmp_path / "edge"
    edge.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
    repo = tmp_path / "repo"
    el = repo / "data" / "earning_learning"
    el.mkdir(parents=True)
    pd.DataFrame(
        {
            "trade_date": ["2026-01-15"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
            "market_real": 4.0,
        }
    ).to_csv(el / "t0_observation_freeze.csv", index=False)
    ensure_storage(edge)
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-01-15",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge,
    )
    assert out["order"] == ["qualification", "continuous_learning", "recognition", "shadow"]
    ts = out["step_timestamps"]
    assert ts["qualification_finished_at"] <= ts["continuous_learning_started_at"]
    assert ts["continuous_learning_finished_at"] <= ts["recognition_started_at"]
    assert out["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert out["assessment_reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE

    skip = run_closed_loop_edge_after_daily(
        target_trade_date="2026-08-30",
        daily_result={"run": {"run_disposition": "SKIPPED_NON_TRADING_DAY"}},
        repo_root=repo,
        data_dir=edge,
    )
    assert skip["skip_reason"] == SKIP_NON_TRADING_DAY
    assert skip["ran_science"] is False
    assert read_ledger("edge_forward_ledger.csv", edge).empty


def test_reuse_forecast_memory_skips_second_hsx_walk(tmp_path, monkeypatch):
    from modules.forecast_research.production_daily_integration import (
        attach_forecast_memory_to_daily_run_result,
    )

    called = []
    monkeypatch.setattr(
        "modules.forecast_research.production_daily_integration.run_forecast_memory_daily_stage",
        lambda *a, **k: called.append("fm") or {"ok": False, "reason": "must_not_run"},
    )
    reused = {"ok": True, "stage_disposition": "SUCCESS", "reason": "from_headless"}
    out = attach_forecast_memory_to_daily_run_result(
        {"run": {"run_id": None, "run_disposition": "SUCCESS"}},
        target_trade_date="2026-08-28",
        repo_root=tmp_path,
        reuse_forecast_memory=reused,
    )
    assert called == []
    assert out["forecast_memory"]["reused_from_headless_eod"] is True
    assert out["forecast_memory"]["reason"] == "from_headless"


def test_receipt_exposes_closed_loop_and_terminated_is_not_pass(tmp_path):
    rec = build_daily_pipeline_receipt(
        "2026-08-28",
        repo_root=tmp_path,
        headless_eod={"stage_disposition": "SUCCESS", "source_rows": 142, "ok": True},
        edge_result={
            "run": {"run_disposition": "SUCCESS", "run_id": "r1"},
            "closed_loop_edge": {
                "ran_science": True,
                "system_status": "SUCCESS",
                "assessment_state": ASSESSMENT_NO_QUALIFIED_MATCH,
                "assessment_reason": REASON_NO_ACTIVE_EDGE_AVAILABLE,
                "order": ["qualification", "continuous_learning", "recognition", "shadow"],
            },
        },
        panel_freshness={"target_in_panel_sessions": True},
        run_provenance={"recovery": False, "run_mode": "LIVE_FORWARD"},
    )
    assert rec["closed_loop_complete"] is True
    assert rec["closed_loop_status"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert rec["closed_loop_edge"]["visible_status"] == ASSESSMENT_NO_QUALIFIED_MATCH

    incomplete = write_incomplete_pipeline_receipt(
        "2026-08-28",
        repo_root=tmp_path,
        headless_eod={"stage_disposition": "SUCCESS", "source_rows": 142},
        termination_reason=PIPELINE_TERMINATED,
    )
    assert incomplete["ok"] is True
    body = incomplete["receipt"]
    assert body["overall"] == OVERALL_FAIL
    assert body["first_failed_stage"] == "pipeline_wall_clock"
    assert body["closed_loop_complete"] is False
    assert body["pipeline_complete"] is False


def test_lock_held_skip_does_not_run_abc():
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-08-28",
        daily_result={"lock_held": True, "run": {"run_disposition": "LOCK_HELD"}},
        repo_root=Path("/tmp"),
        data_dir=None,
    )
    assert out["ran_science"] is False
    assert out["skip_reason"] == SKIP_LOCK_HELD


def test_entrypoint_acquires_lock_before_headless_source():
    src = (REPO / "modules/edge_research/opr_bridge/production_daily_run_entrypoint.py").read_text(
        encoding="utf-8"
    )
    assert src.index("acquire_run_lock") < src.index("run_headless_eod(")
    assert "use_run_lock=False" in src
    assert "reuse_forecast_memory" in src
