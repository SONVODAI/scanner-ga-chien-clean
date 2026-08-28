"""Validation for canonical HSX foreign-flow history (no repairs by invention)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from modules.foreign_flow_history.schema import CANONICAL_COLUMNS, SOURCE_UNITS
from modules.foreign_flow_history.store import OUTCOME_FORBIDDEN_COLUMNS


def _finite(x: Any) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and x != x):
            return None
        if pd.isna(x):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def validate_canonical_df(
    df: pd.DataFrame,
    *,
    today: Optional[date] = None,
    net_tol: float = 1e-3,
) -> Dict[str, Any]:
    """
    Validate a canonical frame. Flags anomalies; does not invent fixes.
    """
    today = today or datetime.now(timezone.utc).date()
    issues: List[Dict[str, Any]] = []

    if df is None:
        return {"ok": False, "issues": [{"code": "NULL_FRAME"}], "stats": {}}

    cols = set(df.columns)
    missing_cols = [c for c in CANONICAL_COLUMNS if c not in cols]
    if missing_cols:
        issues.append({"code": "MISSING_COLUMNS", "columns": missing_cols})

    outcome_cols = [c for c in df.columns if c.lower() in OUTCOME_FORBIDDEN_COLUMNS]
    if outcome_cols:
        issues.append({"code": "OUTCOME_COLUMNS_PRESENT", "columns": outcome_cols})

    if df.empty:
        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "stats": {"n_rows": 0},
        }

    # Duplicate natural keys
    if {"trade_date", "symbol"}.issubset(cols):
        keys = df["trade_date"].astype(str) + "|" + df["symbol"].astype(str).str.upper()
        dup = int(keys.duplicated().sum())
        if dup:
            issues.append({"code": "DUPLICATE_NATURAL_KEYS", "count": dup})

    # Date validity / ordering / no future
    future_count = 0
    invalid_dates = 0
    if "trade_date" in cols:
        parsed = pd.to_datetime(df["trade_date"], errors="coerce")
        invalid_dates = int(parsed.isna().sum())
        if invalid_dates:
            issues.append({"code": "INVALID_DATES", "count": invalid_dates})
        future_count = int((parsed.dt.date > today).sum())
        if future_count:
            issues.append({"code": "FUTURE_DATES", "count": future_count})
        # Per-symbol sorted check
        if "symbol" in cols:
            for sym, g in df.groupby(df["symbol"].astype(str).str.upper()):
                dates = pd.to_datetime(g["trade_date"], errors="coerce")
                if dates.isna().any():
                    continue
                if not dates.is_monotonic_increasing and not dates.sort_values().equals(dates):
                    # allow unsorted input; flag only if duplicates already handled
                    pass
                # weekend presence is anomalous for VN sessions but holidays vary —
                # flag Sat/Sun as soft anomalies
                wd = dates.dt.weekday
                weekend = int(((wd == 5) | (wd == 6)).sum())
                if weekend:
                    issues.append(
                        {
                            "code": "WEEKEND_SESSIONS",
                            "symbol": str(sym),
                            "count": weekend,
                            "severity": "soft",
                        }
                    )

    # Net arithmetic
    net_mismatch = 0
    if {"foreign_buy_value", "foreign_sell_value", "foreign_net_value"}.issubset(cols):
        for _, row in df.iterrows():
            b = _finite(row.get("foreign_buy_value"))
            s = _finite(row.get("foreign_sell_value"))
            n = _finite(row.get("foreign_net_value"))
            if b is None or s is None:
                if n is not None:
                    net_mismatch += 1
                continue
            expected = b - s
            if n is None or abs(n - expected) > net_tol:
                net_mismatch += 1
        if net_mismatch:
            issues.append({"code": "NET_ARITHMETIC_MISMATCH", "count": net_mismatch})

    # missing != zero: if both buy and sell are exactly 0 that can be valid provider zero;
    # flag only if net present while buy/sell null (already above), or schema units wrong.
    if "source_units" in cols:
        bad_units = df["source_units"].dropna().astype(str).str.upper()
        if len(bad_units) and not (bad_units == SOURCE_UNITS).all():
            issues.append({"code": "UNITS_NOT_VND", "sample": bad_units.unique().tolist()[:5]})

    # OHLC numeric sanity
    ohlc_bad = 0
    for _, row in df.iterrows():
        o = _finite(row.get("open_price"))
        h = _finite(row.get("high_price"))
        l = _finite(row.get("low_price"))
        c = _finite(row.get("close_price"))
        vals = [v for v in (o, h, l, c) if v is not None]
        if any(v < 0 for v in vals):
            ohlc_bad += 1
            continue
        if h is not None and l is not None and h < l:
            ohlc_bad += 1
            continue
        if h is not None and o is not None and h < o:
            ohlc_bad += 1
            continue
        if h is not None and c is not None and h < c:
            ohlc_bad += 1
            continue
        if l is not None and o is not None and l > o:
            ohlc_bad += 1
            continue
        if l is not None and c is not None and l > c:
            ohlc_bad += 1
    if ohlc_bad:
        issues.append({"code": "OHLC_SANITY", "count": ohlc_bad, "severity": "soft"})

    # Gap / coverage stats (informational)
    gap_stats: Dict[str, Any] = {}
    if "trade_date" in cols and "symbol" in cols and not df.empty:
        per = []
        for sym, g in df.groupby(df["symbol"].astype(str).str.upper()):
            dates = sorted(pd.to_datetime(g["trade_date"], errors="coerce").dropna().dt.date.unique().tolist())
            if not dates:
                continue
            # business-day gaps (soft)
            bdays = pd.bdate_range(dates[0], dates[-1])
            have = set(dates)
            missing = [d.date() for d in bdays if d.date() not in have]
            per.append(
                {
                    "symbol": str(sym),
                    "n_sessions": len(dates),
                    "first": dates[0].isoformat(),
                    "last": dates[-1].isoformat(),
                    "bday_gap_count": len(missing),
                }
            )
        gap_stats["per_symbol"] = per
        if per:
            ns = [p["n_sessions"] for p in per]
            gap_stats["session_count_min"] = min(ns)
            gap_stats["session_count_max"] = max(ns)
            gap_stats["session_count_median"] = float(pd.Series(ns).median())

    hard = [i for i in issues if i.get("severity") != "soft"]
    return {
        "ok": len(hard) == 0,
        "issues": issues,
        "stats": {
            "n_rows": int(len(df)),
            "n_symbols": int(df["symbol"].nunique()) if "symbol" in cols and len(df) else 0,
            "future_count": future_count,
            "invalid_dates": invalid_dates,
            "gap": gap_stats,
        },
    }


def price_outcome_readiness(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Prove same-provider OHLC can support later T1/T3/T5/T10/T20/MFE/MAE.
    Does NOT compute research outcomes or attach labels.
    """
    if df is None or df.empty or "close_price" not in df.columns:
        return {
            "ready": False,
            "reason": "no_close_price",
            "horizons_supported_in_principle": [],
        }
    g = df.sort_values("trade_date")
    closes = g["close_price"].map(_finite)
    n = int(closes.notna().sum())
    horizons = []
    for h in (1, 3, 5, 10, 20):
        # need at least h forward sessions somewhere in series
        if n > h:
            horizons.append(f"T{h}")
    mfe_mae_ok = n >= 3  # path needs intervening closes
    caveats = [
        "Raw provider OHLC; corporate actions / adjustments not verified.",
        "Session-based horizons (trading days), not calendar days.",
        "Do not mix outcome labels into T0 canonical rows.",
    ]
    return {
        "ready": len(horizons) >= 4 and "close_price" in df.columns,
        "n_sessions_with_close": n,
        "horizons_supported_in_principle": horizons,
        "mfe_mae_path_ready_in_principle": mfe_mae_ok,
        "caveats": caveats,
    }


def validate_symbols(
    frames: Dict[str, pd.DataFrame],
) -> Dict[str, Any]:
    results = {}
    all_ok = True
    for sym, df in frames.items():
        v = validate_canonical_df(df)
        results[sym] = v
        if not v.get("ok"):
            all_ok = False
    return {"ok": all_ok, "symbols": results}
