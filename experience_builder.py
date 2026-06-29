# =========================================================
# MR.BOT V21 - EXPERIENCE BUILDER
# File: experience_builder.py
# Nhiệm vụ:
#   - Đọc bot_experience_learning
#   - Gom các điều kiện giống nhau thành "kinh nghiệm"
#   - Tính số lần xảy ra / WinRate / AvgReturn / độ tin cậy
#   - Lưu thành experience_database để Thinking Engine dùng sau này
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

LEARNING_TABLE = "bot_experience_learning"
EXPERIENCE_TABLE = "experience_database"


def eb_now():
    return datetime.now(VN_TZ)


def eb_today_str():
    return eb_now().strftime("%Y-%m-%d")


def safe_mean(series):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return np.nan
        return round(float(s.mean()), 3)
    except Exception:
        return np.nan


def safe_count(series):
    try:
        return int(pd.Series(series).dropna().shape[0])
    except Exception:
        return 0


def safe_pct_win(series):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return np.nan
        return round(float((s > 0).mean()) * 100, 2)
    except Exception:
        return np.nan


def safe_rate(series):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return np.nan
        return round(float(s.mean()), 2)
    except Exception:
        return np.nan


def confidence_level(n, winrate, avg_return):
    try:
        n = int(n)
    except Exception:
        n = 0

    try:
        winrate = float(winrate)
    except Exception:
        winrate = np.nan

    try:
        avg_return = float(avg_return)
    except Exception:
        avg_return = np.nan

    if n >= 20 and pd.notna(winrate) and winrate >= 65 and pd.notna(avg_return) and avg_return > 1:
        return "🟢 CAO"

    if n >= 10 and pd.notna(winrate) and winrate >= 55:
        return "🟡 TRUNG BÌNH"

    if n >= 5:
        return "🟠 THẤP"

    return "⚪ CHƯA ĐỦ MẪU"


def action_from_experience(winrate, avg_return, confidence):
    try:
        winrate = float(winrate)
    except Exception:
        winrate = np.nan

    try:
        avg_return = float(avg_return)
    except Exception:
        avg_return = np.nan

    if confidence == "🟢 CAO":
        if winrate >= 70 and avg_return >= 2:
            return "CÓ THỂ TĂNG NAV CÓ KIỂM SOÁT"
        return "CÓ THỂ GIAO DỊCH CHỌN LỌC"

    if confidence == "🟡 TRUNG BÌNH":
        if pd.notna(avg_return) and avg_return > 0:
            return "CHỈ TEST / GIẢI NGÂN VỪA"
        return "QUAN SÁT THÊM"

    if confidence == "🟠 THẤP":
        return "CHỈ THAM KHẢO, CHƯA NÊN TĂNG RỦI RO"

    return "CHƯA ĐỦ DỮ LIỆU"


def describe_experience(row):
    condition = row.get("condition_key", "")
    n = row.get("sample_count", 0)
    wr = row.get("t5_winrate_avg", np.nan)
    ret = row.get("t5_return_avg", np.nan)
    conf = row.get("confidence", "")
    action = row.get("suggested_action", "")

    return (
        f"Điều kiện [{condition}] đã xuất hiện {n} lần. "
        f"T+5 WinRate trung bình {wr}%, AvgReturn {ret}. "
        f"Độ tin cậy: {conf}. Hành động gợi ý: {action}."
    )


def prepare_learning_df(df):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "condition_key" not in out.columns:
        return pd.DataFrame()

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"])
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    numeric_cols = [
        "market_real", "market_live", "market_forecast",
        "pull_dep", "pull_vua", "mua_early", "cp_manh", "ga_tang_toc",
        "obv_green_pct", "slope_positive_pct", "rsi_above_50_pct",
        "signals",
        "t1_return_avg", "t3_return_avg", "t5_return_avg",
        "t1_winrate", "t3_winrate", "t5_winrate",
        "evo_symbols", "avg_rank", "avg_score",
        "evo_pull_dep", "evo_pull_vua", "evo_early", "evo_strong", "evo_accel",
    ]

    for c in numeric_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out


def build_experience_database(brain):
    learning = brain.recall(LEARNING_TABLE)
    learning = prepare_learning_df(learning)

    if learning.empty:
        return pd.DataFrame()

    rows = []

    for condition, sub in learning.groupby("condition_key"):
        row = {
            "experience_date": eb_today_str(),
            "condition_key": condition,
            "sample_count": len(sub),

            "first_seen": sub["date"].min() if "date" in sub.columns else "",
            "last_seen": sub["date"].max() if "date" in sub.columns else "",

            "market_real_avg": safe_mean(sub["market_real"]) if "market_real" in sub.columns else np.nan,
            "market_forecast_avg": safe_mean(sub["market_forecast"]) if "market_forecast" in sub.columns else np.nan,

            "pull_dep_avg": safe_mean(sub["pull_dep"]) if "pull_dep" in sub.columns else np.nan,
            "pull_vua_avg": safe_mean(sub["pull_vua"]) if "pull_vua" in sub.columns else np.nan,
            "mua_early_avg": safe_mean(sub["mua_early"]) if "mua_early" in sub.columns else np.nan,
            "cp_manh_avg": safe_mean(sub["cp_manh"]) if "cp_manh" in sub.columns else np.nan,
            "ga_tang_toc_avg": safe_mean(sub["ga_tang_toc"]) if "ga_tang_toc" in sub.columns else np.nan,

            "t1_return_avg": safe_mean(sub["t1_return_avg"]) if "t1_return_avg" in sub.columns else np.nan,
            "t3_return_avg": safe_mean(sub["t3_return_avg"]) if "t3_return_avg" in sub.columns else np.nan,
            "t5_return_avg": safe_mean(sub["t5_return_avg"]) if "t5_return_avg" in sub.columns else np.nan,

            "t1_winrate_avg": safe_mean(sub["t1_winrate"]) if "t1_winrate" in sub.columns else np.nan,
            "t3_winrate_avg": safe_mean(sub["t3_winrate"]) if "t3_winrate" in sub.columns else np.nan,
            "t5_winrate_avg": safe_mean(sub["t5_winrate"]) if "t5_winrate" in sub.columns else np.nan,

            "t1_positive_rate": safe_pct_win(sub["t1_return_avg"]) if "t1_return_avg" in sub.columns else np.nan,
            "t3_positive_rate": safe_pct_win(sub["t3_return_avg"]) if "t3_return_avg" in sub.columns else np.nan,
            "t5_positive_rate": safe_pct_win(sub["t5_return_avg"]) if "t5_return_avg" in sub.columns else np.nan,
        }

        row["confidence"] = confidence_level(
            row["sample_count"],
            row["t5_winrate_avg"],
            row["t5_return_avg"],
        )

        row["suggested_action"] = action_from_experience(
            row["t5_winrate_avg"],
            row["t5_return_avg"],
            row["confidence"],
        )

        row["experience_note"] = describe_experience(row)

        rows.append(row)

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    out = out.sort_values(
        ["confidence", "sample_count", "t5_return_avg"],
        ascending=[True, False, False],
    ).reset_index(drop=True)

    return out


def save_experience_database(brain, keep_days=720):
    exp = build_experience_database(brain)

    if exp.empty:
        old = brain.recall(EXPERIENCE_TABLE)
        return old, "NO_EXPERIENCE_DATA", {}

    saved, status = brain.remember(
        table=EXPERIENCE_TABLE,
        data=exp,
        key=["condition_key"],
        keep_days=keep_days,
        date_col="experience_date",
        sort_by=["confidence", "sample_count"],
        sync_github=True,
        prefer_github=True,
    )

    summary = summarize_experience(saved)

    return saved, status, summary


def summarize_experience(exp_df):
    if exp_df is None or exp_df.empty:
        return {
            "count": 0,
            "message": "Chưa có Experience Database.",
        }

    df = exp_df.copy()

    out = {
        "count": len(df),
        "total_samples": int(pd.to_numeric(df.get("sample_count", 0), errors="coerce").fillna(0).sum()),
    }

    if "confidence" in df.columns:
        out["confidence_count"] = df["confidence"].value_counts().to_dict()

    if "t5_return_avg" in df.columns:
        out["avg_t5_return"] = safe_mean(df["t5_return_avg"])

    if "t5_winrate_avg" in df.columns:
        out["avg_t5_winrate"] = safe_mean(df["t5_winrate_avg"])

    out["message"] = (
        f"Experience Database có {out['count']} mẫu điều kiện, "
        f"tổng {out['total_samples']} lần quan sát. "
        f"T+5 avg={out.get('avg_t5_return', np.nan)}, "
        f"WinRate={out.get('avg_t5_winrate', np.nan)}%."
    )

    return out


def find_experience_by_condition(brain, condition_key: str):
    exp = brain.recall(EXPERIENCE_TABLE)

    if exp is None or exp.empty:
        return {}

    if "condition_key" not in exp.columns:
        return {}

    sub = exp[exp["condition_key"].astype(str) == str(condition_key)]

    if sub.empty:
        return {}

    return sub.tail(1).iloc[0].to_dict()


def build_experience_view(df):
    if df is None or df.empty:
        return pd.DataFrame()

    show_cols = [
        "condition_key",
        "sample_count",
        "confidence",
        "t5_return_avg",
        "t5_winrate_avg",
        "suggested_action",
        "experience_note",
    ]

    cols = [c for c in show_cols if c in df.columns]
    out = df[cols].copy()

    if "sample_count" in out.columns:
        out = out.sort_values("sample_count", ascending=False)

    return out
