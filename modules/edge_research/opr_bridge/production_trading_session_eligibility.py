"""
Phase 3K.2 — Trading session eligibility for production daily runs.

Uses panel-derived trading sessions as authoritative; weekend guard only.
No exchange holiday calendar invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.intraday_memory.scheduler import is_vn_weekend


@dataclass(frozen=True)
class TradingSessionEligibility:
    target_trade_date: str
    eligible: bool
    disposition: str  # ELIGIBLE | SKIPPED_NON_TRADING_DAY | WAITING_FOR_DATA
    reason: str
    is_weekend: bool
    in_panel_sessions: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_trade_date": self.target_trade_date,
            "eligible": self.eligible,
            "disposition": self.disposition,
            "reason": self.reason,
            "is_weekend": self.is_weekend,
            "in_panel_sessions": self.in_panel_sessions,
        }


def extract_panel_trading_sessions(panel: pd.DataFrame) -> List[str]:
    if panel.empty or "trade_date" not in panel.columns:
        return []
    return sorted(panel["trade_date"].astype(str).unique().tolist())


def is_trading_session_in_panel(panel: pd.DataFrame, target_trade_date: str) -> bool:
    sessions = extract_panel_trading_sessions(panel)
    return str(target_trade_date) in sessions


def evaluate_trading_session_eligibility(
    panel: pd.DataFrame,
    target_trade_date: str,
) -> TradingSessionEligibility:
    """
    Determine whether target_trade_date is an eligible trading session for a daily run.
    """
    td = str(target_trade_date)
    try:
        d = pd.Timestamp(td).date()
    except Exception:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="WAITING_FOR_DATA",
            reason="invalid_trade_date_format",
            is_weekend=False,
            in_panel_sessions=False,
        )

    weekend = is_vn_weekend(d)
    in_panel = is_trading_session_in_panel(panel, td)

    if weekend and not in_panel:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="SKIPPED_NON_TRADING_DAY",
            reason="weekend_non_session",
            is_weekend=True,
            in_panel_sessions=False,
        )

    if not in_panel:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="WAITING_FOR_DATA",
            reason="target_date_not_in_panel_sessions",
            is_weekend=weekend,
            in_panel_sessions=False,
        )

    return TradingSessionEligibility(
        target_trade_date=td,
        eligible=True,
        disposition="ELIGIBLE",
        reason="panel_session_confirmed",
        is_weekend=weekend,
        in_panel_sessions=True,
    )


def next_panel_session_after(panel: pd.DataFrame, target_trade_date: str) -> Optional[str]:
    sessions = extract_panel_trading_sessions(panel)
    if target_trade_date not in sessions:
        return None
    idx = sessions.index(target_trade_date)
    if idx + 1 < len(sessions):
        return sessions[idx + 1]
    return None


def prior_panel_session_before(panel: pd.DataFrame, target_trade_date: str) -> Optional[str]:
    sessions = extract_panel_trading_sessions(panel)
    prior = [s for s in sessions if s < target_trade_date]
    return prior[-1] if prior else None
