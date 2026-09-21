"""LIVE CANDIDATE V2 Camera sidecar contract — Slice 2, SHADOW ONLY.

Sidecar for Camera observation transport. Not BUY. Not the production
8-column dynamic_watchlist.json.
"""

from __future__ import annotations

from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

SCHEMA_ID = "live_candidate_v2_camera_sidecar_v1"
SLICE = 2
MODE = "SHADOW_ONLY"

# Keep this string identical to candidate_router.contract.SRC_MARKET_AWARE_SWEETSPOT.
# camera.contract is on the VPS allowlist; candidate_router is not.
SRC_MARKET_AWARE_SWEETSPOT = "market_aware_sweetspot"

# Shadow-only Router enablement. Production ENABLED_SOURCES is unchanged.
# Brain A ∪ Sweet Brain B. OR, not AND. learning_insight stays out.
SHADOW_V2_ENABLED_SOURCES = frozenset({SRC_BRAIN_A, SRC_MARKET_AWARE_SWEETSPOT})

DEFAULT_SIDECAR_RELPATH = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
PRODUCTION_WATCHLIST_RELPATH = "data/live_candidate/dynamic_watchlist.json"

# Slice 3A Cloud local writer. Default OFF. Do not overload Elite/live-camera flags.
ENV_V2_CLOUD_SIDECAR = "MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR"
ENV_V2_CLOUD_SIDECAR_TRUTHY = frozenset({"1", "true", "yes", "on"})
ENV_V2_CLOUD_SIDECAR_FALSY = frozenset({"", "0", "false", "no", "off"})

# Slice 3B GitHub Contents publish. Default OFF. Independent of Gate A.
# Enabling the local sidecar does not publish. Enabling publish does not generate.
ENV_V2_GITHUB_PUBLISH = "MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH"
ENV_V2_GITHUB_PUBLISH_TRUTHY = ENV_V2_CLOUD_SIDECAR_TRUTHY
ENV_V2_GITHUB_PUBLISH_FALSY = ENV_V2_CLOUD_SIDECAR_FALSY

# Dedicated V2 GitHub Contents path. Never retarget production Elite watchlist.
GITHUB_V2_SIDECAR_PATH = DEFAULT_SIDECAR_RELPATH

REF_EMA9 = "EMA9"
REF_BREAKOUT = "BREAKOUT_REF"
REF_UNAVAILABLE = "UNAVAILABLE"
REF_UNIT_MISMATCH = "UNIT_MISMATCH"

# Camera canonical unit. Same helper as validate_raw_bar / CanonicalBar.
CANONICAL_PRICE_UNIT = "integer_vnd"

GENERIC_PXV = frozenset({"STRENGTHEN", "NEUTRAL", "WEAKEN", "CONFLICT", "UNUSABLE"})

SIDECAR_ROW_FIELDS = (
    "symbol",
    "session",
    "candidate_first_seen_ts",
    "candidate_updated_ts",
    "eligible_from",
    "source",
    "status",
    "setup",
    "group",
    "observation_intent",
    "observation_reference",
    "price_at_first_seen",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
    "source_action",
    "source_reason",
    "elite_buy_grade",
    "market_real",
    "market_permission",
    "provenance",
    "candidate_is_buy",
    "alert_eligible",
)
