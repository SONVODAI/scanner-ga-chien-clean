"""Read-only V2 Research Ledger table. It does not query writers or scanners."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.v2_research_ledger.board_view import apply_filters, project_table
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.forward_outcomes import LEDGER_FILES
from research.v2_research_ledger.panel_board import HORIZON_STATUS, load_row_panel
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
    "NOT_YET_OBSERVED is a pending horizon. "
    "T0_REFERENCE_MISSING and TARGET_MISSING are absent reference closes, not zero returns. "
    "APPROX_AVAILABLE is the only displayed percentage. "
    "brain_unlinked rows have no verified nomination link. "
    "No blended win rate is shown. No order is created."
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
DEFAULT_ROW_STORE = _REPO / "research" / "v2_research_ledger" / "durable"
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


def _exact_count(value: object, actual: int) -> bool:
    return type(value) is int and value == actual


def _validated_durable_board(store_path: Path) -> tuple[str, dict[str, Any] | None, str]:
    """Return OK, MISSING, or INVALID. Do not replace a failed store with another board."""
    root = Path(store_path)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return "MISSING", None, "manifest is not present"
    if not manifest_path.is_file():
        return "INVALID", None, "manifest is not a file"
    try:
        store = DurableRowStore(root)
        manifest = store.read_manifest()
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return "INVALID", None, "store is unreadable"
    if manifest is None:
        return "INVALID", None, "manifest schema is not v2_research_row_store_manifest.v1"
    if not _exact_count(manifest.get("identity_count"), len(store.identities)):
        return "INVALID", None, "identity_count does not match identities.jsonl"
    if not _exact_count(manifest.get("link_count"), len(store.links)):
        return "INVALID", None, "link_count does not match links.jsonl"
    if len(store.identities) > 0 and not (root / "identities.jsonl").is_file():
        return "INVALID", None, "identities.jsonl is not present"
    board = load_row_panel(store)
    if not isinstance(board, dict) or not isinstance(board.get("rows"), list):
        return "INVALID", None, "panel projection is missing"
    if len(board["rows"]) != len(store.identities):
        return "INVALID", None, "panel row count does not match identity_count"
    return "OK", board, ""


class _StoreNotOk(Exception):
    """A durable store that must not be cached as a successful board."""

    def __init__(self, state: str, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason


class _FingerprintRace(Exception):
    """The sealed bytes changed between the cache key and the read."""


def _shown_clock(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "missing"


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return "absent"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generation_fingerprints(index_path: Path, outcomes_root: Path) -> tuple[str, ...]:
    """Hash each generation named by the index. A path outside outcomes is refused."""
    if not index_path.is_file():
        return ()
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ("index-unreadable",)
    if not isinstance(loaded, dict):
        return ("index-invalid",)
    root = outcomes_root.resolve()
    found: list[str] = []
    for entry in loaded.get("generations") or []:
        if not isinstance(entry, dict):
            found.append("entry-invalid")
            continue
        relative = str(entry.get("path") or "")
        candidate = (outcomes_root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            found.append("path-escaped")
            continue
        found.append(relative + ":" + _sha256_file(candidate))
    return tuple(found)


def sealed_fingerprint(store_path: Path) -> tuple[str, ...]:
    """Content key for the sealed ledger, the outcomes index, and its generation."""
    root = Path(store_path)
    parts = [name + ":" + _sha256_file(root / name) for name in LEDGER_FILES]
    outcomes = root.parent / "outcomes"
    index = outcomes / "index.json"
    parts.append("index.json:" + _sha256_file(index))
    parts.extend(_generation_fingerprints(index, outcomes))
    return tuple(parts)


def _load_validated_for_fingerprint(
    path_text: str,
    fingerprint: tuple[str, ...],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate one fingerprint. A failure or a changed file is not a success."""
    store_path = Path(path_text)
    actual = sealed_fingerprint(store_path)
    if actual != tuple(fingerprint):
        raise _FingerprintRace(path_text)
    state, board, reason = _validated_durable_board(store_path)
    if state != "OK" or not isinstance(board, dict):
        raise _StoreNotOk(state, reason or "store is not usable")
    confirmed = sealed_fingerprint(store_path)
    if confirmed != actual:
        raise _FingerprintRace(path_text)
    return board, confirmed


_CACHED_OK_BOARD = None


def _streamlit_cached_loader(st: Any):
    """Bind the success cache once to the real Streamlit module. Fakes stay uncached."""
    global _CACHED_OK_BOARD
    if getattr(st, "__name__", "") != "streamlit" or not callable(getattr(st, "cache_data", None)):
        return None
    if _CACHED_OK_BOARD is None:
        _CACHED_OK_BOARD = st.cache_data(show_spinner=False)(_load_validated_for_fingerprint)
    return _CACHED_OK_BOARD


def _remember_validated_board(st: Any, store_path: Path) -> tuple[str, dict[str, Any] | None, str]:
    """Return the validated board. The same sealed bytes are not validated twice."""
    fingerprint = sealed_fingerprint(store_path)
    loader = _streamlit_cached_loader(st)
    if loader is None:
        state, board, reason = _validated_durable_board(store_path)
        return state, board, reason
    try:
        board, confirmed = loader(str(store_path), fingerprint)
    except _StoreNotOk as exc:
        return exc.state, None, exc.reason
    except _FingerprintRace:
        return "INVALID", None, "sealed files changed while they were read"
    if tuple(confirmed) != tuple(fingerprint):
        return "INVALID", None, "sealed fingerprint changed"
    return "OK", board, ""


def _isolate_panel(st: Any, draw: Any) -> None:
    """Rerun only the ledger body when its widgets change. Otherwise draw inline."""
    fragment = getattr(st, "fragment", None)
    if not callable(fragment):
        draw()
        return
    fragment(draw)()


def _show_historical_remote(st: Any, view: DeliveryView | None, *, unavailable_reason: str | None) -> None:
    """Show a remote trio separately. Its rows are not the durable store population."""
    if view is None or not isinstance(view.board, dict):
        if unavailable_reason:
            st.caption(f"historical_remote_delivery=UNAVAILABLE reason={unavailable_reason}.")
        return
    rows = [row for row in (view.board.get("rows") or []) if isinstance(row, dict)]
    fresh = view.board.get("freshness") if isinstance(view.board.get("freshness"), dict) else {}
    latest = fresh.get("latest_t0") or "unknown"
    st.caption(
        "historical_remote_delivery "
        f"state={view.state} "
        f"historical_rows={len(rows)} "
        f"latest T0 (provenance)={latest}. "
        "This is not the durable store population."
    )
    if view.state == SOURCE_STALE:
        st.warning(f"{SOURCE_STALE}: historical remote delivery is stale.")
    if rows:
        st.dataframe(project_table(rows), use_container_width=True, hide_index=True)


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
    row_store: Path | None = None,
) -> None:
    """Expandable table inside RESEARCH / SHADOW. Reads research artifacts only."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore
    historical_view = None
    historical_unavailable = None
    # The remote trio is a full-app read. A fragment rerun does not reach this call.
    if remote and delivery_dir is None and board_path is None:
        if remote_view is None:
            url, token = resolve_remote_config()
            remote_view = fetch_research_trio(url, token)
        if remote_view.state == DELIVERY_UNAVAILABLE or remote_view.board is None:
            historical_unavailable = remote_view.reason or "unavailable"
        else:
            historical_view = remote_view

    def _draw() -> None:
        delivered = None
        cache_reason = None
        from_row_store = False
        if remote and delivery_dir is None and board_path is None:
            store_path = Path(row_store) if row_store is not None else DEFAULT_ROW_STORE
            store_state, board, store_reason = _remember_validated_board(st, store_path)
            if store_state != "OK":
                label = "DURABLE_STORE_MISSING" if store_state == "MISSING" else "DURABLE_STORE_INVALID"
                with st.expander(PANEL_TITLE, expanded=False):
                    st.caption(PANEL_CAPTION)
                    st.warning(f"{label}: {store_reason}.")
                    if store_state == "MISSING":
                        st.warning("ROW_STORE_UNAVAILABLE: the durable research row store is not present.")
                    st.warning("Historical remote data is not the current durable store.")
                    if historical_unavailable:
                        st.warning(f"{DELIVERY_UNAVAILABLE}: {historical_unavailable}.")
                    _show_historical_remote(st, historical_view, unavailable_reason=historical_unavailable)
                return
            from_row_store = True
            status, path = "OK", store_path
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
            fresh = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
            coverage = board.get("coverage") if isinstance(board.get("coverage"), dict) else {}
            if from_row_store:
                forward = board.get("forward_outcomes") if isinstance(board.get("forward_outcomes"), dict) else {}
                horizon_note = HORIZON_STATUS
                if forward.get("status") == "attached":
                    horizon_note = f"attached as_of={forward.get('as_of') or 'unknown'}"
                st.caption(
                    "durable_row_store "
                    f"identities={coverage.get('rows')} "
                    f"sidecar_identities={coverage.get('sidecar_identities')} "
                    f"deduped_research_observations={coverage.get('deduped_research_observations')} "
                    f"historical_row_panel={board.get('historical_row_panel')} "
                    f"row_horizons={horizon_note}."
                )
                st.caption("Sealed T0 is shown from the store. A newer source file is not substituted.")
            elif cache_reason:
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
            elif from_row_store:
                recorded = str(fresh.get("status") or "")
                matched = fresh.get("fingerprint_matches") is True
                if recorded == "VERIFIED" and matched:
                    freshness_state = "VERIFIED"
                elif recorded in {"LATE", "MISSING"} and matched:
                    freshness_state = recorded
                else:
                    freshness_state = "UNVERIFIED"
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
            if from_row_store:
                st.caption(
                    "latest sealed T0="
                    f"{_shown_clock(fresh.get('latest_sealed_t0'))}. "
                    "latest measured T+ session="
                    f"{_shown_clock(fresh.get('latest_measured_session'))}. "
                    "artifact generation time="
                    f"{_shown_clock(fresh.get('artifact_generated_at'))}. "
                    "source update time="
                    f"{_shown_clock(fresh.get('source_updated_at'))}."
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
            elif from_row_store:
                pass
            elif delivered is None and freshness_state == STALE_DATA:
                detail = ", ".join(reasons) if reasons else "stored freshness status"
                st.warning(f"{STALE_DATA}: the research board is behind available source evidence ({detail}).")
            chosen_date = st.selectbox("T0 date", options=[*dates, "all"], index=0 if dates else 0)
            chosen_source = st.selectbox("source", options=["all", *sources], index=0)
            chosen_population = st.selectbox(
                "population",
                options=["all", "brain_linked", "brain_unlinked", "sweetspot", "sweetspot_blank"],
                index=0,
            )
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
                population=str(chosen_population),
            )
            if not selected:
                st.warning(f"{NO_DATA}: no stored candidates match these filters.")
                if from_row_store:
                    _show_historical_remote(st, historical_view, unavailable_reason=historical_unavailable)
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
            if from_row_store:
                _show_historical_remote(st, historical_view, unavailable_reason=historical_unavailable)

    _isolate_panel(st, _draw)
