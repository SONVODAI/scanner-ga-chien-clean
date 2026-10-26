"""
Phase 3J.13 — History-aware follow-on experiment selector (generic Experiment #N).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentCandidateRecord

SELECTOR_VERSION = "follow_on_experiment_selector_lex_v1_3j13"

NO_FAITHFUL_EXPERIMENT = "NO_FAITHFUL_EXPERIMENT"
AMBIGUOUS_EXPERIMENT = "AMBIGUOUS_EXPERIMENT"
SELECTED = "SELECTED"


@dataclass(frozen=True)
class FollowOnExperimentSelectionResult:
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


def _rank_key(c: SecondExperimentCandidateRecord, *, selected_action: str) -> tuple:
    fidelity = 0 if c.decision_fidelity_ok else 1
    fals_rank = 0 if c.falsification_capability == "FALSIFICATION_CAPABLE" else 1
    if selected_action == "SEEK_REPLICATION":
        fals_rank = 0 if c.falsification_capability != "CONFIRMATION_ONLY" else 1

    indep = c.first_experiment_independence_profile.get("sample_independence", "UNKNOWN")
    indep_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3, "UNKNOWN": 4}.get(indep, 4)

    redundancy_rank = {
        "LOW": 0,
        "HIGH_BIRTH_OVERLAP": 1,
        "HIGH_PRIOR_EXPERIMENT_OVERLAP": 2,
        "HIGH_SCIENTIFIC_REDUNDANCY": 3,
        "HIGH_FIRST_EXPERIMENT_OVERLAP": 2,
    }.get(c.redundancy_assessment, 1)

    exec_rank = 0 if c.executability_status == "EXECUTABLE" else 1

    return (
        fidelity,
        fals_rank,
        redundancy_rank,
        indep_rank,
        c.first_experiment_overlap_fraction,
        c.birth_evidence_overlap_fraction,
        exec_rank,
        c.scientific_action_core_hash,
    )


def select_follow_on_experiment(
    candidates: Sequence[SecondExperimentCandidateRecord],
    *,
    selected_action: str = "SEEK_FALSIFICATION",
) -> FollowOnExperimentSelectionResult:
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
        return FollowOnExperimentSelectionResult(
            disposition=NO_FAITHFUL_EXPERIMENT,
            selected=None,
            eligible=tuple(),
            rejected=tuple(rejected),
            ranked=tuple(sorted(candidates, key=lambda x: _rank_key(x, selected_action=selected_action))),
            ranking_trace=tuple(),
            reason="No admissible faithful follow-on experiment design",
        )

    ranked = sorted(eligible, key=lambda x: _rank_key(x, selected_action=selected_action))
    trace = [
        {
            "candidate_id": c.candidate_id,
            "rank_key": str(_rank_key(c, selected_action=selected_action)),
            "falsification_capability": c.falsification_capability,
            "max_prior_overlap": f"{c.first_experiment_overlap_fraction:.3f}",
            "redundancy": c.redundancy_assessment,
        }
        for c in ranked
    ]

    top = ranked[0]
    top_key = _rank_key(top, selected_action=selected_action)
    ties = [c for c in ranked if _rank_key(c, selected_action=selected_action) == top_key]
    if len(ties) > 1:
        return FollowOnExperimentSelectionResult(
            disposition=AMBIGUOUS_EXPERIMENT,
            selected=None,
            eligible=tuple(eligible),
            rejected=tuple(rejected),
            ranked=tuple(ranked),
            ranking_trace=tuple(trace),
            reason=f"Ambiguous tie among {len(ties)} faithful follow-on designs",
        )

    return FollowOnExperimentSelectionResult(
        disposition=SELECTED,
        selected=top,
        eligible=tuple(eligible),
        rejected=tuple(rejected),
        ranked=tuple(ranked),
        ranking_trace=tuple(trace),
        reason=(
            f"Selected {top.scientific_identity.get('cohort_strategy')} targeting "
            f"{top.target_null_key}; max_prior_overlap={top.first_experiment_overlap_fraction:.3f}"
        ),
    )
