"""
Phase 3I.9 — Lexicographic falsification selector (no weighted scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.falsification_records import (
    SELECTOR_VERSION,
    EvidenceIndependenceClass,
    FalsificationCandidateRecord,
    SelectionOutcome,
)
from modules.edge_research.opr_bridge.lifecycle_records import stable_hash


DIRECTNESS_ORDER = {
    "directional_reversal": 0,
    "episode_instability": 1,
    "population_concentration": 2,
    "context_instability": 3,
}

INDEPENDENCE_ORDER = {
    EvidenceIndependenceClass.INDEPENDENT_FALSIFICATION.value: 0,
    EvidenceIndependenceClass.RELATED_FALSIFICATION.value: 1,
    EvidenceIndependenceClass.SAME_FALSIFICATION_DIFFERENT_INSTRUMENT.value: 2,
    EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION.value: 9,
}


@dataclass(frozen=True)
class SelectionResult:
    outcome: SelectionOutcome
    selected: Optional[FalsificationCandidateRecord]
    eligible: Tuple[FalsificationCandidateRecord, ...]
    rejected: Tuple[Dict[str, Any], ...]
    ambiguous_tie_ids: Tuple[str, ...]
    reason: str
    selector_version: str = SELECTOR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "selected_candidate_id": self.selected.candidate_id if self.selected else None,
            "selected_record_hash": self.selected.record_hash if self.selected else None,
            "eligible_count": len(self.eligible),
            "rejected_count": len(self.rejected),
            "ambiguous_tie_ids": list(self.ambiguous_tie_ids),
            "reason": self.reason,
            "selector_version": self.selector_version,
        }


def _validity_pass(candidate: FalsificationCandidateRecord) -> Tuple[bool, str]:
    if candidate.evidence_independence_class == EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION.value:
        return False, "not_actually_falsification"
    if candidate.executability_status != "EXECUTABLE":
        return False, f"executability:{candidate.executability_status}"
    if not candidate.content_hash_differs_from_prior:
        return False, "confirmatory_retest_identical_hash"
    if not candidate.counterfactual_falsifiable:
        return False, "counterfactual_falsifiability_failed"
    if candidate.rescue_risk_status != "pass":
        return False, f"anti_rescue:{candidate.rescue_risk_status}"
    return True, "pass"


def _rank_key(candidate: FalsificationCandidateRecord) -> Tuple:
    directness = DIRECTNESS_ORDER.get(candidate.vulnerability_tested, 5)
    independence = INDEPENDENCE_ORDER.get(candidate.evidence_independence_class, 9)
    sample_margin = 0
    if "Cohort n=" in candidate.executability_detail:
        try:
            n = int(candidate.executability_detail.split("Cohort n=")[1].split(" ")[0])
            sample_margin = -n
        except (IndexError, ValueError):
            sample_margin = 0
    return (
        directness,
        independence,
        sample_margin,
        candidate.candidate_id,
    )


def select_falsification_candidate(
    candidates: Sequence[FalsificationCandidateRecord],
) -> SelectionResult:
    """
    Lexicographic selection — no weighted score, no date preference.
    """
    rejected: List[Dict[str, Any]] = []
    eligible: List[FalsificationCandidateRecord] = []

    for c in candidates:
        ok, reason = _validity_pass(c)
        if ok:
            eligible.append(c)
        else:
            rejected.append({"candidate_id": c.candidate_id, "reason": reason})

    if not eligible:
        return SelectionResult(
            outcome=SelectionOutcome.NO_VALID_FALSIFICATION_CANDIDATE,
            selected=None,
            eligible=tuple(),
            rejected=tuple(rejected),
            ambiguous_tie_ids=tuple(),
            reason="No candidate passed validity, counterfactual, anti-rescue, and independence gates",
        )

    ranked = sorted(eligible, key=_rank_key)
    best_key = _rank_key(ranked[0])
    tied = [c for c in ranked if _rank_key(c) == best_key]

    if len(tied) > 1:
        return SelectionResult(
            outcome=SelectionOutcome.AMBIGUOUS_TIE,
            selected=None,
            eligible=tuple(ranked),
            rejected=tuple(rejected),
            ambiguous_tie_ids=tuple(c.candidate_id for c in tied),
            reason=f"Multiple candidates tied after lexicographic criteria: {[c.candidate_id for c in tied]}",
        )

    winner = ranked[0]
    return SelectionResult(
        outcome=SelectionOutcome.SELECTED,
        selected=winner,
        eligible=tuple(ranked),
        rejected=tuple(rejected),
        ambiguous_tie_ids=tuple(),
        reason=(
            f"Selected {winner.candidate_id}: {winner.vulnerability_tested} / "
            f"{winner.evidence_independence_class} — {winner.scientific_rationale[:120]}"
        ),
    )


def selector_content_hash() -> str:
    return stable_hash({"selector_version": SELECTOR_VERSION, "criteria": "lexicographic_v1_3i8"})
