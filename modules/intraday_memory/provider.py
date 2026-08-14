"""
KBS provider adapter via vnstock 4.x.

Isolated from Legacy vnstock 0.2.9.2 used by app.py.
Supports VNSTOCK_API_KEY via environment variable.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ProviderAdapter(Protocol):
    """Protocol for intraday OHLCV providers."""

    def fetch_session(
        self, symbol: str, session_date: date
    ) -> list[dict[str, Any]]: ...

    def fetch_range(
        self, symbol: str, start: date, end: date
    ) -> list[dict[str, Any]]: ...


class KBSProvider:
    """
    vnstock 4.x Quote adapter with source='KBS'.

    Requires vnstock >= 4.0 installed in the collector environment.
    """

    SOURCE = "KBS"

    def __init__(
        self,
        *,
        requests_per_minute: int = 18,
        max_retries: int = 3,
        retry_base_delay: float = 2.0,
    ) -> None:
        self.requests_per_minute = max(1, requests_per_minute)
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self._min_interval = 60.0 / self.requests_per_minute
        self._last_request_at = 0.0
        self._quote_cls = self._import_quote()

    @staticmethod
    def _import_quote() -> Any:
        try:
            from vnstock.api.quote import Quote  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "vnstock 4.x is required for the intraday collector. "
                "Install with: pip install -r requirements-collector.txt"
            ) from exc
        return Quote

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _fetch_with_retry(
        self, symbol: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                df = self._quote_cls(
                    symbol=symbol, source=self.SOURCE
                ).history(start=start, end=end, interval="5m")
                if df is None or df.empty:
                    return []
                df = df.copy()
                df.columns = [str(c).lower() for c in df.columns]
                records: list[dict[str, Any]] = []
                for _, row in df.iterrows():
                    records.append(
                        {
                            "time": row.get("time"),
                            "open": row.get("open"),
                            "high": row.get("high"),
                            "low": row.get("low"),
                            "close": row.get("close"),
                            "volume": row.get("volume"),
                        }
                    )
                return records
            except Exception as exc:
                last_error = exc
                msg = str(exc).lower()
                transient = any(
                    token in msg
                    for token in ("rate limit", "timeout", "connection", "503", "502")
                )
                if not transient or attempt >= self.max_retries - 1:
                    raise
                delay = self.retry_base_delay * (2 ** attempt)
                logger.warning(
                    "Retry %s/%s for %s after %s (sleep %.1fs)",
                    attempt + 1,
                    self.max_retries,
                    symbol,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)
        raise last_error or RuntimeError(f"Fetch failed for {symbol}")

    def fetch_session(
        self, symbol: str, session_date: date
    ) -> list[dict[str, Any]]:
        day = session_date.isoformat()
        return self._fetch_with_retry(symbol, day, day)

    def fetch_range(
        self, symbol: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        return self._fetch_with_retry(
            symbol, start.isoformat(), end.isoformat()
        )


class MockProvider:
    """In-memory provider for unit tests."""

    def __init__(self, data: dict[tuple[str, str], list[dict[str, Any]]] | None = None):
        self.data = data or {}
        self.call_count = 0
        self.failed_symbols: set[str] = set()

    def fetch_session(
        self, symbol: str, session_date: date
    ) -> list[dict[str, Any]]:
        self.call_count += 1
        if symbol in self.failed_symbols:
            raise RuntimeError(f"Simulated provider failure for {symbol}")
        return list(self.data.get((symbol, session_date.isoformat()), []))

    def fetch_range(
        self, symbol: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        key_prefix = symbol
        for (sym, day), bars in self.data.items():
            if sym != key_prefix:
                continue
            if start.isoformat() <= day <= end.isoformat():
                out.extend(bars)
        return out
