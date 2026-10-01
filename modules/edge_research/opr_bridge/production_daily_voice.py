"""
Phase 3K.1 — Daily Vietnamese narrative renderer (presentation layer only).

Every material claim traces to structured assessment fields.
No persuasive trading language. No hidden template intelligence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_living_observation_records import (
    DailyResearchAssessment,
    DailyVoiceContract,
)
from modules.edge_research.opr_bridge.production_observation_narrative import assert_narrative_faithful


def _join_keys(keys: tuple, fallback: str = "không có") -> str:
    return ", ".join(str(k) for k in keys) if keys else fallback


def render_daily_voice(assessment: DailyResearchAssessment) -> DailyVoiceContract:
    """Build DailyVoiceContract from structured assessment — Vietnamese presentation only."""
    ep = assessment.current_epistemic_state or "UNRESOLVED"
    prev_ep = assessment.previous_epistemic_state or ep
    mkt = assessment.market_delta
    changed = assessment.what_changed
    unchanged = assessment.what_did_not_change
    lifecycle = assessment.observation_lifecycle_state

    q1 = (
        f"Hôm nay ({assessment.assessment_trade_date}) tôi thấy epistemic state là {ep}. "
        f"Lifecycle: {lifecycle}. Research status: {assessment.current_research_status}."
    )

    if assessment.previous_assessment_id:
        q2 = (
            f"So với phiên trước, thay đổi: {_join_keys(changed)}. "
            f"Không đổi: {_join_keys(unchanged)}."
        )
    else:
        q2 = "Đây là assessment đầu tiên sau birth — chưa có phiên trước để so sánh."

    q3 = (
        f"Market delta: {_join_keys(mkt.summary_keys)}. "
        f"Breadth: {mkt.breadth_direction}. Transition: {mkt.transition_direction}. "
        f"Compatibility: {mkt.compatibility_direction}."
    )

    q4 = (
        f"Evidence mới: {_join_keys(assessment.new_evidence_since_prior)}. "
        f"Forward outcomes mới: {_join_keys(assessment.forward_outcomes_newly_available)}."
    )

    belief_changed = assessment.epistemic_delta.changed
    q5 = (
        f"Quan điểm {'đã thay đổi' if belief_changed else 'không thay đổi'} "
        f"({prev_ep} → {ep})."
    )

    q6 = assessment.why_belief_changed_or_not or (
        "Không có lý do được ghi — structured state thiếu why_belief_changed_or_not."
    )

    q7 = f"Điều chống lại hypothesis: {_join_keys(assessment.contradictions)}."

    q8 = (
        f"Chưa biết: {_join_keys(assessment.unresolved_uncertainties)}. "
        f"Limitations: {_join_keys(assessment.current_limitations)}."
    )

    q9 = assessment.what_bot_is_waiting_for or "Không có horizon pending."

    q10 = (
        f"Observation {assessment.observation_id} age {assessment.observation_age_trading_days} trading days. "
        f"Next eligible: {assessment.next_eligible_evaluation_horizon or 'none'} "
        f"on {assessment.next_eligible_evaluation_date or 'N/A'}."
    )

    trace = {
        "assessment_id": assessment.assessment_id,
        "current_epistemic_state": ep,
        "previous_epistemic_state": prev_ep,
        "change_flags": list(assessment.change_flags),
        "market_delta_hash": mkt.delta_hash,
        "stale_copy_risk": assessment.stale_copy_risk,
        "structured_trace_only": True,
    }

    return DailyVoiceContract(
        assessment_id=assessment.assessment_id,
        observation_id=assessment.observation_id,
        assessment_trade_date=assessment.assessment_trade_date,
        q1_today_i_see_vi=q1,
        q2_vs_prior_session_vi=q2,
        q3_market_change_vi=q3,
        q4_new_evidence_vi=q4,
        q5_belief_changed_vi=q5,
        q6_if_not_why_vi=q6,
        q7_counter_hypothesis_vi=q7,
        q8_still_unknown_vi=q8,
        q9_waiting_for_vi=q9,
        q10_old_observations_vi=q10,
        structured_trace=trace,
    )


def assert_voice_faithful(assessment: DailyResearchAssessment, voice: DailyVoiceContract) -> bool:
    """
    CF-LIVE11 — reject narrator upgrades beyond structured epistemic state.
    """
    ep = assessment.current_epistemic_state or "UNRESOLVED"
    combined = " ".join([
        voice.q1_today_i_see_vi,
        voice.q5_belief_changed_vi,
        voice.q6_if_not_why_vi,
    ]).upper()
    forbidden_upgrades = ["CONFIRMED", "STRONG BUY", "STRONG SELL", "BUY", "SELL"]
    for tok in forbidden_upgrades:
        if tok in combined and tok not in ep.upper():
            return False
    return assert_narrative_faithful(ep, ep)


def audit_stale_copy(assessment: DailyResearchAssessment, voice: DailyVoiceContract) -> Dict[str, Any]:
    """CF-LIVE9 — stale presentation audit."""
    market_changed = any(k != "market:unchanged" for k in assessment.market_delta.summary_keys)
    belief_unchanged = not assessment.epistemic_delta.changed
    has_temporal_explanation = bool(assessment.why_belief_changed_or_not)
    passed = not assessment.stale_copy_risk
    if market_changed and belief_unchanged:
        passed = passed and has_temporal_explanation
    return {
        "passed": passed,
        "stale_copy_risk": assessment.stale_copy_risk,
        "market_changed": market_changed,
        "belief_unchanged": belief_unchanged,
        "has_temporal_explanation": has_temporal_explanation,
    }
