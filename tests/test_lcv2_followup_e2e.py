"""Multi-session integration tests for Follow-up Watch SHADOW E2E runtime."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from modules.live_candidate_v2_action.contract import STATE_BUY_READY, STATE_WAIT
from modules.live_candidate_v2_action.state import ActionResult
from modules.live_candidate_v2_followup.contract import (
    ARM_FOLLOWUP,
    ARM_FOLLOWUP_GUARDIAN,
    FOLLOWUP_CANDIDATE_IS_BUY,
    FOLLOWUP_ALERT_ELIGIBLE,
    REASON_INGESTED,
    REASON_TTL_EXPIRED,
    STATUS_EXPIRED,
    STATUS_REJECTED,
)
from modules.live_candidate_v2_followup.measure import load_ledger, mature_buy_ready_outcomes
from modules.live_candidate_v2_followup.registry import (
    RegistryCorruptError,
    load_registry,
    registry_path,
)
from modules.live_candidate_v2_followup.runtime import (
    enrich_rows_with_followup_camera,
    run_followup_runtime_cycle,
    weekday_trading_dates,
    write_camera_queue,
)
from modules.live_candidate_v2_followup.session import (
    run_followup_session,
    sessions_elapsed_inclusive,
)
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Includes weekend gap 2026-10-10 → 2026-10-13 (skip Sat/Sun).
DATES = (
    "2026-10-06",
    "2026-10-07",
    "2026-10-08",
    "2026-10-09",
    "2026-10-10",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
)


def _ts(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T10:00:00+07:00")


def _sidecar(symbol: str, session: str, setup: str = "PULL ĐẸP") -> dict:
    return {
        "symbol": symbol,
        "session": session,
        "setup": setup,
        "group": setup,
        "source": SRC_BRAIN_A,
        "nomination_source": SRC_BRAIN_A,
        "candidate_first_seen_ts": f"{session}T09:20:00+07:00",
        "eligible_from": f"{session}T09:15:00+07:00",
        "price_at_first_seen": 20.0,
        "ema9_at_first_seen": 19.5,
        "breakout_ref_at_first_seen": 21.0,
        "shadow_action": STATE_WAIT,
        "action_state": STATE_WAIT,
        "market_real": 7.0,
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
    }


def _scan(symbol: str, *, setup="PULL ĐẸP", price=20.0, ema9=19.5, ma20=19.0, obv="UP"):
    return {
        "symbol": symbol,
        "group": setup,
        "price": price,
        "ema9": ema9,
        "ma20": ma20,
        "obv_status": obv,
        "rs5": 1.0,
        "rs10": 0.5,
        "volume_ratio": 1.0,
    }


def _wait(nom, bars, **kwargs):
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


def test_flag_default_off_and_constants():
    assert FOLLOWUP_CANDIDATE_IS_BUY is False
    assert FOLLOWUP_ALERT_ELIGIBLE is False


def test_weekend_gap_not_counted_as_trading_session():
    # 10 → 13 is next trading day after weekend; elapsed from 06 to 13 = 6 sessions.
    assert sessions_elapsed_inclusive(DATES[0], DATES[4], DATES) == 5
    assert sessions_elapsed_inclusive(DATES[0], DATES[5], DATES) == 6
    assert "2026-10-11" not in DATES and "2026-10-12" not in DATES


def test_multi_session_ttl_and_guardian_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_DIR", str(tmp_path))
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_MARKET_REAL", "7.0")
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_TRADING_DATES", ",".join(DATES))

    # Day 0 ingest + WAIT
    out0 = run_followup_runtime_cycle(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        sidecar_rows=[_sidecar("AAA", DATES[0])],
        scan_by_symbol={"AAA": _scan("AAA")},
        directory=tmp_path,
        force=True,
        allow_retry=True,
    )
    assert out0["ok"] is True
    assert out0["enabled"] is True
    assert len(out0["ingested"]) == 1
    assert FOLLOWUP_CANDIDATE_IS_BUY is False

    # Days 1-4 continue WAIT (healthy)
    for day in DATES[1:5]:
        out = run_followup_runtime_cycle(
            session=day,
            observed_at=_ts(day),
            sidecar_rows=[],
            scan_by_symbol={"AAA": _scan("AAA", price=20.5, ema9=20.0, ma20=19.5)},
            directory=tmp_path,
            force=True,
            allow_retry=True,
        )
        assert out["ok"] is True
        statuses = [r.get("status") for r in out["results"]]
        assert STATUS_REJECTED not in statuses
        assert STATUS_EXPIRED not in statuses

    # Day 5 (index 5 = 2026-10-13) → elapsed 6 → EXPIRED
    out_x = run_followup_runtime_cycle(
        session=DATES[5],
        observed_at=_ts(DATES[5]),
        sidecar_rows=[],
        scan_by_symbol={"AAA": _scan("AAA")},
        directory=tmp_path,
        force=True,
        allow_retry=True,
    )
    assert any(r.get("status") == STATUS_EXPIRED for r in out_x["results"])
    assert any(r.get("reason") == REASON_TTL_EXPIRED for r in out_x["results"])
    reg = load_registry(tmp_path)
    assert any(c["status"] == STATUS_EXPIRED for c in reg["candidates"].values())


def test_restart_retry_does_not_duplicate_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_DIR", str(tmp_path))
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_TRADING_DATES", ",".join(DATES))

    kwargs = dict(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        sidecar_rows=[_sidecar("BBB", DATES[0])],
        scan_by_symbol={"BBB": _scan("BBB")},
        directory=tmp_path,
        force=True,
    )
    a = run_followup_runtime_cycle(**kwargs, allow_retry=False)
    b = run_followup_runtime_cycle(**kwargs, allow_retry=False)
    assert a["ok"] and b.get("idempotent_skip") is True
    rows = [r for r in load_ledger(tmp_path) if r.get("symbol") == "BBB"]
    # One ingest pair (B+C) + eval rows — not doubled by retry.
    n_ingest = sum(1 for r in rows if r.get("reason") == "INGESTED")
    assert n_ingest == 2  # arms B and C once each
    reg = load_registry(tmp_path)
    assert len(reg["candidates"]) == 1
    hist = next(iter(reg["candidates"].values()))["status_history"]
    ingest_hits = [h for h in hist if h.get("reason") == REASON_INGESTED]
    assert len(ingest_hits) == 1


def test_flag_off_runtime_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("MRBOT_V2_FOLLOWUP_WATCH", raising=False)
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_DIR", str(tmp_path))
    out = run_followup_runtime_cycle(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        sidecar_rows=[_sidecar("CCC", DATES[0])],
        directory=tmp_path,
    )
    assert out["enabled"] is False
    assert not registry_path(tmp_path).exists()


def test_corrupt_registry_quarantined_not_silent_reset(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_DIR", str(tmp_path))
    path = registry_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RegistryCorruptError):
            load_registry(tmp_path)
    assert not path.exists()
    quarantined = list(tmp_path.glob("followup_registry.json.corrupt.*"))
    assert len(quarantined) == 1
    assert "quarantined" in caplog.text.lower() or "corrupt" in caplog.text.lower()


def test_camera_bridge_adds_followup_without_buy_rights(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    now = _ts(DATES[1])
    baseline = [_sidecar("BASE", DATES[1])]
    follow = [
        {
            "symbol": "FU1",
            "session": DATES[1],
            "setup": "PULL ĐẸP",
            "group": "PULL ĐẸP",
            "candidate_first_seen_ts": f"{DATES[0]}T09:20:00+07:00",
            "eligible_from": f"{DATES[1]}T09:15:00+07:00",
            "ema9_at_first_seen": 10.0,
            "shadow_action": STATE_BUY_READY,  # must be stripped
            "candidate_is_buy": True,  # must be forced false
        }
    ]
    write_camera_queue(follow, session=DATES[1], directory=tmp_path)
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_DIR", str(tmp_path))
    merged = enrich_rows_with_followup_camera(
        baseline, now=now, session=DATES[1], directory=tmp_path
    )
    assert merged["enabled"] is True
    assert len(merged["followup_added"]) == 1
    added = merged["followup_added"][0]
    assert added["candidate_is_buy"] is False
    assert added["alert_eligible"] is False
    assert added["pxv_implies_buy"] is False
    assert "shadow_action" not in added
    symbols = {r["symbol"] for r in merged["universe"].fetch}
    assert "FU1" in symbols
    assert "BASE" in symbols


def test_as_of_maturity_blocks_future_prices(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    # Seed a REJECTED ledger row manually via session
    run_followup_session(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[_sidecar("DDD", DATES[0])],
        scan_by_symbol={"DDD": _scan("DDD")},
        directory=tmp_path,
        force=True,
        evaluate=_wait,
    )
    run_followup_session(
        session=DATES[1],
        observed_at=_ts(DATES[1]),
        market_real=7.0,
        trading_dates=DATES,
        sidecar_rows=[],
        scan_by_symbol={
            "DDD": _scan("DDD", price=17.0, ema9=19.0, ma20=20.0, obv="DOWN")
        },
        directory=tmp_path,
        force=True,
        evaluate=_wait,
    )
    reg = load_registry(tmp_path)
    assert any(c["status"] == STATUS_REJECTED for c in reg["candidates"].values())

    prices = {
        "DDD": {
            DATES[1]: 17.0,
            DATES[2]: 18.0,
            DATES[3]: 19.0,
            DATES[4]: 20.0,
            DATES[5]: 21.0,
            DATES[6]: 22.0,
        }
    }
    # as_of = reject day → T3 not available yet (needs 3 later sessions)
    early = mature_buy_ready_outcomes(
        directory=tmp_path,
        symbol_session_prices=prices,
        vnindex_session_prices={d: 1000.0 + i for i, d in enumerate(DATES)},
        trading_dates=DATES,
        as_of_session=DATES[1],
    )
    assert early["matured"] == 0
    # as_of with ≥ T3 sessions after reject (DATES[1]+3 = DATES[4])
    late = mature_buy_ready_outcomes(
        directory=tmp_path,
        symbol_session_prices=prices,
        vnindex_session_prices={d: 1000.0 + i for i, d in enumerate(DATES)},
        trading_dates=DATES,
        as_of_session=DATES[4],
    )
    assert late["matured"] >= 1
    matured_rows = [
        r
        for r in load_ledger(tmp_path)
        if r.get("record_kind") == "OUTCOME_MATURED" and r.get("symbol") == "DDD"
    ]
    assert matured_rows
    assert all(r.get("t3_return_pct") is not None for r in matured_rows)
    # Must not have used sessions after as_of
    assert all((r.get("as_of_session") or "") <= DATES[4] for r in matured_rows)


def test_abc_arms_present_including_false_reject_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MRBOT_V2_FOLLOWUP_WATCH", "1")
    run_followup_runtime_cycle(
        session=DATES[0],
        observed_at=_ts(DATES[0]),
        sidecar_rows=[_sidecar("EEE", DATES[0])],
        action_baseline_rows=[
            {**_sidecar("EEE", DATES[0]), "shadow_action": STATE_WAIT, "action_state": STATE_WAIT}
        ],
        scan_by_symbol={"EEE": _scan("EEE")},
        trading_dates=DATES,
        market_real=7.0,
        directory=tmp_path,
        force=True,
        allow_retry=True,
    )
    rows = load_ledger(tmp_path)
    arms = {r.get("arm") for r in rows}
    assert "A_BASELINE_V2" in arms
    assert ARM_FOLLOWUP in arms
    assert ARM_FOLLOWUP_GUARDIAN in arms


def test_weekday_fallback_skips_weekend():
    # 2026-10-10=Sat, 2026-10-11=Sun, 2026-10-12=Mon, 2026-10-13=Tue
    dates = weekday_trading_dates("2026-10-13", lookback_calendar_days=10)
    assert "2026-10-10" not in dates
    assert "2026-10-11" not in dates
    assert "2026-10-12" in dates
    assert "2026-10-13" in dates
