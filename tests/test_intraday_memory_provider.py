"""Regression tests for KBS provider session fetch semantics."""

from __future__ import annotations

from datetime import date

import pytest

from modules.intraday_memory.provider import (
    KBSProvider,
    _filter_records_by_session_date,
    _session_transport_window,
)


def _bar(ts: str, close: float = 22.2) -> dict:
    return {
        "time": ts,
        "open": close,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "volume": 1000,
    }


@pytest.fixture
def kbs_provider(monkeypatch) -> KBSProvider:
    monkeypatch.setattr(
        KBSProvider,
        "_import_quote",
        staticmethod(lambda: type("Quote", (), {})),
    )
    return KBSProvider()


class TestSessionTransportWindow:
    def test_transport_window_matches_live_vps_evidence(self):
        session = date(2026, 8, 14)
        assert _session_transport_window(session) == ("2026-08-13", "2026-08-15")

    def test_filter_keeps_only_requested_session(self):
        session = date(2026, 8, 14)
        records = [
            _bar("2026-08-13 14:45:00"),
            _bar("2026-08-14 09:15:00"),
            _bar("2026-08-14 14:45:00"),
            _bar("2026-08-15 09:15:00"),
        ]
        filtered = _filter_records_by_session_date(records, session)
        assert len(filtered) == 2
        assert all(r["time"].startswith("2026-08-14") for r in filtered)

    def test_filter_empty_when_requested_session_missing(self):
        session = date(2026, 8, 14)
        records = [
            _bar("2026-08-13 14:45:00"),
            _bar("2026-08-15 09:15:00"),
        ]
        assert _filter_records_by_session_date(records, session) == []


class TestKBSProviderFetchSession:
    def test_fetch_session_uses_transport_window_not_same_day(
        self, kbs_provider, monkeypatch
    ):
        session = date(2026, 8, 14)
        calls: list[tuple[str, str, str]] = []

        def fake_fetch(symbol: str, start: str, end: str) -> list[dict]:
            calls.append((symbol, start, end))
            if start == end:
                raise ValueError(
                    "Dữ liệu trống cho mã VCB với interval 5m."
                )
            return [_bar("2026-08-14 09:15:00")]

        monkeypatch.setattr(kbs_provider, "_fetch_with_retry", fake_fetch)
        result = kbs_provider.fetch_session("VCB", session)

        assert calls == [("VCB", "2026-08-13", "2026-08-15")]
        assert len(result) == 1
        assert result[0]["time"] == "2026-08-14 09:15:00"

    def test_fetch_session_filters_adjacent_day_transport_bars(
        self, kbs_provider, monkeypatch
    ):
        session = date(2026, 8, 14)

        def fake_fetch(symbol: str, start: str, end: str) -> list[dict]:
            return [
                _bar("2026-08-13 14:45:00"),
                _bar("2026-08-14 09:15:00"),
                _bar("2026-08-14 14:45:00"),
                _bar("2026-08-15 09:15:00"),
            ]

        monkeypatch.setattr(kbs_provider, "_fetch_with_retry", fake_fetch)
        result = kbs_provider.fetch_session("VCB", session)

        assert len(result) == 2
        assert {r["time"] for r in result} == {
            "2026-08-14 09:15:00",
            "2026-08-14 14:45:00",
        }

    def test_fetch_session_empty_when_requested_day_has_no_bars(
        self, kbs_provider, monkeypatch
    ):
        session = date(2026, 8, 14)

        def fake_fetch(symbol: str, start: str, end: str) -> list[dict]:
            return [_bar("2026-08-13 14:45:00"), _bar("2026-08-15 09:15:00")]

        monkeypatch.setattr(kbs_provider, "_fetch_with_retry", fake_fetch)
        assert kbs_provider.fetch_session("VCB", session) == []

    def test_fetch_range_single_day_delegates_to_session_logic(
        self, kbs_provider, monkeypatch
    ):
        session = date(2026, 8, 14)
        calls: list[tuple[str, str, str]] = []

        def fake_fetch(symbol: str, start: str, end: str) -> list[dict]:
            calls.append((symbol, start, end))
            return [_bar("2026-08-14 09:15:00")]

        monkeypatch.setattr(kbs_provider, "_fetch_with_retry", fake_fetch)
        result = kbs_provider.fetch_range("VCB", session, session)

        assert calls == [("VCB", "2026-08-13", "2026-08-15")]
        assert len(result) == 1

    def test_fetch_range_multi_day_unchanged(self, kbs_provider, monkeypatch):
        calls: list[tuple[str, str, str]] = []

        def fake_fetch(symbol: str, start: str, end: str) -> list[dict]:
            calls.append((symbol, start, end))
            return [
                _bar("2026-08-13 09:15:00"),
                _bar("2026-08-14 09:15:00"),
            ]

        monkeypatch.setattr(kbs_provider, "_fetch_with_retry", fake_fetch)
        result = kbs_provider.fetch_range(
            "VCB", date(2026, 8, 13), date(2026, 8, 14)
        )

        assert calls == [("VCB", "2026-08-13", "2026-08-14")]
        assert len(result) == 2
