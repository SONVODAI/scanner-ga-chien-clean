"""
Phase 3J.5 — First-experiment research decision eligibility gate (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    DECIDER_VERSION,
    GATE_VERSION,
    FirstExperimentResearchDecisionEnvelope,
    compute_decision_identity_hash,
)


@dataclass(frozen=True)
class ResearchDecisionEligibilityResult:
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


def validate_research_decision_eligibility(
    *,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    existing_decision: Optional[FirstExperimentResearchDecisionEnvelope] = None,
) -> ResearchDecisionEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["interpretation_envelope_present"] = interpretation_envelope is not None
    if not checks["interpretation_envelope_present"]:
        return ResearchDecisionEligibilityResult(False, False, ("no_interpretation_envelope",), checks)

    checks["epistemic_update_present"] = bool(interpretation_envelope.epistemic_update)
    checks["base_interpretation_present"] = bool(interpretation_envelope.base_interpretation)
    checks["frozen_contract_present"] = bool(interpretation_envelope.frozen_contract_ref)
    checks["evidence_assessment_present"] = interpretation_envelope.evidence_assessment is not None

    if not checks["epistemic_update_present"]:
        reasons.append("no_epistemic_update")
    if not checks["base_interpretation_present"]:
        reasons.append("no_base_interpretation")
    if not checks["frozen_contract_present"]:
        reasons.append("no_frozen_contract")

    epu = interpretation_envelope.epistemic_update or {}
    decision_id = compute_decision_identity_hash(
        interpretation_identity_hash=interpretation_envelope.interpretation_identity_hash,
        epistemic_update_hash=str(epu.get("record_hash", "")),
        decider_version=DECIDER_VERSION,
    )

    if existing_decision is not None:
        checks["idempotent_identity_match"] = (
            existing_decision.interpretation_identity_hash == interpretation_envelope.interpretation_identity_hash
            and existing_decision.epistemic_update_hash == str(epu.get("record_hash", ""))
        )
        if checks["idempotent_identity_match"]:
            return ResearchDecisionEligibilityResult(
                True, True, ("identical_decision_already_completed",), checks, decision_id
            )
        reasons.append("existing_decision_identity_mismatch")

    material = [k for k in checks if k != "idempotent_identity_match"]
    eligible = all(checks[k] for k in material)
    if not eligible:
        failed = [k for k, v in checks.items() if not v and k != "idempotent_identity_match"]
        return ResearchDecisionEligibilityResult(False, False, tuple(reasons or failed), checks, decision_id)

    return ResearchDecisionEligibilityResult(True, False, tuple(), checks, decision_id)
