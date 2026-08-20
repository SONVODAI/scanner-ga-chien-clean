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
from modules.edge_research.research_interpreter import (
    FALSIFY_DATE_ARTIFACT,
    FALSIFY_EPISODE_FLUKE,
    FALSIFY_EXTREME_WINNER,
    FALSIFY_SYMBOL_DOMINANCE,
    GAP_EPISODE_REPLICATION,
    GAP_HORIZON_STABILITY,
    GAP_MARKET_DEPENDENCE,
    GAP_NEIGHBORHOOD_STABILITY,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_TIME_DISTRIBUTION,
    GAP_TRAJECTORY_ROLE,
)
from modules.edge_research.research_state import ExperimentSpec, NextActionCandidate, compute_experiment_content_hash
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
    STOP = "STOP"
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

    if intent in (ActionIntent.STOP, ActionIntent.ABANDON):
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


def generate_action_candidates(
    assessment: ResearchAssessment,
    graph: ResearchGraph,
    registry: ToolRegistry,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
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

    # Deduplicate by action_id while preserving order.
    seen: set[str] = set()
    unique: List[ResearchActionCandidate] = []
    for c in candidates:
        if c.action_id not in seen:
            seen.add(c.action_id)
            unique.append(c)
    return tuple(unique)


def viable_candidates(candidates: Sequence[ResearchActionCandidate]) -> Tuple[ResearchActionCandidate, ...]:
    """Non-blocked experiment candidates plus terminal actions."""
    return tuple(c for c in candidates if not c.blocked or c.intent in (ActionIntent.STOP.value, ActionIntent.ABANDON.value))
