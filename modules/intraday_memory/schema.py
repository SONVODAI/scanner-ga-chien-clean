"""
Canonical 5-minute bar schema for Mr.BOT Intraday Memory V1A.

Price unit: integer VND (e.g. 22200, not 22.20).
Timezone: Asia/Ho_Chi_Minh for timestamp and session_date.
Primary identity: (symbol, timestamp).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

# Canonical column order for Parquet persistence.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "symbol",
    "timestamp",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "collected_at",
    "quality_flag",
)

# Integer VND price columns.
PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")

# Quality flag values.
QF_OK = "ok"
QF_ATYPICAL_SESSION = "atypical_session"
QF_REJECTED = "rejected"

SOURCE_VNSTOCK_KBS = "vnstock4_kbs"


@dataclass(frozen=True)
class CanonicalBar:
    """One validated canonical 5-minute bar."""

    symbol: str
    timestamp: datetime  # timezone-aware, Asia/Ho_Chi_Minh
    session_date: date
    open: int  # integer VND
    high: int
    low: int
    close: int
    volume: int
    source: str = SOURCE_VNSTOCK_KBS
    collected_at: datetime | None = None
    quality_flag: str = QF_OK

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "session_date": self.session_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "collected_at": self.collected_at or self.timestamp,
            "quality_flag": self.quality_flag,
        }
