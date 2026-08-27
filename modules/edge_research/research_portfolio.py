"""
Research portfolio intelligence (Phase 3G.3).

Domain-general allocation among competing research opportunities.
No benchmark tuning, no privileged features, no human-edge encoding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.edge_research.research_actions import ResearchActionCandidate
    from modules.edge_research.research_assessment import ResearchAssessment
    from modules.edge_research.research_frontier import FrontierItem, ResearchFrontier
    from modules.edge_research.research_graph import ResearchGraph

PORTFOLIO_VERSION = "research_portfolio_v1"

# Generic portfolio weights — NOT tuned to any blind benchmark outcome.
WEIGHT_EXPLORATION_DEBT = 2.0
WEIGHT_EXPLOITATION = 2.5
WEIGHT_MARGINAL_GAIN = 3.0
WEIGHT_REVISIT = 2.0
WEIGHT_FALSIFICATION_PORTFOLIO = 3.5
WEIGHT_NOVELTY_PORTFOLIO = 1.5
WEIGHT_REDUNDANCY_DIMINISH = 2.5
WEIGHT_DOMINATED_PENALTY = 500.0
WEIGHT_BUDGET_SCARCITY = 1.0
WEIGHT_SAMPLE_BURDEN = 2.0
WEIGHT_SUNK_COST_AVOID = 2.0

MIG_REDUNDANT_TOOL_FACTOR = 0.15
MIG_REPEAT_FEATURE_FACTOR = 0.35
MIG_NEW_DIMENSION_FACTOR = 1.0
MIG_FLAT_NOISY_FACTOR = 0.1


class BranchPortfolioStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEFERRED_PROMISING = "DEFERRED_PROMISING"
    LOW_VALUE = "LOW_VALUE"
    NEEDS_FALSIFICATION = "NEEDS_FALSIFICATION"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    SATURATED = "SATURATED"
    EXHAUSTED = "EXHAUSTED"
    FALSIFIED = "FALSIFIED"


class OpportunityStatus(str, Enum):
    VIABLE = "VIABLE"
    DOMINATED = "DOMINATED"
    STALE = "STALE"
    DEFERRED = "DEFERRED"


@dataclass
class ResearchOpportunity:
    """Auditable representation of one available research action."""

    opportunity_id: str
    action_id: str
    frame_id: str = ""
    branch_root_id: str = ""
    parent_experiment_id: str = ""
    action_type: str = ""
    transformation_type: str = ""
    target_feature: str = ""
    population_spec_hash: str = ""
    outcome_spec_hash: str = ""
    observation_horizon: int = 0
    base_planner_score: float = 0.0
    evidence_strength: float = 0.0
    novelty: float = 0.0
    falsification_value: float = 0.0
    information_gap: float = 0.0
    exploration_debt: float = 0.0
    exploitation_value: float = 0.0
    marginal_information_gain: float = 0.0
    redundancy: float = 0.0
    branch_depth: int = 0
    complexity_burden: float = 0.0
    sample_loss_burden: float = 0.0
    prior_experiments_in_frame: int = 0
    prior_experiments_in_dimension: int = 0
    revisit_count: int = 0
    last_explored_sequence: int = 0
    expected_research_value: float = 0.0
    status: str = OpportunityStatus.VIABLE.value
    dominated_by: str = ""
    is_revisit: bool = False
    from_frontier: bool = False
    gated_novelty_component: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "action_id": self.action_id,
            "frame_id": self.frame_id,
            "branch_root_id": self.branch_root_id,
            "parent_experiment_id": self.parent_experiment_id,
            "action_type": self.action_type,
            "transformation_type": self.transformation_type,
            "target_feature": self.target_feature,
            "population_spec_hash": self.population_spec_hash,
            "outcome_spec_hash": self.outcome_spec_hash,
            "observation_horizon": self.observation_horizon,
            "base_planner_score": self.base_planner_score,
            "evidence_strength": self.evidence_strength,
            "novelty": self.novelty,
            "falsification_value": self.falsification_value,
            "information_gap": self.information_gap,
            "exploration_debt": self.exploration_debt,
            "exploitation_value": self.exploitation_value,
            "marginal_information_gain": self.marginal_information_gain,
            "redundancy": self.redundancy,
            "branch_depth": self.branch_depth,
            "complexity_burden": self.complexity_burden,
            "sample_loss_burden": self.sample_loss_burden,
            "prior_experiments_in_frame": self.prior_experiments_in_frame,
            "prior_experiments_in_dimension": self.prior_experiments_in_dimension,
            "revisit_count": self.revisit_count,
            "last_explored_sequence": self.last_explored_sequence,
            "expected_research_value": self.expected_research_value,
            "status": self.status,
            "dominated_by": self.dominated_by,
            "is_revisit": self.is_revisit,
            "from_frontier": self.from_frontier,
            "gated_novelty_component": self.gated_novelty_component,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchOpportunity":
        return cls(
            opportunity_id=str(payload.get("opportunity_id", "")),
            action_id=str(payload.get("action_id", "")),
            frame_id=str(payload.get("frame_id", "")),
            branch_root_id=str(payload.get("branch_root_id", "")),
            parent_experiment_id=str(payload.get("parent_experiment_id", "")),
            action_type=str(payload.get("action_type", "")),
            transformation_type=str(payload.get("transformation_type", "")),
            target_feature=str(payload.get("target_feature", "")),
            population_spec_hash=str(payload.get("population_spec_hash", "")),
            outcome_spec_hash=str(payload.get("outcome_spec_hash", "")),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            base_planner_score=float(payload.get("base_planner_score", 0.0)),
            evidence_strength=float(payload.get("evidence_strength", 0.0)),
            novelty=float(payload.get("novelty", 0.0)),
            falsification_value=float(payload.get("falsification_value", 0.0)),
            information_gap=float(payload.get("information_gap", 0.0)),
            exploration_debt=float(payload.get("exploration_debt", 0.0)),
            exploitation_value=float(payload.get("exploitation_value", 0.0)),
            marginal_information_gain=float(payload.get("marginal_information_gain", 0.0)),
            redundancy=float(payload.get("redundancy", 0.0)),
            branch_depth=int(payload.get("branch_depth", 0)),
            complexity_burden=float(payload.get("complexity_burden", 0.0)),
            sample_loss_burden=float(payload.get("sample_loss_burden", 0.0)),
            prior_experiments_in_frame=int(payload.get("prior_experiments_in_frame", 0)),
            prior_experiments_in_dimension=int(payload.get("prior_experiments_in_dimension", 0)),
            revisit_count=int(payload.get("revisit_count", 0)),
            last_explored_sequence=int(payload.get("last_explored_sequence", 0)),
            expected_research_value=float(payload.get("expected_research_value", 0.0)),
            status=str(payload.get("status", OpportunityStatus.VIABLE.value)),
            dominated_by=str(payload.get("dominated_by", "")),
            is_revisit=bool(payload.get("is_revisit", False)),
            from_frontier=bool(payload.get("from_frontier", False)),
            gated_novelty_component=float(payload.get("gated_novelty_component", 0.0)),
        )


@dataclass
class BranchPortfolioRecord:
    """Tracks unresolved value and reservation status for one branch root."""

    branch_root_id: str
    status: str = BranchPortfolioStatus.ACTIVE.value
    unresolved_research_value: float = 0.0
    last_explored_sequence: int = 0
    revisit_count: int = 0
    experiments_on_branch: int = 0
    evidence_before_leave: float = 0.0
    leave_reason: str = ""
    last_marginal_gain: float = 0.0
    falsified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_root_id": self.branch_root_id,
            "status": self.status,
            "unresolved_research_value": self.unresolved_research_value,
            "last_explored_sequence": self.last_explored_sequence,
            "revisit_count": self.revisit_count,
            "experiments_on_branch": self.experiments_on_branch,
            "evidence_before_leave": self.evidence_before_leave,
            "leave_reason": self.leave_reason,
            "last_marginal_gain": self.last_marginal_gain,
            "falsified": self.falsified,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BranchPortfolioRecord":
        return cls(
            branch_root_id=str(payload.get("branch_root_id", "")),
            status=str(payload.get("status", BranchPortfolioStatus.ACTIVE.value)),
            unresolved_research_value=float(payload.get("unresolved_research_value", 0.0)),
            last_explored_sequence=int(payload.get("last_explored_sequence", 0)),
            revisit_count=int(payload.get("revisit_count", 0)),
            experiments_on_branch=int(payload.get("experiments_on_branch", 0)),
            evidence_before_leave=float(payload.get("evidence_before_leave", 0.0)),
            leave_reason=str(payload.get("leave_reason", "")),
            last_marginal_gain=float(payload.get("last_marginal_gain", 0.0)),
            falsified=bool(payload.get("falsified", False)),
        )


@dataclass
class ResearchDecisionExplanation:
    """Compact auditable record for one portfolio selection."""

    selected_opportunity_id: str
    selected_action_id: str
    expected_research_value: float
    selection_reasons: Tuple[str, ...] = field(default_factory=tuple)
    best_alternative_id: str = ""
    best_alternative_value: float = 0.0
    opportunity_cost: float = 0.0
    exploration_component: float = 0.0
    exploitation_component: float = 0.0
    falsification_component: float = 0.0
    novelty_component: float = 0.0
    redundancy_penalty: float = 0.0
    complexity_penalty: float = 0.0
    sample_burden_penalty: float = 0.0
    budget_remaining: int = 0
    is_revisit: bool = False
    why_selected_over_alternative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_opportunity_id": self.selected_opportunity_id,
            "selected_action_id": self.selected_action_id,
            "expected_research_value": self.expected_research_value,
            "selection_reasons": list(self.selection_reasons),
            "best_alternative_id": self.best_alternative_id,
            "best_alternative_value": self.best_alternative_value,
            "opportunity_cost": self.opportunity_cost,
            "exploration_component": self.exploration_component,
            "exploitation_component": self.exploitation_component,
            "falsification_component": self.falsification_component,
            "novelty_component": self.novelty_component,
            "redundancy_penalty": self.redundancy_penalty,
            "complexity_penalty": self.complexity_penalty,
            "sample_burden_penalty": self.sample_burden_penalty,
            "budget_remaining": self.budget_remaining,
            "is_revisit": self.is_revisit,
            "why_selected_over_alternative": self.why_selected_over_alternative,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchDecisionExplanation":
        return cls(
            selected_opportunity_id=str(payload.get("selected_opportunity_id", "")),
            selected_action_id=str(payload.get("selected_action_id", "")),
            expected_research_value=float(payload.get("expected_research_value", 0.0)),
            selection_reasons=tuple(payload.get("selection_reasons") or ()),
            best_alternative_id=str(payload.get("best_alternative_id", "")),
            best_alternative_value=float(payload.get("best_alternative_value", 0.0)),
            opportunity_cost=float(payload.get("opportunity_cost", 0.0)),
            exploration_component=float(payload.get("exploration_component", 0.0)),
            exploitation_component=float(payload.get("exploitation_component", 0.0)),
            falsification_component=float(payload.get("falsification_component", 0.0)),
            novelty_component=float(payload.get("novelty_component", 0.0)),
            redundancy_penalty=float(payload.get("redundancy_penalty", 0.0)),
            complexity_penalty=float(payload.get("complexity_penalty", 0.0)),
            sample_burden_penalty=float(payload.get("sample_burden_penalty", 0.0)),
            budget_remaining=int(payload.get("budget_remaining", 0)),
            is_revisit=bool(payload.get("is_revisit", False)),
            why_selected_over_alternative=str(payload.get("why_selected_over_alternative", "")),
        )


@dataclass
class PortfolioSessionMetrics:
    """Session-level research portfolio diagnostics."""

    experiments_executed: int = 0
    unique_frames_executed: int = 0
    unique_explanatory_dimensions: int = 0
    unique_outcomes_executed: int = 0
    unique_populations_executed: int = 0
    unique_horizons_executed: int = 0
    max_same_frame_depth: int = 0
    independent_branch_count: int = 0
    revisit_count: int = 0
    successful_branch_returns: int = 0
    redundant_experiment_count: int = 0
    dominated_opportunities_skipped: int = 0
    high_value_unexplored_at_end: int = 0
    exploration_debt_at_end: float = 0.0
    candidate_yield: int = 0
    anti_edge_yield: int = 0
    falsification_yield: int = 0
    mean_marginal_information_gain: float = 0.0
    median_marginal_information_gain: float = 0.0
    research_value_consumed_per_experiment: float = 0.0
    unresolved_research_value_at_termination: float = 0.0
    viable_frontier_size: int = 0
    high_value_opportunities: int = 0
    stale_opportunities: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PortfolioSessionMetrics":
        fields = cls.__dataclass_fields__
        return cls(**{k: payload.get(k, fields[k].default) for k in fields})


@dataclass
class PortfolioSessionState:
    """Persistent portfolio accounting for one research session."""

    version: str = PORTFOLIO_VERSION
    sequence_counter: int = 0
    branches: Dict[str, BranchPortfolioRecord] = field(default_factory=dict)
    dimension_experiment_counts: Dict[str, int] = field(default_factory=dict)
    tool_attempt_counts: Dict[str, int] = field(default_factory=dict)
    marginal_gains: List[float] = field(default_factory=list)
    decision_explanations: List[Dict[str, Any]] = field(default_factory=list)
    dominated_skipped: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "sequence_counter": self.sequence_counter,
            "branches": {k: v.to_dict() for k, v in sorted(self.branches.items())},
            "dimension_experiment_counts": dict(sorted(self.dimension_experiment_counts.items())),
            "tool_attempt_counts": dict(sorted(self.tool_attempt_counts.items())),
            "marginal_gains": list(self.marginal_gains),
            "decision_explanations": list(self.decision_explanations),
            "dominated_skipped": self.dominated_skipped,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PortfolioSessionState":
        branches_raw = payload.get("branches") or {}
        return cls(
            version=str(payload.get("version", PORTFOLIO_VERSION)),
            sequence_counter=int(payload.get("sequence_counter", 0)),
            branches={
                k: BranchPortfolioRecord.from_dict(v) for k, v in branches_raw.items()
            },
            dimension_experiment_counts=dict(payload.get("dimension_experiment_counts") or {}),
            tool_attempt_counts=dict(payload.get("tool_attempt_counts") or {}),
            marginal_gains=[float(x) for x in (payload.get("marginal_gains") or [])],
            decision_explanations=list(payload.get("decision_explanations") or []),
            dominated_skipped=int(payload.get("dominated_skipped", 0)),
            metrics=dict(payload.get("metrics") or {}),
        )

    def next_sequence(self) -> int:
        self.sequence_counter += 1
        return self.sequence_counter

    def get_branch(self, branch_root_id: str) -> BranchPortfolioRecord:
        if branch_root_id not in self.branches:
            self.branches[branch_root_id] = BranchPortfolioRecord(branch_root_id=branch_root_id)
        return self.branches[branch_root_id]


def _extract_feature_from_candidate(candidate: "ResearchActionCandidate") -> str:
    if candidate.draft_spec is None:
        return ""
    inputs = candidate.draft_spec.inputs or {}
    for key in ("feature_column", "partition_column", "primary_feature", "trajectory_feature"):
        if key in inputs:
            return str(inputs[key])
    return ""


def _spec_hashes(candidate: "ResearchActionCandidate") -> Tuple[str, str, int]:
    pop_hash = ""
    out_hash = ""
    horizon = 0
    if candidate.draft_spec is None:
        return pop_hash, out_hash, horizon
    scope = candidate.draft_spec.research_scope or {}
    pending = scope.get("pending_question_context") or {}
    if pending.get("population_spec"):
        from modules.edge_research.research_grammar import PopulationSpec
        pop_hash = PopulationSpec.from_dict(pending["population_spec"]).content_hash()
    if pending.get("outcome_spec"):
        from modules.edge_research.research_grammar import OutcomeSpec
        out_hash = OutcomeSpec.from_dict(pending["outcome_spec"]).content_hash()
    horizon = int(pending.get("observation_horizon") or 0)
    return pop_hash, out_hash, horizon


def _dimension_key(feature: str, out_hash: str, pop_hash: str, frame_id: str) -> str:
    parts = [feature or "_", out_hash or "_", pop_hash or "_", frame_id or "_"]
    return "|".join(parts)


def compute_exploration_debt(
    graph: "ResearchGraph",
    *,
    target_feature: str = "",
    outcome_hash: str = "",
    population_hash: str = "",
    frame_id: str = "",
    branch_root_id: str = "",
) -> float:
    """
    Unresolved research opportunity from under-examination — NOT round-robin.

    Higher when a dimension has low relative examination vs session totals.
    """
    from modules.edge_research.research_actions import ActionIntent

    state = graph.get_search_accounting()
    session = state.session_ledger
    preflight = graph.session.panel_preflight or {}
    eligible_features = set(preflight.get("eligible_explanatory") or [])
    portfolio = graph.get_portfolio_state()

    debt = 0.0

    if eligible_features:
        tested = set(session.explanatory_features_tested)
        if target_feature and target_feature not in tested:
            untested_ratio = (len(eligible_features) - len(tested & eligible_features)) / max(
                1, len(eligible_features)
            )
            debt += untested_ratio * WEIGHT_EXPLORATION_DEBT

    reg = graph.get_frame_registry()
    if frame_id and frame_id not in session.unique_research_frames:
        created = len(reg.frames)
        executed = len(session.unique_research_frames)
        if created > executed:
            debt += (created - executed) / max(1, created) * WEIGHT_EXPLORATION_DEBT * 0.5

    if outcome_hash and outcome_hash not in session.unique_outcome_specs:
        debt += WEIGHT_EXPLORATION_DEBT * 0.4

    if population_hash and population_hash not in session.unique_population_specs:
        debt += WEIGHT_EXPLORATION_DEBT * 0.4

    if branch_root_id:
        branch = portfolio.get_branch(branch_root_id)
        if branch.status == BranchPortfolioStatus.DEFERRED_PROMISING.value:
            debt += branch.unresolved_research_value * 0.3

    return debt


def compute_exploitation_value(
    assessment: "ResearchAssessment",
    candidate: "ResearchActionCandidate",
    *,
    branch_record: Optional[BranchPortfolioRecord] = None,
) -> float:
    """Value of deepening an existing promising branch."""
    from modules.edge_research.research_actions import ActionIntent

    if candidate.intent in (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    ):
        return 0.0

    value = 0.0
    hints = candidate.priority_hints

    shape_strength = hints.get("shape_strength") or 0.0
    if shape_strength and float(shape_strength) > 5.0:
        value += min(float(shape_strength) / 20.0, 1.0) * WEIGHT_EXPLOITATION

    if assessment.conditional_candidate:
        value += WEIGHT_EXPLOITATION * 0.6

    if assessment.additional_investigation_warranted:
        value += WEIGHT_EXPLOITATION * 0.4

    if not assessment.concentration_concerns:
        value += WEIGHT_EXPLOITATION * 0.2

    if hints.get("threshold_explore") or hints.get("shape_followup"):
        value += WEIGHT_EXPLOITATION * 0.5

    if branch_record and branch_record.unresolved_research_value > 0:
        value += min(branch_record.unresolved_research_value, WEIGHT_EXPLOITATION)

    return value


def estimate_marginal_information_gain(
    graph: "ResearchGraph",
    candidate: "ResearchActionCandidate",
    assessment: "ResearchAssessment",
    *,
    experiment_node_id: Optional[str] = None,
) -> float:
    """
    Diminishing returns for redundant reconfirmation vs genuinely new evidence.
    """
    from modules.edge_research.research_actions import ActionIntent

    if candidate.intent in (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    ):
        return 0.0

    portfolio = graph.get_portfolio_state()
    feat = _extract_feature_from_candidate(candidate)
    pop_hash, out_hash, _ = _spec_hashes(candidate)
    dim_key = _dimension_key(feat, out_hash, pop_hash, "")

    mig = MIG_NEW_DIMENSION_FACTOR

    tool = candidate.tool_name or candidate.action_code
    prior_tool = portfolio.tool_attempt_counts.get(tool, 0)
    if prior_tool >= 2:
        mig *= MIG_REDUNDANT_TOOL_FACTOR ** (prior_tool - 1)
    elif prior_tool == 1:
        mig *= 0.6

    dim_count = portfolio.dimension_experiment_counts.get(dim_key, 0)
    if dim_count >= 3:
        mig *= MIG_REPEAT_FEATURE_FACTOR ** (dim_count - 2)
    elif dim_count >= 1:
        mig *= 0.7

    if tool in assessment.branch_tools_attempted:
        mig *= MIG_REDUNDANT_TOOL_FACTOR

    codes = set(assessment.branch_observation_codes)
    if "SHAPE_FLAT" in codes or "NO_CLEAR_DIFFERENCE" in codes:
        mig *= MIG_FLAT_NOISY_FACTOR

    if candidate.intent == ActionIntent.FALSIFICATION.value:
        mig = max(mig, 0.8)

    if candidate.intent in (
        ActionIntent.REDESCRIBE_OUTCOME.value,
        ActionIntent.REFRAME.value,
    ):
        mig = max(mig, 0.75)

    scope = candidate.draft_spec.research_scope if candidate.draft_spec else {}
    if scope.get("pending_question_context") or scope.get("frame_transformation"):
        mig = max(mig, 0.85)

    hints = candidate.priority_hints
    if hints.get("shape_followup") or hints.get("threshold_explore"):
        mig = max(mig, 0.9)

    return mig * WEIGHT_MARGINAL_GAIN


def compute_revisit_bonus(
    graph: "ResearchGraph",
    branch_root_id: str,
    *,
    from_frontier: bool = False,
) -> Tuple[float, bool]:
    """Bonus for returning to a deferred promising branch — never forced."""
    if not branch_root_id:
        return 0.0, False
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id)
    if branch.falsified:
        return 0.0, False
    if branch.status != BranchPortfolioStatus.DEFERRED_PROMISING.value:
        return 0.0, False
    if branch.unresolved_research_value <= 0:
        return 0.0, False
    bonus = min(branch.unresolved_research_value, WEIGHT_REVISIT) * (
        1.0 + 0.2 * branch.revisit_count
    )
    is_revisit = from_frontier and branch.experiments_on_branch > 0
    return bonus if is_revisit else bonus * 0.5, is_revisit


def compute_budget_awareness_factor(graph: "ResearchGraph") -> float:
    """Remaining budget modulates value of opening new branches — subordinate to evidence."""
    budget = graph.session.experiment_budget
    if budget is None or budget <= 0:
        return 1.0
    remaining = max(0, budget - graph.session.experiments_used)
    ratio = remaining / budget
    if ratio > 0.5:
        return 1.0
    if ratio > 0.25:
        return 0.95
    if remaining > 1:
        return 0.85
    return 1.1 if remaining == 1 else 0.5


def compute_sample_burden_penalty(candidate: "ResearchActionCandidate") -> float:
    hints = candidate.priority_hints
    sample_pen = hints.get("sample_loss_penalty", 0.0)
    if sample_pen:
        return abs(float(sample_pen)) * WEIGHT_SAMPLE_BURDEN
    return 0.0


def compute_sunk_cost_penalty(
    branch_record: Optional[BranchPortfolioRecord],
    assessment: "ResearchAssessment",
) -> float:
    """Penalize continuing deep flat/noisy branches — avoid sunk-cost digging."""
    if branch_record is None:
        return 0.0
    if branch_record.experiments_on_branch < 4:
        return 0.0
    if branch_record.last_marginal_gain > 0.3:
        return 0.0
    if not assessment.additional_investigation_warranted:
        return WEIGHT_SUNK_COST_AVOID * min(branch_record.experiments_on_branch / 8.0, 1.0)
    return 0.0


def build_opportunity_from_candidate(
    candidate: "ResearchActionCandidate",
    *,
    base_score: float,
    components: Dict[str, float],
    graph: "ResearchGraph",
    assessment: "ResearchAssessment",
    experiment_node_id: Optional[str] = None,
    branch_root_id: str = "",
    from_frontier: bool = False,
    defer_evidence_snapshot: Optional[Dict[str, Any]] = None,
) -> ResearchOpportunity:
    """Construct auditable opportunity from planner candidate."""
    from modules.edge_research.research_search_accounting import branch_depth as accounting_branch_depth

    feat = _extract_feature_from_candidate(candidate)
    pop_hash, out_hash, horizon = _spec_hashes(candidate)
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id) if branch_root_id else None

    scope = candidate.draft_spec.research_scope if candidate.draft_spec else {}
    frame_id = str(
        (scope.get("pending_question_context") or {}).get("frame_id")
        or scope.get("frame_id")
        or ""
    )
    transformation = str(scope.get("frame_transformation") or "")

    exp_debt = compute_exploration_debt(
        graph,
        target_feature=feat,
        outcome_hash=out_hash,
        population_hash=pop_hash,
        frame_id=frame_id,
        branch_root_id=branch_root_id,
    )
    exploit = compute_exploitation_value(assessment, candidate, branch_record=branch)
    mig = estimate_marginal_information_gain(
        graph, candidate, assessment, experiment_node_id=experiment_node_id
    )
    revisit_bonus, is_revisit = compute_revisit_bonus(
        graph, branch_root_id, from_frontier=from_frontier
    )

    redundancy = abs(float(components.get("redundancy_penalty", 0.0)))
    fals_val = float(components.get("falsification_threat", 0.0))
    novelty = float(components.get("novelty", 0.0))
    info_gap = float(components.get("information_gap", 0.0))
    complexity = abs(
        float(components.get("search_complexity_penalty", 0.0))
        + float(components.get("draft_complexity_penalty", 0.0))
    )
    sample_pen = compute_sample_burden_penalty(candidate)
    sunk = compute_sunk_cost_penalty(branch, assessment)

    depth = 0
    if experiment_node_id and experiment_node_id in graph.nodes:
        depth = accounting_branch_depth(graph, experiment_node_id)

    dim_key = _dimension_key(feat, out_hash, pop_hash, frame_id)
    prior_dim = portfolio.dimension_experiment_counts.get(dim_key, 0)

    reg = graph.get_frame_registry()
    frame = reg.get(frame_id) if frame_id else None
    prior_frame = frame.experiments_in_frame if frame else 0

    budget_factor = compute_budget_awareness_factor(graph)

    exploration_component = exp_debt + (revisit_bonus if is_revisit else revisit_bonus * 0.5)
    exploitation_component = exploit
    falsification_component = fals_val * (WEIGHT_FALSIFICATION_PORTFOLIO / 4.0)
    novelty_component = novelty * (WEIGHT_NOVELTY_PORTFOLIO / 2.0)

    from modules.edge_research.research_line_freshness import EvidenceSnapshot
    from modules.edge_research.research_novelty_valuation_bridge import (
        apply_novelty_valuation_bridge,
        record_novelty_gating_audit,
    )

    defer_snap = (
        EvidenceSnapshot.from_dict(defer_evidence_snapshot)
        if defer_evidence_snapshot
        else None
    )
    novelty_component, gating_audit = apply_novelty_valuation_bridge(
        graph,
        candidate,
        assessment,
        raw_novelty_component=novelty_component,
        branch_root_id=branch_root_id,
        defer_snapshot=defer_snap,
    )
    record_novelty_gating_audit(graph, gating_audit)

    from modules.edge_research.research_novelty_rank_reconciliation import (
        reconcile_planner_novelty_in_base_score,
        record_rank_reconciliation_audit,
    )

    reconciled_base, rank_audit = reconcile_planner_novelty_in_base_score(
        base_score,
        novelty,
        gating_audit,
    )
    record_rank_reconciliation_audit(graph, rank_audit)
    redundancy_penalty = redundancy * WEIGHT_REDUNDANCY_DIMINISH / 3.0

    expected = (
        reconciled_base
        + exploration_component
        + exploitation_component
        + mig
        + falsification_component
        + novelty_component
        - redundancy_penalty
        - complexity * 0.1
        - sample_pen
        - sunk
    ) * budget_factor

    if branch and branch.falsified:
        expected = min(expected, -100.0)

    opp_id = candidate.action_id
    return ResearchOpportunity(
        opportunity_id=opp_id,
        action_id=candidate.action_id,
        frame_id=frame_id,
        branch_root_id=branch_root_id,
        parent_experiment_id=experiment_node_id or "",
        action_type=candidate.intent,
        transformation_type=transformation,
        target_feature=feat,
        population_spec_hash=pop_hash,
        outcome_spec_hash=out_hash,
        observation_horizon=horizon,
        base_planner_score=base_score,
        evidence_strength=exploit,
        novelty=novelty,
        falsification_value=fals_val,
        information_gap=info_gap,
        exploration_debt=exp_debt,
        exploitation_value=exploit,
        marginal_information_gain=mig,
        redundancy=redundancy,
        branch_depth=depth,
        complexity_burden=complexity,
        sample_loss_burden=sample_pen,
        prior_experiments_in_frame=prior_frame,
        prior_experiments_in_dimension=prior_dim,
        revisit_count=branch.revisit_count if branch else 0,
        last_explored_sequence=branch.last_explored_sequence if branch else 0,
        expected_research_value=expected,
        is_revisit=is_revisit,
        from_frontier=from_frontier,
        gated_novelty_component=novelty_component,
    )


def mark_dominated_opportunities(
    opportunities: Sequence[ResearchOpportunity],
) -> List[ResearchOpportunity]:
    """
    Conservatively mark dominated opportunities — preserve audit history.
    A dominates B if A has >= info value, <= complexity, <= redundancy, no worse novelty.
    """
    from modules.edge_research.research_actions import ActionIntent

    terminal_intents = {
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    }
    result = [ResearchOpportunity(**{**o.to_dict()}) for o in opportunities]
    viable = [
        o for o in result
        if o.status == OpportunityStatus.VIABLE.value
        and o.action_type not in terminal_intents
    ]

    for i, a in enumerate(viable):
        for j, b in enumerate(viable):
            if i == j:
                continue
            if (
                a.expected_research_value >= b.expected_research_value
                and a.complexity_burden <= b.complexity_burden + 0.01
                and a.redundancy <= b.redundancy + 0.01
                and a.marginal_information_gain >= b.marginal_information_gain - 0.1
                and (
                    a.complexity_burden < b.complexity_burden - 0.01
                    or a.redundancy < b.redundancy - 0.01
                    or a.marginal_information_gain > b.marginal_information_gain + 0.1
                )
            ):
                for o in result:
                    if o.action_id == b.action_id and o.status == OpportunityStatus.VIABLE.value:
                        o.status = OpportunityStatus.DOMINATED.value
                        o.dominated_by = a.action_id
    return result


def portfolio_score_adjustments(
    candidate: "ResearchActionCandidate",
    assessment: "ResearchAssessment",
    graph: "ResearchGraph",
    *,
    base_score: float,
    components: Dict[str, float],
    experiment_node_id: Optional[str] = None,
    branch_root_id: str = "",
) -> Tuple[float, Dict[str, float], ResearchOpportunity]:
    """Compute portfolio layer adjustments for one candidate."""
    opp = build_opportunity_from_candidate(
        candidate,
        base_score=base_score,
        components=components,
        graph=graph,
        assessment=assessment,
        experiment_node_id=experiment_node_id,
        branch_root_id=branch_root_id,
    )
    portfolio_components = {
        "exploration_debt_bonus": opp.exploration_debt,
        "exploitation_value_bonus": opp.exploitation_value,
        "marginal_information_gain": opp.marginal_information_gain,
        "portfolio_falsification": opp.falsification_value * (WEIGHT_FALSIFICATION_PORTFOLIO / 4.0),
        "portfolio_novelty": opp.gated_novelty_component,
        "portfolio_redundancy_penalty": -opp.redundancy * WEIGHT_REDUNDANCY_DIMINISH / 3.0,
        "portfolio_sample_burden": -opp.sample_loss_burden,
        "portfolio_revisit_bonus": compute_revisit_bonus(graph, branch_root_id)[0],
    }
    adjustment = sum(portfolio_components.values()) - base_score + opp.expected_research_value
    # expected_research_value already includes base; return delta only
    delta = opp.expected_research_value - base_score
    return delta, portfolio_components, opp


def build_decision_explanation(
    selected: ResearchOpportunity,
    alternatives: Sequence[ResearchOpportunity],
    *,
    budget_remaining: int,
    portfolio_components: Dict[str, float],
) -> ResearchDecisionExplanation:
    """Build auditable decision record."""
    viable = [a for a in alternatives if a.status != OpportunityStatus.DOMINATED.value]
    viable_sorted = sorted(viable, key=lambda o: (-o.expected_research_value, o.action_id))
    best_alt = None
    for alt in viable_sorted:
        if alt.action_id != selected.action_id:
            best_alt = alt
            break

    best_alt_value = best_alt.expected_research_value if best_alt else 0.0
    best_alt_id = best_alt.action_id if best_alt else ""
    opp_cost = max(0.0, best_alt_value - selected.expected_research_value) if best_alt else 0.0

    reasons: List[str] = []
    if selected.exploitation_value > 1.0:
        reasons.append("EXPLOITATION_VALUE")
    if selected.exploration_debt > 0.5:
        reasons.append("EXPLORATION_DEBT")
    if selected.marginal_information_gain > 1.5:
        reasons.append("MARGINAL_INFORMATION_GAIN")
    if selected.falsification_value > 2.0:
        reasons.append("FALSIFICATION")
    if selected.is_revisit:
        reasons.append("BRANCH_REVISIT")
    if selected.novelty > 1.0:
        reasons.append("NOVELTY")
    if not reasons:
        reasons.append("BASE_PLANNER_SCORE")

    why = ""
    if best_alt:
        why = (
            f"selected ERV={selected.expected_research_value:.3f} over "
            f"alternative {best_alt_id} ERV={best_alt_value:.3f}"
        )
    else:
        why = f"selected ERV={selected.expected_research_value:.3f}; no viable alternative"

    return ResearchDecisionExplanation(
        selected_opportunity_id=selected.opportunity_id,
        selected_action_id=selected.action_id,
        expected_research_value=selected.expected_research_value,
        selection_reasons=tuple(reasons),
        best_alternative_id=best_alt_id,
        best_alternative_value=best_alt_value,
        opportunity_cost=opp_cost,
        exploration_component=selected.exploration_debt,
        exploitation_component=selected.exploitation_value,
        falsification_component=selected.falsification_value,
        novelty_component=selected.novelty,
        redundancy_penalty=selected.redundancy,
        complexity_penalty=selected.complexity_burden,
        sample_burden_penalty=selected.sample_loss_burden,
        budget_remaining=budget_remaining,
        is_revisit=selected.is_revisit,
        why_selected_over_alternative=why,
    )


def update_branch_on_experiment(
    graph: "ResearchGraph",
    *,
    branch_root_id: str,
    assessment: "ResearchAssessment",
    marginal_gain: float,
    unresolved_value: float,
) -> None:
    """Update branch portfolio record after an experiment."""
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id)
    seq = portfolio.next_sequence()
    branch.last_explored_sequence = seq
    branch.experiments_on_branch += 1
    branch.last_marginal_gain = marginal_gain
    branch.unresolved_research_value = unresolved_value

    if assessment.fragility_evidence and not assessment.additional_investigation_warranted:
        branch.status = BranchPortfolioStatus.FALSIFIED.value
        branch.falsified = True
        branch.unresolved_research_value = 0.0
    elif assessment.conditional_candidate and assessment.additional_investigation_warranted:
        branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    elif marginal_gain < 0.2 and branch.experiments_on_branch >= 3:
        branch.status = BranchPortfolioStatus.SATURATED.value
    elif unresolved_value > 1.0:
        branch.status = BranchPortfolioStatus.ACTIVE.value
    else:
        branch.status = BranchPortfolioStatus.LOW_VALUE.value

    portfolio.marginal_gains.append(marginal_gain)
    graph.persist_portfolio_state()


def update_branch_on_leave(
    graph: "ResearchGraph",
    *,
    branch_root_id: str,
    unresolved_value: float,
    reason: str = "STOP_BRANCH",
) -> None:
    """Preserve promising branch when leaving for another opportunity."""
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id)
    branch.evidence_before_leave = branch.unresolved_research_value
    branch.unresolved_research_value = unresolved_value
    branch.leave_reason = reason
    if branch.falsified:
        return
    if unresolved_value >= 1.0 and branch.status != BranchPortfolioStatus.SATURATED.value:
        branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    graph.persist_portfolio_state()


def record_branch_revisit(graph: "ResearchGraph", branch_root_id: str) -> None:
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_root_id)
    if branch.falsified:
        return
    branch.revisit_count += 1
    branch.status = BranchPortfolioStatus.ACTIVE.value
    graph.persist_portfolio_state()


def record_dimension_experiment(
    graph: "ResearchGraph",
    *,
    feature: str,
    outcome_hash: str,
    population_hash: str,
    frame_id: str,
    tool: str,
) -> None:
    portfolio = graph.get_portfolio_state()
    dim_key = _dimension_key(feature, outcome_hash, population_hash, frame_id)
    portfolio.dimension_experiment_counts[dim_key] = (
        portfolio.dimension_experiment_counts.get(dim_key, 0) + 1
    )
    portfolio.tool_attempt_counts[tool] = portfolio.tool_attempt_counts.get(tool, 0) + 1
    graph.persist_portfolio_state()


def compute_session_portfolio_metrics(graph: "ResearchGraph") -> PortfolioSessionMetrics:
    """Aggregate session-level portfolio diagnostics."""
    from modules.edge_research.research_search_accounting import branch_root_id

    state = graph.get_search_accounting()
    session = state.session_ledger
    portfolio = graph.get_portfolio_state()
    frontier = graph.get_frontier()

    unexplored = frontier.unexplored_items()
    high_value = sum(1 for i in unexplored if i.planner_score > 2.0)
    stale = sum(
        1
        for i in unexplored
        if i.status == "UNEXPLORED" and portfolio.sequence_counter - getattr(i, "enqueued_sequence", 0) > 5
    )

    horizons: Set[int] = set()
    for node in graph.nodes.values():
        if node.node_type.value != "EXPERIMENT":
            continue
        for pid in node.parent_node_ids:
            parent = graph.nodes.get(pid)
            if parent and parent.question_context:
                horizons.add(parent.question_context.observation_horizon)

    branch_roots = set()
    for node in graph.nodes.values():
        if node.node_type.value == "EXPERIMENT":
            branch_roots.add(branch_root_id(graph, node.node_id))

    gains = portfolio.marginal_gains or [0.0]
    sorted_gains = sorted(gains)
    mid = len(sorted_gains) // 2
    median_mig = sorted_gains[mid] if sorted_gains else 0.0

    deferred = [
        b for b in portfolio.branches.values()
        if b.status == BranchPortfolioStatus.DEFERRED_PROMISING.value
    ]
    unresolved = sum(b.unresolved_research_value for b in portfolio.branches.values())

    revisits = sum(b.revisit_count for b in portfolio.branches.values())

    return PortfolioSessionMetrics(
        experiments_executed=session.experiments_executed,
        unique_frames_executed=len(session.unique_research_frames),
        unique_explanatory_dimensions=len(session.explanatory_features_tested),
        unique_outcomes_executed=len(session.unique_outcome_specs),
        unique_populations_executed=len(session.unique_population_specs),
        unique_horizons_executed=len(horizons),
        max_same_frame_depth=session.branch_depth_max,
        independent_branch_count=len(branch_roots),
        revisit_count=revisits,
        successful_branch_returns=revisits,
        redundant_experiment_count=sum(
            1 for g in gains if g < 0.2
        ),
        dominated_opportunities_skipped=portfolio.dominated_skipped,
        high_value_unexplored_at_end=high_value,
        exploration_debt_at_end=sum(
            compute_exploration_debt(graph, target_feature=f)
            for f in (graph.session.panel_preflight or {}).get("eligible_explanatory") or []
        ),
        falsification_yield=session.falsification_experiments_executed,
        mean_marginal_information_gain=sum(gains) / max(1, len(gains)),
        median_marginal_information_gain=median_mig,
        research_value_consumed_per_experiment=sum(gains) / max(1, session.experiments_executed),
        unresolved_research_value_at_termination=unresolved,
        viable_frontier_size=len(unexplored),
        high_value_opportunities=high_value,
        stale_opportunities=stale,
    )


def score_opportunities_for_selection(
    graph: "ResearchGraph",
    assessment: "ResearchAssessment",
    candidates: Sequence["ResearchActionCandidate"],
    base_scores: Dict[str, Tuple[float, Dict[str, float]]],
    *,
    experiment_node_id: Optional[str] = None,
    branch_root_id: str = "",
    use_information_value_bridge: bool = True,
) -> Tuple[List[ResearchOpportunity], Dict[str, Tuple[float, Dict[str, float]]]]:
    """Score all candidates with portfolio layer; return opportunities and adjusted scores."""
    from modules.edge_research.research_search_accounting import branch_root_id as _branch_root

    root = branch_root_id or (
        _branch_root(graph, experiment_node_id) if experiment_node_id else ""
    )

    bridged_scores = base_scores
    iv_assessments: List[Any] = []
    if use_information_value_bridge:
        from modules.edge_research.research_information_value import apply_information_value_bridge

        bridged_scores, iv_assessments = apply_information_value_bridge(
            base_scores,
            graph=graph,
            assessment=assessment,
            candidates=candidates,
            experiment_node_id=experiment_node_id,
            branch_root_id=root,
        )
        if experiment_node_id and iv_assessments:
            graph._pending_information_value_assessments = iv_assessments  # noqa: SLF001
            graph._pending_information_value_base_scores = base_scores  # noqa: SLF001
            graph._pending_information_value_bridged_scores = bridged_scores  # noqa: SLF001

    opportunities: List[ResearchOpportunity] = []
    adjusted: Dict[str, Tuple[float, Dict[str, float]]] = {}

    for cand in candidates:
        base, comp = bridged_scores.get(cand.action_id, (0.0, {}))
        delta, port_comp, opp = portfolio_score_adjustments(
            cand,
            assessment,
            graph,
            base_score=base,
            components=comp,
            experiment_node_id=experiment_node_id,
            branch_root_id=root,
        )
        merged_comp = {**comp, **port_comp}
        adjusted[cand.action_id] = (opp.expected_research_value, merged_comp)
        opportunities.append(opp)

    opportunities = mark_dominated_opportunities(opportunities)
    for opp in opportunities:
        if opp.status == OpportunityStatus.DOMINATED.value:
            total, comp = adjusted.get(opp.action_id, (0.0, {}))
            adjusted[opp.action_id] = (total - WEIGHT_DOMINATED_PENALTY, {**comp, "dominated_penalty": -WEIGHT_DOMINATED_PENALTY})

    return opportunities, adjusted


def select_best_frontier_opportunity(
    graph: "ResearchGraph",
    frontier: "ResearchFrontier",
    assessment: "ResearchAssessment",
) -> Optional["FrontierItem"]:
    """Portfolio-aware frontier selection — not raw planner_score alone."""
    from modules.edge_research.research_frontier import FrontierItem

    unexplored = frontier.unexplored_items()
    if not unexplored:
        return None

    best_item: Optional[FrontierItem] = None
    best_value = float("-inf")

    for item in unexplored:
        cand = item.to_action_candidate()
        base_scores = {item.action_id: (item.planner_score, {})}
        opps, _ = score_opportunities_for_selection(
            graph,
            assessment,
            [cand],
            base_scores,
            branch_root_id=item.branch_root_id,
        )
        if not opps:
            continue
        opp = opps[0]
        if opp.status == OpportunityStatus.DOMINATED.value:
            continue
        if opp.expected_research_value > best_value:
            best_value = opp.expected_research_value
            best_item = item
            if opp.is_revisit:
                record_branch_revisit(graph, item.branch_root_id)

    if best_item is None:
        unexplored.sort(key=lambda i: (-i.planner_score, i.frontier_id))
        return unexplored[0]
    return best_item
