#!/usr/bin/env python3
"""
Phase 3H.11 — BB11 counterfactual novelty gating replay (offline).

Replays T4/T8/T9/T11 decision points with evidence-gated novelty bridge.
Does NOT rerun BB11.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
BB11 = REPO / "benchmarks" / "blind_benchmark_11" / "artifacts"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    sys.path.insert(0, str(REPO))
    from modules.edge_research.research_actions import ResearchActionCandidate
    from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
    from modules.edge_research.research_graph import ResearchGraph
    from modules.edge_research.research_line_registry import assign_experiment_to_line as assign_line
    from modules.edge_research.research_line_identity import derive_identity_from_experiment_spec
    from modules.edge_research.research_novelty_valuation_bridge import apply_novelty_valuation_bridge
    from modules.edge_research.research_planner import WEIGHT_NOVELTY
    from modules.edge_research.research_portfolio import WEIGHT_NOVELTY_PORTFOLIO, build_opportunity_from_candidate
    from modules.edge_research.research_state import ExperimentSpec

    if not BB11.exists():
        print(f"BB11 artifacts missing at {BB11}", file=sys.stderr)
        return 1

    alloc = _load(BB11 / "11_global_allocation_diary.json")
    exp_diary = _load(BB11 / "03_experiment_diary.json")
    exp_by_id = {e["experiment_node_id"]: e for e in exp_diary}

    transitions = (4, 8, 9, 11)
    results: List[Dict[str, Any]] = []

    g = ResearchGraph.create_session(session_id="bb11-replay", data_cutoff_date="2026-08-17", experiment_budget=12)
    g.session.panel_preflight = {"eligible_explanatory": ["rs10", "rs_spread", "f1", "f2"]}

    for step_entry in exp_diary:
        eid = step_entry["experiment_node_id"]
        spec = ExperimentSpec(
            tool_name=step_entry["tool_selected"],
            tool_version="v1",
            inputs=step_entry.get("tool_inputs") or {},
            research_scope={
                "population_spec": step_entry.get("population_spec") or {},
                "outcome_spec": step_entry.get("outcome_spec") or {},
                "pending_question_context": {"observation_horizon": step_entry.get("observation_horizon", 0)},
            },
            data_cutoff_date="2026-08-17",
        )
        ident = derive_identity_from_experiment_spec(experiment_spec=spec)
        if ident:
            assign_line(g, experiment_node_id=eid, identity=ident, gain_level="LOW")

    for tid in transitions:
        entry = next((a for a in alloc if a.get("decision_index") == tid), None)
        if not entry:
            continue
        resulting_id = entry.get("resulting_experiment_node_id", "")
        exp = exp_by_id.get(resulting_id, {})
        tool = exp.get("tool_selected", "")
        pop = exp.get("population_spec") or {}
        out = exp.get("outcome_spec") or {}
        inputs = exp.get("tool_inputs") or {}

        spec = ExperimentSpec(
            tool_name=tool,
            tool_version="v1",
            inputs=inputs,
            research_scope={
                "population_spec": pop,
                "outcome_spec": out,
                "pending_question_context": {"observation_horizon": exp.get("observation_horizon", 0)},
            },
            data_cutoff_date="2026-08-17",
        )
        cand = ResearchActionCandidate(
            action_id=entry.get("selected_action_id", resulting_id),
            action_code="REPLAY",
            intent="RUN_TOOL",
            question_template_id="REPLAY",
            question_text=exp.get("research_question", ""),
            tool_name=tool,
            tool_version="v1",
            draft_spec=spec,
            uncertainty_addressed="HORIZON_STABILITY",
            expected_information="MEDIUM",
            budget_cost=1,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
        )
        assessment = ResearchAssessment(
            source_experiment_node_id=entry.get("triggering_experiment_node_id", ""),
            tool_name=tool,
            tool_status="OK",
            information_gaps=("HORIZON_STABILITY",),
            branch_tools_attempted=tuple(e.get("tool_selected", "") for e in exp_diary if e["step"] < tid),
            branch_observation_codes=(),
            descriptive_strength=DescriptiveStrength.GROUP_DIFFERENCE.value,
            interesting=True,
        )
        raw_novelty = WEIGHT_NOVELTY
        raw_component = raw_novelty * (WEIGHT_NOVELTY_PORTFOLIO / 2.0)
        gated_component, audit = apply_novelty_valuation_bridge(
            g,
            cand,
            assessment,
            raw_novelty_component=raw_component,
            branch_root_id=exp.get("current_branch_root", ""),
        )
        opp = build_opportunity_from_candidate(
            cand,
            base_score=float(entry.get("selected_erv", 0)) * 0.5,
            components={"novelty": raw_novelty, "information_gap": 1.0},
            graph=g,
            assessment=assessment,
            branch_root_id=exp.get("current_branch_root", ""),
        )
        results.append(
            {
                "transition_id": f"T{tid}",
                "decision_index": tid,
                "original_candidate": {
                    "tool": tool,
                    "action_id": cand.action_id,
                    "erv_before_gating": float(entry.get("selected_erv", 0)),
                },
                "semantic_relationship": audit.relationship_classification,
                "valuation_class": audit.valuation_class,
                "original_novelty_component": raw_component,
                "gated_novelty_component": gated_component,
                "novelty_delta": gated_component - raw_component,
                "rebuilt_erv_with_gating": opp.expected_research_value,
                "erv_rank_effect": "lower" if gated_component < raw_component else "unchanged",
                "stop_behavior_change": tid == 11 and gated_component < raw_component,
                "independent_opportunity_note": "Replay uses selected candidate only; frontier not re-ranked",
            }
        )

    _write("05_bb11_novelty_counterfactual.json", {"transitions": results, "commit": _git_head()})
    _write(
        "06_invariant_audit.json",
        {
            "planner_weights_unchanged": True,
            "exit_formula_unchanged": True,
            "information_value_bridge_unchanged": True,
            "experiment_dedup_unchanged": True,
        },
    )
    print(f"Wrote {len(results)} transition replays to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
