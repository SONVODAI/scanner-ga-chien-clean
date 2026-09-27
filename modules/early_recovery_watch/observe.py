"""Point-in-time qualification against the Evolution Observer ledger.

Previous Health and previous RS10 come only from an earlier ledger line.
This module does not read Earning snapshots or observations.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Any, Mapping, Sequence

from modules.early_recovery_watch.contract import (
    DATA_MODE_FORWARD,
    DELTA_RS10_MIN,
    EARLY_RECOVERY_ALERT_ELIGIBLE,
    EARLY_RECOVERY_IS_BUY,
    MARKET_REAL_MAX_EXCLUSIVE,
    RECOVERY_KIND,
    RS10_MAX,
    SCHEMA_EVENT,
    VOL_CONFIRM_TEXT,
    WEAK_KINDS,
)
from modules.live_candidate.calendar import as_vn
from modules.research_market_context.contract import SOURCE_STREAMLIT_SCAN


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>", "nat"}:
        return ""
    return text


def symbol_key(value: object) -> str:
    return _text(value).upper()


def parse_captured_at(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return as_vn(parsed)


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _fold(value: object) -> str:
    text = _text(value).upper()
    table = str.maketrans(
        {
            "Á": "A", "À": "A", "Ả": "A", "Ã": "A", "Ạ": "A",
            "Ấ": "A", "Ầ": "A", "Ẩ": "A", "Ẫ": "A", "Ậ": "A",
            "É": "E", "È": "E", "Ẻ": "E", "Ẽ": "E", "Ẹ": "E",
            "Ế": "E", "Ề": "E", "Ể": "E", "Ễ": "E", "Ệ": "E",
            "Í": "I", "Ì": "I", "Ỉ": "I", "Ĩ": "I", "Ị": "I",
            "Ó": "O", "Ò": "O", "Ỏ": "O", "Õ": "O", "Ọ": "O",
            "Ố": "O", "Ồ": "O", "Ổ": "O", "Ỗ": "O", "Ộ": "O",
            "Ớ": "O", "Ờ": "O", "Ở": "O", "Ỡ": "O", "Ợ": "O",
            "Ú": "U", "Ù": "U", "Ủ": "U", "Ũ": "U", "Ụ": "U",
            "Ứ": "U", "Ừ": "U", "Ử": "U", "Ữ": "U", "Ự": "U",
            "Ý": "Y", "Ỳ": "Y", "Ỷ": "Y", "Ỹ": "Y", "Ỵ": "Y",
            "Đ": "D",
        }
    )
    return text.translate(table)


def health_kind(value: object) -> str | None:
    """Map a board or ledger Health label onto the locked V1 kinds.

    Longer labels are tested first so YẾU does not swallow RẤT YẾU or YẾU DẦN.
    """
    folded = _fold(value)
    if "RAT YEU" in folded:
        return "RAT_YEU"
    if "YEU DAN" in folded:
        return "YEU_DAN"
    if "DANG HOI" in folded:
        return "DANG_HOI"
    if "TRUNG TINH" in folded:
        return "TRUNG_TINH"
    if "YEU" in folded:
        return "YEU"
    return None


def health_label(kind: str | None) -> str:
    return {
        "RAT_YEU": "RẤT YẾU",
        "YEU": "YẾU",
        "YEU_DAN": "YẾU DẦN",
        "DANG_HOI": "ĐANG HỒI",
        "TRUNG_TINH": "TRUNG TÍNH",
    }.get(kind or "", _text(kind))


def is_weak_health(value: object) -> bool:
    return health_kind(value) in WEAK_KINDS


def is_recovering_health(value: object) -> bool:
    return health_kind(value) == RECOVERY_KIND


def vol_confirmed(evolution_reason: object) -> bool:
    """Canonical Why text. ``Vol chưa xác nhận`` does not match."""
    return VOL_CONFIRM_TEXT in _text(evolution_reason)


def qualifies_v1(
    *,
    previous_health: object,
    current_health: object,
    previous_rs10: object,
    current_rs10: object,
    evolution_reason: object,
    market_real: object,
) -> bool:
    """Locked V1 gate. Metadata such as RSI, RS5, Live, Forecast, and breadth is ignored."""
    previous = _number(previous_rs10)
    current = _number(current_rs10)
    real = _number(market_real)
    if previous is None or current is None or real is None:
        return False
    if not is_weak_health(previous_health):
        return False
    if not is_recovering_health(current_health):
        return False
    if (current - previous) < DELTA_RS10_MIN:
        return False
    if current > RS10_MAX:
        return False
    if not vol_confirmed(evolution_reason):
        return False
    if real >= MARKET_REAL_MAX_EXCLUSIVE:
        return False
    return True


def current_scan_boundary(
    lines: Sequence[Mapping[str, Any]],
    *,
    scan_fingerprint: str,
    trade_date: str,
    source: str = SOURCE_STREAMLIT_SCAN,
) -> datetime | None:
    """Captured time of this scan's own ledger lines.

    Wall-clock now is not the boundary. A later rerun must still treat the
    retained line of this fingerprint as the current observation.
    """
    fingerprint = _text(scan_fingerprint)
    day = _text(trade_date)[:10]
    src = _text(source)
    if not fingerprint or not day or not src:
        return None
    found: list[datetime] = []
    for line in lines:
        if _text(line.get("scan_fingerprint")) != fingerprint:
            continue
        if _text(line.get("trade_date"))[:10] != day:
            continue
        if _text(line.get("source")) != src:
            continue
        stamp = parse_captured_at(line.get("captured_at"))
        if stamp is not None:
            found.append(stamp)
    if not found:
        return None
    return max(found)


def previous_observation(
    lines: Sequence[Mapping[str, Any]],
    symbol: object,
    boundary: datetime | None,
) -> dict[str, Any] | None:
    """Latest Evolution Observer line for the symbol strictly before ``boundary``."""
    if boundary is None:
        return None
    key = symbol_key(symbol)
    if not key:
        return None
    limit = as_vn(boundary)
    chosen: tuple[datetime, int, Mapping[str, Any]] | None = None
    for index, line in enumerate(lines):
        if symbol_key(line.get("symbol")) != key:
            continue
        stamp = parse_captured_at(line.get("captured_at"))
        if stamp is None or stamp >= limit:
            continue
        if chosen is None or (stamp, index) > (chosen[0], chosen[1]):
            chosen = (stamp, index, line)
    if chosen is None:
        return None
    return dict(chosen[2])


def previous_observation_id(line: Mapping[str, Any]) -> str:
    return "|".join(
        (
            _text(line.get("trade_date"))[:10],
            _text(line.get("captured_at")),
            _text(line.get("source")),
            _text(line.get("state_hash")),
        )
    )


def event_id_for(symbol: object, previous_line: Mapping[str, Any]) -> str:
    raw = f"{symbol_key(symbol)}|{previous_observation_id(previous_line)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def later_session_prices(
    lines: Sequence[Mapping[str, Any]],
    symbol: object,
    event_date: str,
) -> list[tuple[str, float]]:
    """One price per later stored trade_date.

    The price is the latest ledger line of that trade_date. A date whose
    latest price is missing does not count as a stored session.
    """
    key = symbol_key(symbol)
    day = _text(event_date)[:10]
    by_date: dict[str, tuple[datetime, int, float | None]] = {}
    for index, line in enumerate(lines):
        if symbol_key(line.get("symbol")) != key:
            continue
        trade_date = _text(line.get("trade_date"))[:10]
        if not trade_date or trade_date <= day:
            continue
        stamp = parse_captured_at(line.get("captured_at"))
        if stamp is None:
            continue
        price = _number(line.get("price"))
        current = by_date.get(trade_date)
        if current is None or (stamp, index) >= (current[0], current[1]):
            by_date[trade_date] = (stamp, index, price)
    ordered: list[tuple[str, float]] = []
    for trade_date in sorted(by_date):
        price = by_date[trade_date][2]
        if price is not None and price > 0:
            ordered.append((trade_date, price))
    return ordered


def horizon_returns(session_prices: Sequence[float], t0_price: object) -> dict[str, float | None]:
    """T+N return from the frozen T0 price. Missing sessions stay null."""
    entry = _number(t0_price)
    out: dict[str, float | None] = {
        "t3_return_pct": None,
        "t5_return_pct": None,
        "t10_return_pct": None,
    }
    if entry is None or entry <= 0:
        return out
    for horizon, field in ((3, "t3_return_pct"), (5, "t5_return_pct"), (10, "t10_return_pct")):
        if len(session_prices) < horizon:
            continue
        future = session_prices[horizon - 1]
        if future > 0:
            out[field] = (future / entry - 1.0) * 100.0
    return out


def build_event(
    *,
    symbol: object,
    event_date: str,
    event_timestamp: datetime,
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
    market_real: float,
    scan_fingerprint: str,
    source: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    previous_rs10 = _number(previous.get("rs10"))
    current_rs10 = _number(current.get("rs10"))
    price = _number(current.get("price"))
    if previous_rs10 is None or current_rs10 is None or price is None or price <= 0:
        raise ValueError("event freeze requires previous RS10, current RS10, and a positive T0 price")
    stamp = as_vn(event_timestamp)
    real = _number(market_real)
    if real is None:
        raise ValueError("event freeze requires this run's Market Real")
    return {
        "record_type": "event",
        "schema": SCHEMA_EVENT,
        "event_id": event_id_for(symbol, previous),
        "symbol": symbol_key(symbol),
        "event_date": _text(event_date)[:10],
        "event_timestamp": stamp.isoformat(),
        "t0_price": price,
        "previous_health": _text(previous.get("evolution_health_group")),
        "current_health": _text(current.get("evolution_health_group")),
        "previous_rs10": previous_rs10,
        "current_rs10": current_rs10,
        "delta_rs10": current_rs10 - previous_rs10,
        "vol_confirm": True,
        "market_real_t0": real,
        "previous_observation_id": previous_observation_id(previous),
        "previous_captured_at": _text(previous.get("captured_at")),
        "previous_trade_date": _text(previous.get("trade_date"))[:10],
        "previous_source": _text(previous.get("source")),
        "previous_state_hash": _text(previous.get("state_hash")),
        "current_scan_fingerprint": scan_fingerprint,
        "current_captured_at": stamp.isoformat(),
        "current_source": source,
        "data_mode": DATA_MODE_FORWARD,
        "rs5": _number(current.get("rs5")),
        "rsi14": _number(current.get("rsi14")),
        "market_live": _number(metadata.get("market_live")),
        "market_forecast": _number(metadata.get("market_forecast")),
        "market_regime": _text(metadata.get("market_regime")),
        "breadth": _number(metadata.get("breadth")),
        "market_status": _text(metadata.get("market_status")),
        "market_action": _text(metadata.get("market_action")),
        "evolution_reason": _text(current.get("evolution_reason")),
        "t3_return_pct": None,
        "t5_return_pct": None,
        "t10_return_pct": None,
        "early_recovery_is_buy": EARLY_RECOVERY_IS_BUY,
        "alert_eligible": EARLY_RECOVERY_ALERT_ELIGIBLE,
    }


def candidate_from_row(
    row: Mapping[str, Any],
    previous: Mapping[str, Any],
    market_real: object,
) -> bool:
    price = _number(row.get("price"))
    if price is None or price <= 0:
        return False
    return qualifies_v1(
        previous_health=previous.get("evolution_health_group"),
        current_health=row.get("evolution_health_group"),
        previous_rs10=previous.get("rs10"),
        current_rs10=row.get("rs10"),
        evolution_reason=row.get("evolution_reason"),
        market_real=market_real,
    )
