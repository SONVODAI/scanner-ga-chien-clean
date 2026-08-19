"""
Streamlit UI shell for Edge Research Engine V1 (Phase 0/1).

Display-only — no production coupling.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.edge_research.engine import EdgeResearchEngine


def _fmt_coverage(start: Optional[str], end: Optional[str], count: int) -> str:
    if not start or not end:
        return "No historical coverage detected"
    return f"{start} → {end} ({count:,} lifecycle rows)"


def render_edge_research_panel(
    current_market_state: Optional[str] = None,
    current_market_transition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Render MR.BOT — EDGE RESEARCH foundation panel.

    Future Research Voice events will append to this panel without
    rewriting Learning Insight or Earning Money.
    """
    import streamlit as st

    st.markdown("## 🔬 MR.BOT — EDGE RESEARCH")

    engine = EdgeResearchEngine()
    engine.initialize()
    status = engine.get_foundation_status(
        current_market_state=current_market_state,
        current_market_transition=current_market_transition,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Engine status", "FOUNDATION / RESEARCH ONLY")
        st.metric("Production coupling", status.production_coupling)
        st.metric("Hypotheses", status.hypotheses)
        st.metric("Validated edges", status.validated_edges)
    with c2:
        st.metric("Market Research State", status.research_market_state)
        st.metric("Market Transition", status.research_market_transition)
        st.metric("Independent episodes", status.independent_episodes)
        st.metric("Action", status.action)

    st.caption(f"Engine version: {status.engine_version}")
    st.markdown(f"**Historical research coverage:** {_fmt_coverage(status.coverage_start, status.coverage_end, status.observation_count)}")
    st.markdown(f"**Last research event:** {status.last_research_event}")

    # Placeholder container for future Research Voice cards (Phase 2+).
    with st.expander("Research Voice (future)", expanded=False):
        st.caption(
            "No research voice events yet. This area will show EDGE CANDIDATE / "
            "EDGE DISABLED messages when Phase 2+ is implemented."
        )

    return status.to_dict()
