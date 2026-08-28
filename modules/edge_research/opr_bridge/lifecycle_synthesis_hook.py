"""
Phase 3I.14 — Canonical post-EPU automatic synthesis hook.

Orchestration only — delegates to frozen EvidenceSynthesisEngine via 3I.13 integration.

Source-of-authority (research lifecycle):
- Single ToolResult interpretation: EpistemicUpdateRecord
- Current proposition knowledge state: EvidenceSynthesisRecord
- Next research-budget recommendation: ResearchPriorityDecision (multi-evidence)
- Immediate single-evidence ResearchDecisionRecord: transitional; must NOT override body-of-evidence priority
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.synthesis_integration import (
    ACTION_RECORDED_ONLY,
    INTEGRATION_VERSION,
    SynthesisIntegrationOutcome,
    update_proposition_knowledge_state,
)

HOOK_VERSION = "lifecycle_synthesis_hook_v1_3i14"

# Source-of-authority declarations (research-only)
AUTHORITY_EPISTEMIC_UPDATE = "EpistemicUpdateRecord"
AUTHORITY_KNOWLEDGE_STATE = "EvidenceSynthesisRecord"
AUTHORITY_RESEARCH_PRIORITY = "ResearchPriorityDecision"
AUTHORITY_IMMEDIATE_DECISION = "ResearchDecisionRecord"  # transitional single-evidence
AUTHORITY_FRONTIER = "ScientificFrontierAssessment"
AUTHORITY_DORMANCY = "ResearchDormancyRecord"
AUTHORITY_REOPENING = "ReopeningEvaluationRecord"


@dataclass
class LifecycleKnowledgeState:
    """Append-only proposition evidence + synthesis + research-activity history."""

    proposition_id: str
    evidence_events: List[Dict[str, Any]] = field(default_factory=list)
    synthesis_history: List[Dict[str, Any]] = field(default_factory=list)
    priority_history: List[Dict[str, Any]] = field(default_factory=list)
    frontier_history: List[Dict[str, Any]] = field(default_factory=list)
    dormancy_history: List[Dict[str, Any]] = field(default_factory=list)
    reopening_history: List[Dict[str, Any]] = field(default_factory=list)
    research_activity_state: str = "ACTIVE"
    outcomes: List[SynthesisIntegrationOutcome] = field(default_factory=list)
    _cutoff_cache: Dict[str, SynthesisIntegrationOutcome] = field(default_factory=dict)
    _dormancy_idempotency_keys: List[str] = field(default_factory=list)
    _opportunity_hashes_seen: List[str] = field(default_factory=list)
    _abstract_evidence_specs: Optional[List[Dict[str, Any]]] = None

    def cutoff_key_for_events(self, events: List[Dict[str, Any]]) -> str:
        ids = [e["epistemic_update"]["update_id"] for e in events]
        return stable_hash({"proposition_id": self.proposition_id, "epu_ids": ids})

    def latest_synthesis(self) -> Optional[Dict[str, Any]]:
        return self.synthesis_history[-1] if self.synthesis_history else None

    def latest_priority(self) -> Optional[Dict[str, Any]]:
        return self.priority_history[-1] if self.priority_history else None

    def latest_frontier(self) -> Optional[Dict[str, Any]]:
        return self.frontier_history[-1] if self.frontier_history else None

    def latest_dormancy(self) -> Optional[Dict[str, Any]]:
        return self.dormancy_history[-1] if self.dormancy_history else None

    def latest_reopening(self) -> Optional[Dict[str, Any]]:
        return self.reopening_history[-1] if self.reopening_history else None

    def is_dormant(self) -> bool:
        return self.research_activity_state == "DORMANT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "evidence_event_count": len(self.evidence_events),
            "synthesis_history_count": len(self.synthesis_history),
            "priority_history_count": len(self.priority_history),
            "frontier_history_count": len(self.frontier_history),
            "dormancy_history_count": len(self.dormancy_history),
            "reopening_history_count": len(self.reopening_history),
            "research_activity_state": self.research_activity_state,
            "epu_ids": [e["epistemic_update"]["update_id"] for e in self.evidence_events],
        }


def build_evidence_event(
    *,
    epistemic_update: Dict[str, Any],
    experiment_spec: Dict[str, Any],
    experiment_ref: str,
    tool_result_hash: str,
    interpretation: Optional[Dict[str, Any]] = None,
    lineage_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mechanical evidence-event bundle for ledger builder."""
    event: Dict[str, Any] = {
        "epistemic_update": epistemic_update,
        "experiment_spec": experiment_spec,
        "experiment_ref": experiment_ref,
        "tool_result_hash": tool_result_hash,
    }
    if interpretation is not None:
        event["interpretation"] = interpretation
    if lineage_metadata is not None:
        event["lineage_metadata"] = lineage_metadata
    return event


def on_epistemic_update_completed(
    proposition: Dict[str, Any],
    epistemic_update: Dict[str, Any],
    experiment_spec: Dict[str, Any],
    experiment_ref: str,
    tool_result_hash: str,
    *,
    interpretation: Optional[Dict[str, Any]] = None,
    lineage_metadata: Optional[Dict[str, Any]] = None,
    knowledge_state: Optional[LifecycleKnowledgeState] = None,
    deterministic_replay: bool = False,
) -> Tuple[LifecycleKnowledgeState, SynthesisIntegrationOutcome]:
    """
    Canonical post-EPU hook: append evidence → run frozen synthesis → ACTION_RECORDED_ONLY.

    Does NOT generate, select, or execute experiments.
    """
    state = knowledge_state or LifecycleKnowledgeState(proposition["proposition_id"])
    epu_id = epistemic_update["update_id"]

    # Append event if not already present (idempotent event append)
    existing_ids = [e["epistemic_update"]["update_id"] for e in state.evidence_events]
    if epu_id not in existing_ids:
        state.evidence_events.append(
            build_evidence_event(
                epistemic_update=epistemic_update,
                experiment_spec=experiment_spec,
                experiment_ref=experiment_ref,
                tool_result_hash=tool_result_hash,
                interpretation=interpretation,
                lineage_metadata=lineage_metadata,
            )
        )

    cutoff_key = state.cutoff_key_for_events(state.evidence_events)
    if cutoff_key in state._cutoff_cache:
        return state, state._cutoff_cache[cutoff_key]

    outcome = update_proposition_knowledge_state(
        proposition,
        list(state.evidence_events),
        synthesis_history=list(state.synthesis_history),
        deterministic_replay=deterministic_replay,
    )

    state._cutoff_cache[cutoff_key] = outcome
    if len(state.outcomes) < len(state.evidence_events):
        state.outcomes.append(outcome)
    elif state.outcomes:
        state.outcomes[-1] = outcome
    else:
        state.outcomes.append(outcome)

    if outcome.integration_status == "SUCCESS" and outcome.synthesis and outcome.priority:
        if not state.synthesis_history or state.synthesis_history[-1].get("synthesis_hash") != outcome.synthesis.synthesis_hash:
            state.synthesis_history.append(outcome.synthesis.to_dict())
        if not state.priority_history or state.priority_history[-1].get("record_hash") != outcome.priority.record_hash:
            state.priority_history.append(outcome.priority.to_dict())

    return state, outcome


def bootstrap_knowledge_state_from_lineage(
    proposition: Dict[str, Any],
    prior_lineage: Dict[str, Any],
    *,
    run_catch_up_synthesis: bool = True,
    deterministic_replay: bool = True,
) -> LifecycleKnowledgeState:
    """
    Bootstrap state with EPU1 from prior lifecycle lineage (e.g. 3I.7 append-only lineage).
    Optionally run Synthesis1 catch-up without re-executing experiment.
    """
    state = LifecycleKnowledgeState(proposition["proposition_id"])
    exp_spec = prior_lineage.get("experiment_spec") or {}
    epu = prior_lineage["epistemic_update"]
    event = build_evidence_event(
        epistemic_update=epu,
        experiment_spec=exp_spec,
        experiment_ref=epu.get("experiment_ref", "prior"),
        tool_result_hash=prior_lineage.get("tool_result_hash", epu.get("tool_result_hash", "")),
        interpretation=prior_lineage.get("interpretation"),
    )
    state.evidence_events.append(event)

    if run_catch_up_synthesis:
        on_epistemic_update_completed(
            proposition,
            epu,
            exp_spec,
            event["experiment_ref"],
            event["tool_result_hash"],
            interpretation=event.get("interpretation"),
            knowledge_state=state,
            deterministic_replay=deterministic_replay,
        )
    return state


def attach_synthesis_to_lifecycle_result(
    result: Dict[str, Any],
    outcome: SynthesisIntegrationOutcome,
    knowledge_state: LifecycleKnowledgeState,
) -> Dict[str, Any]:
    """Merge synthesis hook outputs into lifecycle runner result dict."""
    result["knowledge_state"] = knowledge_state.to_dict()
    result["synthesis_integration"] = outcome.to_dict()
    result["synthesis_status"] = outcome.integration_status
    result["action_disposition"] = (
        outcome.action_disposition if outcome.integration_status == "SUCCESS" else None
    )
    result["source_of_authority"] = {
        "tool_result_interpretation": AUTHORITY_EPISTEMIC_UPDATE,
        "proposition_knowledge_state": AUTHORITY_KNOWLEDGE_STATE,
        "research_priority": AUTHORITY_RESEARCH_PRIORITY,
        "immediate_single_evidence_decision": AUTHORITY_IMMEDIATE_DECISION,
        "immediate_decision_overrides_priority": False,
    }
    if outcome.synthesis:
        result["evidence_synthesis"] = outcome.synthesis.to_dict()
    if outcome.priority:
        result["research_priority_decision"] = outcome.priority.to_dict()
    if "lineage" in result and outcome.integration_status == "SUCCESS" and outcome.synthesis:
        result["lineage"]["evidence_synthesis"] = outcome.synthesis.to_dict()
        result["lineage"]["research_priority_decision"] = outcome.priority.to_dict() if outcome.priority else None
        result["lineage"]["synthesis_status"] = outcome.integration_status
        result["lineage"]["action_disposition"] = ACTION_RECORDED_ONLY
    return result
