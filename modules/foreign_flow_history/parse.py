"""Parse HSX foreign API payloads into canonical row dicts (no outcomes)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.foreign_flow_history.schema import (
    EXCHANGE,
    SCHEMA_VERSION,
    SOURCE_NAME,
    SOURCE_SCOPE,
    SOURCE_UNITS,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _finite_or_none(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except (TypeError, ValueError):
        return None


def report_date_iso(ts: Any) -> Optional[str]:
    try:
        if ts is None:
            return None
        d = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
        return d.isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def stable_row_hash(payload: Dict[str, Any]) -> str:
    body = {k: payload.get(k) for k in sorted(payload.keys()) if k != "row_hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def extract_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        rows = data.get("list") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def parse_hsx_row(
    row: Dict[str, Any],
    *,
    symbol: str,
    fetched_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Parse one provider row. Preserves NULL for missing foreign main values
    (does not invent 0). Still emits the row if a valid reportDate exists so
    OHLC provenance is retained when foreign main is absent.
    """
    td = report_date_iso(row.get("reportDate"))
    if not td:
        return None

    buy_main = _finite_or_none(row.get("mainBuyerForeignValue"))
    sell_main = _finite_or_none(row.get("mainSellerForeignValue"))
    buy_bl = _finite_or_none(row.get("bigLotBuyerForeignValue"))
    sell_bl = _finite_or_none(row.get("bigLotSellerForeignValue"))

    if buy_main is None or sell_main is None:
        buy_v = None
        sell_v = None
        net_v = None
    else:
        # Provider may return bigLot as null → treat missing bigLot addend as 0 only when main present
        buy_v = float(buy_main) + float(buy_bl or 0.0)
        sell_v = float(sell_main) + float(sell_bl or 0.0)
        net_v = buy_v - sell_v

    buy_vol_main = _finite_or_none(row.get("mainBuyerForeignVolume"))
    sell_vol_main = _finite_or_none(row.get("mainSellerForeignVolume"))
    buy_vol_bl = _finite_or_none(row.get("bigLotBuyerForeignVolume"))
    sell_vol_bl = _finite_or_none(row.get("bigLotSellerForeignVolume"))
    buy_vol = (
        float(buy_vol_main) + float(buy_vol_bl or 0.0) if buy_vol_main is not None else None
    )
    sell_vol = (
        float(sell_vol_main) + float(sell_vol_bl or 0.0) if sell_vol_main is not None else None
    )
    net_vol = (buy_vol - sell_vol) if buy_vol is not None and sell_vol is not None else None

    out: Dict[str, Any] = {
        "trade_date": td,
        "symbol": str(symbol).strip().upper(),
        "exchange": EXCHANGE,
        "foreign_buy_value": buy_v,
        "foreign_sell_value": sell_v,
        "foreign_net_value": net_v,
        "foreign_buy_volume": buy_vol,
        "foreign_sell_volume": sell_vol,
        "foreign_net_volume": net_vol,
        "biglot_buy_value": buy_bl,
        "biglot_sell_value": sell_bl,
        "biglot_buy_volume": buy_vol_bl,
        "biglot_sell_volume": sell_vol_bl,
        "open_price": _finite_or_none(row.get("openPrice")),
        "high_price": _finite_or_none(row.get("highPrice")),
        "low_price": _finite_or_none(row.get("lowPrice")),
        "close_price": _finite_or_none(row.get("closePrice")),
        "average_price": _finite_or_none(row.get("averagePrice")),
        "source": SOURCE_NAME,
        "source_scope": SOURCE_SCOPE,
        "source_units": SOURCE_UNITS,
        "fetched_at": fetched_at or _utc_now_iso(),
        "schema_version": SCHEMA_VERSION,
    }
    out["row_hash"] = stable_row_hash(out)
    return out


def parse_payload_to_rows(
    payload: Dict[str, Any],
    *,
    symbol: str,
    fetched_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in extract_list(payload):
        parsed = parse_hsx_row(raw, symbol=symbol, fetched_at=fetched_at)
        if parsed is not None:
            rows.append(parsed)
    return rows
