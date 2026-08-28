#!/usr/bin/env python3
"""
Phase 3I.0 AUDIT + DESIGN ONLY — Autonomous Proposition Generation Readiness.

Generates inventory artifacts from frozen codebase inspection.
Does NOT modify production code.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    dependency_graph = {
        "version": "phase_3i0_v1",
        "commit": _git_head(),
        "stages": [
            {
                "stage": "market_panel",
                "inputs": ["frozen_panel_snapshot.csv", "data_cutoff_date"],
                "outputs": ["eligible_explanatory features", "panel_preflight"],
                "autonomous": False,
                "source": "human_frozen_benchmark_config",
                "modules": ["adapters.py", "research_panel_preflight.py", "market_state.py"],
            },
            {
                "stage": "bootstrap_seed",
                "inputs": ["AutonomousResearchConfig / ROOT_CONFIG"],
                "outputs": ["root OBSERVATION", "root QUESTION", "initial ExperimentSpec"],
                "autonomous": False,
                "source": "human_seeded",
                "modules": ["autonomous_research.py", "bb07_run_benchmark.py"],
                "note": "trigger_kind=AUTONOMOUS_SEED not ANOMALY",
            },
            {
                "stage": "experiment_execution",
                "inputs": ["ExperimentSpec"],
                "outputs": ["ToolResult", "OBS_* codes"],
                "autonomous": True,
                "source": "deterministic_tools",
                "modules": ["research_tools.py", "research_adaptive_tools.py", "research_shape.py"],
            },
            {
                "stage": "interpretation",
                "inputs": ["ToolResult", "branch history"],
                "outputs": ["ResearchAssessment", "information_gaps", "falsification_targets"],
                "autonomous": True,
                "source": "rule_based_interpreter",
                "modules": ["research_interpreter.py", "research_observation_kind.py"],
            },
            {
                "stage": "candidate_generation",
                "inputs": ["ResearchAssessment", "information_gaps"],
                "outputs": ["ResearchActionCandidate[]", "question_text", "draft_spec"],
                "autonomous": False,
                "source": "fixed_template_catalog + grammar_combinatorics",
                "modules": ["research_actions.py", "research_grammar.py", "research_frame.py"],
            },
            {
                "stage": "proposition_identity",
                "inputs": ["draft_spec", "uncertainty_addressed"],
                "outputs": ["CanonicalPropositionCore", "scientific_question_key"],
                "autonomous": True,
                "source": "derived_hash",
                "modules": ["research_proposition_core.py", "research_line_identity.py"],
            },
            {
                "stage": "ranking_selection",
                "inputs": ["candidates", "assessment", "graph"],
                "outputs": ["selected candidate"],
                "autonomous": True,
                "source": "deterministic_scoring",
                "modules": [
                    "research_planner.py",
                    "research_portfolio.py",
                    "research_global_allocator.py",
                ],
            },
            {
                "stage": "spawn_execution",
                "inputs": ["selected candidate"],
                "outputs": ["child QUESTION node", "EXPERIMENT node"],
                "autonomous": True,
                "source": "graph_update",
                "modules": ["research_controller.py", "research_graph.py"],
            },
        ],
        "missing_link": {
            "description": "No stage converts market/panel structural observations into novel scientific propositions",
            "gap_between": ["market_panel", "bootstrap_seed"],
            "also_missing": "No stage synthesizes new uncertainty/question text outside template catalog",
        },
    }

    hard_coded_inventory = {
        "template_ids": [
            "UNCERTAIN_TIME_DISTRIBUTION",
            "UNCERTAIN_SYMBOL_DISTRIBUTION",
            "UNCERTAIN_EPISODE_REPLICATION",
            "UNCERTAIN_MARKET_DEPENDENCE",
            "UNCERTAIN_HORIZON_STABILITY",
            "UNCERTAIN_TRAJECTORY_ROLE",
            "FALSIFY_EXTREME_WINNER",
            "FALSIFY_DATE_ARTIFACT",
            "FALSIFY_SYMBOL_DOMINANCE",
            "REFRAME_ALTERNATIVE_OUTCOME",
            "REPOPULATE_REFINED_COHORT",
            "REPOPULATE_WIDENED_COHORT",
            "ADAPTIVE_PARTITION",
            "THRESHOLD_EXPLORATION",
            "THRESHOLD_NEIGHBORHOOD",
            "CATEGORY_POPULATION_REFINE",
            "THRESHOLD_POPULATION_REFINE",
            "INTERACTION_PARTITION",
            "FRAME_REFRAME",
            "EVIDENCE_POPULATION_REFINE",
            "HORIZON_ADVANCEMENT",
            "STOP_NO_FURTHER_VALUE",
            "ABANDON_FRAGILE",
            "STOP_SESSION_GLOBAL",
        ],
        "gap_codes": [
            "TIME_DISTRIBUTION",
            "SYMBOL_DISTRIBUTION",
            "EPISODE_REPLICATION",
            "MARKET_DEPENDENCE",
            "HORIZON_STABILITY",
            "NEIGHBORHOOD_STABILITY",
            "TRAJECTORY_ROLE",
            "SUBGROUP_ARTIFACT",
            "THRESHOLD_EXPLORATION",
            "NEIGHBORHOOD_THRESHOLD",
            "CATEGORY_REFINEMENT",
            "INTERACTION_FOLLOWUP",
        ],
        "bootstrap_seed": {
            "source": "bb07_run_benchmark.py ROOT_CONFIG",
            "initial_question": "What non-trivial, statistically and economically interesting relationships can be discovered...",
            "classification": "HUMAN-SEED",
        },
        "discovery_pipeline_separate": {
            "module": "discovery.py + challenger.py",
            "connected_to_research_brain_qgen": False,
            "classification": "HUMAN-SEED feature buckets in contracts.py SEARCH_FEATURES",
        },
        "classifications_summary": {
            "REPRESENTATIONAL_CONSTRAINT": [
                "OutcomeSpec grammar kinds",
                "PopulationSpec grammar kinds",
                "Tool registry (executable instruments)",
                "RETURN_COLUMNS / horizon lists",
                "ExperimentSpec schema",
            ],
            "SCIENTIFIC_PRIOR": [
                "question_template_id catalog (implicit hypothesis families)",
                "GAP_* codes (what uncertainties exist)",
                "ResearchNeedType registry",
                "SEARCH_FEATURES / FEATURE_BUCKETS",
                "Initial bootstrap question",
            ],
            "HUMAN-SEED": [
                "ROOT_CONFIG initial_observation / initial_question",
                "Benchmark frozen panel",
                "Discovery grid features",
            ],
            "EXECUTION_SAFETY_CONSTRAINT": [
                "Panel preflight eligible_explanatory",
                "Prohibited feature columns",
                "data_cutoff_date temporal legality",
                "Experiment dedup / content hash",
                "Operational awareness legal set",
            ],
        },
    }

    architectures = {
        "candidates": [
            {
                "id": "A",
                "name": "Observation-Derived Proposition Synthesis",
                "summary": "Structured ToolResult/panel anomalies → PropositionRecord (population, outcome, uncertainty, motivation) → grammar validates executability → bind tool",
                "autonomy": "high",
                "pseudo_creativity_risk": "medium",
                "executability": "high",
                "falsifiability": "high",
                "combinatorial_explosion_risk": "medium",
                "leakage_risk": "low_if_evaluator_separated",
                "compatibility": "high — uses existing ExperimentSpec/tools",
                "blind_eval_ease": "high",
                "minimality": "high — single new layer before template binding",
            },
            {
                "id": "B",
                "name": "Open Proposition Grammar",
                "summary": "Brain constructs CanonicalPropositionCore components directly under grammar constraints without fixed template_id",
                "autonomy": "very_high",
                "pseudo_creativity_risk": "high",
                "executability": "medium",
                "falsifiability": "medium",
                "combinatorial_explosion_risk": "high",
                "leakage_risk": "medium",
                "compatibility": "medium — requires new validation layer",
                "blind_eval_ease": "medium",
                "minimality": "low",
            },
            {
                "id": "C",
                "name": "Hypothesis Mutation / Evolution",
                "summary": "Existing proposition cores scientifically mutated from unresolved evidence (narrow/broad/contradict/abandon) not fixed action templates",
                "autonomy": "medium",
                "pseudo_creativity_risk": "low",
                "executability": "high",
                "falsifiability": "high",
                "combinatorial_explosion_risk": "low",
                "leakage_risk": "low",
                "compatibility": "very_high",
                "blind_eval_ease": "high",
                "minimality": "medium — extends 3H proposition core",
            },
        ],
        "recommended": "A with C as evidence-responsive follow-on",
        "rationale": (
            "Architecture A adds the missing observation→proposition bridge with minimal disruption. "
            "Architecture C handles evidence-responsive redirection without template catalog expansion. "
            "Architecture B deferred — highest pseudo-creativity and explosion risk."
        ),
    }

    blind_benchmark = {
        "name": "Blind Benchmark Proposition Discovery (BB-Prop-01)",
        "separation": {
            "generator_development": "Historical panels WITHOUT hidden-edge labels; synthetic observation fixtures only",
            "frozen_blind_eval": "Held-out panel fingerprint + hidden outcome definitions never in generator code",
            "hidden_evaluator": "Offline-only semantic matcher comparing generated proposition cores to frozen hidden phenomena",
        },
        "convergence_classes": [
            "EXACT_HIDDEN_EDGE_REDISCOVERY",
            "PARTIAL_SEMANTIC_CONVERGENCE",
            "SCIENTIFICALLY_ADJACENT_INDEPENDENT",
            "UNRELATED_PROPOSITION",
            "TEMPLATE_LEAKAGE_OR_ANSWER_IMITATION",
        ],
        "leakage_controls": [
            "Hidden predicates never in SEARCH_FEATURES or template text",
            "Evaluator runs post-hoc only",
            "Generator commit hash frozen before evaluator access",
            "No human/ChatGPT edge strings in generation rules or examples",
        ],
    }

    metrics = {
        "primary_not_raw_count": True,
        "metrics": [
            {"name": "semantic_proposition_diversity", "definition": "Unique scientific_question_key count / session"},
            {"name": "observational_grounding_rate", "definition": "Propositions with linked OBS_* or structural evidence vs ungrounded"},
            {"name": "scientific_independence_rate", "definition": "GENUINELY_INDEPENDENT classifications / total generated"},
            {"name": "falsifiability_score", "definition": "Propositions with explicit comparison/contrast executable via tools"},
            {"name": "executability_rate", "definition": "Generated propositions that pass grammar + tool validation"},
            {"name": "evidence_responsiveness", "definition": "Proposition changes attributable to new evidence not template progression"},
            {"name": "abandoned_hypothesis_rate", "definition": "Propositions explicitly abandoned after falsifying evidence"},
            {"name": "duplicate_rate", "definition": "NEAR_DUPLICATE or IDENTICAL / total generated"},
            {"name": "useful_survivor_rate", "definition": "Propositions receiving further investigation after initial test"},
            {"name": "hidden_benchmark_convergence", "definition": "Blind evaluator class distribution"},
            {"name": "research_budget_efficiency", "definition": "Independent scientific lines explored per experiment"},
            {"name": "hypothesis_spam_penalty", "definition": "Penalize high generation volume with low grounding + low survivor rate"},
        ],
    }

    readiness = {
        "classification": "PARTIALLY_READY",
        "execution_infrastructure": "READY — ExperimentSpec, tools, grammar, ranking, identity, dedup",
        "observation_infrastructure": "PARTIAL — experiment-level OBS_* codes exist; no market-level anomaly→proposition bridge",
        "generative_proposition_layer": "NOT_READY — all question_text from fixed template catalog",
        "single_prerequisite": {
            "name": "Observation-to-Proposition Record (OPR) bridge",
            "description": (
                "A deterministic, auditable layer that converts structured observation evidence "
                "(ToolResult metrics, OBS_* codes, panel statistics) into a CanonicalPropositionCore "
                "plus motivation metadata BEFORE any template_id binding. Must produce novel "
                "uncertainty/question semantics not isomorphic to existing template catalog entries."
            ),
            "why_first": (
                "All downstream infrastructure (grammar, tools, identity, ranking, falsification) "
                "already consumes ExperimentSpec and proposition cores. The sole missing capability "
                "is originating the scientific question itself from observed structure rather than "
                "selecting from research_actions.py templates."
            ),
        },
        "not_ready_items": [
            "No LLM or rule engine synthesizes novel question semantics",
            "Root question always human-seeded",
            "Discovery pipeline (Phase 2) not wired to Research Brain Q-gen",
            "No market-level anomaly detector feeds proposition synthesis",
        ],
    }

    _write("00_dependency_graph.json", dependency_graph)
    _write("01_hard_coded_inventory.json", hard_coded_inventory)
    _write("02_architecture_candidates.json", architectures)
    _write("03_blind_benchmark_design.json", blind_benchmark)
    _write("04_metrics_design.json", metrics)
    _write("05_readiness_assessment.json", readiness)
    print(f"Phase 3I.0 artifacts written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
