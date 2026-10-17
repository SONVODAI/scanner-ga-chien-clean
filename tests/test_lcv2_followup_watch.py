"""Tests for Live Candidate V2 Follow-up Watch V1 + Candidate Guardian."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from modules.live_candidate_v2_action.contract import STATE_BUY_READY, STATE_WAIT
from modules.live_candidate_v2_action.state import ActionResult
from modules.live_candidate_v2_camera.contract import SRC_MARKET_AWARE_SWEETSPOT
from modules.live_candidate_v2_followup.camera_bridge import merge_followup_into_actionable
from modules.live_candidate_v2_followup.candidate_guardian import (
    QUALITY_REJECTED,
    QUALITY_STABLE,
    QUALITY_STRONGER,
    QUALITY_WEAKENING,
    classify_candidate_quality,
)
from modules.live_candidate_v2_followup.contract import (
    ARM_FOLLOWUP,
    ARM_FOLLOWUP_GUARDIAN,
    REASON_CANDIDATE_GUARDIAN_REJECT,
    REASON_CANDIDATE_WEAKENING_BLOCK,
    REASON_MARKET_NOT_OK,
    REASON_QUALITY_STRONGER_WAIT,
    REASON_SETUP_EMPTY,
    REASON_TTL_EXPIRED,
    STATUS_ACTIVE,
    STATUS_BUY_READY,
    STATUS_EXPIRED,
    STATUS_REJECTED,
    TTL_SESSIONS_INCLUSIVE,
    followup_enabled,
)
from modules.live_candidate_v2_followup.guardian_bridge import is_guardian_sell
from modules.live_candidate_v2_followup.measure import (
    load_ledger,
    mature_buy_ready_outcomes,
    record_baseline_action_rows,
    summarize_arms,
)
from modules.live_candidate_v2_followup.registry import load_registry
from modules.live_candidate_v2_followup.session import (
    run_followup_session,
    sessions_elapsed_inclusive,
)
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

VN = ZoneInfo("Asia/Ho_Chi_Minh")
DATES = (
    "2026-10-06",
    "2026-10-07",
    "2026-10-08",
    "2026-10-09",
    "2026-10-10",
    "2026-10-13",
    "2026-10-14",
)


def _ts(day: str, hhmm: str = "10:00:00") -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}+07:00")


def _sidecar_row(
    symbol: str,
    *,
    session: str,
    setup: str = "",
    source: str = SRC_BRAIN_A,
    state: str = STATE_WAIT,
) -> dict:
    return {
        "symbol": symbol,
        "session": session,
        "setup": setup,
        "group": setup,
        "source": source,
        "nomination_source": source,
        "candidate_first_seen_ts": f"{session}T09:20:00+07:00",
        "eligible_from": f"{session}T09:15:00+07:00",
        "price_at_first_seen": 20.0,
        "ema9_at_first_seen": 19.5,
        "breakout_ref_at_first_seen": 21.0,
        "shadow_action": state,
        "action_state": state,
        "market_real": 7.0,
        "market_permission": "OK",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
    }


def _fake_buy_ready(nom, bars, **kwargs):
    return ActionResult(
        action_state=STATE_BUY_READY,
        action_reason="TEST_BUY_READY",
        route="PULL",
        symbol=str(getattr(nom, "symbol", "")),
        session=str(getattr(nom, "session", "")),
        setup=str(getattr(nom, "setup", "")),
        market_permission=str(getattr(nom, "market_permission", "")),
        first_met_at=_ts(str(getattr(nom, "session", DATES[0]))).isoformat(),
        price_at_first_met=21.5,
        condition_met=True,
        research_decision="SHADOW_BUY",
        market_ok=True,
    )


def _fake_wait(nom, bars, **kwargs):
    return ActionResult(
        action_state=STATE_WAIT,
        action_reason="WAIT_CONFIRMATION_INCOMPLETE",
        route="PULL",
        symbol=str(getattr(nom, "symbol", "")),
        session=str(getattr(nom, "session", "")),
        setup=str(getattr(nom, "setup", "")),
        market_permission=str(getattr(nom, "market_permission", "")),
        condition_met=False,
        market_ok=True,
    )


def _ingest(tmp_path, monkeypatch, symbol: str, setup: str = "PULL ĐẸP"):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    day0 = DATES[0]
    run_followup_session(
        session=day0,
        observed_at=_ts(day0),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar_row(symbol, session=day0, setup=setup)],
        scan_by_symbol={
            symbol: {
                "symbol": symbol,
                "group": setup,
                "price": 20.0,
                "ema9": 19.5,
                "ma20": 19.0,
                "obv_status": "UP",
                "rs5": 1.0,
                "rs10": 0.5,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("MRBOT_V2_FOLLOWUP_WATCH", raising=False)
    assert followup_enabled() is False
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "0")
    assert followup_enabled() is False
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    assert followup_enabled() is True


def test_flag_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("MRBOT_V2_FOLLOWUP_WATCH", raising=False)
    out = run_followup_session(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar_row("AAA", session=DATES[0], setup="PULL ĐẸP")],
        directory=tmp_path,
    )
    assert out["enabled"] is False
    assert out["reason"] == "FEATURE_FLAG_OFF"
    assert not (tmp_path / "followup_registry.json").exists()


def test_ttl_inclusive_five_sessions():
    assert sessions_elapsed_inclusive(DATES[0], DATES[0], DATES) == 1
    assert sessions_elapsed_inclusive(DATES[0], DATES[4], DATES) == 5
    assert sessions_elapsed_inclusive(DATES[0], DATES[5], DATES) == 6


def test_ingest_and_empty_setup_stays_wait(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    day0 = DATES[0]
    out = run_followup_session(
        session=day0,
        observed_at=_ts(day0),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[
            _sidecar_row("AAA", session=day0, setup="", source=SRC_MARKET_AWARE_SWEETSPOT)
        ],
        scan_by_symbol={"AAA": {"symbol": "AAA", "group": "", "price": 20.0}},
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    assert out["enabled"] is True
    assert len(out["ingested"]) == 1
    reg = load_registry(tmp_path)
    key = next(iter(reg["candidates"]))
    assert reg["candidates"][key]["status"] == STATUS_ACTIVE
    assert out["results"][0]["reason"] == REASON_SETUP_EMPTY
    assert out["camera_rows"] == []


def test_ttl_expires_after_five_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    day0 = DATES[0]
    run_followup_session(
        session=day0,
        observed_at=_ts(day0),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar_row("BBB", session=day0, setup="PULL ĐẸP")],
        scan_by_symbol={"BBB": {"symbol": "BBB", "group": "PULL ĐẸP", "price": 10, "ema9": 9.5, "ma20": 9.0}},
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    out = run_followup_session(
        session=DATES[5],
        observed_at=_ts(DATES[5]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={"BBB": {"symbol": "BBB", "group": "PULL ĐẸP", "price": 10, "ema9": 9.5, "ma20": 9.0}},
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    assert out["results"][0]["status"] == STATUS_EXPIRED
    assert out["results"][0]["reason"] == REASON_TTL_EXPIRED
    reg = load_registry(tmp_path)
    assert any(c["status"] == STATUS_EXPIRED for c in reg["candidates"].values())


def test_position_guardian_sell_does_not_hard_reject(tmp_path, monkeypatch):
    """Position Guardian BÁN is soft evidence — Candidate Guardian decides reject."""
    _ingest(tmp_path, monkeypatch, "CCC")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            # Healthy stack: price > ema9 > ma20 — CG stays STRONGER/STABLE
            "CCC": {
                "symbol": "CCC",
                "group": "PULL ĐẸP",
                "price": 21.0,
                "ema9": 20.0,
                "ma20": 19.0,
                "obv_status": "UP",
                "rs5": 1.5,
                "rs10": 1.0,
            }
        },
        guardian_by_symbol={"CCC": "🔴 BÁN"},
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    assert is_guardian_sell("🔴 BÁN") is True
    assert out["results"][0]["status"] != STATUS_REJECTED
    assert out["results"][0]["position_guardian_sell"] is True
    assert out["results"][0]["status"] == "WAIT"


def test_healthy_pullback_not_rejected(tmp_path, monkeypatch):
    q = classify_candidate_quality(
        {
            "group": "PULL ĐẸP",
            "price": 19.4,
            "ema9": 20.0,
            "ma20": 19.0,
            "obv_status": "UP",
            "volume_ratio": 0.8,
            "rs5": 0.2,
            "rs10": 0.1,
        },
        original_setup="PULL ĐẸP",
    )
    assert q.label == QUALITY_STABLE
    assert q.healthy_pullback is True
    assert q.reject is False

    _ingest(tmp_path, monkeypatch, "HPB")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "HPB": {
                "symbol": "HPB",
                "group": "PULL ĐẸP",
                "price": 19.4,
                "ema9": 20.0,
                "ma20": 19.0,
                "obv_status": "UP",
                "volume_ratio": 0.8,
                "rs5": 0.2,
                "rs10": 0.1,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    assert out["results"][0]["status"] == "WAIT"
    assert out["results"][0]["candidate_quality"] == QUALITY_STABLE
    reg = load_registry(tmp_path)
    assert all(c["status"] == STATUS_ACTIVE for c in reg["candidates"].values())


def test_confirmed_weakening_rejected(tmp_path, monkeypatch):
    q = classify_candidate_quality(
        {
            "group": "PULL ĐẸP",
            "price": 17.0,
            "ema9": 19.0,
            "ma20": 20.0,
            "obv_status": "DOWN",
            "volume_ratio": 1.5,
            "rs5": -3.0,
            "rs10": -2.5,
        },
        original_setup="PULL ĐẸP",
    )
    assert q.label == QUALITY_REJECTED
    assert q.reject is True

    _ingest(tmp_path, monkeypatch, "WKN")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "WKN": {
                "symbol": "WKN",
                "group": "PULL ĐẸP",
                "price": 17.0,
                "ema9": 19.0,
                "ma20": 20.0,
                "obv_status": "DOWN",
                "volume_ratio": 1.5,
                "rs5": -3.0,
                "rs10": -2.5,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert out["results"][0]["status"] == STATUS_REJECTED
    assert out["results"][0]["reason"] == REASON_CANDIDATE_GUARDIAN_REJECT
    # Arm B counterfactual may still be BUY_READY without CG.
    assert out["results"][0]["status_b"] == STATUS_BUY_READY
    reg = load_registry(tmp_path)
    assert any(c["status"] == STATUS_REJECTED for c in reg["candidates"].values())


def test_stronger_continues_wait_no_auto_buy_ready(tmp_path, monkeypatch):
    q = classify_candidate_quality(
        {
            "group": "PULL ĐẸP",
            "price": 22.0,
            "ema9": 21.0,
            "ma20": 20.0,
            "obv_status": "UP",
            "rs5": 2.0,
            "rs10": 1.5,
        },
        original_setup="PULL ĐẸP",
    )
    assert q.label == QUALITY_STRONGER

    _ingest(tmp_path, monkeypatch, "STR")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "STR": {
                "symbol": "STR",
                "group": "PULL ĐẸP",
                "price": 22.0,
                "ema9": 21.0,
                "ma20": 20.0,
                "obv_status": "UP",
                "rs5": 2.0,
                "rs10": 1.5,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    assert out["results"][0]["status"] == "WAIT"
    assert out["results"][0]["reason"] == REASON_QUALITY_STRONGER_WAIT
    assert out["results"][0]["candidate_quality"] == QUALITY_STRONGER
    assert out["results"][0]["action_state"] == STATE_WAIT


def test_weak_market_strong_stock_keeps_watching(tmp_path, monkeypatch):
    _ingest(tmp_path, monkeypatch, "MKT")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=5.0,  # < 6 → Market Permission not OK
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "MKT": {
                "symbol": "MKT",
                "group": "CP MẠNH",
                "price": 25.0,
                "ema9": 24.0,
                "ma20": 23.0,
                "obv_status": "UP",
                "rs5": 3.0,
                "rs10": 2.0,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert out["results"][0]["status"] == "WAIT"
    assert out["results"][0]["reason"] == REASON_MARKET_NOT_OK
    assert out["results"][0]["status"] != STATUS_REJECTED
    reg = load_registry(tmp_path)
    assert all(c["status"] == STATUS_ACTIVE for c in reg["candidates"].values())


def test_weakening_blocks_buy_ready_arm_c_only(tmp_path, monkeypatch):
    # Trend broken without flow confirm → WEAKENING (not yet REJECTED)
    q = classify_candidate_quality(
        {
            "group": "PULL ĐẸP",
            "price": 18.0,
            "ema9": 19.0,
            "ma20": 20.0,
            "obv_status": "UP",
            "volume_ratio": 0.7,
            "rs5": 0.0,
            "rs10": 0.0,
        },
        original_setup="PULL ĐẸP",
    )
    assert q.label == QUALITY_WEAKENING
    assert q.block_buy_ready is True

    _ingest(tmp_path, monkeypatch, "WSB")
    out = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "WSB": {
                "symbol": "WSB",
                "group": "PULL ĐẸP",
                "price": 18.0,
                "ema9": 19.0,
                "ma20": 20.0,
                "obv_status": "UP",
                "volume_ratio": 0.7,
                "rs5": 0.0,
                "rs10": 0.0,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert out["results"][0]["status"] == "WAIT"
    assert out["results"][0]["reason"] == REASON_CANDIDATE_WEAKENING_BLOCK
    assert out["results"][0]["status_b"] == STATUS_BUY_READY
    assert out["results"][0]["action_state"] == STATE_WAIT


def test_no_buy_ready_from_stale_setup_or_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    day0 = DATES[0]
    run_followup_session(
        session=day0,
        observed_at=_ts(day0),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar_row("DDD", session=day0, setup="PULL ĐẸP")],
        scan_by_symbol={"DDD": {"symbol": "DDD", "group": "PULL ĐẸP", "price": 12, "ema9": 11, "ma20": 10}},
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    # Empty setup this session — must not inherit day0 setup into BUY_READY.
    blocked_setup = run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.5,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={"DDD": {"symbol": "DDD", "group": "", "price": 12, "ema9": 11, "ma20": 10}},
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert blocked_setup["results"][0]["status"] == "WAIT"
    assert blocked_setup["results"][0]["reason"] == REASON_SETUP_EMPTY

    # Weak market blocks BUY_READY even with setup + fake evaluator.
    blocked = run_followup_session(
        session=DATES[2],
        observed_at=_ts(DATES[2]),
        market_real=5.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "DDD": {
                "symbol": "DDD",
                "group": "PULL ĐẸP",
                "price": 12,
                "ema9": 11,
                "ma20": 10,
                "obv_status": "UP",
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert blocked["results"][0]["status"] == "WAIT"
    assert blocked["results"][0]["action_state"] == STATE_WAIT

    ready = run_followup_session(
        session=DATES[3],
        observed_at=_ts(DATES[3]),
        market_real=7.5,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "DDD": {
                "symbol": "DDD",
                "group": "PULL ĐẸP",
                "price": 12,
                "ema9": 11,
                "ma20": 10,
                "obv_status": "UP",
                "rs5": 1.0,
                "rs10": 0.5,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    assert ready["results"][0]["status"] == STATUS_BUY_READY
    reg = load_registry(tmp_path)
    assert any(c["status"] == STATUS_BUY_READY for c in reg["candidates"].values())


def test_camera_bridge_respects_cap_and_flag(monkeypatch):
    monkeypatch.delenv("MRBOT_V2_FOLLOWUP_WATCH", raising=False)
    now = _ts(DATES[0])
    base = [
        _sidecar_row("E1", session=DATES[0], setup="PULL ĐẸP"),
        _sidecar_row("E2", session=DATES[0], setup="CP MẠNH"),
    ]
    follow = [
        {
            "symbol": "F1",
            "session": DATES[0],
            "setup": "PULL ĐẸP",
            "group": "PULL ĐẸP",
            "candidate_first_seen_ts": f"{DATES[0]}T09:20:00+07:00",
            "eligible_from": f"{DATES[0]}T09:15:00+07:00",
            "ema9_at_first_seen": 10.0,
        }
    ]
    off = merge_followup_into_actionable(base, follow, now=now, cap=50)
    assert off["enabled"] is False
    assert off["followup_added"] == []

    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    on = merge_followup_into_actionable(base, follow, now=now, cap=50, enabled=True)
    assert on["n_followup_added"] == 1
    assert {r["symbol"] for r in on["fetch"]} >= {"E1", "E2", "F1"}

    capped = merge_followup_into_actionable(base, follow, now=now, cap=2, enabled=True)
    assert capped["n_baseline"] == 2
    assert capped["n_followup_added"] == 0
    assert capped["followup_skipped_cap"]


def test_registry_survives_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    run_followup_session(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar_row("EEE", session=DATES[0], setup="PULL VỪA")],
        directory=tmp_path,
        force=True,
        evaluate=_fake_wait,
    )
    path = tmp_path / "followup_registry.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"].startswith("live_candidate_v2_followup_registry")
    again = load_registry(tmp_path)
    assert len(again["candidates"]) == 1


def test_measurement_arms_parallel_b_and_c(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    record_baseline_action_rows(
        session=DATES[0],
        action_rows=[_sidecar_row("ZZZ", session=DATES[0], setup="PULL ĐẸP", state=STATE_BUY_READY)],
        directory=tmp_path,
    )
    _ingest(tmp_path, monkeypatch, "YYY")
    # Reject via Candidate Guardian; arm B counterfactual BUY_READY.
    run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "YYY": {
                "symbol": "YYY",
                "group": "PULL ĐẸP",
                "price": 17.0,
                "ema9": 19.0,
                "ma20": 20.0,
                "obv_status": "DOWN",
                "volume_ratio": 1.4,
            }
        },
        directory=tmp_path,
        force=True,
        evaluate=_fake_buy_ready,
    )
    rows = load_ledger(tmp_path)
    assert any(r.get("arm") == "A_BASELINE_V2" for r in rows)
    assert any(r.get("arm") == ARM_FOLLOWUP for r in rows)
    assert any(r.get("arm") == ARM_FOLLOWUP_GUARDIAN for r in rows)
    arm_b = [r for r in rows if r.get("arm") == ARM_FOLLOWUP and r.get("symbol") == "YYY"]
    arm_c = [r for r in rows if r.get("arm") == ARM_FOLLOWUP_GUARDIAN and r.get("symbol") == "YYY"]
    assert any(r.get("status") == STATUS_BUY_READY for r in arm_b)
    assert any(r.get("status") == STATUS_REJECTED for r in arm_c)

    matured = mature_buy_ready_outcomes(
        directory=tmp_path,
        symbol_session_prices={
            "YYY": {
                DATES[1]: 17.0,
                DATES[2]: 17.5,
                DATES[3]: 18.0,
                DATES[4]: 18.5,
                DATES[5]: 19.0,
                DATES[6]: 19.5,
            }
        },
        vnindex_session_prices={
            DATES[1]: 1000.0,
            DATES[2]: 1001.0,
            DATES[3]: 1002.0,
            DATES[4]: 1003.0,
            DATES[5]: 1005.0,
            DATES[6]: 1006.0,
        },
        trading_dates=DATES,
    )
    assert matured["ok"] is True
    summary = summarize_arms(tmp_path)
    assert "B_FOLLOWUP_WATCH" in summary
    assert "C_FOLLOWUP_GUARDIAN" in summary
    assert TTL_SESSIONS_INCLUSIVE == 5


def test_idempotent_reingest_same_episode(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    row = _sidecar_row("IDF", session=DATES[0], setup="PULL ĐẸP")
    for _ in range(2):
        run_followup_session(
            session=DATES[0],
            observed_at=_ts(DATES[0]),
            market_real=7.0,
            trading_dates=DATES,
            sidecar_rows=[row],
            scan_by_symbol={
                "IDF": {
                    "symbol": "IDF",
                    "group": "PULL ĐẸP",
                    "price": 20,
                    "ema9": 19,
                    "ma20": 18,
                    "obv_status": "UP",
                }
            },
            directory=tmp_path,
            force=True,
            evaluate=_fake_wait,
        )
    reg = load_registry(tmp_path)
    assert len(reg["candidates"]) == 1
