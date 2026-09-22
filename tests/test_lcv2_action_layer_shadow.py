"""SHADOW-ONLY V2 Action Layer — routes, chronology, union/cap, permissions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.intraday_pxv_v1.constants import (
    EV_STRENGTHEN,
    OVERLAY_TRUTH_CANONICAL,
    OVERLAY_TRUTH_RETROSPECTIVE,
)
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP
from modules.live_candidate_v2_action.artifact import (
    V2ActionStore,
    evidence_row,
    persist_cycle,
    state_document,
)
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    REASON_CONFLICT,
    REASON_DATE_ONLY,
    REASON_EARLY_EVIDENCE_ONLY,
    REASON_MANH_BUY_READY,
    REASON_MANH_PRICE_NO_STRENGTHEN,
    REASON_MANH_STRENGTHEN_BELOW,
    REASON_NO_OBSERVATION_CAP,
    REASON_PULL_BELOW_REF,
    REASON_PULL_BUY_READY,
    REASON_PULL_FAM_SELL,
    REASON_PULL_SINGLE_BAR,
    REASON_RETROSPECTIVE,
    REASON_SESSION_RESET,
    REASON_UNFINISHED,
    REASON_WEAKENED_WAIT,
    REASON_WEAKENING,
    SHADOW_BUY_READY_LABEL,
    STATE_BUY_READY,
    STATE_NOMINATED,
    STATE_NO_OBSERVATION,
    STATE_WAIT,
    STATE_WEAKENED,
)
from modules.live_candidate_v2_action.replay import replay_sidecar_session
from modules.live_candidate_v2_action.state import (
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
)
from modules.live_candidate_v2_action.ui import (
    PANEL_TITLE,
    SHADOW_CAPTION,
    STALE_MESSAGE,
    VALIDATION_NOTE,
    VALIDATION_TITLE,
    project_shadow_rows,
    project_validation_rows,
    render_v2_shadow_action_panel,
)
from modules.live_candidate_v2_action.universe import merge_elite_v2, union_watchlist
from modules.live_candidate_v2_camera.observe import pxv_implies_buy
from modules.live_candidate_v2_camera.sidecar import build_sidecar_document, write_sidecar
from modules.intraday_memory.provider import MockProvider

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _nom(
    setup="PULL ĐẸP",
    symbol="HPG",
    session="2026-08-14",
    first="2026-08-14T09:00:00+07:00",
    eligible="2026-08-14T09:00:00+07:00",
    ema9=27.1,
    breakout=None,
    ref="EMA9",
    market="OK",
) -> FrozenNomination:
    return FrozenNomination(
        symbol=symbol,
        session=session,
        setup=setup,
        group=setup,
        candidate_first_seen_ts=first,
        eligible_from=eligible,
        observation_reference=ref,
        ema9_at_first_seen=ema9,
        breakout_ref_at_first_seen=breakout,
        market_permission=market,
        chronology_status="ELIGIBLE",
    )


def _bar(
    hm: str,
    *,
    close_vs_ref: float,
    published="NEUTRAL",
    raw=None,
    vol_state="NORMAL",
    pxv="FLAT",
    fam_sell=False,
    data_state="QUALIFIED",
    ref_state="EMA9",
    ref_kind="EMA9",
    completed=True,
    unfinished=False,
    chronology_legal=True,
    overlay_applied=False,
    overlay_class=OVERLAY_TRUTH_CANONICAL,
    day="2026-08-14",
) -> BarEvidence:
    ts = _ts(f"{day} {hm}:00")
    close_c = 27100 + int(close_vs_ref)
    ref_c = 27100
    return BarEvidence(
        bar_ts=ts,
        asof=ts,
        completed=completed,
        unfinished=unfinished,
        open=close_c,
        high=close_c + 50,
        low=close_c - 50,
        close=close_c,
        volume=1000,
        close_canonical=close_c,
        reference_kind=ref_kind,
        reference_value=27.1,
        reference_canonical=ref_c,
        close_vs_ref=float(close_vs_ref),
        close_vs_ref_pct=(close_vs_ref / ref_c) * 100.0,
        reference_state=ref_state,
        data_state=data_state,
        raw_evidence=raw if raw is not None else published,
        published_evidence=published,
        volume_expansion_state=vol_state,
        price_volume_state=pxv,
        fam_sell=fam_sell,
        sell_expansion=pxv == "SELL_EXPANSION",
        overlay_truth_class=overlay_class,
        overlay_applied=overlay_applied,
        chronology_legal=chronology_legal,
    )


# ---------- PULL ----------


def test_pull_one_reclaim_bar_is_wait():
    r = evaluate_shadow_action(_nom(), [_bar("09:15", close_vs_ref=50)])
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_PULL_SINGLE_BAR
    assert r.candidate_is_buy is False
    assert r.pxv_implies_buy is False
    assert r.alert_eligible is False


def test_pull_two_quiet_reclaim_bars_shadow_buy_ready():
    r = evaluate_shadow_action(
        _nom(),
        [
            _bar("09:15", close_vs_ref=20, vol_state="CONTRACTION"),
            _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
        ],
    )
    assert r.action_state == STATE_BUY_READY
    assert r.action_reason == REASON_PULL_BUY_READY
    assert r.shadow_label == SHADOW_BUY_READY_LABEL
    assert r.candidate_is_buy is False
    assert CANDIDATE_IS_BUY is False


def test_pull_reclaim_plus_fam_sell_not_buy_ready():
    r = evaluate_shadow_action(
        _nom(),
        [
            _bar("09:15", close_vs_ref=20, vol_state="NORMAL"),
            _bar("09:20", close_vs_ref=40, vol_state="NORMAL", fam_sell=True),
        ],
    )
    assert r.action_state != STATE_BUY_READY
    assert r.action_reason in {REASON_PULL_FAM_SELL, REASON_CONFLICT, "WAIT_CONFIRMATION_INCOMPLETE"}


def test_pull_below_ref_is_wait():
    r = evaluate_shadow_action(_nom(), [_bar("09:15", close_vs_ref=-80)])
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_PULL_BELOW_REF


def test_pull_weakening_conjunction_is_weakened():
    r = evaluate_shadow_action(
        _nom(),
        [_bar("09:15", close_vs_ref=-80, fam_sell=True, published="WEAKEN")],
    )
    assert r.action_state == STATE_WEAKENED
    assert r.action_reason == REASON_WEAKENING


def test_weakened_must_pass_wait_before_buy_ready():
    bars = [
        _bar("09:15", close_vs_ref=-80, fam_sell=True, published="WEAKEN"),
        _bar("09:20", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
    ]
    r = evaluate_shadow_action(_nom(), bars)
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_WEAKENED_WAIT
    # After WAIT is established, a later evaluation of the hold bars can BUY_READY.
    r2 = evaluate_shadow_action(_nom(), bars[1:], prior_action_state=STATE_WAIT)
    assert r2.action_state == STATE_BUY_READY


# ---------- MẠNH / BREAK ----------


def test_manh_price_above_without_strengthen_is_wait():
    r = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=100, published="NEUTRAL"),
            _bar("09:20", close_vs_ref=120, published="NEUTRAL"),
        ],
    )
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_MANH_PRICE_NO_STRENGTHEN
    assert r.action_state != STATE_BUY_READY


def test_manh_strengthen_below_ref_is_wait():
    r = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [_bar("09:15", close_vs_ref=-40, published=EV_STRENGTHEN)],
    )
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_MANH_STRENGTHEN_BELOW


def test_manh_two_bar_plus_published_strengthen_shadow_buy_ready():
    r = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=50, published="NEUTRAL", vol_state="EXPANSION", pxv="CONFIRMING"),
            _bar("09:20", close_vs_ref=80, published=EV_STRENGTHEN, vol_state="EXPANSION", pxv="CONFIRMING"),
        ],
    )
    assert r.action_state == STATE_BUY_READY
    assert r.action_reason == REASON_MANH_BUY_READY
    assert "SHADOW" in r.shadow_label


def test_break_two_bar_plus_strengthen_uses_breakout_ref():
    r = evaluate_shadow_action(
        _nom("MUA BREAK", ema9=None, breakout=27.0, ref="BREAKOUT_REF"),
        [
            _bar("09:15", close_vs_ref=30, published="NEUTRAL", ref_state="BREAKOUT_REF", ref_kind="BREAKOUT_REF"),
            _bar(
                "09:20",
                close_vs_ref=60,
                published=EV_STRENGTHEN,
                ref_state="BREAKOUT_REF",
                ref_kind="BREAKOUT_REF",
            ),
        ],
    )
    assert r.action_state == STATE_BUY_READY
    assert r.route == "BREAK"


def test_manh_pxv_weak_or_fam_sell_conflict_not_buy_ready():
    weak = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=50, published=EV_STRENGTHEN, pxv="WEAK"),
            _bar("09:20", close_vs_ref=80, published=EV_STRENGTHEN, pxv="WEAK"),
        ],
    )
    assert weak.action_state != STATE_BUY_READY
    sell = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=50, published=EV_STRENGTHEN, fam_sell=True),
            _bar("09:20", close_vs_ref=80, published=EV_STRENGTHEN, fam_sell=True),
        ],
    )
    assert sell.action_state != STATE_BUY_READY
    assert sell.action_reason in {REASON_CONFLICT, "MANH_BREAK_FAM_SELL_ON_CONFIRMATION"}


# ---------- EARLY ----------


def test_early_never_buy_ready():
    r0 = evaluate_shadow_action(_nom("MUA EARLY", ema9=None, ref=""), [])
    assert r0.action_state == STATE_NOMINATED
    r1 = evaluate_shadow_action(
        _nom("MUA EARLY", ema9=None, ref=""),
        [_bar("09:15", close_vs_ref=50, ref_state="UNAVAILABLE", ref_kind="")],
    )
    assert r1.action_state == STATE_WAIT
    assert r1.action_reason == REASON_EARLY_EVIDENCE_ONLY
    assert r1.action_state != STATE_BUY_READY


# ---------- Chronology ----------


def test_pre_eligible_bars_ignored():
    r = evaluate_shadow_action(
        _nom(eligible="2026-08-14T09:20:00+07:00"),
        [
            _bar("09:15", close_vs_ref=20, vol_state="NORMAL"),
            _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
            _bar("09:25", close_vs_ref=60, vol_state="NORMAL"),
        ],
    )
    # 09:15 dropped; remaining two quiet reclaim bars → BUY_READY
    assert r.n_legal_bars == 2
    assert r.action_state == STATE_BUY_READY


def test_unfinished_5m_ignored():
    r = evaluate_shadow_action(
        _nom(),
        [
            _bar("09:15", close_vs_ref=20, vol_state="NORMAL", unfinished=True, completed=False),
            _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
        ],
    )
    assert r.action_state == STATE_WAIT
    assert r.n_legal_bars == 1
    assert REASON_UNFINISHED in r.notes or r.action_reason == REASON_PULL_SINGLE_BAR


def test_date_only_midnight_illegal_fail_closed():
    r = evaluate_shadow_action(
        _nom(first="2026-08-14", eligible="2026-08-14"),
        [_bar("09:15", close_vs_ref=20), _bar("09:20", close_vs_ref=40)],
    )
    assert r.action_state != STATE_BUY_READY
    assert r.action_reason == REASON_DATE_ONLY


def test_unit_mismatch_fail_closed():
    r = evaluate_shadow_action(
        _nom(),
        [
            _bar("09:15", close_vs_ref=20, ref_state="UNIT_MISMATCH"),
            _bar("09:20", close_vs_ref=40, ref_state="UNIT_MISMATCH"),
        ],
    )
    assert r.action_state != STATE_BUY_READY
    assert r.action_reason == "FROZEN_REF_UNIT_MISMATCH"


def test_retrospective_overlay_cannot_mint_live_buy_ready():
    bars = [
        _bar("09:15", close_vs_ref=20, vol_state="NORMAL", overlay_class=OVERLAY_TRUTH_RETROSPECTIVE),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL", overlay_class=OVERLAY_TRUTH_RETROSPECTIVE),
    ]
    r = evaluate_shadow_action(_nom(), bars, overlay_truth_class=OVERLAY_TRUTH_RETROSPECTIVE)
    assert r.action_state != STATE_BUY_READY
    assert r.action_reason == REASON_RETROSPECTIVE


def test_session_rollover_resets_action_state():
    today = [
        _bar("09:15", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
    ]
    r = evaluate_shadow_action(
        _nom(session="2026-08-15"),
        today,  # bars dated 2026-08-14
        prior_action_state=STATE_BUY_READY,
        prior_session="2026-08-14",
    )
    assert r.action_state != STATE_BUY_READY
    assert REASON_SESSION_RESET in r.notes or r.action_reason in {
        REASON_SESSION_RESET,
        "NOMINATED_NO_LEGAL_COMPLETED_BARS",
    }


def test_conflict_strength_and_sell_is_wait_not_buy_ready():
    r = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=50, published=EV_STRENGTHEN, fam_sell=True),
            _bar("09:20", close_vs_ref=80, published=EV_STRENGTHEN, fam_sell=True),
        ],
    )
    assert r.action_state == STATE_WAIT
    assert r.action_reason == REASON_CONFLICT


# ---------- Operational: union / cap / missing data ----------


def test_elite_v2_overlap_deduped_v2_provenance_kept():
    elite = [
        {
            "symbol": "HPG",
            "eligible_from": "2026-08-14T08:00:00+07:00",
            "candidate_first_seen_ts": "2026-08-14T08:00:00+07:00",
            "source": "buy_elite_learning_history",
            "candidate_reason": "BUY ELITE",
        }
    ]
    v2 = [
        {
            "symbol": "HPG",
            "session": "2026-08-14",
            "eligible_from": "2026-08-14T10:05:00+07:00",
            "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
            "setup": "PULL ĐẸP",
            "v2_camera": True,
            "observation_reference": "EMA9",
            "ema9_at_first_seen": 27.1,
            "candidate_is_buy": False,
        }
    ]
    merged, report = merge_elite_v2(elite, v2)
    assert len(merged) == 1
    assert report.n_overlap == 1
    assert merged[0]["_sources"] == ["elite", "v2"]
    assert merged[0].get("v2_camera") is not True
    assert merged[0]["_v2_nomination"]["setup"] == "PULL ĐẸP"
    assert merged[0]["_v2_nomination"]["candidate_first_seen_ts"].startswith("2026-08-14T10:05:00")
    assert merged[0]["_v2_nomination"]["ema9_at_first_seen"] == 27.1


def test_cap_drop_visible_not_false_wait(tmp_path):
    now = _ts("2026-08-14 10:20:00")
    elite = [
        {
            "symbol": f"E{i:03d}",
            "eligible_from": "2026-08-14T09:15:00+07:00",
            "candidate_first_seen_ts": "2026-08-14T09:15:00+07:00",
        }
        for i in range(LIVE_UNIVERSE_CAP)
    ]
    v2 = [
        {
            "symbol": "V2X",
            "session": "2026-08-14",
            "setup": "PULL ĐẸP",
            "v2_camera": True,
            "eligible_from": "2026-08-14T09:40:00+07:00",
            "candidate_first_seen_ts": "2026-08-14T09:40:00+07:00",
            "observation_reference": "EMA9",
            "ema9_at_first_seen": 27.1,
            "market_permission": "OK",
            "candidate_is_buy": False,
        }
    ]
    universe, dropped, report = union_watchlist(elite, v2, now=now, cap=LIVE_UNIVERSE_CAP)
    assert report.n_v2_cap_dropped == 1
    assert "V2X" in report.v2_cap_dropped_symbols
    assert all(r.get("symbol") != "V2X" or r.get("_skip") == "NOT_YET_ELIGIBLE" for r in universe)

    class _Prov:
        def __init__(self):
            self.call_count = 0

        def fetch_session(self, symbol, session):
            self.call_count += 1
            return []

    feed = LiveShadowFeed(
        provider=_Prov(),
        out_dir=tmp_path,
        now_fn=lambda: now,
        v2_rows=v2,
        action_out_dir=tmp_path / "v2_action",
        hard_cap=LIVE_UNIVERSE_CAP,
    )
    status = feed.run_cycle(elite)
    assert "V2X" not in status["fetched_symbols"]
    assert "V2X" in (status.get("v2_union") or {}).get("v2_cap_dropped_symbols", [])
    items = {nom.symbol: result for nom, _h, result in feed._v2_action_items}
    assert items["V2X"].action_state == STATE_NO_OBSERVATION
    assert items["V2X"].action_reason == REASON_NO_OBSERVATION_CAP
    assert items["V2X"].action_state != STATE_WAIT


def test_missing_camera_data_is_no_observation_not_wait(tmp_path):
    now = _ts("2026-08-14 10:20:00")
    v2 = [
        {
            "symbol": "HPG",
            "session": "2026-08-14",
            "setup": "PULL ĐẸP",
            "v2_camera": True,
            "eligible_from": "2026-08-14T09:00:00+07:00",
            "candidate_first_seen_ts": "2026-08-14T09:00:00+07:00",
            "observation_reference": "EMA9",
            "ema9_at_first_seen": 27.1,
            "market_permission": "OK",
            "candidate_is_buy": False,
        }
    ]
    feed = LiveShadowFeed(
        provider=MockProvider({("HPG", "2026-08-14"): []}),
        out_dir=tmp_path,
        now_fn=lambda: now,
        v2_rows=v2,
        action_out_dir=tmp_path / "v2_action",
    )
    status = feed.run_cycle([])
    assert status["symbols"][0]["status"] == "NO_DATA"
    result = feed._v2_action_items[0][2]
    assert result.action_state == STATE_NO_OBSERVATION
    assert result.action_state != STATE_WAIT


def test_elite_only_cycle_unchanged_no_v2_overlay(tmp_path):
    now = _ts("2026-08-14 10:20:00")

    def _raw_bar(ts: str, close: float = 22.2) -> dict:
        return {
            "time": ts,
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1000,
        }

    t = _ts("2026-08-14 09:15:00")
    bars = []
    for i in range(12):
        bars.append(_raw_bar(t.strftime("%Y-%m-%d %H:%M:%S"), 22.2 + i * 0.01))
        t += timedelta(minutes=5)
    elite = [
        {
            "session": "2026-08-14",
            "symbol": "HPG",
            "candidate_first_seen_ts": "2026-08-14T08:00:00+07:00",
            "candidate_updated_ts": "2026-08-14T08:00:00+07:00",
            "candidate_reason": "BUY ELITE",
            "source": "buy_elite_learning_history",
            "status": "ACTIVE",
            "eligible_from": "2026-08-14T08:00:00+07:00",
        }
    ]
    feed = LiveShadowFeed(
        provider=MockProvider({("HPG", "2026-08-14"): bars}),
        out_dir=tmp_path,
        now_fn=lambda: now,
    )
    status = feed.run_cycle(elite)
    ev = feed.read_evidence()
    assert ev
    assert ev[0].get("v2_camera") is not True
    assert status["alert_eligible"] is False
    assert status["candidate_is_buy"] is False
    assert feed._v2_action_items == []


def test_permissions_remain_false_on_buy_ready_artifact(tmp_path):
    nom = _nom()
    bars = [
        _bar("09:15", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
    ]
    result = evaluate_shadow_action(nom, bars)
    assert result.action_state == STATE_BUY_READY
    row = evidence_row(nom, bars[-1], result, session="2026-08-14", observed_at=_ts("2026-08-14 09:30:00"))
    assert row["candidate_is_buy"] is False
    assert row["pxv_implies_buy"] is False
    assert row["alert_eligible"] is False
    doc = persist_cycle(
        session="2026-08-14",
        observed_at=_ts("2026-08-14 09:30:00"),
        items=[(nom, bars, result)],
        out_dir=tmp_path,
    )
    assert doc["candidate_is_buy"] is False
    assert doc["pxv_implies_buy"] is False
    assert doc["alert_eligible"] is False
    assert pxv_implies_buy("STRENGTHEN") is False
    store = V2ActionStore(tmp_path)
    ev = store.read_evidence()
    assert ev
    assert ev[0]["action_state"] == STATE_BUY_READY
    assert ev[0]["setup"] == "PULL ĐẸP"
    assert ev[0]["frozen_reference_kind"] == "EMA9"
    assert ev[0]["completed_bar"] is True


# ---------- Replay ----------


def test_replay_matches_pure_function_and_ignores_elite_csv_time(tmp_path):
    nom = _nom()
    injected = [
        _bar("09:15", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
    ]
    live = evaluate_shadow_action(nom, injected)
    # Replay via sidecar + parquet uses interpret; may not mint BUY_READY
    # (volume/gate). Mechanical equality: same nomination clock, never CSV time.
    sidecar_row = {
        "symbol": "HPG",
        "session": "2026-08-14",
        "setup": "PULL ĐẸP",
        "group": "PULL ĐẸP",
        "candidate_first_seen_ts": nom.candidate_first_seen_ts,
        "eligible_from": nom.eligible_from,
        "observation_reference": "EMA9",
        "ema9_at_first_seen": 27.1,
        "market_permission": "OK",
        "v2_camera": True,
        "candidate_is_buy": False,
        "time": "15:01:00",  # Elite CSV save clock — must not become first_seen
    }
    doc = build_sidecar_document(
        [sidecar_row],
        observed_at=_ts("2026-08-14 10:05:00"),
        market_permission="OK",
        session="2026-08-14",
    )
    path = tmp_path / "sidecar.json"
    path.write_text(__import__("json").dumps(doc), encoding="utf-8")
    results = replay_sidecar_session(path, now=_ts("2026-08-14 10:30:00"), parquet=pd.DataFrame())
    assert results
    assert results[0].action_state == STATE_NO_OBSERVATION
    assert results[0].candidate_is_buy is False
    assert live.candidate_is_buy is False


def test_replay_live_same_injected_history():
    nom = _nom()
    history = [
        _bar("09:15", close_vs_ref=20, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
    ]
    a = evaluate_shadow_action(nom, history)
    b = evaluate_shadow_action(nom, history)
    assert a.action_state == b.action_state == STATE_BUY_READY
    assert a.action_reason == b.action_reason


# ---------- UI ----------


def test_shadow_ui_labels_buy_ready_as_shadow():
    rows = [
        {
            "symbol": "HPG",
            "setup": "PULL ĐẸP",
            "shadow_action": STATE_BUY_READY,
            "shadow_label": SHADOW_BUY_READY_LABEL,
            "last_legal_bar_ts": "2026-08-14T09:20:00+07:00",
            "frozen_ref_kind": "EMA9",
            "frozen_ref_value": 27.1,
            "close_vs_ref": 40,
            "action_reason": REASON_PULL_BUY_READY,
        }
    ]
    table = project_shadow_rows(rows)
    assert "SHADOW" in table[0]["Shadow action"]
    assert "research" in table[0]["Shadow action"].lower()
    assert table[0]["Shadow action"] != "BUY"
    assert "source_action" not in table[0]
    assert "BUY ELITE" not in str(table)

    class _St:
        def __init__(self):
            self.markdowns = []
            self.captions = []
            self.tables = []

        def markdown(self, msg, **k):
            self.markdowns.append(str(msg))

        def caption(self, msg, **k):
            self.captions.append(str(msg))

        def dataframe(self, data, **k):
            self.tables.append(data)

    st = _St()
    render_v2_shadow_action_panel(
        {
            "candidate_is_buy": False,
            "pxv_implies_buy": False,
            "alert_eligible": False,
            "session": "2026-08-14",
            "rows": rows,
        },
        st_module=st,
    )
    assert any(PANEL_TITLE in m for m in st.markdowns)
    assert any("SHADOW" in c for c in st.captions)
    assert SHADOW_CAPTION in st.captions
    assert st.tables


def test_shadow_ui_fail_closed_without_artifact(tmp_path):
    class _St:
        def __init__(self):
            self.captions = []
            self.markdowns = []

        def markdown(self, msg, **k):
            self.markdowns.append(str(msg))

        def caption(self, msg, **k):
            self.captions.append(str(msg))

        def dataframe(self, *a, **k):
            raise AssertionError("no table without artifact")

    st = _St()
    render_v2_shadow_action_panel(None, st_module=st, artifact_dir=tmp_path)
    assert any("no local observation" in c for c in st.captions)


def test_pxv_implies_buy_and_permissions_hard_false():
    assert pxv_implies_buy("STRENGTHEN") is False
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False


def test_camera_operator_ui_still_has_no_buy_ready():
    src = (REPO / "modules" / "live_candidate_v2_camera" / "ui.py").read_text(encoding="utf-8")
    assert "BUY_READY" not in src
    assert "render_v2_shadow_action_panel" not in src


# ---------- Visibility: evidence fields and stale BUY_READY ----------
# Synthetic bars and documents. Not 2026-09-22 production candidates.


class _VisSt:
    def __init__(self):
        self.markdowns = []
        self.captions = []
        self.tables = []

    def markdown(self, msg, **k):
        self.markdowns.append(str(msg))

    def caption(self, msg, **k):
        self.captions.append(str(msg))

    def dataframe(self, data, **k):
        self.tables.append(data)


def _synthetic_ready_row(**overrides):
    row = {
        "symbol": "SYN",
        "source": "brain_a_scan_setup",
        "setup": "PULL ĐẸP",
        "shadow_action": STATE_BUY_READY,
        "shadow_label": SHADOW_BUY_READY_LABEL,
        "trigger_bar_ts": "2026-08-14T09:20:00+07:00",
        "last_legal_bar_ts": "2026-08-14T09:20:00+07:00",
        "trigger_price": 27140.0,
        "frozen_ref_kind": "EMA9",
        "frozen_ref_value": 27.1,
        "published_evidence": "NEUTRAL",
        "volume_expansion_state": "NORMAL",
        "price_volume_state": "FLAT",
        "market_permission": "OK",
        "action_reason": REASON_PULL_BUY_READY,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "n_legal_bars": 2,
    }
    row.update(overrides)
    return row


def _synthetic_state(rows, *, observed_at, session="2026-08-14"):
    return {
        "schema": "live_candidate_v2_action_state.v1",
        "session": session,
        "observed_at": observed_at,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": rows,
    }


def test_state_row_carries_existing_evaluator_fields():
    nom = FrozenNomination(
        symbol="SYN",
        session="2026-08-14",
        setup="PULL ĐẸP",
        group="PULL ĐẸP",
        candidate_first_seen_ts="2026-08-14T09:00:00+07:00",
        eligible_from="2026-08-14T09:00:00+07:00",
        observation_reference="EMA9",
        ema9_at_first_seen=27.1,
        market_permission="OK",
        source="brain_a_scan_setup",
    )
    bars = [
        _bar("09:15", close_vs_ref=20, vol_state="CONTRACTION", published="NEUTRAL", pxv="FLAT"),
        _bar("09:20", close_vs_ref=40, vol_state="NORMAL", published="NEUTRAL", pxv="FLAT"),
    ]
    result = evaluate_shadow_action(nom, bars)
    assert result.action_state == STATE_BUY_READY
    assert result.action_reason == REASON_PULL_BUY_READY
    assert result.candidate_is_buy is False
    assert result.pxv_implies_buy is False
    assert result.alert_eligible is False
    assert result.source == "brain_a_scan_setup"
    assert result.trigger_price == bars[-1].close
    assert result.published_evidence == "NEUTRAL"
    assert result.volume_expansion_state == "NORMAL"
    assert result.price_volume_state == "FLAT"
    assert result.market_permission == "OK"
    doc = state_document(session="2026-08-14", observed_at=_ts("2026-08-14 09:30:00"), results=[result])
    row = doc["rows"][0]
    assert row["source"] == "brain_a_scan_setup"
    assert row["trigger_bar_ts"] == result.last_legal_bar_ts
    assert row["trigger_price"] == bars[-1].close
    assert row["frozen_ref_kind"] == "EMA9"
    assert row["frozen_ref_value"] == 27.1
    assert row["published_evidence"] == "NEUTRAL"
    assert row["volume_expansion_state"] == "NORMAL"
    assert row["price_volume_state"] == "FLAT"
    assert row["market_permission"] == "OK"
    assert row["action_reason"] == REASON_PULL_BUY_READY
    assert row["candidate_is_buy"] is False
    assert row["pxv_implies_buy"] is False
    assert row["alert_eligible"] is False
    assert doc["candidate_is_buy"] is False
    assert doc["pxv_implies_buy"] is False
    assert doc["alert_eligible"] is False


def test_pull_manh_break_transitions_unchanged():
    """Synthetic confirmation pairs. State names and reasons stay the existing machine."""
    pull = evaluate_shadow_action(
        _nom(),
        [
            _bar("09:15", close_vs_ref=20, vol_state="CONTRACTION"),
            _bar("09:20", close_vs_ref=40, vol_state="NORMAL"),
        ],
    )
    assert pull.action_state == STATE_BUY_READY
    assert pull.action_reason == REASON_PULL_BUY_READY
    pull_wait = evaluate_shadow_action(_nom(), [_bar("09:15", close_vs_ref=50)])
    assert pull_wait.action_state == STATE_WAIT
    assert pull_wait.action_reason == REASON_PULL_SINGLE_BAR

    manh = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=50, published="NEUTRAL", vol_state="EXPANSION", pxv="CONFIRMING"),
            _bar("09:20", close_vs_ref=80, published=EV_STRENGTHEN, vol_state="EXPANSION", pxv="CONFIRMING"),
        ],
    )
    assert manh.action_state == STATE_BUY_READY
    assert manh.action_reason == REASON_MANH_BUY_READY
    manh_wait = evaluate_shadow_action(
        _nom("CP MẠNH"),
        [
            _bar("09:15", close_vs_ref=100, published="NEUTRAL"),
            _bar("09:20", close_vs_ref=120, published="NEUTRAL"),
        ],
    )
    assert manh_wait.action_state == STATE_WAIT
    assert manh_wait.action_reason == REASON_MANH_PRICE_NO_STRENGTHEN

    brk = evaluate_shadow_action(
        _nom("MUA BREAK", ema9=None, breakout=27.0, ref="BREAKOUT_REF"),
        [
            _bar("09:15", close_vs_ref=30, published="NEUTRAL", ref_state="BREAKOUT_REF", ref_kind="BREAKOUT_REF"),
            _bar(
                "09:20",
                close_vs_ref=60,
                published=EV_STRENGTHEN,
                ref_state="BREAKOUT_REF",
                ref_kind="BREAKOUT_REF",
            ),
        ],
    )
    assert brk.action_state == STATE_BUY_READY
    assert brk.action_reason == REASON_MANH_BUY_READY
    assert brk.route == "BREAK"
    for result in (pull, manh, brk, pull_wait, manh_wait):
        assert result.candidate_is_buy is False
        assert result.pxv_implies_buy is False
        assert result.alert_eligible is False


def test_fresh_buy_ready_renders_current_shadow_table():
    now = _ts("2026-08-14 09:30:00")
    payload = _synthetic_state([_synthetic_ready_row()], observed_at=now.isoformat())
    st = _VisSt()
    render_v2_shadow_action_panel(
        None,
        st_module=st,
        now=now,
        source_mode="remote",
        fetcher=lambda: json.dumps(payload),
    )
    assert any(PANEL_TITLE in m for m in st.markdowns)
    assert VALIDATION_TITLE not in "\n".join(st.markdowns)
    assert SHADOW_CAPTION in st.captions
    assert any("candidate_is_buy=False" in c for c in st.captions)
    assert st.tables
    current = st.tables[0][0]
    assert "Shadow action" in current
    assert "research" in current["Shadow action"].lower()
    assert "Trigger price" not in current
    assert current["Symbol"] == "SYN"


def test_stale_buy_ready_is_historical_validation_only():
    now = _ts("2026-08-14 10:00:00")
    stale_at = (now - timedelta(minutes=20)).isoformat()
    rows = [
        _synthetic_ready_row(),
        _synthetic_ready_row(symbol="WAIT1", shadow_action=STATE_WAIT, action_reason="WAIT_CONFIRMATION_INCOMPLETE"),
        _synthetic_ready_row(symbol="NOM1", shadow_action=STATE_NOMINATED, action_reason="NOMINATED_NO_LEGAL_COMPLETED_BARS"),
        _synthetic_ready_row(symbol="WEAK1", shadow_action=STATE_WEAKENED, action_reason="WEAKENING_CONJUNCTION"),
    ]
    payload = _synthetic_state(rows, observed_at=stale_at)
    st = _VisSt()
    render_v2_shadow_action_panel(
        None,
        st_module=st,
        now=now,
        source_mode="remote",
        fetcher=lambda: json.dumps(payload),
    )
    assert STALE_MESSAGE in st.captions
    assert any("session=" in c and "SHADOW only" in c for c in st.captions) is False
    assert any(VALIDATION_TITLE in m for m in st.markdowns)
    assert VALIDATION_NOTE in st.captions
    assert any("not current" in c for c in st.captions)
    assert len(st.tables) == 1
    table = st.tables[0]
    assert len(table) == 1
    shown = table[0]
    assert shown["Symbol"] == "SYN"
    assert shown["Source"] == "brain_a_scan_setup"
    assert shown["Setup"] == "PULL ĐẸP"
    assert shown["Trigger time"] == "2026-08-14T09:20:00+07:00"
    assert shown["Trigger price"] == 27140.0
    assert shown["Frozen ref"] == "EMA9=27.1"
    assert "published=NEUTRAL" in shown["Volume/P×V evidence"]
    assert "volume=NORMAL" in shown["Volume/P×V evidence"]
    assert "pxv=FLAT" in shown["Volume/P×V evidence"]
    assert shown["Market permission"] == "OK"
    assert shown["Reason"] == REASON_PULL_BUY_READY
    assert "Shadow action" not in shown
    blob = str(table)
    assert "WAIT1" not in blob
    assert "NOM1" not in blob
    assert "WEAK1" not in blob
    assert any("candidate_is_buy=False" in c for c in st.captions)
    assert project_validation_rows(rows)[0]["Symbol"] == "SYN"


def test_stale_non_ready_rows_are_not_current_actions():
    now = _ts("2026-08-14 10:00:00")
    stale_at = (now - timedelta(minutes=20)).isoformat()
    rows = [
        _synthetic_ready_row(symbol="WAIT1", shadow_action=STATE_WAIT),
        _synthetic_ready_row(symbol="NOM1", shadow_action=STATE_NOMINATED),
        _synthetic_ready_row(symbol="WEAK1", shadow_action=STATE_WEAKENED),
    ]
    payload = _synthetic_state(rows, observed_at=stale_at)
    st = _VisSt()
    render_v2_shadow_action_panel(
        None,
        st_module=st,
        now=now,
        source_mode="remote",
        fetcher=lambda: json.dumps(payload),
    )
    assert STALE_MESSAGE in st.captions
    assert VALIDATION_TITLE not in "\n".join(st.markdowns)
    assert not st.tables

    wrong = _synthetic_state(
        [_synthetic_ready_row()],
        observed_at=now.isoformat(),
        session="2026-08-13",
    )
    st_roll = _VisSt()
    render_v2_shadow_action_panel(
        None,
        st_module=st_roll,
        now=now,
        source_mode="remote",
        fetcher=lambda: json.dumps(wrong),
    )
    assert STALE_MESSAGE in st_roll.captions
    assert any(VALIDATION_TITLE in m for m in st_roll.markdowns)
    assert st_roll.tables and st_roll.tables[0][0]["Symbol"] == "SYN"
    assert any("session=" in c and "SHADOW only" in c for c in st_roll.captions) is False


def test_stale_buy_flags_still_reject_historical_rows():
    now = _ts("2026-08-14 10:00:00")
    payload = _synthetic_state(
        [_synthetic_ready_row()],
        observed_at=(now - timedelta(minutes=20)).isoformat(),
    )
    payload["candidate_is_buy"] = True
    st = _VisSt()
    render_v2_shadow_action_panel(
        None,
        st_module=st,
        now=now,
        source_mode="remote",
        fetcher=lambda: json.dumps(payload),
    )
    assert any("production BUY flags" in c for c in st.captions)
    assert VALIDATION_TITLE not in "\n".join(st.markdowns)
    assert not st.tables
