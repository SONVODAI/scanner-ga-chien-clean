"""
Phase 3I.12/3I.13 — Real proposition ledger diagnostic (diagnostic-only convenience).

Uses generic EvidenceLedgerBuilder — no proposition-specific normalization in production path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from modules.edge_research.opr_bridge.evidence_ledger_builder import (
    build_ledger_specs_from_events,
    proposition_spec_from_record,
)
from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

REPO = Path(__file__).resolve().parents[3]
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I310 = REPO / "diagnostics/phase_3i10_falsification_execution/artifacts"
I39 = REPO / "diagnostics/phase_3i9_falsification_selection/artifacts"


def load_real_lifecycle_events() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load frozen 3I.7/3I.10 lifecycle events for diagnostic replay."""
    prop_wrap = json.loads((I37 / "02_frozen_proposition.json").read_text())
    prop = prop_wrap["full_record"]
    lineage = json.loads((I37 / "09_append_only_lineage.json").read_text())
    e1_update = json.loads((I37 / "07_epistemic_update.json").read_text())
    e2_update = json.loads((I310 / "05_epistemic_update.json").read_text())
    package = json.loads((I39 / "09_one_shot_package.json").read_text())

    event1 = {
        "epistemic_update": e1_update,
        "experiment_spec": lineage["experiment_spec"],
        "experiment_ref": e1_update["experiment_ref"],
        "tool_result_hash": e1_update["tool_result_hash"],
        "interpretation": lineage.get("interpretation"),
    }
    event2 = {
        "epistemic_update": e2_update,
        "experiment_spec": package["selected_experiment_spec"],
        "experiment_ref": e2_update["experiment_ref"],
        "tool_result_hash": e2_update["tool_result_hash"],
        "lineage_metadata": e2_update.get("falsification_refs"),
    }
    return prop, [event1, event2]


def apply_real_ledger_diagnostic() -> Dict[str, Any]:
    """One-shot diagnostic application via generic ledger builder."""
    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, decision = synthesize_evidence(prop_spec, specs, prior_epistemic_state=prior)
    return {
        "proposition_id": prop_spec["proposition_id"],
        "proposition_hash": prop_spec["proposition_hash"],
        "prior_epistemic_state": prior,
        "synthesis": synthesis.to_dict(),
        "research_priority_decision": decision.to_dict(),
        "relationship_e1_to_e2": synthesis.relationship_map.get(events[1]["epistemic_update"]["update_id"]),
        "diagnostic_only": True,
        "no_trading_semantics": True,
        "no_new_experiment": True,
        "builder": "evidence_ledger_builder_v1_3i13",
    }
