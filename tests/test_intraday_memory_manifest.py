"""Focused tests for V1B-2 pre-deployment manifest observability."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from modules.intraday_memory.collector import IntradayCollector
from modules.intraday_memory.config import IntradayConfig, detect_tier
from modules.intraday_memory.manifest import (
    STATUS_FAILED,
    STATUS_NOT_READY,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    compute_final_status,
)
from modules.intraday_memory.provider import MockProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _make_bar(symbol: str, ts: str, open_kbs: float = 22.20) -> dict:
    return {
        "time": ts,
        "open": open_kbs,
        "high": open_kbs + 0.05,
        "low": open_kbs - 0.05,
        "close": open_kbs,
        "volume": 1000,
    }


def _collector(
    tmp_data_root: Path,
    data: dict,
    *,
    rpm: int = 18,
    failed: set[str] | None = None,
) -> IntradayCollector:
    provider = MockProvider(data)
    if failed:
        provider.failed_symbols = failed
    config = IntradayConfig(
        data_root=tmp_data_root,
        app_py_path=APP_PY,
        requests_per_minute=rpm,
    )
    return IntradayCollector(config=config, provider=provider)


class TestManifestObservability:
    def test_successful_run_writes_final_status_success(self, tmp_path):
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data, rpm=60)
        manifest = collector.collect_session(session, symbols=["VCB"])

        assert manifest.final_status == STATUS_SUCCESS
        assert manifest.tier in ("guest", "community")
        assert manifest.requests_per_minute == 60
        assert manifest.duration_sec >= 0.0
        assert manifest.per_symbol_summary == []

        saved_path = tmp_path / "manifests" / f"{manifest.run_id}.json"
        saved = json.loads(saved_path.read_text())
        assert saved["final_status"] == "SUCCESS"
        assert saved["duration_sec"] >= 0

    def test_tier_is_guest_when_no_community_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VNSTOCK_API_KEY", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        assert detect_tier() == "guest"

    def test_community_mode_records_tier_without_exposing_secret(
        self, tmp_path, monkeypatch
    ):
        secret = "super-secret-community-key-xyz"
        monkeypatch.setenv("VNSTOCK_API_KEY", secret)
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data, rpm=30)
        manifest = collector.collect_session(session, symbols=["VCB"])

        assert manifest.tier == "community"
        blob = json.dumps(manifest.to_dict())
        assert secret not in blob
        assert "api_key" not in blob.lower()

    def test_requests_per_minute_recorded(self, tmp_path):
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data, rpm=42)
        manifest = collector.collect_session(session, symbols=["VCB"])
        assert manifest.requests_per_minute == 42

    def test_duration_sec_non_negative(self, tmp_path):
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data)
        manifest = collector.collect_session(session, symbols=["VCB"])
        assert isinstance(manifest.duration_sec, float)
        assert manifest.duration_sec >= 0.0

    def test_failed_symbol_in_per_symbol_summary(self, tmp_path):
        session = date(2026, 8, 13)
        collector = _collector(tmp_path, {}, failed={"BAD"})
        manifest = collector.collect_session(session, symbols=["BAD"])

        assert manifest.final_status == STATUS_FAILED
        assert len(manifest.per_symbol_summary) == 1
        entry = manifest.per_symbol_summary[0]
        assert entry["symbol"] == "BAD"
        assert entry["status"] == "failed"
        assert "Simulated provider failure" in entry["reason"]
        assert entry["bars_fetched"] == 0
        assert entry["bars_valid"] == 0
        assert entry["bars_rejected"] == 0

    def test_api_key_never_in_serialized_manifest(self, tmp_path, monkeypatch):
        secret = "must-not-leak-abc123"
        monkeypatch.setenv("VNSTOCK_API_KEY", secret)
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data)
        collector.collect_session(session, symbols=["VCB"])

        for path in tmp_path.rglob("*.json"):
            assert secret not in path.read_text()

    def test_v1a_idempotency_unchanged(self, tmp_path):
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data)
        first = collector.collect_session(session, symbols=["VCB"])
        second = collector.collect_session(session, symbols=["VCB"])

        assert first.bars_new == 1
        assert second.bars_new == 0
        assert second.bars_existing == 1
        assert second.final_status == STATUS_SUCCESS

    def test_manifest_backward_compatible_fields(self, tmp_path):
        session = date(2026, 8, 13)
        data = {("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")]}
        collector = _collector(tmp_path, data)
        manifest = collector.collect_session(session, symbols=["VCB"])

        d = manifest.to_dict()
        for legacy in (
            "mode",
            "requested_session",
            "started_at",
            "finished_at",
            "universe_count",
            "symbols_success",
            "symbols_failed",
            "bars_fetched",
            "bars_valid",
            "bars_rejected",
            "bars_new",
            "bars_existing",
            "bars_changed",
            "duplicate_count",
            "provider",
            "collector_version",
            "storage_root",
        ):
            assert legacy in d


class TestComputeFinalStatus:
    def test_not_ready_systematic_empty(self):
        assert (
            compute_final_status(
                universe_count=3,
                symbols_failed={},
                bars_valid=0,
                bars_fetched=0,
                per_symbol_summary=[
                    {"symbol": "A", "status": "empty", "reason": "no_rows_returned"},
                ],
            )
            == STATUS_NOT_READY
        )

    def test_partial_mixed(self):
        assert (
            compute_final_status(
                universe_count=3,
                symbols_failed={"BAD": "RuntimeError: boom"},
                bars_valid=100,
                bars_fetched=100,
                per_symbol_summary=[
                    {"symbol": "BAD", "status": "failed", "reason": "boom"},
                ],
            )
            == STATUS_PARTIAL
        )


class TestReconcileObservability:
    def test_reconcile_writes_observability_fields(self, tmp_path):
        session = date(2026, 8, 13)
        data = {
            ("VCB", "2026-08-13"): [
                _make_bar("VCB", "2026-08-13 09:15:00"),
                _make_bar("VCB", "2026-08-13 09:20:00"),
            ],
        }
        collector = _collector(tmp_path, data, rpm=25)
        collector.collect_session(session, symbols=["VCB"])

        partial = {
            ("VCB", "2026-08-13"): [_make_bar("VCB", "2026-08-13 09:15:00")],
        }
        collector2 = _collector(tmp_path, partial, rpm=25)
        manifest, _report = collector2.reconcile(session, symbols=["VCB"])

        assert manifest.final_status == STATUS_SUCCESS
        assert manifest.requests_per_minute == 25
        assert manifest.duration_sec >= 0.0
        assert manifest.tier in ("guest", "community")
