"""
Phase 3J.6 — Lexicographic second-experiment selector (decision-faithful).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.second_experiment_records import (
    SELECTOR_VERSION,
    SecondExperimentCandidateRecord,
    SecondExperimentDisposition,
)


@dataclass(frozen=True)
class SecondExperimentSelectionResult:
    disposition: str
    selected: Optional[SecondExperimentCandidateRecord]
    eligible: Tuple[SecondExperimentCandidateRecord, ...]
    rejected: Tuple[Dict[str, str], ...]
    ranked: Tuple[SecondExperimentCandidateRecord, ...]
    ranking_trace: Tuple[Dict[str, str], ...]
    reason: str
    selector_version: str = SELECTOR_VERSION

    def to_dict(self) -> Dict[str, object]:
        return {
            "disposition": self.disposition,
            "selected_candidate_id": self.selected.candidate_id if self.selected else None,
            "eligible_count": len(self.eligible),
            "rejected_count": len(self.rejected),
            "reason": self.reason,
            "selector_version": self.selector_version,
        }


def _rank_key(c: SecondExperimentCandidateRecord) -> tuple:
    indep = c.first_experiment_independence_profile.get("sample_independence", "UNKNOWN")
    indep_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3, "UNKNOWN": 4}.get(indep, 4)
    fals_rank = 0 if c.falsification_capability == "FALSIFICATION_CAPABLE" else 1
    return (
        0 if c.primary_classification == "ADMISSIBLE" else 1,
        fals_rank,
        indep_rank,
        c.first_experiment_overlap_fraction,
        c.birth_evidence_overlap_fraction,
        c.scientific_action_core_hash,
    )


def select_second_experiment(
    candidates: Sequence[SecondExperimentCandidateRecord],
) -> SecondExperimentSelectionResult:
    rejected: List[Dict[str, str]] = []
    eligible: List[SecondExperimentCandidateRecord] = []

    for c in candidates:
        if c.primary_classification == "ADMISSIBLE" and c.decision_fidelity_ok and not c.rejection_reasons:
            eligible.append(c)
        else:
            rejected.append(
                {
                    "candidate_id": c.candidate_id,
                    "reasons": "; ".join(c.rejection_reasons) or c.primary_classification,
                    "target_null_key": c.target_null_key,
                    "cohort_strategy": c.scientific_identity.get("cohort_strategy", ""),
                }
            )

    if not eligible:
        return SecondExperimentSelectionResult(
            disposition=SecondExperimentDisposition.NO_FAITHFUL_SECOND_EXPERIMENT.value,
            selected=None,
            eligible=tuple(),
            rejected=tuple(rejected),
            ranked=tuple(sorted(candidates, key=_rank_key)),
            ranking_trace=tuple(),
            reason="No admissible faithful second-experiment design",
        )

    ranked = sorted(eligible, key=_rank_key)
    trace = [
        {
            "candidate_id": c.candidate_id,
            "rank_key": str(_rank_key(c)),
            "falsification_capability": c.falsification_capability,
            "first_overlap": f"{c.first_experiment_overlap_fraction:.3f}",
        }
        for c in ranked
    ]

    top = ranked[0]
    ties = [c for c in ranked if _rank_key(c) == _rank_key(top)]
    if len(ties) > 1:
        return SecondExperimentSelectionResult(
            disposition=SecondExperimentDisposition.AMBIGUOUS_SECOND_EXPERIMENT.value,
            selected=None,
            eligible=tuple(eligible),
            rejected=tuple(rejected),
            ranked=tuple(ranked),
            ranking_trace=tuple(trace),
            reason=f"Ambiguous tie among {len(ties)} faithful designs",
        )

    return SecondExperimentSelectionResult(
        disposition=SecondExperimentDisposition.SELECTED.value,
        selected=top,
        eligible=tuple(eligible),
        rejected=tuple(rejected),
        ranked=tuple(ranked),
        ranking_trace=tuple(trace),
        reason=(
            f"Selected {top.scientific_identity.get('cohort_strategy')} targeting "
            f"{top.target_null_key}; first_overlap={top.first_experiment_overlap_fraction:.3f}"
        ),
    )
