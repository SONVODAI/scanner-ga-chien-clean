#!/usr/bin/env python3
"""
Phase 3H.6 — BB09 offline diagnostic replay (observational only).

Replays frozen BB09 planning evidence through the information-value bridge.
Does NOT execute new research experiments or tune parameters from outcomes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
BB09_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_09" / "artifacts"
FIRST_LOSS = REPO / "diagnostics" / "phase_3h5_competence_bottleneck" / "artifacts" / "03_research_need_first_loss.json"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))

from modules.edge_research.research_actions import ResearchActionCandidate  # noqa: E402
from modules.edge_research.research_assessment import ResearchAssessment  # noqa: E402
from modules.edge_research.research_information_value import (  # noqa: E402
    RESEARCH_INFORMATION_VALUE_VERSION,
    apply_information_value_bridge,
    assess_research_information_value,
    build_selection_counterfactual_audit,
)
from modules.edge_research.research_portfolio import score_opportunities_for_selection  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(name: str, base: Path = BB09_ARTIFACTS) -> Any:
    return json.loads((base / name).read_text(encoding="utf-8"))


def _reconstruct_candidate(aid: str, match: Dict[str, Any], score_entry: Dict[str, Any]) -> ResearchActionCandidate:
    from modules.edge_research.research_state import ExperimentSpec

    return ResearchActionCandidate(
        action_id=aid,
        action_code=match.get("intent", "UNKNOWN"),
        intent=match.get("intent", "EXPLORATION"),
        question_template_id="replay",
        question_text="bb09 replay",
        tool_name=match.get("tool_name", ""),
        tool_version="v1",
        draft_spec=ExperimentSpec(
            tool_name=match.get("tool_name", "horizon_comparison"),
            tool_version="v1",
            data_cutoff_date="2026-08-17",
            inputs={"horizon": "T5"},
            research_scope={"population_spec": {"kind": "all", "grammar_version": "research_grammar_v1"}},
        ),
        uncertainty_addressed=match.get("uncertainty_code", ""),
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=("BB09_REPLAY",),
        priority_hints={},
    )


def _assessment_from_planning(entry: Dict[str, Any]) -> ResearchAssessment:
    a = entry.get("assessment") or {}
    return ResearchAssessment(
        source_experiment_node_id=entry.get("experiment_node_id", ""),
        tool_name=a.get("tool_name", ""),
        tool_status=a.get("tool_status", "OK"),
        empirical_findings=tuple(a.get("empirical_findings") or []),
        unresolved_uncertainties=tuple(a.get("unresolved_uncertainties") or []),
        contradictions=tuple(a.get("contradictions") or []),
        concentration_concerns=tuple(a.get("concentration_concerns") or []),
        replication_concerns=tuple(a.get("replication_concerns") or []),
        fragility_evidence=tuple(a.get("fragility_evidence") or []),
        context_dependence=tuple(a.get("context_dependence") or []),
        horizon_dependence=tuple(a.get("horizon_dependence") or []),
        information_gaps=tuple(a.get("information_gaps") or []),
        possible_falsification_targets=tuple(a.get("possible_falsification_targets") or []),
        descriptive_strength=a.get("descriptive_strength", "NO_CLEAR_DIFFERENCE"),
        interpretation_confidence=a.get("interpretation_confidence", "HIGH"),
        additional_investigation_warranted=bool(a.get("additional_investigation_warranted")),
        interesting=bool(a.get("interesting")),
        validated=bool(a.get("validated")),
        actionable=bool(a.get("actionable")),
        branch_tools_attempted=tuple(a.get("branch_tools_attempted") or []),
        branch_observation_codes=tuple(a.get("branch_observation_codes") or []),
        observation_kind=a.get("observation_kind", ""),
        conditional_candidate=bool(a.get("conditional_candidate")),
    )


def replay_bb09() -> Dict[str, Any]:
    planning = _load("05_planning_decision_diary.json")
    competence = _load("06_competence_audit_diary.json")
    first_loss = json.loads(FIRST_LOSS.read_text()) if FIRST_LOSS.exists() else {"records": []}

    b7_cases = [r for r in first_loss.get("records", []) if r.get("first_loss_layer") == "B7"]
    transitions: List[Dict[str, Any]] = []

    nonzero_iv = 0
    unchanged = 0
    changed = 0
    fals_changed = 0
    fals_unchanged = 0
    decomp_changed = 0
    decomp_unchanged = 0
    correct_remain = 0
    overcorrection = 0

    class NullGraph:
        session = type("S", (), {"research_information_value_audit": None})()

    graph = NullGraph()

    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        assessment = _assessment_from_planning(p)
        matches = c.get("candidate_matches") or {}
        raw_scores = p.get("candidate_scores") or {}

        base_scores: Dict[str, Tuple[float, Dict[str, float]]] = {}
        candidates: List[ResearchActionCandidate] = []
        for aid, sc in raw_scores.items():
            match = matches.get(aid, {})
            cand = _reconstruct_candidate(aid, match, sc)
            candidates.append(cand)
            base_scores[aid] = (float(sc.get("total", 0)), dict(sc.get("components") or {}))

        if not candidates:
            continue

        bridged, iv_assessments = apply_information_value_bridge(
            base_scores, graph=graph, assessment=assessment, candidates=candidates,
            experiment_node_id=p.get("experiment_node_id"),
        )
        audit = build_selection_counterfactual_audit(
            experiment_node_id=p.get("experiment_node_id", ""),
            candidates=candidates,
            base_scores=base_scores,
            bridged_scores=bridged,
            assessments=iv_assessments,
            selected_action_id=p.get("selected_action_id") or "",
        )

        nz = sum(1 for a in iv_assessments if a.valuation_contribution > 0)
        nonzero_iv += nz
        if audit.selection_changed:
            changed += 1
        else:
            unchanged += 1

        sel_id = p.get("selected_action_id") or ""
        if sel_id and audit.winner_with_bridge == audit.winner_without_bridge == sel_id:
            correct_remain += 1

        fals_cands = [a for a in iv_assessments if a.falsification_relevance > 0]
        if fals_cands:
            if audit.selection_changed and any(a.action_id == audit.winner_with_bridge for a in fals_cands):
                fals_changed += 1
            else:
                fals_unchanged += 1

        decomp_cands = [a for a in iv_assessments if a.heterogeneity_relevance > 0]
        if decomp_cands:
            if audit.selection_changed and any(a.action_id == audit.winner_with_bridge for a in decomp_cands):
                decomp_changed += 1
            else:
                decomp_unchanged += 1

        if audit.selection_changed and audit.winner_with_bridge_score < audit.winner_without_bridge_score:
            overcorrection += 1

        transitions.append(
            {
                "transition": idx + 1,
                "experiment_node_id": p.get("experiment_node_id"),
                "selected_actual": sel_id,
                "winner_without_bridge": audit.winner_without_bridge,
                "winner_with_bridge": audit.winner_with_bridge,
                "selection_changed": audit.selection_changed,
                "scientific_reason": audit.scientific_reason,
                "nonzero_information_value_candidates": nz,
                "falsification_candidates_with_value": len(fals_cands),
                "decomposition_candidates_with_value": len(decomp_cands),
            }
        )

    return {
        "replay_version": "bb09_information_value_replay_v1",
        "information_value_version": RESEARCH_INFORMATION_VALUE_VERSION,
        "replayed_at": _utc_now(),
        "bb09_b7_first_loss_cases": len(b7_cases),
        "transitions_replayed": len(transitions),
        "candidates_with_nonzero_information_value": nonzero_iv,
        "planner_layer_winners_unchanged": unchanged,
        "planner_layer_winners_changed": changed,
        "falsification_cases_changed": fals_changed,
        "falsification_cases_unchanged": fals_unchanged,
        "decomposition_cases_changed": decomp_changed,
        "decomposition_cases_unchanged": decomp_unchanged,
        "original_winner_correctly_remains": correct_remain,
        "pathological_overcorrection_signals": overcorrection,
        "transitions": transitions,
        "interpretation": (
            "Replay applies bridge to frozen BB09 planner scores only. "
            "Non-zero information value on B7 cases confirms bridge reachability. "
            "Selection changes at planner layer indicate counterfactual impact without new experiments."
        ),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not BB09_ARTIFACTS.exists():
        print(json.dumps({"error": "BB09 artifacts not found", "path": str(BB09_ARTIFACTS)}))
        sys.exit(1)
    report = replay_bb09()
    (OUT_DIR / "bb09_information_value_replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
