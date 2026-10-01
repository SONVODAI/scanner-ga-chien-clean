"""
Phase 3J.6 — Production second-experiment design integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.first_experiment_execution_persistence import (
    envelope_from_dict,
    package_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_persistence import (
    decision_envelope_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    STOP_RESEARCH_DECISION_FROZEN,
)
from modules.edge_research.opr_bridge.second_experiment_design_gate import (
    compute_design_identity_hash,
    validate_second_experiment_design_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_design_persistence import (
    lookup_package_by_design_identity,
    persist_second_experiment_package,
)
from modules.edge_research.opr_bridge.second_experiment_pipeline import (
    SecondExperimentDesignResult,
    run_second_experiment_design_pipeline,
)
from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

INTEGRATION_VERSION = "production_second_experiment_design_v1_3j6"


@dataclass
class ProductionSecondExperimentDesignResult:
    integration_version: str = INTEGRATION_VERSION
    design: Optional[SecondExperimentDesignResult] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "design": self.design.to_dict() if self.design else None,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_second_experiment_design(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    session_id: str,
    package_dict: Dict[str, Any],
    execution_dict: Dict[str, Any],
    interpretation_dict: Dict[str, Any],
    decision_dict: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> ProductionSecondExperimentDesignResult:
    """
    STOP_RESEARCH_DECISION_FROZEN → second-experiment design → STOP_SECOND_EXPERIMENT_DESIGNED.
    Does NOT execute Experiment #2.
    """
    first_package = package_from_dict(package_dict)
    first_execution = envelope_from_dict(execution_dict)
    interpretation = interpretation_envelope_from_dict(interpretation_dict)
    decision = decision_envelope_from_dict(decision_dict)

    rd = decision.research_decision
    design_id = compute_design_identity_hash(
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=decision.research_state_identity,
    )
    cached = lookup_package_by_design_identity(design_id, data_dir=data_dir)

    eligibility = validate_second_experiment_design_eligibility(
        prop=prop,
        first_package=first_package,
        first_execution=first_execution,
        interpretation_envelope=interpretation,
        decision_envelope=decision,
        existing_package=cached,
    )

    if cached and eligibility.idempotent_replay:
        return ProductionSecondExperimentDesignResult(
            design=SecondExperimentDesignResult(
                outcome="IDEMPOTENT_REPLAY",
                package=cached,
                stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
                idempotent_replay=True,
            ),
            stop_boundaries=[STOP_RESEARCH_DECISION_FROZEN, STOP_SECOND_EXPERIMENT_DESIGNED],
            idempotent_replay=True,
        )

    if not eligibility.eligible:
        return ProductionSecondExperimentDesignResult(
            design=SecondExperimentDesignResult(
                outcome="NOT_ATTEMPTED",
                package=None,
                stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
                errors=tuple(eligibility.reasons),
            ),
            stop_boundaries=[STOP_SECOND_EXPERIMENT_DESIGNED],
        )

    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)

    result = run_second_experiment_design_pipeline(
        prop,
        panel,
        first_package=first_package,
        first_execution=first_execution,
        interpretation_envelope=interpretation,
        decision_envelope=decision,
        executability=executability,
        existing_package=cached,
    )

    if result.package:
        persist_second_experiment_package(result.package, data_dir=data_dir)

    return ProductionSecondExperimentDesignResult(
        design=result,
        stop_boundaries=[STOP_RESEARCH_DECISION_FROZEN, STOP_SECOND_EXPERIMENT_DESIGNED],
        idempotent_replay=False,
    )
