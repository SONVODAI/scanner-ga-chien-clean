"""
Regression for the 2026-09-03 session-voice presentation/provenance cases.

Issue 1 — waiting text must not describe a released T3 as still pending.
Issue 2 — session-voice market_real must come from panel.market_real, never market_live.

These tests reconstruct the 2026-09-03 shapes in isolation. They do not read,
rewrite, or backfill production_observations / LIVE_FORWARD artifacts.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.production_daily_assessment import (
    _next_pending_horizon,
    build_daily_summary,
)
from modules.edge_research.opr_bridge.production_daily_voice import render_session_market_voice
from modules.edge_research.opr_bridge.production_market_delta import extract_market_snapshot
from modules.edge_research.opr_bridge.production_observation_cutoff import (
    compute_market_context_identity,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    ForwardEvaluationStatus,
    ForwardHorizonPlaceholder,
    build_forward_horizon_placeholders,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    compute_horizon_eligible_date_vn,
    evaluate_calendar_session_eligibility,
)


def _birth(placeholders: Tuple[ForwardHorizonPlaceholder, ...]) -> SimpleNamespace:
    return SimpleNamespace(forward_horizons=placeholders)


def _placeholder(horizon: str, eligible: str) -> ForwardHorizonPlaceholder:
    return ForwardHorizonPlaceholder(
        horizon=horizon,
        status=ForwardEvaluationStatus.PENDING_FUTURE.value,
        eligible_evaluation_date=eligible,
        realized_outcome=None,
    )


def _outcome(horizon: str, eligible: str, status: str = "EVALUATED") -> SimpleNamespace:
    return SimpleNamespace(horizon=horizon, evaluation_status=status, eligible_evaluation_date=eligible)


def _case_2026_09_03_placeholders() -> Tuple[ForwardHorizonPlaceholder, ...]:
    # Frozen birth clocks reported in the 2026-09-03 session voice.
    return (
        _placeholder("T3", "2026-08-27"),
        _placeholder("T5", "2026-09-03"),
        _placeholder("T10", "2026-09-10"),
    )


def test_released_t3_is_not_described_as_still_waiting_on_2026_08_27():
    birth = _birth(_case_2026_09_03_placeholders())
    stale = _next_pending_horizon(birth, "2026-09-03")
    assert stale == ("T3", "2026-08-27")

    released_t3 = [_outcome("T3", "2026-08-27", "EVALUATED")]
    horizon, eligible = _next_pending_horizon(birth, "2026-09-03", released_t3)
    assert (horizon, eligible) != ("T3", "2026-08-27")
    assert horizon == "T5"
    assert eligible == "2026-09-03"
    waiting = f"Waiting for {horizon} eligible on {eligible}"
    assert "Waiting for T3 eligible on 2026-08-27" not in waiting


def test_released_t3_and_t5_wait_for_t10_only():
    birth = _birth(_case_2026_09_03_placeholders())
    outcomes = [
        _outcome("T3", "2026-08-27", "EVALUATED"),
        _outcome("T5", "2026-09-03", "EVALUATED"),
    ]
    horizon, eligible = _next_pending_horizon(birth, "2026-09-03", outcomes)
    assert (horizon, eligible) == ("T10", "2026-09-10")


def test_missing_data_outcome_does_not_clear_waiting():
    birth = _birth(_case_2026_09_03_placeholders())
    outcomes = [_outcome("T3", "2026-08-27", "MISSING_DATA")]
    horizon, eligible = _next_pending_horizon(birth, "2026-09-03", outcomes)
    assert (horizon, eligible) == ("T3", "2026-08-27")


def test_session_voice_q9_drops_released_t3_from_2026_09_03_concatenation():
    """Reproduce the three-line 2026-09-03 voice after T3 2026-08-27 matured."""
    births = [
        (_case_2026_09_03_placeholders(), [_outcome("T3", "2026-08-27")]),
        ((_placeholder("T3", "2026-09-08"), _placeholder("T5", "2026-09-10"), _placeholder("T10", "2026-09-17")), []),
        ((_placeholder("T3", "2026-09-02"), _placeholder("T5", "2026-09-04"), _placeholder("T10", "2026-09-11")), []),
    ]
    waiting_parts: List[str] = []
    assessments = []
    for i, (placeholders, outcomes) in enumerate(births, start=1):
        horizon, eligible = _next_pending_horizon(_birth(placeholders), "2026-09-03", outcomes)
        waiting = f"Waiting for {horizon} eligible on {eligible}"
        waiting_parts.append(waiting)
        assessments.append(
            SimpleNamespace(
                assessment_id=f"asmt-{i}",
                observation_id=f"obs-{i}",
                observation_lifecycle_state="ACTIVE_PENDING",
                forward_outcomes_newly_available=(),
                market_delta=SimpleNamespace(summary_keys=("market:unchanged",)),
                unresolved_uncertainties=(),
                what_bot_is_waiting_for=waiting,
                epistemic_delta=SimpleNamespace(changed=False),
            )
        )

    summary = build_daily_summary(
        trade_date="2026-09-03",
        assessments=assessments,
        market_snapshot={"market_real": 7.2},
    )
    voice = render_session_market_voice(summary, assessments)
    q9 = voice.q9_waiting_for_vi
    assert "Waiting for T3 eligible on 2026-08-27" not in q9
    assert "Waiting for T5 eligible on 2026-09-03" in q9
    assert "Waiting for T3 eligible on 2026-09-08" in q9
    # Frozen pre-calendar-fix placeholder is not rewritten.
    assert "Waiting for T3 eligible on 2026-09-02" in q9
    assert summary.what_bot_is_waiting_for == q9


def test_future_waiting_dates_use_vn_trading_sessions_not_holidays():
    national_day_closed = {"2026-08-31", "2026-09-01", "2026-09-02"}
    for t0, horizon, expected in (
        ("2026-09-03", "T3", "2026-09-08"),
        ("2026-08-28", "T3", "2026-09-07"),
        ("2026-08-24", "T3", "2026-08-27"),
        ("2026-08-24", "T5", "2026-09-03"),
    ):
        legal = compute_horizon_eligible_date_vn(t0, horizon)
        placeholders = build_forward_horizon_placeholders(t0)
        by_h = {p.horizon: p.eligible_evaluation_date for p in placeholders}
        assert legal == expected
        assert by_h[horizon] == expected
        assert expected not in national_day_closed
        assert evaluate_calendar_session_eligibility(expected).eligible

    new_birth = _birth(build_forward_horizon_placeholders("2026-09-03"))
    horizon, eligible = _next_pending_horizon(new_birth, "2026-09-03")
    assert (horizon, eligible) == ("T3", "2026-09-08")
    assert eligible not in national_day_closed


def _panel_for_voice(rows: List[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_session_voice_market_real_traces_to_canonical_field_for_session():
    panel = _panel_for_voice(
        [
            {
                "trade_date": "2026-08-28",
                "symbol": "AAA",
                "market_real": 5.3,
                "market_live": 7.2,
                "market_forecast": 1.1,
                "breadth_score": 10.0,
                "research_market_state": "MATURE",
            },
            {
                "trade_date": "2026-09-03",
                "symbol": "AAA",
                "market_real": 7.2,
                "market_live": 6.3,
                "market_forecast": 0.5,
                "breadth_score": 13.0,
                "research_market_state": "ROLLOVER",
            },
        ]
    )
    snap = extract_market_snapshot(panel, "2026-09-03")
    assert snap["market_real"] == 7.2
    assert "market_live" not in snap
    summary = build_daily_summary(
        trade_date="2026-09-03",
        assessments=[],
        market_snapshot=snap,
    )
    voice = render_session_market_voice(summary, [])
    assert "market_real=7.2" in voice.q2_vs_prior_session_vi
    assert "market_real=6.3" not in voice.q2_vs_prior_session_vi
    assert summary.market_state_summary["market_real"] == panel.loc[
        panel["trade_date"] == "2026-09-03", "market_real"
    ].iloc[0]


def test_market_live_cannot_silently_populate_market_real():
    panel = _panel_for_voice(
        [
            {
                "trade_date": "2026-09-03",
                "symbol": "AAA",
                "market_real": 6.2,
                "market_live": 7.2,
                "market_forecast": 0.5,
                "breadth_score": 13.0,
                "research_market_state": "ROLLOVER",
            }
        ]
    )
    snap = extract_market_snapshot(panel, "2026-09-03")
    assert snap["market_real"] == 6.2
    assert "market_live" not in snap
    voice = render_session_market_voice(
        build_daily_summary(trade_date="2026-09-03", assessments=[], market_snapshot=snap),
        [],
    )
    assert "market_real=6.2" in voice.q2_vs_prior_session_vi
    assert "market_real=7.2" not in voice.q2_vs_prior_session_vi


def test_rendering_does_not_change_frozen_market_context_hash():
    panel = _panel_for_voice(
        [
            {
                "trade_date": "2026-09-03",
                "symbol": "AAA",
                "market_real": 7.2,
                "market_live": 99.0,
                "market_forecast": 0.5,
                "breadth_score": 13.0,
                "research_market_state": "ROLLOVER",
            }
        ]
    )
    ident_before, hash_before = compute_market_context_identity(panel, "2026-09-03")
    snap = extract_market_snapshot(panel, "2026-09-03")
    render_session_market_voice(
        build_daily_summary(trade_date="2026-09-03", assessments=[], market_snapshot=snap),
        [],
    )
    ident_after, hash_after = compute_market_context_identity(panel, "2026-09-03")
    assert ident_before == ident_after
    assert hash_before == hash_after
    assert hash_before
    assert snap["market_real"] == 7.2


def test_extract_snapshot_exact_date_not_confused_with_other_7_2_row():
    """A historical 7.2 on another date must not win when 2026-09-03 is present."""
    panel = _panel_for_voice(
        [
            {
                "trade_date": "2026-08-20",
                "symbol": "AAA",
                "market_real": 7.2,
                "market_live": 5.3,
                "market_forecast": 1.1,
                "breadth_score": 8.0,
                "research_market_state": "MATURE",
            },
            {
                "trade_date": "2026-09-03",
                "symbol": "AAA",
                "market_real": 6.2,
                "market_live": 6.3,
                "market_forecast": 0.5,
                "breadth_score": 13.0,
                "research_market_state": "ROLLOVER",
            },
        ]
    )
    snap = extract_market_snapshot(panel, "2026-09-03")
    assert snap["market_real"] == 6.2
    assert snap["research_market_state"] == "ROLLOVER"
