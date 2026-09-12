"""Streamlit adapter — artifact read only. Never calls the Camera provider."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from modules.rotation_watch.view import build_panel, display_table

VN = ZoneInfo("Asia/Ho_Chi_Minh")

STATE_COLORS = {
    "BUY_READY": "#065f46",
    "SELL_READY": "#991b1b",
    "TREND_HOLD": "#1e3a8a",
    "RISK": "#9a3412",
    "DATA_UNCERTAIN": "#92400e",
    "HOLD": "#14532d",
}


def render_rotation_watch_panel(
    *,
    now: datetime | None = None,
    artifact_path: Path | None = None,
    board: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import streamlit as st

    panel = board or build_panel(now=now or datetime.now(VN), artifact_path=artifact_path)

    with st.expander("🔄 ROTATION WATCH", expanded=True):
        st.caption(
            "Danh sách xoay vòng thủ công · không tự mua/bán · đọc artifact sidecar · "
            "độc lập Candidate / Edge / Learning · panel chỉ đọc artifact"
        )
        if panel.get("empty"):
            st.info(panel.get("empty_message") or "")
            return panel

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Mã theo dõi", str(len(panel.get("rows") or [])))
        with c2:
            st.metric("Session", str(panel.get("session_phase") or "—"))
        with c3:
            live_n = sum(1 for r in panel.get("rows") or [] if r.get("actionable"))
            st.metric("Actionable now", str(live_n))
        st.caption(f"Artifact observed_at: {panel.get('observed_at') or '—'}")
        transport = panel.get("transport") or {}
        if transport.get("error"):
            st.warning(
                f"Rotation remote GET fail-closed: {transport.get('detail') or transport.get('error')}"
            )

        table = display_table(panel)

        def _style(s):
            colors = {
                "BUY_READY": "background-color: #bbf7d0; color: #065f46; font-weight: 700",
                "BUY READY": "background-color: #bbf7d0; color: #065f46; font-weight: 700",
                "SELL_READY": "background-color: #fecaca; color: #991b1b; font-weight: 700",
                "SELL READY": "background-color: #fecaca; color: #991b1b; font-weight: 700",
                "TREND_HOLD": "background-color: #bfdbfe; color: #1e3a8a; font-weight: 700",
                "TREND HOLD": "background-color: #bfdbfe; color: #1e3a8a; font-weight: 700",
                "RISK": "background-color: #fed7aa; color: #9a3412; font-weight: 700",
                "RISK / REVIEW": "background-color: #fed7aa; color: #9a3412; font-weight: 700",
                "DATA_UNCERTAIN": "background-color: #fde68a; color: #92400e; font-weight: 700",
                "WAIT": "background-color: #fef3c7; color: #92400e; font-weight: 700",
            }
            return [colors.get(str(v), "") for v in s]

        try:
            styled = table.style.apply(_style, subset=["Last-session State"]).apply(
                _style, subset=["Suggested Action"]
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(table, use_container_width=True, hide_index=True)

        for row in panel.get("rows") or []:
            state = str(row.get("last_session_state") or row.get("rotation_state") or "")
            action = str(row.get("suggested_action") or "")
            color = STATE_COLORS.get(state, "#374151")
            if not row.get("actionable"):
                color = "#92400e"
            with st.expander(
                f"{row.get('symbol')} · last {state} · now {action}",
                expanded=action in {"BUY READY", "SELL READY", "TREND HOLD", "RISK / REVIEW", "WAIT"}
                and state in {"BUY_READY", "SELL_READY", "TREND_HOLD", "RISK", "DATA_UNCERTAIN"},
            ):
                st.markdown(
                    f"<div style='color:{color};font-weight:700'>"
                    f"Last-session {state} → current action {action}</div>",
                    unsafe_allow_html=True,
                )
                if row.get("action_gate_reason"):
                    st.warning(row.get("action_gate_reason"))
                st.write(
                    f"Giá **{row.get('current_price')}** · Location **{row.get('location') or '—'}** · "
                    f"Lower **{row.get('lower_zone')}** · "
                    f"Upper **{row.get('upper_zone')}** · Range **{row.get('range_position_pct')}**%"
                )
                st.write(
                    f"Raw P×V **{row.get('raw_pxv')}** · Published P×V **{row.get('published_pxv')}** · "
                    f"nến {row.get('last_bar_ts') or '—'} · freshness **{row.get('freshness')}**"
                )
                st.caption(row.get("pxv_why") or row.get("evidence_why") or "")
                st.markdown("**Rotation evidence**")
                for bit in row.get("rotation_evidence") or []:
                    st.write(f"- {bit}")
    return panel
