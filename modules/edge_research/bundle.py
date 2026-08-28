"""
Versioned Edge Research bundle — canonical persistence format (P2).

Bundles Discovery/Challenger state for durable storage and restore.
Research algorithms unchanged; persistence boundary only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from modules.edge_research.contracts import ENGINE_VERSION
from modules.edge_research.storage import (
    CHALLENGER_RUN_FILE,
    DISCOVERY_RUN_FILE,
    cohort_ledger_hash,
    read_challenger_run,
    read_discovery_run,
    read_ledger,
    resolve_data_dir,
    resolve_discovery_cohort,
)

BUNDLE_VERSION = "edge_research_bundle_v1"
MANIFEST_FILENAME = "manifest.json"
ARTIFACTS_DIRNAME = "artifacts"

CANONICAL_ARTIFACT_NAMES: Tuple[str, ...] = (
    DISCOVERY_RUN_FILE,
    "edge_hypothesis_ledger.csv",
)

CHALLENGER_ARTIFACT_NAME = CHALLENGER_RUN_FILE

OPTIONAL_ARTIFACT_NAMES: Tuple[str, ...] = (
    "challenger_runs.csv",
    "edge_robustness_history.csv",
    "edge_episode_registry.csv",
    "discovery_runs.csv",
    "edge_memory.csv",
    "edge_validation_history.csv",
    "frozen_specs.json",
    "edge_forward_ledger.csv",
    "edge_session_assessments.csv",
    "latest_future_recognition.json",
    "edge_shadow_observations.csv",
    "edge_anti_context.csv",
    "latest_edge_health.json",
)


class BundleValidationError(ValueError):
    """Raised when a bundle fails integrity or provenance checks."""


@dataclass
class BundleValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    manifest: Optional[Dict[str, Any]] = None


@dataclass
class ResearchStateFingerprint:
    discovery_run_id: str = ""
    discovery_timestamp: str = ""
    challenger_run_id: str = ""
    challenger_timestamp: str = ""
    cohort_size: int = 0
    cohort_hash: str = ""
    state_sequence: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "discovery_run_id": self.discovery_run_id,
            "discovery_timestamp": self.discovery_timestamp,
            "challenger_run_id": self.challenger_run_id,
            "challenger_timestamp": self.challenger_timestamp,
            "cohort_size": self.cohort_size,
            "cohort_hash": self.cohort_hash,
            "state_sequence": self.state_sequence,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_sequence(timestamp: str, run_id: str) -> int:
    """Deterministic ordering key: challenger timestamp preferred, else discovery."""
    base = timestamp or ""
    suffix = run_id or ""
    return int(hashlib.sha256(f"{base}:{suffix}".encode()).hexdigest()[:16], 16)


def compute_input_hashes() -> Dict[str, Optional[str]]:
    """Provenance digests for canonical Git-tracked inputs (future hash-skip)."""
    from modules.edge_research.adapters import earning_learning_digests, file_digest
    from modules.edge_research.adapters import OUTCOMES_PATH, REPO_ROOT

    digests = earning_learning_digests()
    lifecycle = REPO_ROOT / "data" / "earning_learning" / "pattern_lifecycle.csv"
    return {
        "pattern_lifecycle": file_digest(lifecycle),
        "outcomes": file_digest(OUTCOMES_PATH),
        "observations": digests.get("observations.csv"),
    }


def fingerprint_working_state(data_dir: Optional[Path] = None) -> ResearchStateFingerprint:
    root = resolve_data_dir(data_dir)
    discovery = read_discovery_run(root)
    challenger = read_challenger_run(root)
    cohort = resolve_discovery_cohort(root)
    cohort_hash = cohort_ledger_hash(cohort) if not cohort.empty else ""
    d_ts = str(discovery.get("timestamp", "") or "")
    c_ts = str(challenger.get("timestamp", "") or "")
    seq_ts = c_ts if challenger.get("run_id") not in (None, "", "skipped") else d_ts
    seq_id = str(challenger.get("run_id", "") or discovery.get("run_id", "") or "")
    return ResearchStateFingerprint(
        discovery_run_id=str(discovery.get("run_id", "") or ""),
        discovery_timestamp=d_ts,
        challenger_run_id=str(challenger.get("run_id", "") or ""),
        challenger_timestamp=c_ts,
        cohort_size=int(len(cohort)),
        cohort_hash=cohort_hash,
        state_sequence=_parse_sequence(seq_ts, seq_id),
    )


def is_publishable_state(data_dir: Optional[Path] = None) -> bool:
    """True when working storage has a valid Discovery cohort worth publishing."""
    root = resolve_data_dir(data_dir)
    discovery = read_discovery_run(root)
    run_id = str(discovery.get("run_id", "") or "")
    if not run_id:
        return False
    cohort = resolve_discovery_cohort(root, discovery_run_id=run_id)
    return not cohort.empty


def _pack_frozen_specs(source_dir: Path) -> Optional[Path]:
    """Snapshot individual frozen spec files into a single bundle artifact."""
    from modules.edge_research.contracts import FROZEN_SPECS_DIRNAME

    spec_dir = source_dir / FROZEN_SPECS_DIRNAME
    if not spec_dir.exists():
        return None
    payload: Dict[str, Any] = {}
    for path in sorted(spec_dir.glob("*.json")):
        try:
            payload[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    if not payload:
        return None
    out = source_dir / "frozen_specs.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _unpack_frozen_specs(data_dir: Path, packed: Path) -> None:
    from modules.edge_research.contracts import FROZEN_SPECS_DIRNAME

    payload = json.loads(packed.read_text(encoding="utf-8"))
    spec_dir = data_dir / FROZEN_SPECS_DIRNAME
    spec_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, dict):
        return
    for hid, spec in payload.items():
        (spec_dir / f"{hid}.json").write_text(
            json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )


def _collect_artifact_paths(source_dir: Path) -> Dict[str, Path]:
    _pack_frozen_specs(source_dir)
    paths: Dict[str, Path] = {}
    for name in CANONICAL_ARTIFACT_NAMES:
        p = source_dir / name
        if p.exists() and p.stat().st_size > 0:
            paths[name] = p
    challenger = source_dir / CHALLENGER_ARTIFACT_NAME
    if challenger.exists() and challenger.stat().st_size > 0:
        paths[CHALLENGER_ARTIFACT_NAME] = challenger
    for name in OPTIONAL_ARTIFACT_NAMES:
        p = source_dir / name
        if p.exists() and p.stat().st_size > 0:
            paths[name] = p
    return paths


def build_manifest_from_working_dir(
    data_dir: Optional[Path] = None,
    *,
    artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build manifest metadata from working storage (artifacts must exist in artifact_dir)."""
    root = resolve_data_dir(data_dir)
    artifact_root = artifact_dir or root
    paths = _collect_artifact_paths(artifact_root)

    missing = [n for n in CANONICAL_ARTIFACT_NAMES if n not in paths]
    if missing:
        raise BundleValidationError(f"Cannot build bundle; missing canonical artifacts: {missing}")

    discovery = json.loads(paths[DISCOVERY_RUN_FILE].read_text(encoding="utf-8"))
    discovery_run_id = str(discovery.get("run_id", "") or "")
    if not discovery_run_id:
        raise BundleValidationError("Discovery run missing run_id")

    cohort = resolve_discovery_cohort(root, discovery_run_id=discovery_run_id)
    if cohort.empty:
        raise BundleValidationError("Discovery run has empty cohort")

    fp = fingerprint_working_state(root)
    challenger: Dict[str, Any] = {}
    has_challenger = CHALLENGER_ARTIFACT_NAME in paths
    if has_challenger:
        challenger = json.loads(paths[CHALLENGER_ARTIFACT_NAME].read_text(encoding="utf-8"))
        if challenger.get("run_id") in (None, "", "skipped"):
            has_challenger = False

    canonical_hashes = {name: _sha256_file(paths[name]) for name in CANONICAL_ARTIFACT_NAMES}
    optional_hashes = {
        name: _sha256_file(paths[name])
        for name in OPTIONAL_ARTIFACT_NAMES
        if name in paths
    }
    if has_challenger:
        canonical_hashes[CHALLENGER_ARTIFACT_NAME] = _sha256_file(paths[CHALLENGER_ARTIFACT_NAME])

    manifest: Dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "engine_version": ENGINE_VERSION,
        "created_at": _iso_now(),
        "discovery_run_id": discovery_run_id,
        "discovery_timestamp": str(discovery.get("timestamp", "") or ""),
        "promoted_candidates": int(discovery.get("promoted_candidates", 0) or 0),
        "cohort_size": int(len(cohort)),
        "cohort_hash": cohort_ledger_hash(cohort),
        "candidate_ledger_hash": challenger.get("candidate_ledger_hash", fp.cohort_hash),
        "input_hashes": compute_input_hashes(),
        "state_sequence": fp.state_sequence,
        "canonical_artifacts": canonical_hashes,
        "optional_artifacts": optional_hashes,
        "has_challenger": has_challenger,
    }
    if has_challenger:
        manifest.update(
            {
                "challenger_run_id": str(challenger.get("run_id", "") or ""),
                "challenger_timestamp": str(challenger.get("timestamp", "") or ""),
                "challenger_discovery_run_id": str(challenger.get("discovery_run_id", "") or ""),
                "robustness_pass": int(challenger.get("robustness_pass", 0) or 0),
                "robustness_fragile": int(challenger.get("robustness_fragile", 0) or 0),
                "robustness_reject": int(challenger.get("robustness_reject", 0) or 0),
            }
        )
    return manifest


def validate_bundle_dir(bundle_dir: Path) -> BundleValidationResult:
    """Validate bundle directory structure, hashes, and provenance."""
    errors: List[str] = []
    manifest_path = bundle_dir / MANIFEST_FILENAME
    artifacts_dir = bundle_dir / ARTIFACTS_DIRNAME

    if not manifest_path.exists():
        return BundleValidationResult(False, ["manifest.json missing"])
    if not artifacts_dir.is_dir():
        return BundleValidationResult(False, ["artifacts/ directory missing"])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return BundleValidationResult(False, [f"manifest.json invalid JSON: {exc}"])

    if manifest.get("bundle_version") != BUNDLE_VERSION:
        errors.append(f"unsupported bundle_version: {manifest.get('bundle_version')}")

    for name in CANONICAL_ARTIFACT_NAMES:
        ap = artifacts_dir / name
        if not ap.exists():
            errors.append(f"missing canonical artifact: {name}")
            continue
        expected = manifest.get("canonical_artifacts", {}).get(name)
        if not expected:
            errors.append(f"manifest missing hash for {name}")
        elif _sha256_file(ap) != expected:
            errors.append(f"hash mismatch: {name}")

    has_challenger = bool(manifest.get("has_challenger"))
    if has_challenger:
        cp = artifacts_dir / CHALLENGER_ARTIFACT_NAME
        if not cp.exists():
            errors.append(f"missing challenger artifact: {CHALLENGER_ARTIFACT_NAME}")
        else:
            expected = manifest.get("canonical_artifacts", {}).get(CHALLENGER_ARTIFACT_NAME)
            if expected and _sha256_file(cp) != expected:
                errors.append(f"hash mismatch: {CHALLENGER_ARTIFACT_NAME}")

    for name, expected_hash in manifest.get("optional_artifacts", {}).items():
        ap = artifacts_dir / name
        if not ap.exists():
            errors.append(f"missing optional artifact listed in manifest: {name}")
        elif _sha256_file(ap) != expected_hash:
            errors.append(f"hash mismatch optional: {name}")

    if errors:
        return BundleValidationResult(False, errors, manifest)

    # Provenance checks using restored artifact copies in bundle dir only.
    discovery = json.loads((artifacts_dir / DISCOVERY_RUN_FILE).read_text(encoding="utf-8"))
    d_run = str(discovery.get("run_id", "") or "")
    if d_run != manifest.get("discovery_run_id"):
        errors.append("discovery run_id mismatch between manifest and artifact")

    promoted = int(discovery.get("promoted_candidates", 0) or 0)
    if promoted != manifest.get("promoted_candidates"):
        errors.append("promoted_candidates mismatch")

    if has_challenger:
        challenger = json.loads((artifacts_dir / CHALLENGER_ARTIFACT_NAME).read_text(encoding="utf-8"))
        if str(challenger.get("discovery_run_id", "") or "") != d_run:
            errors.append("challenger discovery_run_id does not match discovery run_id")
        if str(challenger.get("run_id", "") or "") != manifest.get("challenger_run_id"):
            errors.append("challenger run_id mismatch")
        for field, key in (
            ("robustness_pass", "robustness_pass"),
            ("robustness_fragile", "robustness_fragile"),
            ("robustness_reject", "robustness_reject"),
        ):
            if int(challenger.get(key, 0) or 0) != int(manifest.get(field, 0) or 0):
                errors.append(f"challenger {key} mismatch")

    if errors:
        return BundleValidationResult(False, errors, manifest)

    return BundleValidationResult(True, [], manifest)


def write_bundle_to_dir(source_data_dir: Path, dest_bundle_dir: Path) -> Dict[str, Any]:
    """Stage a validated bundle directory from working storage."""
    if dest_bundle_dir.exists():
        shutil.rmtree(dest_bundle_dir)
    artifacts_dir = dest_bundle_dir / ARTIFACTS_DIRNAME
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    paths = _collect_artifact_paths(source_data_dir)
    missing = [n for n in CANONICAL_ARTIFACT_NAMES if n not in paths]
    if missing:
        raise BundleValidationError(f"Cannot write bundle; missing: {missing}")

    for name, src in paths.items():
        shutil.copy2(src, artifacts_dir / name)

    manifest = build_manifest_from_working_dir(source_data_dir, artifact_dir=artifacts_dir)
    (dest_bundle_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    validation = validate_bundle_dir(dest_bundle_dir)
    if not validation.ok:
        shutil.rmtree(dest_bundle_dir, ignore_errors=True)
        raise BundleValidationError("; ".join(validation.errors))
    return manifest


def restore_bundle_to_working_dir(bundle_dir: Path, data_dir: Path) -> Dict[str, Any]:
    """Restore canonical artifacts from validated bundle into working storage."""
    validation = validate_bundle_dir(bundle_dir)
    if not validation.ok:
        raise BundleValidationError("; ".join(validation.errors))

    manifest = validation.manifest or {}
    artifacts_dir = bundle_dir / ARTIFACTS_DIRNAME
    data_dir.mkdir(parents=True, exist_ok=True)

    restore_names = list(CANONICAL_ARTIFACT_NAMES)
    if manifest.get("has_challenger"):
        restore_names.append(CHALLENGER_ARTIFACT_NAME)
    restore_names.extend(
        name for name in OPTIONAL_ARTIFACT_NAMES if (artifacts_dir / name).exists()
    )

    for name in restore_names:
        shutil.copy2(artifacts_dir / name, data_dir / name)
        if name == "frozen_specs.json":
            _unpack_frozen_specs(data_dir, data_dir / name)

    return manifest


def compare_state_fingerprints(
    local: ResearchStateFingerprint,
    durable: ResearchStateFingerprint,
) -> str:
    """
    Deterministic conflict policy.
    Returns: 'local', 'durable', or 'equal'.
    """
    if local.discovery_run_id == durable.discovery_run_id and local.cohort_hash == durable.cohort_hash:
        if local.state_sequence == durable.state_sequence:
            return "equal"
    if local.state_sequence > durable.state_sequence:
        return "local"
    if durable.state_sequence > local.state_sequence:
        return "durable"
    if local.discovery_timestamp > durable.discovery_timestamp:
        return "local"
    if durable.discovery_timestamp > local.discovery_timestamp:
        return "durable"
    return "equal"
