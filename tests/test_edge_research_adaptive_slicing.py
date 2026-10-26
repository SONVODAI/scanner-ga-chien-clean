"""Tests for Phase 3F adaptive slicing, shape discovery, and evidence-driven follow-up."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    generate_action_candidates,
)
from modules.edge_research.research_adaptive_tools import (
    AdaptivePartitionCompareTool,
    ThresholdExplorationTool,
    ThresholdNeighborhoodTool,
    CategoricalAdaptiveCompareTool,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_feature_eligibility import (
    EligibilityError,
    assess_feature_eligibility,
    require_eligible_feature,
)
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_interpreter import (
    GAP_THRESHOLD_EXPLORATION,
    interpret_tool_result,
)
from modules.edge_research.research_outcome_evaluator import (
    compute_outcome_profile,
    outcome_success_mask,
)
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_shape import (
    OBS_SHAPE_FLAT,
    OBS_SHAPE_MONOTONIC_INCREASING,
    interpret_partition_shape,
    shape_suggests_threshold_exploration,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    ResearchQuestionContext,
)
from modules.edge_research.research_tools import build_default_tool_registry

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()


def _targets(t0: str) -> dict:
    ts = pd.Timestamp(t0)
    return {
        "t3_target_date": (ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        "t5_target_date": (ts + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        "t10_target_date": (ts + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    }


def _synthetic_panel(
    *,
    n: int = 40,
    feature_name: str = "feature_x",
    relationship: str = "increasing",
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fx = float(rng.uniform(-2, 2))
        if relationship == "increasing":
            t5 = fx * 3.0 + float(rng.normal(0, 0.5))
        elif relationship == "decreasing":
            t5 = -fx * 3.0 + float(rng.normal(0, 0.5))
        else:
            t5 = float(rng.normal(0, 0.5))
        t3 = t5 * 0.8
        t10 = t5 * 1.1
        rows.append(
            {
                "trade_date": f"2026-08-{(i % 20) + 1:02d}",
                "symbol": f"S{i % 5}",
                feature_name: fx,
                "t3_return": t3,
                "t5_return": t5,
                "t10_return": t10,
                "research_market_state": "STATE_A" if i % 2 == 0 else "STATE_B",
                "partition_group": "G1" if i % 3 == 0 else "G2",
                "rs10": fx,
                **_targets(f"2026-08-{(i % 20) + 1:02d}"),
            }
        )
    return pd.DataFrame(rows)


def _scope(outcome: OutcomeSpec, **extra) -> dict:
    s = {"outcome_spec": outcome.to_dict(), "outcome_spec_hash": outcome.content_hash()}
    s.update(extra)
    return s


def test_outcome_spec_changes_computed_metrics():
    panel = _synthetic_panel(relationship="flat")
    spec_a = OutcomeSpec.compare("t5_return", ">", 0.0)
    spec_b = OutcomeSpec.compare("t5_return", ">", 1.5)
    prof_a = compute_outcome_profile(panel, spec_a, data_cutoff_date=CUTOFF)
    prof_b = compute_outcome_profile(panel, spec_b, data_cutoff_date=CUTOFF)
    assert prof_a.success_rate != prof_b.success_rate
    mask_a = outcome_success_mask(panel, spec_a).sum()
    mask_b = outcome_success_mask(panel, spec_b).sum()
    assert mask_a != mask_b


def test_partition_group_compare_uses_outcome_spec():
    panel = _synthetic_panel(relationship="increasing")
    spec_high = OutcomeSpec.compare("t5_return", ">", 1.0)
    spec_low = OutcomeSpec.compare("t5_return", ">", -5.0)
    tool = REGISTRY.get("partition_group_compare", "v1")
    r_high = tool.execute(
        panel,
        inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
        research_scope=_scope(spec_high),
        data_cutoff_date=CUTOFF,
    )
    r_low = tool.execute(
        panel,
        inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
        research_scope=_scope(spec_low),
        data_cutoff_date=CUTOFF,
    )
    assert r_high.metrics.get("uses_outcome_spec") is True
    assert r_high.metrics.get("baseline_success_rate") != r_low.metrics.get("baseline_success_rate")


def test_adaptive_partition_data_derived_boundaries():
    panel = _synthetic_panel(n=40, feature_name="feature_x", relationship="increasing")
    tool = AdaptivePartitionCompareTool()
    outcome = OutcomeSpec.compare("t5_return", ">", 0.0)
    result = tool.execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(outcome),
        data_cutoff_date=CUTOFF,
    )
    assert result.status.value == "OK"
    assert "discovered_boundaries" in result.metrics
    assert len(result.metrics["discovered_boundaries"]) >= 1
    assert result.metrics.get("outcome_spec_hash") == outcome.content_hash()


def test_increasing_relationship_produces_gradient_shape():
    panel = _synthetic_panel(n=60, feature_name="feature_x", relationship="increasing", seed=1)
    tool = AdaptivePartitionCompareTool()
    result = tool.execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    shape = result.metrics.get("shape", {})
    codes = {o.code for o in result.structured_observations}
    assert (
        shape.get("shape_code")
        in (
            "SHAPE_MONOTONIC_INCREASING",
            "SHAPE_GRADIENT_DETECTED",
            "SHAPE_STEP_CHANGE",
        )
        or OBS_SHAPE_MONOTONIC_INCREASING in codes
    )


def test_decreasing_relationship_shape():
    panel = _synthetic_panel(n=60, feature_name="feature_y", relationship="decreasing", seed=2)
    tool = AdaptivePartitionCompareTool()
    result = tool.execute(
        panel,
        inputs={"feature_column": "feature_y", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    shape = result.metrics.get("shape", {})
    assert shape.get("shape_code") in (
        "SHAPE_MONOTONIC_DECREASING",
        "SHAPE_GRADIENT_DETECTED",
        "SHAPE_STEP_CHANGE",
    )


def test_flat_data_no_strong_gradient():
    panel = _synthetic_panel(n=50, feature_name="feature_x", relationship="flat", seed=3)
    panel["t5_return"] = np.random.default_rng(99).normal(0, 0.2, len(panel))
    panel["t3_return"] = panel["t5_return"] * 0.9
    panel["t10_return"] = panel["t5_return"] * 1.1
    tool = AdaptivePartitionCompareTool()
    result = tool.execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    shape = result.metrics.get("shape", {})
    # Flat noise should not produce strong gradient evidence warranting follow-up.
    from modules.edge_research.research_shape import shape_suggests_threshold_exploration, interpret_partition_shape

    shape_obj = interpret_partition_shape(
        {k: v for k, v in result.groups.items()},
        baseline_rate=result.metrics.get("baseline_success_rate"),
        min_bin_n=5,
    )
    assert not shape_suggests_threshold_exploration(shape_obj) or shape.get("effect_spread", 99) < 25


def test_gradient_enables_threshold_exploration_candidate():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-3f-thresh")
    panel = _synthetic_panel(n=50, relationship="increasing")
    tool = AdaptivePartitionCompareTool()
    scope = _scope(OutcomeSpec.compare("t5_return", ">", 0.0))
    result = tool.execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=scope,
        data_cutoff_date=CUTOFF,
    )
    oid = graph.add_root_observation(description="seed")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=ResearchQuestionContext(
            population_spec=PopulationSpec.all_().to_dict(),
            outcome_spec=OutcomeSpec.compare("t5_return", ">", 0.0).to_dict(),
        ),
    )
    eid = graph.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            inputs={"feature_column": "feature_x"},
            research_scope=scope,
            data_cutoff_date=CUTOFF,
        ),
    )
    graph.attach_experiment_result(eid, metrics=result.metrics_for_experiment(), observations=list(result.structured_observations))
    assessment = interpret_tool_result(graph, eid, result)
    candidates = generate_action_candidates(assessment, graph, REGISTRY, experiment_node_id=eid)
    codes = {c.action_code for c in candidates}
    assert "EXPLORE_THRESHOLD" in codes or GAP_THRESHOLD_EXPLORATION in assessment.information_gaps


def test_threshold_exploration_data_derived_cuts_only():
    panel = _synthetic_panel(n=50, relationship="increasing")
    part = AdaptivePartitionCompareTool().execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    cuts = part.metrics.get("discovered_boundaries") or []
    assert cuts
    tool = ThresholdExplorationTool()
    result = tool.execute(
        panel,
        inputs={
            "feature_column": "feature_x",
            "candidate_cuts": cuts,
            "direction": "high",
            "parent_experiment_id": "exp-test",
        },
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    tested = [c["threshold"] for c in result.groups.get("candidates", [])]
    assert set(tested).issubset(set(cuts))


def test_neighborhood_cuts_tested():
    panel = _synthetic_panel(n=50, relationship="increasing")
    part = AdaptivePartitionCompareTool().execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    cuts = part.metrics.get("discovered_boundaries") or [0.0]
    thresh = ThresholdExplorationTool().execute(
        panel,
        inputs={"feature_column": "feature_x", "candidate_cuts": cuts, "direction": "high"},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    center = thresh.metrics["best_threshold"]["threshold"]
    nb = ThresholdNeighborhoodTool().execute(
        panel,
        inputs={"feature_column": "feature_x", "center_threshold": center, "direction": "high"},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    assert nb.metrics.get("neighbors_tested", 0) >= 1
    assert nb.metrics.get("stability_class") in (
        "ROBUST_REGION",
        "POINT_ESTIMATE_ONLY",
        "UNSTABLE_THRESHOLD",
    )


def test_unstable_threshold_flagged():
    groups = {
        "q1": {"success_rate": 10.0, "n_eligible": 10},
        "q2": {"success_rate": 90.0, "n_eligible": 10},
        "q3": {"success_rate": 15.0, "n_eligible": 10},
    }
    shape = interpret_partition_shape(groups, baseline_rate=50.0, min_bin_n=5)
    assert shape.shape_code in (
        "SHAPE_STEP_CHANGE",
        "SHAPE_EXTREME_BIN_EFFECT",
        "SHAPE_GRADIENT_DETECTED",
        "SHAPE_INVERTED_U",
    )


def test_categorical_separation_refinement_candidate():
    panel = _synthetic_panel(n=40)
    panel["cat_feat"] = ["A"] * 20 + ["B"] * 20
    panel.loc[panel["cat_feat"] == "A", "t5_return"] = 5.0
    panel.loc[panel["cat_feat"] == "B", "t5_return"] = -2.0
    tool = CategoricalAdaptiveCompareTool()
    result = tool.execute(
        panel,
        inputs={"feature_column": "cat_feat", "min_category_n": 5},
        research_scope=_scope(OutcomeSpec.compare("t5_return", ">", 0.0)),
        data_cutoff_date=CUTOFF,
    )
    codes = {o.code for o in result.structured_observations}
    assert "CATEGORY_SEPARATION_DETECTED" in codes or result.metrics.get("category_spread", 0) >= 2


def test_future_leakage_rejected_at_t0():
    with pytest.raises(EligibilityError, match="future_leakage"):
        require_eligible_feature("t3_return", research_scope={}, observation_horizon=0)


def test_later_horizon_allows_matured_outcome_feature():
    assessment = assess_feature_eligibility(
        "t3_return",
        research_scope={"research_observation_horizon": 3},
        observation_horizon=3,
    )
    assert assessment.eligible_at_observation is True
    assert assessment.role == "forward_outcome"


def test_lineage_explains_threshold_exploration():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-lineage-3f")
    panel = _synthetic_panel(n=50, relationship="increasing")
    scope = _scope(OutcomeSpec.compare("t5_return", ">", 0.0))
    part = AdaptivePartitionCompareTool().execute(
        panel,
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=scope,
        data_cutoff_date=CUTOFF,
    )
    oid = graph.add_root_observation(description="seed", node_id="O1")
    q1 = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Partition feature_x?",
        rationale=QuestionRationale(reason_code="SLICING", prior_node_id=oid),
        node_id="Q1",
    )
    e1 = graph.add_experiment(
        question_node_id=q1,
        spec=ExperimentSpec(
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            inputs={"feature_column": "feature_x"},
            research_scope=scope,
            data_cutoff_date=CUTOFF,
        ),
        node_id="E1",
    )
    graph.attach_experiment_result(e1, metrics=part.metrics_for_experiment(), observations=list(part.structured_observations))
    cuts = part.metrics.get("discovered_boundaries") or [0.0]
    q2 = graph.spawn_child_question_from_experiment(
        e1,
        question_text="Explore threshold on feature_x?",
        reason_code="EXPLORE_THRESHOLD",
        evidence_summary={
            "lineage": {
                "triggering_experiment": "E1",
                "triggering_observation": "SHAPE_GRADIENT",
                "discovered_boundaries": cuts,
            },
            "triggering_experiment": "E1",
            "triggering_observation": "SHAPE_GRADIENT",
        },
        node_id="Q2",
    )
    lineage = graph.reconstruct_lineage(q2)
    assert [n.node_id for n in lineage] == ["O1", "Q1", "E1", "Q2"]
    q2_node = graph.get_node(q2)
    assert q2_node.rationale.reason_code == "EXPLORE_THRESHOLD"
    assert q2_node.rationale.evidence_summary.get("triggering_experiment") == "E1"


def test_duplicate_adaptive_experiments_deduplicate():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=5)
    scope = _scope(OutcomeSpec.compare("t5_return", ">", 0.0))
    spec = ExperimentSpec(
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        inputs={"feature_column": "feature_x", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        research_scope=scope,
        data_cutoff_date=CUTOFF,
    )
    oid = graph.add_root_observation(description="s")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="?",
        rationale=QuestionRationale(reason_code="S", prior_node_id=oid),
    )
    e1 = graph.add_experiment(question_node_id=qid, spec=spec)
    with pytest.raises(Exception):
        graph.add_experiment(question_node_id=qid, spec=spec)


def test_budget_terminates_exploration():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=1)
    scope = {}
    oid = graph.add_root_observation(description="s")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="?",
        rationale=QuestionRationale(reason_code="S", prior_node_id=oid),
    )
    spec = ExperimentSpec(
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        inputs={"feature_column": "feature_x"},
        research_scope=scope,
        data_cutoff_date=CUTOFF,
    )
    graph.add_experiment(question_node_id=qid, spec=spec)
    with pytest.raises(Exception):
        graph.add_experiment(
            question_node_id=qid,
            spec=ExperimentSpec(
                tool_name="threshold_exploration",
                tool_version="v1",
                inputs={"feature_column": "feature_x", "candidate_cuts": [0.0]},
                research_scope=scope,
                data_cutoff_date=CUTOFF,
            ),
        )


def test_production_isolation_imports():
    forbidden = PRODUCTION_FORBIDDEN_IMPORTS
    paths = [
        "modules/edge_research/research_adaptive_tools.py",
        "modules/edge_research/research_outcome_evaluator.py",
        "modules/edge_research/research_feature_eligibility.py",
        "modules/edge_research/research_shape.py",
    ]
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        for f in forbidden:
            assert f not in text


def test_shape_suggests_threshold_exploration_helper():
    groups = {
        "q1": {"success_rate": 20.0, "n_eligible": 10},
        "q2": {"success_rate": 40.0, "n_eligible": 10},
        "q3": {"success_rate": 60.0, "n_eligible": 10},
        "q4": {"success_rate": 80.0, "n_eligible": 10},
    }
    shape = interpret_partition_shape(groups, baseline_rate=50.0, min_bin_n=5)
    assert shape_suggests_threshold_exploration(shape)
