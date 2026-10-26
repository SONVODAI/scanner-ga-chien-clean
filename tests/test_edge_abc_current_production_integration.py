"""Current-production integration: daily pipeline owns A→C→B after canonical T0."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.closed_loop_daily_hook import (
    SKIP_NON_TRADING_DAY,
    SKIP_T0_NOT_READY,
    run_closed_loop_edge_after_daily,
)
from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    ASSESSMENT_QUALIFIED_MATCH_FOUND,
    ASSESSMENT_UNABLE_TO_ASSESS,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)
from modules.edge_research.eod_cycle import run_edge_research_eod_cycle
from modules.edge_research.oos_eval import clauses_from_frozen_spec
from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_records import BACKFILL_NON_FORWARD
from modules.edge_research.storage import ensure_storage, read_ledger
from tests.test_edge_research_phase_a_qualification import _minimal_spec
from tests.test_edge_research_phase_b_future_recognition import (
    COMPATIBLE_MARKET,
    UNKNOWN_MARKET,
    _activate,
    _freeze_df,
    _t0_row,
)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def edge_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_PATH", raising=False)
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_BACKEND", raising=False)
    return d


def _plant_freeze(repo_root: Path, freeze: pd.DataFrame) -> Path:
    el = repo_root / "data" / "earning_learning"
    el.mkdir(parents=True, exist_ok=True)
    path = el / "t0_observation_freeze.csv"
    freeze.to_csv(path, index=False)
    return path


def test_one_authoritative_scheduler_and_retired_edge_timer():
    daily = (REPO / "deploy/systemd/mrbot-daily-research.timer").read_text(encoding="utf-8")
    daily_svc = (REPO / "deploy/systemd/mrbot-daily-research.service").read_text(encoding="utf-8")
    assert "mrbot-daily-research.service" in daily
    assert "production_daily_run_entrypoint" in daily_svc
    retired = (REPO / "deploy/systemd/mrbot-edge-research-eod.timer").read_text(encoding="utf-8")
    assert not any(ln.startswith("OnCalendar=") for ln in retired.splitlines())
    installer = (REPO / "deploy/systemd/install-edge-research-eod.sh").read_text(encoding="utf-8")
    assert "enable --now mrbot-edge-research-eod.timer" not in installer
    assert "mrbot-daily-research.timer" in installer
    daily_install = (REPO / "deploy/systemd/install-daily-research.sh").read_text(encoding="utf-8")
    assert "mrbot-daily-research.timer" in daily_install


def test_streamlit_is_not_the_writer():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "run_edge_research_eod_cycle(" not in app
    entry = (REPO / "modules/edge_research/opr_bridge/production_daily_run_entrypoint.py").read_text(
        encoding="utf-8"
    )
    orch = (REPO / "modules/edge_research/opr_bridge/production_daily_run_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "run_production_daily_research" in entry
    assert "run_closed_loop_edge_after_daily" in orch
    assert "run_headless_eod" in entry


def test_t0_not_ready_skips_abc(edge_dir, tmp_path):
    repo = tmp_path / "repo"
    _plant_freeze(repo, pd.DataFrame({"trade_date": ["2026-08-27"], "symbol": ["AAA"]}))
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-08-28",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge_dir,
    )
    assert out["ran_science"] is False
    assert out["skip_reason"] == SKIP_T0_NOT_READY
    assert out.get("assessment_state") != ASSESSMENT_NO_QUALIFIED_MATCH


def test_non_trading_skip_no_birth(edge_dir, tmp_path):
    repo = tmp_path / "repo"
    _plant_freeze(repo, pd.DataFrame({"trade_date": ["2026-08-28"], "symbol": ["AAA"]}))
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-08-30",
        daily_result={"run": {"run_disposition": "SKIPPED_NON_TRADING_DAY"}},
        repo_root=repo,
        data_dir=edge_dir,
    )
    assert out["ran_science"] is False
    assert out["skip_reason"] == SKIP_NON_TRADING_DAY
    fwd = read_ledger("edge_forward_ledger.csv", edge_dir)
    assert fwd.empty


def test_zero_active_no_match(edge_dir, tmp_path):
    repo = tmp_path / "repo"
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-01-15"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
            "market_real": 4.0,
        }
    )
    _plant_freeze(repo, freeze)
    ensure_storage(edge_dir)
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-01-15",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge_dir,
    )
    assert out["ran_science"] is True
    assert out["order"] == ["qualification", "continuous_learning", "recognition", "shadow"]
    ts = out["step_timestamps"]
    assert ts["qualification_finished_at"] <= ts["continuous_learning_started_at"]
    assert ts["continuous_learning_finished_at"] <= ts["recognition_started_at"]
    assert out["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert out["assessment_reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE
    assert out["system_status"] == "SUCCESS"


def test_unknown_context_unable(edge_dir, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    spec = _activate(_minimal_spec(), edge_dir)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    _plant_freeze(repo, freeze)
    monkeypatch.setattr(
        "modules.edge_research.future_recognition.resolve_session_market_context",
        lambda *a, **k: UNKNOWN_MARKET,
    )
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-01-15",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge_dir,
    )
    assert out["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS


def test_matcher_exception_preserves_t0_and_surfaces_unable(edge_dir, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    freeze = _freeze_df([_t0_row("AAA", clauses=clauses_from_frozen_spec(_minimal_spec()), satisfy=True)])
    path = _plant_freeze(repo, freeze)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    def _boom(*_a, **_k):
        raise RuntimeError("matcher boom")

    monkeypatch.setattr(
        "modules.edge_research.engine.EdgeResearchEngine.run_future_recognition",
        _boom,
    )
    out = run_closed_loop_edge_after_daily(
        target_trade_date="2026-01-15",
        daily_result={"run": {"run_disposition": "SUCCESS"}},
        repo_root=repo,
        data_dir=edge_dir,
    )
    assert out["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert out["assessment_reason"] == "MATCHER_EXCEPTION"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert out["system_status"] == "SUCCESS"


def test_daily_orchestration_order_and_new1_birth(edge_dir, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    spec = _activate(_minimal_spec(), edge_dir)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    _plant_freeze(repo, freeze)
    monkeypatch.setattr(
        "modules.edge_research.future_recognition.resolve_session_market_context",
        lambda *a, **k: COMPATIBLE_MARKET,
    )
    monkeypatch.setattr(
        "modules.forecast_research.production_daily_integration.attach_forecast_memory_to_daily_run_result",
        lambda result, **k: dict(result, forecast_memory={"ok": True, "skipped": True, "reason": "test_stub"}),
    )
    panel = _anomaly_panel(seed=42)
    first = run_production_daily_research(
        panel,
        target_trade_date="2026-01-15",
        run_mode=BACKFILL_NON_FORWARD,
        data_dir=edge_dir,
        repo_root=repo,
    )
    abc = first.get("closed_loop_edge") or {}
    assert abc.get("ran_science") is True
    assert abc.get("order") == ["qualification", "continuous_learning", "recognition", "shadow"]
    ts = abc.get("step_timestamps") or {}
    assert ts["qualification_started_at"] <= ts["qualification_finished_at"] <= ts["continuous_learning_started_at"]
    assert ts["continuous_learning_finished_at"] <= ts["recognition_started_at"]
    assert abc.get("assessment_state") == ASSESSMENT_QUALIFIED_MATCH_FOUND
    fwd = read_ledger("edge_forward_ledger.csv", edge_dir)
    assert len(fwd) == 1
    assert str(fwd.iloc[0]["symbol"]) == "NEW1"

    second = run_production_daily_research(
        panel,
        target_trade_date="2026-01-15",
        run_mode=BACKFILL_NON_FORWARD,
        data_dir=edge_dir,
        repo_root=repo,
    )
    fwd2 = read_ledger("edge_forward_ledger.csv", edge_dir)
    assert len(fwd2) == 1
    rec2 = (second.get("closed_loop_edge") or {}).get("recognition") or {}
    assert int(rec2.get("new_birth_count") or 0) == 0


def test_abc_order_in_eod_cycle_source():
    import inspect

    src = inspect.getsource(run_edge_research_eod_cycle)
    assert src.index("run_qualification_cycle") < src.index("run_continuous_learning")
    assert src.index("run_continuous_learning") < src.index("run_future_recognition")


def test_no_buy_in_closed_loop():
    hook = (REPO / "modules/edge_research/closed_loop_daily_hook.py").read_text(encoding="utf-8")
    eod = (REPO / "modules/edge_research/eod_cycle.py").read_text(encoding="utf-8")
    for src in (hook, eod):
        assert "place_order" not in src
        assert "build_final_decision" not in src
