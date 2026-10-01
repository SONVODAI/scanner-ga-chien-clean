"""Production path contract, session market voice, and headless→panel handoff tests."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from tests.test_headless_eod_zero_touch import EXPECTED_UNIVERSE

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_persistence import runs_root
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    living_root,
    session_voice_path,
)
from modules.edge_research.opr_bridge.production_living_research_observation import (
    run_daily_living_assessment,
)
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
    build_living_research_ui_read_model,
    resolve_production_data_dir,
)
from modules.edge_research.opr_bridge.production_panel_freshness import diagnose_panel_freshness
from modules.edge_research.opr_bridge.production_research_observation import (
    run_production_research_observation,
)
from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    evaluate_trading_session_eligibility,
)
from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root


def test_production_runs_root_no_double_nest():
    edge = resolve_data_dir(None)
    explicit = edge / "production_observations"
    assert resolve_production_runs_root(None) == explicit
    assert resolve_production_runs_root(explicit) == explicit
    assert resolve_production_runs_root(edge) == explicit


def test_ui_and_backend_runs_root_match():
    edge = resolve_data_dir(None)
    ui_passed = edge  # fixed contract: UI passes edge root
    assert runs_root(None) == runs_root(ui_passed)
    assert living_root(None) == resolve_production_data_dir(ui_passed)
    assert resolve_production_data_dir(edge / "production_observations") == runs_root(None)


def test_ui_read_model_sees_backend_daily_run_index(tmp_path: Path):
    edge = tmp_path / "edge_research"
    prod = edge / "production_observations"
    prod.mkdir(parents=True)
    idx = {
        "runs": {
            "run1": {
                "run_id": "run1",
                "target_trade_date": "2026-08-24",
                "run_disposition": "SUCCESS",
                "run_mode": "LIVE_FORWARD",
            }
        }
    }
    (prod / "daily_run_index.json").write_text(json.dumps(idx), encoding="utf-8")

    # Legacy double-nested caller path must still resolve correctly.
    rm = build_living_research_ui_read_model(data_dir=edge / "production_observations")
    assert rm["health"]["latest_successful_research_date"] == "2026-08-24"

    rm2 = build_living_research_ui_read_model(data_dir=edge)
    assert rm2["health"]["latest_successful_research_date"] == "2026-08-24"


def test_headless_eod_panel_handoff_no_streamlit(tmp_path: Path):
    """Simulate headless EL outputs → panel must include target session (no Streamlit)."""
    td = "2026-08-20"
    el = tmp_path / "data" / "earning_learning"
    el.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(EXPECTED_UNIVERSE):
        rows.append(
            {
                "observation_id": f"obs{i}",
                "trade_date": td,
                "symbol": f"S{i:03d}",
                "price": 100 + i,
                "rsi14": 50,
                "rs5": 1,
                "rs10": 0,
                "rs_spread": 1,
            }
        )
    pd.DataFrame(rows).to_csv(el / "observations.csv", index=False)
    pd.DataFrame(rows).to_csv(el / "t0_observation_freeze.csv", index=False)

    panel = build_research_panel(repo_root=tmp_path)
    headless = {"stage_disposition": "SUCCESS", "ok": True, "artifacts": {"earning_learning": {"observations_added": EXPECTED_UNIVERSE}}}
    diag = diagnose_panel_freshness(panel, td, headless_eod=headless)
    assert diag["target_in_panel_sessions"] is True
    elig = evaluate_trading_session_eligibility(panel, td)
    assert elig.eligible is True


def test_session_market_voice_on_no_discovery_day():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("no panel fixture")
    td = "2026-08-05"
    if td not in set(panel["trade_date"].astype(str)):
        pytest.skip(f"{td} not in panel fixture")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        birth = run_production_research_observation(
            panel, data_cutoff_date=td, data_dir=data_dir, persist=True
        )
        assert birth.birth_record is not None
        result = run_daily_living_assessment(
            panel,
            assessment_trade_date=td,
            observation_ids=[birth.observation_id],
            new_observation_ids=[],
            data_dir=data_dir,
        )
        assert result["session_voice"]["observation_id"] == "SESSION_MARKET_VOICE"
        assert session_voice_path(td, data_dir).exists()
        assert result["summary"]["silence_or_no_discovery"] is True
        assert result["assessments"]


def test_waiting_for_data_when_panel_missing_target():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("no panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    future = "2099-12-31"
    assert future not in dates
    with tempfile.TemporaryDirectory() as tmp:
        out = run_production_daily_research(
            panel,
            target_trade_date=future,
            run_mode="BACKFILL_NON_FORWARD",
            data_dir=Path(tmp),
        )
    assert out["run"]["run_disposition"] == "WAITING_FOR_DATA"
    assert out["run"]["failure_or_skip_reason"] == "target_date_not_in_panel_sessions"


def test_panel_freshness_diagnoses_stale_after_failed_headless():
    panel = build_research_panel()
    if panel.empty:
        pytest.skip("no panel")
    dates = sorted(panel["trade_date"].astype(str).unique())
    future = (pd.Timestamp(dates[-1]) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    headless = {"stage_disposition": "TRADING_DAY_PROBE_FAILED", "ok": False}
    diag = diagnose_panel_freshness(panel, future, headless_eod=headless)
    assert diag["target_in_panel_sessions"] is False
    assert diag["likely_cause"] == "headless_eod_did_not_publish_t0_rows_for_target"
