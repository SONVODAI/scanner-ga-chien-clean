"""
BB-CapabilityGapAudit-01 Zone D — Longer-journey safety audit (examiner-only).
"""

from __future__ import annotations

from typing import Any, Dict, List

AUDIT_VERSION = "bb_capability_gap_audit_longer_journey_safety_v1_3j14"


def audit_journey_safety(journey: Dict[str, Any], *, seed: int, blind_class: str) -> Dict[str, Any]:
    """Scan frozen journey for anti-scientific patterns."""
    rows = journey.get("journey_rows") or []
    findings: Dict[str, List[str]] = {
        "confirmation_loops": [],
        "horizon_shopping": [],
        "slice_shopping": [],
        "null_cycling": [],
        "evidence_recycling": [],
        "dependence_undercounting": [],
        "unjustified_confidence_escalation": [],
        "ignored_contradiction": [],
        "premature_stop": [],
        "unnecessary_continuation": [],
    }

    nulls_tested: List[str] = []
    epistemic_trail: List[str] = []
    actions: List[str] = []

    for row in rows:
        ep = row.get("epistemic_state_leaving")
        if ep:
            epistemic_trail.append(str(ep))
        act = row.get("chosen_action")
        if act:
            actions.append(str(act))
        tn = row.get("targeted_null")
        if tn:
            nulls_tested.append(str(tn))

    # Confirmation loop: repeated SEEK_REPLICATION without independence
    repl_count = sum(1 for a in actions if a == "SEEK_REPLICATION")
    if repl_count >= 2:
        findings["confirmation_loops"].append(f"replication_action_count={repl_count}")

    # Unjustified confidence escalation
    if epistemic_trail.count("SUPPORTED") >= 2 and blind_class in ("BLIND-B", "BLIND-D"):
        findings["unjustified_confidence_escalation"].append(
            f"repeated_SUPPORTED_on_{blind_class}"
        )

    # Null cycling
    if len(nulls_tested) != len(set(nulls_tested)):
        findings["null_cycling"].append(f"repeated_nulls:{nulls_tested}")

    # Premature vs unnecessary stop
    outcome = journey.get("lifecycle_outcome")
    stop = journey.get("final_stop_reason")
    exp = journey.get("experiments_completed", 0)
    budget = (journey.get("budget_initial") or {}).get("max_experiment_iterations", 2)

    if outcome == "SCIENTIFIC_STOP" and stop in ("STOP_LOW_INCREMENTAL",) and exp < budget:
        findings["premature_stop"].append(f"scientific_stop_at_exp_{exp}_budget_{budget}")

    if outcome == "FAILED_CLOSED" and "experiment_3_execution_failed" in str(journey.get("termination_reason", "")):
        findings["unnecessary_continuation"].append(
            "attempted_execution_on_NO_FAITHFUL_ordinal_3_package"
        )

    if outcome == "BUDGET_EXHAUSTED" and journey.get("final_decision_kind") == "ACTION":
        findings["unnecessary_continuation"].append("budget_exhausted_with_pending_ACTION")

    total_occurrences = sum(len(v) for v in findings.values())
    return {
        "audit_version": AUDIT_VERSION,
        "seed": seed,
        "blind_class": blind_class,
        "lifecycle_outcome": outcome,
        "experiments_completed": exp,
        "findings": findings,
        "occurrence_counts": {k: len(v) for k, v in findings.items()},
        "total_occurrences": total_occurrences,
    }


def aggregate_journey_safety(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {k: 0 for k in reports[0]["occurrence_counts"]} if reports else {}
    for r in reports:
        for k, v in r.get("occurrence_counts", {}).items():
            totals[k] = totals.get(k, 0) + v
    return {
        "audit_version": AUDIT_VERSION,
        "case_count": len(reports),
        "aggregate_occurrence_counts": totals,
        "cases_with_any_finding": sum(1 for r in reports if r.get("total_occurrences", 0) > 0),
        "per_case": reports,
    }
