"""
Executability adapter — maps PropositionRecord to ExperimentSpec validation AFTER synthesis.

May adapt syntax; must not change scientific meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.proposition_record import ExecutabilityStatus, PropositionRecord
from modules.edge_research.research_frame import validate_specs_at_horizon
from modules.edge_research.research_grammar import GrammarValidationError, parse_outcome_spec, parse_population_spec
from modules.edge_research.research_panel_preflight import build_panel_preflight
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import build_default_tool_registry


@dataclass
class ExecutabilityResult:
    status: ExecutabilityStatus
    experiment_spec: Optional[ExperimentSpec]
    detail: str
    adaptation_notes: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "experiment_spec": (
                {
                    "tool_name": self.experiment_spec.tool_name,
                    "tool_version": self.experiment_spec.tool_version,
                    "inputs": dict(self.experiment_spec.inputs),
                    "research_scope": dict(self.experiment_spec.research_scope or {}),
                    "data_cutoff_date": self.experiment_spec.data_cutoff_date,
                }
                if self.experiment_spec
                else None
            ),
            "detail": self.detail,
            "adaptation_notes": list(self.adaptation_notes),
        }


def adapt_executability(
    record: PropositionRecord,
    panel: pd.DataFrame,
) -> ExecutabilityResult:
    """
    Attempt to bind PropositionRecord to legal ExperimentSpec using existing validation.
    """
    feat = record.explanatory_relation.get("feature_or_contrast") or record.execution_requirements.get(
        "partition_column", "rs_spread"
    )
    horizon = record.observation_horizon
    notes = []

    try:
        pop = parse_population_spec(record.population_context)
        out = parse_outcome_spec(record.outcome)
    except GrammarValidationError as exc:
        record.executability_status = ExecutabilityStatus.GRAMMAR_BLOCKED
        return ExecutabilityResult(
            status=ExecutabilityStatus.GRAMMAR_BLOCKED,
            experiment_spec=None,
            detail=str(exc),
            adaptation_notes=tuple(notes),
        )

    try:
        validate_specs_at_horizon(pop, out, observation_horizon=horizon)
    except GrammarValidationError as exc:
        record.executability_status = ExecutabilityStatus.GRAMMAR_BLOCKED
        return ExecutabilityResult(
            status=ExecutabilityStatus.GRAMMAR_BLOCKED,
            experiment_spec=None,
            detail=f"Horizon validation: {exc}",
            adaptation_notes=tuple(notes),
        )

    registry = build_default_tool_registry()
    tool_name = "partition_group_compare"
    try:
        tool = registry.get(tool_name)
        tool_version = tool.metadata.tool_version
    except KeyError:
        record.executability_status = ExecutabilityStatus.TOOL_BLOCKED
        return ExecutabilityResult(
            status=ExecutabilityStatus.TOOL_BLOCKED,
            experiment_spec=None,
            detail=f"Tool {tool_name} not in registry",
            adaptation_notes=tuple(notes),
        )

    preflight = build_panel_preflight(panel)
    if feat not in preflight.partition_columns_available and feat not in panel.columns:
        record.executability_status = ExecutabilityStatus.NOT_EXECUTABLE
        return ExecutabilityResult(
            status=ExecutabilityStatus.NOT_EXECUTABLE,
            experiment_spec=None,
            detail=f"Partition column {feat} not available on panel",
            adaptation_notes=tuple(notes),
        )

    min_sample = record.execution_requirements.get("min_sample", 0)
    if min_sample and len(panel) < min_sample:
        record.executability_status = ExecutabilityStatus.SAMPLE_INSUFFICIENT
        return ExecutabilityResult(
            status=ExecutabilityStatus.SAMPLE_INSUFFICIENT,
            experiment_spec=None,
            detail=f"Panel rows {len(panel)} < min_sample {min_sample}",
            adaptation_notes=tuple(notes),
        )

    research_scope = {
        "population_spec": record.population_context,
        "outcome_spec": record.outcome,
        "observation_horizon": horizon,
        "pending_question_context": {
            "population_spec": record.population_context,
            "outcome_spec": record.outcome,
            "observation_horizon": horizon,
        },
    }

    spec = ExperimentSpec(
        tool_name=tool_name,
        tool_version=tool_version,
        inputs={"partition_column": feat, "n_groups": 5},
        research_scope=research_scope,
        data_cutoff_date=record.observation_provenance.evidence_anchor.get("data_cutoff_date", ""),
    )

    notes.append(f"Syntax adaptation: partition_column={feat}, n_groups=5")

    # Panel preflight via mock candidate is heavy; validate required fields directly
    required = {feat, record.outcome.get("field", "t5_return")}
    missing = required - set(panel.columns)
    if missing:
        record.executability_status = ExecutabilityStatus.NOT_EXECUTABLE
        return ExecutabilityResult(
            status=ExecutabilityStatus.NOT_EXECUTABLE,
            experiment_spec=spec,
            detail=f"Missing panel columns: {sorted(missing)}",
            adaptation_notes=tuple(notes),
        )

    record.executability_status = ExecutabilityStatus.EXECUTABLE
    record.experiment_spec_draft = {
        "tool_name": spec.tool_name,
        "tool_version": spec.tool_version,
        "inputs": dict(spec.inputs),
        "research_scope": dict(spec.research_scope or {}),
        "data_cutoff_date": spec.data_cutoff_date,
    }
    return ExecutabilityResult(
        status=ExecutabilityStatus.EXECUTABLE,
        experiment_spec=spec,
        detail="ExperimentSpec passes grammar and panel column checks",
        adaptation_notes=tuple(notes),
    )
