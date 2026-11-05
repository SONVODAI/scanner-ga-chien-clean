"""Read-only daily close price book for Research Ledger Stage B1.

Reuses existing historical daily closes (research previous_close archive or
explicit unadjusted daily rows). Does not call collectors, KBS, or scanners.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from research.v2_research_ledger.contract import (
    ADJUSTMENT_EXPLICIT_UNADJUSTED,
    ADJUSTMENT_UNAVAILABLE,
)

# Mirror research_market_context labels without importing that package.
SOURCE_VNSTOCK_D1 = "vnstock_d1_bar_before_session"
PRICE_UNIT_INTEGER_VND = "integer_vnd"


def _text(value: object) -> str:
    return str(value or "").strip()


def _symbol(value: object) -> str:
    return _text(value).upper()


def _parse_day(value: object) -> date | None:
    text = _text(value)
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class PriceBook:
    """Verified unadjusted session closes keyed by (symbol, session)."""

    _rows: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._rows)

    def put(
        self,
        *,
        symbol: str,
        session: date | str,
        close: float,
        price_source: str,
        adjustment_status: str = ADJUSTMENT_EXPLICIT_UNADJUSTED,
        is_live_adjusted: bool = False,
        price_ts: str | None = None,
        price_unit: str | None = None,
    ) -> None:
        sym = _symbol(symbol)
        day = session if isinstance(session, date) else _parse_day(session)
        if not sym or day is None or close is None:
            return
        if adjustment_status != ADJUSTMENT_EXPLICIT_UNADJUSTED or is_live_adjusted:
            return
        key = (sym, day.isoformat())
        self._rows[key] = {
            "symbol": sym,
            "session": day.isoformat(),
            "price": float(close),
            "price_source": _text(price_source) or SOURCE_VNSTOCK_D1,
            "adjustment_status": ADJUSTMENT_EXPLICIT_UNADJUSTED,
            "is_live_adjusted": False,
            "price_ts": price_ts or f"{day.isoformat()}T15:00:00+07:00",
            "price_unit": price_unit or PRICE_UNIT_INTEGER_VND,
        }

    def get(self, symbol: str, session: date | str) -> dict[str, Any] | None:
        sym = _symbol(symbol)
        day = session if isinstance(session, date) else _parse_day(session)
        if not sym or day is None:
            return None
        return self._rows.get((sym, day.isoformat()))

    def observation_map(
        self,
        symbol: str,
        sessions: Iterable[date | str],
    ) -> dict[str, dict[str, Any]]:
        """Map ISO session → ledger observation dict (missing sessions omitted)."""
        out: dict[str, dict[str, Any]] = {}
        for session in sessions:
            row = self.get(symbol, session)
            if row is None:
                continue
            key = row["session"]
            out[key] = {
                "price": row["price"],
                "price_source": row["price_source"],
                "adjustment_status": row["adjustment_status"],
                "is_live_adjusted": row["is_live_adjusted"],
                "price_ts": row["price_ts"],
            }
        return out


def load_price_book_from_previous_close(
    path: Path,
    *,
    require_ok_or_stale: bool = True,
) -> PriceBook:
    """Build a book from ``research/market_context_history/previous_close.jsonl``.

    Each archive line stores the close **on** ``previous_close_date`` (T-1 of
    some later session). That close is the trading-session price for that date.
    """
    book = PriceBook()
    if not Path(path).is_file():
        return book
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, Mapping):
            continue
        status = _text(row.get("status")).lower()
        if require_ok_or_stale and status not in {"ok", "stale", ""}:
            continue
        close = _opt_float(row.get("previous_close"))
        day = _parse_day(row.get("previous_close_date"))
        symbol = _symbol(row.get("symbol"))
        if close is None or day is None or not symbol:
            continue
        book.put(
            symbol=symbol,
            session=day,
            close=close,
            price_source=_text(row.get("source")) or SOURCE_VNSTOCK_D1,
            adjustment_status=ADJUSTMENT_EXPLICIT_UNADJUSTED,
            is_live_adjusted=False,
            price_unit=_text(row.get("price_unit")) or PRICE_UNIT_INTEGER_VND,
        )
    return book


def load_price_book_from_daily_rows(
    rows: Sequence[Mapping[str, Any]] | Path,
) -> PriceBook:
    """Load explicit daily closes.

    Accepted keys: symbol, date|session|trade_date, close|price.
    Rows without ``EXPLICIT_UNADJUSTED`` (or with live adjustment) are ignored
    unless adjustment fields are omitted (treated as explicit unadjusted research
    history for Stage B1 fixtures).
    """
    book = PriceBook()
    if isinstance(rows, Path):
        path = Path(rows)
        if not path.is_file():
            return book
        if path.suffix.lower() == ".jsonl":
            parsed: list[Mapping[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, Mapping):
                    parsed.append(item)
            rows = parsed
        else:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        adj = _text(raw.get("adjustment_status"))
        live = raw.get("is_live_adjusted")
        if adj and adj != ADJUSTMENT_EXPLICIT_UNADJUSTED:
            continue
        if live is True:
            continue
        if adj == ADJUSTMENT_UNAVAILABLE:
            continue
        close = _opt_float(raw.get("close") if "close" in raw else raw.get("price"))
        day = _parse_day(raw.get("date") or raw.get("session") or raw.get("trade_date"))
        symbol = _symbol(raw.get("symbol"))
        if close is None or day is None or not symbol:
            continue
        book.put(
            symbol=symbol,
            session=day,
            close=close,
            price_source=_text(raw.get("price_source")) or SOURCE_VNSTOCK_D1,
            adjustment_status=ADJUSTMENT_EXPLICIT_UNADJUSTED,
            is_live_adjusted=False,
            price_ts=_text(raw.get("price_ts")) or None,
            price_unit=_text(raw.get("price_unit")) or PRICE_UNIT_INTEGER_VND,
        )
    return book
