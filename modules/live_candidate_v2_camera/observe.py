"""Arithmetic observation vs an already-frozen nomination reference.

Not a BUY/SELL rule. Does not invent a level. Does not map P×V to action.

Transport boundary: both Camera close and the frozen Brain A ref are passed
through the existing Camera helper ``normalize_price_to_integer_vnd``
(canonical unit: integer VND). Raw/source values are preserved.

``close_vs_ref`` / ``close_vs_ref_pct`` are emitted only when both sides
normalize. Helper failure → UNIT_MISMATCH + nulls. Missing ref → UNAVAILABLE.
Does not change P×V bar inputs.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from modules.intraday_memory.normalize import normalize_price_to_integer_vnd
from modules.live_candidate_v2_camera.contract import (
    CANONICAL_PRICE_UNIT,
    REF_BREAKOUT,
    REF_EMA9,
    REF_UNAVAILABLE,
    REF_UNIT_MISMATCH,
)


def _num(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def to_canonical_integer_vnd(value: object) -> int | None:
    """Reuse Camera CanonicalBar normalization. None if the helper rejects."""
    try:
        return normalize_price_to_integer_vnd(value)
    except (TypeError, ValueError):
        return None


def frozen_reference_value(row: Mapping[str, Any]) -> tuple[str, float | None]:
    kind = str(row.get("observation_reference") or "").strip()
    if kind == REF_EMA9:
        return kind, _num(row.get("ema9_at_first_seen"))
    if kind == REF_BREAKOUT:
        return kind, _num(row.get("breakout_ref_at_first_seen"))
    return kind, None


def observe_close_vs_ref(row: Mapping[str, Any], close: object) -> dict[str, Any]:
    """close vs frozen EMA9 / breakout_ref in integer VND, or nulls."""
    close_raw = _num(close)
    kind, ref_raw = frozen_reference_value(row)
    out: dict[str, Any] = {
        "close": close_raw,
        "close_canonical": None,
        "reference_kind": kind or None,
        "reference_value": ref_raw,
        "reference_canonical": None,
        "price_unit": None,
        "close_vs_ref": None,
        "close_vs_ref_pct": None,
        "reference_state": REF_UNAVAILABLE,
    }
    if not kind or ref_raw is None or close_raw is None:
        return out

    close_c = to_canonical_integer_vnd(close_raw)
    ref_c = to_canonical_integer_vnd(ref_raw)
    out["close_canonical"] = close_c
    out["reference_canonical"] = ref_c
    if close_c is None or ref_c is None:
        out["reference_state"] = REF_UNIT_MISMATCH
        return out

    delta = close_c - ref_c
    out["price_unit"] = CANONICAL_PRICE_UNIT
    out["close_vs_ref"] = float(delta)
    if ref_c != 0:
        out["close_vs_ref_pct"] = (delta / ref_c) * 100.0
    out["reference_state"] = kind
    return out


def pxv_implies_buy(_published: object) -> bool:
    """Slice 2: generic tape labels never mean BUY."""
    return False
