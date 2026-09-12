"""Isolated adapter over the frozen P×V interpreter.

Calls evaluate_gate → compute_features → decide_evidence(thesis_long=True)
→ PublishedDebouncer. Does not stamp BUY ELITE / Candidate. Does not apply
Candidate chronology or the Candidate session orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from modules.intraday_pxv_v1.constants import (
    DATA_UNUSABLE,
    EV_NEUTRAL,
    EV_UNUSABLE,
)
from modules.intraday_pxv_v1.debounce import PublishedDebouncer
from modules.intraday_pxv_v1.evidence import decide_evidence
from modules.intraday_pxv_v1.features import FAM_PXV, compute_features
from modules.intraday_pxv_v1.gate import evaluate_gate
from modules.live_camera_shadow.bars import completed_to_overlay
from modules.live_candidate.calendar import as_vn


@dataclass
class RotationPxV:
    raw: str = EV_UNUSABLE
    published: str = EV_UNUSABLE
    raw_why: str = ""
    published_why: str = ""
    data_state: str = DATA_UNUSABLE
    gate_reason: str = ""
    pxv_feature_state: str = ""
    n_bars: int = 0
    usable: bool = False
    sequence: list[dict[str, str]] = field(default_factory=list)


def interpret_completed_bars(
    completed: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> RotationPxV:
    """Run the frozen bar-loop with long thesis. No Candidate event."""
    del now  # clock is owned by the data/freshness layer
    if not completed:
        return RotationPxV(
            raw=EV_UNUSABLE,
            published=EV_UNUSABLE,
            raw_why="no completed 5m bars",
            published_why="no completed 5m bars",
            data_state=DATA_UNUSABLE,
            gate_reason="UNAVAILABLE",
        )

    overlay = completed_to_overlay(completed)
    if overlay is None or overlay.empty:
        return RotationPxV(
            raw=EV_UNUSABLE,
            published=EV_UNUSABLE,
            raw_why="empty overlay",
            published_why="empty overlay",
            data_state=DATA_UNUSABLE,
            gate_reason="UNAVAILABLE",
        )

    debouncer = PublishedDebouncer()
    last = RotationPxV()
    sequence: list[dict[str, str]] = []
    for _, bar in overlay.sort_values("timestamp").iterrows():
        asof = bar["timestamp"]
        if hasattr(asof, "to_pydatetime"):
            asof = asof.to_pydatetime()
        asof = as_vn(asof)
        gate = evaluate_gate(overlay, asof=asof, tod_qualified_sessions=0)
        features = compute_features(
            overlay,
            gate,
            asof=asof,
            tod_rvol_baseline=None,
            tod_pace_baseline=None,
        )
        ev = decide_evidence(gate, features, thesis_long=True)
        published, pub_why = debouncer.step(ev.evidence)
        pxv_state = ""
        fam = features.get(FAM_PXV) or {}
        if fam:
            pxv_state = str(fam.get("state") or "")
        last = RotationPxV(
            raw=ev.evidence,
            published=published,
            raw_why=ev.evidence_why,
            published_why=pub_why,
            data_state=gate.data_state,
            gate_reason=gate.gate_reason,
            pxv_feature_state=pxv_state,
            n_bars=gate.n_bars,
            usable=gate.usable_volume and published != EV_UNUSABLE,
        )
        sequence.append(
            {
                "asof": asof.isoformat(),
                "raw": ev.evidence,
                "published": published,
            }
        )
    last.sequence = sequence
    return last
