"""
Phase 3J.0 — Durable OPR production research memory.

Hosts append-only OPR lifecycle records alongside existing Edge Research storage.
Does NOT create a second incompatible memory system — uses data/edge_research/.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import LifecycleKnowledgeState
from modules.edge_research.storage import resolve_data_dir

PERSISTENCE_VERSION = "opr_production_persistence_v1_3j0"
OPR_SESSIONS_DIR = "opr_research_sessions"
OPR_REGISTRY_FILE = "opr_opportunity_registry.json"


def opr_sessions_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / OPR_SESSIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def opr_session_path(session_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = session_id.replace("/", "_").replace("\\", "_")
    return opr_sessions_dir(data_dir) / f"{safe}.json"


def opr_registry_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / OPR_REGISTRY_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class OprProductionSessionRecord:
    """Durable production OPR session — authoritative research memory."""

    session_id: str
    opportunity_identity: str
    replay_identity: str
    proposition_id: str
    proposition_hash: str
    data_cutoff_date: str
    evidence_cutoff_hash: str
    research_activity_state: str = "ACTIVE"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    persistence_version: str = PERSISTENCE_VERSION
    proposition_record: Dict[str, Any] = field(default_factory=dict)
    knowledge_state: Dict[str, Any] = field(default_factory=dict)
    stop_boundaries_reached: List[str] = field(default_factory=list)
    lineage_artifacts: List[str] = field(default_factory=list)
    initial_experiment_package: Optional[Dict[str, Any]] = None
    first_experiment_execution: Optional[Dict[str, Any]] = None
    frozen_interpretation_contract: Optional[Dict[str, Any]] = None
    first_experiment_interpretation: Optional[Dict[str, Any]] = None
    first_experiment_epistemic_update: Optional[Dict[str, Any]] = None

    def record_hash(self) -> str:
        return stable_hash(
            {
                "session_id": self.session_id,
                "opportunity_identity": self.opportunity_identity,
                "proposition_hash": self.proposition_hash,
                "evidence_cutoff_hash": self.evidence_cutoff_hash,
                "persistence_version": self.persistence_version,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "opportunity_identity": self.opportunity_identity,
            "replay_identity": self.replay_identity,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "data_cutoff_date": self.data_cutoff_date,
            "evidence_cutoff_hash": self.evidence_cutoff_hash,
            "research_activity_state": self.research_activity_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "persistence_version": self.persistence_version,
            "proposition_record": self.proposition_record,
            "knowledge_state": self.knowledge_state,
            "stop_boundaries_reached": list(self.stop_boundaries_reached),
            "lineage_artifacts": list(self.lineage_artifacts),
            "initial_experiment_package": self.initial_experiment_package,
            "first_experiment_execution": self.first_experiment_execution,
            "frozen_interpretation_contract": self.frozen_interpretation_contract,
            "first_experiment_interpretation": self.first_experiment_interpretation,
            "first_experiment_epistemic_update": self.first_experiment_epistemic_update,
            "record_hash": self.record_hash(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OprProductionSessionRecord":
        return cls(
            session_id=payload["session_id"],
            opportunity_identity=payload["opportunity_identity"],
            replay_identity=payload["replay_identity"],
            proposition_id=payload["proposition_id"],
            proposition_hash=payload["proposition_hash"],
            data_cutoff_date=payload["data_cutoff_date"],
            evidence_cutoff_hash=payload["evidence_cutoff_hash"],
            research_activity_state=payload.get("research_activity_state", "ACTIVE"),
            created_at=payload.get("created_at", utc_now_iso()),
            updated_at=payload.get("updated_at", utc_now_iso()),
            persistence_version=payload.get("persistence_version", PERSISTENCE_VERSION),
            proposition_record=dict(payload.get("proposition_record") or {}),
            knowledge_state=dict(payload.get("knowledge_state") or {}),
            stop_boundaries_reached=list(payload.get("stop_boundaries_reached") or []),
            lineage_artifacts=list(payload.get("lineage_artifacts") or []),
            initial_experiment_package=payload.get("initial_experiment_package"),
            first_experiment_execution=payload.get("first_experiment_execution"),
            frozen_interpretation_contract=payload.get("frozen_interpretation_contract"),
            first_experiment_interpretation=payload.get("first_experiment_interpretation"),
            first_experiment_epistemic_update=payload.get("first_experiment_epistemic_update"),
        )


def write_opr_session(record: OprProductionSessionRecord, data_dir: Optional[Path] = None) -> Path:
    record.updated_at = utc_now_iso()
    path = opr_session_path(record.session_id, data_dir=data_dir)
    _atomic_write(path, json.dumps(record.to_dict(), indent=2, default=str))
    return path


def read_opr_session(session_id: str, data_dir: Optional[Path] = None) -> OprProductionSessionRecord:
    path = opr_session_path(session_id, data_dir=data_dir)
    if not path.exists():
        raise FileNotFoundError(f"OPR session not found: {session_id}")
    return OprProductionSessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_opportunity_registry(data_dir: Optional[Path] = None) -> Dict[str, str]:
    path = opr_registry_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_opportunity_registry(registry: Dict[str, str], data_dir: Optional[Path] = None) -> Path:
    path = opr_registry_path(data_dir)
    _atomic_write(path, json.dumps(registry, indent=2, sort_keys=True))
    return path


def register_opportunity(
    opportunity_identity: str,
    session_id: str,
    data_dir: Optional[Path] = None,
) -> None:
    reg = load_opportunity_registry(data_dir)
    reg[opportunity_identity] = session_id
    save_opportunity_registry(reg, data_dir)


def lookup_opportunity_session(
    opportunity_identity: str,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    return load_opportunity_registry(data_dir).get(opportunity_identity)


def serialize_knowledge_state(state: LifecycleKnowledgeState) -> Dict[str, Any]:
    return {
        "proposition_id": state.proposition_id,
        "evidence_events": list(state.evidence_events),
        "synthesis_history": list(state.synthesis_history),
        "priority_history": list(state.priority_history),
        "frontier_history": list(state.frontier_history),
        "dormancy_history": list(state.dormancy_history),
        "reopening_history": list(state.reopening_history),
        "research_activity_state": state.research_activity_state,
        "_dormancy_idempotency_keys": list(state._dormancy_idempotency_keys),
        "_opportunity_hashes_seen": list(state._opportunity_hashes_seen),
        "_abstract_evidence_specs": state._abstract_evidence_specs,
    }


def deserialize_knowledge_state(payload: Dict[str, Any]) -> LifecycleKnowledgeState:
    state = LifecycleKnowledgeState(proposition_id=payload["proposition_id"])
    state.evidence_events = list(payload.get("evidence_events") or [])
    state.synthesis_history = list(payload.get("synthesis_history") or [])
    state.priority_history = list(payload.get("priority_history") or [])
    state.frontier_history = list(payload.get("frontier_history") or [])
    state.dormancy_history = list(payload.get("dormancy_history") or [])
    state.reopening_history = list(payload.get("reopening_history") or [])
    state.research_activity_state = payload.get("research_activity_state", "ACTIVE")
    state._dormancy_idempotency_keys = list(payload.get("_dormancy_idempotency_keys") or [])
    state._opportunity_hashes_seen = list(payload.get("_opportunity_hashes_seen") or [])
    state._abstract_evidence_specs = payload.get("_abstract_evidence_specs")
    return state


def reconstruct_session_authoritative_state(
    record: OprProductionSessionRecord,
) -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import (
        reconstruct_authoritative_state,
    )

    if not record.knowledge_state:
        return {
            "proposition_id": record.proposition_id,
            "proposition_hash": record.proposition_hash,
            "research_activity_state": record.research_activity_state,
            "evidence_event_count": 0,
        }
    state = deserialize_knowledge_state(record.knowledge_state)
    auth = reconstruct_authoritative_state(state)
    auth["session_id"] = record.session_id
    auth["opportunity_identity"] = record.opportunity_identity
    return auth
