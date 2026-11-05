"""Legacy vnstock DNSE/Entrade D1 fetch (production-equivalent args).

DNSE/Entrade-specific defaults are isolated here. The archive contract itself
is provider-neutral. Network I/O is injectable for offline tests. Never
injects live bars. Does not import Streamlit or ``app.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Protocol

import pandas as pd

from research.shared_d1_archive.contract import (
    DEFAULT_START_DATE,
    RESOLUTION,
    STOCK_TYPE,
    VNINDEX_SYMBOL,
    VNINDEX_TYPE,
)

# --- DNSE / legacy vnstock specifics (not part of the neutral contract) ---
DNSE_PROVIDER = "vnstock_legacy_dnse_entrade"
DNSE_PROVIDER_SOURCE = "DNSE"
DNSE_FETCH_FN = "vnstock.stock_historical_data"
DNSE_UNIT_NOTE = (
    "values_as_returned_by_legacy_vnstock_dnse;"
    "beautify_scales_stock_ohlc_x1000;"
    "not_a_corporate_action_adjust_flag"
)


def default_fetch_provenance(*, beautify: bool = True) -> dict[str, Any]:
    """Provenance stamp applied when using the legacy DNSE fetcher."""
    return {
        "provider": DNSE_PROVIDER,
        "provider_source": DNSE_PROVIDER_SOURCE,
        "fetch_fn": DNSE_FETCH_FN,
        "beautify": bool(beautify),
        "unit_note": DNSE_UNIT_NOTE,
    }


class D1Fetcher(Protocol):
    def __call__(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        resolution: str,
        type: str,
        beautify: bool,
        source: str,
    ) -> pd.DataFrame: ...


def today_iso(today: date | None = None) -> str:
    return (today or date.today()).isoformat()


def default_vnstock_fetcher(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    resolution: str = RESOLUTION,
    type: str = STOCK_TYPE,
    beautify: bool = True,
    source: str = DNSE_PROVIDER_SOURCE,
) -> pd.DataFrame:
    """Call pinned legacy ``stock_historical_data`` with DNSE defaults."""
    from vnstock import stock_historical_data  # type: ignore[import-untyped]

    df = stock_historical_data(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        type=type,
        beautify=beautify,
        source=source,
    )
    if df is None:
        return pd.DataFrame()
    return df


def normalize_ohlcv_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize OHLCV columns to date/open/high/low/close/volume."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    rename_map: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).lower()
        if "date" in cl or cl == "time":
            rename_map[col] = "date"
        elif cl == "open":
            rename_map[col] = "open"
        elif cl == "high":
            rename_map[col] = "high"
        elif cl == "low":
            rename_map[col] = "low"
        elif cl == "close":
            rename_map[col] = "close"
        elif cl == "volume":
            rename_map[col] = "volume"

    work = df.rename(columns=rename_map)
    needed = ["date", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in work.columns:
            return pd.DataFrame(columns=needed)

    work = work[needed].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["date", "close"]).sort_values("date")
    return work.reset_index(drop=True)


def fetch_symbol_d1(
    symbol: str,
    *,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    instrument_type: str = STOCK_TYPE,
    beautify: bool = True,
    fetcher: D1Fetcher | Callable[..., pd.DataFrame] | None = None,
    provider_source: str = DNSE_PROVIDER_SOURCE,
) -> pd.DataFrame:
    """Fetch raw D1 OHLCV. No live injection."""
    fn = fetcher or default_vnstock_fetcher
    end = end_date or today_iso()
    raw = fn(
        symbol=symbol,
        start_date=start_date,
        end_date=end,
        resolution=RESOLUTION,
        type=instrument_type,
        beautify=beautify,
        source=provider_source,
    )
    return normalize_ohlcv_frame(raw)


def fetch_vnindex_d1(
    *,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    fetcher: D1Fetcher | Callable[..., pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """VNINDEX daily bars (type=index)."""
    return fetch_symbol_d1(
        VNINDEX_SYMBOL,
        start_date=start_date,
        end_date=end_date,
        instrument_type=VNINDEX_TYPE,
        beautify=True,
        fetcher=fetcher,
    )
