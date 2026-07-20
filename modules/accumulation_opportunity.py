"""
==========================================================
ACCUMULATION OPPORTUNITY ENGINE
==========================================================

Version : 1.0 Production Stable
Purpose : Tìm cổ phiếu có cơ hội tích lũy khi thị trường điều chỉnh.
Input   : scan_df
Output  : Accumulation Opportunity Board

Triết lý:
- Tách biệt hoàn toàn với Momentum Engine.
- Opportunity là điểm quyết định chính trên thang 0-100.
- Confidence và opportunity_rank được giữ nội bộ để BOT học.
- Giao diện cố định: Mã, Giá, Nhóm, RSI14, Opportunity,
  Hành động, Lý do.
==========================================================
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
import streamlit as st


# ==========================================================
# CONFIGURATION — FREEZE FOR V1.0
# ==========================================================

MAX_SCORE = 100
TOP_LIMIT = 15
MIN_SCORE_SHOW = 45
MAX_REASON_SHOW = 3


# ==========================================================
# SAFE HELPERS
# ==========================================================


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float without breaking the Streamlit app."""
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_text(value: Any) -> str:
    """Return a safe lowercase string for rule matching."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def first_existing_value(row: pd.Series, columns: Iterable[str], default: Any = "") -> Any:
    """Read the first available, non-null value from candidate columns."""
    for column in columns:
        if column in row.index:
            value = row.get(column)
            if not pd.isna(value):
                return value
    return default


def compact_reasons(reasons: list[str], limit: int = MAX_REASON_SHOW) -> str:
    """Remove duplicates and keep only the most useful reasons."""
    unique: list[str] = []
    for reason in reasons:
        if reason and reason not in unique:
            unique.append(reason)
    return " • ".join(unique[:limit])


# ==========================================================
# OPPORTUNITY SCORE ENGINE
# ==========================================================


def calculate_accumulation_score(row: pd.Series) -> tuple[int, int, str]:
    """
    Calculate accumulation opportunity and internal confidence.

    Returns
    -------
    opportunity_score : int
        Main decision score from 0 to 100.
    confidence : int
        Internal confidence label for learning/statistics; not displayed.
    reason : str
        Maximum three concise, decision-useful reasons.
    """
    score = 0.0
    confidence = 0.0
    reasons: list[str] = []

    rsi = safe_float(row.get("rsi14"))
    rs5 = safe_float(row.get("rs5"))
    rs10 = safe_float(row.get("rs10"))
    rs_gap = rs5 - rs10

    near20 = safe_float(row.get("near_bottom_20_pct"), default=999.0)
    near60 = safe_float(row.get("near_bottom_60_pct"), default=999.0)

    dry5 = safe_float(row.get("dryup_ratio_5"), default=999.0)
    dry10 = safe_float(row.get("dryup_ratio_10"), default=999.0)

    volume = safe_float(row.get("volume"))
    vol_ma20 = safe_float(row.get("vol_ma20"))
    trend_slope = safe_float(row.get("ema9_ma20_slope"))
    obv_status = normalize_text(row.get("obv_status"))

    # 1) RSI — ưu tiên vùng giá thấp nhưng đã bắt đầu ổn định.
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
    elif 0 < rsi < 30:
        score += 10
        confidence += 6
        reasons.append("RSI rất thấp")

    # 2) Relative Strength improvement.
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

    # 3) Position near medium-term bottom.
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
        reasons.append("Gần đáy 20 phiên")

    # 4) OBV confirmation.
    if "positive" in obv_status or "tích cực" in obv_status:
        score += 15
        confidence += 15
        reasons.append("OBV xác nhận")
    elif "bull" in obv_status or "tăng" in obv_status:
        score += 13
        confidence += 12
        reasons.append("OBV cải thiện")
    elif "neutral" in obv_status or "trung tính" in obv_status:
        score += 8
        confidence += 8

    # 5) Supply dry-up.
    if dry5 < 0.60:
        score += 10
        confidence += 8
        reasons.append("Cạn cung mạnh")
    elif dry10 < 0.80:
        score += 7
        confidence += 6
        reasons.append("Nguồn cung thu hẹp")

    # 6) Minimum liquidity participation.
    if vol_ma20 > 0:
        volume_ratio = volume / vol_ma20
        if volume_ratio > 0.60:
            score += 8
        elif volume_ratio > 0.30:
            score += 5

    # 7) Trend-risk penalty — tránh gom mù trong xu hướng rơi mạnh.
    if trend_slope < -0.50:
        score -= 12
        confidence -= 10
        reasons.append("Xu hướng còn yếu")
    elif trend_slope < 0:
        score -= 6
        confidence -= 4

    # 8) Confluence bonus.
    if rs_gap > 2 and 30 <= rsi <= 50:
        score += 4
    if near60 < 15 and ("positive" in obv_status or "tích cực" in obv_status):
        score += 4
    if dry5 < 0.60 and rs_gap > 2:
        score += 3

    opportunity_score = int(max(0, min(MAX_SCORE, round(score))))
    confidence_score = int(max(0, min(MAX_SCORE, round(confidence))))

    return opportunity_score, confidence_score, compact_reasons(reasons)


# ==========================================================
# DECISION ENGINE
# ==========================================================


def classify_accumulation(score: int) -> str:
    """Convert Opportunity score into the fixed five-level action."""
    if score >= 85:
        return "🟢 Gom mạnh"
    if score >= 75:
        return "🟡 Gom dần"
    if score >= 60:
        return "👀 Theo dõi"
    if score >= 45:
        return "⚪ Quan sát"
    return "❌ Bỏ qua"


def accumulation_rank(score: int) -> str:
    """Internal stable label for BOT learning; deliberately hidden from UI."""
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


# ==========================================================
# BOARD BUILDER
# ==========================================================


def build_accumulation_board(scan_df: pd.DataFrame | None) -> pd.DataFrame:
    """
    Build the production board while retaining internal learning columns.

    Internal columns retained:
    - confidence
    - opportunity_rank
    - rs5 / rs10 and original scan fields
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    df = scan_df.copy()

    results = df.apply(calculate_accumulation_score, axis=1, result_type="expand")
    results.columns = ["opportunity_score", "confidence", "reason"]

    df[["opportunity_score", "confidence", "reason"]] = results
    df["action"] = df["opportunity_score"].map(classify_accumulation)
    df["opportunity_rank"] = df["opportunity_score"].map(accumulation_rank)

    # Normalize fields required by the frozen dashboard.
    if "symbol" not in df.columns:
        df["symbol"] = ""

    if "price" not in df.columns:
        df["price"] = 0.0

    if "rsi14" not in df.columns:
        df["rsi14"] = 0.0

    if "group" not in df.columns:
        group_candidates = ["status", "health_group", "classification"]
        available = [column for column in group_candidates if column in df.columns]
        df["group"] = df[available[0]] if available else "Chưa phân nhóm"

    df = df[df["opportunity_score"] >= MIN_SCORE_SHOW]
    df = df.sort_values(
        by=["opportunity_score", "confidence", "symbol"],
        ascending=[False, False, True],
        kind="stable",
    )

    return df.head(TOP_LIMIT).reset_index(drop=True)


# ==========================================================
# DISPLAY FORMATTER
# ==========================================================


def format_accumulation_board(df: pd.DataFrame) -> pd.DataFrame:
    """Create the frozen seven-column user-facing dashboard."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["Mã", "Giá", "Nhóm", "RSI14", "Opportunity", "Hành động", "Lý do"]
        )

    board = pd.DataFrame(index=df.index)
    board["Mã"] = df["symbol"].fillna("").astype(str)
    board["Giá"] = pd.to_numeric(df["price"], errors="coerce").fillna(0).round(2)
    board["Nhóm"] = df["group"].fillna("Chưa phân nhóm").astype(str)
    board["RSI14"] = pd.to_numeric(df["rsi14"], errors="coerce").fillna(0).round(1)
    board["Opportunity"] = df["opportunity_score"].astype(int)
    board["Hành động"] = df["action"].astype(str)
    board["Lý do"] = df["reason"].fillna("").astype(str)

    return board.reset_index(drop=True)


# ==========================================================
# SUMMARY ENGINE
# ==========================================================


def render_accumulation_summary(board: pd.DataFrame) -> None:
    """Render an action-oriented summary using raw numeric data."""
    if board is None or board.empty:
        st.info("Không có cổ phiếu đạt ngưỡng cơ hội tích lũy hôm nay.")
        return

    strong = int((board["opportunity_score"] >= 85).sum())
    gradual = int(board["opportunity_score"].between(75, 84).sum())
    watch = int(board["opportunity_score"].between(60, 74).sum())
    average_score = float(board["opportunity_score"].mean())
    total = int(len(board))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🟢 Gom mạnh", strong)
    c2.metric("🟡 Gom dần", gradual)
    c3.metric("👀 Theo dõi", watch)
    c4.metric("TB Opportunity", f"{average_score:.1f}")
    c5.metric("Số CP", total)


# ==========================================================
# MAIN RENDER — SINGLE ENTRY POINT
# ==========================================================


def render_accumulation_board(scan_df: pd.DataFrame | None) -> pd.DataFrame:
    """
    Render the complete Accumulation Opportunity Board.

    Returns the unformatted production DataFrame so app.py or the Learning
    Engine can save confidence, opportunity_rank and all source indicators.
    """
    board = build_accumulation_board(scan_df)

    st.markdown("---")
    st.subheader("🌱 Accumulation Opportunity Board")

    if board.empty:
        st.info("Không có cổ phiếu đạt ngưỡng cơ hội tích lũy hôm nay.")
        return board

    render_accumulation_summary(board)
    display_board = format_accumulation_board(board)

    st.dataframe(
        display_board,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Mã": st.column_config.TextColumn("Mã", width="small"),
            "Giá": st.column_config.NumberColumn("Giá", format="%.2f", width="small"),
            "Nhóm": st.column_config.TextColumn("Nhóm", width="medium"),
            "RSI14": st.column_config.NumberColumn("RSI14", format="%.1f", width="small"),
            "Opportunity": st.column_config.ProgressColumn(
                "Opportunity",
                min_value=0,
                max_value=100,
                format="%d",
                width="medium",
            ),
            "Hành động": st.column_config.TextColumn("Hành động", width="medium"),
            "Lý do": st.column_config.TextColumn("Lý do", width="large"),
        },
    )

    return board
