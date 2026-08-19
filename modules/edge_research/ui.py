"""
Streamlit UI for Edge Research Engine V1 (Phase 3 challenger).

Display-only — no production coupling.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, TypeVar

from modules.edge_research.engine import EdgeResearchEngine

EDGE_RESEARCH_BUSY_STRICT_VERSION = 1
EDGE_UI_DIAG_BUILD = "EDGE_UI_DIAG_V1"
T = TypeVar("T")


def _fmt_coverage(start: Optional[str], end: Optional[str], count: int) -> str:
    if not start or not end:
        return "No historical coverage detected"
    return f"{start} → {end} ({count:,} lifecycle rows)"


def execution_in_progress_from_session(session_state: Mapping[str, Any]) -> bool:
    """Only literal boolean True means busy; normalize corrupt session values."""
    busy = session_state.get("edge_research_busy", False)
    if busy is True:
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


def format_edge_ui_diagnostic_line(
    *,
    coverage_start: Optional[str],
    coverage_end: Optional[str],
    observation_count: int,
    raw_busy: Any,
    raw_busy_type: str,
    strict_v: Any,
    execution_in_progress: bool,
    has_valid_cohort: bool,
    ui_state: Dict[str, bool],
    discovery_caption: Optional[str],
    challenger_caption: Optional[str],
) -> str:
    discovery_disabled = not ui_state["can_run_discovery"]
    challenger_disabled = not ui_state["can_run_challenger"]
    return (
        f"EDGE UI DIAG | build={EDGE_UI_DIAG_BUILD} | "
        f"coverage={ui_state['has_research_coverage']} | "
        f"coverage_start={coverage_start!r} | "
        f"coverage_end={coverage_end!r} | "
        f"observations={observation_count!r} | "
        f"raw_busy={raw_busy!r} | "
        f"raw_busy_type={raw_busy_type} | "
        f"strict_v={strict_v!r} | "
        f"execution_in_progress={execution_in_progress} | "
        f"cohort={has_valid_cohort} | "
        f"can_run_discovery={ui_state['can_run_discovery']} | "
        f"discovery_disabled={discovery_disabled} | "
        f"can_run_challenger={ui_state['can_run_challenger']} | "
        f"challenger_disabled={challenger_disabled} | "
        f"discovery_caption={discovery_caption!r} | "
        f"challenger_caption={challenger_caption!r}"
    )


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
        execution_in_progress = execution_in_progress_from_session(st.session_state)
        ui_state = compute_edge_research_button_state(
            coverage_start=status.coverage_start,
            coverage_end=status.coverage_end,
            observation_count=status.observation_count,
            has_valid_cohort=has_valid_cohort,
            execution_in_progress=execution_in_progress,
        )

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

        if "edge_research_busy" in st.session_state:
            raw_busy = st.session_state["edge_research_busy"]
            raw_busy_type = type(raw_busy).__name__
        else:
            raw_busy = "<MISSING>"
            raw_busy_type = "missing"
        strict_v = st.session_state.get("_edge_research_busy_strict_v", "<MISSING>")
        discovery_caption = discovery_disabled_caption(ui_state)
        challenger_caption = challenger_disabled_caption(
            ui_state,
            has_valid_cohort=has_valid_cohort,
        )
        discovery_disabled = not ui_state["can_run_discovery"]
        challenger_disabled = not ui_state["can_run_challenger"]
        st.caption(
            format_edge_ui_diagnostic_line(
                coverage_start=status.coverage_start,
                coverage_end=status.coverage_end,
                observation_count=status.observation_count,
                raw_busy=raw_busy,
                raw_busy_type=raw_busy_type,
                strict_v=strict_v,
                execution_in_progress=execution_in_progress,
                has_valid_cohort=has_valid_cohort,
                ui_state=ui_state,
                discovery_caption=discovery_caption,
                challenger_caption=challenger_caption,
            )
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "Run discovery (research only)",
                key="edge_research_run_discovery",
                disabled=discovery_disabled,
            ):
                with st.spinner("Running controlled discovery..."):
                    result = run_with_edge_research_busy_guard(
                        st.session_state,
                        engine.run_discovery,
                    )
                    st.success(f"Discovery complete: {result.promoted_candidates} candidate(s).")
                    st.rerun()
            if discovery_caption:
                st.caption(discovery_caption)
        with col_b:
            if st.button(
                "Run challenger (research only)",
                key="edge_research_run_challenger",
                disabled=challenger_disabled,
            ):
                with st.spinner("Running challenger robustness tests..."):
                    result = run_with_edge_research_busy_guard(
                        st.session_state,
                        lambda: engine.run_challenger(force=True),
                    )
                    if result.run_id == "skipped":
                        st.info("Challenger skipped — same candidate ledger already evaluated.")
                    else:
                        st.success(
                            f"Challenger complete: PASS={result.robustness_pass}, "
                            f"FRAGILE={result.robustness_fragile}, REJECT={result.robustness_reject}"
                        )
                    st.rerun()
            if challenger_caption:
                st.caption(challenger_caption)

        return status.to_dict()

    except Exception as exc:
        st.warning(f"Edge Research: CHALLENGER UNAVAILABLE — {exc}")
        return {"error": str(exc)}
