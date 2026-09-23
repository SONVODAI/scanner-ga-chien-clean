"""
Observation classification for research prioritization (Phase 3G.1).

Distinguishes descriptive/structural observations from conditional edge candidates.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Set

from modules.edge_research.research_tools import (
    OBS_HORIZON_HETEROGENEOUS,
    OBS_MARKET_HETEROGENEOUS,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
)


class ObservationKind(str, Enum):
    DESCRIPTIVE_OBSERVATION = "DESCRIPTIVE_OBSERVATION"
    STRUCTURAL_OBSERVATION = "STRUCTURAL_OBSERVATION"
    CONDITIONAL_CANDIDATE = "CONDITIONAL_CANDIDATE"
    ANTI_EDGE_CANDIDATE = "ANTI_EDGE_CANDIDATE"


# Tools that compare groups/partitions — conditional when they find contrast.
_CONDITIONAL_TOOLS = frozenset(
    {
        "partition_group_compare",
        "adaptive_partition_compare",
        "trajectory_partition_compare",
        "categorical_adaptive_compare",
        "interaction_partition",
        "threshold_exploration",
        "market_conditioning",
    }
)

# Full-cohort tools without explanatory partition — descriptive/structural only.
_COHORT_DESCRIPTIVE_TOOLS = frozenset(
    {
        "horizon_comparison",
        "date_decomposition",
        "symbol_decomposition",
        "episode_decomposition",
        "sensitivity_analysis",
        "neighborhood_stability",
    }
)

_STRUCTURAL_CODES = frozenset(
    {
        OBS_HORIZON_HETEROGENEOUS,
        OBS_MARKET_HETEROGENEOUS,
    }
)


def classify_observation(
    *,
    tool_name: str,
    observation_codes: Set[str],
    metrics: Optional[Dict[str, Any]] = None,
) -> ObservationKind:
    """
    Classify experiment result — descriptive horizon drift is NOT an edge candidate.
    """
    metrics = metrics or {}
    codes = set(observation_codes)

    if OBS_TRAJECTORY_GROUP_DIFFERENCE in codes:
        return ObservationKind.CONDITIONAL_CANDIDATE

    if any(c.startswith("SHAPE_") for c in codes if c not in ("SHAPE_FLAT", "SHAPE_NOISY")):
        if metrics.get("best_group_success_rate") is not None or metrics.get("group_count", 0) > 1:
            return ObservationKind.CONDITIONAL_CANDIDATE

    if tool_name in _CONDITIONAL_TOOLS:
        if metrics.get("group_count", 0) > 1 or metrics.get("best_group_success_rate") is not None:
            best = metrics.get("best_group_success_rate") or metrics.get("success_rate")
            baseline = metrics.get("baseline_success_rate")
            if best is not None and baseline is not None and float(best) < float(baseline) - 0.05:
                return ObservationKind.ANTI_EDGE_CANDIDATE
            return ObservationKind.CONDITIONAL_CANDIDATE
        if codes & _STRUCTURAL_CODES:
            return ObservationKind.STRUCTURAL_OBSERVATION

    if tool_name in _COHORT_DESCRIPTIVE_TOOLS or codes & _STRUCTURAL_CODES:
        if OBS_HORIZON_HETEROGENEOUS in codes or OBS_MARKET_HETEROGENEOUS in codes:
            return ObservationKind.STRUCTURAL_OBSERVATION
        return ObservationKind.DESCRIPTIVE_OBSERVATION

    if tool_name in _CONDITIONAL_TOOLS:
        return ObservationKind.DESCRIPTIVE_OBSERVATION

    return ObservationKind.DESCRIPTIVE_OBSERVATION


def is_conditional_candidate(kind: str) -> bool:
    return kind in (
        ObservationKind.CONDITIONAL_CANDIDATE.value,
        ObservationKind.ANTI_EDGE_CANDIDATE.value,
    )
