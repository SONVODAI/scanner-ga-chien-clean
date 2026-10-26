"""
BB-CapabilityGapAudit-01 Zone D — NO_FAITHFUL_EXPERIMENT silence classifier (examiner-only).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.toolbox_coverage_map import (
    build_toolbox_coverage_map,
    families_for_null,
)

AUDIT_VERSION = "bb_capability_gap_audit_silence_classifier_v1_3j14"

SILENCE_CLASSES = (
    "JUSTIFIED_SCIENTIFIC_SILENCE",
    "CAPABILITY_GAP",
    "EXECUTABILITY_GAP",
    "REDUNDANCY_STOP",
    "SEARCH_BURDEN_STOP",
    "POLICY_GAP",
    "UNKNOWN",
)


def _exercised_from_package_history(
    *,
    candidates_considered: List[Dict[str, Any]],
    prior_packages: List[Dict[str, Any]],
) -> List[tuple[str, str, str]]:
    pairs: List[tuple[str, str, str]] = []
    for pkg in prior_packages:
        obj = pkg.get("objective") or {}
        nk = str(obj.get("target_null_key", ""))
        tu = str(obj.get("target_uncertainty", ""))
        sel = pkg.get("selected_candidate_id")
        for c in pkg.get("deduplicated_candidates") or pkg.get("candidates_considered") or []:
            if c.get("candidate_id") == sel or c.get("primary_classification") == "ADMISSIBLE":
                cohort = (c.get("scientific_identity") or {}).get("cohort_strategy", "")
                if nk and cohort:
                    pairs.append((nk, cohort, tu or str(c.get("target_uncertainty", ""))))
    return pairs


def classify_silence(
    *,
    package: Dict[str, Any],
    prior_decision: Optional[Dict[str, Any]] = None,
    prior_packages: Optional[List[Dict[str, Any]]] = None,
    prior_history_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify NO_FAITHFUL_EXPERIMENT / silence at ordinal >= 3.
    Examiner-side only — uses frozen package + history artifacts.
    """
    disposition = package.get("disposition", "")
    if disposition not in ("NO_FAITHFUL_EXPERIMENT", "NO_FAITHFUL_SECOND_EXPERIMENT"):
        return {"classification": "UNKNOWN", "reason": f"not_silence_disposition:{disposition}"}

    objective = package.get("objective") or {}
    target_null = str(objective.get("target_null_key", ""))
    target_uncertainty = str(objective.get("target_uncertainty", ""))
    selected_action = str(objective.get("selected_action", ""))

    candidates = list(package.get("candidates_considered") or [])
    rejected = list(package.get("rejected") or [])
    deduped = list(package.get("deduplicated_candidates") or [])

    all_rejection_reasons: List[str] = []
    for c in candidates:
        all_rejection_reasons.extend(c.get("rejection_reasons") or [])

    exercised = _exercised_from_package_history(
        candidates_considered=candidates,
        prior_packages=list(prior_packages or []),
    )
    coverage = build_toolbox_coverage_map(exercised_pairs=exercised)
    grammar_families = families_for_null(target_null)
    grammar_keys = {(f["family"], f["target_uncertainty"]) for f in grammar_families}

    generated_keys = {
        (
            c.get("target_null_key"),
            (c.get("scientific_identity") or {}).get("cohort_strategy"),
        )
        for c in candidates
    }

    # Check if every grammar family for this null appears in rejections
    families_for_null_exhausted = True
    for fam in grammar_families:
        fam_rejections = [
            c
            for c in candidates
            if c.get("target_null_key") == target_null
            and (c.get("scientific_identity") or {}).get("cohort_strategy") == fam["family"]
        ]
        if not fam_rejections:
            families_for_null_exhausted = False
            break
        if any(c.get("primary_classification") == "ADMISSIBLE" for c in fam_rejections):
            families_for_null_exhausted = False
            break

    has_search_burden = any("search_burden" in r for r in all_rejection_reasons)
    has_redundancy = any(
        tok in r
        for r in all_rejection_reasons
        for tok in (
            "null_cycling",
            "scientific_question_redundant",
            "full_history_scientific_redundancy",
            "previously_rejected_core_hash",
            "representation_alias",
        )
    )
    has_executability = any("not_executable" in r for r in all_rejection_reasons)
    has_wrong_null = any("wrong_null" in r or "decision_substitution" in r for r in all_rejection_reasons)

    classification = "UNKNOWN"
    rationale: List[str] = []

    if not grammar_families and target_null:
        classification = "CAPABILITY_GAP"
        rationale.append(f"null_{target_null}_not_in_grammar")
    elif has_search_burden and not any(c.get("primary_classification") == "ADMISSIBLE" for c in candidates):
        classification = "SEARCH_BURDEN_STOP"
        rationale.append("search_burden_rejection_dominant")
    elif has_redundancy and families_for_null_exhausted:
        classification = "REDUNDANCY_STOP"
        rationale.append("all_faithful_families_redundant_or_exhausted")
    elif has_executability and not has_redundancy:
        classification = "EXECUTABILITY_GAP"
        rationale.append("faithful_designs_not_executable")
    elif families_for_null_exhausted and target_null:
        classification = "JUSTIFIED_SCIENTIFIC_SILENCE"
        rationale.append("grammar_families_for_frozen_null_all_rejected_or_exhausted")
    elif len(generated_keys) < len(grammar_keys) and not candidates:
        classification = "CAPABILITY_GAP"
        rationale.append("generator_did_not_enumerate_any_candidate")
    elif len(generated_keys) < len(grammar_keys):
        classification = "REDUNDANCY_STOP"
        rationale.append("partial_grammar_enumeration_all_inadmissible")
    else:
        classification = "JUSTIFIED_SCIENTIFIC_SILENCE"
        rationale.append("no_admissible_candidate_after_history_filter")

    return {
        "audit_version": AUDIT_VERSION,
        "classification": classification,
        "target_null_key": target_null,
        "target_uncertainty": target_uncertainty,
        "selected_action": selected_action,
        "experiment_ordinal": package.get("experiment_ordinal"),
        "generator_version": package.get("generator_version"),
        "candidate_count": len(candidates),
        "admissible_count": sum(1 for c in candidates if c.get("primary_classification") == "ADMISSIBLE"),
        "rejection_reasons_aggregate": sorted(set(all_rejection_reasons)),
        "grammar_families_for_null": grammar_families,
        "families_exhausted": families_for_null_exhausted,
        "toolbox_coverage": coverage,
        "rationale": rationale,
        "rejected_selector": rejected,
    }
