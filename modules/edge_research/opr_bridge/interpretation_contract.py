"""
Phase 3I.7 — Pre-result interpretation contract builder.

Rules derived ONLY from proposition scientific commitments — frozen before ToolResult.
"""

from __future__ import annotations

from typing import Any, Dict

from modules.edge_research.opr_bridge.lifecycle_records import (
    LIFECYCLE_VERSION,
    InterpretationContract,
    stable_hash,
    utc_now_iso,
)

CONTRACT_VERSION = "interpretation_contract_v1_3i7"
SPREAD_SUPPORT_FLOOR = 0.5
SPREAD_DISCONFIRM_CEILING = 0.0


def proposition_content_hash(prop: Dict[str, Any]) -> str:
    """Hash immutable scientific content at lifecycle start."""
    payload = {
        "proposition_id": prop["proposition_id"],
        "scientific_question": prop["scientific_question"],
        "canonical_proposition_core": prop["canonical_proposition_core"],
        "falsifiable_expectation": prop["falsifiable_expectation"],
        "disconfirming_observation_spec": prop["disconfirming_observation_spec"],
        "experiment_spec_draft": prop.get("experiment_spec_draft"),
        "epistemic_status": prop.get("epistemic_status"),
    }
    return stable_hash(payload)


def build_interpretation_contract(prop: Dict[str, Any]) -> InterpretationContract:
    """
    Materialize machine-readable interpretation contract from frozen proposition.

    MUST be called before ToolResult is read.
    """
    rel = prop.get("explanatory_relation", {})
    direction = rel.get("contrast_direction", "negative")
    exec_req = prop.get("execution_requirements", {})
    disconfirm = prop.get("disconfirming_observation_spec", {})

    if direction == "positive":
        expected_rule = "high_quintile_mean > low_quintile_mean"
        support_rule = (
            f"high_quintile_mean > low_quintile_mean AND quintile_mean_spread >= {SPREAD_SUPPORT_FLOOR}"
        )
    else:
        expected_rule = "low_quintile_mean > high_quintile_mean"
        support_rule = (
            f"low_quintile_mean > high_quintile_mean AND quintile_mean_spread >= {SPREAD_SUPPORT_FLOOR}"
        )

    disconfirm_rule = (
        f"direction_violation OR outcome_spread <= {SPREAD_DISCONFIRM_CEILING} "
        f"OR median_spread <= {SPREAD_DISCONFIRM_CEILING}"
    )
    falsify_strong_rule = (
        f"direction_violation AND quintile_mean_spread >= {SPREAD_SUPPORT_FLOOR}"
    )
    non_info_rule = (
        f"quintile_mean_spread < {SPREAD_SUPPORT_FLOOR} AND NOT direction_violation "
        f"AND outcome_spread > {SPREAD_DISCONFIRM_CEILING}"
    )
    contradict_rule = (
        "direction_matches_quintile BUT outcome_spread_sign conflicts with quintile_delta_sign"
    )
    invalid_rule = "tool_status != OK OR sample_size < min_sample OR cutoff_mismatch OR missing_quintile_metrics"

    transition_mapping = {
        "SUPPORTING": "SUPPORTED",
        "DISCONFIRMING": "WEAKENED",
        "DISCONFIRMING_STRONG": "FALSIFIED",
        "CONTRADICTORY": "WEAKENED",
        "NON_INFORMATIVE": "INSUFFICIENT_EVIDENCE",
        "INVALID": "UNCHANGED",
    }

    decision_mapping = {
        "SUPPORTING": "SEEK_FALSIFICATION",
        "DISCONFIRMING": "SEEK_REPLICATION",
        "DISCONFIRMING_STRONG": "ABANDON",
        "CONTRADICTORY": "SEEK_FALSIFICATION",
        "NON_INFORMATIVE": "HOLD_UNRESOLVED",
        "INVALID": "HOLD_UNRESOLVED",
    }

    frozen_at = utc_now_iso()
    prop_hash = proposition_content_hash(prop)
    body = {
        "contract_version": CONTRACT_VERSION,
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_hash,
        "contrast_direction": direction,
        "partition_column": exec_req.get("partition_column", "rs_spread"),
        "outcome_field": prop.get("outcome", {}).get("field", "t5_return"),
        "min_sample": int(exec_req.get("min_sample", 58)),
        "spread_support_floor": SPREAD_SUPPORT_FLOOR,
        "spread_disconfirm_ceiling": SPREAD_DISCONFIRM_CEILING,
        "disconfirm_threshold_text": disconfirm.get("threshold", ""),
        "transition_mapping": transition_mapping,
        "decision_mapping": decision_mapping,
        "abandon_requires": "DISCONFIRMING_STRONG → FALSIFIED",
        "frozen_at": frozen_at,
        "lifecycle_version": LIFECYCLE_VERSION,
    }
    contract_hash = stable_hash(body)

    return InterpretationContract(
        contract_version=CONTRACT_VERSION,
        proposition_id=prop["proposition_id"],
        proposition_hash=prop_hash,
        contrast_direction=direction,
        partition_column=body["partition_column"],
        outcome_field=body["outcome_field"],
        min_sample=body["min_sample"],
        spread_support_floor=SPREAD_SUPPORT_FLOOR,
        spread_disconfirm_ceiling=SPREAD_DISCONFIRM_CEILING,
        expected_direction_rule=expected_rule,
        supporting_rule=support_rule,
        disconfirming_rule=disconfirm_rule,
        falsify_strong_rule=falsify_strong_rule,
        non_informative_rule=non_info_rule,
        contradictory_rule=contradict_rule,
        invalid_rule=invalid_rule,
        transition_mapping=transition_mapping,
        decision_mapping=decision_mapping,
        abandon_requires=body["abandon_requires"],
        frozen_at=frozen_at,
        contract_hash=contract_hash,
    )
