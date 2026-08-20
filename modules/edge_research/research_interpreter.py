"""
Deterministic Result Interpreter for Edge Research (PATCH 3C).

ToolResult + branch context → ResearchAssessment. No action selection.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from modules.edge_research.research_assessment import (
    DescriptiveStrength,
    InterpretationConfidence,
    ResearchAssessment,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_state import NodeType
from modules.edge_research.research_tools import (
    OBS_DATE_BROAD,
    OBS_DATE_CONCENTRATED,
    OBS_EPISODE_CONSISTENT,
    OBS_EPISODE_HETEROGENEOUS,
    OBS_EPISODE_INSUFFICIENT,
    OBS_EXTREME_WINNER_ROBUST,
    OBS_EXTREME_WINNER_SENSITIVE,
    OBS_HORIZON_HETEROGENEOUS,
    OBS_MARKET_HETEROGENEOUS,
    OBS_NEIGHBORHOOD_STABLE,
    OBS_NEIGHBORHOOD_UNSTABLE,
    OBS_NO_CLEAR_DIFFERENCE,
    OBS_NO_VARIATION,
    OBS_SENSITIVITY_FRAGILE,
    OBS_SENSITIVITY_ROBUST,
    OBS_SYMBOL_BROAD,
    OBS_SYMBOL_CONCENTRATED,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    ToolResult,
    ToolStatus,
)

# Information gap codes used by action generator (not tool names).
GAP_TIME_DISTRIBUTION = "TIME_DISTRIBUTION"
GAP_SYMBOL_DISTRIBUTION = "SYMBOL_DISTRIBUTION"
GAP_EPISODE_REPLICATION = "EPISODE_REPLICATION"
GAP_MARKET_DEPENDENCE = "MARKET_DEPENDENCE"
GAP_HORIZON_STABILITY = "HORIZON_STABILITY"
GAP_NEIGHBORHOOD_STABILITY = "NEIGHBORHOOD_STABILITY"
GAP_TRAJECTORY_ROLE = "TRAJECTORY_ROLE"
GAP_SUBGROUP_ARTIFACT = "SUBGROUP_ARTIFACT"

FALSIFY_EXTREME_WINNER = "EXTREME_WINNER"
FALSIFY_DATE_ARTIFACT = "DATE_ARTIFACT"
FALSIFY_SYMBOL_DOMINANCE = "SYMBOL_DOMINANCE"
FALSIFY_EPISODE_FLUKE = "EPISODE_FLUKE"


def _branch_tools_attempted(graph: ResearchGraph, experiment_node_id: str) -> Tuple[str, ...]:
    tools: List[str] = []
    for node in graph.reconstruct_lineage(experiment_node_id):
        if node.node_type == NodeType.EXPERIMENT and node.experiment_spec:
            tools.append(node.experiment_spec.tool_name)
    return tuple(tools)


def _branch_observation_codes(graph: ResearchGraph, experiment_node_id: str) -> Tuple[str, ...]:
    codes: List[str] = []
    for node in graph.reconstruct_lineage(experiment_node_id):
        if node.experiment_result:
            codes.extend(o.code for o in node.experiment_result.observations)
    return tuple(codes)


def _obs_codes(result: ToolResult) -> Set[str]:
    return {o.code for o in result.structured_observations}


def interpret_tool_result(
    graph: ResearchGraph,
    experiment_node_id: str,
    tool_result: ToolResult,
) -> ResearchAssessment:
    """Convert deterministic tool output into structured research assessment."""
    codes = _obs_codes(tool_result)
    branch_tools = _branch_tools_attempted(graph, experiment_node_id)
    branch_obs = _branch_observation_codes(graph, experiment_node_id)

    findings = tuple(sorted(codes))
    concentration: List[str] = []
    replication: List[str] = []
    fragility: List[str] = []
    context_dep: List[str] = []
    horizon_dep: List[str] = []
    uncertainties: List[str] = []
    gaps: List[str] = []
    falsify_targets: List[str] = []
    contradictions: List[str] = []

    if OBS_DATE_CONCENTRATED in codes:
        concentration.append("DATE")
        uncertainties.append("TIME_CONCENTRATION")
        falsify_targets.append(FALSIFY_DATE_ARTIFACT)
    if OBS_SYMBOL_CONCENTRATED in codes:
        concentration.append("SYMBOL")
        uncertainties.append("SYMBOL_CONCENTRATION")
        falsify_targets.append(FALSIFY_SYMBOL_DOMINANCE)
    if OBS_DATE_BROAD in codes:
        findings = findings  # recorded; reduces date gap urgency downstream

    if OBS_EPISODE_HETEROGENEOUS in codes:
        replication.append("EPISODE_INCONSISTENT")
        uncertainties.append("EPISODE_REPLICATION")
    if OBS_EPISODE_CONSISTENT in codes:
        replication.append("EPISODE_CONSISTENT")
    if OBS_EPISODE_INSUFFICIENT in codes:
        replication.append("EPISODE_INSUFFICIENT")

    if OBS_EXTREME_WINNER_SENSITIVE in codes or OBS_SENSITIVITY_FRAGILE in codes:
        fragility.append("EXTREME_WINNER_OR_SENSITIVITY")
        falsify_targets.append(FALSIFY_EXTREME_WINNER)
    if OBS_EXTREME_WINNER_ROBUST in codes or OBS_SENSITIVITY_ROBUST in codes:
        findings = findings  # robustness recorded

    if OBS_NEIGHBORHOOD_UNSTABLE in codes:
        fragility.append("NEIGHBORHOOD_UNSTABLE")
        uncertainties.append("NEIGHBORHOOD_STABILITY")
    if OBS_NEIGHBORHOOD_STABLE in codes:
        findings = findings

    if OBS_MARKET_HETEROGENEOUS in codes:
        context_dep.append("MARKET_STATE")
        uncertainties.append("MARKET_DEPENDENCE")

    if OBS_HORIZON_HETEROGENEOUS in codes:
        horizon_dep.append("HORIZON")
        uncertainties.append("HORIZON_STABILITY")

    if OBS_TRAJECTORY_GROUP_DIFFERENCE in codes:
        uncertainties.append("TRAJECTORY_OR_GROUP_DIFFERENCE")

    # Descriptive strength (computed before gap derivation).
    if tool_result.status == ToolStatus.INSUFFICIENT_DATA:
        strength = DescriptiveStrength.INSUFFICIENT
    elif OBS_NO_VARIATION in codes or tool_result.status == ToolStatus.NO_VARIATION:
        strength = DescriptiveStrength.NO_VARIATION
    elif OBS_NO_CLEAR_DIFFERENCE in codes:
        strength = DescriptiveStrength.NO_CLEAR_DIFFERENCE
    elif OBS_TRAJECTORY_GROUP_DIFFERENCE in codes:
        strength = DescriptiveStrength.GROUP_DIFFERENCE
    else:
        strength = DescriptiveStrength.NO_CLEAR_DIFFERENCE

    interesting = strength == DescriptiveStrength.GROUP_DIFFERENCE and not fragility
    if OBS_MARKET_HETEROGENEOUS in codes or OBS_HORIZON_HETEROGENEOUS in codes:
        interesting = True
    if fragility and (OBS_EXTREME_WINNER_SENSITIVE in codes or OBS_SENSITIVITY_FRAGILE in codes):
        interesting = False

    warrant_gaps = interesting or strength == DescriptiveStrength.GROUP_DIFFERENCE

    # Derive information gaps from what has NOT been tested on branch.
    tested = set(branch_tools)
    if warrant_gaps:
        if GAP_TIME_DISTRIBUTION not in _gaps_closed_by_tools(tested) and "date_decomposition" not in tested:
            if tool_result.tool_name != "date_decomposition":
                gaps.append(GAP_TIME_DISTRIBUTION)
        if GAP_SYMBOL_DISTRIBUTION not in _gaps_closed_by_tools(tested) and "symbol_decomposition" not in tested:
            if tool_result.tool_name != "symbol_decomposition":
                gaps.append(GAP_SYMBOL_DISTRIBUTION)
        if "episode_decomposition" not in tested and tool_result.tool_name != "episode_decomposition":
            gaps.append(GAP_EPISODE_REPLICATION)
        if "market_conditioning" not in tested and tool_result.tool_name != "market_conditioning":
            gaps.append(GAP_MARKET_DEPENDENCE)
        if "horizon_comparison" not in tested and tool_result.tool_name != "horizon_comparison":
            gaps.append(GAP_HORIZON_STABILITY)
        if "sensitivity_analysis" not in tested and tool_result.tool_name != "sensitivity_analysis":
            if OBS_TRAJECTORY_GROUP_DIFFERENCE in codes or tool_result.status == ToolStatus.OK:
                falsify_targets.append(FALSIFY_EXTREME_WINNER)
        if "neighborhood_stability" not in tested and tool_result.tool_name != "neighborhood_stability":
            if OBS_TRAJECTORY_GROUP_DIFFERENCE in codes:
                gaps.append(GAP_NEIGHBORHOOD_STABILITY)
        if "trajectory_partition_compare" not in tested and tool_result.tool_name != "trajectory_partition_compare":
            if OBS_TRAJECTORY_GROUP_DIFFERENCE in codes:
                gaps.append(GAP_TRAJECTORY_ROLE)

    # Contradictions: fragility after prior consistency signals on branch.
    if fragility and OBS_EPISODE_CONSISTENT in branch_obs:
        contradictions.append("FRAGILITY_AFTER_EPISODE_CONSISTENT")

    additional = bool(gaps or (interesting and falsify_targets))
    if strength in (DescriptiveStrength.INSUFFICIENT, DescriptiveStrength.NO_VARIATION):
        additional = False
    if strength == DescriptiveStrength.NO_CLEAR_DIFFERENCE and not gaps:
        additional = False
    if fragility and not gaps:
        additional = False

    confidence = InterpretationConfidence.LOW
    if tool_result.sample_size >= 20 and strength == DescriptiveStrength.GROUP_DIFFERENCE:
        confidence = InterpretationConfidence.MEDIUM
    if tool_result.sample_size >= 50 and not fragility:
        confidence = InterpretationConfidence.HIGH

    return ResearchAssessment(
        source_experiment_node_id=experiment_node_id,
        tool_name=tool_result.tool_name,
        tool_status=tool_result.status.value,
        empirical_findings=findings,
        unresolved_uncertainties=tuple(sorted(set(uncertainties))),
        contradictions=tuple(sorted(set(contradictions))),
        concentration_concerns=tuple(sorted(set(concentration))),
        replication_concerns=tuple(sorted(set(replication))),
        fragility_evidence=tuple(sorted(set(fragility))),
        context_dependence=tuple(sorted(set(context_dep))),
        horizon_dependence=tuple(sorted(set(horizon_dep))),
        information_gaps=tuple(sorted(set(gaps))),
        possible_falsification_targets=tuple(sorted(set(falsify_targets))),
        descriptive_strength=strength.value,
        interpretation_confidence=confidence.value,
        additional_investigation_warranted=additional,
        interesting=interesting,
        validated=False,
        actionable=False,
        branch_tools_attempted=branch_tools,
        branch_observation_codes=branch_obs,
    )


def _gaps_closed_by_tools(tested: Set[str]) -> Set[str]:
    closed: Set[str] = set()
    if "date_decomposition" in tested:
        closed.add(GAP_TIME_DISTRIBUTION)
    if "symbol_decomposition" in tested:
        closed.add(GAP_SYMBOL_DISTRIBUTION)
    return closed
