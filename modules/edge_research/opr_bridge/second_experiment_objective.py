"""
Phase 3J.6 — Derive second-experiment objective from frozen ResearchDecisionRecord.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    CandidateActionEvaluation,
    FirstExperimentResearchDecisionEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_records import (
    OBJECTIVE_RECORD_VERSION,
    SecondExperimentObjectiveRecord,
)

NULL_OBJECTIVES = {
    "directional_reversal": (
        "Test whether directional rs_spread quintile commitment holds on the full cross-section",
        "Discriminates directional_reversal null — high quintile must outperform low on forward t5_return",
    ),
    "episode_artifact": (
        "Test whether effect survives evidence independent of motivating episode",
        "Discriminates episode_artifact null — effect must hold excluding birth/motivating dates",
    ),
    "population_concentration": (
        "Test whether effect generalizes beyond concentrated subpopulation",
        "Discriminates population_concentration null",
    ),
    "context_instability": (
        "Test whether effect is stable across market contexts",
        "Discriminates context_instability null",
    ),
}


def _selected_evaluation(
    envelope: FirstExperimentResearchDecisionEnvelope,
) -> Optional[CandidateActionEvaluation]:
    rd = envelope.research_decision
    chosen = rd.get("chosen_next_action", "")
    admissible = [e for e in envelope.candidate_evaluations if e.admissible]
    if not admissible:
        return None
    falsify = [e for e in admissible if e.action_family == "TEST_NEXT_NULL"]
    if falsify:
        falsify.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
        return falsify[0]
    for e in admissible:
        if e.mapped_action_code == chosen and e.action_family != "STOP_NO_INFORMATIVE_ACTION":
            return e
    admissible.sort(key=lambda e: (e.information_gain_rank, e.redundancy_score))
    return admissible[0]


def derive_second_experiment_objective(
    prop: Dict[str, Any],
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
) -> Optional[SecondExperimentObjectiveRecord]:
    if decision_envelope.decision_kind != "ACTION":
        return None

    selected = _selected_evaluation(decision_envelope)
    if selected is None:
        return None

    null_key = selected.target_null_key or "unknown"
    uncertainty = selected.target_uncertainty
    sci_obj, why = NULL_OBJECTIVES.get(
        null_key,
        (selected.scientific_objective, f"Target unresolved null: {null_key}"),
    )

    ts = utc_now_iso()
    oid = new_id("seo")
    rd = decision_envelope.research_decision
    body = {
        "objective_id": oid,
        "proposition_id": prop["proposition_id"],
        "research_decision_id": rd.get("decision_id"),
        "selected_action": rd.get("chosen_next_action"),
        "target_null_key": null_key,
        "target_uncertainty": uncertainty,
    }
    return SecondExperimentObjectiveRecord(
        objective_id=oid,
        record_version=OBJECTIVE_RECORD_VERSION,
        proposition_id=prop["proposition_id"],
        proposition_hash=decision_envelope.proposition_hash,
        research_decision_id=str(rd.get("decision_id", "")),
        research_decision_hash=str(rd.get("record_hash", "")),
        selected_action=str(rd.get("chosen_next_action", "")),
        target_uncertainty=uncertainty,
        target_null_key=null_key,
        scientific_objective=sci_obj,
        why_this_design=why,
        created_at=ts,
        objective_hash=stable_hash(body),
    )


def extract_decision_target(decision_envelope: FirstExperimentResearchDecisionEnvelope) -> Tuple[str, str, str]:
    """Return (selected_action, target_null_key, target_uncertainty)."""
    selected = _selected_evaluation(decision_envelope)
    rd = decision_envelope.research_decision
    if selected is None:
        return str(rd.get("chosen_next_action", "")), "", ""
    return (
        str(rd.get("chosen_next_action", "")),
        selected.target_null_key or "",
        selected.target_uncertainty,
    )
