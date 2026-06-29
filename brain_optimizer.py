# =========================================================
# MR.BOT V21 - BRAIN OPTIMIZER
# File: brain_optimizer.py
#
# Nhiệm vụ:
#   - Đọc Brain / Learning / Decision history
#   - Tự đánh giá các quyết định trong quá khứ
#   - Phát hiện điểm mạnh / điểm yếu
#   - Sinh báo cáo tối ưu
#   - Sinh recommendation để Decision Engine có thể đọc sau này
#
# Nguyên tắc:
#   - KHÔNG tự sửa code
#   - KHÔNG tự thay đổi quyết định giao dịch ngay lập tức
#   - Chỉ quan sát, tổng hợp, đề xuất
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import json
import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

DECISION_TABLE = "bot_decision_history"
LEARNING_TABLE = "bot_experience_learning"
OPTIMIZER_REPORT_TABLE = "brain_optimizer_report"
OPTIMIZER_RECOMMENDATION_TABLE = "brain_optimizer_recommendation"


# =========================================================
# TIME
# =========================================================

def bo_now():
    return datetime.now(VN_TZ)


def bo_today_str():
    return bo_now().strftime("%Y-%m-%d")


def bo_time_str():
    return bo_now().strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# SAFE HELPERS
# =========================================================

def safe_num(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
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


def safe_value_counts(series):
    try:
        return series.astype(str).value_counts().to_dict()
    except Exception:
        return {}


def safe_json_dumps(obj):
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def split_text_field(x):
    if x is None:
        return []

    if isinstance(x, list):
        return x

    try:
        if pd.isna(x):
            return []
    except Exception:
        pass

    text = str(x)

    if "|" in text:
        return [i.strip() for i in text.split("|") if i.strip()]

    if "," in text:
        return [i.strip() for i in text.split(",") if i.strip()]

    if text.strip():
        return [text.strip()]

    return []


# =========================================================
# LOAD DATA
# =========================================================

def load_optimizer_sources(brain):
    decision_df = brain.recall(DECISION_TABLE)
    learning_df = brain.recall(LEARNING_TABLE)
    market_df = brain.recall("market_snapshot")

    if decision_df is None:
        decision_df = pd.DataFrame()

    if learning_df is None:
        learning_df = pd.DataFrame()

    if market_df is None:
        market_df = pd.DataFrame()

    return decision_df, learning_df, market_df


def prepare_date(df, date_col):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if date_col not in out.columns:
        return out

    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col])
    out[date_col] = out[date_col].dt.strftime("%Y-%m-%d")

    return out


# =========================================================
# COLLECT STATISTICS
# =========================================================

def collect_decision_statistics(decision_df):
    if decision_df is None or decision_df.empty:
        return {
            "decision_count": 0,
            "message": "Chưa có decision history.",
        }

    df = decision_df.copy()

    for c in [
        "confidence",
        "suggested_nav",
        "market_real",
        "market_live",
        "market_forecast",
        "pull_dep",
        "pull_vua",
        "mua_early",
        "cp_manh",
        "similar_t5_return",
        "similar_t5_winrate",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    stats = {
        "decision_count": len(df),
        "avg_confidence": safe_mean(df["confidence"]) if "confidence" in df.columns else np.nan,
        "avg_nav": safe_mean(df["suggested_nav"]) if "suggested_nav" in df.columns else np.nan,
        "avg_market_real": safe_mean(df["market_real"]) if "market_real" in df.columns else np.nan,
        "avg_market_forecast": safe_mean(df["market_forecast"]) if "market_forecast" in df.columns else np.nan,
        "avg_similar_t5_return": safe_mean(df["similar_t5_return"]) if "similar_t5_return" in df.columns else np.nan,
        "avg_similar_t5_winrate": safe_mean(df["similar_t5_winrate"]) if "similar_t5_winrate" in df.columns else np.nan,
    }

    if "action" in df.columns:
        stats["action_count"] = safe_value_counts(df["action"])

    if "risk_level" in df.columns:
        stats["risk_count"] = safe_value_counts(df["risk_level"])

    if "priority_groups" in df.columns:
        group_counter = {}

        for x in df["priority_groups"]:
            for g in split_text_field(x):
                group_counter[g] = group_counter.get(g, 0) + 1

        stats["priority_group_count"] = group_counter

    return stats


def collect_learning_statistics(learning_df):
    if learning_df is None or learning_df.empty:
        return {
            "learning_count": 0,
            "message": "Chưa có learning history.",
        }

    df = learning_df.copy()

    for c in [
        "market_real",
        "market_forecast",
        "pull_dep",
        "pull_vua",
        "mua_early",
        "t1_return_avg",
        "t3_return_avg",
        "t5_return_avg",
        "t1_winrate",
        "t3_winrate",
        "t5_winrate",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    stats = {
        "learning_count": len(df),
        "avg_t1_return": safe_mean(df["t1_return_avg"]) if "t1_return_avg" in df.columns else np.nan,
        "avg_t3_return": safe_mean(df["t3_return_avg"]) if "t3_return_avg" in df.columns else np.nan,
        "avg_t5_return": safe_mean(df["t5_return_avg"]) if "t5_return_avg" in df.columns else np.nan,
        "avg_t5_winrate": safe_mean(df["t5_winrate"]) if "t5_winrate" in df.columns else np.nan,
        "avg_market_real": safe_mean(df["market_real"]) if "market_real" in df.columns else np.nan,
        "avg_market_forecast": safe_mean(df["market_forecast"]) if "market_forecast" in df.columns else np.nan,
    }

    if "lesson_type" in df.columns:
        stats["lesson_type_count"] = safe_value_counts(df["lesson_type"])

    return stats


def collect_market_statistics(market_df):
    if market_df is None or market_df.empty:
        return {
            "market_snapshot_count": 0,
            "message": "Chưa có market snapshot.",
        }

    df = market_df.copy()

    for c in [
        "market_real",
        "market_live",
        "market_forecast",
        "pull_dep",
        "pull_vua",
        "mua_early",
        "cp_manh",
        "ga_tang_toc",
        "obv_green_pct",
        "slope_positive_pct",
        "rsi_above_50_pct",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    stats = {
        "market_snapshot_count": len(df),
        "avg_market_real": safe_mean(df["market_real"]) if "market_real" in df.columns else np.nan,
        "avg_market_live": safe_mean(df["market_live"]) if "market_live" in df.columns else np.nan,
        "avg_market_forecast": safe_mean(df["market_forecast"]) if "market_forecast" in df.columns else np.nan,
        "avg_pull_dep": safe_mean(df["pull_dep"]) if "pull_dep" in df.columns else np.nan,
        "avg_pull_vua": safe_mean(df["pull_vua"]) if "pull_vua" in df.columns else np.nan,
        "avg_mua_early": safe_mean(df["mua_early"]) if "mua_early" in df.columns else np.nan,
    }

    return stats


def collect_optimizer_statistics(brain):
    decision_df, learning_df, market_df = load_optimizer_sources(brain)

    decision_df = prepare_date(decision_df, "decision_date")
    learning_df = prepare_date(learning_df, "date")
    market_df = prepare_date(market_df, "date")

    stats = {
        "generated_at": bo_time_str(),
        "decision": collect_decision_statistics(decision_df),
        "learning": collect_learning_statistics(learning_df),
        "market": collect_market_statistics(market_df),
    }

    return stats, decision_df, learning_df, market_df


# =========================================================
# PATTERN DETECTION
# =========================================================

def detect_low_forecast_but_pull_works(learning_df):
    if learning_df is None or learning_df.empty:
        return None

    df = learning_df.copy()

    required = ["market_forecast", "pull_dep", "pull_vua", "t5_return_avg", "t5_winrate"]
    if not all(c in df.columns for c in required):
        return None

    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["pull_total"] = df["pull_dep"].fillna(0) + df["pull_vua"].fillna(0)

    sub = df[
        (df["market_forecast"] < 4)
        & (df["pull_total"] >= 6)
    ].copy()

    if len(sub) < 5:
        return None

    avg_t5 = safe_mean(sub["t5_return_avg"])
    wr5 = safe_mean(sub["t5_winrate"])

    if pd.notna(avg_t5) and avg_t5 > 1:
        return {
            "pattern": "LOW_FORECAST_BUT_PULL_WORKS",
            "sample": len(sub),
            "avg_t5_return": avg_t5,
            "avg_t5_winrate": wr5,
            "message": (
                "Forecast thấp nhưng Pull vẫn hoạt động tốt. "
                "Có thể Decision Engine đang phạt Forecast hơi nặng."
            ),
            "recommendation": {
                "target": "forecast_penalty",
                "action": "decrease",
                "current_hint": -15,
                "suggested_hint": -10,
            },
        }

    return None


def detect_good_environment(learning_df):
    if learning_df is None or learning_df.empty:
        return None

    df = learning_df.copy()

    if "lesson_type" not in df.columns:
        return None

    good = df[df["lesson_type"].astype(str) == "GOOD_ENV"].copy()
    bad = df[df["lesson_type"].astype(str) == "BAD_ENV"].copy()

    if len(good) < 5:
        return None

    if len(good) > len(bad) * 1.5:
        return {
            "pattern": "GOOD_ENV_DOMINANT",
            "sample": len(good),
            "bad_sample": len(bad),
            "message": (
                "Số bài học GOOD_ENV đang áp đảo BAD_ENV. "
                "Bot có thể tự tin hơn khi điều kiện tương tự lặp lại."
            ),
            "recommendation": {
                "target": "confidence_bonus",
                "action": "increase",
                "suggested_hint": 5,
            },
        }

    return None


def detect_standing_outside_too_often(decision_df, learning_df):
    if decision_df is None or decision_df.empty:
        return None

    df = decision_df.copy()

    if "action" not in df.columns:
        return None

    standing = df[df["action"].astype(str).str.contains("ĐỨNG NGOÀI", na=False)].copy()

    if len(df) < 10 or len(standing) < 7:
        return None

    standing_ratio = len(standing) / len(df)

    if standing_ratio >= 0.7:
        return {
            "pattern": "TOO_MUCH_STANDING_OUTSIDE",
            "sample": len(df),
            "standing_count": len(standing),
            "standing_ratio": round(standing_ratio * 100, 2),
            "message": (
                "Decision Engine đang đứng ngoài quá nhiều. "
                "Điều này đúng khi thị trường yếu, nhưng cần theo dõi xem có bỏ lỡ Pull tốt không."
            ),
            "recommendation": {
                "target": "min_buy_confidence",
                "action": "review",
                "current_hint": 45,
                "suggested_hint": 42,
            },
        }

    return None


def detect_forecast_ahead_real(learning_df):
    if learning_df is None or learning_df.empty:
        return None

    df = learning_df.copy()

    required = ["market_forecast", "market_real", "t5_return_avg", "t5_winrate"]
    if not all(c in df.columns for c in required):
        return None

    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    sub = df[
        (df["market_forecast"] >= 6)
        & (df["market_real"] < 6)
    ].copy()

    if len(sub) < 5:
        return None

    avg_t5 = safe_mean(sub["t5_return_avg"])
    wr5 = safe_mean(sub["t5_winrate"])

    if pd.notna(avg_t5) and avg_t5 > 1:
        return {
            "pattern": "FORECAST_AHEAD_REAL_WORKS",
            "sample": len(sub),
            "avg_t5_return": avg_t5,
            "avg_t5_winrate": wr5,
            "message": (
                "Forecast đi trước REAL và sau đó cho kết quả tốt. "
                "Nên xem Forecast như tín hiệu sớm, nhưng vẫn kiểm soát NAV."
            ),
            "recommendation": {
                "target": "forecast_ahead_bonus",
                "action": "increase",
                "current_hint": 4,
                "suggested_hint": 7,
            },
        }

    return None


def detect_patterns(decision_df, learning_df, market_df):
    patterns = []

    detectors = [
        detect_low_forecast_but_pull_works,
        detect_good_environment,
        detect_forecast_ahead_real,
    ]

    for fn in detectors:
        try:
            p = fn(learning_df)
            if p:
                patterns.append(p)
        except Exception:
            pass

    try:
        p = detect_standing_outside_too_often(decision_df, learning_df)
        if p:
            patterns.append(p)
    except Exception:
        pass

    return patterns


# =========================================================
# RECOMMENDATION
# =========================================================

def build_default_recommendation():
    return {
        "generated_at": bo_time_str(),
        "status": "WARMUP",
        "confidence": 0,
        "apply_mode": "SUGGEST_ONLY",
        "weights": {
            "forecast_penalty": -15,
            "forecast_ahead_bonus": 4,
            "confidence_bonus": 0,
            "min_buy_confidence": 45,
        },
        "notes": [
            "Chưa đủ dữ liệu để tối ưu trọng số.",
        ],
    }


def build_recommendation_from_patterns(patterns, stats):
    rec = build_default_recommendation()

    if not patterns:
        return rec

    rec["status"] = "HAS_SUGGESTION"
    rec["confidence"] = min(80, 30 + len(patterns) * 15)
    rec["notes"] = []

    for p in patterns:
        rec["notes"].append(p.get("message", ""))

        r = p.get("recommendation", {})
        target = r.get("target")
        suggested = r.get("suggested_hint")

        if target and suggested is not None:
            rec["weights"][target] = suggested

    return rec


# =========================================================
# REPORT
# =========================================================

def build_report_text(stats, patterns, recommendation):
    lines = []

    lines.append("🧠 BRAIN OPTIMIZER REPORT")
    lines.append("")
    lines.append(f"Ngày tạo: {bo_time_str()}")
    lines.append("")

    d = stats.get("decision", {})
    l = stats.get("learning", {})
    m = stats.get("market", {})

    lines.append("1) Decision")
    lines.append(f"- Số quyết định đã ghi: {d.get('decision_count', 0)}")
    lines.append(f"- Confidence trung bình: {d.get('avg_confidence', np.nan)}")
    lines.append(f"- NAV trung bình: {d.get('avg_nav', np.nan)}")
    lines.append("")

    lines.append("2) Learning")
    lines.append(f"- Số bài học: {l.get('learning_count', 0)}")
    lines.append(f"- T+5 trung bình: {l.get('avg_t5_return', np.nan)}")
    lines.append(f"- WinRate T+5: {l.get('avg_t5_winrate', np.nan)}")
    lines.append("")

    lines.append("3) Market")
    lines.append(f"- Snapshot: {m.get('market_snapshot_count', 0)}")
    lines.append(f"- Market REAL TB: {m.get('avg_market_real', np.nan)}")
    lines.append(f"- Forecast TB: {m.get('avg_market_forecast', np.nan)}")
    lines.append("")

    lines.append("4) Pattern phát hiện")
    if not patterns:
        lines.append("- Chưa phát hiện quy luật đủ mạnh.")
    else:
        for p in patterns:
            lines.append(f"- {p.get('pattern')}: {p.get('message')}")

    lines.append("")
    lines.append("5) Recommendation")
    lines.append(f"- Status: {recommendation.get('status')}")
    lines.append(f"- Confidence: {recommendation.get('confidence')}")
    lines.append(f"- Apply mode: {recommendation.get('apply_mode')}")
    lines.append(f"- Weights: {recommendation.get('weights')}")

    return "\n".join(lines)


def build_optimizer_report(stats, patterns, recommendation):
    return {
        "date": bo_today_str(),
        "created_at": bo_time_str(),
        "status": recommendation.get("status", "WARMUP"),
        "optimizer_confidence": recommendation.get("confidence", 0),
        "decision_count": stats.get("decision", {}).get("decision_count", 0),
        "learning_count": stats.get("learning", {}).get("learning_count", 0),
        "market_snapshot_count": stats.get("market", {}).get("market_snapshot_count", 0),
        "pattern_count": len(patterns),
        "patterns": safe_json_dumps(patterns),
        "recommendation": safe_json_dumps(recommendation),
        "report_text": build_report_text(stats, patterns, recommendation),
    }


# =========================================================
# SAVE
# =========================================================

def save_optimizer_outputs(brain, report, recommendation, keep_days=360):
    report_df = pd.DataFrame([report])
    rec_df = pd.DataFrame([{
        "date": bo_today_str(),
        "created_at": bo_time_str(),
        "status": recommendation.get("status"),
        "confidence": recommendation.get("confidence"),
        "apply_mode": recommendation.get("apply_mode"),
        "weights": safe_json_dumps(recommendation.get("weights", {})),
        "notes": safe_json_dumps(recommendation.get("notes", [])),
        "raw": safe_json_dumps(recommendation),
    }])

    saved_report, report_status = brain.remember(
        table=OPTIMIZER_REPORT_TABLE,
        data=report_df,
        key=["date", "created_at"],
        keep_days=keep_days,
        date_col="date",
        sort_by=["date", "created_at"],
        sync_github=False,
    )

    saved_rec, rec_status = brain.remember(
        table=OPTIMIZER_RECOMMENDATION_TABLE,
        data=rec_df,
        key=["date", "created_at"],
        keep_days=keep_days,
        date_col="date",
        sort_by=["date", "created_at"],
        sync_github=False,
    )

    return {
        "report_status": report_status,
        "recommendation_status": rec_status,
        "saved_report": saved_report,
        "saved_recommendation": saved_rec,
    }


# =========================================================
# PUBLIC API
# =========================================================

def run_brain_optimizer(brain, save=True):
    stats, decision_df, learning_df, market_df = collect_optimizer_statistics(brain)

    patterns = detect_patterns(
        decision_df=decision_df,
        learning_df=learning_df,
        market_df=market_df,
    )

    recommendation = build_recommendation_from_patterns(
        patterns=patterns,
        stats=stats,
    )

    report = build_optimizer_report(
        stats=stats,
        patterns=patterns,
        recommendation=recommendation,
    )

    save_result = None
    if save:
        save_result = save_optimizer_outputs(
            brain=brain,
            report=report,
            recommendation=recommendation,
        )

    return report, recommendation, save_result


def load_latest_optimizer_report(brain):
    df = brain.recall(OPTIMIZER_REPORT_TABLE)

    if df is None or df.empty:
        return {}

    if "created_at" in df.columns:
        out = df.copy()
        out["_created"] = pd.to_datetime(out["created_at"], errors="coerce")
        out = out.sort_values("_created")
        return out.tail(1).iloc[0].to_dict()

    return df.tail(1).iloc[0].to_dict()


def load_latest_recommendation(brain):
    df = brain.recall(OPTIMIZER_RECOMMENDATION_TABLE)

    if df is None or df.empty:
        return build_default_recommendation()

    if "created_at" in df.columns:
        out = df.copy()
        out["_created"] = pd.to_datetime(out["created_at"], errors="coerce")
        out = out.sort_values("_created")
        row = out.tail(1).iloc[0].to_dict()
    else:
        row = df.tail(1).iloc[0].to_dict()

    raw = row.get("raw", "")

    try:
        return json.loads(raw)
    except Exception:
        return build_default_recommendation()


def build_optimizer_view(report):
    if not report:
        return pd.DataFrame()

    row = {
        "Ngày": report.get("date"),
        "Status": report.get("status"),
        "Optimizer Confidence": report.get("optimizer_confidence"),
        "Decision": report.get("decision_count"),
        "Learning": report.get("learning_count"),
        "Market Snapshot": report.get("market_snapshot_count"),
        "Patterns": report.get("pattern_count"),
    }

    return pd.DataFrame([row])


def build_recommendation_view(recommendation):
    if not recommendation:
        return pd.DataFrame()

    weights = recommendation.get("weights", {})
    notes = recommendation.get("notes", [])

    row = {
        "Status": recommendation.get("status"),
        "Confidence": recommendation.get("confidence"),
        "Apply Mode": recommendation.get("apply_mode"),
        "Forecast Penalty": weights.get("forecast_penalty"),
        "Forecast Ahead Bonus": weights.get("forecast_ahead_bonus"),
        "Confidence Bonus": weights.get("confidence_bonus"),
        "Min Buy Confidence": weights.get("min_buy_confidence"),
        "Notes": " | ".join(notes),
    }

    return pd.DataFrame([row])


def build_report_markdown(report):
    if not report:
        return "Chưa có Brain Optimizer Report."

    return str(report.get("report_text", ""))


# =========================================================
# QUICK TEST
# =========================================================

if __name__ == "__main__":

    from brain_manager import get_brain

    brain = get_brain()

    report, recommendation, save_result = run_brain_optimizer(
        brain=brain,
        save=True,
    )

    print(report.get("report_text", ""))
