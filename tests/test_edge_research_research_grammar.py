"""Tests for PATCH 3E OutcomeSpec + PopulationSpec grammar."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from modules.edge_research.research_grammar import (
    GrammarValidationError,
    OutcomeSpec,
    PopulationSpec,
    apply_population_spec,
    compute_spec_hash,
    evaluate_outcome_spec,
    outcome_specs_equal,
    parse_outcome_spec,
    parse_population_spec,
    population_spec_to_research_scope,
    population_specs_equal,
    propose_outcome_reframes,
    propose_population_refinements,
    validate_outcome_spec,
    validate_population_spec,
)
from modules.edge_research.research_tools import apply_research_cutoff


def _panel() -> pd.DataFrame:
    rows = []
    for i in range(4):
        rows.append(
            {
                "trade_date": f"2026-08-{i + 1:02d}",
                "symbol": f"S{i}",
                "t3_return": 1.0 + i,
                "t5_return": 2.0 + i,
                "t10_return": 3.0 + i,
                "rs10": float(i - 1),
                "research_market_state": "EARLY_RECOVERY",
                "partition_group": "A" if i % 2 == 0 else "B",
                "t3_target_date": f"2026-08-{i + 4:02d}",
                "t5_target_date": f"2026-08-{i + 6:02d}",
                "t10_target_date": f"2026-08-{i + 11:02d}",
            }
        )
    return pd.DataFrame(rows)


def test_outcome_spec_compare_and_compose():
    a = OutcomeSpec.compare("t5_return", ">", 0.0)
    b = OutcomeSpec.compare("t10_return", ">", 0.0)
    composed = OutcomeSpec.and_(a, b)
    validate_outcome_spec(composed)
    row = _panel().iloc[0]
    assert evaluate_outcome_spec(composed, row) is True


def test_outcome_spec_persist_continuation_reversal():
    persist = OutcomeSpec.persist("t3_return", ">", 0.0, ("T3", "T5"))
    validate_outcome_spec(persist)
    cont = OutcomeSpec.continuation("T3", "T5", ">", 0.0)
    validate_outcome_spec(cont)
    rev = OutcomeSpec.reversal("T3", "T5", 1.0, -1.0)
    validate_outcome_spec(rev)


def test_outcome_spec_not():
    inner = OutcomeSpec.compare("t5_return", "<", 0.0)
    spec = OutcomeSpec.not_(inner)
    validate_outcome_spec(spec)
    row = _panel().iloc[0]
    assert evaluate_outcome_spec(spec, row) is True


def test_outcome_spec_rejects_invalid_field():
    bad = OutcomeSpec.compare("rs10", ">", 0.0)
    with pytest.raises(GrammarValidationError, match="not allowed"):
        validate_outcome_spec(bad)


def test_outcome_spec_rejects_arbitrary_expression():
    bad = OutcomeSpec(kind="eval", outcome_field="__import__('os')")
    with pytest.raises(GrammarValidationError):
        validate_outcome_spec(bad)


def test_population_spec_all_and_filter():
    pop_all = PopulationSpec.all_()
    validate_population_spec(pop_all)
    filt = PopulationSpec.filter_numeric("rs10", ">", 0.0)
    refined = PopulationSpec.refine(
        pop_all,
        filt,
        reason_code="TEST_REFINE",
        triggering_evidence={"code": "SIGNAL"},
    )
    validate_population_spec(refined)
    panel, _ = apply_research_cutoff(_panel(), "2026-08-20", horizons=["T3", "T5", "T10"])
    filtered, n = apply_population_spec(panel, refined)
    assert n == 2
    assert len(filtered) == 2


def test_population_spec_rejects_forward_field():
    bad = PopulationSpec.filter_numeric("t3_return", ">", 0.0)
    with pytest.raises(GrammarValidationError, match="not allowed"):
        validate_population_spec(bad)


def test_population_spec_categorical():
    cat = PopulationSpec.filter_categorical("partition_group", ["A"])
    validate_population_spec(cat)
    panel, _ = apply_research_cutoff(_panel(), "2026-08-20", horizons=["T3", "T5", "T10"])
    filtered, n = apply_population_spec(panel, cat)
    assert n == 2


def test_spec_deduplication_hash():
    a = OutcomeSpec.compare("t5_return", ">", 0.0)
    b = OutcomeSpec.from_dict(a.to_dict())
    assert outcome_specs_equal(a, b)
    assert a.content_hash() == b.content_hash()

    pop_a = PopulationSpec.filter_numeric("rs10", ">", 0.0)
    pop_b = PopulationSpec.from_dict(json.loads(json.dumps(pop_a.to_dict())))
    assert population_specs_equal(pop_a, pop_b)


def test_population_spec_to_research_scope():
    pop = PopulationSpec.and_(
        PopulationSpec.filter_categorical("research_market_state", ["EARLY_RECOVERY"]),
        PopulationSpec.filter_numeric("rs10", ">", 0.0),
    )
    scope = population_spec_to_research_scope(pop)
    assert "population_spec_hash" in scope
    assert scope.get("market_state") == "EARLY_RECOVERY"
    assert "condition_clauses" in scope


def test_propose_outcome_reframes_no_t3_privilege():
    current = OutcomeSpec.compare("t5_return", ">", 0.0)
    alts = propose_outcome_reframes(current)
    assert len(alts) >= 1
    for alt in alts:
        validate_outcome_spec(alt)
        # Must not hard-code T3 thresholds
        assert alt.content_hash() != current.content_hash()


def test_propose_population_refinements_generic():
    base = PopulationSpec.all_()
    refinements = propose_population_refinements(
        base,
        reason_code="EVIDENCE",
        triggering_evidence={"interesting": True},
    )
    assert len(refinements) >= 1
    for r in refinements:
        validate_population_spec(r)
        assert r.kind == "refine"


def test_parse_helpers():
    spec = parse_outcome_spec(OutcomeSpec.compare("t5_return", ">", 1.0).to_dict())
    assert spec.outcome_field == "t5_return"
    pop = parse_population_spec(PopulationSpec.all_().to_dict())
    assert pop.kind == "all"


def test_compute_spec_hash_stable():
    payload = OutcomeSpec.compare("t5_return", ">", 0.0).to_dict()
    h1 = compute_spec_hash(payload)
    h2 = compute_spec_hash(payload)
    assert h1 == h2
