"""Exact Brain A nomination predicate.

PRIMARY (existing classify_group labels):
  PULL ĐẸP | PULL VỪA | MUA BREAK | CP MẠNH

SECONDARY:
  MUA EARLY only when existing InEarlyLab OR existing TEST EARLY action.

TEST EARLY action = app.py buy_recommendation branch:
  group == MUA EARLY and total_score >= 3 and obv_status == 🟢
  and abs(dist_from_ema9_pct) <= 2.5

Do NOT nominate:
  THEO DÕI, TÍCH LŨY, bare MUA EARLY, GÀ TĂNG TỐC (reserved),
  WATCHLIST alone, WinProb/top-N alone, BUY ELITE / MUA NHỎ alone,
  WATCHLIST - MARKET YẾU (market_real < 6), LOẠI - TRỤC XẤU (hard_bad).

BUY ELITE / MUA NHỎ never define nomination.
No new score. No GROUP_RANK. No P×V.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from modules.live_candidate_v2_nomination.contract import (
    ELITE_BUY_GRADES,
    EXCLUDED_SETUPS,
    HARD_BAD_CONCLUSION,
    MARKET_PERMISSION_OK,
    MARKET_PERMISSION_WEAK,
    PRIMARY_SETUPS,
    QUALIFIED_BY_EARLY_LAB,
    QUALIFIED_BY_PRIMARY,
    QUALIFIED_BY_TEST_EARLY,
    REJECT_BARE_MUA_EARLY,
    REJECT_ELITE_GRADE_ALONE,
    REJECT_HARD_BAD,
    REJECT_MARKET_WEAK,
    REJECT_MISSING_SYMBOL,
    REJECT_NOT_IN_UNIVERSE,
    REJECT_SETUP_EXCLUDED,
    REJECT_SETUP_RESERVED,
    REJECT_WATCHLIST_ALONE,
    REJECT_WINPROB_ALONE,
    RESERVED_SETUPS,
    SECONDARY_SETUP,
    WATCHLIST_CONCLUSIONS,
)

# Copied from app.py buy_recommendation TEST EARLY branch. Do not retune.
TEST_EARLY_MIN_SCORE = 3
TEST_EARLY_MAX_ABS_DIST = 2.5
OBV_OK = "🟢"
HARD_BAD_TOKENS = ("OBV gãy", "Giá dưới EMA9")
MARKET_WEAK_THRESHOLD = 6  # existing buy_recommendation / Elite mr < 6


@dataclass(frozen=True)
class NominationDecision:
    eligible: bool
    reject_reason: str = ""
    qualified_by: str = ""
    nomination_reason: str = ""
    setup: str = ""
    in_early_lab: bool = False
    elite_buy_grade: str = ""
    market_permission: str = ""


def _text(value: object) -> str:
    s = str(value or "").strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return ""
    return s


def as_number(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def setup_of(row: Mapping[str, Any]) -> str:
    return _text(row.get("group") or row.get("setup") or row.get("NHÓM"))


def symbol_of(row: Mapping[str, Any]) -> str:
    return _text(row.get("symbol") or row.get("MÃ")).upper()


def conclusion_of(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("elite_buy_grade")
        or row.get("KẾT LUẬN")
        or row.get("conclusion")
    )


def elite_buy_grade_of(row: Mapping[str, Any]) -> str:
    raw = conclusion_of(row)
    return raw if raw in ELITE_BUY_GRADES else ""


def in_early_lab(row: Mapping[str, Any], early_lab_symbols: Iterable[str] | None = None) -> bool:
    """Consume existing InEarlyLab / early-lab membership. Do not recompute the lab."""
    if "InEarlyLab" in row:
        val = row.get("InEarlyLab")
        if isinstance(val, str):
            return val.strip().lower() in {"1", "true", "yes", "✅"}
        return bool(val)
    if early_lab_symbols is None:
        return False
    lab = {str(s).strip().upper() for s in early_lab_symbols}
    return symbol_of(row) in lab


def is_hard_bad(row: Mapping[str, Any]) -> bool:
    """Existing Elite/buy_recommendation hard_bad: OBV gãy or Giá dưới EMA9."""
    conclusion = _text(row.get("KẾT LUẬN") or row.get("conclusion"))
    if conclusion == HARD_BAD_CONCLUSION:
        return True
    warning = _text(row.get("warning"))
    return any(tok in warning for tok in HARD_BAD_TOKENS)


def is_test_early_action(row: Mapping[str, Any]) -> bool:
    """Existing buy_recommendation TEST EARLY branch, after market/hard_bad."""
    if setup_of(row) != SECONDARY_SETUP:
        return False
    score = as_number(row.get("total_score") if "total_score" in row else row.get("score"))
    dist = as_number(row.get("dist_from_ema9_pct"))
    obv_ok = _text(row.get("obv_status")) == OBV_OK
    if score is None or score < TEST_EARLY_MIN_SCORE:
        return False
    if not obv_ok:
        return False
    if dist is None or abs(dist) > TEST_EARLY_MAX_ABS_DIST:
        return False
    return True


def market_permission(market_real: object) -> str:
    mr = as_number(market_real)
    if mr is None:
        return ""
    if mr < MARKET_WEAK_THRESHOLD:
        return MARKET_PERMISSION_WEAK
    return MARKET_PERMISSION_OK


def _alone_reason(row: Mapping[str, Any]) -> str:
    if elite_buy_grade_of(row) in ELITE_BUY_GRADES:
        return REJECT_ELITE_GRADE_ALONE
    conclusion = conclusion_of(row)
    if conclusion in WATCHLIST_CONCLUSIONS or conclusion.startswith("WATCHLIST"):
        return REJECT_WATCHLIST_ALONE
    if as_number(row.get("WinProb") if "WinProb" in row else row.get("winprob")) is not None:
        return REJECT_WINPROB_ALONE
    return REJECT_NOT_IN_UNIVERSE


def evaluate_nomination(
    row: Mapping[str, Any],
    *,
    market_real: object,
    early_lab_symbols: Iterable[str] | None = None,
) -> NominationDecision:
    symbol = symbol_of(row)
    setup = setup_of(row)
    lab = in_early_lab(row, early_lab_symbols)
    grade = elite_buy_grade_of(row)
    perm = market_permission(market_real)

    if not symbol:
        return NominationDecision(False, REJECT_MISSING_SYMBOL, setup=setup, elite_buy_grade=grade)

    if perm == MARKET_PERMISSION_WEAK:
        return NominationDecision(
            False,
            REJECT_MARKET_WEAK,
            setup=setup,
            in_early_lab=lab,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    if is_hard_bad(row):
        return NominationDecision(
            False,
            REJECT_HARD_BAD,
            setup=setup,
            in_early_lab=lab,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    if setup in RESERVED_SETUPS:
        return NominationDecision(
            False,
            REJECT_SETUP_RESERVED,
            setup=setup,
            in_early_lab=lab,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    if setup in EXCLUDED_SETUPS:
        return NominationDecision(
            False,
            REJECT_SETUP_EXCLUDED,
            setup=setup,
            in_early_lab=lab,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    if setup in PRIMARY_SETUPS:
        return NominationDecision(
            True,
            qualified_by=QUALIFIED_BY_PRIMARY,
            nomination_reason=f"PRIMARY setup {setup}",
            setup=setup,
            in_early_lab=lab,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    if setup == SECONDARY_SETUP:
        test_early = is_test_early_action(row)
        if lab or test_early:
            tags = []
            if lab:
                tags.append(QUALIFIED_BY_EARLY_LAB)
            if test_early:
                tags.append(QUALIFIED_BY_TEST_EARLY)
            qualified = "|".join(tags)
            return NominationDecision(
                True,
                qualified_by=qualified,
                nomination_reason=f"SECONDARY MUA EARLY qualified by {qualified}",
                setup=setup,
                in_early_lab=lab,
                elite_buy_grade=grade,
                market_permission=perm,
            )
        return NominationDecision(
            False,
            REJECT_BARE_MUA_EARLY,
            setup=setup,
            in_early_lab=False,
            elite_buy_grade=grade,
            market_permission=perm,
        )

    return NominationDecision(
        False,
        _alone_reason(row),
        setup=setup,
        in_early_lab=lab,
        elite_buy_grade=grade,
        market_permission=perm,
    )
