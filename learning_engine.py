# =========================================================
# MR.BOT V21 - EXPERIENCE LEARNING ENGINE
# File: learning_engine.py
# Nhiệm vụ:
#   - Đọc Market Snapshot / Evolution / Buy Elite history
#   - Tạo bài học kinh nghiệm theo điều kiện thị trường
#   - Lưu vào Brain để Thinking Engine dùng sau này
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

MARKET_SNAPSHOT_TABLE = "market_snapshot"
EVOLUTION_TABLE = "group_evolution_history"
BUY_ELITE_TABLE = "buy_elite_learning_history"
LEARNING_TABLE = "bot_experience_learning"


def le_now():
    return datetime.now(VN_TZ)


def le_today_str():
    return le_now().strftime("%Y-%m-%d")


def safe_num(x, default=np.nan):
    try:
        v = pd.to_numeric(x, errors="coerce")
        if isinstance(v, pd.Series):
            return v
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def safe_mean(series):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return np.nan
        return round(float(s.mean()), 3)
    except Exception:
        return np.nan


def safe_rate(series):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return np.nan
        return round(float(s.mean()) * 100, 2)
    except Exception:
        return np.nan


def bucket_market(score):
    try:
        score = float(score)
    except Exception:
        return "UNKNOWN"

    if score >= 8:
        return "MARKET_STRONG"
    if score >= 6:
        return "MARKET_NEUTRAL"
    if score >= 4:
        return "MARKET_WEAK"
    return "MARKET_DANGER"


def bucket_forecast(score):
    try:
        score = float(score)
    except Exception:
        return "UNKNOWN"

    if score >= 8:
        return "FORECAST_STRONG"
    if score >= 6:
        return "FORECAST_OK"
    if score >= 4:
        return "FORECAST_WEAK"
    return "FORECAST_RISK"


def bucket_pull_count(n):
    try:
        n = int(n)
    except Exception:
        return "PULL_UNKNOWN"

    if n >= 12:
        return "PULL_MANY"
    if n >= 6:
        return "PULL_MEDIUM"
    if n >= 1:
        return "PULL_FEW"
    return "PULL_NONE"


def bucket_early_count(n):
    try:
        n = int(n)
    except Exception:
        return "EARLY_UNKNOWN"

    if n >= 10:
        return "EARLY_MANY"
    if n >= 5:
        return "EARLY_MEDIUM"
    if n >= 1:
        return "EARLY_FEW"
    return "EARLY_NONE"


def make_market_condition(row):
    market_real = row.get("market_real", np.nan)
    forecast = row.get("market_forecast", np.nan)
    pull_dep = row.get("pull_dep", 0)
    pull_vua = row.get("pull_vua", 0)
    early = row.get("mua_early", 0)

    pull_total = safe_num(pull_dep, 0) + safe_num(pull_vua, 0)

    return "|".join([
        bucket_market(market_real),
        bucket_forecast(forecast),
        bucket_pull_count(pull_total),
        bucket_early_count(early),
    ])


def load_learning_sources(brain):
    market_snapshot = brain.recall(MARKET_SNAPSHOT_TABLE)
    evolution = brain.recall(EVOLUTION_TABLE)
    buy_elite = brain.recall(BUY_ELITE_TABLE)

    if market_snapshot is None:
        market_snapshot = pd.DataFrame()
    if evolution is None:
        evolution = pd.DataFrame()
    if buy_elite is None:
        buy_elite = pd.DataFrame()

    return market_snapshot, evolution, buy_elite


def prepare_market_snapshot(df):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "date" not in out.columns:
        return pd.DataFrame()

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    for c in [
        "market_real", "market_live", "market_forecast",
        "pull_dep", "pull_vua", "mua_early",
        "cp_manh", "ga_tang_toc",
        "obv_green_pct", "slope_positive_pct", "rsi_above_50_pct",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    out["condition_key"] = out.apply(make_market_condition, axis=1)

    return out


def prepare_buy_elite(df):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    date_col = None
    for c in ["date", "created_at", "signal_date"]:
        if c in out.columns:
            date_col = c
            break

    if date_col is None:
        return pd.DataFrame()

    out["date"] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    for c in ["t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out


def prepare_evolution(df):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "date" not in out.columns:
        return pd.DataFrame()

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    for c in ["rank", "score", "price", "volume", "vol_ma20"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out


def summarize_buy_result_by_date(buy_df):
    if buy_df is None or buy_df.empty:
        return pd.DataFrame()

    rows = []

    for d, sub in buy_df.groupby("date"):
        row = {
            "date": d,
            "signals": len(sub),
            "t1_return_avg": safe_mean(sub["t1_return"]) if "t1_return" in sub.columns else np.nan,
            "t3_return_avg": safe_mean(sub["t3_return"]) if "t3_return" in sub.columns else np.nan,
            "t5_return_avg": safe_mean(sub["t5_return"]) if "t5_return" in sub.columns else np.nan,
            "t1_winrate": safe_rate(sub["t1_win"]) if "t1_win" in sub.columns else np.nan,
            "t3_winrate": safe_rate(sub["t3_win"]) if "t3_win" in sub.columns else np.nan,
            "t5_winrate": safe_rate(sub["t5_win"]) if "t5_win" in sub.columns else np.nan,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def summarize_evolution_by_date(evo_df):
    if evo_df is None or evo_df.empty:
        return pd.DataFrame()

    rows = []

    for d, sub in evo_df.groupby("date"):
        row = {
            "date": d,
            "evo_symbols": len(sub),
            "avg_rank": safe_mean(sub["rank"]) if "rank" in sub.columns else np.nan,
            "avg_score": safe_mean(sub["score"]) if "score" in sub.columns else np.nan,
        }

        if "group" in sub.columns:
            row["evo_pull_dep"] = int((sub["group"].astype(str) == "PULL ĐẸP").sum())
            row["evo_pull_vua"] = int((sub["group"].astype(str) == "PULL VỪA").sum())
            row["evo_early"] = int((sub["group"].astype(str) == "MUA EARLY").sum())
            row["evo_strong"] = int((sub["group"].astype(str) == "CP MẠNH").sum())
            row["evo_accel"] = int((sub["group"].astype(str) == "GÀ TĂNG TỐC").sum())

        rows.append(row)

    return pd.DataFrame(rows)


def build_learning_dataset(brain):
    market_df, evo_df, buy_df = load_learning_sources(brain)

    market_df = prepare_market_snapshot(market_df)
    evo_df = prepare_evolution(evo_df)
    buy_df = prepare_buy_elite(buy_df)

    if market_df.empty:
        return pd.DataFrame()

    buy_daily = summarize_buy_result_by_date(buy_df)
    evo_daily = summarize_evolution_by_date(evo_df)

    data = market_df.copy()

    if not buy_daily.empty:
        data = data.merge(buy_daily, on="date", how="left")

    if not evo_daily.empty:
        data = data.merge(evo_daily, on="date", how="left")

    return data


def classify_lesson(row):
    forecast = safe_num(row.get("market_forecast", np.nan))
    real = safe_num(row.get("market_real", np.nan))
    t5 = safe_num(row.get("t5_return_avg", np.nan))
    wr5 = safe_num(row.get("t5_winrate", np.nan))
    pull_total = safe_num(row.get("pull_dep", 0), 0) + safe_num(row.get("pull_vua", 0), 0)

    if pd.notna(t5) and t5 > 3 and pd.notna(wr5) and wr5 >= 65:
        return "GOOD_ENV"

    if pd.notna(t5) and t5 < -2:
        return "BAD_ENV"

    if forecast >= 6 and real < 6:
        return "FORECAST_AHEAD_REAL"

    if real >= 6 and pull_total >= 6:
        return "BUYABLE_PULL_ENV"

    return "NEUTRAL_ENV"


def build_lesson_text(row):
    condition = row.get("condition_key", "")
    lesson_type = row.get("lesson_type", "")

    real = row.get("market_real", np.nan)
    forecast = row.get("market_forecast", np.nan)
    pull_dep = row.get("pull_dep", 0)
    pull_vua = row.get("pull_vua", 0)
    early = row.get("mua_early", 0)
    t5 = row.get("t5_return_avg", np.nan)
    wr5 = row.get("t5_winrate", np.nan)

    if lesson_type == "GOOD_ENV":
        return (
            f"Môi trường tốt: {condition}. "
            f"Market REAL={real}, Forecast={forecast}, Pull đẹp/vừa={pull_dep}/{pull_vua}, Early={early}. "
            f"Kết quả T+5 avg={t5}, winrate={wr5}%. Có thể ưu tiên tăng NAV khi điều kiện lặp lại."
        )

    if lesson_type == "BAD_ENV":
        return (
            f"Môi trường xấu: {condition}. "
            f"Market REAL={real}, Forecast={forecast}, Pull đẹp/vừa={pull_dep}/{pull_vua}, Early={early}. "
            f"Kết quả T+5 avg={t5}. Nên giảm NAV, ưu tiên phòng thủ."
        )

    if lesson_type == "FORECAST_AHEAD_REAL":
        return (
            f"Forecast đi trước Real: {condition}. "
            f"Forecast={forecast} nhưng REAL={real}. Nên quan sát thêm, chưa vội tăng NAV."
        )

    if lesson_type == "BUYABLE_PULL_ENV":
        return (
            f"Môi trường có thể đánh Pull: {condition}. "
            f"REAL={real}, Pull đẹp/vừa={pull_dep}/{pull_vua}. Ưu tiên Pull đẹp/Pull vừa, tránh mua đuổi."
        )

    return (
        f"Môi trường trung tính: {condition}. "
        f"REAL={real}, Forecast={forecast}. Chưa đủ bằng chứng để tăng rủi ro."
    )


def build_experience_lessons(brain):
    data = build_learning_dataset(brain)

    if data.empty:
        return pd.DataFrame()

    rows = []

    for _, r in data.iterrows():
        row = r.to_dict()
        row["learning_date"] = le_today_str()
        row["lesson_type"] = classify_lesson(row)
        row["lesson"] = build_lesson_text(row)

        rows.append(row)

    out = pd.DataFrame(rows)

    keep_cols = [
        "date", "time", "session_slot",
        "learning_date",
        "condition_key", "lesson_type", "lesson",
        "market_real", "market_live", "market_forecast",
        "pull_dep", "pull_vua", "mua_early", "cp_manh", "ga_tang_toc",
        "obv_green_pct", "slope_positive_pct", "rsi_above_50_pct",
        "signals",
        "t1_return_avg", "t3_return_avg", "t5_return_avg",
        "t1_winrate", "t3_winrate", "t5_winrate",
        "evo_symbols", "avg_rank", "avg_score",
        "evo_pull_dep", "evo_pull_vua", "evo_early", "evo_strong", "evo_accel",
    ]

    keep_cols = [c for c in keep_cols if c in out.columns]
    out = out[keep_cols].copy()

    return out


def save_experience_learning(brain, keep_days=360):
    lessons = build_experience_lessons(brain)

    if lessons.empty:
        old = brain.recall(LEARNING_TABLE)
        return old, "NO_LEARNING_DATA", {}

    saved, status = brain.remember(
        table=LEARNING_TABLE,
        data=lessons,
        key=["date", "session_slot", "condition_key"],
        keep_days=keep_days,
        date_col="date",
        sort_by=["date", "session_slot"],
        sync_github=True,
        prefer_github=True,
    )

    summary = summarize_learning(saved)

    return saved, status, summary


def summarize_learning(learning_df):
    if learning_df is None or learning_df.empty:
        return {
            "count": 0,
            "message": "Chưa có dữ liệu học tập.",
        }

    df = learning_df.copy()

    out = {
        "count": len(df),
        "days": df["date"].astype(str).nunique() if "date" in df.columns else 0,
    }

    if "lesson_type" in df.columns:
        out["lesson_type_count"] = df["lesson_type"].value_counts().to_dict()

    if "t5_return_avg" in df.columns:
        out["avg_t5_return"] = safe_mean(df["t5_return_avg"])

    if "t5_winrate" in df.columns:
        out["avg_t5_winrate"] = safe_mean(df["t5_winrate"])

    out["message"] = (
        f"Learning Engine đã ghi {out['count']} bài học / {out['days']} ngày. "
        f"T+5 avg={out.get('avg_t5_return', np.nan)}, "
        f"WinRate={out.get('avg_t5_winrate', np.nan)}%."
    )

    return out


def find_similar_lessons(brain, latest_snapshot=None, top_n=10):
    learning_df = brain.recall(LEARNING_TABLE)

    if learning_df is None or learning_df.empty:
        return pd.DataFrame()

    df = learning_df.copy()

    if latest_snapshot is None or latest_snapshot == {}:
        condition_key = None
    else:
        condition_key = make_market_condition(latest_snapshot)

    if condition_key and "condition_key" in df.columns:
        same = df[df["condition_key"].astype(str) == condition_key].copy()
        if not same.empty:
            return same.tail(top_n)

    if "date" in df.columns:
        return df.sort_values("date").tail(top_n)

    return df.tail(top_n)


def build_learning_view(df):
    if df is None or df.empty:
        return pd.DataFrame()

    show_cols = [
        "date", "session_slot",
        "lesson_type",
        "market_real", "market_forecast",
        "pull_dep", "pull_vua", "mua_early",
        "t5_return_avg", "t5_winrate",
        "lesson",
    ]

    cols = [c for c in show_cols if c in df.columns]
    out = df[cols].copy()

    if "date" in out.columns:
        out = out.sort_values("date", ascending=False)

    return out
