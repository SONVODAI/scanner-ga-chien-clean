"""Tests for Phase 3I.13 lifecycle evidence-synthesis integration."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import (
    BB_EPISTEMIC_01_CASES,
    GENERALIZATION_CASES,
    run_case,
)
from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
from modules.edge_research.opr_bridge.real_ledger_adapter import apply_real_ledger_diagnostic, load_real_lifecycle_events
from modules.edge_research.opr_bridge.synthesis_integration import (
    ACTION_RECORDED_ONLY,
    FROZEN_ENGINE_HASH,
    INTEGRATION_VERSION,
    replay_full_synthesis_history,
    replay_synthesis_at_cutoff,
    update_proposition_knowledge_state,
    verify_frozen_engine_integrity,
)
from modules.edge_research.opr_bridge.synthesis_integration_fixtures import ABSTRACT_INTEGRATION_FIXTURES

REPO = Path(__file__).resolve().parents[1]
I312 = REPO / "diagnostics/phase_3i12_evidence_synthesis/artifacts/06_real_ledger_diagnostic.json"


@pytest.fixture(scope="module")
def real_prop_and_events():
    return load_real_lifecycle_events()


def test_frozen_engine_hash_unchanged():
    audit = verify_frozen_engine_integrity()
    assert audit["passed"], f"Engine hash changed: {audit['current_hash']}"
    assert audit["current_hash"] == FROZEN_ENGINE_HASH


@pytest.mark.parametrize("fixture", [f for f in ABSTRACT_INTEGRATION_FIXTURES if not f.get("skip_direct")], ids=lambda f: f["fixture_id"])
def test_abstract_integration_fixtures(fixture: Dict[str, Any]):
    outcome = update_proposition_knowledge_state(
        fixture["proposition"],
        fixture["events"],
        deterministic_replay=True,
    )
    assert outcome.integration_status == "SUCCESS"
    assert outcome.action_disposition == ACTION_RECORDED_ONLY
    assert outcome.synthesis is not None
    assert outcome.priority is not None
    if "expected_state" in fixture:
        assert outcome.synthesis.synthesized_epistemic_state == fixture["expected_state"]
    if "expected_state_in" in fixture:
        assert outcome.synthesis.synthesized_epistemic_state in fixture["expected_state_in"]
    if fixture.get("expect_relationship") and len(fixture["events"]) > 1:
        eid2 = fixture["events"][1]["epistemic_update"]["update_id"]
        assert outcome.synthesis.relationship_map[eid2] == fixture["expect_relationship"]
    if fixture.get("expect_relationship_in") and len(fixture["events"]) > 1:
        eid2 = fixture["events"][1]["epistemic_update"]["update_id"]
        assert outcome.synthesis.relationship_map[eid2] in fixture["expect_relationship_in"]


def test_correlated_support_not_independent_upgrade():
    fixture = next(f for f in ABSTRACT_INTEGRATION_FIXTURES if f["fixture_id"] == "INT-B")
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"], deterministic_replay=True)
    eid2 = fixture["events"][1]["epistemic_update"]["update_id"]
    assert outcome.synthesis.relationship_map[eid2] in (
        "PARTIAL_REPLICATION",
        "EXACT_REPLICATION",
        "REPRESENTATION_REPLICATION",
        "RELATED_EVIDENCE",
    )
    assert outcome.synthesis.synthesized_epistemic_state == "SUPPORTED"
    assert len(outcome.synthesis.supporting_structure) == 2


def test_temporal_causality_no_future_leakage(real_prop_and_events):
    prop, events = real_prop_and_events
    t1 = replay_synthesis_at_cutoff(prop, events, 1, deterministic_replay=True)
    t2 = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)

    assert t1.integration_status == "SUCCESS"
    assert t2.integration_status == "SUCCESS"
    assert len(t1.synthesis.evidence_ids) == 1
    assert len(t2.synthesis.evidence_ids) == 2
    e2_id = events[1]["epistemic_update"]["update_id"]
    assert e2_id not in t1.synthesis.evidence_ids
    assert e2_id in t2.synthesis.relationship_map


def test_synthesis_history_append_only(real_prop_and_events):
    prop, events = real_prop_and_events
    history = replay_full_synthesis_history(prop, events, deterministic_replay=True)
    assert len(history) == 2
    assert history[0].synthesis_history_index == 1
    assert history[1].synthesis_history_index == 2
    assert history[0].synthesis.synthesis_hash != history[1].synthesis.synthesis_hash
    assert history[0].synthesis is not None
    assert history[1].synthesis is not None


def test_deterministic_replay_same_hashes(real_prop_and_events):
    prop, events = real_prop_and_events
    a = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)
    b = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)
    assert a.synthesis.synthesis_hash == b.synthesis.synthesis_hash
    assert a.priority.record_hash == b.priority.record_hash


def test_action_recorded_only_no_execution():
    fixture = ABSTRACT_INTEGRATION_FIXTURES[0]
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"])
    assert outcome.action_disposition == ACTION_RECORDED_ONLY
    assert outcome.lineage_extension.get("action_disposition") == ACTION_RECORDED_ONLY


def test_failure_isolation_preserves_epu():
    prop = ABSTRACT_INTEGRATION_FIXTURES[0]["proposition"]
    bad_event = [{"epistemic_update": {"update_id": "x"}}]  # malformed
    outcome = update_proposition_knowledge_state(prop, bad_event)
    assert outcome.integration_status == "SYNTHESIS_FAILED"
    assert outcome.priority is None
    assert outcome.action_disposition is None


def test_invalid_evidence_preserved_in_ledger():
    fixture = next(f for f in ABSTRACT_INTEGRATION_FIXTURES if f["fixture_id"] == "INT-E")
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"], deterministic_replay=True)
    invalid = [x for x in outcome.synthesis.invalid_non_informative if x["evidence_id"] == "epu-e2"]
    assert len(invalid) == 1
    assert outcome.synthesis.synthesized_epistemic_state == "SUPPORTED"


def test_non_informative_not_counted_as_support():
    fixture = next(f for f in ABSTRACT_INTEGRATION_FIXTURES if f["fixture_id"] == "INT-F")
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"], deterministic_replay=True)
    assert len(outcome.synthesis.supporting_structure) == 1


def test_contradiction_integration():
    fixture = next(f for f in ABSTRACT_INTEGRATION_FIXTURES if f["fixture_id"] == "INT-D")
    history = replay_full_synthesis_history(fixture["proposition"], fixture["events"], deterministic_replay=True)
    assert history[0].synthesis.synthesized_epistemic_state == "SUPPORTED"
    assert history[1].synthesis.synthesized_epistemic_state in ("CONFLICTED", "FALSIFIED", "WEAKENED")
    assert len(history[0].synthesis.contradiction_structure) == 0
    assert history[0].synthesis.synthesis_hash != history[1].synthesis.synthesis_hash


def test_falsified_preserved_on_later_support():
    fixture = next(f for f in ABSTRACT_INTEGRATION_FIXTURES if f["fixture_id"] == "INT-H")
    outcome = update_proposition_knowledge_state(fixture["proposition"], fixture["events"], deterministic_replay=True)
    assert outcome.synthesis.synthesized_epistemic_state == "FALSIFIED"


@pytest.mark.parametrize("case", BB_EPISTEMIC_01_CASES + GENERALIZATION_CASES, ids=lambda c: c["case_id"])
def test_bb_epistemic_01_regression_unchanged(case: Dict[str, Any]):
    synthesis, decision = run_case(case)
    assert synthesis.synthesized_epistemic_state in case["expected_states"]
    assert decision.chosen_priority_action in case["expected_actions"]


def test_real_t1_replay(real_prop_and_events):
    prop, events = real_prop_and_events
    t1 = replay_synthesis_at_cutoff(prop, events, 1, deterministic_replay=True)
    assert t1.synthesis.synthesized_epistemic_state == "SUPPORTED"
    assert t1.priority.chosen_priority_action in (
        "SEEK_FALSIFICATION",
        "SEEK_REPLICATION",
        "HOLD_UNRESOLVED",
    )
    assert "directional_effect_full_universe" in t1.synthesis.uncertainty_covered


def test_real_t2_equivalent_to_3i12_diagnostic(real_prop_and_events):
    prop, events = real_prop_and_events
    t2 = replay_synthesis_at_cutoff(prop, events, 2, deterministic_replay=True)
    diag = apply_real_ledger_diagnostic()

    assert t2.synthesis.synthesized_epistemic_state == diag["synthesis"]["synthesized_epistemic_state"]
    assert t2.priority.chosen_priority_action == diag["research_priority_decision"]["chosen_priority_action"]
    e2_id = events[1]["epistemic_update"]["update_id"]
    assert t2.synthesis.relationship_map[e2_id] == diag["relationship_e1_to_e2"]
    assert t2.synthesis.saturation_assessment["level"] == diag["synthesis"]["saturation_assessment"]["level"]


def test_no_proposition_specific_wiring_in_builder_source():
    from modules.edge_research.opr_bridge import evidence_ledger_builder as elb

    src = Path(elb.__file__).read_text()
    forbidden = ["prop-efb650d9bd5c451f", "bdd77912", "5964", "6106"]
    for tok in forbidden:
        assert tok not in src


def test_no_trading_coupling_in_integration_source():
    from modules.edge_research.opr_bridge import synthesis_integration as si

    src = Path(si.__file__).read_text().lower()
    for tok in ("buy", "sell", "nav", "market_first", "earning"):
        assert tok not in src
