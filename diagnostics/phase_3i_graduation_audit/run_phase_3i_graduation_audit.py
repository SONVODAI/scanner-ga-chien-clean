#!/usr/bin/env python3
"""
Phase 3I — End-to-End Autonomous Researcher Graduation Audit (read-only).

AUDIT + REPLAY + SYSTEM-LEVEL EVALUATION ONLY.
Does NOT modify scientific components, execute experiments, or regenerate answers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text())


def verify_frozen_hashes() -> dict:
    from modules.edge_research.opr_bridge.cohort_binding_records import binder_content_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.frontier_records import reassessor_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash

    manifest = _load("01_frozen_system_manifest.json")
    expected = {
        "evidence_synthesis_engine": manifest["components"]["evidence_synthesis_engine"]["content_hash"],
        "scientific_action_generator": manifest["components"]["scientific_action_generator"]["content_hash"],
        "scientific_frontier_reassessor": manifest["components"]["scientific_frontier_reassessor"]["content_hash"],
        "research_dormancy_mechanism": manifest["components"]["research_dormancy_mechanism"]["content_hash"],
        "lifecycle_dormancy_integration": manifest["components"]["lifecycle_dormancy_integration"]["content_hash"],
        "evidence_derived_cohort_binder": manifest["components"]["evidence_derived_cohort_binder"]["content_hash"],
    }
    current = {
        "evidence_synthesis_engine": engine_content_hash(),
        "scientific_action_generator": generator_content_hash(),
        "scientific_frontier_reassessor": reassessor_content_hash(),
        "research_dormancy_mechanism": dormancy_content_hash(),
        "lifecycle_dormancy_integration": integration_content_hash(),
        "evidence_derived_cohort_binder": binder_content_hash(),
    }
    checks = {k: expected[k] == current[k] for k in expected}
    return {"passed": all(checks.values()), "checks": checks}


def verify_t2_terminal_state() -> dict:
    replay_path = ROOT / "diagnostics/phase_3i20_dormancy_lifecycle/artifacts/04_t2_lifecycle_replay.json"
    replay = json.loads(replay_path.read_text())
    manifest = _load("01_frozen_system_manifest.json")
    frozen = manifest["frozen_t2_terminal_state"]
    checks = {
        "epistemic_state": replay["epistemic_state"] == frozen["epistemic_state"],
        "frontier_decision": replay["frontier_decision"] == frozen["frontier_decision"],
        "research_activity_state": replay["research_activity_state"] == frozen["research_activity_state"],
        "dormancy_hash": replay["dormancy_hash"] == frozen["dormancy_hash"],
    }
    return {"passed": all(checks.values()), "checks": checks, "source": str(replay_path)}


def verify_opr_isolation() -> dict:
    controller = (ROOT / "modules/edge_research/research_controller.py").read_text()
    imports_opr = "opr_bridge" in controller
    init_text = (ROOT / "modules/edge_research/opr_bridge/__init__.py").read_text()
    return {
        "passed": not imports_opr,
        "research_controller_imports_opr_bridge": imports_opr,
        "opr_bridge_isolation_declared": "Does NOT modify" in init_text,
    }


def main() -> int:
    results = {
        "audit_mode": "AUDIT_REPLAY_SYSTEM_EVALUATION_ONLY",
        "frozen_hash_integrity": verify_frozen_hashes(),
        "t2_terminal_state": verify_t2_terminal_state(),
        "opr_production_isolation": verify_opr_isolation(),
        "scorecard_verdicts": _load("03_autonomy_scorecard.json")["verdicts"],
    }
    summary_path = ARTIFACTS / "04_audit_verification_summary.json"
    summary_path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    passed = all(
        results[k]["passed"]
        for k in ("frozen_hash_integrity", "t2_terminal_state", "opr_production_isolation")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
