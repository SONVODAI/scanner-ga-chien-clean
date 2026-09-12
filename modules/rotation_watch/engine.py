"""Rotation second-layer state machine. Frozen P×V labels in, Rotation state out."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from modules.intraday_pxv_v1.constants import EV_STRENGTHEN, EV_UNUSABLE, EV_WEAKEN
from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.config import WatchRow, load_watchlist, quoted_price
from modules.rotation_watch.constants import (
    ACT_HOLD,
    ACT_WATCH_LOWER,
    FRESH_INVALID,
    FRESH_MISSING,
    FRESH_PROVIDER_ERROR,
    FRESH_STALE,
    FRESH_UNFINISHED_ONLY,
    FRESH_WRONG_SESSION,
    LOC_ABOVE_UPPER,
    LOC_LOWER,
    LOC_MIDDLE,
    LOC_UPPER,
    ST_BUY_READY,
    ST_DATA_UNCERTAIN,
    ST_HOLD,
    ST_LOWER_ZONE,
    ST_RISK,
    ST_SELL_READY,
    ST_TREND_HOLD,
    ST_UPPER_ZONE,
    ST_WATCH,
    STATE_TO_ACTION,
    T25_MIN_SESSIONS,
)
from modules.rotation_watch.data import SymbolSnapshot, fetch_snapshots
from modules.rotation_watch.pxv import RotationPxV, interpret_completed_bars
from modules.rotation_watch.state import apply_transitions, default_state_path


def price_location(price_vnd: int, row: WatchRow) -> str:
    if price_vnd < row.lower_min_vnd:
        return LOC_BELOW_LOWER
    if price_vnd <= row.lower_max_vnd:
        return LOC_LOWER
    if price_vnd < row.upper_min_vnd:
        return LOC_MIDDLE
    if price_vnd <= row.upper_max_vnd:
        return LOC_UPPER
    return LOC_ABOVE_UPPER


def range_position_pct(price_vnd: int, row: WatchRow) -> float | None:
    span = row.upper_max_vnd - row.lower_min_vnd
    if span <= 0:
        return None
    return (price_vnd - row.lower_min_vnd) / span * 100.0


def hold_above_upper(completed: list[dict[str, Any]], upper_max_vnd: int) -> bool:
    if len(completed) < 2:
        return False
    last = int(completed[-1]["close"])
    prev = int(completed[-2]["close"])
    return last > upper_max_vnd and prev > upper_max_vnd


def holding_trading_days(entry: date | None, session: date | None) -> int | None:
    if entry is None or session is None:
        return None
    if session < entry:
        return None
    days = 0
    cur = entry
    while cur < session:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def _decide_state(
    *,
    location: str,
    published: str,
    has_position: bool,
    hold_above: bool,
) -> str:
    if location == LOC_LOWER:
        if published == EV_STRENGTHEN:
            return ST_BUY_READY
        if published == EV_WEAKEN:
            return ST_RISK
        return ST_HOLD if has_position else ST_LOWER_ZONE

    if location == LOC_MIDDLE:
        return ST_HOLD if has_position else ST_WATCH

    if location == LOC_UPPER:
        if published == EV_WEAKEN:
            return ST_SELL_READY
        if published == EV_STRENGTHEN:
            return ST_HOLD if has_position else ST_UPPER_ZONE
        return ST_HOLD if has_position else ST_UPPER_ZONE

    if location == LOC_ABOVE_UPPER:
        if published == EV_STRENGTHEN and hold_above:
            return ST_TREND_HOLD
        if published == EV_WEAKEN:
            return ST_RISK
        return ST_HOLD if has_position else ST_WATCH

    # BELOW_LOWER
    if published == EV_WEAKEN:
        return ST_RISK
    if published == EV_STRENGTHEN:
        return ST_WATCH
    return ST_RISK if has_position else ST_WATCH


@dataclass
class RotationRow:
    symbol: str
    enabled: bool
    current_price: float | None
    lower_zone: str
    upper_zone: str
    range_position_pct: float | None
    location: str
    rotation_state: str
    suggested_action: str
    raw_pxv: str
    published_pxv: str
    pxv_why: str
    published_why: str
    last_bar_ts: str
    freshness: str
    freshness_reason: str
    data_source: str
    data_source_label: str
    entry_price: float | None
    pnl_pct: float | None
    rotation_evidence: list[str] = field(default_factory=list)
    note: str = ""
    previous_state: str = ""
    first_entered_at: str = ""
    latest_transition_at: str = ""
    t25_checkpoint: str = ""
    has_position: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RotationBoard:
    rows: list[RotationRow]
    generated_at: str
    watchlist_path: str
    empty: bool
    empty_message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "watchlist_path": self.watchlist_path,
            "empty": self.empty,
            "empty_message": self.empty_message,
            "rows": [r.as_dict() for r in self.rows],
        }

    def display_table(self) -> Any:
        import pandas as pd

        records = []
        for row in self.rows:
            records.append(
                {
                    "Symbol": row.symbol,
                    "Current Price": row.current_price,
                    "Lower Zone": row.lower_zone,
                    "Upper Zone": row.upper_zone,
                    "Range Position %": (
                        None if row.range_position_pct is None else round(row.range_position_pct, 1)
                    ),
                    "Rotation State": row.rotation_state,
                    "Suggested Action": row.suggested_action,
                    "Raw P×V": row.raw_pxv,
                    "Published P×V": row.published_pxv,
                    "P×V evidence / why": row.pxv_why,
                    "Last completed 5m bar": row.last_bar_ts,
                    "Data Freshness": row.freshness,
                    "Entry Price": row.entry_price,
                    "P/L %": None if row.pnl_pct is None else round(row.pnl_pct, 2),
                    "Rotation evidence": " · ".join(row.rotation_evidence),
                }
            )
        return pd.DataFrame(records)


def evaluate_row(
    row: WatchRow,
    snapshot: SymbolSnapshot,
    pxv: RotationPxV | None = None,
    *,
    now: datetime | None = None,
) -> RotationRow:
    now = as_vn(now or datetime.now())
    lower = f"{quoted_price(row.lower_min_vnd):.2f}–{quoted_price(row.lower_max_vnd):.2f}"
    upper = f"{quoted_price(row.upper_min_vnd):.2f}–{quoted_price(row.upper_max_vnd):.2f}"
    evidence: list[str] = []

    fail_closed = (
        not snapshot.is_usable
        or snapshot.latest_close_vnd is None
        or snapshot.freshness_label
        in {
            FRESH_PROVIDER_ERROR,
            FRESH_STALE,
            FRESH_MISSING,
            FRESH_WRONG_SESSION,
            FRESH_INVALID,
            FRESH_UNFINISHED_ONLY,
        }
        or not row.zones_valid
    )

    if pxv is None:
        pxv = (
            interpret_completed_bars(snapshot.completed, now=now)
            if snapshot.completed
            else RotationPxV()
        )

    if fail_closed or pxv.published == EV_UNUSABLE or not pxv.usable:
        reason = snapshot.freshness_reason or pxv.raw_why or "intraday data not usable"
        if not row.zones_valid:
            reason = "invalid lower/upper zone configuration"
        evidence = [
            f"DATA_UNCERTAIN: {reason}",
            f"source={snapshot.source} ({snapshot.source_label})",
            f"freshness={snapshot.freshness_label}",
            f"published P×V={pxv.published}" if pxv.published else "published P×V unavailable",
        ]
        if pxv.raw_why:
            evidence.append(f"P×V why: {pxv.raw_why}")
        return RotationRow(
            symbol=row.symbol,
            enabled=row.enabled,
            current_price=quoted_price(snapshot.latest_close_vnd),
            lower_zone=lower,
            upper_zone=upper,
            range_position_pct=(
                range_position_pct(snapshot.latest_close_vnd, row)
                if snapshot.latest_close_vnd is not None
                else None
            ),
            location="",
            rotation_state=ST_DATA_UNCERTAIN,
            suggested_action=STATE_TO_ACTION[ST_DATA_UNCERTAIN],
            raw_pxv=pxv.raw,
            published_pxv=pxv.published,
            pxv_why=pxv.raw_why,
            published_why=pxv.published_why,
            last_bar_ts=snapshot.latest_bar_ts.isoformat() if snapshot.latest_bar_ts else "",
            freshness=snapshot.freshness_label,
            freshness_reason=snapshot.freshness_reason,
            data_source=snapshot.source,
            data_source_label=snapshot.source_label,
            entry_price=quoted_price(row.entry_price_vnd),
            pnl_pct=None,
            rotation_evidence=evidence,
            note=row.note,
            has_position=row.has_position,
        )

    price = int(snapshot.latest_close_vnd)
    location = price_location(price, row)
    hold_above = hold_above_upper(snapshot.completed, row.upper_max_vnd)
    state = _decide_state(
        location=location,
        published=pxv.published,
        has_position=row.has_position,
        hold_above=hold_above,
    )
    action = STATE_TO_ACTION[state]
    if state == ST_LOWER_ZONE:
        action = ACT_WATCH_LOWER
    if state == ST_HOLD and location == LOC_LOWER:
        action = ACT_HOLD

    pnl = None
    if row.entry_price_vnd:
        pnl = (price - row.entry_price_vnd) / row.entry_price_vnd * 100.0

    session = snapshot.session_date or snapshot.expected_session
    held = holding_trading_days(row.entry_date, session)
    t25_note = ""
    if held is not None and held >= T25_MIN_SESSIONS:
        profit = pnl is not None and pnl > 0
        if profit and location == LOC_MIDDLE and pxv.published != EV_WEAKEN:
            t25_note = (
                f"T+{held} checkpoint: profit {pnl:.2f}% still below Upper Zone; "
                f"published P×V {pxv.published} → HOLD (not a mechanical sell)"
            )
            if state != ST_DATA_UNCERTAIN:
                state = ST_HOLD
                action = ACT_HOLD

    pos_pct = range_position_pct(price, row)
    last_hm = as_vn(snapshot.latest_bar_ts).strftime("%H:%M") if snapshot.latest_bar_ts else "—"
    evidence = [
        f"price {quoted_price(price):.2f} in {location}",
        f"lower {lower}; upper {upper}",
        f"range position {pos_pct:.1f}%" if pos_pct is not None else "range position n/a",
        f"published P×V {pxv.published}: {pxv.raw_why or pxv.published_why}",
        f"raw P×V {pxv.raw}",
        f"intraday {snapshot.source} fresh as of {last_hm} ({snapshot.freshness_label})",
    ]
    if hold_above:
        evidence.append("two completed closes hold above configured upper_max")
    elif location == LOC_ABOVE_UPPER:
        evidence.append("first completed close above upper_max — TREND_HOLD not confirmed")
    if t25_note:
        evidence.append(t25_note)
    if row.has_position:
        evidence.append(
            f"entry {quoted_price(row.entry_price_vnd):.2f}; P/L {pnl:.2f}%"
            if pnl is not None
            else f"entry {quoted_price(row.entry_price_vnd):.2f}"
        )

    return RotationRow(
        symbol=row.symbol,
        enabled=row.enabled,
        current_price=quoted_price(price),
        lower_zone=lower,
        upper_zone=upper,
        range_position_pct=pos_pct,
        location=location,
        rotation_state=state,
        suggested_action=action,
        raw_pxv=pxv.raw,
        published_pxv=pxv.published,
        pxv_why=pxv.raw_why,
        published_why=pxv.published_why,
        last_bar_ts=snapshot.latest_bar_ts.isoformat() if snapshot.latest_bar_ts else "",
        freshness=snapshot.freshness_label,
        freshness_reason=snapshot.freshness_reason,
        data_source=snapshot.source,
        data_source_label=snapshot.source_label,
        entry_price=quoted_price(row.entry_price_vnd),
        pnl_pct=pnl,
        rotation_evidence=evidence,
        note=row.note,
        t25_checkpoint=t25_note,
        has_position=row.has_position,
    )


def build_board(
    *,
    now: datetime | None = None,
    watchlist_path: Path | None = None,
    provider: Any | None = None,
    injected: dict[str, list[dict[str, Any]]] | None = None,
    persist: bool = False,
    state_path: Path | None = None,
    snapshots: dict[str, SymbolSnapshot] | None = None,
) -> RotationBoard:
    now = as_vn(now or datetime.now())
    rows = load_watchlist(watchlist_path)
    path = str(watchlist_path or "")
    if not rows:
        return RotationBoard(
            rows=[],
            generated_at=now.isoformat(),
            watchlist_path=path,
            empty=True,
            empty_message="Chưa có mã enabled trong data/rotation_watch/watchlist.csv",
        )

    if snapshots is None:
        snapshots = fetch_snapshots(
            [r.symbol for r in rows],
            now,
            provider=provider,
            injected=injected,
        )

    evaluated: list[RotationRow] = []
    for row in rows:
        snap = snapshots.get(row.symbol) or SymbolSnapshot(
            symbol=row.symbol,
            source="unavailable",
            source_label="missing snapshot",
            session_date=None,
            expected_session=now.date(),
            freshness_label=FRESH_PROVIDER_ERROR,
            freshness_reason="snapshot missing",
            is_usable=False,
        )
        pxv = interpret_completed_bars(snap.completed, now=now) if snap.completed else RotationPxV()
        evaluated.append(evaluate_row(row, snap, pxv, now=now))

    if persist:
        persisted = apply_transitions(
            evaluated,
            now=now,
            path=state_path or default_state_path(),
        )
        by_sym = {p["symbol"]: p for p in persisted}
        for item in evaluated:
            rec = by_sym.get(item.symbol) or {}
            item.previous_state = str(rec.get("previous_state") or "")
            item.first_entered_at = str(rec.get("first_entered_at") or "")
            item.latest_transition_at = str(rec.get("latest_transition_at") or "")

    return RotationBoard(
        rows=evaluated,
        generated_at=now.isoformat(),
        watchlist_path=path or (rows[0].source_path if rows else ""),
        empty=False,
    )
