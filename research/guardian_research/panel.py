"""Guardian Research display. It reads snapshots and does not score a new formula."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.guardian_research.performance import read_performance_view
from research.guardian_research.snapshot import read_snapshot

CLASS_ORDER = ("HOLD", "WATCH", "SELL", "UNAVAILABLE")
# Same weight and palette as the Earning Money board health styles.
CLASS_STYLE = {
    "HOLD": "background-color:#d9ead3;color:#1b4332;font-weight:700",
    "WATCH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
    "SELL": "background-color:#f4cccc;color:#990000;font-weight:700",
    "UNAVAILABLE": "background-color:#d9d9d9;color:#333333;font-weight:700",
}
BOARD_COLUMNS = (
    "Classification",
    "Symbol",
    "Reason",
    "Score",
    "State age",
    "Transition",
    "Forward",
)


def default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "guardian_research"


def latest_snapshot(root: Path) -> dict | None:
    local = _latest_local(root)
    if Path(root).resolve() != default_root().resolve():
        return local
    remote = _latest_remote()
    if remote is None:
        return local
    if local is None or str(remote.get("session") or "") > str(local.get("session") or ""):
        return remote
    return local


def _latest_local(root: Path) -> dict | None:
    folder = Path(root) / "sessions"
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob("*.json"), reverse=True):
        try:
            return read_snapshot(path)
        except (OSError, ValueError):
            continue
    return None


def _latest_remote() -> dict | None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from research.guardian_research.pipeline import read_remote_snapshot

    root = default_root()
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    newest = None
    for offset in range(15):
        session = (today - timedelta(days=offset)).isoformat()
        document, state = read_remote_snapshot(root, session)
        if state == "disabled":
            return None
        if state == "present" and (newest is None or session > str(newest.get("session") or "")):
            newest = document
    return newest


def research_board(document: dict, scan_df=None) -> pd.DataFrame:
    """HOLD, WATCH, SELL, then UNAVAILABLE. Earning Money order inside each."""
    rows = []
    seen = set()
    for row in document.get("rows") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        rows.append(
            {
                "Classification": row.get("classification"),
                "Symbol": symbol,
                "Reason": row.get("reason"),
                "Score": row.get("score"),
                "State age": row.get("state_age_sessions"),
                "Transition": row.get("transition"),
                "Forward": (row.get("forward") or {}).get("status"),
            }
        )
    frame = pd.DataFrame(rows, columns=list(BOARD_COLUMNS))
    if frame.empty:
        return frame
    order, groups = _earning_group_order(scan_df)
    frame["Group"] = frame["Symbol"].map(lambda symbol: groups.get(symbol, ""))
    priority = {name: index for index, name in enumerate(CLASS_ORDER)}
    frame["_class"] = frame["Classification"].map(lambda value: priority.get(value, len(priority)))
    position = {symbol: index for index, symbol in enumerate(order)}
    frame["_pos"] = frame["Symbol"].map(lambda symbol: position.get(symbol, len(position)))
    frame["_src"] = range(len(frame))
    return (
        frame.sort_values(["_class", "_pos", "_src"], kind="stable")
        .drop(columns=["_class", "_pos", "_src"])
        .loc[:, ["Group", *BOARD_COLUMNS]]
        .reset_index(drop=True)
    )


def _earning_group_order(scan_df) -> tuple[list[str], dict[str, str]]:
    """Symbol order and health group from the existing Earning Money helper."""
    if not isinstance(scan_df, pd.DataFrame) or scan_df.empty or "symbol" not in scan_df.columns:
        return [], {}
    from modules.evolution_health import get_earning_money_board

    board = get_earning_money_board(scan_df)
    symbols: list[str] = []
    groups: dict[str, str] = {}
    for _, item in board.iterrows():
        symbol = str(item.get("Mã") or "").strip().upper()
        if not symbol or symbol in groups:
            continue
        symbols.append(symbol)
        groups[symbol] = str(item.get("Health") or "")
    return symbols, groups


def render_guardian_research_panel(
    scan_df=None,
    market_real=None,
    now: datetime | None = None,
    *,
    root: Path | None = None,
) -> dict | None:
    """Show the intraday board, then the sealed snapshot in a separate section."""
    import streamlit as st

    del market_real
    store = Path(root) if root is not None else default_root()
    st.markdown("---")
    _render_live(st, scan_df, now)
    document = _render_sealed(st, store, scan_df, root)
    _render_outcomes(st, store)
    return document


def _render_live(st, scan_df, now) -> None:
    """Current scan only. Refreshing this board does not replace a sealed snapshot."""
    from research.guardian_research.live import evaluate_live, live_board

    st.markdown("## 🟢 GUARDIAN RESEARCH LIVE")
    st.caption(
        "Primary board for all tracked symbols. "
        "Same position_guardian.generate_signal call and scan row as Position Guardian. "
        "These counts are the current scan. They are not the sealed T0 snapshot and not a portfolio order."
    )
    try:
        live = evaluate_live(scan_df, evaluated_at=now)
    except Exception as exc:
        st.error(f"Guardian Research LIVE failed: {type(exc).__name__}: {exc}")
        return
    _metric_row(st, _count_classes(live.get("rows") or []))
    if live.get("scan_session"):
        session = live["scan_session"]
    elif live.get("mixed_session"):
        session = "MIXED"
    else:
        session = "UNAVAILABLE"
    st.caption(
        f"Scan bar date {session}. The scan bar date is not a quote time. "
        f"Display clock {live.get('evaluated_at') or 'UNAVAILABLE'}. "
        f"Live-adjusted rows {live.get('live_adjusted_count', 0)}. "
        f"Rows with a quote timestamp {live.get('quoted_count', 0)}. "
        f"Bar freshness fresh {live['fresh_count']} · stale {live['stale_count']} · "
        f"undated {live['undated_count']} · incomplete {live['incomplete_count']} · "
        f"missing {live['missing_count']}. "
        f"{live['tracked_count']} tracked symbols. "
        "A missing quote is left blank."
    )
    board = live_board(live)
    if board.empty:
        st.info("No tracked symbols in the live scan.")
        return
    st.dataframe(
        board.style.map(_paint, subset=["Classification"]),
        use_container_width=True,
        hide_index=True,
        height=720,
    )


def _render_sealed(st, store: Path, scan_df, root: Path | None):
    """Sealed T0 only. Closed by default so its counts are not the live board."""
    document = latest_snapshot(store)
    view = _load_forward_view(root)
    session = (document or view or {}).get("session") or "UNAVAILABLE"
    with st.expander(f"Sealed T0 snapshot {session} — not the live board", expanded=False):
        if document is None and view is None:
            st.caption(
                "HOLD / WATCH / SELL here are research labels, not portfolio orders. "
                "Market Real is context only."
            )
            st.info("No Guardian Research snapshot yet.")
        elif document is None and view is not None:
            st.caption(
                "Reconstructed research board. This is not a contemporaneous close observation "
                "and not a portfolio order. Market Real is context only."
            )
            _classification_summary(st, view.get("counts") or {}, view.get("tracked_count"), view.get("session"))
            if view.get("observation_origin") == "BACKFILLED":
                st.caption("Observation origin BACKFILLED. It was reconstructed from a persisted scan.")
            board = research_board(_view_as_document(view), scan_df)
            st.dataframe(
                board.style.map(_paint, subset=["Classification"]),
                use_container_width=True,
                hide_index=True,
                height=720,
            )
        else:
            st.caption(
                "Latest sealed close-scan snapshot. "
                "HOLD / WATCH / SELL here are research labels, not portfolio orders. "
                "Market Real is context only. The sealed snapshot does not contain measured returns."
            )
            counts = document.get("counts") or {}
            _classification_summary(
                st,
                counts,
                document.get("tracked_count"),
                document.get("session"),
                document.get("market", {}).get("market_real_status"),
            )
            if document.get("observation_origin") == "BACKFILLED":
                st.caption("Observation origin BACKFILLED. It was reconstructed from a persisted scan.")
            board = research_board(document, scan_df)
            styled = board.style.map(_paint, subset=["Classification"])
            st.dataframe(styled, use_container_width=True, hide_index=True, height=720)
    if view is not None:
        _render_forward(st, view)
    return document


def _count_classes(rows) -> dict:
    counts = {name: 0 for name in CLASS_ORDER}
    for row in rows:
        name = str((row or {}).get("classification") or "")
        if name in counts:
            counts[name] += 1
    return counts


def _metric_row(st, counts: dict) -> None:
    columns = st.columns(4)
    for column, name in zip(columns, CLASS_ORDER):
        column.metric(name, int(counts.get(name, 0)))


def _render_outcomes(st, root: Path) -> None:
    """Read the precomputed T+ file. This does not scan or score."""
    if Path(root).resolve() != default_root().resolve():
        return
    from research.guardian_research.outcomes import read_outcomes

    view = read_outcomes()
    with st.expander("Guardian Research — T+ Performance", expanded=False):
        if view is None:
            st.info("T+ evidence file is absent or failed its digest check. No return was calculated.")
            return
        st.caption(view.get("statement") or "")
        st.caption(
            f"Evidence {view.get('evidence_status')} · calendar {view.get('calendar_status')} · "
            f"price basis {view.get('price_basis') or 'absent'}."
        )
        st.dataframe(_outcome_comparison(view), use_container_width=True, hide_index=True)
        st.markdown("**Per-symbol history**")
        st.dataframe(_outcome_symbols(view), use_container_width=True, hide_index=True, height=360)
        st.markdown("**Sample, missing data, and maturity**")
        st.dataframe(_outcome_quality(view), use_container_width=True, hide_index=True)
        st.markdown("**False SELL / later rise**")
        st.dataframe(_outcome_false_sell(view), use_container_width=True, hide_index=True)
        tenure = view.get("tenure") if isinstance(view.get("tenure"), dict) else {}
        st.caption(
            f"New or changed states {tenure.get('NEW_OR_CHANGED', 0)} · "
            f"persistent states {tenure.get('PERSISTENT', 0)} · "
            f"unclassified tenure {tenure.get('UNCLASSIFIED_TENURE', 0)}. "
            "A horizon marked INSUFFICIENT_EVIDENCE has no measured sample."
        )


def _outcome_comparison(view: dict):
    records = []
    classes = view.get("classifications") if isinstance(view.get("classifications"), dict) else {}
    for name in CLASS_ORDER:
        horizons = (classes.get(name) or {}).get("horizons") or {}
        for label, item in _ordered_horizons(horizons):
            records.append({
                "Classification": name,
                "Horizon": label,
                "Evidence": item.get("evidence"),
                "Sample": item.get("primary"),
                "Positive": _rate(item.get("positive_return_rate")),
                "Average": _pct(item.get("average_return_pct")),
                "Median": _pct(item.get("median_return_pct")),
                "Rise >3%": _rate(item.get("win_rate_above_3pct")),
                "Rise >5%": _rate(item.get("win_rate_above_5pct")),
                "Loss <0": _rate(item.get("loss_rate")),
                "Loss <-3%": _rate(item.get("loss_rate_below_minus_3pct")),
                "Loss <-5%": _rate(item.get("loss_rate_below_minus_5pct")),
                "Close-path avg": _pct(item.get("adverse_close_path_average_pct")),
                "Worst close-path": _pct(item.get("adverse_close_path_worst_pct")),
            })
    return pd.DataFrame(records)


def _outcome_symbols(view: dict):
    from research.guardian_research.outcomes import HORIZON_LABELS

    records = []
    for row in view.get("rows") or []:
        horizons = row.get("horizons") or {}
        record = {
            "Session": row.get("session"),
            "Symbol": row.get("symbol"),
            "Classification": row.get("classification"),
            "Tenure": row.get("tenure"),
            "Live-adjusted T0 input": "YES" if row.get("live_adjusted_input") else "",
        }
        for label in HORIZON_LABELS:
            cell = horizons.get(label) or {}
            record[f"{label} status"] = cell.get("status")
            record[label] = cell.get("return_pct")
        records.append(record)
    return pd.DataFrame(records)


def _outcome_quality(view: dict):
    records = []
    classes = view.get("classifications") if isinstance(view.get("classifications"), dict) else {}
    for name in CLASS_ORDER:
        horizons = (classes.get(name) or {}).get("horizons") or {}
        for label, item in _ordered_horizons(horizons):
            records.append({
                "Classification": name,
                "Horizon": label,
                "Evidence": item.get("evidence"),
                "Observations": item.get("observations"),
                "Mature sample": item.get("primary"),
                "Not yet": item.get("immature"),
                "Missing": item.get("missing"),
                "Not measured": item.get("unmeasured"),
                "Truncated": item.get("truncated"),
                "Discontinuity": item.get("discontinuity"),
                "Adverse sample": item.get("adverse_sample"),
            })
    return pd.DataFrame(records)


def _outcome_false_sell(view: dict):
    false_sell = view.get("false_sell") if isinstance(view.get("false_sell"), dict) else {}
    records = []
    for label, item in _ordered_horizons(false_sell.get("horizons") or {}):
        records.append({
            "Horizon": label,
            "Evidence": item.get("evidence"),
            "Sample": item.get("sample"),
            "Later rise": _rate(item.get("rose")),
            "Rise >3%": _rate(item.get("rose_above_3pct")),
            "Rise >5%": _rate(item.get("rose_above_5pct")),
            "Later fall": _rate(item.get("fell")),
        })
    return pd.DataFrame(records)


def _ordered_horizons(horizons: dict):
    from research.guardian_research.outcomes import HORIZON_LABELS

    return [(label, horizons[label]) for label in HORIZON_LABELS if isinstance(horizons, dict) and label in horizons]


def _load_forward_view(root: Path | None) -> dict | None:
    if root is not None and Path(root).resolve() != default_root().resolve():
        return None
    return read_performance_view()


def _classification_summary(st, counts: dict, tracked, session, market_status=None) -> None:
    _metric_row(st, counts)
    market = f" · Market Real {market_status}" if market_status else ""
    st.caption(f"Snapshot session {session} · {tracked} tracked symbols{market}")


def _view_as_document(view: dict) -> dict:
    rows = []
    for row in view.get("rows") or []:
        first = ((row.get("horizons") or {}).get("T+1") or {}).get("status")
        rows.append({**row, "forward": {"status": first or "UNMEASURED"}})
    return {"rows": rows}


def _render_forward(st, view: dict) -> None:
    with st.expander("GUARDIAN APPROXIMATE FORWARD", expanded=False):
        st.caption(view.get("statement") or "")
        assessment = view.get("input_assessment") if isinstance(view.get("input_assessment"), dict) else {}
        st.caption(
            f"Classification inputs={', '.join(assessment.get('classification_inputs') or [])}. "
            f"Position inputs required={assessment.get('position_inputs_required')}. "
            f"Position inputs used={assessment.get('position_inputs_used')}. "
            f"Live-adjusted stored inputs={assessment.get('live_adjusted_inputs')}. "
            "No holding or cost basis was invented."
        )
        drawdown = view.get("subsequent_drawdown") if isinstance(view.get("subsequent_drawdown"), dict) else {}
        st.caption(
            f"Subsequent intraday drawdown={drawdown.get('status')}: {drawdown.get('reason')}. "
            f"Build hash={view.get('snapshot_sha256')}."
        )
        st.dataframe(_forward_table(view), use_container_width=True, hide_index=True)


def _forward_table(view: dict):
    classes = view.get("classifications") if isinstance(view.get("classifications"), dict) else {}
    records = []
    for name in CLASS_ORDER:
        horizons = (classes.get(name) or {}).get("horizons") or {}
        for label, item in horizons.items():
            records.append({
                "Classification": name,
                "Horizon": label,
                "Sample": item.get("primary"),
                "Average": _pct(item.get("average_return_pct")),
                "Median": _pct(item.get("median_return_pct")),
                "Rise >3%": _rate(item.get("win_rate_above_3pct")),
                "Rise >5%": _pct_rate(item.get("win_rate_above_5pct")),
                "Loss rate": _rate(item.get("loss_rate")),
                "Downside p10": _pct(item.get("downside_p10_pct")),
            })
    missed = ((view.get("missed_rally") or {}).get("horizons") or {})
    for label, item in missed.items():
        records.append({
            "Classification": "SELL missed rally",
            "Horizon": label,
            "Sample": item.get("sample"),
            "Average": "—",
            "Median": "—",
            "Rise >3%": _rate(item.get("above_3pct")),
            "Rise >5%": _pct_rate(item.get("above_5pct")),
            "Loss rate": "—",
            "Downside p10": "—",
        })
    return pd.DataFrame(records)


def _pct(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:.2f}%"


def _rate(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value * 100:.1f}%"


def _pct_rate(value) -> str:
    return _rate(value)


def _paint(value: object) -> str:
    return CLASS_STYLE.get(str(value), "")
