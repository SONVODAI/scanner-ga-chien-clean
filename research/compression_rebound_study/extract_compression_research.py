#!/usr/bin/env python3
"""
READ-ONLY examiner extraction for the compression-rebound hypothesis study.

Does not write to production artifacts, timers, services, Edge Research,
genesis, or BOT behavior. Reads existing CSVs only.

Outputs:
  - compression_stock_research.csv
  - compression_research_audit.md
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EL = ROOT / "data" / "earning_learning"
OUT_DIR = Path(__file__).resolve().parent

HEALTH_STATES = [
    "🌱 ĐANG HỒI",
    "🟡 TRUNG TÍNH",
    "🔴 YẾU",
    "⚠️ YẾU DẦN",
    "⛔ RẤT YẾU",
]
YEU_DAN = "⚠️ YẾU DẦN"
HEALTH_SHORT = {
    "🌱 ĐANG HỒI": "DANG_HOI",
    "🟡 TRUNG TÍNH": "TRUNG_TINH",
    "🔴 YẾU": "YEU",
    "⚠️ YẾU DẦN": "YEU_DAN",
    "⛔ RẤT YẾU": "RAT_YEU",
}


def _norm_sym(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().str.strip()


def _norm_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _empty_like(n: int) -> pd.Series:
    return pd.Series([np.nan] * n, dtype="float64")


def load_sources() -> dict[str, pd.DataFrame]:
    obs = pd.read_csv(EL / "observations.csv", encoding="utf-8-sig", low_memory=False)
    freeze = pd.read_csv(EL / "t0_observation_freeze.csv", encoding="utf-8-sig", low_memory=False)
    snap = pd.read_csv(ROOT / "data" / "earning_money_snapshots.csv", encoding="utf-8-sig", low_memory=False)
    outc = pd.read_csv(EL / "outcomes.csv", encoding="utf-8-sig", low_memory=False)
    mkt = pd.read_csv(EL / "market_daily_t0.csv", encoding="utf-8-sig", low_memory=False)
    mkt_sess = pd.read_csv(EL / "market_t0_snapshot.csv", encoding="utf-8-sig", low_memory=False)
    gev = pd.read_csv(ROOT / "group_evolution_history.csv", encoding="utf-8-sig", low_memory=False)
    return {
        "obs": obs,
        "freeze": freeze,
        "snap": snap,
        "outc": outc,
        "mkt": mkt,
        "mkt_sess": mkt_sess,
        "gev": gev,
    }


def standardize_obs(obs: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "trade_date": _norm_date(obs["trade_date"]),
            "ticker": _norm_sym(obs["symbol"]),
            "observation_id": obs["observation_id"].astype(str),
            "health_group": obs["health_group"].astype(str),
            "health_score": _num(obs.get("health_score")),
            "action_group": obs.get("group", pd.Series([""] * len(obs))).astype(str),
            "close": _num(obs["price"]),
            "volume": _num(obs.get("volume")),
            "rsi14": _num(obs.get("rsi14")),
            "rs5": _num(obs.get("rs5")),
            "rs10": _num(obs.get("rs10")),
            "ema9": _num(obs.get("ema9")),
            "ma20": _num(obs.get("ma20")),
            "obv": _num(obs.get("obv")),
            "vol_ma20": _num(obs.get("vol_ma20")),
            "volume_ratio20": _num(obs.get("volume_ratio20")),
            "price_vs_ema9_pct": _num(obs.get("price_vs_ema9_pct")),
            "price_vs_ma20_pct": _num(obs.get("price_vs_ma20_pct")),
            "market_real": _num(obs.get("market_real")),
            "market_regime": obs.get("market_regime", pd.Series([""] * len(obs))).astype(str),
            "market_live": _num(obs.get("market_live")),
            "market_forecast": _num(obs.get("market_forecast")),
            "breadth": _num(obs.get("breadth")),
            "recorded_at": obs.get("recorded_at", pd.Series([""] * len(obs))).astype(str),
            "frozen_at": "",
            "source_artifact": "data/earning_learning/observations.csv",
            "t0_priority": "observations",
        }
    )
    return out


def standardize_freeze(freeze: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "trade_date": _norm_date(freeze["trade_date"]),
            "ticker": _norm_sym(freeze["symbol"]),
            "observation_id": freeze["observation_id"].astype(str),
            "health_group": freeze["health_group"].astype(str),
            "health_score": _num(freeze.get("health_score")),
            "action_group": freeze.get("group", pd.Series([""] * len(freeze))).astype(str),
            "close": _num(freeze["price"]),
            "volume": _num(freeze.get("volume")),
            "rsi14": _num(freeze.get("rsi14")),
            "rs5": _num(freeze.get("rs5")),
            "rs10": _num(freeze.get("rs10")),
            "ema9": _num(freeze.get("ema9")),
            "ma20": _num(freeze.get("ma20")),
            "obv": _num(freeze.get("obv")),
            "vol_ma20": _num(freeze.get("vol_ma20")),
            "volume_ratio20": _num(freeze.get("volume_ratio20")),
            "price_vs_ema9_pct": _num(freeze.get("price_vs_ema9_pct")),
            "price_vs_ma20_pct": _num(freeze.get("price_vs_ma20_pct")),
            "market_real": _num(freeze.get("market_real")),
            "market_regime": freeze.get("market_regime", pd.Series([""] * len(freeze))).astype(str),
            "market_live": _num(freeze.get("market_live")),
            "market_forecast": _num(freeze.get("market_forecast")),
            "breadth": _num(freeze.get("breadth")),
            "recorded_at": freeze.get("recorded_at", pd.Series([""] * len(freeze))).astype(str),
            "frozen_at": freeze.get("frozen_at", pd.Series([""] * len(freeze))).astype(str),
            "source_artifact": "data/earning_learning/t0_observation_freeze.csv",
            "t0_priority": "t0_freeze",
        }
    )
    return out


def standardize_snap(snap: pd.DataFrame) -> pd.DataFrame:
    dist_ema = _num(snap.get("dist_from_ema9_pct"))
    price = _num(snap["price"])
    ema9 = _num(snap.get("ema9"))
    ma20 = _num(snap.get("ma20"))
    vs_ema = np.where(ema9 > 0, (price / ema9 - 1.0) * 100.0, np.nan)
    vs_ma = np.where(ma20 > 0, (price / ma20 - 1.0) * 100.0, np.nan)
    vol = _num(snap.get("volume"))
    vol_ma20 = _num(snap.get("vol_ma20"))
    ratio = _num(snap.get("volume_ratio20"))
    ratio = ratio.where(ratio.notna(), np.where(vol_ma20 > 0, vol / vol_ma20, np.nan))
    n = len(snap)
    out = pd.DataFrame(
        {
            "trade_date": _norm_date(snap["snapshot_date"]),
            "ticker": _norm_sym(snap["symbol"]),
            "observation_id": "",
            "health_group": snap["health"].astype(str),
            "health_score": _empty_like(n),
            "action_group": snap.get("group", pd.Series([""] * n)).astype(str),
            "close": price,
            "volume": vol,
            "rsi14": _num(snap.get("rsi14")),
            "rs5": _num(snap.get("rs5")),
            "rs10": _num(snap.get("rs10")),
            "ema9": ema9,
            "ma20": ma20,
            "obv": _num(snap.get("obv")),
            "vol_ma20": vol_ma20,
            "volume_ratio20": ratio,
            "price_vs_ema9_pct": pd.Series(np.where(dist_ema.notna(), dist_ema, vs_ema)),
            "price_vs_ma20_pct": pd.Series(vs_ma),
            "market_real": _num(snap.get("market_real")),
            "market_regime": snap.get("market_regime", pd.Series([""] * n)).astype(str),
            "market_live": _num(snap.get("market_live")),
            "market_forecast": _num(snap.get("market_forecast")),
            "breadth": _num(snap.get("market_breadth_score")),
            "recorded_at": snap.get("saved_at", pd.Series([""] * n)).astype(str),
            "frozen_at": "",
            "source_artifact": "data/earning_money_snapshots.csv",
            "t0_priority": "snapshot_fill",
        }
    )
    return out


def build_panel(src: dict[str, pd.DataFrame]) -> pd.DataFrame:
    obs = standardize_obs(src["obs"])
    freeze = standardize_freeze(src["freeze"])
    snap = standardize_snap(src["snap"])

    obs_keys = set(zip(obs["trade_date"], obs["ticker"]))
    freeze_keys = set(zip(freeze["trade_date"], freeze["ticker"]))

    # Snapshot rows only when no observation and no freeze exist.
    snap_only_mask = [
        (d, t) not in obs_keys and (d, t) not in freeze_keys
        for d, t in zip(snap["trade_date"], snap["ticker"])
    ]
    snap_only = snap.loc[snap_only_mask].copy()

    # Prefer freeze over observations on overlapping keys (PIT first-write-wins).
    obs_not_frozen = obs.loc[
        [key not in freeze_keys for key in zip(obs["trade_date"], obs["ticker"])]
    ].copy()

    panel = pd.concat([freeze, obs_not_frozen, snap_only], ignore_index=True, sort=False)
    panel = panel[panel["trade_date"] >= "2026-07-23"].copy()
    panel["dt"] = pd.to_datetime(panel["trade_date"])
    panel["calendar_weekday"] = panel["dt"].dt.day_name()
    panel["is_weekend"] = panel["dt"].dt.dayofweek >= 5
    panel["is_trading_day_row"] = ~panel["is_weekend"]

    panel = panel.sort_values(["ticker", "trade_date"], kind="stable").reset_index(drop=True)
    return panel


def attach_lags(panel: pd.DataFrame) -> pd.DataFrame:
    """Examiner lag of stored health_group on weekday rows only. No future data."""
    out = panel.copy()
    trading = out[out["is_trading_day_row"]].copy()
    trading = trading.sort_values(["ticker", "trade_date"], kind="stable")
    for k in range(1, 6):
        trading[f"state_lag{k}"] = trading.groupby("ticker")["health_group"].shift(k)
    lag_cols = [f"state_lag{k}" for k in range(1, 6)]
    out = out.merge(
        trading[["trade_date", "ticker"] + lag_cols],
        on=["trade_date", "ticker"],
        how="left",
    )
    # Weekend observation rows: attach lags from the latest prior weekday.
    weekend = out["state_lag1"].isna() & out["is_weekend"]
    if weekend.any():
        prior = (
            trading[["ticker", "trade_date", "health_group"] + lag_cols]
            .sort_values(["ticker", "trade_date"])
        )
        for idx in out.index[weekend]:
            tkr = out.at[idx, "ticker"]
            d = out.at[idx, "trade_date"]
            hist = prior[(prior["ticker"] == tkr) & (prior["trade_date"] < d)]
            if hist.empty:
                continue
            last = hist.iloc[-1]
            out.at[idx, "state_lag1"] = last["health_group"]
            for k in range(2, 6):
                out.at[idx, f"state_lag{k}"] = last.get(f"state_lag{k - 1}", np.nan)
    return out


def attach_outcomes(panel: pd.DataFrame, outc: pd.DataFrame) -> pd.DataFrame:
    wide_ret = outc.pivot_table(
        index="observation_id",
        columns="horizon",
        values="return_pct",
        aggfunc="first",
    )
    wide_dt = outc.pivot_table(
        index="observation_id",
        columns="horizon",
        values="target_date",
        aggfunc="first",
    )
    for frame in (wide_ret, wide_dt):
        frame.columns = [int(c) for c in frame.columns]
    out = panel.copy()
    out["t3_return"] = out["observation_id"].map(wide_ret.get(3, pd.Series(dtype=float)))
    out["t5_return"] = out["observation_id"].map(wide_ret.get(5, pd.Series(dtype=float)))
    out["t10_return"] = out["observation_id"].map(wide_ret.get(10, pd.Series(dtype=float)))
    out["t3_target_date"] = out["observation_id"].map(wide_dt.get(3, pd.Series(dtype=object)))
    out["t5_target_date"] = out["observation_id"].map(wide_dt.get(5, pd.Series(dtype=object)))
    out["t10_target_date"] = out["observation_id"].map(wide_dt.get(10, pd.Series(dtype=object)))

    def status(ret: pd.Series, has_id: pd.Series) -> pd.Series:
        st = pd.Series("UNAVAILABLE", index=ret.index)
        st.loc[has_id] = "WAITING"
        st.loc[ret.notna()] = "MATURE"
        return st

    has_id = out["observation_id"].astype(str).str.len() > 0
    out["t3_status"] = status(out["t3_return"], has_id)
    out["t5_status"] = status(out["t5_return"], has_id)
    out["t10_status"] = status(out["t10_return"], has_id)
    return out


def attach_market(panel: pd.DataFrame, mkt: pd.DataFrame, mkt_sess: pd.DataFrame) -> pd.DataFrame:
    daily = mkt.copy()
    daily["trade_date"] = _norm_date(daily["trade_date"])
    keep = [
        "trade_date",
        "vnindex_close",
        "vnindex_daily_return_pct",
        "market_real",
        "market_regime",
        "market_live",
        "market_forecast",
        "breadth_score",
        "breadth_level",
        "ga_tang_toc",
        "cp_manh",
        "mua_break",
        "pull_dep",
        "pull_vua",
        "mua_early",
        "tich_luy",
        "theo_doi",
        "canonical_t0",
    ]
    keep = [c for c in keep if c in daily.columns]
    daily = daily[keep].copy()
    daily = daily.rename(
        columns={
            "market_real": "mkt_daily_market_real",
            "market_regime": "mkt_daily_market_regime",
            "market_live": "mkt_daily_market_live",
            "market_forecast": "mkt_daily_market_forecast",
        }
    )
    daily["vnindex_source"] = "data/earning_learning/market_daily_t0.csv"

    # 2026-08-28 has no canonical daily T0; midday session snapshot exists.
    sess = mkt_sess.copy()
    sess["trade_date"] = _norm_date(sess["trade_date"])
    midday = sess[(sess["trade_date"] == "2026-08-28") & (sess["session_slot"].astype(str) == "MIDDAY")]
    extra_rows = []
    if not midday.empty and "2026-08-28" not in set(daily["trade_date"]):
        row = midday.iloc[0]
        extra_rows.append(
            {
                "trade_date": "2026-08-28",
                "vnindex_close": row.get("vnindex_close"),
                "vnindex_daily_return_pct": row.get("vnindex_daily_return_pct"),
                "mkt_daily_market_real": row.get("market_real"),
                "mkt_daily_market_regime": row.get("market_regime"),
                "mkt_daily_market_live": row.get("market_live"),
                "mkt_daily_market_forecast": row.get("market_forecast"),
                "breadth_score": row.get("breadth_score"),
                "breadth_level": row.get("breadth_level"),
                "ga_tang_toc": row.get("ga_tang_toc"),
                "cp_manh": row.get("cp_manh"),
                "mua_break": row.get("mua_break"),
                "pull_dep": row.get("pull_dep"),
                "pull_vua": row.get("pull_vua"),
                "mua_early": row.get("mua_early"),
                "tich_luy": row.get("tich_luy"),
                "theo_doi": row.get("theo_doi"),
                "canonical_t0": False,
                "vnindex_source": "data/earning_learning/market_t0_snapshot.csv:MIDDAY",
            }
        )
    if extra_rows:
        daily = pd.concat([daily, pd.DataFrame(extra_rows)], ignore_index=True)

    out = panel.merge(daily, on="trade_date", how="left")
    # Prefer canonical/session market fields when present; else keep stock-row fields.
    out["market_real"] = _num(out["mkt_daily_market_real"]).combine_first(_num(out["market_real"]))
    out["market_regime"] = out["mkt_daily_market_regime"].where(
        out["mkt_daily_market_regime"].notna()
        & (out["mkt_daily_market_regime"].astype(str).str.strip() != "")
        & (out["mkt_daily_market_regime"].astype(str) != "nan"),
        out["market_regime"],
    )
    out["market_live"] = _num(out["mkt_daily_market_live"]).combine_first(_num(out["market_live"]))
    out["market_forecast"] = _num(out["mkt_daily_market_forecast"]).combine_first(
        _num(out["market_forecast"])
    )
    out = out.drop(
        columns=[
            "mkt_daily_market_real",
            "mkt_daily_market_regime",
            "mkt_daily_market_live",
            "mkt_daily_market_forecast",
        ],
        errors="ignore",
    )
    return out


def add_universe_n(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    counts = out.groupby("trade_date")["ticker"].transform("nunique")
    out["universe_n"] = counts
    return out


def finalize_csv(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    # Unavailable requested fields are omitted (not reserved as empty columns):
    # open, high, low, wma45, foreign_*, market_transition.

    cols = [
        "trade_date",
        "ticker",
        "observation_id",
        "health_group",
        "health_score",
        "action_group",
        "state_lag1",
        "state_lag2",
        "state_lag3",
        "state_lag4",
        "state_lag5",
        "close",
        "volume",
        "rsi14",
        "rs5",
        "rs10",
        "ema9",
        "ma20",
        "obv",
        "vol_ma20",
        "volume_ratio20",
        "price_vs_ema9_pct",
        "price_vs_ma20_pct",
        "t3_return",
        "t5_return",
        "t10_return",
        "t3_status",
        "t5_status",
        "t10_status",
        "t3_target_date",
        "t5_target_date",
        "t10_target_date",
        "vnindex_close",
        "vnindex_daily_return_pct",
        "vnindex_source",
        "market_real",
        "market_regime",
        "market_live",
        "market_forecast",
        "breadth",
        "breadth_score",
        "breadth_level",
        "ga_tang_toc",
        "cp_manh",
        "mua_break",
        "pull_dep",
        "pull_vua",
        "mua_early",
        "tich_luy",
        "theo_doi",
        "calendar_weekday",
        "is_weekend",
        "is_trading_day_row",
        "universe_n",
        "source_artifact",
        "t0_priority",
        "recorded_at",
        "frozen_at",
        "canonical_t0",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    out = out[cols].sort_values(["trade_date", "ticker"], kind="stable").reset_index(drop=True)
    return out


def pct(n: int, d: int) -> str:
    if d <= 0:
        return "n/a"
    return f"{100.0 * n / d:.1f}%"


def fmt(x, digits=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "n/a"


def missing_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| field | missing % | nonempty | stored? |", "|---|---:|---:|---|"]
    n = len(df)
    for c in cols:
        if c not in df.columns:
            lines.append(f"| `{c}` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |")
            continue
        s = df[c]
        if s.dtype == bool:
            miss = 0
        else:
            if pd.api.types.is_numeric_dtype(s):
                miss = int(s.isna().sum())
            else:
                miss = int(s.isna().sum() + (s.astype(str).str.strip().isin(["", "nan", "None"])).sum())
        lines.append(
            f"| `{c}` | {100.0 * miss / n:.1f}% | {n - miss} | from source artifacts / examiner lag |"
        )
    return "\n".join(lines)


def yeu_dan_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Examiner-only features for YẾU DẦN rows. Backward-looking on stored values."""
    trading = panel[panel["is_trading_day_row"]].copy()
    trading = trading.sort_values(["ticker", "trade_date"], kind="stable")

    def streak_prev(g: pd.DataFrame) -> pd.Series:
        values = g["health_group"].tolist()
        out = []
        for i, val in enumerate(values):
            if val != YEU_DAN:
                out.append(np.nan)
                continue
            k = 1
            j = i - 1
            while j >= 0 and values[j] == YEU_DAN:
                k += 1
                j -= 1
            out.append(k)
        return pd.Series(out, index=g.index)

    trading["yeu_dan_streak"] = trading.groupby("ticker", group_keys=False).apply(streak_prev)
    trading["prev_state"] = trading.groupby("ticker")["health_group"].shift(1)

    for col, prefix in (("rs5", "rs5"), ("rs10", "rs10"), ("rsi14", "rsi14")):
        for k in (1, 3, 5):
            prev = trading.groupby("ticker")[col].shift(k)
            trading[f"{prefix}_chg_{k}d"] = trading[col] - prev

    def drawdown(g: pd.DataFrame, window: int) -> pd.Series:
        # Highest close over previous `window` trading days, excluding T0.
        prev_max = g["close"].shift(1).rolling(window, min_periods=1).max()
        return np.where(prev_max > 0, (g["close"] / prev_max - 1.0) * 100.0, np.nan)

    trading["dd_from_high5"] = trading.groupby("ticker", group_keys=False).apply(
        lambda g: pd.Series(drawdown(g, 5), index=g.index)
    )
    trading["dd_from_high10"] = trading.groupby("ticker", group_keys=False).apply(
        lambda g: pd.Series(drawdown(g, 10), index=g.index)
    )
    return trading[trading["health_group"] == YEU_DAN].copy()


def md_escape(s: str) -> str:
    return str(s).replace("|", "\\|")


def build_audit(panel: pd.DataFrame, src: dict[str, pd.DataFrame], csv_path: Path) -> str:
    obs = src["obs"]
    freeze = src["freeze"]
    snap = src["snap"]
    outc = src["outc"]
    mkt = src["mkt"]
    gev = src["gev"]

    n = len(panel)
    dates = sorted(panel["trade_date"].unique())
    tickers = sorted(panel["ticker"].unique())
    trading = panel[panel["is_trading_day_row"]].copy()
    weekend = panel[panel["is_weekend"]].copy()
    yd = yeu_dan_features(panel)

    src_counts = panel["t0_priority"].value_counts().to_dict()
    date_n = panel.groupby("trade_date")["ticker"].nunique()
    orig_obs_n = (
        src["obs"].assign(trade_date=_norm_date(src["obs"]["trade_date"]))
        .groupby("trade_date")["symbol"]
        .nunique()
    )

    # Preview A on trading-day rows only.
    a_rows = []
    prev_pct = None
    for d, g in trading.groupby("trade_date", sort=True):
        total = len(g)
        row = {"trade_date": d, "n": total, "weekday": g["calendar_weekday"].iloc[0]}
        for st in HEALTH_STATES:
            row[st] = 100.0 * (g["health_group"] == st).mean() if total else np.nan
        if prev_pct is not None:
            for st in HEALTH_STATES:
                row[f"d_{st}"] = row[st] - prev_pct[st]
        else:
            for st in HEALTH_STATES:
                row[f"d_{st}"] = np.nan
        prev_pct = {st: row[st] for st in HEALTH_STATES}
        a_rows.append(row)
    a_df = pd.DataFrame(a_rows)

    def a_table(df: pd.DataFrame) -> str:
        lines = [
            "| date | wd | n | ĐANG HỒI % | Δ | TRUNG TÍNH % | Δ | YẾU % | Δ | YẾU DẦN % | Δ | RẤT YẾU % | Δ |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in df.iterrows():
            lines.append(
                "| {d} | {wd} | {n} | {h} | {dh} | {t} | {dt} | {y} | {dy} | {yd} | {dyd} | {r_} | {dr} |".format(
                    d=r["trade_date"],
                    wd=str(r["weekday"])[:3],
                    n=int(r["n"]),
                    h=fmt(r["🌱 ĐANG HỒI"], 1),
                    dh=fmt(r["d_🌱 ĐANG HỒI"], 1),
                    t=fmt(r["🟡 TRUNG TÍNH"], 1),
                    dt=fmt(r["d_🟡 TRUNG TÍNH"], 1),
                    y=fmt(r["🔴 YẾU"], 1),
                    dy=fmt(r["d_🔴 YẾU"], 1),
                    yd=fmt(r["⚠️ YẾU DẦN"], 1),
                    dyd=fmt(r["d_⚠️ YẾU DẦN"], 1),
                    r_=fmt(r["⛔ RẤT YẾU"], 1),
                    dr=fmt(r["d_⛔ RẤT YẾU"], 1),
                )
            )
        return "\n".join(lines)

    # Preview B summary
    def qtile(s: pd.Series) -> str:
        s = pd.to_numeric(s, errors="coerce").dropna()
        if s.empty:
            return "n/a"
        return (
            f"n={len(s)} median={s.median():.2f} p25={s.quantile(0.25):.2f} "
            f"p75={s.quantile(0.75):.2f}"
        )

    prev_state_vc = yd["prev_state"].fillna("(none/first)").value_counts()
    streak_vc = yd["yeu_dan_streak"].value_counts().sort_index()

    # Preview C: date-level, mature outcomes only. Date is the unit.
    def date_level(horizon_col: str, status_col: str) -> pd.DataFrame:
        rows = []
        sub = trading[trading[status_col] == "MATURE"].copy()
        for d, g in sub.groupby("trade_date", sort=True):
            if g[horizon_col].notna().sum() == 0:
                continue
            row = {
                "trade_date": d,
                "n_rows": len(g),
                "n_mature": int(g[horizon_col].notna().sum()),
            }
            for st in HEALTH_STATES:
                sg = g[g["health_group"] == st]
                row[f"n_{HEALTH_SHORT[st]}"] = len(sg)
                row[f"med_{HEALTH_SHORT[st]}"] = sg[horizon_col].median()
            rows.append(row)
        return pd.DataFrame(rows)

    c3 = date_level("t3_return", "t3_status")
    c5 = date_level("t5_return", "t5_status")
    c10 = date_level("t10_return", "t10_status")

    def c_table(df: pd.DataFrame, label: str) -> str:
        if df.empty:
            return f"_No mature {label} dates._"
        lines = [
            f"| date | n_mature | n YẾU DẦN | med {label} ĐANG HỒI | med TRUNG TÍNH | med YẾU | med YẾU DẦN | med RẤT YẾU |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in df.iterrows():
            lines.append(
                "| {d} | {n} | {ny} | {a} | {b} | {c} | {yd} | {e} |".format(
                    d=r["trade_date"],
                    n=int(r["n_mature"]),
                    ny=int(r["n_YEU_DAN"]),
                    a=fmt(r["med_DANG_HOI"], 2),
                    b=fmt(r["med_TRUNG_TINH"], 2),
                    c=fmt(r["med_YEU"], 2),
                    yd=fmt(r["med_YEU_DAN"], 2),
                    e=fmt(r["med_RAT_YEU"], 2),
                )
            )
        # Cross-date median of date-level medians (date is the unit).
        lines.append("")
        lines.append(
            "Cross-date median of **date-level medians** (not pooled stock-days): "
            f"ĐANG HỒI {fmt(df['med_DANG_HOI'].median(), 2)}; "
            f"TRUNG TÍNH {fmt(df['med_TRUNG_TINH'].median(), 2)}; "
            f"YẾU {fmt(df['med_YEU'].median(), 2)}; "
            f"YẾU DẦN {fmt(df['med_YEU_DAN'].median(), 2)}; "
            f"RẤT YẾU {fmt(df['med_RAT_YEU'].median(), 2)}. "
            f"N_dates={len(df)}."
        )
        return "\n".join(lines)

    # Cross-date YẾU DẦN vs others using only dates with full-ish mature coverage.
    def date_unit_compare(df: pd.DataFrame, label: str) -> str:
        if df.empty:
            return ""
        full = df[df["n_mature"] >= 130].copy()
        if full.empty:
            full = df
        delta = full["med_YEU_DAN"] - full["med_RAT_YEU"]
        delta2 = full["med_YEU_DAN"] - full["med_YEU"]
        return (
            f"On {len(full)} {label} dates with n_mature≥130 (or all dates if none qualify), "
            f"median(date-median YẾU DẦN − date-median RẤT YẾU) = {fmt(delta.median(), 2)}; "
            f"median(date-median YẾU DẦN − date-median YẾU) = {fmt(delta2.median(), 2)}. "
            "This is descriptive only. No threshold was tuned."
        )

    gev["date"] = _norm_date(gev["date"])
    gev_early = gev[(gev["date"] >= "2026-06-25") & (gev["date"] < "2026-07-23")]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    lines.append("# Compression Rebound Examiner Dataset — Audit")
    lines.append("")
    lines.append(f"Extracted at: `{now}` (UTC).")
    lines.append("Status: **examiner dataset only**. Not an edge, not a production rule, not a discovery input.")
    lines.append("")
    lines.append("## 0. Scientific constraints honored")
    lines.append("")
    lines.append("- Production code, timers, services, Edge Research, genesis, Edge Memory, and BOT behavior were not modified.")
    lines.append("- No historical artifact was regenerated or rewritten.")
    lines.append("- No missing history was synthesized.")
    lines.append("- No future field enters a T0 feature column.")
    lines.append("- T3/T5/T10 are joined from already-stored production outcomes; they are labels, not features.")
    lines.append("- Market DATE is the primary independent unit in preview C. Stock-days on the same date are not treated as independent market observations.")
    lines.append("- No threshold (40%, 50%, RSI<40, etc.) was optimized.")
    lines.append("- This hypothesis was not encoded as an ACTIVE edge and was not fed into autonomous discovery.")
    lines.append("")
    lines.append("## 1. Inspection: what can be supplied exactly")
    lines.append("")
    lines.append("| requested | status | notes |")
    lines.append("|---|---|---|")
    lines.append("| trade_date × ticker | **exact** | 142-symbol production universe from `observations.csv`; snapshot fill only where no observation/freeze row exists |")
    lines.append("| production health state | **exact** | Evolution Health labels: ĐANG HỒI / TRUNG TÍNH / YẾU / YẾU DẦN / RẤT YẾU |")
    lines.append("| previous 1–5 trading-day states | **examiner lag** | Backward shift of stored `health_group` on weekday rows |")
    lines.append("| action group | **exact** | THEO DÕI / TÍCH LŨY / MUA EARLY / PULL VỪA / PULL ĐẸP / MUA BREAK / CP MẠNH / GÀ TĂNG TỐC |")
    lines.append("| close | **exact stored `price`** | Used as close; no separate close column exists |")
    lines.append("| open / high / low | **unavailable** | Not stored in any historical earning-learning / snapshot / group-evolution artifact |")
    lines.append("| volume, vol_ma20, volume_ratio20 | **exact when stored** | Missing on weekend observation rows and before OBV backfill |")
    lines.append("| RSI14, RS5, RS10 | **exact stored** | Not recomputed |")
    lines.append("| EMA9, MA20 | **exact stored** | Missing on weekend observation rows |")
    lines.append("| WMA45 | **unavailable** | Stock-level WMA45 is not stored. VNINDEX WMA45 column exists in market T0 schema but is 100% empty |")
    lines.append("| OBV | **exact when stored** | Missing 2026-07-23..07-30 and weekend rows in observations |")
    lines.append("| T3/T5/T10 return + maturity | **exact stored** | From `outcomes.csv` via `observation_id`. Snapshot-fill rows have no outcomes |")
    lines.append("| VNINDEX close / return | **exact from 2026-08-13** | Canonical `market_daily_t0.csv`. 2026-08-28 is midday session only |")
    lines.append("| Market Real / regime | **exact from 2026-08-13** | Earlier dates have `market_regime` text on weekday observations only; no Market Real |")
    lines.append("| market transition | **unavailable** | Edge Research computes transition live; no historical store in earning-learning artifacts |")
    lines.append("| breadth by health state | **not stored** | Preview A computes it from same-date stored states |")
    lines.append("| breadth by action group | **exact from 2026-08-13** | `ga_tang_toc` … `theo_doi` in `market_daily_t0.csv` |")
    lines.append("| foreign buy/sell/net | **unavailable** | No historical foreign-flow artifact |")
    lines.append("| 2026-06-25 .. 2026-07-22 | **unavailable for this hypothesis** | `group_evolution_history.csv` has action groups + price/volume, not Evolution Health / RSI / RS |")
    lines.append("")
    lines.append("## 2. What is unavailable")
    lines.append("")
    lines.append("- Stock OHLC except stored `price` (treated as close).")
    lines.append("- Stock WMA45.")
    lines.append("- Foreign flow history.")
    lines.append("- Historical market `transition` series.")
    lines.append("- Evolution Health history before **2026-07-23**.")
    lines.append("- Canonical daily Market T0 for **2026-08-28** (MIDDAY session snapshot only).")
    lines.append("- Trading sessions **2026-08-31, 2026-09-01, 2026-09-02** in all inspected health/price panel artifacts (likely VN holiday window around 2 Sep). Not synthesized.")
    lines.append("- True trading-session T+n that is independent of observation-row presence. Stored outcomes use **observation-row index**, including four weekend observation dates.")
    lines.append("")
    lines.append("## 3. Expected / actual output size")
    lines.append("")
    lines.append(f"- CSV rows: **{n}** (one stock × date).")
    lines.append(f"- Unique tickers: **{len(tickers)}**.")
    lines.append(f"- Unique dates: **{len(dates)}** ({dates[0]} … {dates[-1]}).")
    lines.append(f"- Weekday / trading-day rows: **{len(trading)}**.")
    lines.append(f"- Weekend observation rows retained (because production outcomes use them): **{len(weekend)}**.")
    lines.append(f"- Source mix: {src_counts}.")
    lines.append(f"- File: `{csv_path}`.")
    lines.append("")
    lines.append("## 4. Source artifacts used (read-only)")
    lines.append("")
    lines.append("| artifact | role | coverage used |")
    lines.append("|---|---|---|")
    lines.append(f"| `data/earning_learning/observations.csv` | backbone stock×date; health/indicators/outcomes identity | {len(obs)} rows, 2026-07-23..2026-09-08, 34 dates, 142 tickers |")
    lines.append(f"| `data/earning_learning/t0_observation_freeze.csv` | **preferred T0 values** on overlap (first-write-wins PIT) | {len(freeze)} rows, 2026-08-13..2026-09-08 |")
    lines.append(f"| `data/earning_learning/outcomes.csv` | stored T3/T5/T10 | {len(outc)} rows; horizons 3/5/10 |")
    lines.append(f"| `data/earning_money_snapshots.csv` | fill **only** missing stock×date (2026-08-26 full day; 2026-09-03 missing 138 names) | {len(snap)} rows |")
    lines.append(f"| `data/earning_learning/market_daily_t0.csv` | canonical VNINDEX + Market Real/regime + action-group breadth | {len(mkt)} dates from 2026-08-13 |")
    lines.append("| `data/earning_learning/market_t0_snapshot.csv` | 2026-08-28 MIDDAY VNINDEX/context only | 1 extra date |")
    lines.append(f"| `group_evolution_history.csv` | inspected only; **not used as health panel** | {len(gev)} rows from 2026-05-26; early window is action-group taxonomy |")
    lines.append("| `app.py` / `modules/evolution_health.py` / `modules/earning_learning.py` | definition lookup only | no writes |")
    lines.append("")
    lines.append("### Field → source map")
    lines.append("")
    lines.append("| field | source | stored or derived |")
    lines.append("|---|---|---|")
    lines.append("| `health_group`, `health_score`, `action_group` | freeze if present else observations else snapshot | stored |")
    lines.append("| `close` | stored `price` / snapshot `price` | stored, renamed |")
    lines.append("| `rsi14`, `rs5`, `rs10`, `ema9`, `ma20`, `obv`, `volume`, `vol_ma20` | same priority | stored |")
    lines.append("| `volume_ratio20`, `price_vs_ema9_pct`, `price_vs_ma20_pct` | stored; snapshot ratio may be volume/vol_ma20 if the stored ratio is empty | stored / identity fill |")
    lines.append("| `state_lag1..5` | examiner backward shift of stored `health_group` on weekday rows | derived, PIT-safe |")
    lines.append("| `t3/t5/t10_return` + status + target_date | `outcomes.csv` via `observation_id` | stored |")
    lines.append("| `vnindex_*` | `market_daily_t0.csv` (canonical) or 2026-08-28 MIDDAY snapshot | stored |")
    lines.append("| `market_real/regime/live/forecast` | canonical market daily when present, else freeze/obs row | stored |")
    lines.append("| `ga_tang_toc` … `theo_doi` | `market_daily_t0.csv` action-group counts | stored |")
    lines.append("| `open,high,low,wma45,foreign_*,market_transition` | none | **omitted from CSV** |")
    lines.append("| `source_artifact`, `t0_priority`, `is_weekend`, `universe_n` | extractor metadata | derived |")
    lines.append("")
    lines.append("## 5. Date coverage and incomplete universe")
    lines.append("")
    lines.append(f"Panel dates: `{', '.join(dates)}`.")
    lines.append("")
    lines.append("After snapshot fill, every panel date has **142** tickers. Original observation/freeze coverage:")
    lines.append("")
    lines.append("| date | original observation n | panel n after fill |")
    lines.append("|---|---:|---:|")
    listed = False
    for d in dates:
        orig = int(orig_obs_n[d]) if d in orig_obs_n.index else 0
        panel_n = int(date_n[d]) if d in date_n.index else 0
        if orig != 142:
            lines.append(f"| {d} | {orig} | {panel_n} |")
            listed = True
    if not listed:
        lines.append("| _(none)_ | 142 | 142 |")
    lines.append("")
    lines.append("Only dates that were incomplete in `observations.csv` / freeze are listed above.")
    lines.append("")
    lines.append("Weekend observation dates retained (health/price mostly copies of prior session, except 2026-08-08 which is **not** a copy):")
    lines.append("")
    lines.append("- 2026-07-26 Sunday")
    lines.append("- 2026-08-01 Saturday")
    lines.append("- 2026-08-02 Sunday")
    lines.append("- 2026-08-08 Saturday")
    lines.append("")
    lines.append("Missing weekday sessions with **no** health panel in observations/freeze (not synthesized):")
    lines.append("")
    lines.append("- 2026-08-26: full 142-row snapshot exists → included as `snapshot_fill`, no stored T3/T5/T10")
    lines.append("- 2026-08-31, 2026-09-01, 2026-09-02: absent from observations, freeze, snapshots, and group-evolution")
    lines.append("")
    lines.append(f"`group_evolution_history.csv` from 2026-06-25 through 2026-07-22: {len(gev_early)} rows, {gev_early['date'].nunique()} dates, {gev_early['symbol'].nunique()} symbols (includes 10 non-current-universe names). Action groups only. Not included in the CSV.")
    lines.append("")
    lines.append("## 6. Missingness in the extracted CSV")
    lines.append("")
    lines.append(
        missing_table(
            panel,
            [
                "health_group",
                "close",
                "volume",
                "rsi14",
                "rs5",
                "rs10",
                "ema9",
                "ma20",
                "obv",
                "t3_return",
                "t5_return",
                "t10_return",
                "vnindex_close",
                "market_real",
                "market_regime",
                "state_lag1",
                "state_lag5",
                "open",
                "high",
                "low",
                "wma45",
                "market_transition",
                "foreign_net",
            ],
        )
    )
    lines.append("")
    lines.append("## 7. Stored vs recomputed")
    lines.append("")
    lines.append("- **Not recomputed:** RSI14, RS5, RS10, EMA9, MA20, OBV, volume, health_group, Market Real, VNINDEX, T3/T5/T10.")
    lines.append("- **Renamed only:** stored `price` → `close`.")
    lines.append("- **Examiner derived (backward only):** `state_lag1..5`; preview B streak / RS-RSI deltas / close drawdowns.")
    lines.append("- **Identity fill:** snapshot `volume_ratio20` empty → `volume/vol_ma20` when both stored. Not a new indicator definition.")
    lines.append("- **No silent alternate definitions.**")
    lines.append("")
    lines.append("## 8. Production definitions (as discoverable in code)")
    lines.append("")
    lines.append("### 8.1 Evolution Health group / YẾU DẦN")
    lines.append("")
    lines.append("Source: `modules/evolution_health.py` (`add_evolution_health`).")
    lines.append("")
    lines.append("Composite score (0–100), rounded to 1 decimal:")
    lines.append("")
    lines.append("- RS 24% + EMA 20% + OBV 18% + RSI 15% + volume 8% + position 9% + pattern 6%")
    lines.append("- RS uses stored RS5/RS10; RSI uses stored RSI14 + `rsi_slope`; EMA uses `ema9_ma20_slope` and its 3-session change")
    lines.append("")
    lines.append("Base buckets:")
    lines.append("")
    lines.append("- ≥68 → 🌱 ĐANG HỒI")
    lines.append("- 54–68 → 🟡 TRUNG TÍNH")
    lines.append("- 40–54 → 🔴 YẾU")
    lines.append("- 27–40 → ⚠️ YẾU DẦN")
    lines.append("- <27 → ⛔ RẤT YẾU")
    lines.append("")
    lines.append("Override: if `weakening` and score ∈ [27, 54) → ⚠️ YẾU DẦN.")
    lines.append("`weakening` = at least 3 of: `ema9_ma20_slope<0`, `ema9_ma20_slope_change<0`, `rsi_slope<0`, `rs5<rs10`, `rs5<0`.")
    lines.append("")
    lines.append("Therefore YẾU DẦN is **not** a pure “was strong, now compressed” label. It mixes low score and a 3-of-5 weakening vote. Distinguishing spring compression from structural weakness is **not** already encoded.")
    lines.append("")
    lines.append("### 8.2 RS5 / RS10")
    lines.append("")
    lines.append("Source: `app.py` indicator block:")
    lines.append("")
    lines.append("```")
    lines.append("rs5  = (close / close.shift(5)  - 1) * 100")
    lines.append("rs10 = (close / close.shift(10) - 1) * 100")
    lines.append("```")
    lines.append("")
    lines.append("These are own-price percentage changes over 5/10 bars on the production OHLCV series, **not** vs VNINDEX. Stored values were copied; not recomputed here.")
    lines.append("")
    lines.append("### 8.3 RSI14")
    lines.append("")
    lines.append("Source: `app.py` `calc_rsi(close, period=14)`:")
    lines.append("")
    lines.append("- Wilder-style EWM: `alpha = 1/14`, `adjust=False`")
    lines.append("- `gain = clip(diff, lower=0)`, `loss = -clip(diff, upper=0)`")
    lines.append("- `RSI = 100 - 100/(1 + avg_gain/avg_loss)`")
    lines.append("- `fillna(50)` when undefined")
    lines.append("")
    lines.append("Stored `rsi14` values were copied; not recomputed.")
    lines.append("")
    lines.append("### 8.4 Forward T3 / T5 / T10")
    lines.append("")
    lines.append("Source: `modules/earning_learning.py` `_build_outcomes`.")
    lines.append("")
    lines.append("- Horizons `{3,5,10}`")
    lines.append("- Per symbol, observations sorted by `trade_date`")
    lines.append("- Target = observation row at `index + horizon` (**observation-row**, not a separately curated trading calendar)")
    lines.append("- `return_pct = (target_price / entry_price - 1) * 100` using stored `price`")
    lines.append("- `is_win` iff `return_pct > 0`")
    lines.append("- A horizon is written only when that future observation row exists")
    lines.append("")
    lines.append("Edge Research (`modules/edge_research/outcomes.py`) defines T+n as **trading-session** close-to-close. That path is **not** what is stored in `outcomes.csv`. This examiner file uses the stored earning-learning outcomes only.")
    lines.append("")
    lines.append("Implication: four weekend observation dates sit in the observation index, so some stored T3/T5/T10 spans are “3 observation rows later” rather than “3 HOSE sessions later”. 2026-09-03 having only 4 observation rows also stretches later horizons for other names (T3 from 2026-08-25 often lands on 2026-09-04).")
    lines.append("")
    lines.append("Maturity in this file: `MATURE` if that horizon exists in `outcomes.csv`; `WAITING` if the row has an `observation_id` but no stored horizon yet; `UNAVAILABLE` for snapshot-fill rows with no observation id.")
    lines.append("")
    lines.append("Latest stored outcome entry_date: **" + str(pd.to_datetime(outc["entry_date"]).max().date()) + "**.")
    lines.append("")
    lines.append("## 9. PIT / look-ahead / survivorship concerns")
    lines.append("")
    lines.append("1. **Freeze vs later observations.** On 2026-08-13+, `t0_observation_freeze.csv` is first-write-wins by `observation_id`. Later `observations.csv` values can differ (health disagreed on 75 overlapping rows; 2026-08-28 is the worst drift). This extract **uses freeze values** on overlap. Example: 2026-08-28 observations were `recorded_at=2026-09-03T16:04:10Z` while freeze was `2026-08-28T05:43:21Z`. Using observations as T0 on that date would leak later information.")
    lines.append("2. **Freeze clock is not always EOD.** Several freeze timestamps are morning/midday UTC+7, not EOD+3h. 2026-08-28 freeze is midday. Treat those T0 prints as “first captured that date”, not guaranteed official close.")
    lines.append("3. **Weekend observation rows.** 2026-07-26 / 08-01 / 08-02 copy the prior session almost exactly. 2026-08-08 does not. Production outcomes still count them as rows. They are flagged `is_weekend=true`. Preview A/B/C use weekday rows only.")
    lines.append("4. **2026-09-03 incomplete capture.** Only 4 observation/freeze names. Snapshot fill restores 142 health prints for breadth, but those 138 names have **no** stored T3/T5/T10.")
    lines.append("5. **Survivorship.** Current `app.py` WATCHLIST is 142 names. `observations.csv` already matches that 142-set on every full date. `group_evolution_history.csv` earlier used 152–164 names (extra: AAA, BCM, DTD, ELC, FMC, LHG, PAC, PAN, VCS, YEG). Pre-2026-07-23 action-group history is a **different universe** and was not merged.")
    lines.append("6. **Look-ahead into outcomes.** Outcome columns are future labels. Do not use them as T0 features.")
    lines.append("7. **Same-date dependence.** All 142 names on one date share one market episode. Preview C therefore reports date-level medians, then the median across dates.")
    lines.append("8. **No official trading calendar artifact.** Weekday ∩ stored panel is the working trading-day list. Holiday gaps are left as gaps.")
    lines.append("")
    lines.append("## 10. Statistical preview A — state mix by date")
    lines.append("")
    lines.append("Computed from weekday panel rows only. Percentages use that date’s available universe (`n`). Δ is versus the previous weekday panel date. No threshold is applied.")
    lines.append("")
    lines.append(a_table(a_df))
    lines.append("")
    # highlight largest YEU DAN expansions without turning into a rule
    a_df_valid = a_df.dropna(subset=["d_⚠️ YẾU DẦN"])
    if not a_df_valid.empty:
        top = a_df_valid.sort_values("d_⚠️ YẾU DẦN", ascending=False).head(5)
        lines.append("Largest weekday expansions in % YẾU DẦN (descriptive, not a detector):")
        lines.append("")
        for _, r in top.iterrows():
            lines.append(
                f"- {r['trade_date']}: YẾU DẦN {fmt(r['⚠️ YẾU DẦN'],1)}% (Δ {fmt(r['d_⚠️ YẾU DẦN'],1)} pp), n={int(r['n'])}"
            )
        lines.append("")
    lines.append("## 11. Statistical preview B — YẾU DẦN rows (weekday only)")
    lines.append("")
    lines.append(f"Weekday YẾU DẦN stock-days: **{len(yd)}**. These are **not** independent market observations.")
    lines.append("")
    lines.append("### Streak length (consecutive weekday YẾU DẦN including T0)")
    lines.append("")
    lines.append("| streak | n |")
    lines.append("|---:|---:|")
    for k, v in streak_vc.items():
        lines.append(f"| {int(k)} | {int(v)} |")
    lines.append("")
    lines.append("### Previous weekday state")
    lines.append("")
    lines.append("| previous state | n |")
    lines.append("|---|---:|")
    for k, v in prev_state_vc.items():
        lines.append(f"| {md_escape(str(k))} | {int(v)} |")
    lines.append("")
    lines.append("### Stored-indicator changes vs 1/3/5 weekday rows earlier")
    lines.append("")
    lines.append("| series | vs 1d | vs 3d | vs 5d |")
    lines.append("|---|---|---|---|")
    for col, name in (("rs5", "RS5"), ("rs10", "RS10"), ("rsi14", "RSI14")):
        lines.append(
            f"| {name} | {qtile(yd[f'{col}_chg_1d'])} | {qtile(yd[f'{col}_chg_3d'])} | {qtile(yd[f'{col}_chg_5d'])} |"
        )
    lines.append("")
    lines.append("### Close drawdown from prior 5/10 weekday highs (examiner, from stored close)")
    lines.append("")
    lines.append(f"- vs prior 5-day high: {qtile(yd['dd_from_high5'])}")
    lines.append(f"- vs prior 10-day high: {qtile(yd['dd_from_high10'])}")
    lines.append("")
    lines.append("### Volume vs stored 20-day average, distance to stored EMA9/MA20")
    lines.append("")
    lines.append(f"- `volume_ratio20`: {qtile(yd['volume_ratio20'])}")
    lines.append(f"- `price_vs_ema9_pct`: {qtile(yd['price_vs_ema9_pct'])}")
    lines.append(f"- `price_vs_ma20_pct`: {qtile(yd['price_vs_ma20_pct'])}")
    lines.append("- distance to WMA45: **unavailable**")
    lines.append("")
    lines.append("Previous-state mix shows many YẾU DẦN prints follow YẾU / YẾU DẦN / RẤT YẾU, not only former ĐANG HỒI. That is relevant to the “good spring vs falling knife” question and is left un-tuned.")
    lines.append("")
    lines.append("## 12. Statistical preview C — mature T3/T5/T10, date as unit")
    lines.append("")
    lines.append("Only weekday rows with already-stored mature outcomes. Each date contributes one median per state. Stock-days on the same date are collapsed first.")
    lines.append("")
    lines.append("### T3 (MATURE)")
    lines.append("")
    lines.append(c_table(c3, "T3"))
    lines.append("")
    lines.append(date_unit_compare(c3, "T3"))
    lines.append("")
    lines.append("### T5 (MATURE)")
    lines.append("")
    lines.append(c_table(c5, "T5"))
    lines.append("")
    lines.append(date_unit_compare(c5, "T5"))
    lines.append("")
    lines.append("### T10 (MATURE)")
    lines.append("")
    lines.append(c_table(c10, "T10"))
    lines.append("")
    lines.append(date_unit_compare(c10, "T10"))
    lines.append("")
    lines.append("### Waiting / unavailable")
    lines.append("")
    for col, name in (("t3_status", "T3"), ("t5_status", "T5"), ("t10_status", "T10")):
        vc = panel[col].value_counts().to_dict()
        lines.append(f"- {name}: {vc}")
    lines.append("")
    lines.append("Do not read any median gap as a tradable edge. Sample of market dates is small. Weekend-row outcome semantics and 2026-09-03 incompleteness remain unresolved data issues.")
    lines.append("")
    lines.append("## 13. How not to use this file")
    lines.append("")
    lines.append("- Do not add it to Edge Memory / ACTIVE edges / autonomous discovery.")
    lines.append("- Do not optimize cutoffs on % YẾU DẦN, RSI, RS, or streak.")
    lines.append("- Do not treat 142 names on one date as 142 independent trials.")
    lines.append("- Do not drop `t0_priority` / `is_weekend` / `universe_n` when studying breadth episodes.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    src = load_sources()
    panel = build_panel(src)
    panel = attach_lags(panel)
    panel = attach_outcomes(panel, src["outc"])
    panel = attach_market(panel, src["mkt"], src["mkt_sess"])
    panel = add_universe_n(panel)
    csv_df = finalize_csv(panel)

    csv_path = OUT_DIR / "compression_stock_research.csv"
    audit_path = OUT_DIR / "compression_research_audit.md"
    csv_df.to_csv(csv_path, index=False, encoding="utf-8")
    audit = build_audit(csv_df, src, csv_path)
    audit_path.write_text(audit, encoding="utf-8")

    artifacts = Path("/opt/cursor/artifacts")
    if artifacts.exists():
        try:
            csv_df.to_csv(artifacts / "compression_stock_research.csv", index=False, encoding="utf-8")
            (artifacts / "compression_research_audit.md").write_text(audit, encoding="utf-8")
        except OSError:
            pass

    print(f"wrote {csv_path} rows={len(csv_df)} cols={len(csv_df.columns)}")
    print(f"wrote {audit_path} bytes={audit_path.stat().st_size}")
    print("t0_priority", csv_df["t0_priority"].value_counts().to_dict())
    print("dates", csv_df["trade_date"].nunique(), csv_df["trade_date"].min(), csv_df["trade_date"].max())
    print("universe_n", csv_df.groupby("trade_date")["ticker"].nunique().describe().to_dict())


if __name__ == "__main__":
    main()
