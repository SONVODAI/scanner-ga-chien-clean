"""Read-only V2 Research Ledger table. It does not query writers or scanners."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.v2_research_ledger.board_view import apply_filters, project_table
from research.v2_research_ledger.delivery_view import (
    DELIVERY_UNAVAILABLE,
    SOURCE_STALE,
    DeliveryDiagnostics,
    DeliveryView,
    load_delivery,
)
from research.v2_research_ledger.remote_delivery import fetch_research_trio, resolve_remote_config
from research.v2_research_ledger.freshness import (
    STALE_DATA,
    divergence,
    evidence_clock,
    sidecar_clock,
    status_for,
    sweet_clock,
)

PANEL_TITLE = "V2 RESEARCH LEDGER — T+1 TO T+20"
PANEL_CAPTION = (
    "Research record only. execution_enabled is not used. "
    "NOT_YET_OBSERVED is a pending horizon. MISSING_PRICE means no unadjusted "
    "daily bar was supplied. No order is created."
)
NOT_CONFIGURED = "NOT_CONFIGURED"
NO_DATA = "NO_DATA"


def format_delivery_diagnostics(diagnostics: DeliveryDiagnostics | None) -> str:
    """One read-only line. Missing fields stay unknown. No price is invented."""
    if diagnostics is None:
        return (
            "generation=unknown as_of=unknown published_at=unknown "
            "rows=0 source_health=unknown."
        )
    health = ", ".join(f"{name}={status}" for name, status in diagnostics.source_health) or "unknown"
    return (
        f"generation={diagnostics.generation_id or 'unknown'} "
        f"as_of={diagnostics.as_of or 'unknown'} "
        f"published_at={diagnostics.published_at or 'unknown'} "
        f"rows={diagnostics.rows} "
        f"source_health={health}."
    )


_NOMINATION_SOURCES = frozenset({"brain_a_scan_setup", "market_aware_sweetspot"})


def format_row_composition(rows: list[Any]) -> str:
    """Separate stored nominations from unattributed action rows. Counts only."""
    attributed = 0
    unattributed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        cohort = str(row.get("cohort") or "")
        source = str(row.get("source") or "")
        if cohort == "action_unattributed" or source == "unattributed":
            unattributed += 1
        elif cohort == "nomination" or source in _NOMINATION_SOURCES:
            attributed += 1
    return (
        f"research_rows={len(rows)} "
        f"attributed_nominations={attributed} "
        f"unattributed_action_only={unattributed}."
    )
_REPO = Path(__file__).resolve().parents[2]
DEFAULT_BOARD = _REPO / "research" / "v2_research_ledger" / "view" / "board.json"
DEFAULT_SIDECAR = _REPO / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
DEFAULT_EVIDENCE = _REPO / "research" / "v2_research_ledger" / "evidence"
DEFAULT_SWEET = _REPO / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"


def load_board(path: Path) -> tuple[str, dict[str, Any] | None]:
    """Return NOT_CONFIGURED, NO_DATA, or OK. Missing files are not empty success."""
    if not path.is_file():
        return NOT_CONFIGURED, None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return NO_DATA, None
    if not isinstance(loaded, dict):
        return NO_DATA, None
    rows = loaded.get("rows")
    if not isinstance(rows, list) or not rows:
        return NO_DATA, loaded
    return "OK", loaded


def render_v2_research_ledger_panel(
    st_module: Any = None,
    *,
    board_path: Path | None = None,
    sidecar_path: Path | None = None,
    evidence_dir: Path | None = None,
    sweet_csv: Path | None = None,
    check_sources: bool | None = None,
    delivery_dir: Path | None = None,
    remote: bool = False,
    cache_path: Path | None = None,
    remote_view: DeliveryView | None = None,
) -> None:
    """Expandable table inside RESEARCH / SHADOW. Reads research artifacts only."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore
    delivered = None
    cache_reason = None
    if remote and delivery_dir is None and board_path is None:
        if remote_view is None:
            url, token = resolve_remote_config()
            remote_view = fetch_research_trio(url, token)
        if remote_view.state == DELIVERY_UNAVAILABLE or remote_view.board is None:
            cache_reason = remote_view.reason
            path = Path(cache_path) if cache_path is not None else DEFAULT_BOARD
            status, board = load_board(path)
        else:
            delivered = remote_view
            status, board = "OK", remote_view.board
            path = Path("remote-research-ledger")
    elif delivery_dir is not None:
        delivered = load_delivery(Path(delivery_dir))
        if delivered.state == DELIVERY_UNAVAILABLE:
            with st.expander(PANEL_TITLE, expanded=False):
                st.caption(PANEL_CAPTION)
                st.warning(f"{DELIVERY_UNAVAILABLE}: {delivered.reason}.")
            return
        status, board = "OK", delivered.board
        path = Path(delivery_dir) / "board.json"
    else:
        path = Path(board_path) if board_path is not None else DEFAULT_BOARD
        status, board = load_board(path)
    with st.expander(PANEL_TITLE, expanded=False):
        st.caption(PANEL_CAPTION)
        if cache_reason:
            st.warning(f"{DELIVERY_UNAVAILABLE}: {cache_reason}.")
        if delivered is not None and isinstance(board, dict):
            clocks = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
            st.caption(
                f"delivery={delivered.state}. "
                f"latest T0 (provenance)={clocks.get('latest_t0') or 'unknown'}. "
                f"latest publication session={clocks.get('latest_publication_session') or 'unknown'}. "
                f"latest action session={clocks.get('latest_action_session') or 'unknown'}. "
                f"latest action bar={clocks.get('latest_action_bar') or 'unknown'}."
            )
            st.caption(format_delivery_diagnostics(delivered.diagnostics))
        if status == NOT_CONFIGURED:
            if cache_reason:
                return
            st.warning(f"{NOT_CONFIGURED}: research board artifact is not present at {path}.")
            return
        if status == NO_DATA or board is None:
            st.warning(f"{NO_DATA}: the research board has no candidate rows.")
            return
        rows = list(board.get("rows") or [])
        dates = sorted({str(row.get("t0_date") or "") for row in rows if row.get("t0_date")}, reverse=True)
        sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
        if cache_reason:
            st.caption(
                "cached local board "
                f"source_updated_at={board.get('source_updated_at') or 'unknown'}. "
                "cache_status=STALE. This is not a verified delivery."
            )
        st.caption(
            f"Last data update: {board.get('source_updated_at') or 'unknown'}. "
            f"Cutoff as_of={board.get('as_of') or 'unknown'}. "
            f"Price book: {board.get('price_book') or 'absent'}."
        )
        fresh = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
        coverage = board.get("coverage") if isinstance(board.get("coverage"), dict) else {}
        source_counts = fresh.get("source_coverage") or coverage.get("by_source") or {}
        observe = False if delivered is not None or cache_reason else (bool(fresh) if check_sources is None else check_sources)
        reasons = list(fresh.get("reasons") or [])
        if observe:
            reasons.extend(
                divergence(
                    fresh,
                    sidecar=sidecar_clock(sidecar_path or DEFAULT_SIDECAR),
                    evidence=evidence_clock(evidence_dir or DEFAULT_EVIDENCE),
                    sweet=sweet_clock(sweet_csv or DEFAULT_SWEET),
                )
            )
        if delivered is not None:
            freshness_state = delivered.state
        elif cache_reason:
            freshness_state = "STALE"
        else:
            freshness_state = status_for(fresh, reasons)
        st.caption(
            "artifact_as_of="
            f"{fresh.get('artifact_as_of') or board.get('as_of') or 'unknown'}. "
            f"latest T0 (provenance)={fresh.get('latest_t0') or 'unknown'}. "
            f"latest publication session={fresh.get('latest_publication_session') or 'unknown'}. "
            f"latest first-seen date={fresh.get('latest_first_seen_date') or 'unknown'}. "
            f"latest action session={fresh.get('latest_action_session') or 'unknown'}. "
            f"latest action bar={fresh.get('latest_action_bar') or 'unknown'}. "
            f"freshness={freshness_state}."
        )
        st.caption(format_row_composition(rows))
        if source_counts:
            rendered = ", ".join(f"{name}={count}" for name, count in sorted(source_counts.items()))
            st.caption(f"Source coverage: {rendered}.")
        health = fresh.get("source_health") if isinstance(fresh.get("source_health"), dict) else {}
        if health:
            rendered_health = ", ".join(
                f"{name}={item.get('status')}" for name, item in sorted(health.items()) if isinstance(item, dict)
            )
            st.caption(f"Source health: {rendered_health}.")
        if delivered is not None and delivered.state == SOURCE_STALE:
            detail = ", ".join(reasons) if reasons else delivered.state
            st.warning(f"{SOURCE_STALE}: source evidence is ahead of this delivery ({detail}).")
        elif delivered is None and freshness_state == STALE_DATA:
            detail = ", ".join(reasons) if reasons else "stored freshness status"
            st.warning(f"{STALE_DATA}: the research board is behind available source evidence ({detail}).")
        chosen_date = st.selectbox("T0 date", options=[*dates, "all"], index=0 if dates else 0)
        chosen_source = st.selectbox("source", options=["all", *sources], index=0)
        chosen_state = st.selectbox(
            "state",
            options=["all", "BUY_READY", "WAIT", "WEAKENED", "NO_OBSERVATION", "REJECTED"],
            index=0,
        )
        chosen_visibility = st.selectbox("active/history", options=["all", "active", "history"], index=0)
        symbol = st.text_input("symbol", value="")
        selected = apply_filters(
            rows,
            t0_date=str(chosen_date),
            source=str(chosen_source),
            state=str(chosen_state),
            visibility=str(chosen_visibility),
            symbol=str(symbol or ""),
        )
        if not selected:
            st.warning(f"{NO_DATA}: no stored candidates match these filters.")
            return
        st.dataframe(project_table(selected), use_container_width=True, hide_index=True)
        history = []
        for row in selected:
            for item in row.get("action_history") or []:
                history.append(
                    {
                        "Symbol": row.get("symbol") or "",
                        "T0 date": row.get("t0_date") or "",
                        "bar_ts": item.get("bar_ts") or "",
                        "action_state": item.get("action_state") or "",
                        "source_stream": item.get("source_stream") or "",
                    }
                )
        if history:
            st.caption("Action history for the rows above. WAIT and later states stay listed.")
            st.dataframe(history, use_container_width=True, hide_index=True)
