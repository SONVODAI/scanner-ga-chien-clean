"""P1/P2 durable bundle persistence tests — CASE 1 through CASE 12."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SOURCE = REPO_ROOT / "data" / "edge_research"


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_PATH", raising=False)
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_BACKEND", raising=False)
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_URL", raising=False)
    return d


@pytest.fixture
def durable_dir(tmp_path, monkeypatch):
    d = tmp_path / "durable_store"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_BACKEND", "local")
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_PATH", str(d))
    return d


def _seed_reference_copy(dest: Path) -> None:
    if not REFERENCE_SOURCE.exists():
        pytest.skip("reference data/edge_research not available locally")
    shutil.copytree(REFERENCE_SOURCE, dest, dirs_exist_ok=True)


def _cohort_summary(data_dir: Path) -> dict:
    from modules.edge_research.persistence import summarize_restored_cohort

    return summarize_restored_cohort(data_dir)


# CASE 1 — Fresh runtime restore from durable bundle
def test_case1_fresh_runtime_restore_from_durable(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable, try_restore_durable

    mig = migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    assert mig.last_result == "published"
    assert mig.cohort_size == 20

    shutil.rmtree(edge_data_dir)
    edge_data_dir.mkdir()

    st = try_restore_durable(edge_data_dir)
    assert st.last_result == "restored"
    summary = _cohort_summary(edge_data_dir)
    assert summary["cohort_size"] == 20
    assert summary["robustness_pass"] == 0
    assert summary["robustness_fragile"] == 3
    assert summary["robustness_reject"] == 17


# CASE 2 — Fresh runtime without bundle
def test_case2_fresh_runtime_without_bundle(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.persistence import try_restore_durable

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    st = try_restore_durable(edge_data_dir)
    assert st.last_result == "skipped"
    status = engine.get_foundation_status()
    assert status.hypotheses == 0
    assert status.last_research_event == "NONE"
    assert engine.has_valid_discovery_cohort() is False


# CASE 3 — Corrupt/incomplete bundle rejected
def test_case3_corrupt_bundle_rejected(durable_dir):
    from modules.edge_research.bundle import BundleValidationError, validate_bundle_dir
    from modules.edge_research.durable import LocalDirectoryDurableBackend

    bundle = durable_dir / "current"
    (bundle / "artifacts").mkdir(parents=True)
    (bundle / "manifest.json").write_text('{"bundle_version":"edge_research_bundle_v1"}')
    validation = validate_bundle_dir(bundle)
    assert validation.ok is False

    backend = LocalDirectoryDurableBackend(durable_dir)
    staging = durable_dir / "staging_load"
    result = backend.load_bundle(staging)
    assert result.ok is False


# CASE 4 — Hash mismatch rejected
def test_case4_hash_mismatch_rejected(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable
    from modules.edge_research.durable import LocalDirectoryDurableBackend

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    manifest_path = durable_dir / "current" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest.get("canonical_artifacts", {})
    key = next(iter(artifacts))
    artifacts[key] = "0" * 64
    manifest["canonical_artifacts"] = artifacts
    manifest_path.write_text(json.dumps(manifest))

    backend = LocalDirectoryDurableBackend(durable_dir)
    staging = durable_dir / "load_staging"
    result = backend.load_bundle(staging)
    assert result.ok is False


# CASE 5 — Discovery/Challenger provenance mismatch rejected
def test_case5_provenance_mismatch_rejected(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable
    from modules.edge_research.bundle import BundleValidationError, validate_bundle_dir

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    ch_path = durable_dir / "current" / "artifacts" / "latest_challenger_run.json"
    ch = json.loads(ch_path.read_text())
    ch["discovery_run_id"] = "wrong_run_id"
    ch_path.write_text(json.dumps(ch))

    validation = validate_bundle_dir(durable_dir / "current")
    assert validation.ok is False
    assert any(
        "discovery_run_id" in e or "hash mismatch" in e for e in validation.errors
    )


# CASE 6 — Legacy 40-row ledger resolves 20-row cohort
def test_case6_legacy_ledger_resolves_20_cohort(edge_data_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.storage import read_ledger, resolve_discovery_cohort

    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert len(ledger) == 40
    cohort = resolve_discovery_cohort(edge_data_dir)
    assert len(cohort) == 20


# CASE 7 — Derived status reconstruction after engine_status deleted
def test_case7_derived_status_rebuilt(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.persistence import migrate_working_dir_to_durable, try_restore_durable

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    shutil.rmtree(edge_data_dir)
    edge_data_dir.mkdir()
    try_restore_durable(edge_data_dir)
    (edge_data_dir / "engine_status.json").unlink(missing_ok=True)

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    status = engine.get_foundation_status()
    assert status.hypotheses >= 20
    assert status.challenger_summary is not None
    assert status.challenger_summary["robustness_fragile"] == 3


# CASE 8 — Redeploy simulation
def test_case8_redeploy_simulation(edge_data_dir, durable_dir, monkeypatch):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.persistence import migrate_working_dir_to_durable

    before = _cohort_summary(edge_data_dir)
    migrate_working_dir_to_durable(edge_data_dir, durable_dir)

    redeploy = edge_data_dir.parent / "redeploy_edge_research"
    redeploy.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(redeploy))

    engine = EdgeResearchEngine(data_dir=redeploy)
    engine.initialize()
    after = _cohort_summary(redeploy)
    assert after["cohort_size"] == before["cohort_size"] == 20
    assert after["robustness_reject"] == 17


# CASE 9 — Atomic publication failure preserves prior bundle
def test_case9_publish_failure_preserves_prior(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.durable import LocalDirectoryDurableBackend
    from modules.edge_research.persistence import migrate_working_dir_to_durable

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    prior_manifest = (durable_dir / "current" / "manifest.json").read_text()

    backend = LocalDirectoryDurableBackend(durable_dir)
    invalid = durable_dir / "invalid_bundle"
    invalid.mkdir()
    result = backend.publish_bundle(invalid)
    assert result.ok is False
    assert (durable_dir / "current" / "manifest.json").read_text() == prior_manifest


# CASE 10 — Newer local state preserved over older durable
def test_case10_newer_local_wins(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable, try_restore_durable

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    st = try_restore_durable(edge_data_dir)
    assert st.last_result == "skipped"
    assert "local" in st.message or "equal" in st.message


# CASE 11 — Dtype survives bundle roundtrip
def test_case11_dtype_survives_bundle_roundtrip(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable, try_restore_durable
    from modules.edge_research.storage import read_ledger

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    shutil.rmtree(edge_data_dir)
    edge_data_dir.mkdir()
    try_restore_durable(edge_data_dir)

    cohort = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    from modules.edge_research.storage import resolve_discovery_cohort
    cohort = resolve_discovery_cohort(edge_data_dir)
    assert str(cohort["robustness_status"].dtype) == "string"
    assert set(cohort["robustness_status"].dropna().unique()) <= {"PASS", "FRAGILE", "REJECT"}


# CASE 12 — Algorithm parity reference counts
def test_case12_reference_counts_preserved(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import migrate_working_dir_to_durable, try_restore_durable

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    shutil.rmtree(edge_data_dir)
    edge_data_dir.mkdir()
    try_restore_durable(edge_data_dir)
    summary = _cohort_summary(edge_data_dir)
    assert summary["cohort_size"] == 20
    assert summary["robustness_pass"] == 0
    assert summary["robustness_fragile"] == 3
    assert summary["robustness_reject"] == 17
    counts = summary["cohort_robustness_counts"]
    assert counts.get("FRAGILE") == 3
    assert counts.get("REJECT") == 17


def test_engine_initialize_triggers_restore(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.persistence import migrate_working_dir_to_durable

    migrate_working_dir_to_durable(edge_data_dir, durable_dir)
    shutil.rmtree(edge_data_dir)
    edge_data_dir.mkdir()

    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.initialize()
    assert engine.has_valid_discovery_cohort() is True


def test_publish_after_transaction(edge_data_dir, durable_dir):
    _seed_reference_copy(edge_data_dir)
    from modules.edge_research.persistence import publish_durable, read_persistence_status

    pub = publish_durable(edge_data_dir)
    assert pub.last_result == "published"
    assert (durable_dir / "current" / "manifest.json").exists()
    status = read_persistence_status(edge_data_dir)
    assert status.last_operation == "publish"
