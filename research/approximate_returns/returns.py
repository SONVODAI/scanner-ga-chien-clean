"""T+n returns from the reference store. Frozen nomination prices stay untouched."""

from __future__ import annotations

import math

from research.approximate_returns.contract import (
    COHORT_BRAIN,
    COHORT_OVERLAP,
    COHORT_SWEET,
    COHORT_UNATTRIBUTED,
    HORIZONS,
    PRICE_BASIS,
    REVIEW_STATUSES,
    SOURCE,
    SOURCE_BRAIN,
    SOURCE_SWEET,
    SOURCE_UNATTRIBUTED,
    STATUS_AVAILABLE,
    STATUS_DISCONTINUITY,
    STATUS_NOT_YET,
    STATUS_T0_MISSING,
    STATUS_TARGET_MISSING,
    STATUS_TRUNCATED,
    TRUNCATION_CLOCK,
)
from research.approximate_returns.reference import _minutes, index_store


def evaluate_rows(board_rows: list[dict], store: dict) -> list[dict]:
    """Copy each frozen row and attach approximate horizons. Inputs are not edited."""
    lookup = index_store(store)
    copied = [_public_row(row) for row in board_rows]
    _assign_cohorts(copied)
    evaluated = []
    for row in copied:
        symbol = row["symbol"]
        origin = row["t0_date"]
        reference = lookup["prices"].get((symbol, origin))
        clock = lookup["clocks"].get((symbol, origin))
        frozen = _positive(row.get("frozen_t0_price"))
        gap = None
        if frozen is not None and reference is not None:
            gap = round((reference / frozen - 1) * 100, 6)
        horizons = {}
        position = lookup["index"].get(origin)
        for step in HORIZONS:
            horizons[f"T+{step}"] = _horizon(
                symbol,
                origin,
                position,
                step,
                reference,
                clock,
                lookup,
            )
        evaluated.append({
            **row,
            "reference_t0_price": reference,
            "reference_t0_clock": clock,
            "t0_gap_pct": gap,
            "t0_price_used_as_denominator": False,
            "price_basis": PRICE_BASIS,
            "reference_source": SOURCE,
            "horizons": horizons,
        })
    return evaluated


def _horizon(symbol: str, origin: str, position: int | None, step: int, reference, clock, lookup: dict) -> dict:
    label_target = None
    if position is None or reference is None or not clock:
        return _cell(STATUS_T0_MISSING, None, None, None)
    if position + step >= len(lookup["sessions"]):
        return _cell(STATUS_NOT_YET, None, None, None)
    target = lookup["sessions"][position + step]
    label_target = target
    later = lookup["prices"].get((symbol, target))
    later_clock = lookup["clocks"].get((symbol, target))
    if later is None or not later_clock:
        return _cell(STATUS_TARGET_MISSING, label_target, None, None)
    change = round((later / reference - 1) * 100, 6)
    truncated = _minutes(clock) < _minutes(TRUNCATION_CLOCK) or _minutes(later_clock) < _minutes(TRUNCATION_CLOCK)
    if truncated:
        return _cell(STATUS_TRUNCATED, label_target, later, change)
    for offset in range(1, step + 1):
        if (symbol, lookup["sessions"][position + offset]) in lookup["flagged"]:
            return _cell(STATUS_DISCONTINUITY, label_target, later, change)
    return _cell(STATUS_AVAILABLE, label_target, later, change)


def _cell(status: str, target, price, change) -> dict:
    return {
        "status": status,
        "target_session": target,
        "reference_price": price,
        "return_pct": change if status in {STATUS_AVAILABLE, *REVIEW_STATUSES} else None,
        "included_in_primary": status == STATUS_AVAILABLE,
    }


def _assign_cohorts(rows: list[dict]) -> None:
    groups: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        groups.setdefault((row["symbol"], row["t0_date"]), set()).add(row["source"])
    for row in rows:
        sources = groups[(row["symbol"], row["t0_date"])]
        if SOURCE_BRAIN in sources and SOURCE_SWEET in sources:
            row["comparison_cohort"] = COHORT_OVERLAP
        elif row["source"] == SOURCE_BRAIN:
            row["comparison_cohort"] = COHORT_BRAIN
        elif row["source"] == SOURCE_SWEET:
            row["comparison_cohort"] = COHORT_SWEET
        elif row["source"] == SOURCE_UNATTRIBUTED:
            row["comparison_cohort"] = COHORT_UNATTRIBUTED
        else:
            row["comparison_cohort"] = row["source"] or "unknown"


def _public_row(row: dict) -> dict:
    return {
        "row_id": str(row.get("row_id") or ""),
        "symbol": str(row.get("symbol") or "").strip().upper(),
        "t0_date": str(row.get("t0_date") or "")[:10],
        "source": str(row.get("source") or ""),
        "ledger_cohort": row.get("cohort"),
        "action_state": row.get("action_state"),
        "lifecycle": row.get("lifecycle"),
        "episode_end": row.get("episode_end"),
        "quality_status": row.get("quality_status"),
        "frozen_t0_price": _positive(row.get("t0_price")),
        "frozen_t0_provenance": row.get("t0_price_provenance"),
        "market_real": _finite(row.get("market_real")),
        "market_real_provenance": row.get("market_real_provenance") or None,
    }


def _positive(value):
    number = _finite(value)
    if number is None or number <= 0:
        return None
    if float(number).is_integer():
        return int(number)
    return number


def _finite(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
