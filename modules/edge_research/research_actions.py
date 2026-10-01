"""
Structured action generation for Edge Research (PATCH 3C).

Assessment → multiple ResearchActionCandidate proposals. No selection.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_grammar import (
    GrammarValidationError,
    OutcomeSpec,
    PopulationSpec,
    build_search_accounting,
    population_spec_to_research_scope,
    propose_outcome_reframes,
    propose_population_refinements,
    propose_population_widenings,
    validate_outcome_spec,
)
from modules.edge_research.research_interpreter import (
    FALSIFY_DATE_ARTIFACT,
    FALSIFY_EPISODE_FLUKE,
    FALSIFY_EXTREME_WINNER,
    FALSIFY_SYMBOL_DOMINANCE,
    GAP_CATEGORY_REFINEMENT,
    GAP_EPISODE_REPLICATION,
    GAP_HORIZON_STABILITY,
    GAP_INTERACTION_FOLLOWUP,
    GAP_MARKET_DEPENDENCE,
    GAP_NEIGHBORHOOD_THRESHOLD,
    GAP_NEIGHBORHOOD_STABILITY,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_THRESHOLD_EXPLORATION,
    GAP_TIME_DISTRIBUTION,
    GAP_TRAJECTORY_ROLE,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    NextActionCandidate,
    NodeType,
    ResearchQuestionContext,
    compute_experiment_content_hash,
)
from modules.edge_research.research_tools import ToolRegistry

DEFAULT_HORIZON = "T5"
DEFAULT_TRAJECTORY_FEATURE = "rs10_delta_3"
DEFAULT_TRAJECTORY_BINS = [
    {"lo": None, "hi": 0.0, "label": "neg_delta"},
    {"lo": 0.0, "hi": None, "label": "pos_delta"},
]


class ActionIntent(str, Enum):
    EXPLORATION = "EXPLORATION"
    DECOMPOSITION = "DECOMPOSITION"
    CONDITIONING = "CONDITIONING"
    REPLICATION = "REPLICATION"
    ROBUSTNESS = "ROBUSTNESS"
    FALSIFICATION = "FALSIFICATION"
    REFRAME = "REFRAME"
    REPOPULATE = "REPOPULATE"
    REDESCRIBE_OUTCOME = "REDESCRIBE_OUTCOME"
    EXPLORE_THRESHOLD = "EXPLORE_THRESHOLD"
    TEST_NEIGHBORHOOD = "TEST_NEIGHBORHOOD"
    SLICING = "SLICING"
    STOP = "STOP"
    STOP_SESSION = "STOP_SESSION"
    ABANDON = "ABANDON"


class ExpectedInformation(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class ResearchActionCandidate:
    action_id: str
    action_code: str
    intent: str
    question_template_id: str
    question_text: str
    tool_name: str
    tool_version: str
    draft_spec: Optional[ExperimentSpec]
    uncertainty_addressed: str
    expected_information: str
    budget_cost: int
    already_attempted: bool
    blocked: bool
    blocked_reason: Optional[str]
    rationale_codes: Tuple[str, ...] = field(default_factory=tuple)
    priority_hints: Dict[str, float] = field(default_factory=dict)

    def to_next_action_candidate(self, *, score: Optional[float] = None) -> NextActionCandidate:
        meta: Dict[str, Any] = {
            "action_id": self.action_id,
            "intent": self.intent,
            "question_template_id": self.question_template_id,
            "question_text": self.question_text,
            "tool_version": self.tool_version,
            "uncertainty_addressed": self.uncertainty_addressed,
            "expected_information": self.expected_information,
            "budget_cost": self.budget_cost,
            "already_attempted": self.already_attempted,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "rationale_codes": list(self.rationale_codes),
            "priority_hints": dict(self.priority_hints),
        }
        if self.draft_spec is not None:
            meta["draft_spec"] = self.draft_spec.to_dict()
        if score is not None:
            meta["planner_score"] = score
        return NextActionCandidate(
            action_code=self.action_code,
            tool_name=self.tool_name if self.tool_name else None,
            rationale=",".join(self.rationale_codes),
            metadata=meta,
        )


def _action_id(action_code: str, spec: Optional[ExperimentSpec]) -> str:
    payload = {"action_code": action_code}
    if spec is not None:
        payload["spec_hash"] = compute_experiment_content_hash(spec)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _base_scope(research_scope: Dict[str, Any]) -> Dict[str, Any]:
    return dict(research_scope or {})


def _make_spec(
    *,
    tool_name: str,
    tool_version: str,
    inputs: Dict[str, Any],
    research_scope: Dict[str, Any],
    cutoff: str,
) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool_name,
        tool_version=tool_version,
        inputs=dict(inputs),
        research_scope=_base_scope(research_scope),
        data_cutoff_date=cutoff,
    )


def _check_candidate(
    graph: ResearchGraph,
    *,
    action_code: str,
    intent: ActionIntent,
    template_id: str,
    question: str,
    tool_name: str,
    tool_version: str,
    spec: Optional[ExperimentSpec],
    uncertainty: str,
    expected_info: ExpectedInformation,
    rationale_codes: Sequence[str],
    priority_hints: Dict[str, float],
    registry: ToolRegistry,
) -> ResearchActionCandidate:
    blocked = False
    blocked_reason: Optional[str] = None
    already_attempted = False

    if intent in (ActionIntent.STOP, ActionIntent.ABANDON, ActionIntent.STOP_SESSION):
        action_id = _action_id(action_code, None)
        return ResearchActionCandidate(
            action_id=action_id,
            action_code=action_code,
            intent=intent.value,
            question_template_id=template_id,
            question_text=question,
            tool_name="",
            tool_version="",
            draft_spec=None,
            uncertainty_addressed=uncertainty,
            expected_information=expected_info.value,
            budget_cost=0,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
            rationale_codes=tuple(rationale_codes),
            priority_hints=dict(priority_hints),
        )

    if spec is None:
        blocked = True
        blocked_reason = "MISSING_SPEC"
    else:
        try:
            registry.get(spec.tool_name, spec.tool_version)
        except KeyError:
            blocked = True
            blocked_reason = "UNKNOWN_TOOL"
        if graph.has_attempted_experiment(spec):
            already_attempted = True
            blocked = True
            blocked_reason = "DUPLICATE_EXPERIMENT"

    action_id = _action_id(action_code, spec)
    return ResearchActionCandidate(
        action_id=action_id,
        action_code=action_code,
        intent=intent.value,
        question_template_id=template_id,
        question_text=question,
        tool_name=tool_name,
        tool_version=tool_version,
        draft_spec=spec,
        uncertainty_addressed=uncertainty,
        expected_information=expected_info.value,
        budget_cost=1,
        already_attempted=already_attempted,
        blocked=blocked,
        blocked_reason=blocked_reason,
        rationale_codes=tuple(rationale_codes),
        priority_hints=dict(priority_hints),
    )


def _question_context_from_experiment(graph: ResearchGraph, experiment_node_id: str) -> Optional[ResearchQuestionContext]:
    """Resolve parent question context for grammar-driven candidates."""
    exp = graph.get_node(experiment_node_id)
    for pid in exp.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.node_type == NodeType.QUESTION and parent.question_context is not None:
            return parent.question_context
    return None


def _parse_specs_from_context(ctx: ResearchQuestionContext) -> Tuple[PopulationSpec, OutcomeSpec]:
    pop = PopulationSpec.from_dict(ctx.population_spec)
    out = OutcomeSpec.from_dict(ctx.outcome_spec)
    return pop, out


def _grammar_scope(
    population: PopulationSpec,
    outcome: OutcomeSpec,
    base_scope: Dict[str, Any],
) -> Dict[str, Any]:
    scope = _base_scope(base_scope)
    scope.update(population_spec_to_research_scope(population))
    scope["outcome_spec"] = outcome.to_dict()
    scope["outcome_spec_hash"] = outcome.content_hash()
    return scope


def _grammar_scope_for_frame(
    population: PopulationSpec,
    outcome: OutcomeSpec,
    base_scope: Dict[str, Any],
    *,
    observation_horizon: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Build research scope for a frame, respecting information-horizon legality.

    Outcome-derived population filters are valid only at/after their availability horizon.
    """
    from modules.edge_research.research_frame import validate_population_at_horizon

    try:
        validate_outcome_spec(outcome)
        validate_population_at_horizon(population, observation_horizon=observation_horizon)
    except GrammarValidationError:
        return None

    scope = _base_scope(base_scope)
    if observation_horizon <= 0:
        try:
            scope.update(population_spec_to_research_scope(population))
        except GrammarValidationError:
            return None
    else:
        scope["population_spec"] = population.to_dict()
        scope["population_spec_hash"] = population.content_hash()
    scope["outcome_spec"] = outcome.to_dict()
    scope["outcome_spec_hash"] = outcome.content_hash()
    scope["research_observation_horizon"] = observation_horizon
    return scope


def _add_grammar_candidates(
    candidates: List[ResearchActionCandidate],
    *,
    assessment: ResearchAssessment,
    graph: ResearchGraph,
    registry: ToolRegistry,
    scope: Dict[str, Any],
    cutoff: str,
    experiment_node_id: str,
) -> None:
    """Propose REFRAME / REPOPULATE / WIDEN candidates from question grammar."""
    ctx = _question_context_from_experiment(graph, experiment_node_id)
    if ctx is None:
        return

    population, outcome = _parse_specs_from_context(ctx)
    depth = ctx.research_depth
    parent_hash = population.content_hash()
    evidence = {
        "source_experiment": experiment_node_id,
        "interesting": assessment.interesting,
        "strength": assessment.descriptive_strength,
    }

    def add(**kwargs: Any) -> None:
        candidates.append(_check_candidate(graph, registry=registry, **kwargs))

    # REFRAME / REDESCRIBE OUTCOME — when branch shows signal worth reframing.
    if assessment.interesting or assessment.descriptive_strength == "GROUP_DIFFERENCE":
        for alt_outcome in propose_outcome_reframes(outcome):
            new_depth = depth + 1
            accounting = build_search_accounting(
                population_spec=population,
                outcome_spec=alt_outcome,
                research_depth=new_depth,
                parent_branch_hash=parent_hash,
            )
            new_scope = _grammar_scope(population, alt_outcome, scope)
            new_scope["outcome_reframe"] = True
            new_scope["frame_transformation"] = "OUTCOME_REFRAME"
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=population.to_dict(),
                outcome_spec=alt_outcome.to_dict(),
                research_depth=new_depth,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                population_change={
                    "parent_population_hash": parent_hash,
                    "reason_code": "REFRAME_OUTCOME",
                    "triggering_evidence": evidence,
                },
            ).to_dict()
            add(
                action_code="REFRAME_OUTCOME",
                intent=ActionIntent.REFRAME,
                template_id="REFRAME_ALTERNATIVE_OUTCOME",
                question=f"Does an alternative outcome specification ({alt_outcome.kind}) reveal a stable relationship?",
                tool_name="horizon_comparison",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="horizon_comparison",
                    tool_version="v1",
                    inputs={"horizons": list(HORIZONS)},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="OUTCOME_SPEC_ALTERNATIVE",
                expected_info=ExpectedInformation.MEDIUM,
                rationale_codes=("REFRAME", "ALTERNATIVE_OUTCOME"),
                priority_hints={"information_gap": 2.5, "grammar_reframe": 2.0},
            )

    # REPOPULATE — refine population when signal warrants conditional cohort.
    if assessment.additional_investigation_warranted and not assessment.fragility_evidence:
        for refined in propose_population_refinements(
            population,
            reason_code="EVIDENCE_CONDITIONAL_COHORT",
            triggering_evidence=evidence,
        ):
            new_depth = depth + 1
            accounting = build_search_accounting(
                population_spec=refined,
                outcome_spec=outcome,
                research_depth=new_depth,
                parent_branch_hash=parent_hash,
            )
            new_scope = _grammar_scope(refined, outcome, scope)
            new_scope["population_reframe"] = True
            new_scope["frame_transformation"] = "POPULATION_REFRAME"
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=refined.to_dict(),
                outcome_spec=outcome.to_dict(),
                research_depth=new_depth,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                population_change={
                    "parent_population_hash": parent_hash,
                    "reason_code": "REPOPULATE_REFINE",
                    "triggering_evidence": evidence,
                },
            ).to_dict()
            add(
                action_code="REPOPULATE_REFINE",
                intent=ActionIntent.REPOPULATE,
                template_id="REPOPULATE_REFINED_COHORT",
                question="Does the relationship hold within a refined conditional population?",
                tool_name="partition_group_compare",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="partition_group_compare",
                    tool_version="v1",
                    inputs={
                        "horizon": DEFAULT_HORIZON,
                        "partition_column": "partition_group",
                        "partition_type": "categorical",
                    },
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="POPULATION_REFINEMENT",
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("REPOPULATE", "REFINED_COHORT"),
                priority_hints={"information_gap": 3.0, "grammar_repopulate": 2.5},
            )

    # WIDEN — when population is already refined and sample may be too narrow.
    if population.kind in ("refine", "and", "filter") and population.kind != "all":
        for widened in propose_population_widenings(
            population,
            reason_code="EVIDENCE_SAMPLE_NARROW",
            triggering_evidence=evidence,
        ):
            new_depth = max(0, depth)
            accounting = build_search_accounting(
                population_spec=widened,
                outcome_spec=outcome,
                research_depth=new_depth,
                parent_branch_hash=parent_hash,
            )
            new_scope = _grammar_scope(widened, outcome, scope)
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=widened.to_dict(),
                outcome_spec=outcome.to_dict(),
                research_depth=new_depth,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                population_change={
                    "parent_population_hash": parent_hash,
                    "reason_code": "REPOPULATE_WIDEN",
                    "triggering_evidence": evidence,
                },
            ).to_dict()
            add(
                action_code="REPOPULATE_WIDEN",
                intent=ActionIntent.REPOPULATE,
                template_id="REPOPULATE_WIDENED_COHORT",
                question="Does widening the population preserve or weaken the observed relationship?",
                tool_name="partition_group_compare",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="partition_group_compare",
                    tool_version="v1",
                    inputs={
                        "horizon": DEFAULT_HORIZON,
                        "partition_column": "partition_group",
                        "partition_type": "categorical",
                    },
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="POPULATION_WIDENING",
                expected_info=ExpectedInformation.MEDIUM,
                rationale_codes=("REPOPULATE", "WIDEN_COHORT"),
                priority_hints={"information_gap": 1.5, "grammar_widen": 2.0},
            )


def _experiment_metrics(graph: ResearchGraph, experiment_node_id: str) -> Dict[str, Any]:
    node = graph.get_node(experiment_node_id)
    if node.experiment_result and node.experiment_result.metrics:
        return dict(node.experiment_result.metrics)
    return {}


def _derive_threshold_cuts(metrics: Dict[str, Any]) -> Tuple[List[float], str, str]:
    """Data-derived cut candidates from adaptive partition experiment."""
    feature = str(metrics.get("feature_column", "feature_x"))
    edges = metrics.get("discovered_boundaries") or []
    shape = metrics.get("shape") or {}
    direction = "high"
    if shape.get("shape_code") == "SHAPE_MONOTONIC_DECREASING":
        direction = "low"
    cuts = [float(e) for e in edges]
    if not cuts and metrics.get("best_threshold"):
        cuts = [float(metrics["best_threshold"].get("threshold", 0.0))]
    return cuts, direction, feature


def _add_adaptive_candidates(
    candidates: List[ResearchActionCandidate],
    *,
    assessment: ResearchAssessment,
    graph: ResearchGraph,
    registry: ToolRegistry,
    scope: Dict[str, Any],
    cutoff: str,
    experiment_node_id: str,
    panel_columns: Optional[Sequence[str]] = None,
) -> None:
    """Phase 3F evidence-driven adaptive slicing follow-ups."""

    def add(**kwargs: Any) -> None:
        candidates.append(_check_candidate(graph, registry=registry, **kwargs))

    from modules.edge_research.research_panel_preflight import adaptive_features_from_columns

    metrics = _experiment_metrics(graph, experiment_node_id)
    exp_node = graph.get_node(experiment_node_id)
    parent_tool = exp_node.experiment_spec.tool_name if exp_node.experiment_spec else ""

    partition_feats: Tuple[str, ...] = ()
    if panel_columns:
        partition_feats = adaptive_features_from_columns(panel_columns)

    # Initial adaptive partition on eligible continuous features (exploration).
    if parent_tool not in ("adaptive_partition_compare", "threshold_exploration", "threshold_neighborhood"):
        if assessment.additional_investigation_warranted or assessment.interesting:
            feats = partition_feats if partition_feats else ("feature_x", "feature_y", "rs10")
            for feat in feats:
                add(
                    action_code=f"ADAPTIVE_PARTITION_{feat}",
                    intent=ActionIntent.SLICING,
                    template_id="ADAPTIVE_PARTITION",
                    question=f"Does partitioning {feat} by data-derived quantiles reveal outcome structure?",
                    tool_name="adaptive_partition_compare",
                    tool_version="v1",
                    spec=_make_spec(
                        tool_name="adaptive_partition_compare",
                        tool_version="v1",
                        inputs={"feature_column": feat, "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
                        research_scope=scope,
                        cutoff=cutoff,
                    ),
                    uncertainty="ADAPTIVE_PARTITION",
                    expected_info=ExpectedInformation.HIGH,
                    rationale_codes=("SLICING", "ADAPTIVE_PARTITION"),
                    priority_hints={"slicing_explore": 2.0},
                )

    # Threshold exploration when shape/gradient evidence exists.
    if GAP_THRESHOLD_EXPLORATION in assessment.information_gaps or any(
        c.startswith("SHAPE_") for c in assessment.empirical_findings
    ):
        cuts, direction, feature = _derive_threshold_cuts(metrics)
        if cuts:
            new_scope = dict(scope)
            new_scope["pending_lineage"] = {
                "triggering_experiment": experiment_node_id,
                "triggering_observation": "SHAPE_GRADIENT",
                "reason_code": "EXPLORE_THRESHOLD",
                "discovered_boundaries": cuts,
            }
            add(
                action_code="EXPLORE_THRESHOLD",
                intent=ActionIntent.EXPLORE_THRESHOLD,
                template_id="THRESHOLD_EXPLORATION",
                question=f"Which data-derived cut on {feature} best separates outcomes?",
                tool_name="threshold_exploration",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="threshold_exploration",
                    tool_version="v1",
                    inputs={
                        "feature_column": feature,
                        "candidate_cuts": cuts,
                        "direction": direction,
                        "parent_experiment_id": experiment_node_id,
                    },
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty=GAP_THRESHOLD_EXPLORATION,
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("EXPLORE_THRESHOLD", "SHAPE_EVIDENCE"),
                priority_hints={"threshold_explore": 4.5, "shape_followup": 3.5},
            )

    # Neighborhood stability after threshold exploration.
    if parent_tool == "threshold_exploration" or GAP_NEIGHBORHOOD_THRESHOLD in assessment.information_gaps:
        best = metrics.get("best_threshold") or {}
        threshold = best.get("threshold")
        feature = str(metrics.get("feature_column", "feature_x"))
        if threshold is not None:
            add(
                action_code="TEST_NEIGHBORHOOD",
                intent=ActionIntent.TEST_NEIGHBORHOOD,
                template_id="THRESHOLD_NEIGHBORHOOD",
                question=f"Is the threshold region around {threshold} on {feature} stable?",
                tool_name="threshold_neighborhood",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="threshold_neighborhood",
                    tool_version="v1",
                    inputs={
                        "feature_column": feature,
                        "center_threshold": float(threshold),
                        "direction": best.get("direction", "high"),
                    },
                    research_scope={
                        **scope,
                        "pending_lineage": {
                            "triggering_experiment": experiment_node_id,
                            "reason_code": "TEST_NEIGHBORHOOD",
                            "center_threshold": threshold,
                        },
                    },
                    cutoff=cutoff,
                ),
                uncertainty=GAP_NEIGHBORHOOD_THRESHOLD,
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("TEST_NEIGHBORHOOD", "THRESHOLD_REGION"),
                priority_hints={"neighborhood_test": 4.0},
            )

    # Population refinement from high/low region or category separation.
    if GAP_CATEGORY_REFINEMENT in assessment.information_gaps or "CATEGORY_SEPARATION_DETECTED" in assessment.empirical_findings:
        feature = str(metrics.get("feature_column", "partition_group"))
        best_cat = metrics.get("best_category", "A")
        ctx = _question_context_from_experiment(graph, experiment_node_id)
        if ctx:
            pop, out = _parse_specs_from_context(ctx)
            refined = PopulationSpec.refine(
                pop,
                PopulationSpec.filter_categorical(feature, [str(best_cat)]),
                reason_code="CONDITION_ON_CATEGORY",
                triggering_evidence={"source_experiment": experiment_node_id},
            )
            new_scope = _grammar_scope(refined, out, scope)
            add(
                action_code="CONDITION_ON_CATEGORY",
                intent=ActionIntent.REPOPULATE,
                template_id="CATEGORY_POPULATION_REFINE",
                question=f"Does conditioning on {feature}={best_cat} preserve the relationship?",
                tool_name="categorical_adaptive_compare",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="categorical_adaptive_compare",
                    tool_version="v1",
                    inputs={"feature_column": feature},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty=GAP_CATEGORY_REFINEMENT,
                expected_info=ExpectedInformation.MEDIUM,
                rationale_codes=("REPOPULATE", "CATEGORY_SEPARATION"),
                priority_hints={"category_refinement": 3.0},
            )

    # High/low region population conditioning after threshold discovery.
    if parent_tool == "threshold_exploration" and metrics.get("best_threshold"):
        best = metrics["best_threshold"]
        threshold = best.get("threshold")
        feature = str(metrics.get("feature_column", "feature_x"))
        direction = best.get("direction", "high")
        op = ">=" if direction == "high" else "<="
        ctx = _question_context_from_experiment(graph, experiment_node_id)
        if ctx and threshold is not None:
            pop, out = _parse_specs_from_context(ctx)
            filt = PopulationSpec.filter_numeric(feature, op, float(threshold))
            refined = PopulationSpec.refine(
                pop,
                filt,
                reason_code="CONDITION_ON_HIGH_REGION" if direction == "high" else "CONDITION_ON_LOW_REGION",
                triggering_evidence={
                    "source_experiment": experiment_node_id,
                    "threshold": threshold,
                },
            )
            new_scope = _grammar_scope(refined, out, scope)
            action_code = "CONDITION_ON_HIGH_REGION" if direction == "high" else "CONDITION_ON_LOW_REGION"
            add(
                action_code=action_code,
                intent=ActionIntent.REPOPULATE,
                template_id="THRESHOLD_POPULATION_REFINE",
                question=f"Does the outcome pattern hold within the {direction} region of {feature}?",
                tool_name="adaptive_partition_compare",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="adaptive_partition_compare",
                    tool_version="v1",
                    inputs={"feature_column": feature, "max_bins": 3, "min_bin_n": 5},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="POPULATION_REGION",
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("REPOPULATE", "THRESHOLD_REGION"),
                priority_hints={"region_refinement": 3.5},
            )

    # Bounded interaction when shape interesting and market context untested.
    if assessment.interesting and GAP_MARKET_DEPENDENCE in assessment.information_gaps:
        feature = str(metrics.get("feature_column", "feature_x"))
        add(
            action_code="TEST_MARKET_INTERACTION",
            intent=ActionIntent.CONDITIONING,
            template_id="INTERACTION_PARTITION",
            question=f"Does market context interact with {feature} for outcomes?",
            tool_name="interaction_partition",
            tool_version="v1",
            spec=_make_spec(
                tool_name="interaction_partition",
                tool_version="v1",
                inputs={
                    "primary_feature": feature,
                    "secondary_feature": "research_market_state",
                },
                research_scope={**scope, "complexity_increment": 2},
                cutoff=cutoff,
            ),
            uncertainty=GAP_INTERACTION_FOLLOWUP,
            expected_info=ExpectedInformation.MEDIUM,
            rationale_codes=("INTERACTION", "MARKET_CONTEXT"),
            priority_hints={"interaction_followup": 2.5},
        )

    # Explicit falsification concentration tests (compete with exploration).
    if FALSIFY_DATE_ARTIFACT in assessment.possible_falsification_targets:
        add(
            action_code="FALSIFY_DATE_CONCENTRATION",
            intent=ActionIntent.FALSIFICATION,
            template_id="FALSIFY_DATE_ARTIFACT",
            question="Does the result survive leave-one-date-out removal?",
            tool_name="sensitivity_analysis",
            tool_version="v1",
            spec=_make_spec(
                tool_name="sensitivity_analysis",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON, "tests": ["leave_one_date"]},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=FALSIFY_DATE_ARTIFACT,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("FALSIFY", "DATE_CONCENTRATION"),
            priority_hints={"falsification_threat": 3.5},
        )


DEFAULT_HORIZON_LIST = ["T3", "T5", "T10"]
HORIZONS = DEFAULT_HORIZON_LIST  # alias for grammar candidates


def _add_frame_reframe_candidates(
    candidates: List[ResearchActionCandidate],
    *,
    assessment: ResearchAssessment,
    graph: ResearchGraph,
    registry: ToolRegistry,
    scope: Dict[str, Any],
    cutoff: str,
    experiment_node_id: str,
    panel_columns: Optional[Sequence[str]] = None,
) -> None:
    """Phase 3G.2 — autonomous outcome/population/horizon reframing from frame saturation."""
    from modules.edge_research.research_frame import (
        FrameStatus,
        FrameTransformationType,
        ResearchFrame,
        assess_frame_saturation,
        check_sample_sufficiency,
        propose_horizon_advancement_frames,
        propose_population_from_observed_data,
        propose_structural_reframes,
        validate_frame_temporal_legality,
    )

    ctx = _question_context_from_experiment(graph, experiment_node_id)
    if ctx is None:
        return

    population, outcome = _parse_specs_from_context(ctx)
    reg = graph.get_frame_registry()
    frame_id = ctx.frame_id or reg.active_frame_id
    if not frame_id:
        fid = reg.next_id()
        preflight = graph.session.panel_preflight or {}
        eligible = len(preflight.get("eligible_explanatory") or [])
        frame = ResearchFrame.initial(fid, population, outcome, eligible_feature_count=eligible)
        reg.register(frame)
        graph.persist_frames()
        frame_id = fid

    frame = reg.get(frame_id)
    if frame is None:
        frame = ResearchFrame.initial(frame_id, population, outcome)
        reg.register(frame)

    status, sat_evidence = assess_frame_saturation(frame)
    frame.status = status
    saturated = status in (FrameStatus.LOW_YIELD.value, FrameStatus.EXHAUSTED.value)

    def add(**kwargs: Any) -> None:
        candidates.append(_check_candidate(graph, registry=registry, **kwargs))

    depth = ctx.research_depth
    parent_hash = population.content_hash()
    parent_n = ctx.population_n or 100

    # Structural observation → new frames (even without conditional candidate).
    if assessment.observation_kind in ("STRUCTURAL_OBSERVATION", "DESCRIPTIVE_OBSERVATION"):
        for child_frame in propose_structural_reframes(
            frame,
            observation_kind=assessment.observation_kind,
            observation_codes=assessment.empirical_findings,
        ):
            new_id = reg.next_id()
            child = child_frame.child(
                new_id,
                population=child_frame.population,
                outcome=child_frame.outcome,
                observation_horizon=child_frame.observation_horizon,
                transformation=child_frame.transformation,
                reason=child_frame.reason_created,
                evidence=child_frame.triggering_evidence,
            )
            accounting = build_search_accounting(
                population_spec=child.population,
                outcome_spec=child.outcome,
                research_depth=depth + 1,
                parent_branch_hash=parent_hash,
                alternatives_considered=1,
            )
            new_scope = _grammar_scope_for_frame(
                child.population,
                child.outcome,
                scope,
                observation_horizon=child.observation_horizon,
            )
            if new_scope is None:
                continue
            new_scope["outcome_reframe"] = child.outcome.content_hash() != frame.outcome.content_hash()
            new_scope["population_reframe"] = child.population.content_hash() != frame.population.content_hash()
            new_scope["frame_transformation"] = child.transformation
            new_scope["research_observation_horizon"] = child.observation_horizon
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=child.population.to_dict(),
                outcome_spec=child.outcome.to_dict(),
                research_depth=depth + 1,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                frame_id=new_id,
                observation_horizon=child.observation_horizon,
                population_change={
                    "parent_population_hash": parent_hash,
                    "reason_code": child.transformation,
                    "triggering_evidence": child.triggering_evidence,
                },
            ).to_dict()
            hint = 4.0 if saturated else 2.0
            if child.transformation == FrameTransformationType.OUTCOME_REFRAME.value:
                hint_key = "new_outcome_bonus"
            elif child.transformation == FrameTransformationType.POPULATION_REFRAME.value:
                hint_key = "new_population_bonus"
            elif child.transformation == FrameTransformationType.OUTCOME_TO_POPULATION.value:
                hint_key = "new_information_horizon_bonus"
            else:
                hint_key = "frame_novelty_bonus"
            add(
                action_code=f"REFRAME_{child.transformation}_{new_id}",
                intent=ActionIntent.REFRAME if "OUTCOME" in child.transformation else ActionIntent.REPOPULATE,
                template_id="FRAME_REFRAME",
                question=f"Reframe research: {child.reason_created}",
                tool_name="horizon_comparison",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="horizon_comparison",
                    tool_version="v1",
                    inputs={"horizons": list(HORIZONS)},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="FRAME_REFRAME",
                expected_info=ExpectedInformation.HIGH if saturated else ExpectedInformation.MEDIUM,
                rationale_codes=("REFRAME", child.transformation),
                priority_hints={
                    hint_key: hint,
                    "saturated_parent_reframe_bonus": 3.0 if saturated else 0.0,
                    "grammar_reframe": 2.0,
                },
            )

    # Evidence-driven population from observed metrics (generic fields).
    if assessment.additional_investigation_warranted or saturated:
        metrics = _experiment_metrics(graph, experiment_node_id)
        cat_values: Dict[str, Tuple[str, ...]] = {}
        if metrics.get("best_category"):
            feat = str(metrics.get("feature_column", "partition_group"))
            cat_values[feat] = (str(metrics.get("best_category")),)
        num_splits: Dict[str, float] = {}
        if metrics.get("discovered_boundaries"):
            feat = str(metrics.get("feature_column", ""))
            edges = metrics.get("discovered_boundaries") or []
            if feat and edges:
                num_splits[feat] = float(edges[0])

        for refined in propose_population_from_observed_data(
            population,
            categorical_values=cat_values,
            numeric_median_splits=num_splits,
            reason_code="EVIDENCE_DERIVED_COHORT",
            triggering_evidence={"source_experiment": experiment_node_id},
        ):
            sufficient, loss = check_sample_sufficiency(resulting_n=int(parent_n * 0.4), parent_n=parent_n)
            if not sufficient and loss > 0.7:
                continue
            new_depth = depth + 1
            accounting = build_search_accounting(
                population_spec=refined,
                outcome_spec=outcome,
                research_depth=new_depth,
                parent_branch_hash=parent_hash,
            )
            new_scope = _grammar_scope(refined, outcome, scope)
            new_scope["population_reframe"] = True
            new_scope["frame_transformation"] = "POPULATION_REFRAME"
            new_scope["sample_loss_ratio"] = loss
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=refined.to_dict(),
                outcome_spec=outcome.to_dict(),
                research_depth=new_depth,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                frame_id=frame_id,
                observation_horizon=ctx.observation_horizon,
            ).to_dict()
            feat_col = "feat_alpha"
            if panel_columns:
                from modules.edge_research.research_panel_preflight import adaptive_features_from_columns
                feats = adaptive_features_from_columns(panel_columns)
                if feats:
                    feat_col = feats[0]
            add(
                action_code="REPOPULATE_EVIDENCE",
                intent=ActionIntent.REPOPULATE,
                template_id="EVIDENCE_POPULATION_REFINE",
                question="Does a data-derived conditional population reveal structure?",
                tool_name="adaptive_partition_compare",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="adaptive_partition_compare",
                    tool_version="v1",
                    inputs={"feature_column": feat_col, "max_bins": 3, "min_bin_n": 5},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="POPULATION_EVIDENCE",
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("REPOPULATE", "EVIDENCE_DERIVED"),
                priority_hints={
                    "new_population_bonus": 2.5,
                    "grammar_repopulate": 2.0,
                    "sample_loss_penalty": -2.0 if loss > 0.5 else 0.0,
                },
            )

    # Horizon advancement / outcome-to-population when frame has mature early outcome.
    if saturated or assessment.observation_kind == "STRUCTURAL_OBSERVATION":
        for child_frame in propose_horizon_advancement_frames(frame):
            new_id = reg.next_id()
            if not validate_frame_temporal_legality(child_frame):
                continue
            child = child_frame.child(
                new_id,
                population=child_frame.population,
                outcome=child_frame.outcome,
                observation_horizon=child_frame.observation_horizon,
                transformation=child_frame.transformation,
                reason=child_frame.reason_created,
                evidence=child_frame.triggering_evidence,
            )
            accounting = build_search_accounting(
                population_spec=child.population,
                outcome_spec=child.outcome,
                research_depth=depth + 1,
                parent_branch_hash=parent_hash,
            )
            new_scope = _grammar_scope_for_frame(
                child.population,
                child.outcome,
                scope,
                observation_horizon=child.observation_horizon,
            )
            if new_scope is None:
                continue
            new_scope["frame_transformation"] = FrameTransformationType.OUTCOME_TO_POPULATION.value
            new_scope["research_observation_horizon"] = child.observation_horizon
            new_scope["new_information_horizon_bonus"] = True
            new_scope["pending_question_context"] = ResearchQuestionContext(
                population_spec=child.population.to_dict(),
                outcome_spec=child.outcome.to_dict(),
                research_depth=depth + 1,
                search_complexity=accounting.predicate_count,
                search_accounting=accounting.to_dict(),
                frame_id=new_id,
                observation_horizon=child.observation_horizon,
            ).to_dict()
            add(
                action_code=f"HORIZON_ADVANCE_{new_id}",
                intent=ActionIntent.REFRAME,
                template_id="HORIZON_ADVANCEMENT",
                question=f"Advance information horizon: {child.reason_created}",
                tool_name="horizon_comparison",
                tool_version="v1",
                spec=_make_spec(
                    tool_name="horizon_comparison",
                    tool_version="v1",
                    inputs={"horizons": list(HORIZONS)},
                    research_scope=new_scope,
                    cutoff=cutoff,
                ),
                uncertainty="HORIZON_ADVANCE",
                expected_info=ExpectedInformation.HIGH,
                rationale_codes=("REFRAME", "HORIZON_ADVANCE"),
                priority_hints={
                    "new_information_horizon_bonus": 3.5,
                    "saturated_parent_reframe_bonus": 3.0 if saturated else 0.0,
                },
            )

    graph.persist_frames()


def generate_action_candidates(
    assessment: ResearchAssessment,
    graph: ResearchGraph,
    registry: ToolRegistry,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    experiment_node_id: Optional[str] = None,
    panel_columns: Optional[Sequence[str]] = None,
) -> Tuple[ResearchActionCandidate, ...]:
    """
    Generate multiple scientifically legitimate next actions from assessment.

    Observation codes are evidence inputs — not one-to-one tool mappings.
    """
    scope = _base_scope(research_scope or {})
    cutoff = graph.session.data_cutoff_date
    candidates: List[ResearchActionCandidate] = []

    def add(**kwargs: Any) -> None:
        candidates.append(_check_candidate(graph, registry=registry, **kwargs))

    # Decomposition candidates driven by information gaps.
    if GAP_TIME_DISTRIBUTION in assessment.information_gaps:
        add(
            action_code="DECOMPOSE_DATE",
            intent=ActionIntent.DECOMPOSITION,
            template_id="UNCERTAIN_TIME_DISTRIBUTION",
            question="Is the observed relationship broadly distributed across dates or concentrated?",
            tool_name="date_decomposition",
            tool_version="v1",
            spec=_make_spec(
                tool_name="date_decomposition",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_TIME_DISTRIBUTION,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("GAP_TIME", "DECOMPOSITION"),
            priority_hints={"information_gap": 3.0},
        )

    if GAP_SYMBOL_DISTRIBUTION in assessment.information_gaps:
        add(
            action_code="DECOMPOSE_SYMBOL",
            intent=ActionIntent.DECOMPOSITION,
            template_id="UNCERTAIN_SYMBOL_DISTRIBUTION",
            question="Is the observed relationship broadly distributed across symbols or dominated by few names?",
            tool_name="symbol_decomposition",
            tool_version="v1",
            spec=_make_spec(
                tool_name="symbol_decomposition",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_SYMBOL_DISTRIBUTION,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("GAP_SYMBOL", "DECOMPOSITION"),
            priority_hints={"information_gap": 3.0},
        )

    if GAP_EPISODE_REPLICATION in assessment.information_gaps:
        add(
            action_code="DECOMPOSE_EPISODE",
            intent=ActionIntent.REPLICATION,
            template_id="UNCERTAIN_EPISODE_REPLICATION",
            question="Does the relationship replicate across independent market episodes?",
            tool_name="episode_decomposition",
            tool_version="v1",
            spec=_make_spec(
                tool_name="episode_decomposition",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_EPISODE_REPLICATION,
            expected_info=ExpectedInformation.MEDIUM,
            rationale_codes=("GAP_EPISODE", "REPLICATION"),
            priority_hints={"information_gap": 2.5},
        )

    if GAP_MARKET_DEPENDENCE in assessment.information_gaps:
        add(
            action_code="CONDITION_MARKET",
            intent=ActionIntent.CONDITIONING,
            template_id="UNCERTAIN_MARKET_DEPENDENCE",
            question="How does the relationship differ across market states?",
            tool_name="market_conditioning",
            tool_version="v1",
            spec=_make_spec(
                tool_name="market_conditioning",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON, "partition_by": "research_market_state"},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_MARKET_DEPENDENCE,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("GAP_MARKET", "CONDITIONING"),
            priority_hints={"information_gap": 3.5},
        )

    if GAP_HORIZON_STABILITY in assessment.information_gaps:
        add(
            action_code="COMPARE_HORIZON",
            intent=ActionIntent.ROBUSTNESS,
            template_id="UNCERTAIN_HORIZON_STABILITY",
            question="Does the relationship behave consistently across T3/T5/T10?",
            tool_name="horizon_comparison",
            tool_version="v1",
            spec=_make_spec(
                tool_name="horizon_comparison",
                tool_version="v1",
                inputs={"horizons": ["T3", "T5", "T10"]},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_HORIZON_STABILITY,
            expected_info=ExpectedInformation.MEDIUM,
            rationale_codes=("GAP_HORIZON", "ROBUSTNESS"),
            priority_hints={"information_gap": 2.0},
        )

    if GAP_TRAJECTORY_ROLE in assessment.information_gaps:
        add(
            action_code="TRAJECTORY_COMPARE",
            intent=ActionIntent.EXPLORATION,
            template_id="UNCERTAIN_TRAJECTORY_ROLE",
            question="Does an explicit T0-safe temporal feature partition explain outcome differences?",
            tool_name="trajectory_partition_compare",
            tool_version="v1",
            spec=_make_spec(
                tool_name="trajectory_partition_compare",
                tool_version="v1",
                inputs={
                    "temporal_feature": DEFAULT_TRAJECTORY_FEATURE,
                    "bins": list(DEFAULT_TRAJECTORY_BINS),
                    "horizon": DEFAULT_HORIZON,
                },
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=GAP_TRAJECTORY_ROLE,
            expected_info=ExpectedInformation.MEDIUM,
            rationale_codes=("GAP_TRAJECTORY", "EXPLORATION"),
            priority_hints={"information_gap": 2.5},
        )

    # Falsification candidates — compete with exploration, not a pipeline stage.
    if FALSIFY_EXTREME_WINNER in assessment.possible_falsification_targets:
        threat = 4.0 if assessment.interesting else 2.0
        if "EXTREME_WINNER" in assessment.concentration_concerns or assessment.interesting:
            threat = 4.5
        add(
            action_code="FALSIFY_EXTREME",
            intent=ActionIntent.FALSIFICATION,
            template_id="FALSIFY_EXTREME_WINNER",
            question="Does the result survive removal of the largest positive outcome?",
            tool_name="sensitivity_analysis",
            tool_version="v1",
            spec=_make_spec(
                tool_name="sensitivity_analysis",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON, "tests": ["remove_largest_positive"]},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=FALSIFY_EXTREME_WINNER,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("FALSIFY", "EXTREME_WINNER"),
            priority_hints={"falsification_threat": threat},
        )

    if FALSIFY_DATE_ARTIFACT in assessment.possible_falsification_targets:
        add(
            action_code="FALSIFY_DATE",
            intent=ActionIntent.FALSIFICATION,
            template_id="FALSIFY_DATE_ARTIFACT",
            question="Does the result survive leave-one-date-out removal?",
            tool_name="sensitivity_analysis",
            tool_version="v1",
            spec=_make_spec(
                tool_name="sensitivity_analysis",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON, "tests": ["leave_one_date"]},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=FALSIFY_DATE_ARTIFACT,
            expected_info=ExpectedInformation.HIGH,
            rationale_codes=("FALSIFY", "DATE_ARTIFACT"),
            priority_hints={"falsification_threat": 3.5},
        )

    if FALSIFY_SYMBOL_DOMINANCE in assessment.possible_falsification_targets:
        add(
            action_code="FALSIFY_SYMBOL",
            intent=ActionIntent.FALSIFICATION,
            template_id="FALSIFY_SYMBOL_DOMINANCE",
            question="Does the result survive leave-one-symbol-out removal?",
            tool_name="sensitivity_analysis",
            tool_version="v1",
            spec=_make_spec(
                tool_name="sensitivity_analysis",
                tool_version="v1",
                inputs={"horizon": DEFAULT_HORIZON, "tests": ["leave_one_symbol"]},
                research_scope=scope,
                cutoff=cutoff,
            ),
            uncertainty=FALSIFY_SYMBOL_DOMINANCE,
            expected_info=ExpectedInformation.MEDIUM,
            rationale_codes=("FALSIFY", "SYMBOL_DOMINANCE"),
            priority_hints={"falsification_threat": 3.0},
        )

    # Grammar-driven REFRAME / REPOPULATE candidates (Phase 3E).
    if experiment_node_id:
        _add_grammar_candidates(
            candidates,
            assessment=assessment,
            graph=graph,
            registry=registry,
            scope=scope,
            cutoff=cutoff,
            experiment_node_id=experiment_node_id,
        )
        _add_adaptive_candidates(
            candidates,
            assessment=assessment,
            graph=graph,
            registry=registry,
            scope=scope,
            cutoff=cutoff,
            experiment_node_id=experiment_node_id,
            panel_columns=panel_columns,
        )
        _add_frame_reframe_candidates(
            candidates,
            assessment=assessment,
            graph=graph,
            registry=registry,
            scope=scope,
            cutoff=cutoff,
            experiment_node_id=experiment_node_id,
            panel_columns=panel_columns,
        )

    # Terminal candidates — always available; planner may select immediately.
    stop_urgency = 0.0
    if not assessment.additional_investigation_warranted:
        stop_urgency = 5.0
    if assessment.fragility_evidence and not assessment.information_gaps:
        stop_urgency = 6.0
    add(
        action_code="STOP_BRANCH",
        intent=ActionIntent.STOP,
        template_id="STOP_NO_FURTHER_VALUE",
        question="Stop this branch — no further investigation warranted.",
        tool_name="",
        tool_version="",
        spec=None,
        uncertainty="STOP",
        expected_info=ExpectedInformation.LOW,
        rationale_codes=("STOP", "NO_FURTHER_VALUE"),
        priority_hints={"stop_urgency": stop_urgency},
    )

    abandon_urgency = 0.0
    if assessment.fragility_evidence:
        abandon_urgency = 4.0
    if "FRAGILITY_AFTER_EPISODE_CONSISTENT" in assessment.contradictions:
        abandon_urgency = 5.0
    add(
        action_code="ABANDON_BRANCH",
        intent=ActionIntent.ABANDON,
        template_id="ABANDON_FRAGILE",
        question="Abandon this branch — fragility or contradiction undermines the hypothesis.",
        tool_name="",
        tool_version="",
        spec=None,
        uncertainty="ABANDON",
        expected_info=ExpectedInformation.LOW,
        rationale_codes=("ABANDON", "FRAGILITY"),
        priority_hints={"abandon_urgency": abandon_urgency},
    )

    add(
        action_code="STOP_SESSION",
        intent=ActionIntent.STOP_SESSION,
        template_id="STOP_SESSION_GLOBAL",
        question="Stop entire research session — global stopping criteria satisfied.",
        tool_name="",
        tool_version="",
        spec=None,
        uncertainty="STOP_SESSION",
        expected_info=ExpectedInformation.LOW,
        rationale_codes=("STOP_SESSION", "GLOBAL"),
        priority_hints={"stop_urgency": 0.0},
    )

    # Deduplicate by action_id while preserving order.
    seen: set[str] = set()
    unique: List[ResearchActionCandidate] = []
    for c in candidates:
        if c.action_id not in seen:
            seen.add(c.action_id)
            unique.append(c)

    if experiment_node_id:
        unique = list(_apply_complexity_hints(unique, graph, experiment_node_id))

    return tuple(unique)


def _apply_complexity_hints(
    candidates: List[ResearchActionCandidate],
    graph: ResearchGraph,
    experiment_node_id: str,
) -> List[ResearchActionCandidate]:
    """Add draft vs parent complexity for planner penalty."""
    ctx = _question_context_from_experiment(graph, experiment_node_id)
    if ctx is None:
        return candidates
    try:
        pop, out = _parse_specs_from_context(ctx)
        parent_complexity = float(pop.complexity() + out.complexity())
    except Exception:
        parent_complexity = 0.0

    enriched: List[ResearchActionCandidate] = []
    for c in candidates:
        hints = dict(c.priority_hints)
        hints.setdefault("parent_complexity", parent_complexity)
        draft_complexity = parent_complexity
        if c.draft_spec and c.draft_spec.research_scope.get("pending_question_context"):
            pctx = ResearchQuestionContext.from_dict(
                c.draft_spec.research_scope["pending_question_context"]
            )
            try:
                dp, do = _parse_specs_from_context(pctx)
                draft_complexity = float(dp.complexity() + do.complexity())
            except Exception:
                pass
        elif c.draft_spec and c.draft_spec.research_scope.get("population_spec"):
            try:
                dp = PopulationSpec.from_dict(c.draft_spec.research_scope["population_spec"])
                do_raw = c.draft_spec.research_scope.get("outcome_spec")
                do = OutcomeSpec.from_dict(do_raw) if do_raw else out
                draft_complexity = float(dp.complexity() + do.complexity())
            except Exception:
                pass
        hints["draft_complexity"] = draft_complexity
        if pop.kind == "refine" or pop.parent is not None:
            hints["population_refined"] = 1.0
        enriched.append(
            ResearchActionCandidate(
                action_id=c.action_id,
                action_code=c.action_code,
                intent=c.intent,
                question_template_id=c.question_template_id,
                question_text=c.question_text,
                tool_name=c.tool_name,
                tool_version=c.tool_version,
                draft_spec=c.draft_spec,
                uncertainty_addressed=c.uncertainty_addressed,
                expected_information=c.expected_information,
                budget_cost=c.budget_cost,
                already_attempted=c.already_attempted,
                blocked=c.blocked,
                blocked_reason=c.blocked_reason,
                rationale_codes=c.rationale_codes,
                priority_hints=hints,
            )
        )
    return enriched


def viable_candidates(candidates: Sequence[ResearchActionCandidate]) -> Tuple[ResearchActionCandidate, ...]:
    """Non-blocked experiment candidates plus terminal actions."""
    terminal = (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    )
    return tuple(c for c in candidates if not c.blocked or c.intent in terminal)
