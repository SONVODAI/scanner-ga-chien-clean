"""
Autonomous daily Edge Research UI view — read-only, Streamlit-safe.

Reads ONLY the canonical production root:
  data/edge_research/production_observations

Does not execute research, mutate artifacts, or substitute Challenger voices.
Intentionally avoids heavy opr_bridge imports so Streamlit Cloud (main) can
render this surface without requiring the full OPR stack on the deploy branch.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WAITING_FOR_DATA = "WAITING_FOR_DATA"
SKIPPED_NON_TRADING_DAY = "SKIPPED_NON_TRADING_DAY"

AUTONOMOUS_DAILY_SECTION = "AUTONOMOUS_DAILY_RESEARCH"
HISTORICAL_CHALLENGER_SECTION = "HISTORICAL_CHALLENGER_RESEARCH"

_SESSION_VOICE_KEYS = (
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
)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None


def derive_vn_calendar_date(now: Optional[datetime] = None) -> str:
    """Asia/Ho_Chi_Minh calendar date — never server-local / UTC date."""
    now = now or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    else:
        now = now.astimezone(VN_TZ)
    return now.strftime("%Y-%m-%d")


def _load_holiday_set() -> set[str]:
    path = Path(__file__).resolve().parents[2] / "config" / "vn_trading_calendar.json"
    payload = _read_json(path) or {}
    holidays = {str(h)[:10] for h in (payload.get("holidays") or [])}
    for key, ov in (payload.get("closure_overrides") or {}).items():
        if isinstance(ov, dict) and ov.get("closed"):
            holidays.add(str(key)[:10])
    return holidays


def is_vn_trading_session(trade_date: str) -> bool:
    td = str(trade_date)[:10]
    try:
        weekday = datetime.strptime(td, "%Y-%m-%d").weekday()
    except ValueError:
        return False
    if weekday >= 5:
        return False
    return td not in _load_holiday_set()


def _run_metas(prod_root: Path) -> List[Dict[str, Any]]:
    index = _read_json(prod_root / "daily_run_index.json") or {}
    return [m for m in (index.get("runs") or {}).values() if isinstance(m, dict)]


def _prefer_live(matches: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = list(matches)
    if not rows:
        return None
    live = [m for m in rows if m.get("run_mode") == "LIVE_FORWARD"]
    pool = live or rows

    def _key(m: Dict[str, Any]) -> tuple:
        return (
            str(m.get("run_started_at") or ""),
            str(m.get("run_id") or ""),
        )

    return max(pool, key=_key)


def _latest_successful_run_meta(prod_root: Path) -> Optional[Dict[str, Any]]:
    candidates = [
        m
        for m in _run_metas(prod_root)
        if m.get("run_disposition") == "SUCCESS" and m.get("target_trade_date")
    ]
    if not candidates:
        return None

    def _key(m: Dict[str, Any]) -> tuple:
        mode_rank = 1 if m.get("run_mode") == "LIVE_FORWARD" else 0
        return (str(m.get("target_trade_date")), mode_rank, str(m.get("run_id") or ""))

    return max(candidates, key=_key)


def _authoritative_meta_for_date(prod_root: Path, trade_date: str) -> Optional[Dict[str, Any]]:
    matches = [
        m
        for m in _run_metas(prod_root)
        if m.get("target_trade_date") == trade_date
        and m.get("run_disposition") in ("SUCCESS", SKIPPED_NON_TRADING_DAY, WAITING_FOR_DATA)
    ]
    for disp in ("SUCCESS", SKIPPED_NON_TRADING_DAY):
        picked = _prefer_live(m for m in matches if m.get("run_disposition") == disp)
        if picked:
            return picked
    return _prefer_live(m for m in matches if m.get("run_disposition") == WAITING_FOR_DATA)


def _load_run_payload(prod_root: Path, run_id: str) -> Dict[str, Any]:
    return _read_json(prod_root / "daily_runs" / f"{run_id}.json") or {}


def _load_manifest(prod_root: Path, run_id: str) -> Dict[str, Any]:
    return _read_json(prod_root / "daily_manifests" / f"{run_id}.json") or {}


def _load_session_voice(prod_root: Path, trade_date: str) -> Optional[Dict[str, Any]]:
    return _read_json(prod_root / "daily_voices" / f"session_{trade_date}.json")


def _compose_narrative(session_voice: Dict[str, Any]) -> str:
    parts = [session_voice.get(k, "") for k in _SESSION_VOICE_KEYS if k.startswith("q")]
    return "\n\n".join(p for p in parts if p)


def build_autonomous_daily_edge_ui_view(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build the view the Edge Research Streamlit panel must show first.

    Default session is the current Asia/Ho_Chi_Minh calendar date (or an
    explicit trade_date). A prior SUCCESS is never silently substituted for a
    newer eligible date that is still WAITING_FOR_DATA or missing.
    """
    # Best-effort durable restore for Streamlit Cloud (no-op when backend absent).
    try:
        from modules.edge_research.production_observations_sync import (
            try_restore_production_observations_durable,
        )

        try_restore_production_observations_durable(data_dir=data_dir)
    except Exception:  # noqa: BLE001
        pass

    edge_root = resolve_data_dir(data_dir)
    canon = resolve_production_runs_root(edge_root)
    expected_date = str(trade_date)[:10] if trade_date else derive_vn_calendar_date(now)
    last_success = _latest_successful_run_meta(canon)
    meta = _authoritative_meta_for_date(canon, expected_date)

    if meta:
        session_date = expected_date
        disposition = str(meta.get("run_disposition") or WAITING_FOR_DATA)
        run_id = meta.get("run_id")
    elif is_vn_trading_session(expected_date):
        session_date = expected_date
        disposition = WAITING_FOR_DATA
        run_id = None
    else:
        session_date = expected_date
        disposition = SKIPPED_NON_TRADING_DAY
        run_id = None

    run_payload = _load_run_payload(canon, str(run_id)) if run_id else {}
    manifest = _load_manifest(canon, str(run_id)) if run_id else {}
    show_voice = disposition == "SUCCESS"
    session_voice = (
        _load_session_voice(canon, str(session_date)) if show_voice and session_date else None
    )

    discovery_count = manifest.get("discovery_count")
    if discovery_count is None and run_payload:
        discovery_count = len(run_payload.get("observations_born") or [])
    if discovery_count is None:
        discovery_count = 0

    session_questions: Dict[str, Any] = {}
    if isinstance(session_voice, dict):
        for key in _SESSION_VOICE_KEYS:
            if key in session_voice:
                session_questions[key] = session_voice.get(key)

    narrative = _compose_narrative(session_voice) if isinstance(session_voice, dict) else ""
    run_mode = (meta or {}).get("run_mode") or run_payload.get("run_mode")
    last_success_date = (last_success or {}).get("target_trade_date")

    return {
        "section": AUTONOMOUS_DAILY_SECTION,
        "canonical_root": str(canon),
        "edge_data_dir": str(edge_root),
        "canonical_root_name": Path(canon).name,
        "double_nested": Path(canon).name == "production_observations"
        and Path(canon).parent.name == "production_observations",
        "session_date": session_date,
        "expected_trade_date": expected_date,
        "run_id": run_id,
        "run_disposition": disposition,
        "run_mode": run_mode,
        "discovery_count": int(discovery_count or 0),
        "bot_spoke_today": bool(manifest.get("bot_spoke_today", bool(session_voice))),
        "silence_or_no_discovery": bool(
            manifest.get("silence_or_no_discovery", int(discovery_count or 0) == 0)
        ),
        "daily_market_voice_exists": bool(session_voice),
        "session_voice_observation_id": (
            (session_voice or {}).get("observation_id") if isinstance(session_voice, dict) else None
        ),
        "session_voice_questions": session_questions,
        "narrative_vi": narrative,
        "active_observations": [],
        "last_successful_research_date": last_success_date,
        "health": {
            "latest_successful_research_date": last_success_date,
            "expected_trade_date": expected_date,
            "latest_run_id": run_id,
            "latest_run_mode": run_mode,
            "latest_run_disposition": disposition,
        },
        "authority_badge": "RESEARCH ONLY",
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
    ]
    if view.get("run_disposition") == WAITING_FOR_DATA:
        lines.append(f"WAITING_FOR_DATA — {view.get('session_date')}")
    lines.extend(
        [
            f"Last successful session: {view.get('last_successful_research_date') or 'N/A'}",
            f"Run id: {view.get('run_id') or 'N/A'}",
            f"Run mode: {view.get('run_mode') or 'N/A'}",
            f"Discovery today: {view.get('discovery_count', 0)}",
            "DAILY MARKET VOICE",
        ]
    )
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

    disposition = view.get("run_disposition")
    if disposition == WAITING_FOR_DATA:
        st.warning(f"WAITING_FOR_DATA — {view.get('session_date')}")
        last_ok = view.get("last_successful_research_date")
        if last_ok and last_ok != view.get("session_date"):
            st.caption(f"Last successful session: `{last_ok}`")
    elif disposition == SKIPPED_NON_TRADING_DAY:
        st.info(f"SKIPPED_NON_TRADING_DAY — {view.get('session_date')}")

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
