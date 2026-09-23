"""Setup-specific WHEN predicates: EARLY, pull supply, frozen CHỜ PULL.

BREAK confirmation is not redefined here. Shadow flags stay false.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.intraday_pxv_v1.constants import RESEARCH_DEFAULT_EXPANSION_X
from modules.intraday_pxv_v1.features import FAM_EXPANSION
from modules.live_candidate_v2_action.contract import (
    CANDIDATE_IS_BUY,
    EARLY_MAX_PROGRESS_PCT,
    EARLY_MODERATE_VOLUME_MIN,
    PULL_SUPPLY_VOLUME,
    PULL_ZONE_MAX_PCT,
    PXV_IMPLIES_BUY,
    ALERT_ELIGIBLE,
    REASON_EARLY_BUY_READY,
    REASON_EARLY_FAM_SELL,
    REASON_EARLY_PRICE,
    REASON_EARLY_SINGLE_BAR,
    REASON_EARLY_VOLUME,
    REASON_MANH_BUY_READY,
    REASON_NOMINATED_NO_BARS,
    REASON_PULL_BUY_READY,
    REASON_PULL_FAM_SELL,
    REASON_PULL_NO_QUIET_SUPPLY,
    REASON_PULL_VOLUME_NOT_QUIET,
    REASON_UNFINISHED,
    REASON_CHRONOLOGY_PRE_ELIGIBLE,
)
from modules.live_candidate_v2_action.live_universe import (
    ACTIONABLE_LIVE_SETUPS,
    select_actionable_v2,
)
from modules.live_candidate_v2_action.observe_bars import bar_evidence_from_interpret
from modules.live_candidate_v2_action.state import (
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
    nomination_from_mapping,
)
from modules.live_candidate_v2_nomination.intent import CANH_ADD_ACTION, CHO_PULL_ACTION

VN = ZoneInfo("Asia/Ho_Chi_Minh")
DAY = "2026-08-14"
REF_C = 27100


def _ts(hm: str, day: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN)


def _nom(
    setup: str,
    *,
    source_action: str = "",
    ema9: float | None = 27.1,
    eligible: str = f"{DAY}T09:00:00+07:00",
    first: str = f"{DAY}T09:00:00+07:00",
    session: str = DAY,
) -> FrozenNomination:
    return FrozenNomination(
        symbol="HPG",
        session=session,
        setup=setup,
        group=setup,
        candidate_first_seen_ts=first,
        eligible_from=eligible,
        observation_reference="EMA9" if setup != "MUA EARLY" else "",
        ema9_at_first_seen=ema9,
        market_permission="OK",
        chronology_status="ELIGIBLE",
        source_action=source_action,
    )


def _bar(
    hm: str,
    *,
    close_vs_ref: float,
    vol_state: str | None = "NORMAL",
    ratio: float | None = None,
    pxv: str = "FLAT",
    fam_sell: bool = False,
    published: str = "NEUTRAL",
    completed: bool = True,
    unfinished: bool = False,
    day: str = DAY,
    ref_state: str = "EMA9",
    ref_kind: str = "EMA9",
) -> BarEvidence:
    ts = _ts(hm, day)
    close_c = REF_C + int(close_vs_ref)
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
        reference_canonical=REF_C,
        close_vs_ref=float(close_vs_ref),
        close_vs_ref_pct=(close_vs_ref / REF_C) * 100.0,
        reference_state=ref_state,
        data_state="QUALIFIED",
        raw_evidence=published,
        published_evidence=published,
        volume_expansion_state=vol_state,
        volume_expansion_ratio=ratio,
        price_volume_state=pxv,
        fam_sell=fam_sell,
        sell_expansion=pxv == "SELL_EXPANSION",
        chronology_legal=True,
    )


def _assert_shadow(result) -> None:
    assert result.candidate_is_buy is False
    assert result.pxv_implies_buy is False
    assert result.alert_eligible is False
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False


def _early_pair(*, close_vs_ref: float = 80, ratio: float | None = 1.35, fam_sell: bool = False):
    return [
        _bar("09:20", close_vs_ref=close_vs_ref, ratio=ratio, vol_state="NORMAL", fam_sell=fam_sell),
        _bar("09:25", close_vs_ref=close_vs_ref, ratio=ratio, vol_state="NORMAL", fam_sell=fam_sell),
    ]


def test_thresholds_reuse_existing_pxv_cuts():
    assert PULL_ZONE_MAX_PCT == 1.0
    assert EARLY_MAX_PROGRESS_PCT == PULL_ZONE_MAX_PCT
    assert EARLY_MODERATE_VOLUME_MIN == 1.0
    assert RESEARCH_DEFAULT_EXPANSION_X == 2.0
    assert PULL_SUPPLY_VOLUME == "CONTRACTION"


def test_early_price_alone_is_wait():
    result = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(ratio=None))
    assert result.action_state == "WAIT"
    assert result.action_reason == REASON_EARLY_VOLUME
    _assert_shadow(result)


def test_early_moderate_volume_without_controlled_price_is_wait():
    below = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(close_vs_ref=-40, ratio=1.35))
    assert below.action_state == "WAIT"
    assert below.action_reason == REASON_EARLY_PRICE
    extended = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(close_vs_ref=800, ratio=1.35))
    assert extended.action_state == "WAIT"
    assert extended.action_reason == REASON_EARLY_PRICE
    flat = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(close_vs_ref=0, ratio=1.35))
    assert flat.action_state == "WAIT"
    assert flat.action_reason == REASON_EARLY_PRICE


def test_early_controlled_price_and_moderate_volume_is_shadow_buy_ready():
    result = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(close_vs_ref=80, ratio=1.35))
    assert result.action_state == "BUY_READY"
    assert result.action_reason == REASON_EARLY_BUY_READY
    assert result.route == "EARLY"
    _assert_shadow(result)
    # Boundaries of the reused ratio: median and the 2.0× spike are not moderate.
    at_median = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(ratio=1.0))
    assert at_median.action_state == "WAIT"
    assert at_median.action_reason == REASON_EARLY_VOLUME
    at_spike = evaluate_shadow_action(
        _nom("MUA EARLY"),
        _early_pair(ratio=RESEARCH_DEFAULT_EXPANSION_X),
    )
    assert at_spike.action_state == "WAIT"
    assert at_spike.action_reason == REASON_EARLY_VOLUME


def test_early_distribution_is_not_buy_ready():
    sell = evaluate_shadow_action(_nom("MUA EARLY"), _early_pair(fam_sell=True))
    assert sell.action_state != "BUY_READY"
    assert sell.action_reason == REASON_EARLY_FAM_SELL
    expansion_sell = evaluate_shadow_action(
        _nom("MUA EARLY"),
        [
            _bar("09:20", close_vs_ref=80, ratio=1.4, pxv="SELL_EXPANSION"),
            _bar("09:25", close_vs_ref=80, ratio=1.4, pxv="SELL_EXPANSION"),
        ],
    )
    assert expansion_sell.action_state != "BUY_READY"


def test_early_unfinished_and_pre_eligible_bars_are_ignored():
    nom = _nom("MUA EARLY", eligible=f"{DAY}T09:20:00+07:00")
    only_illegal = evaluate_shadow_action(
        nom,
        [
            _bar("09:15", close_vs_ref=80, ratio=1.4),
            _bar("09:20", close_vs_ref=80, ratio=1.4, unfinished=True, completed=False),
        ],
    )
    assert only_illegal.action_state != "BUY_READY"
    assert only_illegal.n_legal_bars == 0
    assert REASON_CHRONOLOGY_PRE_ELIGIBLE in only_illegal.notes
    assert REASON_UNFINISHED in only_illegal.notes

    one_legal = evaluate_shadow_action(
        nom,
        [
            _bar("09:15", close_vs_ref=80, ratio=1.4),
            _bar("09:20", close_vs_ref=80, ratio=1.4, unfinished=True, completed=False),
            _bar("09:25", close_vs_ref=80, ratio=1.4),
        ],
    )
    assert one_legal.action_state == "WAIT"
    assert one_legal.action_reason == REASON_EARLY_SINGLE_BAR
    assert one_legal.n_legal_bars == 1


def test_early_is_in_the_live_observation_universe():
    assert "MUA EARLY" in ACTIONABLE_LIVE_SETUPS
    now = datetime.fromisoformat("2026-09-23 09:20:45").replace(tzinfo=VN)
    selected = select_actionable_v2(
        [
            {
                "symbol": "MSH",
                "setup": "MUA EARLY",
                "group": "MUA EARLY",
                "eligible_from": "2026-09-23T09:15:00+07:00",
                "candidate_first_seen_ts": "2026-09-22T15:22:00+07:00",
                "source": "brain_a_scan_setup",
                "ema9_at_first_seen": 27.1,
            }
        ],
        now=now,
    )
    assert [row["symbol"] for row in selected.fetch] == ["MSH"]


def test_early_without_frozen_ema9_does_not_invent_a_level():
    empty = evaluate_shadow_action(_nom("MUA EARLY", ema9=None), [])
    assert empty.action_state == "NOMINATED"
    assert empty.action_reason == "EARLY_NO_DEFENSIBLE_FROZEN_REF"
    barred = evaluate_shadow_action(
        _nom("MUA EARLY", ema9=None),
        [_bar("09:20", close_vs_ref=80, ratio=1.4, ref_state="UNAVAILABLE", ref_kind="")],
    )
    assert barred.action_state == "WAIT"
    assert barred.action_reason == "EARLY_NO_DEFENSIBLE_FROZEN_REF"


def test_pull_two_bars_above_without_supply_evidence_is_wait():
    # 400 VND on a 27100 ref is about 1.48%, outside the 1% EMA9 area.
    bars = [
        _bar("09:15", close_vs_ref=400, vol_state="NORMAL"),
        _bar("09:20", close_vs_ref=500, vol_state="NORMAL"),
    ]
    dep = evaluate_shadow_action(_nom("PULL ĐẸP"), bars)
    vua = evaluate_shadow_action(_nom("PULL VỪA"), bars)
    assert dep.action_state == vua.action_state == "WAIT"
    assert dep.action_reason == vua.action_reason == REASON_PULL_NO_QUIET_SUPPLY
    assert dep.route == vua.route == "PULL"
    _assert_shadow(dep)


def test_pull_quiet_supply_then_reclaim_is_shadow_buy_ready():
    bars = [
        _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=30, vol_state="NORMAL"),
        _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
    ]
    result = evaluate_shadow_action(_nom("PULL VỪA"), bars)
    assert result.action_state == "BUY_READY"
    assert result.action_reason == REASON_PULL_BUY_READY
    _assert_shadow(result)
    touched = evaluate_shadow_action(
        _nom("PULL ĐẸP"),
        [
            _bar("09:15", close_vs_ref=40, vol_state="CONTRACTION"),
            _bar("09:20", close_vs_ref=80, vol_state="NORMAL"),
        ],
    )
    assert touched.action_state == "BUY_READY"
    assert touched.action_reason == REASON_PULL_BUY_READY


def test_pull_expansion_or_sell_blocks_the_same_price_path():
    path = [
        _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=30, vol_state="EXPANSION"),
        _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
    ]
    expanded = evaluate_shadow_action(_nom("PULL ĐẸP"), path)
    assert expanded.action_state != "BUY_READY"
    assert expanded.action_reason == REASON_PULL_VOLUME_NOT_QUIET
    sold = evaluate_shadow_action(
        _nom("PULL ĐẸP"),
        [
            _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION", fam_sell=True),
            _bar("09:20", close_vs_ref=30, vol_state="NORMAL", fam_sell=True),
            _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
        ],
    )
    assert sold.action_state != "BUY_READY"
    assert sold.action_reason == REASON_PULL_FAM_SELL


def test_pull_missing_volume_classification_fails_closed():
    missing = evaluate_shadow_action(
        _nom("PULL ĐẸP"),
        [
            _bar("09:15", close_vs_ref=-120, vol_state="CONTRACTION"),
            _bar("09:20", close_vs_ref=30, vol_state=None),
            _bar("09:25", close_vs_ref=40, vol_state=None),
        ],
    )
    assert missing.action_state != "BUY_READY"
    assert missing.action_reason == REASON_PULL_VOLUME_NOT_QUIET
    no_class = evaluate_shadow_action(
        _nom("PULL ĐẸP"),
        [
            _bar("09:15", close_vs_ref=40, vol_state=None),
            _bar("09:20", close_vs_ref=80, vol_state=""),
        ],
    )
    assert no_class.action_state != "BUY_READY"
    assert no_class.action_reason == REASON_PULL_VOLUME_NOT_QUIET


def test_cp_manh_momentum_keeps_strengthen():
    bars = [
        _bar("09:15", close_vs_ref=50, published="NEUTRAL", vol_state="EXPANSION", pxv="CONFIRMING"),
        _bar(
            "09:20",
            close_vs_ref=80,
            published="STRENGTHEN",
            vol_state="EXPANSION",
            pxv="CONFIRMING",
        ),
    ]
    named = evaluate_shadow_action(_nom("CP MẠNH", source_action=CANH_ADD_ACTION), bars)
    implicit = evaluate_shadow_action(_nom("CP MẠNH"), bars)
    assert named.action_state == implicit.action_state == "BUY_READY"
    assert named.action_reason == implicit.action_reason == REASON_MANH_BUY_READY
    assert named.route == implicit.route == "MANH"


def test_frozen_cho_pull_uses_pull_semantics():
    pull_bars = [
        _bar("09:15", close_vs_ref=-80, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
    ]
    cho = evaluate_shadow_action(_nom("CP MẠNH", source_action=CHO_PULL_ACTION), pull_bars)
    assert cho.route == "PULL"
    assert cho.action_state == "BUY_READY"
    assert cho.action_reason == REASON_PULL_BUY_READY
    strengthen = [
        _bar("09:15", close_vs_ref=400, published="NEUTRAL", vol_state="EXPANSION", pxv="CONFIRMING"),
        _bar(
            "09:20",
            close_vs_ref=500,
            published="STRENGTHEN",
            vol_state="EXPANSION",
            pxv="CONFIRMING",
        ),
    ]
    not_momentum = evaluate_shadow_action(_nom("CP MẠNH", source_action=CHO_PULL_ACTION), strengthen)
    assert not_momentum.route == "PULL"
    assert not_momentum.action_state != "BUY_READY"


def test_later_recommendation_cannot_change_frozen_routing():
    cho = nomination_from_mapping(
        {
            "symbol": "HPG",
            "session": DAY,
            "setup": "CP MẠNH",
            "candidate_first_seen_ts": f"{DAY}T09:00:00+07:00",
            "eligible_from": f"{DAY}T09:00:00+07:00",
            "source_action": CHO_PULL_ACTION,
            "dist_from_ema9_pct": 0.2,
            "current_action": CANH_ADD_ACTION,
            "market_permission": "OK",
            "ema9_at_first_seen": 27.1,
        }
    )
    assert cho.route == "PULL"
    assert cho.source_action == CHO_PULL_ACTION
    add = nomination_from_mapping(
        {
            "symbol": "HPG",
            "session": DAY,
            "setup": "CP MẠNH",
            "candidate_first_seen_ts": f"{DAY}T09:00:00+07:00",
            "eligible_from": f"{DAY}T09:00:00+07:00",
            "source_action": CANH_ADD_ACTION,
            "dist_from_ema9_pct": 9.0,
            "current_action": CHO_PULL_ACTION,
            "market_permission": "OK",
            "ema9_at_first_seen": 27.1,
        }
    )
    assert add.route == "MANH"
    bars = [
        _bar("09:15", close_vs_ref=-80, vol_state="CONTRACTION"),
        _bar("09:20", close_vs_ref=20, vol_state="NORMAL"),
        _bar("09:25", close_vs_ref=40, vol_state="NORMAL"),
    ]
    assert evaluate_shadow_action(cho, bars).action_reason == REASON_PULL_BUY_READY
    assert evaluate_shadow_action(add, bars).action_state != "BUY_READY"


def test_interpreter_copies_existing_expansion_ratio():
    class _Ledger:
        features = {FAM_EXPANSION: {"state": "NORMAL", "value": 1.25}}
        data_state = "QUALIFIED"
        gate_reason = ""
        raw_evidence = "NEUTRAL"
        overlay_applied = False

    evidence = bar_evidence_from_interpret(
        _nom("MUA EARLY"),
        bar={"bar_ts": _ts("09:20"), "open": 27.2, "high": 27.3, "low": 27.1, "close": 27.2, "volume": 1200},
        ledger=_Ledger(),
        published="NEUTRAL",
        observe={
            "close_canonical": 27200,
            "reference_kind": "EMA9",
            "reference_value": 27.1,
            "reference_canonical": 27100,
            "close_vs_ref": 100.0,
            "close_vs_ref_pct": 100 / 27100 * 100,
            "reference_state": "EMA9",
        },
        overlay_truth_class="canonical_first_write",
    )
    assert evidence.volume_expansion_state == "NORMAL"
    assert evidence.volume_expansion_ratio == 1.25


def test_early_nominated_then_wait_then_buy_ready():
    nom = _nom("MUA EARLY")
    nominated = evaluate_shadow_action(nom, [])
    assert nominated.action_state == "NOMINATED"
    assert nominated.action_reason == REASON_NOMINATED_NO_BARS
    waiting = evaluate_shadow_action(nom, [_bar("09:20", close_vs_ref=80, ratio=1.3)])
    assert waiting.action_state == "WAIT"
    assert waiting.action_reason == REASON_EARLY_SINGLE_BAR
    ready = evaluate_shadow_action(nom, _early_pair())
    assert ready.action_state == "BUY_READY"
    assert ready.action_reason == REASON_EARLY_BUY_READY
