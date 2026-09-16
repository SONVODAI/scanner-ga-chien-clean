"""Arithmetic observation vs an already-frozen nomination reference.

Not a BUY/SELL rule. Does not invent a level. Does not map P×V to action.

``close`` is used as provided (Camera ``validate_raw_bar`` stores integer VND).
Frozen refs are used as stored on the nomination (scan units, typically
thousands of VND). Slice 2 does not convert units and does not invent a level.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from modules.live_candidate_v2_camera.contract import REF_BREAKOUT, REF_EMA9, REF_UNAVAILABLE


def _num(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def frozen_reference_value(row: Mapping[str, Any]) -> tuple[str, float | None]:
    kind = str(row.get("observation_reference") or "").strip()
    if kind == REF_EMA9:
        return kind, _num(row.get("ema9_at_first_seen"))
    if kind == REF_BREAKOUT:
        return kind, _num(row.get("breakout_ref_at_first_seen"))
    return kind, None


def observe_close_vs_ref(row: Mapping[str, Any], close: object) -> dict[str, Any]:
    """close vs frozen EMA9 / breakout_ref. Nulls when no applicable ref."""
    close_n = _num(close)
    kind, ref = frozen_reference_value(row)
    out = {
        "close": close_n,
        "reference_kind": kind or None,
        "reference_value": ref,
        "close_vs_ref": None,
        "close_vs_ref_pct": None,
        "reference_state": REF_UNAVAILABLE,
    }
    if close_n is None or ref is None or not kind:
        return out
    delta = close_n - ref
    out["close_vs_ref"] = delta
    if ref != 0:
        out["close_vs_ref_pct"] = (delta / ref) * 100.0
    out["reference_state"] = kind
    return out


def pxv_implies_buy(_published: object) -> bool:
    """Slice 2: generic tape labels never mean BUY."""
    return False
