"""V2 Action Layer — SHADOW ONLY.

Brain A = WHAT. Camera/P×V = WHEN. Action Layer = shadow confirmation of WHEN.
Not authority to spend capital.

Replay helpers are lazy: the live Camera consumer must not import
``replay.py`` (historical parquet / ``intraday_memory.storage``).
"""

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    STATE_BUY_READY,
    STATE_NOMINATED,
    STATE_NO_OBSERVATION,
    STATE_WAIT,
    STATE_WEAKENED,
)
from modules.live_candidate_v2_action.state import (
    ActionResult,
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
    nomination_from_mapping,
)

__all__ = [
    "ALERT_ELIGIBLE",
    "CANDIDATE_IS_BUY",
    "PXV_IMPLIES_BUY",
    "STATE_BUY_READY",
    "STATE_NOMINATED",
    "STATE_NO_OBSERVATION",
    "STATE_WAIT",
    "STATE_WEAKENED",
    "ActionResult",
    "BarEvidence",
    "FrozenNomination",
    "evaluate_shadow_action",
    "nomination_from_mapping",
    "replay_shadow_action",
    "replay_sidecar_session",
]


def __getattr__(name: str):
    if name in {"replay_shadow_action", "replay_sidecar_session"}:
        from modules.live_candidate_v2_action.replay import (
            replay_shadow_action,
            replay_sidecar_session,
        )

        return replay_shadow_action if name == "replay_shadow_action" else replay_sidecar_session
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
