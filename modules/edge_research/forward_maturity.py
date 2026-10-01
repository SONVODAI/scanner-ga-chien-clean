"""
Trading-session maturity for Phase B edge-forward births (Phase C).

T+n uses canonical trading sessions via unique_trading_sessions / session_index.
Never calendar days. T0 birth facts are immutable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    BASELINE_CALC_VERSION,
    FORWARD_MATURITY_VERSION,
    FORWARD_OUTCOME_MATURE,
    FORWARD_OUTCOME_PARTIAL,
    FORWARD_OUTCOME_PENDING,
    HORIZON_STATUS_MATURE,
    HORIZON_STATUS_PENDING,
)
from modules.edge_research.forward_ledger import IMMUTABLE_BIRTH_FIELDS, persist_maturity_updates
from modules.edge_research.metrics import HORIZONS
from modules.edge_research.oos import session_index, unique_trading_sessions
from modules.edge_research.outcomes import forward_return_at_index, normalize_ohlcv
from modules.edge_research.storage import ensure_storage, read_ledger
from modules.edge_research.t0_universe import load_t0_freeze

HORIZON_N = {"T3": 3, "T5": 5, "T10": 10}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(pd.Timestamp(ts).normalize().date())


def resolve_session_calendar(
    *,
    session_calendar: Optional[Sequence[str]] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
) -> List[pd.Timestamp]:
    if session_calendar:
        dates = sorted({pd.Timestamp(d).normalize() for d in session_calendar})
        return dates
    parts: List[pd.Timestamp] = []
    if freeze_df is not None and not freeze_df.empty:
        parts.extend(unique_trading_sessions(freeze_df))
    else:
        try:
            freeze_df = load_t0_freeze()
            parts.extend(unique_trading_sessions(freeze_df))
        except Exception:
            pass
    if ohlcv_by_symbol:
        for frame in ohlcv_by_symbol.values():
            if frame is None or frame.empty:
                continue
            work = frame.copy()
            col = "date" if "date" in work.columns else "trade_date"
            if col not in work.columns:
                continue
            parts.extend(unique_trading_sessions(work, date_col=col))
    return sorted(set(parts))


def target_trading_session(
    sessions: Sequence[pd.Timestamp],
    t0_date: str,
    horizon: int,
) -> Optional[str]:
    idx = session_index(sessions, t0_date)
    if idx is None:
        return None
    tgt = idx + int(horizon)
    if tgt >= len(sessions):
        return None
    return _norm_date(sessions[tgt])


def _close_on(frame: pd.DataFrame, date: str) -> Optional[float]:
    if frame is None or frame.empty:
        return None
    work = normalize_ohlcv(frame)
    ts = pd.Timestamp(date).normalize()
    hit = work[work["date"] == ts]
    if hit.empty:
        return None
    val = pd.to_numeric(hit.iloc[0]["close"], errors="coerce")
    if pd.isna(val) or float(val) == 0:
        return None
    return float(val)


def lookup_horizon_outcome(
    symbol: str,
    t0_date: str,
    horizon: int,
    *,
    sessions: Sequence[pd.Timestamp],
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Resolve T+n return using trading-session OHLCV first, then outcomes.csv.

    Missing data stays pending — never writes 0.
    """
    target = target_trading_session(sessions, t0_date, horizon)
    result: Dict[str, Any] = {
        "target_date": target or "",
        "status": HORIZON_STATUS_PENDING,
        "return": None,
        "close_t0": None,
        "close_tn": None,
        "source": "",
    }
    sym = str(symbol).upper().strip()
    # OHLCV T+n is only valid when the trading-session target exists.
    if target and ohlcv_by_symbol and sym in ohlcv_by_symbol:
        frame = normalize_ohlcv(ohlcv_by_symbol[sym])
        t0_idx_matches = frame.index[frame["date"] == pd.Timestamp(t0_date).normalize()].tolist()
        if t0_idx_matches:
            t0_idx = int(t0_idx_matches[0])
            ret = forward_return_at_index(frame["close"], t0_idx, horizon)
            c0 = _close_on(frame, t0_date)
            cn = _close_on(frame, target)
            if ret is not None:
                result.update(
                    {
                        "status": HORIZON_STATUS_MATURE,
                        "return": float(ret),
                        "close_t0": c0,
                        "close_tn": cn,
                        "source": "ohlcv_trading_sessions",
                    }
                )
                return result
    if outcomes_df is not None and not outcomes_df.empty:
        work = outcomes_df.copy()
        work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
        if "entry_date" in work.columns:
            work["entry_date"] = pd.to_datetime(work["entry_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            sub = work[
                (work["symbol"] == sym)
                & (work["entry_date"] == _norm_date(t0_date))
                & (pd.to_numeric(work.get("horizon"), errors="coerce") == horizon)
            ]
            if not sub.empty:
                ret = pd.to_numeric(sub.iloc[0].get("return_pct"), errors="coerce")
                if pd.notna(ret):
                    tgt = ""
                    if "target_date" in sub.columns:
                        tgt = _norm_date(sub.iloc[0].get("target_date"))
                    c0 = pd.to_numeric(sub.iloc[0].get("entry_price"), errors="coerce") if "entry_price" in sub.columns else None
                    cn = pd.to_numeric(sub.iloc[0].get("target_price"), errors="coerce") if "target_price" in sub.columns else None
                    result.update(
                        {
                            "status": HORIZON_STATUS_MATURE,
                            "return": float(ret),
                            "close_t0": None if c0 is None or pd.isna(c0) else float(c0),
                            "close_tn": None if cn is None or pd.isna(cn) else float(cn),
                            "target_date": tgt or target or result["target_date"],
                            "source": "outcomes_csv",
                        }
                    )
                    return result
    return result


def _overall_outcome_status(row: Mapping[str, Any]) -> str:
    statuses = [str(row.get(f"{h.lower()}_status") or HORIZON_STATUS_PENDING) for h in HORIZONS]
    matured = sum(1 for s in statuses if s == HORIZON_STATUS_MATURE)
    if matured <= 0:
        return FORWARD_OUTCOME_PENDING
    if matured >= 3:
        return FORWARD_OUTCOME_MATURE
    return FORWARD_OUTCOME_PARTIAL


def mature_edge_forward_ledger(
    session_date: str,
    *,
    data_dir: Optional[Path] = None,
    session_calendar: Optional[Sequence[str]] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Mature PENDING/PARTIAL births whose trading-session horizons have arrived.

    Idempotent: already-MATURE horizons are not rewritten.
    """
    root = ensure_storage(data_dir)
    as_of = _norm_date(session_date)
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
    if ohlcv_by_symbol is None and outcomes_df is None:
        try:
            from modules.edge_research.adapters import load_canonical_maturity_inputs

            prod_outcomes, prod_dates = load_canonical_maturity_inputs()
            if outcomes_df is None and prod_outcomes is not None and not prod_outcomes.empty:
                outcomes_df = prod_outcomes
            if session_calendar is None and prod_dates:
                session_calendar = prod_dates
        except Exception:
            pass
    sessions = resolve_session_calendar(
        session_calendar=session_calendar,
        freeze_df=freeze_df,
        ohlcv_by_symbol=ohlcv_by_symbol,
    )
    if not as_of:
        return {"ok": False, "reason": "SESSION_DATE_MISSING", "matured_horizons": 0, "rows": 0}
    if not sessions:
        return {"ok": False, "reason": "SESSION_CALENDAR_UNAVAILABLE", "matured_horizons": 0, "rows": int(len(ledger))}
    if ledger.empty:
        return {"ok": True, "reason": "NO_BIRTHS", "matured_horizons": 0, "rows": 0, "as_of": as_of}

    as_of_ts = pd.Timestamp(as_of).normalize()
    now = _iso_now()
    updates: List[Dict[str, Any]] = []
    matured_horizons = 0
    skipped_idempotent = 0

    for _, row in ledger.iterrows():
        t0 = _norm_date(row.get("t0_trade_date") or row.get("t0_date"))
        symbol = str(row.get("symbol") or "").upper().strip()
        if not t0 or not symbol:
            continue
        patch: Dict[str, Any] = {
            "ledger_id": row.get("ledger_id"),
            "maturity_policy_version": FORWARD_MATURITY_VERSION,
        }
        changed = False
        for h in HORIZONS:
            n = HORIZON_N[h]
            prefix = h.lower()
            status_col = f"{prefix}_status"
            existing_status = str(row.get(status_col) or HORIZON_STATUS_PENDING)
            target = target_trading_session(sessions, t0, n)
            patch[f"{prefix}_target_date"] = target or row.get(f"{prefix}_target_date") or ""
            if existing_status == HORIZON_STATUS_MATURE:
                skipped_idempotent += 1
                continue
            if target and pd.Timestamp(target).normalize() > as_of_ts:
                continue
            outcome = lookup_horizon_outcome(
                symbol,
                t0,
                n,
                sessions=sessions,
                ohlcv_by_symbol=ohlcv_by_symbol,
                outcomes_df=outcomes_df,
            )
            outcome_target = _norm_date(outcome.get("target_date") or target)
            if outcome_target and pd.Timestamp(outcome_target).normalize() > as_of_ts:
                continue
            if not target and not outcome_target:
                continue
            if outcome["status"] != HORIZON_STATUS_MATURE:
                continue
            patch[status_col] = HORIZON_STATUS_MATURE
            patch[f"{prefix}_return"] = outcome["return"]
            patch[f"{prefix}_close_t0"] = outcome.get("close_t0")
            patch[f"{prefix}_close_tn"] = outcome.get("close_tn")
            patch[f"{prefix}_matured_at"] = now
            patch[f"{prefix}_source"] = outcome.get("source")
            patch[f"{prefix}_target_date"] = outcome.get("target_date") or target or outcome_target
            changed = True
            matured_horizons += 1
        if changed:
            merged = dict(row)
            merged.update(patch)
            patch["outcome_status"] = _overall_outcome_status(merged)
            updates.append(patch)

    persist_maturity_updates(updates, data_dir=root)
    return {
        "ok": True,
        "reason": "OK",
        "as_of": as_of,
        "rows": int(len(ledger)),
        "updated_rows": len(updates),
        "matured_horizons": matured_horizons,
        "idempotent_skips": skipped_idempotent,
        "maturity_version": FORWARD_MATURITY_VERSION,
        "baseline_calc_version": BASELINE_CALC_VERSION,
        "immutable_fields": list(IMMUTABLE_BIRTH_FIELDS),
    }
