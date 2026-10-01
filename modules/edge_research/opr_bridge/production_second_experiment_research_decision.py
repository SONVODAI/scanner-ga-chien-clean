"""
Phase 3J.9 — Production second cumulative research decision integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict as first_interpretation_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_persistence import (
    decision_envelope_from_dict as first_decision_from_dict,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_persistence import (
    second_interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    STOP_SECOND_EVIDENCE_INTERPRETED,
)
from modules.edge_research.opr_bridge.second_experiment_research_decider import (
    SecondExperimentResearchDecisionResult,
    decide_second_experiment_research_action,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_gate import (
    validate_second_research_decision_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_persistence import (
    lookup_decision_by_identity,
    persist_decision_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    DECIDER_VERSION,
    STOP_SECOND_RESEARCH_DECISION_FROZEN,
    compute_second_decision_identity_hash,
)

INTEGRATION_VERSION = "production_second_experiment_research_decision_v1_3j9"


@dataclass
class ProductionSecondExperimentResearchDecisionResult:
    integration_version: str = INTEGRATION_VERSION
    decision: Optional[SecondExperimentResearchDecisionResult] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "decision": self.decision.to_dict() if self.decision else None,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_second_experiment_research_decision(
    prop: Dict[str, Any],
    *,
    session_id: str,
    second_interpretation_dict: Dict[str, Any],
    first_decision_dict: Dict[str, Any],
    first_interpretation_dict: Optional[Dict[str, Any]] = None,
    data_dir: Optional[Path] = None,
    complexity_override: Optional[float] = None,
    cardinality_override: Optional[int] = None,
    budget_exhausted_override: Optional[bool] = None,
) -> ProductionSecondExperimentResearchDecisionResult:
    """
    STOP_SECOND_EVIDENCE_INTERPRETED → Research Decision #2 → STOP_SECOND_RESEARCH_DECISION_FROZEN.
    Does NOT generate or execute Experiment #3.
    """
    second_interpretation = second_interpretation_envelope_from_dict(second_interpretation_dict)
    first_decision = first_decision_from_dict(first_decision_dict)
    first_interpretation = (
        first_interpretation_from_dict(first_interpretation_dict)
        if first_interpretation_dict
        else None
    )

    eligibility = validate_second_research_decision_eligibility(
        interpretation_envelope=second_interpretation,
        first_decision_envelope=first_decision,
    )
    epu = second_interpretation.epistemic_update or {}
    decision_id = compute_second_decision_identity_hash(
        interpretation_identity_hash=second_interpretation.interpretation_identity_hash,
        epistemic_update_hash=str(epu.get("record_hash", "")),
        first_decision_hash=first_decision.envelope_hash,
        decider_version=DECIDER_VERSION,
    )
    cached = lookup_decision_by_identity(decision_id, data_dir=data_dir)

    if cached:
        eligibility = validate_second_research_decision_eligibility(
            interpretation_envelope=second_interpretation,
            first_decision_envelope=first_decision,
            existing_decision=cached,
        )
        if eligibility.idempotent_replay:
            return ProductionSecondExperimentResearchDecisionResult(
                decision=SecondExperimentResearchDecisionResult(
                    outcome="IDEMPOTENT_REPLAY",
                    envelope=cached,
                    stop_boundary=STOP_SECOND_RESEARCH_DECISION_FROZEN,
                ),
                stop_boundaries=[
                    STOP_SECOND_EVIDENCE_INTERPRETED,
                    STOP_SECOND_RESEARCH_DECISION_FROZEN,
                ],
                idempotent_replay=True,
            )

    if not eligibility.eligible:
        return ProductionSecondExperimentResearchDecisionResult(
            decision=SecondExperimentResearchDecisionResult(
                outcome="NOT_ATTEMPTED",
                envelope=None,
                stop_boundary=STOP_SECOND_RESEARCH_DECISION_FROZEN,
                errors=tuple(eligibility.reasons),
            ),
            stop_boundaries=[STOP_SECOND_RESEARCH_DECISION_FROZEN],
        )

    result = decide_second_experiment_research_action(
        prop,
        second_interpretation,
        first_decision,
        session_id=session_id,
        first_interpretation_envelope=first_interpretation,
        complexity_override=complexity_override,
        cardinality_override=cardinality_override,
        budget_exhausted_override=budget_exhausted_override,
    )

    if result.envelope:
        persist_decision_envelope(result.envelope, data_dir=data_dir)

    return ProductionSecondExperimentResearchDecisionResult(
        decision=result,
        stop_boundaries=[STOP_SECOND_EVIDENCE_INTERPRETED, STOP_SECOND_RESEARCH_DECISION_FROZEN],
        idempotent_replay=False,
    )
