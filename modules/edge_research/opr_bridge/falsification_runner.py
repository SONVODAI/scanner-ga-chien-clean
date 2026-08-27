"""
Phase 3I.9 — Falsification candidate generation and selection runner.

Does NOT execute selected ExperimentSpec or read ToolResult.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    GENERATOR_VERSION,
    generate_falsification_candidates,
    generator_content_hash,
)
from modules.edge_research.opr_bridge.falsification_records import SelectionOutcome
from modules.edge_research.opr_bridge.falsification_selector import (
    select_falsification_candidate,
    selector_content_hash,
)
from modules.edge_research.opr_bridge.interpretation_contract import (
    interpretation_contract_from_dict,
    proposition_content_hash,
)
from modules.edge_research.opr_bridge.lifecycle_records import stable_hash, utc_now_iso
from modules.edge_research.research_state import compute_experiment_content_hash, ExperimentSpec


def load_frozen_3i7_lineage(artifacts_dir: Path) -> Dict[str, Any]:
    """Load preserved 3I.7 artifacts without regeneration."""
    def _load(name: str) -> Any:
        return json.loads((artifacts_dir / name).read_text(encoding="utf-8"))

    prop_wrap = _load("02_frozen_proposition.json")
    return {
        "proposition": prop_wrap["full_record"],
        "proposition_wrap": prop_wrap,
        "interpretation_contract": _load("03_interpretation_contract.json"),
        "tool_result": _load("04_tool_result.json"),
        "epistemic_update": _load("07_epistemic_update.json"),
        "research_decision": _load("08_research_decision.json"),
        "lineage": _load("09_append_only_lineage.json"),
    }


def verify_3i7_lineage_integrity(frozen: Dict[str, Any]) -> Dict[str, Any]:
    prop = frozen["proposition"]
    prop_wrap = frozen["proposition_wrap"]
    recomputed = proposition_content_hash(prop)
    decision = frozen["research_decision"]
    update = frozen["epistemic_update"]
    return {
        "proposition_hash_match": prop_wrap["proposition_hash"] == recomputed,
        "proposition_hash": prop_wrap["proposition_hash"],
        "decision_action": decision["chosen_next_action"],
        "resulting_state": update["resulting_epistemic_state"],
        "decision_cites_update": decision["epistemic_update_id"] == update["update_id"],
        "lineage_hash": frozen["lineage"].get("lineage_hash"),
        "passed": (
            prop_wrap["proposition_hash"] == recomputed
            and decision["chosen_next_action"] == "SEEK_FALSIFICATION"
            and update["resulting_epistemic_state"] == "SUPPORTED"
        ),
    }


def run_falsification_selection(
    frozen: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    include_audit_sketches: bool = False,
) -> Dict[str, Any]:
    """
    Generate candidates and select once — no experiment execution.
    """
    prop = frozen["proposition"]
    contract = interpretation_contract_from_dict(frozen["interpretation_contract"])
    lineage = frozen["lineage"]
    prior_spec_dict = lineage["experiment_spec"]
    prior_hash = compute_experiment_content_hash(
        ExperimentSpec(
            tool_name=prior_spec_dict["tool_name"],
            tool_version=prior_spec_dict.get("tool_version", "v1"),
            inputs=dict(prior_spec_dict["inputs"]),
            research_scope=dict(prior_spec_dict["research_scope"]),
            data_cutoff_date=prior_spec_dict["data_cutoff_date"],
        )
    )

    candidates = generate_falsification_candidates(
        prop,
        interpretation_contract=contract,
        epistemic_update=frozen["epistemic_update"],
        research_decision=frozen["research_decision"],
        prior_experiment_spec=prior_spec_dict,
        prior_experiment_content_hash=prior_hash,
        lineage_hash=lineage["lineage_hash"],
        prior_tool_result_hash=frozen["epistemic_update"]["tool_result_hash"],
        panel=panel,
        include_audit_sketches=include_audit_sketches,
    )

    selection = select_falsification_candidate(candidates)
    cand_set_hash = generator_content_hash(candidates)
    created = utc_now_iso()

    package = None
    if selection.outcome == SelectionOutcome.SELECTED and selection.selected:
        sel = selection.selected
        package_body = {
            "package_version": "falsification_one_shot_v1_3i9",
            "proposition_id": prop["proposition_id"],
            "proposition_hash": proposition_content_hash(prop),
            "prior_lineage_hash": lineage["lineage_hash"],
            "interpretation_contract_hash": contract.contract_hash,
            "interpretation_contract_ref": "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json",
            "generator_version": GENERATOR_VERSION,
            "generator_hash": stable_hash({"version": GENERATOR_VERSION}),
            "candidate_set_hash": cand_set_hash,
            "selector_version": selector_content_hash(),
            "selected_candidate_id": sel.candidate_id,
            "selected_candidate_hash": sel.record_hash,
            "selected_experiment_spec": sel.proposed_experiment_spec,
            "selected_experiment_content_hash": sel.experiment_content_hash,
            "cutoff_policy": sel.leakage_cutoff_requirements,
            "interpretation_requirements": "Reuse frozen 3I.7 InterpretationContract quintile rules",
            "anti_rescue_constraints": sel.rescue_risk_status,
            "execution_status": "NOT_EXECUTED",
            "created_at": created,
        }
        package = {**package_body, "package_hash": stable_hash(package_body)}

    return {
        "lineage_integrity": verify_3i7_lineage_integrity(frozen),
        "interpretation_contract_hash": contract.contract_hash,
        "candidates": [c.to_dict() for c in candidates],
        "candidate_set_hash": cand_set_hash,
        "selection": selection.to_dict(),
        "selected_candidate": selection.selected.to_dict() if selection.selected else None,
        "one_shot_package": package,
        "second_experiment_executed": False,
        "created_at": created,
    }


def build_abstract_proposition_fixture(
    *,
    proposition_id: str = "prop-abstract-test",
    dispersion_feature: str = "vol_dispersion",
    outcome_field: str = "t3_return",
    focal_date: str = "2026-03-15",
    cutoff: str = "2026-04-01",
) -> Dict[str, Any]:
    """Abstract proposition for generalization control — not rs_spread/t5_return."""
    grammar = "research_grammar_v1"
    core = {
        "version": "research_proposition_core_v1",
        "population_spec": {"kind": "all", "grammar_version": grammar},
        "outcome_spec": {
            "kind": "compare",
            "field": outcome_field,
            "operator": ">",
            "value": 0.0,
            "grammar_version": grammar,
        },
        "observation_horizon": 0,
        "uncertainty_family": "CROSS_SECTIONAL_DISPERSION",
        "conditioning_context": {
            "dispersion_feature": dispersion_feature,
            "focal_date": focal_date,
            "contrast_direction": "positive",
        },
    }
    return {
        "proposition_id": proposition_id,
        "record_version": "proposition_record_v1",
        "canonical_proposition_core": core,
        "scientific_question": (
            f"Does cross-sectional {dispersion_feature} tier predict differential forward "
            f"{outcome_field} across the market cross-section?"
        ),
        "observation_provenance": {
            "evidence_anchor": {"focal_date": focal_date, "data_cutoff_date": cutoff},
            "empirical_artifacts": [{"name": "spread", "value": 2.0, "date": focal_date}],
        },
        "explanatory_relation": {
            "feature_or_contrast": dispersion_feature,
            "contrast_direction": "positive",
        },
        "outcome": {
            "kind": "compare",
            "field": outcome_field,
            "operator": ">",
            "value": 0.0,
            "grammar_version": grammar,
        },
        "population_context": {"kind": "all", "grammar_version": grammar},
        "observation_horizon": 0,
        "execution_requirements": {"min_sample": 30, "partition_column": dispersion_feature},
        "falsifiable_expectation": f"High {dispersion_feature} quintile exceeds low on {outcome_field}",
        "null_competing_explanation": (
            f"Small-sample artifact or market-wide level effects on {focal_date}"
        ),
        "disconfirming_observation_spec": {
            "description": f"If high {dispersion_feature} does not outperform low on {outcome_field}",
            "operational_test": f"partition_group_compare median_spread <= 0",
            "threshold": "median_spread <= 0 or rank reversal",
            "alternative_interpretation": "Artifact",
        },
        "epistemic_status": "SUPPORTED",
    }
