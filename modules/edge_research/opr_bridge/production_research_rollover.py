"""
Production research-date rollover.

Scheduled runs must not abandon a previous eligible VN session just because
the VN calendar date advanced after midnight.

Order:
1. explicit --trade-date
2. previous eligible VN session with no terminal SUCCESS/SKIP (catch-up)
3. current Asia/Ho_Chi_Minh calendar date
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_timezone_policy import derive_vn_trade_date
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
    offset_trading_sessions,
)

TERMINAL_DISPOSITIONS = frozenset({"SUCCESS", "SKIPPED_NON_TRADING_DAY"})


@dataclass(frozen=True)
class ResearchRolloverTarget:
    target_trade_date: str
    vn_calendar_date: str
    reason: str
    previous_eligible_date: Optional[str]
    catch_up: bool
    calendar_eligible: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_trade_date": self.target_trade_date,
            "vn_calendar_date": self.vn_calendar_date,
            "reason": self.reason,
            "previous_eligible_date": self.previous_eligible_date,
            "catch_up": self.catch_up,
            "calendar_eligible": self.calendar_eligible,
        }


def _index_has_terminal_run(
    target_trade_date: str,
    run_mode: str,
    *,
    data_dir: Optional[Path] = None,
) -> bool:
    from modules.edge_research.opr_bridge.production_daily_run_persistence import load_run_index

    index = load_run_index(data_dir)
    for meta in (index.get("runs") or {}).values():
        if not isinstance(meta, dict):
            continue
        if meta.get("target_trade_date") != target_trade_date:
            continue
        if meta.get("run_mode") != run_mode:
            continue
        if meta.get("run_disposition") in TERMINAL_DISPOSITIONS:
            return True
    return False


def resolve_research_rollover_target(
    explicit_date: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    data_dir: Optional[Path] = None,
    run_mode: str = LIVE_FORWARD,
) -> ResearchRolloverTarget:
    """
    Choose the production research date for this invocation.

    Catch-up is one previous eligible session only. That recovers a day whose
    last same-day timer fired before T0/data readiness, then was abandoned
    after VN midnight when --derive-vn-date advanced.
    """
    vn_today = derive_vn_trade_date(now)
    if explicit_date:
        td = str(explicit_date)[:10]
        cal = evaluate_calendar_session_eligibility(td)
        return ResearchRolloverTarget(
            target_trade_date=td,
            vn_calendar_date=vn_today,
            reason="explicit_trade_date",
            previous_eligible_date=offset_trading_sessions(td, -1),
            catch_up=False,
            calendar_eligible=cal.eligible,
        )

    today_cal = evaluate_calendar_session_eligibility(vn_today)
    previous = offset_trading_sessions(vn_today, -1)
    if previous and not _index_has_terminal_run(previous, run_mode, data_dir=data_dir):
        prev_cal = evaluate_calendar_session_eligibility(previous)
        return ResearchRolloverTarget(
            target_trade_date=previous,
            vn_calendar_date=vn_today,
            reason="catch_up_previous_eligible_session",
            previous_eligible_date=previous,
            catch_up=True,
            calendar_eligible=prev_cal.eligible,
        )

    return ResearchRolloverTarget(
        target_trade_date=vn_today,
        vn_calendar_date=vn_today,
        reason="vn_calendar_today",
        previous_eligible_date=previous,
        catch_up=False,
        calendar_eligible=today_cal.eligible,
    )
