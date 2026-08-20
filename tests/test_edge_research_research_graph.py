"""Tests for PATCH 3A research graph + state foundation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.edge_research.research_graph import (
    DuplicateExperimentError,
    ResearchGraph,
    ResearchGraphError,
)
from modules.edge_research.research_state import (
    RESEARCH_GRAPH_SCHEMA_VERSION,
    ExperimentSpec,
    NextActionCandidate,
    NodeStatus,
    NodeType,
    QuestionRationale,
    ResearchGraphSnapshot,
    SessionStatus,
    StructuredResearchObservation,
    compute_experiment_content_hash,
)
from modules.edge_research.storage import (
    list_research_session_ids,
    read_research_graph,
    write_research_graph,
)


def _spec(
    *,
    tool: str = "decompose_date",
    version: str = "v1",
    inputs: dict | None = None,
    scope: dict | None = None,
    cutoff: str = "2026-08-17",
) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version=version,
        inputs=inputs or {"horizon": "T5"},
        research_scope=scope or {"subset": "candidate_rows"},
        data_cutoff_date=cutoff,
    )


# --- Session ---


def test_create_session():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17", experiment_budget=10)
    assert g.session.data_cutoff_date == "2026-08-17"
    assert g.session.experiment_budget == 10
    assert g.session.status == SessionStatus.ACTIVE
    assert g.session.schema_version == RESEARCH_GRAPH_SCHEMA_VERSION


def test_data_cutoff_date_persists():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-01")
    reloaded = ResearchGraph.deserialize(g.serialize())
    assert reloaded.session.data_cutoff_date == "2026-08-01"


def test_data_cutoff_date_cannot_silently_change():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-01")
    with pytest.raises(ResearchGraphError, match="immutable"):
        g.assert_data_cutoff_immutable("2026-08-02")


# --- Lineage ---


def test_add_root_observation():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Unusual pattern detected")
    node = g.get_node(oid)
    assert node.node_type == NodeType.OBSERVATION
    assert oid in g.session.root_node_ids


def test_observation_to_question_lineage():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Is effect date-concentrated?",
        rationale=QuestionRationale(
            reason_code="UNEXPLAINED_MAGNITUDE",
            prior_node_id=oid,
        ),
    )
    assert g.get_node(qid).parent_node_ids == [oid]
    assert qid in g.get_node(oid).child_node_ids


def test_question_to_experiment_lineage():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(question_node_id=qid, spec=_spec())
    assert g.get_node(eid).parent_node_ids == [qid]
    assert eid in g.get_node(qid).child_node_ids


def test_attach_deterministic_result():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(question_node_id=qid, spec=_spec())
    g.attach_experiment_result(
        eid,
        metrics={"largest_date_share": 0.2, "unique_dates": 5},
        observations=[StructuredResearchObservation(code="EFFECT_BROAD", severity="LOW")],
    )
    result = g.get_node(eid).experiment_result
    assert result is not None
    assert result.metrics["unique_dates"] == 5
    assert result.finalized is True


def test_result_survives_serialization_round_trip():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    eid = g.add_experiment(question_node_id=qid, spec=_spec())
    g.attach_experiment_result(eid, metrics={"value": 42})
    reloaded = ResearchGraph.deserialize(g.serialize())
    assert reloaded.get_node(eid).experiment_result.metrics["value"] == 42


def test_experiment_to_child_questions():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    q1 = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q1?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    e1 = g.add_experiment(question_node_id=q1, spec=_spec())
    g.attach_experiment_result(e1, metrics={"flag": True})
    q2 = g.spawn_child_question_from_experiment(
        e1, question_text="Q2?", reason_code="FOLLOW_UP"
    )
    q3 = g.spawn_child_question_from_experiment(
        e1, question_text="Q3?", reason_code="FOLLOW_UP"
    )
    assert q2 in g.get_node(e1).child_node_ids
    assert q3 in g.get_node(e1).child_node_ids


def test_multiple_child_branches():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    q1 = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q1?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    e1 = g.add_experiment(question_node_id=q1, spec=_spec())
    g.attach_experiment_result(e1, metrics={})
    q2 = g.spawn_child_question_from_experiment(e1, question_text="Q2?", reason_code="A")
    q3 = g.spawn_child_question_from_experiment(e1, question_text="Q3?", reason_code="B")
    assert len(g.get_node(e1).child_node_ids) == 2
    assert g.get_node(q2).status == NodeStatus.OPEN
    assert g.get_node(q3).status == NodeStatus.OPEN


def test_multiple_parents_supported():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    o1 = g.add_root_observation(description="A")
    o2 = g.add_root_observation(description="B")
    qid = g.spawn_question(
        parent_node_ids=[o1, o2],
        question_text="Convergent question?",
        rationale=QuestionRationale(reason_code="CONVERGE", prior_node_id=o1),
    )
    assert set(g.get_node(qid).parent_node_ids) == {o1, o2}


def test_abandon_branch_with_reason():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    g.abandon_node(qid, reason="Contradictory evidence")
    assert g.get_node(qid).status == NodeStatus.ABANDONED
    assert g.get_node(qid).terminal_reason == "Contradictory evidence"


def test_abandon_without_reason_rejected():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    with pytest.raises(ResearchGraphError, match="explicit terminal_reason"):
        g.abandon_node(qid, reason="")


def test_parent_child_integrity():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
    )
    g.validate()


def test_invalid_parent_rejected():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    with pytest.raises(ResearchGraphError, match="Unknown node_id"):
        g.spawn_question(
            parent_node_ids=["missing"],
            question_text="Q?",
            rationale=QuestionRationale(reason_code="TEST", prior_node_id="missing"),
        )


def test_cycle_rejected():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    o1 = g.add_root_observation(description="A")
    q1 = g.spawn_question(
        parent_node_ids=[o1],
        question_text="Q1",
        rationale=QuestionRationale(reason_code="T", prior_node_id=o1),
    )
    q2 = g.spawn_question(
        parent_node_ids=[q1],
        question_text="Q2",
        rationale=QuestionRationale(reason_code="T", prior_node_id=q1),
    )
    with pytest.raises(ResearchGraphError, match="cycle"):
        g._link_parent_child(q2, o1)


def test_self_link_rejected():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="A")
    node = g.get_node(oid)
    with pytest.raises(ResearchGraphError, match="Self-link"):
        g._link_parent_child(oid, oid)


def test_open_branches_query():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    q_open = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Open?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    q_dead = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Dead?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    g.abandon_node(q_dead, reason="No signal")
    open_ids = {n.node_id for n in g.list_open_branches()}
    assert q_open in open_ids
    assert q_dead not in open_ids


def test_full_lineage_reconstruction():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Root")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    eid = g.add_experiment(question_node_id=qid, spec=_spec())
    lineage = g.reconstruct_lineage(eid)
    assert [n.node_id for n in lineage] == [oid, qid, eid]


# --- Dedup ---


def test_equivalent_specs_same_content_hash():
    s1 = _spec(inputs={"horizon": "T5", "a": 1})
    s2 = _spec(inputs={"a": 1, "horizon": "T5"})
    assert compute_experiment_content_hash(s1) == compute_experiment_content_hash(s2)


def test_different_inputs_different_hash():
    s1 = _spec(inputs={"horizon": "T5"})
    s2 = _spec(inputs={"horizon": "T10"})
    assert compute_experiment_content_hash(s1) != compute_experiment_content_hash(s2)


def test_different_cutoff_different_hash():
    s1 = _spec(cutoff="2026-08-01")
    s2 = _spec(cutoff="2026-08-02")
    assert compute_experiment_content_hash(s1) != compute_experiment_content_hash(s2)


def test_duplicate_experiment_blocked():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    q1 = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q1?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    spec = _spec()
    g.add_experiment(question_node_id=q1, spec=spec)
    q2 = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q2?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    with pytest.raises(DuplicateExperimentError):
        g.add_experiment(question_node_id=q2, spec=spec)


def test_abandoned_experiment_still_in_dedup_index():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    q1 = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q1?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    spec = _spec()
    e1 = g.add_experiment(question_node_id=q1, spec=spec)
    g.attach_experiment_result(e1, metrics={})
    g.abandon_node(q1, reason="Dead end")
    assert g.has_attempted_experiment(spec)


def test_finalized_result_cannot_mutate():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(description="Pattern")
    qid = g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    eid = g.add_experiment(question_node_id=qid, spec=_spec())
    g.attach_experiment_result(eid, metrics={"a": 1})
    with pytest.raises(ResearchGraphError, match="cannot be mutated"):
        g.attach_experiment_result(eid, metrics={"a": 2})


def test_serialize_deserialize_deterministic():
    g = ResearchGraph.create_session(
        data_cutoff_date="2026-08-17",
        session_id="rs-fixed123456",
        started_at="2026-08-20T00:00:00Z",
    )
    oid = g.add_root_observation(
        description="Pattern",
        node_id="obs-fixed123456",
        created_at="2026-08-20T00:00:01Z",
    )
    s1 = g.serialize()
    s2 = ResearchGraph.deserialize(s1).serialize()
    assert s1 == s2


def test_unknown_schema_version_fails():
    payload = {
        "schema_version": "research_graph_v999",
        "session": {
            "research_session_id": "rs-x",
            "started_at": "2026-08-20T00:00:00Z",
            "data_cutoff_date": "2026-08-17",
            "guardrails_config_version": "guardrails_v1",
            "status": "ACTIVE",
            "root_node_ids": [],
            "experiments_used": 0,
            "schema_version": "research_graph_v999",
        },
        "nodes": {},
        "experiment_index": {},
    }
    with pytest.raises(ValueError, match="Unsupported research graph schema"):
        ResearchGraphSnapshot.from_dict(payload)


def test_no_forward_return_leakage_in_state():
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17")
    oid = g.add_root_observation(
        description="Pattern",
        source_metrics={"incremental_median": 1.5},
    )
    text = g.serialize()
    assert "t3_return" not in text
    assert "t5_return" not in text
    assert "t10_return" not in text
    node = g.get_node(oid)
    assert "t5_return" not in (node.trigger.source_metrics if node.trigger else {})


def test_no_production_coupling():
    from modules.edge_research import contracts

    for mod_name in ("research_graph", "research_state"):
        import importlib
        import inspect

        mod = importlib.import_module(f"modules.edge_research.{mod_name}")
        src = inspect.getsource(mod)
        for forbidden in contracts.PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in src


# --- Storage ---


def test_storage_atomic_write_and_reload(tmp_path):
    data_dir = tmp_path / "edge_research"
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17", session_id="rs-storage01")
    oid = g.add_root_observation(description="Persist me")
    g.spawn_question(
        parent_node_ids=[oid],
        question_text="Q?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=oid),
    )
    write_research_graph(g, data_dir=data_dir)
    assert "rs-storage01" in list_research_session_ids(data_dir=data_dir)
    loaded = read_research_graph("rs-storage01", data_dir=data_dir)
    assert loaded.session.data_cutoff_date == "2026-08-17"
    assert len(loaded.nodes) == 2


def test_storage_does_not_touch_hypothesis_ledger(tmp_path):
    data_dir = tmp_path / "edge_research"
    g = ResearchGraph.create_session(data_cutoff_date="2026-08-17", session_id="rs-ledger01")
    g.add_root_observation(description="X")
    write_research_graph(g, data_dir=data_dir)
    ledger_path = data_dir / "edge_hypothesis_ledger.csv"
    assert ledger_path.exists()
    content = ledger_path.read_text(encoding="utf-8")
    assert "rs-ledger01" not in content


# --- Acceptance scenario (Task N) ---


def test_acceptance_scenario_full_lineage_and_dedup(tmp_path):
    cutoff = "2026-08-17"
    g = ResearchGraph.create_session(
        data_cutoff_date=cutoff,
        session_id="rs-acceptance01",
        started_at="2026-08-20T10:00:00Z",
    )

    o1 = g.add_root_observation(
        description="An unusual empirical pattern was detected.",
        source_metrics={"note": "synthetic"},
        node_id="obs-o1",
        created_at="2026-08-20T10:00:01Z",
    )

    q1 = g.spawn_question(
        parent_node_ids=[o1],
        question_text="Does the pattern survive basic decomposition?",
        rationale=QuestionRationale(
            reason_code="TRIGGERED_BY_OBSERVATION",
            prior_node_id=o1,
            evidence_summary={"observation": "unusual pattern"},
        ),
        node_id="q-q1",
    )

    spec_e1 = _spec(
        tool="basic_decomposition",
        inputs={"check": "initial"},
        scope={"observation_id": o1},
        cutoff=cutoff,
    )
    e1 = g.add_experiment(question_node_id=q1, spec=spec_e1, node_id="exp-e1")
    g.attach_experiment_result(
        e1,
        metrics={"branch_factor": 2},
        observations=[StructuredResearchObservation(code="STRUCTURE_FOUND")],
        candidate_next_actions=[
            NextActionCandidate(action_code="DRILL_DOWN", tool_name="decompose_date"),
            NextActionCandidate(action_code="DRILL_DOWN", tool_name="partition_market"),
        ],
    )

    q2 = g.spawn_child_question_from_experiment(
        e1,
        question_text="Is date concentration explaining the pattern?",
        reason_code="FOLLOW_UP_DECOMPOSITION",
        node_id="q-q2",
    )
    q3 = g.spawn_child_question_from_experiment(
        e1,
        question_text="Is market-state heterogeneity present?",
        reason_code="FOLLOW_UP_DECOMPOSITION",
        node_id="q-q3",
    )

    g.abandon_node(q2, reason="Date concentration too high — branch not viable")

    assert g.get_node(q2).status == NodeStatus.ABANDONED
    assert g.get_node(q3).status == NodeStatus.OPEN

    q_retry = g.spawn_question(
        parent_node_ids=[o1],
        question_text="Retry same experiment?",
        rationale=QuestionRationale(reason_code="RETRY", prior_node_id=o1),
        node_id="q-retry",
    )
    with pytest.raises(DuplicateExperimentError):
        g.add_experiment(question_node_id=q_retry, spec=spec_e1)

    write_research_graph(g, data_dir=tmp_path / "edge_research")
    loaded = read_research_graph("rs-acceptance01", data_dir=tmp_path / "edge_research")

    # Reconstructability checks
    q1_node = loaded.get_node("q-q1")
    assert q1_node.rationale.prior_node_id == o1
    assert q1_node.rationale.reason_code == "TRIGGERED_BY_OBSERVATION"

    exp_for_q1 = [c.node_id for c in loaded.get_children("q-q1")]
    assert "exp-e1" in exp_for_q1

    e1_result = loaded.get_node("exp-e1").experiment_result
    assert e1_result.metrics["branch_factor"] == 2

    children_of_e1 = set(loaded.get_node("exp-e1").child_node_ids)
    assert children_of_e1 == {"q-q2", "q-q3"}

    assert loaded.get_node("q-q2").terminal_reason.startswith("Date concentration")
    assert loaded.get_node("q-q3").status == NodeStatus.OPEN

    assert loaded.has_attempted_experiment(spec_e1)
    assert loaded.session.data_cutoff_date == cutoff

    open_ids = {n.node_id for n in loaded.list_open_branches()}
    assert "q-q3" in open_ids
    assert "q-q2" not in open_ids

    lineage = loaded.reconstruct_lineage("exp-e1")
    assert [n.node_id for n in lineage] == ["obs-o1", "q-q1", "exp-e1"]
