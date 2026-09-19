"""SHADOW / RESEARCH visibility for the V2 Action Layer.

Not a production BUY interface. Does not import the operator V2 table.
Does not expose source_action / Elite BUY metadata as the action state.
Fail-closed when the local research artifact is absent (Cloud has no VPS 5m).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.live_candidate_v2_action.artifact import V2ActionStore, default_action_dir
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    SHADOW_BUY_READY_LABEL,
    SHADOW_CAPTION,
    STATE_BUY_READY,
)

PANEL_TITLE = "V2 Action Layer — SHADOW / RESEARCH"
UNAVAILABLE_MESSAGE = "SHADOW Action Layer: no local observation this cycle."
EMPTY_MESSAGE = "SHADOW Action Layer: no V2 nominations observed this session."

SHADOW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Symbol", "symbol"),
    ("Setup", "setup"),
    ("Shadow action", "shadow_display"),
    ("Last legal 5m", "last_legal_bar_ts"),
    ("Frozen ref", "frozen_ref_display"),
    ("Close vs ref", "close_vs_ref"),
    ("Reason", "action_reason"),
)


def load_shadow_state(path: Path | None = None) -> dict[str, Any] | None:
    store = V2ActionStore(path) if path is not None else V2ActionStore(default_action_dir())
    return store.read_state()


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


def render_v2_shadow_action_panel(
    document: Mapping[str, Any] | None = None,
    *,
    st_module: Any = None,
    artifact_dir: Path | None = None,
) -> None:
    """Minimum SHADOW visibility. Never a green production BUY table."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore

    doc = document if document is not None else load_shadow_state(artifact_dir)
    st.markdown(f"### {PANEL_TITLE}")
    st.caption(SHADOW_CAPTION)
    st.caption(
        f"permissions: candidate_is_buy={CANDIDATE_IS_BUY} · "
        f"pxv_implies_buy={PXV_IMPLIES_BUY} · alert_eligible={ALERT_ELIGIBLE}"
    )
    if doc is None:
        st.caption(UNAVAILABLE_MESSAGE)
        return
    if doc.get("candidate_is_buy") is True or doc.get("alert_eligible") is True or doc.get("pxv_implies_buy") is True:
        st.caption(UNAVAILABLE_MESSAGE)
        return
    rows = doc.get("rows") if isinstance(doc, Mapping) else None
    if not isinstance(rows, list) or not rows:
        session = str(doc.get("session") or "")
        if session:
            st.caption(f"session={session} · rows=0")
        st.caption(EMPTY_MESSAGE)
        return
    session = str(doc.get("session") or "")
    st.caption(f"session={session} · rows={len(rows)} · SHADOW only")
    table = project_shadow_rows(rows)
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)
