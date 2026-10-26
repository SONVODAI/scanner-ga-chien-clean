"""Tests for Phase 3I.5 observation prioritization and scientific-identity deduplication."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION
from modules.edge_research.opr_bridge.evidence_ingest import ingest_dispersion_evidence
from modules.edge_research.opr_bridge.pipeline import run_opr_pipeline
from modules.edge_research.opr_bridge.prioritized_pipeline import run_opr_pipeline_prioritized
from modules.edge_research.opr_bridge.prioritization import PRIORITIZER_VERSION
from modules.edge_research.opr_bridge.scientific_identity import classify_pairwise, group_observation_events, scientific_identity_key
from modules.edge_research.opr_bridge.semantic_projection import project_contrast_semantics
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise
from modules.edge_research.opr_bridge.observation_entities import ObservationEvent
from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel, inject_dispersion_anomaly


EXPANDED_PANEL = Path("benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")
FROZEN_RECORDS = Path(
    "diagnostics/phase_3i3_real_evidence_expansion/artifacts/06_frozen_proposition_records.json"
)
CUTOFF = "2026-08-17"


@pytest.fixture(scope="module")
def expanded_panel() -> pd.DataFrame:
    return pd.read_csv(EXPANDED_PANEL)


def test_frozen_generator_version_unchanged():
    assert OPR_GENERATOR_VERSION == "opr_generator_v1_3i2"


def test_prioritizer_version_frozen():
    assert PRIORITIZER_VERSION == "opr_prioritizer_v1_3i5"


def test_semantic_projection_matches_synthesizer_question(expanded_panel):
    """Pre-emission projection uses frozen CONTRAST_TO_PROPOSITION semantics."""
    evidence = ingest_dispersion_evidence(
        expanded_panel, focal_date="2026-06-29", data_cutoff_date=CUTOFF
    )
    assert evidence is not None
    surprise = assess_dispersion_surprise(evidence)
    proj = project_contrast_semantics(evidence, surprise)
    assert "rs_spread" in proj.scientific_question
    assert "t5_return" in proj.scientific_question
    assert proj.uncertainty_family == "CROSS_SECTIONAL_DISPERSION"


def test_same_proposition_grouping_on_frozen_dates(expanded_panel):
    """2026-06-29, 2026-06-30, 2026-07-23 must group as one proposition."""
    dates = ["2026-06-29", "2026-06-30", "2026-07-23"]
    events = []
    for d in dates:
        ev = ingest_dispersion_evidence(expanded_panel, focal_date=d, data_cutoff_date=CUTOFF)
        assert ev is not None
        surprise = assess_dispersion_surprise(ev)
        events.append(
            ObservationEvent(
                focal_date=d,
                data_cutoff_date=CUTOFF,
                evidence=ev,
                surprise=surprise,
            )
        )

    groups = group_observation_events(events)
    assert len(groups) == 1
    assert groups[0].independent_evidence_count == 3
    assert groups[0].representative.focal_date == "2026-06-30"  # highest spread


def test_pairwise_classification_same_proposition(expanded_panel):
    d1 = ingest_dispersion_evidence(expanded_panel, focal_date="2026-06-29", data_cutoff_date=CUTOFF)
    d2 = ingest_dispersion_evidence(expanded_panel, focal_date="2026-06-30", data_cutoff_date=CUTOFF)
    s1 = assess_dispersion_surprise(d1)
    s2 = assess_dispersion_surprise(d2)
    p1 = project_contrast_semantics(d1, s1)
    p2 = project_contrast_semantics(d2, s2)
    assert classify_pairwise(p1, p2) == "SAME_PROPOSITION_DIFFERENT_EVIDENCE"
    assert scientific_identity_key(p1) == scientific_identity_key(p2)


def test_counterfactual_old_vs_new_replay(expanded_panel):
    """NEW prioritization compresses duplicate propositions and picks stronger representative."""
    old = run_opr_pipeline(
        expanded_panel, data_cutoff_date=CUTOFF, max_propositions=3, run_leakage=False
    )
    new = run_opr_pipeline_prioritized(
        expanded_panel, data_cutoff_date=CUTOFF, max_unique_propositions=3, run_leakage=False
    )

    old_questions = {r.scientific_question for r in old.records}
    new_questions = {r.scientific_question for r in new.records}

    assert len(old.records) == 3
    assert len(old_questions) == 1

    assert len(new.records) == 1
    assert len(new_questions) == 1
    assert new.surprising_observation_events == 22
    assert new.unique_proposition_groups == 1

    rep_date = new.evidence_lineages[0].representative_focal_date
    assert rep_date == "2026-08-02"  # highest quintile spread in 22-trigger set
    assert len(new.evidence_lineages[0].aggregated_evidence_events) == 22

    old_first_date = old.records[0].observation_provenance.evidence_anchor["focal_date"]
    assert old_first_date == "2026-06-29"
    assert rep_date != old_first_date


def test_negative_control_pure_noise(expanded_panel):
    noise = expanded_panel.copy()
    rng = np.random.default_rng(42)
    noise["rs_spread"] = rng.normal(0, 1, len(noise))
    noise["t5_return"] = rng.normal(0, 1, len(noise))
    result = run_opr_pipeline_prioritized(
        noise, data_cutoff_date=CUTOFF, max_unique_propositions=3, run_leakage=False
    )
    assert len(result.records) == 0


def test_negative_control_identical_duplicate_observations(expanded_panel):
    """Identical focal dates should collapse to one evidence group."""
    evidence = ingest_dispersion_evidence(
        expanded_panel, focal_date="2026-06-30", data_cutoff_date=CUTOFF
    )
    surprise = assess_dispersion_surprise(evidence)
    dup = ObservationEvent(
        focal_date="2026-06-30",
        data_cutoff_date=CUTOFF,
        evidence=evidence,
        surprise=surprise,
    )
    groups = group_observation_events([dup, dup])
    assert len(groups) == 1
    assert groups[0].independent_evidence_count == 2


def test_negative_control_low_value_valid_silence(expanded_panel):
    """Single non-surprising observation → valid silence."""
    result = run_opr_pipeline_prioritized(
        expanded_panel,
        data_cutoff_date=CUTOFF,
        focal_date="2026-08-05",
        max_unique_propositions=3,
        run_leakage=False,
    )
    assert len(result.records) == 0
    assert any(s.reason_code == "INSUFFICIENT_SURPRISE" for s in result.silences)


def test_frozen_thresholds_unchanged():
    from modules.edge_research.opr_bridge.constants import (
        QUINTILE_SPREAD_THRESHOLD,
        SURPRISE_ZSCORE_THRESHOLD,
    )

    assert SURPRISE_ZSCORE_THRESHOLD == 2.0
    assert QUINTILE_SPREAD_THRESHOLD == 1.5
