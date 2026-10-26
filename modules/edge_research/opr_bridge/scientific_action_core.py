"""
Phase 3I.16 — ScientificActionCore identity and ledger-implied cores.
"""

from __future__ import annotations

from typing import Dict, List, Set, TYPE_CHECKING

from modules.edge_research.opr_bridge.scientific_action_records import ScientificActionCore

if TYPE_CHECKING:
    from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext


# Map ledger population/cohort semantics to cohort strategies for redundancy inference.
_LEDGER_COHORT_TO_STRATEGY = {
    "full_universe": "full_panel_contrast",
    "holdout_exclude_dates": "episode_holdout_excluding_motivating",
    "filtered_date_cohort": "episode_holdout_excluding_motivating",
    "regime_separated": "regime_separated_contrast",
    "population_subgroup": "population_subgroup_contrast",
    "independent_holdout": "episode_holdout_excluding_motivating",
    "counterexample_search": "counterexample_period_search",
}


def infer_executed_core_hashes(ctx: "ActionGenerationContext") -> Set[str]:
    """Infer ScientificActionCore hashes from prior evidence ledger."""
    hashes: Set[str] = set()
    commitment = _commitment_label(ctx)
    contrast = _contrast_relation(ctx)

    for entry in ctx.ledger_entries:
        if entry.validity != "VALID":
            continue
        if entry.evidence_class in ("INVALID", "NON_INFORMATIVE"):
            continue
        axis = entry.uncertainty_axis_tested or "directional_effect_full_universe"
        cohort = _LEDGER_COHORT_TO_STRATEGY.get(entry.population_semantics, entry.population_semantics)
        if "holdout" in entry.cohort_episode_scope.lower() or "holdout" in entry.population_semantics.lower():
            cohort = "episode_holdout_excluding_motivating"
        gain = "falsify" if entry.falsification_intent else "inform"
        core = ScientificActionCore(
            objective_target_uncertainty=axis,
            proposition_commitment_challenged=commitment,
            cohort_strategy=cohort,
            contrast_relation=contrast,
            expected_epistemic_consequence_type=f"{gain}_{axis}",
            information_gain_type=gain,
        )
        hashes.add(core.core_hash)
    return hashes


def deduplicate_candidates(candidates: List) -> List:
    """Keep best executability per ScientificActionCore hash."""
    from modules.edge_research.opr_bridge.scientific_action_records import ExecutabilityClass

    exec_rank = {
        ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value: 0,
        ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value: 1,
        ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value: 2,
        ExecutabilityClass.REPRESENTATION_ONLY.value: 3,
        ExecutabilityClass.RESCUE_RISK.value: 4,
        ExecutabilityClass.INVALID.value: 5,
    }
    best: Dict[str, object] = {}
    for c in candidates:
        key = c.scientific_action_core_hash
        if key not in best or exec_rank.get(c.executability_classification, 9) < exec_rank.get(
            best[key].executability_classification, 9
        ):
            best[key] = c
    return list(best.values())


def _commitment_label(ctx: "ActionGenerationContext") -> str:
    ptype = ctx.proposition_type
    if ptype == "context_modulation":
        feat = ctx.proposition_record.get("feature", "context_gate")
        return f"context_modulation_{feat}"
    feat = ctx.proposition_record.get("feature") or ctx.proposition_record.get("explanatory_relation", {}).get(
        "feature_or_contrast", "partition_feature"
    )
    return f"partition_contrast_{feat}"


def _contrast_relation(ctx: "ActionGenerationContext") -> str:
    if ctx.proposition_type == "context_modulation":
        return "context_modulation_contrast"
    return "partition_quintile_contrast"
