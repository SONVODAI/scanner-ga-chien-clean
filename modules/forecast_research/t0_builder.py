"""
Build Forecast T0 feature records from existing canonical sources.

Primary board: data/earning_money_snapshots.csv (full-universe DNA).
Market aggregates / VNI: data/earning_learning/market_daily_t0.csv when present.
Does not invent missing historical fields.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_INVALID,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_WAITING,
    CONTRACT_VERSION,
    EXPECTED_UNIVERSE_SIZE,
    FEATURE_SCHEMA_VERSION,
    GROUPS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMS = REPO_ROOT / "data" / "earning_money_snapshots.csv"
DEFAULT_MDT0 = REPO_ROOT / "data" / "earning_learning" / "market_daily_t0.csv"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_board(ems_path: Path, trade_date: str) -> pd.DataFrame:
    if not ems_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(ems_path, low_memory=False)
    if "snapshot_date" not in df.columns:
        return pd.DataFrame()
    d = df["snapshot_date"].astype(str).str[:10]
    out = df.loc[d == trade_date].copy()
    return out


def load_market_daily(md_path: Path, trade_date: str) -> Optional[Dict[str, Any]]:
    if not md_path.exists():
        return None
    md = pd.read_csv(md_path, low_memory=False)
    if md.empty or "trade_date" not in md.columns:
        return None
    md["trade_date"] = md["trade_date"].astype(str).str[:10]
    hit = md[md["trade_date"] == trade_date]
    if hit.empty:
        return None
    return hit.iloc[-1].to_dict()


def _share(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return float("nan")
    return float(series.mean())


def _calc_fc(board: pd.DataFrame) -> float:
    total = len(board)
    if total == 0:
        return float("nan")
    strong = int((board["group"] == "CP MẠNH").sum()) if "group" in board.columns else 0
    accel = int((board["group"] == "GÀ TĂNG TỐC").sum()) if "group" in board.columns else 0
    breakout = int((board["group"] == "MUA BREAK").sum()) if "group" in board.columns else 0
    pull_good = int((board["group"] == "PULL ĐẸP").sum()) if "group" in board.columns else 0
    weak = int((board["group"] == "THEO DÕI").sum()) if "group" in board.columns else 0
    obv = _share(board["obv_status"] == "🟢") if "obv_status" in board.columns else 0.0
    slope = _share(pd.to_numeric(board.get("ema9_ma20_slope"), errors="coerce") > 0)
    score = (
        min(accel / 5, 2)
        + min(strong / 10, 2)
        + min(breakout / 8, 2)
        + min(pull_good / 8, 2)
        + obv
        + slope
        - min(weak / 15, 2)
    )
    return round(max(min(float(score), 10.0), 0.0), 1)


def build_t0_features_from_board(board: pd.DataFrame) -> Dict[str, Any]:
    """Derive T0 cross-section features from a same-day full board snapshot."""
    feats: Dict[str, Any] = {}
    n = len(board)
    feats["universe_count"] = int(n)
    for gr in GROUPS:
        cnt = int((board["group"] == gr).sum()) if "group" in board.columns else 0
        feats[f"cnt_{gr}"] = cnt
        feats[f"share_{gr}"] = (cnt / n) if n else float("nan")

    rsi = pd.to_numeric(board["rsi14"], errors="coerce") if "rsi14" in board.columns else pd.Series(dtype=float)
    feats["rsi40_share"] = _share(rsi > 40)
    feats["rsi50_share"] = _share(rsi > 50)
    feats["rsi60_share"] = _share(rsi > 60)
    feats["med_rsi14"] = float(rsi.median()) if len(rsi.dropna()) else float("nan")

    if "obv_status" in board.columns:
        feats["obv_green_share"] = _share(board["obv_status"] == "🟢")
    else:
        feats["obv_green_share"] = float("nan")

    slope = pd.to_numeric(board["ema9_ma20_slope"], errors="coerce") if "ema9_ma20_slope" in board.columns else pd.Series(dtype=float)
    feats["slope_pos_share"] = _share(slope > 0)

    rs5 = pd.to_numeric(board["rs5"], errors="coerce") if "rs5" in board.columns else pd.Series(dtype=float)
    rs10 = pd.to_numeric(board["rs10"], errors="coerce") if "rs10" in board.columns else pd.Series(dtype=float)
    feats["mean_rs5"] = float(rs5.mean()) if len(rs5.dropna()) else float("nan")
    feats["mean_rs10"] = float(rs10.mean()) if len(rs10.dropna()) else float("nan")
    feats["pos_rs5_share"] = _share(rs5 > 0)
    feats["pos_rs10_share"] = _share(rs10 > 0)
    feats["rs5_dispersion"] = float(rs5.std()) if len(rs5.dropna()) > 1 else float("nan")

    near20 = pd.to_numeric(board["near_bottom_20_pct"], errors="coerce") if "near_bottom_20_pct" in board.columns else pd.Series(dtype=float)
    near60 = pd.to_numeric(board["near_bottom_60_pct"], errors="coerce") if "near_bottom_60_pct" in board.columns else pd.Series(dtype=float)
    feats["near_low20_share"] = _share(near20 <= 2)
    feats["near_low60_share"] = _share(near60 <= 3)

    if "dist_high20_pct" in board.columns:
        dist_hi = pd.to_numeric(board["dist_high20_pct"], errors="coerce")
        feats["near_high20_share"] = _share(dist_hi >= -2)
    else:
        feats["near_high20_share"] = float("nan")

    pos = board.loc[rs5 > 0].copy() if len(rs5) else pd.DataFrame()
    if not pos.empty and "rs5" in pos.columns and float(pos["rs5"].sum()) != 0:
        top = pos.sort_values("rs5", ascending=False).head(10)
        feats["lead_conc_top10"] = float(top["rs5"].sum() / pos["rs5"].sum())
    else:
        feats["lead_conc_top10"] = float("nan")

    # Prefer board-embedded market scores when present; else recompute FC.
    for col, key in (
        ("market_real", "market_real"),
        ("market_live", "market_live"),
        ("market_forecast", "market_forecast"),
    ):
        if col in board.columns and board[col].notna().any():
            feats[key] = float(pd.to_numeric(board[col], errors="coerce").dropna().iloc[-1])
        else:
            feats[key] = float("nan")
    if pd.isna(feats.get("market_forecast")):
        feats["market_forecast"] = _calc_fc(board)
    return feats


def _attach_trajectories(record: Dict[str, Any], history: pd.DataFrame) -> Dict[str, Any]:
    """Add PIT Δ1/Δ3/Δ5 from prior COMPLETE/PARTIAL T0 history (no future rows)."""
    if history is None or history.empty:
        for key in ("market_real", "market_forecast", "rsi50_share", "obv_green_share", "slope_pos_share"):
            for h in (1, 3, 5):
                record[f"{key}_d{h}"] = float("nan")
        record["fc_accel_1"] = float("nan")
        record["real_minus_fc"] = (
            float(record["market_real"]) - float(record["market_forecast"])
            if pd.notna(record.get("market_real")) and pd.notna(record.get("market_forecast"))
            else float("nan")
        )
        record["live_minus_fc"] = (
            float(record["market_live"]) - float(record["market_forecast"])
            if pd.notna(record.get("market_live")) and pd.notna(record.get("market_forecast"))
            else float("nan")
        )
        return record

    hist = history.sort_values("trade_date")
    # only prior dates
    prior = hist[hist["trade_date"].astype(str) < str(record["trade_date"])].copy()
    for key in ("market_real", "market_forecast", "rsi50_share", "obv_green_share", "slope_pos_share"):
        cur = record.get(key)
        for h in (1, 3, 5):
            if len(prior) < h or pd.isna(cur):
                record[f"{key}_d{h}"] = float("nan")
            else:
                prev = pd.to_numeric(prior.iloc[-h][key], errors="coerce") if key in prior.columns else np.nan
                record[f"{key}_d{h}"] = float(cur) - float(prev) if pd.notna(prev) else float("nan")
    d1 = record.get("market_forecast_d1")
    if len(prior) >= 2 and pd.notna(d1) and "market_forecast" in prior.columns:
        prev_d1 = float(prior.iloc[-1]["market_forecast"]) - float(prior.iloc[-2]["market_forecast"])
        record["fc_accel_1"] = float(d1) - prev_d1
    else:
        record["fc_accel_1"] = float("nan")

    record["real_minus_fc"] = (
        float(record["market_real"]) - float(record["market_forecast"])
        if pd.notna(record.get("market_real")) and pd.notna(record.get("market_forecast"))
        else float("nan")
    )
    record["live_minus_fc"] = (
        float(record["market_live"]) - float(record["market_forecast"])
        if pd.notna(record.get("market_live")) and pd.notna(record.get("market_forecast"))
        else float("nan")
    )
    return record


def assess_completeness(universe_count: int, has_market_daily: bool, board_empty: bool) -> str:
    if board_empty:
        return COMPLETENESS_WAITING
    if universe_count <= 0:
        return COMPLETENESS_INVALID
    if universe_count == EXPECTED_UNIVERSE_SIZE and has_market_daily:
        return COMPLETENESS_COMPLETE
    if universe_count == EXPECTED_UNIVERSE_SIZE:
        return COMPLETENESS_PARTIAL  # full board but missing canonical market_daily_t0 / VNI
    if universe_count > 0:
        return COMPLETENESS_PARTIAL
    return COMPLETENESS_INVALID


def build_forecast_t0_record(
    trade_date: str,
    *,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    prior_t0_history: Optional[pd.DataFrame] = None,
    snapshot_asof: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Build one Forecast T0 record for trade_date from existing stores.

    Returns (record_or_None, reason).
    """
    trade_date = str(trade_date)[:10]
    board = load_board(ems_path, trade_date)
    md = load_market_daily(md_path, trade_date)

    if board.empty and md is None:
        return None, COMPLETENESS_WAITING

    feats = build_t0_features_from_board(board) if not board.empty else {
        "universe_count": 0,
        "market_real": float("nan"),
        "market_live": float("nan"),
        "market_forecast": float("nan"),
    }

    # Prefer canonical market_daily_t0 scores / VNI when available (official AFTER_CLOSE).
    if md is not None:
        for src, dst in (
            ("market_real", "market_real"),
            ("market_live", "market_live"),
            ("market_forecast", "market_forecast"),
            ("breadth_score", "breadth_score_md"),
            ("vnindex_close", "vnindex_close"),
            ("vnindex_open", "vnindex_open"),
            ("vnindex_high", "vnindex_high"),
            ("vnindex_low", "vnindex_low"),
            ("vnindex_volume", "vnindex_volume"),
            ("vnindex_daily_return_pct", "vnindex_daily_return_pct"),
            ("daily_snapshot_id", "market_daily_snapshot_id"),
            ("captured_at", "market_daily_captured_at"),
        ):
            if src in md and pd.notna(md.get(src)):
                feats[dst] = md.get(src)
        # Prefer MDT0 group counts when present (same day).
        for src, dst in (
            ("ga_tang_toc", "cnt_GÀ TĂNG TỐC"),
            ("cp_manh", "cnt_CP MẠNH"),
            ("mua_break", "cnt_MUA BREAK"),
            ("pull_dep", "cnt_PULL ĐẸP"),
            ("theo_doi", "cnt_THEO DÕI"),
            ("obv_green_pct", "obv_green_share_pct_md"),
            ("slope_positive_pct", "slope_pos_share_pct_md"),
        ):
            if src in md and pd.notna(md.get(src)):
                feats[dst] = md.get(src)

    completeness = assess_completeness(
        int(feats.get("universe_count") or 0),
        has_market_daily=md is not None,
        board_empty=board.empty,
    )

    asof = snapshot_asof or _utc_now_iso()
    source_hashes = {
        "earning_money_snapshots_sha256": _file_sha256(ems_path),
        "market_daily_t0_sha256": _file_sha256(md_path),
    }
    # Feature hash excludes provenance timestamps.
    feature_body = {k: v for k, v in feats.items()}
    feature_hash = _stable_hash({"trade_date": trade_date, "features": feature_body, "schema": FEATURE_SCHEMA_VERSION})

    record: Dict[str, Any] = {
        "trade_date": trade_date,
        "snapshot_asof": asof,
        "data_cutoff": trade_date,
        "contract_version": CONTRACT_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
        "completeness_status": completeness,
        "created_at": _utc_now_iso(),
        "source_ems_path": str(ems_path),
        "source_md_path": str(md_path),
        "source_hashes_json": json.dumps(source_hashes, sort_keys=True),
        "feature_hash": feature_hash,
        "frozen": True,
        **feats,
    }
    record = _attach_trajectories(record, prior_t0_history)
    return record, completeness
