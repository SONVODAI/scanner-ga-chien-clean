"""
Phase 3K.1 — Daily research assessment orchestrator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_daily_voice import render_daily_voice
from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import (
    evaluate_eligible_outcomes,
    interpret_outcome_evidence,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    assessment_exists,
    list_outcomes_for_observation,
    lookup_assessment,
    lookup_latest_assessment_for_observation,
    persist_assessment,
    persist_outcome_record,
    persist_voice,
)
from modules.edge_research.opr_bridge.production_living_observation_records import (
    ChangeKind,
    DailyResearchAssessment,
    DailyResearchSummary,
    EpistemicDelta,
    compute_daily_assessment_identity,
    new_assessment_id,
    new_summary_id,
    DEFAULT_SHADOW_AUTHORITY,
)
from modules.edge_research.opr_bridge.production_market_delta import (
    compute_market_delta,
    extract_market_snapshot,
)
from modules.edge_research.opr_bridge.production_observation_cutoff import (
    compute_market_context_identity,
    truncate_panel_at_cutoff,
    validate_temporal_provenance,
)
from modules.edge_research.opr_bridge.production_observation_persistence import lookup_birth_record
from modules.edge_research.opr_bridge.production_observation_records import (
    ResearchObservationBirthRecord,
)
from modules.edge_research.opr_bridge.production_observation_lifecycle import (
    compute_observation_age_trading_days,
    derive_epistemic_update,
    derive_lifecycle_state,
    detect_stale_copy_risk,
    reject_artificial_belief_change,
)


def _next_pending_horizon(birth: ResearchObservationBirthRecord, assessment_date: str) -> Tuple[Optional[str], Optional[str]]:
    pending = [
        h for h in birth.forward_horizons
        if h.status in ("PENDING_FUTURE", "ELIGIBLE") and h.realized_outcome is None
    ]
    if not pending:
        return None, None
    nxt = min(pending, key=lambda h: h.eligible_evaluation_date or "9999")
    return nxt.horizon, nxt.eligible_evaluation_date


def _build_why_belief_text(
    *,
    belief_changed: bool,
    epistemic_delta: EpistemicDelta,
    market_delta_keys: Tuple[str, ...],
    new_evidence: Tuple[str, ...],
    current_ep: Optional[str],
) -> str:
    if belief_changed:
        return (
            f"Epistemic state changed ({epistemic_delta.previous_state} → {epistemic_delta.current_state}) "
            f"due to {epistemic_delta.change_kind}: {_join_rationale(epistemic_delta.rationale_keys)}."
        )
    market_changed = any(k != "market:unchanged" for k in market_delta_keys)
    if market_changed and new_evidence:
        return (
            f"Epistemic state remains {current_ep}. Market changed ({_join_rationale(market_delta_keys)}) "
            f"and new evidence arrived ({_join_rationale(new_evidence)}), but it does not materially "
            f"address the surviving null; therefore the scientific conclusion is unchanged."
        )
    if market_changed:
        return (
            f"Epistemic state remains {current_ep}. Market context changed ({_join_rationale(market_delta_keys)}), "
            f"but no relevant new evidence arrived to justify changing belief."
        )
    return (
        f"Epistemic state remains {current_ep}. No material market or evidence change since prior assessment."
    )


def _join_rationale(keys: Tuple[str, ...]) -> str:
    return "; ".join(str(k) for k in keys) if keys else "none"


def build_daily_assessment(
    panel: pd.DataFrame,
    birth: ResearchObservationBirthRecord,
    *,
    assessment_trade_date: str,
    trading_dates: Optional[List[str]] = None,
    data_dir: Optional[Path] = None,
    persist: bool = True,
    replay_mode: Optional[str] = None,
) -> Tuple[DailyResearchAssessment, List[Any]]:
    """
    Build append-only DailyResearchAssessment for one observation on one trading day.
    Returns (assessment, new_outcome_records).
    """
    truncated, diag = truncate_panel_at_cutoff(panel, assessment_trade_date)
    ok, errors = validate_temporal_provenance(truncated, assessment_trade_date, diag)
    if not ok:
        raise ValueError(f"temporal_provenance_failed:{';'.join(errors)}")

    dates = trading_dates or sorted(truncated["trade_date"].astype(str).unique().tolist())
    prev_date = None
    for i, d in enumerate(dates):
        if d == assessment_trade_date and i > 0:
            prev_date = dates[i - 1]
            break

    prev_assessment = lookup_latest_assessment_for_observation(
        birth.observation_id,
        before_trade_date=assessment_trade_date,
        data_dir=data_dir,
    )
    existing_outcomes = list_outcomes_for_observation(birth.observation_id, data_dir=data_dir)
    existing_ids = tuple(o.outcome_record_id for o in existing_outcomes)

    new_outcomes, _ = evaluate_eligible_outcomes(
        truncated,
        birth,
        assessment_trade_date=assessment_trade_date,
        existing_outcome_ids=existing_ids,
    )
    if persist:
        for o in new_outcomes:
            persist_outcome_record(o, data_dir=data_dir)

    all_outcomes = existing_outcomes + new_outcomes
    interpretations = [interpret_outcome_evidence(birth=birth, outcome=o) for o in new_outcomes]
    new_evidence_keys = tuple(
        f"forward_outcome:{o.horizon}:{o.outcome_record_id}" for o in new_outcomes
    )

    prev_ep = (
        prev_assessment.current_epistemic_state
        if prev_assessment
        else birth.final_epistemic_state
    )
    current_ep, change_kind, rationale, belief_changed = derive_epistemic_update(
        birth=birth,
        previous_epistemic=prev_ep,
        new_outcome_interpretations=interpretations,
        new_evidence_keys=new_evidence_keys,
    )

    allowed, reject_reason = reject_artificial_belief_change(
        previous_epistemic=prev_ep,
        proposed_epistemic=current_ep,
        new_evidence_keys=new_evidence_keys,
        new_outcome_interpretations=interpretations,
    )
    if not allowed:
        current_ep = prev_ep
        belief_changed = False
        change_kind = ChangeKind.UNCHANGED

    ctx_id, ctx_hash = compute_market_context_identity(truncated, assessment_trade_date)
    prev_ctx_id = prev_assessment.current_market_context_identity if prev_assessment else birth.cutoff.market_context_identity
    prev_ctx_hash = prev_assessment.current_market_context_hash if prev_assessment else birth.cutoff.market_context_hash

    market_delta = compute_market_delta(
        truncated,
        current_trade_date=assessment_trade_date,
        previous_trade_date=prev_date,
        cohort_symbols=birth.cohort_attribution.symbols_at_birth,
    )

    age = compute_observation_age_trading_days(
        birth.cutoff.trade_date,
        assessment_trade_date,
        dates,
    )

    change_flags: List[str] = []
    if market_delta.summary_keys != ("market:unchanged",):
        change_flags.append(ChangeKind.MARKET_CHANGED.value)
    if new_evidence_keys:
        change_flags.append(ChangeKind.EVIDENCE_CHANGED.value)
    if belief_changed:
        change_flags.append(ChangeKind.BELIEF_CHANGED.value)
    if not change_flags:
        change_flags.append(ChangeKind.UNCHANGED.value)

    what_changed: List[str] = []
    what_did_not_change: List[str] = []
    if market_delta.summary_keys != ("market:unchanged",):
        what_changed.extend(list(market_delta.summary_keys))
    else:
        what_did_not_change.append("market_context")
    if new_evidence_keys:
        what_changed.extend(list(new_evidence_keys))
    if belief_changed:
        what_changed.append(f"epistemic:{prev_ep}->{current_ep}")
    else:
        what_did_not_change.append(f"epistemic:{current_ep}")

    epistemic_delta = EpistemicDelta(
        previous_state=prev_ep,
        current_state=current_ep,
        changed=belief_changed,
        change_kind=change_kind.value if hasattr(change_kind, "value") else str(change_kind),
        rationale_keys=rationale,
    )

    why = _build_why_belief_text(
        belief_changed=belief_changed,
        epistemic_delta=epistemic_delta,
        market_delta_keys=market_delta.summary_keys,
        new_evidence=new_evidence_keys,
        current_ep=current_ep,
    )

    prev_why = prev_assessment.why_belief_changed_or_not if prev_assessment else None
    stale_risk = detect_stale_copy_risk(
        previous_why=prev_why,
        current_why=why,
        market_delta_keys=market_delta.summary_keys,
        belief_unchanged=not belief_changed,
    )

    next_horizon, next_date = _next_pending_horizon(birth, assessment_trade_date)
    waiting = (
        f"Waiting for {next_horizon} eligible on {next_date}"
        if next_horizon
        else "No pending forward horizon"
    )

    lifecycle = derive_lifecycle_state(
        birth=birth,
        current_epistemic_state=current_ep,
        outcomes=tuple(all_outcomes),
        observation_age_trading_days=age,
        has_new_forward_evidence=bool(new_outcomes),
        epistemic_changed=belief_changed,
    )

    cutoff_prov = {
        "assessment_trade_date": assessment_trade_date,
        "temporal_provenance_hash": birth.cutoff.temporal_provenance_hash,
        "panel_row_count": len(truncated),
        "replay_mode": replay_mode,
    }
    prov_hash = stable_hash(cutoff_prov)
    outcome_ids = tuple(o.outcome_record_id for o in all_outcomes)

    identity = compute_daily_assessment_identity(
        observation_id=birth.observation_id,
        assessment_trade_date=assessment_trade_date,
        birth_record_hash=birth.birth_record_hash,
        cutoff_provenance_hash=prov_hash,
        previous_assessment_id=prev_assessment.assessment_id if prev_assessment else None,
        market_context_hash=ctx_hash,
        outcome_ids=outcome_ids,
    )
    assessment_id = new_assessment_id(identity)

    if assessment_exists(assessment_id, data_dir):
        existing = lookup_assessment(assessment_id, data_dir)
        if existing:
            return existing, new_outcomes

    contradictions = list(birth.contradictions)
    for interp in interpretations:
        if interp.get("contradicts_birth_expectation"):
            contradictions.append(f"forward_contradiction:{interp.get('horizon')}")

    assessment = DailyResearchAssessment(
        assessment_id=assessment_id,
        observation_id=birth.observation_id,
        assessment_trade_date=assessment_trade_date,
        assessment_timestamp=utc_now_iso(),
        previous_assessment_id=prev_assessment.assessment_id if prev_assessment else None,
        birth_record_hash=birth.birth_record_hash,
        cutoff_provenance=cutoff_prov,
        current_market_context_identity=ctx_id,
        current_market_context_hash=ctx_hash,
        previous_market_context_identity=prev_ctx_id,
        previous_market_context_hash=prev_ctx_hash,
        market_delta=market_delta,
        new_evidence_since_prior=new_evidence_keys,
        forward_outcomes_newly_available=tuple(o.outcome_record_id for o in new_outcomes),
        current_epistemic_state=current_ep,
        previous_epistemic_state=prev_ep,
        epistemic_delta=epistemic_delta,
        null_ledger_current=list(birth.null_ledger_summary),
        null_ledger_delta=(),
        contradictions=tuple(contradictions),
        dependence_warnings=(birth.dependence_warning,) if birth.dependence_warning else (),
        unresolved_uncertainties=birth.unresolved_uncertainties,
        current_limitations=birth.limitations,
        current_research_status="ACTIVE" if lifecycle not in ("RESOLVED", "REJECTED", "EXPIRED") else lifecycle,
        current_lifecycle_status=lifecycle,
        observation_lifecycle_state=lifecycle,
        what_changed=tuple(what_changed),
        what_did_not_change=tuple(what_did_not_change),
        why_belief_changed_or_not=why,
        what_bot_is_waiting_for=waiting,
        next_eligible_evaluation_horizon=next_horizon,
        next_eligible_evaluation_date=next_date,
        observation_age_trading_days=age,
        change_flags=tuple(change_flags),
        shadow_authority=DEFAULT_SHADOW_AUTHORITY,
        stale_copy_risk=stale_risk,
        assessment_identity_hash=identity,
    )

    if persist:
        persist_assessment(assessment, data_dir=data_dir)
        voice = render_daily_voice(assessment)
        persist_voice(voice, data_dir=data_dir)

    return assessment, new_outcomes


def build_daily_summary(
    *,
    trade_date: str,
    assessments: List[DailyResearchAssessment],
    market_snapshot: Dict[str, Any],
    new_observation_ids: Tuple[str, ...] = (),
    replay_mode: Optional[str] = None,
) -> DailyResearchSummary:
    strengthened = sum(1 for a in assessments if a.observation_lifecycle_state == "STRENGTHENED")
    weakened = sum(1 for a in assessments if a.observation_lifecycle_state in ("WEAKENED", "CHALLENGED"))
    resolved = sum(1 for a in assessments if a.observation_lifecycle_state in ("RESOLVED", "REJECTED"))
    forward_new = tuple(
        oid for a in assessments for oid in a.forward_outcomes_newly_available
    )
    silence = not new_observation_ids

    market_deltas = [a.market_delta for a in assessments]
    most_delta = None
    if market_deltas:
        best = max(market_deltas, key=lambda m: len(m.summary_keys))
        most_delta = best.summary_keys[0] if best.summary_keys else None

    unresolved_q = None
    for a in assessments:
        if a.unresolved_uncertainties:
            unresolved_q = a.unresolved_uncertainties[0]
            break

    waiting_parts = [a.what_bot_is_waiting_for for a in assessments if a.what_bot_is_waiting_for]
    waiting = "; ".join(waiting_parts[:3]) if waiting_parts else "No active observations waiting"

    prov = stable_hash({
        "trade_date": trade_date,
        "assessment_ids": sorted(a.assessment_id for a in assessments),
        "replay_mode": replay_mode,
    })

    return DailyResearchSummary(
        summary_id=new_summary_id(trade_date, prov),
        trade_date=trade_date,
        summary_timestamp=utc_now_iso(),
        market_state_summary=market_snapshot,
        most_meaningful_market_delta=most_delta,
        new_observations_born=new_observation_ids,
        active_observations_reassessed=tuple(a.observation_id for a in assessments),
        strengthened_count=strengthened,
        weakened_or_challenged_count=weakened,
        resolved_or_rejected_count=resolved,
        silence_or_no_discovery=silence,
        newly_arrived_forward_evidence=forward_new,
        most_important_unresolved_question=unresolved_q,
        what_bot_is_waiting_for=waiting,
        provenance_hash=prov,
    )
