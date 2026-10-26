"""
Phase 3K.3 — Forward evidence eligibility gate (LIVE_FORWARD only, fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.production_daily_run_records import (
    LIVE_FORWARD,
    NON_FORWARD_MODES,
    mode_counts_as_forward_evidence,
)
from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import (
    horizon_eligible_on_date,
    reject_early_outcome,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    ForwardEvaluationStatus,
    ResearchObservationBirthRecord,
    ResearchObservationOutcomeRecord,
)


@dataclass(frozen=True)
class ForwardEvidenceEligibilityResult:
    eligible: bool
    reason: str
    checks: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"eligible": self.eligible, "reason": self.reason, "checks": list(self.checks)}


def evaluate_forward_evidence_eligibility(
    *,
    birth: ResearchObservationBirthRecord,
    outcome: ResearchObservationOutcomeRecord,
    run_mode: str,
    run_counts_as_forward_evidence: bool,
    release_trade_date: str,
    birth_existed_before_outcome: bool = True,
    data_integrity_ok: bool = True,
) -> ForwardEvidenceEligibilityResult:
    """
    An observation counts as forward evidence only if all checks pass.
    BACKFILL_NON_FORWARD and HISTORICAL_REPLAY_TEST permanently excluded.
    """
    checks: List[str] = []

    if run_mode in NON_FORWARD_MODES or run_mode != LIVE_FORWARD:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason=f"non_forward_run_mode:{run_mode}",
            checks=("run_mode_not_live_forward",),
        )
    checks.append("run_mode_live_forward")

    if not run_counts_as_forward_evidence or not mode_counts_as_forward_evidence(run_mode):
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason="counts_as_forward_evidence_false",
            checks=tuple(checks + ["counts_as_forward_evidence_false"]),
        )
    checks.append("counts_as_forward_evidence_true")

    if birth.observation_mode in NON_FORWARD_MODES:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason=f"birth_observation_mode_non_forward:{birth.observation_mode}",
            checks=tuple(checks + ["birth_mode_non_forward"]),
        )
    checks.append("birth_mode_forward_capable")

    if not birth_existed_before_outcome:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason="outcome_predates_birth_record",
            checks=tuple(checks + ["birth_temporal_order_violation"]),
        )
    checks.append("birth_before_outcome")

    if reject_early_outcome(outcome.horizon, birth.cutoff.trade_date, release_trade_date):
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason=f"outcome_not_legally_observable:{outcome.horizon}",
            checks=tuple(checks + ["early_outcome_rejected"]),
        )
    checks.append("horizon_legally_eligible")

    if outcome.evaluation_status == ForwardEvaluationStatus.MISSING_DATA.value:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason="missing_data_not_forward_evidence",
            checks=tuple(checks + ["missing_data"]),
        )

    if outcome.evaluation_status not in (
        ForwardEvaluationStatus.EVALUATED.value,
        ForwardEvaluationStatus.SUSPENDED.value,
        ForwardEvaluationStatus.DELISTED.value,
    ):
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason=f"outcome_status_not_eligible:{outcome.evaluation_status}",
            checks=tuple(checks + [f"status_{outcome.evaluation_status}"]),
        )
    checks.append("outcome_status_valid")

    if not data_integrity_ok:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason="data_integrity_failure",
            checks=tuple(checks + ["data_integrity_failed"]),
        )
    checks.append("data_integrity_ok")

    if not birth.cutoff.temporal_provenance_hash:
        return ForwardEvidenceEligibilityResult(
            eligible=False,
            reason="missing_temporal_provenance",
            checks=tuple(checks + ["provenance_missing"]),
        )
    checks.append("temporal_provenance_valid")

    return ForwardEvidenceEligibilityResult(
        eligible=True,
        reason="eligible",
        checks=tuple(checks),
    )


def reject_backfill_as_forward_evidence(run_mode: str) -> Tuple[bool, str]:
    """CF-CAL1 — BACKFILL inserted as forward evidence -> reject."""
    if run_mode in NON_FORWARD_MODES:
        return False, f"rejected_non_forward_mode:{run_mode}"
    return True, "ok"


def reject_replay_mixed_with_live_forward(run_mode: str, ledger_has_live: bool) -> Tuple[bool, str]:
    """CF-CAL15 — replay evidence mixed with LIVE_FORWARD in same authoritative batch."""
    if run_mode in NON_FORWARD_MODES and ledger_has_live:
        return False, "replay_cannot_mix_with_live_forward_batch"
    return True, "ok"
