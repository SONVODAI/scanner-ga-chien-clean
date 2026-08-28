"""
BB-CapabilityGapAudit-01 Zone D — Examiner-side capability gap probes (diagnostic only).

These probes MUST NOT be imported by research runtime modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.toolbox_coverage_map import (
    KNOWN_UNREPRESENTED_CATEGORIES,
    families_for_null,
)

AUDIT_VERSION = "bb_capability_gap_audit_capability_probe_v1_3j14"


def probe_missing_capability(
    *,
    target_null_key: str,
    target_uncertainty: str,
    selected_action: str,
    exercised_pairs: List[tuple[str, str, str]],
    rejection_reasons: List[str],
    admissible_count: int,
) -> Dict[str, Any]:
    """
    Examiner asks: is there a scientifically legitimate next experiment that the
    current generator cannot represent, given frozen decision + history?

    Returns abstract capability category if gap found; otherwise none.
    Does NOT produce executable specs or teach answers to the Research Brain.
    """
    grammar = families_for_null(target_null_key)
    exercised_for_null = {(nk, cohort, tu) for nk, cohort, tu in exercised_pairs if nk == target_null_key}

    unexercised_grammar = [
        f
        for f in grammar
        if (target_null_key, f["family"], f["target_uncertainty"]) not in exercised_for_null
    ]

    gap_found = False
    abstract_gaps: List[Dict[str, str]] = []
    notes: List[str] = []

    if admissible_count > 0:
        return {
            "audit_version": AUDIT_VERSION,
            "gap_found": False,
            "abstract_gaps": [],
            "notes": ["admissible_candidates_exist_no_representational_gap"],
        }

    if not grammar:
        gap_found = True
        abstract_gaps.append(
            {
                "category": "missing_null_family_in_grammar",
                "description": f"No cohort strategies registered for null {target_null_key}",
            }
        )
    elif unexercised_grammar:
        notes.append("unexercised_grammar_families_remain_but_all_inadmissible")
        # If grammar families remain but were rejected, likely redundancy not representational gap
        if any("not_executable" in r for r in rejection_reasons):
            gap_found = True
            abstract_gaps.append(
                {
                    "category": "executability_not_representation",
                    "description": "Remaining grammar families exist but fail executability binding",
                }
            )
    elif grammar and not unexercised_grammar:
        notes.append("all_grammar_families_exercised_for_frozen_null")
        # Probe whether abstract categories beyond grammar could help
        if target_null_key == "episode_artifact" and selected_action == "SEEK_FALSIFICATION":
            notes.append(
                "episode_artifact_exhausted_holdout_strategies;"
                "orthogonal_measurement_or_independent_temporal_episode_might_exist_in_principle"
            )
            # Only flag as potential gap if data could support — examiner documents abstractly
            abstract_gaps.append(
                {
                    "category": "independent_temporal_episode",
                    "description": (
                        "Abstract: a holdout on an independent episode slice not equivalent to "
                        "counterexample_period_search or episode_holdout_excluding_motivating "
                        "is not representable in current NULL_COHORT_STRATEGIES"
                    ),
                }
            )
            gap_found = True

    if selected_action == "SEEK_REPLICATION" and any("fake_replication" in r for r in rejection_reasons):
        abstract_gaps.append(
            {
                "category": "genuinely_independent_replication",
                "description": "Independent replication requires sample independence unavailable in panel partition grammar",
            }
        )
        gap_found = True

    return {
        "audit_version": AUDIT_VERSION,
        "gap_found": gap_found,
        "abstract_gaps": abstract_gaps,
        "known_unrepresented_categories": list(KNOWN_UNREPRESENTED_CATEGORIES),
        "notes": notes,
        "target_null_key": target_null_key,
        "target_uncertainty": target_uncertainty,
        "selected_action": selected_action,
    }
