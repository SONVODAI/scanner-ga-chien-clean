"""
Observation-ledger maturity on eligible Vietnam trading sessions.

Observational research memory only. Never births ACTIVE edges or LIVE_FORWARD.
T3/T5/T10 count subsequent eligible VN sessions, never calendar days.
Non-trading days do not mature any horizon.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.actionable_research.paths import FusionPaths
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
    offset_trading_sessions,
)

HORIZON_N = {"T3": 3, "T5": 5, "T10": 10}
IMMUTABLE_T0_FIELDS = frozenset(
    {
        "observation_id",
        "trade_date",
        "symbol",
        "authority",
        "observation_relation",
        "edge_status",
        "matched_edge_ids",
        "activity_status",
        "trading_value_status",
        "volume_acceleration_status",
        "price_direction",
        "foreign_flow_status",
        "market_state",
        "market_transition",
        "stock_state",
        "camera_cutoff_timestamp",
        "evidence_summary",
        "reasons",
        "original_evidence_labels",
        "provenance",
        "generated_at",
    }
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(pd.Timestamp(ts).normalize().date())


def target_session_for_horizon(t0_date: str, horizon: str) -> Optional[str]:
    offset = HORIZON_N.get(horizon)
    if not offset:
        return None
    return offset_trading_sessions(str(t0_date)[:10], int(offset))


def current_session_is_eligible(trade_date: str) -> bool:
    return bool(evaluate_calendar_session_eligibility(str(trade_date)[:10]).eligible)


def load_observation_ledger(paths: FusionPaths) -> List[Dict[str, Any]]:
    path = paths.observation_ledger_path()
    rows: List[Dict[str, Any]] = []
    if not path.exists() or path.stat().st_size <= 0:
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _atomic_write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _freeze_price_map(paths: FusionPaths) -> Dict[tuple, float]:
    path = paths.t0_freeze_path()
    out: Dict[tuple, float] = {}
    if not path.exists() or path.stat().st_size <= 0:
        return out
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return out
    if df.empty or "trade_date" not in df.columns or "symbol" not in df.columns:
        return out
    price_col = next((c for c in ("price", "close", "t0_price") if c in df.columns), None)
    if price_col is None:
        return out
    work = df.copy()
    work["trade_date"] = work["trade_date"].map(_norm_date)
    work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    work[price_col] = pd.to_numeric(work[price_col], errors="coerce")
    for _, row in work.iterrows():
        val = row[price_col]
        if pd.isna(val) or float(val) == 0:
            continue
        out[(str(row["trade_date"])[:10], str(row["symbol"]))] = float(val)
    return out


def _horizon_return(
    *,
    t0: str,
    symbol: str,
    horizon: str,
    as_of: str,
    prices: Dict[tuple, float],
) -> Dict[str, Any]:
    target = target_session_for_horizon(t0, horizon)
    result: Dict[str, Any] = {
        "horizon": horizon,
        "target_session": target,
        "status": "PENDING",
        "return_pct": None,
        "reason": "",
    }
    if not target:
        result["reason"] = "TARGET_SESSION_UNRESOLVED"
        return result
    if str(as_of)[:10] < target:
        result["reason"] = "TARGET_SESSION_NOT_REACHED"
        return result
    p0 = prices.get((str(t0)[:10], symbol))
    pn = prices.get((target, symbol))
    if p0 is None or pn is None or p0 == 0:
        result["reason"] = "PRICE_UNAVAILABLE_STAY_PENDING"
        return result
    result["status"] = "MATURE"
    result["return_pct"] = (pn / p0 - 1.0) * 100.0
    result["reason"] = "TRADING_SESSION_OHLCV_OR_FREEZE_PRICE"
    return result


def mature_observation_ledger(
    *,
    as_of_trade_date: str,
    paths: FusionPaths,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Advance PENDING T3/T5/T10 using eligible VN sessions only.

    First-write-wins on each horizon field. Never writes 0 for missing prices.
    No-op on non-trading days unless force=True (tests only).
    """
    td = str(as_of_trade_date)[:10]
    if not force and not current_session_is_eligible(td):
        return {
            "ran": False,
            "skipped": True,
            "reason": "NON_TRADING_DAY_NO_MATURITY",
            "as_of": td,
            "matured_horizons": 0,
            "still_pending": 0,
        }
    rows = load_observation_ledger(paths)
    if not rows:
        return {
            "ran": True,
            "skipped": False,
            "reason": "EMPTY_LEDGER",
            "as_of": td,
            "matured_horizons": 0,
            "still_pending": 0,
        }
    prices = _freeze_price_map(paths)
    matured = 0
    pending = 0
    now = _iso_now()
    updated: List[Dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        t0 = str(out.get("trade_date") or "")[:10]
        symbol = str(out.get("symbol") or "").upper()
        horizon_statuses = []
        for horizon, key in (("T3", "t3_return_pct"), ("T5", "t5_return_pct"), ("T10", "t10_return_pct")):
            existing = out.get(key)
            status_key = f"{horizon.lower()}_status"
            target_key = f"{horizon.lower()}_target_session"
            if existing is not None:
                horizon_statuses.append("MATURE")
                if not out.get(target_key):
                    out[target_key] = target_session_for_horizon(t0, horizon)
                continue
            info = _horizon_return(t0=t0, symbol=symbol, horizon=horizon, as_of=td, prices=prices)
            out[target_key] = info.get("target_session")
            if info["status"] == "MATURE":
                out[key] = info["return_pct"]
                out[status_key] = "MATURE"
                out[f"{horizon.lower()}_matured_at"] = now
                matured += 1
                horizon_statuses.append("MATURE")
            else:
                out[status_key] = "PENDING"
                out[f"{horizon.lower()}_pending_reason"] = info.get("reason")
                pending += 1
                horizon_statuses.append("PENDING")
        if all(s == "MATURE" for s in horizon_statuses):
            out["outcome_status"] = "MATURE"
        elif any(s == "MATURE" for s in horizon_statuses):
            out["outcome_status"] = "PARTIAL"
        else:
            out["outcome_status"] = "PENDING"
        out["maturity_basis"] = "vn_trading_sessions"
        out["maturity_as_of"] = td
        updated.append(out)
    _atomic_write_jsonl(paths.observation_ledger_path(), updated)
    return {
        "ran": True,
        "skipped": False,
        "reason": "OK",
        "as_of": td,
        "matured_horizons": matured,
        "still_pending": pending,
        "row_count": len(updated),
    }
