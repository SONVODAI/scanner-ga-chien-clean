# =========================================================
# MR.BOT V21 - DECISION ENGINE
# File: decision_engine.py
#
# Nhiệm vụ:
#   - Đọc Brain / Learning
#   - Đánh giá môi trường thị trường hiện tại
#   - Sinh quyết định hành động:
#       NAV bao nhiêu?
#       Ưu tiên nhóm nào?
#       Có nên mua không?
#       Rủi ro cao/thấp?
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

DECISION_TABLE = "bot_decision_history"
LEARNING_TABLE = "bot_experience_learning"


def de_now():
    return datetime.now(VN_TZ)


def de_today_str():
    return de_now().strftime("%Y-%m-%d")


def safe_num(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def safe_text(x, default=""):
    try:
        if pd.isna(x):
            return default
        return str(x)
    except Exception:
        return default


def clamp(v, low=0, high=100):
    try:
        v = float(v)
        return max(low, min(high, v))
    except Exception:
        return low


# =========================================================
# MARKET SNAPSHOT
# =========================================================

def get_latest_market_snapshot(brain):
    df = brain.recall("market_snapshot")

    if df is None or df.empty:
        return {}

    if "date" in df.columns:
        out = df.copy()
        out["_date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.sort_values("_date")
        out = out.drop(columns=["_date"])
        return out.tail(1).iloc[0].to_dict()

    return df.tail(1).iloc[0].to_dict()


def make_condition_from_snapshot(row):
    real = safe_num(row.get("market_real"))
    forecast = safe_num(row.get("market_forecast"))
    pull_dep = safe_num(row.get("pull_dep"), 0)
    pull_vua = safe_num(row.get("pull_vua"), 0)
    early = safe_num(row.get("mua_early"), 0)

    pull_total = pull_dep + pull_vua

    if real >= 8:
        market_bucket = "MARKET_STRONG"
    elif real >= 6:
        market_bucket = "MARKET_NEUTRAL"
    elif real >= 4:
        market_bucket = "MARKET_WEAK"
    else:
        market_bucket = "MARKET_DANGER"

    if forecast >= 8:
        forecast_bucket = "FORECAST_STRONG"
    elif forecast >= 6:
        forecast_bucket = "FORECAST_OK"
    elif forecast >= 4:
        forecast_bucket = "FORECAST_WEAK"
    else:
        forecast_bucket = "FORECAST_RISK"

    if pull_total >= 12:
        pull_bucket = "PULL_MANY"
    elif pull_total >= 6:
        pull_bucket = "PULL_MEDIUM"
    elif pull_total >= 1:
        pull_bucket = "PULL_FEW"
    else:
        pull_bucket = "PULL_NONE"

    if early >= 10:
        early_bucket = "EARLY_MANY"
    elif early >= 5:
        early_bucket = "EARLY_MEDIUM"
    elif early >= 1:
        early_bucket = "EARLY_FEW"
    else:
        early_bucket = "EARLY_NONE"

    return "|".join([
        market_bucket,
        forecast_bucket,
        pull_bucket,
        early_bucket,
    ])


# =========================================================
# LEARNING
# =========================================================

def get_similar_learning(brain, snapshot, top_n=20):
    learning = brain.recall(LEARNING_TABLE)

    if learning is None or learning.empty:
        return pd.DataFrame()

    df = learning.copy()

    condition_key = make_condition_from_snapshot(snapshot)

    if "condition_key" in df.columns:
        same = df[df["condition_key"].astype(str) == condition_key].copy()
        if not same.empty:
            return same.tail(top_n)

    if "date" in df.columns:
        return df.sort_values("date").tail(top_n)

    return df.tail(top_n)


def summarize_similar_learning(df):
    if df is None or df.empty:
        return {
            "similar_count": 0,
            "avg_t5_return": np.nan,
            "avg_t5_winrate": np.nan,
            "good_env_count": 0,
            "bad_env_count": 0,
        }

    out = {
        "similar_count": len(df),
        "avg_t5_return": np.nan,
        "avg_t5_winrate": np.nan,
        "good_env_count": 0,
        "bad_env_count": 0,
    }

    if "t5_return_avg" in df.columns:
        s = pd.to_numeric(df["t5_return_avg"], errors="coerce").dropna()
        if not s.empty:
            out["avg_t5_return"] = round(float(s.mean()), 3)

    if "t5_winrate" in df.columns:
        s = pd.to_numeric(df["t5_winrate"], errors="coerce").dropna()
        if not s.empty:
            out["avg_t5_winrate"] = round(float(s.mean()), 2)

    if "lesson_type" in df.columns:
        vc = df["lesson_type"].astype(str).value_counts().to_dict()
        out["good_env_count"] = int(vc.get("GOOD_ENV", 0))
        out["bad_env_count"] = int(vc.get("BAD_ENV", 0))

    return out


# =========================================================
# CORE DECISION
# =========================================================

def score_market(snapshot):
    real = safe_num(snapshot.get("market_real"))
    forecast = safe_num(snapshot.get("market_forecast"))
    live = safe_num(snapshot.get("market_live"))
    pull_dep = safe_num(snapshot.get("pull_dep"), 0)
    pull_vua = safe_num(snapshot.get("pull_vua"), 0)
    early = safe_num(snapshot.get("mua_early"), 0)
    cp_manh = safe_num(snapshot.get("cp_manh"), 0)

    score = 50
    reasons = []

    if real >= 8:
        score += 20
        reasons.append("Market REAL rất mạnh.")
    elif real >= 6:
        score += 12
        reasons.append("Market REAL đủ điều kiện hành động.")
    elif real >= 4:
        score -= 8
        reasons.append("Market REAL còn yếu.")
    else:
        score -= 22
        reasons.append("Market REAL nguy hiểm, ưu tiên phòng thủ.")

    if forecast >= 8:
        score += 15
        reasons.append("Forecast mạnh, thị trường có dấu hiệu mở rộng.")
    elif forecast >= 6:
        score += 8
        reasons.append("Forecast ổn.")
    elif forecast < 4:
        score -= 15
        reasons.append("Forecast yếu, không nên nâng NAV.")

    if pd.notna(forecast) and pd.notna(real) and forecast >= 6 and real < 6:
        score += 4
        reasons.append("Forecast đang đi trước REAL, có thể là giai đoạn sớm nhưng chưa nên vội.")

    pull_total = pull_dep + pull_vua

    if pull_dep >= 5:
        score += 12
        reasons.append("Pull đẹp xuất hiện nhiều, điểm mua thuận lợi.")
    elif pull_total >= 6:
        score += 8
        reasons.append("Pull vừa/đẹp đủ nhiều, có thể chọn lọc mua.")
    elif pull_total <= 1:
        score -= 6
        reasons.append("Ít mã Pull, cơ hội mua an toàn chưa nhiều.")

    if early >= 8:
        score += 8
        reasons.append("Early xuất hiện nhiều, thị trường có mầm hồi phục.")
    elif early >= 3:
        score += 4
        reasons.append("Có một số mã Early đáng theo dõi.")

    if cp_manh >= 10:
        score += 6
        reasons.append("Số lượng cổ phiếu mạnh tốt.")

    return clamp(score), reasons


def score_learning(learning_summary):
    score = 0
    reasons = []

    count = learning_summary.get("similar_count", 0)
    avg_t5 = learning_summary.get("avg_t5_return", np.nan)
    wr5 = learning_summary.get("avg_t5_winrate", np.nan)
    good = learning_summary.get("good_env_count", 0)
    bad = learning_summary.get("bad_env_count", 0)

    if count <= 0:
        reasons.append("Chưa có bài học tương tự trong Brain.")
        return score, reasons

    if pd.notna(avg_t5):
        if avg_t5 >= 3:
            score += 15
            reasons.append(f"Bài học tương tự có T+5 trung bình tốt: {avg_t5}.")
        elif avg_t5 >= 1:
            score += 8
            reasons.append(f"Bài học tương tự có T+5 dương: {avg_t5}.")
        elif avg_t5 <= -2:
            score -= 15
            reasons.append(f"Bài học tương tự từng cho T+5 xấu: {avg_t5}.")
        elif avg_t5 < 0:
            score -= 6
            reasons.append(f"Bài học tương tự hơi âm: {avg_t5}.")

    if pd.notna(wr5):
        if wr5 >= 70:
            score += 15
            reasons.append(f"WinRate T+5 của điều kiện tương tự cao: {wr5}%.")
        elif wr5 >= 60:
            score += 8
            reasons.append(f"WinRate T+5 tương đối ổn: {wr5}%.")
        elif wr5 < 45:
            score -= 12
            reasons.append(f"WinRate T+5 thấp: {wr5}%.")

    if good > bad:
        score += 8
        reasons.append("Số bài học GOOD_ENV nhiều hơn BAD_ENV.")
    elif bad > good:
        score -= 8
        reasons.append("Số bài học BAD_ENV nhiều hơn GOOD_ENV.")

    return score, reasons


def decide_nav(confidence, risk_level):
    if risk_level == "DANGER":
        return 0

    if confidence >= 85:
        return 70

    if confidence >= 75:
        return 60

    if confidence >= 65:
        return 40

    if confidence >= 55:
        return 25

    if confidence >= 45:
        return 10

    return 0


def decide_risk(confidence, snapshot):
    real = safe_num(snapshot.get("market_real"))
    forecast = safe_num(snapshot.get("market_forecast"))

    if real < 4 and forecast < 4:
        return "DANGER"

    if confidence >= 80:
        return "LOW"

    if confidence >= 60:
        return "MEDIUM"

    return "HIGH"


def decide_priority_groups(snapshot):
    real = safe_num(snapshot.get("market_real"))
    forecast = safe_num(snapshot.get("market_forecast"))
    pull_dep = safe_num(snapshot.get("pull_dep"), 0)
    pull_vua = safe_num(snapshot.get("pull_vua"), 0)
    early = safe_num(snapshot.get("mua_early"), 0)

    groups = []

    if real >= 6 and pull_dep > 0:
        groups.append("PULL ĐẸP")

    if real >= 5 and pull_vua > 0:
        groups.append("PULL VỪA")

    if forecast >= 5 and early > 0:
        groups.append("MUA EARLY")

    if real >= 7:
        groups.append("CP MẠNH")

    if not groups:
        groups.append("THEO DÕI")

    return groups


def decide_action(confidence, risk, nav):
    if risk == "DANGER" or nav == 0:
        return "ĐỨNG NGOÀI"

    if confidence >= 80:
        return "CÓ THỂ MUA CHỌN LỌC"

    if confidence >= 65:
        return "MUA NHỎ / CHỜ CUỐI PHIÊN"

    if confidence >= 50:
        return "THEO DÕI, CHƯA VỘI MUA"

    return "PHÒNG THỦ"


def build_decision_text(decision):
    action = decision.get("action")
    confidence = decision.get("confidence")
    nav = decision.get("suggested_nav")
    risk = decision.get("risk_level")
    groups = decision.get("priority_groups", [])

    return (
        f"Decision Engine: {action}. "
        f"Confidence={confidence}/100, Risk={risk}, NAV gợi ý={nav}%. "
        f"Ưu tiên: {', '.join(groups)}."
    )


# =========================================================
# PUBLIC API
# =========================================================

def make_market_decision(brain, latest_snapshot=None, save=True):
    if latest_snapshot is None:
        snapshot = get_latest_market_snapshot(brain)
    else:
        snapshot = latest_snapshot

    if not snapshot:
        decision = {
            "decision_date": de_today_str(),
            "created_at": de_now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": "NO_DATA",
            "confidence": 0,
            "risk_level": "UNKNOWN",
            "suggested_nav": 0,
            "priority_groups": ["THEO DÕI"],
            "condition_key": "",
            "decision_text": "Decision Engine chưa có dữ liệu market_snapshot.",
        }
        return decision

    market_score, market_reasons = score_market(snapshot)

    similar = get_similar_learning(brain, snapshot)
    learning_summary = summarize_similar_learning(similar)
    learning_score, learning_reasons = score_learning(learning_summary)

    confidence = clamp(market_score + learning_score)

    risk = decide_risk(confidence, snapshot)
    nav = decide_nav(confidence, risk)
    priority_groups = decide_priority_groups(snapshot)
    action = decide_action(confidence, risk, nav)

    condition_key = make_condition_from_snapshot(snapshot)

    decision = {
        "decision_date": de_today_str(),
        "created_at": de_now().strftime("%Y-%m-%d %H:%M:%S"),
        "condition_key": condition_key,

        "market_real": snapshot.get("market_real", np.nan),
        "market_live": snapshot.get("market_live", np.nan),
        "market_forecast": snapshot.get("market_forecast", np.nan),

        "pull_dep": snapshot.get("pull_dep", np.nan),
        "pull_vua": snapshot.get("pull_vua", np.nan),
        "mua_early": snapshot.get("mua_early", np.nan),
        "cp_manh": snapshot.get("cp_manh", np.nan),
        "ga_tang_toc": snapshot.get("ga_tang_toc", np.nan),

        "similar_count": learning_summary.get("similar_count", 0),
        "similar_t5_return": learning_summary.get("avg_t5_return", np.nan),
        "similar_t5_winrate": learning_summary.get("avg_t5_winrate", np.nan),

        "confidence": round(float(confidence), 2),
        "risk_level": risk,
        "suggested_nav": nav,
        "priority_groups": priority_groups,
        "action": action,

        "reason": market_reasons + learning_reasons,
    }

    decision["decision_text"] = build_decision_text(decision)

    if save:
        save_decision(brain, decision)

    return decision


def save_decision(brain, decision, keep_days=360):
    row = decision.copy()

    if isinstance(row.get("priority_groups"), list):
        row["priority_groups"] = " | ".join(row["priority_groups"])

    if isinstance(row.get("reason"), list):
        row["reason"] = " | ".join(row["reason"])

    df = pd.DataFrame([row])

    saved, status = brain.remember(
        table=DECISION_TABLE,
        data=df,
        key=["decision_date", "condition_key", "created_at"],
        keep_days=keep_days,
        date_col="decision_date",
        sort_by=["decision_date", "created_at"],
        sync_github=True,
        prefer_github=True,
    )

    return saved, status


def load_decision_history(brain):
    return brain.recall(DECISION_TABLE)


def build_decision_view(decision):
    if not decision:
        return pd.DataFrame()

    row = {
        "Ngày": decision.get("decision_date"),
        "Hành động": decision.get("action"),
        "Confidence": decision.get("confidence"),
        "Risk": decision.get("risk_level"),
        "NAV gợi ý": decision.get("suggested_nav"),
        "Nhóm ưu tiên": " | ".join(decision.get("priority_groups", [])),
        "Lý do": " | ".join(decision.get("reason", [])),
    }

    return pd.DataFrame([row])


def build_decision_history_view(brain, n=20):
    df = load_decision_history(brain)

    if df is None or df.empty:
        return pd.DataFrame()

    show_cols = [
        "decision_date",
        "created_at",
        "action",
        "confidence",
        "risk_level",
        "suggested_nav",
        "priority_groups",
        "similar_t5_return",
        "similar_t5_winrate",
        "decision_text",
    ]

    cols = [c for c in show_cols if c in df.columns]

    return df[cols].tail(n).sort_values(
        cols[0],
        ascending=False
    )


# =========================================================
# QUICK TEST
# =========================================================

if __name__ == "__main__":

    from brainmanager import get_brain

    brain = get_brain()

    decision = make_market_decision(
        brain=brain,
        latest_snapshot=None,
        save=True,
    )

    print(decision["decision_text"])

    for r in decision.get("reason", []):
        print("-", r)
