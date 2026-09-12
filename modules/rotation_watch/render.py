"""Streamlit adapter for isolated Rotation Watch."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from modules.rotation_watch.engine import RotationBoard, build_board

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
    watchlist_path: Path | None = None,
    provider: Any | None = None,
    injected: dict | None = None,
    board: RotationBoard | None = None,
    persist: bool = True,
) -> RotationBoard:
    """Render one expander. Failure is handled by the app.py try/except."""
    import streamlit as st

    panel = board or build_board(
        now=now or datetime.now(VN),
        watchlist_path=watchlist_path,
        provider=provider,
        injected=injected,
        persist=persist,
    )

    with st.expander("🔄 ROTATION WATCH", expanded=True):
        st.caption(
            "Danh sách xoay vòng thủ công · không phải lệnh tự động · "
            "độc lập BOT Candidate / Edge / Learning · P×V dùng interpreter đóng băng"
        )
        if panel.empty:
            st.info(panel.empty_message)
            return panel

        source = panel.rows[0].data_source_label if panel.rows else ""
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Mã theo dõi", str(len(panel.rows)))
        with c2:
            st.metric("Nguồn giá", panel.rows[0].data_source if panel.rows else "—")
        with c3:
            live_n = sum(1 for r in panel.rows if r.freshness == "LIVE")
            st.metric("LIVE", str(live_n))
        st.caption(f"Data source: {source}")

        table = panel.display_table()

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
            }
            return [colors.get(str(v), "") for v in s]

        try:
            styled = table.style.apply(_style, subset=["Rotation State"]).apply(
                _style, subset=["Suggested Action"]
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(table, use_container_width=True, hide_index=True)

        for row in panel.rows:
            color = STATE_COLORS.get(row.rotation_state, "#374151")
            with st.expander(
                f"{row.symbol} · {row.rotation_state} · {row.suggested_action}",
                expanded=row.rotation_state
                in {"BUY_READY", "SELL_READY", "TREND_HOLD", "RISK", "DATA_UNCERTAIN"},
            ):
                st.markdown(
                    f"<div style='color:{color};font-weight:700'>"
                    f"{row.rotation_state} → {row.suggested_action}</div>",
                    unsafe_allow_html=True,
                )
                st.write(
                    f"Giá **{row.current_price}** · Lower **{row.lower_zone}** · "
                    f"Upper **{row.upper_zone}** · Range **{row.range_position_pct}**%"
                    if row.range_position_pct is not None
                    else f"Giá **{row.current_price}** · Lower **{row.lower_zone}** · Upper **{row.upper_zone}**"
                )
                st.write(
                    f"Raw P×V **{row.raw_pxv}** · Published P×V **{row.published_pxv}** · "
                    f"nến {row.last_bar_ts or '—'} · freshness **{row.freshness}**"
                )
                st.caption(row.pxv_why or "")
                st.markdown("**Rotation evidence**")
                for bit in row.rotation_evidence:
                    st.write(f"- {bit}")
                if row.t25_checkpoint:
                    st.info(row.t25_checkpoint)
    return panel
