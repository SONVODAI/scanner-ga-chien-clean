"""
Phase 3I.12 — Minimal Evidence Synthesis Engine.

Reasons over append-only evidence ledger — not vote counting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_independence import (
    compute_all_profiles,
    independence_summary,
)
from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
from modules.edge_research.opr_bridge.evidence_relationship_classifier import (
    classify_all_relationships,
    pairwise_relationships,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    SYNTHESIS_ENGINE_VERSION,
    EvidenceLedgerEntry,
    EvidenceRelationship,
    EvidenceSaturationAssessment,
    EvidenceSynthesisRecord,
    IndependenceLevel,
    ResearchPriorityAction,
    ResearchPriorityDecision,
    SaturationLevel,
    new_id,
    stable_hash,
    utc_now_iso,
)
from modules.edge_research.opr_bridge.uncertainty_coverage import (
    assess_coverage,
    derive_uncertainty_dimensions,
)


def synthesize_evidence(
    proposition_spec: Dict[str, Any],
    evidence_specs: List[Dict[str, Any]],
    *,
    prior_epistemic_state: str = "PROPOSED",
) -> Tuple[EvidenceSynthesisRecord, ResearchPriorityDecision]:
    """Main synthesis entry point."""
    prop_id = proposition_spec["proposition_id"]
    prop_hash = proposition_spec.get("proposition_hash", stable_hash({"id": prop_id}))

    entries = build_ledger_from_specs(prop_id, prop_hash, evidence_specs)
    return _synthesize_from_ledger(proposition_spec, entries, prior_epistemic_state=prior_epistemic_state)


def synthesize_from_ledger_entries(
    proposition_spec: Dict[str, Any],
    entries: List[EvidenceLedgerEntry],
    *,
    prior_epistemic_state: str = "PROPOSED",
) -> Tuple[EvidenceSynthesisRecord, ResearchPriorityDecision]:
    return _synthesize_from_ledger(proposition_spec, entries, prior_epistemic_state=prior_epistemic_state)


def _synthesize_from_ledger(
    proposition_spec: Dict[str, Any],
    entries: List[EvidenceLedgerEntry],
    *,
    prior_epistemic_state: str,
) -> Tuple[EvidenceSynthesisRecord, ResearchPriorityDecision]:
    prop_id = proposition_spec["proposition_id"]
    prop_hash = proposition_spec.get("proposition_hash", entries[0].proposition_hash if entries else "")

    rel_map = classify_all_relationships(entries)
    profiles = compute_all_profiles(entries)
    all_dims = derive_uncertainty_dimensions(proposition_spec)
    covered, unresolved = assess_coverage(entries, all_dims)

    valid_entries = [e for e in entries if e.validity == "VALID" and e.evidence_class not in ("INVALID",)]
    belief_entries = [e for e in valid_entries if e.evidence_class not in ("NON_INFORMATIVE",)]

    supporting = [e for e in belief_entries if e.evidence_class == "SUPPORTING"]
    disconfirming = [e for e in belief_entries if e.evidence_class == "DISCONFIRMING"]
    contradictory = [e for e in belief_entries if e.evidence_class == "CONTRADICTORY"]
    invalid_ni = [e for e in entries if e.validity != "VALID" or e.evidence_class in ("INVALID", "NON_INFORMATIVE")]

    contradiction_structure = _build_contradiction_structure(entries, pairwise_relationships(entries))
    synthesized_state, state_rationale = _synthesize_epistemic_state(
        prior_epistemic_state, belief_entries, supporting, disconfirming, contradictory, contradiction_structure, profiles, rel_map
    )

    saturation = _assess_saturation(
        entries, rel_map, profiles, covered, unresolved, contradiction_structure, proposition_spec
    )

    priority_action, priority_rationale, rejected = _decide_research_priority(
        synthesized_state, saturation, contradiction_structure, unresolved, rel_map, profiles, proposition_spec
    )

    synthesis_id = new_id("syn")
    created_at = utc_now_iso()

    supporting_struct = [_entry_summary(e, rel_map, profiles) for e in supporting]
    disconfirming_struct = [_entry_summary(e, rel_map, profiles) for e in disconfirming]

    rationale = state_rationale + saturation.rationale + priority_rationale
    causality_refs = tuple(
        f"{e.evidence_id}:{e.evidence_class}:{rel_map.get(e.evidence_id, 'INITIAL')}" for e in entries
    )

    synth_body = {
        "proposition_id": prop_id,
        "proposition_hash": prop_hash,
        "evidence_ids": [e.evidence_id for e in entries],
        "evidence_hashes": [e.record_hash for e in entries],
        "relationship_map": rel_map,
        "synthesized_epistemic_state": synthesized_state,
        "prior_epistemic_state": prior_epistemic_state,
        "uncertainty_covered": list(covered),
        "uncertainty_unresolved": list(unresolved),
        "saturation_level": saturation.level.value,
        "chosen_priority_action": priority_action.value,
        "synthesis_engine_version": SYNTHESIS_ENGINE_VERSION,
    }
    synthesis_hash = stable_hash(synth_body)

    synthesis = EvidenceSynthesisRecord(
        synthesis_id=synthesis_id,
        proposition_id=prop_id,
        proposition_hash=prop_hash,
        evidence_ids=tuple(e.evidence_id for e in entries),
        evidence_hashes=tuple(e.record_hash for e in entries),
        relationship_map=rel_map,
        independence_profiles={k: v.to_dict() for k, v in profiles.items()},
        supporting_structure=supporting_struct,
        disconfirming_structure=disconfirming_struct,
        contradiction_structure=contradiction_structure,
        invalid_non_informative=[{"evidence_id": e.evidence_id, "class": e.evidence_class, "validity": e.validity} for e in invalid_ni],
        uncertainty_covered=covered,
        uncertainty_unresolved=unresolved,
        saturation_assessment=saturation.to_dict(),
        synthesized_epistemic_state=synthesized_state,
        prior_epistemic_state=prior_epistemic_state,
        scientific_rationale=rationale,
        counterfactual_causality_refs=causality_refs,
        synthesis_engine_version=SYNTHESIS_ENGINE_VERSION,
        created_at=created_at,
        synthesis_hash=synthesis_hash,
    )

    decision_body = {
        "synthesis_id": synthesis_id,
        "synthesized_epistemic_state": synthesized_state,
        "chosen_priority_action": priority_action.value,
        "saturation_level": saturation.level.value,
    }
    decision = ResearchPriorityDecision(
        decision_id=new_id("rpd"),
        proposition_id=prop_id,
        synthesis_id=synthesis_id,
        synthesized_epistemic_state=synthesized_state,
        unresolved_uncertainty=unresolved,
        saturation_level=saturation.level.value,
        marginal_information=saturation.marginal_information,
        contradiction_status="UNRESOLVED" if contradiction_structure else "NONE",
        independence_summary=independence_summary(profiles),
        chosen_priority_action=priority_action.value,
        rationale=priority_rationale,
        rejected_alternatives=tuple(rejected),
        created_at=created_at,
        synthesis_engine_version=SYNTHESIS_ENGINE_VERSION,
        record_hash=stable_hash(decision_body),
    )
    return synthesis, decision


def _entry_summary(
    entry: EvidenceLedgerEntry,
    rel_map: Dict[str, str],
    profiles: Dict[str, Any],
) -> Dict[str, Any]:
    prof = profiles.get(entry.evidence_id)
    return {
        "evidence_id": entry.evidence_id,
        "evidence_class": entry.evidence_class,
        "relationship": rel_map.get(entry.evidence_id),
        "uncertainty_axis": entry.uncertainty_axis_tested,
        "effect_magnitude": entry.effect_magnitude,
        "independence_profile": prof.to_dict() if prof else {},
    }


def _build_contradiction_structure(
    entries: List[EvidenceLedgerEntry],
    pairs: List[Tuple[str, str, EvidenceRelationship]],
) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    entry_map = {e.evidence_id: e for e in entries}
    for cur_id, prior_id, rel in pairs:
        if rel != EvidenceRelationship.CONTRADICTORY_EVIDENCE:
            continue
        cur = entry_map[cur_id]
        prior = entry_map[prior_id]
        if cur.validity != "VALID" or prior.validity != "VALID":
            continue
        conflicts.append(
            {
                "evidence_a": prior_id,
                "evidence_b": cur_id,
                "class_a": prior.evidence_class,
                "class_b": cur.evidence_class,
                "axis": cur.uncertainty_axis_tested,
                "resolution_needed": True,
            }
        )
    return conflicts


def _has_independent(
    evidence_list: List[EvidenceLedgerEntry],
    profiles: Dict[str, Any],
) -> bool:
    for e in evidence_list:
        p = profiles.get(e.evidence_id)
        if not p:
            continue
        if p.sample_independence in (IndependenceLevel.HIGH, IndependenceLevel.MEDIUM):
            return True
        if p.semantic_independence == IndependenceLevel.HIGH:
            return True
    return False


def _synthesize_epistemic_state(
    prior: str,
    belief_entries: List[EvidenceLedgerEntry],
    supporting: List[EvidenceLedgerEntry],
    disconfirming: List[EvidenceLedgerEntry],
    contradictory: List[EvidenceLedgerEntry],
    conflicts: List[Dict[str, Any]],
    profiles: Dict[str, Any],
    rel_map: Dict[str, str],
) -> Tuple[str, Tuple[str, ...]]:
    rationale: List[str] = []

    if not belief_entries:
        rationale.append("No valid belief-moving evidence.")
        return prior if prior not in ("PROPOSED",) else "UNRESOLVED", tuple(rationale)

    strong_disconfirm = [e for e in disconfirming if e.effect_magnitude == "strong"]
    weak_disconfirm = [e for e in disconfirming if e.effect_magnitude == "weak"]
    strong_support = [e for e in supporting if e.effect_magnitude in ("strong", "weak")]

    # FALSIFIED preserved — later support does not erase
    if prior == "FALSIFIED":
        if supporting:
            rationale.append("FALSIFIED preserved; later supportive evidence flagged as anomaly — no resurrection.")
        return "FALSIFIED", tuple(rationale)

    # Unresolved contradiction between independent support and disconfirm
    if conflicts and strong_support and (strong_disconfirm or disconfirming):
        indep_conflict = any(
            _has_independent([belief_entries[0]], profiles) or _has_independent(disconfirming, profiles)
            for _ in [1]
        )
        if indep_conflict or len(conflicts) >= 1:
            rationale.append("Independent supporting and disconfirming evidence coexist — CONFLICTED.")
            return "CONFLICTED", tuple(rationale)

    if contradictory:
        rationale.append("CONTRADICTORY evidence class present.")
        return "CONFLICTED", tuple(rationale)

    # Strong independent disconfirmation
    if strong_disconfirm and _has_independent(strong_disconfirm, profiles):
        if strong_support and _has_independent(strong_support, profiles):
            rationale.append("Strong independent support and disconfirm — CONFLICTED.")
            return "CONFLICTED", tuple(rationale)
        rationale.append("Strong independent disconfirmation without balanced support.")
        return "FALSIFIED", tuple(rationale)

    if strong_disconfirm:
        rationale.append("Strong disconfirmation — FALSIFIED.")
        return "FALSIFIED", tuple(rationale)

    if weak_disconfirm and supporting:
        rationale.append("Weak disconfirmation with prior support — WEAKENED.")
        return "WEAKENED", tuple(rationale)

    if weak_disconfirm:
        rationale.append("Weak disconfirmation — WEAKENED.")
        return "WEAKENED", tuple(rationale)

    if supporting:
        if prior in ("PROPOSED", "UNDER_TEST", "HYPOTHESIS", "UNRESOLVED", "INSUFFICIENT_EVIDENCE"):
            rationale.append("Informative supporting evidence — SUPPORTED.")
            return "SUPPORTED", tuple(rationale)
        if prior == "WEAKENED":
            if _has_independent(supporting, profiles):
                rationale.append("Independent supporting after WEAKENED — conflict structure check.")
                if conflicts:
                    return "CONFLICTED", tuple(rationale)
            rationale.append("Supporting evidence after WEAKENED — partial recovery to SUPPORTED.")
            return "SUPPORTED", tuple(rationale)
        rationale.append("Supporting evidence — state remains SUPPORTED (not upgraded by count).")
        return "SUPPORTED", tuple(rationale)

    rationale.append("No resolving evidence structure — UNRESOLVED.")
    return "UNRESOLVED", tuple(rationale)


def _assess_saturation(
    entries: List[EvidenceLedgerEntry],
    rel_map: Dict[str, str],
    profiles: Dict[str, Any],
    covered: Tuple[str, ...],
    unresolved: Tuple[str, ...],
    conflicts: List[Dict[str, Any]],
    proposition_spec: Dict[str, Any],
) -> EvidenceSaturationAssessment:
    rationale: List[str] = []
    all_dims = derive_uncertainty_dimensions(proposition_spec)
    major_remaining = [d for d in unresolved if d in all_dims[:6]]

    redundant_axes: List[str] = []
    for e in entries:
        rel = rel_map.get(e.evidence_id, "")
        if rel in (
            EvidenceRelationship.EXACT_REPLICATION.value,
            EvidenceRelationship.REPRESENTATION_REPLICATION.value,
            EvidenceRelationship.PARTIAL_REPLICATION.value,
        ):
            redundant_axes.append(e.uncertainty_axis_tested)

    indep_obtained = []
    for eid, prof in profiles.items():
        if prof.semantic_independence == IndependenceLevel.HIGH or prof.sample_independence == IndependenceLevel.HIGH:
            indep_obtained.append(eid)

    high_info_ops = [d for d in unresolved if d not in redundant_axes]

    if conflicts:
        rationale.append("Unresolved contradictions — saturation cannot be HIGH.")
        return EvidenceSaturationAssessment(
            level=SaturationLevel.LOW,
            unresolved_contradictions=True,
            major_uncertainty_dimensions_remaining=tuple(major_remaining),
            independence_obtained=tuple(indep_obtained),
            redundant_test_axes=tuple(set(redundant_axes)),
            executable_high_info_opportunities=tuple(high_info_ops),
            marginal_information="high",
            rationale=tuple(rationale),
        )

    if not entries:
        return EvidenceSaturationAssessment(
            level=SaturationLevel.INDETERMINATE,
            unresolved_contradictions=False,
            major_uncertainty_dimensions_remaining=tuple(all_dims),
            independence_obtained=(),
            redundant_test_axes=(),
            executable_high_info_opportunities=tuple(all_dims),
            marginal_information="high",
            rationale=("No evidence — indeterminate saturation.",),
        )

    # Saturation from structure, not count
    coverage_ratio = len(covered) / max(len(all_dims), 1)
    has_independent_support = any(
        profiles.get(e.evidence_id, None)
        and (
            profiles[e.evidence_id].sample_independence in (IndependenceLevel.HIGH, IndependenceLevel.MEDIUM)
            or profiles[e.evidence_id].semantic_independence == IndependenceLevel.HIGH
        )
        for e in entries
        if e.evidence_class == "SUPPORTING"
    )

    if coverage_ratio >= 0.75 and has_independent_support and len(major_remaining) == 0:
        rationale.append("Major uncertainty axes covered with independent support — HIGH saturation.")
        level = SaturationLevel.HIGH
        marginal = "low"
    elif coverage_ratio >= 0.5 and len(redundant_axes) >= 1 and len(major_remaining) <= 2:
        rationale.append("Partial coverage with redundant axes identified — PARTIAL saturation.")
        level = SaturationLevel.PARTIAL
        marginal = "medium"
    elif len(redundant_axes) >= len(entries) - 1 and len(entries) > 1:
        rationale.append("Evidence predominantly redundant — PARTIAL saturation on tested axes.")
        level = SaturationLevel.PARTIAL
        marginal = "low"
    else:
        rationale.append("Major uncertainty dimensions remain — LOW saturation.")
        level = SaturationLevel.LOW
        marginal = "high"

    return EvidenceSaturationAssessment(
        level=level,
        unresolved_contradictions=bool(conflicts),
        major_uncertainty_dimensions_remaining=tuple(major_remaining),
        independence_obtained=tuple(indep_obtained),
        redundant_test_axes=tuple(set(redundant_axes)),
        executable_high_info_opportunities=tuple(high_info_ops),
        marginal_information=marginal,
        rationale=tuple(rationale),
    )


def _decide_research_priority(
    state: str,
    saturation: EvidenceSaturationAssessment,
    conflicts: List[Dict[str, Any]],
    unresolved: Tuple[str, ...],
    rel_map: Dict[str, str],
    profiles: Dict[str, Any],
    proposition_spec: Dict[str, Any],
) -> Tuple[ResearchPriorityAction, Tuple[str, ...], List[Dict[str, str]]]:
    rationale: List[str] = []
    candidates = [
        ResearchPriorityAction.SEEK_FALSIFICATION,
        ResearchPriorityAction.SEEK_REPLICATION,
        ResearchPriorityAction.SEEK_CONTRADICTION_RESOLUTION,
        ResearchPriorityAction.HOLD_PROVISIONALLY,
        ResearchPriorityAction.HOLD_UNRESOLVED,
        ResearchPriorityAction.ABANDON,
    ]

    if state == "FALSIFIED":
        chosen = ResearchPriorityAction.ABANDON
        rationale.append("FALSIFIED — ABANDON as highest-value research action.")
    elif state == "CONFLICTED" and conflicts:
        if saturation.executable_high_info_opportunities:
            chosen = ResearchPriorityAction.SEEK_CONTRADICTION_RESOLUTION
            rationale.append("CONFLICTED with resolvable axis — seek contradiction resolution.")
        else:
            chosen = ResearchPriorityAction.HOLD_UNRESOLVED
            rationale.append("CONFLICTED but no executable resolution — HOLD_UNRESOLVED.")
    elif state == "WEAKENED":
        chosen = ResearchPriorityAction.SEEK_REPLICATION
        rationale.append("WEAKENED — seek independent replication.")
    elif saturation.level == SaturationLevel.HIGH and not saturation.unresolved_contradictions:
        chosen = ResearchPriorityAction.HOLD_PROVISIONALLY
        rationale.append(
            "HIGH saturation, no contradiction — HOLD_PROVISIONALLY "
            "(research-usable provisional knowledge, not proven true)."
        )
    elif saturation.executable_high_info_opportunities and saturation.marginal_information == "high":
        # Prefer falsification on untouched axes over generic holdout repeat
        redundant = set(saturation.redundant_test_axes)
        non_redundant = [d for d in saturation.executable_high_info_opportunities if d not in redundant]
        if non_redundant:
            chosen = ResearchPriorityAction.SEEK_FALSIFICATION
            rationale.append(
                f"Material unresolved vulnerability on axes {non_redundant} — SEEK_FALSIFICATION "
                "(distinct axis, not redundant holdout)."
            )
        elif saturation.redundant_test_axes and not non_redundant:
            chosen = ResearchPriorityAction.HOLD_PROVISIONALLY
            rationale.append(
                "Remaining opportunities are redundant with ledger — generic holdout not highest value; "
                "HOLD_PROVISIONALLY or seek non-redundant axis."
            )
        else:
            chosen = ResearchPriorityAction.SEEK_FALSIFICATION
            rationale.append("Unresolved uncertainty with marginal information — SEEK_FALSIFICATION.")
    elif saturation.marginal_information == "low" and state == "SUPPORTED":
        if saturation.major_uncertainty_dimensions_remaining:
            chosen = ResearchPriorityAction.SEEK_FALSIFICATION
            rationale.append(
                f"Major uncertainty dimensions remain {list(saturation.major_uncertainty_dimensions_remaining)} "
                "— SEEK_FALSIFICATION despite low marginal on redundant axes."
            )
        else:
            chosen = ResearchPriorityAction.HOLD_PROVISIONALLY
            rationale.append("SUPPORTED with low marginal information on immediate next test — HOLD_PROVISIONALLY.")
    elif not saturation.executable_high_info_opportunities:
        chosen = ResearchPriorityAction.HOLD_UNRESOLVED
        rationale.append("No executable high-information experiment remains — HOLD_UNRESOLVED.")
    else:
        chosen = ResearchPriorityAction.SEEK_FALSIFICATION
        rationale.append("Default: unresolved vulnerability with falsification opportunity.")

    rejected = [
        {"action": c.value, "reason": f"Not selected over {chosen.value}"}
        for c in candidates
        if c != chosen
    ]
    return chosen, tuple(rationale), rejected


def engine_content_hash() -> str:
    """Deterministic hash of engine version for freeze gate."""
    return stable_hash({"engine_version": SYNTHESIS_ENGINE_VERSION, "ruleset": "3i12_v1"})
