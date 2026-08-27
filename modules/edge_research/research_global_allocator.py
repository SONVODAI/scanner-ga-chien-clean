"""
Global research allocator (Phase 3G.4).

Unifies local, frontier, deferred, and revisit opportunities into one
current-state comparison at every planning decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from modules.edge_research.research_experiment_identity import (
    EXPERIMENT_IDENTITY_VERSION,
    apply_experiment_identity_deduplication,
    canonical_hash_from_candidate,
)

if TYPE_CHECKING:
    from modules.edge_research.research_actions import ResearchActionCandidate
    from modules.edge_research.research_assessment import ResearchAssessment
    from modules.edge_research.research_frontier import FrontierItem, ResearchFrontier
    from modules.edge_research.research_graph import ResearchGraph
    from modules.edge_research.research_planner import PlanDecision

GLOBAL_ALLOCATOR_VERSION = "research_global_allocator_v1_2"


class OpportunitySource(str, Enum):
    LOCAL = "LOCAL"
    FRONTIER = "FRONTIER"
    DEFERRED = "DEFERRED"
    REVISIT = "REVISIT"


@dataclass
class GlobalComparableOpportunity:
    """One opportunity admitted (or excluded) from global comparison."""

    opportunity_id: str
    source: str
    action_id: str
    action_candidate: Optional["ResearchActionCandidate"]
    frontier_id: str = ""
    parent_experiment_node_id: str = ""
    branch_root_id: str = ""
    frame_id: str = ""
    historical_planner_score: float = 0.0
    current_revalued_value: float = 0.0
    expected_research_value: float = 0.0
    erv_components: Dict[str, float] = field(default_factory=dict)
    comparable: bool = True
    exclusion_reason: str = ""
    created_sequence: int = 0
    revalued_sequence: int = 0
    context_switch_required: bool = False
    current_branch_root_id: str = ""
    is_revisit: bool = False
    from_frontier: bool = False
    experiment_content_hash: str = ""
    duplicate_of_experiment_id: str = ""
    duplicate_representative_id: str = ""
    opportunity: Any = None  # ResearchOpportunity when available
    research_line_id: str = ""
    semantic_relationship: str = ""
    freshness_classification: str = ""
    semantic_marginal_audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "source": self.source,
            "action_id": self.action_id,
            "frontier_id": self.frontier_id,
            "parent_experiment_node_id": self.parent_experiment_node_id,
            "branch_root_id": self.branch_root_id,
            "frame_id": self.frame_id,
            "historical_planner_score": self.historical_planner_score,
            "current_revalued_value": self.current_revalued_value,
            "expected_research_value": self.expected_research_value,
            "erv_components": dict(self.erv_components),
            "comparable": self.comparable,
            "exclusion_reason": self.exclusion_reason,
            "created_sequence": self.created_sequence,
            "revalued_sequence": self.revalued_sequence,
            "context_switch_required": self.context_switch_required,
            "current_branch_root_id": self.current_branch_root_id,
            "is_revisit": self.is_revisit,
            "from_frontier": self.from_frontier,
            "experiment_content_hash": self.experiment_content_hash,
            "duplicate_of_experiment_id": self.duplicate_of_experiment_id,
            "duplicate_representative_id": self.duplicate_representative_id,
            "opportunity": self.opportunity.to_dict() if self.opportunity is not None else None,
            "research_line_id": self.research_line_id,
            "semantic_relationship": self.semantic_relationship,
            "freshness_classification": self.freshness_classification,
            "semantic_marginal_audit": dict(self.semantic_marginal_audit),
        }


@dataclass
class GlobalAllocationResult:
    """Outcome of one global allocation decision."""

    selected: Optional[GlobalComparableOpportunity]
    all_opportunities: Tuple[GlobalComparableOpportunity, ...]
    excluded: Tuple[GlobalComparableOpportunity, ...]
    best_local_erv: float = 0.0
    best_frontier_erv: float = 0.0
    best_deferred_erv: float = 0.0
    best_global_alternative_erv: float = 0.0
    global_opportunity_cost: float = 0.0
    comparable_count: int = 0
    excluded_count: int = 0
    context_switch_occurred: bool = False
    previous_branch_root_id: str = ""
    new_branch_root_id: str = ""
    budget_remaining: int = 0
    valuation_sequence: int = 0
    local_plan_decision: Optional["PlanDecision"] = None
    stop_session_selected: bool = False
    exit_value: float = 0.0
    exit_value_components: Dict[str, float] = field(default_factory=dict)
    branch_marginal_state: str = ""
    current_best_revalued_score: float = 0.0
    best_revisit_erv: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected": self.selected.to_dict() if self.selected else None,
            "all_opportunities": [o.to_dict() for o in self.all_opportunities],
            "excluded": [o.to_dict() for o in self.excluded],
            "best_local_erv": self.best_local_erv,
            "best_frontier_erv": self.best_frontier_erv,
            "best_deferred_erv": self.best_deferred_erv,
            "best_global_alternative_erv": self.best_global_alternative_erv,
            "global_opportunity_cost": self.global_opportunity_cost,
            "comparable_count": self.comparable_count,
            "excluded_count": self.excluded_count,
            "context_switch_occurred": self.context_switch_occurred,
            "previous_branch_root_id": self.previous_branch_root_id,
            "new_branch_root_id": self.new_branch_root_id,
            "budget_remaining": self.budget_remaining,
            "valuation_sequence": self.valuation_sequence,
            "stop_session_selected": self.stop_session_selected,
            "exit_value": self.exit_value,
            "exit_value_components": dict(self.exit_value_components),
            "branch_marginal_state": self.branch_marginal_state,
            "current_best_revalued_score": self.current_best_revalued_score,
            "best_revisit_erv": self.best_revisit_erv,
        }


def _remaining_budget(graph: "ResearchGraph") -> int:
    budget = graph.session.experiment_budget
    if budget is None:
        return 999999
    return max(0, budget - graph.session.experiments_used)


def _validate_frontier_temporal_legality(
    item: "FrontierItem",
    *,
    observation_horizon: int,
) -> Tuple[bool, str]:
    """Horizon-aware validation for reactivated frontier items."""
    from modules.edge_research.research_frame import validate_specs_at_horizon
    from modules.edge_research.research_grammar import GrammarValidationError, OutcomeSpec, PopulationSpec

    if not item.population_spec and not item.outcome_spec:
        return True, ""

    try:
        if item.population_spec:
            pop = PopulationSpec.from_dict(item.population_spec)
        else:
            pop = PopulationSpec.from_dict({"filters": []})
        if item.outcome_spec:
            out = OutcomeSpec.from_dict(item.outcome_spec)
        else:
            return False, "missing_outcome_spec"
        horizon = observation_horizon
        if horizon <= 0 and item.draft_spec:
            scope = (item.draft_spec or {}).get("research_scope") or {}
            pending = scope.get("pending_question_context") or {}
            horizon = int(pending.get("observation_horizon") or 0)
        if horizon <= 0:
            return True, ""
        validate_specs_at_horizon(pop, out, observation_horizon=horizon)
    except GrammarValidationError as exc:
        return False, f"temporal_illegal:{exc}"
    except Exception as exc:
        return False, f"temporal_validation_error:{type(exc).__name__}"
    return True, ""


def _record_line_opportunity_audit(graph: "ResearchGraph", entry: Dict[str, Any]) -> None:
    trail = list(getattr(graph.session, "research_line_opportunity_audit", None) or [])
    trail.append(entry)
    graph.session.research_line_opportunity_audit = trail[-200:]


def enrich_opportunity_semantic_context(
    graph: "ResearchGraph",
    opp: GlobalComparableOpportunity,
    assessment: "ResearchAssessment",
    *,
    planning_sequence: int = 0,
    frontier_item: Optional["FrontierItem"] = None,
) -> GlobalComparableOpportunity:
    """Attach research-line identity, relationship, and freshness audit metadata."""
    from modules.edge_research.research_line_decay_transfer import build_semantic_marginal_evidence
    from modules.edge_research.research_line_freshness import (
        EvidenceSnapshot,
        assess_freshness,
    )
    from modules.edge_research.research_line_identity import (
        ResearchLineIdentity,
        derive_identity_from_candidate,
        derive_identity_from_frontier_item,
    )
    from modules.edge_research.research_line_registry import (
        get_line_realized_gain_history,
        resolve_line_for_candidate,
    )
    from modules.edge_research.research_realized_information_gain import get_branch_realized_gain_history
    from modules.edge_research.research_search_accounting import branch_root_id

    identity: Optional[ResearchLineIdentity] = None
    if opp.action_candidate is not None:
        identity = derive_identity_from_candidate(opp.action_candidate)
    elif frontier_item is not None:
        identity = derive_identity_from_frontier_item(frontier_item)

    if identity is None:
        return opp

    line_id, rel_dict = resolve_line_for_candidate(graph, identity)
    relationship = (rel_dict or {}).get("classification", "")

    defer_snap: Optional[EvidenceSnapshot] = None
    if frontier_item and frontier_item.defer_evidence_snapshot:
        defer_snap = EvidenceSnapshot.from_dict(frontier_item.defer_evidence_snapshot)
    elif frontier_item and frontier_item.research_line_identity:
        defer_snap = EvidenceSnapshot(
            uncertainty_codes=tuple(
                (frontier_item.research_line_identity or {}).get("uncertainty_codes") or ()
            ),
            observation_horizon=int(
                (frontier_item.research_line_identity or {}).get("observation_horizon") or 0
            ),
            population_spec=dict(frontier_item.population_spec),
            outcome_spec=dict(frontier_item.outcome_spec),
            planning_sequence=frontier_item.enqueued_sequence,
        )

    current_snap = EvidenceSnapshot.from_assessment(
        assessment, identity=identity, planning_sequence=planning_sequence
    )
    prior_gain = ""
    prior_attempts = 0
    if line_id:
        gains = get_line_realized_gain_history(graph, line_id)
        prior_attempts = len(gains)
        if gains:
            prior_gain = gains[-1]

    freshness = assess_freshness(
        identity=identity,
        research_line_id=line_id or "",
        defer_snapshot=defer_snap,
        current_snapshot=current_snap,
        prior_attempt_count=prior_attempts,
        prior_realized_gain=prior_gain,
        last_attempt_sequence=defer_snap.planning_sequence if defer_snap else 0,
        erv_changed_only=opp.is_revisit and not defer_snap,
    )

    br_root = opp.branch_root_id or ""
    if not br_root and opp.parent_experiment_node_id:
        br_root = branch_root_id(graph, opp.parent_experiment_node_id)
    branch_hist = get_branch_realized_gain_history(graph, br_root)
    branch_levels = [e.get("gain_level", "UNRESOLVED") for e in branch_hist]
    tools = tuple(assessment.branch_tools_attempted or ())

    semantic_ev = build_semantic_marginal_evidence(
        graph,
        candidate_identity=identity,
        branch_levels=branch_levels,
        branch_tools_attempted=tools,
        freshness_classification=freshness.classification,
    )

    audit_entry = {
        "opportunity_id": opp.opportunity_id,
        "research_line_id": line_id or semantic_ev.matched_line_id,
        "semantic_relationship": semantic_ev.relationship_classification,
        "freshness": freshness.to_dict(),
        "semantic_marginal": semantic_ev.to_dict(),
    }
    _record_line_opportunity_audit(graph, audit_entry)

    if frontier_item is not None:
        frontier_item.research_line_id = line_id or semantic_ev.matched_line_id
        frontier_item.freshness_classification = freshness.classification
        if defer_snap is None:
            frontier_item.defer_evidence_snapshot = current_snap.to_dict()

    return GlobalComparableOpportunity(
        opportunity_id=opp.opportunity_id,
        source=opp.source,
        action_id=opp.action_id,
        action_candidate=opp.action_candidate,
        frontier_id=opp.frontier_id,
        parent_experiment_node_id=opp.parent_experiment_node_id,
        branch_root_id=opp.branch_root_id,
        frame_id=opp.frame_id,
        historical_planner_score=opp.historical_planner_score,
        current_revalued_value=opp.current_revalued_value,
        expected_research_value=opp.expected_research_value,
        erv_components=dict(opp.erv_components),
        comparable=opp.comparable,
        exclusion_reason=opp.exclusion_reason,
        created_sequence=opp.created_sequence,
        revalued_sequence=opp.revalued_sequence,
        context_switch_required=opp.context_switch_required,
        current_branch_root_id=opp.current_branch_root_id,
        is_revisit=opp.is_revisit,
        from_frontier=opp.from_frontier,
        experiment_content_hash=opp.experiment_content_hash,
        duplicate_of_experiment_id=opp.duplicate_of_experiment_id,
        duplicate_representative_id=opp.duplicate_representative_id,
        opportunity=opp.opportunity,
        research_line_id=line_id or semantic_ev.matched_line_id,
        semantic_relationship=semantic_ev.relationship_classification,
        freshness_classification=freshness.classification,
        semantic_marginal_audit=semantic_ev.to_dict(),
    )


def _reconstruct_frontier_context(
    graph: "ResearchGraph",
    item: "FrontierItem",
    panel_columns: Optional[Tuple[str, ...]],
) -> Tuple[bool, str, Optional["ResearchActionCandidate"]]:
    """Verify frontier item can be safely reconstructed."""
    from modules.edge_research.research_panel_preflight import validate_action_against_panel

    if item.parent_experiment_node_id and item.parent_experiment_node_id not in graph.nodes:
        return False, "missing_parent_node", None
    if item.draft_spec is None:
        return False, "missing_draft_spec", None
    try:
        cand = item.to_action_candidate()
    except Exception as exc:
        return False, f"context_reconstruction_failed:{type(exc).__name__}", None
    if cand.draft_spec is None:
        return False, "missing_draft_spec", None
    if panel_columns:
        valid, reason = validate_action_against_panel(cand, panel_columns)
        if not valid:
            return False, f"panel_invalid:{reason}", None
    return True, "", cand


def revalue_frontier_opportunity(
    graph: "ResearchGraph",
    item: "FrontierItem",
    assessment: "ResearchAssessment",
    *,
    current_branch_root_id: str = "",
    panel_columns: Optional[Tuple[str, ...]] = None,
    revalued_sequence: int = 0,
) -> GlobalComparableOpportunity:
    """
    Revalue one frontier item under current session state.

    Preserves historical planner_score; never treats it as current ERV.
    """
    from modules.edge_research.research_actions import ActionIntent
    from modules.edge_research.research_planner import score_candidate
    from modules.edge_research.research_portfolio import (
        BranchPortfolioStatus,
        OpportunityStatus,
        build_opportunity_from_candidate,
        mark_dominated_opportunities,
    )

    historical = float(item.planner_score)
    opp_id = f"frontier:{item.frontier_id}"

    ok, reason, cand = _reconstruct_frontier_context(graph, item, panel_columns)
    if not ok:
        return GlobalComparableOpportunity(
            opportunity_id=opp_id,
            source=OpportunitySource.FRONTIER.value,
            action_id=item.action_id,
            action_candidate=None,
            frontier_id=item.frontier_id,
            parent_experiment_node_id=item.parent_experiment_node_id,
            branch_root_id=item.branch_root_id,
            frame_id=item.frame_id,
            historical_planner_score=historical,
            comparable=False,
            exclusion_reason=reason,
            created_sequence=item.enqueued_sequence,
            revalued_sequence=revalued_sequence,
            current_branch_root_id=current_branch_root_id,
            from_frontier=True,
        )

    assert cand is not None
    horizon = 0
    if item.draft_spec:
        scope = (item.draft_spec or {}).get("research_scope") or {}
        pending = scope.get("pending_question_context") or {}
        horizon = int(pending.get("observation_horizon") or 0)

    legal, temporal_reason = _validate_frontier_temporal_legality(item, observation_horizon=horizon)
    if not legal:
        return GlobalComparableOpportunity(
            opportunity_id=opp_id,
            source=OpportunitySource.FRONTIER.value,
            action_id=item.action_id,
            action_candidate=cand,
            frontier_id=item.frontier_id,
            parent_experiment_node_id=item.parent_experiment_node_id,
            branch_root_id=item.branch_root_id,
            frame_id=item.frame_id,
            historical_planner_score=historical,
            comparable=False,
            exclusion_reason=temporal_reason,
            created_sequence=item.enqueued_sequence,
            revalued_sequence=revalued_sequence,
            current_branch_root_id=current_branch_root_id,
            from_frontier=True,
        )

    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(item.branch_root_id)
    is_deferred = branch.status == BranchPortfolioStatus.DEFERRED_PROMISING.value
    is_revisit = is_deferred and branch.experiments_on_branch > 0

    parent_id = item.parent_experiment_node_id if item.parent_experiment_node_id in graph.nodes else None
    base_score, components = score_candidate(
        cand,
        assessment,
        graph,
        experiment_node_id=parent_id,
    )

    opp = build_opportunity_from_candidate(
        cand,
        base_score=base_score,
        components=components,
        graph=graph,
        assessment=assessment,
        experiment_node_id=parent_id,
        branch_root_id=item.branch_root_id,
        from_frontier=True,
    )
    opp.from_frontier = True
    opp.is_revisit = is_revisit

    source = OpportunitySource.REVISIT.value if is_revisit else (
        OpportunitySource.DEFERRED.value if is_deferred else OpportunitySource.FRONTIER.value
    )

    context_switch = bool(
        current_branch_root_id
        and item.branch_root_id
        and current_branch_root_id != item.branch_root_id
    )

    return GlobalComparableOpportunity(
        opportunity_id=opp_id,
        source=source,
        action_id=item.action_id,
        action_candidate=cand,
        frontier_id=item.frontier_id,
        parent_experiment_node_id=item.parent_experiment_node_id,
        branch_root_id=item.branch_root_id,
        frame_id=item.frame_id or opp.frame_id,
        historical_planner_score=historical,
        current_revalued_value=opp.expected_research_value,
        expected_research_value=opp.expected_research_value,
        erv_components={
            "base_planner_score": base_score,
            "exploration_debt": opp.exploration_debt,
            "exploitation_value": opp.exploitation_value,
            "marginal_information_gain": opp.marginal_information_gain,
            "redundancy": opp.redundancy,
            "complexity_burden": opp.complexity_burden,
            "historical_planner_score": historical,
        },
        comparable=opp.status != OpportunityStatus.DOMINATED.value,
        exclusion_reason="" if opp.status != OpportunityStatus.DOMINATED.value else "dominated",
        created_sequence=item.enqueued_sequence,
        revalued_sequence=revalued_sequence,
        context_switch_required=context_switch,
        current_branch_root_id=current_branch_root_id,
        is_revisit=is_revisit,
        from_frontier=True,
        experiment_content_hash=canonical_hash_from_candidate(cand) or "",
        opportunity=opp,
    )


def collect_global_opportunities(
    graph: "ResearchGraph",
    assessment: "ResearchAssessment",
    local_candidates: Sequence["ResearchActionCandidate"],
    base_scores: Dict[str, Tuple[float, Dict[str, float]]],
    *,
    experiment_node_id: Optional[str] = None,
    panel_columns: Optional[Tuple[str, ...]] = None,
) -> Tuple[List[GlobalComparableOpportunity], List[GlobalComparableOpportunity]]:
    """
    Build the current decision set: local + revalued frontier/deferred/revisit.
    """
    from modules.edge_research.research_actions import ActionIntent
    from modules.edge_research.research_portfolio import (
        OpportunityStatus,
        score_opportunities_for_selection,
    )
    from modules.edge_research.research_search_accounting import branch_root_id

    current_root = branch_root_id(graph, experiment_node_id) if experiment_node_id else ""
    portfolio = graph.get_portfolio_state()
    seq = portfolio.sequence_counter + 1

    local_opps, _ = score_opportunities_for_selection(
        graph,
        assessment,
        local_candidates,
        base_scores,
        experiment_node_id=experiment_node_id,
        branch_root_id=current_root,
    )

    global_opps: List[GlobalComparableOpportunity] = []
    excluded: List[GlobalComparableOpportunity] = []

    terminal_intents = {
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    }

    for opp in local_opps:
        cand = next((c for c in local_candidates if c.action_id == opp.action_id), None)
        is_terminal = opp.action_type in terminal_intents
        g = GlobalComparableOpportunity(
            opportunity_id=f"local:{opp.action_id}",
            source=OpportunitySource.LOCAL.value,
            action_id=opp.action_id,
            action_candidate=cand,
            branch_root_id=current_root,
            frame_id=opp.frame_id,
            historical_planner_score=opp.base_planner_score,
            current_revalued_value=opp.expected_research_value,
            expected_research_value=opp.expected_research_value,
            erv_components={
                "base_planner_score": opp.base_planner_score,
                "exploration_debt": opp.exploration_debt,
                "exploitation_value": opp.exploitation_value,
                "marginal_information_gain": opp.marginal_information_gain,
            },
            comparable=opp.status != OpportunityStatus.DOMINATED.value and not is_terminal,
            exclusion_reason="terminal_intent" if is_terminal else (
                "dominated" if opp.status == OpportunityStatus.DOMINATED.value else ""
            ),
            revalued_sequence=seq,
            context_switch_required=False,
            current_branch_root_id=current_root,
            experiment_content_hash=canonical_hash_from_candidate(cand) or "",
            opportunity=opp,
        )
        if g.comparable:
            global_opps.append(g)
        else:
            excluded.append(g)

    frontier = graph.get_frontier()
    for item in frontier.unexplored_items():
        g = revalue_frontier_opportunity(
            graph,
            item,
            assessment,
            current_branch_root_id=current_root,
            panel_columns=panel_columns,
            revalued_sequence=seq,
        )
        if g.comparable:
            global_opps.append(g)
        else:
            excluded.append(g)

    comparable_pool, excluded = apply_experiment_identity_deduplication(
        global_opps, excluded, graph
    )

    enriched: List[GlobalComparableOpportunity] = []
    frontier_dirty = False
    for g in comparable_pool:
        frontier_item = frontier.items.get(g.frontier_id) if g.frontier_id else None
        enriched.append(
            enrich_opportunity_semantic_context(
                graph,
                g,
                assessment,
                planning_sequence=seq,
                frontier_item=frontier_item,
            )
        )
        if frontier_item is not None:
            frontier_dirty = True
    if frontier_dirty:
        graph.persist_frontier()
    return enriched, excluded


def _best_erv_by_source(
    opportunities: Sequence[GlobalComparableOpportunity],
) -> Tuple[float, float, float]:
    best_local = float("-inf")
    best_frontier = float("-inf")
    best_deferred = float("-inf")
    for o in opportunities:
        if not o.comparable:
            continue
        val = o.expected_research_value
        if o.source == OpportunitySource.LOCAL.value:
            best_local = max(best_local, val)
        elif o.source in (OpportunitySource.FRONTIER.value, OpportunitySource.REVISIT.value):
            best_frontier = max(best_frontier, val)
        elif o.source == OpportunitySource.DEFERRED.value:
            best_deferred = max(best_deferred, val)
        if o.source == OpportunitySource.REVISIT.value:
            best_deferred = max(best_deferred, val)
    return (
        best_local if best_local != float("-inf") else 0.0,
        best_frontier if best_frontier != float("-inf") else 0.0,
        best_deferred if best_deferred != float("-inf") else 0.0,
    )


def build_global_decision_explanation(
    selected: Optional[GlobalComparableOpportunity],
    opportunities: Sequence[GlobalComparableOpportunity],
    excluded: Sequence[GlobalComparableOpportunity],
    *,
    best_local_erv: float,
    best_frontier_erv: float,
    best_deferred_erv: float,
    budget_remaining: int,
    valuation_sequence: int,
    context_switch_occurred: bool,
    previous_branch_root_id: str,
    new_branch_root_id: str,
    local_plan_decision: Optional["PlanDecision"] = None,
) -> Dict[str, Any]:
    """Extended decision explanation for global allocation audit."""
    from modules.edge_research.research_portfolio import build_decision_explanation

    comparable = [o for o in opportunities if o.comparable]
    viable_sorted = sorted(comparable, key=lambda o: (-o.expected_research_value, o.action_id))

    best_alt = None
    if selected:
        for alt in viable_sorted:
            if alt.action_id != selected.action_id or alt.source != selected.source:
                best_alt = alt
                break

    best_global_alt_erv = best_alt.expected_research_value if best_alt else 0.0
    selected_erv = selected.expected_research_value if selected else 0.0
    opp_cost = max(0.0, best_global_alt_erv - selected_erv) if best_alt else 0.0

    base_explanation: Dict[str, Any] = {}
    if selected and selected.opportunity is not None:
        expl = build_decision_explanation(
            selected.opportunity,
            [o.opportunity for o in comparable if o.opportunity is not None],
            budget_remaining=budget_remaining,
            portfolio_components=selected.erv_components,
        )
        base_explanation = expl.to_dict()

    exclusion_summary = [
        {"opportunity_id": e.opportunity_id, "reason": e.exclusion_reason}
        for e in excluded
    ]

    revisit_audit: Dict[str, Any] = {}
    if selected and selected.is_revisit:
        portfolio = None
        revisit_audit = {
            "branch_originally_left_at_experiment": selected.parent_experiment_node_id,
            "reason_left": "DEFERRED_PROMISING",
            "erv_when_reconsidered": selected_erv,
            "reason_revisited": "GLOBAL_HIGHEST_ERV",
            "revisit_count": selected.opportunity.revisit_count if selected.opportunity else 0,
        }

    return {
        **base_explanation,
        "allocator_version": GLOBAL_ALLOCATOR_VERSION,
        "experiment_identity_version": EXPERIMENT_IDENTITY_VERSION,
        "selected_source": selected.source if selected else "",
        "selected_frontier_id": selected.frontier_id if selected else "",
        "selected_erv": selected_erv,
        "best_local_erv": best_local_erv,
        "best_frontier_erv": best_frontier_erv,
        "best_deferred_erv": best_deferred_erv,
        "best_global_alternative_erv": best_global_alt_erv,
        "global_opportunity_cost": opp_cost,
        "globally_comparable_count": len(comparable),
        "excluded_count": len(excluded),
        "exclusion_reasons": exclusion_summary,
        "context_switch_occurred": context_switch_occurred,
        "previous_branch_root_id": previous_branch_root_id,
        "new_branch_root_id": new_branch_root_id,
        "budget_remaining": budget_remaining,
        "valuation_sequence": valuation_sequence,
        "historical_planner_score": selected.historical_planner_score if selected else 0.0,
        "current_revalued_value": selected.current_revalued_value if selected else 0.0,
        "revisit_audit": revisit_audit,
        "local_would_have_selected": (
            local_plan_decision.selected.action_id
            if local_plan_decision and local_plan_decision.selected
            else None
        ),
    }


def select_global_research_opportunity(
    graph: "ResearchGraph",
    assessment: "ResearchAssessment",
    local_candidates: Sequence["ResearchActionCandidate"],
    base_scores: Dict[str, Tuple[float, Dict[str, float]]],
    local_decision: "PlanDecision",
    *,
    experiment_node_id: Optional[str] = None,
    panel_columns: Optional[Tuple[str, ...]] = None,
) -> GlobalAllocationResult:
    """
    Global allocation: compare all legal opportunities under current state.

    Returns allocation result; caller converts to PlanDecision.
    """
    from modules.edge_research.research_actions import ActionIntent
    from modules.edge_research.research_planner import PlanDecisionType
    from modules.edge_research.research_search_accounting import branch_root_id

    current_root = branch_root_id(graph, experiment_node_id) if experiment_node_id else ""
    remaining = _remaining_budget(graph)
    portfolio = graph.get_portfolio_state()
    seq = portfolio.sequence_counter + 1

    global_opps, excluded = collect_global_opportunities(
        graph,
        assessment,
        local_candidates,
        base_scores,
        experiment_node_id=experiment_node_id,
        panel_columns=panel_columns,
    )

    all_audit_opportunities = tuple(global_opps) + tuple(excluded)
    comparable = list(global_opps)
    best_local, best_frontier, best_deferred = _best_erv_by_source(comparable)

    terminal_intents = {
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    }
    experiment_comparable = [
        o for o in comparable
        if o.action_candidate is not None
        and o.action_candidate.intent not in terminal_intents
        and not o.action_candidate.blocked
    ]

    selected: Optional[GlobalComparableOpportunity] = None
    stop_session_selected = False
    exit_value_result = 0.0
    exit_components: Dict[str, float] = {}
    branch_marginal_state_str = ""
    current_best_revalued = 0.0

    best_revisit_erv = max(
        (o.expected_research_value for o in comparable if o.source == OpportunitySource.REVISIT.value),
        default=float("-inf"),
    )
    if best_revisit_erv == float("-inf"):
        best_revisit_erv = 0.0

    if experiment_comparable:
        experiment_comparable.sort(
            key=lambda o: (-o.expected_research_value, o.action_id, o.source)
        )
        best_experiment = experiment_comparable[0]
        current_best_revalued = best_experiment.expected_research_value

        from modules.edge_research.research_branch_marginal_state import (
            build_branch_marginal_state,
            record_branch_marginal_state,
        )
        from modules.edge_research.research_exit_valuation import (
            _independent_frontier_erv,
            compute_research_exit_value,
            evaluate_exit_vs_experiment,
        )
        from modules.edge_research.research_line_decay_transfer import (
            build_semantic_marginal_evidence,
            record_semantic_marginal_audit,
        )
        from modules.edge_research.research_line_identity import derive_identity_from_candidate
        from modules.edge_research.research_realized_information_gain import (
            get_branch_realized_gain_history,
        )

        cand_identity = None
        if best_experiment.action_candidate is not None:
            cand_identity = derive_identity_from_candidate(best_experiment.action_candidate)
        branch_hist = get_branch_realized_gain_history(graph, current_root)
        branch_levels = [e.get("gain_level", "UNRESOLVED") for e in branch_hist]
        semantic_ev = build_semantic_marginal_evidence(
            graph,
            candidate_identity=cand_identity,
            branch_levels=branch_levels,
            branch_tools_attempted=tuple(assessment.branch_tools_attempted or ()),
            freshness_classification=best_experiment.freshness_classification,
        )
        record_semantic_marginal_audit(graph, semantic_ev)

        marginal = build_branch_marginal_state(
            graph=graph,
            assessment=assessment,
            branch_root_id=current_root,
            experiment_node_id=experiment_node_id,
            planning_sequence=seq,
            semantic_realized_levels=semantic_ev.merged_realized_levels,
            semantic_relationship=semantic_ev.relationship_classification,
            representation_novelty_only=semantic_ev.representation_novelty_only,
        )
        record_branch_marginal_state(graph, marginal)
        branch_marginal_state_str = marginal.marginal_state

        historical_best = graph.get_frontier().best_unexplored_score()
        features_touched = len(
            graph.get_search_accounting().session_ledger.explanatory_features_tested
        )
        eligible = len((graph.session.panel_preflight or {}).get("eligible_explanatory") or [])
        indep_erv = _independent_frontier_erv(comparable, current_root)

        exit_val = compute_research_exit_value(
            marginal_state=marginal,
            best_experiment_erv=best_experiment.expected_research_value,
            best_local_erv=best_local,
            best_frontier_erv=best_frontier,
            best_revisit_erv=best_revisit_erv,
            best_deferred_erv=best_deferred,
            historical_best_frontier_score=historical_best,
            remaining_budget=remaining,
            experiment_budget=graph.session.experiment_budget,
            features_touched=features_touched,
            eligible_feature_count=eligible,
            independent_frontier_erv=indep_erv,
        )
        exit_value_result = exit_val.exit_value
        exit_components = exit_val.components

        if evaluate_exit_vs_experiment(exit_val, best_experiment.expected_research_value):
            stop_session_selected = True
            selected = None
        else:
            local_is_terminal = local_decision.decision_type in (
                PlanDecisionType.STOP_BRANCH,
                PlanDecisionType.ABANDON,
                PlanDecisionType.STOP_SESSION,
            )

            local_terminal_erv = float("-inf")
            if local_decision.selected is not None:
                for o in comparable:
                    if o.action_id == local_decision.selected.action_id:
                        local_terminal_erv = o.expected_research_value
                        break

            if local_is_terminal:
                if best_experiment.expected_research_value > local_terminal_erv:
                    selected = best_experiment
            else:
                selected = best_experiment
    else:
        best_experiment = None

    if selected and selected.source == OpportunitySource.LOCAL.value:
        context_switch = False
        new_root = current_root
    elif selected and selected.source != OpportunitySource.LOCAL.value:
        context_switch = selected.context_switch_required
        new_root = selected.branch_root_id
    else:
        context_switch = False
        new_root = current_root

    best_global_alt = float("-inf")
    if stop_session_selected and experiment_comparable:
        best_global_alt_erv = experiment_comparable[0].expected_research_value
        opp_cost = max(0.0, exit_value_result - best_global_alt_erv)
    elif selected:
        for o in experiment_comparable:
            if o.action_id != selected.action_id or o.source != selected.source:
                best_global_alt = max(best_global_alt, o.expected_research_value)
        best_global_alt_erv = best_global_alt if best_global_alt != float("-inf") else 0.0
        opp_cost = max(
            0.0,
            best_global_alt_erv - selected.expected_research_value,
        )
    else:
        best_global_alt_erv = 0.0
        opp_cost = 0.0

    return GlobalAllocationResult(
        selected=selected,
        all_opportunities=all_audit_opportunities,
        excluded=tuple(excluded),
        best_local_erv=best_local,
        best_frontier_erv=best_frontier,
        best_deferred_erv=best_deferred,
        best_global_alternative_erv=best_global_alt_erv,
        global_opportunity_cost=opp_cost,
        comparable_count=len(comparable),
        excluded_count=len(excluded),
        context_switch_occurred=(
            context_switch
            and selected is not None
            and selected.source != OpportunitySource.LOCAL.value
        ),
        previous_branch_root_id=current_root,
        new_branch_root_id=new_root if selected else current_root,
        budget_remaining=remaining,
        valuation_sequence=seq,
        local_plan_decision=local_decision,
        stop_session_selected=stop_session_selected,
        exit_value=exit_value_result,
        exit_value_components=exit_components,
        branch_marginal_state=branch_marginal_state_str,
        current_best_revalued_score=current_best_revalued,
        best_revisit_erv=best_revisit_erv,
    )


def apply_global_allocation_to_plan_decision(
    graph: "ResearchGraph",
    local_decision: "PlanDecision",
    allocation: GlobalAllocationResult,
    *,
    local_opportunities: Sequence[Any],
) -> "PlanDecision":
    """
    Merge global allocation outcome into PlanDecision.

    May upgrade local STOP to frontier SWITCH when globally better.
    """
    from modules.edge_research.research_actions import ActionIntent
    from modules.edge_research.research_planner import PlanDecision, PlanDecisionType

    remaining = allocation.budget_remaining
    selected = allocation.selected

    explanation = build_global_decision_explanation(
        selected,
        allocation.all_opportunities,
        allocation.excluded,
        best_local_erv=allocation.best_local_erv,
        best_frontier_erv=allocation.best_frontier_erv,
        best_deferred_erv=allocation.best_deferred_erv,
        budget_remaining=remaining,
        valuation_sequence=allocation.valuation_sequence,
        context_switch_occurred=allocation.context_switch_occurred,
        previous_branch_root_id=allocation.previous_branch_root_id,
        new_branch_root_id=allocation.new_branch_root_id,
        local_plan_decision=local_decision,
    )

    portfolio = graph.get_portfolio_state()
    portfolio.decision_explanations.append(explanation)
    graph.persist_portfolio_state()

    if allocation.stop_session_selected:
        from modules.edge_research.research_actions import ActionIntent

        stop_cand = next(
            (
                c
                for c in local_decision.all_candidates
                if c.intent == ActionIntent.STOP_SESSION.value
            ),
            local_decision.selected,
        )
        return PlanDecision(
            decision_type=PlanDecisionType.STOP_SESSION,
            selected=stop_cand,
            all_candidates=local_decision.all_candidates,
            score_breakdown={
                "components": allocation.exit_value_components,
                "total": allocation.exit_value,
            },
            rationale_codes=("STOP_SESSION", "EXIT_VALUATION_DOMINANT"),
            portfolio_explanation=explanation,
            portfolio_opportunities=local_decision.portfolio_opportunities,
            global_allocation_source="EXIT_PRESERVE_BUDGET",
            selected_frontier_id="",
            context_switch_required=False,
            global_allocation=allocation.to_dict(),
        )

    if selected is None:
        return PlanDecision(
            decision_type=local_decision.decision_type,
            selected=local_decision.selected,
            all_candidates=local_decision.all_candidates,
            score_breakdown=local_decision.score_breakdown,
            rationale_codes=local_decision.rationale_codes + ("GLOBAL_NO_BETTER_EXPERIMENT",),
            portfolio_explanation=explanation,
            portfolio_opportunities=local_decision.portfolio_opportunities,
            global_allocation_source="",
            selected_frontier_id="",
            context_switch_required=False,
            global_allocation=allocation.to_dict(),
        )

    if selected.source == OpportunitySource.LOCAL.value:
        cand = selected.action_candidate or local_decision.selected
        return PlanDecision(
            decision_type=PlanDecisionType.EXPERIMENT,
            selected=cand,
            all_candidates=local_decision.all_candidates,
            score_breakdown={
                "components": selected.erv_components,
                "total": selected.expected_research_value,
            },
            rationale_codes=(
                (cand.action_code if cand else "EXPERIMENT", "GLOBAL_LOCAL_SELECTED")
            ),
            portfolio_explanation=explanation,
            portfolio_opportunities=local_decision.portfolio_opportunities,
            global_allocation_source=OpportunitySource.LOCAL.value,
            selected_frontier_id="",
            context_switch_required=False,
            global_allocation=allocation.to_dict(),
        )

    cand = selected.action_candidate
    if cand is None:
        return local_decision

    source = selected.source
    rationale = (
        "GLOBAL_FRONTIER_SELECTED",
        f"ERV={selected.expected_research_value:.3f}",
        f"LOCAL_BEST={allocation.best_local_erv:.3f}",
    )
    if selected.is_revisit:
        rationale = rationale + ("GLOBAL_REVISIT",)

    return PlanDecision(
        decision_type=PlanDecisionType.SWITCH_OPPORTUNITY,
        selected=cand,
        all_candidates=local_decision.all_candidates,
        score_breakdown={
            "components": selected.erv_components,
            "total": selected.expected_research_value,
            "historical_planner_score": selected.historical_planner_score,
        },
        rationale_codes=rationale,
        portfolio_explanation=explanation,
        portfolio_opportunities=local_decision.portfolio_opportunities,
        global_allocation_source=source,
        selected_frontier_id=selected.frontier_id,
        context_switch_required=allocation.context_switch_occurred,
        global_allocation=allocation.to_dict(),
    )
