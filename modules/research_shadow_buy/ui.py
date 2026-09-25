"""Research-only SHADOW BUY panel. Not a production BUY table."""

from __future__ import annotations

from typing import Any

from modules.research_shadow_buy.ledger import load_shadow_buy_events, load_shadow_buy_status

PANEL_TITLE = "RESEARCH / SHADOW — NO EXECUTION"
PANEL_CAPTION = (
    "SHADOW BUY is a hypothetical research decision. "
    "execution_enabled=false · candidate_is_buy=false · "
    "pxv_implies_buy=false · alert_eligible=false · no order"
)


def _display_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        if str(event.get("research_decision") or "") != "SHADOW_BUY":
            continue
        blocked = bool(event.get("market_blocked"))
        rows.append(
            {
                "symbol": event.get("symbol") or "",
                "decision": "SHADOW BUY — MARKET BLOCKED" if blocked else "SHADOW BUY",
                "time": event.get("first_met_at") or "",
                "price": event.get("price_at_first_met"),
                "setup_route": event.get("evaluated_route") or "",
                "source": event.get("candidate_source") or "",
                "condition_reason": event.get("evaluator_reason") or "",
                "market_permission": event.get("market_permission") or "",
                "market_blocked": blocked,
            }
        )
    return rows


def _status_decision(item: dict[str, Any]) -> str:
    if item.get("condition_met") and item.get("market_blocked"):
        return "SHADOW BUY — MARKET BLOCKED"
    if item.get("condition_met"):
        return "SHADOW BUY"
    if item.get("route_became_evaluable_at"):
        return "CURRENT ROUTE ACQUIRED / WAITING WHEN"
    return "NO CURRENT EVALUABLE ROUTE"


def _non_event_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in status.values():
        if not isinstance(item, dict) or item.get("condition_met"):
            continue
        reason = str(item.get("non_event_reason") or item.get("current_route_status") or "")
        if not reason and not item.get("route_became_evaluable_at"):
            continue
        rows.append(
            {
                "symbol": item.get("symbol") or "",
                "decision": _status_decision(item),
                "current_setup": item.get("evaluated_setup") or "",
                "origin_setup": item.get("origin_setup") or item.get("origin_group") or "",
                "reason": reason,
                "source": item.get("candidate_source") or "",
            }
        )
    return rows


def render_shadow_buy_research_panel(st_module: Any = None) -> None:
    """Smallest research visibility. Fail-open. Does not feed NAV or holdings."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore
    try:
        events = load_shadow_buy_events()
        status = load_shadow_buy_status()
    except Exception as exc:  # noqa: BLE001
        st.caption(f"SHADOW BUY research panel skipped: {type(exc).__name__}")
        return
    st.markdown(f"### {PANEL_TITLE}")
    st.caption(PANEL_CAPTION)
    table = _display_rows(events)
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.caption("No SHADOW BUY events recorded.")
    missing = _non_event_rows(status)
    if missing:
        st.caption("Not a SHADOW BUY — timing was not evaluable or not met.")
        st.dataframe(missing, use_container_width=True, hide_index=True)
