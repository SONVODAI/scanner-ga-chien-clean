"""Phase 1 Market T0 snapshot preservation tests."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modules.market_t0_capture import (
    CANONICAL_RULE,
    ELIGIBLE_AFTER,
    MARKET_CLOSE_REFERENCE,
    MARKET_DAILY_T0_FILE,
    MARKET_ENTITY,
    MARKET_T0_SNAPSHOT_FILE,
    append_market_daily_t0,
    append_market_t0_snapshot,
    build_market_daily_t0_row,
    build_market_t0_row,
    capture_market_t0_snapshot,
    daily_snapshot_id,
    is_canonical_eligible,
    market_snapshot_id,
    validate_canonical_trade_date,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _vn_dt(hour: int, minute: int, trade_date: str = "2026-08-12") -> datetime:
    return datetime.strptime(trade_date, "%Y-%m-%d").replace(
        hour=hour, minute=minute, second=0, tzinfo=VN_TZ
    )


def _sample_scan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "group": "PULL ĐẸP",
                "price": 10.0,
                "rsi14": 55.0,
                "E": 1,
                "R": 1,
                "O": 1,
                "S": 1,
                "total_score": 80,
                "ema9_ma20_slope": 1.2,
                "obv_status": "🟢",
                "is_live_adjusted": True,
            },
            {
                "symbol": "BBB",
                "group": "CP MẠNH",
                "price": 20.0,
                "rsi14": 62.0,
                "E": 1,
                "R": 0,
                "O": 1,
                "S": 0,
                "total_score": 75,
                "ema9_ma20_slope": 0.5,
                "obv_status": "🟢",
                "is_live_adjusted": True,
            },
        ]
    )


def _breadth_report() -> dict:
    return {
        "total": 2,
        "counts": {60: 1, 50: 2, 40: 2, 30: 2, 20: 2, 10: 2},
        "percentages": {60: 50.0, 50: 100.0, 40: 100.0, 30: 100.0, 20: 100.0, 10: 100.0},
        "score": 100,
        "level": "RẤT KHỎE",
    }


def _row_kwargs(**overrides):
    base = dict(
        scan_df=_sample_scan(),
        trade_date="2026-08-12",
        market_real=9.0,
        market_live=7.5,
        market_forecast=6.0,
        market_forecast_text="Forecast text",
        market_confidence=72.0,
        market_status="🟢 THỊ TRƯỜNG KHỎE",
        market_action="✅ Có thể vào tiền",
        market_regime="🟢 MÙA XUÂN",
        market_regime_note="Market khỏe",
        rsi_breadth_report=_breadth_report(),
        trading_today=True,
        trading_reason="ok",
        include_vnindex_ohlcv=False,
    )
    base.update(overrides)
    return base


class BuildMarketT0RowTests(unittest.TestCase):
    def test_core_fields_present(self):
        row = build_market_t0_row(**_row_kwargs())
        for field in (
            "market_snapshot_id",
            "trade_date",
            "entity",
            "session_slot",
            "snapshot_version",
            "captured_at",
            "market_real",
            "market_live",
            "market_forecast",
            "market_regime",
            "breadth_score",
            "ga_tang_toc",
            "cp_manh",
            "obv_green_pct",
        ):
            self.assertIn(field, row)
        self.assertEqual(row["entity"], MARKET_ENTITY)
        self.assertAlmostEqual(float(row["market_real"]), 9.0)
        self.assertAlmostEqual(float(row["breadth_score"]), 100.0)

    def test_missing_optional_technical_fields_do_not_crash(self):
        row = build_market_t0_row(**_row_kwargs(include_vnindex_ohlcv=False))
        self.assertTrue(pd.isna(row.get("vnindex_close")))
        self.assertEqual(row.get("tf_daily_status"), "")


class AppendMarketT0SnapshotTests(unittest.TestCase):
    def test_first_write_wins_same_identity(self):
        row = build_market_t0_row(**_row_kwargs())
        df = pd.DataFrame([row])
        first, added1 = append_market_t0_snapshot(pd.DataFrame(), df)
        self.assertEqual(added1, 1)

        changed = row.copy()
        changed["market_real"] = 99.0
        second, added2 = append_market_t0_snapshot(first, pd.DataFrame([changed]))
        self.assertEqual(added2, 0)
        self.assertAlmostEqual(float(second.iloc[0]["market_real"]), 9.0)

    def test_new_trading_day_appends_new_row(self):
        row_a = build_market_t0_row(**_row_kwargs(trade_date="2026-08-10"))
        row_b = build_market_t0_row(**_row_kwargs(trade_date="2026-08-12"))
        merged, added1 = append_market_t0_snapshot(
            pd.DataFrame(),
            pd.DataFrame([row_a]),
        )
        merged, added2 = append_market_t0_snapshot(
            merged,
            pd.DataFrame([row_b]),
        )
        self.assertEqual(added1, 1)
        self.assertEqual(added2, 1)
        self.assertEqual(len(merged), 2)

    def test_snapshot_id_deterministic(self):
        sid = market_snapshot_id("2026-08-12", MARKET_ENTITY, "MORNING")
        self.assertEqual(len(sid), 16)
        self.assertEqual(sid, market_snapshot_id("2026-08-12", MARKET_ENTITY, "MORNING"))


class CanonicalEligibilityTests(unittest.TestCase):
    def test_1759_not_eligible(self):
        self.assertFalse(is_canonical_eligible(_vn_dt(17, 59)))

    def test_1800_eligible(self):
        self.assertTrue(is_canonical_eligible(_vn_dt(18, 0)))

    def test_1801_eligible(self):
        self.assertTrue(is_canonical_eligible(_vn_dt(18, 1)))

    def test_trade_date_mismatch_rejected(self):
        ok, reason = validate_canonical_trade_date(
            "2026-08-11",
            now=_vn_dt(20, 0, "2026-08-12"),
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "TRADE_DATE_MISMATCH")


class CanonicalDailyRowTests(unittest.TestCase):
    def test_daily_row_metadata(self):
        session = build_market_t0_row(
            **_row_kwargs(now=_vn_dt(18, 3)),
        )
        daily = build_market_daily_t0_row(session, now=_vn_dt(18, 3))
        self.assertTrue(daily["canonical_t0"])
        self.assertEqual(daily["canonical_rule"], CANONICAL_RULE)
        self.assertEqual(daily["market_close_reference"], MARKET_CLOSE_REFERENCE)
        self.assertEqual(daily["eligible_after"], ELIGIBLE_AFTER)
        self.assertEqual(daily["entity"], MARKET_ENTITY)
        self.assertNotIn("market_snapshot_id", daily)

    def test_daily_snapshot_id_ignores_session_slot(self):
        morning = build_market_t0_row(
            **_row_kwargs(now=_vn_dt(10, 0)),
        )
        evening = build_market_t0_row(
            **_row_kwargs(now=_vn_dt(21, 30)),
        )
        daily_m = build_market_daily_t0_row(morning)
        daily_e = build_market_daily_t0_row(evening)
        expected = daily_snapshot_id("2026-08-12", MARKET_ENTITY)
        self.assertEqual(daily_m["daily_snapshot_id"], expected)
        self.assertEqual(daily_e["daily_snapshot_id"], expected)
        self.assertNotEqual(
            morning["market_snapshot_id"],
            evening["market_snapshot_id"],
        )

    def test_append_daily_first_write_wins(self):
        session = build_market_t0_row(**_row_kwargs(now=_vn_dt(18, 1)))
        daily = build_market_daily_t0_row(session, now=_vn_dt(18, 1))
        merged, added1 = append_market_daily_t0(pd.DataFrame(), pd.DataFrame([daily]))
        self.assertEqual(added1, 1)

        changed = daily.copy()
        changed["market_real"] = 88.0
        merged2, added2 = append_market_daily_t0(merged, pd.DataFrame([changed]))
        self.assertEqual(added2, 0)
        self.assertAlmostEqual(float(merged2.iloc[0]["market_real"]), 9.0)


class CaptureMarketT0SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "earning_learning"
        self.data_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_session_store(self) -> pd.DataFrame:
        path = self.data_dir / MARKET_T0_SNAPSHOT_FILE
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    def _read_daily_store(self) -> pd.DataFrame:
        path = self.data_dir / MARKET_DAILY_T0_FILE
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    def test_first_capture_writes_storage(self):
        result = capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(10, 0)),
            data_dir=self.data_dir,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["added"], 1)
        store = self._read_session_store()
        self.assertEqual(len(store), 1)
        self.assertAlmostEqual(float(store.iloc[0]["market_real"]), 9.0)

    def test_second_capture_same_identity_no_mutation(self):
        capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(10, 0)),
            data_dir=self.data_dir,
        )
        first = self._read_session_store().copy()
        result = capture_market_t0_snapshot(
            **_row_kwargs(market_real=11.0, now=_vn_dt(10, 30)),
            data_dir=self.data_dir,
        )
        second = self._read_session_store()
        self.assertEqual(result["added"], 0)
        pd.testing.assert_frame_equal(
            first.reset_index(drop=True),
            second.reset_index(drop=True),
            check_dtype=False,
        )

    def test_trading_day_gate_skips(self):
        result = capture_market_t0_snapshot(
            **_row_kwargs(trading_today=False, now=_vn_dt(20, 0)),
            data_dir=self.data_dir,
        )
        self.assertEqual(result["skipped_reason"], "NON_TRADING_SESSION")
        self.assertEqual(result["canonical_skipped_reason"], "NON_TRADING_SESSION")
        self.assertFalse((self.data_dir / MARKET_T0_SNAPSHOT_FILE).exists())
        self.assertFalse((self.data_dir / MARKET_DAILY_T0_FILE).exists())

    def test_storage_failure_fail_safe(self):
        with mock.patch(
            "modules.earning_learning._make_storage",
            side_effect=RuntimeError("storage down"),
        ):
            result = capture_market_t0_snapshot(**_row_kwargs(), data_dir=self.data_dir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["added"], 0)
        self.assertIn("storage down", result.get("error", ""))


class CanonicalCaptureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "earning_learning"
        self.data_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_daily(self) -> pd.DataFrame:
        path = self.data_dir / MARKET_DAILY_T0_FILE
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    def _read_session(self) -> pd.DataFrame:
        path = self.data_dir / MARKET_T0_SNAPSHOT_FILE
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    def test_1759_canonical_not_written(self):
        result = capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(17, 59)),
            data_dir=self.data_dir,
        )
        self.assertEqual(result["canonical_added"], 0)
        self.assertEqual(result["canonical_skipped_reason"], "BEFORE_EOD_PLUS_3H")
        self.assertTrue(self._read_session().empty is False)
        self.assertTrue(self._read_daily().empty)

    def test_1801_first_run_writes_one_canonical_row(self):
        result = capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(18, 1)),
            data_dir=self.data_dir,
        )
        self.assertEqual(result["canonical_added"], 1)
        daily = self._read_daily()
        self.assertEqual(len(daily), 1)
        self.assertTrue(daily.iloc[0]["canonical_t0"])
        self.assertEqual(
            daily.iloc[0]["daily_snapshot_id"],
            daily_snapshot_id("2026-08-12", MARKET_ENTITY),
        )

    def test_2000_rerun_does_not_mutate_canonical(self):
        capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(18, 1)),
            data_dir=self.data_dir,
        )
        first = self._read_daily().copy()
        result = capture_market_t0_snapshot(
            **_row_kwargs(market_real=42.0, now=_vn_dt(20, 0)),
            data_dir=self.data_dir,
        )
        second = self._read_daily()
        self.assertEqual(result["canonical_added"], 0)
        self.assertEqual(result["canonical_skipped_reason"], "ALREADY_FROZEN")
        pd.testing.assert_frame_equal(first, second, check_dtype=False)
        self.assertAlmostEqual(float(second.iloc[0]["market_real"]), 9.0)

    def test_2200_rerun_still_unchanged(self):
        capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(18, 1)),
            data_dir=self.data_dir,
        )
        first = self._read_daily().copy()
        result = capture_market_t0_snapshot(
            **_row_kwargs(market_real=55.0, now=_vn_dt(22, 0)),
            data_dir=self.data_dir,
        )
        second = self._read_daily()
        self.assertEqual(result["canonical_added"], 0)
        pd.testing.assert_frame_equal(first, second, check_dtype=False)

    def test_next_trading_day_adds_second_canonical_row(self):
        capture_market_t0_snapshot(
            **_row_kwargs(trade_date="2026-08-12", now=_vn_dt(18, 5, "2026-08-12")),
            data_dir=self.data_dir,
        )
        result = capture_market_t0_snapshot(
            **_row_kwargs(trade_date="2026-08-13", now=_vn_dt(19, 0, "2026-08-13")),
            data_dir=self.data_dir,
        )
        daily = self._read_daily()
        self.assertEqual(result["canonical_added"], 1)
        self.assertEqual(len(daily), 2)
        ids = set(daily["daily_snapshot_id"].astype(str))
        self.assertEqual(
            ids,
            {
                daily_snapshot_id("2026-08-12", MARKET_ENTITY),
                daily_snapshot_id("2026-08-13", MARKET_ENTITY),
            },
        )

    def test_session_snapshot_unchanged_by_canonical_gate(self):
        before = capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(11, 0)),
            data_dir=self.data_dir,
        )
        after = capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(18, 30)),
            data_dir=self.data_dir,
        )
        session = self._read_session()
        self.assertEqual(before["added"], 1)
        self.assertEqual(after["added"], 1)
        self.assertEqual(len(session), 2)
        self.assertEqual(after["canonical_added"], 1)

    def test_daily_snapshot_id_stable_for_outcome_join(self):
        capture_market_t0_snapshot(
            **_row_kwargs(now=_vn_dt(21, 30)),
            data_dir=self.data_dir,
        )
        sid = self._read_daily().iloc[0]["daily_snapshot_id"]
        self.assertEqual(sid, daily_snapshot_id("2026-08-12", MARKET_ENTITY))
        self.assertEqual(len(str(sid)), 16)

    def test_canonical_storage_failure_fail_safe(self):
        original_write = None

        def selective_write(storage, filename, df, *, commit_message):
            if filename == MARKET_DAILY_T0_FILE:
                raise RuntimeError("daily storage down")
            return original_write(storage, filename, df, commit_message=commit_message)

        from modules import earning_learning

        original_write = earning_learning._write_csv_to_storage
        with mock.patch(
            "modules.earning_learning._write_csv_to_storage",
            side_effect=selective_write,
        ):
            result = capture_market_t0_snapshot(
                **_row_kwargs(now=_vn_dt(20, 0)),
                data_dir=self.data_dir,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["canonical_added"], 0)
        self.assertEqual(result["canonical_skipped_reason"], "STORAGE_ERROR")
        self.assertTrue(self._read_session().empty is False)
        self.assertTrue(self._read_daily().empty)


class ObserverOnlyTests(unittest.TestCase):
    def test_capture_does_not_return_ranking_outputs(self):
        source = inspect.getsource(capture_market_t0_snapshot)
        self.assertNotIn("build_buy_elite", source)
        self.assertNotIn("ShadowFinalScore", source)
        self.assertNotIn("calc_market_real", source)

    def test_build_row_does_not_mutate_scan_df(self):
        scan = _sample_scan()
        before = scan.copy()
        build_market_t0_row(**_row_kwargs(scan_df=scan))
        pd.testing.assert_frame_equal(scan, before)

    def test_no_production_reader_of_daily_file(self):
        import os

        root = Path(__file__).resolve().parents[1]
        hits = []
        for path in root.rglob("*.py"):
            if path.name.endswith(".py") and "test_" not in path.name:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "market_daily_t0" in text and path.name != "market_t0_capture.py":
                    hits.append(str(path))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
