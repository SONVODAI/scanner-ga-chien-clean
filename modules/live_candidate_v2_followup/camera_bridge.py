"""Gated Camera bridge for Follow-up Watch.

When the feature flag is OFF this module is a pure no-op.
When ON, follow-up rows fill only remaining slots under LIVE_UNIVERSE_CAP
after the ordinary actionable V2 universe is counted — never raises the cap.

Follow-up rows never carry stale BUY_READY / buy rights into Camera.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP
from modules.live_candidate_v2_action.live_universe import (
    ACTIONABLE_LIVE_SETUPS,
    ActionableUniverse,
    select_actionable_v2,
)
from modules.live_candidate_v2_followup.contract import (
    REASON_CAP,
    REASON_FLAG_OFF,
    SRC_FOLLOWUP,
    followup_enabled,
)


def _setup(row: Mapping[str, Any]) -> str:
    return str(row.get("setup") or row.get("group") or "").strip()


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _sanitize_followup_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Fresh Camera nomination — strip any inherited buy rights / prior action."""
    row = dict(raw)
    row["symbol"] = _symbol(row)
    row["source"] = SRC_FOLLOWUP
    row["nomination_source"] = SRC_FOLLOWUP
    row["v2_camera"] = True
    row["v2_followup"] = True
    row["candidate_is_buy"] = False
    row["alert_eligible"] = False
    row["pxv_implies_buy"] = False
    row.pop("shadow_action", None)
    row.pop("action_state", None)
    row.pop("prior_action_state", None)
    row.pop("buy_ready_at", None)
    row.pop("price_at_first_met", None)
    row.pop("first_met_at", None)
    return row


def merge_followup_into_actionable(
    sidecar_rows: Sequence[Mapping[str, Any]] | None,
    followup_camera_rows: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Return fetch list = baseline actionable ∪ follow-up fill, cap unchanged."""
    on = followup_enabled() if enabled is None else bool(enabled)
    baseline = select_actionable_v2(sidecar_rows, now=now, cap=cap)
    if not on:
        return {
            "enabled": False,
            "reason": REASON_FLAG_OFF,
            "fetch": list(baseline.fetch),
            "followup_added": [],
            "followup_skipped_cap": [],
            "hard_cap": baseline.hard_cap,
            "n_baseline": len(baseline.fetch),
            "universe": baseline,
        }

    listed = {_symbol(r) for r in baseline.fetch} | {_symbol(r) for r in baseline.not_yet}
    remaining = max(0, int(cap) - len(baseline.fetch))
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in followup_camera_rows or ():
        if not isinstance(raw, Mapping):
            continue
        if _setup(raw) not in ACTIONABLE_LIVE_SETUPS:
            continue
        symbol = _symbol(raw)
        if not symbol or symbol in listed:
            continue
        row = _sanitize_followup_row(raw)
        if remaining <= 0:
            row["_skip"] = REASON_CAP
            skipped.append(row)
            continue
        added.append(row)
        listed.add(symbol)
        remaining -= 1

    universe = ActionableUniverse(
        fetch=list(baseline.fetch) + added,
        not_yet=list(baseline.not_yet),
        cap_dropped=list(baseline.cap_dropped) + skipped,
        n_actionable=baseline.n_actionable + len(added),
        hard_cap=int(cap),
    )
    return {
        "enabled": True,
        "reason": "OK",
        "fetch": list(universe.fetch),
        "followup_added": added,
        "followup_skipped_cap": skipped,
        "hard_cap": int(cap),
        "n_baseline": len(baseline.fetch),
        "n_followup_added": len(added),
        "universe": universe,
    }


def apply_followup_to_universe(
    sidecar_rows: Sequence[Mapping[str, Any]] | None,
    followup_camera_rows: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Camera feed entrypoint — returns ActionableUniverse under ``universe``."""
    return merge_followup_into_actionable(
        sidecar_rows,
        followup_camera_rows,
        now=now,
        cap=cap,
        enabled=enabled,
    )


__all__ = ["apply_followup_to_universe", "merge_followup_into_actionable"]
