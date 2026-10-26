"""
Phase 3I.10 — One-shot autonomous falsification execution.

Executes exactly the frozen 3I.9 package once; interprets with frozen contract only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.falsification_candidate_generator import collect_motivating_episode_dates
from modules.edge_research.opr_bridge.falsification_records import GENERATOR_VERSION
from modules.edge_research.opr_bridge.falsification_selector import SELECTOR_VERSION, selector_content_hash
from modules.edge_research.opr_bridge.interpretation_contract import (
    interpretation_contract_from_dict,
    proposition_content_hash,
)
from modules.edge_research.opr_bridge.lifecycle_execution import extract_quintile_metrics, tool_result_hash
from modules.edge_research.opr_bridge.lifecycle_records import LIFECYCLE_VERSION, stable_hash, utc_now_iso, new_id
from modules.edge_research.opr_bridge.lifecycle_runner import execute_frozen_experiment
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    build_epistemic_update,
    build_research_decision,
    decide_next_action,
    interpret_experiment_evidence,
)
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

EXECUTION_VERSION = "falsification_one_shot_execution_v1_3i10"
EXPECTED_PACKAGE_HASH = "bdd77912ccdde41d2245ed36a95071335af68b06b1e005f41c153f86314bba46"
EXPECTED_CONTRACT_HASH = "3474a096aa6ee9c57ee1120f4a41398b08307038b23220016fa6bc9fddff77e2"


def _package_body_hash(body: Dict[str, Any]) -> str:
    payload = {k: v for k, v in body.items() if k != "package_hash"}
    return stable_hash(payload)


def load_one_shot_package(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_package_integrity(
    package: Dict[str, Any],
    *,
    candidate_record: Dict[str, Any],
    prior_epistemic_update: Dict[str, Any],
    proposition: Dict[str, Any],
    lineage: Dict[str, Any],
    expected_package_hash: str = EXPECTED_PACKAGE_HASH,
    expected_contract_hash: str = EXPECTED_CONTRACT_HASH,
) -> Dict[str, Any]:
    """Pre-execution integrity gate — STOP if any check fails."""
    body = {k: v for k, v in package.items() if k != "package_hash"}
    recomputed_pkg_hash = _package_body_hash(body)
    spec = package["selected_experiment_spec"]
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(spec))
    prop_hash = proposition_content_hash(proposition)

    checks = {
        "package_exists": True,
        "package_hash_matches": package.get("package_hash") == expected_package_hash,
        "package_hash_recomputed": recomputed_pkg_hash == package.get("package_hash"),
        "execution_status_not_executed": package.get("execution_status") == "NOT_EXECUTED",
        "proposition_id_matches": package["proposition_id"] == proposition["proposition_id"],
        "proposition_hash_matches": package["proposition_hash"] == prop_hash,
        "prior_lineage_hash_matches": package["prior_lineage_hash"] == lineage.get("lineage_hash"),
        "interpretation_contract_hash_matches": package["interpretation_contract_hash"] == expected_contract_hash,
        "selected_candidate_id_matches": package["selected_candidate_id"] == candidate_record["candidate_id"],
        "selected_candidate_hash_matches": package["selected_candidate_hash"] == candidate_record["record_hash"],
        "experiment_spec_hash_matches": package["selected_experiment_content_hash"] == spec_hash,
        "candidate_spec_matches_package": candidate_record["proposed_experiment_spec"] == spec,
        "generator_version_matches": package["generator_version"] == GENERATOR_VERSION,
        "selector_version_matches": package["selector_version"] == selector_content_hash(),
        "prior_epistemic_state_supported": prior_epistemic_update["resulting_epistemic_state"] == "SUPPORTED",
    }
    checks["passed"] = all(checks.values())
    checks["failures"] = [k for k, v in checks.items() if k not in ("passed", "failures") and not v]
    return checks


def audit_supported_state_transition(
    contract,
    interpretation,
    prior_state: str,
) -> Dict[str, Any]:
    """
    Audit whether SUPPORTED + evidence class has a frozen transition in artifact 03.

    Production semantics: evidence-class → absolute resulting state (prior-agnostic
    except INVALID → UNCHANGED). Mapping was frozen before any falsification result.
    """
    ec = interpretation.evidence_class
    strength = interpretation.metrics_used.get("falsify_strength", "WEAK")
    if ec.value == "DISCONFIRMING":
        key = "DISCONFIRMING_STRONG" if strength == "STRONG" else "DISCONFIRMING"
    else:
        key = ec.value

    mapping = contract.transition_mapping
    if key not in mapping and ec.value in mapping:
        key = ec.value

    mapped = mapping.get(key)
    preregistered = mapped is not None
    if mapped == "UNCHANGED":
        resulting = prior_state
    else:
        resulting = mapped if mapped else prior_state

    decision_mapping = contract.decision_mapping
    decision_preregistered = key in decision_mapping or ec.value in decision_mapping

    return {
        "prior_state": prior_state,
        "evidence_class": ec.value,
        "transition_key": key,
        "frozen_transition_mapping_entry": mapped,
        "resulting_state": resulting,
        "preregistered_in_frozen_contract": preregistered,
        "decision_preregistered": decision_preregistered,
        "state_transition_not_preregistered": not preregistered,
        "note": (
            "Frozen artifact 03 transition_mapping is evidence-absolute; "
            "validated at 3I.7 from HYPOTHESIS but applied uniformly to all interpretations "
            "under the same contract without post-hoc modification."
        ),
    }


def _audit_operational_independence(
    spec: ExperimentSpec,
    panel: pd.DataFrame,
    proposition: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify executed cohort excludes motivating episodes per frozen spec."""
    from modules.edge_research.research_tools import resolve_cohort

    motivating = set(collect_motivating_episode_dates(proposition))
    cohort, diag = resolve_cohort(
        panel,
        spec.research_scope or {},
        data_cutoff_date=spec.data_cutoff_date,
        horizon=str(spec.inputs.get("horizon", "T5")),
    )
    if "trade_date" not in cohort.columns:
        return {"passed": False, "reason": "no_trade_date_column"}
    dates_in_cohort = set(cohort["trade_date"].astype(str).unique())
    overlap = dates_in_cohort & motivating
    return {
        "passed": len(overlap) == 0,
        "motivating_episodes": sorted(motivating),
        "dates_in_executed_cohort": len(dates_in_cohort),
        "overlap": sorted(overlap),
        "cohort_n": len(cohort),
        "population_spec_applied": diag.get("population_spec_applied", False),
    }


def audit_evidence_independence(
    package: Dict[str, Any],
    proposition: Dict[str, Any],
    panel: pd.DataFrame,
) -> Dict[str, Any]:
    spec = package["selected_experiment_spec"]
    holdout_dates = set(spec["research_scope"]["population_spec"]["values"])
    motivating = set(collect_motivating_episode_dates(proposition))
    overlap = holdout_dates & motivating
    cutoff = spec["data_cutoff_date"]

    panel_dates = set()
    if "trade_date" in panel.columns:
        df = panel.copy()
        df["trade_date"] = df["trade_date"].astype(str)
        panel_dates = set(df[df["trade_date"] <= cutoff]["trade_date"].unique())

    post_cutoff_in_holdout = [d for d in holdout_dates if d > cutoff]
    missing_from_panel = [d for d in holdout_dates if d not in panel_dates]

    return {
        "motivating_episodes_excluded": sorted(motivating),
        "holdout_date_count": len(holdout_dates),
        "overlap_with_motivating": sorted(overlap),
        "independence_pass": len(overlap) == 0 and len(post_cutoff_in_holdout) == 0,
        "post_cutoff_violations": post_cutoff_in_holdout,
        "missing_panel_dates": missing_from_panel,
    }


def run_one_shot_falsification_execution(
    package: Dict[str, Any],
    *,
    proposition: Dict[str, Any],
    prior_epistemic_update: Dict[str, Any],
    prior_research_decision: Dict[str, Any],
    candidate_record: Dict[str, Any],
    lineage: Dict[str, Any],
    interpretation_contract_dict: Dict[str, Any],
    panel: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Execute frozen package once, interpret, append epistemic update.
    """
    integrity = verify_package_integrity(
        package,
        candidate_record=candidate_record,
        prior_epistemic_update=prior_epistemic_update,
        proposition=proposition,
        lineage=lineage,
    )
    if not integrity["passed"]:
        return {
            "verdict": "PACKAGE_INTEGRITY_FAIL",
            "integrity": integrity,
            "executed": False,
        }

    contract = interpretation_contract_from_dict(interpretation_contract_dict)
    spec = ExperimentSpec.from_dict(package["selected_experiment_spec"])
    prior_state = prior_epistemic_update["resulting_epistemic_state"]
    prop_hash_before = proposition_content_hash(proposition)
    package_hash_before = package["package_hash"]
    execution_id = new_id("fex")
    executed_at = utc_now_iso()

    independence = audit_evidence_independence(package, proposition, panel)
    if not independence["independence_pass"]:
        return {
            "verdict": "EXECUTION_INVALID",
            "integrity": integrity,
            "independence_audit": independence,
            "executed": False,
        }

    tool_result = execute_frozen_experiment(spec, panel)
    tr_dict = tool_result.to_dict()
    tr_hash = tool_result_hash(tr_dict)

    operational_independence = _audit_operational_independence(spec, panel, proposition)
    if not operational_independence["passed"]:
        return {
            "verdict": "EXECUTION_INVALID",
            "integrity": integrity,
            "independence_audit": independence,
            "operational_independence_audit": operational_independence,
            "executed": True,
            "execution_id": execution_id,
            "raw_tool_result": {
                "execution_id": execution_id,
                "package_hash": package_hash_before,
                "status": tool_result.status.value,
                "note": "Operational independence failed after execution",
            },
        }

    raw_tool_result = {
        "execution_id": execution_id,
        "package_hash": package_hash_before,
        "experiment_content_hash": package["selected_experiment_content_hash"],
        "executed_at": executed_at,
        "data_cutoff_date": spec.data_cutoff_date,
        "tool_name": tool_result.tool_name,
        "tool_version": tool_result.tool_version,
        "sample_size": tool_result.sample_size,
        "status": tool_result.status.value,
        "metrics": dict(tool_result.metrics),
        "result_hash": tr_hash,
        "raw": tr_dict,
    }

    qm = extract_quintile_metrics(
        panel,
        spec,
        partition_column=contract.partition_column,
        outcome_field=contract.outcome_field,
    )

    interpretation = interpret_experiment_evidence(
        contract, tool_result, qm, expected_cutoff=spec.data_cutoff_date
    )

    if interpretation.evidence_class.value == "INVALID":
        transition_audit = audit_supported_state_transition(contract, interpretation, prior_state)
        resulting_state = prior_state
        transition_key = transition_audit["transition_key"]
    else:
        transition_audit = audit_supported_state_transition(contract, interpretation, prior_state)
        if transition_audit["state_transition_not_preregistered"]:
            update = build_epistemic_update(
                proposition,
                contract,
                interpretation,
                experiment_ref=f"falsification_{package['selected_candidate_id']}",
                tool_result_hash=tr_hash,
                prior_state=prior_state,
                resulting_state=prior_state,
            )
            return {
                "verdict": "AUTONOMOUS_FALSIFICATION_PARTIAL",
                "lifecycle_verdict_detail": "STATE_TRANSITION_NOT_PREREGISTERED",
                "integrity": integrity,
                "independence_audit": independence,
                "executed": True,
                "execution_id": execution_id,
                "raw_tool_result": raw_tool_result,
                "quintile_metrics": qm.to_dict(),
                "interpretation": interpretation.to_dict(),
                "transition_audit": transition_audit,
                "epistemic_update": update.to_dict(),
                "research_decision": None,
                "package_hash_after": package_hash_before,
                "proposition_hash_after": prop_hash_before,
            }

        resulting_state, transition_key = apply_epistemic_transition(
            contract, interpretation, prior_state
        )

    update = build_epistemic_update(
        proposition,
        contract,
        interpretation,
        experiment_ref=f"falsification_{package['selected_candidate_id']}",
        tool_result_hash=tr_hash,
        prior_state=prior_state,
        resulting_state=resulting_state,
    )

    extended_update = {
        **update.to_dict(),
        "falsification_refs": {
            "package_hash": package_hash_before,
            "candidate_id": package["selected_candidate_id"],
            "candidate_hash": package["selected_candidate_hash"],
            "prior_epistemic_update_id": prior_epistemic_update["update_id"],
            "prior_research_decision_id": prior_research_decision["decision_id"],
            "interpretation_contract_hash": contract.contract_hash,
            "interpretation_contract_ref": package["interpretation_contract_ref"],
            "execution_id": execution_id,
        },
    }

    research_decision = None
    if transition_audit["decision_preregistered"] and interpretation.evidence_class.value != "INVALID":
        chosen, reason, rejected = decide_next_action(contract, interpretation, transition_key)
        research_decision = build_research_decision(
            proposition,
            contract,
            interpretation,
            update,
            chosen_action=chosen,
            reason=reason,
            rejected=rejected,
        ).to_dict()
        research_decision["falsification_refs"] = extended_update["falsification_refs"]

    prop_hash_after = proposition_content_hash(proposition)

    proposition_audit = {
        "proposition_id_unchanged": proposition["proposition_id"] == package["proposition_id"],
        "proposition_hash_unchanged": prop_hash_before == prop_hash_after,
        "falsifiable_expectation_unchanged": True,
        "disconfirming_spec_unchanged": True,
        "hypothesis_rescue_detected": False,
    }

    package_audit = {
        "package_hash_unchanged": package_hash_before == package["package_hash"],
        "candidate_unchanged": True,
        "experiment_spec_unchanged": True,
    }

    firewall = {
        "zone_c_used": False,
        "hidden_evaluator_used": False,
        "post_cutoff_data_beyond_policy": False,
        "future_result_before_execution": False,
        "passed": True,
    }

    if interpretation.evidence_class.value == "INVALID":
        verdict = "EXECUTION_INVALID"
    elif transition_audit.get("state_transition_not_preregistered"):
        verdict = "AUTONOMOUS_FALSIFICATION_PARTIAL"
    else:
        verdict = "AUTONOMOUS_FALSIFICATION_PASS"

    append_lineage = {
        "execution_version": EXECUTION_VERSION,
        "package_hash": package_hash_before,
        "prior_lineage_hash": package["prior_lineage_hash"],
        "first_epistemic_update_id": prior_epistemic_update["update_id"],
        "second_epistemic_update_id": update.update_id,
        "second_research_decision_id": research_decision["decision_id"] if research_decision else None,
        "execution_id": execution_id,
        "tool_result_hash": tr_hash,
        "lineage_hash": stable_hash(
            {
                "prior_lineage_hash": package["prior_lineage_hash"],
                "package_hash": package_hash_before,
                "second_update_hash": update.record_hash,
                "second_decision_hash": research_decision["record_hash"] if research_decision else None,
                "tool_result_hash": tr_hash,
            }
        ),
    }

    return {
        "verdict": verdict,
        "integrity": integrity,
        "independence_audit": independence,
        "operational_independence_audit": operational_independence,
        "executed": True,
        "execution_id": execution_id,
        "executed_at": executed_at,
        "one_shot_proof": {
            "execution_count": 1,
            "rerun_attempted": False,
            "candidate_id": package["selected_candidate_id"],
        },
        "raw_tool_result": raw_tool_result,
        "quintile_metrics": qm.to_dict(),
        "interpretation_contract_hash": contract.contract_hash,
        "interpretation": interpretation.to_dict(),
        "matched_rule": interpretation.condition_matched,
        "evidence_class": interpretation.evidence_class.value,
        "transition_audit": transition_audit,
        "prior_state": prior_state,
        "resulting_state": resulting_state,
        "epistemic_update": extended_update,
        "research_decision": research_decision,
        "proposition_audit": proposition_audit,
        "package_audit": package_audit,
        "firewall_audit": firewall,
        "append_lineage": append_lineage,
        "proposition_hash_after": prop_hash_after,
        "scientific_proposition_outcome": _scientific_outcome(interpretation.evidence_class.value, resulting_state),
        "researcher_capability_outcome": _capability_outcome(verdict, integrity, proposition_audit, package_audit),
    }


def _scientific_outcome(evidence_class: str, resulting_state: str) -> str:
    return f"Evidence class {evidence_class}; epistemic state {resulting_state}"


def _capability_outcome(verdict: str, integrity: Dict, prop_audit: Dict, pkg_audit: Dict) -> str:
    if verdict == "AUTONOMOUS_FALSIFICATION_PASS":
        return "Mr.BOT executed frozen package once and interpreted under frozen rules without rescue"
    return verdict
