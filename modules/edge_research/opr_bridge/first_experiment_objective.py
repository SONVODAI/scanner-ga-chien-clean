"""
Phase 3J.2 — Derive InitialExperimentObjectiveRecord from proposition commitments only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    collect_motivating_episode_dates,
    derive_proposition_vulnerabilities,
)
from modules.edge_research.opr_bridge.falsification_records import VulnerabilityKind
from modules.edge_research.opr_bridge.first_experiment_records import (
    InitialExperimentObjectiveRecord,
    build_objective_record,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash

_FORBIDDEN_RESCUE = (
    "population_narrowing",
    "horizon_mutation",
    "outcome_field_mutation",
    "feature_mutation",
    "rescue_by_regime_cherry_pick",
)


def derive_initial_experiment_objectives(prop: Dict[str, Any]) -> List[InitialExperimentObjectiveRecord]:
    """
    Derive first-experiment objectives from immutable proposition commitments — not tool names.
    """
    prop_hash = proposition_content_hash(prop)
    prop_id = prop["proposition_id"]
    vulnerabilities = derive_proposition_vulnerabilities(prop)
    null_text = prop.get("null_competing_explanation", "")
    dis = prop.get("disconfirming_observation_spec", {})
    canonical = prop.get("canonical_proposition_core", prop.get("scientific_question", ""))
    falsifiable = prop.get("falsifiable_expectation", "")
    motivating = collect_motivating_episode_dates(prop)

    objectives: List[InitialExperimentObjectiveRecord] = []

    dir_vuln = next((v for v in vulnerabilities if v.kind == VulnerabilityKind.DIRECTIONAL_REVERSAL), vulnerabilities[0])
    objectives.append(
        build_objective_record(
            proposition_id=prop_id,
            proposition_hash=prop_hash,
            target_uncertainty="directional_effect_full_universe",
            scientific_vulnerability=dir_vuln.kind.value,
            why_first=(
                "Central falsifiable commitment must be tested before subsidiary robustness: "
                f"{dis.get('description', dir_vuln.description)}"
            ),
            outcome_branches={
                "more_credible": "Directional contrast replicates on independent cohort without rescue",
                "less_credible": dis.get("operational_test", "Directional reversal or spread collapse"),
                "unresolved": "Cohort insufficient or ambiguous spread — no belief transition",
            },
            forbidden_rescue_mutations=_FORBIDDEN_RESCUE,
            provenance={
                "falsifiable_expectation": falsifiable[:120] if falsifiable else "",
                "disconfirming_observation_spec": dis.get("description", ""),
                "canonical_proposition_core": str(canonical)[:120],
            },
            directness_rank=dir_vuln.directness_rank,
        )
    )

    ep_vuln = next((v for v in vulnerabilities if v.kind == VulnerabilityKind.EPISODE_INSTABILITY), None)
    if ep_vuln and motivating:
        objectives.append(
            build_objective_record(
                proposition_id=prop_id,
                proposition_hash=prop_hash,
                target_uncertainty="episode_robustness",
                scientific_vulnerability=ep_vuln.kind.value,
                why_first=(
                    "Null competing explanation suggests episode artifact; "
                    "first high-information test should use evidence independent of motivating dates"
                ),
                outcome_branches={
                    "more_credible": "Effect holds on episodes excluding birth/motivating dates",
                    "less_credible": "Effect absent or reversed on independent episodes — supports artifact hypothesis",
                    "unresolved": "Holdout cohort too small or non-informative",
                },
                forbidden_rescue_mutations=_FORBIDDEN_RESCUE,
                provenance={
                    "null_competing_explanation": null_text[:120] if null_text else "",
                    "motivating_episode_dates": ",".join(motivating),
                    "disconfirming_observation_spec": dis.get("alternative_interpretation", ""),
                },
                directness_rank=ep_vuln.directness_rank,
            )
        )

    ptype = prop.get("proposition_type", "partition_contrast")
    if ptype == "context_modulation":
        objectives.append(
            build_objective_record(
                proposition_id=prop_id,
                proposition_hash=prop_hash,
                target_uncertainty="context_modulation_direction",
                scientific_vulnerability="context_instability",
                why_first="Context-gated proposition requires modulation contrast across independent contexts",
                outcome_branches={
                    "more_credible": "Modulation direction consistent across contexts",
                    "less_credible": "Modulation absent or reversed in held-out context",
                    "unresolved": "Context strata insufficient",
                },
                forbidden_rescue_mutations=_FORBIDDEN_RESCUE,
                provenance={
                    "canonical_proposition_core": str(canonical)[:120],
                    "structural_context": str(
                        prop.get("observation_provenance", {}).get("structural_context", {})
                    )[:120],
                },
                directness_rank=2,
            )
        )

    rel = prop.get("explanatory_relation", {})
    if rel.get("relation_kind") == "surface_skew" or "skew" in str(canonical).lower():
        objectives.append(
            build_objective_record(
                proposition_id=prop_id,
                proposition_hash=prop_hash,
                target_uncertainty="surface_skew_direction",
                scientific_vulnerability="directional_reversal",
                why_first="Surface-skew commitment requires independent skew-direction test",
                outcome_branches={
                    "more_credible": "Skew direction replicates on independent sample",
                    "less_credible": "Skew sign reversal or collapse",
                    "unresolved": "Skew measurement non-informative",
                },
                forbidden_rescue_mutations=_FORBIDDEN_RESCUE,
                provenance={
                    "falsifiable_expectation": falsifiable[:120] if falsifiable else "",
                    "explanatory_relation": str(rel)[:120],
                },
                directness_rank=0,
            )
        )

    return objectives
