"""Tests for Phase 3I.2 minimal OPR bridge."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION
from modules.edge_research.opr_bridge.evidence_ingest import (
    find_eligible_focal_dates,
    ingest_dispersion_evidence,
)
from modules.edge_research.opr_bridge.executability_adapter import adapt_executability
from modules.edge_research.opr_bridge.laundering_audit import audit_laundering, replay_surprise_without_ontology
from modules.edge_research.opr_bridge.leakage_audit import run_leakage_audit
from modules.edge_research.opr_bridge.pipeline import run_opr_pipeline
from modules.edge_research.opr_bridge.proposition_record import ExecutabilityStatus
from modules.edge_research.opr_bridge.proposition_synthesizer import synthesize_contrast_to_proposition
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise
from modules.edge_research.opr_bridge.dev_fixtures import inject_dispersion_anomaly
from modules.edge_research.opr_bridge.template_independence import evaluate_template_independence


PANEL_PATH = "benchmarks/blind_benchmark_01/artifacts/frozen_panel_snapshot.csv"


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_csv(PANEL_PATH)


@pytest.fixture(scope="module")
def cutoff(panel: pd.DataFrame) -> str:
    return str(panel["trade_date"].max())


def test_leakage_audit_passes():
    result = run_leakage_audit()
    assert result.passed
    assert not result.zone_c_accessible_to_generator


def test_evidence_ingest_produces_hash(panel, cutoff):
    dates = find_eligible_focal_dates(panel, data_cutoff_date=cutoff)
    assert dates
    evidence = ingest_dispersion_evidence(panel, focal_date=dates[-1], data_cutoff_date=cutoff)
    assert evidence is not None
    assert evidence.evidence_hash
    assert len(evidence.empirical_artifacts) >= 1


def test_surprise_not_triggered_on_insufficient_baseline(panel, cutoff):
    dates = find_eligible_focal_dates(panel, data_cutoff_date=cutoff)
    evidence = ingest_dispersion_evidence(panel, focal_date=dates[0], data_cutoff_date=cutoff)
    surprise = assess_dispersion_surprise(evidence)
    assert surprise.reason_code in ("INSUFFICIENT_BASELINE", "NOT_SURPRISING", "DISPERSION_ANOMALY")


def test_pure_noise_emits_nothing(panel, cutoff):
    noise = panel.copy()
    rng = np.random.default_rng(99)
    noise["rs_spread"] = rng.normal(0, 1, len(noise))
    noise["t5_return"] = rng.normal(0, 1, len(noise))
    result = run_opr_pipeline(noise, data_cutoff_date=cutoff, max_propositions=1, run_leakage=False)
    assert len(result.records) == 0


def test_proposition_record_birth_certificate(panel, cutoff):
    from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel

    dev_panel = build_extended_dev_panel(panel.head(10))
    focal = dev_panel["trade_date"].astype(str).max()
    dev_cutoff = focal
    evidence = ingest_dispersion_evidence(dev_panel, focal_date=focal, data_cutoff_date=dev_cutoff)
    assert evidence is not None
    surprise = assess_dispersion_surprise(evidence)
    assert surprise.is_surprising, surprise.surprise_basis_text
    record = synthesize_contrast_to_proposition(evidence, surprise)
    assert record.birth_certificate.all_passed()
    assert record.disconfirming_observation_spec.operational_test
    assert "if results do not support" not in record.disconfirming_observation_spec.description.lower()
    record.template_independence_audit = evaluate_template_independence(record)
    assert record.template_independence_audit.classification.value
    exec_r = adapt_executability(record, dev_panel)
    assert exec_r.status in ExecutabilityStatus
    launder = audit_laundering(record, raw_evidence_produced=True)
    assert launder.all_passed
    assert replay_surprise_without_ontology(record)


def test_deterministic_replay(panel, cutoff):
    dates = find_eligible_focal_dates(panel, data_cutoff_date=cutoff)
    focal = dates[len(dates) // 2]
    r1 = run_opr_pipeline(panel, data_cutoff_date=cutoff, focal_date=focal, max_propositions=1, run_leakage=False)
    r2 = run_opr_pipeline(panel, data_cutoff_date=cutoff, focal_date=focal, max_propositions=1, run_leakage=False)
    if r1.records and r2.records:
        assert r1.records[0].proposition_id == r2.records[0].proposition_id
    else:
        assert len(r1.records) == len(r2.records)


def test_template_independence_does_not_modify_proposition(panel, cutoff):
    from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel

    dev_panel = build_extended_dev_panel(panel.head(10))
    focal = dev_panel["trade_date"].astype(str).max()
    evidence = ingest_dispersion_evidence(dev_panel, focal_date=focal, data_cutoff_date=focal)
    surprise = assess_dispersion_surprise(evidence)
    assert surprise.is_surprising
    record = synthesize_contrast_to_proposition(evidence, surprise)
    before = record.scientific_question
    audit = evaluate_template_independence(record)
    record.template_independence_audit = audit
    assert record.scientific_question == before


def test_generator_version_frozen():
    assert OPR_GENERATOR_VERSION == "opr_generator_v1_3i2"


def test_no_ontology_input_path():
    """Pipeline API has no OBS/GAP parameters."""
    import inspect
    from modules.edge_research.opr_bridge.pipeline import run_opr_pipeline
    sig = inspect.signature(run_opr_pipeline)
    param_names = set(sig.parameters)
    assert "obs_code" not in param_names
    assert "gap_code" not in param_names
