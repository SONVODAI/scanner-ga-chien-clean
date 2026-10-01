"""
Phase 3I.13 — Lifecycle evidence-synthesis integration.

Wires frozen EvidenceSynthesisEngine into proposition lifecycle.
ResearchPriorityDecision → ACTION_RECORDED_ONLY → STOP (no auto-execution).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_ledger_builder import (
    build_ledger_specs_from_events,
    proposition_spec_from_record,
)
from modules.edge_research.opr_bridge.evidence_synthesis_engine import (
    SYNTHESIS_ENGINE_VERSION,
    engine_content_hash,
    synthesize_evidence,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceSynthesisRecord,
    ResearchPriorityDecision,
    stable_hash,
)

INTEGRATION_VERSION = "lifecycle_synthesis_integration_v1_3i13"
FROZEN_ENGINE_HASH = "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
ACTION_RECORDED_ONLY = "ACTION_RECORDED_ONLY"


@dataclass(frozen=True)
class SynthesisIntegrationOutcome:
    """Result of one synthesis integration step."""

    synthesis: Optional[EvidenceSynthesisRecord]
    priority: Optional[ResearchPriorityDecision]
    integration_status: str  # SUCCESS | SYNTHESIS_FAILED
    action_disposition: Optional[str]
    synthesis_history_index: int
    evidence_cutoff_count: int
    error: Optional[str] = None
    lineage_extension: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": INTEGRATION_VERSION,
            "integration_status": self.integration_status,
            "action_disposition": self.action_disposition,
            "synthesis_history_index": self.synthesis_history_index,
            "evidence_cutoff_count": self.evidence_cutoff_count,
            "error": self.error,
            "synthesis": self.synthesis.to_dict() if self.synthesis else None,
            "research_priority_decision": self.priority.to_dict() if self.priority else None,
            "lineage_extension": dict(self.lineage_extension),
        }


def verify_frozen_engine_integrity() -> Dict[str, Any]:
    current = engine_content_hash()
    return {
        "expected_hash": FROZEN_ENGINE_HASH,
        "current_hash": current,
        "engine_version": SYNTHESIS_ENGINE_VERSION,
        "passed": current == FROZEN_ENGINE_HASH,
    }


def update_proposition_knowledge_state(
    proposition: Dict[str, Any],
    evidence_events: List[Dict[str, Any]],
    *,
    synthesis_history: Optional[List[Dict[str, Any]]] = None,
    deterministic_replay: bool = False,
) -> SynthesisIntegrationOutcome:
    """
    Append synthesis snapshot over all evidence_events (temporal cutoff = full list).

    Does NOT generate, select, or execute experiments.
    ResearchPriorityDecision → ACTION_RECORDED_ONLY.
    """
    history = list(synthesis_history or [])
    history_index = len(history) + 1
    cutoff = len(evidence_events)

    if not evidence_events:
        return SynthesisIntegrationOutcome(
            synthesis=None,
            priority=None,
            integration_status="SYNTHESIS_FAILED",
            action_disposition=None,
            synthesis_history_index=history_index,
            evidence_cutoff_count=0,
            error="no_evidence_events",
        )

    try:
        prop_spec = proposition_spec_from_record(proposition)
        specs = build_ledger_specs_from_events(proposition, evidence_events)
        prior_state = evidence_events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")

        synthesis, priority = synthesize_evidence(
            prop_spec,
            specs,
            prior_epistemic_state=prior_state,
            deterministic_replay=deterministic_replay,
            replay_key=_replay_key(proposition, evidence_events) if deterministic_replay else None,
        )

        lineage_ext = _build_lineage_extension(
            proposition,
            evidence_events,
            synthesis,
            priority,
            history_index,
        )

        return SynthesisIntegrationOutcome(
            synthesis=synthesis,
            priority=priority,
            integration_status="SUCCESS",
            action_disposition=ACTION_RECORDED_ONLY,
            synthesis_history_index=history_index,
            evidence_cutoff_count=cutoff,
            lineage_extension=lineage_ext,
        )
    except Exception as exc:
        return SynthesisIntegrationOutcome(
            synthesis=None,
            priority=None,
            integration_status="SYNTHESIS_FAILED",
            action_disposition=None,
            synthesis_history_index=history_index,
            evidence_cutoff_count=cutoff,
            error=str(exc),
        )


def replay_synthesis_at_cutoff(
    proposition: Dict[str, Any],
    all_evidence_events: List[Dict[str, Any]],
    cutoff: int,
    *,
    deterministic_replay: bool = True,
) -> SynthesisIntegrationOutcome:
    """
    Reconstruct synthesis as known at temporal cutoff (1-indexed).

    Synthesis at cutoff=1 sees only EPU1; cutoff=2 sees EPU1+EPU2.
    """
    if cutoff < 1 or cutoff > len(all_evidence_events):
        raise ValueError(f"cutoff {cutoff} out of range for {len(all_evidence_events)} events")
    events_slice = all_evidence_events[:cutoff]
    prior_history = []
    return update_proposition_knowledge_state(
        proposition,
        events_slice,
        synthesis_history=prior_history,
        deterministic_replay=deterministic_replay,
    )


def replay_full_synthesis_history(
    proposition: Dict[str, Any],
    all_evidence_events: List[Dict[str, Any]],
    *,
    deterministic_replay: bool = True,
) -> List[SynthesisIntegrationOutcome]:
    """Append-only replay: Synthesis1 after EPU1, Synthesis2 after EPU1+EPU2, ..."""
    outcomes: List[SynthesisIntegrationOutcome] = []
    history: List[Dict[str, Any]] = []
    for cutoff in range(1, len(all_evidence_events) + 1):
        events_slice = all_evidence_events[:cutoff]
        outcome = update_proposition_knowledge_state(
            proposition,
            events_slice,
            synthesis_history=history,
            deterministic_replay=deterministic_replay,
        )
        outcomes.append(outcome)
        if outcome.integration_status == "SUCCESS" and outcome.synthesis:
            history.append(outcome.synthesis.to_dict())
    return outcomes


def _replay_key(proposition: Dict[str, Any], events: List[Dict[str, Any]]) -> str:
    ids = [e["epistemic_update"]["update_id"] for e in events]
    return stable_hash(
        {
            "proposition_id": proposition["proposition_id"],
            "epu_ids": ids,
            "engine": SYNTHESIS_ENGINE_VERSION,
        }
    )


def _build_lineage_extension(
    proposition: Dict[str, Any],
    events: List[Dict[str, Any]],
    synthesis: EvidenceSynthesisRecord,
    priority: ResearchPriorityDecision,
    history_index: int,
) -> Dict[str, Any]:
    epu_ids = [e["epistemic_update"]["update_id"] for e in events]
    body = {
        "integration_version": INTEGRATION_VERSION,
        "proposition_id": proposition["proposition_id"],
        "synthesis_id": synthesis.synthesis_id,
        "synthesis_hash": synthesis.synthesis_hash,
        "priority_decision_id": priority.decision_id,
        "priority_record_hash": priority.record_hash,
        "evidence_update_ids": epu_ids,
        "synthesis_history_index": history_index,
        "action_disposition": ACTION_RECORDED_ONLY,
        "engine_hash": engine_content_hash(),
    }
    return {
        **body,
        "lineage_extension_hash": stable_hash(body),
    }
