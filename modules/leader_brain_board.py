# ==========================================================
# LEADER BRAIN BOARD
# Mr.BOT PRO V4
# ==========================================================

import pandas as pd
import streamlit as st

from leader_memory import load_memory


# ==========================================================
# Helper
# ==========================================================

def leader_level(score: float) -> str:

    if pd.isna(score):
        return "-"

    if score >= 95:
        return "👑 Elite"

    if score >= 85:
        return "🔥 Strong"

    if score >= 75:
        return "⭐ Good"

    if score >= 60:
        return "🟢 Watch"

    return "⚪ Normal"


def ai_color(text):

    if pd.isna(text):
        return ""

    text = str(text)

    if "MUA" in text.upper():
        return "🟢 " + text

    if "GIỮ" in text.upper():
        return "🟡 " + text

    if "THEO" in text.upper():
        return "🔵 " + text

    if "BÁN" in text.upper():
        return "🔴 " + text

    return text


# ==========================================================
# Main
# ==========================================================

def render_leader_brain():

    st.markdown("---")

    st.subheader("🧠 Leader Brain")

    df = load_memory()

    if df is None:

        st.info("Leader Brain chưa có dữ liệu.")

        return

    if len(df) == 0:

        st.info("Leader Brain chưa có dữ liệu.")

        return

    board = df.copy()

    # ======================================================
    # sort
    # ======================================================

    if "leader_score" in board.columns:

        board = board.sort_values(
            "leader_score",
            ascending=False
        )

    board = board.reset_index(drop=True)

    # ======================================================
    # Rank
    # ======================================================

    medals = []

    for i in range(len(board)):

        if i == 0:

            medals.append("🥇")

        elif i == 1:

            medals.append("🥈")

        elif i == 2:

            medals.append("🥉")

        else:

            medals.append(str(i + 1))

    board["Rank"] = medals
    # ======================================================
    # Các cột hiển thị
    # ======================================================

    def safe_col(name, default=None):
        if name in board.columns:
            return board[name]
        return pd.Series([default] * len(board))

    board["Symbol"] = safe_col("symbol", "")

    board["Leader"] = (
        pd.to_numeric(
            safe_col("leader_score", 0),
            errors="coerce"
        )
        .fillna(0)
        .round(0)
        .astype(int)
    )

    board["Level"] = board["Leader"].apply(leader_level)

    board["Group"] = safe_col(
        "current_group",
        "-"
    )

    rs5 = pd.to_numeric(
        safe_col("current_rs5", 0),
        errors="coerce"
    ).fillna(0)

    rs10 = pd.to_numeric(
        safe_col("current_rs10", 0),
        errors="coerce"
    ).fillna(0)

    board["RS"] = (
        rs5.round(1).astype(str)
        + " / "
        + rs10.round(1).astype(str)
    )

    board["RSI"] = (
        pd.to_numeric(
            safe_col("current_rsi14", 0),
            errors="coerce"
        )
        .fillna(0)
        .round(1)
    )

    board["Persistence"] = (
        pd.to_numeric(
            safe_col("persistence_20_pct", 0),
            errors="coerce"
        )
        .fillna(0)
        .round(1)
        .astype(str)
        + "%"
    )

    board["WinRate"] = (
        pd.to_numeric(
            safe_col("winrate_t5", 0),
            errors="coerce"
        )
        .fillna(0)
        .round(1)
        .astype(str)
        + "%"
    )

    board["AI"] = safe_col(
        "recommendation",
        "-"
    ).apply(ai_color)

    board["Action"] = safe_col(
        "recommendation_reason",
        "-"
    )
      # ======================================================
    # Hiển thị Leader Brain
    # ======================================================

    show_cols = [
        "Rank",
        "Symbol",
        "Leader",
        "Level",
        "Group",
        "RS",
        "RSI",
        "Persistence",
        "WinRate",
        "AI",
        "Action",
    ]

    show_cols = [c for c in show_cols if c in board.columns]

    st.dataframe(
        board[show_cols],
        use_container_width=True,
        hide_index=True,
    )

    # ======================================================
    # Thống kê nhanh
    # ======================================================

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Leader",
            len(board)
        )

    with col2:
        elite = (board["Leader"] >= 95).sum()
        st.metric(
            "👑 Elite",
            int(elite)
        )

    with col3:
        avg = round(board["Leader"].mean(), 1)
        st.metric(
            "TB Leader",
            avg
        )

    # ======================================================
    # Top 10 Leader
    # ======================================================

    st.markdown("### 🏆 Top Leader")

    top = board.head(10)

    for _, row in top.iterrows():

        st.write(
            f"{row['Rank']} **{row['Symbol']}**"
            f" | {row['Level']}"
            f" | Leader {row['Leader']}"
            f" | RSI {row['RSI']}"
            f" | {row['AI']}"
        )

    # ======================================================
    # Database đầy đủ
    # ======================================================

    with st.expander("📂 Xem Database đầy đủ"):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )
