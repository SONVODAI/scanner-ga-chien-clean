"""
Deterministic research graph manager for Edge Research (PATCH 3A).

Graph + lineage + deduplication only — no planner, no LLM, no edge search.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from modules.edge_research.contracts import GUARDRAILS_CONFIG_VERSION
from modules.edge_research.research_state import (
    RESEARCH_GRAPH_SCHEMA_VERSION,
    EvidenceReference,
    ExperimentResult,
    ExperimentSpec,
    NextActionCandidate,
    NodeStatus,
    NodeType,
    QuestionRationale,
    ResearchGraphSnapshot,
    ResearchNode,
    ResearchSession,
    ResearchTrigger,
    SessionStatus,
    StructuredResearchObservation,
    compute_experiment_content_hash,
    compute_result_hash,
)


class ResearchGraphError(ValueError):
    """Raised when graph operations violate invariants."""


class DuplicateExperimentError(ResearchGraphError):
    """Raised when an identical experiment spec is attempted again."""

    def __init__(self, content_hash: str, existing_node_id: str) -> None:
        super().__init__(
            f"Duplicate experiment content_hash={content_hash} "
            f"already recorded at node {existing_node_id}"
        )
        self.content_hash = content_hash
        self.existing_node_id = existing_node_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ResearchGraph:
    """In-memory research graph with deterministic serialization."""

    def __init__(
        self,
        session: ResearchSession,
        nodes: Optional[Dict[str, ResearchNode]] = None,
        experiment_index: Optional[Dict[str, str]] = None,
    ) -> None:
        self.session = session
        self.nodes: Dict[str, ResearchNode] = dict(nodes or {})
        self.experiment_index: Dict[str, str] = dict(experiment_index or {})

    @classmethod
    def create_session(
        cls,
        *,
        data_cutoff_date: str,
        guardrails_config_version: str = GUARDRAILS_CONFIG_VERSION,
        experiment_budget: Optional[int] = None,
        started_at: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> "ResearchGraph":
        sid = session_id or _new_id("rs")
        session = ResearchSession(
            research_session_id=sid,
            started_at=started_at or _utc_now_iso(),
            data_cutoff_date=data_cutoff_date,
            guardrails_config_version=guardrails_config_version,
            status=SessionStatus.ACTIVE,
            experiment_budget=experiment_budget,
        )
        return cls(session=session)

    def snapshot(self) -> ResearchGraphSnapshot:
        return ResearchGraphSnapshot(
            schema_version=RESEARCH_GRAPH_SCHEMA_VERSION,
            session=self.session,
            nodes=self.nodes,
            experiment_index=self.experiment_index,
        )

    @classmethod
    def from_snapshot(cls, snapshot: ResearchGraphSnapshot) -> "ResearchGraph":
        return cls(
            session=snapshot.session,
            nodes=snapshot.nodes,
            experiment_index=snapshot.experiment_index,
        )

    @classmethod
    def deserialize(cls, text: str) -> "ResearchGraph":
        return cls.from_snapshot(ResearchGraphSnapshot.deserialize(text))

    def serialize(self) -> str:
        return self.snapshot().serialize()

    def get_node(self, node_id: str) -> ResearchNode:
        if node_id not in self.nodes:
            raise ResearchGraphError(f"Unknown node_id: {node_id}")
        return self.nodes[node_id]

    def _link_parent_child(self, parent_id: str, child_id: str) -> None:
        parent = self.get_node(parent_id)
        child = self.get_node(child_id)
        if parent_id == child_id:
            raise ResearchGraphError("Self-link between parent and child is not allowed")
        if self._would_create_cycle(child_id, parent_id):
            raise ResearchGraphError(f"Adding edge {parent_id} -> {child_id} would create a cycle")
        if child_id not in parent.child_node_ids:
            parent.child_node_ids.append(child_id)
        if parent_id not in child.parent_node_ids:
            child.parent_node_ids.append(parent_id)

    def _would_create_cycle(self, child_id: str, new_parent_id: str) -> bool:
        """Adding new_parent -> child creates cycle if child can reach new_parent."""
        visited: Set[str] = set()
        stack = list(self.get_node(child_id).child_node_ids)
        while stack:
            current = stack.pop()
            if current == new_parent_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.get_node(current).child_node_ids)
        return False

    def add_root_observation(
        self,
        *,
        description: str,
        source_metrics: Optional[Dict[str, Any]] = None,
        trigger_kind: str = "ANOMALY",
        node_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        nid = node_id or _new_id("obs")
        node = ResearchNode(
            node_id=nid,
            session_id=self.session.research_session_id,
            node_type=NodeType.OBSERVATION,
            status=NodeStatus.OPEN,
            created_at=created_at or _utc_now_iso(),
            trigger=ResearchTrigger(
                kind=trigger_kind,
                description=description,
                source_metrics=dict(source_metrics or {}),
            ),
        )
        self.nodes[nid] = node
        if nid not in self.session.root_node_ids:
            self.session.root_node_ids.append(nid)
        return nid

    def spawn_question(
        self,
        *,
        parent_node_ids: Sequence[str],
        question_text: str,
        rationale: QuestionRationale,
        node_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        for pid in parent_node_ids:
            self.get_node(pid)
        nid = node_id or _new_id("q")
        node = ResearchNode(
            node_id=nid,
            session_id=self.session.research_session_id,
            node_type=NodeType.QUESTION,
            status=NodeStatus.OPEN,
            created_at=created_at or _utc_now_iso(),
            parent_node_ids=list(parent_node_ids),
            question_text=question_text,
            rationale=rationale,
        )
        self.nodes[nid] = node
        for pid in parent_node_ids:
            self._link_parent_child(pid, nid)
        return nid

    def add_experiment(
        self,
        *,
        question_node_id: str,
        spec: ExperimentSpec,
        node_id: Optional[str] = None,
        created_at: Optional[str] = None,
        allow_duplicate: bool = False,
    ) -> str:
        question = self.get_node(question_node_id)
        if question.node_type != NodeType.QUESTION:
            raise ResearchGraphError("Experiments must test a QUESTION node")
        if spec.data_cutoff_date != self.session.data_cutoff_date:
            raise ResearchGraphError(
                "Experiment data_cutoff_date must match session data_cutoff_date"
            )
        content_hash = compute_experiment_content_hash(spec)
        existing = self.experiment_index.get(content_hash)
        if existing and not allow_duplicate:
            raise DuplicateExperimentError(content_hash, existing)

        if self.session.experiment_budget is not None:
            if self.session.experiments_used >= self.session.experiment_budget:
                raise ResearchGraphError(
                    f"Experiment budget exhausted: {self.session.experiments_used}/"
                    f"{self.session.experiment_budget}"
                )

        nid = node_id or _new_id("exp")
        node = ResearchNode(
            node_id=nid,
            session_id=self.session.research_session_id,
            node_type=NodeType.EXPERIMENT,
            status=NodeStatus.RUNNING,
            created_at=created_at or _utc_now_iso(),
            parent_node_ids=[question_node_id],
            experiment_spec=spec,
            experiment_content_hash=content_hash,
        )
        self.nodes[nid] = node
        self._link_parent_child(question_node_id, nid)
        self.experiment_index[content_hash] = nid
        self.session.experiments_used += 1
        return nid

    def attach_experiment_result(
        self,
        experiment_node_id: str,
        *,
        metrics: Dict[str, Any],
        observations: Optional[Sequence[StructuredResearchObservation]] = None,
        evidence_for: Optional[Sequence[EvidenceReference]] = None,
        evidence_against: Optional[Sequence[EvidenceReference]] = None,
        uncertainties: Optional[Sequence[str]] = None,
        candidate_next_actions: Optional[Sequence[NextActionCandidate]] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        node = self.get_node(experiment_node_id)
        if node.node_type != NodeType.EXPERIMENT:
            raise ResearchGraphError("Results may only be attached to EXPERIMENT nodes")
        if node.experiment_result is not None and node.experiment_result.finalized:
            raise ResearchGraphError(
                f"Experiment {experiment_node_id} result is finalized and cannot be mutated"
            )
        obs = tuple(observations or ())
        result = ExperimentResult(
            metrics=dict(metrics),
            result_hash=compute_result_hash(metrics),
            observations=obs,
            finalized=True,
        )
        node.experiment_result = result
        if evidence_for is not None:
            node.evidence_for = list(evidence_for)
        if evidence_against is not None:
            node.evidence_against = list(evidence_against)
        if uncertainties is not None:
            node.uncertainties = list(uncertainties)
        if candidate_next_actions is not None:
            node.candidate_next_actions = list(candidate_next_actions)
        node.status = NodeStatus.RESOLVED
        node.completed_at = completed_at or _utc_now_iso()

    def add_structured_observations(
        self,
        experiment_node_id: str,
        observations: Sequence[StructuredResearchObservation],
    ) -> None:
        node = self.get_node(experiment_node_id)
        if node.node_type != NodeType.EXPERIMENT:
            raise ResearchGraphError("Observations may only be added to EXPERIMENT nodes")
        if node.experiment_result is None:
            raise ResearchGraphError("Experiment must have a result before adding observations")
        if node.experiment_result.finalized:
            raise ResearchGraphError("Cannot mutate finalized experiment observations")
        existing = list(node.experiment_result.observations)
        existing.extend(observations)
        node.experiment_result = ExperimentResult(
            metrics=dict(node.experiment_result.metrics),
            result_hash=node.experiment_result.result_hash,
            observations=tuple(existing),
            finalized=node.experiment_result.finalized,
        )

    def spawn_child_question_from_experiment(
        self,
        experiment_node_id: str,
        *,
        question_text: str,
        reason_code: str,
        evidence_summary: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None,
    ) -> str:
        exp = self.get_node(experiment_node_id)
        if exp.node_type != NodeType.EXPERIMENT:
            raise ResearchGraphError("Child questions must spawn from EXPERIMENT nodes")
        if exp.experiment_result is None:
            raise ResearchGraphError("Experiment must have a result before spawning child question")
        return self.spawn_question(
            parent_node_ids=[experiment_node_id],
            question_text=question_text,
            rationale=QuestionRationale(
                reason_code=reason_code,
                prior_node_id=experiment_node_id,
                evidence_summary=dict(evidence_summary or {}),
            ),
            node_id=node_id,
        )

    def abandon_node(self, node_id: str, *, reason: str) -> None:
        if not reason or not reason.strip():
            raise ResearchGraphError("Abandoned nodes require an explicit terminal_reason")
        node = self.get_node(node_id)
        if node.status == NodeStatus.FROZEN:
            raise ResearchGraphError("FROZEN nodes cannot be abandoned")
        node.status = NodeStatus.ABANDONED
        node.terminal_reason = reason.strip()
        node.completed_at = _utc_now_iso()

    def resolve_node(self, node_id: str, *, terminal_reason: str = "") -> None:
        node = self.get_node(node_id)
        if node.status == NodeStatus.FROZEN:
            raise ResearchGraphError("FROZEN nodes cannot be resolved to OPEN/RESOLVED")
        node.status = NodeStatus.RESOLVED
        if terminal_reason:
            node.terminal_reason = terminal_reason
        node.completed_at = _utc_now_iso()

    def freeze_node(
        self,
        node_id: str,
        *,
        frozen_spec_ref: Dict[str, Any],
        terminal_reason: str = "FROZEN_FOR_FUTURE_OOS",
    ) -> None:
        node = self.get_node(node_id)
        if node.status == NodeStatus.FROZEN:
            raise ResearchGraphError("Node is already FROZEN")
        node.node_type = NodeType.FROZEN_HYPOTHESIS
        node.status = NodeStatus.FROZEN
        node.frozen_spec_ref = dict(frozen_spec_ref)
        node.terminal_reason = terminal_reason
        node.completed_at = _utc_now_iso()

    def get_parents(self, node_id: str) -> List[ResearchNode]:
        node = self.get_node(node_id)
        return [self.get_node(pid) for pid in node.parent_node_ids]

    def get_children(self, node_id: str) -> List[ResearchNode]:
        node = self.get_node(node_id)
        return [self.get_node(cid) for cid in node.child_node_ids]

    def reconstruct_lineage(self, node_id: str) -> List[ResearchNode]:
        """Return nodes from roots to node_id in topological order."""
        self.get_node(node_id)
        ordered: List[str] = []
        visited: Set[str] = set()

        def visit(nid: str) -> None:
            if nid in visited:
                return
            node = self.get_node(nid)
            for pid in node.parent_node_ids:
                visit(pid)
            visited.add(nid)
            ordered.append(nid)

        visit(node_id)
        return [self.get_node(n) for n in ordered]

    def list_open_branches(self) -> List[ResearchNode]:
        return [
            n
            for n in self.nodes.values()
            if n.status in (NodeStatus.OPEN, NodeStatus.RUNNING)
        ]

    def find_experiment_by_content_hash(self, content_hash: str) -> Optional[str]:
        return self.experiment_index.get(content_hash)

    def has_attempted_experiment(self, spec: ExperimentSpec) -> bool:
        return compute_experiment_content_hash(spec) in self.experiment_index

    def validate(self) -> None:
        sid = self.session.research_session_id
        for node in self.nodes.values():
            if node.session_id != sid:
                raise ResearchGraphError(
                    f"Node {node.node_id} session_id mismatch: {node.session_id!r} != {sid!r}"
                )
            if node.node_id in node.parent_node_ids:
                raise ResearchGraphError(f"Node {node.node_id} cannot be its own parent")
            if node.node_id in node.child_node_ids:
                raise ResearchGraphError(f"Node {node.node_id} cannot be its own child")
            for pid in node.parent_node_ids:
                if pid not in self.nodes:
                    raise ResearchGraphError(f"Node {node.node_id} missing parent {pid}")
                if node.node_id not in self.nodes[pid].child_node_ids:
                    raise ResearchGraphError(
                        f"Inconsistent parent/child: {pid} -> {node.node_id}"
                    )
            for cid in node.child_node_ids:
                if cid not in self.nodes:
                    raise ResearchGraphError(f"Node {node.node_id} missing child {cid}")
                if node.node_id not in self.nodes[cid].parent_node_ids:
                    raise ResearchGraphError(
                        f"Inconsistent child/parent: {node.node_id} -> {cid}"
                    )
            if node.node_type == NodeType.EXPERIMENT and node.experiment_result is not None:
                if not node.experiment_result.finalized:
                    raise ResearchGraphError(
                        f"Experiment {node.node_id} has non-finalized result"
                    )
            if node.status == NodeStatus.ABANDONED and not node.terminal_reason.strip():
                raise ResearchGraphError(f"ABANDONED node {node.node_id} missing terminal_reason")
            if node.status == NodeStatus.FROZEN and node.node_type != NodeType.FROZEN_HYPOTHESIS:
                raise ResearchGraphError(
                    f"FROZEN status requires FROZEN_HYPOTHESIS type on {node.node_id}"
                )

        for root_id in self.session.root_node_ids:
            if root_id not in self.nodes:
                raise ResearchGraphError(f"Missing root node {root_id}")

        self._validate_acyclic()
        self._validate_experiment_index()

    def _validate_acyclic(self) -> None:
        visited: Set[str] = set()
        stack: Set[str] = set()

        def dfs(nid: str) -> None:
            if nid in stack:
                raise ResearchGraphError(f"Cycle detected involving node {nid}")
            if nid in visited:
                return
            stack.add(nid)
            for cid in self.get_node(nid).child_node_ids:
                dfs(cid)
            stack.remove(nid)
            visited.add(nid)

        for nid in self.nodes:
            dfs(nid)

    def _validate_experiment_index(self) -> None:
        for content_hash, node_id in self.experiment_index.items():
            if node_id not in self.nodes:
                raise ResearchGraphError(
                    f"experiment_index references missing node {node_id}"
                )
            node = self.nodes[node_id]
            if node.experiment_content_hash != content_hash:
                raise ResearchGraphError(
                    f"experiment_index hash mismatch for node {node_id}"
                )

    def set_session_status(self, status: SessionStatus) -> None:
        self.session.status = status

    def assert_data_cutoff_immutable(self, new_cutoff: str) -> None:
        if new_cutoff != self.session.data_cutoff_date:
            raise ResearchGraphError("session data_cutoff_date is immutable")
