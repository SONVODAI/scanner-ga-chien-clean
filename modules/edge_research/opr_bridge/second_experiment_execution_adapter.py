"""
Phase 3J.7 — Adapter: SecondExperimentPackage → InitialExperimentPackage for 3J.3 reuse.
"""

from __future__ import annotations

from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_records import (
    FirstExperimentCandidateRecord,
    FirstExperimentDisposition,
    InitialExperimentObjectiveRecord,
    InitialExperimentPackage,
)
from modules.edge_research.opr_bridge.second_experiment_records import (
    SecondExperimentCandidateRecord,
    SecondExperimentDisposition,
    SecondExperimentPackage,
)


def _to_first_candidate(c: SecondExperimentCandidateRecord) -> FirstExperimentCandidateRecord:
    return FirstExperimentCandidateRecord(
        candidate_id=c.candidate_id,
        record_version="second_to_first_adapter_v1_3j7",
        proposition_id=c.proposition_id,
        proposition_hash=c.proposition_hash,
        objective_id=c.objective_id,
        scientific_action_core_hash=c.scientific_action_core_hash,
        scientific_identity=dict(c.scientific_identity),
        primary_classification=c.primary_classification,
        secondary_classifications=(),
        classification_rationale=c.falsification_rationale,
        falsification_capable=c.falsification_capable,
        confirmatory_only=not c.falsification_capable,
        birth_evidence_overlap_fraction=c.birth_evidence_overlap_fraction,
        independence_profile=dict(c.first_experiment_independence_profile),
        directness_rank=0,
        epistemic_alteration_potential="MEDIUM",
        rescue_risk_status="pass",
        executability_status=c.executability_status,
        executability_detail=c.executability_detail,
        experiment_spec=c.experiment_spec,
        representation_envelope=dict(c.representation_envelope),
        created_at=c.created_at,
        record_hash=c.record_hash,
    )


def second_package_to_initial_package(package: SecondExperimentPackage) -> InitialExperimentPackage:
    """Thin adapter — preserves selected spec/candidate for 3J.3 binding layer."""
    obj = package.objective
    objective = InitialExperimentObjectiveRecord(
        objective_id=obj.objective_id,
        record_version="second_to_first_adapter_v1_3j7",
        proposition_id=obj.proposition_id,
        proposition_hash=obj.proposition_hash,
        target_uncertainty=obj.target_uncertainty,
        scientific_vulnerability=obj.target_null_key,
        why_first=obj.why_this_design,
        outcome_branches={},
        forbidden_rescue_mutations=(),
        provenance={},
        directness_rank=0,
        created_at=obj.created_at,
        objective_hash=obj.objective_hash,
    )
    deduped = tuple(_to_first_candidate(c) for c in package.deduplicated_candidates)
    considered = tuple(_to_first_candidate(c) for c in package.candidates_considered)
    disposition = (
        FirstExperimentDisposition.SELECTED.value
        if package.disposition == SecondExperimentDisposition.SELECTED.value
        else FirstExperimentDisposition.NO_HIGH_INFORMATION_FIRST_EXPERIMENT.value
    )
    return InitialExperimentPackage(
        package_id=package.package_id,
        record_version="second_to_first_adapter_v1_3j7",
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        generator_version=package.generator_version,
        selector_version=package.selector_version,
        objectives=(objective,),
        candidates_considered=considered,
        deduplicated_candidates=deduped,
        rejected=package.rejected,
        ranking_trace=package.ranking_trace,
        disposition=disposition,
        selected_candidate_id=package.selected_candidate_id,
        selected_experiment_spec=package.selected_experiment_spec,
        selection_reason=package.selection_reason,
        human_choice_material=False,
        human_choice_reason="second_experiment_adapter",
        execution_status=package.execution_status,
        created_at=package.created_at,
        package_hash=package.package_hash,
    )
