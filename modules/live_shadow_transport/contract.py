"""LIVE shadow transport identity / freshness contract.

Read-only constants. No network. No Camera archive. No P×V recompute.
"""
from __future__ import annotations

# Existing Cloud → git bus (app.py _github_write_text / _github_read_text).
GITHUB_WATCHLIST_PATH = "data/live_candidate/dynamic_watchlist.json"
# Canonical no-candidate document. Missing object (HTTP 404) is a transport
# error, not an empty universe. Never represent zero candidates by absence.
EMPTY_WATCHLIST_TEXT = "[]"
GITHUB_ELITE_HISTORY_PATH = "buy_elite_learning_history.csv"

# Existing Cloud ← VPS bus (artifact server + Streamlit EDGE_RESEARCH_DURABLE_*).
# New GET-only objects; do not put these inside Edge Research bundle.tar.gz.
ARTIFACT_EVIDENCE_PATH = "/current/live_shadow/live_evidence.jsonl"
ARTIFACT_STATUS_PATH = "/current/live_shadow/live_shadow_status.json"
VPS_SHADOW_STORE = "/var/lib/mrbot/live_pxv_shadow"

# Never these:
FORBIDDEN_CAMERA_ARCHIVE = "/var/lib/mrbot/intraday_memory"
FORBIDDEN_EDGE_BUNDLE = "/current/bundle.tar.gz"

EPISODE_KEY = ("session", "symbol")
BAR_KEY = ("symbol", "bar_ts")

IDENTITY_FIELDS = (
    "session",
    "symbol",
    "candidate_first_seen_ts",
    "eligible_from",
    "candidate_updated_ts",
    "bar_ts",
    "observed_at",
    "raw_evidence",
    "published_evidence",
    "data_state",
    "data_quality",
    "chronology_legal",
    "runner_observed_at",
    "runner_label",
)

# Pass-through only. Never rewrite clocks.
IMMUTABLE_ON_TRANSPORT = (
    "candidate_first_seen_ts",
    "eligible_from",
    "bar_ts",
    "chronology_legal",
)

RUNNER_STALE_AFTER_SEC = 600
ALERT_ELIGIBLE = False

WATCHLIST_TRANSPORT_ERROR = "WATCHLIST_TRANSPORT_ERROR"
EVIDENCE_TRANSPORT_ERROR = "EVIDENCE_TRANSPORT_ERROR"
RUNNER_LIVE = "LIVE"
RUNNER_STALE = "STALE"
RUNNER_STOPPED = "STOPPED"

WATCHLIST_PUBLISH_STATUS_NAME = "watchlist_publish_status.json"
EVIDENCE_NAME = "live_evidence.jsonl"
STATUS_NAME = "live_shadow_status.json"

ENV_WATCHLIST_SOURCE = "MRBOT_WATCHLIST_SOURCE"
ENV_SHADOW_STORE = "MRBOT_LIVE_PXV_SHADOW_STORE"
ENV_UI_SOURCE = "MRBOT_LIVE_PXV_UI_SOURCE"
