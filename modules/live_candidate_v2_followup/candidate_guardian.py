"""V2 Candidate Guardian — research quality classifier for Follow-up Watch.

Inspired by Position Guardian factors (EMA9/MA20/OBV) but NOT a mechanical
copy of held-position SELL signals. Distinguishes healthy pullbacks from
confirmed trend breaks. Market Real < 6 never rejects by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

from modules.live_candidate_v2_action.live_universe import ACTIONABLE_LIVE_SETUPS
from modules.live_candidate_v2_nomination.contract import EXCLUDED_SETUPS

QUALITY_STRONGER = "STRONGER"
QUALITY_STABLE = "STABLE"
QUALITY_WEAKENING = "WEAKENING"
QUALITY_REJECTED = "REJECTED"

REASON_HEALTHY_PULLBACK = "HEALTHY_PULLBACK_STABLE"
REASON_TREND_IMPROVING = "TREND_AND_FLOW_IMPROVING"
REASON_CONFIRMED_BREAK = "CONFIRMED_TREND_BREAK"
REASON_SETUP_COLLAPSE = "SETUP_COLLAPSED_EXCLUDED"
REASON_FLOW_DETERIORATING = "FLOW_OR_RS_DETERIORATING"
REASON_NEUTRAL_STABLE = "NEUTRAL_STABLE"
REASON_MISSING_SCAN = "MISSING_SCAN_ROW_STABLE"

# Soft pull band vs EMA9 (percent). Inside this with trend intact = healthy pull.
HEALTHY_PULL_MAX_PCT_BELOW_EMA9 = 3.0
# Consecutive WEAKENING sessions before confirmed REJECTED.
WEAKENING_STREAK_TO_REJECT = 2


def _num(row: Mapping[str, Any] | None, *keys: str) -> float | None:
    if not row:
        return None
    for key in keys:
        if key not in row and not hasattr(row, "get"):
            continue
        try:
            raw = row.get(key) if hasattr(row, "get") else None
        except Exception:
            raw = None
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value == value:
            return value
    return None


def _text(row: Mapping[str, Any] | None, *keys: str) -> str:
    if not row:
        return ""
    for key in keys:
        if hasattr(row, "get"):
            raw = row.get(key)
        else:
            continue
        text = str(raw or "").strip()
        if text and text.lower() not in {"nan", "none", "nat"}:
            return text
    return ""


def _setup(row: Mapping[str, Any] | None) -> str:
    return _text(row, "group", "setup")


@dataclass(frozen=True)
class CandidateQuality:
    label: str
    reason: str
    score: int = 0
    healthy_pullback: bool = False
    block_buy_ready: bool = False
    reject: bool = False
    factors: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _obv_negative(row: Mapping[str, Any] | None) -> bool:
    status = _text(row, "obv_status", "obv").upper()
    if "DOWN" in status or "NEGATIVE" in status or "GÃY" in status or "GAY" in status:
        return True
    obv = _num(row, "obv")
    obv_ema = _num(row, "obv_ema9")
    if obv is not None and obv_ema is not None and obv < obv_ema:
        return True
    return False


def _obv_positive(row: Mapping[str, Any] | None) -> bool:
    status = _text(row, "obv_status", "obv").upper()
    if "UP" in status or "POSITIVE" in status or "TÍCH" in status:
        return True
    obv = _num(row, "obv")
    obv_ema = _num(row, "obv_ema9")
    if obv is not None and obv_ema is not None and obv >= obv_ema:
        return True
    return False


def _rs_improving(row: Mapping[str, Any] | None, prior: Mapping[str, Any] | None) -> bool:
    rs5 = _num(row, "rs5", "RS5")
    rs10 = _num(row, "rs10", "RS10")
    prev5 = _num(prior, "rs5", "RS5") if prior else None
    prev10 = _num(prior, "rs10", "RS10") if prior else None
    if rs5 is None and rs10 is None:
        return False
    better = False
    if rs5 is not None and prev5 is not None and rs5 > prev5:
        better = True
    if rs10 is not None and prev10 is not None and rs10 > prev10:
        better = True
    # Absolute constructive RS without prior.
    if prior is None and ((rs5 is not None and rs5 >= 0) or (rs10 is not None and rs10 >= 0)):
        better = True
    return better


def _rs_deteriorating(row: Mapping[str, Any] | None, prior: Mapping[str, Any] | None) -> bool:
    rs5 = _num(row, "rs5", "RS5")
    rs10 = _num(row, "rs10", "RS10")
    prev5 = _num(prior, "rs5", "RS5") if prior else None
    prev10 = _num(prior, "rs10", "RS10") if prior else None
    worse = 0
    if rs5 is not None and prev5 is not None and rs5 < prev5 - 0.5:
        worse += 1
    if rs10 is not None and prev10 is not None and rs10 < prev10 - 0.5:
        worse += 1
    if prior is None and rs5 is not None and rs10 is not None and rs5 < -2 and rs10 < -2:
        worse += 2
    return worse >= 2


def _setup_improving(current: str, original: str) -> bool:
    rank = {
        "": 0,
        "THEO DÕI": 0,
        "TÍCH LŨY": 1,
        "MUA EARLY": 2,
        "PULL VỪA": 3,
        "PULL ĐẸP": 4,
        "MUA BREAK": 5,
        "CP MẠNH": 6,
    }
    return rank.get(current, 0) > rank.get(original, 0)


def classify_candidate_quality(
    scan_row: Mapping[str, Any] | None,
    *,
    original_setup: str = "",
    prior_snapshot: Mapping[str, Any] | None = None,
    weakening_streak: int = 0,
    market_real: object = None,
) -> CandidateQuality:
    """Classify ACTIVE candidate quality for the current session.

    ``market_real`` is recorded as context only — never forces REJECTED.
    """
    _ = market_real  # intentional: Market First does not reject here
    if scan_row is None:
        return CandidateQuality(
            label=QUALITY_STABLE,
            reason=REASON_MISSING_SCAN,
            score=0,
            factors={"scan": "missing"},
        )

    price = _num(scan_row, "price", "Giá")
    ema9 = _num(scan_row, "ema9")
    ma20 = _num(scan_row, "ma20", "sma20")
    vol_ratio = _num(scan_row, "volume_ratio", "volume_ratio20", "vol_ratio")
    setup = _setup(scan_row)
    factors = {
        "price": price,
        "ema9": ema9,
        "ma20": ma20,
        "volume_ratio": vol_ratio,
        "setup": setup,
        "rs5": _num(scan_row, "rs5", "RS5"),
        "rs10": _num(scan_row, "rs10", "RS10"),
        "obv_negative": _obv_negative(scan_row),
        "obv_positive": _obv_positive(scan_row),
        "weakening_streak": int(weakening_streak or 0),
    }

    # --- Confirmed structural rejection ---
    if setup in EXCLUDED_SETUPS and original_setup in ACTIONABLE_LIVE_SETUPS:
        return CandidateQuality(
            label=QUALITY_REJECTED,
            reason=REASON_SETUP_COLLAPSE,
            score=-80,
            reject=True,
            block_buy_ready=True,
            factors=factors,
        )

    trend_broken = (
        price is not None
        and ema9 is not None
        and ma20 is not None
        and price < ema9
        and ema9 < ma20
    )
    flow_confirms_break = _obv_negative(scan_row) or (
        vol_ratio is not None and vol_ratio >= 1.2 and price is not None and ema9 is not None and price < ema9
    )
    if trend_broken and flow_confirms_break:
        return CandidateQuality(
            label=QUALITY_REJECTED,
            reason=REASON_CONFIRMED_BREAK,
            score=-70,
            reject=True,
            block_buy_ready=True,
            factors=factors,
        )
    if int(weakening_streak or 0) >= WEAKENING_STREAK_TO_REJECT and trend_broken:
        return CandidateQuality(
            label=QUALITY_REJECTED,
            reason=REASON_CONFIRMED_BREAK,
            score=-60,
            reject=True,
            block_buy_ready=True,
            factors={**factors, "streak_reject": True},
        )

    # --- Healthy pullback: price under EMA9 but EMA9 still ≥ MA20 ---
    below_ema = price is not None and ema9 is not None and price < ema9
    trend_intact = ema9 is not None and ma20 is not None and ema9 >= ma20
    pct_below = None
    if below_ema and ema9:
        pct_below = (ema9 - price) / ema9 * 100.0  # type: ignore[operator]
    healthy_pull = bool(
        below_ema
        and trend_intact
        and not _obv_negative(scan_row)
        and (
            pct_below is None
            or pct_below <= HEALTHY_PULL_MAX_PCT_BELOW_EMA9 + 1e-9
        )
        and (setup in ACTIONABLE_LIVE_SETUPS or setup in {"", "TÍCH LŨY", "MUA EARLY"})
    )
    factors["pct_below_ema9"] = pct_below
    factors["healthy_pullback"] = healthy_pull

    # --- STRONGER ---
    above_stack = (
        price is not None
        and ema9 is not None
        and ma20 is not None
        and price >= ema9
        and ema9 >= ma20
    )
    stronger = above_stack and (
        _obv_positive(scan_row) or _rs_improving(scan_row, prior_snapshot) or _setup_improving(setup, original_setup)
    )
    if stronger and not below_ema:
        return CandidateQuality(
            label=QUALITY_STRONGER,
            reason=REASON_TREND_IMPROVING,
            score=40,
            block_buy_ready=False,
            factors=factors,
        )

    # --- WEAKENING (not yet confirmed reject) ---
    weakening = False
    if trend_broken and not flow_confirms_break:
        weakening = True
    if below_ema and not trend_intact and not healthy_pull:
        weakening = True
    if _rs_deteriorating(scan_row, prior_snapshot) and below_ema:
        weakening = True
    if weakening:
        return CandidateQuality(
            label=QUALITY_WEAKENING,
            reason=REASON_FLOW_DETERIORATING,
            score=-30,
            block_buy_ready=True,
            factors=factors,
        )

    if healthy_pull:
        return CandidateQuality(
            label=QUALITY_STABLE,
            reason=REASON_HEALTHY_PULLBACK,
            score=10,
            healthy_pullback=True,
            block_buy_ready=False,
            factors=factors,
        )

    return CandidateQuality(
        label=QUALITY_STABLE,
        reason=REASON_NEUTRAL_STABLE,
        score=0,
        block_buy_ready=False,
        factors=factors,
    )


def snapshot_from_scan(scan_row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not scan_row:
        return {}
    return {
        "price": _num(scan_row, "price", "Giá"),
        "ema9": _num(scan_row, "ema9"),
        "ma20": _num(scan_row, "ma20", "sma20"),
        "rs5": _num(scan_row, "rs5", "RS5"),
        "rs10": _num(scan_row, "rs10", "RS10"),
        "setup": _setup(scan_row),
        "obv_status": _text(scan_row, "obv_status"),
        "volume_ratio": _num(scan_row, "volume_ratio", "volume_ratio20", "vol_ratio"),
    }


__all__ = [
    "HEALTHY_PULL_MAX_PCT_BELOW_EMA9",
    "QUALITY_REJECTED",
    "QUALITY_STABLE",
    "QUALITY_STRONGER",
    "QUALITY_WEAKENING",
    "REASON_CONFIRMED_BREAK",
    "REASON_HEALTHY_PULLBACK",
    "REASON_SETUP_COLLAPSE",
    "REASON_TREND_IMPROVING",
    "WEAKENING_STREAK_TO_REJECT",
    "CandidateQuality",
    "classify_candidate_quality",
    "snapshot_from_scan",
]
