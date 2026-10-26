"""
Phase 3H.8 — Branch-level marginal scientific state.

Derives branch exhaustion/productivity from existing evidence only.
No fixed branch-depth stop rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_realized_information_gain import (
    RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
    RealizedGainLevel,
    get_branch_realized_gain_history,
)

RESEARCH_BRANCH_MARGINAL_STATE_VERSION = "research_branch_marginal_state_v1"


class BranchMarginalState(str, Enum):
    PRODUCTIVE = "PRODUCTIVE"
    DIMINISHING = "DIMINISHING"
    LOW_MARGINAL_VALUE = "LOW_MARGINAL_VALUE"
    EXHAUSTION_EVIDENCE = "EXHAUSTION_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ResearchBranchMarginalState:
    """Auditable branch-level marginal scientific state before next decision."""

    version: str
    branch_root_id: str
    observation_horizon: int
    experiments_on_branch: int
    current_frame_id: str
    unresolved_uncertainty_codes: Tuple[str, ...]
    prior_resolution_attempts: int
    recent_information_value_history: Tuple[float, ...]
    realized_information_gain_history: Tuple[str, ...]
    redundancy_evidence: Tuple[str, ...]
    novelty_evidence: Tuple[str, ...]
    recent_revalued_opportunity_history: Tuple[float, ...]
    marginal_state: str
    marginal_state_reason: str
    planning_sequence: int
    built_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "branch_root_id": self.branch_root_id,
            "observation_horizon": self.observation_horizon,
            "experiments_on_branch": self.experiments_on_branch,
            "current_frame_id": self.current_frame_id,
            "unresolved_uncertainty_codes": list(self.unresolved_uncertainty_codes),
            "prior_resolution_attempts": self.prior_resolution_attempts,
            "recent_information_value_history": list(self.recent_information_value_history),
            "realized_information_gain_history": list(self.realized_information_gain_history),
            "redundancy_evidence": list(self.redundancy_evidence),
            "novelty_evidence": list(self.novelty_evidence),
            "recent_revalued_opportunity_history": list(self.recent_revalued_opportunity_history),
            "marginal_state": self.marginal_state,
            "marginal_state_reason": self.marginal_state_reason,
            "planning_sequence": self.planning_sequence,
            "built_at": self.built_at,
        }


def _recent_iv_contributions(graph: Any, limit: int = 5) -> Tuple[float, ...]:
    trail = list(getattr(graph.session, "research_information_value_audit", None) or [])
    contribs: List[float] = []
    for entry in trail[-limit:]:
        for a in entry.get("candidate_assessments") or []:
            c = a.get("valuation_contribution") or 0
            if c > 0:
                contribs.append(float(c))
    return tuple(contribs[-limit:])


def _recent_revalued_erv(graph: Any, branch_root_id: str, limit: int = 5) -> Tuple[float, ...]:
    trail = list(getattr(graph.session, "research_revalued_erv_history", None) or [])
    vals = [
        float(e.get("selected_erv", 0))
        for e in trail
        if e.get("branch_root_id") == branch_root_id
    ]
    return tuple(vals[-limit:])


def _count_resolution_attempts(assessment: ResearchAssessment) -> int:
    return len(assessment.branch_tools_attempted or ())


def _derive_marginal_state(
    *,
    experiments_on_branch: int,
    realized_levels: List[str],
    revalued_history: Tuple[float, ...],
    unresolved_count: int,
    redundancy_evidence: List[str],
    frame_status: str,
    information_gaps: Tuple[str, ...],
) -> Tuple[str, str]:
    """Evidence-based state — branch depth alone is never sufficient."""
    if experiments_on_branch < 2:
        return (
            BranchMarginalState.INSUFFICIENT_EVIDENCE.value,
            "Fewer than two experiments on branch — insufficient decay evidence",
        )

    exhaustion_score = 0.0
    reasons: List[str] = []

    zero_low = sum(
        1 for g in realized_levels[-4:]
        if g in (RealizedGainLevel.ZERO.value, RealizedGainLevel.LOW.value)
    )
    if zero_low >= 2:
        exhaustion_score += 0.35
        reasons.append(f"{zero_low} recent LOW/ZERO realized gains")

    if len(revalued_history) >= 2 and revalued_history[-1] < 0 and revalued_history[-2] < 0:
        exhaustion_score += 0.25
        reasons.append("recent revalued ERV deteriorating negative")

    if unresolved_count >= 3 and zero_low >= 1:
        exhaustion_score += 0.15
        reasons.append("persistent unresolved uncertainties with low gain")

    if redundancy_evidence:
        exhaustion_score += min(0.25, 0.08 * len(redundancy_evidence))
        reasons.append(f"redundancy evidence: {redundancy_evidence[:3]}")

    if frame_status in ("LOW_YIELD", "EXHAUSTED"):
        exhaustion_score += 0.2
        reasons.append(f"frame status {frame_status}")

    high_recent = sum(1 for g in realized_levels[-3:] if g == RealizedGainLevel.HIGH.value)
    if high_recent >= 2:
        exhaustion_score = max(0.0, exhaustion_score - 0.3)
        reasons.append("recent HIGH realized gains offset exhaustion")

    if len(information_gaps) >= 4 and high_recent == 0 and zero_low < 2:
        exhaustion_score += 0.1
        reasons.append("many open gaps without recent resolution")

    if exhaustion_score >= 0.65:
        state = BranchMarginalState.EXHAUSTION_EVIDENCE.value
    elif exhaustion_score >= 0.45:
        state = BranchMarginalState.LOW_MARGINAL_VALUE.value
    elif exhaustion_score >= 0.2:
        state = BranchMarginalState.DIMINISHING.value
    else:
        state = BranchMarginalState.PRODUCTIVE.value

    reason = "; ".join(reasons) if reasons else "branch continuing productive marginal evidence"
    return state, reason


def build_branch_marginal_state(
    *,
    graph: Any,
    assessment: ResearchAssessment,
    branch_root_id: str,
    experiment_node_id: Optional[str] = None,
    planning_sequence: int = 0,
    semantic_realized_levels: Optional[Tuple[str, ...]] = None,
    semantic_relationship: str = "",
    representation_novelty_only: bool = False,
) -> ResearchBranchMarginalState:
    """Build auditable branch marginal state from evidence available before planning."""
    from modules.edge_research.research_frame import assess_frame_saturation

    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id)
    experiments_on_branch = branch.experiments_on_branch if branch else 0

    realized_history = get_branch_realized_gain_history(graph, branch_root_id)
    branch_levels = [e.get("gain_level", RealizedGainLevel.UNRESOLVED.value) for e in realized_history]
    if semantic_realized_levels is not None:
        realized_levels = list(semantic_realized_levels)
    else:
        realized_levels = branch_levels

    revalued_history = _recent_revalued_erv(graph, branch_root_id)
    iv_history = _recent_iv_contributions(graph)

    unresolved = tuple(sorted(set(assessment.information_gaps) | set(assessment.unresolved_uncertainties)))

    redundancy: List[str] = []
    tools = list(assessment.branch_tools_attempted or ())
    if tools:
        from collections import Counter

        counts = Counter(tools)
        for t, c in counts.items():
            if c >= 2:
                redundancy.append(f"repeated_tool_attempt:{t}x{c}")

    novelty: List[str] = []
    if not representation_novelty_only:
        for g in realized_history[-3:]:
            if g.get("gain_level") in (RealizedGainLevel.HIGH.value, RealizedGainLevel.MEDIUM.value):
                novelty.append(f"experiment:{g.get('experiment_node_id', '')[:12]}")
    if semantic_relationship:
        novelty.append(f"semantic_relationship:{semantic_relationship}")

    frame_id = ""
    frame_status = "ACTIVE"
    reg = graph.get_frame_registry()
    if reg.active_frame_id:
        frame_id = reg.active_frame_id
        frame = reg.get(frame_id)
        if frame:
            frame_status, _ = assess_frame_saturation(frame)

    obs_horizon = 0
    if experiment_node_id:
        exp = graph.get_node(experiment_node_id)
        if exp and exp.experiment_spec:
            scope = exp.experiment_spec.research_scope or {}
            pending = scope.get("pending_question_context") or {}
            obs_horizon = int(pending.get("observation_horizon") or 0)

    marginal_state, reason = _derive_marginal_state(
        experiments_on_branch=experiments_on_branch,
        realized_levels=realized_levels,
        revalued_history=revalued_history,
        unresolved_count=len(unresolved),
        redundancy_evidence=redundancy,
        frame_status=frame_status,
        information_gaps=assessment.information_gaps,
    )

    return ResearchBranchMarginalState(
        version=RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
        branch_root_id=branch_root_id,
        observation_horizon=obs_horizon,
        experiments_on_branch=experiments_on_branch,
        current_frame_id=frame_id,
        unresolved_uncertainty_codes=unresolved,
        prior_resolution_attempts=_count_resolution_attempts(assessment),
        recent_information_value_history=iv_history,
        realized_information_gain_history=tuple(realized_levels[-6:]),
        redundancy_evidence=tuple(redundancy),
        novelty_evidence=tuple(novelty),
        recent_revalued_opportunity_history=revalued_history,
        marginal_state=marginal_state,
        marginal_state_reason=reason,
        planning_sequence=planning_sequence,
    )


def record_branch_marginal_state(graph: Any, state: ResearchBranchMarginalState) -> None:
    trail = list(getattr(graph.session, "research_branch_marginal_audit", None) or [])
    trail.append(state.to_dict())
    graph.session.research_branch_marginal_audit = trail


def record_revalued_erv_snapshot(
    graph: Any,
    *,
    branch_root_id: str,
    selected_erv: float,
    planning_sequence: int,
) -> None:
    trail = list(getattr(graph.session, "research_revalued_erv_history", None) or [])
    trail.append(
        {
            "branch_root_id": branch_root_id,
            "selected_erv": selected_erv,
            "planning_sequence": planning_sequence,
        }
    )
    graph.session.research_revalued_erv_history = trail[-100:]
