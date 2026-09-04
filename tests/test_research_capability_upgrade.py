"""General research capability upgrade — lifecycle, claim-aligned forward, memory, waiting."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import (
    ExperimentHistoryEntry,
    budget_exhausted,
    scientific_consumption_complete,
    unconsumed_successful_experiments,
)
from modules.edge_research.opr_bridge.claim_aligned_forward import (
    ADJUDICATION_CONTEXT_ONLY,
    ADJUDICATION_DISCONFIRMING,
    ADJUDICATION_LEGACY,
    ADJUDICATION_SUPPORTING,
    CLAIM_CONTRACT_ALIGNED,
    CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
    build_claim_spec,
    evaluate_claim_aligned_metrics,
    freeze_t0_group_membership,
    interpret_claim_aligned_evidence,
)
from modules.edge_research.opr_bridge.production_daily_assessment import _next_pending_horizon
from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import interpret_outcome_evidence
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ForwardEvaluationStatus,
    ForwardHorizonPlaceholder,
    build_forward_evaluation_contract,
)
from modules.edge_research.opr_bridge.production_persistence import OprProductionSessionRecord
from modules.edge_research.opr_bridge.proposition_selection import (
    PropositionCandidate,
    select_proposition_with_memory,
)
from modules.edge_research.opr_bridge.research_memory import (
    PropositionFamilyMemory,
    ResearchMemoryStore,
    proposition_family_key,
    scientific_repeat_reasons,
)

REPO = Path(__file__).resolve().parents[1]


def _session(history):
    return OprProductionSessionRecord(
        session_id="sess-test",
        opportunity_identity="opp",
        replay_identity="replay",
        proposition_id="prop-1",
        proposition_hash="ph",
        data_cutoff_date="2026-08-27",
        evidence_cutoff_hash="eh",
        experiment_history=[e.to_dict() for e in history],
    )


def _consumed_entry(ordinal: int) -> ExperimentHistoryEntry:
    return ExperimentHistoryEntry(
        ordinal=ordinal,
        package={"disposition": "SELECTED", "package_id": f"pkg{ordinal}"},
        frozen_contract={"contract_hash": "c"},
        execution={"execution_outcome": "SUCCESS", "execution_id": f"ex{ordinal}"},
        interpretation={"interpretation_id": f"in{ordinal}"},
        epistemic_update={"resulting_epistemic_state": "SUPPORTED"},
        decision={"decision_kind": "CONTINUE", "decision_envelope_id": f"dec{ordinal}"},
    )


def test_1_last_experiment_finalization_budget_semantics():
    """TEST 1 — start budget=2 must not skip consumption of experiment 2."""
    budget = ResearchBudget(max_experiment_iterations=2)
    e1 = _consumed_entry(1)
    e2 = ExperimentHistoryEntry(
        ordinal=2,
        package={"disposition": "SELECTED", "package_id": "pkg2"},
        execution={"execution_outcome": "SUCCESS", "execution_id": "ex2"},
    )
    record = _session([e1, e2])
    assert unconsumed_successful_experiments(
        [ExperimentHistoryEntry.from_dict(e) for e in record.experiment_history]
    )
    assert budget_exhausted(budget, record) is False

    e2.interpretation = {"interpretation_id": "in2"}
    e2.epistemic_update = {"resulting_epistemic_state": "WEAKENED"}
    e2.decision = {"decision_kind": "STOP", "decision_envelope_id": "dec2"}
    record2 = _session([e1, e2])
    assert scientific_consumption_complete(e2)
    assert budget_exhausted(budget, record2) is True


def test_1_controller_consumes_executed_experiment_two(monkeypatch, tmp_path):
    """TEST 1 — controller interprets/decides experiment 2 before budget stop."""
    from modules.edge_research.opr_bridge import bounded_lifecycle_controller as ctl

    e1 = _consumed_entry(1)
    e2 = ExperimentHistoryEntry(
        ordinal=2,
        package={"disposition": "SELECTED", "package_id": "pkg2"},
        execution={"execution_outcome": "SUCCESS", "execution_id": "ex2"},
    )
    record = _session([e1, e2])
    record.bounded_lifecycle_enabled = True
    record.research_budget = ResearchBudget(max_experiment_iterations=2).to_dict()

    called = {"interpret": 0, "decide": 0}

    def fake_interpret(prop, history, entry, record, *, data_dir=None):
        called["interpret"] += 1
        entry.interpretation = {"interpretation_id": "in2"}
        entry.epistemic_update = {"resulting_epistemic_state": "WEAKENED"}
        return True, None

    def fake_decide(prop, history, entry, record, *, data_dir=None):
        called["decide"] += 1
        entry.decision = {
            "decision_kind": "CONTINUE",
            "decision_envelope_id": "dec2",
        }
        return True, None

    monkeypatch.setattr(ctl, "_run_follow_on_interpret", fake_interpret)
    monkeypatch.setattr(ctl, "_run_follow_on_decide", fake_decide)

    result = ctl.run_bounded_lifecycle_loop(
        {"proposition_id": "prop-1", "scientific_question": "q"},
        pd.DataFrame({"trade_date": ["2026-08-27"], "symbol": ["A"], "rs_spread": [1.0], "t5_return": [0.1]}),
        record,
        budget=ResearchBudget(max_experiment_iterations=2),
        data_dir=tmp_path,
    )
    assert called["interpret"] == 1
    assert called["decide"] == 1
    hist = [ExperimentHistoryEntry.from_dict(e) for e in record.experiment_history]
    exp2 = next(e for e in hist if e.ordinal == 2)
    assert exp2.interpretation is not None
    assert exp2.epistemic_update is not None
    assert exp2.decision is not None
    assert result.experiments_completed == 2
    assert all(e.ordinal <= 2 for e in hist)
    assert result.outcome in ("BUDGET_EXHAUSTED", "SCIENTIFIC_STOP")


def _tier_panel(high_ret: float, low_ret: float, feature_shift: float = 0.0) -> pd.DataFrame:
    rows = []
    for i in range(10):
        feat = -10.0 + i if i < 5 else 10.0 + i
        ret = low_ret if i < 5 else high_ret
        rows.append(
            {
                "trade_date": "2026-08-27",
                "symbol": f"S{i}",
                "rs_spread": feat + feature_shift,
                "t5_return": ret,
            }
        )
    return pd.DataFrame(rows)


def _tier_prop() -> dict:
    return {
        "proposition_id": "prop-tier",
        "scientific_question": "Does feature tier predict differential forward t5_return?",
        "explanatory_relation": {
            "feature_or_contrast": "rs_spread",
            "contrast_direction": "positive",
        },
        "execution_requirements": {
            "required_tool_capabilities": ["partition_group_compare"],
            "partition_column": "rs_spread",
            "n_groups": 5,
        },
        "outcome": {"kind": "compare", "field": "t5_return"},
        "observation_horizon": 0,
        "population_context": {"kind": "all"},
        "canonical_proposition_core": {"uncertainty_codes": ["CROSS_SECTIONAL_DISPERSION"]},
    }


def test_2_claim_aligned_forward_support():
    """TEST 2 — HIGH=-1%, LOW=-5% supports HIGH>LOW even if cohort is negative."""
    panel = _tier_panel(high_ret=-1.0, low_ret=-5.0)
    symbols = tuple(panel["symbol"].astype(str))
    spec = build_claim_spec(
        prop=_tier_prop(),
        panel=panel,
        trade_date="2026-08-27",
        symbols=symbols,
        frozen_contract={
            "contrast_direction": "positive",
            "partition_column": "rs_spread",
            "outcome_field": "t5_return",
            "spread_support_floor": 0.5,
            "expected_direction_rule": "high_quintile_mean > low_quintile_mean",
            "supporting_rule": "high_quintile_mean > low_quintile_mean AND quintile_mean_spread >= 0.5",
            "falsify_strong_rule": "direction_violation AND quintile_mean_spread >= 0.5",
        },
    )
    assert spec["claim_contract_status"] == CLAIM_CONTRACT_ALIGNED
    contract = build_forward_evaluation_contract("obs-support", claim_spec=spec)
    generic, claim, status = evaluate_claim_aligned_metrics(
        panel=panel,
        birth_trade_date="2026-08-27",
        symbols=symbols,
        horizon="T5",
        return_field="t5_return",
        contract=contract,
    )
    assert status == "EVALUATED"
    assert generic["cohort_mean_return"] < 0
    assert claim["metrics"]["high_minus_low"] == pytest.approx(4.0)
    assert claim["metrics"]["signed_contrast"] == pytest.approx(4.0)
    assert claim["adjudication"] == ADJUDICATION_SUPPORTING
    assert claim["support_matched"] is True
    interp = interpret_claim_aligned_evidence(claim_aligned=claim, generic=generic)
    assert interp["adjudicates_proposition"] is True
    assert interp["supports_birth_expectation"] is True


def test_3_claim_aligned_forward_falsification():
    """TEST 3 — HIGH=-5%, LOW=-1% disconfirms HIGH>LOW."""
    panel = _tier_panel(high_ret=-5.0, low_ret=-1.0)
    symbols = tuple(panel["symbol"].astype(str))
    spec = build_claim_spec(
        prop=_tier_prop(),
        panel=panel,
        trade_date="2026-08-27",
        symbols=symbols,
        frozen_contract={
            "contrast_direction": "positive",
            "partition_column": "rs_spread",
            "outcome_field": "t5_return",
            "spread_support_floor": 0.5,
            "expected_direction_rule": "high_quintile_mean > low_quintile_mean",
            "supporting_rule": "high_quintile_mean > low_quintile_mean AND quintile_mean_spread >= 0.5",
            "falsify_strong_rule": "direction_violation AND quintile_mean_spread >= 0.5",
        },
    )
    contract = build_forward_evaluation_contract("obs-falsify", claim_spec=spec)
    generic, claim, _ = evaluate_claim_aligned_metrics(
        panel=panel,
        birth_trade_date="2026-08-27",
        symbols=symbols,
        horizon="T5",
        return_field="t5_return",
        contract=contract,
    )
    assert claim["metrics"]["signed_contrast"] == pytest.approx(-4.0)
    assert claim["adjudication"] == ADJUDICATION_DISCONFIRMING
    assert claim["falsify_matched"] is True
    interp = interpret_claim_aligned_evidence(claim_aligned=claim, generic=generic)
    assert interp["contradicts_birth_expectation"] is True


def test_4_no_hindsight_regrouping():
    """TEST 4 — later feature changes must not regroup T0 membership."""
    t0 = _tier_panel(high_ret=-1.0, low_ret=-5.0, feature_shift=0.0)
    symbols = tuple(t0["symbol"].astype(str))
    frozen = freeze_t0_group_membership(
        t0, trade_date="2026-08-27", feature="rs_spread", symbols=symbols, n_groups=5
    )
    later = t0.copy()
    later["rs_spread"] = -later["rs_spread"]
    later_membership = freeze_t0_group_membership(
        later, trade_date="2026-08-27", feature="rs_spread", symbols=symbols, n_groups=5
    )
    assert frozen != later_membership

    spec = build_claim_spec(
        prop=_tier_prop(),
        panel=t0,
        trade_date="2026-08-27",
        symbols=symbols,
        frozen_contract={
            "contrast_direction": "positive",
            "partition_column": "rs_spread",
            "outcome_field": "t5_return",
            "spread_support_floor": 0.5,
        },
    )
    contract = build_forward_evaluation_contract("obs-pit", claim_spec=spec)
    _, claim, _ = evaluate_claim_aligned_metrics(
        panel=later,
        birth_trade_date="2026-08-27",
        symbols=symbols,
        horizon="T5",
        return_field="t5_return",
        contract=contract,
    )
    assert claim["metrics"]["high_minus_low"] == pytest.approx(4.0)
    assert spec["frozen_group_membership"] == frozen


def test_5_generic_cohort_return_is_context_only():
    """TEST 5 — negative whole-cohort mean must not falsify a relative claim."""
    contract = build_forward_evaluation_contract("obs-legacy")
    assert contract.claim_contract_status == "LEGACY_INSUFFICIENT_CLAIM_SPEC"
    generic = {
        "horizon": "T5",
        "return_field": "t5_return",
        "cohort_mean_return": -1.259,
        "cohort_median_return": -1.279,
        "cohort_size": 142,
        "positive_fraction": 0.2324,
    }
    claim = {
        "claim_family": CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
        "claim_contract_status": "LEGACY_INSUFFICIENT_CLAIM_SPEC",
        "adjudication": ADJUDICATION_LEGACY,
        "adjudicates_proposition": False,
        "reason": "legacy_contract_insufficient_claim_specification",
        "metrics": {},
    }
    interp = interpret_claim_aligned_evidence(claim_aligned=claim, generic=generic)
    assert interp["generic_cohort_role"] == ADJUDICATION_CONTEXT_ONLY
    assert interp["adjudicates_proposition"] is False
    assert interp["supports_birth_expectation"] is None
    assert interp["contradicts_birth_expectation"] is None

    birth = SimpleNamespace(
        final_epistemic_state="SUPPORTED",
        strongest_evidence={"direction": "SUPPORTING"},
        forward_evaluation_contract=contract,
    )
    outcome = SimpleNamespace(
        horizon="T5",
        outcome_record_id="out-1",
        evaluation_status=ForwardEvaluationStatus.EVALUATED.value,
        realized_outcomes={**generic, "claim_aligned": claim},
    )
    live = interpret_outcome_evidence(birth=birth, outcome=outcome)
    assert live["contradicts_birth_expectation"] is None
    assert live["supports_birth_expectation"] is None
    assert "generic_cohort_return_context_only" in live["rationale_keys"]


def _candidate(feature: str, outcome: str, surprise: float, source: str = "alternative_anchor") -> PropositionCandidate:
    rec = SimpleNamespace(
        scientific_question=f"Does {feature} tier predict {outcome}?",
        proposition_id=f"prop-{feature}-{outcome}",
    )
    ident = {
        "feature": feature,
        "outcome": outcome,
        "horizon": 0,
        "population_kind": "all",
        "claim_family": CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
        "directional_claim": "positive",
        "scientific_question": rec.scientific_question,
    }
    key = proposition_family_key(
        feature=feature,
        outcome=outcome,
        horizon=0,
        population_kind="all",
        claim_family=CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
    )
    return PropositionCandidate(
        record=rec,
        family_key=key,
        feature=feature,
        outcome=outcome,
        focal_date="2026-08-27",
        surprise_strength=surprise,
        identity_fields=ident,
        source=source,
    )


def test_6_research_memory_penalizes_redundant_repetition():
    """TEST 6 — redundant family loses to a novel family."""
    repeat = _candidate("feat_a", "t5_return", surprise=3.0, source="default_pipeline")
    novel = _candidate("feat_b", "t5_return", surprise=2.5)
    memory = ResearchMemoryStore()
    memory.upsert(
        PropositionFamilyMemory(
            family_key=repeat.family_key,
            feature="feat_a",
            outcome="t5_return",
            horizon=0,
            population_kind="all",
            claim_family=CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
            episode_count=2,
            tested_episode_dates=["2026-08-24", "2026-08-27"],
            support_count=1,
            last_epistemic_state="SUPPORTED",
            observation_ids=["obs-old"],
            forward_validation_history=[{"adjudication": "CLAIM_SUPPORTING"}],
        )
    )
    selected, provenance = select_proposition_with_memory(
        default_candidate=repeat,
        alternatives=[novel],
        memory=memory,
        cutoff_date="2026-08-27",
    )
    assert selected.family_key == novel.family_key
    assert "NOVEL_FAMILY" in provenance.scientific_reasons
    assert any(r.get("feature") == "feat_a" for r in provenance.rejected)


def test_7_scientific_replication_allowed_with_provenance():
    """TEST 7 — same family may be reselected for an explicit scientific reason."""
    same = _candidate("feat_a", "t5_return", surprise=3.0, source="default_pipeline")
    memory = ResearchMemoryStore()
    memory.upsert(
        PropositionFamilyMemory(
            family_key=same.family_key,
            feature="feat_a",
            outcome="t5_return",
            horizon=0,
            population_kind="all",
            claim_family=CLAIM_FAMILY_CROSS_SECTIONAL_TIER,
            episode_count=1,
            tested_episode_dates=["2026-08-24"],
            unresolved_count=1,
            surviving_nulls=["market_level_confound"],
            contradiction_count=1,
            last_epistemic_state="UNRESOLVED",
            observation_ids=["obs-old"],
        )
    )
    reasons = scientific_repeat_reasons(memory.lookup(same.family_key), cutoff_date="2026-09-03")
    assert "NEW_INDEPENDENT_EPISODE" in reasons
    assert "UNRESOLVED_NULL" in reasons
    assert "CONTRADICTION" in reasons
    selected, provenance = select_proposition_with_memory(
        default_candidate=same,
        alternatives=[],
        memory=memory,
        cutoff_date="2026-09-03",
    )
    assert selected.family_key == same.family_key
    assert any(
        r in provenance.scientific_reasons
        for r in ("NEW_INDEPENDENT_EPISODE", "UNRESOLVED_NULL", "CONTRADICTION", "ROBUSTNESS_REPLICATION")
    )
    assert "why" in provenance.why_selected.lower() or "because" in provenance.why_selected.lower()


def test_8_waiting_horizon_excludes_released_t3():
    """TEST 8 — future voice must not wait for an already released T3."""
    birth = SimpleNamespace(
        forward_horizons=(
            ForwardHorizonPlaceholder(
                horizon="T3",
                status="PENDING_FUTURE",
                eligible_evaluation_date="2026-08-27",
                realized_outcome=None,
            ),
            ForwardHorizonPlaceholder(
                horizon="T5",
                status="PENDING_FUTURE",
                eligible_evaluation_date="2026-08-29",
                realized_outcome=None,
            ),
        )
    )
    released = [
        SimpleNamespace(horizon="T3", evaluation_status=ForwardEvaluationStatus.EVALUATED.value)
    ]
    horizon, date = _next_pending_horizon(birth, "2026-09-03", released)
    assert horizon == "T5"
    assert date == "2026-08-29"
    waiting = f"Waiting for {horizon} eligible on {date}"
    assert "Waiting for T3" not in waiting


def test_9_research_only_safety():
    """TEST 9 — no new BUY/SELL authority path."""
    assert DEFAULT_SHADOW_AUTHORITY.research_only is True
    assert DEFAULT_SHADOW_AUTHORITY.trading_authority is False
    assert DEFAULT_SHADOW_AUTHORITY.buy_signal is False
    assert DEFAULT_SHADOW_AUTHORITY.sell_signal is False
    forbidden_imports = {
        "decision_engine",
        "position_guardian",
        "final_decision_engine",
        "brain_optimizer",
    }
    new_files = [
        REPO / "modules/edge_research/opr_bridge/research_memory.py",
        REPO / "modules/edge_research/opr_bridge/proposition_selection.py",
        REPO / "modules/edge_research/opr_bridge/claim_aligned_forward.py",
    ]
    for path in new_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden_imports
                assert "BUY" not in node.module and "SELL" not in node.module


def test_legacy_contract_does_not_fabricate_claim_fields():
    contract = build_forward_evaluation_contract("obs-old")
    assert contract.record_version == "forward_evaluation_contract_v1_3k0"
    assert contract.claim_spec == {}
    assert contract.claim_contract_status == "LEGACY_INSUFFICIENT_CLAIM_SPEC"
    panel = _tier_panel(-1.0, -5.0)
    generic, claim, _ = evaluate_claim_aligned_metrics(
        panel=panel,
        birth_trade_date="2026-08-27",
        symbols=tuple(panel["symbol"].astype(str)),
        horizon="T5",
        return_field="t5_return",
        contract=contract,
    )
    assert generic is not None
    assert claim["adjudication"] == ADJUDICATION_LEGACY
    assert claim["metrics"] == {}
