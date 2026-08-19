"""
Streamlit UI for Edge Research Engine V1 (Phase 2 discovery).

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
    return (
        f"**EDGE CANDIDATE — {candidate.get('edge_id', '')}**\n\n"
        f"Market: {candidate.get('market_transition', '')}\n\n"
        f"Condition: {candidate.get('condition_text', '')}\n\n"
        f"Best horizon: {candidate.get('best_horizon', '')}\n\n"
        f"Candidate median: {candidate.get('candidate_median', '—')}%\n\n"
        f"Same-state baseline median: {candidate.get('baseline_median', '—')}%\n\n"
        f"Incremental median: {candidate.get('incremental_median', '—')}%\n\n"
        f"Candidate WR: {candidate.get('candidate_win_rate', '—')}%\n\n"
        f"Baseline WR: {candidate.get('baseline_win_rate', '—')}%\n\n"
        f"Observations: {candidate.get('candidate_n', 0)}\n\n"
        f"Status: {candidate.get('status', 'CANDIDATE')}\n\n"
        f"**ACTION: RESEARCH ONLY — NOT VALIDATED**"
    )


def render_edge_research_panel(
    current_market_state: Optional[str] = None,
    current_market_transition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Render MR.BOT — EDGE RESEARCH panel (Phase 2 discovery).
    Reads cached discovery results — does not run search on every rerender.
    """
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
        top_candidates = engine.get_top_candidates(limit=10)

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Engine status", "DISCOVERY / RESEARCH ONLY")
            st.metric("Production coupling", status.production_coupling)
            st.metric("Hypotheses", status.hypotheses)
            st.metric("Validated edges", status.validated_edges)
        with c2:
            st.metric("Market Research State", status.research_market_state)
            st.metric("Market Transition", status.research_market_transition)
            st.metric("Independent episodes", 0)
            st.metric("Action", status.action)

        st.caption(f"Engine version: {status.engine_version}")
        st.markdown(
            f"**Historical research coverage:** "
            f"{_fmt_coverage(status.coverage_start, status.coverage_end, status.observation_count)}"
        )

        if status.discovery_summary:
            ds = status.discovery_summary
            st.markdown(
                f"**Discovery summary:** "
                f"Eligible observations: {ds.get('eligible_observations', 0):,} | "
                f"Market contexts: {ds.get('market_contexts_analyzed', 0)} | "
                f"Conditions tested: {ds.get('conditions_tested', 0):,} | "
                f"Candidates discovered: {ds.get('candidates_discovered', 0)}"
            )

        st.markdown(f"**Last research event:** {status.last_research_event}")

        if top_candidates:
            with st.expander("TOP EDGE CANDIDATES — DISCOVERY ONLY", expanded=False):
                st.caption("DISCOVERY ONLY — NOT VALIDATED")
                display_cols = [
                    "edge_id",
                    "market_transition",
                    "condition_text",
                    "best_horizon",
                    "candidate_n",
                    "candidate_median",
                    "baseline_median",
                    "incremental_median",
                    "candidate_win_rate",
                    "baseline_win_rate",
                    "incremental_win_rate",
                    "status",
                ]
                import pandas as pd

                df = pd.DataFrame(top_candidates)
                cols = [c for c in display_cols if c in df.columns]
                st.dataframe(df[cols], use_container_width=True, hide_index=True)

        with st.expander("Research Voice", expanded=False):
            if top_candidates:
                st.markdown(_format_research_voice(top_candidates[0]))
            else:
                st.caption("No research voice events. Silence is valid.")

        with st.expander("Discovery details", expanded=False):
            if discovery:
                dq = discovery.get("data_quality", {})
                st.json(
                    {
                        "run_id": discovery.get("run_id"),
                        "data_quality": dq,
                        "conditions_tested": discovery.get("conditions_tested"),
                        "rejected_insufficient_sample": discovery.get("rejected_insufficient_sample"),
                        "rejected_no_incremental_edge": discovery.get("rejected_no_incremental_edge"),
                        "promoted_candidates": discovery.get("promoted_candidates"),
                    }
                )
            else:
                st.caption("No discovery run recorded yet.")

        if st.button("Run discovery (research only)", key="edge_research_run_discovery"):
            with st.spinner("Running controlled discovery..."):
                result = engine.run_discovery()
                st.success(
                    f"Discovery complete: {result.promoted_candidates} candidate(s) promoted."
                )
                st.rerun()

        return status.to_dict()

    except Exception as exc:
        st.warning(f"Edge Research: RESEARCH UNAVAILABLE — {exc}")
        return {"error": str(exc)}
