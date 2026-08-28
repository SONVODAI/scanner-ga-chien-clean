"""
Phase 3J.2 — Lexicographic first-experiment selector (pre-result, frozen policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.first_experiment_records import (
    CandidateClassification,
    FirstExperimentCandidateRecord,
    FirstExperimentDisposition,
    SELECTOR_VERSION,
)

_REJECT_CLASSES = frozenset(
    {
        CandidateClassification.RESCUE_MUTATION.value,
        CandidateClassification.NEW_PROPOSITION_REQUIRED.value,
        CandidateClassification.NON_INFORMATIVE.value,
        CandidateClassification.REPRESENTATION_ONLY.value,
        CandidateClassification.REDUNDANT_WITH_BIRTH_EVIDENCE.value,
    }
)

_INDEP_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3, "UNKNOWN": 4}
_EPISTEMIC_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_EXEC_RANK = {"EXECUTABLE": 0, "NOT_EXECUTABLE": 1, "RESCUE_REJECTED": 2, "INVALID": 3}


@dataclass(frozen=True)
class FirstExperimentSelectionResult:
    disposition: str
    selected: Optional[FirstExperimentCandidateRecord]
    eligible: Tuple[FirstExperimentCandidateRecord, ...]
    rejected: Tuple[Dict[str, str], ...]
    ranked: Tuple[FirstExperimentCandidateRecord, ...]
    ranking_trace: Tuple[Dict[str, str], ...]
    ambiguous_tie_ids: Tuple[str, ...]
    reason: str
    selector_version: str = SELECTOR_VERSION

    def to_dict(self) -> Dict[str, object]:
        return {
            "disposition": self.disposition,
            "selected_candidate_id": self.selected.candidate_id if self.selected else None,
            "eligible_count": len(self.eligible),
            "rejected_count": len(self.rejected),
            "ambiguous_tie_ids": list(self.ambiguous_tie_ids),
            "reason": self.reason,
            "selector_version": self.selector_version,
        }


def select_first_experiment(
    candidates: Sequence[FirstExperimentCandidateRecord],
) -> FirstExperimentSelectionResult:
    """
    Frozen lexicographic policy — scientific merit before executability.
    """
    rejected: List[Dict[str, str]] = []
    eligible: List[FirstExperimentCandidateRecord] = []

    has_falsification = any(
        c.primary_classification == CandidateClassification.FALSIFICATION_CAPABLE.value
        for c in candidates
    )

    for c in candidates:
        ok, reason = _eligible(c, has_falsification=has_falsification)
        if ok:
            eligible.append(c)
        else:
            rejected.append(
                {
                    "candidate_id": c.candidate_id,
                    "reason": reason,
                    "classification": c.primary_classification,
                }
            )

    ranked = _rank(eligible)
    trace = tuple(_trace_entry(c) for c in ranked)

    if not eligible:
        return FirstExperimentSelectionResult(
            disposition=FirstExperimentDisposition.NO_HIGH_INFORMATION_FIRST_EXPERIMENT.value,
            selected=None,
            eligible=tuple(),
            rejected=tuple(rejected),
            ranked=tuple(_rank(list(candidates))),
            ranking_trace=trace,
            ambiguous_tie_ids=tuple(),
            reason="No candidate survived scientific gates — valid silence",
        )

    best_key = _rank_key(ranked[0])
    ties = [c for c in ranked if _rank_key(c) == best_key]

    if len(ties) > 1:
        return FirstExperimentSelectionResult(
            disposition=FirstExperimentDisposition.AMBIGUOUS_FIRST_EXPERIMENT.value,
            selected=None,
            eligible=tuple(eligible),
            rejected=tuple(rejected),
            ranked=tuple(ranked),
            ranking_trace=trace,
            ambiguous_tie_ids=tuple(c.candidate_id for c in ties),
            reason=f"Ambiguous tie among {len(ties)} candidates at lexicographic rank {best_key}",
        )

    winner = ranked[0]
    return FirstExperimentSelectionResult(
        disposition=FirstExperimentDisposition.SELECTED.value,
        selected=winner,
        eligible=tuple(eligible),
        rejected=tuple(rejected),
        ranked=tuple(ranked),
        ranking_trace=trace,
        ambiguous_tie_ids=tuple(),
        reason=(
            f"Lexicographic winner: {winner.primary_classification} "
            f"(independence={winner.independence_profile.get('sample_independence')}, "
            f"overlap={winner.birth_evidence_overlap_fraction:.3f})"
        ),
    )


def _eligible(c: FirstExperimentCandidateRecord, *, has_falsification: bool) -> Tuple[bool, str]:
    if c.primary_classification in _REJECT_CLASSES:
        return False, f"rejected_class:{c.primary_classification}"

    if c.primary_classification == CandidateClassification.NOT_EXECUTABLE.value:
        return False, "not_executable"

    if c.confirmatory_only and has_falsification:
        return False, "confirmatory_only_when_falsification_available"

    if c.primary_classification == CandidateClassification.CONFIRMATORY_ONLY.value and has_falsification:
        return False, "confirmatory_only_when_falsification_available"

    if c.rescue_risk_status != "pass":
        return False, f"rescue:{c.rescue_risk_status}"

    if c.executability_status != "EXECUTABLE":
        return False, f"not_executable_status:{c.executability_status}"

    return True, "pass"


def _rank_key(c: FirstExperimentCandidateRecord) -> Tuple:
    falsify = 0 if c.falsification_capable else 1
    indep = _INDEP_RANK.get(c.independence_profile.get("sample_independence", "UNKNOWN"), 4)
    overlap = c.birth_evidence_overlap_fraction
    direct = c.directness_rank
    epistemic = _EPISTEMIC_RANK.get(c.epistemic_alteration_potential, 2)
    exec_rank = _EXEC_RANK.get(c.executability_status, 3)
    cls_rank = (
        0
        if c.primary_classification == CandidateClassification.FALSIFICATION_CAPABLE.value
        else (1 if c.primary_classification == CandidateClassification.DIRECT_INITIAL_TEST.value else 2)
    )
    return (cls_rank, falsify, indep, overlap, direct, epistemic, exec_rank, c.scientific_action_core_hash)


def _rank(candidates: List[FirstExperimentCandidateRecord]) -> List[FirstExperimentCandidateRecord]:
    return sorted(candidates, key=_rank_key)


def _trace_entry(c: FirstExperimentCandidateRecord) -> Dict[str, str]:
    return {
        "candidate_id": c.candidate_id,
        "classification": c.primary_classification,
        "rank_key": str(_rank_key(c)),
        "overlap": f"{c.birth_evidence_overlap_fraction:.3f}",
        "independence": c.independence_profile.get("sample_independence", ""),
        "executability": c.executability_status,
    }
