"""Read-only Live Candidate V2 — Brain A operator panel.

Current-cycle Gate B GET only. Candidate != BUY. Does not nominate,
does not GET, does not read the production Elite watchlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

KIND_UNAVAILABLE = "UNAVAILABLE"
KIND_OK_EMPTY = "OK_EMPTY"
KIND_OK_ROWS = "OK_ROWS"
KIND_FAILURE = "FAILURE"

PANEL_TITLE = "Live Candidate V2 — Brain A"
SEMANTIC_CAPTION = "Candidate ≠ BUY · observation only · not Elite action · not NAV"
EMPTY_MESSAGE = "No Brain A candidate this session."
UNAVAILABLE_MESSAGE = "Live Candidate V2 unavailable this cycle."

STATUS_OK_EMPTY = "OK_EMPTY"
STATUS_OK_ROWS = "OK_ROWS"

def _sanitize(text: object) -> str:
    """Reuse Gate B sanitizer without importing github_bus at module load."""
    from modules.live_candidate_v2_camera.github_bus import sanitize_v2_github_message

    return sanitize_v2_github_message(text)


OPERATOR_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Symbol", "symbol"),
    ("Setup", "setup"),
    ("Source", "source"),
    ("Why", "nomination_reason"),
    ("Detail", "source_reason"),
    ("Waiting for", "observation_intent"),
    ("Watch ref", "observation_reference"),
    ("First seen", "candidate_first_seen_ts"),
    ("Frozen price", "price_at_first_seen"),
    ("Frozen EMA9", "ema9_at_first_seen"),
    ("Frozen breakout", "breakout_ref_at_first_seen"),
    ("Elite grade (metadata)", "elite_buy_grade"),
)


@dataclass(frozen=True)
class V2UiView:
    kind: str
    status: str = ""
    n_rows: int = 0
    session: str = ""
    market_permission: str = ""
    rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    error: str = ""


def unavailable_v2_ui() -> V2UiView:
    return V2UiView(kind=KIND_UNAVAILABLE, status=KIND_UNAVAILABLE)


def v2_ui_from_failure(*, status: str = "", error: str = "") -> V2UiView:
    raw_status = str(status or "TRANSPORT_ERROR")
    return V2UiView(
        kind=KIND_FAILURE,
        status=_sanitize(raw_status),
        error=_sanitize(error or raw_status),
        n_rows=0,
        rows=(),
    )


def v2_ui_from_get(fetched: Any) -> V2UiView:
    """Project THIS cycle's Gate B GET result. Never reads local/sidecar files."""
    ok = bool(getattr(fetched, "ok", False))
    status = str(getattr(fetched, "status", "") or "")
    document = getattr(fetched, "document", None)
    n_rows = int(getattr(fetched, "n_rows", 0) or 0)
    error = _sanitize(getattr(fetched, "error", "") or "")
    if not ok:
        return v2_ui_from_failure(status=status or "TRANSPORT_ERROR", error=error)

    session = ""
    permission = ""
    row_objs: tuple[Mapping[str, Any], ...] = ()
    if isinstance(document, dict):
        session = str(document.get("session") or "")
        permission = str(document.get("market_permission") or "")
        raw_rows = document.get("rows")
        if isinstance(raw_rows, list):
            row_objs = tuple(r for r in raw_rows if isinstance(r, Mapping))

    if status == STATUS_OK_EMPTY:
        return V2UiView(
            kind=KIND_OK_EMPTY,
            status=STATUS_OK_EMPTY,
            n_rows=0,
            session=session,
            market_permission=permission,
            rows=(),
        )
    if status == STATUS_OK_ROWS:
        return V2UiView(
            kind=KIND_OK_ROWS,
            status=STATUS_OK_ROWS,
            n_rows=n_rows if n_rows else len(row_objs),
            session=session,
            market_permission=permission,
            rows=row_objs,
        )
    return v2_ui_from_failure(status=status or "INVALID_DOCUMENT", error=error)


def _cell(rec: Mapping[str, Any], key: str) -> Any:
    if key == "source":
        return rec.get("nomination_source") or rec.get("source") or ""
    if key == "elite_buy_grade":
        raw = rec.get("elite_buy_grade")
        text = "" if raw is None else str(raw).strip()
        return "—" if not text else text
    return rec.get(key, "")


def project_operator_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Display labels only. Does not treat freeze ledger as current rows."""
    projected: list[dict[str, Any]] = []
    for rec in rows:
        if not isinstance(rec, Mapping):
            continue
        projected.append({label: _cell(rec, key) for label, key in OPERATOR_COLUMNS})
    return projected


def render_live_candidate_v2_panel(view: V2UiView | None, *, st_module: Any = None) -> None:
    """Render the durable Brain A panel. Never fetches. Never writes."""
    st = st_module
    if st is None:
        import streamlit as st
    panel = view if view is not None else unavailable_v2_ui()
    st.markdown(f"## {PANEL_TITLE}")
    st.caption(SEMANTIC_CAPTION)
    if panel.kind == KIND_OK_EMPTY:
        if panel.session or panel.market_permission:
            st.caption(
                f"session={panel.session} · market_permission={panel.market_permission} · rows=0"
            )
        st.markdown(EMPTY_MESSAGE)
        return
    if panel.kind == KIND_OK_ROWS:
        st.caption(
            f"session={panel.session} · market_permission={panel.market_permission} · rows={panel.n_rows}"
        )
        table = project_operator_rows(panel.rows)
        if table:
            st.dataframe(table, use_container_width=True, hide_index=True)
        return
    if panel.kind == KIND_FAILURE:
        st.caption(
            f"Live Candidate V2 status={_sanitize(panel.status)}"
        )
        return
    st.markdown(UNAVAILABLE_MESSAGE)
