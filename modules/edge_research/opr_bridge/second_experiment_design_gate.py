"""
Phase 3J.6 — Second-experiment design gate (fail closed on stale decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    DECIDER_VERSION,
    FirstExperimentResearchDecisionEnvelope,
    compute_decision_identity_hash,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.second_experiment_records import (
    DESIGN_VERSION,
    SecondExperimentPackage,
)

GATE_VERSION = "second_experiment_design_gate_v1_3j6"


@dataclass(frozen=True)
class SecondExperimentDesignEligibilityResult:
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


def compute_design_identity_hash(
    *,
    research_decision_hash: str,
    research_state_identity: str,
    design_version: str = DESIGN_VERSION,
) -> str:
    from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash

    return stable_hash(
        {
            "research_decision_hash": research_decision_hash,
            "research_state_identity": research_state_identity,
            "design_version": design_version,
        }
    )


def validate_second_experiment_design_eligibility(
    *,
    prop: Dict[str, Any],
    first_package: InitialExperimentPackage,
    first_execution: FirstExperimentExecutionEnvelope,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
    existing_package: Optional[SecondExperimentPackage] = None,
) -> SecondExperimentDesignEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["decision_envelope_present"] = decision_envelope is not None
    checks["interpretation_present"] = interpretation_envelope is not None
    checks["first_package_present"] = first_package is not None
    checks["first_execution_present"] = first_execution is not None

    if not checks["decision_envelope_present"]:
        return SecondExperimentDesignEligibilityResult(False, False, ("no_decision_envelope",), checks)

    rd = decision_envelope.research_decision
    checks["decision_kind_action"] = decision_envelope.decision_kind == "ACTION"
    checks["proposition_id_matches"] = decision_envelope.proposition_id == prop["proposition_id"]
    checks["first_package_id_matches"] = first_package.package_id == first_execution.package_id
    checks["interpretation_id_matches"] = (
        interpretation_envelope.interpretation_id == decision_envelope.interpretation_id
    )
    checks["epistemic_update_hash_matches"] = (
        decision_envelope.epistemic_update_hash == interpretation_envelope.epistemic_update.get("record_hash")
    )

    expected_decision_id = compute_decision_identity_hash(
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
        epistemic_update_hash=str(interpretation_envelope.epistemic_update.get("record_hash", "")),
        decider_version=DECIDER_VERSION,
    )
    actual_decision_id = compute_decision_identity_hash(
        interpretation_identity_hash=decision_envelope.interpretation_identity_hash,
        epistemic_update_hash=decision_envelope.epistemic_update_hash,
        decider_version=DECIDER_VERSION,
    )
    checks["decision_identity_consistent"] = expected_decision_id == actual_decision_id
    checks["research_decision_hash_matches"] = rd.get("record_hash") == rd.get("record_hash")

    if decision_envelope.decision_kind != "ACTION":
        reasons.append("decision_kind_not_action")

    design_id = compute_design_identity_hash(
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=decision_envelope.research_state_identity,
    )

    if existing_package is not None:
        checks["idempotent_identity_match"] = (
            existing_package.research_decision_hash == str(rd.get("record_hash", ""))
            and existing_package.research_state_identity == decision_envelope.research_state_identity
        )
        if checks["idempotent_identity_match"]:
            return SecondExperimentDesignEligibilityResult(
                True, True, ("identical_design_already_completed",), checks, design_id
            )
        return SecondExperimentDesignEligibilityResult(
            False, False, ("existing_design_identity_mismatch",), checks, design_id
        )

    material = [k for k in checks if k != "idempotent_identity_match"]
    eligible = all(checks[k] for k in material if k != "decision_kind_action") and checks.get("decision_kind_action", False)
    if not eligible:
        failed = [k for k, v in checks.items() if not v and k != "idempotent_identity_match"]
        return SecondExperimentDesignEligibilityResult(False, False, tuple(reasons or failed), checks, design_id)

    return SecondExperimentDesignEligibilityResult(True, False, tuple(), checks, design_id)
