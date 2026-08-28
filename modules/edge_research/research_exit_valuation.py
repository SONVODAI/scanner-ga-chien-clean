"""
Phase 3H.8 — Evidence-based branch exit valuation.

STOP / preserve-budget competes on the same current revalued basis as experiments.
EXIT IS A VALUATION DECISION, NOT A HARD-CODED BEHAVIORAL RULE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.research_branch_marginal_state import (
    RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
    BranchMarginalState,
    ResearchBranchMarginalState,
    build_branch_marginal_state,
    record_branch_marginal_state,
    record_revalued_erv_snapshot,
)
from modules.edge_research.research_realized_information_gain import (
    assess_realized_information_gain,
    record_realized_information_gain,
)

RESEARCH_EXIT_VALUATION_VERSION = "research_exit_valuation_v1"

# Generic scales — not tuned from benchmark outcomes.
BUDGET_OPTION_SCALE = 1.5
EXHAUSTION_PRESERVATION_SCALE = 1.2
REALIZED_DECAY_SCALE = 1.5

_COMPETING_EXIT_STATES = frozenset(
    {
        BranchMarginalState.LOW_MARGINAL_VALUE.value,
        BranchMarginalState.EXHAUSTION_EVIDENCE.value,
    }
)

_MARGINAL_STATE_EXIT_WEIGHT: Dict[str, float] = {
    BranchMarginalState.PRODUCTIVE.value: 0.0,
    BranchMarginalState.DIMINISHING.value: 0.4,
    BranchMarginalState.LOW_MARGINAL_VALUE.value: 1.0,
    BranchMarginalState.EXHAUSTION_EVIDENCE.value: 1.8,
    BranchMarginalState.INSUFFICIENT_EVIDENCE.value: 0.0,
}

from modules.edge_research.exit_valuation_negative_control_tokens import (
    FORBIDDEN_EXIT_TOKENS as _FORBIDDEN_EXIT_TOKENS,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ResearchExitValue:
    """Auditable value of preserving remaining research budget / exiting."""

    version: str
    exit_value: float
    components: Dict[str, float]
    marginal_state: str
    marginal_state_reason: str
    best_experiment_erv: float
    best_local_erv: float
    best_frontier_erv: float
    best_revisit_erv: float
    best_deferred_erv: float
    historical_best_frontier_score: float
    remaining_budget: int
    built_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "exit_value": self.exit_value,
            "components": dict(self.components),
            "marginal_state": self.marginal_state,
            "marginal_state_reason": self.marginal_state_reason,
            "best_experiment_erv": self.best_experiment_erv,
            "best_local_erv": self.best_local_erv,
            "best_frontier_erv": self.best_frontier_erv,
            "best_revisit_erv": self.best_revisit_erv,
            "best_deferred_erv": self.best_deferred_erv,
            "historical_best_frontier_score": self.historical_best_frontier_score,
            "remaining_budget": self.remaining_budget,
            "built_at": self.built_at,
        }


@dataclass(frozen=True)
class ResearchExitDecisionAudit:
    """Counterfactual audit for STOP vs CONTINUE at each planning decision."""

    event: str
    planning_sequence: int
    current_branch_root_id: str
    branch_marginal_state: str
    branch_marginal_reason: str
    best_experiment_source: str
    best_experiment_action_id: str
    best_experiment_erv: float
    best_local_erv: float
    best_frontier_erv: float
    best_revisit_erv: float
    best_deferred_erv: float
    historical_best_frontier_score: float
    exit_value: float
    exit_value_components: Dict[str, float]
    selected_action: str
    stop_competed: bool
    stop_won: bool
    why_selected: str
    runner_up: str
    runner_up_value: float
    opportunity_cost: float
    would_pre_3h8_have_continued: bool
    selection_changed_by_exit_valuation: bool
    alternative_branch_roots: Tuple[str, ...] = field(default_factory=tuple)
    same_structural_branch_notes: Tuple[str, ...] = field(default_factory=tuple)
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "planning_sequence": self.planning_sequence,
            "current_branch_root_id": self.current_branch_root_id,
            "branch_marginal_state": self.branch_marginal_state,
            "branch_marginal_reason": self.branch_marginal_reason,
            "best_experiment_source": self.best_experiment_source,
            "best_experiment_action_id": self.best_experiment_action_id,
            "best_experiment_erv": self.best_experiment_erv,
            "best_local_erv": self.best_local_erv,
            "best_frontier_erv": self.best_frontier_erv,
            "best_revisit_erv": self.best_revisit_erv,
            "best_deferred_erv": self.best_deferred_erv,
            "historical_best_frontier_score": self.historical_best_frontier_score,
            "exit_value": self.exit_value,
            "exit_value_components": dict(self.exit_value_components),
            "selected_action": self.selected_action,
            "stop_competed": self.stop_competed,
            "stop_won": self.stop_won,
            "why_selected": self.why_selected,
            "runner_up": self.runner_up,
            "runner_up_value": self.runner_up_value,
            "opportunity_cost": self.opportunity_cost,
            "would_pre_3h8_have_continued": self.would_pre_3h8_have_continued,
            "selection_changed_by_exit_valuation": self.selection_changed_by_exit_valuation,
            "alternative_branch_roots": list(self.alternative_branch_roots),
            "same_structural_branch_notes": list(self.same_structural_branch_notes),
            "timestamp": self.timestamp,
        }


def compute_research_exit_value(
    *,
    marginal_state: ResearchBranchMarginalState,
    best_experiment_erv: float,
    best_local_erv: float,
    best_frontier_erv: float,
    best_revisit_erv: float,
    best_deferred_erv: float,
    historical_best_frontier_score: float,
    remaining_budget: int,
    experiment_budget: Optional[int],
    features_touched: int,
    eligible_feature_count: int,
    independent_frontier_erv: float = 0.0,
) -> ResearchExitValue:
    """
    Derive exit value from evidence — NOT fixed STOP score or ERV sign rule.
    Conservative when INSUFFICIENT_EVIDENCE.
    """
    components: Dict[str, float] = {}
    state = marginal_state.marginal_state

    if (
        state == BranchMarginalState.INSUFFICIENT_EVIDENCE.value
        or state not in _COMPETING_EXIT_STATES
    ):
        reason_key = (
            "insufficient_evidence"
            if state == BranchMarginalState.INSUFFICIENT_EVIDENCE.value
            else "non_competing_marginal_state"
        )
        return ResearchExitValue(
            version=RESEARCH_EXIT_VALUATION_VERSION,
            exit_value=float("-inf"),
            components={reason_key: 0.0},
            marginal_state=state,
            marginal_state_reason=marginal_state.marginal_state_reason,
            best_experiment_erv=best_experiment_erv,
            best_local_erv=best_local_erv,
            best_frontier_erv=best_frontier_erv,
            best_revisit_erv=best_revisit_erv,
            best_deferred_erv=best_deferred_erv,
            historical_best_frontier_score=historical_best_frontier_score,
            remaining_budget=remaining_budget,
        )

    if remaining_budget <= 0:
        return ResearchExitValue(
            version=RESEARCH_EXIT_VALUATION_VERSION,
            exit_value=float("-inf"),
            components={"budget_exhausted": 0.0},
            marginal_state=state,
            marginal_state_reason=marginal_state.marginal_state_reason,
            best_experiment_erv=best_experiment_erv,
            best_local_erv=best_local_erv,
            best_frontier_erv=best_frontier_erv,
            best_revisit_erv=best_revisit_erv,
            best_deferred_erv=best_deferred_erv,
            historical_best_frontier_score=historical_best_frontier_score,
            remaining_budget=remaining_budget,
        )

    budget_option = 0.0
    if experiment_budget and experiment_budget > 0:
        remaining_ratio = remaining_budget / experiment_budget
        if eligible_feature_count > 0:
            untouched = max(0, eligible_feature_count - features_touched) / eligible_feature_count
            budget_option = remaining_ratio * untouched * BUDGET_OPTION_SCALE
            components["budget_option_value"] = budget_option

    state_weight = _MARGINAL_STATE_EXIT_WEIGHT.get(state, 0.0)
    exhaustion_component = state_weight * EXHAUSTION_PRESERVATION_SCALE
    components["exhaustion_preservation"] = exhaustion_component

    zero_low = sum(
        1 for g in marginal_state.realized_information_gain_history
        if g in ("ZERO", "LOW")
    )
    decay_component = min(1.0, zero_low * 0.25) * REALIZED_DECAY_SCALE
    components["realized_decay"] = decay_component

    if independent_frontier_erv > best_experiment_erv and independent_frontier_erv > 0:
        components["independent_alternative_available"] = -0.5 * independent_frontier_erv

    exit_value = budget_option + exhaustion_component + decay_component
    for k, v in components.items():
        if k == "independent_alternative_available":
            exit_value += v

    return ResearchExitValue(
        version=RESEARCH_EXIT_VALUATION_VERSION,
        exit_value=exit_value,
        components=components,
        marginal_state=state,
        marginal_state_reason=marginal_state.marginal_state_reason,
        best_experiment_erv=best_experiment_erv,
        best_local_erv=best_local_erv,
        best_frontier_erv=best_frontier_erv,
        best_revisit_erv=best_revisit_erv,
        best_deferred_erv=best_deferred_erv,
        historical_best_frontier_score=historical_best_frontier_score,
        remaining_budget=remaining_budget,
    )


def _independent_frontier_erv(
    opportunities: Sequence[Any],
    current_branch_root_id: str,
) -> float:
    best = float("-inf")
    for o in opportunities:
        if not getattr(o, "comparable", True):
            continue
        root = getattr(o, "branch_root_id", "") or ""
        if root and root != current_branch_root_id:
            val = getattr(o, "expected_research_value", float("-inf"))
            if val > best:
                best = val
    return best if best != float("-inf") else 0.0


def evaluate_exit_vs_experiment(
    exit_val: ResearchExitValue,
    best_experiment_erv: float,
) -> bool:
    """STOP wins only when exit value exceeds best experiment — no sign shortcut."""
    if exit_val.exit_value == float("-inf"):
        return False
    return exit_val.exit_value > best_experiment_erv


def build_exit_decision_audit(
    *,
    planning_sequence: int,
    branch_root_id: str,
    marginal_state: ResearchBranchMarginalState,
    exit_val: ResearchExitValue,
    best_experiment_source: str,
    best_experiment_action_id: str,
    best_experiment_erv: float,
    selected_action: str,
    stop_competed: bool,
    stop_won: bool,
    why_selected: str,
    runner_up: str,
    runner_up_value: float,
    opportunity_cost: float,
    would_pre_3h8_continue: bool,
    selection_changed: bool,
    alternative_branch_roots: Tuple[str, ...] = (),
    same_branch_notes: Tuple[str, ...] = (),
) -> ResearchExitDecisionAudit:
    return ResearchExitDecisionAudit(
        event="RESEARCH_EXIT_DECISION_AUDIT",
        planning_sequence=planning_sequence,
        current_branch_root_id=branch_root_id,
        branch_marginal_state=marginal_state.marginal_state,
        branch_marginal_reason=marginal_state.marginal_state_reason,
        best_experiment_source=best_experiment_source,
        best_experiment_action_id=best_experiment_action_id,
        best_experiment_erv=best_experiment_erv,
        best_local_erv=exit_val.best_local_erv,
        best_frontier_erv=exit_val.best_frontier_erv,
        best_revisit_erv=exit_val.best_revisit_erv,
        best_deferred_erv=exit_val.best_deferred_erv,
        historical_best_frontier_score=exit_val.historical_best_frontier_score,
        exit_value=exit_val.exit_value,
        exit_value_components=exit_val.components,
        selected_action=selected_action,
        stop_competed=stop_competed,
        stop_won=stop_won,
        why_selected=why_selected,
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        opportunity_cost=opportunity_cost,
        would_pre_3h8_have_continued=would_pre_3h8_continue,
        selection_changed_by_exit_valuation=selection_changed,
        alternative_branch_roots=alternative_branch_roots,
        same_structural_branch_notes=same_branch_notes,
    )


def record_exit_decision_audit(graph: Any, audit: ResearchExitDecisionAudit) -> None:
    trail = list(getattr(graph.session, "research_exit_decision_audit", None) or [])
    trail.append(audit.to_dict())
    graph.session.research_exit_decision_audit = trail


def prepare_post_experiment_exit_context(
    graph: Any,
    *,
    experiment_node_id: str,
    current_assessment: Any,
    branch_root_id: str,
) -> None:
    """Record realized gain after interpret — before next planning."""
    gain = assess_realized_information_gain(
        graph=graph,
        experiment_node_id=experiment_node_id,
        current_assessment=current_assessment,
        branch_root_id=branch_root_id,
    )
    record_realized_information_gain(graph, gain)
    from modules.edge_research.research_line_registry import assign_and_record_experiment_line

    frame_id = ""
    reg = graph.get_frame_registry()
    if reg.active_frame_id:
        frame_id = reg.active_frame_id
    assign_and_record_experiment_line(
        graph,
        experiment_node_id=experiment_node_id,
        gain_level=gain.gain_level,
        gain_entry=gain.to_dict(),
        frame_id=frame_id,
    )


def validate_no_forbidden_exit_patterns(source: Any) -> List[str]:
    text = str(source).lower()
    return sorted(t for t in _FORBIDDEN_EXIT_TOKENS if t in text)
