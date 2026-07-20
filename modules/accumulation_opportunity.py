"""
==========================================================
ACCUMULATION OPPORTUNITY ENGINE
==========================================================

Version : 1.0

Purpose
-------
Tìm cổ phiếu đáng để tích lũy khi thị trường điều chỉnh.

Khác hoàn toàn với Momentum Engine.

Input
-----
scan_df

Output
------
Accumulation Opportunity Board

Author
------
Mr.Bot
==========================================================
"""

import numpy as np
import pandas as pd
import streamlit as st


# ==========================================================
# CONSTANTS
# ==========================================================

MAX_SCORE = 100

TOP_LIMIT = 15

MIN_SCORE_SHOW = 55

RSI_WEIGHT = 25
RS_WEIGHT = 20
BOTTOM_WEIGHT = 20
OBV_WEIGHT = 15
VOLUME_WEIGHT = 10
LIQUIDITY_WEIGHT = 10


# ==========================================================
# SAFE FUNCTIONS
# ==========================================================

def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except:
        return default


def safe_bool(value):
    try:
        return bool(value)
    except:
        return False


# ==========================================================
# SCORE ENGINE
# ==========================================================

# ==========================================================
# OPPORTUNITY SCORE ENGINE V2
# ==========================================================

def calculate_accumulation_score(row):

    score = 0.0
    confidence = 0.0
    reasons = []

    rsi = safe_float(row.get("rsi14"))
    rs5 = safe_float(row.get("rs5"))
    rs10 = safe_float(row.get("rs10"))

    near20 = safe_float(row.get("near_bottom_20_pct"))
    near60 = safe_float(row.get("near_bottom_60_pct"))

    dry5 = safe_float(row.get("dryup_ratio_5"))
    dry10 = safe_float(row.get("dryup_ratio_10"))

    volume = safe_float(row.get("volume"))
    vol_ma20 = safe_float(row.get("vol_ma20"))

    slope = safe_float(row.get("ema9_ma20_slope"))

    obv = str(row.get("obv_status", "")).lower()

    # ======================================================
    # RSI
    # ======================================================

    if 30 <= rsi <= 40:
        score += 25
        confidence += 20
        reasons.append("RSI vùng tích lũy đẹp")

    elif 40 < rsi <= 50:
        score += 22
        confidence += 17
        reasons.append("RSI bắt đầu hồi")

    elif 50 < rsi <= 60:
        score += 14
        confidence += 10

    elif rsi < 30:
        score += 10
        confidence += 6
        reasons.append("RSI quá thấp")

    # ======================================================
    # RS Improvement
    # ======================================================

    rs_gap = rs5 - rs10

    if rs_gap >= 4:
        score += 22
        confidence += 18
        reasons.append("RS tăng mạnh")

    elif rs_gap >= 2:
        score += 18
        confidence += 15
        reasons.append("RS cải thiện")

    elif rs_gap > 0:
        score += 12
        confidence += 10

    # ======================================================
    # Bottom
    # ======================================================

    if near60 <= 10:
        score += 20
        confidence += 18
        reasons.append("Sát đáy 60 phiên")

    elif near60 <= 20:
        score += 16
        confidence += 15
        reasons.append("Gần đáy 60 phiên")

    elif near20 <= 10:
        score += 12
        confidence += 10

    # ======================================================
    # OBV
    # ======================================================

    if "positive" in obv:

        score += 15
        confidence += 15
        reasons.append("OBV xác nhận")

    elif "bull" in obv:

        score += 13
        confidence += 12

    elif "neutral" in obv:

        score += 8
        confidence += 8

    # ======================================================
    # Dry Up
    # ======================================================

    if dry5 < 0.6:

        score += 10
        confidence += 8
        reasons.append("Cạn cung mạnh")

    elif dry10 < 0.8:

        score += 7
        confidence += 6

    # ======================================================
    # Liquidity
    # ======================================================

    if vol_ma20 > 0:

        ratio = volume / vol_ma20

        if ratio > 0.6:
            score += 8

        elif ratio > 0.3:
            score += 5

    # ======================================================
    # Trend Penalty
    # ======================================================

    if slope < -0.5:

        score -= 12
        confidence -= 10
        reasons.append("Xu hướng còn yếu")

    elif slope < 0:

        score -= 6
        confidence -= 4

    # ======================================================
    # Bonus
    # ======================================================

    bonus = 0

    if rs_gap > 2 and 30 <= rsi <= 50:
        bonus += 4

    if near60 < 15 and "positive" in obv:
        bonus += 4

    if dry5 < 0.6 and rs_gap > 2:
        bonus += 3

    score += bonus

    # ======================================================
    # Normalize
    # ======================================================

    score = max(0, min(100, round(score)))

    confidence = max(0, min(100, round(confidence)))

    return (
        score,
        confidence,
        " • ".join(reasons)
    )

# ==========================================================
# DECISION ENGINE
# ==========================================================

def classify_accumulation(score):

    if score >= 85:
        return "🌱 Tích lũy đẹp", "🟢 Gom mạnh"

    if score >= 75:
        return "🌱 Tích lũy", "🟢 Gom dần"

    if score >= 60:
        return "👀 Theo dõi", "🟡 Chờ xác nhận"

    return "⚪ Chưa hình thành", "⚪ Quan sát"


# ==========================================================
# BUILD BOARD
# ==========================================================

def build_accumulation_board(scan_df):

    if scan_df is None or len(scan_df) == 0:
        return pd.DataFrame()

    df = scan_df.copy()

    scores = []

    confidences = []

    reasons = []

    stages = []

    actions = []

    for _, row in df.iterrows():

        score, conf, reason = calculate_accumulation_score(row)

        stage, action = classify_accumulation(score)

        scores.append(score)

        confidences.append(conf)

        reasons.append(reason)

        stages.append(stage)

        actions.append(action)

    df["opportunity_score"] = scores

    df["confidence"] = confidences

    df["stage"] = stages

    df["action"] = actions

    df["reason"] = reasons

    df = df[df["opportunity_score"] >= MIN_SCORE_SHOW]

    df = df.sort_values(
        ["opportunity_score", "confidence"],
        ascending=False,
    )

    return df.head(TOP_LIMIT)


# ==========================================================
# RENDER
# ==========================================================

def render_accumulation_board(scan_df):

    board = build_accumulation_board(scan_df)

    if board.empty:
        return

    st.subheader("🌱 ACCUMULATION OPPORTUNITY BOARD")

    show_cols = [
        "symbol",
        "price",
        "opportunity_score",
        "confidence",
        "stage",
        "action",
        "reason",
    ]

    show_cols = [c for c in show_cols if c in board.columns]

    st.dataframe(
        board[show_cols],
        use_container_width=True,
        hide_index=True,
    )
# ==========================================================
# FORMAT ENGINE
# ==========================================================

def format_accumulation_board(df):

    if df.empty:
        return df

    board = df.copy()

    # Score
    if "opportunity_score" in board.columns:
        board["Opportunity"] = board["opportunity_score"].astype(int)

    # Confidence
    if "confidence" in board.columns:
        board["Confidence"] = board["confidence"].astype(int).astype(str) + "%"

    # Price
    if "price" in board.columns:
        board["Giá"] = board["price"].round(2)

    # Symbol
    if "symbol" in board.columns:
        board["Mã"] = board["symbol"]

    # Stage
    if "stage" in board.columns:
        board["Giai đoạn"] = board["stage"]

    # Action
    if "action" in board.columns:
        board["Hành động"] = board["action"]

    # Reason
    if "reason" in board.columns:
        board["Lý do"] = board["reason"]

    cols = [
        "Mã",
        "Giá",
        "Opportunity",
        "Confidence",
        "Giai đoạn",
        "Hành động",
        "Lý do",
    ]

    cols = [c for c in cols if c in board.columns]

    return board[cols]


# ==========================================================
# SUMMARY ENGINE
# ==========================================================

def accumulation_summary(df):

    if df.empty:
        st.info("Không có cơ hội tích lũy phù hợp.")
        return

    strong = (df["Opportunity"] >= 85).sum()

    good = ((df["Opportunity"] >= 75) &
            (df["Opportunity"] < 85)).sum()

    watch = ((df["Opportunity"] >= 60) &
             (df["Opportunity"] < 75)).sum()

    avg_score = df["Opportunity"].mean()

    avg_conf = (
        df["Confidence"]
        .str.replace("%", "", regex=False)
        .astype(int)
        .mean()
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("⭐⭐⭐⭐⭐", strong)

    c2.metric("⭐⭐⭐⭐", good)

    c3.metric("⭐⭐⭐", watch)

    c4.metric("TB Score", f"{avg_score:.1f}")

    c5.metric("TB Confidence", f"{avg_conf:.0f}%")


# ==========================================================
# MAIN RENDER
# ==========================================================

def render_accumulation_board(scan_df):

    board = build_accumulation_board(scan_df)

    board = format_accumulation_board(board)

    st.markdown("---")

    st.subheader("🌱 Accumulation Opportunity Board")

    accumulation_summary(board)

    st.dataframe(
        board,
        use_container_width=True,
        hide_index=True,
    )




