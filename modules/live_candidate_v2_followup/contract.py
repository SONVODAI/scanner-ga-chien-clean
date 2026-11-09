"""Live Candidate V2 Follow-up Watch V1 — SHADOW / RESEARCH ONLY.

Tracks nominated V2 candidates across VNIndex sessions without loosening
BUY_READY rules and without touching production BUY / Elite / Sweet / Learning.

Feature flag default OFF: MRBOT_V2_FOLLOWUP_WATCH.
"""

from __future__ import annotations

import os

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    ROUTE_BREAK,
    ROUTE_EARLY,
    ROUTE_MANH,
    ROUTE_PULL,
)
from modules.live_candidate_v2_camera.contract import SRC_MARKET_AWARE_SWEETSPOT
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

SCHEMA_REGISTRY = "live_candidate_v2_followup_registry.v1"
SCHEMA_LEDGER = "live_candidate_v2_followup_ledger.v1"
SCHEMA_SESSION = "live_candidate_v2_followup_session.v1"
MODE = "SHADOW_ONLY"
SLICE = "followup_watch_v1"

# Production BUY permissions — hard false for this research slice.
FOLLOWUP_CANDIDATE_IS_BUY = CANDIDATE_IS_BUY  # False
FOLLOWUP_PXV_IMPLIES_BUY = PXV_IMPLIES_BUY  # False
FOLLOWUP_ALERT_ELIGIBLE = ALERT_ELIGIBLE  # False
FOLLOWUP_EXECUTION_ENABLED = False

ENV_FOLLOWUP_WATCH = "MRBOT_V2_FOLLOWUP_WATCH"
ENV_FOLLOWUP_DIR = "MRBOT_V2_FOLLOWUP_DIR"
ENV_FOLLOWUP_TRUTHY = frozenset({"1", "true", "yes", "on"})
ENV_FOLLOWUP_FALSY = frozenset({"", "0", "false", "no", "off"})

# Inclusive VNIndex sessions from original_session through current.
TTL_SESSIONS_INCLUSIVE = 5

ACTIONABLE_SETUPS = frozenset(ROUTE_PULL | {ROUTE_MANH, ROUTE_BREAK, ROUTE_EARLY})

SRC_FOLLOWUP = "v2_followup_watch"
ALLOWED_SOURCES = frozenset({SRC_BRAIN_A, SRC_MARKET_AWARE_SWEETSPOT})

STATUS_ACTIVE = "ACTIVE"
STATUS_WAIT = "WAIT"
STATUS_BUY_READY = "BUY_READY"
STATUS_EXPIRED = "EXPIRED"
STATUS_REJECTED = "REJECTED"

# Measurement arms (immutable ledger tags).
ARM_BASELINE = "A_BASELINE_V2"
ARM_FOLLOWUP = "B_FOLLOWUP_WATCH"
ARM_FOLLOWUP_GUARDIAN = "C_FOLLOWUP_GUARDIAN"

REMOTE_DIR = "research/live_candidate_v2_followup"
REGISTRY_NAME = "followup_registry.json"
LEDGER_NAME = "followup_ledger.jsonl"
SESSION_LOG_NAME = "followup_session_log.jsonl"

REASON_TTL_EXPIRED = "TTL_EXPIRED"
REASON_GUARDIAN_SELL = "GUARDIAN_SELL"  # legacy soft signal only; not a hard reject
REASON_CANDIDATE_GUARDIAN_REJECT = "CANDIDATE_GUARDIAN_REJECTED"
REASON_CANDIDATE_WEAKENING_BLOCK = "CANDIDATE_WEAKENING_BLOCKS_BUY_READY"
REASON_SETUP_EMPTY = "SETUP_EMPTY_CONTINUE_WAIT"
REASON_MARKET_NOT_OK = "MARKET_PERMISSION_NOT_OK_CONTINUE_WAIT"
REASON_WHEN_NOT_MET = "WHEN_NOT_MET_CONTINUE_WAIT"
REASON_BUY_READY = "SHADOW_BUY_READY"
REASON_INGESTED = "INGESTED_FROM_SIDECAR"
REASON_FLAG_OFF = "FEATURE_FLAG_OFF"
REASON_CAP = "CAMERA_CAP_SKIPPED"
REASON_QUALITY_STRONGER_WAIT = "STRONGER_CONTINUE_WAIT_FOR_WHEN"

HORIZONS = (3, 5, 10)


def followup_enabled(raw: str | None = None) -> bool:
    """Default OFF. Explicit truthy required."""
    text = (os.environ.get(ENV_FOLLOWUP_WATCH, "") if raw is None else raw) or ""
    value = str(text).strip().lower()
    if value in ENV_FOLLOWUP_FALSY:
        return False
    return value in ENV_FOLLOWUP_TRUTHY


__all__ = [
    "ACTIONABLE_SETUPS",
    "ALLOWED_SOURCES",
    "ARM_BASELINE",
    "ARM_FOLLOWUP",
    "ARM_FOLLOWUP_GUARDIAN",
    "ENV_FOLLOWUP_DIR",
    "ENV_FOLLOWUP_WATCH",
    "FOLLOWUP_ALERT_ELIGIBLE",
    "FOLLOWUP_CANDIDATE_IS_BUY",
    "FOLLOWUP_EXECUTION_ENABLED",
    "FOLLOWUP_PXV_IMPLIES_BUY",
    "HORIZONS",
    "LEDGER_NAME",
    "MODE",
    "REASON_BUY_READY",
    "REASON_CANDIDATE_GUARDIAN_REJECT",
    "REASON_CANDIDATE_WEAKENING_BLOCK",
    "REASON_CAP",
    "REASON_FLAG_OFF",
    "REASON_GUARDIAN_SELL",
    "REASON_INGESTED",
    "REASON_MARKET_NOT_OK",
    "REASON_QUALITY_STRONGER_WAIT",
    "REASON_SETUP_EMPTY",
    "REASON_TTL_EXPIRED",
    "REASON_WHEN_NOT_MET",
    "REGISTRY_NAME",
    "REMOTE_DIR",
    "SCHEMA_LEDGER",
    "SCHEMA_REGISTRY",
    "SCHEMA_SESSION",
    "SESSION_LOG_NAME",
    "SLICE",
    "SRC_BRAIN_A",
    "SRC_FOLLOWUP",
    "SRC_MARKET_AWARE_SWEETSPOT",
    "STATUS_ACTIVE",
    "STATUS_BUY_READY",
    "STATUS_EXPIRED",
    "STATUS_REJECTED",
    "STATUS_WAIT",
    "TTL_SESSIONS_INCLUSIVE",
    "followup_enabled",
]
