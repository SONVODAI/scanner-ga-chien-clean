"""
Phase 3J.9 — Second cumulative research decision eligibility gate (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    FirstExperimentResearchDecisionEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    SecondExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    DECIDER_VERSION,
    GATE_VERSION,
    SecondExperimentResearchDecisionEnvelope,
    compute_second_decision_identity_hash,
)


@dataclass(frozen=True)
class SecondResearchDecisionEligibilityResult:
    eligible: bool
    idempotent_replay: bool
    reasons: Tuple[str, ...]
    checks: Dict[str, bool]
    decision_identity_hash: Optional[str] = None
    gate_version: str = GATE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "idempotent_replay": self.idempotent_replay,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "decision_identity_hash": self.decision_identity_hash,
            "gate_version": self.gate_version,
        }


def validate_second_research_decision_eligibility(
    *,
    interpretation_envelope: SecondExperimentInterpretationEnvelope,
    first_decision_envelope: FirstExperimentResearchDecisionEnvelope,
    existing_decision: Optional[SecondExperimentResearchDecisionEnvelope] = None,
) -> SecondResearchDecisionEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["interpretation_envelope_present"] = interpretation_envelope is not None
    if not checks["interpretation_envelope_present"]:
        return SecondResearchDecisionEligibilityResult(False, False, ("no_interpretation_envelope",), checks)

    checks["first_decision_present"] = first_decision_envelope is not None
    checks["epistemic_update_present"] = bool(interpretation_envelope.epistemic_update)
    checks["base_interpretation_present"] = bool(interpretation_envelope.base_interpretation)
    checks["frozen_contract_present"] = bool(interpretation_envelope.frozen_contract_ref)
    checks["cumulative_assessment_present"] = interpretation_envelope.cumulative_assessment is not None
    checks["experiment_ordinal_is_2"] = interpretation_envelope.experiment_ordinal == 2

    if not checks["first_decision_present"]:
        reasons.append("no_first_decision_envelope")
    if not checks["epistemic_update_present"]:
        reasons.append("no_epistemic_update")
    if not checks["base_interpretation_present"]:
        reasons.append("no_base_interpretation")
    if not checks["frozen_contract_present"]:
        reasons.append("no_frozen_contract")
    if not checks["cumulative_assessment_present"]:
        reasons.append("no_cumulative_assessment")
    if not checks["experiment_ordinal_is_2"]:
        reasons.append("interpretation_not_second_experiment")

    epu = interpretation_envelope.epistemic_update or {}
    decision_id = compute_second_decision_identity_hash(
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
        epistemic_update_hash=str(epu.get("record_hash", "")),
        first_decision_hash=first_decision_envelope.envelope_hash if first_decision_envelope else "",
        decider_version=DECIDER_VERSION,
    )

    if existing_decision is not None:
        checks["idempotent_identity_match"] = (
            existing_decision.interpretation_identity_hash == interpretation_envelope.interpretation_identity_hash
            and existing_decision.epistemic_update_hash == str(epu.get("record_hash", ""))
            and existing_decision.first_decision_hash == first_decision_envelope.envelope_hash
        )
        if checks["idempotent_identity_match"]:
            return SecondResearchDecisionEligibilityResult(
                True, True, ("identical_decision_already_completed",), checks, decision_id
            )
        reasons.append("existing_decision_identity_mismatch")

    material = [k for k in checks if k != "idempotent_identity_match"]
    eligible = all(checks[k] for k in material)
    if not eligible:
        failed = [k for k, v in checks.items() if not v and k != "idempotent_identity_match"]
        return SecondResearchDecisionEligibilityResult(False, False, tuple(reasons or failed), checks, decision_id)

    return SecondResearchDecisionEligibilityResult(True, False, tuple(), checks, decision_id)
