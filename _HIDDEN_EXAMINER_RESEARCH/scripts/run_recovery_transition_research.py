#!/usr/bin/env python3
"""
HIDDEN EXAMINER RESEARCH — decline → recovery transition investigation.

ISOLATION:
  - Reads repo historical CSVs only.
  - Writes exclusively under _HIDDEN_EXAMINER_RESEARCH/.
  - Does not import modules.edge_research (storage.py would create Brain files).
  - Does not modify production/Brain/tests/prompts.

This script is the examiner analysis engine, not a Mr.BOT feature.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO = Path("/workspace")
HIDDEN = REPO / "_HIDDEN_EXAMINER_RESEARCH"
OUT = HIDDEN / "outputs"
FROZEN = HIDDEN / "FROZEN_BENCHMARK_PACKAGE"
SCRIPTS = HIDDEN / "scripts"

TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_ID = f"examiner-recovery-transition-{TIMESTAMP.replace(':', '').replace('-', '')}"

BRAIN_INPUT_PATHS = [
    "data/earning_learning/",
    "data/edge_research/",
    "research_exports/",
    "pattern_history.csv",
    "buy_elite_learning_history.csv",
    "modules/edge_research/",
]
FORBIDDEN_WRITE_PREFIXES = (
    "data/",
    "modules/",
    "tests/",
    "docs/",
    "scripts/",
    "deploy/",
    "app.py",
    "app_v20_clean.py",
)

FEATURE_COLS = [
    "symbol",
    "trade_date",
    "price",
    "health_group",
    "health_score",
    "health_rank",
    "rsi14",
    "rsi_slope",
    "rs5",
    "rs10",
    "rs_spread",
    "ema9",
    "ma20",
    "ema9_ma20_slope",
    "ema9_ma20_slope_change",
    "price_vs_ema9_pct",
    "price_vs_ma20_pct",
    "obv_status",
    "volume",
    "vol_ma20",
    "volume_ratio20",
    "dist_from_ema9_pct",
    "near_bottom_20_pct",
    "near_bottom_60_pct",
    "dist_high20",
    "green2",
    "early",
    "pull",
    "group",
    "sector",
    "market_score",
    "market_regime",
    "dryup",
    "obv",
    "volume_ratio",
    "t3_return_pct",
    "t5_return_pct",
    "t10_return_pct",
    "t3_max_gain_pct",
    "t5_max_gain_pct",
    "t10_max_gain_pct",
    "t3_max_drawdown_pct",
    "t5_max_drawdown_pct",
    "t10_max_drawdown_pct",
]

HORIZONS = (3, 5, 10, 15, 20)
SRC_FILES = [
    REPO / "data/earning_learning/pattern_lifecycle.csv",
    REPO / "data/earning_learning/pattern_history.csv",
    REPO / "data/earning_learning/outcomes.csv",
    REPO / "data/earning_learning/market_daily_t0.csv",
    REPO / "data/earning_learning/market_t0_snapshot.csv",
    REPO / "data/earning_money_snapshots.csv",
    REPO / "pattern_history.csv",
    REPO / "app.py",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_py(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            return None
        if isinstance(x, np.floating) and (not np.isfinite(x)):
            return None
        return float(x)
    if isinstance(x, (pd.Timestamp, datetime)):
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    if isinstance(x, np.ndarray):
        return [to_py(v) for v in x.tolist()]
    if isinstance(x, dict):
        return {str(k): to_py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_py(v) for v in x]
    if pd.isna(x):
        return None
    return x


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_py(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def assert_hidden_write(path: Path) -> None:
    resolved = path.resolve()
    hidden = HIDDEN.resolve()
    if not str(resolved).startswith(str(hidden)):
        raise RuntimeError(f"Refusing write outside hidden sandbox: {resolved}")
    rel = str(path)
    for prefix in FORBIDDEN_WRITE_PREFIXES:
        if rel == str(REPO / prefix.rstrip("/")) or str(resolved).startswith(str((REPO / prefix).resolve())):
            if str(hidden).startswith(str((REPO / prefix).resolve())):
                continue
            raise RuntimeError(f"Refusing write under production prefix {prefix}: {resolved}")


def write_df(path: Path, df: pd.DataFrame) -> None:
    assert_hidden_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_universe() -> List[str]:
    source = (REPO / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r"WATCHLIST\s*=\s*sorted\s*\(\s*list\s*\(\s*set\s*\(\s*\[(.*?)\]\s*\)\s*\)\s*\)",
        source,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("WATCHLIST block not found")
    symbols = sorted(set(re.findall(r'"([A-Z0-9]+)"', match.group(1))))
    if len(symbols) != 142:
        raise RuntimeError(f"Expected 142-symbol universe, got {len(symbols)}")
    return symbols


def _coerce_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    mapped = s.map({True: True, False: False, "True": True, "False": False, "true": True, "false": False, 1: True, 0: False, "1": True, "0": False})
    return mapped.astype("boolean")


def _select_available(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in df.columns]
    return df[keep].copy()


def build_panel(universe: Sequence[str]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    lc = pd.read_csv(REPO / "data/earning_learning/pattern_lifecycle.csv", low_memory=False)
    lc["trade_date"] = pd.to_datetime(lc["trade_date"], errors="coerce")
    lc = lc[lc["symbol"].isin(universe)].copy()
    lc = _select_available(lc, FEATURE_COLS)
    lc["panel_source"] = "pattern_lifecycle"

    eh = pd.read_csv(REPO / "data/earning_learning/pattern_history.csv", low_memory=False)
    eh["trade_date"] = pd.to_datetime(eh["trade_date"], errors="coerce")
    eh = eh[eh["symbol"].isin(universe)].copy()
    if "recorded_at" in eh.columns:
        eh = eh.sort_values(["symbol", "trade_date", "recorded_at"])
    else:
        eh = eh.sort_values(["symbol", "trade_date"])
    eh_last = eh.groupby(["symbol", "trade_date"], as_index=False).tail(1)
    eh_last = _select_available(eh_last, FEATURE_COLS)
    eh_last["panel_source"] = "pattern_history_last"

    # Prefer lifecycle on overlapping dates; extend with later history dates.
    lc_keys = set(zip(lc["symbol"].astype(str), lc["trade_date"]))
    extra = eh_last[~eh_last.apply(lambda r: (str(r["symbol"]), r["trade_date"]) in lc_keys, axis=1)].copy()
    panel = pd.concat([lc, extra], ignore_index=True, sort=False)

    for c in ["green2", "early", "pull", "dryup"]:
        if c in panel.columns:
            panel[c] = _coerce_bool(panel[c])

    for c in [
        "price",
        "health_score",
        "health_rank",
        "rsi14",
        "rsi_slope",
        "rs5",
        "rs10",
        "rs_spread",
        "ema9",
        "ma20",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "price_vs_ema9_pct",
        "price_vs_ma20_pct",
        "volume",
        "vol_ma20",
        "volume_ratio20",
        "dist_from_ema9_pct",
        "near_bottom_20_pct",
        "near_bottom_60_pct",
        "dist_high20",
        "market_score",
        "obv",
        "volume_ratio",
        "t3_return_pct",
        "t5_return_pct",
        "t10_return_pct",
        "t3_max_gain_pct",
        "t5_max_gain_pct",
        "t10_max_gain_pct",
        "t3_max_drawdown_pct",
        "t5_max_drawdown_pct",
        "t10_max_drawdown_pct",
    ]:
        if c in panel.columns:
            panel[c] = pd.to_numeric(panel[c], errors="coerce")

    panel["obv_green"] = panel["obv_status"].astype(str).str.contains("🟢", na=False)
    panel["weekday"] = panel["trade_date"].dt.day_name()
    panel["is_weekend"] = panel["trade_date"].dt.weekday >= 5
    panel["indicators_ok"] = panel["ema9"].notna() & panel["dist_high20"].notna() & panel["price"].notna()

    # Canonical trading sessions: weekday + complete indicators.
    signal_ok = (~panel["is_weekend"]) & panel["indicators_ok"]
    trading_dates = sorted(panel.loc[signal_ok, "trade_date"].dropna().unique())
    panel["is_trading_session"] = panel["trade_date"].isin(trading_dates)

    # Market series from root pattern_history (available through the July crash).
    ph = pd.read_csv(REPO / "pattern_history.csv", usecols=["date", "market_real", "market_forecast"], low_memory=False)
    ph["date"] = pd.to_datetime(ph["date"], errors="coerce")
    mkt = (
        ph.dropna(subset=["date"])
        .groupby("date", as_index=False)
        .agg(market_real_hist=("market_real", "median"), market_forecast_hist=("market_forecast", "median"))
    )
    panel = panel.merge(mkt, left_on="trade_date", right_on="date", how="left")
    panel = panel.drop(columns=["date"], errors="ignore")

    meta = {
        "lifecycle_rows": int(len(lc)),
        "history_extra_rows": int(len(extra)),
        "panel_rows": int(len(panel)),
        "symbols": int(panel["symbol"].nunique()),
        "raw_dates": sorted(panel["trade_date"].dropna().dt.strftime("%Y-%m-%d").unique()),
        "trading_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in trading_dates],
        "n_trading_dates": len(trading_dates),
        "min_date": pd.Timestamp(panel["trade_date"].min()).strftime("%Y-%m-%d"),
        "max_date": pd.Timestamp(panel["trade_date"].max()).strftime("%Y-%m-%d"),
        "cutoff": pd.Timestamp(panel["trade_date"].max()).strftime("%Y-%m-%d"),
    }
    return panel, meta, trading_dates


def add_cross_section(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    g = df.groupby("trade_date", dropna=False)
    df["xs_median_ret_proxy"] = g["rs5"].transform("median")
    df["xs_median_rs10"] = g["rs10"].transform("median")
    df["xs_median_rsi"] = g["rsi14"].transform("median")
    df["xs_median_dd20"] = g["dist_high20"].transform("median")
    df["xs_pct_nb20_le2"] = g["near_bottom_20_pct"].transform(lambda s: float((s <= 2).mean()) if s.notna().any() else np.nan)
    df["xs_pct_slope_pos"] = g["ema9_ma20_slope"].transform(lambda s: float((s > 0).mean()) if s.notna().any() else np.nan)
    df["xs_pct_rsi_gt50"] = g["rsi14"].transform(lambda s: float((s > 50).mean()) if s.notna().any() else np.nan)
    df["xs_pct_obv_green"] = g["obv_green"].transform("mean")
    df["xs_median_price"] = g["price"].transform("median")
    # Synchronization with a market-wide low: high share of names sitting on 20d lows.
    df["sync_bottom"] = df["xs_pct_nb20_le2"] >= 0.35
    df["sync_rebound"] = (df["xs_pct_slope_pos"] >= 0.45) & (df["xs_pct_nb20_le2"] < 0.20)
    return df


def add_lags_and_transitions(panel: pd.DataFrame, trading_dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    df = panel[panel["is_trading_session"]].copy()
    df = df.sort_values(["symbol", "trade_date"])
    date_index = {pd.Timestamp(d): i for i, d in enumerate(trading_dates)}
    df["sess_i"] = df["trade_date"].map(lambda d: date_index.get(pd.Timestamp(d), np.nan))

    lag_cols = [
        "price",
        "rsi14",
        "rsi_slope",
        "rs5",
        "rs10",
        "rs_spread",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "price_vs_ema9_pct",
        "price_vs_ma20_pct",
        "volume_ratio20",
        "near_bottom_20_pct",
        "near_bottom_60_pct",
        "dist_high20",
        "health_score",
        "obv_green",
        "xs_pct_nb20_le2",
        "xs_pct_slope_pos",
        "market_real_hist",
    ]
    g = df.groupby("symbol", group_keys=False)
    for col in lag_cols:
        if col not in df.columns:
            continue
        df[f"{col}_lag1"] = g[col].shift(1)
        df[f"{col}_lag2"] = g[col].shift(2)
        df[f"{col}_lag3"] = g[col].shift(3)
        # Consecutive-session check (no skipped trading date).
        prev_i = g["sess_i"].shift(1)
        df[f"{col}_lag1"] = np.where(df["sess_i"] == prev_i + 1, df[f"{col}_lag1"], np.nan)

    df["at_nb20_low"] = df["near_bottom_20_pct"] <= 1.0
    df["at_nb20_low_lag1"] = df["near_bottom_20_pct_lag1"] <= 1.0
    df["at_nb20_low_lag2"] = df["near_bottom_20_pct_lag2"] <= 1.0
    df["at_nb20_low_lag3"] = df["near_bottom_20_pct_lag3"] <= 1.0
    df["was_nb20_low_l3"] = df[["at_nb20_low_lag1", "at_nb20_low_lag2", "at_nb20_low_lag3"]].any(axis=1)
    df["days_since_nb20_low"] = np.where(
        df["at_nb20_low"],
        0,
        np.where(df["at_nb20_low_lag1"], 1, np.where(df["at_nb20_low_lag2"], 2, np.where(df["at_nb20_low_lag3"], 3, np.nan))),
    )
    # Rolling 5-session low using only current and past prices.
    df["rollmin5"] = g["price"].transform(lambda s: s.rolling(5, min_periods=3).min())
    df["at_rollmin5"] = (df["price"] <= df["rollmin5"] * 1.002) & df["rollmin5"].notna()
    df["px_chg1"] = (df["price"] / df["price_lag1"] - 1.0) * 100.0
    df["up1"] = df["px_chg1"] > 0
    df["up1_lag1"] = g["up1"].shift(1)
    df["up1_lag2"] = g["up1"].shift(2)
    df["consec_up2"] = df["up1"] & df["up1_lag1"].fillna(False)
    df["consec_up3"] = df["consec_up2"] & df["up1_lag2"].fillna(False)
    return df


def add_forward_returns(df: pd.DataFrame, trading_dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """Prospective close-to-close returns from the trading-session price path only."""
    out = df.copy()
    prices = out.pivot_table(index="trade_date", columns="symbol", values="price", aggfunc="last")
    prices = prices.reindex(trading_dates)
    n = len(trading_dates)
    date_to_i = {pd.Timestamp(d): i for i, d in enumerate(trading_dates)}

    arr = prices.to_numpy(dtype=float)
    symbols = list(prices.columns)
    idx = np.arange(n)

    computed = {}
    for h in HORIZONS:
        fwd = np.full_like(arr, np.nan, dtype=float)
        if n > h:
            fwd[: n - h, :] = arr[h:, :] / arr[: n - h, :] - 1.0
        computed[h] = pd.DataFrame(fwd * 100.0, index=prices.index, columns=symbols)

        mfe = np.full_like(arr, np.nan, dtype=float)
        mae = np.full_like(arr, np.nan, dtype=float)
        for i in range(n - 1):
            j = min(n, i + h + 1)
            window = arr[i + 1 : j, :]
            if window.size == 0:
                continue
            with np.errstate(invalid="ignore", divide="ignore"):
                rel = window / arr[i : i + 1, :] - 1.0
                mfe[i, :] = np.nanmax(rel, axis=0) * 100.0
                mae[i, :] = np.nanmin(rel, axis=0) * 100.0
        computed[f"mfe{h}"] = pd.DataFrame(mfe, index=prices.index, columns=symbols)
        computed[f"mae{h}"] = pd.DataFrame(mae, index=prices.index, columns=symbols)

    def melt(frame: pd.DataFrame, name: str) -> pd.DataFrame:
        m = frame.stack(future_stack=True).rename(name).reset_index()
        m.columns = ["trade_date", "symbol", name]
        return m

    merged = out
    for h in HORIZONS:
        merged = merged.merge(melt(computed[h], f"ret_t{h}"), on=["trade_date", "symbol"], how="left")
        merged = merged.merge(melt(computed[f"mfe{h}"], f"mfe_t{h}"), on=["trade_date", "symbol"], how="left")
        merged = merged.merge(melt(computed[f"mae{h}"], f"mae_t{h}"), on=["trade_date", "symbol"], how="left")

    # Same-date cross-sectional excess (Baseline B residual).
    for h in (3, 5, 10):
        merged[f"xs_median_ret_t{h}"] = merged.groupby("trade_date")[f"ret_t{h}"].transform("median")
        merged[f"exret_t{h}"] = merged[f"ret_t{h}"] - merged[f"xs_median_ret_t{h}"]

    # Episode labels (calendar clusters, not optimized).
    def episode(ts: pd.Timestamp) -> str:
        d = pd.Timestamp(ts)
        if d <= pd.Timestamp("2026-07-31"):
            return "E1_JUL_BOTTOM_BOUNCE"
        if d <= pd.Timestamp("2026-08-07"):
            return "E2_EARLY_AUG_CONTINUATION"
        if d <= pd.Timestamp("2026-08-14"):
            return "E3_MID_AUG"
        return "E4_LATE_AUG"

    merged["episode"] = merged["trade_date"].map(episode)
    merged["in_july_cluster"] = merged["trade_date"].between("2026-07-27", "2026-07-31")
    # Discovery / holdout split frozen before looking at incremental results:
    # first 11 trading dates vs remainder. Not tuned.
    split_i = 11
    split_date = pd.Timestamp(trading_dates[split_i]) if len(trading_dates) > split_i else pd.Timestamp(trading_dates[-1])
    merged["split"] = np.where(merged["sess_i"] < split_i, "DISCOVERY", "HOLDOUT")
    merged.attrs["split_date"] = pd.Timestamp(trading_dates[split_i - 1]).strftime("%Y-%m-%d")
    merged.attrs["holdout_start"] = pd.Timestamp(split_date).strftime("%Y-%m-%d")
    return merged


def nan_stats(s: pd.Series) -> Dict[str, Any]:
    x = pd.to_numeric(s, errors="coerce").dropna()
    n = int(len(x))
    if n == 0:
        return {"n": 0, "winrate": None, "mean": None, "median": None, "p10": None, "p25": None, "p75": None, "p90": None, "frac_lt_m3": None, "mean_neg": None}
    return {
        "n": n,
        "winrate": float((x > 0).mean()),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "p10": float(x.quantile(0.10)),
        "p25": float(x.quantile(0.25)),
        "p75": float(x.quantile(0.75)),
        "p90": float(x.quantile(0.90)),
        "frac_lt_m3": float((x < -3).mean()),
        "mean_neg": float(x[x < 0].mean()) if (x < 0).any() else None,
    }


def profile(df: pd.DataFrame, mask: pd.Series, label: str) -> Dict[str, Any]:
    sub = df.loc[mask].copy()
    n = int(len(sub))
    out: Dict[str, Any] = {
        "label": label,
        "n": n,
        "n_stocks": int(sub["symbol"].nunique()) if n else 0,
        "n_dates": int(sub["trade_date"].nunique()) if n else 0,
        "dates": sorted(sub["trade_date"].dt.strftime("%Y-%m-%d").unique()) if n else [],
        "episodes": sorted(sub["episode"].unique()) if n else [],
        "n_episodes": int(sub["episode"].nunique()) if n else 0,
        "july_cluster_share": float(sub["in_july_cluster"].mean()) if n else None,
        "horizons": {},
        "excess": {},
        "mfe_mae": {},
        "date_clustered": {},
        "episode_breakdown": {},
        "split_breakdown": {},
    }
    if n == 0:
        return out
    for h in HORIZONS:
        col = f"ret_t{h}"
        out["horizons"][f"t{h}"] = nan_stats(sub[col])
        if f"mfe_t{h}" in sub.columns:
            out["mfe_mae"][f"t{h}"] = {
                "mfe": nan_stats(sub[f"mfe_t{h}"]),
                "mae": nan_stats(sub[f"mae_t{h}"]),
            }
    for h in (3, 5, 10):
        out["excess"][f"t{h}"] = nan_stats(sub[f"exret_t{h}"])

    for h in (3, 5, 10):
        gm = sub.groupby("trade_date")[f"ret_t{h}"].median()
        out["date_clustered"][f"t{h}"] = {
            "n_dates_with_obs": int(gm.dropna().shape[0]),
            "median_of_date_medians": float(gm.median()) if gm.notna().any() else None,
            "mean_of_date_medians": float(gm.mean()) if gm.notna().any() else None,
            "share_dates_positive": float((gm > 0).mean()) if gm.notna().any() else None,
        }
    for ep, g in sub.groupby("episode"):
        out["episode_breakdown"][str(ep)] = {
            "n": int(len(g)),
            "n_stocks": int(g["symbol"].nunique()),
            "n_dates": int(g["trade_date"].nunique()),
            "t5": nan_stats(g["ret_t5"]),
            "t10": nan_stats(g["ret_t10"]),
            "ex_t5": nan_stats(g["exret_t5"]),
        }
    for sp, g in sub.groupby("split"):
        out["split_breakdown"][str(sp)] = {
            "n": int(len(g)),
            "t5": nan_stats(g["ret_t5"]),
            "t10": nan_stats(g["ret_t10"]),
            "ex_t5": nan_stats(g["exret_t5"]),
        }
    return out


def incremental(cand: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    inc: Dict[str, Any] = {}
    for h in ("t3", "t5", "t10", "t15", "t20"):
        c = (cand.get("horizons") or {}).get(h) or {}
        b = (base.get("horizons") or {}).get(h) or {}
        if c.get("median") is None or b.get("median") is None:
            inc[h] = None
            continue
        inc[h] = {
            "delta_median": c["median"] - b["median"],
            "delta_mean": (c["mean"] - b["mean"]) if c.get("mean") is not None and b.get("mean") is not None else None,
            "delta_winrate": (c["winrate"] - b["winrate"]) if c.get("winrate") is not None and b.get("winrate") is not None else None,
        }
    c5 = (cand.get("excess") or {}).get("t5") or {}
    b5 = (base.get("excess") or {}).get("t5") or {}
    if c5.get("median") is not None and b5.get("median") is not None:
        inc["ex_t5_delta_median"] = c5["median"] - b5["median"]
    else:
        inc["ex_t5_delta_median"] = None
    return inc


def date_matched_control(df: pd.DataFrame, cand_mask: pd.Series, pool_mask: pd.Series) -> pd.Series:
    """Eligible names on the same dates as candidate signals (Baseline D / date-matched)."""
    dates = set(df.loc[cand_mask, "trade_date"])
    return pool_mask & df["trade_date"].isin(dates)


POPULATIONS: List[Dict[str, Any]] = [
    {"id": "P_dd20_8", "name": "dist_high20 <= -8 (drawdown from 20d high)", "fn": lambda d: d["dist_high20"] <= -8},
    {"id": "P_dd20_12", "name": "dist_high20 <= -12", "fn": lambda d: d["dist_high20"] <= -12},
    {"id": "P_dd20_15", "name": "dist_high20 <= -15", "fn": lambda d: d["dist_high20"] <= -15},
    {"id": "P_nb20_2", "name": "near 20d low (near_bottom_20_pct <= 2)", "fn": lambda d: d["near_bottom_20_pct"] <= 2},
    {"id": "P_nb20_5", "name": "near 20d low (near_bottom_20_pct <= 5)", "fn": lambda d: d["near_bottom_20_pct"] <= 5},
    {"id": "P_nb60_3", "name": "near 60d low (near_bottom_60_pct <= 3)", "fn": lambda d: d["near_bottom_60_pct"] <= 3},
    {"id": "P_rs10_m5", "name": "RS10 <= -5", "fn": lambda d: d["rs10"] <= -5},
    {"id": "P_rs10_m10", "name": "RS10 <= -10", "fn": lambda d: d["rs10"] <= -10},
    {"id": "P_rsi_30", "name": "RSI14 <= 30", "fn": lambda d: d["rsi14"] <= 30},
    {"id": "P_rsi_35", "name": "RSI14 <= 35", "fn": lambda d: d["rsi14"] <= 35},
    {"id": "P_below_ma20_8", "name": "price vs MA20 <= -8%", "fn": lambda d: d["price_vs_ma20_pct"] <= -8},
    {"id": "P_dd20_8_nb20_5", "name": "dd20<=-8 AND nb20<=5", "fn": lambda d: (d["dist_high20"] <= -8) & (d["near_bottom_20_pct"] <= 5)},
    {"id": "P_rsi40_dd20_10", "name": "RSI<=40 AND dd20<=-10", "fn": lambda d: (d["rsi14"] <= 40) & (d["dist_high20"] <= -10)},
]


def transition_specs() -> List[Dict[str, Any]]:
    def t(id_, name, complexity, reason, fn, needs_lag=True, family="transition"):
        return {"id": id_, "name": name, "complexity": complexity, "why_tested": reason, "fn": fn, "needs_lag": needs_lag, "family": family}

    return [
        t("T01", "slope_cross_up", 2, "falling→rising: EMA9-MA20 slope crosses from <0 to >=0",
          lambda d: (d["ema9_ma20_slope_lag1"] < 0) & (d["ema9_ma20_slope"] >= 0)),
        t("T02", "slope_flatten_from_steep_neg", 3, "falling→flattening: slope was < -1.5 and now in [-1.5, 0.5)",
          lambda d: (d["ema9_ma20_slope_lag1"] < -1.5) & (d["ema9_ma20_slope"] >= -1.5) & (d["ema9_ma20_slope"] < 0.5)),
        t("T03", "slope_accel_from_neg", 2, "negative slope accelerating upward (slope_change>0.4 while lag slope<0)",
          lambda d: (d["ema9_ma20_slope_lag1"] < 0) & (d["ema9_ma20_slope_change"] > 0.4)),
        t("T04", "rsi_rising_from_oversold", 2, "RSI<=40 and RSI > RSI_lag1",
          lambda d: (d["rsi14"] <= 40) & (d["rsi14"] > d["rsi14_lag1"] + 0.5)),
        t("T05", "rsi_slope_pos_oversold", 2, "RSI<=40 and rsi_slope>0",
          lambda d: (d["rsi14"] <= 40) & (d["rsi_slope"] > 0), needs_lag=False),
        t("T06", "rsi_cross_40_up", 2, "RSI crosses above 40",
          lambda d: (d["rsi14_lag1"] < 40) & (d["rsi14"] >= 40)),
        t("T07", "rs5_turn_up_from_neg", 2, "RS5 was negative and improved by >1pt",
          lambda d: (d["rs5_lag1"] < 0) & (d["rs5"] > d["rs5_lag1"] + 1.0)),
        t("T08", "rs_spread_pos", 1, "RS5 > RS10 (short-term RS leading 10d)",
          lambda d: d["rs_spread"] > 0, needs_lag=False),
        t("T09", "rs_spread_flip_pos", 2, "rs_spread crosses from <=0 to >0",
          lambda d: (d["rs_spread_lag1"] <= 0) & (d["rs_spread"] > 0)),
        t("T10", "rs10_weak_rs5_improving", 3, "RS10 still <=-3 but RS5 turning up",
          lambda d: (d["rs10"] <= -3) & (d["rs5"] > d["rs5_lag1"] + 1.0)),
        t("T11", "reclaim_ema9", 2, "price crosses from <=EMA9 to >EMA9",
          lambda d: (d["price_vs_ema9_pct_lag1"] <= 0) & (d["price_vs_ema9_pct"] > 0)),
        t("T12", "reclaim_ma20", 2, "price crosses from <=MA20 to >MA20",
          lambda d: (d["price_vs_ma20_pct_lag1"] <= 0) & (d["price_vs_ma20_pct"] > 0)),
        t("T13", "approaching_ema9", 2, "still below EMA9 but gap shrinking",
          lambda d: (d["price_vs_ema9_pct"] < 0) & (d["price_vs_ema9_pct"] > d["price_vs_ema9_pct_lag1"] + 0.3)),
        t("T14", "obv_flip_green", 2, "OBV status red→green",
          lambda d: (~d["obv_green_lag1"].astype(bool)) & (d["obv_green"])),
        t("T15", "vol_dryup", 1, "volume_ratio20 < 0.7 (supply contraction)",
          lambda d: d["volume_ratio20"] < 0.7, needs_lag=False),
        t("T16", "vol_expansion", 1, "volume_ratio20 > 1.3",
          lambda d: d["volume_ratio20"] > 1.3, needs_lag=False),
        t("T17", "vol_expand_after_dryup", 3, "prior vol_ratio<0.8 then vol_ratio>1.2",
          lambda d: (d["volume_ratio20_lag1"] < 0.8) & (d["volume_ratio20"] > 1.2)),
        t("T18", "at_20d_low", 1, "sitting on 20d low (nb20<=1) — level, not transition",
          lambda d: d["near_bottom_20_pct"] <= 1.0, needs_lag=False, family="level"),
        t("T19", "leaving_20d_low", 2, "was at 20d low last session, now 2-6% off low",
          lambda d: (d["near_bottom_20_pct_lag1"] <= 1.5) & (d["near_bottom_20_pct"] > 2) & (d["near_bottom_20_pct"] <= 6)),
        t("T20", "health_improve", 2, "health_score rose by >8 vs lag1",
          lambda d: d["health_score"] > d["health_score_lag1"] + 8),
        t("T21", "sync_bottom_day", 1, "market-wide: >=35% of universe at 20d-low",
          lambda d: d["sync_bottom"], needs_lag=False, family="market"),
        t("T22", "sync_bottom_and_rsi_rising", 3, "sync bottom day AND RSI rising",
          lambda d: d["sync_bottom"] & (d["rsi14"] > d["rsi14_lag1"] + 0.5)),
        t("T23", "market_real_turn_up", 2, "market_real_hist rose by >0.8 after being <=2",
          lambda d: (d["market_real_hist_lag1"] <= 2.0) & (d["market_real_hist"] >= d["market_real_hist_lag1"] + 0.8)),
        t("T24", "consec_up2", 1, "two consecutive up closes",
          lambda d: d["consec_up2"].fillna(False), needs_lag=False),
        t("T25", "consec_up3", 1, "three consecutive up closes",
          lambda d: d["consec_up3"].fillna(False), needs_lag=False),
        t("T26", "dd20_healing", 2, "still in drawdown (dd20<-8) but dist_high20 improving",
          lambda d: (d["dist_high20"] <= -8) & (d["dist_high20"] > d["dist_high20_lag1"] + 0.8)),
        t("T27", "green2_flag", 1, "Mr.BOT green2 flag (control: existing labeled pattern)",
          lambda d: d["green2"].fillna(False).astype(bool), needs_lag=False, family="labeled"),
        t("T28", "early_flag", 1, "Mr.BOT early flag (control)",
          lambda d: d["early"].fillna(False).astype(bool), needs_lag=False, family="labeled"),
        t("T29", "pull_flag", 1, "Mr.BOT pull flag (control)",
          lambda d: d["pull"].fillna(False).astype(bool), needs_lag=False, family="labeled"),
        t("T30", "below_ema9_slope_still_steep_neg", 2, "ANTI: still below EMA9 with slope < -2",
          lambda d: (d["price_vs_ema9_pct"] < 0) & (d["ema9_ma20_slope"] < -2), needs_lag=False, family="anti"),
        t("T31", "new_low_rsi_falling", 2, "ANTI: at 20d low and RSI declining",
          lambda d: (d["near_bottom_20_pct"] <= 1.0) & (d["rsi14"] < d["rsi14_lag1"]), family="anti"),
        t("T32", "vol_expand_on_new_low", 2, "ANTI: volume expansion while still on 20d low",
          lambda d: (d["near_bottom_20_pct"] <= 1.0) & (d["volume_ratio20"] > 1.3), needs_lag=False, family="anti"),
        t("T33", "rs10_still_deteriorating", 2, "ANTI: RS10 more negative than lag1 by >1",
          lambda d: d["rs10"] < d["rs10_lag1"] - 1.0, family="anti"),
        t("T34", "reclaim_ema9_after_nb20_low", 3, "sequence: 20d-low in last 3 sessions then reclaim EMA9",
          lambda d: d["was_nb20_low_l3"] & (d["price_vs_ema9_pct_lag1"] <= 0) & (d["price_vs_ema9_pct"] > 0), family="sequence"),
        t("T35", "rsi_rising_after_nb20_low", 3, "sequence: 20d-low in last 3 sessions then RSI rising from <=40",
          lambda d: d["was_nb20_low_l3"] & (d["rsi14"] <= 45) & (d["rsi14"] > d["rsi14_lag1"] + 0.5), family="sequence"),
        t("T36", "slope_cross_after_nb20_low", 3, "sequence: 20d-low in last 3 sessions then slope cross up",
          lambda d: d["was_nb20_low_l3"] & (d["ema9_ma20_slope_lag1"] < 0) & (d["ema9_ma20_slope"] >= 0), family="sequence"),
        t("T37", "dryup_then_expand_after_low", 4, "sequence: was at 20d low, prior dryup, now expansion",
          lambda d: d["was_nb20_low_l3"] & (d["volume_ratio20_lag1"] < 0.8) & (d["volume_ratio20"] > 1.2), family="sequence"),
        t("T38", "obv_green_and_reclaim_ema9", 3, "joint: OBV green AND reclaim EMA9",
          lambda d: d["obv_green"] & (d["price_vs_ema9_pct_lag1"] <= 0) & (d["price_vs_ema9_pct"] > 0), family="sequence"),
        t("T39", "early_confirm_at_low", 2, "EARLY confirmation: at 20d low today (day-0)",
          lambda d: d["at_nb20_low"], needs_lag=False, family="timing"),
        t("T40", "late_confirm_d1_3_reclaim_ema9", 3, "LATER confirmation: 1-3d after 20d low AND reclaim EMA9",
          lambda d: d["was_nb20_low_l3"] & (~d["at_nb20_low"]) & (d["price_vs_ema9_pct"] > 0), family="timing"),
        t("T41", "late_confirm_d1_3_slope_pos", 3, "LATER confirmation: 1-3d after 20d low AND slope>=0",
          lambda d: d["was_nb20_low_l3"] & (~d["at_nb20_low"]) & (d["ema9_ma20_slope"] >= 0), family="timing"),
        t("T42", "too_extended_after_low", 2, "ANTI: 1-3d after low but already >8% off 20d low",
          lambda d: d["was_nb20_low_l3"] & (d["near_bottom_20_pct"] > 8), family="anti"),
        t("T43", "market_sync_plus_reclaim_ema9", 3, "sync-bottom day (or lag1) and reclaim EMA9",
          lambda d: (d["sync_bottom"] | (d["xs_pct_nb20_le2_lag1"] >= 0.35)) & (d["price_vs_ema9_pct_lag1"] <= 0) & (d["price_vs_ema9_pct"] > 0), family="sequence"),
        t("T44", "breadth_turn_slope", 2, "xs_pct_slope_pos crosses above 0.35 from below 0.25",
          lambda d: (d["xs_pct_slope_pos_lag1"] < 0.25) & (d["xs_pct_slope_pos"] >= 0.35), family="market"),
        t("T45", "price_above_ema9_first_time_in_drawdown", 2, "currently >EMA9 while still dd20<=-8 (reclaim while not recovered)",
          lambda d: (d["dist_high20"] <= -8) & (d["price_vs_ema9_pct"] > 0) & (d["price_vs_ema9_pct_lag1"] <= 0)),
    ]


TERTILE_FEATURES = [
    "rsi14",
    "rsi_slope",
    "rs5",
    "rs10",
    "rs_spread",
    "ema9_ma20_slope",
    "ema9_ma20_slope_change",
    "price_vs_ema9_pct",
    "volume_ratio20",
    "near_bottom_20_pct",
    "dist_high20",
    "health_score",
    "xs_pct_nb20_le2",
]


def tertile_screen(df: pd.DataFrame, pop_mask: pd.Series) -> List[Dict[str, Any]]:
    rows = []
    base = df.loc[pop_mask]
    if len(base) < 30:
        return rows
    for feat in TERTILE_FEATURES:
        if feat not in base.columns:
            continue
        x = pd.to_numeric(base[feat], errors="coerce")
        valid = x.notna()
        if int(valid.sum()) < 30:
            continue
        try:
            buckets = pd.qcut(x[valid], 3, labels=["T1_low", "T2_mid", "T3_high"], duplicates="drop")
        except ValueError:
            continue
        tmp = base.loc[valid].copy()
        tmp["_b"] = buckets.astype(str)
        rec = {"feature": feat, "buckets": {}}
        meds = []
        for b, g in tmp.groupby("_b"):
            st = nan_stats(g["ret_t5"])
            rec["buckets"][str(b)] = {"n": int(len(g)), "t5": st, "t10": nan_stats(g["ret_t10"]), "ex_t5": nan_stats(g["exret_t5"])}
            if st.get("median") is not None:
                meds.append((str(b), st["median"]))
        # Monotonicity across ordered tertiles if all three exist.
        order = ["T1_low", "T2_mid", "T3_high"]
        seq = [rec["buckets"].get(k, {}).get("t5", {}).get("median") for k in order]
        if all(v is not None for v in seq):
            rec["monotonic_up"] = seq[0] < seq[1] < seq[2]
            rec["monotonic_down"] = seq[0] > seq[1] > seq[2]
            rec["t5_spread_t3_minus_t1"] = seq[2] - seq[0]
        else:
            rec["monotonic_up"] = False
            rec["monotonic_down"] = False
            rec["t5_spread_t3_minus_t1"] = None
        rows.append(rec)
    return rows


def classify_verdict(row: Dict[str, Any]) -> str:
    """Conservative classification. One-month history cannot support ROBUST EDGE."""
    inc = row.get("incremental_vs_C") or {}
    d5 = (inc.get("t5") or {}).get("delta_median")
    d10 = (inc.get("t10") or {}).get("delta_median")
    n = row.get("candidate", {}).get("n") or 0
    n_ep = row.get("candidate", {}).get("n_episodes") or 0
    july = row.get("candidate", {}).get("july_cluster_share")
    hold = ((row.get("candidate") or {}).get("split_breakdown") or {}).get("HOLDOUT") or {}
    hold_n = hold.get("n") or 0
    hold_d5 = None
    if hold.get("t5") and row.get("baseline_C", {}).get("split_breakdown", {}).get("HOLDOUT"):
        hm = hold["t5"].get("median")
        bm = row["baseline_C"]["split_breakdown"]["HOLDOUT"]["t5"].get("median")
        if hm is not None and bm is not None:
            hold_d5 = hm - bm
    if n < 25:
        return "NO EDGE"
    # Require incremental median improvement of at least +1.0pp at T5 or T10 vs same-decline without transition.
    strong = (d5 is not None and d5 >= 1.0) or (d10 is not None and d10 >= 1.5)
    if not strong:
        # Anti-edge: clearly worse
        if (d5 is not None and d5 <= -1.0) or (d10 is not None and d10 <= -1.5):
            return "NO EDGE"
        return "NO EDGE"
    # Market-date residual: if excess T5 median of candidate is ~0, it is mostly beta.
    ex = ((row.get("candidate") or {}).get("excess") or {}).get("t5") or {}
    ex_med = ex.get("median")
    mostly_beta = ex_med is not None and abs(ex_med) < 0.4 and (d5 is not None and d5 < 2.0)
    if july is not None and july >= 0.55:
        if n_ep <= 2:
            return "REGIME-CONDITIONAL CANDIDATE" if not mostly_beta else "INTERESTING OBSERVATION"
    if hold_n >= 20 and hold_d5 is not None and hold_d5 >= 0.8 and n_ep >= 3 and not mostly_beta:
        return "RESEARCH EDGE"
    if strong and not mostly_beta:
        return "INTERESTING OBSERVATION"
    if mostly_beta:
        return "INTERESTING OBSERVATION"
    return "NO EDGE"


def failure_analysis(df: pd.DataFrame, mask: pd.Series, name: str) -> Dict[str, Any]:
    sub = df.loc[mask].copy()
    if sub.empty:
        return {"name": name, "n": 0}
    fail = sub[sub["ret_t5"] <= 0]
    win = sub[sub["ret_t5"] > 0]
    def cmp(col):
        return {
            "fail_median": to_py(fail[col].median()) if col in fail and len(fail) else None,
            "win_median": to_py(win[col].median()) if col in win and len(win) else None,
        }
    return {
        "name": name,
        "n": int(len(sub)),
        "n_fail_t5": int(len(fail)),
        "fail_rate_t5": float((sub["ret_t5"] <= 0).mean()) if sub["ret_t5"].notna().any() else None,
        "fail_rate_t10": float((sub["ret_t10"] <= 0).mean()) if sub["ret_t10"].notna().any() else None,
        "fail_episode_counts": fail["episode"].value_counts().to_dict() if len(fail) else {},
        "win_episode_counts": win["episode"].value_counts().to_dict() if len(win) else {},
        "july_share_fail": float(fail["in_july_cluster"].mean()) if len(fail) else None,
        "july_share_win": float(win["in_july_cluster"].mean()) if len(win) else None,
        "rsi14": cmp("rsi14"),
        "rsi_slope": cmp("rsi_slope"),
        "rs10": cmp("rs10"),
        "volume_ratio20": cmp("volume_ratio20"),
        "ema9_ma20_slope": cmp("ema9_ma20_slope"),
        "near_bottom_20_pct": cmp("near_bottom_20_pct"),
        "dist_high20": cmp("dist_high20"),
        "xs_pct_nb20_le2": cmp("xs_pct_nb20_le2"),
        "market_real_hist": cmp("market_real_hist"),
        "fail_symbols_sample": sorted(fail.sort_values("ret_t5")["symbol"].unique())[:25] if len(fail) else [],
        "worst_t5": (
            fail.nsmallest(8, "ret_t5")[["symbol", "trade_date", "ret_t5", "ret_t10", "rsi14", "rs10", "ema9_ma20_slope", "volume_ratio20", "episode"]]
            .assign(trade_date=lambda x: x["trade_date"].dt.strftime("%Y-%m-%d"))
            .to_dict(orient="records")
            if len(fail)
            else []
        ),
    }


def isolation_audit(universe: Sequence[str]) -> Dict[str, Any]:
    hashes = {}
    for p in SRC_FILES:
        if p.exists():
            hashes[str(p.relative_to(REPO))] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    # Brain path existence
    brain_paths = {
        "data/earning_learning": (REPO / "data/earning_learning").is_dir(),
        "data/edge_research": (REPO / "data/edge_research").exists(),
        "research_exports": (REPO / "research_exports").exists(),
        "modules/edge_research": (REPO / "modules/edge_research").is_dir(),
    }
    # Confirm hidden path is not a known Brain input
    hidden_rel = str(HIDDEN.relative_to(REPO))
    collision = any(hidden_rel.startswith(p.rstrip("/")) or p.startswith(hidden_rel) for p in BRAIN_INPUT_PATHS)
    return {
        "timestamp_utc": TIMESTAMP,
        "run_id": RUN_ID,
        "hidden_root": hidden_rel,
        "brain_input_paths": BRAIN_INPUT_PATHS,
        "brain_path_exists": brain_paths,
        "hidden_collides_with_brain_paths": collision,
        "universe_n": len(universe),
        "universe": list(universe),
        "source_hashes": hashes,
        "imports_edge_research": False,
        "writes_only_under_hidden": True,
        "note": "storage.py ensure_storage was never called; data/edge_research/ must remain untouched.",
    }


def fmt_pct(x: Optional[float], digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.{digits}f}%"


def fmt_num(x: Optional[float], digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FROZEN.mkdir(parents=True, exist_ok=True)
    (OUT / "failures").mkdir(parents=True, exist_ok=True)

    universe = load_universe()
    audit = isolation_audit(universe)
    dump_json(OUT / "isolation_verification.json", audit)
    if audit["hidden_collides_with_brain_paths"]:
        raise RuntimeError("Hidden path collides with Brain inputs — aborting")

    panel_raw, panel_meta, trading_dates = build_panel(universe)
    panel_raw = add_cross_section(panel_raw)
    df = add_lags_and_transitions(panel_raw, trading_dates)
    df = add_forward_returns(df, trading_dates)
    df = df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    write_df(OUT / "canonical_panel.csv", df)
    dump_json(OUT / "panel_meta.json", {**panel_meta, "split_date": df.attrs.get("split_date"), "holdout_start": df.attrs.get("holdout_start")})

    # Local-min diagnostic (panel-min is NOT a signal; look-ahead if used as such).
    piv = df.pivot_table(index="symbol", columns="trade_date", values="price", aggfunc="last")
    min_dates = piv.idxmin(axis=1)
    min_counts = min_dates.value_counts().sort_index()
    dump_json(
        OUT / "local_min_diagnostic.json",
        {
            "warning": "Panel-wide local min uses the full sample including future prices. Descriptive only — not a signal.",
            "counts": {pd.Timestamp(k).strftime("%Y-%m-%d"): int(v) for k, v in min_counts.items()},
            "n_on_2026-07-27": int((min_dates == pd.Timestamp("2026-07-27")).sum()),
        },
    )

    ledger: List[Dict[str, Any]] = []
    pop_profiles: Dict[str, Any] = {}
    pop_masks: Dict[str, pd.Series] = {}

    # Primary population used for transition search (documented, not cherry-picked after outcomes).
    PRIMARY_POP = "P_dd20_8_nb20_5"

    for pop in POPULATIONS:
        mask = pop["fn"](df) & df["price"].notna()
        pop_masks[pop["id"]] = mask
        prof = profile(df, mask, pop["id"])
        pop_profiles[pop["id"]] = {"definition": pop["name"], **prof}
        ledger.append({
            "id": pop["id"],
            "kind": "population_definition",
            "status": "documented",
            "definition": pop["name"],
            "n": prof["n"],
            "n_stocks": prof["n_stocks"],
            "n_dates": prof["n_dates"],
            "t5_median": (prof["horizons"].get("t5") or {}).get("median"),
            "t10_median": (prof["horizons"].get("t10") or {}).get("median"),
        })

    dump_json(OUT / "population_profiles.json", pop_profiles)

    # Universe-wide baseline (all trading-session rows).
    all_mask = pd.Series(True, index=df.index)
    baseline_all = profile(df, all_mask, "ALL_TRADING_SESSION_ROWS")
    dump_json(OUT / "baseline_all_rows.json", baseline_all)

    tertiles = tertile_screen(df, pop_masks[PRIMARY_POP])
    dump_json(OUT / "tertile_screen_primary_pop.json", tertiles)
    for rec in tertiles:
        ledger.append({
            "id": f"Q_{rec['feature']}",
            "kind": "tertile_monotonicity",
            "feature": rec["feature"],
            "monotonic_up": rec.get("monotonic_up"),
            "monotonic_down": rec.get("monotonic_down"),
            "t5_spread_t3_minus_t1": rec.get("t5_spread_t3_minus_t1"),
            "status": (
                "promising_monotonic"
                if rec.get("monotonic_up") or rec.get("monotonic_down")
                else "no_monotonicity"
            ),
        })

    specs = transition_specs()
    candidate_rows: List[Dict[str, Any]] = []
    primary = pop_masks[PRIMARY_POP]
    alt_pops_for_screen = ["P_dd20_8", "P_nb20_2", "P_rsi_35", "P_dd20_12"]

    for spec in specs:
        try:
            raw = spec["fn"](df)
            if isinstance(raw, pd.Series):
                tmask = raw.fillna(False).astype(bool)
            else:
                tmask = pd.Series(bool(raw), index=df.index)
        except Exception as exc:
            ledger.append({"id": spec["id"], "kind": "transition", "status": "error", "error": str(exc)})
            continue

        # Candidate = primary decline population AND transition, T0-safe by construction.
        cand_mask = primary & tmask
        # Require lag availability for lag-based rules: drop rows where needed lag is NaN.
        if spec.get("needs_lag"):
            cand_mask = cand_mask & df["price_lag1"].notna()

        base_A = profile(df, primary, "A_primary_decline")
        base_C_mask = primary & (~tmask)
        if spec.get("needs_lag"):
            base_C_mask = base_C_mask & df["price_lag1"].notna()
        base_C = profile(df, base_C_mask, "C_decline_without_transition")
        cand = profile(df, cand_mask, spec["id"])
        b_mask = date_matched_control(df, cand_mask, all_mask)
        base_B = profile(df, b_mask, "B_all_stocks_on_signal_dates")
        d_mask = date_matched_control(df, cand_mask, primary)
        base_D = profile(df, d_mask, "D_eligible_on_signal_dates")

        row = {
            "id": spec["id"],
            "name": spec["name"],
            "family": spec["family"],
            "complexity": spec["complexity"],
            "why_tested": spec["why_tested"],
            "primary_population": PRIMARY_POP,
            "candidate": cand,
            "baseline_A": {k: base_A[k] for k in ("n", "n_stocks", "n_dates", "horizons", "excess", "july_cluster_share", "split_breakdown", "episode_breakdown") if k in base_A},
            "baseline_B": {k: base_B[k] for k in ("n", "n_stocks", "n_dates", "horizons", "excess") if k in base_B},
            "baseline_C": {k: base_C[k] for k in ("n", "n_stocks", "n_dates", "horizons", "excess", "split_breakdown", "episode_breakdown") if k in base_C},
            "baseline_D": {k: base_D[k] for k in ("n", "n_stocks", "n_dates", "horizons", "excess") if k in base_D},
            "incremental_vs_A": incremental(cand, base_A),
            "incremental_vs_C": incremental(cand, base_C),
            "incremental_vs_D": incremental(cand, base_D),
            "incremental_vs_B": incremental(cand, base_B),
        }
        row["verdict"] = classify_verdict(row)
        # Keep compact numeric summary for screening table.
        c5 = (cand.get("horizons") or {}).get("t5") or {}
        c10 = (cand.get("horizons") or {}).get("t10") or {}
        incC = row["incremental_vs_C"] or {}
        row["screen"] = {
            "n": cand["n"],
            "n_stocks": cand["n_stocks"],
            "n_dates": cand["n_dates"],
            "n_episodes": cand["n_episodes"],
            "july_share": cand["july_cluster_share"],
            "t3_median": (cand.get("horizons") or {}).get("t3", {}).get("median"),
            "t5_median": c5.get("median"),
            "t5_mean": c5.get("mean"),
            "t5_winrate": c5.get("winrate"),
            "t10_median": c10.get("median"),
            "t10_mean": c10.get("mean"),
            "t10_winrate": c10.get("winrate"),
            "ex_t5_median": (cand.get("excess") or {}).get("t5", {}).get("median"),
            "incC_t5_median": (incC.get("t5") or {}).get("delta_median"),
            "incC_t10_median": (incC.get("t10") or {}).get("delta_median"),
            "incC_t5_winrate": (incC.get("t5") or {}).get("delta_winrate"),
            "complexity": spec["complexity"],
            "verdict": row["verdict"],
        }
        candidate_rows.append(row)
        ledger.append({
            "id": spec["id"],
            "kind": "transition",
            "name": spec["name"],
            "family": spec["family"],
            "status": "tested",
            "verdict": row["verdict"],
            **row["screen"],
            "why_tested": spec["why_tested"],
        })

        # Sensitivity on alternate populations (screen only, no extra fitting).
        alt = {}
        for pid in alt_pops_for_screen:
            am = pop_masks[pid] & tmask
            if spec.get("needs_lag"):
                am = am & df["price_lag1"].notna()
            cm = pop_masks[pid] & (~tmask)
            if spec.get("needs_lag"):
                cm = cm & df["price_lag1"].notna()
            cp = profile(df, am, f"{spec['id']}|{pid}")
            bp = profile(df, cm, f"C|{pid}")
            alt[pid] = {
                "n": cp["n"],
                "t5_median": (cp["horizons"].get("t5") or {}).get("median"),
                "t10_median": (cp["horizons"].get("t10") or {}).get("median"),
                "incC_t5": ((cp["horizons"].get("t5") or {}).get("median") or np.nan) - ((bp["horizons"].get("t5") or {}).get("median") or np.nan)
                if cp["n"] and bp["n"]
                else None,
            }
        row["alt_population_sensitivity"] = alt

    dump_json(OUT / "transition_full_results.json", candidate_rows)
    screen_df = pd.DataFrame([r["screen"] | {"id": r["id"], "name": r["name"], "family": r["family"]} for r in candidate_rows])
    screen_df = screen_df.sort_values(["incC_t5_median", "n"], ascending=[False, False], na_position="last")
    write_df(OUT / "transition_screen.csv", screen_df)

    # Promising set: conservative pre-declared rule, not max-return fishing.
    promising = []
    rejected = []
    anti = []
    for r in candidate_rows:
        fam = r["family"]
        scr = r["screen"]
        if fam == "anti":
            anti.append(r)
        inc5 = scr.get("incC_t5_median")
        n = scr.get("n") or 0
        if n >= 25 and inc5 is not None and inc5 >= 1.0 and fam != "anti":
            promising.append(r)
        elif fam != "anti":
            rejected.append(r)

    # Failure analyses for promising + a few attractive rejects + timing pair.
    fail_targets = {r["id"]: r for r in promising}
    for wanted in ["T11", "T01", "T34", "T39", "T40", "T21", "T08", "T27", "T30", "T31"]:
        for r in candidate_rows:
            if r["id"] == wanted:
                fail_targets[r["id"]] = r
    failures = {}
    for rid, r in fail_targets.items():
        spec = next(s for s in specs if s["id"] == rid)
        tmask = spec["fn"](df)
        tmask = tmask.fillna(False).astype(bool) if isinstance(tmask, pd.Series) else pd.Series(bool(tmask), index=df.index)
        cand_mask = primary & tmask
        if spec.get("needs_lag"):
            cand_mask = cand_mask & df["price_lag1"].notna()
        failures[rid] = failure_analysis(df, cand_mask, r["name"])
    dump_json(OUT / "failure_analyses.json", failures)

    # Early vs later confirmation special test (section 15) on primary pop.
    early_spec = next(s for s in specs if s["id"] == "T39")
    late_spec = next(s for s in specs if s["id"] == "T40")
    early_mask = primary & early_spec["fn"](df).fillna(False)
    late_mask = primary & late_spec["fn"](df).fillna(False) & df["price_lag1"].notna()
    # Entry-price proxy: near_bottom_20_pct (higher = more expensive vs the low).
    early_vs_late = {
        "definition_early": "Primary decline pop AND at 20d low today (nb20<=1)",
        "definition_late": "Primary decline pop AND 1-3 sessions after a 20d low AND price > EMA9",
        "early": profile(df, early_mask, "EARLY"),
        "late": profile(df, late_mask, "LATE"),
        "early_entry_extension_nb20_median": to_py(df.loc[early_mask, "near_bottom_20_pct"].median()),
        "late_entry_extension_nb20_median": to_py(df.loc[late_mask, "near_bottom_20_pct"].median()),
        "early_mae_t5": nan_stats(df.loc[early_mask, "mae_t5"]),
        "late_mae_t5": nan_stats(df.loc[late_mask, "mae_t5"]),
        "early_mfe_t5": nan_stats(df.loc[early_mask, "mfe_t5"]),
        "late_mfe_t5": nan_stats(df.loc[late_mask, "mfe_t5"]),
        "false_positive_early_t5": float((df.loc[early_mask, "ret_t5"] <= 0).mean()) if early_mask.any() else None,
        "false_positive_late_t5": float((df.loc[late_mask, "ret_t5"] <= 0).mean()) if late_mask.any() else None,
    }
    dump_json(OUT / "early_vs_late.json", early_vs_late)

    # Market dependence: candidate on July cluster vs rest.
    market_dep = []
    for r in candidate_rows:
        cand = r["candidate"]
        ep = cand.get("episode_breakdown") or {}
        market_dep.append({
            "id": r["id"],
            "name": r["name"],
            "n": cand["n"],
            "july_share": cand.get("july_cluster_share"),
            "E1_t5": ((ep.get("E1_JUL_BOTTOM_BOUNCE") or {}).get("t5") or {}).get("median"),
            "E1_n": (ep.get("E1_JUL_BOTTOM_BOUNCE") or {}).get("n"),
            "E2_t5": ((ep.get("E2_EARLY_AUG_CONTINUATION") or {}).get("t5") or {}).get("median"),
            "E2_n": (ep.get("E2_EARLY_AUG_CONTINUATION") or {}).get("n"),
            "E3_t5": ((ep.get("E3_MID_AUG") or {}).get("t5") or {}).get("median"),
            "E3_n": (ep.get("E3_MID_AUG") or {}).get("n"),
            "E4_t5": ((ep.get("E4_LATE_AUG") or {}).get("t5") or {}).get("median"),
            "E4_n": (ep.get("E4_LATE_AUG") or {}).get("n"),
            "ex_t5": ((cand.get("excess") or {}).get("t5") or {}).get("median"),
            "incC_t5": (r["incremental_vs_C"].get("t5") or {}).get("delta_median"),
        })
    write_df(OUT / "market_dependence.csv", pd.DataFrame(market_dep))

    dump_json(OUT / "research_ledger.json", {
        "run_id": RUN_ID,
        "timestamp_utc": TIMESTAMP,
        "n_ledger_entries": len(ledger),
        "n_populations_tested": len(POPULATIONS),
        "n_transitions_tested": len(specs),
        "n_tertile_features": len(TERTILE_FEATURES),
        "primary_population": PRIMARY_POP,
        "search_cardinality_approx": len(POPULATIONS) + len(specs) + len(TERTILE_FEATURES) + len(specs) * len(alt_pops_for_screen),
        "entries": ledger,
    })

    # Example rebound magnitudes (descriptive, using panel min→max after min — LOOK-AHEAD, not a signal).
    examples = ["FRT", "GIL", "DGW", "GEX", "GVR", "GAS", "VRE", "PVT", "PNJ", "VTP", "DGC", "VIX"]
    ex_rows = []
    for sym in examples:
        s = df[df["symbol"] == sym].sort_values("trade_date")
        if s.empty:
            continue
        i = s["price"].idxmin()
        pmin = float(s.loc[i, "price"])
        dmin = pd.Timestamp(s.loc[i, "trade_date"]).strftime("%Y-%m-%d")
        after = s.loc[s["trade_date"] >= s.loc[i, "trade_date"]]
        pmax = float(after["price"].max())
        ex_rows.append({
            "symbol": sym,
            "panel_min_date": dmin,
            "panel_min_price": pmin,
            "panel_max_after": pmax,
            "peak_rebound_pct": (pmax / pmin - 1) * 100.0,
            "t10_from_min": to_py(s.loc[i, "ret_t10"]),
            "WARNING": "uses full-sample min; descriptive only",
        })
    dump_json(OUT / "descriptive_example_rebounds.json", ex_rows)

    # Freeze top candidates (by incremental vs C, min N) for the package — still labeled with conservative verdicts.
    ranked = sorted(
        [r for r in candidate_rows if r["family"] != "anti" and (r["screen"]["n"] or 0) >= 20],
        key=lambda r: (r["screen"].get("incC_t5_median") is not None, r["screen"].get("incC_t5_median") or -999),
        reverse=True,
    )
    strongest = ranked[:8]
    dump_json(OUT / "strongest_candidates.json", strongest)
    dump_json(OUT / "rejected_candidates.json", [
        {"id": r["id"], "name": r["name"], "family": r["family"], "screen": r["screen"], "why_rejected_hint": r["why_tested"]}
        for r in rejected
    ])
    dump_json(OUT / "anti_edge_candidates.json", [
        {"id": r["id"], "name": r["name"], "screen": r["screen"]} for r in anti
    ])

    print(f"RUN_ID={RUN_ID}")
    print(f"panel rows={len(df)} symbols={df['symbol'].nunique()} dates={df['trade_date'].nunique()}")
    print(f"primary pop n={int(primary.sum())}")
    print("top incremental vs C:")
    print(screen_df.head(12).to_string(index=False))
    print("anti:")
    print(screen_df[screen_df["family"] == "anti"].to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (OUT).mkdir(parents=True, exist_ok=True)
        (OUT / "run_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
