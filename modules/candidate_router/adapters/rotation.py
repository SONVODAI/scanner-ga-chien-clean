"""Downstream Rotation artifact → Candidate adapter.

SLICE 1: disconnected. Returns no nominations.

Future slices will map a Rotation Watch *artifact* (board/status JSON) onto
NominatedCandidate rows. Direction is one-way:

    Rotation artifact → this adapter → Candidate Router

NOT:

    Rotation Watch → Candidate internals

modules.rotation_watch must never import modules.candidate_router.
This adapter must not import Rotation Watch engine/state/decision logic;
it will consume published artifact bytes only.
"""

from __future__ import annotations

from typing import Any

from modules.candidate_router.contract import NominatedCandidate


def nominations_from_rotation_artifact(
    _artifact: Any = None,
) -> tuple[NominatedCandidate, ...]:
    """Slice 1: Rotation is not an enabled Candidate source."""
    return ()
