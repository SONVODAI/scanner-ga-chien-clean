"""Column projection and filters for an already built research board.

This module does not read ledger files and does not calculate prices.
"""

from __future__ import annotations

from typing import Any, Mapping

DISPLAY_COLUMNS = (
    "Symbol",
    "T0 date",
    "source",
    "setup",
    "T0 price",
    "current V2 Action state",
    "Market Real",
    "age in trading sessions",
    "T+1",
    "T+3",
    "T+5",
    "T+10",
    "T+15",
    "T+20",
    "quality status",
)
HORIZON_LABELS = ("T+1", "T+3", "T+5", "T+10", "T+15", "T+20")
ACTIVE = "ACTIVE"
COMPLETED = "COMPLETED"
MISSING_DATA = "MISSING_DATA"
CENSORED = "CENSORED"


def horizon_text(cell: Mapping[str, Any] | None) -> str:
    if not cell:
        return "NOT_YET_OBSERVED"
    status = str(cell.get("status") or "NOT_YET_OBSERVED")
    if status == "VALID" and cell.get("return_pct") is not None:
        return f"{cell['return_pct']:.2f}%"
    return status


def project_row(row: Mapping[str, Any]) -> dict[str, Any]:
    horizons = row.get("horizons") or {}
    return {
        "Symbol": row.get("symbol") or "",
        "T0 date": row.get("t0_date") or "",
        "source": row.get("source") or "",
        "setup": row.get("setup"),
        "T0 price": row.get("t0_price"),
        "current V2 Action state": row.get("action_state") or "",
        "Market Real": row.get("market_real"),
        "age in trading sessions": row.get("age_sessions"),
        "T+1": horizon_text(horizons.get("T+1")),
        "T+3": horizon_text(horizons.get("T+3")),
        "T+5": horizon_text(horizons.get("T+5")),
        "T+10": horizon_text(horizons.get("T+10")),
        "T+15": horizon_text(horizons.get("T+15")),
        "T+20": horizon_text(horizons.get("T+20")),
        "quality status": row.get("quality_status") or "",
    }


def project_table(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [project_row(row) for row in rows]


def apply_filters(
    rows: list[Mapping[str, Any]],
    *,
    t0_date: str | None = None,
    source: str | None = None,
    state: str | None = None,
    visibility: str = "all",
    symbol: str = "",
) -> list[dict[str, Any]]:
    """Return matching rows. `None` or `all` leaves that dimension open."""
    wanted_symbol = symbol.strip().upper()
    selected: list[dict[str, Any]] = []
    for row in rows:
        if t0_date and t0_date != "all" and row.get("t0_date") != t0_date:
            continue
        if source and source != "all" and row.get("source") != source:
            continue
        if state and state != "all" and row.get("action_state") != state:
            continue
        lifecycle = str(row.get("lifecycle") or "")
        if visibility == "active" and lifecycle != ACTIVE:
            continue
        if visibility == "history" and lifecycle == ACTIVE:
            continue
        if wanted_symbol and wanted_symbol not in str(row.get("symbol") or "").upper():
            continue
        selected.append(dict(row))
    return selected
