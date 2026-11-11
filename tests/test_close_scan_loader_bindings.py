"""The headless close loader must call the production scan-fetch helpers.

Import lines in app.py are not part of the extracted module. Without the
bindings, download_symbol_data raises NameError: TransportTimeout and never
reaches historical data. That is the guardian-close run #2 failure.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types

import pandas as pd
import requests

from modules.close_session_scan import load_production_scan_api
from modules.scan_fetch import (
    LiveQuoteDeferred,
    TransportTimeout,
    bounded_yf_download,
    call_with_request_timeout,
)
from tests.test_guardian_close_workflow_gate import (
    SEALED,
    SEALED_CONTENT_SHA256,
    SEALED_FILE_SHA256,
)

HELPERS = {
    "call_with_request_timeout": call_with_request_timeout,
    "TransportTimeout": TransportTimeout,
    "bounded_yf_download": bounded_yf_download,
    "LiveQuoteDeferred": LiveQuoteDeferred,
}


def _history():
    return pd.DataFrame({
        "time": ["2026-11-07", "2026-11-10"],
        "open": [20.0, 21.0],
        "high": [22.0, 23.0],
        "low": [19.0, 20.0],
        "close": [21.0, 22.5],
        "volume": [1000, 1100],
    })


def _install_history(monkeypatch, fn):
    module = types.ModuleType("vnstock")
    module.stock_historical_data = fn
    monkeypatch.setitem(sys.modules, "vnstock", module)


def test_missing_bindings_reproduce_the_original_transport_timeout_name_error(monkeypatch):
    api = load_production_scan_api()
    for name in HELPERS:
        api.pop(name)
    called = []

    def stock_historical_data(**kwargs):
        called.append(kwargs.get("symbol"))
        return _history()

    _install_history(monkeypatch, stock_historical_data)
    try:
        api["download_symbol_data"]("HPG")
    except NameError as exc:
        message = str(exc)
    else:
        raise AssertionError("unbound loader returned a frame")
    assert message == "name 'TransportTimeout' is not defined"
    assert called == []


def test_loaded_download_reaches_mocked_historical_data(monkeypatch):
    api = load_production_scan_api()
    seen = []

    def stock_historical_data(**kwargs):
        seen.append(kwargs)
        return _history()

    _install_history(monkeypatch, stock_historical_data)
    frame = api["download_symbol_data"]("HPG")
    assert seen[0]["symbol"] == "HPG"
    assert seen[0]["resolution"] == "1D"
    assert seen[0]["type"] == "stock"
    assert list(frame["close"]) == [21.0, 22.5]
    assert list(frame["date"].dt.strftime("%Y-%m-%d")) == ["2026-11-07", "2026-11-10"]


def test_scan_fetch_helpers_are_the_production_objects():
    api = load_production_scan_api()
    for name, production in HELPERS.items():
        assert api[name] is production
        assert api["download_symbol_data"].__globals__[name] is production
        assert api["fetch_live_price"].__globals__[name] is production


def test_loaded_download_keeps_timeout_and_generic_error_behavior(monkeypatch):
    api = load_production_scan_api()
    attempts = []

    def timed_out(**_kwargs):
        attempts.append("attempt")
        raise requests.Timeout("slow")

    _install_history(monkeypatch, timed_out)
    try:
        api["download_symbol_data"]("HPG")
    except TransportTimeout:
        refused = True
    else:
        refused = False
    assert refused
    assert len(attempts) == 2

    def broken(**_kwargs):
        raise RuntimeError("invalid symbol")

    _install_history(monkeypatch, broken)
    assert api["download_symbol_data"]("HPG").empty


def test_loaded_live_quote_uses_the_production_fetcher_and_reraises_deferral():
    api = load_production_scan_api()
    seen = []

    def download(*_args, **kwargs):
        seen.append(kwargs["ticker"] if "ticker" in kwargs else _args[0])
        return pd.DataFrame(
            {"Close": [26.5], "Volume": [1000.0]},
            index=pd.to_datetime(["2026-11-10 14:45"]),
        )

    api["yf"] = types.SimpleNamespace(download=download)
    quote = api["fetch_live_price"]("HPG")
    assert seen == ["HPG.VN"]
    assert quote["source"] == "YF_15M"
    assert quote["price"] == 26.5

    def deferred(*_args, **kwargs):
        raise LiveQuoteDeferred(kwargs["ticker"])

    api["bounded_yf_download"] = deferred
    try:
        api["fetch_live_price"]("HPG")
    except LiveQuoteDeferred as exc:
        assert str(exc) == "HPG.VN"
    else:
        raise AssertionError("deferred live quote was swallowed")


def test_sealed_2026_11_06_hashes_stay_unchanged():
    raw = SEALED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEALED_FILE_SHA256
    assert json.loads(raw)["content_sha256"] == SEALED_CONTENT_SHA256
