# app.py
# -*- coding: utf-8 -*-

import math
import numpy as np
import pandas as pd
import streamlit as st

# =========================================================
# CẤU HÌNH GIAO DIỆN
# =========================================================
st.set_page_config(page_title="Scanner Gà Chiến V20", layout="wide")

st.markdown("""
<style>
    .main-title {
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 8px;
    }
    .sub-note {
        color: #666;
        font-size: 14px;
        margin-bottom: 14px;
    }
    .section-title {
        font-size: 20px;
        font-weight: 800;
        margin-top: 20px;
        margin-bottom: 12px;
    }
    .tiny-note {
        color: #666;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">SCANNER GÀ CHIẾN V20 – GIỮ FORM CŨ, SỬA LOGIC EARLY + 222</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-note">222 = tín hiệu momentum mạnh | Risk chỉ để cảnh báo hành động, không dùng để loại cổ phiếu</div>',
    unsafe_allow_html=True
)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("Nguồn dữ liệu")
    mode = st.radio("Chọn dữ liệu", ["Demo", "Upload CSV/XLSX"], index=0)

    st.markdown("---")
    st.markdown("### Ý nghĩa")
    st.write("- **EARLY** = chuẩn bị chạy, chưa phải mạnh hẳn")
    st.write("- **CP MẠNH** = đang vận động tốt, có thể mua/pull/chờ")
    st.write("- **222** = có momentum mạnh")
    st.write("- **Risk** = chỉ để nhắc có nên đuổi hay chờ pull")

    st.markdown("---")
    show_only_focus = st.checkbox("Chỉ hiện các mã đáng chú ý", value=False)

# =========================================================
# NGƯỠNG LOGIC
# =========================================================
CFG = {
    # ---- EARLY (nới để không quá cứng) ----
    "early_rsi_min": 40.0,
    "early_rsi_max": 60.0,
    "early_dist_from_ema9_max": 2.8,
    "early_ema9_ma20_gap_max": 5.0,
    "early_obv_drop_tol_pct": -3.5,
    "early_vol_ratio_max": 1.15,

    # ---- CP MẠNH / ENTRY ----
    "strong_rsi_min": 55.0,
    "strong_rsi_max": 72.0,
    "strong_dist_from_ema9_max": 5.5,
    "strong_ema9_ma20_gap_max": 9.0,

    # ---- HOT / LATE ----
    "late_rsi_warn": 72.0,
    "late_rsi_hot": 75.0,
    "late_dist_from_ema9_warn": 4.5,
    "late_dist_from_ema9_hot": 6.5,
    "late_ema9_ma20_gap_warn": 7.0,
    "late_ema9_ma20_gap_hot": 10.0,

    # ---- Risk phạt nhẹ, KHÔNG giết cp ----
    "risk_rsi_mid": 75.0,
    "risk_rsi_high": 80.0,
    "risk_dist_mid": 3.0,
    "risk_dist_high": 6.0,
    "risk_gap_mid": 6.0,
    "risk_gap_high": 10.0,
    "risk_atr_mid": 3.8,
    "risk_atr_high": 5.2,

    # ---- Pull ----
    "pull_beauty_max_dist": 2.2,
    "pull_medium_max_dist": 4.0,

    # ---- Hiển thị ----
    "min_price": 3.0,
}

# =========================================================
# HÀM TIỆN ÍCH
# =========================================================
def to_float(x, default=np.nan):
    try:
        if x is None:
            return default
        return float(x)
    except:
        return default

def safe_pct(a, b):
    a = to_float(a)
    b = to_float(b)
    if pd.isna(a) or pd.isna(b) or b == 0:
        return np.nan
    return (a - b) / abs(b) * 100.0

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    rename_map = {
        "ticker": "symbol",
        "code": "symbol",
        "stock": "symbol",

        "Close": "price",
        "close": "price",
        "price_close": "price",

        "Open": "open",
        "open_price": "open",

        "High": "high",
        "Low": "low",

        "Volume": "volume",
        "vol": "volume",

        "EMA9": "ema9",
        "ema_9": "ema9",

        "MA20": "ma20",
        "ma_20": "ma20",

        "WMA45": "wma45",
        "wma_45": "wma45",

        "MA100": "ma100",
        "ma_100": "ma100",

        "RSI": "rsi14",
        "rsi": "rsi14",
        "rsi14": "rsi14",

        "RSI_EMA9": "rsi_ema9",
        "rsi_ema9": "rsi_ema9",

        "OBV": "obv",
        "obv_value": "obv",

        "OBV_EMA9": "obv_ema9",
        "obv_ema9": "obv_ema9",

        "MACD": "macd",
        "macd_value": "macd",

        "MACD_SIGNAL": "macd_signal",
        "macd_signal_line": "macd_signal",

        "MACD_HIST": "macd_hist",
        "hist": "macd_hist",

        "ATR": "atr",
        "atr14": "atr",

        "BB_UPPER": "bb_upper",
        "bb_upper": "bb_upper",

        "BB_LOWER": "bb_lower",
        "bb_lower": "bb_lower",

        "VOL_SMA20": "vol_sma20",
        "vol_ma20": "vol_sma20",

        "close_prev": "price_prev",
        "rsi_prev": "rsi_prev",
        "obv_prev": "obv_prev",
        "atr_prev": "atr_prev",
    }

    df = df.rename(columns=rename_map)

    needed = [
        "symbol", "price", "open", "high", "low", "volume",
        "ema9", "ma20", "wma45", "ma100",
        "rsi14", "rsi_ema9",
        "obv", "obv_ema9",
        "macd", "macd_signal", "macd_hist",
        "atr", "bb_upper", "bb_lower", "vol_sma20",
        "price_prev", "rsi_prev", "obv_prev", "atr_prev"
    ]

    for c in needed:
        if c not in df.columns:
            df[c] = np.nan

    num_cols = [c for c in df.columns if c != "symbol"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # fallback prev
    if df["price_prev"].isna().all():
        df["price_prev"] = df["price"]
    if df["rsi_prev"].isna().all():
        df["rsi_prev"] = df["rsi14"]
    if df["obv_prev"].isna().all():
        df["obv_prev"] = df["obv"]
    if df["atr_prev"].isna().all():
        df["atr_prev"] = df["atr"]

    return df

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["dist_from_ema9_pct"] = (df["price"] - df["ema9"]) / df["ema9"].replace(0, np.nan) * 100
    df["dist_from_ma20_pct"] = (df["price"] - df["ma20"]) / df["ma20"].replace(0, np.nan) * 100
    df["ema9_ma20_gap_pct"] = (df["ema9"] - df["ma20"]) / df["ma20"].replace(0, np.nan) * 100

    df["rsi_slope"] = df["rsi14"] - df["rsi_prev"]
    df["obv_slope_pct"] = (df["obv"] - df["obv_prev"]) / df["obv_prev"].replace(0, np.nan) * 100
    df["atr_pct"] = df["atr"] / df["price"].replace(0, np.nan) * 100
    df["vol_ratio"] = df["volume"] / df["vol_sma20"].replace(0, np.nan)

    df["price_above_ema9"] = df["price"] > df["ema9"]
    df["price_above_ma20"] = df["price"] > df["ma20"]
    df["ema9_above_ma20"] = df["ema9"] >= df["ma20"]
    df["rsi_above_ema9"] = df["rsi14"] > df["rsi_ema9"]
    df["obv_above_ema9"] = df["obv"] > df["obv_ema9"]
    df["macd_above_signal"] = df["macd"] > df["macd_signal"]
    df["hist_positive"] = df["macd_hist"] > 0

    # nến
    df["body_pct"] = (df["price"] - df["open"]).abs() / df["price"].replace(0, np.nan) * 100
    df["is_green"] = df["price"] > df["open"]

    return df

# =========================================================
# SIGNAL 222
# =========================================================
def compute_E_score(row):
    score = 0
    if row["price_above_ema9"]:
        score += 1
    if row["rsi_above_ema9"]:
        score += 1
    if row["obv_above_ema9"]:
        score += 1
    return min(score, 2) if score >= 2 else score

def has_222(row):
    return bool(row["price_above_ema9"] and row["rsi_above_ema9"] and row["obv_above_ema9"])

# =========================================================
# STAGE / GROUP
# =========================================================
def classify_stage(row):
    rsi = row["rsi14"]
    dist = row["dist_from_ema9_pct"]
    gap = row["ema9_ma20_gap_pct"]
    obv_slope = row["obv_slope_pct"]
    vol_ratio = row["vol_ratio"]

    # EARLY: nới hơn, không bắt buộc nến xanh nhỏ
    early_cond = (
        (CFG["early_rsi_min"] <= rsi <= CFG["early_rsi_max"])
        and (abs(dist) <= CFG["early_dist_from_ema9_max"])
        and (abs(gap) <= CFG["early_ema9_ma20_gap_max"])
        and (pd.isna(obv_slope) or obv_slope >= CFG["early_obv_drop_tol_pct"])
        and (pd.isna(vol_ratio) or vol_ratio <= CFG["early_vol_ratio_max"])
    )

    if early_cond:
        return "EARLY"

    # CP MẠNH / ENTRY: nới để không loại leader đẹp
    strong_cond = (
        row["price_above_ema9"]
        and row["ema9_above_ma20"]
        and (CFG["strong_rsi_min"] <= rsi <= CFG["strong_rsi_max"])
        and (dist <= CFG["strong_dist_from_ema9_max"])
        and (gap <= CFG["strong_ema9_ma20_gap_max"])
        and row["rsi_above_ema9"]
    )
    if strong_cond:
        return "STRONG"

    # HOT / LATE
    late_cond = (
        row["price_above_ema9"]
        and row["ema9_above_ma20"]
        and (
            rsi >= CFG["late_rsi_warn"]
            or dist >= CFG["late_dist_from_ema9_warn"]
            or gap >= CFG["late_ema9_ma20_gap_warn"]
        )
    )
    if late_cond:
        return "LATE"

    return "WATCH"

def classify_group(row, stage):
    dist = row["dist_from_ema9_pct"]
    rsi = row["rsi14"]

    if stage == "EARLY":
        return "MUA EARLY"

    if stage == "STRONG":
        if abs(dist) <= CFG["pull_beauty_max_dist"]:
            return "PULL VỪA"
        return "CP MẠNH"

    if stage == "LATE":
        return "CP MẠNH"

    if has_222(row):
        return "CP MẠNH"

    if rsi >= 50:
        return "THEO DÕI"

    return "WATCHLIST"

# =========================================================
# RISK CHỈ CẢNH BÁO, KHÔNG DÙNG ĐỂ LOẠI
# =========================================================
def compute_R_score(row, stage):
    rsi = row["rsi14"]
    dist = row["dist_from_ema9_pct"]
    gap = row["ema9_ma20_gap_pct"]
    atr_pct = row["atr_pct"]

    penalty = 0

    if rsi >= CFG["risk_rsi_high"]:
        penalty += 2
    elif rsi >= CFG["risk_rsi_mid"]:
        penalty += 1

    if dist >= CFG["risk_dist_high"]:
        penalty += 2
    elif dist >= CFG["risk_dist_mid"]:
        penalty += 1

    if gap >= CFG["risk_gap_high"]:
        penalty += 2
    elif gap >= CFG["risk_gap_mid"]:
        penalty += 1

    if atr_pct >= CFG["risk_atr_high"]:
        penalty += 2
    elif atr_pct >= CFG["risk_atr_mid"]:
        penalty += 1

    # stage chỉ nhắc nhẹ
    if stage == "EARLY":
        base = 0
    elif stage == "STRONG":
        base = 1
    elif stage == "LATE":
        base = 2
    else:
        base = 1

    total = penalty + base

    # đổi sang thang R cũ kiểu 0/1/2
    # 0 = rủi ro thấp
    # 1 = vừa
    # 2 = cao hơn nhưng vẫn giữ cp
    if total <= 1:
        return 0
    elif total <= 4:
        return 1
    else:
        return 2

def risk_label_from_R(r):
    if r == 0:
        return "THẤP"
    if r == 1:
        return "VỪA"
    return "CAO"

# =========================================================
# QUALITY / Q
# =========================================================
def compute_Q_score(row, stage):
    score = 0

    if stage == "EARLY":
        score += 2
    elif stage == "STRONG":
        score += 2
    elif stage == "LATE":
        score += 1
    else:
        score += 1

    if row["macd_above_signal"]:
        score += 1
    if row["hist_positive"]:
        score += 1
    if row["ema9_above_ma20"]:
        score += 1

    # scale về 0/1/2
    if score >= 4:
        return 2
    elif score >= 2:
        return 1
    return 0

# =========================================================
# PULL LABEL
# =========================================================
def compute_pull_label(row, stage):
    dist = abs(row["dist_from_ema9_pct"])

    if stage == "EARLY":
        return "EARLY"

    if stage in ["STRONG", "LATE"]:
        if dist <= CFG["pull_beauty_max_dist"]:
            return "PULL ĐẸP"
        elif dist <= CFG["pull_medium_max_dist"]:
            return "PULL VỪA"
        else:
            return "PULL XẤU"

    return "QUAN SÁT"

# =========================================================
# ACTION
# =========================================================
def decide_action(row, stage, group, E, R, Q):
    if stage == "EARLY":
        if R == 0:
            return "THEO DÕI SỚM"
        return "CANH XÁC NHẬN"

    if stage == "STRONG":
        if abs(row["dist_from_ema9_pct"]) <= CFG["pull_beauty_max_dist"] and R <= 1:
            return "MUA ĐƯỢC"
        elif R <= 1:
            return "MUA THĂM DÒ / CHỜ PULL"
        return "CHỜ PULL"

    if stage == "LATE":
        if has_222(row):
            return "LEADER MẠNH - CHỜ PULL"
        return "KHÔNG ĐUỔI"

    if has_222(row):
        return "GIỮ TRONG WATCHLIST"

    return "QUAN SÁT"

# =========================================================
# ĐÈN
# =========================================================
def light_icon(group, action, R):
    if action == "MUA ĐƯỢC":
        return "🟩"
    if group == "MUA EARLY":
        return "🟨"
    if "CHỜ PULL" in action or R == 2:
        return "🟥"
    return "🟨"

# =========================================================
# CHẠY LOGIC CHÍNH
# =========================================================
def run_scanner(df):
    df = normalize_columns(df)
    df = add_features(df)

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row["price"]) or row["price"] < CFG["min_price"]:
            continue

        stage = classify_stage(row)
        group = classify_group(row, stage)

        E = compute_E_score(row)
        R = compute_R_score(row, stage)
        Q = compute_Q_score(row, stage)

        total_score = E + (2 - R) + Q
        pull_label = compute_pull_label(row, stage)
        action = decide_action(row, stage, group, E, R, Q)
        icon = light_icon(group, action, R)

        obv_status = "🟢" if row["obv_above_ema9"] else "🔴"
        signal_222 = "222" if has_222(row) else ""

        rows.append({
            "đèn": icon,
            "symbol": row["symbol"],
            "group": group,
            "price": round(row["price"], 2),
            "ema9": round(row["ema9"], 2) if pd.notna(row["ema9"]) else np.nan,
            "ma20": round(row["ma20"], 2) if pd.notna(row["ma20"]) else np.nan,
            "rsi14": round(row["rsi14"], 2) if pd.notna(row["rsi14"]) else np.nan,
            "rsi_slope": round(row["rsi_slope"], 2) if pd.notna(row["rsi_slope"]) else np.nan,
            "obv": round(row["obv"], 0) if pd.notna(row["obv"]) else np.nan,
            "obv_ema9": round(row["obv_ema9"], 0) if pd.notna(row["obv_ema9"]) else np.nan,
            "obv_status": obv_status,
            "222": signal_222,
            "E": E,
            "R": R,
            "Q": Q,
            "total_score": total_score,
            "dist_from_ema9_pct": round(row["dist_from_ema9_pct"], 2) if pd.notna(row["dist_from_ema9_pct"]) else np.nan,
            "pull_label": pull_label,
            "stage": stage,
            "action": action,
            "risk_text": risk_label_from_R(R),
            "ema9_ma20_gap_pct": round(row["ema9_ma20_gap_pct"], 2) if pd.notna(row["ema9_ma20_gap_pct"]) else np.nan,
            "atr_pct": round(row["atr_pct"], 2) if pd.notna(row["atr_pct"]) else np.nan,
            "vol_ratio": round(row["vol_ratio"], 2) if pd.notna(row["vol_ratio"]) else np.nan,
        })

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    # giữ form cũ: mã mua được / cp mạnh / early lên trên
    group_order = {
        "PULL VỪA": 0,
        "CP MẠNH": 1,
        "MUA EARLY": 2,
        "THEO DÕI": 3,
        "WATCHLIST": 4,
    }
    out["group_order"] = out["group"].map(group_order).fillna(9)

    out = out.sort_values(
        by=["group_order", "total_score", "E", "Q", "R", "dist_from_ema9_pct"],
        ascending=[True, False, False, False, True, True]
    ).reset_index(drop=True)

    return out

# =========================================================
# DEMO DATA
# =========================================================
def demo_data():
    return pd.DataFrame([
        {
            "symbol": "TLG", "price": 51200, "open": 50800, "high": 51500, "low": 50500, "volume": 1200000,
            "ema9": 50728.57, "ma20": 49710, "wma45": 48500, "ma100": 47000,
            "rsi14": 56.51, "rsi_ema9": 55.57, "obv": 6746876, "obv_ema9": 6459698,
            "macd": 12, "macd_signal": 10, "macd_hist": 2, "atr": 1100,
            "bb_upper": 52000, "bb_lower": 49000, "vol_sma20": 1300000,
            "price_prev": 50900, "rsi_prev": 55.57, "obv_prev": 6680000, "atr_prev": 1080
        },
        {
            "symbol": "MSB", "price": 12650, "open": 12500, "high": 12700, "low": 12480, "volume": 14000000,
            "ema9": 12471.24, "ma20": 12052.5, "wma45": 11897, "ma100": 11750,
            "rsi14": 64.78, "rsi_ema9": 60.96, "obv": -292767545, "obv_ema9": -292972625,
            "macd": 200, "macd_signal": 150, "macd_hist": 50, "atr": 330,
            "bb_upper": 13200, "bb_lower": 10900, "vol_sma20": 12000000,
            "price_prev": 12400, "rsi_prev": 60.96, "obv_prev": -293500000, "atr_prev": 320
        },
        {
            "symbol": "NAB", "price": 13700, "open": 13550, "high": 13900, "low": 13500, "volume": 3500000,
            "ema9": 13493.83, "ma20": 13290, "wma45": 13050, "ma100": 12850,
            "rsi14": 64.78, "rsi_ema9": 58.35, "obv": -790209, "obv_ema9": -1837054,
            "macd": 110, "macd_signal": 75, "macd_hist": 35, "atr": 280,
            "bb_upper": 14400, "bb_lower": 12700, "vol_sma20": 3100000,
            "price_prev": 13300, "rsi_prev": 58.35, "obv_prev": -1200000, "atr_prev": 270
        },
        {
            "symbol": "GEX", "price": 40600, "open": 40100, "high": 40750, "low": 39950, "volume": 5200000,
            "ema9": 39966.04, "ma20": 38472.5, "wma45": 37500, "ma100": 36000,
            "rsi14": 59.37, "rsi_ema9": 58.42, "obv": -62053871, "obv_ema9": -63307186,
            "macd": 115, "macd_signal": 100, "macd_hist": 15, "atr": 1050,
            "bb_upper": 42000, "bb_lower": 36500, "vol_sma20": 5000000,
            "price_prev": 40200, "rsi_prev": 58.42, "obv_prev": -62500000, "atr_prev": 1040
        },
        {
            "symbol": "VHC", "price": 62500, "open": 62200, "high": 62800, "low": 62000, "volume": 850000,
            "ema9": 61512.77, "ma20": 60050, "wma45": 59200, "ma100": 56900,
            "rsi14": 60.92, "rsi_ema9": 60.16, "obv": 8446001, "obv_ema9": 7690749,
            "macd": 130, "macd_signal": 118, "macd_hist": 12, "atr": 1500,
            "bb_upper": 64000, "bb_lower": 54000, "vol_sma20": 900000,
            "price_prev": 62000, "rsi_prev": 60.16, "obv_prev": 8350000, "atr_prev": 1480
        },
        {
            "symbol": "NVL", "price": 18200, "open": 17650, "high": 18400, "low": 17500, "volume": 41000000,
            "ema9": 17138.49, "ma20": 15815, "wma45": 14964, "ma100": 13618,
            "rsi14": 76.81, "rsi_ema9": 74.42, "obv": 370524919, "obv_ema9": 287857733,
            "macd": 420, "macd_signal": 300, "macd_hist": 120, "atr": 1050,
            "bb_upper": 18900, "bb_lower": 12700, "vol_sma20": 30000000,
            "price_prev": 17150, "rsi_prev": 74.42, "obv_prev": 340000000, "atr_prev": 980
        },
        {
            "symbol": "VNM", "price": 61800, "open": 61700, "high": 62000, "low": 61500, "volume": 1800000,
            "ema9": 61614.81, "ma20": 61410, "wma45": 61410, "ma100": 59957,
            "rsi14": 48.77, "rsi_ema9": 47.38, "obv": -128959550, "obv_ema9": -132171786,
            "macd": 20, "macd_signal": 10, "macd_hist": 10, "atr": 950,
            "bb_upper": 62800, "bb_lower": 59900, "vol_sma20": 1900000,
            "price_prev": 61700, "rsi_prev": 47.38, "obv_prev": -130000000, "atr_prev": 940
        },
        {
            "symbol": "LHG", "price": 28450, "open": 28250, "high": 28550, "low": 28100, "volume": 980000,
            "ema9": 28362.04, "ma20": 28270, "wma45": 27600, "ma100": 27000,
            "rsi14": 52.58, "rsi_ema9": 51.61, "obv": -423994, "obv_ema9": -474268,
            "macd": 12, "macd_signal": 11, "macd_hist": 1, "atr": 650,
            "bb_upper": 29000, "bb_lower": 27000, "vol_sma20": 1050000,
            "price_prev": 28300, "rsi_prev": 51.61, "obv_prev": -450000, "atr_prev": 640
        },
        {
            "symbol": "DGC", "price": 55100, "open": 54600, "high": 55300, "low": 54400, "volume": 4200000,
            "ema9": 54309.38, "ma20": 53525, "wma45": 53510, "ma100": 49680,
            "rsi14": 46.11, "rsi_ema9": 41.64, "obv": -70781713, "obv_ema9": -73260846,
            "macd": 18, "macd_signal": 11, "macd_hist": 7, "atr": 1650,
            "bb_upper": 57700, "bb_lower": 49700, "vol_sma20": 4500000,
            "price_prev": 54200, "rsi_prev": 41.64, "obv_prev": -72000000, "atr_prev": 1620
        },
    ])

# =========================================================
# LOAD DATA
# =========================================================
def load_uploaded_file(uploaded_file):
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")
        return None

if mode == "Demo":
    raw_df = demo_data()
else:
    uploaded = st.file_uploader("Upload file CSV/XLSX", type=["csv", "xlsx"])
    if uploaded is not None:
        raw_df = load_uploaded_file(uploaded)
    else:
        raw_df = None

if raw_df is None:
    st.info("Anh chọn Demo hoặc upload file dữ liệu.")
    st.stop()

# =========================================================
# CHẠY SCAN
# =========================================================
result_df = run_scanner(raw_df)

if result_df.empty:
    st.warning("Không có dữ liệu hợp lệ.")
    st.stop()

# bộ lọc phụ
if show_only_focus:
    result_df = result_df[
        result_df["group"].isin(["PULL VỪA", "CP MẠNH", "MUA EARLY"])
    ].copy()

# =========================================================
# TÓM TẮT
# =========================================================
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("PULL VỪA", int((result_df["group"] == "PULL VỪA").sum()))
with c2:
    st.metric("CP MẠNH", int((result_df["group"] == "CP MẠNH").sum()))
with c3:
    st.metric("MUA EARLY", int((result_df["group"] == "MUA EARLY").sum()))
with c4:
    st.metric("Có 222", int((result_df["222"] == "222").sum()))
with c5:
    st.metric("Mua được", int((result_df["action"] == "MUA ĐƯỢC").sum()))

# =========================================================
# BẢNG TỔNG CHI TIẾT
# =========================================================
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

detail_cols = [
    "symbol", "group", "price", "ema9", "ma20",
    "rsi14", "rsi_slope", "obv", "obv_ema9", "obv_status",
    "E", "R", "Q", "total_score",
    "dist_from_ema9_pct", "pull_label",
    "222", "stage", "action", "risk_text",
    "ema9_ma20_gap_pct", "atr_pct", "vol_ratio"
]

st.dataframe(
    result_df[detail_cols],
    use_container_width=True,
    hide_index=True,
    height=540
)

# =========================================================
# TOP LIST GIỐNG KIỂU CŨ
# =========================================================
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown('<div class="section-title">TOP PULL / MUA ĐƯỢC</div>', unsafe_allow_html=True)
    df1 = result_df[
        (result_df["group"].isin(["PULL VỪA", "CP MẠNH"])) &
        (result_df["action"].isin(["MUA ĐƯỢC", "MUA THĂM DÒ / CHỜ PULL", "CHỜ PULL", "LEADER MẠNH - CHỜ PULL"]))
    ].head(15)
    st.dataframe(
        df1[["symbol", "group", "price", "E", "R", "Q", "total_score", "pull_label", "action"]],
        use_container_width=True,
        hide_index=True
    )

with col2:
    st.markdown('<div class="section-title">TOP EARLY</div>', unsafe_allow_html=True)
    df2 = result_df[result_df["group"] == "MUA EARLY"].head(15)
    st.dataframe(
        df2[["symbol", "group", "price", "E", "R", "Q", "total_score", "pull_label", "action"]],
        use_container_width=True,
        hide_index=True
    )

with col3:
    st.markdown('<div class="section-title">TOP 222 / LEADER</div>', unsafe_allow_html=True)
    df3 = result_df[result_df["222"] == "222"].head(15)
    st.dataframe(
        df3[["symbol", "group", "price", "E", "R", "Q", "total_score", "pull_label", "action"]],
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# GHI CHÚ
# =========================================================
st.markdown("---")
st.markdown("""
**Cách đọc bản V20**
- **E** = lực momentum ngắn hạn (222 nằm ở đây)
- **R** = mức rủi ro điểm vào hiện tại, chỉ để cảnh báo
- **Q** = chất lượng vận động tổng thể
- **total_score** = điểm tổng để xếp thứ tự
- **group** giữ form cũ: `PULL VỪA / CP MẠNH / MUA EARLY`
- **Risk không dùng để loại cổ phiếu mạnh**
""")
