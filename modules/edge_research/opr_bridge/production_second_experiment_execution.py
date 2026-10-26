"""
Phase 3J.7 — Production second-experiment execution integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.first_experiment_execution_persistence import envelope_from_dict as first_envelope_from_dict
from modules.edge_research.opr_bridge.first_experiment_research_decision_persistence import (
    decision_envelope_from_dict,
)
from modules.edge_research.opr_bridge.second_experiment_design_persistence import package_from_dict
from modules.edge_research.opr_bridge.second_experiment_execution_persistence import (
    lookup_second_execution_by_identity,
    persist_second_execution_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_execution_records import STOP_SECOND_EXPERIMENT_EXECUTED
from modules.edge_research.opr_bridge.second_experiment_executor import (
    SecondExperimentExecutionResult,
    execute_second_experiment,
)
from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

INTEGRATION_VERSION = "production_second_experiment_execution_v1_3j7"


@dataclass
class ProductionSecondExperimentExecutionResult:
    integration_version: str = INTEGRATION_VERSION
    execution: Optional[SecondExperimentExecutionResult] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "execution": self.execution.to_dict() if self.execution else None,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_second_experiment_execution(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    session_id: str,
    package_dict: Dict[str, Any],
    decision_dict: Dict[str, Any],
    first_execution_dict: Dict[str, Any],
    data_dir: Optional[Path] = None,
    row_overlap_fraction: Optional[float] = None,
) -> ProductionSecondExperimentExecutionResult:
    """
    STOP_SECOND_EXPERIMENT_DESIGNED → eligibility → novelty → execute → STOP_SECOND_EXPERIMENT_EXECUTED.
    Does NOT interpret ToolResult #2.
    """
    package = package_from_dict(package_dict)
    decision = decision_envelope_from_dict(decision_dict)
    first_execution = first_envelope_from_dict(first_execution_dict)

    if row_overlap_fraction is None and package.selected_candidate_id:
        for c in package.deduplicated_candidates:
            if c.candidate_id == package.selected_candidate_id:
                row_overlap_fraction = c.first_experiment_overlap_fraction
                break

    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)

    from modules.edge_research.opr_bridge.first_experiment_execution_gate import (
        compute_execution_identity_hash,
        compute_panel_provenance_hash,
    )
    from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

    existing_envelope = None
    if package.selected_experiment_spec:
        spec = ExperimentSpec.from_dict(package.selected_experiment_spec)
        exp_hash = compute_experiment_content_hash(spec)
        panel_hash = compute_panel_provenance_hash(panel, data_cutoff_date=cutoff)
        exec_id = compute_execution_identity_hash(
            package_hash=package.package_hash,
            experiment_content_hash=exp_hash,
            panel_provenance_hash=panel_hash,
        )
        cached = lookup_second_execution_by_identity(exec_id, data_dir=data_dir)
        if cached:
            existing_envelope = cached

    result = execute_second_experiment(
        package,
        prop,
        panel,
        decision_envelope=decision,
        first_execution=first_execution,
        session_id=session_id,
        executability=executability,
        existing_envelope=existing_envelope,
        row_overlap_fraction=row_overlap_fraction,
    )

    idempotent = result.outcome == "IDEMPOTENT_REPLAY"
    if result.envelope and not idempotent:
        persist_second_execution_envelope(result.envelope, data_dir=data_dir)

    return ProductionSecondExperimentExecutionResult(
        execution=result,
        stop_boundaries=[STOP_SECOND_EXPERIMENT_DESIGNED, STOP_SECOND_EXPERIMENT_EXECUTED],
        idempotent_replay=idempotent,
    )
