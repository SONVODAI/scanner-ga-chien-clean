"""
Phase 3J.12 — Generic follow-on experiment design gate (ordinal >= 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.follow_on_research_decision_adapter import NormalizedPriorDecision
from modules.edge_research.opr_bridge.second_experiment_design_gate import compute_design_identity_hash
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage

GATE_VERSION = "follow_on_experiment_design_gate_v1_3j12"


@dataclass(frozen=True)
class FollowOnDesignEligibilityResult:
    eligible: bool
    idempotent_replay: bool
    reasons: Tuple[str, ...]
    checks: Dict[str, bool]
    design_identity_hash: Optional[str] = None
    gate_version: str = GATE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "idempotent_replay": self.idempotent_replay,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "design_identity_hash": self.design_identity_hash,
            "gate_version": self.gate_version,
        }


def validate_follow_on_design_eligibility(
    *,
    prop: Dict[str, Any],
    first_package: InitialExperimentPackage,
    first_execution: FirstExperimentExecutionEnvelope,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    prior_decision: NormalizedPriorDecision,
    existing_package: Optional[SecondExperimentPackage] = None,
    experiment_ordinal: int,
) -> FollowOnDesignEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["prior_decision_action"] = prior_decision.is_action
    checks["interpretation_present"] = interpretation_envelope is not None
    checks["birth_package_present"] = first_package is not None
    checks["birth_execution_present"] = first_execution is not None
    checks["experiment_ordinal_valid"] = experiment_ordinal >= 3

    if not checks["prior_decision_action"]:
        return FollowOnDesignEligibilityResult(False, False, ("prior_decision_not_action",), checks)

    rd = prior_decision.research_decision
    design_id = compute_design_identity_hash(
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=prior_decision.research_state_identity,
    )
    checks["proposition_id_matches"] = prior_decision.proposition_id == prop.get("proposition_id")
    checks["interpretation_id_matches"] = (
        interpretation_envelope.interpretation_id == prior_decision.interpretation_id
    )

    if existing_package and existing_package.experiment_ordinal == experiment_ordinal:
        if existing_package.package_hash:
            return FollowOnDesignEligibilityResult(
                True, True, (), checks, design_identity_hash=design_id
            )

    if not checks["interpretation_id_matches"]:
        reasons.append("interpretation_decision_mismatch")

    eligible = all(checks.values()) and not reasons
    return FollowOnDesignEligibilityResult(eligible, False, tuple(reasons), checks, design_id)
