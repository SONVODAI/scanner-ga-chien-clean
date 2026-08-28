"""Production activation orchestration tests — not new research science."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pandas as pd

from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    ASSESSMENT_UNABLE_TO_ASSESS,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)
from modules.edge_research.eod_cycle import (
    SKIP_NON_TRADING_DAY,
    SKIP_T0_NOT_READY,
    SYSTEM_SKIPPED,
    SYSTEM_SUCCESS,
    main,
    production_preflight,
    run_edge_research_eod_cycle,
    run_edge_research_eod_from_ui,
    write_latest_eod_status,
)
from modules.edge_research.storage import ensure_storage


REPO = Path(__file__).resolve().parents[1]


def test_timer_is_after_canonical_t0_eligibility():
    timer = (REPO / "deploy/systemd/mrbot-edge-research-eod.timer").read_text(encoding="utf-8")
    on_calendar = [ln for ln in timer.splitlines() if ln.startswith("OnCalendar=")]
    assert all("16:05" not in ln for ln in on_calendar)
    assert "Asia/Ho_Chi_Minh" in timer
    assert any("19:15:00" in ln for ln in on_calendar)
    assert any("20:30:00" in ln for ln in on_calendar)
    svc = (REPO / "deploy/systemd/mrbot-edge-research-eod.service").read_text(encoding="utf-8")
    assert "python -m modules.edge_research.eod_cycle" in svc
    assert "After=mrbot-intraday-collect" not in svc


def test_weekend_without_freeze_skips_non_trading(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame({"trade_date": ["2026-08-28"], "symbol": ["AAA"]})
    pre = production_preflight("2026-08-30", freeze_df=freeze)  # Sunday
    assert pre["skip"] is True
    assert pre["skip_reason"] == SKIP_NON_TRADING_DAY
    result = run_edge_research_eod_cycle(
        trade_date="2026-08-30",
        data_dir=d,
        freeze_df=freeze,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
    )
    assert result["system_status"] == SYSTEM_SKIPPED
    assert result["skip_reason"] == SKIP_NON_TRADING_DAY
    assert result["ran_science"] is False
    assert result.get("assessment_state") == ""
    status = json.loads((d / "latest_eod_run.json").read_text())
    assert status["skip_reason"] == SKIP_NON_TRADING_DAY


def test_missing_t0_skips_not_no_match(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame({"trade_date": ["2026-08-27"], "symbol": ["AAA"]})
    pre = production_preflight("2026-08-28", freeze_df=freeze)
    assert pre["skip"] is True
    assert pre["skip_reason"] == SKIP_T0_NOT_READY
    result = run_edge_research_eod_cycle(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
    )
    assert result["system_status"] == SYSTEM_SKIPPED
    rec = result.get("recognition") or {}
    assert rec.get("assessment_state") != ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["ran_science"] is False


def test_runtime_order_timestamps(tmp_path, monkeypatch):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-08-28"] * 3,
            "symbol": ["AAA", "BBB", "CCC"],
            "rs10": [-1.0, -1.0, -1.0],
            "rs5": [-1.0, -1.0, -1.0],
            "rsi14": [50.0, 50.0, 50.0],
            "rs_spread": [0.0, 0.0, 0.0],
        }
    )
    result = run_edge_research_eod_cycle(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
        market_context={"research_market_state": "STRESS", "research_market_transition": "STRESS -> STRESS"},
    )
    ts = result["step_timestamps"]
    assert ts["qualification_started_at"] <= ts["qualification_finished_at"]
    assert ts["qualification_finished_at"] <= ts["continuous_learning_started_at"]
    assert ts["continuous_learning_finished_at"] <= ts["recognition_started_at"]
    assert result["order"] == ["qualification", "continuous_learning", "recognition", "shadow"]
    assert result["system_status"] == SYSTEM_SUCCESS
    assert result["assessment_state"] in {ASSESSMENT_NO_QUALIFIED_MATCH, ASSESSMENT_UNABLE_TO_ASSESS}
    if result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH:
        assert result["assessment_reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE


def test_ui_fallback_does_not_rerun_after_headless(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    write_latest_eod_status(
        {
            "trade_date": "2026-08-28",
            "system_status": SYSTEM_SUCCESS,
            "runner": "headless",
            "assessment_state": ASSESSMENT_NO_QUALIFIED_MATCH,
            "assessment_reason": REASON_NO_ACTIVE_EDGE_AVAILABLE,
        },
        data_dir=d,
    )
    out = run_edge_research_eod_from_ui(trade_date="2026-08-28", data_dir=d)
    assert out["skipped_duplicate"] is True
    assert out["ran_science"] is False
    assert out["reason"] == "HEADLESS_AUTHORITATIVE_ALREADY_RAN"


def test_cli_skip_exit_zero_on_weekend(tmp_path, monkeypatch):
    d = tmp_path / "edge"
    ensure_storage(d)
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    code = main(["--trade-date", "2026-08-30", "--data-dir", str(d)])
    assert code == 0
    status = json.loads((d / "latest_eod_run.json").read_text())
    assert status["system_status"] == SYSTEM_SKIPPED


def test_app_uses_ui_fallback_wrapper():
    src = (REPO / "app.py").read_text(encoding="utf-8")
    assert "run_edge_research_eod_cycle" in src
    assert "run_edge_research_eod_from_ui" in src
    eod_src = inspect.getsource(run_edge_research_eod_cycle)
    assert eod_src.index("run_qualification_cycle") < eod_src.index("run_continuous_learning")
    assert eod_src.index("run_continuous_learning") < eod_src.index("run_future_recognition")


def test_no_buy_in_activation_modules():
    eod = inspect.getsource(__import__("modules.edge_research.eod_cycle", fromlist=["x"]))
    audit = inspect.getsource(__import__("modules.edge_research.production_audit", fromlist=["x"]))
    for src in (eod, audit):
        assert "place_order" not in src
        assert "build_final_decision" not in src


def test_system_success_with_research_no_match(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-08-28"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
        }
    )
    result = run_edge_research_eod_cycle(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
        market_context={"research_market_state": "STRESS", "research_market_transition": "STRESS -> STRESS"},
    )
    assert result["system_status"] == SYSTEM_SUCCESS
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["assessment_reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE
    status = json.loads((d / "latest_eod_run.json").read_text())
    assert status["system_status"] == SYSTEM_SUCCESS
    assert status["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH


def test_idempotent_replay_does_not_duplicate_rows(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-08-28"] * 2,
            "symbol": ["AAA", "BBB"],
            "rs10": [-1.0, -1.0],
            "rs5": [-1.0, -1.0],
            "rsi14": [50.0, 50.0],
            "rs_spread": [0.0, 0.0],
        }
    )
    kwargs = dict(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
        market_context={"research_market_state": "STRESS", "research_market_transition": "STRESS -> STRESS"},
    )
    first = run_edge_research_eod_cycle(**kwargs)

    def _scientific_hashes() -> dict[str, str]:
        names = (
            "edge_memory.csv",
            "edge_forward_ledger.csv",
            "edge_validation_history.csv",
            "edge_hypothesis_ledger.csv",
        )
        out = {}
        for name in names:
            p = d / name
            out[name] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""
        frozen = sorted((d / "frozen_specs").glob("*.json")) if (d / "frozen_specs").exists() else []
        out["frozen_specs"] = hashlib.sha256(b"".join(p.read_bytes() for p in frozen)).hexdigest()
        return out

    hashes_after_first = _scientific_hashes()
    n_forward = len(pd.read_csv(d / "edge_forward_ledger.csv")) if (d / "edge_forward_ledger.csv").exists() else 0
    n_mem = len(pd.read_csv(d / "edge_memory.csv")) if (d / "edge_memory.csv").exists() else 0
    n_assess = len(pd.read_csv(d / "edge_session_assessments.csv")) if (d / "edge_session_assessments.csv").exists() else 0
    second = run_edge_research_eod_cycle(**kwargs)
    hashes_after_second = _scientific_hashes()
    assert first["system_status"] == SYSTEM_SUCCESS
    assert second["system_status"] == SYSTEM_SUCCESS
    assert first["assessment_state"] == second["assessment_state"]
    assert n_forward == 0
    assert n_mem == 0
    assert hashes_after_first == hashes_after_second
    n_assess_2 = len(pd.read_csv(d / "edge_session_assessments.csv")) if (d / "edge_session_assessments.csv").exists() else 0
    # Replay may append a distinct run_id audit row; it must not change the scientific conclusion.
    assert n_assess_2 >= n_assess
    assess = pd.read_csv(d / "edge_session_assessments.csv") if n_assess_2 else pd.DataFrame()
    if not assess.empty and "assessment_state" in assess.columns:
        assert set(assess["assessment_state"].astype(str)) <= {ASSESSMENT_NO_QUALIFIED_MATCH, ASSESSMENT_UNABLE_TO_ASSESS}
    frozen = list((d / "frozen_specs").glob("*.json")) if (d / "frozen_specs").exists() else []
    assert frozen == []


def test_matcher_exception_does_not_corrupt_canonical_freeze(tmp_path, monkeypatch):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze_path = tmp_path / "t0_observation_freeze.csv"
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-08-28"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
        }
    )
    freeze.to_csv(freeze_path, index=False)
    before = hashlib.sha256(freeze_path.read_bytes()).hexdigest()

    def _boom(*_a, **_k):
        raise RuntimeError("matcher boom")

    monkeypatch.setattr(
        "modules.edge_research.engine.EdgeResearchEngine.run_future_recognition",
        _boom,
    )
    result = run_edge_research_eod_cycle(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        freeze_path=freeze_path,
        enforce_canonical_t0=True,
        persist_status=True,
        panel=pd.DataFrame(),
    )
    assert result["system_status"] == SYSTEM_SUCCESS
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["assessment_reason"] == "MATCHER_EXCEPTION"
    assert hashlib.sha256(freeze_path.read_bytes()).hexdigest() == before
    assert freeze_path.exists()


def test_ui_fallback_runs_when_headless_has_not(tmp_path):
    d = tmp_path / "edge"
    ensure_storage(d)
    freeze = pd.DataFrame(
        {
            "trade_date": ["2026-08-28"],
            "symbol": ["AAA"],
            "rs10": [-1.0],
            "rs5": [-1.0],
            "rsi14": [50.0],
            "rs_spread": [0.0],
        }
    )
    out = run_edge_research_eod_from_ui(
        trade_date="2026-08-28",
        data_dir=d,
        freeze_df=freeze,
        persist_status=True,
        panel=pd.DataFrame(),
    )
    assert out.get("skipped_duplicate") is not True
    assert out["ran_science"] is True
    assert out["runner"] == "streamlit_fallback"


def test_discovery_challenger_remain_button_gated_not_render():
    ui = (REPO / "modules/edge_research/ui.py").read_text(encoding="utf-8")
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "st.button" in ui
    assert "engine.run_discovery" in ui
    assert "engine.run_challenger" in ui
    assert "run_discovery" not in app
    assert "run_challenger" not in app
    # Daily A→C→B is the only Edge Research science invoked from app render.
    assert "run_edge_research_eod_from_ui(" in app
