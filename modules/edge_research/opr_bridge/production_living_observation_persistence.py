"""
Phase 3K.1 — Living research observation persistence (append-only assessments/outcomes/summaries).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.production_living_observation_records import (
    DailyResearchAssessment,
    DailyResearchSummary,
    DailyVoiceContract,
    EpistemicDelta,
    MarketDelta,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    ResearchObservationOutcomeRecord,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    ShadowAuthoritySemantics,
    DEFAULT_SHADOW_AUTHORITY,
)
from modules.edge_research.storage import resolve_data_dir

LIVING_PERSISTENCE_VERSION = "living_observation_persistence_v1_3k1"
ASSESSMENTS_DIR = "daily_assessments"
OUTCOMES_DIR = "forward_outcomes"
SUMMARIES_DIR = "daily_summaries"
VOICES_DIR = "daily_voices"
LIVING_INDEX = "living_observation_index.json"
ASSESSMENT_LEDGER = "daily_assessment_ledger.jsonl"
OUTCOME_LEDGER = "forward_outcome_ledger.jsonl"
SUMMARY_LEDGER = "daily_summary_ledger.jsonl"


def living_root(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir) / "production_observations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _subdir(name: str, data_dir: Optional[Path] = None) -> Path:
    path = living_root(data_dir) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def assessment_path(assessment_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = assessment_id.replace("/", "_")
    return _subdir(ASSESSMENTS_DIR, data_dir) / f"{safe}.json"


def outcome_path(outcome_record_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = outcome_record_id.replace("/", "_")
    return _subdir(OUTCOMES_DIR, data_dir) / f"{safe}.json"


def summary_path(summary_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = summary_id.replace("/", "_")
    return _subdir(SUMMARIES_DIR, data_dir) / f"{safe}.json"


def voice_path(assessment_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = assessment_id.replace("/", "_")
    return _subdir(VOICES_DIR, data_dir) / f"{safe}.json"


def assessment_ledger_path(data_dir: Optional[Path] = None) -> Path:
    return living_root(data_dir) / ASSESSMENT_LEDGER


def outcome_ledger_path(data_dir: Optional[Path] = None) -> Path:
    return living_root(data_dir) / OUTCOME_LEDGER


def summary_ledger_path(data_dir: Optional[Path] = None) -> Path:
    return living_root(data_dir) / SUMMARY_LEDGER


def load_living_index(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = living_root(data_dir) / LIVING_INDEX
    if not path.exists():
        return {"version": LIVING_PERSISTENCE_VERSION, "assessments": {}, "outcomes": {}, "summaries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_living_index(index: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    index["version"] = LIVING_PERSISTENCE_VERSION
    _atomic_write(living_root(data_dir) / LIVING_INDEX, json.dumps(index, indent=2, default=str))


def assessment_exists(assessment_id: str, data_dir: Optional[Path] = None) -> bool:
    return assessment_path(assessment_id, data_dir).exists()


def outcome_exists(outcome_record_id: str, data_dir: Optional[Path] = None) -> bool:
    return outcome_path(outcome_record_id, data_dir).exists()


def summary_exists(summary_id: str, data_dir: Optional[Path] = None) -> bool:
    return summary_path(summary_id, data_dir).exists()


def persist_assessment(
    assessment: DailyResearchAssessment,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if assessment_exists(assessment.assessment_id, data_dir) and not allow_overwrite:
        return assessment_path(assessment.assessment_id, data_dir)
    if not assessment.assessment_identity_hash:
        assessment.finalize_hash()
    path = assessment_path(assessment.assessment_id, data_dir)
    _atomic_write(path, json.dumps(assessment.to_dict(), indent=2, default=str))
    _append_jsonl(assessment_ledger_path(data_dir), {
        "assessment_id": assessment.assessment_id,
        "observation_id": assessment.observation_id,
        "assessment_trade_date": assessment.assessment_trade_date,
        "assessment_identity_hash": assessment.assessment_identity_hash,
    })
    index = load_living_index(data_dir)
    index.setdefault("assessments", {})[assessment.assessment_id] = {
        "assessment_id": assessment.assessment_id,
        "observation_id": assessment.observation_id,
        "trade_date": assessment.assessment_trade_date,
        "identity_hash": assessment.assessment_identity_hash,
    }
    save_living_index(index, data_dir)
    return path


def persist_outcome_record(
    outcome: ResearchObservationOutcomeRecord,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if outcome_exists(outcome.outcome_record_id, data_dir) and not allow_overwrite:
        return outcome_path(outcome.outcome_record_id, data_dir)
    path = outcome_path(outcome.outcome_record_id, data_dir)
    _atomic_write(path, json.dumps(outcome.to_dict(), indent=2, default=str))
    _append_jsonl(outcome_ledger_path(data_dir), {
        "outcome_record_id": outcome.outcome_record_id,
        "observation_id": outcome.observation_id,
        "horizon": outcome.horizon,
        "eligible_evaluation_date": outcome.eligible_evaluation_date,
    })
    index = load_living_index(data_dir)
    index.setdefault("outcomes", {})[outcome.outcome_record_id] = {
        "outcome_record_id": outcome.outcome_record_id,
        "observation_id": outcome.observation_id,
        "horizon": outcome.horizon,
    }
    save_living_index(index, data_dir)
    return path


def persist_summary(
    summary: DailyResearchSummary,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if summary_exists(summary.summary_id, data_dir) and not allow_overwrite:
        return summary_path(summary.summary_id, data_dir)
    path = summary_path(summary.summary_id, data_dir)
    _atomic_write(path, json.dumps(summary.to_dict(), indent=2, default=str))
    _append_jsonl(summary_ledger_path(data_dir), {
        "summary_id": summary.summary_id,
        "trade_date": summary.trade_date,
        "provenance_hash": summary.provenance_hash,
    })
    index = load_living_index(data_dir)
    index.setdefault("summaries", {})[summary.summary_id] = {
        "summary_id": summary.summary_id,
        "trade_date": summary.trade_date,
    }
    save_living_index(index, data_dir)
    return path


def persist_voice(voice: DailyVoiceContract, *, data_dir: Optional[Path] = None) -> Path:
    path = voice_path(voice.assessment_id, data_dir)
    _atomic_write(path, json.dumps(voice.to_dict(), indent=2, default=str))
    return path


def lookup_assessment(assessment_id: str, data_dir: Optional[Path] = None) -> Optional[DailyResearchAssessment]:
    path = assessment_path(assessment_id, data_dir)
    if not path.exists():
        return None
    return _assessment_from_dict(json.loads(path.read_text(encoding="utf-8")))


def lookup_latest_assessment_for_observation(
    observation_id: str,
    *,
    before_trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Optional[DailyResearchAssessment]:
    index = load_living_index(data_dir)
    candidates = [
        meta for meta in index.get("assessments", {}).values()
        if meta.get("observation_id") == observation_id
    ]
    if before_trade_date:
        candidates = [c for c in candidates if c.get("trade_date", "") < before_trade_date]
    if not candidates:
        return None
    latest = max(candidates, key=lambda c: c.get("trade_date", ""))
    return lookup_assessment(latest["assessment_id"], data_dir)


def list_assessments_for_observation(
    observation_id: str,
    *,
    data_dir: Optional[Path] = None,
) -> List[DailyResearchAssessment]:
    index = load_living_index(data_dir)
    rows = []
    for meta in index.get("assessments", {}).values():
        if meta.get("observation_id") == observation_id:
            a = lookup_assessment(meta["assessment_id"], data_dir)
            if a:
                rows.append(a)
    return sorted(rows, key=lambda a: a.assessment_trade_date)


def list_outcomes_for_observation(
    observation_id: str,
    *,
    data_dir: Optional[Path] = None,
) -> List[ResearchObservationOutcomeRecord]:
    index = load_living_index(data_dir)
    rows = []
    for meta in index.get("outcomes", {}).values():
        if meta.get("observation_id") == observation_id:
            path = outcome_path(meta["outcome_record_id"], data_dir)
            if path.exists():
                rows.append(_outcome_from_dict(json.loads(path.read_text(encoding="utf-8"))))
    return rows


def list_summaries(*, data_dir: Optional[Path] = None) -> List[DailyResearchSummary]:
    index = load_living_index(data_dir)
    rows = []
    for meta in index.get("summaries", {}).values():
        path = summary_path(meta["summary_id"], data_dir)
        if path.exists():
            rows.append(_summary_from_dict(json.loads(path.read_text(encoding="utf-8"))))
    return sorted(rows, key=lambda s: s.trade_date)


def assert_assessment_immutable(
    assessment_id: str,
    *,
    attempted_mutation: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> bool:
    existing = lookup_assessment(assessment_id, data_dir)
    if existing is None:
        return True
    mutated = dict(existing.to_dict())
    mutated.update(attempted_mutation)
    new_hash = stable_hash({k: v for k, v in mutated.items() if k != "assessment_identity_hash"})
    return new_hash == existing.assessment_identity_hash


def _market_delta_from_dict(d: Dict[str, Any]) -> MarketDelta:
    return MarketDelta(
        regime_changed=bool(d.get("regime_changed")),
        breadth_direction=str(d.get("breadth_direction", "UNKNOWN")),
        transition_direction=str(d.get("transition_direction", "UNKNOWN")),
        dispersion_changed=bool(d.get("dispersion_changed")),
        cohort_relative_changed=bool(d.get("cohort_relative_changed")),
        compatibility_direction=str(d.get("compatibility_direction", "UNKNOWN")),
        summary_keys=tuple(d.get("summary_keys") or []),
        previous_context_hash=str(d.get("previous_context_hash", "")),
        current_context_hash=str(d.get("current_context_hash", "")),
        delta_hash=str(d.get("delta_hash", "")),
    )


def _epistemic_delta_from_dict(d: Dict[str, Any]) -> EpistemicDelta:
    return EpistemicDelta(
        previous_state=d.get("previous_state"),
        current_state=d.get("current_state"),
        changed=bool(d.get("changed")),
        change_kind=str(d.get("change_kind", "UNCHANGED")),
        rationale_keys=tuple(d.get("rationale_keys") or []),
    )


def _shadow_from_dict(d: Optional[Dict[str, Any]]) -> ShadowAuthoritySemantics:
    d = d or {}
    return ShadowAuthoritySemantics(
        research_only=bool(d.get("research_only", True)),
        trading_authority=bool(d.get("trading_authority", False)),
        buy_signal=bool(d.get("buy_signal", False)),
        sell_signal=bool(d.get("sell_signal", False)),
        edge_active=bool(d.get("edge_active", False)),
    )


def _assessment_from_dict(payload: Dict[str, Any]) -> DailyResearchAssessment:
    return DailyResearchAssessment(
        assessment_id=payload["assessment_id"],
        observation_id=payload["observation_id"],
        assessment_trade_date=payload["assessment_trade_date"],
        assessment_timestamp=payload["assessment_timestamp"],
        previous_assessment_id=payload.get("previous_assessment_id"),
        birth_record_hash=payload["birth_record_hash"],
        cutoff_provenance=dict(payload.get("cutoff_provenance") or {}),
        current_market_context_identity=payload["current_market_context_identity"],
        current_market_context_hash=payload["current_market_context_hash"],
        previous_market_context_identity=payload.get("previous_market_context_identity"),
        previous_market_context_hash=payload.get("previous_market_context_hash"),
        market_delta=_market_delta_from_dict(payload.get("market_delta") or {}),
        new_evidence_since_prior=tuple(payload.get("new_evidence_since_prior") or []),
        forward_outcomes_newly_available=tuple(payload.get("forward_outcomes_newly_available") or []),
        current_epistemic_state=payload.get("current_epistemic_state"),
        previous_epistemic_state=payload.get("previous_epistemic_state"),
        epistemic_delta=_epistemic_delta_from_dict(payload.get("epistemic_delta") or {}),
        null_ledger_current=list(payload.get("null_ledger_current") or []),
        null_ledger_delta=tuple(payload.get("null_ledger_delta") or []),
        contradictions=tuple(payload.get("contradictions") or []),
        dependence_warnings=tuple(payload.get("dependence_warnings") or []),
        unresolved_uncertainties=tuple(payload.get("unresolved_uncertainties") or []),
        current_limitations=tuple(payload.get("current_limitations") or []),
        current_research_status=payload.get("current_research_status", "ACTIVE"),
        current_lifecycle_status=payload.get("current_lifecycle_status", "ACTIVE_PENDING"),
        observation_lifecycle_state=payload.get("observation_lifecycle_state", "ACTIVE_PENDING"),
        what_changed=tuple(payload.get("what_changed") or []),
        what_did_not_change=tuple(payload.get("what_did_not_change") or []),
        why_belief_changed_or_not=payload.get("why_belief_changed_or_not", ""),
        what_bot_is_waiting_for=payload.get("what_bot_is_waiting_for", ""),
        next_eligible_evaluation_horizon=payload.get("next_eligible_evaluation_horizon"),
        next_eligible_evaluation_date=payload.get("next_eligible_evaluation_date"),
        observation_age_trading_days=int(payload.get("observation_age_trading_days", 0)),
        change_flags=tuple(payload.get("change_flags") or []),
        shadow_authority=_shadow_from_dict(payload.get("shadow_authority")),
        assessment_identity_hash=payload.get("assessment_identity_hash", ""),
        stale_copy_risk=bool(payload.get("stale_copy_risk")),
    )


def _outcome_from_dict(payload: Dict[str, Any]) -> ResearchObservationOutcomeRecord:
    return ResearchObservationOutcomeRecord(
        outcome_record_id=payload["outcome_record_id"],
        observation_id=payload["observation_id"],
        horizon=payload["horizon"],
        eligible_evaluation_date=payload["eligible_evaluation_date"],
        actual_evaluation_timestamp=payload.get("actual_evaluation_timestamp"),
        realized_outcomes=payload.get("realized_outcomes"),
        evaluation_status=payload.get("evaluation_status", "EVALUATED"),
        data_identity=payload.get("data_identity"),
        missing_handling=payload.get("missing_handling"),
        contract_id=payload["contract_id"],
        contract_hash=payload["contract_hash"],
        provenance=dict(payload.get("provenance") or {}),
    )


def _summary_from_dict(payload: Dict[str, Any]) -> DailyResearchSummary:
    return DailyResearchSummary(
        summary_id=payload["summary_id"],
        trade_date=payload["trade_date"],
        summary_timestamp=payload["summary_timestamp"],
        market_state_summary=dict(payload.get("market_state_summary") or {}),
        most_meaningful_market_delta=payload.get("most_meaningful_market_delta"),
        new_observations_born=tuple(payload.get("new_observations_born") or []),
        active_observations_reassessed=tuple(payload.get("active_observations_reassessed") or []),
        strengthened_count=int(payload.get("strengthened_count", 0)),
        weakened_or_challenged_count=int(payload.get("weakened_or_challenged_count", 0)),
        resolved_or_rejected_count=int(payload.get("resolved_or_rejected_count", 0)),
        silence_or_no_discovery=bool(payload.get("silence_or_no_discovery")),
        newly_arrived_forward_evidence=tuple(payload.get("newly_arrived_forward_evidence") or []),
        most_important_unresolved_question=payload.get("most_important_unresolved_question"),
        what_bot_is_waiting_for=payload.get("what_bot_is_waiting_for", ""),
        provenance_hash=payload.get("provenance_hash", ""),
        shadow_authority=_shadow_from_dict(payload.get("shadow_authority")),
    )
