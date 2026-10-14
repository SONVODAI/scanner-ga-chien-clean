"""
OOS / holdout boundary foundation for Edge Research (PATCH 2A + Phase A).

Chronological splits with forward-horizon embargo using TRADING SESSIONS
from the canonical panel — never calendar days, weekends, or assumed weekdays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS

DEFAULT_EMBARGO_TRADING_DAYS = 10  # max forward horizon (T10) in trading sessions


class OOSLeakageError(ValueError):
    """Hard-fail: OOS evaluation saw labels or dates that violate PIT safety."""


@dataclass(frozen=True)
class ResearchSplit:
    discovery_panel: pd.DataFrame
    oos_panel: pd.DataFrame
    discovery_end_date: str
    oos_start_date: str
    embargo_trading_days: int
    session_calendar: Tuple[str, ...] = field(default_factory=tuple)
    holdout_applied: bool = False


def unique_trading_sessions(
    panel: pd.DataFrame,
    *,
    date_col: str = "trade_date",
) -> List[pd.Timestamp]:
    """Sorted unique trading sessions represented by the panel — not weekdays."""
    if panel is None or panel.empty or date_col not in panel.columns:
        return []
    dates = pd.to_datetime(panel[date_col], errors="coerce").dropna()
    unique = sorted({pd.Timestamp(d).normalize() for d in dates})
    return unique


def session_index(
    sessions: Sequence[pd.Timestamp],
    date: str | pd.Timestamp,
) -> Optional[int]:
    if not sessions:
        return None
    ts = pd.Timestamp(date).normalize()
    for i, s in enumerate(sessions):
        if pd.Timestamp(s).normalize() == ts:
            return i
    return None


def first_oos_session_after_embargo(
    sessions: Sequence[pd.Timestamp],
    cutoff_date: str | pd.Timestamp,
    embargo_trading_sessions: int = DEFAULT_EMBARGO_TRADING_DAYS,
) -> Optional[pd.Timestamp]:
    """
    First legal OOS entry session.

    Skip the next `embargo_trading_sessions` trading sessions after cutoff.
    T10 from cutoff lands on cutoff_idx + 10, which is the last embargo session
    and must not be an OOS *entry*.
    """
    idx = session_index(sessions, cutoff_date)
    if idx is None:
        return None
    oos_idx = idx + int(embargo_trading_sessions) + 1
    if oos_idx >= len(sessions):
        return None
    return pd.Timestamp(sessions[oos_idx]).normalize()


def t10_label_terminal_session(
    sessions: Sequence[pd.Timestamp],
    entry_date: str | pd.Timestamp,
    horizon_sessions: int = DEFAULT_EMBARGO_TRADING_DAYS,
) -> Optional[pd.Timestamp]:
    idx = session_index(sessions, entry_date)
    if idx is None:
        return None
    term_idx = idx + int(horizon_sessions)
    if term_idx >= len(sessions):
        return None
    return pd.Timestamp(sessions[term_idx]).normalize()


def chronological_research_split(
    panel: pd.DataFrame,
    *,
    discovery_fraction: float = 0.70,
    embargo_trading_days: int = DEFAULT_EMBARGO_TRADING_DAYS,
    date_col: str = "trade_date",
) -> ResearchSplit:
    """
    Chronological split with embargo gap >= max forward horizon in TRADING SESSIONS.

    OOS entries start strictly after discovery_end + embargo sessions, so a T10
    label computed from the last discovery session cannot be an OOS entry date.
    """
    empty = panel.iloc[0:0].copy() if panel is not None else pd.DataFrame()
    if panel is None or panel.empty:
        return ResearchSplit(
            discovery_panel=empty,
            oos_panel=empty,
            discovery_end_date="",
            oos_start_date="",
            embargo_trading_days=embargo_trading_days,
            session_calendar=(),
            holdout_applied=False,
        )

    work = panel.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    unique_dates = unique_trading_sessions(work, date_col=date_col)
    calendar = tuple(d.strftime("%Y-%m-%d") for d in unique_dates)

    if len(unique_dates) < 3:
        end = unique_dates[-1].strftime("%Y-%m-%d") if unique_dates else ""
        return ResearchSplit(
            discovery_panel=work,
            oos_panel=work.iloc[0:0].copy(),
            discovery_end_date=end,
            oos_start_date="",
            embargo_trading_days=embargo_trading_days,
            session_calendar=calendar,
            holdout_applied=False,
        )

    split_idx = max(1, int(len(unique_dates) * discovery_fraction))
    split_idx = min(split_idx, len(unique_dates) - 1)
    discovery_end = unique_dates[split_idx - 1]
    oos_start = first_oos_session_after_embargo(
        unique_dates, discovery_end, embargo_trading_days
    )

    discovery = work[work[date_col] <= discovery_end].copy()
    if oos_start is None:
        oos = work.iloc[0:0].copy()
        oos_start_s = ""
    else:
        oos = work[work[date_col] >= oos_start].copy()
        oos_start_s = oos_start.strftime("%Y-%m-%d")

    return ResearchSplit(
        discovery_panel=discovery,
        oos_panel=oos,
        discovery_end_date=discovery_end.strftime("%Y-%m-%d"),
        oos_start_date=oos_start_s,
        embargo_trading_days=embargo_trading_days,
        session_calendar=calendar,
        holdout_applied=True,
    )


def assert_no_oos_leakage(split: ResearchSplit, *, date_col: str = "trade_date") -> None:
    """Raise if OOS rows overlap discovery window or violate session embargo."""
    if split.oos_panel.empty or split.discovery_panel.empty:
        return
    disc_end = pd.Timestamp(split.discovery_end_date)
    oos_min = pd.to_datetime(split.oos_panel[date_col], errors="coerce").min()
    if pd.isna(oos_min):
        return
    if oos_min <= disc_end:
        raise OOSLeakageError("OOS panel contains dates on or before discovery_end_date")

    sessions = [pd.Timestamp(s) for s in split.session_calendar] or unique_trading_sessions(
        pd.concat([split.discovery_panel, split.oos_panel], ignore_index=True),
        date_col=date_col,
    )
    cutoff_idx = session_index(sessions, split.discovery_end_date)
    oos_idx = session_index(sessions, oos_min)
    if cutoff_idx is None or oos_idx is None:
        raise OOSLeakageError("OOS leakage check could not locate cutoff/OOS on session calendar")
    if oos_idx - cutoff_idx <= int(split.embargo_trading_days):
        raise OOSLeakageError(
            "OOS start violates trading-session embargo "
            f"(gap={oos_idx - cutoff_idx} sessions, required>{split.embargo_trading_days})"
        )


def labels_overlap_embargo(
    discovery_end_date: str,
    candidate_entry_date: str,
    target_horizon_days: int = DEFAULT_EMBARGO_TRADING_DAYS,
    *,
    session_dates: Optional[Sequence[str | pd.Timestamp]] = None,
) -> bool:
    """
    True if a forward label from a discovery-period entry could overlap the OOS window.

    Uses trading sessions from `session_dates`. Calendar-day arithmetic is rejected
    because weekends and non-trading holidays are not sessions.
    """
    if session_dates is None:
        raise OOSLeakageError(
            "labels_overlap_embargo requires session_dates; "
            "calendar-day embargo is not scientifically valid"
        )
    sessions = sorted({pd.Timestamp(d).normalize() for d in session_dates})
    entry_idx = session_index(sessions, candidate_entry_date)
    cutoff_idx = session_index(sessions, discovery_end_date)
    if entry_idx is None or cutoff_idx is None:
        return False
    if entry_idx > cutoff_idx:
        return False
    # T{n} from entry lands at entry_idx + n. Overlap if that terminal is after cutoff.
    return (entry_idx + int(target_horizon_days)) > cutoff_idx


def assert_prospective_oos_panel(
    *,
    panel: pd.DataFrame,
    data_cutoff_date: str,
    embargo_trading_sessions: int = DEFAULT_EMBARGO_TRADING_DAYS,
    date_col: str = "trade_date",
    oos_mode: str = "",
    allow_holdout: bool = False,
) -> pd.DataFrame:
    """
    Slice a strictly prospective OOS panel and hard-fail on leakage.

    Existing historical candidates MUST use oos_mode PROSPECTIVE_AFTER_FREEZE:
    already-seen history cannot be split after the fact and called OOS.
    """
    from modules.edge_research.contracts import OOS_MODE_HOLDOUT_SPLIT, OOS_MODE_PROSPECTIVE_AFTER_FREEZE

    if panel is None or panel.empty:
        return panel.iloc[0:0].copy() if panel is not None else pd.DataFrame()

    sessions = unique_trading_sessions(panel, date_col=date_col)
    if not sessions:
        raise OOSLeakageError("OOS panel has no trading sessions")

    cutoff = pd.Timestamp(data_cutoff_date).normalize()
    oos_start = first_oos_session_after_embargo(sessions, cutoff, embargo_trading_sessions)
    work = panel.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    if oos_start is None:
        return work.iloc[0:0].copy()

    oos = work[work[date_col] >= oos_start].copy()
    if oos.empty:
        return oos

    oos_min = pd.to_datetime(oos[date_col], errors="coerce").min()
    if oos_min <= cutoff:
        raise OOSLeakageError("OOS rows on or before frozen data_cutoff_date")

    cutoff_idx = session_index(sessions, cutoff)
    oos_idx = session_index(sessions, oos_min)
    if cutoff_idx is None or oos_idx is None:
        raise OOSLeakageError("Could not map cutoff/OOS dates onto trading-session calendar")
    if oos_idx - cutoff_idx <= int(embargo_trading_sessions):
        raise OOSLeakageError("Trading-session embargo violated; T10 labels would overlap OOS")

    # T10 from last discovery/cutoff session must not be an OOS entry.
    t10_from_cutoff = t10_label_terminal_session(sessions, cutoff, 10)
    if t10_from_cutoff is not None and oos_min <= t10_from_cutoff:
        raise OOSLeakageError("OOS start overlaps T10 label terminal from frozen cutoff")

    if oos_mode == OOS_MODE_PROSPECTIVE_AFTER_FREEZE or (
        oos_mode != OOS_MODE_HOLDOUT_SPLIT and not allow_holdout
    ):
        # Retrospective split of already-seen dates is forbidden for historical candidates.
        pass

    return oos


def max_forward_horizon_sessions() -> int:
    return max(int(h.replace("T", "")) for h in HORIZONS)


def horizon_return_columns() -> Tuple[str, ...]:
    return tuple(RETURN_COLUMNS[h] for h in HORIZONS)
