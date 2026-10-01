"""
Phase 3I.12 — One-shot real proposition ledger adapter.

ONLY invoked after engine freeze. Diagnostic application — no trading semantics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash

REPO = Path(__file__).resolve().parents[3]
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I310 = REPO / "diagnostics/phase_3i10_falsification_execution/artifacts"


def load_real_proposition_ledger() -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """Build proposition spec + evidence specs from frozen 3I.7/3I.10 artifacts."""
    prop_wrap = json.loads((I37 / "02_frozen_proposition.json").read_text())
    prop = prop_wrap["full_record"]
    prop_hash = proposition_content_hash(prop)

    e1 = json.loads((I37 / "07_epistemic_update.json").read_text())
    e2 = json.loads((I310 / "05_epistemic_update.json").read_text())
    lineage = json.loads((I37 / "09_append_only_lineage.json").read_text())

    proposition_spec = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_hash,
        "proposition_type": "partition_contrast",
    }

    # Normalized evidence specs — references authoritative artifacts
    evidence_specs: List[Dict[str, Any]] = [
        {
            "evidence_id": e1["update_id"],
            "experiment_id": e1["experiment_ref"],
            "experiment_content_hash": lineage.get("experiment_spec_hash", "lifecycle_real_001"),
            "epistemic_update_ref": e1["update_id"],
            "evidence_class": e1["evidence_class"],
            "validity": "VALID",
            "feature_semantics": "continuous_partition",
            "population_semantics": "full_panel_all_dates",
            "outcome_semantics": "forward_return",
            "horizon": "T5",
            "cohort_episode_scope": "all_dates",
            "data_cutoff": lineage["experiment_spec"].get("data_cutoff_date", "2026-08-17"),
            "sample_size": int(e1["metrics_used"]["sample_size"]),
            "effect_direction": "positive",
            "effect_magnitude": "strong",
            "measurement_tool": "partition_group_compare",
            "uncertainty_axis_tested": "directional_effect_full_universe",
            "falsification_intent": False,
            "cohort_overlap_ratio": 0.0,
            "provenance_refs": {
                "epistemic_update": str(I37 / "07_epistemic_update.json"),
                "tool_result_hash": e1["tool_result_hash"],
            },
        },
        {
            "evidence_id": e2["update_id"],
            "experiment_id": e2["experiment_ref"],
            "experiment_content_hash": e2.get("falsification_refs", {}).get("package_hash", "falsification_holdout"),
            "epistemic_update_ref": e2["update_id"],
            "evidence_class": e2["evidence_class"],
            "validity": "VALID",
            "feature_semantics": "continuous_partition",
            "population_semantics": "holdout_exclude_focal_date",
            "outcome_semantics": "forward_return",
            "horizon": "T5",
            "cohort_episode_scope": "holdout_exclude_2026-08-02",
            "data_cutoff": "2026-08-17",
            "sample_size": int(e2["metrics_used"]["sample_size"]),
            "effect_direction": "positive",
            "effect_magnitude": "strong",
            "measurement_tool": "partition_group_compare",
            "uncertainty_axis_tested": "episode_robustness",
            "falsification_intent": True,
            "cohort_overlap_ratio": round(5964 / 6106, 4),
            "provenance_refs": {
                "epistemic_update": str(I310 / "05_epistemic_update.json"),
                "tool_result_hash": e2["tool_result_hash"],
                "falsification_package_hash": e2.get("falsification_refs", {}).get("package_hash"),
            },
        },
    ]

    prior_state = e2["prior_epistemic_state"]
    return proposition_spec, evidence_specs, prior_state


def apply_real_ledger_diagnostic() -> Dict[str, Any]:
    """One-shot diagnostic application to prop-efb650d9bd5c451f."""
    prop_spec, evidence, prior = load_real_proposition_ledger()
    synthesis, decision = synthesize_evidence(prop_spec, evidence, prior_epistemic_state=prior)
    return {
        "proposition_id": prop_spec["proposition_id"],
        "proposition_hash": prop_spec["proposition_hash"],
        "prior_epistemic_state": prior,
        "synthesis": synthesis.to_dict(),
        "research_priority_decision": decision.to_dict(),
        "relationship_e1_to_e2": synthesis.relationship_map.get(evidence[1]["evidence_id"]),
        "diagnostic_only": True,
        "no_trading_semantics": True,
        "no_new_experiment": True,
    }
