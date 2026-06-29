# =========================================================
# MR.BOT V21 - THINKING ENGINE
# File: thinking_engine.py
# Nhiệm vụ:
#   - Đọc Market Snapshot + Learning
#   - Tìm bài học tương tự
#   - Tự viết kết luận thị trường
#   - Đề xuất NAV / nhóm ưu tiên / nhóm tránh
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

MARKET_SNAPSHOT_TABLE = "market_snapshot"
LEARNING_TABLE = "bot_experience_learning"
THINKING_TABLE = "bot_thinking_journal"


def te_now():
    return datetime.now(VN_TZ)


def te_today_str():
    return te_now().strftime("%Y-%m-%d")


def te_time_str():
    return te_now().strftime("%H:%M:%S")


def safe_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def latest_row(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}

    out = df.copy()

    sort_cols = [c for c in ["date", "time"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)

    return out.tail(1).iloc[0].to_dict()


def get_latest_snapshot(brain) -> dict:
    df = brain.recall(MARKET_SNAPSHOT_TABLE)
    return latest_row(df)


def get_learning_df(brain) -> pd.DataFrame:
    df = brain.recall(LEARNING_TABLE)
    if df is None:
        return pd.DataFrame()
    return df.copy()


def score_similarity(snapshot: dict, lesson: dict) -> float:
    score = 0.0

    fields = [
        ("market_real", 2.5),
        ("market_forecast", 2.5),
        ("pull_dep", 1.5),
        ("pull_vua", 1.2),
        ("mua_early", 1.0),
        ("cp_manh", 1.0),
        ("ga_tang_toc", 1.0),
        ("obv_green_pct", 1.0),
        ("slope_positive_pct", 1.0),
        ("rsi_above_50_pct", 0.8),
    ]

    for col, weight in fields:
        a = safe_float(snapshot.get(col, np.nan))
        b = safe_float(lesson.get(col, np.nan))

        if pd.isna(a) or pd.isna(b):
            continue

        diff = abs(a - b)

        if col in ["market_real", "market_forecast"]:
            part = max(0, 1 - diff / 4)
        elif "pct" in col:
            part = max(0, 1 - diff / 50)
        else:
            part = max(0, 1 - diff / 12)

        score += part * weight

    return round(score, 3)


def find_similar_experiences(brain, snapshot: dict, top_n: int = 8) -> pd.DataFrame:
    learning = get_learning_df(brain)

    if learning.empty or not snapshot:
        return pd.DataFrame()

    rows = []

    for _, r in learning.iterrows():
        item = r.to_dict()
        item["similarity"] = score_similarity(snapshot, item)
        rows.append(item)

    out = pd.DataFrame(rows)

    if out.empty or "similarity" not in out.columns:
        return pd.DataFrame()

    out = out.sort_values("similarity", ascending=False).head(top_n)

    return out


def nav_decision(snapshot: dict, similar_df: pd.DataFrame) -> tuple[str, str]:
    real = safe_float(snapshot.get("market_real", np.nan))
    forecast = safe_float(snapshot.get("market_forecast", np.nan))
    pull_dep = safe_float(snapshot.get("pull_dep", 0), 0)
    pull_vua = safe_float(snapshot.get("pull_vua", 0), 0)
    early = safe_float(snapshot.get("mua_early", 0), 0)

    pull_total = pull_dep + pull_vua

    avg_t5 = np.nan
    avg_wr = np.nan

    if similar_df is not None and not similar_df.empty:
        if "t5_return_avg" in similar_df.columns:
            avg_t5 = pd.to_numeric(similar_df["t5_return_avg"], errors="coerce").mean()
        if "t5_winrate" in similar_df.columns:
            avg_wr = pd.to_numeric(similar_df["t5_winrate"], errors="coerce").mean()

    if pd.notna(real) and real < 4:
        return "0-20% NAV", "Market REAL rất yếu, ưu tiên sống sót."

    if pd.notna(real) and real < 6:
        if pd.notna(forecast) and forecast >= 6 and pull_total >= 5:
            return "20-30% NAV", "Forecast đi trước Real, chỉ test nhỏ nhóm Pull/Early."
        return "0-20% NAV", "REAL < 6, không nên mở rộng vị thế."

    if pd.notna(real) and real >= 6:
        if pd.notna(avg_wr) and avg_wr >= 65 and pd.notna(avg_t5) and avg_t5 > 1.5:
            return "40-60% NAV", "Điều kiện hiện tại giống các giai đoạn thắng cao trong quá khứ."

        if pull_total >= 8:
            return "30-50% NAV", "Có nhiều Pull đẹp/vừa, có thể giải ngân chọn lọc."

        if early >= 8:
            return "25-40% NAV", "Early nhiều, phù hợp test sớm nhưng vẫn cần chia vốn."

        return "25-35% NAV", "Market đủ điều kiện nhưng chưa có xác nhận mạnh."

    return "0-20% NAV", "Dữ liệu chưa đủ rõ để tăng NAV."


def priority_groups(snapshot: dict) -> tuple[list[str], list[str]]:
    real = safe_float(snapshot.get("market_real", np.nan))
    forecast = safe_float(snapshot.get("market_forecast", np.nan))
    pull_dep = safe_float(snapshot.get("pull_dep", 0), 0)
    pull_vua = safe_float(snapshot.get("pull_vua", 0), 0)
    early = safe_float(snapshot.get("mua_early", 0), 0)
    accel = safe_float(snapshot.get("ga_tang_toc", 0), 0)

    ưu_tiên = []
    tránh = []

    if pd.notna(real) and real < 6:
        if pull_dep + pull_vua > 0:
            ưu_tiên.append("PULL ĐẸP / PULL VỪA nhưng chỉ test nhỏ")
        if early > 0:
            ưu_tiên.append("EARLY cạn cung + GREEN2 gần đáy")
        tránh.extend(["BREAKOUT", "GÀ TĂNG TỐC", "mua đuổi xanh mạnh"])
    else:
        if pull_dep >= 3:
            ưu_tiên.append("PULL ĐẸP")
        if pull_vua >= 3:
            ưu_tiên.append("PULL VỪA")
        if early >= 5:
            ưu_tiên.append("MUA EARLY")
        if pd.notna(forecast) and forecast >= 7 and accel >= 3:
            ưu_tiên.append("CP MẠNH / TĂNG TỐC có điểm mua gần EMA9")

        tránh.append("mã xa EMA9 hoặc RSI quá nóng")

    if not ưu_tiên:
        ưu_tiên.append("Quan sát, chưa có nhóm mua rõ")

    return ưu_tiên, tránh


def market_mood(snapshot: dict) -> str:
    real = safe_float(snapshot.get("market_real", np.nan))
    forecast = safe_float(snapshot.get("market_forecast", np.nan))

    if pd.isna(real):
        return "UNKNOWN"

    if real >= 8 and forecast >= 7:
        return "🟢 THỊ TRƯỜNG KHỎE"
    if real >= 6:
        return "🟡 THỊ TRƯỜNG CÓ THỂ ĐÁNH CHỌN LỌC"
    if forecast >= 6 and real < 6:
        return "🟠 FORECAST ĐI TRƯỚC, REAL CHƯA XÁC NHẬN"
    return "🔴 THỊ TRƯỜNG YẾU"


def build_thinking_text(snapshot: dict, similar_df: pd.DataFrame, nav: str, nav_reason: str) -> str:
    mood = market_mood(snapshot)

    real = snapshot.get("market_real", "")
    live = snapshot.get("market_live", "")
    forecast = snapshot.get("market_forecast", "")
    pull_dep = snapshot.get("pull_dep", 0)
    pull_vua = snapshot.get("pull_vua", 0)
    early = snapshot.get("mua_early", 0)
    cp_manh = snapshot.get("cp_manh", 0)
    accel = snapshot.get("ga_tang_toc", 0)

    ưu_tiên, tránh = priority_groups(snapshot)

    similar_note = "Chưa có đủ bài học tương tự."
    if similar_df is not None and not similar_df.empty:
        n = len(similar_df)
        avg_t5 = np.nan
        avg_wr = np.nan

        if "t5_return_avg" in similar_df.columns:
            avg_t5 = pd.to_numeric(similar_df["t5_return_avg"], errors="coerce").mean()
        if "t5_winrate" in similar_df.columns:
            avg_wr = pd.to_numeric(similar_df["t5_winrate"], errors="coerce").mean()

        similar_note = (
            f"Tìm thấy {n} kinh nghiệm gần giống. "
            f"T+5 avg≈{round(avg_t5, 2) if pd.notna(avg_t5) else 'NA'}, "
            f"WinRate≈{round(avg_wr, 1) if pd.notna(avg_wr) else 'NA'}%."
        )

    text = (
        f"{mood}\n\n"
        f"REAL={real}, LIVE={live}, FORECAST={forecast}.\n"
        f"Pull đẹp={pull_dep}, Pull vừa={pull_vua}, Early={early}, "
        f"CP mạnh={cp_manh}, Tăng tốc={accel}.\n\n"
        f"{similar_note}\n\n"
        f"Đề xuất NAV: {nav}.\n"
        f"Lý do: {nav_reason}\n\n"
        f"Nhóm ưu tiên: {', '.join(ưu_tiên)}.\n"
        f"Nhóm nên tránh: {', '.join(tránh)}.\n\n"
        f"Kết luận: Market First. Chỉ mua khi có điểm mua gần vùng quản trị rủi ro. "
        f"Không FOMO, không mua vì bảng đẹp nếu thị trường chưa xác nhận."
    )

    return text


def build_thinking_row(brain) -> dict:
    snapshot = get_latest_snapshot(brain)

    if not snapshot:
        return {
            "date": te_today_str(),
            "time": te_time_str(),
            "status": "NO_SNAPSHOT",
            "thinking": "Chưa có Market Snapshot để suy nghĩ.",
        }

    similar = find_similar_experiences(brain, snapshot, top_n=8)
    nav, nav_reason = nav_decision(snapshot, similar)
    ưu_tiên, tránh = priority_groups(snapshot)

    row = {
        "date": te_today_str(),
        "time": te_time_str(),
        "snapshot_date": snapshot.get("date", ""),
        "session_slot": snapshot.get("session_slot", ""),
        "status": "OK",
        "market_mood": market_mood(snapshot),
        "market_real": snapshot.get("market_real", np.nan),
        "market_live": snapshot.get("market_live", np.nan),
        "market_forecast": snapshot.get("market_forecast", np.nan),
        "pull_dep": snapshot.get("pull_dep", np.nan),
        "pull_vua": snapshot.get("pull_vua", np.nan),
        "mua_early": snapshot.get("mua_early", np.nan),
        "cp_manh": snapshot.get("cp_manh", np.nan),
        "ga_tang_toc": snapshot.get("ga_tang_toc", np.nan),
        "similar_count": len(similar) if similar is not None else 0,
        "nav_suggestion": nav,
        "nav_reason": nav_reason,
        "priority_groups": ", ".join(ưu_tiên),
        "avoid_groups": ", ".join(tránh),
        "thinking": build_thinking_text(snapshot, similar, nav, nav_reason),
    }

    return row


def save_thinking_journal(brain, keep_days=360):
    row = build_thinking_row(brain)

    saved, status = brain.remember(
        table=THINKING_TABLE,
        data=row,
        key=["date", "session_slot"],
        keep_days=keep_days,
        date_col="date",
        sort_by=["date", "time"],
        sync_github=True,
        prefer_github=True,
    )

    return saved, status, row


def load_thinking_journal(brain) -> pd.DataFrame:
    df = brain.recall(THINKING_TABLE)
    if df is None:
        return pd.DataFrame()
    return df


def latest_thinking(brain) -> dict:
    df = load_thinking_journal(brain)
    return latest_row(df)


def build_thinking_view(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    show_cols = [
        "date", "time", "session_slot",
        "market_mood",
        "market_real", "market_forecast",
        "nav_suggestion",
        "priority_groups",
        "avoid_groups",
        "thinking",
    ]

    cols = [c for c in show_cols if c in df.columns]
    out = df[cols].copy()

    if "date" in out.columns:
        out = out.sort_values(["date", "time"] if "time" in out.columns else ["date"], ascending=False)

    return out


def thinking_summary(row: dict) -> str:
    if not row:
        return "Chưa có Thinking Journal."

# =========================================================
# CONTROLLER API
# =========================================================

def get_thinking_summary(brain):
    """
    API chuẩn cho Brain Controller.
    Trả về suy nghĩ mới nhất của Bot.
    """
    try:
        row = latest_thinking(brain)

        if not row:
            return {
                "module": "thinking_engine",
                "status": "NO_DATA",
                "message": "Chưa có Thinking Journal.",
            }

        return {
            "module": "thinking_engine",
            "status": row.get("status", "UNKNOWN"),
            "market_mood": row.get("market_mood", ""),
            "nav_suggestion": row.get("nav_suggestion", ""),
            "nav_reason": row.get("nav_reason", ""),
            "priority_groups": row.get("priority_groups", ""),
            "avoid_groups": row.get("avoid_groups", ""),
            "similar_count": row.get("similar_count", 0),
            "thinking": row.get("thinking", ""),
        }

    except Exception as e:
        return {
            "module": "thinking_engine",
            "status": "ERROR",
            "error": str(e),
        }
    

    return row.get("thinking", "Chưa có nội dung suy nghĩ.")
