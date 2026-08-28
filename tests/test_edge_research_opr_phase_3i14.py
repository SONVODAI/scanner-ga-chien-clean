"""Tests for Phase 3I.14 automatic lifecycle synthesis hook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pandas as pd
import pytest

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import BB_EPISTEMIC_01_CASES, GENERALIZATION_CASES, run_case
from modules.edge_research.opr_bridge.interpretation_contract import build_interpretation_contract
from modules.edge_research.opr_bridge.lifecycle_records import QuintileMetrics
from modules.edge_research.opr_bridge.lifecycle_runner import extract_frozen_proposition_from_3i5, run_minimal_lifecycle
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import (
    ACTION_RECORDED_ONLY,
    AUTHORITY_KNOWLEDGE_STATE,
    AUTHORITY_RESEARCH_PRIORITY,
    LifecycleKnowledgeState,
    attach_synthesis_to_lifecycle_result,
    bootstrap_knowledge_state_from_lineage,
    on_epistemic_update_completed,
)
from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
from modules.edge_research.opr_bridge.synthesis_integration import replay_synthesis_at_cutoff, update_proposition_knowledge_state, verify_frozen_engine_integrity
from modules.edge_research.opr_bridge.synthesis_integration_fixtures import ABSTRACT_INTEGRATION_FIXTURES
from modules.edge_research.research_tools import ToolResult, ToolStatus

REPO = Path(__file__).resolve().parents[1]
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
I313_T1 = REPO / "diagnostics/phase_3i13_lifecycle_synthesis_integration/artifacts/04_real_t1_replay.json"


@pytest.mark.parametrize("fixture", [f for f in ABSTRACT_INTEGRATION_FIXTURES if not f.get("skip_direct")], ids=lambda f: f["fixture_id"])
def test_hook_abstract_end_to_end(fixture: Dict[str, Any]):
    state = LifecycleKnowledgeState(fixture["proposition"]["proposition_id"])
    last_outcome = None
    for ev in fixture["events"]:
        epu = ev["epistemic_update"]
        state, last_outcome = on_epistemic_update_completed(
            fixture["proposition"],
            epu,
            ev["experiment_spec"],
            ev["experiment_ref"],
            ev["tool_result_hash"],
            interpretation=ev.get("interpretation"),
            lineage_metadata=ev.get("lineage_metadata"),
            knowledge_state=state,
            deterministic_replay=True,
        )
    assert last_outcome is not None
    assert last_outcome.integration_status == "SUCCESS"
    assert last_outcome.action_disposition == ACTION_RECORDED_ONLY


def test_hook_idempotency():
    fixture = ABSTRACT_INTEGRATION_FIXTURES[0]
    ev = fixture["events"][0]
    state = LifecycleKnowledgeState(fixture["proposition"]["proposition_id"])
    state, o1 = on_epistemic_update_completed(
        fixture["proposition"],
        ev["epistemic_update"],
        ev["experiment_spec"],
        ev["experiment_ref"],
        ev["tool_result_hash"],
        knowledge_state=state,
        deterministic_replay=True,
    )
    state, o2 = on_epistemic_update_completed(
        fixture["proposition"],
        ev["epistemic_update"],
        ev["experiment_spec"],
        ev["experiment_ref"],
        ev["tool_result_hash"],
        knowledge_state=state,
        deterministic_replay=True,
    )
    assert o1.synthesis.synthesis_hash == o2.synthesis.synthesis_hash
    assert len(state.evidence_events) == 1


def test_hook_temporal_causality():
    prop, events = load_real_lifecycle_events()
    state = LifecycleKnowledgeState(prop["proposition_id"])
    e1 = events[0]
    state, o1 = on_epistemic_update_completed(
        prop,
        e1["epistemic_update"],
        e1["experiment_spec"],
        e1["experiment_ref"],
        e1["tool_result_hash"],
        interpretation=e1.get("interpretation"),
        knowledge_state=state,
        deterministic_replay=True,
    )
    syn1_hash = o1.synthesis.synthesis_hash
    e2 = events[1]
    state, o2 = on_epistemic_update_completed(
        prop,
        e2["epistemic_update"],
        e2["experiment_spec"],
        e2["experiment_ref"],
        e2["tool_result_hash"],
        lineage_metadata=e2.get("lineage_metadata"),
        knowledge_state=state,
        deterministic_replay=True,
    )
    assert len(o1.synthesis.evidence_ids) == 1
    assert events[1]["epistemic_update"]["update_id"] not in o1.synthesis.evidence_ids
    assert state.synthesis_history[0]["synthesis_hash"] == syn1_hash
    assert o2.synthesis.synthesis_hash != syn1_hash


def test_hook_failure_isolation_preserves_epu():
    prop = ABSTRACT_INTEGRATION_FIXTURES[0]["proposition"]
    ev = ABSTRACT_INTEGRATION_FIXTURES[0]["events"][0]
    state = LifecycleKnowledgeState(prop["proposition_id"])
    with patch(
        "modules.edge_research.opr_bridge.synthesis_integration.synthesize_evidence",
        side_effect=RuntimeError("synthesis boom"),
    ):
        state, outcome = on_epistemic_update_completed(
            prop,
            ev["epistemic_update"],
            ev["experiment_spec"],
            ev["experiment_ref"],
            ev["tool_result_hash"],
            knowledge_state=state,
        )
    assert outcome.integration_status == "SYNTHESIS_FAILED"
    assert outcome.priority is None
    assert len(state.evidence_events) == 1


def test_frozen_engine_unchanged():
    assert verify_frozen_engine_integrity()["passed"]


@pytest.mark.parametrize("case", BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES, ids=lambda c: c["case_id"])
def test_bb_regression(case):
    syn, dec = run_case(case)
    assert syn.synthesized_epistemic_state in case["expected_states"]
    assert dec.chosen_priority_action in case["expected_actions"]


def test_frozen_epu1_replay_matches_3i13():
    prop, events = load_real_lifecycle_events()
    state = LifecycleKnowledgeState(prop["proposition_id"])
    e1 = events[0]
    _, o1 = on_epistemic_update_completed(
        prop,
        e1["epistemic_update"],
        e1["experiment_spec"],
        e1["experiment_ref"],
        e1["tool_result_hash"],
        interpretation=e1.get("interpretation"),
        knowledge_state=state,
        deterministic_replay=True,
    )
    t1_ref = replay_synthesis_at_cutoff(prop, events, 1, deterministic_replay=True)
    assert o1.synthesis.synthesized_epistemic_state == t1_ref.synthesis.synthesized_epistemic_state
    assert o1.priority.chosen_priority_action == t1_ref.priority.chosen_priority_action
    if I313_T1.exists():
        ref = json.loads(I313_T1.read_text())
        assert o1.synthesis.synthesized_epistemic_state == ref["synthesis"]["synthesized_epistemic_state"]


def test_frozen_epu2_replay_matches_3i13():
    prop, events = load_real_lifecycle_events()
    lineage = json.loads((I37 / "09_append_only_lineage.json").read_text())
    state = bootstrap_knowledge_state_from_lineage(prop, lineage, deterministic_replay=True)
    e2 = events[1]
    _, o2 = on_epistemic_update_completed(
        prop,
        e2["epistemic_update"],
        e2["experiment_spec"],
        e2["experiment_ref"],
        e2["tool_result_hash"],
        lineage_metadata=e2.get("lineage_metadata"),
        knowledge_state=state,
        deterministic_replay=True,
    )
    t2_ref = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)
    assert o2.synthesis.synthesized_epistemic_state == t2_ref.synthesis.synthesized_epistemic_state
    assert o2.priority.chosen_priority_action == t2_ref.priority.chosen_priority_action
    rel_e2 = o2.synthesis.relationship_map.get(e2["epistemic_update"]["update_id"])
    assert rel_e2 == "PARTIAL_REPLICATION"


def test_decision_conflict_surfaces_multi_evidence_priority():
    case = next(c for c in BB_EPISTEMIC_01_CASES if c["case_id"] == "BE-11")
    _, pri = run_case(case)
    assert pri.chosen_priority_action in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED")


def test_source_of_authority():
    fixture = ABSTRACT_INTEGRATION_FIXTURES[0]
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"], deterministic_replay=True)
    result = attach_synthesis_to_lifecycle_result({}, outcome, LifecycleKnowledgeState("p"))
    assert result["source_of_authority"]["proposition_knowledge_state"] == AUTHORITY_KNOWLEDGE_STATE
    assert result["source_of_authority"]["research_priority"] == AUTHORITY_RESEARCH_PRIORITY
    assert result["source_of_authority"]["immediate_decision_overrides_priority"] is False


def test_no_auto_execution_on_priority():
    fixture = ABSTRACT_INTEGRATION_FIXTURES[0]
    state = LifecycleKnowledgeState(fixture["proposition"]["proposition_id"])
    ev = fixture["events"][0]
    _, outcome = on_epistemic_update_completed(
        fixture["proposition"],
        ev["epistemic_update"],
        ev["experiment_spec"],
        ev["experiment_ref"],
        ev["tool_result_hash"],
        knowledge_state=state,
        deterministic_replay=True,
    )
    assert outcome.action_disposition == ACTION_RECORDED_ONLY


def test_lifecycle_runner_auto_synthesis():
    replay = REPO / "diagnostics/phase_3i5_observation_prioritization/artifacts/02_counterfactual_replay.json"
    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    if not replay.exists() or not panel_path.exists():
        pytest.skip("frozen artifacts unavailable")
    prop = extract_frozen_proposition_from_3i5(replay)
    panel = pd.read_csv(panel_path)
    contract = build_interpretation_contract(prop)
    tr = ToolResult(
        tool_name="partition_group_compare",
        tool_version="v1",
        data_cutoff_date="2026-08-17",
        input_hash="test",
        sample_size=6106,
        status=ToolStatus.OK,
        metrics={"outcome_spread": 100.0, "uses_outcome_spec": True},
        groups={},
    )
    qm = QuintileMetrics(
        quintile_means=(1, 2, 3, 4, 5),
        quintile_ns=(10, 10, 10, 10, 10),
        low_quintile_mean=1,
        high_quintile_mean=5,
        quintile_mean_spread=2.5,
        low_high_delta=4,
        sample_size=6106,
    )
    result = run_minimal_lifecycle(
        prop,
        panel,
        experiment_ref="hook_test_001",
        prebuilt_tool_result=tr,
        prebuilt_quintile_metrics=qm,
        interpretation_contract=contract,
        deterministic_synthesis_replay=True,
    )
    assert result.get("synthesis_status") == "SUCCESS"
    assert result.get("action_disposition") == ACTION_RECORDED_ONLY
    assert "evidence_synthesis" in result
    assert "research_priority_decision" in result


def test_no_proposition_wiring_in_hook():
    from modules.edge_research.opr_bridge import lifecycle_synthesis_hook as hook

    src = Path(hook.__file__).read_text()
    for tok in ("prop-efb650d9bd5c451f", "bdd77912", "5964", "6106"):
        assert tok not in src
