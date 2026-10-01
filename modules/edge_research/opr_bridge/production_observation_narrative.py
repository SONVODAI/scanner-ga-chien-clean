"""
Phase 3K.0 — Observation narrative and UI contracts (presentation layer only).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_observation_records import (
    ObservationNarrativeContract,
    ObservationUIContract,
    ResearchObservationBirthRecord,
)


def build_narrative_contract(birth: ResearchObservationBirthRecord) -> ObservationNarrativeContract:
    """Derive structured narrative inputs from frozen birth state — no persuasive prose."""
    state = birth.final_epistemic_state or "UNRESOLVED"
    return ObservationNarrativeContract(
        observation_id=birth.observation_id,
        research_topic_vi_key="bot_dang_nghien_cuu",
        research_topic_en=birth.research_question or birth.observation_outcome_kind,
        evidence_summary_keys=tuple(
            k for k in (
                f"epistemic_state:{state}",
                f"evidence_strength:{birth.evidence_strength}",
                f"experiments:{birth.experiment_count}",
            )
            if k.split(":")[-1] not in ("None", "")
        ),
        counter_evidence_keys=tuple(birth.contradictions),
        surviving_null_keys=tuple(birth.surviving_nulls),
        independence_status_key=birth.dependence_warning or "UNKNOWN_INDEPENDENCE",
        continue_reason_key=None if birth.lifecycle_outcome in ("SCIENTIFIC_STOP", "DESIGN_SILENCE", "BUDGET_EXHAUSTED") else "ACTION_REMAINING",
        stop_reason_key=birth.stop_reason or birth.termination_reason,
        unknowns_keys=tuple(birth.unresolved_uncertainties),
        pending_verification_keys=tuple(h.horizon for h in birth.forward_horizons),
        structured_state_snapshot={
            "observation_outcome_kind": birth.observation_outcome_kind,
            "final_epistemic_state": birth.final_epistemic_state,
            "null_ledger_count": len(birth.null_ledger_summary),
            "rejected_hypotheses": list(birth.rejected_hypotheses),
            "weakened_findings": list(birth.weakened_findings),
            "artifact_warnings": list(birth.artifact_warnings),
            "shadow_authority": birth.shadow_authority.to_dict(),
        },
    )


def render_minimal_narrative_preview(contract: ObservationNarrativeContract) -> Dict[str, str]:
    """
    Presentation-only deterministic renderer for diagnostics.
    NOT scientific authority — structured state remains canonical.
    """
    snap = contract.structured_state_snapshot
    return {
        "research_topic_en": contract.research_topic_en,
        "epistemic_state": str(snap.get("final_epistemic_state") or "UNRESOLVED"),
        "outcome_kind": str(snap.get("observation_outcome_kind")),
        "stop_reason": contract.stop_reason_key or "N/A",
        "pending_horizons": ", ".join(contract.pending_verification_keys) or "none",
        "presentation_only": "true",
    }


def build_ui_contract(birth: ResearchObservationBirthRecord) -> ObservationUIContract:
    """Future Research UI schema — sections A–I, no trade actions."""
    sections = [
        {"id": "A", "vi_label": "Hôm nay Bot đang nghiên cứu gì?", "en_key": "current_research_topic", "data": birth.research_question},
        {"id": "B", "vi_label": "Research Journey", "en_key": "journey_rows", "data": birth.journey_rows},
        {"id": "C", "vi_label": "Evidence", "en_key": "strongest_evidence", "data": birth.strongest_evidence},
        {"id": "D", "vi_label": "Nulls / alternative explanations", "en_key": "surviving_nulls", "data": list(birth.surviving_nulls)},
        {"id": "E", "vi_label": "Current epistemic state", "en_key": "final_epistemic_state", "data": birth.final_epistemic_state},
        {"id": "F", "vi_label": "Why STOP / why continue", "en_key": "stop_reason", "data": birth.stop_reason},
        {"id": "G", "vi_label": "Limitations / warnings", "en_key": "limitations", "data": list(birth.limitations)},
        {
            "id": "H",
            "vi_label": "T3/T5/T10 — PENDING",
            "en_key": "forward_horizons",
            "data": [h.to_dict() for h in birth.forward_horizons],
        },
        {"id": "I", "vi_label": "Historical observation summary", "en_key": "observation_outcome_kind", "data": birth.observation_outcome_kind},
    ]
    return ObservationUIContract(
        observation_id=birth.observation_id,
        sections=tuple(sections),
    )


def assert_narrative_faithful(epistemic_state: str, narrative_strength: str) -> bool:
    """Reject narrative upgrades beyond structured epistemic state."""
    rank = {"WEAK": 1, "MODERATE": 2, "STRONG": 3, "SUPPORTED": 3, "WEAKENED": 1, "REJECTED": 0}
    es = rank.get(epistemic_state.upper(), 1)
    ns = rank.get(narrative_strength.upper(), 1)
    return ns <= es
