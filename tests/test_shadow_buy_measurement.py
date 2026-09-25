"""SHADOW BUY measurement V1. Research only. Execution stays impossible."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    EXECUTION_ENABLED,
    PXV_IMPLIES_BUY,
    REASON_INSUFFICIENT_BARS,
    REASON_MISSING_QUALIFIER,
    REASON_MISSING_REFERENCE,
    REASON_NO_ORIGIN_SETUP,
    REASON_PULL_BUY_READY,
    REASON_UNKNOWN_SETUP,
    REASON_UNSUPPORTED_ORIGIN,
    REASON_WHEN_NOT_MET,
    RESEARCH_DECISION_SHADOW_BUY,
    STATE_BUY_READY,
)
from modules.live_candidate_v2_action.state import (
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
)
from modules.candidate_router.contract import ENABLED_SOURCES, SRC_MARKET_AWARE_SWEETSPOT
from modules.live_candidate_v2_nomination.contract import MARKET_PERMISSION_WEAK
from modules.live_candidate_v2_nomination.predicate import MARKET_WEAK_THRESHOLD, market_permission
from modules.live_candidate_v2_nomination.sweet_brain_b import nomination_from_sweet_row
from modules.market_aware_sweetspot_observer import (
    ORIGIN_ACTION_SETUPS,
    compute_observer_snapshot,
    origin_fields_from_scan_row,
)
from modules.research_shadow_buy.ledger import load_shadow_buy_events, try_record_shadow_buy
from modules.research_shadow_buy.ui import PANEL_TITLE, _display_rows
from modules.sweetspot_analyzer import MIN_RANK_N

VN = ZoneInfo("Asia/Ho_Chi_Minh")
DAY = "2026-08-14"
REF_C = 27100
REPO = Path(__file__).resolve().parents[1]


def _ts(hm: str) -> datetime:
    return datetime.fromisoformat(f"{DAY} {hm}:00").replace(tzinfo=VN)


def _bar(hm: str, *, close_vs_ref: float, vol_state: str = "NORMAL") -> BarEvidence:
    close_c = REF_C + int(close_vs_ref)
    return BarEvidence(
        bar_ts=_ts(hm),
        asof=_ts(hm),
        completed=True,
        close=float(close_c),
        close_canonical=close_c,
        reference_kind="EMA9",
        reference_value=27.1,
        reference_canonical=REF_C,
        close_vs_ref=float(close_vs_ref),
        close_vs_ref_pct=(close_vs_ref / REF_C) * 100.0,
        reference_state="EMA9",
        data_state="QUALIFIED",
        published_evidence="NEUTRAL",
        volume_expansion_state=vol_state,
        chronology_legal=True,
    )


def _pull_bars() -> list[BarEvidence]:
    return [
        _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=30),
        _bar("09:25", close_vs_ref=40),
    ]


def _nom(setup: str, *, market: str = "OK", market_real: float = 7.0, **kwargs) -> FrozenNomination:
    return FrozenNomination(
        symbol="HPG",
        session=DAY,
        setup=setup,
        group=setup,
        candidate_first_seen_ts=f"{DAY}T09:00:00+07:00",
        eligible_from=f"{DAY}T09:00:00+07:00",
        observation_reference="EMA9",
        ema9_at_first_seen=27.1,
        market_permission=market,
        market_real=market_real,
        source="brain_a_scan_setup",
        **kwargs,
    )


def _assert_no_execution(result) -> None:
    assert result.candidate_is_buy is False
    assert result.pxv_implies_buy is False
    assert result.alert_eligible is False
    assert result.execution_enabled is False
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
    assert EXECUTION_ENABLED is False


def _lifecycle() -> pd.DataFrame:
    rows = []
    for i in range(MIN_RANK_N):
        rows.append(
            {
                "trade_date": "2026-08-01",
                "symbol": f"S{i:02d}",
                "rs5": 0.0,
                "rs10": -2.0,
                "rsi14": 40.0,
                "t3_return_pct": 2.0,
                "t5_return_pct": 2.0,
                "t10_return_pct": 2.0,
                "market_context_key": "6-8|40-60|6-8",
            }
        )
    return pd.DataFrame(rows)


def _sweet_row(**extra) -> dict:
    row = {
        "symbol": "HPG",
        "observer_status": "OBSERVE",
        "created_at": "2026-08-13T11:13:40Z",
        "t0_date": "2026-08-13",
        "price_t0": 27000,
        "matched_sweetspot": "RS5=0 | RS10=-2 | RSI14=40",
        "historical_winrate": 0.72,
        "historical_sample_n": 40,
    }
    row.update(extra)
    return row


def test_origin_setup_copied_only_from_real_scan_group():
    copied = origin_fields_from_scan_row(
        {
            "group": "PULL ĐẸP",
            "ema9": 27.1,
            "breakout_ref": 30.0,
            "pull_label": "ĐẸP",
            "evolution_health_group": "🌱 ĐANG HỒI",
            "evolution_health_score": 7.5,
        }
    )
    assert copied["origin_group"] == "PULL ĐẸP"
    assert copied["origin_setup"] == "PULL ĐẸP"
    assert copied["origin_ema9"] == 27.1
    assert copied["origin_breakout_ref"] == 30.0
    assert copied["origin_pull_label"] == "ĐẸP"
    assert "PULL ĐẸP" in ORIGIN_ACTION_SETUPS

    pattern_only = origin_fields_from_scan_row(
        {"matched_sweetspot": "RS5=0", "historical_winrate": 0.9, "rs5": 1, "rsi14": 40}
    )
    assert pattern_only["origin_setup"] == ""
    assert pattern_only["origin_group"] == ""

    unsupported = origin_fields_from_scan_row({"group": "THEO DÕI", "ema9": 10})
    assert unsupported["origin_group"] == "THEO DÕI"
    assert unsupported["origin_setup"] == ""


def test_sweet_snapshot_does_not_invent_setup_from_pattern():
    board = pd.DataFrame([{"symbol": "AAA", "price": 10.0, "rs5": 0.0, "rs10": -2.0, "rsi14": 40.0}])
    scan = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "group": "CP MẠNH",
                "ema9": 9.5,
                "breakout_ref": 11.0,
                "pull_label": "",
                "evolution_health_group": "🟡 TRUNG TÍNH",
                "evolution_health_score": 5.0,
            }
        ]
    )
    stamped = compute_observer_snapshot(
        t0_date="2026-08-10",
        earning_board_df=board,
        lifecycle_df=_lifecycle(),
        market_real=7.0,
        market_forecast=6.0,
        breadth=50.0,
        scan_df=scan,
    )
    row = next(r for r in stamped["rows"] if r["symbol"] == "AAA")
    assert row["origin_setup"] == "CP MẠNH"
    assert row["origin_ema9"] == 9.5
    assert row["matched_sweetspot"]
    assert row["origin_setup"] != row["matched_sweetspot"]

    bare = compute_observer_snapshot(
        t0_date="2026-08-10",
        earning_board_df=board,
        lifecycle_df=_lifecycle(),
        market_real=7.0,
        market_forecast=6.0,
        breadth=50.0,
    )
    bare_row = next(r for r in bare["rows"] if r["symbol"] == "AAA")
    assert bare_row["origin_setup"] == ""
    assert bare_row["historical_winrate"] == bare_row["historical_winrate"]
    assert bare_row["origin_group"] == ""


def test_sweet_nomination_keeps_origin_off_the_evaluation_setup():
    nom, extra = nomination_from_sweet_row(
        _sweet_row(origin_setup="PULL ĐẸP", origin_group="PULL ĐẸP", origin_ema9=27.1),
        session_t=DAY,
        market_real=7,
        observed_at=_ts("10:05"),
    )
    assert nom is not None
    assert nom.source == "market_aware_sweetspot"
    assert nom.setup == ""
    assert nom.ema9_at_first_seen is None
    assert nom.breakout_ref_at_first_seen is None
    assert nom.origin_setup == "PULL ĐẸP"
    assert nom.origin_ema9 == 27.1
    assert extra["historical_winrate"] == 0.72
    assert extra["origin_setup"] == "PULL ĐẸP"


def test_pattern_and_winrate_cannot_create_condition_met():
    nom, _ = nomination_from_sweet_row(
        _sweet_row(),
        session_t=DAY,
        market_real=8,
        observed_at=_ts("10:05"),
    )
    result = evaluate_shadow_action(asdict(nom), _pull_bars())
    assert result.condition_met is False
    assert result.research_decision == ""
    assert result.action_state != STATE_BUY_READY
    assert result.action_reason == REASON_UNKNOWN_SETUP
    assert result.non_event_reason == REASON_NO_ORIGIN_SETUP
    _assert_no_execution(result)


def test_missing_qualifier_and_missing_reference_stay_non_evaluable():
    early, _ = nomination_from_sweet_row(
        _sweet_row(origin_setup="MUA EARLY", origin_group="MUA EARLY", origin_ema9=27.1),
        session_t=DAY,
        market_real=8,
        observed_at=_ts("10:05"),
    )
    early_result = evaluate_shadow_action(asdict(early), _pull_bars())
    assert early_result.condition_met is False
    assert early_result.non_event_reason == REASON_MISSING_QUALIFIER
    assert early_result.route == "UNKNOWN"

    manh, _ = nomination_from_sweet_row(
        _sweet_row(origin_setup="CP MẠNH", origin_group="CP MẠNH", origin_ema9=27.1, origin_pull_label=""),
        session_t=DAY,
        market_real=8,
        observed_at=_ts("10:05"),
    )
    manh_result = evaluate_shadow_action(asdict(manh), _pull_bars())
    assert manh_result.condition_met is False
    assert manh_result.non_event_reason == REASON_MISSING_REFERENCE
    assert manh_result.route == "UNKNOWN"
    assert manh.source_action == "OBSERVE"

    watched = FrozenNomination(
        symbol="HPG",
        session=DAY,
        setup="",
        candidate_first_seen_ts=f"{DAY}T09:00:00+07:00",
        eligible_from=f"{DAY}T09:00:00+07:00",
        origin_group="THEO DÕI",
        source="market_aware_sweetspot",
    )
    unsupported = evaluate_shadow_action(watched, _pull_bars())
    assert unsupported.condition_met is False
    assert unsupported.non_event_reason == REASON_UNSUPPORTED_ORIGIN


def test_supported_setup_reaches_condition_met_and_market_block_keeps_it():
    ready = evaluate_shadow_action(_nom("PULL VỪA"), _pull_bars())
    assert ready.condition_met is True
    assert ready.research_decision == RESEARCH_DECISION_SHADOW_BUY
    assert ready.action_state == STATE_BUY_READY
    assert ready.condition_reason == REASON_PULL_BUY_READY
    assert ready.market_ok is True
    assert ready.market_blocked is False
    assert ready.first_met_at.endswith("09:25:00+07:00")
    _assert_no_execution(ready)

    blocked = evaluate_shadow_action(
        _nom("PULL VỪA", market=MARKET_PERMISSION_WEAK, market_real=5.0),
        _pull_bars(),
    )
    assert blocked.condition_met is True
    assert blocked.research_decision == RESEARCH_DECISION_SHADOW_BUY
    assert blocked.action_state != STATE_BUY_READY
    assert blocked.market_ok is False
    assert blocked.market_blocked is True
    assert blocked.market_permission == MARKET_PERMISSION_WEAK
    assert blocked.market_real == 5.0
    assert market_permission(5) == MARKET_PERMISSION_WEAK
    assert MARKET_WEAK_THRESHOLD == 6
    _assert_no_execution(blocked)


def test_when_not_met_and_short_history_are_not_shadow_buy():
    short = evaluate_shadow_action(_nom("PULL VỪA"), _pull_bars()[:1])
    assert short.condition_met is False
    assert short.non_event_reason == REASON_INSUFFICIENT_BARS
    waiting = evaluate_shadow_action(
        _nom("PULL VỪA"),
        [
            _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION"),
            _bar("09:20", close_vs_ref=-40, vol_state="CONTRACTION"),
        ],
    )
    assert waiting.condition_met is False
    assert waiting.non_event_reason == REASON_WHEN_NOT_MET


def test_first_met_survives_reversal_and_rerun(tmp_path: Path):
    nom = _nom("PULL VỪA")
    met = evaluate_shadow_action(nom, _pull_bars())
    price = met.price_at_first_met
    when = met.first_met_at
    first = try_record_shadow_buy(nom, met, directory=tmp_path)
    assert first["appended"] is True

    reversed_bars = _pull_bars() + [_bar("11:00", close_vs_ref=-200, vol_state="CONTRACTION")]
    later = evaluate_shadow_action(nom, reversed_bars)
    assert later.condition_met is True
    assert later.action_state != STATE_BUY_READY
    assert later.first_met_at == when
    assert later.price_at_first_met == price
    again = try_record_shadow_buy(nom, later, directory=tmp_path)
    assert again["appended"] is False
    same = try_record_shadow_buy(nom, met, directory=tmp_path)
    assert same["appended"] is False

    events = load_shadow_buy_events(tmp_path)
    assert len(events) == 1
    event = events[0]
    assert event["research_decision"] == "SHADOW_BUY"
    assert event["first_met_at"] == when
    assert event["price_at_first_met"] == price
    assert event["legal_bar_ts"] == when
    assert event["condition_met"] is True
    assert event["execution_enabled"] is False
    assert event["candidate_is_buy"] is False
    assert event["pxv_implies_buy"] is False
    assert event["alert_eligible"] is False
    assert "t3_return_pct" not in event
    assert "t5_return_pct" not in event
    assert "t10_return_pct" not in event

    shown = _display_rows(events)
    assert shown[0]["decision"] == "SHADOW BUY"
    assert shown[0]["symbol"] == "HPG"
    assert PANEL_TITLE == "RESEARCH / SHADOW — NO EXECUTION"


def test_market_blocked_event_is_labeled_and_not_a_production_buy(tmp_path: Path):
    nom = _nom("PULL VỪA", market=MARKET_PERMISSION_WEAK, market_real=4.5)
    blocked = evaluate_shadow_action(nom, _pull_bars())
    try_record_shadow_buy(nom, blocked, directory=tmp_path)
    event = load_shadow_buy_events(tmp_path)[0]
    assert event["market_ok"] is False
    assert event["market_blocked"] is True
    assert event["market_permission"] == MARKET_PERMISSION_WEAK
    assert event["action_state"] != STATE_BUY_READY
    assert event["execution_enabled"] is False
    shown = _display_rows([event])[0]
    assert shown["decision"] == "SHADOW BUY — MARKET BLOCKED"


def test_order_paths_do_not_read_the_ledger():
    untouched = [
        "position_guardian.py",
        "modules/candidate_router/router.py",
        "modules/candidate_router/contract.py",
        "modules/rotation_watch/engine.py",
        "modules/earning_learning.py",
        "modules/evolution_health.py",
        "modules/research_evolution_ledger/ledger.py",
        "modules/live_candidate_v2_action/live_universe.py",
        "modules/live_candidate_v2_nomination/predicate.py",
    ]
    for rel in untouched:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "research_shadow_buy" not in text
        assert "shadow_buy_events" not in text

    app = (REPO / "app.py").read_text(encoding="utf-8")
    for start, end in (
        ("def buy_recommendation", "def build_buy_table"),
        ("def elite_nav_v2", "def build_buy_elite_decision_engine"),
        ("def calc_market_real", "def calc_market_live"),
    ):
        body = app[app.index(start):app.index(end, app.index(start) + 10)]
        assert "research_shadow_buy" not in body
        assert "shadow_buy_events" not in body
    assert SRC_MARKET_AWARE_SWEETSPOT not in ENABLED_SOURCES
