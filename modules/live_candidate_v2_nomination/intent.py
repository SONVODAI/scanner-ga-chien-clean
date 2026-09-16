"""Provenance vs Camera task.

source_action / source_reason: exact app.py::buy_recommendation text.
observation_intent: neutral Camera watch task. Does NOT mean BUY.
observation_reference: which already-frozen field Camera watches, if any.

Does not invent P×V conditions. Does not map P×V states to actions.
Does not copy NAV.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from modules.live_candidate_v2_nomination.contract import SECONDARY_SETUP

# Verbatim action + lý do from app.py buy_recommendation (provenance only).
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

APP_PY_PROVENANCE_STRINGS = (
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
# Backward-compatible alias used by existing tests.
APP_PY_INTENT_STRINGS = APP_PY_PROVENANCE_STRINGS

# Neutral Camera task. Not BUY. Not a P×V state.
INTENT_WATCH_FROZEN_REF = "WATCH_PRICE_TAPE_VS_FROZEN_REF"
INTENT_WATCH_SETUP = "WATCH_NOMINATED_SETUP"
CAMERA_INTENTS = frozenset({INTENT_WATCH_FROZEN_REF, INTENT_WATCH_SETUP})

REF_EMA9 = "EMA9"
REF_BREAKOUT = "BREAKOUT_REF"

BUY_LIKE_TOKENS = (
    "MUA ",
    "BUY",
    "CANH ADD",
    "TEST EARLY",
    "CHỜ PULL",
    "STRENGTHEN",
    "CONTRACTION",
    "EXPANSION",
    "CONFIRMING",
    "SELL_EXPANSION",
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


def source_action_reason(row: Mapping[str, Any]) -> tuple[str, str]:
    """Exact buy_recommendation action + lý do. Provenance, not Camera task."""
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


def camera_observation(setup: str) -> tuple[str, str]:
    """Neutral Camera task + which existing frozen ref to watch.

    Does not invent a price level or a P×V trigger.
    """
    setup = str(setup or "").strip()
    if setup in {"PULL ĐẸP", "PULL VỪA", "CP MẠNH"}:
        return INTENT_WATCH_FROZEN_REF, REF_EMA9
    if setup == "MUA BREAK":
        return INTENT_WATCH_FROZEN_REF, REF_BREAKOUT
    if setup == SECONDARY_SETUP:
        return INTENT_WATCH_SETUP, ""
    return INTENT_WATCH_SETUP, ""


def observation_intent(row: Mapping[str, Any]) -> str:
    intent, _ref = camera_observation(str(row.get("group") or row.get("setup") or ""))
    return intent


def observation_reference(row: Mapping[str, Any]) -> str:
    _intent, ref = camera_observation(str(row.get("group") or row.get("setup") or ""))
    return ref
