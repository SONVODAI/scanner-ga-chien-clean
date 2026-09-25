"""Current-session research route for a carried Sweet candidate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_v2_action.contract import (
    CANDIDATE_IS_BUY,
    ALERT_ELIGIBLE,
    PXV_IMPLIES_BUY,
    REASON_CURRENT_EARLY_QUALIFIER,
    REASON_CURRENT_UNSUPPORTED,
    STATE_BUY_READY,
)
from modules.live_candidate_v2_action.state import BarEvidence, evaluate_shadow_action, nomination_from_mapping
from modules.live_candidate_v2_camera.sidecar import build_sidecar_from_scan
from modules.live_candidate_v2_nomination.contract import MARKET_PERMISSION_WEAK, SRC_BRAIN_A
from modules.live_candidate_v2_nomination.intent import CANH_ADD_ACTION, CHO_PULL_ACTION
from modules.live_candidate_v2_nomination.sweet_brain_b import BrainBConsult, nomination_from_sweet_row
from modules.research_shadow_buy.acquire import load_research_stamps
from modules.research_shadow_buy.ledger import load_shadow_buy_events, try_record_shadow_buy
from modules.research_shadow_buy.ui import _status_decision

VN = ZoneInfo("Asia/Ho_Chi_Minh")
DAY = "2026-08-25"
REF_C = 27100


def _ts(hm: str, day: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN)


def _sweet(origin_setup: str = "", **extra):
    row = {
        "symbol": "HPG",
        "observer_status": "OBSERVE",
        "created_at": "2026-08-24T11:13:40Z",
        "t0_date": "2026-08-24",
        "price_t0": 27000,
        "matched_sweetspot": "RS5=0 | RS10=-2 | RSI14=40",
        "historical_winrate": 0.8,
        "origin_setup": origin_setup,
        "origin_group": origin_setup,
        "origin_ema9": 11.0,
        "origin_breakout_ref": 99.0,
    }
    row.update(extra)
    nom, _ = nomination_from_sweet_row(row, session_t=DAY, market_real=extra.get("market_real", 5), observed_at=_ts("10:20"))
    assert nom is not None
    consult = BrainBConsult(
        status="NOMINATED",
        session=DAY,
        predecessor="2026-08-24",
        reason="PREDECESSOR_SWEET_OBSERVE",
        nominations=(nom,),
    )
    return consult


def _scan(group: str, **extra) -> dict:
    rec = {
        "symbol": "HPG",
        "date": DAY,
        "group": group,
        "price": 27.5,
        "ema9": 27.1,
        "breakout_ref": 30.0,
        "dist_from_ema9_pct": 1.4,
        "total_score": 5,
        "obv_status": "🟢",
        "warning": "",
    }
    rec.update(extra)
    return rec


def _build(scan, consult, tmp_path: Path, *, when: str = "10:20", market_real: float = 5.0, early=None):
    return build_sidecar_from_scan(
        scan,
        market_real=market_real,
        observed_at=_ts(when),
        brain_b=consult,
        early_lab_symbols=early,
        research_stamp_dir=tmp_path,
    )


def _bar(hm: str, *, close_vs_ref: float, vol_state: str = "NORMAL", kind: str = "EMA9") -> BarEvidence:
    close_c = REF_C + int(close_vs_ref)
    return BarEvidence(
        bar_ts=_ts(hm),
        asof=_ts(hm),
        completed=True,
        close=float(close_c),
        close_canonical=close_c,
        reference_kind=kind,
        reference_value=27.1 if kind == "EMA9" else 30.0,
        reference_canonical=REF_C,
        close_vs_ref=float(close_vs_ref),
        close_vs_ref_pct=(close_vs_ref / REF_C) * 100.0,
        reference_state=kind,
        data_state="QUALIFIED",
        published_evidence="STRENGTHEN" if kind == "BREAKOUT_REF" else "NEUTRAL",
        volume_expansion_state=vol_state,
        price_volume_state="FLAT",
        chronology_legal=True,
    )


def _pull_ready(start: str = "10:20") -> list[BarEvidence]:
    h, m = start.split(":")
    minutes = int(h) * 60 + int(m)
    stamps = []
    for step in (0, 5, 10):
        total = minutes + step
        stamps.append(f"{total // 60:02d}:{total % 60:02d}")
    return [
        _bar(stamps[0], close_vs_ref=-120, vol_state="CONTRACTION"),
        _bar(stamps[1], close_vs_ref=30),
        _bar(stamps[2], close_vs_ref=40),
    ]


def test_yesterday_pull_is_not_inherited_when_today_is_unsupported(tmp_path: Path):
    report, rows = _build([_scan("THEO DÕI")], _sweet("PULL ĐẸP"), tmp_path)
    row = rows[0]
    assert row["source"] == "market_aware_sweetspot"
    assert row["setup"] == ""
    assert row["ema9_at_first_seen"] is None
    assert row["origin_setup"] == "PULL ĐẸP"
    assert row["current_route_status"] == REASON_CURRENT_UNSUPPORTED
    assert row["research_stamp"] is False
    assert report.freeze_ledger == () or all(rec.symbol != "HPG" for rec in report.freeze_ledger)
    assert load_research_stamps(tmp_path) == {}


def test_today_pull_dep_and_vua_freeze_todays_ema9(tmp_path: Path):
    _, dep = _build([_scan("PULL ĐẸP", ema9=21.5)], _sweet(""), tmp_path)
    assert dep[0]["setup"] == "PULL ĐẸP"
    assert dep[0]["ema9_at_first_seen"] == 21.5
    assert dep[0]["origin_ema9"] == 11.0
    assert dep[0]["route_became_evaluable_at"].endswith("10:20:00+07:00")
    assert dep[0]["research_stamp"] is True
    vua_dir = tmp_path / "vua"
    _, vua = _build([_scan("PULL VỪA", ema9=22.0)], _sweet(""), vua_dir)
    assert vua[0]["setup"] == "PULL VỪA"
    assert vua[0]["ema9_at_first_seen"] == 22.0
    assert nomination_from_mapping(vua[0]).route == "PULL"


def test_break_uses_todays_breakout_and_bare_early_does_not_acquire(tmp_path: Path):
    _, rows = _build([_scan("MUA BREAK", breakout_ref=33.0)], _sweet("PULL ĐẸP"), tmp_path)
    assert rows[0]["setup"] == "MUA BREAK"
    assert rows[0]["breakout_ref_at_first_seen"] == 33.0
    assert rows[0]["origin_breakout_ref"] == 99.0
    assert rows[0]["ema9_at_first_seen"] is None
    bare = tmp_path / "bare"
    _, early = _build([_scan("MUA EARLY", total_score=1, obv_status="🔴")], _sweet(""), bare)
    assert early[0]["setup"] == ""
    assert early[0]["current_route_status"] == REASON_CURRENT_EARLY_QUALIFIER
    qualified = tmp_path / "early"
    _, ok = _build([_scan("MUA EARLY", ema9=18.0, dist_from_ema9_pct=1.0)], _sweet(""), qualified)
    assert ok[0]["setup"] == "MUA EARLY"
    assert ok[0]["ema9_at_first_seen"] == 18.0
    assert nomination_from_mapping(ok[0]).route == "EARLY"


def test_cp_manh_uses_existing_distance_and_does_not_invent_cho_pull(tmp_path: Path):
    _, far = _build([_scan("CP MẠNH", dist_from_ema9_pct=5.0, ema9=19.0)], _sweet(""), tmp_path)
    assert far[0]["source_action"] == CHO_PULL_ACTION
    assert nomination_from_mapping(far[0]).route == "PULL"
    near = tmp_path / "near"
    _, close = _build([_scan("CP MẠNH", dist_from_ema9_pct=1.0, ema9=19.5)], _sweet(""), near)
    assert close[0]["source_action"] == CANH_ADD_ACTION
    assert nomination_from_mapping(close[0]).route == "MANH"
    missing = tmp_path / "missing"
    row = _scan("CP MẠNH")
    row.pop("dist_from_ema9_pct")
    _, no_dist = _build([row], _sweet(""), missing)
    assert no_dist[0]["source_action"] != CHO_PULL_ACTION


def test_market_below_six_can_shadow_buy_while_brain_a_rejects(tmp_path: Path):
    report, rows = _build([_scan("PULL ĐẸP", ema9=27.1)], _sweet(""), tmp_path, market_real=5)
    assert report.freeze_ledger == () or all(rec.symbol != "HPG" for rec in report.freeze_ledger)
    assert rows[0]["market_permission"] == MARKET_PERMISSION_WEAK
    nom = nomination_from_mapping(rows[0])
    result = evaluate_shadow_action(nom, _pull_ready("10:20"))
    assert result.condition_met is True
    assert result.research_decision == "SHADOW_BUY"
    assert result.market_blocked is True
    assert result.action_state != STATE_BUY_READY
    assert result.candidate_is_buy is False
    assert result.pxv_implies_buy is False
    assert result.alert_eligible is False
    assert CANDIDATE_IS_BUY is False and PXV_IMPLIES_BUY is False and ALERT_ELIGIBLE is False
    saved = try_record_shadow_buy(nom, result, directory=tmp_path)
    assert saved["appended"] is True
    event = load_shadow_buy_events(tmp_path)[0]
    assert event["candidate_source"] == "market_aware_sweetspot"
    assert event["evaluated_setup"] == "PULL ĐẸP"
    assert event["route_became_evaluable_at"].endswith("10:20:00+07:00")
    assert event["frozen_ref_value"] == 27.1
    assert event["market_blocked"] is True
    assert event["execution_enabled"] is False
    assert "t3_return_pct" not in event
    again = try_record_shadow_buy(nom, result, directory=tmp_path)
    assert again["appended"] is False
    assert len(load_shadow_buy_events(tmp_path)) == 1


def test_brain_a_owns_the_symbol_and_research_stamp_is_not_written(tmp_path: Path):
    report, rows = _build(
        [_scan("PULL ĐẸP", ema9=27.1)],
        _sweet("PULL ĐẸP"),
        tmp_path,
        market_real=7.5,
    )
    assert rows[0]["source"] == SRC_BRAIN_A
    assert rows[0]["setup"] == "PULL ĐẸP"
    assert rows[0]["research_stamp"] is False
    assert any(rec.symbol == "HPG" for rec in report.freeze_ledger)
    assert load_research_stamps(tmp_path) == {}


def test_bars_before_acquisition_cannot_create_shadow_buy(tmp_path: Path):
    _, rows = _build([_scan("PULL ĐẸP", ema9=27.1)], _sweet(""), tmp_path, when="10:20", market_real=5)
    nom = nomination_from_mapping(rows[0])
    early = _pull_ready("09:15") + [
        _bar("10:10", close_vs_ref=-80, vol_state="CONTRACTION"),
        _bar("10:15", close_vs_ref=40),
    ]
    blocked = evaluate_shadow_action(nom, early)
    assert blocked.condition_met is False
    assert blocked.research_decision == ""
    later = evaluate_shadow_action(nom, early + _pull_ready("10:20"))
    assert later.condition_met is True
    assert later.first_met_at.endswith("10:30:00+07:00")
    assert "09:" not in (later.first_met_at or "")
    assert "10:15" not in (later.first_met_at or "")


def test_rerun_does_not_move_the_research_clock_or_reference(tmp_path: Path):
    _build([_scan("PULL ĐẸP", ema9=21.0)], _sweet(""), tmp_path, when="10:20", market_real=5)
    _, rows = _build([_scan("PULL ĐẸP", ema9=88.0)], _sweet(""), tmp_path, when="11:00", market_real=5)
    assert rows[0]["ema9_at_first_seen"] == 21.0
    assert rows[0]["route_became_evaluable_at"].endswith("10:20:00+07:00")
    stamps = load_research_stamps(tmp_path)
    assert len(stamps) == 1
    assert _status_decision({"route_became_evaluable_at": rows[0]["route_became_evaluable_at"], "condition_met": False}) == (
        "CURRENT ROUTE ACQUIRED / WAITING WHEN"
    )
    assert _status_decision({"condition_met": False, "current_route_status": "NO_CURRENT_EVALUABLE_ROUTE"}) == (
        "NO CURRENT EVALUABLE ROUTE"
    )
