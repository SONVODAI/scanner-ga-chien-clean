"""
Immutable Market T0 snapshot capture (Phase 1 — evidence preservation only).

Observer-only: does not feed production ranking or decision engines.

Two stores (do not conflate):

``market_t0_snapshot.csv`` — SESSION-LEVEL RESEARCH HISTORY
    Identity: ``(trade_date, entity, session_slot)``
    May contain PRE_MARKET / MORNING / MIDDAY / AFTERNOON / CLOSE / AFTER_CLOSE rows.
    NOT for independent daily T3/T5/T10 population statistics.

``market_daily_t0.csv`` — CANONICAL DAILY MARKET T0 (official pattern memory)
    Identity: ``(trade_date, entity)`` where ``entity = MARKET``
    ONE row per trading day, first-write-wins, frozen at or after 18:00 VN (EOD+3H).
    Future: T3/T5/T10 maturation, MDD/MFE, Market DNA, analog recall, NAV/risk guidance.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from market_snapshot import build_market_snapshot_row, market_session_slot, ms_now

logger = logging.getLogger(__name__)

MARKET_ENTITY = "MARKET"
SNAPSHOT_VERSION = "1.0.0"

# Session-level research store (intraday evidence; not daily statistics population).
MARKET_T0_SNAPSHOT_FILE = "market_t0_snapshot.csv"
MARKET_T0_IDENTITY_COLUMNS = ("trade_date", "entity", "session_slot")

# Canonical daily store (one official Market T0 per trading day).
MARKET_DAILY_T0_FILE = "market_daily_t0.csv"
MARKET_DAILY_IDENTITY_COLUMNS = ("trade_date", "entity")

CANONICAL_RULE = "EOD_PLUS_3H"
MARKET_CLOSE_REFERENCE = "15:00"
ELIGIBLE_AFTER = "18:00"
CANONICAL_ELIGIBLE_MINUTE = 18 * 60  # 18:00 Asia/Ho_Chi_Minh

# Reserved nullable columns for Phase 1B / later outcome join.
VNINDEX_TECH_COLUMNS = (
    "vnindex_open",
    "vnindex_high",
    "vnindex_low",
    "vnindex_close",
    "vnindex_volume",
    "vnindex_daily_return_pct",
    "vnindex_ema9",
    "vnindex_ma20",
    "vnindex_wma45",
    "vnindex_sma50",
    "vnindex_rsi14",
    "vnindex_macd",
    "vnindex_macd_signal",
    "vnindex_macd_histogram",
    "vnindex_bb_middle",
    "vnindex_bb_upper",
    "vnindex_bb_lower",
    "vnindex_atr14",
    "vnindex_obv",
)

MULTI_TF_COLUMNS = (
    "tf_4h_status",
    "tf_daily_status",
    "tf_weekly_status",
    "tf_monthly_status",
)


def _utc_now_iso(now: Optional[datetime] = None) -> str:
    if now is not None and now.tzinfo is not None:
        dt = now.astimezone(timezone.utc).replace(microsecond=0)
    elif now is not None:
        dt = now.replace(tzinfo=timezone.utc, microsecond=0)
    else:
        dt = datetime.now(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def market_snapshot_id(
    trade_date: str,
    entity: str,
    session_slot: str,
) -> str:
    raw = "|".join(str(v).strip() for v in (trade_date, entity, session_slot))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def daily_snapshot_id(trade_date: str, entity: str) -> str:
    """Deterministic canonical identity — ignores session_slot."""
    raw = "|".join(str(v).strip() for v in (trade_date, entity))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_canonical_eligible(now: Optional[datetime] = None) -> bool:
    """
    Canonical daily T0 may freeze only at or after 18:00 Asia/Ho_Chi_Minh.

    Does NOT use session_slot (CLOSE / AFTER_CLOSE) for eligibility.
    """
    if now is None:
        now = ms_now()
    hm = now.hour * 60 + now.minute
    return hm >= CANONICAL_ELIGIBLE_MINUTE


def validate_canonical_trade_date(
    trade_date: str,
    *,
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Ensure runtime ``trade_date`` represents today's VN trading session.

    Uses explicit calendar alignment — never assumes stale scan data is canonical.
    """
    normalized = str(trade_date or "").strip()
    if not normalized:
        return False, "MISSING_TRADE_DATE"

    if now is None:
        now = ms_now()

    vn_today = now.strftime("%Y-%m-%d")
    if normalized != vn_today:
        return False, "TRADE_DATE_MISMATCH"

    return True, ""


def _safe_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return np.nan
        result = float(value)
        return result if np.isfinite(result) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _flatten_breadth_report(report: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "breadth_score": np.nan,
            "breadth_level": "",
            "breadth_total": np.nan,
        }

    out: Dict[str, Any] = {
        "breadth_score": _safe_float(report.get("score")),
        "breadth_level": str(report.get("level") or ""),
        "breadth_total": _safe_float(report.get("total")),
    }
    counts = report.get("counts") or {}
    percentages = report.get("percentages") or {}
    for level in (60, 50, 40, 30, 20, 10):
        out[f"breadth_count_{level}"] = _safe_float(counts.get(level))
        out[f"breadth_pct_{level}"] = _safe_float(percentages.get(level))
    return out


def _fetch_vnindex_ohlcv_for_date(trade_date: str) -> Dict[str, Any]:
    """
    Best-effort same-day VNINDEX OHLCV via vnstock (fail-safe, optional).

    Returns empty dict on any failure. Does not compute indicators in Phase 1.
    """
    out: Dict[str, Any] = {}
    try:
        from vnstock import stock_historical_data

        attempts = (
            {"symbol": "VNINDEX", "type": "index"},
            {"symbol": "VNINDEX", "type": "stock"},
        )
        target = pd.Timestamp(trade_date).date()

        for cfg in attempts:
            try:
                df = stock_historical_data(
                    symbol=cfg["symbol"],
                    start_date=(target - pd.Timedelta(days=14)).isoformat(),
                    end_date=target.isoformat(),
                    resolution="1D",
                    type=cfg["type"],
                    beautify=True,
                )
            except Exception:
                continue
            if df is None or df.empty:
                continue

            rename_map = {}
            for col in df.columns:
                cl = str(col).lower()
                if "date" in cl or "time" in cl:
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
            df = df.rename(columns=rename_map)
            if "date" not in df.columns or "close" not in df.columns:
                continue

            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            row = df[df["date"] == target]
            if row.empty:
                continue

            bar = row.iloc[-1]
            close = _safe_float(bar.get("close"))
            open_ = _safe_float(bar.get("open"))
            out = {
                "vnindex_open": open_,
                "vnindex_high": _safe_float(bar.get("high")),
                "vnindex_low": _safe_float(bar.get("low")),
                "vnindex_close": close,
                "vnindex_volume": _safe_float(bar.get("volume")),
            }
            if np.isfinite(open_) and open_ != 0 and np.isfinite(close):
                out["vnindex_daily_return_pct"] = (close / open_ - 1.0) * 100.0
            return out
    except Exception as exc:
        logger.debug("VNINDEX OHLCV fetch skipped: %s", exc)
    return out


def build_market_t0_row(
    *,
    scan_df: pd.DataFrame,
    trade_date: str,
    market_real: float,
    market_live: float,
    market_forecast: float,
    market_forecast_text: str = "",
    market_confidence: float | None = None,
    market_status: str = "",
    market_action: str = "",
    market_regime: str = "",
    market_regime_note: str = "",
    rsi_breadth_report: Optional[Mapping[str, Any]] = None,
    trading_today: bool = True,
    trading_reason: str = "",
    entity: str = MARKET_ENTITY,
    include_vnindex_ohlcv: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build one immutable Market T0 row from canonical runtime values.

    Does not mutate inputs. Reuses ``build_market_snapshot_row`` for aggregates.
    """
    if now is None:
        now = ms_now()
    session_slot = market_session_slot(now)

    snapshot_row = build_market_snapshot_row(
        scan_df=scan_df,
        market_real=market_real,
        market_live=market_live,
        market_forecast=market_forecast,
        market_forecast_text=market_forecast_text,
        market_status=market_status,
        market_action=market_action,
        trading_today=trading_today,
        trading_reason=trading_reason,
    )

    row: Dict[str, Any] = {
        "market_snapshot_id": market_snapshot_id(trade_date, entity, session_slot),
        "trade_date": str(trade_date),
        "entity": str(entity),
        "session_slot": str(session_slot),
        "snapshot_version": SNAPSHOT_VERSION,
        "captured_at": _utc_now_iso(now),
        "market_real": _safe_float(market_real),
        "market_live": _safe_float(market_live),
        "market_forecast": _safe_float(market_forecast),
        "market_forecast_confidence": _safe_float(market_confidence),
        "market_regime": str(market_regime or ""),
        "market_regime_note": str(market_regime_note or ""),
        "market_forecast_text": str(market_forecast_text or ""),
        "market_status": str(market_status or ""),
        "market_action": str(market_action or ""),
        "trading_today": bool(trading_today),
        "trading_reason": str(trading_reason or ""),
    }
    row.update(_flatten_breadth_report(rsi_breadth_report))

    # Session aggregates from market_snapshot engine (point-in-time from scan_df).
    for key, value in snapshot_row.items():
        if key in row:
            continue
        row[key] = value

    if include_vnindex_ohlcv:
        row.update(_fetch_vnindex_ohlcv_for_date(str(trade_date)))

    for col in VNINDEX_TECH_COLUMNS:
        row.setdefault(col, np.nan)
    for col in MULTI_TF_COLUMNS:
        row.setdefault(col, "")

    return row


def build_market_daily_t0_row(
    session_row: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build canonical daily Market T0 row from session payload + metadata.

    Identity is ``(trade_date, entity)`` via ``daily_snapshot_id`` — session_slot
    is retained only as metadata and does not affect canonical identity.
    """
    trade_date = str(session_row["trade_date"])
    entity = str(session_row.get("entity") or MARKET_ENTITY)

    row = dict(session_row)
    row.pop("market_snapshot_id", None)
    row["daily_snapshot_id"] = daily_snapshot_id(trade_date, entity)
    row["trade_date"] = trade_date
    row["entity"] = entity
    row["canonical_t0"] = True
    row["canonical_rule"] = CANONICAL_RULE
    row["market_close_reference"] = MARKET_CLOSE_REFERENCE
    row["eligible_after"] = ELIGIBLE_AFTER
    row["snapshot_version"] = SNAPSHOT_VERSION
    row["captured_at"] = _utc_now_iso(now)
    return row


def append_market_t0_snapshot(
    existing: pd.DataFrame,
    new_rows: pd.DataFrame,
) -> Tuple[pd.DataFrame, int]:
    """First-write-wins append keyed by ``market_snapshot_id``."""
    if new_rows is None or new_rows.empty:
        return (
            existing.copy() if existing is not None else pd.DataFrame(),
            0,
        )

    prepared = new_rows.copy()
    if "market_snapshot_id" not in prepared.columns:
        raise ValueError("new_rows must contain market_snapshot_id")

    old = existing.copy() if existing is not None else pd.DataFrame()
    if not old.empty and "market_snapshot_id" not in old.columns:
        raise ValueError("existing snapshot file missing market_snapshot_id")

    existing_ids = set()
    if not old.empty:
        existing_ids = set(old["market_snapshot_id"].astype(str))

    to_append = prepared[
        ~prepared["market_snapshot_id"].astype(str).isin(existing_ids)
    ].copy()

    if to_append.empty:
        return old.reset_index(drop=True), 0

    combined = pd.concat([old, to_append], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(
        subset=["market_snapshot_id"],
        keep="first",
    )
    return combined.reset_index(drop=True), int(len(to_append))


def append_market_daily_t0(
    existing: pd.DataFrame,
    new_rows: pd.DataFrame,
) -> Tuple[pd.DataFrame, int]:
    """First-write-wins append keyed by ``daily_snapshot_id`` (canonical daily)."""
    if new_rows is None or new_rows.empty:
        return (
            existing.copy() if existing is not None else pd.DataFrame(),
            0,
        )

    prepared = new_rows.copy()
    if "daily_snapshot_id" not in prepared.columns:
        raise ValueError("new_rows must contain daily_snapshot_id")

    old = existing.copy() if existing is not None else pd.DataFrame()
    if not old.empty and "daily_snapshot_id" not in old.columns:
        raise ValueError("existing daily T0 file missing daily_snapshot_id")

    existing_ids = set()
    if not old.empty:
        existing_ids = set(old["daily_snapshot_id"].astype(str))

    to_append = prepared[
        ~prepared["daily_snapshot_id"].astype(str).isin(existing_ids)
    ].copy()

    if to_append.empty:
        return old.reset_index(drop=True), 0

    combined = pd.concat([old, to_append], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(
        subset=["daily_snapshot_id"],
        keep="first",
    )
    return combined.reset_index(drop=True), int(len(to_append))


def _persist_canonical_daily_t0(
    *,
    session_row: Dict[str, Any],
    trade_date: str,
    data_dir: Optional[str],
    remote_dir: Optional[str],
    now: Optional[datetime],
) -> Dict[str, Any]:
    """Attempt canonical daily freeze; fail-safe, never raises."""
    if not is_canonical_eligible(now):
        return {
            "canonical_added": 0,
            "daily_snapshot_id": None,
            "canonical_skipped_reason": "BEFORE_EOD_PLUS_3H",
        }

    ok_date, date_reason = validate_canonical_trade_date(trade_date, now=now)
    if not ok_date:
        return {
            "canonical_added": 0,
            "daily_snapshot_id": None,
            "canonical_skipped_reason": date_reason,
        }

    daily_row = build_market_daily_t0_row(session_row, now=now)

    from modules.earning_learning import (
        _make_storage,
        _read_csv_from_storage,
        _write_csv_to_storage,
    )

    storage = _make_storage(data_dir, remote_dir)
    existing, _ = _read_csv_from_storage(storage, MARKET_DAILY_T0_FILE)
    merged, added = append_market_daily_t0(existing, pd.DataFrame([daily_row]))

    if added > 0:
        _write_csv_to_storage(
            storage,
            MARKET_DAILY_T0_FILE,
            merged,
            commit_message=(
                f"Mr.BOT append canonical market daily T0 {trade_date} +{added}"
            ),
        )

    return {
        "canonical_added": added,
        "daily_snapshot_id": daily_row.get("daily_snapshot_id"),
        "canonical_skipped_reason": None if added > 0 else "ALREADY_FROZEN",
    }


def capture_market_t0_snapshot(
    *,
    scan_df: pd.DataFrame,
    trade_date: str,
    market_real: float,
    market_live: float,
    market_forecast: float,
    market_forecast_text: str = "",
    market_confidence: float | None = None,
    market_status: str = "",
    market_action: str = "",
    rsi_breadth_report: Optional[Mapping[str, Any]] = None,
    trading_today: bool = True,
    trading_reason: str = "",
    market_regime: str = "",
    market_regime_note: str = "",
    data_dir: Optional[str] = None,
    remote_dir: Optional[str] = None,
    include_vnindex_ohlcv: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build + persist immutable Market T0 snapshot. Fail-safe observer only.

    Writes session research history unconditionally (when trading_today).
    Writes canonical daily T0 only when eligible (>= 18:00 VN, valid trade_date).
    """
    if now is None:
        now = ms_now()

    if trading_today is False:
        return {
            "ok": True,
            "added": 0,
            "skipped_reason": "NON_TRADING_SESSION",
            "canonical_added": 0,
            "daily_snapshot_id": None,
            "canonical_skipped_reason": "NON_TRADING_SESSION",
        }

    try:
        row = build_market_t0_row(
            scan_df=scan_df,
            trade_date=trade_date,
            market_real=market_real,
            market_live=market_live,
            market_forecast=market_forecast,
            market_forecast_text=market_forecast_text,
            market_confidence=market_confidence,
            market_status=market_status,
            market_action=market_action,
            rsi_breadth_report=rsi_breadth_report,
            trading_today=trading_today,
            trading_reason=trading_reason,
            market_regime=market_regime,
            market_regime_note=market_regime_note,
            include_vnindex_ohlcv=include_vnindex_ohlcv,
            now=now,
        )

        from modules.earning_learning import (
            _make_storage,
            _read_csv_from_storage,
            _write_csv_to_storage,
        )

        storage = _make_storage(data_dir, remote_dir)
        existing, _ = _read_csv_from_storage(storage, MARKET_T0_SNAPSHOT_FILE)
        merged, added = append_market_t0_snapshot(
            existing,
            pd.DataFrame([row]),
        )

        if added > 0:
            _write_csv_to_storage(
                storage,
                MARKET_T0_SNAPSHOT_FILE,
                merged,
                commit_message=(
                    f"Mr.BOT append market T0 snapshot {trade_date} "
                    f"{row.get('session_slot')} +{added}"
                ),
            )

        try:
            canonical_result = _persist_canonical_daily_t0(
                session_row=row,
                trade_date=trade_date,
                data_dir=data_dir,
                remote_dir=remote_dir,
                now=now,
            )
        except Exception as exc:
            logger.warning("Canonical daily T0 capture failed safely: %s", exc)
            canonical_result = {
                "canonical_added": 0,
                "daily_snapshot_id": None,
                "canonical_skipped_reason": "STORAGE_ERROR",
            }

        return {
            "ok": True,
            "added": added,
            "market_snapshot_id": row.get("market_snapshot_id"),
            "trade_date": trade_date,
            "session_slot": row.get("session_slot"),
            "skipped_reason": None if added > 0 else "ALREADY_FROZEN",
            **canonical_result,
        }
    except Exception as exc:
        logger.warning("Market T0 capture failed safely: %s", exc)
        return {
            "ok": False,
            "added": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "canonical_added": 0,
            "daily_snapshot_id": None,
            "canonical_skipped_reason": "CAPTURE_ERROR",
        }


__all__ = [
    "CANONICAL_RULE",
    "ELIGIBLE_AFTER",
    "MARKET_CLOSE_REFERENCE",
    "MARKET_DAILY_IDENTITY_COLUMNS",
    "MARKET_DAILY_T0_FILE",
    "MARKET_ENTITY",
    "SNAPSHOT_VERSION",
    "MARKET_T0_SNAPSHOT_FILE",
    "MARKET_T0_IDENTITY_COLUMNS",
    "VNINDEX_TECH_COLUMNS",
    "MULTI_TF_COLUMNS",
    "append_market_daily_t0",
    "append_market_t0_snapshot",
    "build_market_daily_t0_row",
    "build_market_t0_row",
    "capture_market_t0_snapshot",
    "daily_snapshot_id",
    "is_canonical_eligible",
    "market_snapshot_id",
    "validate_canonical_trade_date",
]
