"""Pure replayable V2 Action Layer.

    (frozen_nomination, legal_completed_5m_history) -> shadow_action_state + reason

Usable from live shadow, historical replay, and tests.
Does not import Streamlit. Does not mint a production BUY.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from modules.intraday_pxv_v1.constants import (
    DATA_UNUSABLE,
    EV_CONFLICT,
    EV_STRENGTHEN,
    EV_WEAKEN,
    OVERLAY_TRUTH_CANONICAL,
    OVERLAY_TRUTH_RETROSPECTIVE,
    RESEARCH_DEFAULT_EXPANSION_X,
)
from modules.intraday_pxv_v1.features import PXV_SELL_EXP, PXV_WEAK
from modules.intraday_pxv_v1.time_contract import parse_legal_ts
from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_camera.contract import REF_UNAVAILABLE, REF_UNIT_MISMATCH
from modules.live_candidate_v2_camera.observe import pxv_implies_buy
from modules.live_candidate_v2_nomination.intent import CHO_PULL_ACTION
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    EARLY_MAX_PROGRESS_PCT,
    EARLY_MODERATE_VOLUME_MIN,
    MARKET_PERMISSION_OK,
    MODE,
    PULL_SUPPLY_VOLUME,
    PULL_ZONE_MAX_PCT,
    PXV_IMPLIES_BUY,
    QUIET_VOLUME,
    REASON_CHRONOLOGY_PRE_ELIGIBLE,
    REASON_CONFLICT,
    REASON_DATA_UNUSABLE,
    REASON_DATE_ONLY,
    REASON_EARLY_BUY_READY,
    REASON_EARLY_EVIDENCE_ONLY,
    REASON_EARLY_FAM_SELL,
    REASON_EARLY_NO_FROZEN_REF,
    REASON_EARLY_PRICE,
    REASON_EARLY_SINGLE_BAR,
    REASON_EARLY_VOLUME,
    REASON_MANH_BUY_READY,
    REASON_MANH_FAM_SELL,
    REASON_MANH_PRICE_NO_STRENGTHEN,
    REASON_MANH_PXV_WEAK,
    REASON_MANH_STRENGTHEN_BELOW,
    REASON_MARKET_NOT_OK,
    REASON_NOMINATED_NO_BARS,
    REASON_NO_OBSERVATION_CAP,
    REASON_NO_OBSERVATION_MISSING_CAMERA,
    REASON_NO_OBSERVATION_NO_DATA,
    REASON_NO_OBSERVATION_PROVIDER,
    REASON_PULL_BELOW_REF,
    REASON_PULL_BUY_READY,
    REASON_PULL_FAM_SELL,
    REASON_PULL_NO_QUIET_SUPPLY,
    REASON_PULL_SINGLE_BAR,
    REASON_PULL_VOLUME_NOT_QUIET,
    REASON_REF_UNIT_MISMATCH,
    REASON_REF_UNUSABLE,
    REASON_RETROSPECTIVE,
    REASON_SESSION_RESET,
    REASON_UNFINISHED,
    REASON_UNKNOWN_SETUP,
    REASON_WAIT,
    REASON_WEAKENED_WAIT,
    REASON_WEAKENING,
    REF_BREAKOUT,
    REF_EMA9,
    ROUTE_BREAK,
    ROUTE_EARLY,
    ROUTE_MANH,
    ROUTE_PULL,
    SHADOW_BUY_READY_LABEL,
    SLICE,
    STATE_BUY_READY,
    STATE_NOMINATED,
    STATE_NO_OBSERVATION,
    STATE_WAIT,
    STATE_WEAKENED,
)

# Observation-reason tokens that must never masquerade as WAIT confirmation.
_NO_OBS_REASONS = {
    "CAP": REASON_NO_OBSERVATION_CAP,
    "SKIPPED_CAP": REASON_NO_OBSERVATION_CAP,
    "NO_DATA": REASON_NO_OBSERVATION_NO_DATA,
    "MISSING_CAMERA": REASON_NO_OBSERVATION_MISSING_CAMERA,
    "PROVIDER_ERROR": REASON_NO_OBSERVATION_PROVIDER,
    "RATE_LIMITED": REASON_NO_OBSERVATION_PROVIDER,
    "UNUSABLE": REASON_NO_OBSERVATION_NO_DATA,
    "STALE_BAR": REASON_NO_OBSERVATION_NO_DATA,
}


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return as_vn(ts).isoformat()


def _as_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return as_vn(value)
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return as_vn(ts.to_pydatetime())


def _num(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def action_route(setup: str, source_action: str = "") -> str:
    """Route from the frozen setup. CP MẠNH `CHỜ PULL` is the frozen action only."""
    setup = str(setup or "").strip()
    if setup in ROUTE_PULL:
        return "PULL"
    if setup == ROUTE_MANH:
        if str(source_action or "").strip() == CHO_PULL_ACTION:
            return "PULL"
        return "MANH"
    if setup == ROUTE_BREAK:
        return "BREAK"
    if setup == ROUTE_EARLY:
        return "EARLY"
    return "UNKNOWN"


def required_reference_kind(setup: str) -> str:
    setup = str(setup or "").strip()
    if setup in ROUTE_PULL or setup == ROUTE_MANH or setup == ROUTE_EARLY:
        return REF_EMA9
    if setup == ROUTE_BREAK:
        return REF_BREAKOUT
    return ""


@dataclass(frozen=True)
class FrozenNomination:
    """Already-nominated Brain A candidate. Not a BUY ticket."""

    symbol: str
    session: str
    setup: str
    candidate_first_seen_ts: str
    eligible_from: str
    observation_reference: str = ""
    ema9_at_first_seen: float | None = None
    breakout_ref_at_first_seen: float | None = None
    market_permission: str = ""
    chronology_status: str = ""
    group: str = ""
    nomination_reason: str = ""
    source: str = ""
    source_action: str = ""

    @property
    def route(self) -> str:
        return action_route(self.setup or self.group, self.source_action)

    @property
    def required_ref(self) -> str:
        return required_reference_kind(self.setup or self.group)


@dataclass(frozen=True)
class BarEvidence:
    """One legal-or-candidate 5m observation. Features already computed."""

    bar_ts: datetime
    asof: datetime
    completed: bool
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    close_canonical: int | None = None
    reference_kind: str | None = None
    reference_value: float | None = None
    reference_canonical: int | None = None
    close_vs_ref: float | None = None
    close_vs_ref_pct: float | None = None
    reference_state: str = REF_UNAVAILABLE
    data_state: str = ""
    gate_reason: str = ""
    raw_evidence: str = ""
    published_evidence: str = ""
    volume_expansion_state: str | None = None
    volume_expansion_ratio: float | None = None
    price_volume_state: str | None = None
    fam_sell: bool = False
    sell_expansion: bool = False
    overlay_truth_class: str = OVERLAY_TRUTH_CANONICAL
    overlay_applied: bool = False
    chronology_legal: bool = True
    unfinished: bool = False

    @property
    def close_ge_ref(self) -> bool | None:
        if self.close_vs_ref is None:
            return None
        return float(self.close_vs_ref) >= 0.0

    @property
    def close_lt_ref(self) -> bool | None:
        if self.close_vs_ref is None:
            return None
        return float(self.close_vs_ref) < 0.0

    @property
    def data_usable(self) -> bool:
        return str(self.data_state or "") != DATA_UNUSABLE and bool(self.data_state)

    @property
    def quiet_volume(self) -> bool:
        return str(self.volume_expansion_state or "") in QUIET_VOLUME

    @property
    def pxv_weak(self) -> bool:
        return str(self.price_volume_state or "") == PXV_WEAK

    @property
    def has_sell(self) -> bool:
        return bool(self.fam_sell) or bool(self.sell_expansion) or str(
            self.price_volume_state or ""
        ) == PXV_SELL_EXP


@dataclass(frozen=True)
class ActionResult:
    action_state: str
    action_reason: str
    route: str
    symbol: str
    session: str
    setup: str
    last_legal_bar_ts: str | None = None
    frozen_ref_kind: str = ""
    frozen_ref_value: float | None = None
    close_canonical: int | None = None
    reference_canonical: int | None = None
    close_vs_ref: float | None = None
    close_vs_ref_pct: float | None = None
    reference_state: str = REF_UNAVAILABLE
    n_legal_bars: int = 0
    observed: bool = True
    candidate_is_buy: bool = CANDIDATE_IS_BUY
    pxv_implies_buy: bool = PXV_IMPLIES_BUY
    alert_eligible: bool = ALERT_ELIGIBLE
    mode: str = MODE
    slice: str = SLICE
    shadow_label: str = ""
    source: str = ""
    trigger_price: float | None = None
    published_evidence: str = ""
    volume_expansion_state: str | None = None
    price_volume_state: str | None = None
    market_permission: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def nomination_from_mapping(raw: Mapping[str, Any]) -> FrozenNomination:
    setup = str(raw.get("setup") or raw.get("group") or "").strip()
    return FrozenNomination(
        symbol=str(raw.get("symbol") or "").strip().upper(),
        session=str(raw.get("session") or "").strip(),
        setup=setup,
        group=str(raw.get("group") or setup),
        candidate_first_seen_ts=str(raw.get("candidate_first_seen_ts") or ""),
        eligible_from=str(raw.get("eligible_from") or ""),
        observation_reference=str(raw.get("observation_reference") or ""),
        ema9_at_first_seen=_num(raw.get("ema9_at_first_seen")),
        breakout_ref_at_first_seen=_num(raw.get("breakout_ref_at_first_seen")),
        market_permission=str(raw.get("market_permission") or ""),
        chronology_status=str(raw.get("chronology_status") or ""),
        nomination_reason=str(raw.get("nomination_reason") or raw.get("candidate_reason") or ""),
        source=str(raw.get("nomination_source") or raw.get("source") or ""),
        source_action=str(raw.get("source_action") or ""),
    )


def bar_evidence_from_mapping(raw: Mapping[str, Any]) -> BarEvidence:
    bar_ts = _as_dt(raw.get("bar_ts") or raw.get("asof") or raw.get("timestamp"))
    if bar_ts is None:
        raise ValueError("bar_ts/asof required")
    asof = _as_dt(raw.get("asof") or raw.get("bar_ts") or raw.get("timestamp")) or bar_ts
    fam_sell = raw.get("fam_sell")
    if fam_sell is None:
        fam_sell = raw.get("FAM_SELL")
    if isinstance(fam_sell, Mapping):
        fam_sell = bool(fam_sell.get("state"))
    sell_exp = raw.get("sell_expansion")
    if sell_exp is None:
        pxv = str(raw.get("price_volume_state") or "")
        sell_exp = pxv == PXV_SELL_EXP
    completed = raw.get("completed")
    if completed is None:
        completed = raw.get("completed_bar")
    if completed is None:
        completed = not bool(raw.get("unfinished"))
    return BarEvidence(
        bar_ts=bar_ts,
        asof=asof,
        completed=bool(completed),
        open=_num(raw.get("open")),
        high=_num(raw.get("high")),
        low=_num(raw.get("low")),
        close=_num(raw.get("close")),
        volume=_num(raw.get("volume")),
        close_canonical=int(raw["close_canonical"]) if raw.get("close_canonical") is not None else None,
        reference_kind=str(raw.get("reference_kind") or raw.get("frozen_reference_kind") or "") or None,
        reference_value=_num(raw.get("reference_value") or raw.get("frozen_reference_value")),
        reference_canonical=(
            int(raw["reference_canonical"]) if raw.get("reference_canonical") is not None else None
        ),
        close_vs_ref=_num(raw.get("close_vs_ref")),
        close_vs_ref_pct=_num(raw.get("close_vs_ref_pct")),
        reference_state=str(raw.get("reference_state") or REF_UNAVAILABLE),
        data_state=str(raw.get("data_state") or ""),
        gate_reason=str(raw.get("gate_reason") or ""),
        raw_evidence=str(raw.get("raw_evidence") or ""),
        published_evidence=str(raw.get("published_evidence") or ""),
        volume_expansion_state=raw.get("volume_expansion_state"),
        volume_expansion_ratio=_num(raw.get("volume_expansion_ratio")),
        price_volume_state=raw.get("price_volume_state"),
        fam_sell=bool(fam_sell),
        sell_expansion=bool(sell_exp),
        overlay_truth_class=str(raw.get("overlay_truth_class") or OVERLAY_TRUTH_CANONICAL),
        overlay_applied=bool(raw.get("overlay_applied")),
        chronology_legal=bool(raw.get("chronology_legal", True)),
        unfinished=bool(raw.get("unfinished")),
    )


def _shadow_label(state: str) -> str:
    if state == STATE_BUY_READY:
        return SHADOW_BUY_READY_LABEL
    if state == STATE_NO_OBSERVATION:
        return f"SHADOW {STATE_NO_OBSERVATION}"
    return f"SHADOW {state}"


def _result(
    nom: FrozenNomination,
    state: str,
    reason: str,
    *,
    bars: Sequence[BarEvidence] = (),
    observed: bool = True,
    notes: Sequence[str] = (),
) -> ActionResult:
    last = bars[-1] if bars else None
    return ActionResult(
        action_state=state,
        action_reason=reason,
        route=nom.route,
        symbol=nom.symbol,
        session=nom.session,
        setup=nom.setup,
        last_legal_bar_ts=_iso(last.bar_ts) if last is not None else None,
        frozen_ref_kind=str((last.reference_kind if last else None) or nom.required_ref or ""),
        frozen_ref_value=last.reference_value if last is not None else (
            nom.ema9_at_first_seen if nom.required_ref == REF_EMA9 else nom.breakout_ref_at_first_seen
        ),
        close_canonical=last.close_canonical if last is not None else None,
        reference_canonical=last.reference_canonical if last is not None else None,
        close_vs_ref=last.close_vs_ref if last is not None else None,
        close_vs_ref_pct=last.close_vs_ref_pct if last is not None else None,
        reference_state=last.reference_state if last is not None else REF_UNAVAILABLE,
        n_legal_bars=len(bars),
        observed=observed,
        candidate_is_buy=CANDIDATE_IS_BUY,
        pxv_implies_buy=pxv_implies_buy(last.published_evidence if last is not None else None),
        alert_eligible=ALERT_ELIGIBLE,
        shadow_label=_shadow_label(state),
        source=nom.source,
        trigger_price=last.close if last is not None else None,
        published_evidence=str(last.published_evidence or "") if last is not None else "",
        volume_expansion_state=last.volume_expansion_state if last is not None else None,
        price_volume_state=last.price_volume_state if last is not None else None,
        market_permission=nom.market_permission,
        notes=tuple(notes),
    )


def _no_observation_reason(observation_reason: str) -> str:
    key = str(observation_reason or "").strip().upper()
    if key in _NO_OBS_REASONS:
        return _NO_OBS_REASONS[key]
    if "CAP" in key:
        return REASON_NO_OBSERVATION_CAP
    if "NO_DATA" in key or "MISSING" in key:
        return REASON_NO_OBSERVATION_NO_DATA
    if observation_reason:
        return str(observation_reason)
    return REASON_NO_OBSERVATION_MISSING_CAMERA


def evaluation_trading_session(nom: FrozenNomination) -> str:
    """Cash-session date a legal 5m bar must belong to.

    ``nom.session`` remains the freeze / scan provenance key. It is not
    rewritten. ``eligible_from`` is the chronology clock from
    ``episode_window``: a discovery after the provenance cash close is
    eligible at the next session open, and live bars belong to that date.
    An ``eligible_from`` earlier than the provenance date does not pull
    the guard backward. This does not read ``now``.
    """
    provenance = str(nom.session or "")[:10]
    eligible = parse_legal_ts(nom.eligible_from)
    if eligible is None:
        return provenance
    elig_day = as_vn(eligible).date().isoformat()
    if provenance and elig_day < provenance:
        return provenance
    return elig_day or provenance


def _legal_history(
    nom: FrozenNomination,
    history: Sequence[BarEvidence | Mapping[str, Any]],
) -> tuple[list[BarEvidence], list[str]]:
    """Drop unfinished / pre-eligible / illegal bars. Fail-closed notes."""
    notes: list[str] = []
    first = parse_legal_ts(nom.candidate_first_seen_ts)
    if first is None:
        notes.append(REASON_DATE_ONLY)
        return [], notes

    eligible = parse_legal_ts(nom.eligible_from)
    if eligible is None:
        # eligible_from must be a real clock, not date-only / midnight.
        notes.append(REASON_DATE_ONLY)
        return [], notes

    action_session = evaluation_trading_session(nom)
    out: list[BarEvidence] = []
    for raw in history:
        bar = raw if isinstance(raw, BarEvidence) else bar_evidence_from_mapping(raw)
        if bar.unfinished or not bar.completed:
            notes.append(REASON_UNFINISHED)
            continue
        if not bar.chronology_legal:
            notes.append(REASON_CHRONOLOGY_PRE_ELIGIBLE)
            continue
        if bar.asof < eligible or bar.bar_ts < eligible:
            notes.append(REASON_CHRONOLOGY_PRE_ELIGIBLE)
            continue
        if bar.asof < first:
            notes.append(REASON_CHRONOLOGY_PRE_ELIGIBLE)
            continue
        if action_session and as_vn(bar.asof).date().isoformat() != action_session:
            notes.append(REASON_SESSION_RESET)
            continue
        out.append(bar)
    out.sort(key=lambda b: b.asof)
    return out, notes


def _ref_usable(bar: BarEvidence, required: str) -> tuple[bool, str]:
    state = str(bar.reference_state or "")
    if state == REF_UNIT_MISMATCH:
        return False, REASON_REF_UNIT_MISMATCH
    if state in {"", REF_UNAVAILABLE} or bar.close_vs_ref is None:
        return False, REASON_REF_UNUSABLE
    if required and state != required and bar.reference_kind not in {required, None, ""}:
        return False, REASON_REF_UNUSABLE
    if required and bar.reference_kind and bar.reference_kind != required:
        return False, REASON_REF_UNUSABLE
    if bar.close_canonical is None or bar.reference_canonical is None:
        return False, REASON_REF_UNUSABLE
    return True, ""


def _conflict(bars: Sequence[BarEvidence]) -> bool:
    for bar in bars:
        if str(bar.published_evidence or "") == EV_CONFLICT:
            return True
        strengthen = str(bar.published_evidence or "") == EV_STRENGTHEN or str(
            bar.raw_evidence or ""
        ) == EV_STRENGTHEN
        weak = bar.pxv_weak or bar.has_sell or str(bar.published_evidence or "") == EV_WEAKEN
        if strengthen and weak:
            return True
    return False


def _weakening_conjunction(bar: BarEvidence, required: str) -> bool:
    """Price below frozen ref AND existing WEAKEN / SELL_EXPANSION / PXV_WEAK / FAM_SELL."""
    ok, _ = _ref_usable(bar, required)
    if not ok or bar.close_lt_ref is not True:
        return False
    return bool(
        bar.has_sell
        or bar.pxv_weak
        or str(bar.published_evidence or "") == EV_WEAKEN
        or str(bar.raw_evidence or "") == EV_WEAKEN
    )


def _pair_above_ref(a: BarEvidence, b: BarEvidence, required: str) -> bool:
    ok_a, _ = _ref_usable(a, required)
    ok_b, _ = _ref_usable(b, required)
    return ok_a and ok_b and a.close_ge_ref is True and b.close_ge_ref is True


def _gate_ok(bars: Sequence[BarEvidence]) -> bool:
    return all(bar.data_usable for bar in bars)


def _market_ok(nom: FrozenNomination) -> bool:
    return str(nom.market_permission or "").strip() == MARKET_PERMISSION_OK


def _in_pull_zone(bar: BarEvidence) -> bool:
    """Touched or under the frozen EMA9 area. Far-above bars are not a pull."""
    if bar.close_vs_ref_pct is None:
        return bar.close_lt_ref is True
    return float(bar.close_vs_ref_pct) <= PULL_ZONE_MAX_PCT


def _pull_supply_bar(bar: BarEvidence) -> bool:
    """Price in the EMA9 area while classified volume is CONTRACTION.

    NORMAL is not supply evidence. A missing expansion classification is not
    supply evidence. Sell on that bar disqualifies it.
    """
    if not _in_pull_zone(bar) or bar.has_sell or not bar.data_usable:
        return False
    return str(bar.volume_expansion_state or "") == PULL_SUPPLY_VOLUME


def _pull_ready(pair: Sequence[BarEvidence], history: Sequence[BarEvidence]) -> tuple[bool, str]:
    if any(bar.has_sell for bar in pair):
        return False, REASON_PULL_FAM_SELL
    if not all(bar.quiet_volume for bar in pair):
        return False, REASON_PULL_VOLUME_NOT_QUIET
    if not _gate_ok(pair):
        return False, REASON_DATA_UNUSABLE
    if not any(_pull_supply_bar(bar) for bar in history):
        return False, REASON_PULL_NO_QUIET_SUPPLY
    return True, REASON_PULL_BUY_READY


def _manh_break_ready(pair: Sequence[BarEvidence]) -> tuple[bool, str]:
    a, b = pair
    if any(bar.pxv_weak for bar in pair):
        return False, REASON_MANH_PXV_WEAK
    if any(bar.has_sell for bar in pair):
        return False, REASON_MANH_FAM_SELL
    if str(b.published_evidence or "") != EV_STRENGTHEN:
        return False, REASON_MANH_PRICE_NO_STRENGTHEN
    if not _gate_ok(pair):
        return False, REASON_DATA_UNUSABLE
    return True, REASON_MANH_BUY_READY


def _classify_wait(
    nom: FrozenNomination,
    legal: Sequence[BarEvidence],
    *,
    notes: Sequence[str],
) -> ActionResult:
    required = nom.required_ref
    last = legal[-1]
    ok, ref_why = _ref_usable(last, required)
    if not ok:
        return _result(nom, STATE_WAIT, ref_why, bars=legal, notes=notes)
    if not last.data_usable:
        return _result(nom, STATE_WAIT, REASON_DATA_UNUSABLE, bars=legal, notes=notes)
    if not _market_ok(nom):
        return _result(nom, STATE_WAIT, REASON_MARKET_NOT_OK, bars=legal, notes=notes)
    if last.close_lt_ref is True:
        reason = REASON_PULL_BELOW_REF if nom.route == "PULL" else REASON_MANH_STRENGTHEN_BELOW
        if nom.route in {"MANH", "BREAK"} and str(last.published_evidence or "") == EV_STRENGTHEN:
            reason = REASON_MANH_STRENGTHEN_BELOW
        elif nom.route in {"MANH", "BREAK"} and last.close_ge_ref is not True:
            reason = REASON_MANH_STRENGTHEN_BELOW
        else:
            reason = REASON_PULL_BELOW_REF
        return _result(nom, STATE_WAIT, reason, bars=legal, notes=notes)
    if nom.route == "PULL":
        if len(legal) < 2:
            return _result(nom, STATE_WAIT, REASON_PULL_SINGLE_BAR, bars=legal, notes=notes)
        return _result(nom, STATE_WAIT, REASON_WAIT, bars=legal, notes=notes)
    if nom.route in {"MANH", "BREAK"}:
        if last.close_ge_ref is True and str(last.published_evidence or "") != EV_STRENGTHEN:
            return _result(nom, STATE_WAIT, REASON_MANH_PRICE_NO_STRENGTHEN, bars=legal, notes=notes)
        if str(last.published_evidence or "") == EV_STRENGTHEN and last.close_ge_ref is not True:
            return _result(nom, STATE_WAIT, REASON_MANH_STRENGTHEN_BELOW, bars=legal, notes=notes)
        return _result(nom, STATE_WAIT, REASON_WAIT, bars=legal, notes=notes)
    return _result(nom, STATE_WAIT, REASON_WAIT, bars=legal, notes=notes)


def _try_buy_ready(
    nom: FrozenNomination,
    legal: Sequence[BarEvidence],
) -> tuple[bool, str]:
    if len(legal) < 2:
        return False, REASON_PULL_SINGLE_BAR if nom.route == "PULL" else REASON_WAIT
    if not _market_ok(nom):
        return False, REASON_MARKET_NOT_OK
    pair = legal[-2:]
    required = nom.required_ref
    if not _pair_above_ref(pair[0], pair[1], required):
        return False, REASON_WAIT
    if _conflict(pair):
        return False, REASON_CONFLICT
    if nom.route == "PULL":
        return _pull_ready(pair, legal)
    if nom.route in {"MANH", "BREAK"}:
        return _manh_break_ready(pair)
    return False, REASON_UNKNOWN_SETUP


def _moderate_volume(bar: BarEvidence) -> bool:
    """Existing expansion ratio, strictly between the median and the 2.0× spike."""
    ratio = bar.volume_expansion_ratio
    if ratio is None:
        return False
    return EARLY_MODERATE_VOLUME_MIN < float(ratio) < float(RESEARCH_DEFAULT_EXPANSION_X)


def _early_price_progress(bar: BarEvidence) -> bool:
    """Slightly above the frozen EMA9. Flat, below, or extended is not EARLY."""
    if bar.close_vs_ref is None or bar.close_vs_ref_pct is None:
        return False
    pct = float(bar.close_vs_ref_pct)
    return float(bar.close_vs_ref) > 0.0 and 0.0 < pct <= EARLY_MAX_PROGRESS_PCT


def _try_early_ready(
    nom: FrozenNomination,
    legal: Sequence[BarEvidence],
) -> tuple[bool, str]:
    if len(legal) < 2:
        return False, REASON_EARLY_SINGLE_BAR
    if not _market_ok(nom):
        return False, REASON_MARKET_NOT_OK
    pair = legal[-2:]
    if not _gate_ok(pair):
        return False, REASON_DATA_UNUSABLE
    if any(bar.has_sell for bar in pair):
        return False, REASON_EARLY_FAM_SELL
    if not all(_early_price_progress(bar) for bar in pair):
        return False, REASON_EARLY_PRICE
    if not all(_moderate_volume(bar) for bar in pair):
        return False, REASON_EARLY_VOLUME
    return True, REASON_EARLY_BUY_READY


def _is_retrospective(legal: Sequence[BarEvidence], overlay_truth_class: str) -> bool:
    return overlay_truth_class == OVERLAY_TRUTH_RETROSPECTIVE or any(
        bar.overlay_truth_class == OVERLAY_TRUTH_RETROSPECTIVE or bar.overlay_applied for bar in legal
    )


def _evaluate_early(
    nom: FrozenNomination,
    legal: Sequence[BarEvidence],
    notes: Sequence[str],
    *,
    overlay_truth_class: str,
) -> ActionResult:
    """Controlled progress vs frozen EMA9 plus moderate volume. Never STRENGTHEN."""
    if not legal:
        if nom.ema9_at_first_seen is None:
            return _result(nom, STATE_NOMINATED, REASON_EARLY_NO_FROZEN_REF, notes=notes)
        return _result(nom, STATE_NOMINATED, REASON_NOMINATED_NO_BARS, notes=notes)

    ok, ref_why = _ref_usable(legal[-1], REF_EMA9)
    if not ok:
        reason = REASON_EARLY_NO_FROZEN_REF if ref_why == REASON_REF_UNUSABLE else ref_why
        return _result(nom, STATE_WAIT, reason, bars=legal, notes=notes)

    ready, why = _try_early_ready(nom, legal)
    if ready and _is_retrospective(legal, overlay_truth_class):
        return _result(
            nom,
            STATE_WAIT,
            REASON_RETROSPECTIVE,
            bars=legal,
            notes=tuple(notes) + (REASON_RETROSPECTIVE,),
        )
    if ready:
        return _result(nom, STATE_BUY_READY, why, bars=legal, notes=notes)
    if why == REASON_WAIT:
        return _result(nom, STATE_WAIT, REASON_EARLY_EVIDENCE_ONLY, bars=legal, notes=notes)
    return _result(nom, STATE_WAIT, why, bars=legal, notes=notes)


def evaluate_shadow_action(
    nomination: FrozenNomination | Mapping[str, Any],
    legal_completed_bars: Sequence[BarEvidence | Mapping[str, Any]],
    *,
    now: datetime | None = None,
    overlay_truth_class: str = OVERLAY_TRUTH_CANONICAL,
    observed: bool = True,
    observation_reason: str = "",
    prior_action_state: str | None = None,
    prior_session: str | None = None,
) -> ActionResult:
    """Pure state function. BUY_READY is SHADOW research only."""
    nom = nomination if isinstance(nomination, FrozenNomination) else nomination_from_mapping(nomination)
    _ = now  # reserved: caller already filtered unfinished bars vs now

    if prior_session and nom.session and str(prior_session) != str(nom.session):
        prior_action_state = STATE_NOMINATED

    if not observed:
        return _result(
            nom,
            STATE_NO_OBSERVATION,
            _no_observation_reason(observation_reason),
            observed=False,
            notes=(REASON_SESSION_RESET,) if prior_session and prior_session != nom.session else (),
        )

    legal, notes = _legal_history(nom, legal_completed_bars)
    if REASON_DATE_ONLY in notes:
        return _result(nom, STATE_NOMINATED, REASON_DATE_ONLY, notes=notes)

    if nom.route == "EARLY":
        return _evaluate_early(nom, legal, notes, overlay_truth_class=overlay_truth_class)

    if nom.route == "UNKNOWN":
        if not legal:
            return _result(nom, STATE_NOMINATED, REASON_UNKNOWN_SETUP, notes=notes)
        return _result(nom, STATE_WAIT, REASON_UNKNOWN_SETUP, bars=legal, notes=notes)

    if not legal:
        reason = REASON_NOMINATED_NO_BARS
        if REASON_UNFINISHED in notes and REASON_CHRONOLOGY_PRE_ELIGIBLE not in notes:
            reason = REASON_UNFINISHED
        elif REASON_CHRONOLOGY_PRE_ELIGIBLE in notes:
            reason = REASON_CHRONOLOGY_PRE_ELIGIBLE
        return _result(nom, STATE_NOMINATED, reason, notes=notes)

    # Walk bar-by-bar so WEAKENED cannot skip WAIT on the way to BUY_READY.
    # First-slice recovery: a WEAKENED touch in this evaluation can only
    # recover as far as WAIT; BUY_READY requires a later evaluation.
    state = STATE_NOMINATED
    touched_weakened = False
    if prior_action_state == STATE_WEAKENED and (not prior_session or prior_session == nom.session):
        state = STATE_WEAKENED
        touched_weakened = True
    reason = REASON_NOMINATED_NO_BARS
    prefix: list[BarEvidence] = []
    retrospective = overlay_truth_class == OVERLAY_TRUTH_RETROSPECTIVE or any(
        bar.overlay_truth_class == OVERLAY_TRUTH_RETROSPECTIVE or bar.overlay_applied for bar in legal
    )

    for bar in legal:
        prefix.append(bar)
        required = nom.required_ref
        if _weakening_conjunction(bar, required):
            state = STATE_WEAKENED
            reason = REASON_WEAKENING
            touched_weakened = True
            continue
        if _conflict(prefix[-2:] if len(prefix) >= 2 else prefix):
            if state == STATE_WEAKENED:
                state = STATE_WAIT
                reason = REASON_WEAKENED_WAIT
            else:
                state = STATE_WAIT
                reason = REASON_CONFLICT
            continue

        ready, ready_why = _try_buy_ready(nom, prefix)
        if ready:
            if state == STATE_WEAKENED or touched_weakened:
                state = STATE_WAIT
                reason = REASON_WEAKENED_WAIT
                continue
            if retrospective:
                state = STATE_WAIT
                reason = REASON_RETROSPECTIVE
                notes = list(notes) + [REASON_RETROSPECTIVE]
                continue
            state = STATE_BUY_READY
            reason = ready_why
            continue

        # Not ready this bar.
        if state == STATE_WEAKENED:
            state = STATE_WAIT
            reason = REASON_WEAKENED_WAIT
            continue
        if state == STATE_BUY_READY:
            # Lost the 2-bar hold / confirm → back to WAIT (not WEAKENED unless conjunction).
            state = STATE_WAIT
            reason = ready_why or REASON_WAIT
            continue
        state = STATE_WAIT
        reason = ready_why or REASON_WAIT

    if state == STATE_BUY_READY:
        return _result(nom, STATE_BUY_READY, reason, bars=legal, notes=notes)
    if state == STATE_WEAKENED:
        return _result(nom, STATE_WEAKENED, REASON_WEAKENING, bars=legal, notes=notes)
    if state == STATE_WAIT:
        # Prefer a more specific WAIT reason from the latest bars when the walk
        # stored a generic incomplete-pair token.
        if reason in {REASON_WAIT, REASON_PULL_SINGLE_BAR, REASON_WEAKENED_WAIT, REASON_RETROSPECTIVE}:
            specific = _classify_wait(nom, legal, notes=notes)
            if reason in {REASON_WEAKENED_WAIT, REASON_RETROSPECTIVE}:
                return _result(nom, STATE_WAIT, reason, bars=legal, notes=specific.notes)
            if specific.action_reason != REASON_WAIT:
                return specific
        return _result(nom, STATE_WAIT, reason, bars=legal, notes=notes)
    return _result(nom, STATE_NOMINATED, reason, bars=legal, notes=notes)


def session_of(value: datetime | date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return as_vn(value).date().isoformat()
    return str(value)[:10]
