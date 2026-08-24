"""
Streamlit UI for Edge Research Engine V1 (Phase 3 challenger).

Display-only — no production coupling.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, TypeVar

from modules.edge_research.engine import EdgeResearchEngine

EDGE_RESEARCH_BUSY_STRICT_VERSION = 1
EDGE_RESEARCH_PENDING_KEY = "edge_research_pending"
EDGE_RESEARCH_LAST_RUN_KEY = "edge_research_last_run"
T = TypeVar("T")

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(token|secret|password|api[_-]?key)\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"EDGE_RESEARCH_DURABLE_TOKEN\S*", re.IGNORECASE),
    re.compile(r"EDGE_RESEARCH_ARTIFACT_TOKEN\S*", re.IGNORECASE),
)


def _fmt_coverage(start: Optional[str], end: Optional[str], count: int) -> str:
    if not start or not end:
        return "No historical coverage detected"
    return f"{start} → {end} ({count:,} lifecycle rows)"


def execution_in_progress_from_session(session_state: Mapping[str, Any]) -> bool:
    """Only literal boolean True or a queued pending action means busy."""
    if session_state.get("edge_research_busy") is True:
        return True
    pending = session_state.get(EDGE_RESEARCH_PENDING_KEY)
    if pending in ("discovery", "challenger"):
        return True
    return False


def normalize_edge_research_busy_session(
    session_state: MutableMapping[str, Any],
) -> None:
    """Coerce non-boolean busy values without treating strings as active execution."""
    busy = session_state.get("edge_research_busy", False)
    if busy is not False and busy is not True:
        session_state["edge_research_busy"] = False


def recover_legacy_edge_research_busy(session_state: MutableMapping[str, Any]) -> None:
    """
    One-time recovery for browser sessions that inherited stale busy=True
    from the pre-finally implementation. Does not run on every render once
    the strict-busy version marker is present.
    """
    if session_state.get("_edge_research_busy_strict_v", 0) >= EDGE_RESEARCH_BUSY_STRICT_VERSION:
        normalize_edge_research_busy_session(session_state)
        return
    busy = session_state.get("edge_research_busy", False)
    if busy is not False:
        session_state["edge_research_busy"] = False
    session_state["_edge_research_busy_strict_v"] = EDGE_RESEARCH_BUSY_STRICT_VERSION


def get_pending_research_action(session_state: Mapping[str, Any]) -> Optional[str]:
    pending = session_state.get(EDGE_RESEARCH_PENDING_KEY)
    if pending in ("discovery", "challenger"):
        return pending
    return None


def consume_pending_research_action(session_state: MutableMapping[str, Any]) -> Optional[str]:
    pending = get_pending_research_action(session_state)
    if pending is None:
        return None
    session_state.pop(EDGE_RESEARCH_PENDING_KEY, None)
    return pending


def queue_research_action(session_state: MutableMapping[str, Any], action: str) -> bool:
    """Record a pending research action without executing it."""
    if action not in ("discovery", "challenger"):
        return False
    if execution_in_progress_from_session(session_state):
        return False
    session_state.pop(EDGE_RESEARCH_LAST_RUN_KEY, None)
    session_state[EDGE_RESEARCH_PENDING_KEY] = action
    session_state["edge_research_busy"] = True
    return True


def research_run_phase_from_session(session_state: Mapping[str, Any]) -> str:
    if get_pending_research_action(session_state) or session_state.get("edge_research_busy") is True:
        return "RUNNING"
    last_run = session_state.get(EDGE_RESEARCH_LAST_RUN_KEY)
    if isinstance(last_run, dict):
        status = last_run.get("status")
        if status == "COMPLETED":
            return "COMPLETED"
        if status == "FAILED":
            return "FAILED"
    return "IDLE"


def sanitize_research_error_message(exc: BaseException) -> str:
    message = str(exc) or exc.__class__.__name__
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub("[REDACTED]", message)
    return message[:500]


def build_discovery_run_record(result: Any) -> Dict[str, Any]:
    data_quality = getattr(result, "data_quality", {}) or {}
    eligible = data_quality.get("eligible_observations", 0)
    tested = getattr(result, "conditions_tested", 0)
    candidates = getattr(result, "promoted_candidates", 0)
    return {
        "action": "discovery",
        "status": "COMPLETED",
        "timestamp": getattr(result, "timestamp", "") or _utc_now_iso(),
        "run_id": getattr(result, "run_id", ""),
        "discovery_run_id": getattr(result, "run_id", ""),
        "summary": (
            f"{candidates} candidate(s); {tested:,} conditions tested; "
            f"{eligible:,} eligible observations"
        ),
    }


def build_challenger_run_record(result: Any) -> Dict[str, Any]:
    run_id = getattr(result, "run_id", "")
    if run_id == "skipped":
        return {
            "action": "challenger",
            "status": "COMPLETED",
            "timestamp": getattr(result, "timestamp", "") or _utc_now_iso(),
            "run_id": "skipped",
            "discovery_run_id": getattr(result, "discovery_run_id", ""),
            "summary": "Challenger skipped — same candidate ledger already evaluated.",
        }
    return {
        "action": "challenger",
        "status": "COMPLETED",
        "timestamp": getattr(result, "timestamp", "") or _utc_now_iso(),
        "run_id": run_id,
        "discovery_run_id": getattr(result, "discovery_run_id", ""),
        "summary": (
            f"PASS={getattr(result, 'robustness_pass', 0)}, "
            f"FRAGILE={getattr(result, 'robustness_fragile', 0)}, "
            f"REJECT={getattr(result, 'robustness_reject', 0)}"
        ),
    }


def complete_research_run_success(
    session_state: MutableMapping[str, Any],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    session_state[EDGE_RESEARCH_LAST_RUN_KEY] = record
    session_state.pop(EDGE_RESEARCH_PENDING_KEY, None)
    session_state["edge_research_busy"] = False
    return record


def complete_research_run_failure(
    session_state: MutableMapping[str, Any],
    action: str,
    error_message: str,
) -> Dict[str, Any]:
    record = {
        "action": action,
        "status": "FAILED",
        "timestamp": _utc_now_iso(),
        "run_id": "",
        "discovery_run_id": "",
        "summary": error_message,
    }
    session_state[EDGE_RESEARCH_LAST_RUN_KEY] = record
    session_state.pop(EDGE_RESEARCH_PENDING_KEY, None)
    session_state["edge_research_busy"] = False
    return record


def format_research_run_status_message(last_run: Mapping[str, Any]) -> str:
    action = last_run.get("action", "research")
    status = last_run.get("status", "")
    summary = last_run.get("summary", "")
    run_id = last_run.get("run_id", "")
    parts = [f"{action.title()} {status.lower()}"]
    if run_id:
        parts.append(f"run_id={run_id}")
    if summary:
        parts.append(summary)
    return " — ".join(parts)


def run_with_edge_research_busy_guard(
    session_state: MutableMapping[str, Any],
    action: Callable[[], T],
) -> T:
    """Exception-safe busy lifecycle for synchronous button-triggered runs."""
    session_state["edge_research_busy"] = True
    try:
        return action()
    finally:
        session_state["edge_research_busy"] = False


def execute_pending_research_action(
    session_state: MutableMapping[str, Any],
    engine: EdgeResearchEngine,
) -> Optional[Dict[str, Any]]:
    """Execute exactly one queued research action and persist session metadata."""
    pending_action = consume_pending_research_action(session_state)
    if pending_action is None:
        return None

    try:
        if pending_action == "discovery":
            result = run_with_edge_research_busy_guard(session_state, engine.run_discovery)
            record = build_discovery_run_record(result)
        elif pending_action == "challenger":
            result = run_with_edge_research_busy_guard(
                session_state,
                lambda: engine.run_challenger(force=True),
            )
            record = build_challenger_run_record(result)
        else:
            raise ValueError(f"Unknown research action: {pending_action}")
        return complete_research_run_success(session_state, record)
    except Exception as exc:
        return complete_research_run_failure(
            session_state,
            pending_action,
            sanitize_research_error_message(exc),
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_edge_research_button_state(
    *,
    coverage_start: Optional[str],
    coverage_end: Optional[str],
    observation_count: int,
    has_valid_cohort: bool,
    execution_in_progress: bool = False,
) -> Dict[str, bool]:
    """
    UI gating for explicit research actions.

    Discovery depends only on historical research coverage availability.
    Challenger depends on a persisted, cohort-scoped discovery result.
    """
    has_research_coverage = bool(
        coverage_start and coverage_end and observation_count > 0
    )
    busy = execution_in_progress is True
    return {
        "has_research_coverage": has_research_coverage,
        "execution_in_progress": busy,
        "can_run_discovery": has_research_coverage and not busy,
        "can_run_challenger": has_valid_cohort and not busy,
    }


def discovery_disabled_caption(ui_state: Dict[str, bool]) -> Optional[str]:
    if ui_state.get("can_run_discovery"):
        return None
    if ui_state.get("execution_in_progress"):
        return "Research run in progress..."
    if not ui_state.get("has_research_coverage"):
        return "Historical research coverage required."
    return None


def challenger_disabled_caption(
    ui_state: Dict[str, bool],
    *,
    has_valid_cohort: bool,
) -> Optional[str]:
    if ui_state.get("can_run_challenger"):
        return None
    if ui_state.get("execution_in_progress"):
        return "Research run in progress..."
    if not has_valid_cohort:
        return "Run discovery first."
    return None


def _format_research_voice(candidate: Dict[str, Any]) -> str:
    rs = candidate.get("robustness_status", "")
    edge_id = candidate.get("edge_id", "")
    if rs == "PASS":
        header = f"**EDGE CANDIDATE — ROBUSTNESS PASS — {edge_id}**"
        action = "**ACTION: RESEARCH ONLY — NOT VALIDATED**"
    elif rs == "FRAGILE":
        header = f"**EDGE FRAGILE — {edge_id}**"
        action = "**ACTION: RESEARCH ONLY — NEEDS VALIDATION**"
    elif rs == "REJECT":
        header = f"**EDGE REJECTED — {edge_id}**"
        action = "**ACTION: ARCHIVE AS DISCOVERY FAILURE**"
    else:
        header = f"**EDGE CANDIDATE — {edge_id}**"
        action = "**ACTION: RESEARCH ONLY — NOT VALIDATED**"

    return (
        f"{header}\n\n"
        f"Market: {candidate.get('market_transition', '')}\n\n"
        f"Condition: {candidate.get('condition_text', '')}\n\n"
        f"Best horizon: {candidate.get('best_horizon', '')}\n\n"
        f"Observations: {candidate.get('candidate_n', 0)}\n\n"
        f"Observed Market episodes: {candidate.get('observed_episodes', 0)}\n\n"
        f"Main issue: {candidate.get('main_fragility_flag') or candidate.get('rejection_reasons', '—')}\n\n"
        f"Robustness status: {rs or 'PENDING'}\n\n"
        f"{action}"
    )


def _render_research_run_status(st: Any, session_state: Mapping[str, Any]) -> None:
    phase = research_run_phase_from_session(session_state)
    pending = get_pending_research_action(session_state)

    if phase == "RUNNING":
        label = "Discovery" if pending == "discovery" else "Challenger"
        if pending is None:
            last_run = session_state.get(EDGE_RESEARCH_LAST_RUN_KEY, {})
            if isinstance(last_run, dict) and last_run.get("action") == "discovery":
                label = "Discovery"
            else:
                label = "Challenger"
        st.info(f"**RUNNING:** {label} (research only) — request accepted, execution in progress.")
        return

    last_run = session_state.get(EDGE_RESEARCH_LAST_RUN_KEY)
    if not isinstance(last_run, dict):
        return

    message = format_research_run_status_message(last_run)
    if last_run.get("status") == "COMPLETED":
        st.success(message)
    elif last_run.get("status") == "FAILED":
        st.error(message)


def _run_autonomous_heartbeat_safely(
    *,
    current_market_state: Optional[str],
    current_market_transition: Optional[str],
    research_coverage_end: Optional[str],
    execution_in_progress: bool,
) -> Optional[Dict[str, Any]]:
    """
    Cheap autonomous observe→decide→persist heartbeat.

    Skipped while a manual discovery/challenger run is in progress to avoid conflict.
    Idempotent on identical data identity (Streamlit reruns safe).
    """
    if execution_in_progress:
        return None
    try:
        from modules.edge_research.autonomous_heartbeat import (
            get_autonomous_status_snapshot,
            run_autonomous_research_heartbeat,
        )

        decision = run_autonomous_research_heartbeat(
            research_market_state=current_market_state or "UNKNOWN",
            research_market_transition=current_market_transition or "UNKNOWN",
            research_coverage_end=research_coverage_end,
        )
        snap = get_autonomous_status_snapshot()
        return {"decision": decision.to_dict(), "snapshot": snap}
    except Exception as exc:  # noqa: BLE001 — panel must remain display-safe
        return {"error": str(exc)}


def _render_autonomous_heartbeat_status(st: Any, heartbeat: Optional[Dict[str, Any]]) -> None:
    if not heartbeat:
        return
    if heartbeat.get("error"):
        st.caption(f"Autonomous research heartbeat skipped: {heartbeat['error']}")
        return
    snap = heartbeat.get("snapshot") or {}
    decision = heartbeat.get("decision") or {}
    code = snap.get("last_autonomous_decision") or decision.get("decision_code") or "—"
    reason = snap.get("last_autonomous_reason") or decision.get("reason") or ""
    cutoff = snap.get("last_observation_cutoff") or decision.get("data_cutoff") or "—"
    waiting = "yes" if snap.get("waiting_for_outcomes") else "no"
    ran = "yes" if snap.get("research_ran") else "no"
    replay = " (idempotent replay)" if decision.get("idempotent_replay") else ""
    active = snap.get("active_experiment_id") or "—"
    nxt = snap.get("next_eligible_trigger") or "—"
    st.markdown(
        f"**Autonomous research heartbeat:** `{code}`{replay}  \n"
        f"Data cutoff: `{cutoff}` · Research ran: `{ran}` · Waiting outcomes: `{waiting}`  \n"
        f"Active experiment: `{active}` · Next trigger: `{nxt}`  \n"
        f"Reason: {reason}"
    )


def render_edge_research_panel(
    current_market_state: Optional[str] = None,
    current_market_transition: Optional[str] = None,
) -> Dict[str, Any]:
    """Render MR.BOT — EDGE RESEARCH panel (Phase 3)."""
    import streamlit as st

    st.markdown("## 🔬 MR.BOT — EDGE RESEARCH")

    try:
        engine = EdgeResearchEngine()
        engine.initialize()
        status = engine.get_foundation_status(
            current_market_state=current_market_state,
            current_market_transition=current_market_transition,
        )
        discovery = engine.get_last_discovery()
        challenger = engine.get_last_challenger()
        top_candidates = engine.get_top_candidates(limit=20)
        has_valid_cohort = engine.has_valid_discovery_cohort()
        recover_legacy_edge_research_busy(st.session_state)

        pending_before_execute = get_pending_research_action(st.session_state)
        execution_in_progress = execution_in_progress_from_session(st.session_state)
        ui_state = compute_edge_research_button_state(
            coverage_start=status.coverage_start,
            coverage_end=status.coverage_end,
            observation_count=status.observation_count,
            has_valid_cohort=has_valid_cohort,
            execution_in_progress=execution_in_progress,
        )

        # Autonomous observe→decide→persist (cheap; not expensive discovery)
        heartbeat = _run_autonomous_heartbeat_safely(
            current_market_state=current_market_state,
            current_market_transition=current_market_transition,
            research_coverage_end=status.coverage_end,
            execution_in_progress=execution_in_progress,
        )
        # Refresh status voice after heartbeat persistence
        if heartbeat and not heartbeat.get("error"):
            status = engine.get_foundation_status(
                current_market_state=current_market_state,
                current_market_transition=current_market_transition,
            )

        _render_research_run_status(st, st.session_state)
        _render_autonomous_heartbeat_status(st, heartbeat)

        engine_label = (
            "CHALLENGER / RESEARCH ONLY"
            if status.phase == "challenger"
            else "DISCOVERY / RESEARCH ONLY"
        )

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Engine status", engine_label)
            st.metric("Production coupling", status.production_coupling)
            st.metric("Hypotheses", status.hypotheses)
            st.metric("Validated edges", status.validated_edges)
        with c2:
            st.metric("Market Research State", status.research_market_state)
            st.metric("Market Transition", status.research_market_transition)
            st.metric("Observed Market episodes", status.observed_episodes)
            st.metric("Action", status.action)

        st.caption(f"Engine version: {status.engine_version}")
        st.caption("Independent validated episodes: 0 (Phase 3 counts observed episodes only)")

        st.markdown(
            f"**Historical research coverage:** "
            f"{_fmt_coverage(status.coverage_start, status.coverage_end, status.observation_count)}"
        )

        if status.discovery_summary:
            ds = status.discovery_summary
            st.markdown(
                f"**Discovery summary:** "
                f"Eligible: {ds.get('eligible_observations', 0):,} | "
                f"Tested: {ds.get('conditions_tested', 0):,} | "
                f"Candidates: {ds.get('candidates_discovered', 0)}"
            )

        if status.challenger_summary:
            cs = status.challenger_summary
            st.markdown(
                f"**Challenger summary:** "
                f"Entered: {cs.get('candidates_entered', 0)} | "
                f"PASS: {cs.get('robustness_pass', 0)} | "
                f"FRAGILE: {cs.get('robustness_fragile', 0)} | "
                f"REJECTED: {cs.get('robustness_reject', 0)} | "
                f"Market episodes segmented: {cs.get('episodes_segmented', 0)}"
            )

        st.markdown(f"**Last research event:** {status.last_research_event}")
        st.caption(
            "Manual discovery/challenger buttons are optional diagnostic controls. "
            "Autonomous heartbeat observes each new-data cycle and records a deliberate "
            "decision (including NO_RESEARCH). Expensive discovery is not auto-run."
        )

        if top_candidates:
            with st.expander("TOP EDGE CANDIDATES — DISCOVERY ONLY", expanded=False):
                st.caption("DISCOVERY ONLY — NOT VALIDATED")
                import pandas as pd

                display_cols = [
                    "edge_id",
                    "market_transition",
                    "condition_text",
                    "best_horizon",
                    "candidate_n",
                    "observed_episodes",
                    "robustness_status",
                    "main_fragility_flag",
                    "incremental_median",
                    "status",
                ]
                df = pd.DataFrame(top_candidates)
                cols = [c for c in display_cols if c in df.columns]
                st.dataframe(df[cols], use_container_width=True, hide_index=True)

        with st.expander("Research Voice", expanded=False):
            if top_candidates:
                st.markdown(_format_research_voice(top_candidates[0]))
            else:
                st.caption("No research voice events. Silence is valid.")

        with st.expander("Challenger details", expanded=False):
            if challenger and challenger.get("run_id") not in (None, "skipped"):
                st.json(
                    {
                        "run_id": challenger.get("run_id"),
                        "discovery_run_id": challenger.get("discovery_run_id"),
                        "candidate_ledger_hash": challenger.get("candidate_ledger_hash"),
                        "report_status": challenger.get("report_status", "ACTIVE"),
                        "data_quality": challenger.get("data_quality"),
                        "candidates_entering": challenger.get(
                            "candidates_entering", challenger.get("candidates_entered")
                        ),
                        "robustness_pass": challenger.get("robustness_pass"),
                        "robustness_fragile": challenger.get("robustness_fragile"),
                        "robustness_reject": challenger.get("robustness_reject"),
                    }
                )
            else:
                st.caption("No challenger run recorded yet.")

        discovery_caption = discovery_disabled_caption(ui_state)
        challenger_caption = challenger_disabled_caption(
            ui_state,
            has_valid_cohort=has_valid_cohort,
        )
        discovery_disabled = not ui_state["can_run_discovery"]
        challenger_disabled = not ui_state["can_run_challenger"]

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "Run discovery (research only)",
                key="edge_research_run_discovery",
                disabled=discovery_disabled,
            ):
                if queue_research_action(st.session_state, "discovery"):
                    st.rerun()
            if discovery_caption:
                st.caption(discovery_caption)
        with col_b:
            if st.button(
                "Run challenger (research only)",
                key="edge_research_run_challenger",
                disabled=challenger_disabled,
            ):
                if queue_research_action(st.session_state, "challenger"):
                    st.rerun()
            if challenger_caption:
                st.caption(challenger_caption)

        if pending_before_execute is not None:
            spinner_label = (
                "Running controlled discovery..."
                if pending_before_execute == "discovery"
                else "Running challenger robustness tests..."
            )
            with st.spinner(spinner_label):
                execute_pending_research_action(st.session_state, engine)
            st.rerun()

        return status.to_dict()

    except Exception as exc:
        st.warning(f"Edge Research: CHALLENGER UNAVAILABLE — {exc}")
        return {"error": str(exc)}
