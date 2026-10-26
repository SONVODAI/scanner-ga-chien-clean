"""
Phase 3K.1 — Living research observation read model (future UI contract, no Streamlit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_daily_voice import render_daily_voice
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    list_assessments_for_observation,
    list_outcomes_for_observation,
    list_summaries,
    lookup_assessment,
    lookup_latest_assessment_for_observation,
    voice_path,
)
from modules.edge_research.opr_bridge.production_living_observation_records import READ_MODEL_VERSION
from modules.edge_research.opr_bridge.production_observation_persistence import lookup_birth_record


def build_today_read_model(
    *,
    trade_date: str,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """TODAY section — daily voice, market delta, belief delta, active observations."""
    summaries = [s for s in list_summaries(data_dir=data_dir) if s.trade_date == trade_date]
    summary = summaries[0] if summaries else None

    index = _load_assessment_index_for_date(trade_date, data_dir)
    voices = []
    assessments = []
    for aid in index:
        a = lookup_assessment(aid, data_dir)
        if a:
            assessments.append(a)
            vpath = voice_path(a.assessment_id, data_dir)
            if vpath.exists():
                import json
                voices.append(json.loads(vpath.read_text(encoding="utf-8")))
            else:
                voices.append(render_daily_voice(a).to_dict())

    return {
        "section": "TODAY",
        "trade_date": trade_date,
        "version": READ_MODEL_VERSION,
        "daily_summary": summary.to_dict() if summary else None,
        "daily_voices": voices,
        "market_deltas": [a.market_delta.to_dict() for a in assessments],
        "belief_deltas": [a.epistemic_delta.to_dict() for a in assessments],
        "active_observations": [
            {
                "observation_id": a.observation_id,
                "lifecycle": a.observation_lifecycle_state,
                "epistemic_state": a.current_epistemic_state,
                "what_changed": list(a.what_changed),
            }
            for a in assessments
        ],
        "new_forward_evidence": [
            oid for a in assessments for oid in a.forward_outcomes_newly_available
        ],
        "unresolved_questions": [
            q for a in assessments for q in a.unresolved_uncertainties
        ],
        "shadow_authority": {"research_only": True, "trading_authority": False},
    }


def build_observation_detail_read_model(
    observation_id: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """OBSERVATION DETAIL — birth, timeline, T3/T5/T10, current state."""
    birth = lookup_birth_record(observation_id, data_dir=data_dir)
    if birth is None:
        return {"section": "OBSERVATION_DETAIL", "error": "birth_not_found", "observation_id": observation_id}

    assessments = list_assessments_for_observation(observation_id, data_dir=data_dir)
    outcomes = list_outcomes_for_observation(observation_id, data_dir=data_dir)
    latest = assessments[-1] if assessments else None

    return {
        "section": "OBSERVATION_DETAIL",
        "observation_id": observation_id,
        "version": READ_MODEL_VERSION,
        "at_birth": {
            "original_belief": birth.final_epistemic_state,
            "original_evidence": birth.strongest_evidence,
            "original_limitations": list(birth.limitations),
            "birth_record_hash": birth.birth_record_hash,
            "birth_timestamp": birth.birth_timestamp,
        },
        "today": {
            "current_assessment": latest.to_dict() if latest else None,
            "what_changed": list(latest.what_changed) if latest else [],
            "why": latest.why_belief_changed_or_not if latest else None,
        } if latest else None,
        "forward": {
            h.horizon: {
                "status": h.status,
                "eligible_date": h.eligible_evaluation_date,
                "realized_outcome": h.realized_outcome,
            }
            for h in birth.forward_horizons
        },
        "outcome_records": [o.to_dict() for o in outcomes],
        "assessment_timeline": [a.to_dict() for a in assessments],
        "current_state": {
            "epistemic": latest.current_epistemic_state if latest else birth.final_epistemic_state,
            "lifecycle": latest.observation_lifecycle_state if latest else "BORN",
        },
        "evidence_null_history": {
            "null_ledger": latest.null_ledger_current if latest else birth.null_ledger_summary,
            "surviving_nulls": list(birth.surviving_nulls),
        },
    }


def build_history_read_model(
    *,
    data_dir: Optional[Path] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    """HISTORY — prior daily summaries, silence/rejected records, calibration placeholders."""
    summaries = list_summaries(data_dir=data_dir)[-limit:]
    return {
        "section": "HISTORY",
        "version": READ_MODEL_VERSION,
        "daily_summaries": [s.to_dict() for s in summaries],
        "silence_days": [s.trade_date for s in summaries if s.silence_or_no_discovery],
        "calibration_placeholders": {
            "note": "Calibration data not yet populated — Phase 3K.2 boundary",
            "forward_outcome_count": sum(len(s.newly_arrived_forward_evidence) for s in summaries),
        },
        "rejected_or_negative": [
            {"trade_date": s.trade_date, "resolved_count": s.resolved_or_rejected_count}
            for s in summaries if s.resolved_or_rejected_count > 0
        ],
    }


def build_full_read_model(
    *,
    trade_date: str,
    observation_ids: Optional[List[str]] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    return {
        "today": build_today_read_model(trade_date=trade_date, data_dir=data_dir),
        "observations": [
            build_observation_detail_read_model(oid, data_dir=data_dir)
            for oid in (observation_ids or [])
        ],
        "history": build_history_read_model(data_dir=data_dir),
        "version": READ_MODEL_VERSION,
    }


def _load_assessment_index_for_date(trade_date: str, data_dir: Optional[Path]) -> List[str]:
    from modules.edge_research.opr_bridge.production_living_observation_persistence import load_living_index
    index = load_living_index(data_dir)
    return [
        meta["assessment_id"]
        for meta in index.get("assessments", {}).values()
        if meta.get("trade_date") == trade_date
    ]
