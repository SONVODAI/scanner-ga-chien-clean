"""
Streamlit UI for Edge Research Engine V1 (Phase 3 challenger).

Display-only — no production coupling.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.edge_research.engine import EdgeResearchEngine


def _fmt_coverage(start: Optional[str], end: Optional[str], count: int) -> str:
    if not start or not end:
        return "No historical coverage detected"
    return f"{start} → {end} ({count:,} lifecycle rows)"


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
        has_candidates = engine.has_discovery_candidates()

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

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Run discovery (research only)", key="edge_research_run_discovery"):
                with st.spinner("Running controlled discovery..."):
                    result = engine.run_discovery()
                    st.success(f"Discovery complete: {result.promoted_candidates} candidate(s).")
                    st.rerun()
        with col_b:
            if st.button(
                "Run challenger (research only)",
                key="edge_research_run_challenger",
                disabled=not has_candidates,
            ):
                with st.spinner("Running challenger robustness tests..."):
                    result = engine.run_challenger(force=True)
                    if result.run_id == "skipped":
                        st.info("Challenger skipped — same candidate ledger already evaluated.")
                    else:
                        st.success(
                            f"Challenger complete: PASS={result.robustness_pass}, "
                            f"FRAGILE={result.robustness_fragile}, REJECT={result.robustness_reject}"
                        )
                    st.rerun()
            if not has_candidates:
                st.caption("Run discovery first.")

        return status.to_dict()

    except Exception as exc:
        st.warning(f"Edge Research: CHALLENGER UNAVAILABLE — {exc}")
        return {"error": str(exc)}
