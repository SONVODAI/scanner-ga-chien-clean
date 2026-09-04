"""
Phase 3J.3 — Production first-experiment execution integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    FREEZE_POINT_PRE_EXECUTION,
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import (
    envelope_from_dict,
    lookup_execution_by_identity,
    persist_execution_envelope,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    STOP_FIRST_EXPERIMENT_EXECUTED,
)
from modules.edge_research.opr_bridge.first_experiment_executor import (
    FirstExperimentExecutionResult,
    execute_first_experiment,
)
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

INTEGRATION_VERSION = "production_first_experiment_execution_v1_3j3"


@dataclass
class ProductionFirstExperimentResult:
    integration_version: str = INTEGRATION_VERSION
    package_dict: Optional[Dict[str, Any]] = None
    execution: Optional[FirstExperimentExecutionResult] = None
    frozen_contract_ref: Optional[Dict[str, Any]] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "package": self.package_dict,
            "execution": self.execution.to_dict() if self.execution else None,
            "frozen_contract_ref": self.frozen_contract_ref,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_first_experiment_execution(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    session_id: str,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    existing_package_dict: Optional[Dict[str, Any]] = None,
    existing_execution_dict: Optional[Dict[str, Any]] = None,
) -> ProductionFirstExperimentResult:
    """
    Derive/freeze package (3J.2) → eligibility → execute → persist envelope → STOP.
    """
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", data_cutoff_date)
    executability = ExecutabilityContext.real_partition_for_panel(
        data_cutoff=cutoff, panel=panel
    )

    if existing_package_dict:
        from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict

        package = package_from_dict(existing_package_dict)
    else:
        package = run_first_experiment_pipeline(prop, panel, executability=executability)

    existing_envelope = None
    if existing_execution_dict:
        existing_envelope = envelope_from_dict(existing_execution_dict)

    from modules.edge_research.opr_bridge.first_experiment_execution_gate import (
        compute_execution_identity_hash,
        compute_panel_provenance_hash,
    )
    from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

    exp_hash = ""
    frozen_ref = None
    if package.selected_experiment_spec:
        spec = ExperimentSpec.from_dict(package.selected_experiment_spec)
        exp_hash = compute_experiment_content_hash(spec)
        panel_hash = compute_panel_provenance_hash(panel, data_cutoff_date=cutoff)
        exec_id = compute_execution_identity_hash(
            package_hash=package.package_hash,
            experiment_content_hash=exp_hash,
            panel_provenance_hash=panel_hash,
        )
        cached = lookup_execution_by_identity(exec_id, data_dir=data_dir)
        if cached and existing_envelope is None:
            existing_envelope = cached

        if package.selected_candidate_id:
            core_hash = ""
            for c in package.deduplicated_candidates:
                if c.candidate_id == package.selected_candidate_id:
                    core_hash = c.scientific_action_core_hash
                    break
            frozen_ref = freeze_interpretation_contract_pre_result(
                prop,
                package_id=package.package_id,
                experiment_content_hash=exp_hash,
                scientific_action_core_hash=core_hash,
                freeze_point=FREEZE_POINT_PRE_EXECUTION,
            )
    else:
        frozen_ref = None

    execution = execute_first_experiment(
        package,
        prop,
        panel,
        session_id=session_id,
        executability=executability,
        existing_envelope=existing_envelope,
    )

    idempotent = execution.outcome == "IDEMPOTENT_REPLAY"
    if execution.envelope and not idempotent:
        persist_execution_envelope(execution.envelope, data_dir=data_dir)

    stop = [STOP_FIRST_EXPERIMENT_EXECUTED]
    return ProductionFirstExperimentResult(
        package_dict=execution.package.to_dict() if hasattr(execution.package, "to_dict") else package.to_dict(),
        execution=execution,
        frozen_contract_ref=frozen_ref.to_dict() if frozen_ref else None,
        stop_boundaries=stop,
        idempotent_replay=idempotent,
    )
