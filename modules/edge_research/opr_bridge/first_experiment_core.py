"""
Phase 3J.2 — First-experiment scientific identity (generalized 3I.16).
"""

from __future__ import annotations

from typing import Dict, List

from modules.edge_research.opr_bridge.first_experiment_records import FirstExperimentCandidateRecord
from modules.edge_research.opr_bridge.scientific_action_records import ScientificActionCore


def candidate_to_core(identity: Dict[str, str]) -> ScientificActionCore:
    return ScientificActionCore(
        objective_target_uncertainty=identity["objective_target_uncertainty"],
        proposition_commitment_challenged=identity["proposition_commitment_challenged"],
        cohort_strategy=identity["cohort_strategy"],
        contrast_relation=identity["contrast_relation"],
        expected_epistemic_consequence_type=identity["expected_epistemic_consequence_type"],
        information_gain_type=identity["information_gain_type"],
    )


def deduplicate_by_scientific_identity(
    candidates: List[FirstExperimentCandidateRecord],
) -> List[FirstExperimentCandidateRecord]:
    """Keep highest scientific merit per core hash — tool representation excluded."""
    from modules.edge_research.opr_bridge.first_experiment_candidates import deduplicate_first_experiment_candidates

    return deduplicate_first_experiment_candidates(candidates)
