"""
Phase 3J.12 — Generic Experiment #N follow-on record helpers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash

GENERALIZATION_VERSION = "follow_on_experiment_records_v1_3j12"
HISTORY_AWARE_GENERATOR_VERSION = "follow_on_experiment_generator_v1_3j13"
HISTORY_AWARE_SELECTOR_VERSION = "follow_on_experiment_selector_lex_v1_3j13"
STOP_HISTORY_AWARE_FOLLOW_ON_GENERATION = "STOP_HISTORY_AWARE_FOLLOW_ON_GENERATION"

# Generic follow-on dispositions (ordinal >= 3). Legacy second-experiment names frozen at ordinal 2.
NO_FAITHFUL_EXPERIMENT = "NO_FAITHFUL_EXPERIMENT"
AMBIGUOUS_EXPERIMENT = "AMBIGUOUS_EXPERIMENT"
FOLLOW_ON_SELECTED = "SELECTED"


def compute_follow_on_decision_identity_hash(
    *,
    interpretation_identity_hash: str,
    epistemic_update_hash: str,
    prior_decision_hash: str,
    decision_ordinal: int,
    decider_version: str,
) -> str:
    return stable_hash(
        {
            "interpretation_identity_hash": interpretation_identity_hash,
            "epistemic_update_hash": epistemic_update_hash,
            "prior_decision_hash": prior_decision_hash,
            "decision_ordinal": decision_ordinal,
            "decider_version": decider_version,
        }
    )


def compute_follow_on_research_state_identity(
    *,
    proposition_hash: str,
    resulting_epistemic_state: str,
    interpretation_identity_hash: str,
    prior_decision_hash: str,
    decision_ordinal: int,
) -> str:
    return stable_hash(
        {
            "proposition_hash": proposition_hash,
            "resulting_epistemic_state": resulting_epistemic_state,
            "interpretation_identity_hash": interpretation_identity_hash,
            "prior_decision_hash": prior_decision_hash,
            "decision_ordinal": decision_ordinal,
        }
    )


def compute_follow_on_interpretation_identity_hash(
    *,
    contract_hash: str,
    tool_result_hash: str,
    execution_identity_hash: str,
    scientific_action_core_hash: str,
    prior_interpretation_id: str,
    experiment_ordinal: int,
    interpreter_version: str,
) -> str:
    return stable_hash(
        {
            "contract_hash": contract_hash,
            "tool_result_hash": tool_result_hash,
            "execution_identity_hash": execution_identity_hash,
            "scientific_action_core_hash": scientific_action_core_hash,
            "prior_interpretation_id": prior_interpretation_id,
            "experiment_ordinal": experiment_ordinal,
            "interpreter_version": interpreter_version,
        }
    )


def stop_boundary_for_follow_on_ordinal(ordinal: int, stage: str) -> str:
    if ordinal == 2:
        mapping = {
            "designed": "STOP_SECOND_EXPERIMENT_DESIGNED",
            "executed": "STOP_SECOND_EXPERIMENT_EXECUTED",
            "interpreted": "STOP_SECOND_EVIDENCE_INTERPRETED",
            "decided": "STOP_SECOND_RESEARCH_DECISION_FROZEN",
        }
        return mapping.get(stage, f"STOP_EXPERIMENT_{ordinal}_{stage.upper()}")
    mapping = {
        "designed": f"STOP_EXPERIMENT_{ordinal}_DESIGNED",
        "executed": f"STOP_EXPERIMENT_{ordinal}_EXECUTED",
        "interpreted": f"STOP_EXPERIMENT_{ordinal}_INTERPRETED",
        "decided": f"STOP_EXPERIMENT_{ordinal}_DECISION_FROZEN",
    }
    return mapping.get(stage, f"STOP_EXPERIMENT_{ordinal}_{stage.upper()}")
