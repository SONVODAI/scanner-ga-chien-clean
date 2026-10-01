"""
FC-1 data accumulation health status.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from modules.forecast_research.fc1.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_PARTIAL,
    FC1_VERSION,
    GATE_MIN_SWITCHES,
    GATE_T10_DATES,
    GATE_T3_DATES,
    GATE_T5_DATES,
)
from modules.forecast_research.fc1.episodes import direction_switches_from_labels, episode_summary


def build_accumulation_status(
    pit: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    pit_with_episodes: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    pit = pit.copy()
    labels = labels.copy() if labels is not None else pd.DataFrame()

    complete = int((pit.get("completeness_status") == COMPLETENESS_COMPLETE).sum()) if not pit.empty else 0
    partial = int((pit.get("completeness_status") == COMPLETENESS_PARTIAL).sum()) if not pit.empty else 0

    matured = {}
    for h, gate in ((3, GATE_T3_DATES), (5, GATE_T5_DATES), (10, GATE_T10_DATES)):
        n = int((labels["horizon"] == h).sum()) if not labels.empty else 0
        matured[f"T{h}"] = {
            "matured_dates": n,
            "gate": gate,
            "remaining_to_gate": max(gate - n, 0),
            "gate_met": n >= gate,
        }

    switches = direction_switches_from_labels(labels, horizon=3) if not labels.empty else 0
    ep = episode_summary(pit_with_episodes if pit_with_episodes is not None else pit)

    # Required field missingness on latest date
    missing_required = []
    if not pit.empty:
        latest = pit.sort_values("trade_date").iloc[-1]
        for f in ("market_real", "market_live", "market_forecast", "rsi50_share", "obv_green_share"):
            if f not in latest or pd.isna(latest.get(f)):
                missing_required.append(f)

    status = {
        "fc1_version": FC1_VERSION,
        "latest_t0_date": str(pit["trade_date"].max()) if not pit.empty else None,
        "earliest_t0_date": str(pit["trade_date"].min()) if not pit.empty else None,
        "n_t0_dates": int(len(pit)),
        "n_complete": complete,
        "n_partial": partial,
        "maturity": matured,
        "direction_switches_T3_favorable_median": switches,
        "episode_summary_all_t0": ep,
        "missing_required_on_latest": missing_required,
        "research_gates": {
            "T3": GATE_T3_DATES,
            "T5": GATE_T5_DATES,
            "T10": GATE_T10_DATES,
            "min_switches": GATE_MIN_SWITCHES,
        },
        "gates_met": {
            "T3": matured["T3"]["gate_met"],
            "T5": matured["T5"]["gate_met"],
            "T10": matured["T10"]["gate_met"],
            "switches": switches >= GATE_MIN_SWITCHES,
        },
        "note": (
            "No calendar ETA: trading-day scheduling not projected. "
            "Remaining counts are date deficits only."
        ),
    }
    return status
