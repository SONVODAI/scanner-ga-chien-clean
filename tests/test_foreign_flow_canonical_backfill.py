"""Tests for canonical HSX foreign-flow historical backfill (research store)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import pandas as pd
import pytest

from modules.foreign_flow_history import schema
from modules.foreign_flow_history.hsx_client import (
    ProviderRateLimited,
    ProviderTransientError,
    build_url,
    fetch_symbol_pages,
    fetch_with_retries,
)
from modules.foreign_flow_history.parse import parse_hsx_row, parse_payload_to_rows
from modules.foreign_flow_history.store import (
    load_checkpoint,
    merge_canonical_frames,
    read_symbol_canonical,
    rows_to_dataframe,
    save_checkpoint,
    write_symbol_canonical,
)
from modules.foreign_flow_history.validate import price_outcome_readiness, validate_canonical_df


def _ts(ymd: str) -> int:
    # UTC midnight for YYYY-MM-DD
    y, m, d = map(int, ymd.split("-"))
    from datetime import datetime, timezone

    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def _raw_row(
    ymd: str,
    *,
    buy: float | None = 100.0,
    sell: float | None = 40.0,
    open_p: float = 10.0,
    high: float = 11.0,
    low: float = 9.0,
    close: float = 10.5,
) -> Dict[str, Any]:
    return {
        "reportDate": _ts(ymd),
        "mainBuyerForeignValue": buy,
        "mainSellerForeignValue": sell,
        "mainBuyerForeignVolume": 1.0 if buy is not None else None,
        "mainSellerForeignVolume": 1.0 if sell is not None else None,
        "bigLotBuyerForeignValue": None,
        "bigLotSellerForeignValue": None,
        "bigLotBuyerForeignVolume": None,
        "bigLotSellerForeignVolume": None,
        "openPrice": open_p,
        "highPrice": high,
        "lowPrice": low,
        "closePrice": close,
        "averagePrice": 10.2,
    }


def _payload(
    rows: List[Dict[str, Any]],
    *,
    page_index: int = 1,
    total: int | None = None,
    page_size: int | None = None,
) -> Dict[str, Any]:
    total = total if total is not None else len(rows)
    ps = int(page_size if page_size is not None else max(len(rows), 1))
    return {
        "success": True,
        "data": {
            "list": rows,
            "object": None,
            "paging": {
                "pageIndex": page_index,
                "pageSize": ps,
                "totalCount": total,
                "totalPages": max(1, (total + ps - 1) // ps),
            },
        },
    }


def test_build_url_official_hsx():
    url = build_url("vnm", page_size=500, page_index=2)
    assert url.startswith("https://api.hsx.vn/mk/api/v1/market/securities/foreign/VNM?")
    assert "pageSize=500" in url
    assert "pageIndex=2" in url


def test_missing_main_not_zero():
    row = parse_hsx_row(_raw_row("2020-01-02", buy=None, sell=None), symbol="VNM")
    assert row is not None
    assert row["foreign_buy_value"] is None
    assert row["foreign_sell_value"] is None
    assert row["foreign_net_value"] is None
    assert row["close_price"] == 10.5


def test_net_arithmetic():
    row = parse_hsx_row(_raw_row("2020-01-02", buy=100.0, sell=40.0), symbol="VNM")
    assert row["foreign_net_value"] == 60.0


def test_no_outcomes_in_canonical_columns():
    forbidden = {"t3_return", "t5_return", "t10_return", "mfe", "mae", "label"}
    assert not forbidden.intersection(set(schema.CANONICAL_COLUMNS))


def test_pagination_collects_pages(tmp_path):
    pages = {
        1: _payload(
            [_raw_row("2024-01-03"), _raw_row("2024-01-02")],
            page_index=1,
            total=3,
            page_size=2,
        ),
        2: _payload([_raw_row("2024-01-01")], page_index=2, total=3, page_size=2),
    }

    def opener(req, timeout):
        url = req.full_url
        class Resp:
            status = 200
            def read(self):
                if "pageSize=5000" in url and "pageIndex" not in url:
                    raise OSError("IncompleteRead simulated")
                if "pageIndex=1" in url:
                    return json.dumps(pages[1]).encode()
                if "pageIndex=2" in url:
                    return json.dumps(pages[2]).encode()
                return json.dumps(pages[1]).encode()
            def getcode(self):
                return 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return Resp()

    sleeps: List[float] = []
    result = fetch_symbol_pages(
        "VNM",
        page_size=2,
        prefer_full_page=True,
        opener=opener,
        sleeper=sleeps.append,
        pacing_sec=0.01,
        max_retries=1,
    )
    assert result.mode == "paginated"
    assert result.page_count == 2
    assert result.raw_row_count == 3


def test_retry_then_success():
    calls = {"n": 0}

    def opener(req, timeout):
        calls["n"] += 1
        class Resp:
            status = 200
            def read(self):
                if calls["n"] < 3:
                    raise OSError("transient")
                return json.dumps(_payload([_raw_row("2024-01-02")])).encode()
            def getcode(self):
                return 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return Resp()

    sleeps: List[float] = []
    status, payload = fetch_with_retries(
        "https://api.hsx.vn/mk/api/v1/market/securities/foreign/VNM?pageSize=1",
        opener=opener,
        sleeper=sleeps.append,
        max_retries=3,
        backoff_base_sec=0.01,
    )
    assert status == 200
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_idempotent_merge_first_write_wins(tmp_path):
    root = tmp_path / "ff"
    r1 = parse_hsx_row(_raw_row("2020-01-02", buy=100.0, sell=40.0), symbol="AAA")
    r2 = parse_hsx_row(_raw_row("2020-01-02", buy=999.0, sell=1.0), symbol="AAA")  # conflict
    r3 = parse_hsx_row(_raw_row("2020-01-03", buy=50.0, sell=10.0), symbol="AAA")
    ok, status, n = write_symbol_canonical("AAA", [r1, r3], root=root)
    assert ok and n == 2
    ok2, status2, n2 = write_symbol_canonical("AAA", [r2], root=root)
    assert ok2
    df = read_symbol_canonical("AAA", root)
    assert len(df) == 2
    row = df[df["trade_date"] == "2020-01-02"].iloc[0]
    assert float(row["foreign_buy_value"]) == 100.0  # first-write wins


def test_date_preservation_no_shrink(tmp_path):
    root = tmp_path / "ff"
    rows = [
        parse_hsx_row(_raw_row("2020-01-02"), symbol="BBB"),
        parse_hsx_row(_raw_row("2020-01-03"), symbol="BBB"),
    ]
    write_symbol_canonical("BBB", rows, root=root)
    # merge with subset — should keep both dates
    write_symbol_canonical("BBB", [rows[1]], root=root)
    df = read_symbol_canonical("BBB", root)
    assert set(df["trade_date"].astype(str)) == {"2020-01-02", "2020-01-03"}


def test_atomic_write_leaves_prior_on_failure(tmp_path):
    root = tmp_path / "ff"
    rows = [parse_hsx_row(_raw_row("2020-01-02"), symbol="CCC")]
    write_symbol_canonical("CCC", rows, root=root)
    path = root / "canonical" / "by_symbol" / "CCC.csv"
    before = path.read_text(encoding="utf-8")

    with patch("modules.foreign_flow_history.store.atomic_write_csv", side_effect=OSError("boom")):
        ok, status, n = write_symbol_canonical(
            "CCC",
            [parse_hsx_row(_raw_row("2020-01-03"), symbol="CCC")],
            root=root,
            backup=False,
        )
    assert not ok
    assert path.read_text(encoding="utf-8") == before


def test_partial_symbol_failure_preserves_others(tmp_path):
    root = tmp_path / "ff"
    write_symbol_canonical(
        "DDD",
        [parse_hsx_row(_raw_row("2020-01-02"), symbol="DDD")],
        root=root,
    )
    cp = load_checkpoint(root)
    cp["symbols"] = {
        "DDD": {"status": "completed", "n_rows": 1},
        "EEE": {"status": "failed", "errors": ["boom"]},
    }
    save_checkpoint(cp, root)
    cp2 = load_checkpoint(root)
    assert cp2["symbols"]["DDD"]["status"] == "completed"
    assert cp2["symbols"]["EEE"]["status"] == "failed"
    assert len(read_symbol_canonical("DDD", root)) == 1


def test_duplicate_natural_keys_flagged():
    df = pd.DataFrame(
        [
            {"trade_date": "2020-01-02", "symbol": "X", "foreign_buy_value": 1, "foreign_sell_value": 0, "foreign_net_value": 1, "source_units": "VND"},
            {"trade_date": "2020-01-02", "symbol": "X", "foreign_buy_value": 2, "foreign_sell_value": 0, "foreign_net_value": 2, "source_units": "VND"},
        ]
    )
    for c in schema.CANONICAL_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[schema.CANONICAL_COLUMNS]
    v = validate_canonical_df(df)
    codes = [i["code"] for i in v["issues"]]
    assert "DUPLICATE_NATURAL_KEYS" in codes


def test_validate_net_and_no_outcomes():
    row = parse_hsx_row(_raw_row("2020-01-02", buy=10, sell=3), symbol="VNM")
    df = rows_to_dataframe([row])
    v = validate_canonical_df(df)
    assert v["ok"]
    assert "OUTCOME_COLUMNS_PRESENT" not in [i["code"] for i in v["issues"]]
    ready = price_outcome_readiness(df)
    # single row: not enough for T3+
    assert ready["n_sessions_with_close"] == 1


def test_schema_drift_missing_column_detected():
    df = pd.DataFrame([{"trade_date": "2020-01-02", "symbol": "Z"}])
    v = validate_canonical_df(df)
    assert any(i["code"] == "MISSING_COLUMNS" for i in v["issues"])


def test_resume_skips_completed(tmp_path):
    from modules.foreign_flow_history.backfill import backfill_symbol

    root = tmp_path / "ff"
    write_symbol_canonical(
        "VNM",
        [parse_hsx_row(_raw_row("2020-01-02"), symbol="VNM")],
        root=root,
    )
    cp = {"symbols": {"VNM": {"status": "completed", "n_rows": 1}}}
    res = backfill_symbol("VNM", root=root, checkpoint=cp, skip_completed=True)
    assert res["status"] == "skipped_completed"


def test_rate_limit_stops_safely(tmp_path):
    from modules.foreign_flow_history.backfill import backfill_symbol

    root = tmp_path / "ff"
    cp = {"symbols": {}}

    def boom(*a, **k):
        from modules.foreign_flow_history.hsx_client import FetchResult

        r = FetchResult(symbol="VNM")
        r.stopped_reason = "rate_limited"
        r.errors = ["HTTP 429"]
        return r

    with patch("modules.foreign_flow_history.backfill.fetch_symbol_pages", side_effect=boom):
        res = backfill_symbol("VNM", root=root, checkpoint=cp)
    assert res["status"] == "rate_limited"
    assert cp["symbols"]["VNM"]["status"] == "rate_limited"
