"""Focused receipt date-status contract (VPS-local semantic restore)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.production_daily_receipt import _count_date_rows


def test_date_csv_with_symbol_sets_status_and_unique_symbols(tmp_path: Path):
    path = tmp_path / "with_symbol.csv"
    pd.DataFrame(
        {
            "trade_date": ["2026-08-28", "2026-08-28", "2026-08-27"],
            "symbol": ["AAA", "BBB", "AAA"],
        }
    ).to_csv(path, index=False)
    present = _count_date_rows(path, "2026-08-28")
    assert present["status"] == "PRESENT"
    assert present["rows"] == 2
    assert present["unique_symbols"] == 2
    absent = _count_date_rows(path, "2026-09-03")
    assert absent["status"] == "ABSENT_FOR_DATE"
    assert absent["rows"] == 0
    assert absent["unique_symbols"] == 0


def test_date_csv_without_symbol_still_sets_present_or_absent(tmp_path: Path):
    path = tmp_path / "no_symbol.csv"
    pd.DataFrame(
        {
            "trade_date": ["2026-08-28", "2026-08-27"],
            "value": [1.0, 2.0],
        }
    ).to_csv(path, index=False)
    present = _count_date_rows(path, "2026-08-28")
    assert present["status"] == "PRESENT"
    assert present["rows"] == 1
    assert present["unique_symbols"] is None
    absent = _count_date_rows(path, "2026-09-03")
    assert absent["status"] == "ABSENT_FOR_DATE"
    assert absent["rows"] == 0
    assert absent["unique_symbols"] is None
