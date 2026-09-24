"""Published Action state, nomination session, and EMA9 unit boundary."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_v2_action.artifact import state_document
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    MODE,
    PXV_IMPLIES_BUY,
)
from modules.live_candidate_v2_action.state import (
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
    evaluation_trading_session,
)
from modules.live_candidate_v2_action.ui import (
    EMPTY_MESSAGE,
    STALE_MESSAGE,
    choose_local_action_state,
    render_v2_shadow_action_panel,
)
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class _St:
    def __init__(self):
        self.captions: list[str] = []
        self.tables: list = []
        self.markdowns: list[str] = []

    def markdown(self, msg, **_k):
        self.markdowns.append(str(msg))

    def caption(self, msg, **_k):
        self.captions.append(str(msg))

    def dataframe(self, data, **_k):
        self.tables.append(data)


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=VN)


def _bar(day: str, hm: str) -> BarEvidence:
    ts = _ts(f"{day} {hm}:00")
    return BarEvidence(
        bar_ts=ts,
        asof=ts,
        completed=True,
        close=27120.0,
        close_canonical=27120,
        reference_kind="EMA9",
        reference_value=27.1,
        reference_canonical=27100,
        close_vs_ref=20.0,
        close_vs_ref_pct=20.0 / 27100.0 * 100.0,
        reference_state="EMA9",
        data_state="QUALIFIED",
        volume_expansion_state="NORMAL",
        price_volume_state="FLAT",
    )


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _doc(session: str, observed_at: str, rows: list) -> dict:
    return {
        "schema": "live_candidate_v2_action_state.v1",
        "mode": MODE,
        "session": session,
        "observed_at": observed_at,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": rows,
    }


def test_published_rows_win_over_empty_local_copy(tmp_path):
    published = tmp_path / "store" / "v2_action_state.json"
    research = tmp_path / "research" / "v2_action_state.json"
    row = {"symbol": "BFC", "session": "2026-09-23", "shadow_action": "WAIT", "n_legal_bars": 3}
    _write(published, _doc("2026-09-24", "2026-09-24T11:30:49+07:00", [row]))
    _write(research, _doc("2026-09-24", "2026-09-24T11:30:49+07:00", []))
    chosen = choose_local_action_state(published, research)
    assert chosen is not None
    assert chosen["rows"][0]["symbol"] == "BFC"
    st = _St()
    render_v2_shadow_action_panel(
        chosen,
        st_module=st,
        now=_ts("2026-09-24 11:31:00"),
    )
    assert any("rows=1" in cap for cap in st.captions)
    assert EMPTY_MESSAGE not in st.captions
    assert st.tables and st.tables[0][0]["Symbol"] == "BFC"


def test_stale_published_state_stays_rejected(tmp_path):
    published = tmp_path / "store" / "v2_action_state.json"
    research = tmp_path / "research" / "v2_action_state.json"
    _write(
        published,
        _doc("2026-09-23", "2026-09-23T14:50:00+07:00", [{"symbol": "OLD", "shadow_action": "WAIT"}]),
    )
    _write(research, _doc("2026-09-24", "2026-09-24T11:30:49+07:00", []))
    chosen = choose_local_action_state(published, research)
    assert chosen["rows"] == []
    st = _St()
    render_v2_shadow_action_panel(
        None,
        st_module=st,
        artifact_dir=tmp_path / "research",
        now=_ts("2026-09-24 11:31:00"),
    )
    assert any("rows=0" in cap for cap in st.captions)
    stale_dir = tmp_path / "stale"
    _write(
        stale_dir / "v2_action_state.json",
        _doc("2026-09-23", "2026-09-23T14:50:00+07:00", [{"symbol": "OLD", "shadow_action": "WAIT"}]),
    )
    stale = _St()
    render_v2_shadow_action_panel(
        None,
        st_module=stale,
        artifact_dir=stale_dir,
        now=_ts("2026-09-24 11:31:00"),
    )
    assert STALE_MESSAGE in stale.captions
    assert all("rows=1" not in cap for cap in stale.captions)


def test_rollover_keeps_nomination_session_and_records_observation_session():
    nom = FrozenNomination(
        symbol="BFC",
        session="2026-09-23",
        setup="PULL VỪA",
        group="PULL VỪA",
        candidate_first_seen_ts="2026-09-23T15:22:00+07:00",
        eligible_from="2026-09-24T09:15:00+07:00",
        observation_reference="EMA9",
        ema9_at_first_seen=27.1,
        market_permission="OK",
    )
    assert evaluation_trading_session(nom) == "2026-09-24"
    result = evaluate_shadow_action(
        nom,
        [_bar("2026-09-23", "14:40"), _bar("2026-09-24", "09:20")],
        now=_ts("2026-09-24 09:25:00"),
    )
    assert result.session == "2026-09-23"
    assert result.n_legal_bars == 1
    assert result.candidate_is_buy is False
    assert result.pxv_implies_buy is False
    assert result.alert_eligible is False
    doc = state_document(
        session="2026-09-24",
        observed_at=_ts("2026-09-24 09:25:00"),
        results=[result],
    )
    assert doc["session"] == "2026-09-24"
    assert doc["mode"] == MODE == "SHADOW_ONLY"
    assert doc["candidate_is_buy"] is CANDIDATE_IS_BUY is False
    assert doc["pxv_implies_buy"] is PXV_IMPLIES_BUY is False
    assert doc["alert_eligible"] is ALERT_ELIGIBLE is False
    row = doc["rows"][0]
    assert row["session"] == "2026-09-23"
    assert row["observation_session"] == "2026-09-24"


def test_fractional_vnd_ema9_is_not_rescaled_and_breakout_stays_put():
    ema = observe_close_vs_ref(
        {"observation_reference": "EMA9", "ema9_at_first_seen": 143958.2},
        145900,
    )
    assert ema["close_canonical"] == 145900
    assert ema["reference_canonical"] == 143958
    assert ema["close_vs_ref"] == 1942.0
    assert abs(ema["close_vs_ref"] - 1941.8) < 1
    assert abs(ema["close_vs_ref_pct"] - (1941.8 / 143958.2 * 100.0)) < 0.01
    assert ema["reference_state"] == "EMA9"
    brk = observe_close_vs_ref(
        {"observation_reference": "BREAKOUT_REF", "breakout_ref_at_first_seen": 13500},
        14150,
    )
    assert brk["close_canonical"] == 14150
    assert brk["reference_canonical"] == 13500
    assert brk["close_vs_ref"] == 650.0
    assert abs(brk["close_vs_ref_pct"] - (650.0 / 13500.0 * 100.0)) < 1e-9
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
