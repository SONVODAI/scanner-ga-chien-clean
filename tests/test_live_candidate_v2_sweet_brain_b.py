"""Live Candidate V2 SHADOW — Market-Aware Sweetspot Observer as Brain B.

Observation only. Candidate != BUY. Sweet-only must never BUY_READY.
Does not depend on VNINDEX/vnstock network.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.candidate_router.contract import (
    DEFAULT_SOURCE_PRIORITY,
    ENABLED_SOURCES,
    SOURCE_PRIORITY,
    SRC_BRAIN_A_SCAN_SETUP,
    SRC_BUY_ELITE,
    SRC_LEARNING_INSIGHT,
    SRC_MARKET_AWARE_SWEETSPOT,
    SRC_ROTATION,
)
from modules.candidate_router.router import source_priority
from modules.live_candidate_v2_action.contract import (
    REASON_UNKNOWN_SETUP,
    STATE_BUY_READY,
    STATE_NOMINATED,
    STATE_WAIT,
)
from modules.live_candidate_v2_action.state import (
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
    nomination_from_mapping,
)
from modules.live_candidate_v2_camera.contract import (
    REF_UNAVAILABLE,
    SHADOW_V2_ENABLED_SOURCES,
)
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref
from modules.live_candidate_v2_camera.sidecar import (
    build_sidecar_document,
    build_sidecar_from_scan,
    freeze_record_from_mapping,
    freeze_records_from_document,
)
from modules.live_candidate_v2_camera.ui import PANEL_TITLE
from modules.live_candidate_v2_nomination.contract import (
    MARKET_PERMISSION_OK,
    MARKET_PERMISSION_WEAK,
    SRC_BRAIN_A,
)
from modules.live_candidate_v2_nomination.intent import INTENT_WATCH_SETUP, REF_EMA9
from modules.live_candidate_v2_nomination.sweet_brain_b import (
    BRAIN_B_NOMINATED,
    BRAIN_B_NOT_TRADING_SESSION,
    BRAIN_B_UNAVAILABLE,
    BRAIN_B_VALID_EMPTY,
    DEFAULT_SWEET_LEDGER,
    REASON_FETCH_FAILURE,
    REASON_LEDGER_FAILURE,
    REASON_MISSING_FREEZE,
    REASON_NOT_TRADING,
    SWEET_OUTCOME_FIELDS,
    SWEET_PROVENANCE_FIELDS,
    consult_brain_b,
    predecessor_vnindex_session,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _scan(symbol: str, group: str, **extra) -> dict:
    rec = {
        "symbol": symbol,
        "date": extra.pop("date", "2026-08-25"),
        "group": group,
        "price": extra.pop("price", 27.5),
        "ema9": extra.pop("ema9", 27.1),
        "breakout_ref": extra.pop("breakout_ref", 28.0),
        "dist_from_ema9_pct": extra.pop("dist_from_ema9_pct", 1.4),
        "total_score": extra.pop("total_score", 5),
        "obv_status": extra.pop("obv_status", "🟢"),
        "warning": extra.pop("warning", ""),
    }
    rec.update(extra)
    return rec


def _consult(
    now: str,
    *,
    market_real: object = 7.2,
    trading_dates: tuple[str, ...] | None = None,
    ledger_path: Path | None = LEDGER,
    ledger: pd.DataFrame | None = None,
    vnindex_fetcher=None,
) -> object:
    kwargs: dict = {
        "observed_at": _ts(now),
        "market_real": market_real,
    }
    if trading_dates is not None:
        kwargs["trading_dates"] = trading_dates
    if ledger is not None:
        kwargs["ledger"] = ledger
    elif ledger_path is not None:
        kwargs["ledger_path"] = ledger_path
    if vnindex_fetcher is not None:
        kwargs["vnindex_fetcher"] = vnindex_fetcher
    return consult_brain_b(**kwargs)


def _sidecar(scan, brain_b, *, now: str, market_real: object = 7.2, prior_freeze=None):
    return build_sidecar_from_scan(
        scan,
        market_real=market_real,
        observed_at=_ts(now),
        prior_freeze=prior_freeze,
        brain_b=brain_b,
    )


def _sidecar_doc(report, rows, *, now: str):
    return build_sidecar_document(
        rows,
        observed_at=_ts(now),
        market_real=report.market_real,
        market_permission=report.market_permission,
        freeze_ledger=report.freeze_ledger,
        session=str(now)[:10],
    )


def _bar_pair_that_would_buy_pull(day: str = "2026-08-25") -> list[BarEvidence]:
    def bar(hm: str, close_vs_ref: float) -> BarEvidence:
        ts = _ts(f"{day} {hm}:00")
        close_c = 27100 + int(close_vs_ref)
        return BarEvidence(
            bar_ts=ts,
            asof=ts,
            completed=True,
            open=close_c,
            high=close_c + 50,
            low=close_c - 50,
            close=close_c,
            volume=1000,
            close_canonical=close_c,
            reference_kind="EMA9",
            reference_value=27.1,
            reference_canonical=27100,
            close_vs_ref=float(close_vs_ref),
            close_vs_ref_pct=(close_vs_ref / 27100) * 100.0,
            reference_state="EMA9",
            data_state="QUALIFIED",
            raw_evidence="STRENGTHEN",
            published_evidence="STRENGTHEN",
            volume_expansion_state="CONTRACTION",
            price_volume_state="FLAT",
            chronology_legal=True,
        )

    return [bar("09:20", 50), bar("09:25", 80)]


# ---------- source contract ----------


def test_source_id_shadow_only_not_production_and_not_reused():
    assert SRC_MARKET_AWARE_SWEETSPOT == "market_aware_sweetspot"
    from modules.live_candidate_v2_camera.contract import (
        SRC_MARKET_AWARE_SWEETSPOT as CAM_SWEET,
    )
    assert CAM_SWEET == SRC_MARKET_AWARE_SWEETSPOT
    assert SRC_MARKET_AWARE_SWEETSPOT != SRC_LEARNING_INSIGHT
    assert SRC_MARKET_AWARE_SWEETSPOT != SRC_BRAIN_A
    assert SRC_MARKET_AWARE_SWEETSPOT != SRC_BUY_ELITE
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_MARKET_AWARE_SWEETSPOT not in ENABLED_SOURCES
    assert SRC_BRAIN_A not in ENABLED_SOURCES
    assert SRC_BRAIN_A in SHADOW_V2_ENABLED_SOURCES
    assert SRC_MARKET_AWARE_SWEETSPOT in SHADOW_V2_ENABLED_SOURCES
    assert SRC_LEARNING_INSIGHT not in SHADOW_V2_ENABLED_SOURCES
    assert SRC_ROTATION not in SHADOW_V2_ENABLED_SOURCES
    assert SRC_BRAIN_A == SRC_BRAIN_A_SCAN_SETUP
    assert SOURCE_PRIORITY[SRC_BRAIN_A] == 5
    assert SOURCE_PRIORITY[SRC_MARKET_AWARE_SWEETSPOT] == 40
    assert source_priority(SRC_BRAIN_A) < source_priority(SRC_MARKET_AWARE_SWEETSPOT)
    assert source_priority(SRC_BRAIN_A) != DEFAULT_SOURCE_PRIORITY
    assert source_priority(SRC_MARKET_AWARE_SWEETSPOT) != DEFAULT_SOURCE_PRIORITY


def test_predecessor_is_previous_vnindex_session_not_calendar_t_minus_1():
    assert predecessor_vnindex_session("2026-08-17", ("2026-08-14", "2026-08-17")) == "2026-08-14"
    assert predecessor_vnindex_session("2026-09-03", ("2026-08-27", "2026-09-03")) == "2026-08-27"
    assert predecessor_vnindex_session("2026-08-25", ("2026-08-24", "2026-08-25")) == "2026-08-24"


# ---------- 1. Sweet-only enters SHADOW V2 ----------


def test_sweet_only_nomination_enters_shadow_v2_without_brain_a():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    assert brain_b.status == BRAIN_B_NOMINATED
    assert {n.symbol for n in brain_b.nominations} == {"DPG"}
    report, rows = _sidecar([], brain_b, now="2026-08-25 10:05:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "DPG"
    assert row["source"] == SRC_MARKET_AWARE_SWEETSPOT
    assert row["nomination_source"] == SRC_MARKET_AWARE_SWEETSPOT
    assert row["candidate_is_buy"] is False
    assert report.nominations[0].source == SRC_MARKET_AWARE_SWEETSPOT
    assert not any(r.symbol == "DPG" for r in report.freeze_ledger)


# ---------- 2. Brain A-only unchanged ----------


def test_brain_a_only_behavior_unchanged_when_brain_b_not_consulted():
    report, rows = build_sidecar_from_scan(
        [_scan("HPG", "PULL ĐẸP", date="2026-08-14")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    assert len(rows) == 1
    assert rows[0]["symbol"] == "HPG"
    assert rows[0]["source"] == SRC_BRAIN_A
    assert rows[0]["setup"] == "PULL ĐẸP"
    assert rows[0]["observation_reference"] == REF_EMA9
    assert rows[0]["ema9_at_first_seen"] == 27.1
    assert report.brain_b_status == ""
    assert report.freeze_ledger[0].symbol == "HPG"


# ---------- 3. A+B same symbol ----------


def test_a_plus_b_same_symbol_one_row_brain_a_canonical_both_provenance():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    report, rows = _sidecar(
        [_scan("DPG", "PULL ĐẸP", date="2026-08-25", ema9=30.1, price=31.0)],
        brain_b,
        now="2026-08-25 10:05:00",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "DPG"
    assert row["source"] == SRC_BRAIN_A
    assert row["setup"] == "PULL ĐẸP"
    assert row["observation_reference"] == REF_EMA9
    assert row["ema9_at_first_seen"] == 30.1
    sources = [p["source"] for p in row["provenance"]]
    assert SRC_BRAIN_A in sources
    assert SRC_MARKET_AWARE_SWEETSPOT in sources
    sweet = next(p for p in row["provenance"] if p["source"] == SRC_MARKET_AWARE_SWEETSPOT)
    assert sweet["sweet_t0_date"] == "2026-08-24"
    assert sweet["sweet_created_at"] == "2026-08-24T11:13:40Z"
    assert report.freeze_ledger[0].ema9_at_first_seen == 30.1


def test_a_plus_b_canonical_is_source_priority_not_string_order():
    """Identical clocks: Brain A still wins. String order would prefer Sweet."""
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    assert SRC_MARKET_AWARE_SWEETSPOT > SRC_BRAIN_A  # string-order trap
    report, rows = _sidecar(
        [_scan("DPG", "MUA BREAK", date="2026-08-25", breakout_ref=32.0)],
        brain_b,
        now="2026-08-25 10:05:00",
    )
    assert rows[0]["source"] == SRC_BRAIN_A
    assert rows[0]["setup"] == "MUA BREAK"
    assert report.nominations[0].source == SRC_BRAIN_A


# ---------- 4+5. Sweet-only never BUY_READY, no EMA9/breakout ref ----------


def test_sweet_only_never_buy_ready_and_has_no_timing_reference():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    _, rows = _sidecar([], brain_b, now="2026-08-25 10:05:00")
    row = rows[0]
    assert row["setup"] == ""
    assert row["group"] == ""
    assert row["observation_reference"] in {"", None}
    assert row["observation_intent"] == INTENT_WATCH_SETUP
    assert row["ema9_at_first_seen"] is None
    assert row["breakout_ref_at_first_seen"] is None
    obs = observe_close_vs_ref(row, 32000)
    assert obs["reference_state"] == REF_UNAVAILABLE
    assert obs["close_vs_ref"] is None

    nom = nomination_from_mapping(row)
    assert nom.route == "UNKNOWN"
    assert nom.required_ref == ""
    bars = _bar_pair_that_would_buy_pull()
    result = evaluate_shadow_action(nom, bars)
    assert result.action_state != STATE_BUY_READY
    assert result.action_state in {STATE_WAIT, STATE_NOMINATED}
    assert result.action_reason == REASON_UNKNOWN_SETUP
    assert result.candidate_is_buy is False

    pull = FrozenNomination(
        symbol="DPG",
        session="2026-08-25",
        setup="PULL ĐẸP",
        candidate_first_seen_ts=row["candidate_first_seen_ts"],
        eligible_from=row["eligible_from"],
        observation_reference=REF_EMA9,
        ema9_at_first_seen=27.1,
        market_permission=MARKET_PERMISSION_OK,
    )
    would_ready = evaluate_shadow_action(pull, bars)
    assert would_ready.action_state == STATE_BUY_READY


# ---------- 6+7+8. clocks ----------


def test_sweet_clocks_first_seen_created_at_eligible_t_open_session_t():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    nom = brain_b.nominations[0]
    assert nom.session == "2026-08-25"
    assert nom.session != "2026-08-24"
    assert nom.candidate_first_seen_ts == "2026-08-24T11:13:40Z"
    assert not nom.candidate_first_seen_ts.startswith("2026-08-25T09:15")
    assert nom.eligible_from.startswith("2026-08-25T09:15:00")
    first = pd.Timestamp(nom.candidate_first_seen_ts)
    elig = pd.Timestamp(nom.eligible_from)
    assert elig >= first
    extra = brain_b.provenance[0]
    assert extra["sweet_t0_date"] == "2026-08-24"
    assert extra["sweet_created_at"] == "2026-08-24T11:13:40Z"


# ---------- 9. zero predecessor = valid empty, A still works ----------


def test_zero_predecessor_sweet_day_is_valid_empty_brain_a_still_works():
    brain_b = _consult(
        "2026-09-07 10:05:00",
        trading_dates=("2026-09-04", "2026-09-07"),
    )
    assert brain_b.status == BRAIN_B_VALID_EMPTY
    assert brain_b.predecessor == "2026-09-04"
    assert brain_b.nominations == ()
    report, rows = _sidecar(
        [_scan("HPG", "PULL ĐẸP", date="2026-09-07")],
        brain_b,
        now="2026-09-07 10:05:00",
    )
    assert report.brain_b_status == BRAIN_B_VALID_EMPTY
    assert [r["symbol"] for r in rows] == ["HPG"]
    assert rows[0]["source"] == SRC_BRAIN_A


# ---------- 10+11. missing freeze != empty, no carry-forward ----------


def test_missing_predecessor_freeze_is_unavailable_not_empty_no_carry_forward():
    brain_b = _consult(
        "2026-08-27 10:05:00",
        trading_dates=("2026-08-25", "2026-08-26", "2026-08-27"),
    )
    assert brain_b.status == BRAIN_B_UNAVAILABLE
    assert brain_b.predecessor == "2026-08-26"
    assert REASON_MISSING_FREEZE in brain_b.reason
    assert brain_b.nominations == ()
    symbols = {n.symbol for n in brain_b.nominations}
    assert "NT2" not in symbols
    assert "IDC" not in symbols
    assert "HPG" not in symbols
    report, rows = _sidecar(
        [_scan("SSI", "MUA BREAK", date="2026-08-27")],
        brain_b,
        now="2026-08-27 10:05:00",
    )
    assert report.brain_b_status == BRAIN_B_UNAVAILABLE
    assert report.brain_b_status != BRAIN_B_VALID_EMPTY
    assert [r["symbol"] for r in rows] == ["SSI"]


# ---------- 12. weekend / holiday-shaped VNINDEX gap ----------


def test_weekend_gap_uses_previous_vnindex_session_not_calendar_t_minus_1():
    brain_b = _consult(
        "2026-08-17 10:05:00",
        trading_dates=("2026-08-14", "2026-08-17"),
    )
    assert brain_b.predecessor == "2026-08-14"
    assert brain_b.predecessor != "2026-08-16"
    assert brain_b.status == BRAIN_B_VALID_EMPTY  # 2026-08-14 insufficient freeze


def test_holiday_shaped_gap_uses_previous_vnindex_session():
    brain_b = _consult(
        "2026-09-03 10:05:00",
        trading_dates=("2026-08-27", "2026-09-03"),
    )
    assert brain_b.predecessor == "2026-08-27"
    assert brain_b.predecessor != "2026-09-02"
    assert brain_b.status == BRAIN_B_NOMINATED
    assert "HPG" in {n.symbol for n in brain_b.nominations}


def test_not_trading_session_is_unavailable_not_valid_empty():
    brain_b = _consult(
        "2026-08-16 10:05:00",  # Sunday
        trading_dates=("2026-08-14", "2026-08-17"),
    )
    assert brain_b.status == BRAIN_B_NOT_TRADING_SESSION
    assert brain_b.status != BRAIN_B_VALID_EMPTY
    assert brain_b.reason == REASON_NOT_TRADING


# ---------- 13. T+1 does not retain D candidate without new Sweet T freeze ----------


def test_t_plus_1_does_not_retain_d_candidate_without_new_sweet_freeze():
    t = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25", "2026-08-26"),
    )
    assert {n.symbol for n in t.nominations} == {"DPG"}
    t1 = _consult(
        "2026-08-26 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25", "2026-08-26"),
    )
    assert t1.predecessor == "2026-08-25"
    assert "DPG" not in {n.symbol for n in t1.nominations}
    assert "NT2" in {n.symbol for n in t1.nominations}


# ---------- 14+15. live T market_permission vs frozen Sweet provenance ----------


def test_live_market_permission_can_change_frozen_sweet_provenance_unchanged():
    weak = _consult(
        "2026-08-25 10:05:00",
        market_real=5.4,
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    strong = _consult(
        "2026-08-25 13:00:00",
        market_real=7.2,
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    assert weak.nominations[0].symbol == "DPG"
    assert strong.nominations[0].symbol == "DPG"
    assert weak.nominations[0].market_permission == MARKET_PERMISSION_WEAK
    assert strong.nominations[0].market_permission == MARKET_PERMISSION_OK
    frozen_w = copy.deepcopy(weak.provenance[0])
    frozen_s = copy.deepcopy(strong.provenance[0])
    for key in ("symbol",):
        frozen_w.pop(key, None)
        frozen_s.pop(key, None)
    frozen_w.pop("chronology_status", None)
    frozen_s.pop("chronology_status", None)
    assert frozen_w == frozen_s
    assert "market_permission" not in frozen_w
    assert frozen_w["market_real_t0"] == 9.6
    assert frozen_w["market_real_t0"] != 5.4

    _, weak_rows = _sidecar([], weak, now="2026-08-25 10:05:00", market_real=5.4)
    assert weak_rows[0]["symbol"] == "DPG"
    assert weak_rows[0]["market_permission"] == MARKET_PERMISSION_WEAK
    action = evaluate_shadow_action(nomination_from_mapping(weak_rows[0]), [])
    assert action.action_state != STATE_BUY_READY


def test_weak_live_market_does_not_delete_sweet_only_nomination():
    """Brain A evaluate_nomination would drop WHAT on weak T. Sweet must stay."""
    brain_b = _consult(
        "2026-08-25 10:05:00",
        market_real=5.4,
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    report, rows = _sidecar(
        [_scan("AAA", "PULL ĐẸP", date="2026-08-25")],
        brain_b,
        now="2026-08-25 10:05:00",
        market_real=5.4,
    )
    symbols = {r["symbol"] for r in rows}
    assert "DPG" in symbols
    assert "AAA" not in symbols  # Brain A rejected MARKET_WEAK
    assert rows[0]["market_permission"] == MARKET_PERMISSION_WEAK


# ---------- 16. later outcome columns not copied ----------


def test_later_sweet_outcome_columns_are_not_copied_into_provenance():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    extra = brain_b.provenance[0]
    for col in SWEET_OUTCOME_FIELDS:
        assert col not in extra
    blob = str(extra)
    assert "t3_return_pct" not in blob
    assert "t5_return_pct" not in blob
    assert "t10_return_pct" not in blob
    for key in SWEET_PROVENANCE_FIELDS:
        assert key in extra
    assert extra["observer_id"]
    assert extra["matched_sweetspot"]
    _, rows = _sidecar([], brain_b, now="2026-08-25 10:05:00")
    sweet = next(p for p in rows[0]["provenance"] if p["source"] == SRC_MARKET_AWARE_SWEETSPOT)
    for col in SWEET_OUTCOME_FIELDS:
        assert col not in sweet


# ---------- fetch / ledger failure ----------


def test_ledger_read_failure_is_unavailable():
    brain_b = consult_brain_b(
        observed_at=_ts("2026-08-25 10:05:00"),
        market_real=7.2,
        trading_dates=("2026-08-24", "2026-08-25"),
        ledger_path=REPO / "data" / "earning_learning" / "no_such_sweet_ledger.csv",
    )
    assert brain_b.status == BRAIN_B_UNAVAILABLE
    assert REASON_LEDGER_FAILURE in brain_b.reason
    assert brain_b.status != BRAIN_B_VALID_EMPTY


def test_vnindex_fetch_failure_is_unavailable():
    def boom(start: str, end: str):
        raise RuntimeError("network down")

    brain_b = consult_brain_b(
        observed_at=_ts("2026-08-25 10:05:00"),
        market_real=7.2,
        vnindex_fetcher=boom,
    )
    assert brain_b.status == BRAIN_B_UNAVAILABLE
    assert REASON_FETCH_FAILURE in brain_b.reason


# ---------- 17. production ENABLED_SOURCES + 18/19/20 isolation ----------


def test_production_enabled_sources_and_untouched_surfaces():
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert PANEL_TITLE == "Live Candidate V2"
    observer = (REPO / "modules" / "market_aware_sweetspot_observer.py").read_text(encoding="utf-8")
    assert "consult_brain_b" not in observer
    assert "live_candidate_v2" not in observer
    predicate = (REPO / "modules" / "live_candidate_v2_nomination" / "predicate.py").read_text(
        encoding="utf-8"
    )
    assert SRC_MARKET_AWARE_SWEETSPOT not in predicate
    assert "evaluate_nomination" in predicate
    for rel in (
        "modules/rotation_watch/engine.py",
        "modules/live_candidate_v2_action/state.py",
        "modules/intraday_pxv_v1/interpret.py",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert SRC_MARKET_AWARE_SWEETSPOT not in text
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "run_v2_cloud_sidecar(" in app
    assert "fetch_v2_sidecar()" in app
    digest = hashlib.sha256(LEDGER.read_bytes()).hexdigest()
    assert hashlib.sha256(DEFAULT_SWEET_LEDGER.read_bytes()).hexdigest() == digest


def test_no_sweet_top_n_all_observe_rows_enter_sidecar():
    brain_b = _consult(
        "2026-08-26 10:05:00",
        trading_dates=("2026-08-25", "2026-08-26"),
    )
    assert len(brain_b.nominations) >= 8
    _, rows = _sidecar([], brain_b, now="2026-08-26 10:05:00")
    assert {r["symbol"] for r in rows} == {n.symbol for n in brain_b.nominations}


def test_idc_observe_clocks_from_historical_ledger_row():
    brain_b = _consult(
        "2026-09-18 10:05:00",
        trading_dates=("2026-09-17", "2026-09-18"),
    )
    by = {n.symbol: n for n in brain_b.nominations}
    assert "IDC" in by
    assert by["IDC"].candidate_first_seen_ts == "2026-09-17T12:41:54Z"
    assert by["IDC"].session == "2026-09-18"
    assert by["IDC"].eligible_from.startswith("2026-09-18T09:15:00")
    extra = next(p for p in brain_b.provenance if p["symbol"] == "IDC")
    assert extra["price_t0"] == 32000.0
    assert extra["market_real_t0"] == 5.4
    assert extra["evidence_status"] == "EARLY"
    assert by["IDC"].source_reason == "OBSERVE"
    assert extra["evidence_status"] == "EARLY"


# ---------- freeze ownership: Sweet must never backfill Brain A prior_freeze ----------


def test_sweet_only_row_does_not_backfill_brain_a_freeze():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    report, rows = _sidecar([], brain_b, now="2026-08-25 10:05:00")
    row = rows[0]
    assert row["symbol"] == "DPG"
    assert row["source"] == SRC_MARKET_AWARE_SWEETSPOT
    assert freeze_record_from_mapping(row) is None
    assert freeze_record_from_mapping(row, require_brain_a_source=True) is None
    doc = _sidecar_doc(report, rows, now="2026-08-25 10:05:00")
    assert doc["freeze_ledger"] == []
    prior = freeze_records_from_document(doc)
    assert prior == ()
    assert not any(r.symbol == "DPG" for r in report.freeze_ledger)


def test_sweet_only_then_later_brain_a_same_session_mints_own_freeze():
    """Original DPG poison: Sweet-only first, then same-T Brain A PULL."""
    sweet_at = "2026-08-25 10:05:00"
    brain_b = _consult(sweet_at, trading_dates=("2026-08-24", "2026-08-25"))
    report1, rows1 = _sidecar([], brain_b, now=sweet_at)
    sweet_first = rows1[0]["candidate_first_seen_ts"]
    assert sweet_first == "2026-08-24T11:13:40Z"
    doc1 = _sidecar_doc(report1, rows1, now=sweet_at)
    prior = freeze_records_from_document(doc1)
    assert prior == ()

    later = "2026-08-25 13:00:00"
    report2, rows2 = _sidecar(
        [_scan("DPG", "PULL ĐẸP", date="2026-08-25", ema9=30.1, price=31.0)],
        brain_b,
        now=later,
        prior_freeze=prior,
    )
    assert len(rows2) == 1
    row = rows2[0]
    assert row["source"] == SRC_BRAIN_A
    assert row["setup"] == "PULL ĐẸP"
    assert row["ema9_at_first_seen"] == 30.1
    assert row["candidate_first_seen_ts"] == _ts(later).isoformat()
    assert row["candidate_first_seen_ts"] != sweet_first
    assert SRC_MARKET_AWARE_SWEETSPOT in {p["source"] for p in row["provenance"]}
    assert report2.freeze_ledger[0].ema9_at_first_seen == 30.1
    assert report2.freeze_ledger[0].candidate_first_seen_ts == row["candidate_first_seen_ts"]


def test_brain_a_then_later_sweet_keeps_brain_a_freeze_and_adds_provenance():
    first_at = "2026-08-25 10:05:00"
    report1, rows1 = _sidecar(
        [_scan("DPG", "PULL ĐẸP", date="2026-08-25", ema9=30.1, price=31.0)],
        None,
        now=first_at,
    )
    assert rows1[0]["source"] == SRC_BRAIN_A
    first_seen = rows1[0]["candidate_first_seen_ts"]
    assert first_seen.startswith("2026-08-25T10:05:00")
    doc1 = _sidecar_doc(report1, rows1, now=first_at)
    prior = freeze_records_from_document(doc1)
    assert len(prior) == 1
    assert prior[0].symbol == "DPG"
    assert prior[0].ema9_at_first_seen == 30.1
    assert prior[0].candidate_first_seen_ts == first_seen

    later = "2026-08-25 13:00:00"
    brain_b = _consult(later, trading_dates=("2026-08-24", "2026-08-25"))
    report2, rows2 = _sidecar(
        [_scan("DPG", "PULL ĐẸP", date="2026-08-25", ema9=99.0, price=40.0)],
        brain_b,
        now=later,
        prior_freeze=prior,
    )
    assert len(rows2) == 1
    row = rows2[0]
    assert row["source"] == SRC_BRAIN_A
    assert row["setup"] == "PULL ĐẸP"
    assert row["ema9_at_first_seen"] == 30.1
    assert row["candidate_first_seen_ts"] == first_seen
    sources = [p["source"] for p in row["provenance"]]
    assert SRC_BRAIN_A in sources
    assert SRC_MARKET_AWARE_SWEETSPOT in sources
    assert report2.freeze_ledger[0].ema9_at_first_seen == 30.1
    assert report2.freeze_ledger[0].candidate_first_seen_ts == first_seen


def test_genuine_brain_a_row_still_backfills_prior_freeze():
    now = "2026-08-14 10:05:00"
    report, rows = build_sidecar_from_scan(
        [_scan("HPG", "PULL ĐẸP", date="2026-08-14")],
        market_real=7.2,
        observed_at=_ts(now),
    )
    row = rows[0]
    assert row["source"] == SRC_BRAIN_A
    rec = freeze_record_from_mapping(row, require_brain_a_source=True)
    assert rec is not None
    assert rec.ema9_at_first_seen == 27.1
    doc = _sidecar_doc(report, rows, now=now)
    doc["freeze_ledger"] = []
    prior = freeze_records_from_document(doc)
    assert len(prior) == 1
    assert prior[0].symbol == "HPG"
    assert prior[0].candidate_first_seen_ts == row["candidate_first_seen_ts"]
    assert prior[0].ema9_at_first_seen == 27.1

    later, rows2 = build_sidecar_from_scan(
        [_scan("HPG", "PULL ĐẸP", date="2026-08-14", ema9=40.0, price=41.0)],
        market_real=7.2,
        observed_at=_ts("2026-08-14 13:00:00"),
        prior_freeze=prior,
    )
    assert rows2[0]["candidate_first_seen_ts"] == row["candidate_first_seen_ts"]
    assert rows2[0]["ema9_at_first_seen"] == 27.1
    assert later.freeze_ledger[0].ema9_at_first_seen == 27.1


def test_non_brain_a_generic_source_cannot_poison_brain_a_freeze():
    fake = {
        "symbol": "DPG",
        "session": "2026-08-25",
        "source": SRC_LEARNING_INSIGHT,
        "nomination_source": SRC_LEARNING_INSIGHT,
        "candidate_first_seen_ts": "2026-08-24T11:13:40Z",
        "eligible_from": "2026-08-25T09:15:00+07:00",
        "setup": "PULL ĐẸP",
        "ema9_at_first_seen": None,
        "breakout_ref_at_first_seen": None,
        "price_at_first_seen": 30500.0,
        "provenance": [{"source": SRC_BRAIN_A}],
    }
    assert freeze_record_from_mapping(fake) is None
    assert freeze_record_from_mapping(fake, require_brain_a_source=True) is None
    prior = freeze_records_from_document({"freeze_ledger": [], "rows": [fake]})
    assert prior == ()


def test_brain_a_row_with_sweet_in_provenance_still_owns_freeze():
    brain_b = _consult(
        "2026-08-25 10:05:00",
        trading_dates=("2026-08-24", "2026-08-25"),
    )
    report, rows = _sidecar(
        [_scan("DPG", "PULL ĐẸP", date="2026-08-25", ema9=30.1, price=31.0)],
        brain_b,
        now="2026-08-25 10:05:00",
    )
    row = rows[0]
    assert row["source"] == SRC_BRAIN_A
    assert SRC_MARKET_AWARE_SWEETSPOT in {p["source"] for p in row["provenance"]}
    rec = freeze_record_from_mapping(row, require_brain_a_source=True)
    assert rec is not None
    assert rec.ema9_at_first_seen == 30.1
    doc = _sidecar_doc(report, rows, now="2026-08-25 10:05:00")
    doc["freeze_ledger"] = []
    prior = freeze_records_from_document(doc)
    assert len(prior) == 1
    assert prior[0].ema9_at_first_seen == 30.1


# ---------- live session before today's VNINDEX daily bar ----------

LIVE_GAP_SYMBOLS = (
    "BFC",
    "BID",
    "BMP",
    "CTG",
    "HAH",
    "NTL",
    "OCB",
    "TVN",
    "VCB",
    "VGC",
)


def _live_gap_ledger() -> pd.DataFrame:
    """2026-09-21 freeze, one look-ahead D row, and one same-day T freeze."""
    rows = [
        {
            "t0_date": "2026-09-21",
            "symbol": symbol,
            "observer_status": "OBSERVE",
            "created_at": "2026-09-21T11:16:38Z",
            "price_t0": 10000.0,
        }
        for symbol in LIVE_GAP_SYMBOLS
    ]
    rows.append(
        {
            "t0_date": "2026-09-21",
            "symbol": "POISON",
            "observer_status": "OBSERVE",
            "created_at": "2026-09-22T04:00:00Z",
            "price_t0": 1.0,
        }
    )
    rows.append(
        {
            "t0_date": "2026-09-22",
            "symbol": "SAMEDAY",
            "observer_status": "OBSERVE",
            "created_at": "2026-09-22T01:00:00Z",
            "price_t0": 1.0,
        }
    )
    return pd.DataFrame(rows)


def test_open_live_session_uses_prior_freeze_before_todays_daily_bar():
    """VNINDEX history has 2026-09-21 only. 10:52 on 2026-09-22 is an open session."""
    from modules.intraday_execution_boundary import research_below_boundary_locked

    now = _ts("2026-09-22 10:52:00")
    assert research_below_boundary_locked(now) is True
    brain_b = _consult(
        "2026-09-22 10:52:00",
        market_real=5.7,
        trading_dates=("2026-09-21",),
        ledger=_live_gap_ledger(),
    )
    assert brain_b.status == BRAIN_B_NOMINATED
    assert brain_b.session == "2026-09-22"
    assert brain_b.predecessor == "2026-09-21"
    assert brain_b.reason == "PREDECESSOR_SWEET_OBSERVE"
    symbols = [n.symbol for n in brain_b.nominations]
    assert symbols == sorted(LIVE_GAP_SYMBOLS)
    assert "SAMEDAY" not in symbols
    assert "POISON" not in symbols
    for nom in brain_b.nominations:
        assert nom.eligible_from.startswith("2026-09-22T09:15:00")
        assert nom.chronology_status == "ELIGIBLE"
        assert nom.candidate_first_seen_ts == "2026-09-21T11:16:38Z"
        assert nom.market_permission == MARKET_PERMISSION_WEAK
        assert nom.source == SRC_MARKET_AWARE_SWEETSPOT
    _, rows = _sidecar([], brain_b, now="2026-09-22 10:52:00", market_real=5.7)
    assert [r["symbol"] for r in rows] == sorted(LIVE_GAP_SYMBOLS)
    assert rows[0]["market_permission"] == "WATCHLIST - MARKET YẾU"
    assert all(r["source"] == SRC_MARKET_AWARE_SWEETSPOT for r in rows)


def test_weekend_and_closed_clock_stay_not_trading_without_todays_bar():
    sunday = _consult(
        "2026-09-20 10:52:00",
        market_real=5.7,
        trading_dates=("2026-09-18",),
        ledger=_live_gap_ledger(),
    )
    assert sunday.status == BRAIN_B_NOT_TRADING_SESSION
    assert sunday.reason == REASON_NOT_TRADING
    assert sunday.nominations == ()

    pre_open = _consult(
        "2026-09-22 08:30:00",
        market_real=5.7,
        trading_dates=("2026-09-21",),
        ledger=_live_gap_ledger(),
    )
    assert pre_open.status == BRAIN_B_NOT_TRADING_SESSION
    assert pre_open.predecessor == ""

    after_close = _consult(
        "2026-09-22 15:30:00",
        market_real=5.7,
        trading_dates=("2026-09-21",),
        ledger=_live_gap_ledger(),
    )
    assert after_close.status == BRAIN_B_NOT_TRADING_SESSION
    assert after_close.nominations == ()


def test_completed_daily_bar_still_recognizes_t_after_the_cash_window():
    brain_b = _consult(
        "2026-09-22 19:40:00",
        market_real=5.7,
        trading_dates=("2026-09-21", "2026-09-22"),
        ledger=_live_gap_ledger(),
    )
    assert brain_b.status == BRAIN_B_NOMINATED
    assert brain_b.session == "2026-09-22"
    assert brain_b.predecessor == "2026-09-21"
    assert "SAMEDAY" not in {n.symbol for n in brain_b.nominations}
