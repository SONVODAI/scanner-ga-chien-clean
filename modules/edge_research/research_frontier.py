"""
Research frontier — persistent unexplored action queue (Phase 3G.1).

When a branch ends, legitimate unexplored actions return here for session-wide selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.edge_research.research_actions import ResearchActionCandidate

from modules.edge_research.research_state import (
    ExperimentSpec,
    QuestionRationale,
    ResearchQuestionContext,
)

FRONTIER_VERSION = "research_frontier_v1"


class FrontierItemStatus(str, Enum):
    UNEXPLORED = "UNEXPLORED"
    SELECTED = "SELECTED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class FrontierItem:
    """One legitimate research action awaiting execution."""

    frontier_id: str
    action_id: str
    action_code: str
    parent_experiment_node_id: str
    branch_root_id: str
    action_type: str
    target_feature: str = ""
    population_spec: Dict[str, Any] = field(default_factory=dict)
    outcome_spec: Dict[str, Any] = field(default_factory=dict)
    reason_generated: str = ""
    triggering_evidence: Dict[str, Any] = field(default_factory=dict)
    expected_information: str = ""
    novelty_score: float = 0.0
    falsification_value: float = 0.0
    complexity_cost: float = 0.0
    planner_score: float = 0.0
    status: str = FrontierItemStatus.UNEXPLORED.value
    invalid_reason: str = ""
    question_text: str = ""
    draft_spec: Optional[Dict[str, Any]] = None
    frame_id: str = ""
    transformation_type: str = ""
    enqueued_sequence: int = 0
    portfolio_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frontier_id": self.frontier_id,
            "action_id": self.action_id,
            "action_code": self.action_code,
            "parent_experiment_node_id": self.parent_experiment_node_id,
            "branch_root_id": self.branch_root_id,
            "action_type": self.action_type,
            "target_feature": self.target_feature,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "reason_generated": self.reason_generated,
            "triggering_evidence": dict(self.triggering_evidence),
            "expected_information": self.expected_information,
            "novelty_score": self.novelty_score,
            "falsification_value": self.falsification_value,
            "complexity_cost": self.complexity_cost,
            "planner_score": self.planner_score,
            "status": self.status,
            "invalid_reason": self.invalid_reason,
            "question_text": self.question_text,
            "draft_spec": dict(self.draft_spec) if self.draft_spec else None,
            "frame_id": self.frame_id,
            "transformation_type": self.transformation_type,
            "enqueued_sequence": self.enqueued_sequence,
            "portfolio_score": self.portfolio_score,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FrontierItem":
        return cls(
            frontier_id=str(payload["frontier_id"]),
            action_id=str(payload.get("action_id", "")),
            action_code=str(payload.get("action_code", "")),
            parent_experiment_node_id=str(payload.get("parent_experiment_node_id", "")),
            branch_root_id=str(payload.get("branch_root_id", "")),
            action_type=str(payload.get("action_type", "")),
            target_feature=str(payload.get("target_feature", "")),
            population_spec=dict(payload.get("population_spec") or {}),
            outcome_spec=dict(payload.get("outcome_spec") or {}),
            reason_generated=str(payload.get("reason_generated", "")),
            triggering_evidence=dict(payload.get("triggering_evidence") or {}),
            expected_information=str(payload.get("expected_information", "")),
            novelty_score=float(payload.get("novelty_score", 0.0)),
            falsification_value=float(payload.get("falsification_value", 0.0)),
            complexity_cost=float(payload.get("complexity_cost", 0.0)),
            planner_score=float(payload.get("planner_score", 0.0)),
            status=str(payload.get("status", FrontierItemStatus.UNEXPLORED.value)),
            invalid_reason=str(payload.get("invalid_reason", "")),
            question_text=str(payload.get("question_text", "")),
            draft_spec=dict(payload.get("draft_spec")) if payload.get("draft_spec") else None,
            frame_id=str(payload.get("frame_id", "")),
            transformation_type=str(payload.get("transformation_type", "")),
            enqueued_sequence=int(payload.get("enqueued_sequence", 0)),
            portfolio_score=float(payload.get("portfolio_score", 0.0)),
        )

    def to_action_candidate(self) -> "ResearchActionCandidate":
        from modules.edge_research.research_actions import ResearchActionCandidate

        spec = ExperimentSpec.from_dict(self.draft_spec) if self.draft_spec else None
        return ResearchActionCandidate(
            action_id=self.action_id,
            action_code=self.action_code,
            intent=self.action_type,
            question_template_id=self.action_code,
            question_text=self.question_text,
            tool_name=spec.tool_name if spec else "",
            tool_version=spec.tool_version if spec else "",
            draft_spec=spec,
            uncertainty_addressed=self.reason_generated,
            expected_information=self.expected_information,
            budget_cost=1,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
            rationale_codes=(self.action_code,),
            priority_hints={"planner_score": self.planner_score, "from_frontier": 1.0},
        )


@dataclass
class SessionStopReason:
    """Structured reason for global session termination."""

    code: str
    detail: str = ""
    remaining_budget: int = 0
    unexplored_frontier_count: int = 0
    features_touched: int = 0
    eligible_features: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "remaining_budget": self.remaining_budget,
            "unexplored_frontier_count": self.unexplored_frontier_count,
            "features_touched": self.features_touched,
            "eligible_features": self.eligible_features,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SessionStopReason":
        return cls(
            code=str(payload.get("code", "")),
            detail=str(payload.get("detail", "")),
            remaining_budget=int(payload.get("remaining_budget", 0)),
            unexplored_frontier_count=int(payload.get("unexplored_frontier_count", 0)),
            features_touched=int(payload.get("features_touched", 0)),
            eligible_features=int(payload.get("eligible_features", 0)),
        )


@dataclass
class ResearchFrontier:
    """Session-level queue of unexplored research directions."""

    version: str = FRONTIER_VERSION
    items: Dict[str, FrontierItem] = field(default_factory=dict)
    _counter: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "items": {k: v.to_dict() for k, v in sorted(self.items.items())},
            "_counter": self._counter,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchFrontier":
        raw = payload.get("items") or {}
        return cls(
            version=str(payload.get("version", FRONTIER_VERSION)),
            items={k: FrontierItem.from_dict(v) for k, v in raw.items()},
            _counter=int(payload.get("_counter", 0)),
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def deserialize(cls, text: str) -> "ResearchFrontier":
        return cls.from_dict(json.loads(text))

    def _next_id(self) -> str:
        self._counter += 1
        return f"frontier-{self._counter:05d}"

    def unexplored_items(self) -> List[FrontierItem]:
        return [
            i
            for i in self.items.values()
            if i.status == FrontierItemStatus.UNEXPLORED.value
        ]

    def add_from_candidates(
        self,
        *,
        candidates: Sequence["ResearchActionCandidate"],
        scores: Dict[str, Tuple[float, Dict[str, float]]],
        parent_experiment_node_id: str,
        branch_root_id: str,
        selected_action_id: Optional[str],
        question_context: Optional[Dict[str, Any]] = None,
        enqueued_sequence: int = 0,
    ) -> int:
        """Enqueue non-selected experiment candidates. Returns count added."""
        existing_action_ids = {i.action_id for i in self.items.values()}
        added = 0
        qctx = question_context or {}
        pop_spec = dict(qctx.get("population_spec") or {})
        out_spec = dict(qctx.get("outcome_spec") or {})

        for cand in candidates:
            if cand.intent in ("STOP", "STOP_SESSION", "ABANDON"):
                continue
            if cand.blocked:
                self._add_invalid(cand, parent_experiment_node_id, branch_root_id, cand.blocked_reason or "blocked")
                added += 1
                continue
            if cand.action_id == selected_action_id:
                continue
            if cand.action_id in existing_action_ids:
                self._mark_duplicate_by_action_id(cand.action_id)
                continue
            if cand.draft_spec is None:
                continue

            scope = cand.draft_spec.research_scope or {}
            pending = scope.get("pending_question_context") or {}
            if pending.get("population_spec"):
                pop_spec = dict(pending["population_spec"])
            if pending.get("outcome_spec"):
                out_spec = dict(pending["outcome_spec"])
            frame_id = str(pending.get("frame_id") or scope.get("frame_id") or "")
            transformation = str(scope.get("frame_transformation") or "")

            total, comp = scores.get(cand.action_id, (0.0, {}))
            feat = _extract_feature(cand)
            fid = self._next_id()
            self.items[fid] = FrontierItem(
                frontier_id=fid,
                action_id=cand.action_id,
                action_code=cand.action_code,
                parent_experiment_node_id=parent_experiment_node_id,
                branch_root_id=branch_root_id,
                action_type=cand.intent,
                target_feature=feat,
                population_spec=pop_spec,
                outcome_spec=out_spec,
                reason_generated=cand.uncertainty_addressed,
                triggering_evidence={"parent_experiment": parent_experiment_node_id},
                expected_information=cand.expected_information,
                novelty_score=float(comp.get("novelty", 0.0)),
                falsification_value=float(comp.get("falsification_threat", 0.0)),
                complexity_cost=abs(float(comp.get("draft_complexity_penalty", 0.0))),
                planner_score=float(total),
                question_text=cand.question_text,
                draft_spec=cand.draft_spec.to_dict(),
                frame_id=frame_id,
                transformation_type=transformation,
                enqueued_sequence=enqueued_sequence,
                portfolio_score=float(total),
            )
            existing_action_ids.add(cand.action_id)
            added += 1
        return added

    def _add_invalid(
        self,
        cand: "ResearchActionCandidate",
        parent_id: str,
        branch_root: str,
        reason: str,
    ) -> None:
        if cand.action_id in {i.action_id for i in self.items.values()}:
            return
        fid = self._next_id()
        self.items[fid] = FrontierItem(
            frontier_id=fid,
            action_id=cand.action_id,
            action_code=cand.action_code,
            parent_experiment_node_id=parent_id,
            branch_root_id=branch_root,
            action_type=cand.intent,
            status=FrontierItemStatus.INVALID.value,
            invalid_reason=reason,
            question_text=cand.question_text,
            draft_spec=cand.draft_spec.to_dict() if cand.draft_spec else None,
        )

    def _mark_duplicate_by_action_id(self, action_id: str) -> None:
        for item in self.items.values():
            if item.action_id == action_id and item.status == FrontierItemStatus.UNEXPLORED.value:
                item.status = FrontierItemStatus.DUPLICATE.value

    def mark_duplicate_by_content_hash(
        self,
        content_hash: str,
        *,
        executed_node_id: str = "",
    ) -> int:
        """Mark UNEXPLORED frontier items whose draft spec matches executed identity."""
        from modules.edge_research.research_state import (
            ExperimentSpec,
            compute_experiment_content_hash,
        )

        marked = 0
        for item in self.items.values():
            if item.status != FrontierItemStatus.UNEXPLORED.value:
                continue
            if not item.draft_spec:
                continue
            try:
                spec = ExperimentSpec.from_dict(item.draft_spec)
                item_hash = compute_experiment_content_hash(spec)
            except Exception:
                continue
            if item_hash == content_hash:
                item.status = FrontierItemStatus.DUPLICATE.value
                item.invalid_reason = (
                    f"duplicate_experiment_already_executed:{content_hash}"
                )
                if executed_node_id:
                    item.triggering_evidence = {
                        **(item.triggering_evidence or {}),
                        "duplicate_of_experiment_node_id": executed_node_id,
                    }
                marked += 1
        return marked

    def mark_invalid(self, frontier_id: str, reason: str) -> None:
        if frontier_id in self.items:
            self.items[frontier_id].status = FrontierItemStatus.INVALID.value
            self.items[frontier_id].invalid_reason = reason

    def mark_selected(self, frontier_id: str) -> None:
        if frontier_id in self.items:
            self.items[frontier_id].status = FrontierItemStatus.SELECTED.value

    def mark_executed(self, frontier_id: str) -> None:
        if frontier_id in self.items:
            self.items[frontier_id].status = FrontierItemStatus.EXECUTED.value

    def mark_exhausted(self, frontier_id: str) -> None:
        if frontier_id in self.items:
            self.items[frontier_id].status = FrontierItemStatus.EXHAUSTED.value

    def select_best_unexplored(
        self,
        graph: Optional[Any] = None,
        assessment: Optional[Any] = None,
    ) -> Optional[FrontierItem]:
        """Deterministic highest-value unexplored item (portfolio-aware when graph provided)."""
        unexplored = self.unexplored_items()
        if not unexplored:
            return None
        if graph is not None and assessment is not None:
            from modules.edge_research.research_portfolio import select_best_frontier_opportunity
            selected = select_best_frontier_opportunity(graph, self, assessment)
            if selected is not None:
                return selected
        unexplored.sort(key=lambda i: (-i.planner_score, i.frontier_id))
        return unexplored[0]

    def best_unexplored_score(self) -> float:
        item = self.select_best_unexplored()
        return item.planner_score if item else 0.0

    def count_by_status(self, status: str) -> int:
        return sum(1 for i in self.items.values() if i.status == status)


def _extract_feature(cand: "ResearchActionCandidate") -> str:
    if cand.draft_spec is None:
        return ""
    inputs = cand.draft_spec.inputs or {}
    for key in ("feature_column", "partition_column", "primary_feature", "trajectory_feature"):
        if key in inputs:
            return str(inputs[key])
    return ""


def evaluate_global_stop(
    *,
    remaining_budget: int,
    frontier: ResearchFrontier,
    features_touched: int,
    eligible_feature_count: int,
    min_research_value_threshold: float = 0.5,
) -> Tuple[bool, SessionStopReason]:
    """
    Global stopping evaluation — session may stop only when justified.

    Returns (should_stop_session, reason).
    """
    unexplored = frontier.unexplored_items()
    n_unexplored = len(unexplored)

    if remaining_budget <= 0:
        return True, SessionStopReason(
            code="BUDGET_EXHAUSTED",
            detail="Experiment budget exhausted",
            remaining_budget=0,
            unexplored_frontier_count=n_unexplored,
            features_touched=features_touched,
            eligible_features=eligible_feature_count,
        )

    if n_unexplored == 0:
        return True, SessionStopReason(
            code="NO_VALID_FRONTIER",
            detail="No unexplored frontier items remain",
            remaining_budget=remaining_budget,
            unexplored_frontier_count=0,
            features_touched=features_touched,
            eligible_features=eligible_feature_count,
        )

    best_score = frontier.best_unexplored_score()
    if best_score >= min_research_value_threshold:
        return False, SessionStopReason(
            code="CONTINUE",
            detail="Unexplored frontier items exceed minimum research value",
            remaining_budget=remaining_budget,
            unexplored_frontier_count=n_unexplored,
            features_touched=features_touched,
            eligible_features=eligible_feature_count,
        )

    # Low coverage + valid frontier — do NOT stop globally.
    if features_touched < eligible_feature_count and n_unexplored > 0 and remaining_budget > 0:
        return False, SessionStopReason(
            code="CONTINUE_LOW_COVERAGE",
            detail="Eligible features remain untouched with valid frontier items",
            remaining_budget=remaining_budget,
            unexplored_frontier_count=n_unexplored,
            features_touched=features_touched,
            eligible_features=eligible_feature_count,
        )

    return True, SessionStopReason(
        code="INSUFFICIENT_RESEARCH_VALUE",
        detail="Remaining frontier items below minimum research value threshold",
        remaining_budget=remaining_budget,
        unexplored_frontier_count=n_unexplored,
        features_touched=features_touched,
        eligible_features=eligible_feature_count,
    )
