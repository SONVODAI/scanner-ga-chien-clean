"""Streamlit panel for EARLY RECOVERY WATCH. Research display only."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from modules.early_recovery_watch.contract import EMPTY_MESSAGE, PANEL_TITLE
from modules.early_recovery_watch.service import run_watch
from modules.early_recovery_watch.store import TextMirror
from modules.research_market_context.contract import SOURCE_STREAMLIT_SCAN


def _pct(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}%"


def _rate(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def _num(value: object, digits: int) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def render_early_recovery_watch(
    *,
    scan_df: pd.DataFrame | None,
    market_real: object,
    trade_date: date | str,
    source: str = SOURCE_STREAMLIT_SCAN,
    market_live: object = None,
    market_forecast: object = None,
    market_regime: object = None,
    breadth: object = None,
    market_status: object = None,
    market_action: object = None,
    evolution_path: Path | None = None,
    directory: Path | None = None,
    storage: TextMirror | None = None,
    streamlit_module: Any = None,
) -> dict[str, Any]:
    """Draw the research panel. Failure here must not change the Earning board."""
    st = streamlit_module
    if st is None:
        import streamlit as st  # type: ignore[no-redef]

    result = run_watch(
        scan_df=scan_df,
        market_real=market_real,
        trade_date=trade_date,
        source=source,
        market_live=market_live,
        market_forecast=market_forecast,
        market_regime=market_regime,
        breadth=breadth,
        market_status=market_status,
        market_action=market_action,
        evolution_path=evolution_path,
        directory=directory,
        storage=storage,
    )
    view = result["view"]
    card = view["scorecard"]
    st.markdown(f"## {PANEL_TITLE}")
    st.caption("Research only. Không tạo lệnh mua, không đổi bảng Earning Money.")
    row1 = st.columns(4)
    row1[0].metric("Events", card["events"])
    row1[1].metric("Independent Signal Days", card["independent_signal_days"])
    row1[2].metric("Mature T3 N", card["mature_t3_n"])
    row1[3].metric("T3 Winrate", _rate(card["t3_winrate"]))
    row2 = st.columns(4)
    row2[0].metric("Median T3", _pct(card["median_t3"]))
    row2[1].metric("Mature T5 N", card["mature_t5_n"])
    row2[2].metric("T5 Winrate", _rate(card["t5_winrate"]))
    row2[3].metric("Median T5", _pct(card["median_t5"]))
    if not view["rows"]:
        st.caption(EMPTY_MESSAGE)
        return result
    frame = pd.DataFrame(view["rows"])
    for column, digits in (("Giá T0", 2), ("RS10", 2), ("ΔRS10", 2), ("M.Real", 1)):
        if column in frame.columns:
            frame[column] = frame[column].map(lambda value, digits=digits: _num(value, digits))
    for column in ("T3", "T5", "T10"):
        frame[column] = frame[column].map(_pct)
    st.dataframe(frame, use_container_width=True, hide_index=True, height=280)
    return result
