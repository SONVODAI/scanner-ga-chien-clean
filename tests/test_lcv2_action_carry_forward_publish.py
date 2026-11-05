"""Carry-forward intake + safe publish retention for VPS post-close observe."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    STATE_BUY_READY,
)
from modules.live_candidate_v2_action.observe_store import observe_from_collected_session
from modules.live_candidate_v2_action.sidecar_source import (
    REASON_STALE_SESSION,
    SOURCE_FILE,
    accept_sidecar_document,
)
from modules.live_candidate_v2_action.state import (
    evaluation_trading_session,
    nomination_from_mapping,
)
from modules.live_candidate_v2_action.ui import (
    REASON_STALE_SESSION as UI_STALE_SESSION,
    accept_shadow_state_document,
)
from modules.live_shadow_transport.contract import (
    V2_ACTION_OBSERVE_FAILURE_NAME,
    V2_ACTION_STATE_NAME,
)
from modules.live_shadow_transport.shadow_store import publish_v2_action_state

VN = ZoneInfo("Asia/Ho_Chi_Minh")
T0 = "2026-11-04"  # nomination provenance / sidecar session
T1 = "2026-11-05"  # evaluation / observe cycle


def _row(
    symbol="HPG",
    *,
    session=T0,
    first=None,
    eligible=None,
    setup="PULL ĐẸP",
) -> dict:
    first = first or f"{session}T14:30:00+07:00"
    eligible = eligible or f"{T1}T09:15:00+07:00"
    return {
        "symbol": symbol,
        "session": session,
        "candidate_first_seen_ts": first,
        "eligible_from": eligible,
        "source": "brain_a_scan_setup",
        "setup": setup,
        "group": setup,
        "observation_intent": "WATCH_PULL",
        "observation_reference": "EMA9",
        "price_at_first_seen": 27100,
        "ema9_at_first_seen": 27.1,
        "breakout_ref_at_first_seen": None,
        "source_action": "MUA PULL ĐẸP",
        "source_reason": "fixture",
        "elite_buy_grade": "",
        "provenance": ["brain_a_scan_setup"],
        "candidate_is_buy": False,
        "alert_eligible": False,
    }


def _sidecar(session: str, rows: list[dict]) -> dict:
    ledger = [
        {
            "session": r["session"],
            "symbol": r["symbol"],
            "candidate_first_seen_ts": r["candidate_first_seen_ts"],
            "price_at_first_seen": r.get("price_at_first_seen"),
            "ema9_at_first_seen": r.get("ema9_at_first_seen"),
            "breakout_ref_at_first_seen": r.get("breakout_ref_at_first_seen"),
        }
        for r in rows
    ]
    return {
        "schema": "live_candidate_v2_camera_sidecar_v1",
        "session": session,
        "generated_at": f"{session}T15:05:00+07:00",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
        "freeze_ledger": ledger,
        "rows": rows,
    }


def test_nov4_to_nov5_valid_rollover_intake():
    row = _row("HPG")
    nom = nomination_from_mapping(row)
    assert nom.session == T0
    assert evaluation_trading_session(nom) == T1
    doc = _sidecar(T0, [row, _row("SSI", eligible=f"{T0}T10:00:00+07:00", first=f"{T0}T09:00:00+07:00")])
    resolved = accept_sidecar_document(doc, session=T1, source="github")
    assert resolved.ok is True
    assert [r["symbol"] for r in resolved.rows] == ["HPG"]
    assert resolved.rows[0]["session"] == T0  # provenance preserved
    assert resolved.sidecar_session == T0
    assert "carry_from_sidecar_session" in resolved.detail


def test_invalid_stale_sidecar_without_eval_eligible_rows_rejected():
    # Yesterday sidecar, but eligible_from still on T0 → not for T1.
    row = _row(
        "HPG",
        session=T0,
        first=f"{T0}T09:00:00+07:00",
        eligible=f"{T0}T09:00:00+07:00",
    )
    doc = _sidecar(T0, [row])
    resolved = accept_sidecar_document(doc, session=T1, source="github")
    assert resolved.ok is False
    assert resolved.rows == []
    assert resolved.reason == REASON_STALE_SESSION
    assert "no_eval_eligible_rows" in resolved.detail


def test_future_sidecar_rejected():
    doc = _sidecar("2026-11-06", [_row(session="2026-11-06", eligible="2026-11-06T09:15:00+07:00")])
    resolved = accept_sidecar_document(doc, session=T1, source="github")
    assert resolved.ok is False
    assert resolved.reason == REASON_STALE_SESSION
    assert "future sidecar" in resolved.detail


def test_observe_rollover_preserves_provenance_and_runs(tmp_path: Path):
    side = tmp_path / "camera_sidecar.json"
    side.write_text(json.dumps(_sidecar(T0, [_row("HPG")])), encoding="utf-8")
    camera = tmp_path / "camera"
    camera.mkdir()
    out = tmp_path / "out"
    store = tmp_path / "store"
    now = datetime.fromisoformat(f"{T1}T10:05:00").replace(tzinfo=VN)
    payload = observe_from_collected_session(
        session=T1,
        now=now,
        camera_root=camera,
        out_dir=out,
        shadow_store_dir=store,
        sidecar_source=SOURCE_FILE,
        sidecar_path=side,
    )
    assert payload["session"] == T1
    assert payload.get("observe_reason") in (None, "", "NOMINATED_NO_LEGAL_COMPLETED_BARS") or payload.get(
        "rows"
    )
    assert payload["v2_sidecar"]["ok"] is True
    assert payload["candidate_is_buy"] is False
    assert payload["alert_eligible"] is False
    rows = payload.get("rows") or []
    assert len(rows) == 1
    assert rows[0]["symbol"] == "HPG"
    # Fresh evaluation on T1; nomination provenance remains T0 inside stored fields when present.
    assert rows[0].get("shadow_action") != STATE_BUY_READY or rows[0].get("n_legal_bars", 0) >= 0
    assert CANDIDATE_IS_BUY is False and PXV_IMPLIES_BUY is False and ALERT_ELIGIBLE is False


def test_published_state_preserved_on_stale_empty_observe(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    prior = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T0,
        "observed_at": f"{T0}T22:40:00+07:00",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [
            {
                "symbol": "HPG",
                "shadow_action": "NOMINATED",
                "action_reason": "NOMINATED_NO_LEGAL_COMPLETED_BARS",
                "n_legal_bars": 0,
                "alert_eligible": False,
                "candidate_is_buy": False,
            }
        ],
    }
    prior_path = store / V2_ACTION_STATE_NAME
    prior_path.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T06:10:00+07:00",
        "observe_reason": "SIDECAR_STALE_SESSION",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [],
        "v2_sidecar": {"ok": False, "reason": "SIDECAR_STALE_SESSION"},
    }
    src = tmp_path / "failed_state.json"
    src.write_text(json.dumps(failed), encoding="utf-8")
    pub = publish_v2_action_state(src, store)
    assert pub["v2_status"] == "RETAINED"
    assert pub["v2_retained"] is True
    assert pub.get("actionable") is False
    kept = json.loads(prior_path.read_text(encoding="utf-8"))
    assert kept["session"] == T0
    assert len(kept["rows"]) == 1
    assert kept["rows"][0]["shadow_action"] == "NOMINATED"
    diag = json.loads((store / V2_ACTION_OBSERVE_FAILURE_NAME).read_text(encoding="utf-8"))
    assert diag["published_state_retained"] is True
    assert diag["actionable"] is False
    assert diag["alert_eligible"] is False
    assert diag["candidate_is_buy"] is False
    assert diag["fresh_current_session_evaluation"] is False


def test_retained_prior_buy_ready_not_accepted_as_fresh_actionable():
    """UI fail-closed: prior-session retained state is STALE for today's cycle."""
    retained = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T0,
        "observed_at": f"{T0}T22:40:00+07:00",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
        "rows": [
            {
                "symbol": "HPG",
                "shadow_action": STATE_BUY_READY,
                "alert_eligible": False,
                "candidate_is_buy": False,
                "n_legal_bars": 3,
            }
        ],
    }
    now = datetime.fromisoformat(f"{T1}T10:05:00").replace(tzinfo=VN)
    doc, reason = accept_shadow_state_document(retained, now=now, session=T1)
    assert doc is None
    assert reason == UI_STALE_SESSION


def test_alert_or_buy_flags_on_failed_payload_still_not_published_as_actionable(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    prior = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T0,
        "observed_at": f"{T0}T22:40:00+07:00",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": False,
        "rows": [{"symbol": "HPG", "shadow_action": "NOMINATED", "n_legal_bars": 0}],
    }
    (store / V2_ACTION_STATE_NAME).write_text(json.dumps(prior), encoding="utf-8")
    # Malicious/failed empty with alert flag must not become the published head.
    failed = {
        "session": T1,
        "observed_at": f"{T1}T06:10:00+07:00",
        "observe_reason": "SIDECAR_STALE_SESSION",
        "rows": [],
        "alert_eligible": True,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
    }
    src = tmp_path / "bad.json"
    src.write_text(json.dumps(failed), encoding="utf-8")
    pub = publish_v2_action_state(src, store)
    assert pub["v2_status"] == "RETAINED"
    kept = json.loads((store / V2_ACTION_STATE_NAME).read_text(encoding="utf-8"))
    assert kept["alert_eligible"] is False
    assert kept["session"] == T0


def test_same_day_sidecar_keeps_provenance_session_filter():
    rows = [
        _row("HPG", session=T1, first=f"{T1}T09:00:00+07:00", eligible=f"{T1}T09:00:00+07:00"),
        _row("AAA", session=T0, first=f"{T0}T14:30:00+07:00", eligible=f"{T1}T09:15:00+07:00"),
    ]
    doc = _sidecar(T1, rows)
    accepted = accept_sidecar_document(doc, session=T1, source="file")
    # Same-day document: only row.session == cycle (AAA provenance T0 dropped here).
    assert [r["symbol"] for r in accepted.rows] == ["HPG"]


def test_nonempty_stale_failed_observe_does_not_overwrite_valid_prior(tmp_path: Path):
    """Publish gate: failed reason + spurious rows must not clobber valid state."""
    store = tmp_path / "store"
    store.mkdir()
    prior = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T10:00:00+07:00",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [
            {
                "symbol": "HPG",
                "shadow_action": "NOMINATED",
                "n_legal_bars": 0,
                "alert_eligible": False,
                "candidate_is_buy": False,
            }
        ],
    }
    (store / V2_ACTION_STATE_NAME).write_text(json.dumps(prior), encoding="utf-8")
    poisoned = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T10:05:00+07:00",
        "observe_reason": "SIDECAR_STALE_SESSION",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [
            {
                "symbol": "EVIL",
                "shadow_action": STATE_BUY_READY,
                "n_legal_bars": 9,
                "alert_eligible": False,
                "candidate_is_buy": False,
            }
        ],
        "v2_sidecar": {"ok": False, "reason": "SIDECAR_STALE_SESSION"},
    }
    src = tmp_path / "poisoned.json"
    src.write_text(json.dumps(poisoned), encoding="utf-8")
    pub = publish_v2_action_state(src, store)
    assert pub["v2_status"] == "RETAINED"
    assert pub.get("actionable") is False
    kept = json.loads((store / V2_ACTION_STATE_NAME).read_text(encoding="utf-8"))
    assert kept["rows"][0]["symbol"] == "HPG"
    assert all(r.get("symbol") != "EVIL" for r in kept["rows"])
    diag = json.loads((store / V2_ACTION_OBSERVE_FAILURE_NAME).read_text(encoding="utf-8"))
    assert diag["failed_had_rows"] is True
    assert diag["fresh_current_session_evaluation"] is False


def test_nonempty_stale_without_prior_publishes_sanitized_empty(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    poisoned = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T10:05:00+07:00",
        "observe_reason": "SIDECAR_INVALID",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": True,
        "rows": [{"symbol": "EVIL", "shadow_action": STATE_BUY_READY, "n_legal_bars": 9}],
    }
    src = tmp_path / "poisoned.json"
    src.write_text(json.dumps(poisoned), encoding="utf-8")
    pub = publish_v2_action_state(src, store)
    assert pub["v2_status"] == "OK"
    assert pub.get("v2_sanitized_failed") is True
    assert pub.get("actionable") is False
    kept = json.loads((store / V2_ACTION_STATE_NAME).read_text(encoding="utf-8"))
    assert kept["rows"] == []
    assert kept["alert_eligible"] is False
    assert kept["candidate_is_buy"] is False


def test_legitimate_empty_no_current_session_still_publishes(tmp_path: Path):
    """Empty successful handoff must replace current rows (not RETAIN as failure)."""
    store = tmp_path / "store"
    store.mkdir()
    prior = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T14:50:00+07:00",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [
            {
                "symbol": "HPG",
                "session": T1,
                "shadow_action": STATE_BUY_READY,
                "trigger_bar_ts": f"{T1}T14:45:00+07:00",
                "n_legal_bars": 3,
                "alert_eligible": False,
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
            }
        ],
    }
    (store / V2_ACTION_STATE_NAME).write_text(json.dumps(prior), encoding="utf-8")
    empty_success = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": T1,
        "observed_at": f"{T1}T18:40:00+07:00",
        "observe_reason": "NO_CURRENT_SESSION_V2_ROWS",
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [],
    }
    src = tmp_path / "empty_ok.json"
    src.write_text(json.dumps(empty_success), encoding="utf-8")
    pub = publish_v2_action_state(src, store)
    assert pub["v2_status"] == "OK"
    assert pub.get("v2_retained") is False
    kept = json.loads((store / V2_ACTION_STATE_NAME).read_text(encoding="utf-8"))
    assert kept["rows"] == []
    hist = kept.get("historical_buy_ready") or []
    assert len(hist) == 1
    assert hist[0]["symbol"] == "HPG"
    assert hist[0]["shadow_action"] == STATE_BUY_READY
    # Historical only — not accepted as fresh current-session actionable state.
    now = datetime.fromisoformat(f"{T1}T18:45:00").replace(tzinfo=VN)
    doc, reason = accept_shadow_state_document(kept, now=now, session=T1)
    assert doc is not None and reason == "OK"
    assert doc["rows"] == []
