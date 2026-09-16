"""Observation intent from existing app.py buy_recommendation text.

Source of truth: app.py::buy_recommendation (action + lý do only).
This is a Camera task description, NOT a buy rule.
Does not invent P×V conditions. Does not copy NAV.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from modules.live_candidate_v2_nomination.contract import (
    PRIMARY_SETUPS,
    SECONDARY_SETUP,
)

# Verbatim action + lý do from app.py buy_recommendation.
# Keep in lockstep; tests assert these strings still exist in app.py.
PULL_DEP_ACTION = "MUA PULL ĐẸP"
PULL_DEP_REASON = "Pull sát EMA9, OBV còn xanh"
PULL_VUA_ACTION = "MUA PULL VỪA"
PULL_VUA_REASON = "Pull vừa, mua thăm dò"
MUA_BREAK_ACTION = "MUA BREAK"
MUA_BREAK_REASON = "Break xác nhận, không đuổi quá xa"
TEST_EARLY_ACTION = "TEST EARLY"
TEST_EARLY_REASON = "Early sạch, test nhỏ"
CHO_PULL_ACTION = "CHỜ PULL"
CHO_PULL_REASON = "CP mạnh nhưng xa EMA9"
CANH_ADD_ACTION = "CANH ADD CP MẠNH"
CANH_ADD_REASON = "CP mạnh, có thể add nhỏ"

# Existing CP MẠNH branch: dist > 4 → CHỜ PULL, else CANH ADD.
CP_MANH_CHO_PULL_DIST = 4

APP_PY_INTENT_STRINGS = (
    PULL_DEP_ACTION,
    PULL_DEP_REASON,
    PULL_VUA_ACTION,
    PULL_VUA_REASON,
    MUA_BREAK_ACTION,
    MUA_BREAK_REASON,
    TEST_EARLY_ACTION,
    TEST_EARLY_REASON,
    CHO_PULL_ACTION,
    CHO_PULL_REASON,
    CANH_ADD_ACTION,
    CANH_ADD_REASON,
)


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (float, int)) and isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def format_intent(action: str, reason: str) -> str:
    action = str(action or "").strip()
    reason = str(reason or "").strip()
    if action and reason:
        return f"{action} — {reason}"
    return action or reason


def observation_action_reason(row: Mapping[str, Any]) -> tuple[str, str]:
    """Setup wait context copied from buy_recommendation branches.

    Not gated on obv_ok: nomination already decided; this is what Camera
    is asked to observe, not a permission to buy.
    CP MẠNH still uses the existing dist > 4 split (CHỜ PULL vs CANH ADD).
    """
    group = str(row.get("group") or row.get("setup") or "").strip()
    dist = _num(row.get("dist_from_ema9_pct"))

    if group == "PULL ĐẸP":
        return PULL_DEP_ACTION, PULL_DEP_REASON
    if group == "PULL VỪA":
        return PULL_VUA_ACTION, PULL_VUA_REASON
    if group == "MUA BREAK":
        return MUA_BREAK_ACTION, MUA_BREAK_REASON
    if group == "CP MẠNH":
        if dist is not None and dist > CP_MANH_CHO_PULL_DIST:
            return CHO_PULL_ACTION, CHO_PULL_REASON
        return CANH_ADD_ACTION, CANH_ADD_REASON
    if group == SECONDARY_SETUP:
        return TEST_EARLY_ACTION, TEST_EARLY_REASON
    return "", ""


def observation_intent(row: Mapping[str, Any]) -> str:
    action, reason = observation_action_reason(row)
    return format_intent(action, reason)


def intent_applies_to_setup(group: str) -> bool:
    return group in PRIMARY_SETUPS or group == SECONDARY_SETUP
