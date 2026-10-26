"""
Phase 3K.4 — Living Research UI read model (authoritative, read-only).

Consumes persisted 3K.0–3K.3 records only. No scientific reinterpretation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import (
    list_ledger_entries,
    list_snapshots,
)
from modules.edge_research.opr_bridge.production_calibration_self_knowledge import (
    build_self_knowledge_read_model,
)
from modules.edge_research.opr_bridge.production_daily_run_persistence import (
    load_run_index,
    lookup_prior_successful_run,
    lookup_run,
    lookup_run_for_date,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    LIVE_FORWARD,
    NON_FORWARD_MODES,
)
from modules.edge_research.opr_bridge.production_daily_voice import render_daily_voice
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    list_assessments_for_observation,
    list_outcomes_for_observation,
    list_summaries,
    lookup_assessment,
    session_voice_path,
    voice_path,
)
from modules.edge_research.opr_bridge.production_living_research_ui_records import (
    AUTHORITY_BADGE_RESEARCH_ONLY,
    LIVING_RESEARCH_UI_VERSION,
    RUN_MODE_LABELS,
)
from modules.edge_research.opr_bridge.production_observation_persistence import (
    load_observation_index,
    lookup_birth_record,
)
from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root


def resolve_production_data_dir(data_dir: Optional[Path] = None) -> Path:
    """Canonical production runs root (assessments, voices, daily runs)."""
    return resolve_production_runs_root(data_dir)


def list_available_trade_dates(*, data_dir: Optional[Path] = None) -> List[str]:
    dates = set()
    for s in list_summaries(data_dir=data_dir):
        dates.add(s.trade_date)
    index = load_run_index(data_dir)
    for meta in index.get("runs", {}).values():
        if meta.get("run_disposition") == "SUCCESS":
            dates.add(meta.get("target_trade_date", ""))
    return sorted(d for d in dates if d)


def _latest_successful_run(*, data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    index = load_run_index(data_dir)
    candidates = [
        m for m in index.get("runs", {}).values()
        if m.get("run_disposition") == "SUCCESS"
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda m: m.get("target_trade_date", ""))
    run = lookup_run(best["run_id"], data_dir)
    return {
        "run_id": best["run_id"],
        "target_trade_date": best.get("target_trade_date"),
        "run_mode": best.get("run_mode"),
        "run_disposition": best.get("run_disposition"),
        "counts_as_forward_evidence": bool(run.counts_as_forward_evidence) if run else False,
        "daily_summary_id": run.daily_summary_id if run else None,
        "manifest_run_mode_label": RUN_MODE_LABELS.get(best.get("run_mode", ""), best.get("run_mode")),
    }


def build_ui_health_read_model(*, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    latest = _latest_successful_run(data_dir=data_dir)
    index = load_run_index(data_dir)
    failed = [
        m for m in index.get("runs", {}).values()
        if m.get("run_disposition") in ("FAILED_CLOSED", "PARTIAL_RECOVERABLE", "WAITING_FOR_DATA")
    ]
    latest_failed = max(failed, key=lambda m: m.get("target_trade_date", "")) if failed else None
    return {
        "latest_successful_research_date": latest.get("target_trade_date") if latest else None,
        "latest_run_id": latest.get("run_id") if latest else None,
        "latest_run_mode": latest.get("run_mode") if latest else None,
        "latest_run_disposition": latest.get("run_disposition") if latest else None,
        "waiting_for_data": latest_failed.get("run_disposition") == "WAITING_FOR_DATA" if latest_failed else False,
        "failed_closed": latest_failed.get("run_disposition") == "FAILED_CLOSED" if latest_failed else False,
        "partial_recoverable": latest_failed.get("run_disposition") == "PARTIAL_RECOVERABLE" if latest_failed else False,
        "warnings": [
            f"Latest non-success disposition: {latest_failed.get('run_disposition')} on {latest_failed.get('target_trade_date')}"
        ] if latest_failed else [],
    }


def build_ui_daily_change_read_model(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    summaries = {s.trade_date: s for s in list_summaries(data_dir=data_dir)}
    today = summaries.get(trade_date)
    prior_run_id = lookup_prior_successful_run(trade_date, data_dir=data_dir)
    prior_run = lookup_run(prior_run_id, data_dir) if prior_run_id else None
    prior_date = prior_run.target_trade_date if prior_run else None
    prior_summary = summaries.get(prior_date) if prior_date else None

    today_assessments = _assessments_on_date(trade_date, data_dir)
    prior_assessments = _assessments_on_date(prior_date, data_dir) if prior_date else []

    belief_changes = [
        {
            "observation_id": a.observation_id,
            "previous": a.previous_epistemic_state,
            "current": a.current_epistemic_state,
            "why": a.why_belief_changed_or_not,
            "changed": a.epistemic_delta.changed,
        }
        for a in today_assessments
        if a.epistemic_delta.changed
    ]
    unchanged_with_market_change = [
        {
            "observation_id": a.observation_id,
            "epistemic_state": a.current_epistemic_state,
            "why": a.why_belief_changed_or_not,
            "market_keys": list(a.market_delta.summary_keys),
        }
        for a in today_assessments
        if not a.epistemic_delta.changed and "MARKET_CHANGED" in (a.change_flags or ())
    ]

    return {
        "trade_date": trade_date,
        "previous_trade_date": prior_date,
        "market_regime_delta": today.most_meaningful_market_delta if today else None,
        "prior_market_regime_delta": prior_summary.most_meaningful_market_delta if prior_summary else None,
        "observation_count_delta": {
            "born_today": len(today.new_observations_born) if today else 0,
            "reassessed_today": len(today.active_observations_reassessed) if today else 0,
            "prior_reassessed": len(prior_summary.active_observations_reassessed) if prior_summary else 0,
        },
        "belief_changes": belief_changes,
        "unchanged_belief_with_market_change": unchanged_with_market_change,
        "new_evidence_arrivals": [
            oid for a in today_assessments for oid in a.forward_outcomes_newly_available
        ],
        "silence_or_no_discovery": bool(today.silence_or_no_discovery) if today else False,
        "new_discovery": bool(today and today.new_observations_born),
        "nothing_meaningful_changed": (
            not belief_changes
            and not (today and today.new_observations_born)
            and not (today and today.newly_arrived_forward_evidence)
            and not (today and today.strengthened_count)
        ),
    }


def build_ui_active_observations_read_model(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    obs_index = load_observation_index(data_dir)
    rows: List[Dict[str, Any]] = []
    for oid, meta in obs_index.get("observations", {}).items():
        birth = lookup_birth_record(oid, data_dir=data_dir)
        if birth is None:
            continue
        birth_date = birth.cutoff.trade_date
        if birth_date > trade_date:
            continue
        assessments = [a for a in list_assessments_for_observation(oid, data_dir=data_dir) if a.assessment_trade_date <= trade_date]
        if not assessments and birth_date != trade_date:
            continue
        latest = max(assessments, key=lambda a: a.assessment_trade_date) if assessments else None
        outcomes = [
            o for o in list_outcomes_for_observation(oid, data_dir=data_dir)
            if (o.provenance or {}).get("assessment_trade_date", o.eligible_evaluation_date) <= trade_date
        ]
        horizon_status = {}
        for h in birth.forward_horizons:
            released = next((o for o in outcomes if o.horizon == h.horizon), None)
            horizon_status[h.horizon] = {
                "status": released.evaluation_status if released else h.status,
                "eligible_date": h.eligible_evaluation_date,
                "released": released is not None,
            }
        rows.append({
            "observation_id": oid,
            "hypothesis": birth.research_question or birth.observation_outcome_kind,
            "birth_date": birth_date,
            "observation_mode": birth.observation_mode,
            "forward_authority": birth.observation_mode == LIVE_FORWARD,
            "age_trading_days": latest.observation_age_trading_days if latest else 0,
            "epistemic_state": latest.current_epistemic_state if latest else birth.final_epistemic_state,
            "evidence_strength": birth.evidence_strength,
            "lifecycle": latest.observation_lifecycle_state if latest else "BORN",
            "last_meaningful_change": list(latest.what_changed)[0] if latest and latest.what_changed else None,
            "unresolved_nulls": list(latest.null_ledger_current) if latest else list(birth.surviving_nulls),
            "waiting_for": latest.what_bot_is_waiting_for if latest else "Chưa có assessment",
            "horizon_status": horizon_status,
            "dependence_warning": birth.dependence_warning,
        })
    return sorted(rows, key=lambda r: r["birth_date"], reverse=True)


def build_observation_timeline_read_model(
    observation_id: str,
    *,
    as_of_trade_date: str,
    data_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Chronological timeline showing state AT THAT TIME — no current belief overwrite.
    """
    birth = lookup_birth_record(observation_id, data_dir=data_dir)
    if birth is None:
        return []
    timeline: List[Dict[str, Any]] = [{
        "kind": "BIRTH",
        "trade_date": birth.cutoff.trade_date,
        "epistemic_state": birth.final_epistemic_state,
        "lifecycle": "BORN",
        "evidence_strength": birth.evidence_strength,
        "summary": birth.observation_outcome_kind,
    }]
    assessments = [
        a for a in list_assessments_for_observation(observation_id, data_dir=data_dir)
        if a.assessment_trade_date <= as_of_trade_date
    ]
    outcomes = [
        o for o in list_outcomes_for_observation(observation_id, data_dir=data_dir)
        if (o.provenance or {}).get("assessment_trade_date", o.eligible_evaluation_date) <= as_of_trade_date
    ]
    events: List[Tuple[str, str, Dict[str, Any]]] = []
    for a in assessments:
        events.append((a.assessment_trade_date, "ASSESSMENT", {
            "kind": "ASSESSMENT",
            "trade_date": a.assessment_trade_date,
            "epistemic_state": a.current_epistemic_state,
            "lifecycle": a.observation_lifecycle_state,
            "belief_changed": a.epistemic_delta.changed,
            "why": a.why_belief_changed_or_not,
            "previous_epistemic": a.previous_epistemic_state,
            "market_delta_keys": list(a.market_delta.summary_keys),
        }))
    for o in outcomes:
        release = (o.provenance or {}).get("assessment_trade_date", o.eligible_evaluation_date)
        events.append((release, f"OUTCOME_{o.horizon}", {
            "kind": "OUTCOME",
            "horizon": o.horizon,
            "trade_date": release,
            "evaluation_status": o.evaluation_status,
            "realized_outcomes": o.realized_outcomes,
        }))
    events.sort(key=lambda x: (x[0], 0 if x[1] == "ASSESSMENT" else 1))
    timeline.extend(e[2] for e in events)
    return timeline


def build_ui_forward_evidence_panel(*, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    self_k = build_self_knowledge_read_model(data_dir=data_dir)
    entries = list_ledger_entries(data_dir=data_dir, forward_only=True)
    snapshots = list_snapshots(data_dir=data_dir)
    latest_snap = snapshots[-1] if snapshots else None
    by_horizon = {"T3": 0, "T5": 0, "T10": 0, "pending": 0}
    for e in entries:
        if e.horizon in by_horizon:
            by_horizon[e.horizon] += 1
    obs_modes = {}
    for e in entries:
        obs_modes[e.observation_id] = e.run_mode
    live_n = len(set(e.observation_id for e in entries if e.run_mode == LIVE_FORWARD))
    return {
        "live_forward_observation_count": self_k.get("live_forward_observation_count", live_n),
        "ledger_entry_count": len(entries),
        "t3_available": by_horizon["T3"],
        "t5_available": by_horizon["T5"],
        "t10_available": by_horizon["T10"],
        "pending_n": self_k.get("t5_pending_count", 0),
        "maturity_label": self_k.get("maturity_label"),
        "eligible_forward_evidence_n": self_k.get("eligible_forward_evidence_n", 0),
        "tiny_sample_warning": self_k.get("eligible_forward_evidence_n", 0) < 3,
        "statements": self_k.get("statements", []),
        "latest_snapshot_id": latest_snap.snapshot_id if latest_snap else None,
        "authority_note": "REAL FORWARD chỉ từ LIVE_FORWARD; BACKFILL/REPLAY không phải forward evidence thật",
        "has_real_forward_evidence": live_n > 0,
        "historical_only": live_n == 0 and len(entries) == 0,
    }


def build_ui_voice_narrative(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggregate DailyVoiceContract into readable Vietnamese narrative."""
    import json

    assessments = _assessments_on_date(trade_date, data_dir)
    voices = []
    for a in assessments:
        vpath = voice_path(a.assessment_id, data_dir)
        if vpath.exists():
            voice = json.loads(vpath.read_text(encoding="utf-8"))
        else:
            voice = render_daily_voice(a).to_dict()
        voices.append(voice)

    session_voice = None
    spath = session_voice_path(trade_date, data_dir)
    if spath.exists():
        session_voice = json.loads(spath.read_text(encoding="utf-8"))

    summary = next((s for s in list_summaries(data_dir=data_dir) if s.trade_date == trade_date), None)

    if session_voice and voices:
        narrative = _compose_session_and_observation_voice(session_voice, voices, summary)
    elif session_voice:
        narrative = _compose_session_voice_only(session_voice)
    elif not voices and summary and summary.silence_or_no_discovery:
        narrative = _silence_day_narrative(trade_date, summary, data_dir)
    elif not voices:
        narrative = _empty_state_narrative(trade_date, data_dir)
    else:
        narrative = _compose_voice_narrative(voices, summary)

    all_voices = ([session_voice] if session_voice else []) + voices
    return {
        "trade_date": trade_date,
        "voices": all_voices,
        "session_voice": session_voice,
        "narrative_vi": narrative,
        "voice_count": len(all_voices),
        "silence_or_no_discovery": bool(summary.silence_or_no_discovery) if summary else len(all_voices) == 0,
    }


def build_historical_date_read_model(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Historical view — no future information beyond trade_date."""
    run = lookup_run_for_date(trade_date, LIVE_FORWARD, data_dir=data_dir)
    if run is None:
        run = lookup_run_for_date(trade_date, BACKFILL_NON_FORWARD, data_dir=data_dir)
    snapshots = [s for s in list_snapshots(data_dir=data_dir) if s.as_of_trade_date <= trade_date]
    cal_snap = snapshots[-1] if snapshots else None
    return {
        "trade_date": trade_date,
        "temporal_cutoff": trade_date,
        "daily_change": build_ui_daily_change_read_model(trade_date, data_dir=data_dir),
        "voice": build_ui_voice_narrative(trade_date, data_dir=data_dir),
        "active_observations": build_ui_active_observations_read_model(trade_date, data_dir=data_dir),
        "run_mode": run.run_mode if run else None,
        "run_disposition": run.run_disposition if run else None,
        "calibration_snapshot": cal_snap.to_dict() if cal_snap else None,
        "future_leakage_blocked": True,
    }


def build_living_research_ui_read_model(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    health = build_ui_health_read_model(data_dir=data_dir)
    effective_date = trade_date or health.get("latest_successful_research_date")
    if not effective_date:
        return {
            "version": LIVING_RESEARCH_UI_VERSION,
            "trade_date": None,
            "failure_state": "NO_DATA",
            "health": health,
            "authority_badge": AUTHORITY_BADGE_RESEARCH_ONLY,
            "message_vi": "Chưa có dữ liệu research production. Hệ thống sẵn sàng nhưng chưa chạy LIVE_FORWARD.",
            "self_knowledge": build_self_knowledge_read_model(data_dir=data_dir),
            "forward_evidence": build_ui_forward_evidence_panel(data_dir=data_dir),
            "available_dates": list_available_trade_dates(data_dir=data_dir),
        }

    run = lookup_run_for_date(effective_date, LIVE_FORWARD, data_dir=data_dir)
    if run is None:
        run = lookup_run_for_date(effective_date, BACKFILL_NON_FORWARD, data_dir=data_dir)

    stale_warning = (
        trade_date is None
        and health.get("latest_successful_research_date")
        and effective_date != trade_date
    )

    return {
        "version": LIVING_RESEARCH_UI_VERSION,
        "trade_date": effective_date,
        "requested_trade_date": trade_date,
        "stale_data_warning": None,
        "health": health,
        "authority_badge": AUTHORITY_BADGE_RESEARCH_ONLY,
        "run_mode": run.run_mode if run else None,
        "run_mode_label": RUN_MODE_LABELS.get(run.run_mode, run.run_mode) if run else None,
        "counts_as_forward_evidence": bool(run.counts_as_forward_evidence) if run else False,
        "voice": build_ui_voice_narrative(effective_date, data_dir=data_dir),
        "daily_change": build_ui_daily_change_read_model(effective_date, data_dir=data_dir),
        "active_observations": build_ui_active_observations_read_model(effective_date, data_dir=data_dir),
        "forward_evidence": build_ui_forward_evidence_panel(data_dir=data_dir),
        "self_knowledge": build_self_knowledge_read_model(data_dir=data_dir),
        "available_dates": list_available_trade_dates(data_dir=data_dir),
        "failure_state": _detect_failure_state(run, health),
    }


def _assessments_on_date(trade_date: Optional[str], data_dir: Optional[Path]) -> List[Any]:
    if not trade_date:
        return []
    from modules.edge_research.opr_bridge.production_living_observation_persistence import load_living_index
    index = load_living_index(data_dir)
    rows = []
    for meta in index.get("assessments", {}).values():
        if meta.get("trade_date") == trade_date:
            a = lookup_assessment(meta["assessment_id"], data_dir)
            if a:
                rows.append(a)
    return rows


def _compose_session_voice_only(session_voice: Dict[str, Any]) -> str:
    parts = [
        session_voice.get("q1_today_i_see_vi", ""),
        session_voice.get("q2_vs_prior_session_vi", ""),
        session_voice.get("q3_market_change_vi", ""),
        session_voice.get("q5_belief_changed_vi", ""),
        session_voice.get("q6_if_not_why_vi", ""),
        session_voice.get("q9_waiting_for_vi", ""),
    ]
    return "\n\n".join(p for p in parts if p)


def _compose_session_and_observation_voice(
    session_voice: Dict[str, Any],
    voices: List[Dict[str, Any]],
    summary: Any,
) -> str:
    head = _compose_session_voice_only(session_voice)
    body = _compose_voice_narrative(voices, summary)
    return f"{head}\n\n---\n\n{body}" if body else head


def _compose_voice_narrative(voices: List[Dict[str, Any]], summary: Any) -> str:
    parts: List[str] = []
    for i, v in enumerate(voices):
        if len(voices) > 1:
            parts.append(f"**Observation {i + 1}**")
        parts.append(v.get("q1_today_i_see_vi", ""))
        parts.append(v.get("q2_vs_prior_session_vi", ""))
        if v.get("q3_market_change_vi"):
            parts.append(v.get("q3_market_change_vi", ""))
        parts.append(v.get("q5_belief_changed_vi", ""))
        parts.append(v.get("q6_if_not_why_vi", ""))
        if v.get("q7_counter_hypothesis_vi"):
            parts.append(v.get("q7_counter_hypothesis_vi", ""))
        parts.append(v.get("q8_still_unknown_vi", ""))
        parts.append(v.get("q9_waiting_for_vi", ""))
    if summary and summary.silence_or_no_discovery and not summary.new_observations_born:
        parts.insert(0, "Hôm nay tôi không tạo observation mới.")
    return "\n\n".join(p for p in parts if p)


def _silence_day_narrative(trade_date: str, summary: Any, data_dir: Optional[Path]) -> str:
    dc = build_ui_daily_change_read_model(trade_date, data_dir=data_dir)
    lines = [
        f"Hôm nay ({trade_date}) tôi không tạo observation mới.",
        f"Market delta đáng chú ý: {summary.most_meaningful_market_delta or 'không ghi nhận thay đổi lớn'}.",
        f"Observations đang sống được reassess: {len(summary.active_observations_reassessed)}.",
    ]
    if dc.get("belief_changes"):
        lines.append(f"Có {len(dc['belief_changes'])} thay đổi belief.")
    elif dc.get("unchanged_belief_with_market_change"):
        lines.append("Market thay đổi nhưng belief chưa đủ evidence để đổi — xem chi tiết từng observation.")
    else:
        lines.append("Không có evidence mới đủ để thay đổi kết luận.")
    lines.append(summary.what_bot_is_waiting_for or "Đang chờ forward outcomes hoặc evidence mới.")
    return "\n\n".join(lines)


def _empty_state_narrative(trade_date: str, data_dir: Optional[Path]) -> str:
    health = build_ui_health_read_model(data_dir=data_dir)
    if health.get("waiting_for_data"):
        return f"Ngày {trade_date}: WAITING_FOR_DATA — chưa có EOD để research."
    if health.get("failed_closed"):
        return f"Ngày {trade_date}: run thất bại (FAILED_CLOSED). Scientific records vẫn có thể xem nếu đã persist."
    return f"Ngày {trade_date}: chưa có assessment/voice. Có thể chưa chạy daily research hoặc không có observation active."


def _detect_failure_state(run: Any, health: Dict[str, Any]) -> Optional[str]:
    if health.get("waiting_for_data"):
        return "WAITING_FOR_DATA"
    if health.get("failed_closed"):
        return "FAILED_CLOSED"
    if health.get("partial_recoverable"):
        return "PARTIAL_RECOVERABLE"
    if run is None and not health.get("latest_successful_research_date"):
        return "NO_LIVE_FORWARD_DATA"
    return None
