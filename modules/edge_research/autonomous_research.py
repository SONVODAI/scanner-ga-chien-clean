"""
Autonomous research session bootstrap for Edge Research (PATCH 3D).

Safe bridge between EdgeResearchEngine and PATCH 3A–3C controller loop.
Read-only panel input, automatic session persistence, feature-flagged entry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.contracts import GUARDRAILS_CONFIG_VERSION
from modules.edge_research.research_controller import (
    ControllerStepResult,
    DEFAULT_SESSION_EXPERIMENT_BUDGET,
    run_research_session,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_grammar import (
    OutcomeSpec,
    PopulationSpec,
    apply_population_spec,
    build_search_accounting,
    population_spec_to_research_scope,
    validate_outcome_spec,
    validate_population_spec,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    QuestionRationale,
    ResearchQuestionContext,
)
from modules.edge_research.research_tools import ToolRegistry, apply_research_cutoff, build_default_tool_registry
from modules.edge_research.storage import read_research_graph, write_research_graph

AUTONOMOUS_RESEARCH_ENV_FLAG = "EDGE_RESEARCH_AUTONOMOUS"


def autonomous_research_enabled(explicit: Optional[bool] = None) -> bool:
    """Feature flag — autonomous research is opt-in."""
    if explicit is not None:
        return explicit
    return os.environ.get(AUTONOMOUS_RESEARCH_ENV_FLAG, "0") in ("1", "true", "TRUE", "yes")


@dataclass
class AutonomousResearchConfig:
    """Configuration for one autonomous research session."""

    data_cutoff_date: str
    initial_observation: str
    initial_question: str
    population_spec: PopulationSpec
    outcome_spec: OutcomeSpec
    initial_tool_name: str = "partition_group_compare"
    initial_tool_inputs: Dict[str, Any] = field(
        default_factory=lambda: {
            "horizon": "T5",
            "partition_column": "partition_group",
            "partition_type": "categorical",
        }
    )
    experiment_budget: int = DEFAULT_SESSION_EXPERIMENT_BUDGET
    max_steps: Optional[int] = None
    auto_persist: bool = True
    session_id: Optional[str] = None


@dataclass
class AutonomousResearchResult:
    graph: ResearchGraph
    steps: List[ControllerStepResult]
    session_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.graph.session.research_session_id,
            "status": self.graph.session.status.value,
            "experiments_used": self.graph.session.experiments_used,
            "step_count": len(self.steps),
            "session_path": str(self.session_path) if self.session_path else None,
        }


def bootstrap_research_graph(config: AutonomousResearchConfig) -> tuple[ResearchGraph, str, str]:
    """
    Create session graph with root observation, question, and initial experiment.

    Returns (graph, question_node_id, initial_experiment_id).
    """
    validate_population_spec(config.population_spec)
    validate_outcome_spec(config.outcome_spec)

    graph = ResearchGraph.create_session(
        data_cutoff_date=config.data_cutoff_date,
        guardrails_config_version=GUARDRAILS_CONFIG_VERSION,
        experiment_budget=config.experiment_budget,
        session_id=config.session_id,
    )

    oid = graph.add_root_observation(
        description=config.initial_observation,
        trigger_kind="AUTONOMOUS_SEED",
    )

    accounting = build_search_accounting(
        population_spec=config.population_spec,
        outcome_spec=config.outcome_spec,
        research_depth=0,
    )
    research_scope = population_spec_to_research_scope(config.population_spec)
    research_scope["outcome_spec"] = config.outcome_spec.to_dict()
    research_scope["outcome_spec_hash"] = config.outcome_spec.content_hash()

    qctx = ResearchQuestionContext(
        population_spec=config.population_spec.to_dict(),
        outcome_spec=config.outcome_spec.to_dict(),
        research_depth=0,
        search_complexity=accounting.predicate_count,
        search_accounting=accounting.to_dict(),
    )

    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text=config.initial_question,
        rationale=QuestionRationale(
            reason_code="AUTONOMOUS_INITIAL",
            prior_node_id=oid,
            evidence_summary={"seed": True},
        ),
        question_context=qctx,
    )

    spec = ExperimentSpec(
        tool_name=config.initial_tool_name,
        tool_version="v1",
        inputs=dict(config.initial_tool_inputs),
        research_scope=research_scope,
        data_cutoff_date=config.data_cutoff_date,
    )
    eid = graph.add_experiment(question_node_id=qid, spec=spec)
    return graph, qid, eid


def run_autonomous_research_session(
    panel: pd.DataFrame,
    config: AutonomousResearchConfig,
    *,
    registry: Optional[ToolRegistry] = None,
    data_dir: Optional[Path] = None,
    enabled: Optional[bool] = None,
) -> AutonomousResearchResult:
    """
    Run a full autonomous research session on a read-only panel.

    Applies cutoff filtering, bootstraps graph, runs controller loop, persists session.
    """
    if not autonomous_research_enabled(enabled):
        raise RuntimeError(
            f"Autonomous research is disabled. Set {AUTONOMOUS_RESEARCH_ENV_FLAG}=1 to enable."
        )

    validate_population_spec(config.population_spec)
    validate_outcome_spec(config.outcome_spec)

    work_panel = panel.copy()
    cutoff_panel, _ = apply_research_cutoff(work_panel, config.data_cutoff_date, horizons=["T3", "T5", "T10"])
    pop_panel, pop_n = apply_population_spec(cutoff_panel, config.population_spec)
    if pop_panel.empty:
        raise ValueError("Population spec yields empty cohort after cutoff — cannot start session")

    graph, _qid, eid = bootstrap_research_graph(config)
    # Record resulting N on root question context.
    root_q = graph.get_node(_qid)
    if root_q.question_context:
        updated = ResearchQuestionContext(
            population_spec=root_q.question_context.population_spec,
            outcome_spec=root_q.question_context.outcome_spec,
            research_depth=root_q.question_context.research_depth,
            search_complexity=root_q.question_context.search_complexity,
            population_n=pop_n,
            search_accounting=root_q.question_context.search_accounting,
        )
        root_q.question_context = updated

    reg = registry or build_default_tool_registry()
    research_scope = population_spec_to_research_scope(config.population_spec)
    max_steps = config.max_steps if config.max_steps is not None else config.experiment_budget

    steps = run_research_session(
        graph,
        pop_panel,
        reg,
        initial_experiment_id=eid,
        research_scope=research_scope,
        max_steps=max_steps,
        auto_persist=config.auto_persist,
        persist_dir=data_dir,
    )

    session_path: Optional[Path] = None
    if config.auto_persist and data_dir is not None:
        session_path = write_research_graph(graph, data_dir=data_dir)

    return AutonomousResearchResult(graph=graph, steps=steps, session_path=session_path)


def load_autonomous_research_session(
    session_id: str,
    data_dir: Optional[Path] = None,
) -> ResearchGraph:
    """Reload a persisted autonomous research session."""
    return read_research_graph(session_id, data_dir=data_dir)
