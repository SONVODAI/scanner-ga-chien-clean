"""
Phase 3J.2 — First-experiment pipeline orchestrator.

Causal order:
PropositionRecord → objectives → candidates → dedup → independence → rank → spec → package → STOP
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_candidates import (
    deduplicate_first_experiment_candidates,
    generate_first_experiment_candidates,
)
from modules.edge_research.opr_bridge.first_experiment_objective import derive_initial_experiment_objectives
from modules.edge_research.opr_bridge.first_experiment_records import (
    GENERATOR_VERSION,
    PACKAGE_RECORD_VERSION,
    InitialExperimentPackage,
    PackageExecutionStatus,
)
from modules.edge_research.opr_bridge.first_experiment_selector import select_first_experiment
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

PIPELINE_VERSION = "first_experiment_pipeline_v1_3j2"


def build_panel_index(panel: pd.DataFrame, *, cutoff: str) -> PanelMetadataIndex:
    return PanelMetadataIndex.from_dataframe(panel, cutoff=cutoff)


def run_first_experiment_pipeline(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    executability: Optional[ExecutabilityContext] = None,
    include_audit_sketches: bool = False,
) -> InitialExperimentPackage:
    """
    Derive, generate, deduplicate, rank, and freeze InitialExperimentPackage.
    Does NOT execute any experiment.
    """
    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    if executability is None:
        executability = ExecutabilityContext.real_partition_for_panel(
            data_cutoff=cutoff, panel=panel
        )

    panel_index = build_panel_index(panel, cutoff=cutoff or executability.data_cutoff)

    objectives = derive_initial_experiment_objectives(prop)
    raw_candidates = generate_first_experiment_candidates(
        prop,
        objectives,
        panel_index,
        executability,
        include_audit_sketches=include_audit_sketches,
        panel_df=panel,
    )
    deduped = deduplicate_first_experiment_candidates(raw_candidates)
    selection = select_first_experiment(deduped)

    prop_hash = proposition_content_hash(prop)
    ts = utc_now_iso()
    pkg_id = new_id("iefp")

    human_material = _assess_human_choice_material(selection, deduped)

    body = {
        "package_id": pkg_id,
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_hash,
        "disposition": selection.disposition,
        "selected_candidate_id": selection.selected.candidate_id if selection.selected else None,
        "candidate_hashes": sorted(c.record_hash for c in deduped),
    }
    return InitialExperimentPackage(
        package_id=pkg_id,
        record_version=PACKAGE_RECORD_VERSION,
        proposition_id=prop["proposition_id"],
        proposition_hash=prop_hash,
        generator_version=GENERATOR_VERSION,
        selector_version=selection.selector_version,
        objectives=tuple(objectives),
        candidates_considered=tuple(raw_candidates),
        deduplicated_candidates=tuple(deduped),
        rejected=selection.rejected,
        ranking_trace=selection.ranking_trace,
        disposition=selection.disposition,
        selected_candidate_id=selection.selected.candidate_id if selection.selected else None,
        selected_experiment_spec=selection.selected.experiment_spec if selection.selected else None,
        selection_reason=selection.reason,
        human_choice_material=human_material,
        human_choice_reason=_human_choice_reason(selection, deduped),
        execution_status=PackageExecutionStatus.NOT_EXECUTED.value,
        created_at=ts,
        package_hash=stable_hash(body),
    )


def _assess_human_choice_material(selection, candidates) -> bool:
    """True if winner is determined by tool prior rather than scientific dominance."""
    if not selection.selected:
        return False
    if selection.selected.primary_classification in (
        "REDUNDANT_WITH_BIRTH_EVIDENCE",
        "CONFIRMATORY_ONLY",
    ):
        return True
    falsifiers = [c for c in candidates if c.primary_classification == "FALSIFICATION_CAPABLE"]
    if falsifiers and selection.selected.primary_classification != "FALSIFICATION_CAPABLE":
        return True
    return False


def _human_choice_reason(selection, candidates) -> str:
    if not selection.selected:
        if selection.disposition == "NO_HIGH_INFORMATION_FIRST_EXPERIMENT":
            return "Valid scientific silence — no high-information first experiment"
        if selection.disposition == "AMBIGUOUS_FIRST_EXPERIMENT":
            return "Ambiguous tie — no unilateral selection"
        return "No selection"
    if _assess_human_choice_material(selection, candidates):
        return "Selected path may not reflect scientific dominance over birth-redundant default"
    return "Scientific lexicographic dominance — tools bound last"
