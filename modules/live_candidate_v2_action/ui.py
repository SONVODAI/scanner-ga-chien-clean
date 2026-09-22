"""SHADOW / RESEARCH visibility for the V2 Action Layer.

Not a production BUY interface. Does not import the operator V2 table.
Does not expose source_action / Elite BUY metadata as the action state.
Cloud reads the VPS-computed artifact via the existing live-shadow GET bus.
Never recomputes Camera evidence. Fail-closed on absent/stale/BUY flags.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_pxv_ui.read import resolve_ui_source
from modules.live_candidate_v2_action.artifact import V2ActionStore, default_action_dir
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    SHADOW_BUY_READY_LABEL,
    SHADOW_CAPTION,
    STATE_BUY_READY,
    WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M,
)
from modules.live_shadow_transport.artifact_get import (
    EvidenceTransportError,
    LiveShadowNotFound,
    get_v2_action_state_text,
)
from modules.live_shadow_transport.freshness import classify_freshness

PANEL_TITLE = "V2 Action Layer — SHADOW / RESEARCH"
UNAVAILABLE_MESSAGE = "SHADOW Action Layer: no VPS observation this cycle."
LOCAL_UNAVAILABLE_MESSAGE = "SHADOW Action Layer: no local observation this cycle."
EMPTY_MESSAGE = "SHADOW Action Layer: no V2 nominations observed this session."
STALE_MESSAGE = "SHADOW Action Layer: VPS state rejected (stale or wrong session)."
TRANSPORT_MESSAGE = "SHADOW Action Layer: VPS state transport failed (fail closed)."
PERMISSIONS_MESSAGE = "SHADOW Action Layer: production BUY flags present — rejected."
VALIDATION_TITLE = "SHADOW BUY_READY — FOR VALIDATION ONLY"
VALIDATION_NOTE = (
    "Historical shadow evidence only. Not the current action state and not a production BUY. "
    "candidate_is_buy=false · pxv_implies_buy=false · alert_eligible=false"
)

REASON_OK = "OK"
REASON_ABSENT = "ABSENT"
REASON_STALE_SESSION = "STALE_SESSION"
REASON_STALE_OBSERVED_AT = "STALE_OBSERVED_AT"
REASON_TRANSPORT = "TRANSPORT"
REASON_PERMISSIONS = "PERMISSIONS"
REASON_INVALID = "INVALID"
REASON_WAITING = WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M
STALE_REASONS = frozenset({REASON_STALE_SESSION, REASON_STALE_OBSERVED_AT})

SHADOW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Symbol", "symbol"),
    ("Setup", "setup"),
    ("Shadow action", "shadow_display"),
    ("Last legal 5m", "last_legal_bar_ts"),
    ("Frozen ref", "frozen_ref_display"),
    ("Close vs ref", "close_vs_ref"),
    ("Reason", "action_reason"),
)

VALIDATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Symbol", "symbol"),
    ("Source", "source"),
    ("Setup", "setup"),
    ("Trigger time", "trigger_time"),
    ("Trigger price", "trigger_price"),
    ("Frozen ref", "frozen_ref_display"),
    ("Volume/P×V evidence", "pxv_evidence"),
    ("Market permission", "market_permission"),
    ("Reason", "action_reason"),
)


def load_shadow_state(path: Path | None = None) -> dict[str, Any] | None:
    store = V2ActionStore(path) if path is not None else V2ActionStore(default_action_dir())
    return store.read_state()


def accept_shadow_state_document(
    doc: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    session: date | str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Current-session + freshness + SHADOW permissions. Never invents rows."""
    if not isinstance(doc, Mapping):
        return None, REASON_ABSENT
    if doc.get("candidate_is_buy") is True or doc.get("alert_eligible") is True or doc.get("pxv_implies_buy") is True:
        return None, REASON_PERMISSIONS
    now_l = as_vn(now or datetime.now())
    want = session.isoformat() if isinstance(session, date) else str(session or now_l.date().isoformat())
    got = str(doc.get("session") or "").strip()
    if got != want:
        return None, REASON_STALE_SESSION
    fresh = classify_freshness(doc.get("observed_at"), now_l)
    if fresh.get("is_stale"):
        return None, REASON_STALE_OBSERVED_AT
    return dict(doc), REASON_OK


def shadow_waiting_for_eligible_bar(doc: Mapping[str, Any] | None) -> bool:
    if not isinstance(doc, Mapping):
        return False
    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        return True
    return all(int(r.get("n_legal_bars") or 0) <= 0 for r in rows if isinstance(r, Mapping))


def load_accepted_shadow_state(
    path: Path | None = None,
    *,
    now: datetime | None = None,
    source_mode: str | None = None,
    fetcher: Callable[[], str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Remote-first when EDGE_RESEARCH_DURABLE_URL is set. No local fallback."""
    mode = resolve_ui_source(source_mode)
    if mode == "remote":
        try:
            text = fetcher() if fetcher is not None else get_v2_action_state_text()
            data = json.loads(text)
        except LiveShadowNotFound:
            return None, REASON_ABSENT
        except (EvidenceTransportError, json.JSONDecodeError, TypeError):
            return None, REASON_TRANSPORT
        if not isinstance(data, dict):
            return None, REASON_INVALID
        return accept_shadow_state_document(data, now=now)
    doc = load_shadow_state(path)
    return accept_shadow_state_document(doc, now=now)


def _shadow_display(rec: Mapping[str, Any]) -> str:
    state = str(rec.get("shadow_action") or rec.get("action_state") or "")
    if state == STATE_BUY_READY:
        return SHADOW_BUY_READY_LABEL
    label = str(rec.get("shadow_label") or "")
    if label:
        return label
    return f"SHADOW {state}" if state else "SHADOW —"


def _ref_display(rec: Mapping[str, Any]) -> str:
    kind = str(rec.get("frozen_ref_kind") or "")
    value = rec.get("frozen_ref_value")
    if not kind:
        return "—"
    if value is None:
        return kind
    return f"{kind}={value}"


def project_shadow_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for rec in rows:
        if not isinstance(rec, Mapping):
            continue
        view = dict(rec)
        view["shadow_display"] = _shadow_display(rec)
        view["frozen_ref_display"] = _ref_display(rec)
        projected.append({label: view.get(key, "") for label, key in SHADOW_COLUMNS})
    return projected


def _row_permissions_closed(rec: Mapping[str, Any]) -> bool:
    return (
        rec.get("candidate_is_buy") is not True
        and rec.get("pxv_implies_buy") is not True
        and rec.get("alert_eligible") is not True
    )


def _is_buy_ready_row(rec: Mapping[str, Any]) -> bool:
    state = str(rec.get("shadow_action") or rec.get("action_state") or "")
    return state == STATE_BUY_READY and _row_permissions_closed(rec)


def historical_buy_ready_rows(doc: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """BUY_READY rows retained for validation. Not a current action."""
    if not isinstance(doc, Mapping):
        return []
    if doc.get("candidate_is_buy") is True or doc.get("alert_eligible") is True or doc.get("pxv_implies_buy") is True:
        return []
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return []
    return [rec for rec in rows if isinstance(rec, Mapping) and _is_buy_ready_row(rec)]


def _pxv_evidence(rec: Mapping[str, Any]) -> str:
    published = str(rec.get("published_evidence") or "")
    volume = rec.get("volume_expansion_state")
    pxv = rec.get("price_volume_state")
    parts = []
    if published:
        parts.append(f"published={published}")
    if volume not in (None, ""):
        parts.append(f"volume={volume}")
    if pxv not in (None, ""):
        parts.append(f"pxv={pxv}")
    return " · ".join(parts)


def project_validation_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for rec in rows:
        if not _is_buy_ready_row(rec):
            continue
        view = dict(rec)
        view["frozen_ref_display"] = _ref_display(rec)
        view["trigger_time"] = rec.get("trigger_bar_ts") or rec.get("last_legal_bar_ts") or ""
        view["pxv_evidence"] = _pxv_evidence(rec)
        projected.append({label: view.get(key, "") for label, key in VALIDATION_COLUMNS})
    return projected


def _load_raw_shadow_state(
    path: Path | None,
    *,
    source_mode: str | None,
    fetcher: Callable[[], str] | None,
) -> tuple[dict[str, Any] | None, str]:
    """Fetch the document without applying freshness. Fail closed on transport."""
    mode = resolve_ui_source(source_mode)
    if mode == "remote":
        try:
            text = fetcher() if fetcher is not None else get_v2_action_state_text()
            data = json.loads(text)
        except LiveShadowNotFound:
            return None, REASON_ABSENT
        except (EvidenceTransportError, json.JSONDecodeError, TypeError):
            return None, REASON_TRANSPORT
        if not isinstance(data, dict):
            return None, REASON_INVALID
        return data, REASON_OK
    doc = load_shadow_state(path)
    if doc is None:
        return None, REASON_ABSENT
    return doc, REASON_OK


def _render_historical_buy_ready(st: Any, raw: Mapping[str, Any] | None) -> None:
    """Stale or rolled-over snapshot: BUY_READY evidence only, never as current state."""
    ready = historical_buy_ready_rows(raw)
    if not ready:
        return
    session = str((raw or {}).get("session") or "")
    observed = str((raw or {}).get("observed_at") or "")
    st.markdown(f"#### {VALIDATION_TITLE}")
    st.caption(VALIDATION_NOTE)
    if session or observed:
        st.caption(f"snapshot session={session or '—'} · observed_at={observed or '—'} · not current")
    table = project_validation_rows(ready)
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)


def _reason_caption(reason: str, *, local: bool) -> str:
    if reason == REASON_ABSENT:
        return LOCAL_UNAVAILABLE_MESSAGE if local else UNAVAILABLE_MESSAGE
    if reason in {REASON_STALE_SESSION, REASON_STALE_OBSERVED_AT}:
        return STALE_MESSAGE
    if reason == REASON_TRANSPORT:
        return TRANSPORT_MESSAGE
    if reason == REASON_PERMISSIONS:
        return PERMISSIONS_MESSAGE
    return UNAVAILABLE_MESSAGE


def render_v2_shadow_action_panel(
    document: Mapping[str, Any] | None = None,
    *,
    st_module: Any = None,
    artifact_dir: Path | None = None,
    now: datetime | None = None,
    source_mode: str | None = None,
    fetcher: Callable[[], str] | None = None,
) -> None:
    """Minimum SHADOW visibility. Never a green production BUY table."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore

    reason = REASON_OK
    resolved_mode = source_mode
    if resolved_mode is None and artifact_dir is not None:
        resolved_mode = "local"
    raw: dict[str, Any] | None = None
    if document is not None:
        doc: dict[str, Any] | None = dict(document) if isinstance(document, Mapping) else None
        if doc is None:
            reason = REASON_ABSENT
        elif doc.get("candidate_is_buy") is True or doc.get("alert_eligible") is True or doc.get("pxv_implies_buy") is True:
            doc = None
            reason = REASON_PERMISSIONS
    else:
        raw, reason = _load_raw_shadow_state(
            artifact_dir,
            source_mode=resolved_mode,
            fetcher=fetcher,
        )
        if raw is None:
            doc = None
        elif raw.get("candidate_is_buy") is True or raw.get("alert_eligible") is True or raw.get("pxv_implies_buy") is True:
            doc = None
            raw = None
            reason = REASON_PERMISSIONS
        else:
            doc, reason = accept_shadow_state_document(raw, now=now)

    st.markdown(f"### {PANEL_TITLE}")
    st.caption(SHADOW_CAPTION)
    st.caption(
        f"permissions: candidate_is_buy={CANDIDATE_IS_BUY} · "
        f"pxv_implies_buy={PXV_IMPLIES_BUY} · alert_eligible={ALERT_ELIGIBLE}"
    )
    if doc is None:
        local = resolve_ui_source(resolved_mode) == "local"
        st.caption(_reason_caption(reason, local=local))
        if reason in STALE_REASONS:
            _render_historical_buy_ready(st, raw)
        return
    rows = doc.get("rows") if isinstance(doc, Mapping) else None
    session = str(doc.get("session") or "")
    if not isinstance(rows, list) or not rows:
        if session:
            st.caption(f"session={session} · rows=0")
        st.caption(EMPTY_MESSAGE)
        st.caption(WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M)
        return
    st.caption(f"session={session} · rows={len(rows)} · SHADOW only")
    if shadow_waiting_for_eligible_bar(doc):
        st.caption(WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M)
    table = project_shadow_rows(rows)
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)
