"""
BB-CapabilityGapAudit-01 Zone D — Generic toolbox coverage map (examiner-only).

Maps ResearchDecision uncertainty classes to representable/executable families.
Does NOT encode blind-case answers.
"""

from __future__ import annotations

from typing import Any, Dict, List

AUDIT_VERSION = "bb_capability_gap_audit_toolbox_map_v1_3j14"

# Generic grammar families from frozen NULL_COHORT_STRATEGIES (read-only reference).
UNCERTAINTY_TO_FAMILIES: Dict[str, List[Dict[str, Any]]] = {
    "directional_reversal": [
        {
            "family": "full_panel_contrast",
            "target_uncertainty": "directional_effect_full_universe",
            "population": "all",
            "tool_binding": "quintile_spread_compare",
            "representable": True,
            "executable": True,
        },
    ],
    "episode_artifact": [
        {
            "family": "counterexample_period_search",
            "target_uncertainty": "episode_robustness",
            "population": "holdout",
            "tool_binding": "quintile_spread_compare",
            "representable": True,
            "executable": True,
        },
        {
            "family": "episode_holdout_excluding_motivating",
            "target_uncertainty": "episode_robustness",
            "population": "holdout",
            "tool_binding": "quintile_spread_compare",
            "representable": True,
            "executable": True,
        },
    ],
    "population_concentration": [
        {
            "family": "full_panel_contrast",
            "target_uncertainty": "population_generalization",
            "population": "all",
            "tool_binding": "quintile_spread_compare",
            "representable": True,
            "executable": True,
        },
    ],
    "context_instability": [
        {
            "family": "regime_partition_contrast",
            "target_uncertainty": "context_stability",
            "population": "all",
            "tool_binding": "quintile_spread_compare",
            "representable": True,
            "executable": True,
        },
    ],
}

# Abstract capability categories NOT currently in production grammar.
KNOWN_UNREPRESENTED_CATEGORIES: List[Dict[str, str]] = [
    {
        "category": "independent_temporal_episode",
        "description": "Holdout on a genuinely new episode slice not covered by existing holdout strategies",
    },
    {
        "category": "interaction_test",
        "description": "Conditional effect test across feature × context interaction",
    },
    {
        "category": "alternative_outcome_semantics",
        "description": "Same scientific question with orthogonal outcome field / horizon",
    },
    {
        "category": "negative_control",
        "description": "Explicit negative-control population or sham contrast",
    },
    {
        "category": "orthogonal_measurement",
        "description": "Different tool/representation answering same null when quintile path exhausted",
    },
]


def build_toolbox_coverage_map(
    *,
    exercised_pairs: List[tuple[str, str, str]] | None = None,
) -> Dict[str, Any]:
    """
    Generic map: uncertainty/null → families → representable/executable/exercised.
    exercised_pairs: list of (null_key, cohort_strategy, target_uncertainty) from history.
    """
    exercised = set(exercised_pairs or [])
    rows: List[Dict[str, Any]] = []
    for null_key, families in UNCERTAINTY_TO_FAMILIES.items():
        for fam in families:
            key = (null_key, fam["family"], fam["target_uncertainty"])
            rows.append(
                {
                    "null_key": null_key,
                    "cohort_strategy": fam["family"],
                    "target_uncertainty": fam["target_uncertainty"],
                    "population": fam["population"],
                    "tool_binding": fam["tool_binding"],
                    "representable": fam["representable"],
                    "executable": fam["executable"],
                    "previously_exercised": key in exercised,
                    "missing_abstraction": None,
                }
            )
    return {
        "audit_version": AUDIT_VERSION,
        "rows": rows,
        "unrepresented_categories": list(KNOWN_UNREPRESENTED_CATEGORIES),
        "null_keys_in_grammar": list(UNCERTAINTY_TO_FAMILIES.keys()),
    }


def families_for_null(null_key: str) -> List[Dict[str, Any]]:
    return list(UNCERTAINTY_TO_FAMILIES.get(null_key, []))
