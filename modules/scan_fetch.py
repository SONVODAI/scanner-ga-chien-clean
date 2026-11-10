"""Bound scan network calls so a stalled feed cannot hold the page open.

A missed response stays missing. This module does not invent a price.
"""

from __future__ import annotations

import threading
from typing import Callable

import requests

CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 8
LIVE_QUOTE_TIMEOUT_SECONDS = 8
DAILY_ATTEMPTS = 2

_live_lock = threading.Lock()


class TransportTimeout(TimeoutError):
    """The daily feed did not answer inside the deadline."""


class LiveQuoteDeferred(TimeoutError):
    """An optional live quote is still running, or this one missed its deadline."""


def call_with_request_timeout(fn: Callable):
    """Run ``fn`` with a default timeout on ``requests.request``.

    Callers that already pass ``timeout`` keep their own value. A dropped
    connection is tried once. A second timeout is raised and not cached by
    the caller.
    """
    original = requests.request

    def bounded(method, url, **kwargs):
        kwargs.setdefault("timeout", (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS))
        return original(method, url, **kwargs)

    requests.request = bounded
    try:
        last_error: Exception | None = None
        for attempt in range(DAILY_ATTEMPTS):
            try:
                return fn()
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt + 1 >= DAILY_ATTEMPTS:
                    raise TransportTimeout(str(exc)) from exc
        if last_error is not None:
            raise TransportTimeout(str(last_error)) from last_error
        raise TransportTimeout("daily feed did not answer")
    finally:
        requests.request = original


def bounded_yf_download(download: Callable, *, ticker: str, period: str, interval: str, timeout: float = LIVE_QUOTE_TIMEOUT_SECONDS):
    """Download one Yahoo window. A stuck call does not block the next symbol.

    The worker keeps the live-quote lock until it returns. While that lock is
    held, later symbols raise ``LiveQuoteDeferred`` immediately.
    """
    if not _live_lock.acquire(blocking=False):
        raise LiveQuoteDeferred(ticker)

    box: dict = {}

    def run() -> None:
        try:
            box["data"] = download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=timeout,
            )
        except Exception as exc:
            box["error"] = exc
        finally:
            _live_lock.release()

    worker = threading.Thread(target=run, name="live-quote", daemon=True)
    worker.start()
    worker.join(timeout + 0.5)
    if worker.is_alive():
        raise LiveQuoteDeferred(ticker)
    if "error" in box:
        raise box["error"]
    return box.get("data")
