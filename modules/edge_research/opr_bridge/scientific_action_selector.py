"""
Phase 3I.16 — Lexicographic scientific action selector (pre-result).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_records import (
    ActionDisposition,
    ExecutabilityClass,
    RedundancyClass,
    ScientificActionCandidateRecord,
    ScientificObjectiveRecord,
    SELECTOR_VERSION,
)


@dataclass(frozen=True)
class SelectionResult:
    disposition: ActionDisposition
    selected: Optional[ScientificActionCandidateRecord]
    selected_objective: Optional[ScientificObjectiveRecord]
    ranked: Tuple[ScientificActionCandidateRecord, ...]
    eligible: Tuple[ScientificActionCandidateRecord, ...]
    rejected: Tuple[Dict[str, str], ...]
    ambiguous_tie_ids: Tuple[str, ...]
    reason: str
    selector_version: str = SELECTOR_VERSION

    def to_dict(self) -> dict:
        return {
            "disposition": self.disposition.value,
            "selected_candidate_id": self.selected.action_candidate_id if self.selected else None,
            "selected_core_hash": self.selected.scientific_action_core_hash if self.selected else None,
            "ranked_count": len(self.ranked),
            "eligible_count": len(self.eligible),
            "rejected_count": len(self.rejected),
            "ambiguous_tie_ids": list(self.ambiguous_tie_ids),
            "reason": self.reason,
            "selector_version": self.selector_version,
        }


_EXEC_RANK = {
    ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value: 0,
    ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value: 1,
    ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value: 2,
    ExecutabilityClass.REPRESENTATION_ONLY.value: 3,
    ExecutabilityClass.RESCUE_RISK.value: 4,
    ExecutabilityClass.INVALID.value: 5,
}

_REDUNDANCY_RANK = {
    RedundancyClass.NOVEL.value: 0,
    RedundancyClass.MARGINAL.value: 1,
    RedundancyClass.REDUNDANT.value: 2,
}


def select_scientific_action(
    candidates: Sequence[ScientificActionCandidateRecord],
    objectives: Sequence[ScientificObjectiveRecord],
    ctx: ActionGenerationContext,
) -> SelectionResult:
    priority = ctx.priority_action

    if priority == "ABANDON":
        return SelectionResult(
            disposition=ActionDisposition.NO_HIGH_INFORMATION_ACTION,
            selected=None,
            selected_objective=None,
            ranked=tuple(),
            eligible=tuple(),
            rejected=tuple(),
            ambiguous_tie_ids=tuple(),
            reason="ABANDON — no rescue experiments permitted",
        )

    if priority in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"):
        return SelectionResult(
            disposition=ActionDisposition.HOLD,
            selected=None,
            selected_objective=None,
            ranked=tuple(candidates),
            eligible=tuple(),
            rejected=tuple(),
            ambiguous_tie_ids=tuple(),
            reason=f"{priority} — generator must not force experiment selection",
        )

    eligible: List[ScientificActionCandidateRecord] = []
    rejected: List[Dict[str, str]] = []

    for c in candidates:
        ok, reason = _eligible(c, ctx)
        if ok:
            eligible.append(c)
        else:
            rejected.append({"candidate_id": c.action_candidate_id, "reason": reason})

    if not eligible:
        return SelectionResult(
            disposition=ActionDisposition.NO_HIGH_INFORMATION_ACTION,
            selected=None,
            selected_objective=None,
            ranked=tuple(_rank_all(candidates, ctx)),
            eligible=tuple(),
            rejected=tuple(rejected),
            ambiguous_tie_ids=tuple(),
            reason="No eligible high-information executable candidates",
        )

    ranked = _rank_all(eligible, ctx)
    best_key = _rank_key(ranked[0], ctx)
    ties = [c for c in ranked if _rank_key(c, ctx) == best_key]

    if len(ties) > 1:
        return SelectionResult(
            disposition=ActionDisposition.AMBIGUOUS_TIE,
            selected=None,
            selected_objective=_objective_for(ties[0], objectives),
            ranked=tuple(ranked),
            eligible=tuple(eligible),
            rejected=tuple(rejected),
            ambiguous_tie_ids=tuple(c.action_candidate_id for c in ties),
            reason=f"Ambiguous tie among {len(ties)} candidates at rank {best_key}",
        )

    winner = ranked[0]
    return SelectionResult(
        disposition=ActionDisposition.SELECTED,
        selected=winner,
        selected_objective=_objective_for(winner, objectives),
        ranked=tuple(ranked),
        eligible=tuple(eligible),
        rejected=tuple(rejected),
        ambiguous_tie_ids=tuple(),
        reason=f"Lexicographic winner: {winner.action_scientific_semantics[:80]}",
    )


def _eligible(c: ScientificActionCandidateRecord, ctx: ActionGenerationContext) -> Tuple[bool, str]:
    if c.executability_classification == ExecutabilityClass.INVALID.value:
        return False, "invalid"
    if c.executability_classification == ExecutabilityClass.RESCUE_RISK.value:
        return False, "rescue_risk"
    if c.executability_classification == ExecutabilityClass.REPRESENTATION_ONLY.value:
        return False, "representation_only"
    if c.redundancy_classification == RedundancyClass.REDUNDANT.value:
        return False, "redundant"
    if c.executability_classification == ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value:
        return False, "low_information"
    if ctx.priority_action == "SEEK_FALSIFICATION" and not c.falsification_capability:
        return False, "not_falsification"
    if ctx.priority_action == "SEEK_REPLICATION" and c.scientific_action_core.information_gain_type != "replicate":
        return False, "not_replication"
    if ctx.priority_action == "SEEK_CONTRADICTION_RESOLUTION" and not c.contradiction_resolution_capability:
        return False, "not_contradiction_resolution"
    if c.executability_classification != ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value:
        return False, "not_executable"
    if ctx.priority.marginal_information == "low" and ctx.max_cohort_overlap >= 0.95:
        indep = c.expected_independence_profile.get("sample_independence", "")
        if indep != "HIGH" and c.scientific_action_core.cohort_strategy in (
            "full_panel_contrast",
            "episode_holdout_excluding_motivating",
        ):
            return False, "correlated_cohort_low_marginal"
    return True, "pass"


def _rank_key(c: ScientificActionCandidateRecord, ctx: ActionGenerationContext) -> Tuple:
    axis = c.expected_new_uncertainty_coverage
    major = 0 if axis in ctx.major_unresolved else 1
    redundant = _REDUNDANCY_RANK.get(c.redundancy_classification, 2)
    exec_rank = _EXEC_RANK.get(c.executability_classification, 9)
    falsify = 0 if c.falsification_capability and ctx.priority_action == "SEEK_FALSIFICATION" else 1
    contra = 0 if c.contradiction_resolution_capability else 1
    independence = 0 if c.expected_independence_profile.get("sample_independence") == "HIGH" else 1
    return (exec_rank, redundant, major, falsify, contra, independence, axis)


def _rank_all(candidates: Sequence[ScientificActionCandidateRecord], ctx: ActionGenerationContext) -> List[ScientificActionCandidateRecord]:
    return sorted(candidates, key=lambda c: _rank_key(c, ctx))


def _objective_for(
    candidate: ScientificActionCandidateRecord,
    objectives: Sequence[ScientificObjectiveRecord],
) -> Optional[ScientificObjectiveRecord]:
    for o in objectives:
        if o.objective_id == candidate.objective_id:
            return o
    return None
