"""
Phase 3J.9 — Durable second cumulative research decision persistence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    CandidateActionEvaluation,
    SearchAccountingContext,
)
from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
    DECIDER_VERSION,
    SecondExperimentResearchDecisionEnvelope,
)
from modules.edge_research.storage import resolve_data_dir

DECISIONS_DIR = "second_experiment_research_decisions"
DECISION_INDEX_FILE = "second_experiment_research_decision_index.json"
PERSISTENCE_VERSION = "second_experiment_research_decision_persistence_v1_3j9"


def decisions_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / DECISIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def decision_index_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / DECISION_INDEX_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def decision_envelope_from_dict(payload: Dict[str, Any]) -> SecondExperimentResearchDecisionEnvelope:
    evals = tuple(
        CandidateActionEvaluation(
            action_family=e["action_family"],
            mapped_action_code=e["mapped_action_code"],
            scientific_objective=e["scientific_objective"],
            target_uncertainty=e["target_uncertainty"],
            target_null_key=e.get("target_null_key"),
            expected_information_contribution=e["expected_information_contribution"],
            independence_requirement=e["independence_requirement"],
            admissible=bool(e["admissible"]),
            rejection_reasons=tuple(e.get("rejection_reasons") or ()),
            redundancy_score=float(e.get("redundancy_score", 0.0)),
            information_gain_rank=int(e.get("information_gain_rank", 0)),
        )
        for e in payload.get("candidate_evaluations") or []
    )
    sa = payload.get("search_accounting") or {}
    search = SearchAccountingContext(
        experiments_attempted=int(sa.get("experiments_attempted", 2)),
        search_complexity_score=float(sa.get("search_complexity_score", 0.0)),
        search_cardinality=int(sa.get("search_cardinality", 2)),
        evidence_burden_assessment=str(sa.get("evidence_burden_assessment", "HIGH")),
        budget_exhausted=bool(sa.get("budget_exhausted", False)),
    )
    return SecondExperimentResearchDecisionEnvelope(
        decision_envelope_id=payload["decision_envelope_id"],
        record_version=payload["record_version"],
        decision_ordinal=int(payload.get("decision_ordinal", 2)),
        interpretation_id=payload["interpretation_id"],
        interpretation_identity_hash=payload["interpretation_identity_hash"],
        epistemic_update_id=payload["epistemic_update_id"],
        epistemic_update_hash=payload["epistemic_update_hash"],
        first_decision_envelope_id=payload["first_decision_envelope_id"],
        first_decision_hash=payload["first_decision_hash"],
        first_interpretation_id=payload["first_interpretation_id"],
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        session_id=payload["session_id"],
        cumulative_research_state_identity=payload["cumulative_research_state_identity"],
        research_decision=dict(payload["research_decision"]),
        decision_kind=payload["decision_kind"],
        stop_reason=payload.get("stop_reason"),
        cumulative_null_ledger=tuple(payload.get("cumulative_null_ledger") or ()),
        surviving_nulls=tuple(payload.get("surviving_nulls") or ()),
        candidate_evaluations=evals,
        search_accounting=search,
        dependence_summary=dict(payload.get("dependence_summary") or {}),
        incremental_evidence_summary=dict(payload.get("incremental_evidence_summary") or {}),
        confirmation_bias_guard_applied=bool(payload.get("confirmation_bias_guard_applied", False)),
        mechanical_sequencing_blocked=bool(payload.get("mechanical_sequencing_blocked", False)),
        third_experiment_generated=bool(payload.get("third_experiment_generated", False)),
        third_experiment_executed=bool(payload.get("third_experiment_executed", False)),
        decider_version=payload["decider_version"],
        created_at=payload["created_at"],
        envelope_hash=payload["envelope_hash"],
    )


def load_decision_index(data_dir: Optional[Path] = None) -> Dict[str, str]:
    path = decision_index_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_decision_index(index: Dict[str, str], data_dir: Optional[Path] = None) -> Path:
    path = decision_index_path(data_dir)
    _atomic_write(path, json.dumps(index, indent=2, sort_keys=True))
    return path


def decision_envelope_path(decision_envelope_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = decision_envelope_id.replace("/", "_")
    return decisions_dir(data_dir) / f"{safe}.json"


def compute_index_key(envelope: SecondExperimentResearchDecisionEnvelope) -> str:
    from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
        compute_second_decision_identity_hash,
    )

    return compute_second_decision_identity_hash(
        interpretation_identity_hash=envelope.interpretation_identity_hash,
        epistemic_update_hash=envelope.epistemic_update_hash,
        first_decision_hash=envelope.first_decision_hash,
        decider_version=DECIDER_VERSION,
    )


def persist_decision_envelope(
    envelope: SecondExperimentResearchDecisionEnvelope,
    data_dir: Optional[Path] = None,
) -> Path:
    payload = envelope.to_dict()
    payload["persistence_version"] = PERSISTENCE_VERSION
    path = decision_envelope_path(envelope.decision_envelope_id, data_dir=data_dir)
    _atomic_write(path, json.dumps(payload, indent=2, default=str))
    index = load_decision_index(data_dir)
    key = compute_index_key(envelope)
    index[key] = envelope.decision_envelope_id
    save_decision_index(index, data_dir=data_dir)
    return path


def lookup_decision_by_identity(
    decision_identity_hash: str,
    data_dir: Optional[Path] = None,
) -> Optional[SecondExperimentResearchDecisionEnvelope]:
    index = load_decision_index(data_dir)
    did = index.get(decision_identity_hash)
    if not did:
        return None
    path = decision_envelope_path(did, data_dir=data_dir)
    if not path.exists():
        return None
    return decision_envelope_from_dict(json.loads(path.read_text(encoding="utf-8")))
