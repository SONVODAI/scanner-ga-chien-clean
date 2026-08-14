"""
Mr.BOT Intraday Memory V1A — immutable 5-minute OHLCV foundation.

Data foundation only. No absorption, distribution, or trading logic.
"""

from modules.intraday_memory.config import COLLECTOR_VERSION, IntradayConfig
from modules.intraday_memory.schema import CANONICAL_COLUMNS, CanonicalBar

__all__ = [
    "IntradayCollector",
    "IntradayConfig",
    "CANONICAL_COLUMNS",
    "CanonicalBar",
    "COLLECTOR_VERSION",
]


def __getattr__(name: str):
    if name == "IntradayCollector":
        from modules.intraday_memory.collector import IntradayCollector
        return IntradayCollector
    raise AttributeError(name)
