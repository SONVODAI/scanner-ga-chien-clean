"""
Phase 3J.6 — First-experiment execution cohort overlap (history-aware design).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Set, Tuple

from modules.edge_research.opr_bridge.cohort_overlap_estimator import (
    PanelMetadataIndex,
    PriorCohortFingerprint,
    candidate_row_keys,
    derive_independence_from_overlap,
    estimate_overlap,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope


@dataclass(frozen=True)
class FirstExperimentCohortFingerprint:
    population_spec: Dict[str, Any]
    cohort_strategy: str
    row_keys: Set[Tuple[str, str]]
    dates: Set[str]
    experiment_content_hash: str
    scientific_action_core_hash: str
    tool_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "population_spec": dict(self.population_spec),
            "cohort_strategy": self.cohort_strategy,
            "row_count": len(self.row_keys),
            "dates": sorted(self.dates),
            "experiment_content_hash": self.experiment_content_hash,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "tool_name": self.tool_name,
        }


def build_first_experiment_fingerprint(
    envelope: FirstExperimentExecutionEnvelope,
    panel: PanelMetadataIndex,
    *,
    cohort_strategy: str = "unknown",
) -> FirstExperimentCohortFingerprint:
    audit = envelope.binding_audit
    pop = dict(audit.population_spec)
    keys = candidate_row_keys(panel, pop)
    dates = {d for d, _ in keys}
    return FirstExperimentCohortFingerprint(
        population_spec=pop,
        cohort_strategy=cohort_strategy,
        row_keys=keys,
        dates=dates,
        experiment_content_hash=envelope.experiment_content_hash,
        scientific_action_core_hash=envelope.scientific_action_core_hash,
        tool_name=audit.tool_name,
    )


def measure_first_experiment_overlap(
    *,
    candidate_population_spec: Dict[str, Any],
    panel: PanelMetadataIndex,
    first_fp: FirstExperimentCohortFingerprint,
) -> Tuple[float, Dict[str, str]]:
    cand_keys = candidate_row_keys(panel, candidate_population_spec)
    if not first_fp.row_keys:
        return 0.0, {"sample_independence": "HIGH", "rationale": "no_first_experiment_rows"}

    prior = PriorCohortFingerprint(
        evidence_id="first_experiment",
        row_keys=first_fp.row_keys,
        dates=first_fp.dates,
        symbols={s for _, s in cand_keys},
        contexts=set(),
        population_semantics=str(first_fp.population_spec.get("kind", "filter")),
        cohort_overlap_ratio=1.0,
    )
    profile = estimate_overlap(cand_keys, panel, [prior], motivating_dates=tuple(sorted(first_fp.dates)))
    indep = derive_independence_from_overlap(profile, source_dimension="first_experiment")
    inter = len(cand_keys & first_fp.row_keys)
    overlap_frac = inter / max(len(cand_keys), 1)
    return overlap_frac, indep.to_dict()
