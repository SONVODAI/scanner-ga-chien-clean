"""LIVE_FORWARD live-policy hashes must stay byte-identical to the 3K.5 pin.

Production 2026-09-07 failed with
`live_policy_hash_mismatch_genesis:bounded_lifecycle_controller.py`.
This test pins the expected hashes from the committed 3K.5 readiness artifact
and proves the first-mismatch reason string the orchestrator surfaces.
It does not create or overwrite production genesis.
"""

from __future__ import annotations

import json
from pathlib import Path

from modules.edge_research.opr_bridge.blind_research_examination_runner import (
    compute_research_policy_hashes,
)
from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_live_forward_genesis import (
    persist_genesis,
    validate_live_forward_prerequisites,
    build_genesis_record,
)

REPO = Path(__file__).resolve().parents[1]
PIN_PATH = (
    REPO
    / "diagnostics"
    / "phase_3k5_live_forward_production_readiness"
    / "artifacts"
    / "00_full_readiness_audit.json"
)
HASHED_POLICY_FILES = (
    "bounded_lifecycle_controller.py",
    "bounded_lifecycle_records.py",
    "bounded_lifecycle_state.py",
    "production_bounded_lifecycle.py",
    "first_experiment_research_decider.py",
    "second_experiment_research_decider.py",
    "first_experiment_evidence_interpreter.py",
    "second_experiment_evidence_interpreter.py",
    "multi_evidence_accounting.py",
    "production_trigger.py",
    "prioritized_pipeline.py",
    "proposition_synthesizer.py",
)


def _expected_policy_hashes() -> dict[str, str]:
    audit = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    hashes = dict(audit["policy"]["policy_hashes"])
    assert set(hashes) == set(HASHED_POLICY_FILES)
    return hashes


def test_live_policy_hashes_match_3k5_pin():
    expected = _expected_policy_hashes()
    live = compute_research_policy_hashes(REPO)
    mismatches = {
        name: {"expected": expected[name], "actual": live.get(name)}
        for name in HASHED_POLICY_FILES
        if live.get(name) != expected[name]
    }
    assert mismatches == {}, mismatches


def test_genesis_gate_reports_first_controller_mismatch(tmp_path):
    expected = _expected_policy_hashes()
    genesis = build_genesis_record(
        first_eligible_trade_date="2026-09-07",
        code_commit="test-pin",
        policy_hashes=expected,
        dataset_identities={"panel": "test"},
        deployment_identity="test-restore",
    )
    persist_genesis(genesis, data_dir=tmp_path, allow_overwrite=False)

    live = compute_research_policy_hashes(REPO)
    ok, reason, checks = validate_live_forward_prerequisites(
        "2026-09-07",
        run_mode=LIVE_FORWARD,
        policy_hashes=live,
        data_dir=tmp_path,
    )
    assert ok is True
    assert reason == "ok"
    assert "live_policy_hashes_match_genesis" in checks

    drifted = dict(live)
    drifted["bounded_lifecycle_controller.py"] = "0" * 64
    ok2, reason2, _ = validate_live_forward_prerequisites(
        "2026-09-07",
        run_mode=LIVE_FORWARD,
        policy_hashes=drifted,
        data_dir=tmp_path,
    )
    assert ok2 is False
    assert reason2 == "live_policy_hash_mismatch_genesis:bounded_lifecycle_controller.py"
