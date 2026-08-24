"""
Universe-142 foreign-flow aggregation (EMS research universe).

Primary: Official HSX per-symbol foreign VALUE (dated reportDate, VND).
Fallback: vnstock VCI Trading.price_board (current session only, VND).

Never label aggregates as HOSE / whole-market / VNINDEX foreign flow.
Missing ≠ 0.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.contract import (
    EXPECTED_UNIVERSE_SIZE,
    P0_COMPLETENESS_COMPLETE,
    P0_COMPLETENESS_PARTIAL,
    P0_COMPLETENESS_SOURCE_ERROR,
    P0_COMPLETENESS_WAITING,
    P0_UNIVERSE_FOREIGN_SCOPE,
    P0_UNIVERSE_TURNOVER_SCOPE,
)
from modules.forecast_research.p0_providers import ProviderResult, _finite_or_none, _utc_now_iso
from modules.forecast_research.t0_builder import DEFAULT_EMS, load_board

logger = logging.getLogger(__name__)

HSX_FOREIGN_URL = "https://api.hsx.vn/mk/api/v1/market/securities/foreign/{symbol}"
HSX_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.hsx.vn",
    "Referer": "https://www.hsx.vn/du-lieu-giao-dich/giao-dich-ndtnn",
    "User-Agent": "MrBOT-P0-universe-foreign/1.0",
}

GetJsonFn = Callable[[str], Dict[str, Any]]


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def ems_universe_symbols(trade_date: str, *, ems_path: Path = DEFAULT_EMS) -> List[str]:
    """
    Membership-asof rule:
    Immutable EMS board for exact snapshot_date == trade_date.
    Symbols = sorted unique non-empty symbol codes on that board.
    If no EMS row for the date → empty list (no canonical aggregate).
    """
    board = load_board(ems_path, str(trade_date)[:10])
    if board.empty or "symbol" not in board.columns:
        return []
    syms = (
        board["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
        .replace({"": np.nan, "NAN": np.nan, "NONE": np.nan})
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(str(s) for s in syms)


def universe_membership_meta(trade_date: str, symbols: Sequence[str], *, ems_path: Path = DEFAULT_EMS) -> Dict[str, Any]:
    return {
        "membership_rule": "EMS_SNAPSHOT_DATE_EXACT",
        "membership_authority": "data/earning_money_snapshots.csv",
        "ems_path": str(ems_path),
        "trade_date": str(trade_date)[:10],
        "symbols": list(symbols),
        "expected_count": int(len(symbols)),
        "universe_hash": _stable_hash(list(symbols)),
        "scope": P0_UNIVERSE_FOREIGN_SCOPE,
    }


def _report_date_iso(ts: Any) -> Optional[str]:
    try:
        if ts is None:
            return None
        # HSX uses unix seconds at UTC midnight for the session date
        d = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
        return d.isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_hsx_foreign_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse HSX foreign JSON into dated rows with VND values."""
    data = payload.get("data") if isinstance(payload, dict) else None
    rows_in = []
    if isinstance(data, dict):
        rows_in = data.get("list") or []
    elif isinstance(data, list):
        rows_in = data
    out: List[Dict[str, Any]] = []
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        rd = _report_date_iso(row.get("reportDate"))
        if not rd:
            continue
        buy_main = _finite_or_none(row.get("mainBuyerForeignValue"))
        sell_main = _finite_or_none(row.get("mainSellerForeignValue"))
        buy_bl = _finite_or_none(row.get("bigLotBuyerForeignValue")) or 0.0
        sell_bl = _finite_or_none(row.get("bigLotSellerForeignValue")) or 0.0
        # main may be missing → entire value missing (do not invent 0 from bigLot alone if main null)
        if buy_main is None or sell_main is None:
            continue
        buy_v = float(buy_main) + float(buy_bl)
        sell_v = float(sell_main) + float(sell_bl)
        buy_vol_main = _finite_or_none(row.get("mainBuyerForeignVolume"))
        sell_vol_main = _finite_or_none(row.get("mainSellerForeignVolume"))
        buy_vol_bl = _finite_or_none(row.get("bigLotBuyerForeignVolume")) or 0.0
        sell_vol_bl = _finite_or_none(row.get("bigLotSellerForeignVolume")) or 0.0
        buy_vol = (float(buy_vol_main) + float(buy_vol_bl)) if buy_vol_main is not None else None
        sell_vol = (float(sell_vol_main) + float(sell_vol_bl)) if sell_vol_main is not None else None
        out.append(
            {
                "report_date": rd,
                "foreign_buy_value": buy_v,
                "foreign_sell_value": sell_v,
                "foreign_net_value": buy_v - sell_v,
                "foreign_buy_volume": buy_vol,
                "foreign_sell_volume": sell_vol,
                "foreign_net_volume": (buy_vol - sell_vol) if buy_vol is not None and sell_vol is not None else None,
                "units": "VND",
            }
        )
    return out


def default_hsx_get_json(url: str, *, timeout_s: float = 20.0) -> Dict[str, Any]:
    import requests

    resp = requests.get(url, headers=HSX_HEADERS, timeout=timeout_s)
    if resp.status_code != 200:
        raise RuntimeError(f"http_{resp.status_code}")
    return resp.json()


def fetch_hsx_symbol_history(
    symbol: str,
    *,
    page_size: int = 80,
    get_json: Optional[GetJsonFn] = None,
) -> List[Dict[str, Any]]:
    getter = get_json or default_hsx_get_json
    url = HSX_FOREIGN_URL.format(symbol=str(symbol).upper()) + f"?pageSize={int(page_size)}"
    payload = getter(url)
    return parse_hsx_foreign_payload(payload)


def row_for_exact_date(rows: Sequence[Dict[str, Any]], trade_date: str) -> Optional[Dict[str, Any]]:
    td = str(trade_date)[:10]
    for row in rows:
        if str(row.get("report_date"))[:10] == td:
            return row
    return None


def aggregate_symbol_rows(
    trade_date: str,
    symbols: Sequence[str],
    per_symbol_rows: Dict[str, Sequence[Dict[str, Any]]],
    *,
    source: str,
) -> ProviderResult:
    """
    Aggregate only exact report_date matches.
    COMPLETE iff every required symbol has a dated VALUE observation.
    """
    td = str(trade_date)[:10]
    expected = list(symbols)
    if not expected:
        return ProviderResult(
            ok=False,
            status="MISSING",
            error="no_ems_membership_for_date",
            meta={
                "provider": source,
                "scope": P0_UNIVERSE_FOREIGN_SCOPE,
                "units": "VND",
                "trade_date": td,
                "expected_count": 0,
                "observed_count": 0,
                "completeness": P0_COMPLETENESS_WAITING,
                "completeness_ratio": None,
            },
        )

    buy_sum = 0.0
    sell_sum = 0.0
    buy_vol_sum = 0.0
    sell_vol_sum = 0.0
    n_buy_vol = 0
    n_sell_vol = 0
    observed: List[str] = []
    missing: List[str] = []
    rejected_wrong_date = 0

    for sym in expected:
        rows = per_symbol_rows.get(sym) or per_symbol_rows.get(sym.upper()) or []
        # Detect wrong-date-only responses (have rows but none match)
        if rows and row_for_exact_date(rows, td) is None:
            rejected_wrong_date += 1
        hit = row_for_exact_date(rows, td)
        if hit is None:
            missing.append(sym)
            continue
        bv = _finite_or_none(hit.get("foreign_buy_value"))
        sv = _finite_or_none(hit.get("foreign_sell_value"))
        if bv is None or sv is None:
            missing.append(sym)
            continue
        buy_sum += float(bv)
        sell_sum += float(sv)
        observed.append(sym)
        bvol = _finite_or_none(hit.get("foreign_buy_volume"))
        svol = _finite_or_none(hit.get("foreign_sell_volume"))
        if bvol is not None:
            buy_vol_sum += float(bvol)
            n_buy_vol += 1
        if svol is not None:
            sell_vol_sum += float(svol)
            n_sell_vol += 1

    n_exp = len(expected)
    n_obs = len(observed)
    ratio = (n_obs / n_exp) if n_exp else None
    if n_obs == 0:
        completeness = P0_COMPLETENESS_WAITING if rejected_wrong_date == 0 else P0_COMPLETENESS_WAITING
        # If we got rows but all wrong dates → still WAITING/MISSING for that date (not SOURCE_ERROR)
        status = "MISSING"
        ok = False
        values = {
            "universe_foreign_buy_value": None,
            "universe_foreign_sell_value": None,
            "universe_foreign_net_value": None,
            "universe_foreign_buy_volume": None,
            "universe_foreign_sell_volume": None,
            "universe_foreign_net_volume": None,
        }
    else:
        net = buy_sum - sell_sum
        values = {
            "universe_foreign_buy_value": buy_sum,
            "universe_foreign_sell_value": sell_sum,
            "universe_foreign_net_value": net,
            "universe_foreign_buy_volume": buy_vol_sum if n_buy_vol == n_obs else None,
            "universe_foreign_sell_volume": sell_vol_sum if n_sell_vol == n_obs else None,
            "universe_foreign_net_volume": (buy_vol_sum - sell_vol_sum)
            if (n_buy_vol == n_obs and n_sell_vol == n_obs)
            else None,
        }
        if n_obs == n_exp:
            completeness = P0_COMPLETENESS_COMPLETE
            status = "OK"
            ok = True
        else:
            completeness = P0_COMPLETENESS_PARTIAL
            status = "OK"  # partial but usable evidence
            ok = True

    meta = {
        "provider": source,
        "scope": P0_UNIVERSE_FOREIGN_SCOPE,
        "units": "VND",
        "trade_date": td,
        "report_date_match_required": True,
        "expected_count": n_exp,
        "observed_count": n_obs,
        "missing_count": len(missing),
        "missing_symbols": missing[:50],
        "missing_symbols_truncated": len(missing) > 50,
        "completeness": completeness,
        "completeness_ratio": ratio,
        "rejected_wrong_date_symbols": rejected_wrong_date,
        "universe_hash": _stable_hash(expected),
        "observed_at": _utc_now_iso(),
    }
    return ProviderResult(ok=ok, status=status if n_obs or status == "MISSING" else status, values=values, meta=meta, error=None if n_obs else "no_matching_reportDate_rows")


@dataclass
class HsXUniverseForeignProvider:
    """Official HSX dated foreign VALUE → EMS universe aggregate."""

    ems_path: Path = DEFAULT_EMS
    page_size: int = 80
    get_json: Optional[GetJsonFn] = None
    sleep_s: float = 0.05
    # Optional preloaded {symbol: [rows]} for tests / backfill cache
    cache: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def fetch_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        sym = str(symbol).upper()
        if sym in self.cache:
            return self.cache[sym]
        try:
            rows = fetch_hsx_symbol_history(sym, page_size=self.page_size, get_json=self.get_json)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HSX foreign fetch failed for %s: %s", sym, exc)
            return []
        self.cache[sym] = rows
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return rows

    def fetch(self, trade_date: str) -> ProviderResult:
        td = str(trade_date)[:10]
        symbols = ems_universe_symbols(td, ems_path=self.ems_path)
        mem = universe_membership_meta(td, symbols, ems_path=self.ems_path)
        if not symbols:
            return ProviderResult(
                ok=False,
                status="MISSING",
                error="no_ems_membership_for_date",
                meta={**mem, "provider": "hsx_official_foreign", "units": "VND", "historical_supported": True},
            )

        per: Dict[str, List[Dict[str, Any]]] = {}
        fetch_errors = 0
        for sym in symbols:
            try:
                per[sym] = self.fetch_symbol(sym)
                if not per[sym]:
                    # empty list may be valid (no history) or error — count as missing later
                    pass
            except Exception:  # noqa: BLE001
                fetch_errors += 1
                per[sym] = []

        result = aggregate_symbol_rows(td, symbols, per, source="hsx_official_foreign")
        result.meta.update(
            {
                **mem,
                "historical_supported": True,
                "historical_capability": "HISTORICAL_AND_FORWARD",
                "fetch_errors": fetch_errors,
            }
        )
        if fetch_errors == len(symbols):
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error="all_symbol_fetches_failed",
                meta=result.meta,
            )
        return result


@dataclass
class VciUniverseForeignProvider:
    """
    VCI price_board foreign VALUE — current/live session only.
    Rejects historical dates that do not match listing_trading_date on the board.
    """

    ems_path: Path = DEFAULT_EMS
    batch_size: int = 20
    price_board_fn: Optional[Callable[[List[str]], pd.DataFrame]] = None
    # Injected "today" for tests (YYYY-MM-DD). If set, trade_date must equal it OR board dates.
    session_today: Optional[str] = None

    def _board(self, symbols: List[str]) -> pd.DataFrame:
        if self.price_board_fn is not None:
            return self.price_board_fn(symbols)
        from vnstock.explorer.vci.trading import Trading

        t = Trading(show_log=False)
        frames = []
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i : i + self.batch_size]
            df = t.price_board(batch, show_log=False, flatten_columns=True)
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch(self, trade_date: str) -> ProviderResult:
        td = str(trade_date)[:10]
        symbols = ems_universe_symbols(td, ems_path=self.ems_path)
        mem = universe_membership_meta(td, symbols, ems_path=self.ems_path)
        base_meta = {
            **mem,
            "provider": "vci_price_board",
            "units": "VND",
            "historical_supported": False,
            "historical_capability": "FORWARD_ONLY",
            "forward_only": True,
        }
        if not symbols:
            return ProviderResult(ok=False, status="MISSING", error="no_ems_membership_for_date", meta=base_meta)

        # Hard rule: VCI cannot invent history. If caller requests a past date without board match, fail.
        today = self.session_today or date.today().isoformat()
        try:
            df = self._board(symbols)
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error=f"vci_price_board:{exc}",
                meta=base_meta,
            )
        if df is None or df.empty:
            return ProviderResult(ok=False, status="SOURCE_ERROR", error="empty_price_board", meta=base_meta)

        # Normalize columns
        colmap = {str(c).lower(): c for c in df.columns}
        sym_col = colmap.get("listing_symbol") or colmap.get("symbol")
        date_col = colmap.get("listing_trading_date") or colmap.get("trading_date")
        buy_col = colmap.get("match_foreign_buy_value")
        sell_col = colmap.get("match_foreign_sell_value")
        buy_vol_col = colmap.get("match_foreign_buy_volume")
        sell_vol_col = colmap.get("match_foreign_sell_volume")
        if sym_col is None or buy_col is None or sell_col is None:
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error=f"missing_foreign_value_cols:{list(df.columns)[:30]}",
                meta=base_meta,
            )

        df = df.copy()
        df["_sym"] = df[sym_col].astype(str).str.upper().str.strip()
        if date_col is not None:
            df["_td"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
            # All observed board dates must match requested trade_date
            board_dates = sorted({d for d in df["_td"].dropna().astype(str).tolist()})
            if board_dates and board_dates != [td]:
                return ProviderResult(
                    ok=False,
                    status="MISSING",
                    error=f"vci_session_date_mismatch:board={board_dates},requested={td}",
                    meta={**base_meta, "board_dates": board_dates, "note": "historical VCI prohibited"},
                )
        elif td != today:
            # No trading date column and not today → refuse historical use
            return ProviderResult(
                ok=False,
                status="MISSING",
                error="vci_historical_prohibited_without_listing_trading_date",
                meta=base_meta,
            )

        per: Dict[str, List[Dict[str, Any]]] = {}
        for sym in symbols:
            hit = df[df["_sym"] == sym]
            if hit.empty:
                per[sym] = []
                continue
            row = hit.iloc[0]
            bv = _finite_or_none(row[buy_col])
            sv = _finite_or_none(row[sell_col])
            if bv is None or sv is None:
                per[sym] = []
                continue
            per[sym] = [
                {
                    "report_date": td,
                    "foreign_buy_value": float(bv),
                    "foreign_sell_value": float(sv),
                    "foreign_net_value": float(bv) - float(sv),
                    "foreign_buy_volume": _finite_or_none(row[buy_vol_col]) if buy_vol_col else None,
                    "foreign_sell_volume": _finite_or_none(row[sell_vol_col]) if sell_vol_col else None,
                    "units": "VND",
                }
            ]

        result = aggregate_symbol_rows(td, symbols, per, source="vci_price_board")
        result.meta.update(base_meta)
        return result


@dataclass
class UniverseForeignFlowCascade:
    """
    Source hierarchy: HSX → VCI (current session only) → NULL/status.
    Prefer one coherent source per daily aggregate (no silent mixed rows).
    Optional cross-check when both succeed for the same session.
    """

    hsx: Optional[HsXUniverseForeignProvider] = None
    vci: Optional[VciUniverseForeignProvider] = None
    ems_path: Path = DEFAULT_EMS
    enable_cross_check: bool = True
    cross_check_rel_tol: float = 0.05  # 5% relative on net for quality flag

    def __post_init__(self) -> None:
        if self.hsx is None:
            self.hsx = HsXUniverseForeignProvider(ems_path=self.ems_path)
        if self.vci is None:
            self.vci = VciUniverseForeignProvider(ems_path=self.ems_path)

    def fetch(self, trade_date: str) -> ProviderResult:
        td = str(trade_date)[:10]
        assert self.hsx is not None and self.vci is not None
        primary = self.hsx.fetch(td)
        cross: Dict[str, Any] = {}

        # HSX COMPLETE or PARTIAL with values → use HSX (single source)
        if primary.ok and primary.values.get("universe_foreign_net_value") is not None:
            if self.enable_cross_check and primary.meta.get("completeness") == P0_COMPLETENESS_COMPLETE:
                try:
                    fb = self.vci.fetch(td)
                    if fb.ok and fb.values.get("universe_foreign_net_value") is not None:
                        a = float(primary.values["universe_foreign_net_value"])
                        b = float(fb.values["universe_foreign_net_value"])
                        denom = max(abs(a), abs(b), 1.0)
                        rel = abs(a - b) / denom
                        cross = {
                            "cross_check_provider": "vci_price_board",
                            "cross_check_net_hsx": a,
                            "cross_check_net_vci": b,
                            "cross_check_rel_diff": rel,
                            "cross_check_ok": rel <= self.cross_check_rel_tol,
                        }
                        if not cross["cross_check_ok"]:
                            primary.meta["quality_flag"] = "HSX_VCI_NET_MISMATCH"
                except Exception as exc:  # noqa: BLE001
                    cross = {"cross_check_error": str(exc)}
            primary.meta["source_hierarchy"] = "HSX"
            primary.meta.update(cross)
            return primary

        # Fallback VCI only when HSX failed / empty
        fallback = self.vci.fetch(td)
        if fallback.ok and fallback.values.get("universe_foreign_net_value") is not None:
            fallback.meta["source_hierarchy"] = "VCI_FALLBACK"
            fallback.meta["primary_hsx_status"] = primary.status
            fallback.meta["primary_hsx_error"] = primary.error
            return fallback

        # Neither usable
        meta = {
            "provider": "universe_foreign_cascade",
            "scope": P0_UNIVERSE_FOREIGN_SCOPE,
            "units": "VND",
            "source_hierarchy": "HSX→VCI→NULL",
            "hsx": {"status": primary.status, "error": primary.error, "meta": primary.meta},
            "vci": {"status": fallback.status, "error": fallback.error, "meta": fallback.meta},
            "observed_at": _utc_now_iso(),
        }
        if primary.status == "SOURCE_ERROR" and fallback.status == "SOURCE_ERROR":
            return ProviderResult(ok=False, status="SOURCE_ERROR", error="hsx_and_vci_failed", meta=meta)
        return ProviderResult(ok=False, status="MISSING", error="no_reliable_universe_foreign", meta=meta)


def empty_universe_foreign_values() -> Dict[str, Optional[float]]:
    return {
        "universe_foreign_buy_value": None,
        "universe_foreign_sell_value": None,
        "universe_foreign_net_value": None,
        "universe_foreign_buy_volume": None,
        "universe_foreign_sell_volume": None,
        "universe_foreign_net_volume": None,
    }
