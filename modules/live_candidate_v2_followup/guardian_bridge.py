"""Optional Guardian signal lookup for Follow-up Watch arm C.

Lazy-imports position_guardian when available. Falls back to the same
EMA9/MA20 sell heuristic without touching Streamlit or holdings I/O.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

SIGNAL_SELL_TEXT = "🔴 BÁN"


def _fallback_signal(row: Mapping[str, Any] | pd.Series) -> str:
    def num(key: str) -> float:
        try:
            v = row.get(key) if hasattr(row, "get") else row[key]  # type: ignore[index]
            f = float(v)
            return f if f == f else float("nan")
        except Exception:
            return float("nan")

    price, ema9, ma20 = num("price"), num("ema9"), num("ma20")
    if pd.notna(ema9) and pd.notna(ma20) and ema9 < ma20:
        return SIGNAL_SELL_TEXT
    if pd.notna(price) and pd.notna(ema9) and price < ema9:
        return "🟡 CẢNH BÁO"
    return "🟢 GIỮ"


def guardian_signal_from_row(row: Mapping[str, Any] | pd.Series | None) -> str:
    if row is None:
        return ""
    try:
        from position_guardian import generate_signal

        series = row if isinstance(row, pd.Series) else pd.Series(dict(row))
        signal, _reason, _score = generate_signal(series)
        return str(signal or "")
    except Exception:
        try:
            series = row if isinstance(row, pd.Series) else pd.Series(dict(row))
            return _fallback_signal(series)
        except Exception:
            return ""


def is_guardian_sell(signal: object) -> bool:
    text = str(signal or "").strip()
    if not text:
        return False
    if text == SIGNAL_SELL_TEXT:
        return True
    upper = text.upper()
    return "BÁN" in upper or upper.endswith(" BAN") or "SELL" in upper


def guardian_map_from_scan(scan_df: pd.DataFrame | None) -> dict[str, str]:
    if scan_df is None or not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return {}
    if "symbol" not in scan_df.columns:
        return {}
    out: dict[str, str] = {}
    for _, row in scan_df.iterrows():
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        out[symbol] = guardian_signal_from_row(row)
    return out


__all__ = [
    "guardian_map_from_scan",
    "guardian_signal_from_row",
    "is_guardian_sell",
]
