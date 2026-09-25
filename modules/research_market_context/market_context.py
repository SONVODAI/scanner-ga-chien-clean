"""Append-only Market Context history. Research only.

The writer stores scores the caller already computed. It does not call
``calc_market_real`` or any nomination / action function.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.research_market_context.previous_close import append_json_line, context_dir

MARKET_CONTEXT_NAME = "market_context.jsonl"
STATUS_OK = "ok"


def market_context_path(directory: Path | None = None) -> Path:
    return context_dir(directory) / MARKET_CONTEXT_NAME


def _price_token(value: object) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return ""
    rounded = round(float(number), 0)
    if float(number) == rounded:
        return str(int(rounded))
    return str(float(number))


def scan_fingerprint(scan_df: pd.DataFrame | None) -> str:
    """Deterministic hash of symbol, price, and group. Order of rows does not matter."""
    lines: list[str] = []
    if scan_df is not None and isinstance(scan_df, pd.DataFrame) and not scan_df.empty:
        records = scan_df.to_dict("records")
        for rec in records:
            symbol = str(rec.get("symbol") or "").strip().upper()
            group = str(rec.get("group") or "").strip()
            lines.append(f"{symbol}|{_price_token(rec.get('price'))}|{group}")
    payload = "\n".join(sorted(lines))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _same_number(left: object, right: object) -> bool:
    a = _json_number(left)
    b = _json_number(right)
    if a is None or b is None:
        return a is None and b is None
    return a == b


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _last_for(rows: list[dict[str, Any]], trade_date: str, source: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("trade_date") or "") == trade_date and str(row.get("source") or "") == source:
            found = row
    return found


def _unchanged(previous: dict[str, Any], row: dict[str, Any]) -> bool:
    return (
        _same_number(previous.get("market_real"), row["market_real"])
        and _same_number(previous.get("market_live"), row["market_live"])
        and _same_number(previous.get("market_forecast"), row["market_forecast"])
        and str(previous.get("scan_fingerprint") or "") == row["scan_fingerprint"]
    )


def append_market_context(
    *,
    trade_date: date | str,
    market_real: object,
    market_live: object,
    market_forecast: object,
    market_regime: object,
    source: str,
    scan_df: pd.DataFrame | None,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append when Real, live, forecast, or the scan fingerprint changed.

    Identical reruns are skipped. No minimum time gap.
    """
    day = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)[:10]
    src = str(source or "").strip()
    if not day or not src:
        raise ValueError("trade_date and source are required")
    now = as_vn(captured_at or datetime.now())
    row = {
        "trade_date": day,
        "captured_at": now.isoformat(),
        "market_real": _json_number(market_real),
        "market_live": _json_number(market_live),
        "market_forecast": _json_number(market_forecast),
        "market_regime": str(market_regime or ""),
        "source": src,
        "scan_fingerprint": scan_fingerprint(scan_df),
        "status": STATUS_OK,
    }
    dest = Path(path) if path is not None else market_context_path()
    previous = _last_for(_read_rows(dest), day, src) if dest.exists() else None
    if previous is not None and _unchanged(previous, row):
        return {"ok": True, "written": False, "reason": "unchanged", "row": previous}
    append_json_line(dest, row)
    return {"ok": True, "written": True, "reason": "appended", "row": row}


def try_append_market_context(
    *,
    trade_date: date | str,
    market_real: object,
    market_live: object,
    market_forecast: object,
    market_regime: object,
    source: str,
    scan_df: pd.DataFrame | None,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Fail-open. A research write error does not propagate."""
    try:
        return append_market_context(
            trade_date=trade_date,
            market_real=market_real,
            market_live=market_live,
            market_forecast=market_forecast,
            market_regime=market_regime,
            source=source,
            scan_df=scan_df,
            captured_at=captured_at,
            path=path,
        )
    except Exception as exc:  # noqa: BLE001 — research retention must not stop the scan
        return {"ok": False, "written": False, "reason": "write_failed", "error": type(exc).__name__}


def load_market_context(path: Path) -> list[dict[str, Any]]:
    return _read_rows(path)
