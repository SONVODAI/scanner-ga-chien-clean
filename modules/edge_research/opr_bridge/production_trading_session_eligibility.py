"""
Phase 3K.2 / 3K.5A — Trading session eligibility for production daily runs.

Uses VN trading calendar + panel-derived sessions. Fail closed on calendar unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
)


@dataclass(frozen=True)
class TradingSessionEligibility:
    target_trade_date: str
    eligible: bool
    disposition: str  # ELIGIBLE | SKIPPED_NON_TRADING_DAY | WAITING_FOR_DATA | CALENDAR_UNKNOWN
    reason: str
    is_weekend: bool
    in_panel_sessions: bool
    calendar_eligible: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_trade_date": self.target_trade_date,
            "eligible": self.eligible,
            "disposition": self.disposition,
            "reason": self.reason,
            "is_weekend": self.is_weekend,
            "in_panel_sessions": self.in_panel_sessions,
            "calendar_eligible": self.calendar_eligible,
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
    *,
    calendar_path: Optional[Path] = None,
) -> TradingSessionEligibility:
    """
    Determine whether target_trade_date is an eligible trading session for a daily run.
  """
    td = str(target_trade_date)
    cal = evaluate_calendar_session_eligibility(td, calendar_path=calendar_path)

    if cal.disposition == "CALENDAR_UNKNOWN":
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="CALENDAR_UNKNOWN",
            reason=cal.reason,
            is_weekend=False,
            in_panel_sessions=False,
            calendar_eligible=False,
        )

    if not cal.eligible:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition=cal.disposition,
            reason=cal.reason,
            is_weekend=cal.is_weekend,
            in_panel_sessions=False,
            calendar_eligible=False,
        )

    try:
        pd.Timestamp(td).date()
    except Exception:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="WAITING_FOR_DATA",
            reason="invalid_trade_date_format",
            is_weekend=cal.is_weekend,
            in_panel_sessions=False,
            calendar_eligible=True,
        )

    in_panel = is_trading_session_in_panel(panel, td)
    if not in_panel:
        return TradingSessionEligibility(
            target_trade_date=td,
            eligible=False,
            disposition="WAITING_FOR_DATA",
            reason="target_date_not_in_panel_sessions",
            is_weekend=cal.is_weekend,
            in_panel_sessions=False,
            calendar_eligible=True,
        )

    return TradingSessionEligibility(
        target_trade_date=td,
        eligible=True,
        disposition="ELIGIBLE",
        reason="calendar_and_panel_session_confirmed",
        is_weekend=cal.is_weekend,
        in_panel_sessions=True,
        calendar_eligible=True,
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
