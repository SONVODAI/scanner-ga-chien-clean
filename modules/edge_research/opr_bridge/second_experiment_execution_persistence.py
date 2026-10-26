"""
Phase 3J.7 — Durable second-experiment execution persistence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.first_experiment_execution_records import ExecutionBindingAudit
from modules.edge_research.opr_bridge.second_experiment_execution_records import (
    ENVELOPE_VERSION,
    SecondExperimentExecutionEnvelope,
)
from modules.edge_research.storage import resolve_data_dir

PERSISTENCE_VERSION = "second_experiment_execution_persistence_v1_3j7"
EXECUTIONS_DIR = "second_experiment_executions"
EXECUTION_INDEX_FILE = "second_experiment_execution_index.json"


def executions_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / EXECUTIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def execution_index_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / EXECUTION_INDEX_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def envelope_from_dict(payload: Dict[str, Any]) -> SecondExperimentExecutionEnvelope:
    audit_d = payload["binding_audit"]
    audit = ExecutionBindingAudit(
        scientific_spec_hash=audit_d["scientific_spec_hash"],
        execution_spec_hash=audit_d["execution_spec_hash"],
        scientific_action_core_hash=audit_d["scientific_action_core_hash"],
        population_spec=dict(audit_d["population_spec"]),
        outcome_spec=dict(audit_d["outcome_spec"]),
        observation_horizon=int(audit_d["observation_horizon"]),
        tool_name=audit_d["tool_name"],
        tool_version=audit_d["tool_version"],
        inputs=dict(audit_d["inputs"]),
        binding_notes=tuple(audit_d.get("binding_notes") or ()),
    )
    return SecondExperimentExecutionEnvelope(
        execution_id=payload["execution_id"],
        record_version=payload.get("record_version", ENVELOPE_VERSION),
        experiment_ordinal=int(payload.get("experiment_ordinal", 2)),
        package_id=payload["package_id"],
        package_hash=payload["package_hash"],
        research_decision_id=payload["research_decision_id"],
        research_decision_hash=payload["research_decision_hash"],
        first_execution_id=payload["first_execution_id"],
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        session_id=payload["session_id"],
        selected_candidate_id=payload["selected_candidate_id"],
        scientific_action_core_hash=payload["scientific_action_core_hash"],
        experiment_content_hash=payload["experiment_content_hash"],
        execution_identity_hash=payload["execution_identity_hash"],
        target_null_key=payload["target_null_key"],
        target_uncertainty=payload["target_uncertainty"],
        novelty_decomposition=dict(payload.get("novelty_decomposition") or {}),
        binding_audit=audit,
        tool_result=dict(payload["tool_result"]),
        tool_result_hash=payload["tool_result_hash"],
        raw_quintile_metrics=payload.get("raw_quintile_metrics"),
        panel_provenance_hash=payload["panel_provenance_hash"],
        execution_outcome=payload["execution_outcome"],
        tool_status=payload["tool_status"],
        sample_size=int(payload.get("sample_size", 0)),
        warnings=tuple(payload.get("warnings") or ()),
        errors=tuple(payload.get("errors") or ()),
        executor_version=payload["executor_version"],
        interpretation_generated=bool(payload.get("interpretation_generated", False)),
        research_decision_generated=bool(payload.get("research_decision_generated", False)),
        created_at=payload["created_at"],
        envelope_hash=payload["envelope_hash"],
    )


def envelope_to_dict(envelope: SecondExperimentExecutionEnvelope) -> Dict[str, Any]:
    d = envelope.to_dict()
    d["persistence_version"] = PERSISTENCE_VERSION
    return d


def load_execution_index(data_dir: Optional[Path] = None) -> Dict[str, str]:
    path = execution_index_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_execution_index(index: Dict[str, str], data_dir: Optional[Path] = None) -> Path:
    path = execution_index_path(data_dir)
    _atomic_write(path, json.dumps(index, indent=2, sort_keys=True))
    return path


def execution_envelope_path(execution_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = execution_id.replace("/", "_")
    return executions_dir(data_dir) / f"{safe}.json"


def persist_second_execution_envelope(
    envelope: SecondExperimentExecutionEnvelope,
    data_dir: Optional[Path] = None,
) -> Path:
    path = execution_envelope_path(envelope.execution_id, data_dir=data_dir)
    _atomic_write(path, json.dumps(envelope_to_dict(envelope), indent=2, default=str))
    index = load_execution_index(data_dir)
    index[envelope.execution_identity_hash] = envelope.execution_id
    save_execution_index(index, data_dir=data_dir)
    return path


def lookup_second_execution_by_identity(
    execution_identity_hash: str,
    data_dir: Optional[Path] = None,
) -> Optional[SecondExperimentExecutionEnvelope]:
    index = load_execution_index(data_dir)
    eid = index.get(execution_identity_hash)
    if not eid:
        return None
    path = execution_envelope_path(eid, data_dir=data_dir)
    if not path.exists():
        return None
    return envelope_from_dict(json.loads(path.read_text(encoding="utf-8")))
