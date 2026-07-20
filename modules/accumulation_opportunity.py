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

def calculate_accumulation_score(row):

    score = 0
    confidence = 0

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

    obv = str(row.get("obv_status", "")).lower()

    slope = safe_float(row.get("ema9_ma20_slope"))

    # ------------------------------------------------------
    # RSI
    # ------------------------------------------------------

    if 25 <= rsi <= 45:
        score += RSI_WEIGHT
        confidence += 18
        reasons.append("RSI vùng tích lũy")

    elif 45 < rsi <= 55:
        score += RSI_WEIGHT * 0.8
        confidence += 14
        reasons.append("RSI cải thiện")

    elif rsi < 25:
        score += RSI_WEIGHT * 0.4
        confidence += 6
        reasons.append("RSI quá thấp")

    # ------------------------------------------------------
    # RS
    # ------------------------------------------------------

    if rs5 > rs10:

        diff = rs5 - rs10

        if diff >= 2:
            score += RS_WEIGHT
            confidence += 18
            reasons.append("RS5 vượt RS10")

        elif diff > 0:
            score += RS_WEIGHT * 0.7
            confidence += 12
            reasons.append("RS cải thiện")

    # ------------------------------------------------------
    # Bottom
    # ------------------------------------------------------

    if near60 <= 20:
        score += BOTTOM_WEIGHT
        confidence += 18
        reasons.append("Gần đáy 60 phiên")

    elif near20 <= 15:
        score += BOTTOM_WEIGHT * 0.7
        confidence += 10
        reasons.append("Gần đáy 20 phiên")

    # ------------------------------------------------------
    # OBV
    # ------------------------------------------------------

    if "positive" in obv or "bull" in obv:
        score += OBV_WEIGHT
        confidence += 15
        reasons.append("OBV tích cực")

    elif "neutral" in obv:
        score += OBV_WEIGHT * 0.5
        confidence += 8
        reasons.append("OBV ổn định")

    # ------------------------------------------------------
    # Dry Volume
    # ------------------------------------------------------

    if dry5 < 0.8 or dry10 < 0.8:
        score += VOLUME_WEIGHT
        confidence += 10
        reasons.append("Thanh khoản cạn")

    # ------------------------------------------------------
    # Liquidity
    # ------------------------------------------------------

    if volume > vol_ma20 * 0.4:
        score += LIQUIDITY_WEIGHT
        confidence += 10

    # ------------------------------------------------------
    # Trend penalty
    # ------------------------------------------------------

    if slope < 0:
        score -= 8
        confidence -= 5

    score = max(0, min(MAX_SCORE, round(score)))

    confidence = max(0, min(100, round(confidence)))

    return score, confidence, ", ".join(reasons)


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
