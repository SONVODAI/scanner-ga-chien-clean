"""VN session phase + actionability overlay.

Does not change the Rotation zone × P×V table. It only decides whether the
current clock may emit a live BUY_READY / SELL_READY action.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.constants import (
    ACT_WAIT,
    ARTIFACT_STALE_AFTER_SEC,
    FRESH_STALE,
    LIVE_ACTIONABLE_PHASES,
    PHASE_LUNCH,
    PHASE_PRE_OPEN,
    PHASE_SESSION_CLOSED,
    PHASE_LIVE,
    PHASE_WEEKEND,
    ST_DATA_UNCERTAIN,
    STATE_TO_ACTION,
)

SESSION_OPEN = time(9, 15)
LUNCH_START = time(11, 30)
LUNCH_END = time(13, 0)
SESSION_END = time(14, 50)

PHASE_REASON = {
    PHASE_WEEKEND: "weekend — last session is review-only; current action WAIT",
    PHASE_PRE_OPEN: "before session open — previous session visible; current action WAIT",
    PHASE_SESSION_CLOSED: "session closed — review-only; current action WAIT",
}


def session_phase(now: datetime) -> str:
    now = as_vn(now)
    if now.weekday() >= 5:
        return PHASE_WEEKEND
    clock = now.timetz().replace(tzinfo=None)
    if clock < SESSION_OPEN:
        return PHASE_PRE_OPEN
    if LUNCH_START <= clock < LUNCH_END:
        return PHASE_LUNCH
    if clock >= SESSION_END:
        return PHASE_SESSION_CLOSED
    return PHASE_LIVE


def is_live_actionable(phase: str) -> bool:
    return phase in LIVE_ACTIONABLE_PHASES


def apply_actionability(
    row: dict[str, Any],
    now: datetime,
    *,
    artifact_observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Copy last-session evidence; gate the current suggested action."""
    out = dict(row)
    phase = session_phase(now)
    last_state = str(out.get("last_session_state") or out.get("rotation_state") or ST_DATA_UNCERTAIN)
    last_action = str(out.get("last_session_action") or STATE_TO_ACTION.get(last_state, ACT_WAIT))
    out["last_session_state"] = last_state
    out["last_session_action"] = last_action
    out["session_phase"] = phase
    out["rotation_state"] = last_state

    if is_live_actionable(phase) and artifact_observed_at is not None:
        age = (as_vn(now) - as_vn(artifact_observed_at)).total_seconds()
        if age > ARTIFACT_STALE_AFTER_SEC:
            out["suggested_action"] = ACT_WAIT
            out["actionable"] = False
            out["action_gate_reason"] = (
                f"artifact older than {ARTIFACT_STALE_AFTER_SEC}s in live session"
            )
            out["freshness"] = FRESH_STALE
            out["rotation_state"] = ST_DATA_UNCERTAIN
            # last_session_state kept for review
            return out

    if last_state == ST_DATA_UNCERTAIN:
        out["suggested_action"] = ACT_WAIT
        out["actionable"] = False
        out["action_gate_reason"] = str(out.get("freshness_reason") or "data uncertain")
        return out

    if not is_live_actionable(phase):
        out["suggested_action"] = ACT_WAIT
        out["actionable"] = False
        out["action_gate_reason"] = PHASE_REASON[phase]
        return out

    out["suggested_action"] = last_action
    out["actionable"] = True
    out["action_gate_reason"] = ""
    return out
