"""Streamlit adapter for the read-only LIVE CANDIDATE × P×V panel."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from modules.live_candidate_pxv_ui.view import build_panel

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def render_live_candidate_pxv_panel(
    *,
    now: datetime | None = None,
    watchlist_path: Path | None = None,
    evidence_path: Path | None = None,
    status_path: Path | None = None,
    state: Any = None,
) -> None:
    """Render one compact expander. Never calls Camera. Never writes sources."""
    import streamlit as st

    panel = state or build_panel(
        now=now or datetime.now(VN),
        watchlist_path=watchlist_path,
        evidence_path=evidence_path,
        status_path=status_path,
    )
    data = panel.as_dict() if hasattr(panel, "as_dict") else panel
    runner = data.get("runner") or {}

    with st.expander("LIVE CANDIDATE × P×V", expanded=True):
        st.caption("Quan sát only · không phải lệnh mua/bán · không Telegram · alert_eligible=false")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Runner", runner.get("label") or "STOPPED")
        with c2:
            st.metric("Freshness", "STALE" if runner.get("is_stale") else "LIVE")
        with c3:
            st.metric("alert_eligible", "false")
        if runner.get("is_stale"):
            st.warning(runner.get("banner") or "Live-shadow runner STALE / stopped. Evidence below is NOT current.")
        else:
            st.info(runner.get("detail") or "")

        if data.get("empty"):
            st.markdown(f"**{data.get('empty_message')}**")
            return

        for card in data.get("cards") or []:
            _render_card(st, card)


def _render_card(st: Any, card: dict[str, Any]) -> None:
    valid = bool(card.get("evidence_valid"))
    waiting = bool(card.get("waiting_first_bar"))
    pub = card.get("published_evidence") or ("WAIT" if waiting else "—")
    raw = card.get("raw_evidence") or ("WAIT" if waiting else "—")
    title = f"{card.get('symbol')} · {card.get('candidate_reason') or ''}"
    st.markdown(f"**{title}**")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.write(f"PUBLISHED **{pub}**")
    with m2:
        st.write(f"RAW **{raw}**")
    with m3:
        st.write(f"Data **{card.get('data_state') or '—'}**")
    with m4:
        legal = card.get("chronology_legal")
        legal_s = "true" if legal is True else ("false" if legal is False else "n/a")
        st.write(f"chronology_legal **{legal_s}**")
    st.caption(
        f"Candidate {card.get('candidate_first_seen_hm') or card.get('candidate_first_seen_ts')} · "
        f"eligible_from {card.get('eligible_from_hm') or card.get('eligible_from')} · "
        f"bar {card.get('latest_asof_hm') or '—'} · "
        f"observed {card.get('observed_at') or '—'} · "
        f"freshness {card.get('freshness')}"
    )
    st.write(card.get("explanation") or "")
    if not valid and not waiting:
        st.warning("chronology_legal=false — không trình bày như bằng chứng hợp lệ.")
    hist = card.get("history") or []
    if hist:
        with st.expander(f"Lịch sử P×V — {card.get('symbol')}", expanded=False):
            for h in hist:
                st.write(
                    f"{h.get('asof_hm') or ''}  {h.get('kind')}  "
                    f"RAW {h.get('raw_from')}→{h.get('raw_to')}  "
                    f"PUBLISHED {h.get('published_from')}→{h.get('published_to')}"
                )
    st.divider()
