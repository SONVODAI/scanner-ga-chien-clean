#!/usr/bin/env python3
"""
Phase 3I.5 — Counterfactual replay, blind evaluation, and capability gate.

Pre-registration: artifacts/01_prioritization_preregistration.json (written before eval).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
CUTOFF = "2026-08-17"

import sys

sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION
from modules.edge_research.opr_bridge.pipeline import run_opr_pipeline
from modules.edge_research.opr_bridge.prioritized_pipeline import run_opr_pipeline_prioritized
from modules.edge_research.opr_bridge.prioritization import PRIORITIZER_VERSION, SELECTED_SIGNALS, REJECTED_SIGNALS


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def preregistration() -> Dict[str, Any]:
    return {
        "phase": "3I.5",
        "prioritizer_version": PRIORITIZER_VERSION,
        "generator_version_frozen": OPR_GENERATOR_VERSION,
        "ranking_mechanism": "LEXICOGRAPHIC",
        "rank_key_order": [
            "contradiction_presence",
            "independent_repeated_evidence",
            "surprise_magnitude_max_quintile_spread",
            "contrast_magnitude_max_abs_empirical_delta",
            "historical_rarity_max_abs_zscore",
        ],
        "selected_signals": list(SELECTED_SIGNALS),
        "rejected_signals": list(REJECTED_SIGNALS),
        "gates": ["evidence_quality_gate", "surprise_gate", "executability_gate"],
        "budget_semantics": {
            "max_unique_propositions": 3,
            "budget_unit": "unique_scientific_proposition",
            "observation_processing": "all_eligible_dates",
        },
        "forbidden_signals": [
            "hidden_phenomenon_similarity",
            "chronological_order",
            "profitability",
        ],
        "evaluation_metrics": [
            "unique_scientific_propositions_emitted",
            "duplicate_evidence_compression",
            "representative_evidence_quality",
            "research_worthiness_rate",
            "scientific_diversity",
            "grounding",
            "falsifiability",
            "executability",
            "silence_behavior",
            "budget_efficiency",
        ],
        "hidden_convergence_axis": "POST_HOC_ONLY",
    }


def counterfactual_replay(panel: pd.DataFrame) -> Dict[str, Any]:
    old = run_opr_pipeline(panel, data_cutoff_date=CUTOFF, max_propositions=3, run_leakage=False)
    new = run_opr_pipeline_prioritized(
        panel, data_cutoff_date=CUTOFF, max_unique_propositions=3, run_leakage=False
    )

    old_dates = [
        r.observation_provenance.evidence_anchor["focal_date"] for r in old.records
    ]
    new_rep = (
        new.evidence_lineages[0].representative_focal_date if new.evidence_lineages else None
    )
    old_spreads = []
    for r in old.records:
        for a in r.observation_provenance.empirical_artifacts:
            if a.get("name") == "quintile_return_spread":
                old_spreads.append(a.get("value"))

    new_spread = None
    if new.records:
        for a in new.records[0].observation_provenance.empirical_artifacts:
            if a.get("name") == "quintile_return_spread":
                new_spread = a.get("value")

    return {
        "old_pipeline": {
            "selection_mode": "CHRONOLOGICAL_FIRST_COME",
            "propositions_emitted": len(old.records),
            "unique_scientific_questions": len({r.scientific_question for r in old.records}),
            "emitted_focal_dates": old_dates,
            "quintile_spreads": old_spreads,
        },
        "new_pipeline": {
            "selection_mode": "PRIORITIZED",
            "propositions_emitted": len(new.records),
            "unique_scientific_questions": len({r.scientific_question for r in new.records}),
            "observations_considered": new.observation_events_considered,
            "surprising_observations": new.surprising_observation_events,
            "unique_proposition_groups": new.unique_proposition_groups,
            "representative_focal_date": new_rep,
            "representative_quintile_spread": new_spread,
            "aggregated_evidence_count": (
                len(new.evidence_lineages[0].aggregated_evidence_events)
                if new.evidence_lineages
                else 0
            ),
        },
        "improvements": {
            "proposition_spam_decreased": len(old.records) > len(new.records),
            "higher_information_representative": (
                new_spread is not None and max(old_spreads or [0]) < new_spread
            ),
            "duplicate_compression": len(old.records) - len(new.records),
            "scientific_diversity_unchanged": (
                len({r.scientific_question for r in old.records})
                == len({r.scientific_question for r in new.records})
            ),
        },
        "new_result_dict": new.to_dict(),
    }


def blind_evaluation(replay: Dict[str, Any]) -> Dict[str, Any]:
    old = replay["old_pipeline"]
    new = replay["new_pipeline"]

    records = replay["new_result_dict"].get("records", [])
    worthy = sum(
        1
        for r in records
        if r.get("birth_certificate", {}).get("all_passed")
        and r.get("executability_status") == "EXECUTABLE"
    )

    return {
        "unique_scientific_propositions_emitted": new["unique_scientific_questions"],
        "duplicate_evidence_compression": old["propositions_emitted"] - new["propositions_emitted"],
        "representative_evidence_quality": {
            "old_max_spread": max(old.get("quintile_spreads") or [0]),
            "new_representative_spread": new.get("representative_quintile_spread"),
            "improved": replay["improvements"]["higher_information_representative"],
        },
        "research_worthiness_rate": worthy / max(new["propositions_emitted"], 1),
        "scientific_diversity": new["unique_scientific_questions"],
        "grounding": all(
            r.get("observation_provenance", {}).get("evidence_hash") for r in records
        ),
        "falsifiability": all(r.get("disconfirming_observation_spec") for r in records),
        "executability": all(r.get("executability_status") == "EXECUTABLE" for r in records),
        "silence_behavior": {
            "aggregated_as_evidence_silences": sum(
                1
                for s in replay["new_result_dict"].get("silences", [])
                if s.get("reason_code") == "AGGREGATED_AS_EVIDENCE"
            ),
        },
        "budget_efficiency": {
            "unique_ideas_per_budget_slot": new["unique_scientific_questions"] / 3,
            "old_unique_per_slot": old["unique_scientific_questions"] / 3,
        },
    }


def capability_gate(replay: Dict[str, Any], blind: Dict[str, Any]) -> str:
    imp = replay["improvements"]
    if (
        imp["proposition_spam_decreased"]
        and imp["higher_information_representative"]
        and blind["duplicate_evidence_compression"] >= 2
    ):
        return "PRIORITIZE_PASS"
    if imp["higher_information_representative"] or imp["proposition_spam_decreased"]:
        return "PRIORITIZE_PARTIAL"
    return "PRIORITIZE_FAIL"


def hidden_firewall_audit() -> Dict[str, Any]:
    """Confirm prioritizer modules do not import Zone C."""
    prio_modules = [
        REPO / "modules/edge_research/opr_bridge/prioritization.py",
        REPO / "modules/edge_research/opr_bridge/prioritized_pipeline.py",
        REPO / "modules/edge_research/opr_bridge/scientific_identity.py",
        REPO / "modules/edge_research/opr_bridge/semantic_projection.py",
    ]
    forbidden = "zone_c_hidden"
    hits = []
    for mod in prio_modules:
        text = mod.read_text(encoding="utf-8")
        if forbidden in text.lower():
            hits.append(str(mod))
    return {
        "zone_c_accessible_to_prioritizer": len(hits) > 0,
        "forbidden_hits": hits,
        "hidden_convergence_evaluated_post_hoc": True,
        "passed": len(hits) == 0,
    }


def post_hoc_hidden_convergence(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run hidden evaluator AFTER prioritizer frozen — abstract output only."""
    try:
        from benchmarks.bb_prop_01.zone_d_evaluator.hidden_evaluator import evaluate_frozen_run

        return evaluate_frozen_run({"records": records})
    except Exception as exc:
        return {"error": str(exc), "abstract_summary": "POST_HOC_EVAL_SKIPPED"}


def main() -> int:
    pre = preregistration()
    _write("01_prioritization_preregistration.json", pre)

    panel = pd.read_csv(PANEL)
    replay = counterfactual_replay(panel)
    _write("02_counterfactual_replay.json", replay)

    blind = blind_evaluation(replay)
    _write("03_blind_evaluation.json", blind)

    firewall = hidden_firewall_audit()
    _write("04_hidden_firewall_audit.json", firewall)

    hidden = post_hoc_hidden_convergence(replay["new_result_dict"].get("records", []))
    _write("05_post_hoc_hidden_convergence.json", hidden)

    verdict = capability_gate(replay, blind)
    summary = {
        "phase": "3I.5",
        "git_head": _git_head(),
        "prioritizer_version": PRIORITIZER_VERSION,
        "generator_version": OPR_GENERATOR_VERSION,
        "verdict": verdict,
        "replay_improvements": replay["improvements"],
        "blind_evaluation": blind,
        "hidden_firewall_passed": firewall["passed"],
        "highest_leverage_remaining": "BROADER_OBSERVATION_REPERTOIRE",
    }
    _write("06_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
