"""
Phase 3J.3 — Deterministic research-tool alias resolution (representation only).
"""

from __future__ import annotations

from typing import Tuple

from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry

# Frozen representation aliases — same semantics, different registry name.
REPRESENTATION_TOOL_ALIASES = {
    "tier_compare": "partition_group_compare",
    "flux_decomposition": "date_decomposition",
    "regime_contrast": "market_conditioning",
    "measurement_sensitivity": "sensitivity_analysis",
}


def _tool_in_registry(registry: ToolRegistry, tool_name: str, tool_version: str) -> bool:
    try:
        registry.get(tool_name, tool_version)
        return True
    except KeyError:
        return False


def tool_is_executable(tool_name: str, tool_version: str, registry: ToolRegistry | None = None) -> bool:
    reg = registry or build_default_tool_registry()
    if _tool_in_registry(reg, tool_name, tool_version):
        return True
    alias = REPRESENTATION_TOOL_ALIASES.get(tool_name)
    return bool(alias and _tool_in_registry(reg, alias, tool_version))


def resolve_execution_spec(
    spec: ExperimentSpec,
    registry: ToolRegistry | None = None,
) -> Tuple[ExperimentSpec, Tuple[str, ...]]:
    """
    Resolve frozen spec to registry tool without changing scientific meaning.

    Original spec identity (content hash) remains based on frozen tool_name.
    """
    reg = registry or build_default_tool_registry()
    if _tool_in_registry(reg, spec.tool_name, spec.tool_version):
        return spec, ()
    alias = REPRESENTATION_TOOL_ALIASES.get(spec.tool_name)
    if alias and _tool_in_registry(reg, alias, spec.tool_version):
        resolved = ExperimentSpec(
            tool_name=alias,
            tool_version=spec.tool_version,
            inputs=dict(spec.inputs),
            research_scope=dict(spec.research_scope or {}),
            data_cutoff_date=spec.data_cutoff_date,
        )
        return resolved, (f"representation_alias:{spec.tool_name}->{alias}",)
    return spec, (f"unresolved_tool:{spec.tool_name}",)
