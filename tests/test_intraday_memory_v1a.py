"""Tests for Mr.BOT Intraday Memory V1A data foundation."""

from __future__ import annotations

import importlib
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from modules.intraday_memory.collector import IntradayCollector
from modules.intraday_memory.config import IntradayConfig
from modules.intraday_memory.normalize import (
    PRICE_SCALE_FACTOR,
    normalize_price_to_integer_vnd,
    normalize_volume,
)
from modules.intraday_memory.provider import MockProvider
from modules.intraday_memory.schema import (
    CANONICAL_COLUMNS,
    QF_ATYPICAL_SESSION,
    QF_OK,
    QF_REJECTED,
    CanonicalBar,
)
from modules.intraday_memory.storage import (
    bars_to_dataframe,
    load_session,
    query_session_symbols,
    upsert_session,
)
from modules.intraday_memory.timezone_policy import (
    VN_TZ,
    parse_provider_timestamp,
    session_date_from_timestamp,
)
from modules.intraday_memory.universe import load_production_universe, universe_count
from modules.intraday_memory.validate import detect_duplicates, validate_raw_bar

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_root(tmp_path):
    return tmp_path / "intraday_test"


@pytest.fixture
def sample_raw_hpg():
    return {
        "time": "2026-08-13 09:15:00",
        "open": 22.20,
        "high": 22.25,
        "low": 22.15,
        "close": 22.20,
        "volume": 131500,
    }


@pytest.fixture
def sample_canonical_hpg(sample_raw_hpg):
    outcome = validate_raw_bar("HPG", sample_raw_hpg)
    assert outcome.accepted
    return outcome.bar


def _make_bar(
    symbol: str,
    ts: str,
    open_kbs: float = 22.20,
    **kwargs,
) -> dict:
    return {
        "time": ts,
        "open": open_kbs,
        "high": kwargs.get("high", open_kbs + 0.05),
        "low": kwargs.get("low", open_kbs - 0.05),
        "close": kwargs.get("close", open_kbs),
        "volume": kwargs.get("volume", 1000),
    }


# ---------------------------------------------------------------------------
# 1. Price normalization
# ---------------------------------------------------------------------------

class TestPriceNormalization:
    def test_kbs_thousands_to_integer_vnd(self):
        assert normalize_price_to_integer_vnd(22.20) == 22200
        assert normalize_price_to_integer_vnd(22.15) == 22150

    def test_legacy_integer_passthrough(self):
        assert normalize_price_to_integer_vnd(22200) == 22200

    def test_scale_factor_documented(self):
        assert PRICE_SCALE_FACTOR == 1000

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError):
            normalize_price_to_integer_vnd(0)
        with pytest.raises(ValueError):
            normalize_price_to_integer_vnd(-1)

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            normalize_price_to_integer_vnd(float("nan"))


# ---------------------------------------------------------------------------
# 2. Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_canonical_columns(self):
        assert "symbol" in CANONICAL_COLUMNS
        assert "timestamp" in CANONICAL_COLUMNS
        assert "open" in CANONICAL_COLUMNS
        assert len(CANONICAL_COLUMNS) == 11

    def test_canonical_bar_types(self, sample_canonical_hpg):
        bar = sample_canonical_hpg
        assert isinstance(bar.open, int)
        assert isinstance(bar.high, int)
        assert isinstance(bar.close, int)
        assert bar.open == 22200


# ---------------------------------------------------------------------------
# 3. Timezone
# ---------------------------------------------------------------------------

class TestTimezone:
    def test_naive_timestamp_localized_to_vn(self):
        ts = parse_provider_timestamp("2026-08-13 09:15:00")
        assert ts.tzinfo == VN_TZ
        assert ts.hour == 9
        assert ts.minute == 15

    def test_session_date_from_vn_timestamp(self):
        ts = parse_provider_timestamp("2026-08-13 09:15:00")
        assert session_date_from_timestamp(ts) == date(2026, 8, 13)

    def test_utc_timestamp_converts_without_date_shift(self):
        # 02:15 UTC on Aug 13 = 09:15 VN — same session date
        ts = parse_provider_timestamp("2026-08-13T02:15:00+00:00")
        assert session_date_from_timestamp(ts) == date(2026, 8, 13)
        assert ts.astimezone(VN_TZ).hour == 9


# ---------------------------------------------------------------------------
# 4–6. Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_ohlc_validation(self, sample_raw_hpg):
        outcome = validate_raw_bar("HPG", sample_raw_hpg)
        assert outcome.accepted
        assert outcome.quality_flag == QF_OK

    def test_negative_volume_rejected(self, sample_raw_hpg):
        bad = {**sample_raw_hpg, "volume": -100}
        outcome = validate_raw_bar("HPG", bad)
        assert not outcome.accepted
        assert outcome.quality_flag == QF_REJECTED

    def test_impossible_ohlc_rejected(self, sample_raw_hpg):
        bad = {**sample_raw_hpg, "high": 10.0, "low": 50.0}
        outcome = validate_raw_bar("HPG", bad)
        assert not outcome.accepted

    def test_duplicate_detection(self, sample_canonical_hpg):
        bar2 = CanonicalBar(
            symbol=sample_canonical_hpg.symbol,
            timestamp=sample_canonical_hpg.timestamp,
            session_date=sample_canonical_hpg.session_date,
            open=22200, high=22250, low=22150, close=22200,
            volume=100,
        )
        dups = detect_duplicates([sample_canonical_hpg, bar2])
        assert len(dups) == 1

    def test_atypical_upcom_session_not_rejected(self):
        # UPCOM may have bars to 15:00 — valid, not rejected
        raw = _make_bar("TVN", "2026-08-13 15:00:00", open_kbs=9.39)
        outcome = validate_raw_bar("TVN", raw)
        assert outcome.accepted
        assert outcome.quality_flag in (QF_OK, QF_ATYPICAL_SESSION)

    def test_hnx_0900_start_not_rejected(self):
        raw = _make_bar("SHS", "2026-08-13 09:00:00", open_kbs=16.28)
        outcome = validate_raw_bar("SHS", raw)
        assert outcome.accepted


# ---------------------------------------------------------------------------
# 7–10. Storage idempotency & reconciliation
# ---------------------------------------------------------------------------

class TestStorage:
    def test_storage_round_trip(self, tmp_data_root, sample_canonical_hpg):
        session = date(2026, 8, 13)
        upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        loaded = load_session(tmp_data_root, session)
        assert len(loaded) == 1
        assert int(loaded.iloc[0]["open"]) == 22200
        assert int(loaded.iloc[0]["volume"]) == 131500

    def test_idempotent_repeated_collection(self, tmp_data_root, sample_canonical_hpg):
        session = date(2026, 8, 13)
        r1 = upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        r2 = upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        assert r1.new == 1
        assert r2.new == 0
        assert r2.existing == 1
        loaded = load_session(tmp_data_root, session)
        assert len(loaded) == 1

    def test_same_session_twice_no_duplicate_rows(self, tmp_data_root, sample_canonical_hpg):
        session = date(2026, 8, 13)
        upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        assert len(load_session(tmp_data_root, session)) == 1

    def test_reconciliation_detects_changed_bar(self, tmp_data_root, sample_canonical_hpg):
        session = date(2026, 8, 13)
        upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        changed = CanonicalBar(
            symbol="HPG",
            timestamp=sample_canonical_hpg.timestamp,
            session_date=session,
            open=22300, high=22350, low=22250, close=22300,
            volume=131500,
        )
        result = upsert_session(
            tmp_data_root, session, [changed], reconcile=True
        )
        assert result.changed == 1
        loaded = load_session(tmp_data_root, session)
        assert int(loaded.iloc[0]["open"]) == 22200  # canonical preserved

    def test_reconciliation_detects_new_bar(self, tmp_data_root, sample_canonical_hpg):
        session = date(2026, 8, 13)
        upsert_session(tmp_data_root, session, [sample_canonical_hpg])
        new_bar = validate_raw_bar(
            "HPG", _make_bar("HPG", "2026-08-13 09:20:00")
        ).bar
        result = upsert_session(tmp_data_root, session, [new_bar])
        assert result.new == 1
        assert len(load_session(tmp_data_root, session)) == 2


# ---------------------------------------------------------------------------
# 11–12. Collector integration with mock provider
# ---------------------------------------------------------------------------

class TestCollector:
    def _collector_with_mock(
        self, tmp_data_root, data: dict, failed: set | None = None
    ) -> IntradayCollector:
        provider = MockProvider(data)
        if failed:
            provider.failed_symbols = failed
        config = IntradayConfig(data_root=tmp_data_root, app_py_path=APP_PY)
        return IntradayCollector(config=config, provider=provider)

    def test_collect_session(self, tmp_data_root):
        session = date(2026, 8, 13)
        data = {
            ("HPG", "2026-08-13"): [_make_bar("HPG", "2026-08-13 09:15:00")],
            ("VNM", "2026-08-13"): [_make_bar("VNM", "2026-08-13 09:15:00", 62.0)],
        }
        collector = self._collector_with_mock(tmp_data_root, data)
        manifest = collector.collect_session(session, symbols=["HPG", "VNM"])
        assert len(manifest.symbols_success) == 2
        assert manifest.bars_valid == 2
        assert len(load_session(tmp_data_root, session)) == 2

    def test_one_symbol_failure_does_not_corrupt_others(self, tmp_data_root):
        session = date(2026, 8, 13)
        data = {
            ("HPG", "2026-08-13"): [_make_bar("HPG", "2026-08-13 09:15:00")],
        }
        collector = self._collector_with_mock(
            tmp_data_root, data, failed={"BADSYM"}
        )
        manifest = collector.collect_session(
            session, symbols=["HPG", "BADSYM"]
        )
        assert "HPG" in manifest.symbols_success
        assert "BADSYM" in manifest.symbols_failed
        assert len(load_session(tmp_data_root, session)) == 1

    def test_idempotent_collect_twice(self, tmp_data_root):
        session = date(2026, 8, 13)
        data = {
            ("HPG", "2026-08-13"): [_make_bar("HPG", "2026-08-13 09:15:00")],
        }
        collector = self._collector_with_mock(tmp_data_root, data)
        m1 = collector.collect_session(session, symbols=["HPG"])
        m2 = collector.collect_session(session, symbols=["HPG"])
        assert m1.bars_new == 1
        assert m2.bars_new == 0
        assert m2.bars_existing == 1

    def test_reconcile_path(self, tmp_data_root):
        session = date(2026, 8, 13)
        data = {
            ("HPG", "2026-08-13"): [
                _make_bar("HPG", "2026-08-13 09:15:00"),
                _make_bar("HPG", "2026-08-13 09:20:00"),
            ],
        }
        collector = self._collector_with_mock(tmp_data_root, data)
        collector.collect_session(session, symbols=["HPG"])
        # Reconcile with only one bar — should detect missing
        partial_data = {
            ("HPG", "2026-08-13"): [_make_bar("HPG", "2026-08-13 09:15:00")],
        }
        collector2 = self._collector_with_mock(tmp_data_root, partial_data)
        manifest, report = collector2.reconcile(session, symbols=["HPG"])
        assert report["comparison"]["stable"] >= 1


# ---------------------------------------------------------------------------
# 13. Universe
# ---------------------------------------------------------------------------

class TestUniverse:
    def test_loads_142_symbols_from_app_py(self):
        assert universe_count(APP_PY) == 142

    def test_no_streamlit_import_for_universe(self):
        mods_before = set(sys.modules.keys())
        syms = load_production_universe(APP_PY)
        assert len(syms) == 142
        assert "streamlit" not in sys.modules or "streamlit" in mods_before


# ---------------------------------------------------------------------------
# 14. No Streamlit in collector core
# ---------------------------------------------------------------------------

class TestNoStreamlitDependency:
    def test_collector_modules_do_not_import_streamlit(self):
        modules = [
            "modules.intraday_memory.collector",
            "modules.intraday_memory.storage",
            "modules.intraday_memory.validate",
            "modules.intraday_memory.provider",
            "modules.intraday_memory.universe",
        ]
        for mod_name in modules:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
        for mod_name in modules:
            importlib.import_module(mod_name)
        assert "streamlit" not in sys.modules
