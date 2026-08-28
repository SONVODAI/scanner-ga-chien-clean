"""
Phase 3J.6 — Durable second-experiment design persistence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.second_experiment_design_gate import compute_design_identity_hash
from modules.edge_research.opr_bridge.second_experiment_objective import SecondExperimentObjectiveRecord
from modules.edge_research.opr_bridge.second_experiment_records import (
    CANDIDATE_RECORD_VERSION,
    DESIGN_VERSION,
    OBJECTIVE_RECORD_VERSION,
    PACKAGE_RECORD_VERSION,
    SecondExperimentCandidateRecord,
    SecondExperimentPackage,
)
from modules.edge_research.storage import resolve_data_dir

PERSISTENCE_VERSION = "second_experiment_design_persistence_v1_3j6"
PACKAGES_DIR = "second_experiment_packages"
PACKAGE_INDEX_FILE = "second_experiment_package_index.json"


def packages_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / PACKAGES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def package_index_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / PACKAGE_INDEX_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _objective_from_dict(payload: Dict[str, Any]) -> SecondExperimentObjectiveRecord:
    return SecondExperimentObjectiveRecord(
        objective_id=payload["objective_id"],
        record_version=payload.get("record_version", OBJECTIVE_RECORD_VERSION),
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        research_decision_id=payload["research_decision_id"],
        research_decision_hash=payload["research_decision_hash"],
        selected_action=payload["selected_action"],
        target_uncertainty=payload["target_uncertainty"],
        target_null_key=payload["target_null_key"],
        scientific_objective=payload["scientific_objective"],
        why_this_design=payload["why_this_design"],
        created_at=payload["created_at"],
        objective_hash=payload["objective_hash"],
    )


def _candidate_from_dict(payload: Dict[str, Any]) -> SecondExperimentCandidateRecord:
    return SecondExperimentCandidateRecord(
        candidate_id=payload["candidate_id"],
        record_version=payload.get("record_version", CANDIDATE_RECORD_VERSION),
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        objective_id=payload["objective_id"],
        scientific_action_core_hash=payload["scientific_action_core_hash"],
        scientific_identity=dict(payload["scientific_identity"]),
        target_null_key=payload["target_null_key"],
        target_uncertainty=payload["target_uncertainty"],
        scientific_objective=payload["scientific_objective"],
        falsification_rationale=payload["falsification_rationale"],
        informative_observation=payload["informative_observation"],
        cannot_establish=payload["cannot_establish"],
        primary_classification=payload["primary_classification"],
        falsification_capable=bool(payload["falsification_capable"]),
        birth_evidence_overlap_fraction=float(payload["birth_evidence_overlap_fraction"]),
        first_experiment_overlap_fraction=float(payload["first_experiment_overlap_fraction"]),
        birth_independence_profile=dict(payload["birth_independence_profile"]),
        first_experiment_independence_profile=dict(payload["first_experiment_independence_profile"]),
        redundancy_assessment=payload["redundancy_assessment"],
        falsification_capability=payload["falsification_capability"],
        executability_status=payload["executability_status"],
        executability_detail=payload["executability_detail"],
        experiment_spec=payload.get("experiment_spec"),
        representation_envelope=dict(payload.get("representation_envelope") or {}),
        experiment_content_hash=payload["experiment_content_hash"],
        content_hash_differs_from_first=bool(payload["content_hash_differs_from_first"]),
        decision_fidelity_ok=bool(payload["decision_fidelity_ok"]),
        rejection_reasons=tuple(payload.get("rejection_reasons") or ()),
        created_at=payload["created_at"],
        record_hash=payload["record_hash"],
    )


def package_from_dict(payload: Dict[str, Any]) -> SecondExperimentPackage:
    objective = _objective_from_dict(payload["objective"]) if payload.get("objective") else None
    if objective is None:
        raise ValueError("SecondExperimentPackage requires objective")

    candidates = tuple(_candidate_from_dict(c) for c in payload.get("candidates_considered") or [])
    deduped = tuple(_candidate_from_dict(c) for c in payload.get("deduplicated_candidates") or [])

    return SecondExperimentPackage(
        package_id=payload["package_id"],
        record_version=payload.get("record_version", PACKAGE_RECORD_VERSION),
        experiment_ordinal=int(payload.get("experiment_ordinal", 2)),
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        epistemic_update_id=payload["epistemic_update_id"],
        epistemic_update_hash=payload["epistemic_update_hash"],
        research_decision_id=payload["research_decision_id"],
        research_decision_hash=payload["research_decision_hash"],
        research_state_identity=payload["research_state_identity"],
        first_package_id=payload["first_package_id"],
        first_package_hash=payload["first_package_hash"],
        first_execution_id=payload["first_execution_id"],
        first_execution_identity_hash=payload["first_execution_identity_hash"],
        generator_version=payload["generator_version"],
        selector_version=payload["selector_version"],
        design_version=payload.get("design_version", DESIGN_VERSION),
        objective=objective,
        candidates_considered=candidates,
        deduplicated_candidates=deduped,
        rejected=tuple(dict(r) for r in payload.get("rejected") or []),
        ranking_trace=tuple(dict(t) for t in payload.get("ranking_trace") or []),
        disposition=payload["disposition"],
        selected_candidate_id=payload.get("selected_candidate_id"),
        selected_experiment_spec=payload.get("selected_experiment_spec"),
        selected_experiment_content_hash=payload.get("selected_experiment_content_hash"),
        selection_reason=payload.get("selection_reason", ""),
        execution_status=payload.get("execution_status", "NOT_EXECUTED"),
        created_at=payload["created_at"],
        package_hash=payload["package_hash"],
    )


def load_package_index(data_dir: Optional[Path] = None) -> Dict[str, str]:
    path = package_index_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_package_index(index: Dict[str, str], data_dir: Optional[Path] = None) -> Path:
    path = package_index_path(data_dir)
    _atomic_write(path, json.dumps(index, indent=2, sort_keys=True))
    return path


def package_path(package_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = package_id.replace("/", "_")
    return packages_dir(data_dir) / f"{safe}.json"


def compute_index_key(
    *,
    research_decision_hash: str,
    research_state_identity: str,
) -> str:
    return compute_design_identity_hash(
        research_decision_hash=research_decision_hash,
        research_state_identity=research_state_identity,
    )


def persist_second_experiment_package(
    package: SecondExperimentPackage,
    data_dir: Optional[Path] = None,
) -> Path:
    payload = package.to_dict()
    payload["persistence_version"] = PERSISTENCE_VERSION
    path = package_path(package.package_id, data_dir=data_dir)
    _atomic_write(path, json.dumps(payload, indent=2, default=str))
    index = load_package_index(data_dir)
    key = compute_index_key(
        research_decision_hash=package.research_decision_hash,
        research_state_identity=package.research_state_identity,
    )
    index[key] = package.package_id
    save_package_index(index, data_dir=data_dir)
    return path


def lookup_package_by_design_identity(
    design_identity_hash: str,
    data_dir: Optional[Path] = None,
) -> Optional[SecondExperimentPackage]:
    index = load_package_index(data_dir)
    pid = index.get(design_identity_hash)
    if not pid:
        return None
    path = package_path(pid, data_dir=data_dir)
    if not path.exists():
        return None
    return package_from_dict(json.loads(path.read_text(encoding="utf-8")))
