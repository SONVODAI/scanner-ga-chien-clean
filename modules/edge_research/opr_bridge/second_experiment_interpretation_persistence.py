"""
Phase 3J.8 — Durable second-experiment interpretation persistence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import frozen_ref_from_dict
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
)
from modules.edge_research.opr_bridge.multi_evidence_accounting import (
    CumulativeEvidenceAssessment,
    EvidenceDependenceAccounting,
    IncrementalEvidenceContribution,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    ENVELOPE_VERSION,
    SecondExperimentInterpretationEnvelope,
)
from modules.edge_research.storage import resolve_data_dir

PERSISTENCE_VERSION = "second_experiment_interpretation_persistence_v1_3j8"
INTERPRETATIONS_DIR = "second_experiment_interpretations"
INTERPRETATION_INDEX_FILE = "second_experiment_interpretation_index.json"


def interpretations_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / INTERPRETATIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def interpretation_index_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / INTERPRETATION_INDEX_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _assessment_from_dict(assess_d: Dict[str, Any]) -> IntentAwareEvidenceAssessment:
    null_acct = tuple(
        NullExplanationAccounting(
            null_explanation_text=n["null_explanation_text"],
            null_key=n["null_key"],
            state_before=n["state_before"],
            state_after=n["state_after"],
            rationale=n["rationale"],
        )
        for n in assess_d.get("null_accounting") or []
    )
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary=assess_d["experiment_intent_summary"],
        cohort_strategy=assess_d["cohort_strategy"],
        target_uncertainty=assess_d["target_uncertainty"],
        evidence_relevance=assess_d["evidence_relevance"],
        evidence_direction=assess_d["evidence_direction"],
        evidence_strength=assess_d["evidence_strength"],
        remaining_uncertainty=tuple(assess_d.get("remaining_uncertainty") or ()),
        other_nulls_still_alive=tuple(assess_d.get("other_nulls_still_alive") or ()),
        null_accounting=null_acct,
        base_evidence_class=assess_d["base_evidence_class"],
        condition_matched=assess_d["condition_matched"],
        limitations=tuple(assess_d.get("limitations") or ()),
        tool_semantic_labels_ignored=tuple(assess_d.get("tool_semantic_labels_ignored") or ()),
    )


def _cumulative_from_dict(payload: Dict[str, Any]) -> CumulativeEvidenceAssessment:
    dep = payload["dependence_accounting"]
    inc = payload["incremental_contribution"]
    ledger = tuple(
        NullExplanationAccounting(
            null_explanation_text=n["null_explanation_text"],
            null_key=n["null_key"],
            state_before=n["state_before"],
            state_after=n["state_after"],
            rationale=n["rationale"],
        )
        for n in payload.get("cumulative_null_ledger") or []
    )
    return CumulativeEvidenceAssessment(
        experiment_ordinal=int(payload.get("experiment_ordinal", 2)),
        per_experiment_assessments=tuple(payload.get("per_experiment_assessments") or ()),
        dependence_accounting=EvidenceDependenceAccounting(
            row_overlap_fraction=float(dep["row_overlap_fraction"]),
            null_target_overlap=float(dep["null_target_overlap"]),
            scientific_question_overlap=float(dep["scientific_question_overlap"]),
            sample_dependence_level=str(dep["sample_dependence_level"]),
            question_novelty=str(dep["question_novelty"]),
            evidence_relationship=str(dep["evidence_relationship"]),
            counted_as_independent_replication=bool(dep["counted_as_independent_replication"]),
            independence_rationale=tuple(dep.get("independence_rationale") or ()),
        ),
        incremental_contribution=IncrementalEvidenceContribution(
            raw_evidence_strength=str(inc["raw_evidence_strength"]),
            incremental_strength=str(inc["incremental_strength"]),
            incremental_direction=str(inc["incremental_direction"]),
            double_counting_blocked=bool(inc["double_counting_blocked"]),
            conflict_detected=bool(inc["conflict_detected"]),
            conflict_description=str(inc.get("conflict_description", "")),
            rationale=tuple(inc.get("rationale") or ()),
        ),
        cumulative_null_ledger=ledger,
        cumulative_evidence_summary=str(payload.get("cumulative_evidence_summary", "")),
        limitations=tuple(payload.get("limitations") or ()),
    )


def second_interpretation_envelope_from_dict(payload: Dict[str, Any]) -> SecondExperimentInterpretationEnvelope:
    ref = frozen_ref_from_dict(payload["frozen_contract_ref"])
    return SecondExperimentInterpretationEnvelope(
        interpretation_id=payload["interpretation_id"],
        record_version=payload.get("record_version", ENVELOPE_VERSION),
        experiment_ordinal=int(payload.get("experiment_ordinal", 2)),
        execution_id=payload["execution_id"],
        execution_identity_hash=payload["execution_identity_hash"],
        tool_result_hash=payload["tool_result_hash"],
        package_id=payload["package_id"],
        package_hash=payload["package_hash"],
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        session_id=payload["session_id"],
        scientific_action_core_hash=payload["scientific_action_core_hash"],
        first_interpretation_id=payload["first_interpretation_id"],
        first_execution_id=payload["first_execution_id"],
        frozen_contract_ref=ref,
        base_interpretation=dict(payload["base_interpretation"]),
        evidence_assessment=_assessment_from_dict(payload["evidence_assessment"]),
        cumulative_assessment=_cumulative_from_dict(payload["cumulative_assessment"]),
        epistemic_update=dict(payload["epistemic_update"]),
        prior_epistemic_state=payload["prior_epistemic_state"],
        resulting_epistemic_state=payload["resulting_epistemic_state"],
        interpretation_identity_hash=payload["interpretation_identity_hash"],
        interpreter_version=payload["interpreter_version"],
        research_decision_generated=bool(payload.get("research_decision_generated", False)),
        created_at=payload["created_at"],
        envelope_hash=payload["envelope_hash"],
    )


def load_interpretation_index(data_dir: Optional[Path] = None) -> Dict[str, str]:
    path = interpretation_index_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_interpretation_index(index: Dict[str, str], data_dir: Optional[Path] = None) -> Path:
    path = interpretation_index_path(data_dir)
    _atomic_write(path, json.dumps(index, indent=2, sort_keys=True))
    return path


def interpretation_envelope_path(interpretation_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = interpretation_id.replace("/", "_")
    return interpretations_dir(data_dir) / f"{safe}.json"


def persist_second_interpretation_envelope(
    envelope: SecondExperimentInterpretationEnvelope,
    data_dir: Optional[Path] = None,
) -> Path:
    path = interpretation_envelope_path(envelope.interpretation_id, data_dir=data_dir)
    d = envelope.to_dict()
    d["persistence_version"] = PERSISTENCE_VERSION
    _atomic_write(path, json.dumps(d, indent=2, default=str))
    index = load_interpretation_index(data_dir)
    index[envelope.interpretation_identity_hash] = envelope.interpretation_id
    save_interpretation_index(index, data_dir=data_dir)
    return path


def lookup_second_interpretation_by_identity(
    interpretation_identity_hash: str,
    data_dir: Optional[Path] = None,
) -> Optional[SecondExperimentInterpretationEnvelope]:
    index = load_interpretation_index(data_dir)
    iid = index.get(interpretation_identity_hash)
    if not iid:
        return None
    path = interpretation_envelope_path(iid, data_dir=data_dir)
    if not path.exists():
        return None
    return second_interpretation_envelope_from_dict(json.loads(path.read_text(encoding="utf-8")))
