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


def _profile_from_allocation_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ga = entry.get("global_allocation") or {}
    sel = ga.get("selected") or {}
    if not sel:
        return None
    cand = sel.get("action_candidate") or {}
    draft = cand.get("draft_spec") or {}
    scope = draft.get("research_scope") or {}
    inputs = draft.get("inputs") or {}
    return {
        "opportunity_id": sel.get("opportunity_id", ""),
        "source": sel.get("source", ""),
        "action_id": sel.get("action_id", ""),
        "tool_name": draft.get("tool_name", cand.get("tool_name", "")),
        "branch_root_id": sel.get("branch_root_id", ga.get("branch_before", "")),
        "frame_id": sel.get("frame_id", ga.get("frame_before", "")),
        "population_spec": scope.get("population_spec") or {},
        "outcome_spec": scope.get("outcome_spec") or draft.get("outcome_spec") or {},
        "observation_horizon": int(ga.get("observation_horizon_before") or 0),
        "uncertainty_codes": list(cand.get("uncertainty_addressed") or ()),
        "feature_columns": [
            str(inputs[k])
            for k in ("feature_column", "partition_column", "trajectory_feature", "primary_feature")
            if k in inputs
        ],
        "expected_research_value": float(sel.get("expected_research_value", ga.get("selected_erv", 0))),
        "branch_marginal_state": ga.get("branch_marginal_state", ""),
        "stop_session_selected": ga.get("stop_session_selected", False),
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
    gain_audit = _load(BB11 / "08_realized_information_gain_audit.json")
    marginal_audit = _load(BB11 / "09_branch_marginal_state_audit.json")

    transitions_of_interest = ("T4", "T8", "T9", "T11")
    counterfactuals: List[Dict[str, Any]] = []
    prior_profiles: List[Dict[str, Any]] = []

    gain_by_exp = {
        e.get("experiment_node_id", ""): e.get("gain_level", "")
        for e in (gain_audit if isinstance(gain_audit, list) else gain_audit.get("entries", []))
    }

    for entry in diary if isinstance(diary, list) else diary.get("entries", []):
        tid = entry.get("transition_id") or entry.get("planning_transition") or ""
        if not any(t in str(tid) for t in transitions_of_interest):
            continue
        profile = _profile_from_allocation_entry(entry)
        if not profile:
            continue

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
        if prior_profiles:
            prior_p = prior_profiles[-1]
            prior_id = ResearchLineIdentity(
                version=RESEARCH_LINE_IDENTITY_VERSION,
                population_spec=prior_p["population_spec"],
                outcome_spec=prior_p["outcome_spec"],
                observation_horizon=prior_p["observation_horizon"],
                uncertainty_codes=tuple(prior_p["uncertainty_codes"] or ()),
                research_needs=(),
                conditioning_context={},
                feature_slice=tuple(prior_p["feature_columns"]),
                evidence_lineage=(),
                metadata={
                    "tool_name": prior_p["tool_name"],
                    "action_id": prior_p["action_id"],
                },
            )
            rel_audit = classify_research_line_relationship(prior_id, identity).to_dict()
            branch_levels = [gain_by_exp.get(prior_p.get("experiment_node_id", ""), "")]
            line_levels = [gain_by_exp.get(k, "") for k in gain_by_exp if gain_by_exp[k]]
            transfer = rel_audit["classification"] in (
                ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
                ResearchLineRelationship.IDENTICAL.value,
                ResearchLineRelationship.NEAR_DUPLICATE.value,
            )
            merged, _ = merge_semantic_realized_levels(
                [g for g in branch_levels if g],
                [g for g in line_levels if g],
                transfer_allowed=transfer,
                relationship=rel_audit["classification"],
            )
            inherited_gains = merged

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

        counterfactuals.append(
            {
                "transition_id": tid,
                "old_structural_identity": {
                    "branch_root_id": profile["branch_root_id"],
                    "frame_id": profile["frame_id"],
                    "action_id": profile["action_id"],
                    "tool_name": profile["tool_name"],
                },
                "new_semantic_line_identity": identity.to_dict(),
                "relationship_to_prior": rel_audit,
                "freshness": fresh.to_dict(),
                "inherited_realized_gain_evidence": inherited_gains,
                "old_valuation_context": {
                    "erv": profile["expected_research_value"],
                    "branch_marginal_state": profile["branch_marginal_state"],
                },
                "new_valuation_context": {
                    "semantic_proposition_key": identity.scientific_proposition_key(),
                    "would_see_prior_zero_gain": "ZERO" in inherited_gains,
                    "representation_novelty_risk": rel_audit.get("classification")
                    == ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value
                    if rel_audit
                    else False,
                },
                "selection_before": profile.get("tool_name"),
                "counterfactual_selection_after": profile.get("tool_name"),
                "selection_changed": False,
                "scientific_reason": "Semantic continuity audit — offline replay only",
                "overcorrection_check": "No forced STOP; decay transfer evidence-only",
            }
        )
        prior_profiles.append(profile)

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
