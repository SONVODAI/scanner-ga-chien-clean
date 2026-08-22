"""
Phase 3I.7 — Minimal lifecycle runner (single proposition, single experiment, no retry).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.executability_adapter import adapt_executability
from modules.edge_research.opr_bridge.interpretation_contract import (
    build_interpretation_contract,
    proposition_content_hash,
)
from modules.edge_research.opr_bridge.lifecycle_execution import (
    extract_quintile_metrics,
    tool_result_hash,
)
from modules.edge_research.opr_bridge.lifecycle_records import LIFECYCLE_VERSION, stable_hash
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    build_epistemic_update,
    build_research_decision,
    decide_next_action,
    interpret_experiment_evidence,
)
from modules.edge_research.opr_bridge.proposition_record import PropositionRecord
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry


def load_proposition_record(prop_dict: Dict[str, Any]) -> PropositionRecord:
    """Rehydrate PropositionRecord from frozen JSON dict."""
    from modules.edge_research.opr_bridge.proposition_record import (
        Confidence,
        DisconfirmingObservationSpec,
        EpistemicStatus,
        ExecutabilityStatus,
        ObservationProvenance,
        ScientificBirthCertificate,
        BirthCertificateAnswer,
        TemplateIndependenceResult,
        TemplateClassification,
    )

    prov = prop_dict["observation_provenance"]
    dis = prop_dict["disconfirming_observation_spec"]
    bc = prop_dict["birth_certificate"]

    record = PropositionRecord(
        proposition_id=prop_dict["proposition_id"],
        record_version=prop_dict["record_version"],
        created_at=prop_dict["created_at"],
        research_step=prop_dict.get("research_step", 0),
        generator_version=prop_dict["generator_version"],
        observation_provenance=ObservationProvenance(
            evidence_anchor=prov["evidence_anchor"],
            empirical_artifacts=tuple(prov["empirical_artifacts"]),
            structural_context=prov["structural_context"],
            surprise_basis=prov["surprise_basis"],
            evidence_hash=prov["evidence_hash"],
        ),
        motivating_observation=prop_dict["motivating_observation"],
        surprise_or_uncertainty=prop_dict["surprise_or_uncertainty"],
        scientific_question=prop_dict["scientific_question"],
        canonical_proposition_core=prop_dict["canonical_proposition_core"],
        population_context=prop_dict["population_context"],
        explanatory_relation=prop_dict["explanatory_relation"],
        outcome=prop_dict["outcome"],
        observation_horizon=prop_dict["observation_horizon"],
        falsifiable_expectation=prop_dict["falsifiable_expectation"],
        null_competing_explanation=prop_dict["null_competing_explanation"],
        disconfirming_observation_spec=DisconfirmingObservationSpec(
            description=dis["description"],
            operational_test=dis["operational_test"],
            threshold=dis["threshold"],
            alternative_interpretation=dis["alternative_interpretation"],
        ),
        evidence_required=prop_dict["evidence_required"],
        execution_requirements=prop_dict["execution_requirements"],
        epistemic_status=EpistemicStatus(prop_dict.get("epistemic_status", "HYPOTHESIS")),
        confidence=Confidence(prop_dict.get("confidence", "LOW")),
        semantic_parent_id=prop_dict.get("semantic_parent_id"),
        generation_lineage=tuple(prop_dict.get("generation_lineage", [])),
        birth_certificate=ScientificBirthCertificate(
            answers=tuple(
                BirthCertificateAnswer(a["question_id"], a["passed"], a["answer"])
                for a in bc["answers"]
            )
        ),
        experiment_spec_draft=prop_dict.get("experiment_spec_draft"),
        executability_status=ExecutabilityStatus(
            prop_dict.get("executability_status", "NOT_ATTEMPTED")
        ),
    )
    return record


def execute_frozen_experiment(
    spec: ExperimentSpec,
    panel: pd.DataFrame,
    registry: Optional[ToolRegistry] = None,
):
    from modules.edge_research.research_tools import ToolResult

    reg = registry or build_default_tool_registry()
    tool = reg.get(spec.tool_name, spec.tool_version)
    return tool.execute(
        panel.copy(),
        inputs=dict(spec.inputs),
        research_scope=dict(spec.research_scope or {}),
        data_cutoff_date=spec.data_cutoff_date,
    )


def run_minimal_lifecycle(
    prop_dict: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    experiment_ref: str = "lifecycle_exp_001",
    prebuilt_tool_result=None,
    prebuilt_quintile_metrics=None,
    interpretation_contract=None,
    interpretation_contract_ref: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full minimal lifecycle: contract → execute → interpret → update → decide → lineage.

    If prebuilt_tool_result provided (synthetic tests), skips panel execution.
    If interpretation_contract provided, uses frozen contract (provenance-safe).
    """
    from modules.edge_research.opr_bridge.interpretation_contract import (
        InterpretationContract,
    )

    prop_hash = proposition_content_hash(prop_dict)
    if interpretation_contract is not None:
        contract = interpretation_contract
    else:
        contract = build_interpretation_contract(prop_dict)
    contract_ref = interpretation_contract_ref or {
        "source": "runtime_build",
        "contract_hash": contract.contract_hash,
    }
    prior_state = prop_dict.get("epistemic_status", "HYPOTHESIS")
    cutoff = prop_dict["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]

    record = load_proposition_record(prop_dict)
    exec_result = adapt_executability(record, panel)
    if exec_result.experiment_spec is None:
        raise RuntimeError(f"Proposition not executable: {exec_result.detail}")
    spec = exec_result.experiment_spec

    if prebuilt_tool_result is not None:
        tool_result = prebuilt_tool_result
        qm = prebuilt_quintile_metrics
    else:
        tool_result = execute_frozen_experiment(spec, panel)
        qm = extract_quintile_metrics(
            panel,
            spec,
            partition_column=contract.partition_column,
            outcome_field=contract.outcome_field,
        )

    interpretation = interpret_experiment_evidence(
        contract, tool_result, qm, expected_cutoff=cutoff
    )
    resulting_state, transition_key = apply_epistemic_transition(
        contract, interpretation, prior_state
    )
    chosen, reason, rejected = decide_next_action(contract, interpretation, transition_key)

    tr_hash = tool_result_hash(tool_result.to_dict())
    update = build_epistemic_update(
        prop_dict,
        contract,
        interpretation,
        experiment_ref=experiment_ref,
        tool_result_hash=tr_hash,
        prior_state=prior_state,
        resulting_state=resulting_state,
    )
    decision = build_research_decision(
        prop_dict,
        contract,
        interpretation,
        update,
        chosen_action=chosen,
        reason=reason,
        rejected=rejected,
    )

    lineage = {
        "lifecycle_version": LIFECYCLE_VERSION,
        "proposition_id": prop_dict["proposition_id"],
        "proposition_hash": prop_hash,
        "proposition_immutable": True,
        "experiment_spec": exec_result.experiment_spec.to_dict() if hasattr(exec_result.experiment_spec, "to_dict") else {
            "tool_name": spec.tool_name,
            "inputs": dict(spec.inputs),
            "data_cutoff_date": spec.data_cutoff_date,
        },
        "tool_result_hash": tr_hash,
        "interpretation_contract_hash": contract.contract_hash,
        "interpretation_contract_ref": contract_ref,
        "interpretation": interpretation.to_dict(),
        "epistemic_update": update.to_dict(),
        "research_decision": decision.to_dict(),
        "lineage_hash": stable_hash(
            {
                "proposition_hash": prop_hash,
                "contract_hash": contract.contract_hash,
                "tool_result_hash": tr_hash,
                "update_hash": update.record_hash,
                "decision_hash": decision.record_hash,
            }
        ),
    }

    return {
        "contract": contract.to_dict(),
        "tool_result": tool_result.to_dict(),
        "quintile_metrics": qm.to_dict(),
        "interpretation": interpretation.to_dict(),
        "epistemic_update": update.to_dict(),
        "research_decision": decision.to_dict(),
        "lineage": lineage,
        "proposition_hash": prop_hash,
    }


def extract_frozen_proposition_from_3i5(replay_path: Path) -> Dict[str, Any]:
    """Load prioritized representative proposition from 3I.5 replay artifact."""
    data = json.loads(replay_path.read_text())
    records = data["new_result_dict"]["records"]
    if not records:
        raise RuntimeError("No records in 3I.5 replay")
    return records[0]
