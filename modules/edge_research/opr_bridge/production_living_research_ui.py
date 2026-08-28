"""
Phase 3K.4 — Living Research UI (Streamlit, read-only).

Reads persisted 3K.0–3K.3 products only. Does not execute research or mutate records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
    build_historical_date_read_model,
    build_living_research_ui_read_model,
    build_observation_timeline_read_model,
)
from modules.edge_research.opr_bridge.production_living_research_ui_records import (
    AUTHORITY_BADGE_RESEARCH_ONLY,
    FORBIDDEN_UI_TERMS,
    LIVING_RESEARCH_UI_VERSION,
    STOP_LIVING_RESEARCH_UI_READY,
)
from modules.edge_research.storage import resolve_data_dir


def audit_ui_forbidden_terms(text: str) -> List[str]:
    upper = text.upper()
    return [t for t in FORBIDDEN_UI_TERMS if t in upper]


def render_living_research_ui_text_snapshot(
    read_model: Dict[str, Any],
    *,
    include_timelines: bool = False,
    data_dir: Optional[Path] = None,
) -> str:
    """Deterministic text snapshot for tests and diagnostics (no Streamlit)."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("MR.BOT — HÔM NAY TÔI ĐANG NGHĨ GÌ?")
    lines.append(f"Version: {read_model.get('version', LIVING_RESEARCH_UI_VERSION)}")
    lines.append(f"Authority: {AUTHORITY_BADGE_RESEARCH_ONLY}")
    lines.append(f"Trade date: {read_model.get('trade_date', 'N/A')}")
    if read_model.get("run_mode_label"):
        lines.append(f"Run mode: {read_model['run_mode_label']}")
    if read_model.get("failure_state"):
        lines.append(f"Failure state: {read_model['failure_state']}")
    lines.append("")

    voice = read_model.get("voice") or {}
    lines.append("--- TODAY'S VOICE ---")
    lines.append(voice.get("narrative_vi") or read_model.get("message_vi", "Không có voice."))
    lines.append("")

    dc = read_model.get("daily_change") or {}
    lines.append("--- HÔM NAY vs HÔM QUA ---")
    lines.append(f"Previous session: {dc.get('previous_trade_date', 'N/A')}")
    lines.append(f"Silence/no discovery: {dc.get('silence_or_no_discovery')}")
    lines.append(f"New discovery: {dc.get('new_discovery')}")
    lines.append(f"Belief changes: {len(dc.get('belief_changes') or [])}")
    for bc in (dc.get("belief_changes") or [])[:3]:
        lines.append(f"  • {bc.get('observation_id')}: {bc.get('previous')} → {bc.get('current')}")
    for uc in (dc.get("unchanged_belief_with_market_change") or [])[:2]:
        lines.append(f"  • Unchanged despite market: {uc.get('observation_id')} — {uc.get('why', '')[:80]}")
    lines.append("")

    obs = read_model.get("active_observations") or []
    lines.append(f"--- OBSERVATIONS ĐANG SỐNG ({len(obs)}) ---")
    for o in obs[:5]:
        auth = "REAL FORWARD" if o.get("forward_authority") else "NON-FORWARD"
        lines.append(
            f"  • {o.get('observation_id')[:12]}… | {o.get('epistemic_state')} | "
            f"{o.get('lifecycle')} | age={o.get('age_trading_days')} | {auth}"
        )
    lines.append("")

    fwd = read_model.get("forward_evidence") or {}
    lines.append("--- FORWARD EVIDENCE ---")
    lines.append(f"Maturity: {fwd.get('maturity_label')}")
    lines.append(f"Eligible N: {fwd.get('eligible_forward_evidence_n')}")
    if fwd.get("tiny_sample_warning"):
        lines.append("⚠ Mẫu forward quá nhỏ — không đủ để kết luận.")
    if fwd.get("historical_only"):
        lines.append("ℹ Chỉ có dữ liệu historical/backfill — KHÔNG phải forward evidence thật.")
    for stmt in (fwd.get("statements") or [])[:3]:
        lines.append(f"  • {stmt}")
    lines.append("")

    sk = read_model.get("self_knowledge") or {}
    lines.append("--- MR.BOT BIẾT GÌ VỀ CHÍNH MÌNH? ---")
    for stmt in (sk.get("statements") or [])[:4]:
        lines.append(f"  • {stmt}")
    lines.append("")

    health = read_model.get("health") or {}
    lines.append("--- DATA HEALTH ---")
    lines.append(f"Latest success: {health.get('latest_successful_research_date')}")
    if health.get("warnings"):
        for w in health["warnings"]:
            lines.append(f"⚠ {w}")

    if include_timelines and obs and read_model.get("trade_date"):
        lines.append("")
        lines.append("--- OBSERVATION TIMELINE (first) ---")
        oid = obs[0]["observation_id"]
        timeline = build_observation_timeline_read_model(
            oid, as_of_trade_date=read_model["trade_date"], data_dir=data_dir
        )
        for ev in timeline[:8]:
            lines.append(f"  [{ev.get('trade_date')}] {ev.get('kind')}: {ev.get('epistemic_state') or ev.get('horizon', '')}")

    return "\n".join(lines)


def render_living_research_ui_panel(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Streamlit panel — read persisted products only.
    Returns read model dict for testing/audit.
    """
    import streamlit as st

    data_dir = data_dir or resolve_data_dir(None)
    available = build_living_research_ui_read_model(data_dir=data_dir).get("available_dates") or []

    st.markdown("## 🧠 MR.BOT — HÔM NAY TÔI ĐANG NGHĨ GÌ?")
    st.caption(
        "Autonomous living research notebook — read-only from "
        "data/edge_research/production_observations. "
        "Không khuyến nghị mua/bán. Không chạy research khi render. "
        "Distinct from Historical Challenger research."
    )
    st.info(f"🏷 **{AUTHORITY_BADGE_RESEARCH_ONLY}** — UI này không có trading authority.")

    col_date, col_mode = st.columns([2, 2])
    with col_date:
        if available:
            selected = st.selectbox(
                "Ngày research",
                options=sorted(available, reverse=True),
                index=0 if trade_date is None else (available.index(trade_date) if trade_date in available else 0),
                key="living_research_ui_date",
            )
        else:
            selected = trade_date
            st.warning("Chưa có ngày research nào được persist.")
    with col_mode:
        preview_rm = build_living_research_ui_read_model(trade_date=selected, data_dir=data_dir)
        if preview_rm.get("run_mode_label"):
            st.caption(preview_rm["run_mode_label"])

    read_model = build_living_research_ui_read_model(trade_date=selected, data_dir=data_dir)

    _render_health_strip(read_model)
    _render_today_voice(st, read_model)
    _render_daily_change(st, read_model)
    _render_active_observations(st, read_model, data_dir)
    _render_forward_evidence(st, read_model)
    _render_self_knowledge(st, read_model)
    _render_history_tab(st, read_model, data_dir)

    snapshot_text = render_living_research_ui_text_snapshot(read_model, data_dir=data_dir)
    forbidden = audit_ui_forbidden_terms(snapshot_text)
    if forbidden:
        st.error(f"UI audit: forbidden terms detected: {forbidden}")

    with st.expander("🔍 Audit / provenance (optional)", expanded=False):
        st.caption(f"UI version: {LIVING_RESEARCH_UI_VERSION} | Stop: {STOP_LIVING_RESEARCH_UI_READY}")
        st.json({
            "trade_date": read_model.get("trade_date"),
            "run_mode": read_model.get("run_mode"),
            "failure_state": read_model.get("failure_state"),
            "health": read_model.get("health"),
        })

    return read_model


def _render_health_strip(read_model: Dict[str, Any]) -> None:
    import streamlit as st

    health = read_model.get("health") or {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Latest research", health.get("latest_successful_research_date") or "—")
    with c2:
        st.metric("Viewing", read_model.get("trade_date") or "—")
    with c3:
        st.metric("Observations", len(read_model.get("active_observations") or []))
    with c4:
        fwd = read_model.get("forward_evidence") or {}
        st.metric("Forward N", fwd.get("eligible_forward_evidence_n", 0))
    if read_model.get("failure_state") == "WAITING_FOR_DATA":
        st.warning("⏳ WAITING_FOR_DATA — chưa có EOD cho ngày này.")
    elif read_model.get("failure_state") == "FAILED_CLOSED":
        st.error("❌ Daily run FAILED_CLOSED — xem records nếu đã persist.")
    elif read_model.get("failure_state") == "NO_LIVE_FORWARD_DATA":
        st.info("ℹ Chưa có LIVE_FORWARD data — chỉ historical/backfill hoặc chưa chạy production.")


def _render_today_voice(st: Any, read_model: Dict[str, Any]) -> None:
    st.markdown("### 📓 Giọng nói hôm nay")
    voice = read_model.get("voice") or {}
    narrative = voice.get("narrative_vi") or read_model.get("message_vi", "")
    if narrative:
        st.markdown(narrative)
    else:
        st.info("Không có narrative cho ngày này — có thể là ngày im lặng hoặc chưa chạy research.")


def _render_daily_change(st: Any, read_model: Dict[str, Any]) -> None:
    st.markdown("### ↔ Hôm nay vs hôm qua")
    dc = read_model.get("daily_change") or {}
    prev = dc.get("previous_trade_date")
    if prev:
        st.caption(f"So sánh với phiên trước: **{prev}**")
    else:
        st.caption("Không có phiên trước để so sánh.")

    if dc.get("silence_or_no_discovery"):
        st.info("Hôm nay không có discovery mới.")

    changes = dc.get("belief_changes") or []
    if changes:
        st.markdown("**Belief đã thay đổi:**")
        for bc in changes:
            with st.expander(f"{bc['observation_id'][:16]}… : {bc.get('previous')} → {bc.get('current')}"):
                st.write(bc.get("why") or "Không ghi lý do.")
    elif dc.get("unchanged_belief_with_market_change"):
        st.markdown("**Market đổi nhưng belief chưa đổi:**")
        for uc in dc["unchanged_belief_with_market_change"]:
            st.caption(f"{uc['observation_id']}: {uc.get('why', '')}")
    elif dc.get("nothing_meaningful_changed"):
        st.caption("Không có thay đổi meaningful — không paraphrase để tạo vẻ mới.")


def _render_active_observations(st: Any, read_model: Dict[str, Any], data_dir: Optional[Path]) -> None:
    st.markdown("### 🔬 Observations đang sống")
    obs = read_model.get("active_observations") or []
    if not obs:
        st.info("Không có observation active cho ngày này.")
        return
    for o in obs:
        auth_badge = "🟢 LIVE_FORWARD" if o.get("forward_authority") else "⚪ NON-FORWARD"
        label = f"{o.get('hypothesis', o['observation_id'])[:48]}… | {o.get('epistemic_state')} | {auth_badge}"
        with st.expander(label, expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Age (sessions)", o.get("age_trading_days", 0))
            c2.metric("Lifecycle", o.get("lifecycle", "—"))
            c3.metric("Strength", o.get("evidence_strength") or "—")
            st.caption(f"Birth: {o.get('birth_date')} | Mode: {o.get('observation_mode')}")
            st.write(f"**Đang chờ:** {o.get('waiting_for', '—')}")
            hs = o.get("horizon_status") or {}
            st.write("**T3/T5/T10:**", ", ".join(
                f"{h}: {'✓' if v.get('released') else 'pending'}" for h, v in hs.items()
            ))
            if o.get("dependence_warning"):
                st.warning(f"Dependence: {o['dependence_warning']}")
            if read_model.get("trade_date"):
                timeline = build_observation_timeline_read_model(
                    o["observation_id"],
                    as_of_trade_date=read_model["trade_date"],
                    data_dir=data_dir,
                )
                st.markdown("**Timeline (state tại thời điểm đó):**")
                for ev in timeline:
                    if ev["kind"] == "BIRTH":
                        st.caption(f"🌱 {ev['trade_date']} BIRTH — {ev.get('epistemic_state')}")
                    elif ev["kind"] == "ASSESSMENT":
                        ch = " (belief changed)" if ev.get("belief_changed") else ""
                        st.caption(f"📋 {ev['trade_date']} — {ev.get('epistemic_state')}{ch}")
                    elif ev["kind"] == "OUTCOME":
                        st.caption(f"📊 {ev['trade_date']} {ev.get('horizon')} — {ev.get('evaluation_status')}")


def _render_forward_evidence(st: Any, read_model: Dict[str, Any]) -> None:
    st.markdown("### 📈 Forward evidence")
    fwd = read_model.get("forward_evidence") or {}
    if fwd.get("historical_only"):
        st.warning("Chưa có REAL FORWARD evidence. Mọi simulation là NON-FORWARD.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("T3", fwd.get("t3_available", 0))
    c2.metric("T5", fwd.get("t5_available", 0))
    c3.metric("T10", fwd.get("t10_available", 0))
    c4.metric("Maturity", fwd.get("maturity_label") or "—")
    if fwd.get("tiny_sample_warning"):
        st.warning("⚠ Mẫu forward quá nhỏ (N<3) — không đủ để kết luận đáng tin.")
    st.caption(fwd.get("authority_note", ""))


def _render_self_knowledge(st: Any, read_model: Dict[str, Any]) -> None:
    st.markdown("### 🪞 Mr.BOT biết gì về chính mình?")
    sk = read_model.get("self_knowledge") or {}
    for stmt in sk.get("statements") or []:
        st.caption(f"• {stmt}")
    if not sk.get("statements"):
        st.info("Chưa có self-knowledge statements — ledger trống.")


def _render_history_tab(st: Any, read_model: Dict[str, Any], data_dir: Optional[Path]) -> None:
    with st.expander("📅 Research History", expanded=False):
        dates = read_model.get("available_dates") or []
        if not dates:
            st.caption("Chưa có lịch sử.")
            return
        hist_date = st.selectbox("Xem ngày", options=sorted(dates, reverse=True), key="living_research_hist_date")
        hist = build_historical_date_read_model(hist_date, data_dir=data_dir)
        st.caption(f"Temporal cutoff: {hist['temporal_cutoff']} — future leakage blocked")
        st.markdown(render_living_research_ui_text_snapshot(
            {**read_model, **hist, "trade_date": hist_date},
            data_dir=data_dir,
        ))
