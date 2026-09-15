#!/usr/bin/env python3
"""
READ-ONLY Examiner V2: WHEN (date/episode) and WHICH (T0 stock features).

Uses only compression_stock_research_clean_outcomes.csv plus derived
T0/prior-session features. Does not write production artifacts, outcomes,
Edge Memory, discovery, UI, timers, or BOT logic.

No threshold optimization. No trading rule. Date is the independent unit.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
SRC = OUT_DIR / "compression_stock_research_clean_outcomes.csv"

HEALTH = [
    "🌱 ĐANG HỒI",
    "🟡 TRUNG TÍNH",
    "🔴 YẾU",
    "⚠️ YẾU DẦN",
    "⛔ RẤT YẾU",
]
HSHORT = {
    "🌱 ĐANG HỒI": "DANG_HOI",
    "🟡 TRUNG TÍNH": "TRUNG_TINH",
    "🔴 YẾU": "YEU",
    "⚠️ YẾU DẦN": "YEU_DAN",
    "⛔ RẤT YẾU": "RAT_YEU",
}
WEAK = {"🔴 YẾU", "⚠️ YẾU DẦN", "⛔ RẤT YẾU"}
HEALTHY_PRIOR = {"🌱 ĐANG HỒI", "🟡 TRUNG TÍNH"}
BLIND = {"2026-09-04", "2026-09-07", "2026-09-08"}
# Documented floor so TOP10 can exist as at least one name. Not tuned.
MIN_N_FOR_PERCENTILE_LABELS = 10
HORIZONS = (3, 5, 10)
# Weekend-tolerant episode split: a gap longer than a normal weekend.
EPISODE_GAP_DAYS = 4


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def load_eligible() -> pd.DataFrame:
    df = pd.read_csv(SRC, encoding="utf-8")
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df = df.loc[~df["is_weekend"].astype(bool)].copy()
    df = df.sort_values(["ticker", "trade_date"], kind="stable").reset_index(drop=True)
    sessions = sorted(df["trade_date"].unique())
    df.attrs["sessions"] = sessions
    return df


def add_history_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["rs5"] = _num(out["rs5"])
    out["rs10"] = _num(out["rs10"])
    out["rsi14"] = _num(out["rsi14"])
    out["close"] = _num(out["close"])
    out["volume"] = _num(out["volume"])
    out["obv"] = _num(out["obv"])
    out["volume_ratio20"] = _num(out["volume_ratio20"])
    out["dist_ema9"] = _num(out["price_vs_ema9_pct"])
    out["dist_ma20"] = _num(out["price_vs_ma20_pct"])

    def within_date_pct(col: str, name: str) -> None:
        out[name] = out.groupby("trade_date")[col].rank(method="average", pct=True)

    within_date_pct("rs5", "rs5_pct")
    within_date_pct("rs10", "rs10_pct")
    within_date_pct("rsi14", "rsi14_pct")
    out["rs10_minus_rs5_pct"] = out["rs10_pct"] - out["rs5_pct"]

    g = out.groupby("ticker", group_keys=False)

    def streak_len(s: pd.Series) -> pd.Series:
        vals = s.tolist()
        res = []
        for i, v in enumerate(vals):
            k = 1
            j = i - 1
            while j >= 0 and vals[j] == v:
                k += 1
                j -= 1
            res.append(k)
        return pd.Series(res, index=s.index)

    out["state_streak"] = g["health_group"].transform(streak_len)

    for col, prefix in (("rs5", "rs5"), ("rs10", "rs10"), ("rsi14", "rsi14"), ("obv", "obv")):
        for k in (1, 3, 5):
            out[f"{prefix}_chg_{k}"] = out[col] - g[col].shift(k)

    out["vol_vs_prior"] = out["volume"] / g["volume"].shift(1).replace(0, np.nan)
    out["obv_dir_1"] = np.sign(out["obv_chg_1"])

    def rolling_max_prev(s: pd.Series, window: int) -> pd.Series:
        return s.shift(1).rolling(window, min_periods=1).max()

    prev5 = g["close"].transform(lambda s: rolling_max_prev(s, 5))
    prev10 = g["close"].transform(lambda s: rolling_max_prev(s, 10))
    out["dd5"] = np.where(prev5 > 0, (out["close"] / prev5 - 1.0) * 100.0, np.nan)
    out["dd10"] = np.where(prev10 > 0, (out["close"] / prev10 - 1.0) * 100.0, np.nan)

    for k in range(1, 6):
        out[f"state_l{k}"] = g["health_group"].shift(k)

    def n_changes(row) -> float:
        seq = [row.get(f"state_l{k}") for k in range(1, 6)]
        seq = [x for x in seq if isinstance(x, str) and x]
        if len(seq) < 2:
            return np.nan
        return float(sum(a != b for a, b in zip(seq, seq[1:])))

    out["n_state_changes_5"] = out.apply(n_changes, axis=1)

    def count_prior(row, pred) -> float:
        seq = [row.get(f"state_l{k}") for k in range(1, 6)]
        vals = [x for x in seq if isinstance(x, str) and x]
        if not vals:
            return np.nan
        return float(sum(pred(x) for x in vals))

    out["n_prior5_healthy"] = out.apply(lambda r: count_prior(r, lambda x: x in HEALTHY_PRIOR), axis=1)
    out["n_prior5_rat_yeu"] = out.apply(lambda r: count_prior(r, lambda x: x == "⛔ RẤT YẾU"), axis=1)
    out["n_prior5_yeu_dan"] = out.apply(lambda r: count_prior(r, lambda x: x == "⚠️ YẾU DẦN"), axis=1)
    out["prev_was_dang_hoi"] = (out["state_l1"] == "🌱 ĐANG HỒI").astype(float)
    out["prev_was_healthy"] = out["state_l1"].isin(HEALTHY_PRIOR).astype(float)

    for look in (3, 5):
        best_rs5 = g["rs5_pct"].transform(lambda s: s.shift(1).rolling(look, min_periods=1).max())
        best_rs10 = g["rs10_pct"].transform(lambda s: s.shift(1).rolling(look, min_periods=1).max())
        out[f"rs5_rank_drop_{look}"] = best_rs5 - out["rs5_pct"]
        out[f"rs10_rank_drop_{look}"] = best_rs10 - out["rs10_pct"]

    out["traj3"] = (
        out["state_l3"].fillna("?")
        + ">"
        + out["state_l2"].fillna("?")
        + ">"
        + out["state_l1"].fillna("?")
    )
    return out


def add_date_breadth(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sessions = sorted(df["trade_date"].unique())
    for d, g in df.groupby("trade_date", sort=True):
        n = len(g)
        rec = {"trade_date": d, "n_universe": n}
        shares = {}
        for st in HEALTH:
            p = 100.0 * (g["health_group"] == st).mean() if n else np.nan
            rec[f"pct_{HSHORT[st]}"] = p
            shares[st] = p / 100.0 if pd.notna(p) else 0.0
        rec["pct_weak3"] = rec["pct_YEU"] + rec["pct_YEU_DAN"] + rec["pct_RAT_YEU"]
        rec["pct_weak2"] = rec["pct_YEU"] + rec["pct_RAT_YEU"]
        dom = max(HEALTH, key=lambda s: shares[s])
        rec["dominant_state"] = dom
        rec["dominant_share"] = 100.0 * shares[dom]
        rec["hhi"] = sum(v * v for v in shares.values())
        rec["entropy_log2"] = -sum(v * math.log(v, 2) for v in shares.values() if v > 0)
        rec["market_real"] = _num(g["market_real"]).dropna().iloc[0] if g["market_real"].notna().any() else np.nan
        regime = g["market_regime"].dropna().astype(str)
        regime = regime[regime.str.strip().isin(["", "nan"]) == False]
        rec["market_regime"] = regime.iloc[0] if len(regime) else ""
        rec["vnindex_return"] = (
            _num(g["vnindex_daily_return_pct"]).dropna().iloc[0]
            if g["vnindex_daily_return_pct"].notna().any()
            else np.nan
        )
        rows.append(rec)
    br = pd.DataFrame(rows).sort_values("trade_date")
    for lag, suf in ((1, "d1"), (2, "d2"), (3, "d3")):
        for col in [f"pct_{HSHORT[s]}" for s in HEALTH] + ["pct_weak3", "pct_weak2"]:
            br[f"{col}_chg_{suf}"] = br[col] - br[col].shift(lag)
    br["episode_id"] = assign_episodes(br["trade_date"].tolist())
    br["iso_week"] = pd.to_datetime(br["trade_date"]).dt.strftime("%G-W%V")
    return br


def assign_episodes(dates: list[str]) -> list[int]:
    ids = []
    ep = 0
    prev = None
    for d in dates:
        cur = pd.Timestamp(d)
        if prev is None or (cur - prev).days > EPISODE_GAP_DAYS:
            ep += 1
        ids.append(ep)
        prev = cur
    return ids


def add_outcome_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in HORIZONS:
        out[f"mature_T{n}"] = out[f"clean_T{n}_status"] == "MATURE"
        out[f"ret_T{n}"] = _num(out[f"clean_T{n}_return"])
        out.loc[~out[f"mature_T{n}"], f"ret_T{n}"] = np.nan

    out["t5_label_eligible"] = False
    out["T5_TOP10"] = False
    out["T5_TOP20"] = False
    out["T5_BOTTOM20"] = False
    out["n_mature_T5_date"] = out.groupby("trade_date")["mature_T5"].transform("sum")

    for d, g in out.groupby("trade_date", sort=True):
        if d in BLIND:
            continue
        idx = g.index
        m = g["mature_T5"]
        n_m = int(m.sum())
        if n_m < MIN_N_FOR_PERCENTILE_LABELS:
            continue
        ranks = g.loc[m, "ret_T5"].rank(method="first", pct=True)
        out.loc[idx, "t5_label_eligible"] = m
        top10 = ranks >= 0.90
        top20 = ranks >= 0.80
        bot20 = ranks <= 0.20
        out.loc[ranks.index[top10], "T5_TOP10"] = True
        out.loc[ranks.index[top20], "T5_TOP20"] = True
        out.loc[ranks.index[bot20], "T5_BOTTOM20"] = True
    return out


def date_state_stats(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    ret = f"ret_T{horizon}"
    mature = f"mature_T{horizon}"
    rows = []
    for d, g0 in df.groupby("trade_date", sort=True):
        if d in BLIND:
            continue
        g = g0[g0[mature]].copy()
        if g.empty:
            continue
        uni_mean = g[ret].mean()
        uni_med = g[ret].median()
        for st in HEALTH:
            sg = g[g["health_group"] == st]
            n = len(sg)
            rec = {
                "trade_date": d,
                "horizon": horizon,
                "state": st,
                "state_key": HSHORT[st],
                "n": n,
                "mean": sg[ret].mean() if n else np.nan,
                "median": sg[ret].median() if n else np.nan,
                "winrate": float((sg[ret] > 0).mean()) if n else np.nan,
                "universe_mean": uni_mean,
                "universe_median": uni_med,
            }
            if n >= 10:
                q = sg[ret].quantile(0.90)
                rec["top_decile_median"] = sg.loc[sg[ret] >= q, ret].median()
            else:
                rec["top_decile_median"] = np.nan
            rec["beats_uni_mean"] = (
                float(rec["mean"] > uni_mean)
                if n and pd.notna(rec["mean"])
                else np.nan
            )
            rec["beats_uni_median"] = (
                float(rec["median"] > uni_med)
                if n and pd.notna(rec["median"])
                else np.nan
            )
            rows.append(rec)
    return pd.DataFrame(rows)


def summarize_state_across_dates(st: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (h, state), g in st.groupby(["horizon", "state"]):
        g = g[g["n"] > 0]
        rows.append(
            {
                "horizon": h,
                "state": state,
                "state_key": HSHORT[state],
                "n_dates": int(len(g)),
                "median_of_date_means": g["mean"].median(),
                "median_of_date_medians": g["median"].median(),
                "pct_dates_beat_uni_mean": 100.0 * _num(g["beats_uni_mean"]).mean(),
                "pct_dates_beat_uni_median": 100.0 * _num(g["beats_uni_median"]).mean(),
                "median_winrate": g["winrate"].median(),
            }
        )
    return pd.DataFrame(rows)


def quintile_compare(df: pd.DataFrame, feature: str, horizon: int) -> pd.DataFrame:
    ret = f"ret_T{horizon}"
    mature = f"mature_T{horizon}"
    rows = []
    for d, g0 in df.groupby("trade_date", sort=True):
        if d in BLIND:
            continue
        g = g0[g0[mature] & g0[feature].notna()].copy()
        if len(g) < 10:
            continue
        try:
            g["q"] = pd.qcut(g[feature], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        if g["q"].nunique() < 5:
            continue
        low = g[g["q"] == g["q"].min()]
        high = g[g["q"] == g["q"].max()]
        rows.append(
            {
                "trade_date": d,
                "horizon": horizon,
                "feature": feature,
                "n_low": len(low),
                "n_high": len(high),
                "med_low": low[ret].median(),
                "med_high": high[ret].median(),
                "mean_low": low[ret].mean(),
                "mean_high": high[ret].mean(),
                "spread_med": low[ret].median() - high[ret].median(),
            }
        )
    return pd.DataFrame(rows)


def attach_outcome_to_breadth(br: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    out = br.copy()
    for n in HORIZONS:
        ret = f"ret_T{n}"
        mature = f"mature_T{n}"
        for d, g0 in df.groupby("trade_date"):
            if d in BLIND:
                continue
            g = g0[g0[mature]]
            if g.empty:
                continue
            mask = out["trade_date"] == d
            out.loc[mask, f"uni_T{n}_mean"] = g[ret].mean()
            out.loc[mask, f"uni_T{n}_median"] = g[ret].median()
            for st, key in (("⚠️ YẾU DẦN", "yeudan"), ("⛔ RẤT YẾU", "ratyeu")):
                sg = g[g["health_group"] == st]
                out.loc[mask, f"{key}_T{n}_n"] = len(sg)
                out.loc[mask, f"{key}_T{n}_mean"] = sg[ret].mean() if len(sg) else np.nan
                out.loc[mask, f"{key}_T{n}_median"] = sg[ret].median() if len(sg) else np.nan
    out["blind_forward"] = out["trade_date"].isin(BLIND)
    return out


FEATURE_COLS = [
    ("state_streak", "current-state streak"),
    ("n_state_changes_5", "state changes in prior 5 sessions"),
    ("n_prior5_healthy", "prior-5 sessions in ĐANG HỒI/TRUNG TÍNH"),
    ("n_prior5_rat_yeu", "prior-5 sessions in RẤT YẾU"),
    ("n_prior5_yeu_dan", "prior-5 sessions in YẾU DẦN"),
    ("prev_was_dang_hoi", "previous session was ĐANG HỒI"),
    ("prev_was_healthy", "previous session was ĐANG HỒI/TRUNG TÍNH"),
    ("rs5", "RS5"),
    ("rs10", "RS10"),
    ("rs5_chg_1", "RS5 change vs 1 session"),
    ("rs5_chg_3", "RS5 change vs 3 sessions"),
    ("rs5_chg_5", "RS5 change vs 5 sessions"),
    ("rs10_chg_1", "RS10 change vs 1 session"),
    ("rs10_chg_3", "RS10 change vs 3 sessions"),
    ("rs10_chg_5", "RS10 change vs 5 sessions"),
    ("rs5_pct", "within-date RS5 percentile"),
    ("rs10_pct", "within-date RS10 percentile"),
    ("rs10_minus_rs5_pct", "RS10 pct minus RS5 pct"),
    ("rs5_rank_drop_3", "best RS5 pct in prior 3 minus current"),
    ("rs5_rank_drop_5", "best RS5 pct in prior 5 minus current"),
    ("rs10_rank_drop_3", "best RS10 pct in prior 3 minus current"),
    ("rs10_rank_drop_5", "best RS10 pct in prior 5 minus current"),
    ("rsi14", "RSI14"),
    ("rsi14_chg_1", "RSI14 change vs 1 session"),
    ("rsi14_chg_3", "RSI14 change vs 3 sessions"),
    ("rsi14_chg_5", "RSI14 change vs 5 sessions"),
    ("rsi14_pct", "within-date RSI14 percentile"),
    ("dd5", "drawdown vs prior-5 high close"),
    ("dd10", "drawdown vs prior-10 high close"),
    ("dist_ema9", "distance to EMA9 %"),
    ("dist_ma20", "distance to MA20 %"),
    ("volume_ratio20", "volume / MA20"),
    ("vol_vs_prior", "volume vs prior session"),
    ("obv_chg_1", "OBV change vs 1 session"),
    ("obv_chg_3", "OBV change vs 3 sessions"),
    ("obv_chg_5", "OBV change vs 5 sessions"),
    ("obv_dir_1", "OBV direction vs prior session"),
]


def cohort_mask(g: pd.DataFrame, cohort: str) -> pd.Series:
    if cohort == "YEU_DAN":
        return g["health_group"] == "⚠️ YẾU DẦN"
    if cohort == "YEU":
        return g["health_group"] == "🔴 YẾU"
    if cohort == "RAT_YEU":
        return g["health_group"] == "⛔ RẤT YẾU"
    if cohort == "WEAK":
        return g["health_group"].isin(WEAK)
    raise KeyError(cohort)


def feature_date_spreads(
    df: pd.DataFrame,
    cohort: str,
    winner_col: str,
    other_mode: str,
) -> pd.DataFrame:
    """
    other_mode:
      same_state_nonwinner — same date, same cohort, not in winner_col
      bottom20 — same date, same cohort, T5_BOTTOM20
    Date-level e_d = median(feature|winners) - median(feature|others).
    """
    rows = []
    for d, g0 in df.groupby("trade_date", sort=True):
        if d in BLIND:
            continue
        g = g0[g0["t5_label_eligible"]].copy()
        if g.empty:
            continue
        c = g[cohort_mask(g, cohort)]
        if c.empty:
            continue
        win = c[c[winner_col]]
        if other_mode == "bottom20":
            oth = c[c["T5_BOTTOM20"] & ~c[winner_col]]
        else:
            oth = c[~c[winner_col]]
        if len(win) < 1 or len(oth) < 1:
            continue
        for feat, label in FEATURE_COLS:
            wv = _num(win[feat]).dropna()
            ov = _num(oth[feat]).dropna()
            if wv.empty or ov.empty:
                continue
            e = float(wv.median() - ov.median())
            rows.append(
                {
                    "trade_date": d,
                    "cohort": cohort,
                    "winner_label": winner_col,
                    "other_mode": other_mode,
                    "feature": feat,
                    "feature_label": label,
                    "n_win": int(len(wv)),
                    "n_oth": int(len(ov)),
                    "med_win": float(wv.median()),
                    "med_oth": float(ov.median()),
                    "spread": e,
                    "episode_id": int(g0["episode_id"].iloc[0]) if "episode_id" in g0.columns else np.nan,
                    "iso_week": g0["iso_week"].iloc[0] if "iso_week" in g0.columns else "",
                }
            )
    return pd.DataFrame(rows)


def summarize_feature_spreads(sp: pd.DataFrame, br: pd.DataFrame) -> pd.DataFrame:
    if sp.empty:
        return pd.DataFrame()
    date_ep = br.set_index("trade_date")["episode_id"].to_dict()
    date_week = br.set_index("trade_date")["iso_week"].to_dict()
    rows = []
    windows = {
        "W_0813_0820": set(pd.date_range("2026-08-13", "2026-08-20").strftime("%Y-%m-%d")),
        "W_0828_on": {d for d in sp["trade_date"].unique() if d >= "2026-08-28"},
        "W_0907_on": {d for d in sp["trade_date"].unique() if d >= "2026-09-07"},
    }
    for keys, g in sp.groupby(["cohort", "winner_label", "other_mode", "feature"], sort=False):
        cohort, wlab, omode, feat = keys
        med_spread = g["spread"].median()
        direction = "higher_in_winners" if med_spread > 0 else ("lower_in_winners" if med_spread < 0 else "flat")
        agree = int((np.sign(g["spread"]) == np.sign(med_spread)).sum()) if med_spread != 0 else int((g["spread"] == 0).sum())
        l1 = g["spread"].abs().sum()
        # Episode concentration
        ep_mass = {}
        for ep, eg in g.groupby(g["trade_date"].map(date_ep)):
            ep_mass[ep] = float(eg["spread"].abs().sum()) / l1 if l1 else 0.0
        max_ep = max(ep_mass, key=ep_mass.get) if ep_mass else None
        max_ep_share = ep_mass.get(max_ep, 0.0) if max_ep is not None else 0.0
        # Sign flip if remove max-L1 episode
        if max_ep is not None:
            remain = g[g["trade_date"].map(date_ep) != max_ep]
            remain_med = remain["spread"].median() if len(remain) else np.nan
            sign_flip_ep = (
                pd.notna(remain_med)
                and remain_med != 0
                and med_spread != 0
                and np.sign(remain_med) != np.sign(med_spread)
            )
        else:
            remain_med = np.nan
            sign_flip_ep = False
        # Leave mentioned windows out
        win_notes = {}
        for wname, wdates in windows.items():
            remain = g[~g["trade_date"].isin(wdates)]
            if remain.empty:
                win_notes[wname] = "no_remaining_dates"
                continue
            rm = remain["spread"].median()
            flip = med_spread != 0 and rm != 0 and np.sign(rm) != np.sign(med_spread)
            win_notes[wname] = f"remain_med={rm:.4g}; sign_flip={flip}"
        n_eps = int(len(ep_mass))
        if n_eps <= 1:
            flagged = False
            flag_reason = "SINGLE_EPISODE_SAMPLE"
        else:
            flagged = bool(max_ep_share > 0.50 or sign_flip_ep)
            flag_reason = "EPISODE_CONCENTRATED" if flagged else ""
        rows.append(
            {
                "cohort": cohort,
                "winner_label": wlab,
                "other_mode": omode,
                "feature": feat,
                "feature_label": g["feature_label"].iloc[0],
                "n_dates": int(len(g)),
                "median_win_of_date_medians": g["med_win"].median(),
                "median_oth_of_date_medians": g["med_oth"].median(),
                "median_same_date_spread": med_spread,
                "min_same_date_spread": g["spread"].min(),
                "max_same_date_spread": g["spread"].max(),
                "direction": direction,
                "n_dates_agree": agree,
                "pct_dates_agree": 100.0 * agree / len(g) if len(g) else np.nan,
                "max_episode_id": max_ep,
                "max_episode_l1_share": max_ep_share,
                "sign_flip_if_drop_max_episode": sign_flip_ep,
                "median_spread_without_max_episode": remain_med,
                "episode_concentrated": flagged,
                "episode_flag_reason": flag_reason,
                "leaveout_0813_0820": win_notes.get("W_0813_0820", ""),
                "leaveout_0828_on": win_notes.get("W_0828_on", ""),
                "leaveout_0907_on": win_notes.get("W_0907_on", ""),
                "n_win_stockdays": int(g["n_win"].sum()),
                "n_oth_stockdays": int(g["n_oth"].sum()),
            }
        )
    return pd.DataFrame(rows)


def fmt(x, d=2):
    if x is None or (isinstance(x, float) and (pd.isna(x) or np.isinf(x))):
        return "n/a"
    return f"{float(x):.{d}f}"


def build_report(
    sessions: list[str],
    br: pd.DataFrame,
    state_daily: pd.DataFrame,
    state_sum: pd.DataFrame,
    q_sum: dict,
    feat_sum: pd.DataFrame,
    df: pd.DataFrame,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t5_dates = sorted(state_daily.loc[state_daily["horizon"] == 5, "trade_date"].unique())
    t3_dates = sorted(state_daily.loc[state_daily["horizon"] == 3, "trade_date"].unique())
    t10_dates = sorted(state_daily.loc[state_daily["horizon"] == 10, "trade_date"].unique())

    lines = []
    lines.append("# Examiner V2 — WHEN / WHICH (clean trading-session clock)")
    lines.append("")
    lines.append(f"Generated `{now}` UTC. **Human-examiner research only.**")
    lines.append("Not an edge. Not a rule. Not a production candidate list. No BUY/SELL recommendation.")
    lines.append("")
    lines.append("Independent unit: **eligible market date**. Stock-days on the same date share one market episode.")
    lines.append(f"Source: `{SRC.name}`. Production T3/T5/T10 columns were not used for this study.")
    lines.append(f"Eligible sessions in file: {len(sessions)}. Blind forward dates (no outcome inference): `{', '.join(sorted(BLIND))}`.")
    lines.append(f"Percentile labels require ≥{MIN_N_FOR_PERCENTILE_LABELS} same-date mature clean-T5 names (so TOP10 can exist). This floor was not tuned.")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")

    def beat_line(h, key):
        r = state_sum[(state_sum["horizon"] == h) & (state_sum["state_key"] == key)]
        if r.empty:
            return "n/a"
        x = r.iloc[0]
        return (
            f"median-of-date-medians {fmt(x['median_of_date_medians'])}; "
            f"beat same-day universe median on {fmt(x['pct_dates_beat_uni_median'],1)}% of {int(x['n_dates'])} dates"
        )

    lines.append(
        f"- Clean-clock T5 sample: **{len(t5_dates)}** dates (last mature T0 `{t5_dates[-1] if t5_dates else 'n/a'}`). "
        f"T3: {len(t3_dates)} dates. T10: {len(t10_dates)} dates."
    )
    lines.append(f"- YẾU DẦN T5: {beat_line(5, 'YEU_DAN')}.")
    lines.append(f"- RẤT YẾU T5: {beat_line(5, 'RAT_YEU')}.")
    lines.append(f"- ĐANG HỒI T5: {beat_line(5, 'DANG_HOI')}.")

    # Quintile T5 RS5
    def q_line(feat, h=5):
        q = q_sum.get((feat, h))
        if q is None or q.empty:
            return "n/a"
        med = q["spread_med"].median()
        agree = (np.sign(q["spread_med"]) == np.sign(med)).mean() * 100 if med != 0 else np.nan
        return (
            f"median(date median_Q1 − median_Q5)={fmt(med)}; "
            f"same sign on {fmt(agree,1)}% of {len(q)} dates"
        )

    lines.append(f"- Low vs high within-date RS5 quintile (T5): {q_line('rs5')}.")
    lines.append(f"- Low vs high within-date RS10 quintile (T5): {q_line('rs10')}.")
    lines.append(f"- Low vs high within-date RSI14 quintile (T5): {q_line('rsi14')}.")

    prim = feat_sum[
        (feat_sum["cohort"] == "YEU_DAN")
        & (feat_sum["winner_label"] == "T5_TOP20")
        & (feat_sum["other_mode"] == "same_state_nonwinner")
    ]
    if not prim.empty:
        top = prim[prim["direction"] != "flat"].copy()
        top["abs_spread"] = top["median_same_date_spread"].abs()
        top = top.sort_values(["pct_dates_agree", "abs_spread"], ascending=False)
        lines.append(
            "- Among YẾU DẦN names, T5_TOP20 vs other same-date YẾU DẦN — non-flat features with highest date-agreement "
            "(descriptive, not selected as a model):"
        )
        for _, r in top.head(6).iterrows():
            extra = ""
            if r["episode_concentrated"]:
                extra = ", EPISODE_CONCENTRATED"
            elif str(r.get("episode_flag_reason", "")) == "SINGLE_EPISODE_SAMPLE":
                extra = ", single-episode sample"
            lines.append(
                f"  - {r['feature_label']}: {r['direction']}, median date-spread {fmt(r['median_same_date_spread'],3)}, "
                f"agree {fmt(r['pct_dates_agree'],1)}% of {int(r['n_dates'])} dates{extra}"
            )
    lines.append("- Forward 2026-09-04 / 09-07 / 09-08 remain unlabeled. No conclusion is drawn from them.")
    lines.append("")

    lines.append("## Clean-clock revalidation")
    lines.append("")
    lines.append("For each health state and each eligible date with mature clean returns, the date contributes one mean, one median, one win rate. Cross-date summaries are medians of those date values. Stock-days are not pooled as independent trials.")
    lines.append("")
    lines.append("| horizon | state | n_dates | med of date-means | med of date-medians | % dates > uni mean | % dates > uni median | med date winrate |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in state_sum.sort_values(["horizon", "state_key"]).iterrows():
        lines.append(
            f"| T{int(r['horizon'])} | {r['state']} | {int(r['n_dates'])} | "
            f"{fmt(r['median_of_date_means'])} | {fmt(r['median_of_date_medians'])} | "
            f"{fmt(r['pct_dates_beat_uni_mean'],1)} | {fmt(r['pct_dates_beat_uni_median'],1)} | "
            f"{fmt(r['median_winrate'],1)} |"
        )
    lines.append("")
    lines.append("Within-date quintiles (Q1=lowest feature that day, Q5=highest). Spread = date-median return(Q1) − date-median return(Q5). Positive spread means the low quintile had the higher same-day median clean return.")
    lines.append("")
    lines.append("| horizon | feature | n_dates | med(Q1−Q5 date-median) | % dates Q1>Q5 |")
    lines.append("|---|---|---:|---:|---:|")
    for feat in ("rs5", "rs10", "rsi14"):
        for h in HORIZONS:
            q = q_sum.get((feat, h))
            if q is None or q.empty:
                continue
            med = q["spread_med"].median()
            pct = 100.0 * (q["spread_med"] > 0).mean()
            lines.append(f"| T{h} | {feat} | {len(q)} | {fmt(med)} | {fmt(pct,1)} |")
    lines.append("")
    lines.append("T5 by market date (mature clean T5 only; n / median / winrate>0). Full T3/T10 live in `examiner_v2_date_level.csv`.")
    lines.append("")
    t5d = state_daily[state_daily["horizon"] == 5].copy()
    lines.append("| date | ĐH n/med/wr | TT n/med/wr | YẾU n/med/wr | YĐ n/med/wr | RY n/med/wr | uni med |")
    lines.append("|---|---|---|---|---|---|---:|")
    for d in sorted(t5d["trade_date"].unique()):
        g = t5d[t5d["trade_date"] == d]
        cells = []
        uni = np.nan
        for st in HEALTH:
            r = g[g["state"] == st]
            if r.empty or r.iloc[0]["n"] == 0:
                cells.append("—")
            else:
                x = r.iloc[0]
                uni = x["universe_median"]
                cells.append(f"{int(x['n'])}/{fmt(x['median'])}/{fmt(x['winrate'],2)}")
        lines.append(f"| {d} | " + " | ".join(cells) + f" | {fmt(uni)} |")
    lines.append("")
    lines.append("This is a revalidation check only. A higher beat-rate for a weak state on the clean clock does **not** become a rule.")
    lines.append("")

    lines.append("## WHEN findings")
    lines.append("")
    lines.append("Breadth shares and 1/2/3-session changes are in `examiner_v2_date_level.csv`. HHI = Σ p² on the five state fractions (1 = one state has everyone; 0.20 = equal fifths). Entropy = −Σ p log2(p) (max log2(5) ≈ 2.32).")
    lines.append("")
    lines.append("Inspected windows (not used to fit anything): 2026-08-13..08-20, 2026-08-28 onward, 2026-09-07 onward.")
    lines.append("")
    show_dates = [
        d
        for d in br["trade_date"]
        if d <= "2026-08-21" and d >= "2026-08-12" or d >= "2026-08-27"
    ]
    lines.append("| date | %ĐH | %TT | %YẾU | %YĐ | %RY | %weak3 | Δweak3 d1 | HHI | dom | MR | VNIDX | YĐ T5 med | uni T5 med |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|")
    for _, r in br.iterrows():
        if r["trade_date"] not in set(show_dates) and r["trade_date"] not in {
            "2026-07-23",
            "2026-07-31",
            "2026-08-06",
            "2026-08-14",
        }:
            if not (r["trade_date"] >= "2026-08-13"):
                continue
        lines.append(
            "| {d} | {a} | {b} | {c} | {yd} | {ry} | {w} | {dw} | {h} | {dom} | {mr} | {vx} | {y5} | {u5} |".format(
                d=r["trade_date"],
                a=fmt(r["pct_DANG_HOI"], 1),
                b=fmt(r["pct_TRUNG_TINH"], 1),
                c=fmt(r["pct_YEU"], 1),
                yd=fmt(r["pct_YEU_DAN"], 1),
                ry=fmt(r["pct_RAT_YEU"], 1),
                w=fmt(r["pct_weak3"], 1),
                dw=fmt(r.get("pct_weak3_chg_d1"), 1),
                h=fmt(r["hhi"], 2),
                dom=HSHORT.get(r["dominant_state"], ""),
                mr=fmt(r["market_real"], 1),
                vx=fmt(r["vnindex_return"], 2),
                y5=fmt(r.get("yeudan_T5_median"), 2),
                u5=fmt(r.get("uni_T5_median"), 2),
            )
        )
    lines.append("")
    lines.append("`market_transition` is unavailable and was not invented. 2026-09-04/07/08 outcome cells are blank by design.")
    lines.append("")

    lines.append("## WHICH findings")
    lines.append("")
    lines.append("Labels are **same-date percentiles of clean_T5_return** among mature names that day: T5_TOP20 / T5_TOP10 / T5_BOTTOM20. No absolute return cutoff.")
    lines.append("Primary comparison: YẾU DẦN ∩ T5_TOP20 vs other YẾU DẦN on the **same date**. Robustness: YẾU, RẤT YẾU, combined weak, and vs T5_BOTTOM20.")
    lines.append("Each date contributes one median(feature|winners) and one median(feature|others). The table below is the median of those date-level values, plus how often the date-level spread has the same sign as the overall median spread.")
    lines.append("")

    def dump_feat(cohort, wlab, omode, title):
        sub = feat_sum[
            (feat_sum["cohort"] == cohort)
            & (feat_sum["winner_label"] == wlab)
            & (feat_sum["other_mode"] == omode)
        ]
        lines.append(f"### {title}")
        lines.append("")
        if sub.empty:
            lines.append("_No comparable dates (need ≥1 winner and ≥1 other in-cohort that day)._")
            lines.append("")
            return
        sub = sub.sort_values(["pct_dates_agree", "n_dates"], ascending=False)
        lines.append("| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |")
        lines.append("|---|---:|---:|---:|---:|---|---:|---|")
        for _, r in sub.iterrows():
            flag = (
                "EPISODE_CONCENTRATED"
                if r["episode_concentrated"]
                else str(r.get("episode_flag_reason", "") or "")
            )
            lines.append(
                f"| {r['feature_label']} | {int(r['n_dates'])} | {fmt(r['median_same_date_spread'],3)} | "
                f"{fmt(r['min_same_date_spread'],3)} | {fmt(r['max_same_date_spread'],3)} | "
                f"{r['direction']} | {fmt(r['pct_dates_agree'],1)} | {flag} |"
            )
        lines.append("")

    dump_feat("YEU_DAN", "T5_TOP20", "same_state_nonwinner", "YẾU DẦN · T5_TOP20 vs other same-date YẾU DẦN")
    dump_feat("YEU_DAN", "T5_TOP10", "same_state_nonwinner", "YẾU DẦN · T5_TOP10 vs other same-date YẾU DẦN")
    dump_feat("YEU_DAN", "T5_TOP20", "bottom20", "YẾU DẦN · T5_TOP20 vs T5_BOTTOM20")
    dump_feat("YEU", "T5_TOP20", "same_state_nonwinner", "Robustness · YẾU · T5_TOP20 vs other YẾU")
    dump_feat("RAT_YEU", "T5_TOP20", "same_state_nonwinner", "Robustness · RẤT YẾU · T5_TOP20 vs other RẤT YẾU")
    dump_feat("WEAK", "T5_TOP20", "same_state_nonwinner", "Robustness · combined weak · T5_TOP20 vs other weak")

    lines.append("Market Real / regime / breadth percentages are **constant within a date**, so they cannot distinguish winners from others on the same date. They belong to WHEN, not WHICH.")
    lines.append("")

    lines.append("## Temporary compression vs structural weakness")
    lines.append("")
    lines.append("Descriptive contrast only. No composite score was built.")
    lines.append("If “short-term compressed on a healthier base” were visible at T0, YẾU DẦN T5_TOP20 names would tend to show, versus other same-date YẾU DẦN:")
    lines.append("")
    lines.append("- lower current RS5 rank than RS10 rank (positive `rs10_minus_rs5_pct`)")
    lines.append("- a drop from a better RS rank in the prior 3/5 sessions (`rs5_rank_drop_*` > 0)")
    lines.append("- shorter current-state streak / more prior healthy states")
    lines.append("- shallower 10-session drawdown than chronic weakness")
    lines.append("")
    keys = [
        "rs5_pct",
        "rs10_pct",
        "rs10_minus_rs5_pct",
        "rs5_rank_drop_3",
        "rs5_rank_drop_5",
        "rs10_rank_drop_3",
        "rs10_rank_drop_5",
        "state_streak",
        "n_prior5_healthy",
        "n_prior5_rat_yeu",
        "dd5",
        "dd10",
        "dist_ema9",
        "dist_ma20",
        "volume_ratio20",
        "obv_dir_1",
    ]
    sub = prim[prim["feature"].isin(keys)] if not prim.empty else pd.DataFrame()
    if sub.empty:
        lines.append("_Insufficient YẾU DẦN date-level winner/other pairs._")
    else:
        lines.append("| test piece | direction | med spread | % dates agree | n_dates | concentrated? |")
        lines.append("|---|---|---:|---:|---:|---|")
        for feat in keys:
            r = sub[sub["feature"] == feat]
            if r.empty:
                continue
            x = r.iloc[0]
            lines.append(
                f"| {x['feature_label']} | {x['direction']} | {fmt(x['median_same_date_spread'],3)} | "
                f"{fmt(x['pct_dates_agree'],1)} | {int(x['n_dates'])} | "
                f"{'YES' if x['episode_concentrated'] else 'no'} |"
            )
    lines.append("")
    lines.append("Agreement across dates is the claim-check. A single large episode can still dominate; see the next section.")
    lines.append("")

    lines.append("## Date-level robustness")
    lines.append("")
    lines.append("Episode definition: a new episode starts when the gap between consecutive eligible sessions exceeds **4 calendar days** (weekend-tolerant; the National Day hole splits 2026-08-28 from 2026-09-03).")
    lines.append("")
    lines.append("Date-level effect `e_d` = median(feature | winners, date d) − median(feature | others, date d).")
    lines.append("Episode L1 share = Σ_d∈ep |e_d| / Σ_all |e_d|.")
    lines.append("EPISODE_CONCENTRATED if max episode L1 share > 50%, **or** dropping that episode flips the sign of median(e_d).")
    lines.append("Leave-one-window-out columns in `examiner_v2_feature_comparison.csv` recompute median(e_d) after removing 2026-08-13..08-20, 2026-08-28 onward, or 2026-09-07 onward. Those windows were listed in the brief; they were not chosen by scanning outcomes.")
    lines.append("")
    if not feat_sum.empty:
        n_flag = int(
            (
                (feat_sum["cohort"] == "YEU_DAN")
                & (feat_sum["winner_label"] == "T5_TOP20")
                & (feat_sum["other_mode"] == "same_state_nonwinner")
                & feat_sum["episode_concentrated"]
            ).sum()
        )
        n_tot = int(
            (
                (feat_sum["cohort"] == "YEU_DAN")
                & (feat_sum["winner_label"] == "T5_TOP20")
                & (feat_sum["other_mode"] == "same_state_nonwinner")
            ).sum()
        )
        lines.append(
            f"YẾU DẦN T5_TOP20 vs others: **{n_flag}/{n_tot}** features flagged EPISODE_CONCENTRATED "
            f"(multi-episode L1/sign test). If only one T5 episode exists, rows are marked SINGLE_EPISODE_SAMPLE instead."
        )
    lines.append(f"Episode ids present on T5-mature dates: {sorted(set(br.loc[br['trade_date'].isin(t5_dates),'episode_id']))}.")
    lines.append("")

    lines.append("## Episode concentration warnings")
    lines.append("")
    lines.append("- Almost all mature clean-T5 dates sit in **one** pre–National Day episode (2026-07-23..2026-08-28). Post-holiday T5 is immature, so leave-one-episode-out is weak.")
    lines.append("- Results that survive only inside 2026-08-13..08-20 should be treated as that window’s description, not a repeated market regularity.")
    lines.append("- 2026-08-26 is a snapshot-fill session (observations missed it). It is in the clean calendar but is a lower-quality T0 print.")
    lines.append("")

    lines.append("## Data limitations / PIT warnings")
    lines.append("")
    lines.append("- T0 features prefer freeze-on-overlap from the parent extract; 2026-08-28 freeze is midday.")
    lines.append("- Clean T+n uses stored panel closes on confirmed sessions only. No missing close was interpolated.")
    lines.append("- No official HOSE gazette file; National Day window is evidence-derived (see Examiner V1 audit §14).")
    lines.append("- RS5/RS10 are own-price changes, not vs VNINDEX.")
    lines.append("- Within-date percentiles use the full eligible universe that day (T0), then labels use mature clean T5 only.")
    lines.append("- Weekend observation rows are excluded from this study’s date unit.")
    lines.append("- `market_transition` does not exist historically.")
    lines.append("- Small N_dates (T10 shorter than T3). Date-agreement can look high by chance.")
    lines.append("")

    lines.append("## BLIND_FORWARD_EPISODES")
    lines.append("")
    lines.append("T0/breadth only. **No outcome interpretation.**")
    lines.append("")
    lines.append("| date | n | %ĐH | %TT | %YẾU | %YĐ | %RY | %weak3 | ΔYĐ d1 | Δweak3 d1 | dom | HHI | MR | regime | VNIDX |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---:|")
    for d in sorted(BLIND):
        r = br[br["trade_date"] == d]
        if r.empty:
            lines.append(f"| {d} | | | | | | | | | | | | | not in panel | |")
            continue
        x = r.iloc[0]
        lines.append(
            "| {d} | {n} | {a} | {b} | {c} | {yd} | {ry} | {w} | {dyd} | {dw} | {dom} | {h} | {mr} | {rg} | {vx} |".format(
                d=d,
                n=int(x["n_universe"]),
                a=fmt(x["pct_DANG_HOI"], 1),
                b=fmt(x["pct_TRUNG_TINH"], 1),
                c=fmt(x["pct_YEU"], 1),
                yd=fmt(x["pct_YEU_DAN"], 1),
                ry=fmt(x["pct_RAT_YEU"], 1),
                w=fmt(x["pct_weak3"], 1),
                dyd=fmt(x.get("pct_YEU_DAN_chg_d1"), 1),
                dw=fmt(x.get("pct_weak3_chg_d1"), 1),
                dom=HSHORT.get(x["dominant_state"], ""),
                h=fmt(x["hhi"], 2),
                mr=fmt(x["market_real"], 1),
                rg=str(x["market_regime"])[:24],
                vx=fmt(x["vnindex_return"], 2),
            )
        )
    lines.append("")
    # T0 feature snapshot for blind dates: state mix already above; add median RS/RSI of YEU DAN
    lines.append("YẾU DẦN T0 location on blind dates (features only):")
    lines.append("")
    lines.append("| date | n YĐ | med RS5 | med RS10 | med RSI14 | med RS5 pct | med dd10 | med vol_ratio20 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for d in sorted(BLIND):
        g = df[(df["trade_date"] == d) & (df["health_group"] == "⚠️ YẾU DẦN")]
        if g.empty:
            continue
        lines.append(
            f"| {d} | {len(g)} | {fmt(g['rs5'].median())} | {fmt(g['rs10'].median())} | "
            f"{fmt(g['rsi14'].median())} | {fmt(g['rs5_pct'].median(),2)} | "
            f"{fmt(g['dd10'].median())} | {fmt(g['volume_ratio20'].median(),2)} |"
        )
    lines.append("")
    lines.append("These rows are context for a later examiner pass after clean T5 matures. They were not used to choose features.")
    lines.append("")

    lines.append("## What remains unknown")
    lines.append("")
    lines.append("- Whether any WHEN pattern repeats outside this single July–August 2026 stretch.")
    lines.append("- Whether 2026-08-26 snapshot T0 is comparable to freeze T0.")
    lines.append("- Whether “good rebound” should be T5, T3, or path T3→T5→T10. This file labels on T5 only.")
    lines.append("- Foreign flow, WMA45, OHLC structure, and official holiday gazette.")
    lines.append("- Causal structure: breadth expansion and single-name rebound can be the same market move.")
    lines.append("- Any out-of-sample period after 2026-09-08.")
    lines.append("")
    lines.append("Do not load these tables into Edge Memory, discovery, or the BOT.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    raw = load_eligible()
    sessions = raw.attrs["sessions"]
    df = add_history_features(raw)
    br = add_date_breadth(df)
    df = df.merge(br[["trade_date", "episode_id", "iso_week"]], on="trade_date", how="left")
    df = add_outcome_labels(df)
    br = attach_outcome_to_breadth(br, df)

    state_daily = pd.concat([date_state_stats(df, h) for h in HORIZONS], ignore_index=True)
    state_sum = summarize_state_across_dates(state_daily)

    q_sum = {}
    q_rows = []
    for feat in ("rs5", "rs10", "rsi14"):
        for h in HORIZONS:
            q = quintile_compare(df, feat, h)
            q_sum[(feat, h)] = q
            if not q.empty:
                q_rows.append(q)
    q_all = pd.concat(q_rows, ignore_index=True) if q_rows else pd.DataFrame()

    spreads = []
    for cohort in ("YEU_DAN", "YEU", "RAT_YEU", "WEAK"):
        for wlab in ("T5_TOP20", "T5_TOP10"):
            spreads.append(feature_date_spreads(df, cohort, wlab, "same_state_nonwinner"))
            spreads.append(feature_date_spreads(df, cohort, wlab, "bottom20"))
    sp = pd.concat([s for s in spreads if not s.empty], ignore_index=True) if spreads else pd.DataFrame()
    feat_sum = summarize_feature_spreads(sp, br)

    date_csv = br.copy()
    for h in HORIZONS:
        sub = state_daily[state_daily["horizon"] == h]
        for _, r in sub.iterrows():
            k = r["state_key"]
            mask = date_csv["trade_date"] == r["trade_date"]
            date_csv.loc[mask, f"{k}_T{h}_n"] = r["n"]
            date_csv.loc[mask, f"{k}_T{h}_mean"] = r["mean"]
            date_csv.loc[mask, f"{k}_T{h}_median"] = r["median"]
            date_csv.loc[mask, f"{k}_T{h}_winrate"] = r["winrate"]
            date_csv.loc[mask, f"{k}_T{h}_beats_uni_median"] = r["beats_uni_median"]
    date_path = OUT_DIR / "examiner_v2_date_level.csv"
    date_csv.to_csv(date_path, index=False, encoding="utf-8")

    stock_cols = [
        "trade_date",
        "ticker",
        "health_group",
        "health_score",
        "action_group",
        "close",
        "state_streak",
        "state_l1",
        "state_l2",
        "state_l3",
        "state_l4",
        "state_l5",
        "n_state_changes_5",
        "n_prior5_healthy",
        "n_prior5_rat_yeu",
        "n_prior5_yeu_dan",
        "prev_was_dang_hoi",
        "prev_was_healthy",
        "traj3",
        "rs5",
        "rs10",
        "rsi14",
        "rs5_chg_1",
        "rs5_chg_3",
        "rs5_chg_5",
        "rs10_chg_1",
        "rs10_chg_3",
        "rs10_chg_5",
        "rsi14_chg_1",
        "rsi14_chg_3",
        "rsi14_chg_5",
        "rs5_pct",
        "rs10_pct",
        "rsi14_pct",
        "rs10_minus_rs5_pct",
        "rs5_rank_drop_3",
        "rs5_rank_drop_5",
        "rs10_rank_drop_3",
        "rs10_rank_drop_5",
        "dd5",
        "dd10",
        "dist_ema9",
        "dist_ma20",
        "volume",
        "volume_ratio20",
        "vol_vs_prior",
        "obv",
        "obv_chg_1",
        "obv_chg_3",
        "obv_chg_5",
        "obv_dir_1",
        "market_real",
        "market_regime",
        "vnindex_daily_return_pct",
        "episode_id",
        "iso_week",
        "mature_T3",
        "mature_T5",
        "mature_T10",
        "ret_T3",
        "ret_T5",
        "ret_T10",
        "t5_label_eligible",
        "n_mature_T5_date",
        "T5_TOP10",
        "T5_TOP20",
        "T5_BOTTOM20",
        "clean_T3_status",
        "clean_T5_status",
        "clean_T10_status",
    ]
    # attach a few breadth cols
    stock = df.merge(
        br[
            [
                "trade_date",
                "pct_DANG_HOI",
                "pct_TRUNG_TINH",
                "pct_YEU",
                "pct_YEU_DAN",
                "pct_RAT_YEU",
                "pct_weak3",
                "pct_YEU_DAN_chg_d1",
                "pct_weak3_chg_d1",
                "hhi",
                "dominant_state",
            ]
        ],
        on="trade_date",
        how="left",
    )
    extra = [
        "pct_DANG_HOI",
        "pct_TRUNG_TINH",
        "pct_YEU",
        "pct_YEU_DAN",
        "pct_RAT_YEU",
        "pct_weak3",
        "pct_YEU_DAN_chg_d1",
        "pct_weak3_chg_d1",
        "hhi",
        "dominant_state",
    ]
    stock_path = OUT_DIR / "examiner_v2_stock_features.csv"
    stock[stock_cols + extra].to_csv(stock_path, index=False, encoding="utf-8")

    feat_path = OUT_DIR / "examiner_v2_feature_comparison.csv"
    feat_sum.to_csv(feat_path, index=False, encoding="utf-8")

    # also write state-daily and quintile as extra? User asked only 4 files.
    # Fold essential daily state stats into date_level already; keep feature_comparison as requested.

    report = build_report(sessions, br, state_daily, state_sum, q_sum, feat_sum, df)
    report_path = OUT_DIR / "examiner_v2_when_which_report.md"
    report_path.write_text(report, encoding="utf-8")

    artifacts = Path("/opt/cursor/artifacts")
    if artifacts.exists():
        try:
            for p in (date_path, stock_path, feat_path, report_path):
                (artifacts / p.name).write_bytes(p.read_bytes())
        except OSError:
            pass

    print("sessions", len(sessions))
    print("T5 dates", state_daily[state_daily.horizon == 5].trade_date.nunique())
    print("wrote", report_path, date_path, stock_path, feat_path)
    print("feat rows", len(feat_sum))
    print(state_sum[state_sum.horizon == 5][["state_key", "n_dates", "median_of_date_medians", "pct_dates_beat_uni_median"]].to_string(index=False))


if __name__ == "__main__":
    main()
