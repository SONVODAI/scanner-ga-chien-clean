"""
Autonomous daily Edge Research UI view — read-only.

Surfaces the latest successful production session from
``data/edge_research/production_observations`` for Streamlit display.
Does not execute research, mutate artifacts, or substitute Challenger voices.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_daily_run_persistence import (
    lookup_run,
    lookup_run_for_date,
    manifest_path,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    LIVE_FORWARD,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    session_voice_path,
)
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
    build_living_research_ui_read_model,
    build_ui_health_read_model,
    resolve_production_data_dir,
)
from modules.edge_research.storage import resolve_data_dir

AUTONOMOUS_DAILY_SECTION = "AUTONOMOUS_DAILY_RESEARCH"
HISTORICAL_CHALLENGER_SECTION = "HISTORICAL_CHALLENGER_RESEARCH"


def _load_manifest_dict(run_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = manifest_path(run_id, data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _prefer_live_forward_run(trade_date: str, *, data_dir: Optional[Path] = None):
    run = lookup_run_for_date(trade_date, LIVE_FORWARD, data_dir=data_dir)
    if run is None:
        run = lookup_run_for_date(trade_date, BACKFILL_NON_FORWARD, data_dir=data_dir)
    return run


def build_autonomous_daily_edge_ui_view(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Build the view the Edge Research Streamlit panel must show first.

    Uses the canonical living-research read model over production_observations.
    Latest successful session is selected when trade_date is omitted.
    """
    edge_root = resolve_data_dir(data_dir)
    canon = resolve_production_data_dir(edge_root)
    # Pass edge root (or explicit) — resolve_production_runs_root never double-nests.
    rm = build_living_research_ui_read_model(trade_date=trade_date, data_dir=edge_root)
    health = rm.get("health") or build_ui_health_read_model(data_dir=edge_root)
    session_date = rm.get("trade_date") or health.get("latest_successful_research_date")

    run = _prefer_live_forward_run(session_date, data_dir=edge_root) if session_date else None
    if run is None and health.get("latest_run_id"):
        run = lookup_run(str(health["latest_run_id"]), edge_root)

    manifest = _load_manifest_dict(run.run_id, data_dir=edge_root) if run else {}
    discovery_count = manifest.get("discovery_count")
    if discovery_count is None and run is not None:
        discovery_count = len(getattr(run, "observations_born", ()) or ())
    if discovery_count is None:
        dc = rm.get("daily_change") or {}
        discovery_count = 1 if dc.get("new_discovery") else 0

    voice_block = rm.get("voice") or {}
    session_voice = voice_block.get("session_voice")
    if session_voice is None and session_date:
        spath = session_voice_path(session_date, edge_root)
        if spath.exists():
            try:
                session_voice = json.loads(spath.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                session_voice = None

    session_questions = {}
    if isinstance(session_voice, dict):
        for key in (
            "q1_today_i_see_vi",
            "q2_vs_prior_session_vi",
            "q3_market_change_vi",
            "q4_new_evidence_vi",
            "q5_belief_changed_vi",
            "q6_if_not_why_vi",
            "q9_waiting_for_vi",
            "observation_id",
            "assessment_trade_date",
            "voice_kind",
        ):
            if key in session_voice:
                session_questions[key] = session_voice.get(key)

    disposition = (
        (run.run_disposition if run else None)
        or health.get("latest_run_disposition")
        or rm.get("failure_state")
        or "NO_DATA"
    )
    run_id = (run.run_id if run else None) or health.get("latest_run_id")
    run_mode = (run.run_mode if run else None) or health.get("latest_run_mode") or rm.get("run_mode")

    return {
        "section": AUTONOMOUS_DAILY_SECTION,
        "canonical_root": str(canon),
        "edge_data_dir": str(edge_root),
        "canonical_root_name": Path(canon).name,
        "double_nested": Path(canon).name == "production_observations"
        and Path(canon).parent.name == "production_observations",
        "session_date": session_date,
        "run_id": run_id,
        "run_disposition": disposition,
        "run_mode": run_mode,
        "discovery_count": int(discovery_count or 0),
        "bot_spoke_today": bool(manifest.get("bot_spoke_today", voice_block.get("voice_count", 0) > 0)),
        "silence_or_no_discovery": bool(
            manifest.get("silence_or_no_discovery", voice_block.get("silence_or_no_discovery", False))
        ),
        "daily_market_voice_exists": bool(session_voice),
        "session_voice_observation_id": (
            (session_voice or {}).get("observation_id") if isinstance(session_voice, dict) else None
        ),
        "session_voice_questions": session_questions,
        "narrative_vi": voice_block.get("narrative_vi") or "",
        "active_observations": rm.get("active_observations") or [],
        "health": health,
        "authority_badge": rm.get("authority_badge"),
        "living_read_model": rm,
        "view_only": True,
        "requires_streamlit_action": False,
        "challenger_voice_substituted": False,
    }


def render_autonomous_daily_edge_text_snapshot(view: Dict[str, Any]) -> str:
    """Deterministic text surface for tests / diagnostics (no Streamlit)."""
    lines: List[str] = [
        "MR.BOT — EDGE RESEARCH",
        AUTONOMOUS_DAILY_SECTION,
        f"Session: {view.get('session_date') or 'N/A'}",
        f"Run: {view.get('run_disposition') or 'N/A'}",
        f"Run id: {view.get('run_id') or 'N/A'}",
        f"Run mode: {view.get('run_mode') or 'N/A'}",
        f"Discovery today: {view.get('discovery_count', 0)}",
        "DAILY MARKET VOICE",
    ]
    if view.get("daily_market_voice_exists"):
        lines.append(f"Voice id: {view.get('session_voice_observation_id')}")
        qs = view.get("session_voice_questions") or {}
        for key in (
            "q1_today_i_see_vi",
            "q2_vs_prior_session_vi",
            "q3_market_change_vi",
            "q4_new_evidence_vi",
            "q5_belief_changed_vi",
            "q9_waiting_for_vi",
        ):
            val = qs.get(key)
            if val:
                lines.append(str(val))
        if view.get("narrative_vi"):
            lines.append(str(view["narrative_vi"]))
    else:
        lines.append("Session Market Voice: ABSENT")
    lines.append(f"Canonical root: {view.get('canonical_root')}")
    lines.append(HISTORICAL_CHALLENGER_SECTION)
    return "\n".join(lines)


def render_autonomous_daily_edge_block(st: Any, view: Dict[str, Any]) -> None:
    """Streamlit renderer for the autonomous daily production block."""
    st.markdown(f"### {AUTONOMOUS_DAILY_SECTION.replace('_', ' ')}")
    st.caption(
        "Canonical autonomous production — read-only. "
        "Không cần bấm Run discovery / Run challenger. "
        "Không phải Challenger Research Voice."
    )
    if not view.get("session_date"):
        st.info("Chưa có autonomous daily research session trong production_observations.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Session", view.get("session_date") or "—")
    c2.metric("Run", view.get("run_disposition") or "—")
    c3.metric("Discovery today", view.get("discovery_count", 0))
    c4.metric("Mode", view.get("run_mode") or "—")
    if view.get("run_id"):
        st.caption(f"Run id: `{view['run_id']}`")

    st.markdown("#### DAILY MARKET VOICE")
    if view.get("daily_market_voice_exists"):
        oid = view.get("session_voice_observation_id") or "SESSION_MARKET_VOICE"
        st.success(f"**{oid}** — persisted session voice")
        qs = view.get("session_voice_questions") or {}
        for key, label in (
            ("q1_today_i_see_vi", "Hôm nay tôi thấy"),
            ("q2_vs_prior_session_vi", "So với phiên trước"),
            ("q3_market_change_vi", "Market change"),
            ("q4_new_evidence_vi", "Evidence mới"),
            ("q5_belief_changed_vi", "Belief"),
            ("q9_waiting_for_vi", "Đang chờ"),
        ):
            val = qs.get(key)
            if val:
                st.markdown(f"**{label}:** {val}")
        if view.get("narrative_vi") and not qs:
            st.markdown(view["narrative_vi"])
    else:
        st.warning("SESSION_MARKET_VOICE chưa có cho session này.")

    obs = view.get("active_observations") or []
    if obs:
        with st.expander(f"Current observations ({len(obs)})", expanded=False):
            for o in obs[:12]:
                st.caption(
                    f"{o.get('observation_id', '')[:16]}… | "
                    f"{o.get('epistemic_state')} | age={o.get('age_trading_days')}"
                )
