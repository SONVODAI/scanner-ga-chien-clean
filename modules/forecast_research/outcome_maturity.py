"""
Forecast outcome maturity — trading-session T3/T5/T10 labels.

T0 records remain immutable. Outcomes are a separate append-only layer.
MFE/MAE basis: equal-weight universe path (see contract.MFE_MAE_BASIS).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.contract import (
    DOWN_PCT,
    FAIL_STRONG_REAL,
    FAIL_STRONG_XS_T5,
    MFE_MAE_BASIS,
    OUTCOME_HORIZONS,
    OUTCOME_SCHEMA_VERSION,
    RECOVER_WEAK_REAL,
    RECOVER_WEAK_XS_T5,
    STRONG_UP_PCT,
    THRESHOLDS_VERSION,
)
from modules.forecast_research.t0_builder import DEFAULT_EMS, DEFAULT_MDT0, load_board, load_market_daily
from modules.forecast_research.t0_persistence import (
    load_outcomes_table,
    load_t0_table,
    persist_outcome_record,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def list_board_trading_dates(ems_path: Path) -> List[str]:
    if not ems_path.exists():
        return []
    df = pd.read_csv(ems_path, usecols=["snapshot_date"], low_memory=False)
    dates = sorted(df["snapshot_date"].astype(str).str[:10].unique().tolist())
    return dates


def _session_index(dates: Sequence[str], trade_date: str) -> Optional[int]:
    td = str(trade_date)[:10]
    try:
        return list(dates).index(td)
    except ValueError:
        return None


def _xs_stats(ems_path: Path, d0: str, d1: str) -> Dict[str, float]:
    a = load_board(ems_path, d0)
    b = load_board(ems_path, d1)
    if a.empty or b.empty:
        return {
            "xs_mean_return": float("nan"),
            "xs_median_return": float("nan"),
            "xs_positive_share": float("nan"),
            "n_common": 0,
        }
    a = a.set_index("symbol")["price"] if "price" in a.columns else pd.Series(dtype=float)
    b = b.set_index("symbol")["price"] if "price" in b.columns else pd.Series(dtype=float)
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return {
            "xs_mean_return": float("nan"),
            "xs_median_return": float("nan"),
            "xs_positive_share": float("nan"),
            "n_common": 0,
        }
    rets = (b.loc[common] / a.loc[common] - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "xs_mean_return": float(rets.mean() * 100.0),
        "xs_median_return": float(rets.median() * 100.0),
        "xs_positive_share": float((rets > 0).mean() * 100.0),
        "n_common": int(len(rets)),
    }


def _ew_path_mfe_mae(ems_path: Path, dates: Sequence[str], i0: int, horizon: int) -> Dict[str, float]:
    """
    Build EW level path from T0 to Th using consecutive board mean returns.
    MFE = max cumulative % from T0; MAE = min cumulative % from T0.
    """
    if i0 + horizon >= len(dates):
        return {"mfe": float("nan"), "mae": float("nan"), "ew_return": float("nan")}
    level = 100.0
    path = []
    prev_date = dates[i0]
    for k in range(1, horizon + 1):
        d1 = dates[i0 + k]
        stats = _xs_stats(ems_path, prev_date, d1)
        r = stats["xs_mean_return"]
        if pd.isna(r):
            return {"mfe": float("nan"), "mae": float("nan"), "ew_return": float("nan")}
        level *= 1.0 + (r / 100.0)
        path.append(level / 100.0 * 100.0 - 100.0)
        prev_date = d1
    if not path:
        return {"mfe": float("nan"), "mae": float("nan"), "ew_return": float("nan")}
    return {"mfe": float(max(path)), "mae": float(min(path)), "ew_return": float(path[-1])}


def _vni_return(md_path: Path, d0: str, d_h: str) -> float:
    a = load_market_daily(md_path, d0)
    b = load_market_daily(md_path, d_h)
    if not a or not b:
        return float("nan")
    c0 = pd.to_numeric(a.get("vnindex_close"), errors="coerce")
    c1 = pd.to_numeric(b.get("vnindex_close"), errors="coerce")
    if pd.isna(c0) or pd.isna(c1) or float(c0) == 0:
        return float("nan")
    return float((float(c1) / float(c0) - 1.0) * 100.0)


def _breadth_change(t0_row: pd.Series, later: Optional[pd.Series]) -> float:
    if later is None or "rsi50_share" not in t0_row or "rsi50_share" not in later:
        return float("nan")
    a = pd.to_numeric(t0_row.get("rsi50_share"), errors="coerce")
    b = pd.to_numeric(later.get("rsi50_share"), errors="coerce")
    if pd.isna(a) or pd.isna(b):
        return float("nan")
    return float(b - a)


def build_outcome_record(
    t0_row: pd.Series,
    horizon: int,
    *,
    session_dates: Sequence[str],
    ems_path: Path,
    md_path: Path,
    t0_table: pd.DataFrame,
) -> Optional[Dict[str, Any]]:
    td = str(t0_row["trade_date"])[:10]
    i0 = _session_index(session_dates, td)
    if i0 is None:
        return None
    if i0 + horizon >= len(session_dates):
        return None  # not mature

    d_h = session_dates[i0 + horizon]
    xs = _xs_stats(ems_path, td, d_h)
    path = _ew_path_mfe_mae(ems_path, session_dates, i0, horizon)
    vni = _vni_return(md_path, td, d_h)

    later_row = None
    if not t0_table.empty:
        hit = t0_table[t0_table["trade_date"].astype(str).str[:10] == d_h]
        if not hit.empty:
            later_row = hit.iloc[-1]

    xs_mean = path["ew_return"] if pd.notna(path["ew_return"]) else xs["xs_mean_return"]
    real0 = pd.to_numeric(t0_row.get("market_real"), errors="coerce")

    up = int(xs_mean > 0) if pd.notna(xs_mean) else None
    strong_up = int(xs_mean >= STRONG_UP_PCT) if pd.notna(xs_mean) else None
    down = int(xs_mean <= DOWN_PCT) if pd.notna(xs_mean) else None
    recover_weak = None
    fail_strong = None
    if pd.notna(real0) and pd.notna(xs_mean):
        recover_weak = int(float(real0) < RECOVER_WEAK_REAL and xs_mean >= RECOVER_WEAK_XS_T5) if horizon == 5 else None
        fail_strong = int(float(real0) >= FAIL_STRONG_REAL and xs_mean <= FAIL_STRONG_XS_T5) if horizon == 5 else None

    body = {
        "trade_date": td,
        "horizon": int(horizon),
        "mature_trade_date": d_h,
        "xs_mean_return": xs_mean,
        "xs_median_return": xs["xs_median_return"],
        "xs_positive_share": xs["xs_positive_share"],
        "n_common": xs["n_common"],
        "mfe": path["mfe"],
        "mae": path["mae"],
        "mfe_mae_basis": MFE_MAE_BASIS,
        "vni_return": vni,
        "rsi50_share_change": _breadth_change(t0_row, later_row),
        "label_up": up,
        "label_strong_up": strong_up,
        "label_down": down,
        "label_recover_weak": recover_weak,
        "label_fail_strong": fail_strong,
        "thresholds_version": THRESHOLDS_VERSION,
        "outcome_schema_version": OUTCOME_SCHEMA_VERSION,
        "t0_feature_hash": t0_row.get("feature_hash"),
        "created_at": _utc_now_iso(),
    }
    body["outcome_hash"] = _stable_hash({k: v for k, v in body.items() if k != "created_at"})
    return body


def mature_all_outcomes(
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    horizons: Sequence[int] = OUTCOME_HORIZONS,
) -> Dict[str, Any]:
    t0 = load_t0_table(data_dir)
    if t0.empty:
        return {"ok": True, "written": 0, "skipped": 0, "reason": "no_t0_records"}
    dates = list_board_trading_dates(ems_path)
    written = 0
    skipped = 0
    details: List[Dict[str, Any]] = []
    for _, row in t0.iterrows():
        for h in horizons:
            rec = build_outcome_record(
                row,
                int(h),
                session_dates=dates,
                ems_path=ems_path,
                md_path=md_path,
                t0_table=t0,
            )
            if rec is None:
                skipped += 1
                continue
            ok, reason = persist_outcome_record(rec, data_dir=data_dir)
            details.append({"trade_date": rec["trade_date"], "horizon": h, "written": ok, "reason": reason})
            if ok:
                written += 1
            else:
                skipped += 1
    return {"ok": True, "written": written, "skipped": skipped, "details": details}
