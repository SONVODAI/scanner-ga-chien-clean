"""Live Candidate V2 Follow-up Watch V1 — SHADOW / RESEARCH ONLY.

Default OFF via MRBOT_V2_FOLLOWUP_WATCH. Does not alter production BUY paths.
"""

from modules.live_candidate_v2_followup.camera_bridge import merge_followup_into_actionable
from modules.live_candidate_v2_followup.contract import (
    ENV_FOLLOWUP_WATCH,
    TTL_SESSIONS_INCLUSIVE,
    followup_enabled,
)
from modules.live_candidate_v2_followup.measure import (
    mature_buy_ready_outcomes,
    record_baseline_action_rows,
    summarize_arms,
)
from modules.live_candidate_v2_followup.runtime import run_followup_runtime_cycle
from modules.live_candidate_v2_followup.session import run_followup_session

__all__ = [
    "ENV_FOLLOWUP_WATCH",
    "TTL_SESSIONS_INCLUSIVE",
    "followup_enabled",
    "mature_buy_ready_outcomes",
    "merge_followup_into_actionable",
    "record_baseline_action_rows",
    "run_followup_runtime_cycle",
    "run_followup_session",
    "summarize_arms",
]
