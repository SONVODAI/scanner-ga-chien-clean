"""
Phase 3J.5 — Production first-experiment research decision integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    STOP_FIRST_EVIDENCE_INTERPRETED,
)
from modules.edge_research.opr_bridge.first_experiment_research_decider import (
    FirstExperimentResearchDecisionResult,
    decide_first_experiment_research_action,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_gate import (
    validate_research_decision_eligibility,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_persistence import (
    lookup_decision_by_identity,
    persist_decision_envelope,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    DECIDER_VERSION,
    STOP_RESEARCH_DECISION_FROZEN,
    compute_decision_identity_hash,
)

INTEGRATION_VERSION = "production_first_experiment_research_decision_v1_3j5"


@dataclass
class ProductionFirstExperimentResearchDecisionResult:
    integration_version: str = INTEGRATION_VERSION
    decision: Optional[FirstExperimentResearchDecisionResult] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "decision": self.decision.to_dict() if self.decision else None,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_first_experiment_research_decision(
    prop: Dict[str, Any],
    *,
    session_id: str,
    package_dict: Dict[str, Any],
    interpretation_dict: Dict[str, Any],
    data_dir: Optional[Path] = None,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> ProductionFirstExperimentResearchDecisionResult:
    """
    STOP_FIRST_EVIDENCE_INTERPRETED → research decision → STOP_RESEARCH_DECISION_FROZEN.
    Does NOT generate or execute a second experiment.
    """
    package = package_from_dict(package_dict)
    interpretation_envelope = interpretation_envelope_from_dict(interpretation_dict)

    eligibility = validate_research_decision_eligibility(
        interpretation_envelope=interpretation_envelope,
    )
    epu = interpretation_envelope.epistemic_update or {}
    decision_id = compute_decision_identity_hash(
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
        epistemic_update_hash=str(epu.get("record_hash", "")),
        decider_version=DECIDER_VERSION,
    )
    cached = lookup_decision_by_identity(decision_id, data_dir=data_dir)

    if cached:
        eligibility = validate_research_decision_eligibility(
            interpretation_envelope=interpretation_envelope,
            existing_decision=cached,
        )
        if eligibility.idempotent_replay:
            return ProductionFirstExperimentResearchDecisionResult(
                decision=FirstExperimentResearchDecisionResult(
                    outcome="IDEMPOTENT_REPLAY",
                    envelope=cached,
                    stop_boundary=STOP_RESEARCH_DECISION_FROZEN,
                ),
                stop_boundaries=[
                    STOP_FIRST_EVIDENCE_INTERPRETED,
                    STOP_RESEARCH_DECISION_FROZEN,
                ],
                idempotent_replay=True,
            )

    if not eligibility.eligible:
        return ProductionFirstExperimentResearchDecisionResult(
            decision=FirstExperimentResearchDecisionResult(
                outcome="NOT_ATTEMPTED",
                envelope=None,
                stop_boundary=STOP_RESEARCH_DECISION_FROZEN,
                errors=tuple(eligibility.reasons),
            ),
            stop_boundaries=[STOP_RESEARCH_DECISION_FROZEN],
        )

    result = decide_first_experiment_research_action(
        prop,
        package,
        interpretation_envelope,
        session_id=session_id,
        complexity_override=complexity_override,
        cardinality_override=cardinality_override,
        budget_exhausted_override=budget_exhausted_override,
    )

    if result.envelope:
        persist_decision_envelope(result.envelope, data_dir=data_dir)

    return ProductionFirstExperimentResearchDecisionResult(
        decision=result,
        stop_boundaries=[STOP_FIRST_EVIDENCE_INTERPRETED, STOP_RESEARCH_DECISION_FROZEN],
        idempotent_replay=False,
    )
