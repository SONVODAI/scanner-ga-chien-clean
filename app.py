# app_v19_clean.py
# -*- coding: utf-8 -*-

import math
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st


# =========================================================
# V19 CORE
# - Tách riêng EARLY / ENTRY / LATE
# - 222 = MOMENTUM, KHÔNG phải risk thấp
# - Có thêm R-ENTRY để đánh giá có nên mua ngay không
# =========================================================

st.set_page_config(page_title="V19 - Early / 222 / Risk", layout="wide")

st.title("V19 – Tách EARLY chuẩn + 222 + Risk Entry")
st.caption("222 = Momentum mạnh | Quyết định mua = Stage + Risk Entry")


# =========================================================
# 1) CẤU HÌNH NGƯỠNG
# =========================================================
CFG = {
    # ----- EARLY -----
    "early_rsi_min": 40,
    "early_rsi_max": 55,
    "early_max_price_vs_ma20_pct": 3.0,      # giá không được vượt MA20 quá xa
    "early_max_ema9_ma20_gap_pct": 3.5,      # EMA9 không được xa MA20 quá nhiều
    "early_max_obv_slope_pct": 3.0,          # OBV chỉ được đi ngang / nhích nhẹ
    "early_max_vol_ratio": 1.05,             # vol thấp / cạn cung
    "early_need_green_small_candle": True,

    # ----- ENTRY / BREAK / PULL -----
    "entry_rsi_min": 55,
    "entry_rsi_max": 70,
    "entry_max_price_vs_ema9_pct": 4.0,      # mua đẹp khi giá chưa xa EMA9 quá
    "entry_max_ema9_ma20_gap_pct": 7.0,      # EMA9 bắt đầu tách MA20 vừa phải
    "entry_min_vol_ratio": 0.95,             # vol không được quá kiệt nếu là break

    # ----- LATE / HOT -----
    "late_rsi_warn": 70,
    "late_rsi_hot": 75,
    "late_ema9_ma20_gap_pct": 8.0,
    "late_price_vs_ema9_pct": 5.0,
    "late_bb_expand_pct": 18.0,              # BB width % giá tương đối lớn

    # ----- 222 -----
    "signal_222_need_price_above_ema9": True,
    "signal_222_need_rsi_above_rsi_ema9": True,
    "signal_222_need_obv_above_obv_ema9": True,

    # ----- RISK ENTRY -----
    "risk_rsi_mid": 70,
    "risk_rsi_high": 75,
    "risk_price_vs_ema9_mid": 3.5,
    "risk_price_vs_ema9_high": 5.0,
    "risk_ema9_ma20_gap_mid": 6.0,
    "risk_ema9_ma20_gap_high": 8.0,
    "risk_bb_width_mid": 14.0,
    "risk_bb_width_high": 18.0,
    "risk_atr_pct_mid": 3.5,
    "risk_atr_pct_high": 5.0,

    # ----- XẾP HẠNG / HIỂN THỊ -----
    "min_close": 3,
}


# =========================================================
# 2) HÀM TIỆN ÍCH
# =========================================================
def safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def pct_diff(a, b) -> float:
    a = safe_float(a)
    b = safe_float(b)
    if pd.isna(a) or pd.isna(b) or b == 0:
        return np.nan
    return (a - b) / abs(b) * 100.0


def is_up(a, b) -> bool:
    a = safe_float(a)
    b = safe_float(b)
    if pd.isna(a) or pd.isna(b):
        return False
    return a > b


def is_flat_or_up(cur, prev, tol_pct=0.2) -> bool:
    cur = safe_float(cur)
    prev = safe_float(prev)
    if pd.isna(cur) or pd.isna(prev) or prev == 0:
        return False
    change = (cur - prev) / abs(prev) * 100.0
    return change >= -tol_pct


def candle_body_pct(open_, close_, ref_price) -> float:
    open_ = safe_float(open_)
    close_ = safe_float(close_)
    ref_price = safe_float(ref_price)
    if pd.isna(open_) or pd.isna(close_) or pd.isna(ref_price) or ref_price == 0:
        return np.nan
    return abs(close_ - open_) / ref_price * 100.0


def candle_is_green(open_, close_) -> bool:
    open_ = safe_float(open_)
    close_ = safe_float(close_)
    if pd.isna(open_) or pd.isna(close_):
        return False
    return close_ > open_


def classify_candle_size(body_pct: float) -> str:
    if pd.isna(body_pct):
        return "?"
    if body_pct <= 1.5:
        return "small"
    if body_pct <= 3.0:
        return "medium"
    return "large"


def score_to_light(stage: str, risk: str, signal_222: bool) -> str:
    if stage == "ENTRY" and risk == "LOW":
        return "🟩"
    if stage == "EARLY" and risk in ["LOW", "MID"]:
        return "🟨"
    if signal_222 and risk == "HIGH":
        return "🟥"
    if stage == "LATE":
        return "🟥"
    return "🟨"


# =========================================================
# 3) CHUẨN HÓA DỮ LIỆU
# =========================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Kỳ vọng tối thiểu có các cột sau.
    Nếu nguồn dữ liệu anh đang dùng tên khác, chỉ cần sửa map ở đây.

    symbol, close, open, high, low, volume,
    ema9, ma20, wma45, ma100,
    rsi, rsi_ema9,
    obv, obv_ema9,
    macd, macd_signal, macd_hist,
    atr,
    bb_upper, bb_lower,
    vol_sma20,
    close_prev, rsi_prev, obv_prev, atr_prev
    """

    df = df.copy()

    rename_map = {
        "ticker": "symbol",
        "code": "symbol",
        "stock": "symbol",

        "Close": "close",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Volume": "volume",

        "EMA9": "ema9",
        "MA20": "ma20",
        "WMA45": "wma45",
        "MA100": "ma100",

        "RSI": "rsi",
        "RSI_EMA9": "rsi_ema9",

        "OBV": "obv",
        "OBV_EMA9": "obv_ema9",

        "MACD": "macd",
        "MACD_SIGNAL": "macd_signal",
        "MACD_HIST": "macd_hist",

        "ATR": "atr",

        "BB_UPPER": "bb_upper",
        "BB_LOWER": "bb_lower",

        "VOL_SMA20": "vol_sma20",
        "close_yday": "close_prev",
        "rsi_yday": "rsi_prev",
        "obv_yday": "obv_prev",
        "atr_yday": "atr_prev",
    }
    df = df.rename(columns=rename_map)

    required_cols = [
        "symbol", "close", "open", "high", "low", "volume",
        "ema9", "ma20", "wma45", "ma100",
        "rsi", "rsi_ema9", "obv", "obv_ema9",
        "macd", "macd_signal", "macd_hist",
        "atr", "bb_upper", "bb_lower", "vol_sma20",
    ]

    for c in required_cols:
        if c not in df.columns:
            df[c] = np.nan

    # Nếu chưa có prev -> tạm dùng current để tránh crash
    for c in ["close_prev", "rsi_prev", "obv_prev", "atr_prev"]:
        if c not in df.columns:
            df[c] = df.get(c.replace("_prev", ""), np.nan)

    # Ép kiểu
    num_cols = [c for c in df.columns if c != "symbol"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


# =========================================================
# 4) TÍNH CHỈ SỐ PHỤ
# =========================================================
def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["price_vs_ema9_pct"] = (df["close"] - df["ema9"]) / df["ema9"] * 100
    df["price_vs_ma20_pct"] = (df["close"] - df["ma20"]) / df["ma20"] * 100
    df["ema9_ma20_gap_pct"] = (df["ema9"] - df["ma20"]) / df["ma20"] * 100

    df["vol_ratio"] = df["volume"] / df["vol_sma20"].replace(0, np.nan)
    df["atr_pct"] = df["atr"] / df["close"].replace(0, np.nan) * 100

    df["bb_width_pct"] = (df["bb_upper"] - df["bb_lower"]) / df["close"].replace(0, np.nan) * 100

    df["rsi_slope"] = df["rsi"] - df["rsi_prev"]
    # obv đổi theo % tương đối để dễ so
    df["obv_slope_pct"] = (df["obv"] - df["obv_prev"]) / df["obv_prev"].replace(0, np.nan) * 100
    df["atr_slope"] = df["atr"] - df["atr_prev"]

    df["body_pct"] = (df["close"] - df["open"]).abs() / df["close"].replace(0, np.nan) * 100
    df["is_green"] = df["close"] > df["open"]
    df["candle_size"] = df["body_pct"].apply(classify_candle_size)

    # Cấu trúc tương đối cơ bản
    df["price_above_ema9"] = df["close"] > df["ema9"]
    df["price_above_ma20"] = df["close"] > df["ma20"]
    df["ema9_above_ma20"] = df["ema9"] > df["ma20"]
    df["rsi_above_rsi_ema9"] = df["rsi"] > df["rsi_ema9"]
    df["obv_above_obv_ema9"] = df["obv"] > df["obv_ema9"]
    df["macd_above_signal"] = df["macd"] > df["macd_signal"]
    df["hist_positive"] = df["macd_hist"] > 0

    return df


# =========================================================
# 5) SIGNAL 222 = MOMENTUM
# =========================================================
def detect_222(row: pd.Series) -> bool:
    conds = []

    if CFG["signal_222_need_price_above_ema9"]:
        conds.append(bool(row["price_above_ema9"]))

    if CFG["signal_222_need_rsi_above_rsi_ema9"]:
        conds.append(bool(row["rsi_above_rsi_ema9"]))

    if CFG["signal_222_need_obv_above_obv_ema9"]:
        conds.append(bool(row["obv_above_obv_ema9"]))

    return all(conds)


# =========================================================
# 6) PHÂN LOẠI STAGE: EARLY / ENTRY / LATE / OTHER
# =========================================================
def classify_stage(row: pd.Series) -> str:
    rsi = row["rsi"]
    price_vs_ma20 = row["price_vs_ma20_pct"]
    price_vs_ema9 = row["price_vs_ema9_pct"]
    gap = row["ema9_ma20_gap_pct"]
    obv_slope = row["obv_slope_pct"]
    vol_ratio = row["vol_ratio"]
    is_green = bool(row["is_green"])
    candle_size = row["candle_size"]

    # -------- EARLY chuẩn --------
    early_ok = (
        (CFG["early_rsi_min"] <= rsi <= CFG["early_rsi_max"])
        and (price_vs_ma20 <= CFG["early_max_price_vs_ma20_pct"])
        and (abs(gap) <= CFG["early_max_ema9_ma20_gap_pct"])
        and (pd.isna(obv_slope) or abs(obv_slope) <= CFG["early_max_obv_slope_pct"])
        and (pd.isna(vol_ratio) or vol_ratio <= CFG["early_max_vol_ratio"])
        and (not row["price_vs_ema9_pct"] > 5.0)
        and (not row["price_above_ma20"] or price_vs_ma20 <= CFG["early_max_price_vs_ma20_pct"])
        and bool(row["rsi_above_rsi_ema9"])
    )

    if CFG["early_need_green_small_candle"]:
        early_ok = early_ok and is_green and (candle_size == "small")

    if early_ok:
        return "EARLY"

    # -------- ENTRY đẹp --------
    entry_ok = (
        row["price_above_ema9"]
        and row["price_above_ma20"]
        and row["ema9_above_ma20"]
        and (CFG["entry_rsi_min"] <= rsi <= CFG["entry_rsi_max"])
        and (price_vs_ema9 <= CFG["entry_max_price_vs_ema9_pct"])
        and (gap <= CFG["entry_max_ema9_ma20_gap_pct"])
        and row["rsi_above_rsi_ema9"]
        and row["obv_above_obv_ema9"]
        and (pd.isna(vol_ratio) or vol_ratio >= CFG["entry_min_vol_ratio"])
    )
    if entry_ok:
        return "ENTRY"

    # -------- LATE / HOT --------
    late_ok = (
        row["price_above_ema9"]
        and row["ema9_above_ma20"]
        and (
            (rsi >= CFG["late_rsi_warn"])
            or (gap >= CFG["late_ema9_ma20_gap_pct"])
            or (price_vs_ema9 >= CFG["late_price_vs_ema9_pct"])
            or (row["bb_width_pct"] >= CFG["late_bb_expand_pct"])
        )
    )
    if late_ok:
        return "LATE"

    return "OTHER"


# =========================================================
# 7) CHẤM RISK ENTRY
# =========================================================
def classify_risk_entry(row: pd.Series, stage: str, signal_222: bool) -> tuple[str, int, str]:
    """
    Risk càng cao thì càng không nên mua ngay.
    Trả về:
      risk_label, penalty_points, note
    """
    penalty = 0
    notes = []

    rsi = row["rsi"]
    price_vs_ema9 = row["price_vs_ema9_pct"]
    gap = row["ema9_ma20_gap_pct"]
    bb = row["bb_width_pct"]
    atr_pct = row["atr_pct"]

    # 1) RSI nóng
    if rsi >= CFG["risk_rsi_high"]:
        penalty += 3
        notes.append("RSI quá cao")
    elif rsi >= CFG["risk_rsi_mid"]:
        penalty += 1
        notes.append("RSI bắt đầu nóng")

    # 2) Giá xa EMA9
    if price_vs_ema9 >= CFG["risk_price_vs_ema9_high"]:
        penalty += 3
        notes.append("Giá xa EMA9")
    elif price_vs_ema9 >= CFG["risk_price_vs_ema9_mid"]:
        penalty += 1
        notes.append("Giá hơi xa EMA9")

    # 3) EMA9 xa MA20
    if gap >= CFG["risk_ema9_ma20_gap_high"]:
        penalty += 3
        notes.append("EMA9 xa MA20")
    elif gap >= CFG["risk_ema9_ma20_gap_mid"]:
        penalty += 1
        notes.append("EMA9 tách MA20 vừa")

    # 4) BB bung mạnh
    if bb >= CFG["risk_bb_width_high"]:
        penalty += 2
        notes.append("BB bung mạnh")
    elif bb >= CFG["risk_bb_width_mid"]:
        penalty += 1
        notes.append("BB bắt đầu nở")

    # 5) ATR cao
    if atr_pct >= CFG["risk_atr_pct_high"]:
        penalty += 2
        notes.append("ATR cao")
    elif atr_pct >= CFG["risk_atr_pct_mid"]:
        penalty += 1
        notes.append("ATR tăng")

    # 6) Stage điều chỉnh risk
    if stage == "EARLY":
        penalty -= 1
        notes.append("Stage early")
    elif stage == "ENTRY":
        penalty += 0
    elif stage == "LATE":
        penalty += 2
        notes.append("Stage late")

    # 7) 222 không làm giảm risk.
    # Chỉ xác nhận momentum, không phải điểm vào an toàn.
    if signal_222 and stage == "LATE":
        penalty += 1
        notes.append("222 nhưng đã nóng")

    # Chặn âm
    penalty = max(penalty, 0)

    if penalty <= 1:
        return "LOW", penalty, " | ".join(notes) if notes else "R thấp"
    elif penalty <= 4:
        return "MID", penalty, " | ".join(notes) if notes else "R trung bình"
    else:
        return "HIGH", penalty, " | ".join(notes) if notes else "R cao"


# =========================================================
# 8) HÀNH ĐỘNG KHUYẾN NGHỊ
# =========================================================
def decide_action(stage: str, risk: str, signal_222: bool, row: pd.Series) -> str:
    if stage == "EARLY" and risk == "LOW":
        return "Theo dõi sát / có thể gom sớm"
    if stage == "EARLY" and risk == "MID":
        return "Theo dõi, chờ xác nhận thêm"
    if stage == "ENTRY" and risk == "LOW":
        return "Mua được"
    if stage == "ENTRY" and risk == "MID":
        return "Mua thăm dò / ưu tiên chờ pull đẹp"
    if stage == "LATE" and signal_222 and risk == "HIGH":
        return "Leader mạnh nhưng không đuổi, chờ pull EMA9"
    if stage == "LATE":
        return "Không mua đuổi"
    if signal_222 and risk == "MID":
        return "Có momentum, chờ điểm vào đẹp hơn"
    return "Quan sát"


# =========================================================
# 9) MOMENTUM SCORE & ENTRY SCORE
# =========================================================
def calc_momentum_score(row: pd.Series, signal_222: bool) -> int:
    score = 0

    if row["price_above_ema9"]:
        score += 1
    if row["ema9_above_ma20"]:
        score += 1
    if row["rsi_above_rsi_ema9"]:
        score += 1
    if row["obv_above_obv_ema9"]:
        score += 1
    if row["macd_above_signal"]:
        score += 1
    if row["hist_positive"]:
        score += 1
    if row["rsi"] >= 55:
        score += 1
    if signal_222:
        score += 2

    return score  # max ~8


def calc_entry_score(stage: str, risk: str) -> int:
    # Score riêng cho "điểm mua"
    base = {
        "EARLY": 3,
        "ENTRY": 5,
        "LATE": 1,
        "OTHER": 0,
    }.get(stage, 0)

    risk_adj = {
        "LOW": 3,
        "MID": 1,
        "HIGH": -2,
    }.get(risk, 0)

    return base + risk_adj


# =========================================================
# 10) PIPELINE CHÍNH
# =========================================================
def run_v19_logic(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    df = add_derived_features(df)

    results = []
    for _, row in df.iterrows():
        if pd.isna(row["close"]) or row["close"] < CFG["min_close"]:
            continue

        signal_222 = detect_222(row)
        stage = classify_stage(row)
        risk, penalty, risk_note = classify_risk_entry(row, stage, signal_222)
        action = decide_action(stage, risk, signal_222, row)
        momentum_score = calc_momentum_score(row, signal_222)
        entry_score = calc_entry_score(stage, risk)
        light = score_to_light(stage, risk, signal_222)

        results.append({
            "Mã": row["symbol"],
            "Giá": round(row["close"], 2) if pd.notna(row["close"]) else np.nan,
            "Stage": stage,
            "222": "YES" if signal_222 else "",
            "Risk": risk,
            "Đèn": light,
            "Action": action,

            "MomentumScore": momentum_score,
            "EntryScore": entry_score,
            "RiskPenalty": penalty,

            "RSI": round(row["rsi"], 2) if pd.notna(row["rsi"]) else np.nan,
            "RSI_EMA9": round(row["rsi_ema9"], 2) if pd.notna(row["rsi_ema9"]) else np.nan,
            "OBV>EMA9": bool(row["obv_above_obv_ema9"]),
            "MACD>Signal": bool(row["macd_above_signal"]),
            "Hist+": bool(row["hist_positive"]),

            "Price_vs_EMA9_%": round(row["price_vs_ema9_pct"], 2) if pd.notna(row["price_vs_ema9_pct"]) else np.nan,
            "EMA9_MA20_Gap_%": round(row["ema9_ma20_gap_pct"], 2) if pd.notna(row["ema9_ma20_gap_pct"]) else np.nan,
            "BB_Width_%": round(row["bb_width_pct"], 2) if pd.notna(row["bb_width_pct"]) else np.nan,
            "ATR_%": round(row["atr_pct"], 2) if pd.notna(row["atr_pct"]) else np.nan,
            "Vol_Ratio": round(row["vol_ratio"], 2) if pd.notna(row["vol_ratio"]) else np.nan,

            "RiskNote": risk_note,
        })

    out = pd.DataFrame(results)

    if not out.empty:
        out = out.sort_values(
            by=["EntryScore", "MomentumScore", "RiskPenalty"],
            ascending=[False, False, True]
        ).reset_index(drop=True)

    return out


# =========================================================
# 11) DEMO DATA / LOAD DATA
# =========================================================
def make_demo_data() -> pd.DataFrame:
    # Demo để app không trắng.
    # Khi dùng thật, anh thay bằng data fetch thật của anh.
    demo = pd.DataFrame([
        {
            "symbol": "VIC", "close": 207.2, "open": 193.7, "high": 208, "low": 192,
            "volume": 4_714_000, "ema9": 182.95, "ma20": 157.99, "wma45": 157.99, "ma100": 151.71,
            "rsi": 81.96, "rsi_ema9": 72.72, "obv": 319.774, "obv_ema9": 307.433,
            "macd": 14058, "macd_signal": 7951, "macd_hist": 6107,
            "atr": 9.4, "bb_upper": 215, "bb_lower": 160, "vol_sma20": 4_200_000,
            "close_prev": 193.7, "rsi_prev": 77, "obv_prev": 311, "atr_prev": 8.9
        },
        {
            "symbol": "MSB", "close": 12.75, "open": 12.45, "high": 12.85, "low": 12.35,
            "volume": 14_152_000, "ema9": 12.49, "ma20": 12.18, "wma45": 12.06, "ma100": 11.90,
            "rsi": 66.42, "rsi_ema9": 64.04, "obv": 459.17, "obv_ema9": 448.81,
            "macd": 293, "macd_signal": 232, "macd_hist": 62,
            "atr": 0.35, "bb_upper": 13.20, "bb_lower": 10.91, "vol_sma20": 12_800_000,
            "close_prev": 12.45, "rsi_prev": 64.8, "obv_prev": 455.0, "atr_prev": 0.33
        },
        {
            "symbol": "DGC", "close": 54.8, "open": 53.5, "high": 55.2, "low": 53.4,
            "volume": 4_246_000, "ema9": 54.25, "ma20": 53.51, "wma45": 53.51, "ma100": 49.68,
            "rsi": 45.41, "rsi_ema9": 42.77, "obv": -80.49, "obv_ema9": -83.8,
            "macd": -2177, "macd_signal": -2837, "macd_hist": 661,
            "atr": 2.0, "bb_upper": 57.34, "bb_lower": 49.68, "vol_sma20": 4_500_000,
            "close_prev": 53.3, "rsi_prev": 44.6, "obv_prev": -81.0, "atr_prev": 2.05
        },
    ])
    return demo


def load_uploaded_csv(uploaded_file) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(uploaded_file)
        return df
    except Exception:
        try:
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
            return df
        except Exception as e:
            st.error(f"Lỗi đọc file: {e}")
            return None


# =========================================================
# 12) SIDEBAR
# =========================================================
with st.sidebar:
    st.header("Nguồn dữ liệu")
    data_mode = st.radio(
        "Chọn dữ liệu",
        ["Demo", "Upload CSV/XLSX"],
        index=0
    )

    st.markdown("---")
    st.subheader("Ý nghĩa")
    st.write("• EARLY = chuẩn bị chạy")
    st.write("• ENTRY = vùng mua đẹp")
    st.write("• LATE = đang mạnh nhưng không còn điểm vào đẹp")
    st.write("• 222 = momentum mạnh, không phải risk thấp")

    st.markdown("---")
    st.subheader("Bộ lọc nhanh")
    show_only_watch = st.checkbox("Chỉ hiện mã mua được / theo dõi", value=False)


# =========================================================
# 13) LOAD DATA
# =========================================================
if data_mode == "Demo":
    raw_df = make_demo_data()
else:
    uploaded = st.file_uploader("Upload file CSV hoặc Excel", type=["csv", "xlsx"])
    if uploaded is not None:
        raw_df = load_uploaded_csv(uploaded)
    else:
        raw_df = None


# =========================================================
# 14) RUN
# =========================================================
if raw_df is None:
    st.info("Anh upload file dữ liệu hoặc để chế độ Demo.")
    st.stop()

result_df = run_v19_logic(raw_df)

if result_df.empty:
    st.warning("Không có dữ liệu hợp lệ.")
    st.stop()

if show_only_watch:
    result_df = result_df[result_df["Action"].isin([
        "Theo dõi sát / có thể gom sớm",
        "Theo dõi, chờ xác nhận thêm",
        "Mua được",
        "Mua thăm dò / ưu tiên chờ pull đẹp",
    ])].copy()

# =========================================================
# 15) TÓM TẮT
# =========================================================
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("EARLY", int((result_df["Stage"] == "EARLY").sum()))
with c2:
    st.metric("ENTRY", int((result_df["Stage"] == "ENTRY").sum()))
with c3:
    st.metric("LATE", int((result_df["Stage"] == "LATE").sum()))
with c4:
    st.metric("Có 222", int((result_df["222"] == "YES").sum()))

st.markdown("---")

# =========================================================
# 16) BẢNG CHÍNH
# =========================================================
display_cols = [
    "Đèn", "Mã", "Giá", "Stage", "222", "Risk", "Action",
    "MomentumScore", "EntryScore", "RiskPenalty",
    "RSI", "RSI_EMA9",
    "Price_vs_EMA9_%", "EMA9_MA20_Gap_%", "BB_Width_%", "ATR_%", "Vol_Ratio",
    "RiskNote"
]

st.subheader("Bảng tổng hợp V19")
st.dataframe(
    result_df[display_cols],
    use_container_width=True,
    hide_index=True
)

# =========================================================
# 17) TÁCH NHÓM RÕ RÀNG
# =========================================================
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🟢 EARLY chuẩn")
    early_df = result_df[result_df["Stage"] == "EARLY"].copy()
    st.dataframe(
        early_df[["Đèn", "Mã", "Giá", "Risk", "Action", "RSI", "Price_vs_EMA9_%", "EMA9_MA20_Gap_%", "RiskNote"]],
        use_container_width=True,
        hide_index=True
    )

with col2:
    st.subheader("🟡 ENTRY / Mua được")
    entry_df = result_df[result_df["Stage"] == "ENTRY"].copy()
    st.dataframe(
        entry_df[["Đèn", "Mã", "Giá", "222", "Risk", "Action", "RSI", "Price_vs_EMA9_%", "EMA9_MA20_Gap_%", "RiskNote"]],
        use_container_width=True,
        hide_index=True
    )

with col3:
    st.subheader("🔴 LEADER nóng / Không đuổi")
    late_df = result_df[(result_df["Stage"] == "LATE") | ((result_df["222"] == "YES") & (result_df["Risk"] == "HIGH"))].copy()
    st.dataframe(
        late_df[["Đèn", "Mã", "Giá", "222", "Risk", "Action", "RSI", "Price_vs_EMA9_%", "EMA9_MA20_Gap_%", "RiskNote"]],
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# 18) TOP LIST
# =========================================================
st.markdown("---")
a, b, c = st.columns(3)

with a:
    st.subheader("Top EARLY")
    top_early = result_df[result_df["Stage"] == "EARLY"].sort_values(
        by=["RiskPenalty", "MomentumScore"],
        ascending=[True, False]
    ).head(10)
    st.dataframe(
        top_early[["Mã", "Giá", "Risk", "Action", "RSI", "RiskNote"]],
        use_container_width=True,
        hide_index=True
    )

with b:
    st.subheader("Top ENTRY")
    top_entry = result_df[result_df["Stage"] == "ENTRY"].sort_values(
        by=["EntryScore", "MomentumScore"],
        ascending=[False, False]
    ).head(10)
    st.dataframe(
        top_entry[["Mã", "Giá", "222", "Risk", "Action", "RSI", "RiskNote"]],
        use_container_width=True,
        hide_index=True
    )

with c:
    st.subheader("Top 222 nhưng không đuổi")
    top_hot = result_df[(result_df["222"] == "YES") & (result_df["Risk"] == "HIGH")].sort_values(
        by=["MomentumScore", "RiskPenalty"],
        ascending=[False, False]
    ).head(10)
    st.dataframe(
        top_hot[["Mã", "Giá", "Stage", "Risk", "Action", "RSI", "Price_vs_EMA9_%", "EMA9_MA20_Gap_%"]],
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# 19) GHI CHÚ CUỐI
# =========================================================
st.markdown("---")
st.markdown("""
### Cách hiểu V19
- **EARLY**: cổ phiếu chuẩn bị chạy, chưa mạnh rõ
- **ENTRY**: vùng mua đẹp nhất
- **LATE**: đang rất mạnh nhưng không còn điểm mua đẹp
- **222**: xác nhận momentum mạnh, **không được hiểu là risk thấp**
- **Risk Entry** mới là phần quyết định có mua ngay hay chờ pull
""")
