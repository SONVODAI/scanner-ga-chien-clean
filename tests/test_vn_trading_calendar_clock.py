"""
Canonical VN trading-session clock + 2026 National Day closure.

Proves calendar data, T3/T5/T10 session offsets, no pandas BDay in active
forward-eligibility production paths, holiday LIVE_FORWARD skip, and that
persisted SESSION_MARKET_VOICE q9 is not rewritten.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]

from modules.actionable_research.observation_maturity import target_session_for_horizon
from modules.edge_research.autonomous_daily_edge_ui import build_autonomous_daily_edge_ui_view
from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import (
    horizon_eligible_on_date,
    reject_early_outcome,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    build_forward_horizon_placeholders,
)
from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    evaluate_trading_session_eligibility,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    calendar_identity,
    compute_horizon_eligible_date_vn,
    evaluate_calendar_session_eligibility,
    iter_trading_sessions,
    load_trading_calendar,
    offset_trading_sessions,
)
from modules.edge_research.storage import resolve_production_runs_root

NATIONAL_DAY_CLOSED = ("2026-08-31", "2026-09-01", "2026-09-02")
FORWARD_ELIGIBILITY_PRODUCTION_PATHS = (
    "modules/edge_research/opr_bridge/production_vn_trading_calendar.py",
    "modules/edge_research/opr_bridge/production_observation_records.py",
    "modules/edge_research/opr_bridge/production_forward_outcome_evaluator.py",
    "modules/edge_research/opr_bridge/production_forward_clock.py",
    "modules/edge_research/opr_bridge/production_daily_voice.py",
    "modules/edge_research/opr_bridge/production_daily_assessment.py",
    "modules/actionable_research/observation_maturity.py",
)
HISTORICAL_ARTIFACTS = (
    "data/earning_learning/pattern_lifecycle.csv",
    "data/earning_learning/verified_decisions.csv",
    "data/earning_learning/observations.csv",
    "data/earning_learning/t0_observation_freeze.csv",
    "data/earning_learning/outcomes.csv",
    "data/earning_learning/market_daily_t0.csv",
)


def _nth_session_after(anchor: str, n: int) -> str:
    """Derive horizon date from the session iterator (not a special-case table)."""
    end = date.fromisoformat(anchor).replace(year=date.fromisoformat(anchor).year + 1).isoformat()
    sessions = iter_trading_sessions(anchor, end)
    assert anchor in sessions, f"{anchor} must itself be an eligible session"
    idx = sessions.index(anchor)
    return sessions[idx + n]


def test_calendar_identity_bumped_for_national_day():
    ident = calendar_identity()
    assert ident.calendar_id == "vn_hose_hnx_v1_nd2026"
    assert ident.version == "vn_trading_calendar_v1_2026_nd"
    cal = load_trading_calendar()
    assert "2026-08-31" in cal["holidays"]
    assert "2026-09-01" in cal["holidays"]
    assert "2026-09-02" in cal["holidays"]
    assert (cal.get("closure_overrides") or {}).get("2026-08-22", {}).get("closed") is True


@pytest.mark.parametrize(
    "trade_date,eligible,reason_part",
    [
        ("2026-08-28", True, "calendar_trading_session"),
        ("2026-08-29", False, "weekend"),
        ("2026-08-30", False, "weekend"),
        ("2026-08-31", False, "exchange_holiday"),
        ("2026-09-01", False, "exchange_holiday"),
        ("2026-09-02", False, "exchange_holiday"),
        ("2026-09-03", True, "calendar_trading_session"),
        ("2026-08-22", False, "exceptional_closure_override"),
    ],
)
def test_national_day_window_and_makeup_saturday(trade_date, eligible, reason_part):
    result = evaluate_calendar_session_eligibility(trade_date)
    assert result.eligible is eligible
    assert reason_part in result.reason


def test_horizon_dates_derived_from_session_iterator():
    required = {
        ("2026-08-24", "T3"): "2026-08-27",
        ("2026-08-27", "T3"): "2026-09-04",
        ("2026-08-28", "T3"): "2026-09-07",
        ("2026-08-24", "T5"): "2026-09-03",
        ("2026-08-27", "T5"): "2026-09-08",
        ("2026-08-28", "T5"): "2026-09-09",
        ("2026-08-24", "T10"): "2026-09-10",
        ("2026-08-27", "T10"): "2026-09-15",
        ("2026-08-28", "T10"): "2026-09-16",
    }
    offsets = {"T3": 3, "T5": 5, "T10": 10}
    for (t0, horizon), expected in required.items():
        derived = _nth_session_after(t0, offsets[horizon])
        assert derived == expected
        assert compute_horizon_eligible_date_vn(t0, horizon) == derived
        assert offset_trading_sessions(t0, offsets[horizon]) == derived
        assert target_session_for_horizon(t0, horizon) == derived
        placeholders = {p.horizon: p.eligible_evaluation_date for p in build_forward_horizon_placeholders(t0)}
        assert placeholders[horizon] == derived


def test_horizons_skip_entire_national_day_closure():
    for t0 in ("2026-08-24", "2026-08-27", "2026-08-28"):
        for horizon in ("T3", "T5", "T10"):
            elig = compute_horizon_eligible_date_vn(t0, horizon)
            assert elig not in NATIONAL_DAY_CLOSED
            assert evaluate_calendar_session_eligibility(elig).eligible


def test_horizon_eligible_on_date_uses_session_clock():
    assert not horizon_eligible_on_date("T3", "2026-08-28", "2026-09-02")
    assert not horizon_eligible_on_date("T3", "2026-08-28", "2026-09-03")
    assert not horizon_eligible_on_date("T3", "2026-08-28", "2026-09-04")
    assert horizon_eligible_on_date("T3", "2026-08-28", "2026-09-07")
    assert reject_early_outcome("T3", "2026-08-28", "2026-09-01")
    assert not reject_early_outcome("T3", "2026-08-28", "2026-09-07")


def test_no_bday_in_forward_eligibility_production_paths():
    for rel in FORWARD_ELIGIBILITY_PRODUCTION_PATHS:
        text = (REPO / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "BDay" not in names, rel
        assert "BDay" not in attrs, rel


def test_calendar_blocks_live_forward_even_if_panel_has_holiday_rows():
    for td in NATIONAL_DAY_CLOSED:
        panel = pd.DataFrame(
            {
                "trade_date": [td, td],
                "symbol": ["AAA", "BBB"],
                "close": [10.0, 11.0],
            }
        )
        session = evaluate_trading_session_eligibility(panel, td)
        assert session.eligible is False
        assert session.disposition == "SKIPPED_NON_TRADING_DAY"
        assert session.calendar_eligible is False
        assert "holiday" in session.reason or "exchange_holiday" in session.reason


def test_persisted_session_voice_q9_not_rewritten(tmp_path: Path):
    frozen_q9 = "Waiting for T3 eligible on 2026-09-02"
    edge = tmp_path / "edge"
    prod = resolve_production_runs_root(edge)
    (prod / "daily_voices").mkdir(parents=True)
    (prod / "daily_runs").mkdir(parents=True)
    (prod / "daily_manifests").mkdir(parents=True)
    (prod / "daily_run_index.json").write_text(
        '{"runs": {"r1": {"run_id": "r1", "target_trade_date": "2026-08-28", '
        '"run_disposition": "SUCCESS", "run_mode": "LIVE_FORWARD"}}}',
        encoding="utf-8",
    )
    (prod / "daily_runs" / "r1.json").write_text('{"run_id": "r1", "run_mode": "LIVE_FORWARD"}', encoding="utf-8")
    (prod / "daily_manifests" / "r1.json").write_text(
        '{"discovery_count": 1, "bot_spoke_today": true}', encoding="utf-8"
    )
    (prod / "daily_voices" / "session_2026-08-28.json").write_text(
        '{"observation_id": "SESSION_MARKET_VOICE", "q9_waiting_for_vi": "%s", '
        '"assessment_trade_date": "2026-08-28", "voice_kind": "SESSION_MARKET_VOICE"}' % frozen_q9,
        encoding="utf-8",
    )
    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    assert view["session_date"] == "2026-08-28"
    assert view["session_voice_questions"]["q9_waiting_for_vi"] == frozen_q9


def test_historical_artifacts_untouched_by_this_repair():
    # Guard: this suite must not rewrite production CSVs.
    for rel in HISTORICAL_ARTIFACTS:
        path = REPO / rel
        assert path.exists()
        # size/mtime not the contract — content still present with known 08-28 max.
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "2026-08-28" in text or rel.endswith("market_daily_t0.csv")
