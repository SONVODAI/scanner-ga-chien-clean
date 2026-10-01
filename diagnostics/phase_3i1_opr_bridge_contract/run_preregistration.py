#!/usr/bin/env python3
"""
Phase 3I.1 DESIGN + CONTRACT + PRE-REGISTRATION ONLY.

Validates OPR bridge contract artifacts and emits frozen manifest hashes.
Does NOT modify production code or implement OPR generation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
BENCHMARK = REPO / "benchmarks" / "bb_prop_01"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "unknown"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


REQUIRED_ARTIFACTS: List[str] = [
    "00_input_evidence_classification.json",
    "01_opr_source_of_truth_rule.json",
    "02_proposition_record_contract.json",
    "03_scientific_birth_certificate.json",
    "04_template_independence_evaluator.json",
    "05_obs_gap_laundering_protection.json",
    "06_executability_boundary.json",
    "07_generation_budget_policy.json",
    "08_bb_prop_01_frozen_manifest.json",
    "09_hidden_benchmark_protection_policy.json",
    "10_creativity_metrics_preregistration.json",
    "11_negative_adversarial_controls.json",
    "12_evidence_responsive_lineage.json",
    "13_falsification_birthright.json",
    "14_minimal_3i2_implementation_boundary.json",
    "15_readiness_gate.json",
]


def validate_artifacts() -> Dict[str, Any]:
    missing: List[str] = []
    hashes: Dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = ARTIFACTS / name
        if not path.exists():
            missing.append(name)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        hashes[name] = _sha256_file(path)
        if name == "15_readiness_gate.json":
            if data.get("verdict") != "READY_FOR_MINIMAL_OPR":
                raise ValueError(f"Readiness gate verdict: {data.get('verdict')}")

    if missing:
        raise FileNotFoundError(f"Missing artifacts: {missing}")

    bundle_hash = _sha256_json(hashes)
    return {
        "phase": "3I.1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_branch": _git_branch(),
        "git_head": _git_head(),
        "artifact_count": len(hashes),
        "artifact_hashes": hashes,
        "bundle_hash": bundle_hash,
        "readiness_verdict": "READY_FOR_MINIMAL_OPR",
    }


def write_manifest(manifest: Dict[str, Any]) -> Path:
    BENCHMARK.mkdir(parents=True, exist_ok=True)
    out = BENCHMARK / "frozen_preregistration_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out


def main() -> int:
    try:
        manifest = validate_artifacts()
    except Exception as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    out_path = write_manifest(manifest)
    print(json.dumps(manifest, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
