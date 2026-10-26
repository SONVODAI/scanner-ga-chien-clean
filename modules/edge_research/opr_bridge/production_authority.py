"""
Phase 3J.0 — Production OPR research authority routing.

Wiring-only: defines single canonical authority for autonomous proposition research.
Does NOT modify scientific rules.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from modules.edge_research.research_graph import ResearchGraph

AUTHORITY_VERSION = "production_opr_authority_v1_3j0"
OPR_AUTHORITY_MARKER = "OPR_LIFECYCLE"
LEGACY_AUTHORITY_MARKER = "LEGACY_TEMPLATE_GAP"


class LegacyPathClassification(str, Enum):
    OPR_AUTHORITY = "OPR_AUTHORITY"
    LEGACY_SUPPORT_ONLY = "LEGACY_SUPPORT_ONLY"
    LEGACY_DIAGNOSTIC_ONLY = "LEGACY_DIAGNOSTIC_ONLY"
    EXECUTION_UTILITY = "EXECUTION_UTILITY"
    DEPRECATED_PARALLEL_AUTHORITY = "DEPRECATED_PARALLEL_AUTHORITY"


class OprLegacyPlannerBlockedError(RuntimeError):
    """Raised when legacy template/GAP planner is invoked under OPR authority."""


# Explicit authority map (pre-implementation audit baseline)
LEGACY_PATH_AUTHORITY_MAP: Dict[str, LegacyPathClassification] = {
    "opr_bridge.prioritized_pipeline": LegacyPathClassification.OPR_AUTHORITY,
    "opr_bridge.lifecycle_runner": LegacyPathClassification.OPR_AUTHORITY,
    "opr_bridge.lifecycle_synthesis_hook": LegacyPathClassification.OPR_AUTHORITY,
    "opr_bridge.lifecycle_dormancy_integration": LegacyPathClassification.OPR_AUTHORITY,
    "opr_bridge.scientific_action_generator": LegacyPathClassification.OPR_AUTHORITY,
    "research_actions.generate_action_candidates": LegacyPathClassification.DEPRECATED_PARALLEL_AUTHORITY,
    "research_planner.plan_next_action": LegacyPathClassification.DEPRECATED_PARALLEL_AUTHORITY,
    "research_interpreter.interpret_tool_result": LegacyPathClassification.LEGACY_SUPPORT_ONLY,
    "research_tools.execute_research_experiment": LegacyPathClassification.EXECUTION_UTILITY,
    "research_tools.ToolRegistry": LegacyPathClassification.EXECUTION_UTILITY,
    "research_graph.ResearchGraph": LegacyPathClassification.LEGACY_SUPPORT_ONLY,
    "autonomous_research.bootstrap_research_graph": LegacyPathClassification.DEPRECATED_PARALLEL_AUTHORITY,
    "diagnostics.run_phase_3i": LegacyPathClassification.LEGACY_DIAGNOSTIC_ONLY,
}


def mark_session_opr_authority(graph: ResearchGraph) -> None:
    """Tag graph session as OPR-governed (integration marker only)."""
    acct = dict(graph.session.search_accounting or {})
    acct["research_authority"] = OPR_AUTHORITY_MARKER
    acct["research_authority_version"] = AUTHORITY_VERSION
    graph.session.search_accounting = acct


def session_has_opr_authority(graph: ResearchGraph) -> bool:
    acct = graph.session.search_accounting or {}
    return acct.get("research_authority") == OPR_AUTHORITY_MARKER


def assert_legacy_planner_blocked(graph: ResearchGraph) -> None:
    """Block legacy GAP/template planner when OPR is authoritative."""
    if session_has_opr_authority(graph):
        raise OprLegacyPlannerBlockedError(
            "Legacy template/GAP planner blocked: session is OPR-authoritative "
            f"({AUTHORITY_VERSION})"
        )


def authority_map_summary() -> Dict[str, Any]:
    return {
        "authority_version": AUTHORITY_VERSION,
        "canonical_authority": OPR_AUTHORITY_MARKER,
        "legacy_parallel_paths": [
            k
            for k, v in LEGACY_PATH_AUTHORITY_MAP.items()
            if v == LegacyPathClassification.DEPRECATED_PARALLEL_AUTHORITY
        ],
        "execution_utilities": [
            k
            for k, v in LEGACY_PATH_AUTHORITY_MAP.items()
            if v == LegacyPathClassification.EXECUTION_UTILITY
        ],
        "path_classifications": {k: v.value for k, v in LEGACY_PATH_AUTHORITY_MAP.items()},
    }
