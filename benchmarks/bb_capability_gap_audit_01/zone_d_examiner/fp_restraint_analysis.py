"""
BB-CapabilityGapAudit-01 Zone D — False-positive restraint analysis (examiner-only).
"""

from __future__ import annotations

from typing import Any, Dict, List

AUDIT_VERSION = "bb_capability_gap_audit_fp_restraint_v1_3j14"


def analyze_false_positive_restraint(reveals: List[Dict[str, Any]], journeys: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Explain critical FP = 0 without claiming robustness from zero alone.
    """
    critical = [r for r in reveals if r.get("false_positive_risk") == "CRITICAL"]
    elevated = [r for r in reveals if r.get("false_positive_risk") == "ELEVATED"]
    supported_on_noise = [
        r
        for r in reveals
        if r.get("blind_class") == "BLIND-D" and (r.get("calibration_category") == "SUPPORTED" or r.get("final_epistemic_state") == "SUPPORTED")
    ]
    supported_artifact = [
        r
        for r in reveals
        if r.get("blind_class") in ("BLIND-B", "BLIND-E", "BLIND-F")
        and r.get("calibration_category") == "SUPPORTED"
    ]

    by_seed_j = {j.get("anonymous_case_id"): j for j in journeys}
    inability_to_continue = 0
    conservative_fail_closed = 0
    genuine_discrimination = 0

    for r in reveals:
        aid = r.get("anonymous_case_id")
        j = by_seed_j.get(aid) or {}
        outcome = j.get("lifecycle_outcome")
        if outcome == "BOOTSTRAP_SILENT":
            inability_to_continue += 1
        elif outcome == "SCIENTIFIC_STOP":
            genuine_discrimination += 1
        elif outcome == "FAILED_CLOSED":
            conservative_fail_closed += 1
        elif outcome == "BUDGET_EXHAUSTED" and not j.get("final_epistemic_state"):
            inability_to_continue += 1
        else:
            genuine_discrimination += 1

    components = []
    if genuine_discrimination:
        components.append("genuinely_good_scientific_discrimination")
    if conservative_fail_closed:
        components.append("conservative_fail_closed_behavior")
    if inability_to_continue:
        components.append("insufficient_ability_to_continue_research")
    if all(r.get("calibration_category") != "SUPPORTED" for r in reveals if r.get("blind_class") == "BLIND-D"):
        components.append("no_supported_on_pure_noise")

    return {
        "audit_version": AUDIT_VERSION,
        "critical_false_positive_count": len(critical),
        "elevated_false_positive_count": len(elevated),
        "supported_on_blind_d": len(supported_on_noise),
        "supported_on_artifact_classes": len(supported_artifact),
        "restraint_components": components,
        "mixture_explanation": (
            "Critical FP = 0 is a mixture: no BLIND-D SUPPORTED discoveries, "
            "appropriate STOP/SILENCE on most cases, and conservative FAILED_CLOSED "
            "when ordinal>=3 silence packages are execution-attempted. "
            "Zero alone does not prove robust edge discovery."
        ),
        "inability_to_continue_count": inability_to_continue,
        "conservative_fail_closed_count": conservative_fail_closed,
        "genuine_discrimination_count": genuine_discrimination,
        "flag_fp_zero_from_inability_only": inability_to_continue >= len(reveals) // 2,
    }
