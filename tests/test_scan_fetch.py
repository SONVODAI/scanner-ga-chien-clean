"""Stalled scan feeds must give up. A missed quote is not a live price."""

import threading
import time

import pandas as pd
import requests

from modules.scan_fetch import (
    LiveQuoteDeferred,
    TransportTimeout,
    bounded_yf_download,
    call_with_request_timeout,
)


def test_daily_request_uses_a_short_timeout_and_retries_once(monkeypatch):
    calls = []

    def fake(method, url, **kwargs):
        calls.append(kwargs.get("timeout"))
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "request", fake)
    try:
        call_with_request_timeout(lambda: requests.request("GET", "https://example.test"))
    except TransportTimeout:
        refused = True
    else:
        refused = False
    assert refused
    assert calls == [(3.05, 8), (3.05, 8)]


def test_explicit_request_timeout_is_kept(monkeypatch):
    calls = []

    def fake(method, url, **kwargs):
        calls.append(kwargs.get("timeout"))
        return "ok"

    monkeypatch.setattr(requests, "request", fake)
    assert call_with_request_timeout(lambda: requests.request("GET", "https://example.test", timeout=1)) == "ok"
    assert calls == [1]


def test_live_quote_deadline_does_not_block_the_next_symbol():
    release = threading.Event()

    def download(*_args, **kwargs):
        assert kwargs["timeout"] == 0.05
        assert kwargs["threads"] is False
        release.wait(2)
        return pd.DataFrame({"Close": [1.0]})

    started = time.perf_counter()
    try:
        bounded_yf_download(download, ticker="ACV.VN", period="1d", interval="15m", timeout=0.05)
    except LiveQuoteDeferred:
        deferred = True
    else:
        deferred = False
    assert deferred
    assert time.perf_counter() - started < 1.5

    started = time.perf_counter()
    try:
        bounded_yf_download(download, ticker="BVS.VN", period="1d", interval="15m", timeout=5)
    except LiveQuoteDeferred:
        skipped = True
    else:
        skipped = False
    assert skipped
    assert time.perf_counter() - started < 0.5
    release.set()
    deadline = time.perf_counter() + 2
    while time.perf_counter() < deadline:
        if bounded_yf_download.__globals__["_live_lock"].acquire(blocking=False):
            bounded_yf_download.__globals__["_live_lock"].release()
            return
        time.sleep(0.02)
    raise AssertionError("live quote lock was not released")


def test_live_quote_returns_when_the_feed_answers():
    def download(*_args, **kwargs):
        return pd.DataFrame({"Close": [12.5]})

    frame = bounded_yf_download(download, ticker="HPG.VN", period="1d", interval="15m", timeout=1)
    assert list(frame["Close"]) == [12.5]
