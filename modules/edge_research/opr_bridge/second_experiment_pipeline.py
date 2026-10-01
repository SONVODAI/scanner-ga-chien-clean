"""
Phase 3J.6 — Second-experiment design pipeline orchestrator.

Causal order:
Frozen ResearchDecisionRecord → objective → candidates → dedup → rank → package → STOP
Does NOT execute Experiment #2 or rerun decide_next_action().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_execution_overlap import (
    build_first_experiment_fingerprint,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import envelope_from_dict
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.first_experiment_research_decision_persistence import (
    decision_envelope_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    FirstExperimentResearchDecisionEnvelope,
)
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.second_experiment_candidates import (
    deduplicate_second_experiment_candidates,
    generate_second_experiment_candidates,
)
from modules.edge_research.opr_bridge.second_experiment_design_gate import (
    validate_second_experiment_design_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_objective import derive_second_experiment_objective
from modules.edge_research.opr_bridge.second_experiment_records import (
    DESIGN_VERSION,
    GENERATOR_VERSION,
    PACKAGE_RECORD_VERSION,
    SELECTOR_VERSION,
    STOP_SECOND_EXPERIMENT_DESIGNED,
    SecondExperimentPackage,
)
from modules.edge_research.opr_bridge.second_experiment_selector import select_second_experiment

PIPELINE_VERSION = "second_experiment_pipeline_v1_3j6"


def _cohort_strategy_from_package(package: InitialExperimentPackage) -> str:
    if not package.selected_candidate_id:
        return "unknown"
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c.scientific_identity.get("cohort_strategy", "unknown")
    return "unknown"


@dataclass
class SecondExperimentDesignResult:
    outcome: str
    package: Optional[SecondExperimentPackage]
    stop_boundary: str
    idempotent_replay: bool = False
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "package": self.package.to_dict() if self.package else None,
            "stop_boundary": self.stop_boundary,
            "idempotent_replay": self.idempotent_replay,
            "errors": list(self.errors),
            "pipeline_version": PIPELINE_VERSION,
        }


def run_second_experiment_design_pipeline(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    first_package: InitialExperimentPackage,
    first_execution: FirstExperimentExecutionEnvelope,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
    executability: Optional[ExecutabilityContext] = None,
    include_wrong_null_audit: bool = False,
    existing_package: Optional[SecondExperimentPackage] = None,
) -> SecondExperimentDesignResult:
    """
    Transform frozen ResearchDecisionRecord into SecondExperimentPackage(NOT_EXECUTED).
    """
    eligibility = validate_second_experiment_design_eligibility(
        prop=prop,
        first_package=first_package,
        first_execution=first_execution,
        interpretation_envelope=interpretation_envelope,
        decision_envelope=decision_envelope,
        existing_package=existing_package,
    )

    if eligibility.idempotent_replay and existing_package is not None:
        return SecondExperimentDesignResult(
            outcome="IDEMPOTENT_REPLAY",
            package=existing_package,
            stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
            idempotent_replay=True,
        )

    if not eligibility.eligible:
        return SecondExperimentDesignResult(
            outcome="NOT_ELIGIBLE",
            package=None,
            stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
            errors=tuple(eligibility.reasons),
        )

    if decision_envelope.decision_kind != "ACTION":
        stub = _stub_objective(prop, decision_envelope)
        return SecondExperimentDesignResult(
            outcome="DECISION_STOPPED",
            package=_build_silence_package(
                prop,
                first_package,
                first_execution,
                interpretation_envelope,
                decision_envelope,
                objective=stub,
                raw_candidates=tuple(),
                deduped=tuple(),
                selection_reason="Research decision is STOP — no second experiment design",
            ),
            stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
        )

    cutoff = prop.get("observation_provenance", {}).get("evidence_anchor", {}).get("data_cutoff_date", "")
    if executability is None:
        executability = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)

    panel_index = PanelMetadataIndex.from_dataframe(panel, cutoff=cutoff or executability.data_cutoff)
    cohort = _cohort_strategy_from_package(first_package)
    first_fp = build_first_experiment_fingerprint(
        first_execution, panel_index, cohort_strategy=cohort
    )

    objective = derive_second_experiment_objective(prop, decision_envelope)
    if objective is None:
        return SecondExperimentDesignResult(
            outcome="NO_OBJECTIVE",
            package=_build_silence_package(
                prop,
                first_package,
                first_execution,
                interpretation_envelope,
                decision_envelope,
                objective=None,
                raw_candidates=tuple(),
                deduped=tuple(),
                selection_reason="Could not derive objective from frozen decision",
            ),
            stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
        )

    raw_candidates = generate_second_experiment_candidates(
        prop,
        objective,
        first_package=first_package,
        first_execution=first_execution,
        first_fp=first_fp,
        panel=panel_index,
        executability=executability,
        panel_df=panel,
        include_wrong_null_audit=include_wrong_null_audit,
    )
    deduped = deduplicate_second_experiment_candidates(raw_candidates)
    selection = select_second_experiment(deduped)

    package = _build_package(
        prop,
        first_package,
        first_execution,
        interpretation_envelope,
        decision_envelope,
        objective,
        raw_candidates=tuple(raw_candidates),
        deduped=tuple(deduped),
        selection=selection,
    )

    return SecondExperimentDesignResult(
        outcome="DESIGNED" if selection.selected else selection.disposition,
        package=package,
        stop_boundary=STOP_SECOND_EXPERIMENT_DESIGNED,
    )


def _build_package(
    prop: Dict[str, Any],
    first_package: InitialExperimentPackage,
    first_execution: FirstExperimentExecutionEnvelope,
    interpretation_envelope: FirstExperimentInterpretationEnvelope,
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
    objective,
    *,
    raw_candidates,
    deduped,
    selection,
) -> SecondExperimentPackage:
    ts = utc_now_iso()
    pkg_id = new_id("sefp")
    rd = decision_envelope.research_decision
    epu = interpretation_envelope.epistemic_update or {}

    body = {
        "package_id": pkg_id,
        "proposition_id": prop["proposition_id"],
        "research_decision_hash": rd.get("record_hash"),
        "disposition": selection.disposition,
        "selected_candidate_id": selection.selected.candidate_id if selection.selected else None,
    }

    return SecondExperimentPackage(
        package_id=pkg_id,
        record_version=PACKAGE_RECORD_VERSION,
        experiment_ordinal=2,
        proposition_id=prop["proposition_id"],
        proposition_hash=decision_envelope.proposition_hash,
        epistemic_update_id=str(epu.get("update_id", "")),
        epistemic_update_hash=str(epu.get("record_hash", "")),
        research_decision_id=str(rd.get("decision_id", "")),
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=decision_envelope.research_state_identity,
        first_package_id=first_package.package_id,
        first_package_hash=first_package.package_hash,
        first_execution_id=first_execution.execution_id,
        first_execution_identity_hash=first_execution.execution_identity_hash,
        generator_version=GENERATOR_VERSION,
        selector_version=SELECTOR_VERSION,
        design_version=DESIGN_VERSION,
        objective=objective,
        candidates_considered=raw_candidates,
        deduplicated_candidates=deduped,
        rejected=selection.rejected,
        ranking_trace=selection.ranking_trace,
        disposition=selection.disposition,
        selected_candidate_id=selection.selected.candidate_id if selection.selected else None,
        selected_experiment_spec=selection.selected.experiment_spec if selection.selected else None,
        selected_experiment_content_hash=(
            selection.selected.experiment_content_hash if selection.selected else None
        ),
        selection_reason=selection.reason,
        execution_status="NOT_EXECUTED",
        created_at=ts,
        package_hash=stable_hash(body),
    )


def _stub_objective(prop, decision_envelope) -> "SecondExperimentObjectiveRecord":
    from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
    from modules.edge_research.opr_bridge.second_experiment_objective import SecondExperimentObjectiveRecord
    from modules.edge_research.opr_bridge.second_experiment_records import OBJECTIVE_RECORD_VERSION

    rd = decision_envelope.research_decision
    ts = utc_now_iso()
    oid = new_id("seo")
    body = {
        "objective_id": oid,
        "proposition_id": prop["proposition_id"],
        "research_decision_id": rd.get("decision_id"),
        "selected_action": rd.get("chosen_next_action"),
        "target_null_key": "",
        "target_uncertainty": "",
    }
    return SecondExperimentObjectiveRecord(
        objective_id=oid,
        record_version=OBJECTIVE_RECORD_VERSION,
        proposition_id=prop["proposition_id"],
        proposition_hash=decision_envelope.proposition_hash,
        research_decision_id=str(rd.get("decision_id", "")),
        research_decision_hash=str(rd.get("record_hash", "")),
        selected_action=str(rd.get("chosen_next_action", "")),
        target_uncertainty="",
        target_null_key="",
        scientific_objective="No second experiment — decision stopped",
        why_this_design="Decision kind is not ACTION",
        created_at=ts,
        objective_hash=stable_hash(body),
    )


def _build_silence_package(
    prop,
    first_package,
    first_execution,
    interpretation_envelope,
    decision_envelope,
    *,
    objective,
    raw_candidates,
    deduped,
    selection_reason: str,
) -> SecondExperimentPackage:
    from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentDisposition

    ts = utc_now_iso()
    pkg_id = new_id("sefp")
    rd = decision_envelope.research_decision
    epu = interpretation_envelope.epistemic_update or {}
    body = {
        "package_id": pkg_id,
        "proposition_id": prop["proposition_id"],
        "research_decision_hash": rd.get("record_hash"),
        "disposition": SecondExperimentDisposition.NO_FAITHFUL_SECOND_EXPERIMENT.value,
    }
    null_objective = objective
    if null_objective is None:
        null_objective = _stub_objective(prop, decision_envelope) if decision_envelope else objective

    return SecondExperimentPackage(
        package_id=pkg_id,
        record_version=PACKAGE_RECORD_VERSION,
        experiment_ordinal=2,
        proposition_id=prop["proposition_id"],
        proposition_hash=decision_envelope.proposition_hash,
        epistemic_update_id=str(epu.get("update_id", "")),
        epistemic_update_hash=str(epu.get("record_hash", "")),
        research_decision_id=str(rd.get("decision_id", "")),
        research_decision_hash=str(rd.get("record_hash", "")),
        research_state_identity=decision_envelope.research_state_identity,
        first_package_id=first_package.package_id,
        first_package_hash=first_package.package_hash,
        first_execution_id=first_execution.execution_id,
        first_execution_identity_hash=first_execution.execution_identity_hash,
        generator_version=GENERATOR_VERSION,
        selector_version=SELECTOR_VERSION,
        design_version=DESIGN_VERSION,
        objective=null_objective,
        candidates_considered=raw_candidates,
        deduplicated_candidates=deduped,
        rejected=tuple(),
        ranking_trace=tuple(),
        disposition=SecondExperimentDisposition.NO_FAITHFUL_SECOND_EXPERIMENT.value,
        selected_candidate_id=None,
        selected_experiment_spec=None,
        selected_experiment_content_hash=None,
        selection_reason=selection_reason,
        execution_status="NOT_EXECUTED",
        created_at=ts,
        package_hash=stable_hash(body),
    )


def run_second_experiment_design_from_dicts(
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    package_dict: Dict[str, Any],
    execution_dict: Dict[str, Any],
    interpretation_dict: Dict[str, Any],
    decision_dict: Dict[str, Any],
    executability: Optional[ExecutabilityContext] = None,
    include_wrong_null_audit: bool = False,
    existing_package_dict: Optional[Dict[str, Any]] = None,
) -> SecondExperimentDesignResult:
    from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict
    from modules.edge_research.opr_bridge.second_experiment_design_persistence import package_from_dict as se_pkg_from_dict

    first_package = package_from_dict(package_dict)
    first_execution = envelope_from_dict(execution_dict)
    interpretation = interpretation_envelope_from_dict(interpretation_dict)
    decision = decision_envelope_from_dict(decision_dict)
    existing = se_pkg_from_dict(existing_package_dict) if existing_package_dict else None

    return run_second_experiment_design_pipeline(
        prop,
        panel,
        first_package=first_package,
        first_execution=first_execution,
        interpretation_envelope=interpretation,
        decision_envelope=decision,
        executability=executability,
        include_wrong_null_audit=include_wrong_null_audit,
        existing_package=existing,
    )
