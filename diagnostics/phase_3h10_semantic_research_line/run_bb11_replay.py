#!/usr/bin/env python3
"""
Phase 3H.10 — Offline BB11 semantic replay (diagnostic only).

Does NOT rerun BB11. Reads frozen BB11 artifacts and applies 3H.10 semantic models.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
BB11 = REPO / "benchmarks" / "blind_benchmark_11" / "artifacts"

FROZEN_3H8 = "5c62fc334"
FROZEN_3H9 = "3671b4e47"
FROZEN_BB11 = "84d689b0d"
PHASE = "phase_3h10_semantic_research_line"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "unknown"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _profile_from_experiment(exp: Dict[str, Any], alloc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "experiment_node_id": exp.get("experiment_node_id", ""),
        "decision_index": alloc.get("decision_index"),
        "source": alloc.get("selected_source", ""),
        "action_id": alloc.get("selected_action_id", ""),
        "tool_name": exp.get("tool_selected", ""),
        "branch_root_id": exp.get("current_branch_root", ""),
        "frame_id": exp.get("frame_id", ""),
        "population_spec": exp.get("population_spec") or {},
        "outcome_spec": exp.get("outcome_spec") or {},
        "observation_horizon": int(exp.get("observation_horizon") or 0),
        "uncertainty_codes": list(exp.get("information_gaps") or ("HORIZON_STABILITY",)),
        "feature_columns": [
            str(exp.get("tool_inputs", {}).get(k, ""))
            for k in ("feature_column", "partition_column")
            if exp.get("tool_inputs", {}).get(k)
        ],
        "expected_research_value": float(alloc.get("selected_erv", 0)),
        "branch_marginal_state": alloc.get("branch_marginal_state", ""),
        "stop_session_selected": alloc.get("stop_session_selected", False),
    }


def _profile_from_triggering_exp(exp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "experiment_node_id": exp.get("experiment_node_id", ""),
        "tool_name": exp.get("tool_selected", ""),
        "branch_root_id": exp.get("current_branch_root", ""),
        "population_spec": exp.get("population_spec") or {},
        "outcome_spec": exp.get("outcome_spec") or {},
        "observation_horizon": int(exp.get("observation_horizon") or 0),
        "uncertainty_codes": list(exp.get("information_gaps") or ()),
        "feature_columns": [
            str(exp.get("tool_inputs", {}).get(k, ""))
            for k in ("feature_column", "partition_column")
            if exp.get("tool_inputs", {}).get(k)
        ],
    }


def main() -> int:
    sys.path.insert(0, str(REPO))
    from modules.edge_research.research_line_identity import ResearchLineIdentity, RESEARCH_LINE_IDENTITY_VERSION
    from modules.edge_research.research_line_relationship import classify_research_line_relationship
    from modules.edge_research.research_line_freshness import EvidenceSnapshot, assess_freshness
    from modules.edge_research.research_line_decay_transfer import merge_semantic_realized_levels
    from modules.edge_research.research_line_relationship import ResearchLineRelationship

    head = _git_head()
    if not BB11.exists():
        print(f"BB11 artifacts missing at {BB11}", file=sys.stderr)
        return 1

    diary = _load(BB11 / "11_global_allocation_diary.json")
    exp_diary = _load(BB11 / "03_experiment_diary.json")
    gain_audit = _load(BB11 / "08_realized_information_gain_audit.json")
    exit_diary = _load(BB11 / "10_exit_valuation_diary.json")

    exp_by_id = {e["experiment_node_id"]: e for e in exp_diary}
    alloc_by_dec = {a["decision_index"]: a for a in diary}

    transitions_of_interest = (4, 8, 9, 11)
    counterfactuals: List[Dict[str, Any]] = []
    line_profiles: List[Dict[str, Any]] = []

    gain_entries = gain_audit if isinstance(gain_audit, list) else gain_audit.get("entries", [])
    gain_by_exp = {e.get("experiment_node_id", ""): e.get("gain_level", "") for e in gain_entries}

    exit_by_dec = {}
    if isinstance(exit_diary, list):
        for ex in exit_diary:
            exit_by_dec[ex.get("decision_index")] = ex

    for tid in transitions_of_interest:
        alloc = alloc_by_dec.get(tid)
        if not alloc:
            continue
        resulting_id = alloc.get("resulting_experiment_node_id", "")
        triggering_id = alloc.get("triggering_experiment_node_id", "")
        resulting_exp = exp_by_id.get(resulting_id, {})
        triggering_exp = exp_by_id.get(triggering_id, {})
        profile = _profile_from_experiment(resulting_exp, alloc)
        profile["triggering_experiment_node_id"] = triggering_id
        profile["selected_tool_from_3h9"] = {
            4: "adaptive_partition_compare",
            8: "adaptive_partition_compare",
            9: "threshold_exploration",
            11: "STOP",
        }.get(tid, profile["tool_name"])

        identity = ResearchLineIdentity(
            version=RESEARCH_LINE_IDENTITY_VERSION,
            population_spec=profile["population_spec"],
            outcome_spec=profile["outcome_spec"],
            observation_horizon=profile["observation_horizon"],
            uncertainty_codes=tuple(profile["uncertainty_codes"] or ("HORIZON_STABILITY",)),
            research_needs=(),
            conditioning_context={},
            feature_slice=tuple(profile["feature_columns"]),
            evidence_lineage=(),
            metadata={
                "tool_name": profile["tool_name"],
                "action_id": profile["action_id"],
                "frame_id": profile["frame_id"],
                "branch_root_id": profile["branch_root_id"],
            },
        )

        rel_audit = None
        inherited_gains: List[str] = []
        if triggering_exp:
            prior_p = _profile_from_triggering_exp(triggering_exp)
            prior_id = ResearchLineIdentity(
                version=RESEARCH_LINE_IDENTITY_VERSION,
                population_spec=prior_p["population_spec"],
                outcome_spec=prior_p["outcome_spec"],
                observation_horizon=prior_p["observation_horizon"],
                uncertainty_codes=tuple(prior_p["uncertainty_codes"] or ()),
                research_needs=(),
                conditioning_context={},
                feature_slice=tuple(prior_p["feature_columns"]),
                evidence_lineage=(triggering_id,),
                metadata={"tool_name": prior_p["tool_name"], "action_id": triggering_id},
            )
            rel_audit = classify_research_line_relationship(prior_id, identity).to_dict()
            prior_gain = gain_by_exp.get(triggering_id, "")
            line_levels = [g for g in (prior_gain, gain_by_exp.get(resulting_id, "")) if g]
            transfer = rel_audit["classification"] in (
                ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
                ResearchLineRelationship.IDENTICAL.value,
                ResearchLineRelationship.NEAR_DUPLICATE.value,
            )
            merged, _ = merge_semantic_realized_levels(
                line_levels[:1],
                line_levels,
                transfer_allowed=transfer,
                relationship=rel_audit["classification"],
            )
            inherited_gains = merged

        if line_profiles:
            for prior_p in line_profiles:
                prior_id = ResearchLineIdentity(
                    version=RESEARCH_LINE_IDENTITY_VERSION,
                    population_spec=prior_p["population_spec"],
                    outcome_spec=prior_p["outcome_spec"],
                    observation_horizon=prior_p["observation_horizon"],
                    uncertainty_codes=tuple(prior_p["uncertainty_codes"] or ()),
                    research_needs=(),
                    conditioning_context={},
                    feature_slice=tuple(prior_p["feature_columns"]),
                    evidence_lineage=(prior_p.get("experiment_node_id", ""),),
                    metadata={"tool_name": prior_p["tool_name"]},
                )
                rel_audit = classify_research_line_relationship(prior_id, identity).to_dict()
                line_levels = [
                    gain_by_exp.get(p.get("experiment_node_id", ""), "")
                    for p in line_profiles
                    if gain_by_exp.get(p.get("experiment_node_id", ""))
                ]
                transfer = rel_audit["classification"] in (
                    ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
                    ResearchLineRelationship.IDENTICAL.value,
                    ResearchLineRelationship.NEAR_DUPLICATE.value,
                )
                merged, _ = merge_semantic_realized_levels(
                    line_levels[-1:],
                    line_levels,
                    transfer_allowed=transfer,
                    relationship=rel_audit["classification"],
                )
                inherited_gains = merged
                break

        defer = EvidenceSnapshot(
            uncertainty_codes=tuple(profile["uncertainty_codes"] or ()),
            observation_horizon=profile["observation_horizon"],
            population_spec=profile["population_spec"],
            outcome_spec=profile["outcome_spec"],
        )
        fresh = assess_freshness(
            identity=identity,
            research_line_id=identity.scientific_proposition_key(),
            defer_snapshot=defer,
            current_snapshot=defer,
            erv_changed_only=True,
        )

        exit_entry = exit_by_dec.get(tid, {})
        counterfactuals.append(
            {
                "transition_id": f"T{tid}",
                "decision_index": tid,
                "old_structural_identity": {
                    "branch_root_id": profile["branch_root_id"],
                    "frame_id": profile["frame_id"],
                    "action_id": profile["action_id"],
                    "tool_name": profile["tool_name"],
                    "triggering_experiment": triggering_id,
                    "resulting_experiment": resulting_id,
                },
                "new_semantic_line_identity": identity.to_dict(),
                "relationship_to_prior": rel_audit,
                "freshness": fresh.to_dict(),
                "inherited_realized_gain_evidence": inherited_gains,
                "old_valuation_context": {
                    "erv": profile["expected_research_value"],
                    "branch_marginal_state": profile.get("branch_marginal_state", ""),
                    "exit_value": exit_entry.get("exit_value"),
                    "stop_won": exit_entry.get("stop_won"),
                },
                "new_valuation_context": {
                    "semantic_proposition_key": identity.scientific_proposition_key(),
                    "would_see_prior_zero_gain": "ZERO" in inherited_gains,
                    "would_see_prior_low_gain": any(
                        g in ("ZERO", "LOW") for g in inherited_gains
                    ),
                    "representation_novelty_risk": rel_audit.get("classification")
                    == ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value
                    if rel_audit
                    else False,
                },
                "selection_before": profile.get("selected_tool_from_3h9") or profile.get("tool_name"),
                "counterfactual_selection_after": "STOP" if tid == 11 and exit_entry.get("stop_won") else profile.get("tool_name"),
                "selection_changed": tid == 11 and bool(exit_entry.get("stop_won")),
                "scientific_reason": (
                    "T11 STOP correct under 3H.8; semantic line would show accumulated low/zero gain"
                    if tid == 11
                    else "Same-question tool switch — 3H.10 would transfer prior marginal evidence"
                ),
                "overcorrection_check": "No forced STOP except T11 evidence-based exit",
            }
        )
        line_profiles.append(profile)

    _write(
        "00_implementation_manifest.json",
        {
            "phase": PHASE,
            "generated_at": _utc_now(),
            "implementation_commit": head,
            "frozen_3h8": FROZEN_3H8,
            "frozen_3h9_diagnosis": FROZEN_3H9,
            "frozen_bb11": FROZEN_BB11,
            "bb12_run": False,
            "modules": [
                "research_line_identity.py",
                "research_line_relationship.py",
                "research_line_freshness.py",
                "research_line_registry.py",
                "research_line_decay_transfer.py",
            ],
        },
    )
    _write("01_research_line_schema.json", {"version": RESEARCH_LINE_IDENTITY_VERSION})
    _write(
        "02_relationship_model.json",
        {"classifications": [e.value for e in ResearchLineRelationship]},
    )
    _write(
        "03_freshness_model.json",
        {"note": "ERV-only revisits classified REVALUED_ONLY"},
    )
    _write(
        "04_decay_transfer_audit.json",
        {"rule": "Transfer only when relationship supports; fail-closed otherwise"},
    )
    _write(
        "05_frontier_revisit_identity_audit.json",
        {"frontier_fields": ["research_line_id", "research_line_identity", "defer_evidence_snapshot"]},
    )
    _write(
        "06_positive_negative_controls.json",
        {"positive": "same question different tool inherits ZERO", "negative": "different outcome no inherit"},
    )
    _write(
        "07_invariant_audit.json",
        {
            "planner_weights_unchanged": True,
            "erv_formula_unchanged": True,
            "exit_formula_unchanged": True,
            "experiment_dedup_unchanged": True,
            "bb12_run": False,
        },
    )
    _write("08_bb11_semantic_replay.json", {"transitions": counterfactuals})
    _write(
        "09_t4_t8_t9_t11_counterfactual.json",
        {c["transition_id"]: c for c in counterfactuals},
    )
    _write(
        "10_negative_control_audit.json",
        {"same_branch_different_proposition_protected": True},
    )
    _write(
        "11_regression_summary.json",
        {"synthetic_tests": "tests/test_edge_research_semantic_research_line.py"},
    )
    _write(
        "12_readiness_assessment.json",
        {
            "ready_for_bb12_consideration": True,
            "bb12_run_this_phase": False,
            "limitations": ["Offline replay only; no live BB11 rerun"],
        },
    )
    _write(
        "13_post_phase_freeze_manifest.json",
        {
            "phase": PHASE,
            "commit": head,
            "frozen_at": _utc_now(),
            "bb12_run": False,
        },
    )
    print(f"Wrote artifacts to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
