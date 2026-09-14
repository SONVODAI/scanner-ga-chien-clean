# =========================================================
# POSITION GUARDIAN
# Version : 1.00
#
# Mr.BOT PROJECT
#
# Sprint 1
# ---------------------------------------------------------
# ✓ Watchlist
# ✓ EMA9
# ✓ MA20
# ✓ OBV
# ✓ Green / Yellow / Red Signal
#
# Future
# ---------------------------------------------------------
# V1.1 Holding Days
# V1.2 Cost Price
# V1.3 Profit %
# V2.0 Sell Score
# V3.0 Brain Learning
# =========================================================

import streamlit as st
import pandas as pd
import numpy as np


# =========================================================
# CONFIG
# =========================================================
DEFAULT_WATCHLIST = ""
# =========================================================
# PORTFOLIO MEMORY (user-owned, not keyed by trade_date)
# =========================================================

PORTFOLIO_FILE = "portfolio_symbols.txt"
HOLDINGS_WIDGET_KEY = "position_guardian_watchlist"
HOLDINGS_EDITOR_SHOWN_KEY = "_user_holdings_editor_shown"


def load_portfolio():
    from modules.user_holdings import load_holdings_text

    try:
        return load_holdings_text()
    except Exception:
        return DEFAULT_WATCHLIST


def save_portfolio(text):
    from modules.user_holdings import save_holdings_text

    save_holdings_text(text if text is not None else "")


SIGNAL_HOLD = "🟢 GIỮ"
SIGNAL_WARNING = "🟡 CẢNH BÁO"
SIGNAL_SELL = "🔴 BÁN"


# =========================================================
# SAFE VALUE
# =========================================================

def safe_value(row, column, default=np.nan):

    if column not in row.index:
        return default

    value = row[column]

    if pd.isna(value):
        return default

    return value


# =========================================================
# WATCHLIST
# =========================================================

def parse_watchlist(text):

    if text is None:
        return []

    text = text.upper()
    text = text.replace("\n", ",")

    symbols = []

    for item in text.split(","):

        item = item.strip()

        if item == "":
            continue

        if item not in symbols:
            symbols.append(item)

    return symbols


# =========================================================
# HEADER
# =========================================================

def render_holdings_editor():
    """Manual holdings editor. Persist only when the text actually changes."""
    from modules.user_holdings import load_holdings_text, persist_if_changed

    st.markdown("---")
    st.subheader("📦 Cổ phiếu đang nắm giữ")
    st.caption(
        "Danh sách nắm giữ do bạn nhập thủ công · giữ nguyên qua ngày mới / phiên mới · "
        "chỉ đổi khi bạn sửa · không bị Rotation / BOT / Learning tự thêm hoặc xóa"
    )

    stored = load_holdings_text()
    if HOLDINGS_WIDGET_KEY not in st.session_state:
        st.session_state[HOLDINGS_WIDGET_KEY] = stored

    watch_text = st.text_area(
        "Nhập các mã đang nắm giữ (mỗi mã một dòng hoặc ngăn cách bằng dấu phẩy)",
        placeholder="""
Ví dụ:

SSI
PVD
BSR

hoặc

SSI,PVD,BSR
""",
        height=150,
        key=HOLDINGS_WIDGET_KEY,
    )
    persist_if_changed(watch_text, stored)
    st.session_state[HOLDINGS_EDITOR_SHOWN_KEY] = True
    return parse_watchlist(watch_text)


def guardian_header():
    return render_holdings_editor()


# =========================================================
# BUILD WATCHLIST
# =========================================================

def build_watchlist_df(scan_df, symbols):

    if scan_df is None:
        return pd.DataFrame()

    if len(symbols) == 0:
        return pd.DataFrame()

    df = scan_df.copy()

    df["symbol"] = (
        df["symbol"]
        .astype(str)
        .str.upper()
    )

    df = df[df["symbol"].isin(symbols)]

    df = df.reset_index(drop=True)

    return df


# =========================================================
# FORMAT NUMBER
# =========================================================

# =========================================================
# FORMAT NUMBER
# =========================================================

def fmt_price(value):

    if pd.isna(value):
        return ""

    return f"{float(value):,.2f}"


def fmt_number(value):

    if pd.isna(value):
        return ""

    return f"{float(value):,.0f}"
# =========================================================
# SIGNAL ENGINE
# =========================================================

def generate_signal(row):

    price = safe_value(row, "price")
    ema9 = safe_value(row, "ema9")
    ma20 = safe_value(row, "ma20")

    obv = safe_value(row, "obv")
    obv_ema9 = safe_value(row, "obv_ema9")

    signal = SIGNAL_HOLD
    reason = "Xu hướng khỏe"

    score = 0

    # ----------------------------------------
    # PRICE < EMA9
    # ----------------------------------------

    if (
        pd.notna(price)
        and pd.notna(ema9)
        and price < ema9
    ):

        score += 40

        signal = SIGNAL_WARNING

        reason = "Giá dưới EMA9"

    # ----------------------------------------
    # EMA9 < MA20
    # ----------------------------------------

    if (
        pd.notna(ema9)
        and pd.notna(ma20)
        and ema9 < ma20
    ):

        score += 60

        signal = SIGNAL_SELL

        reason = "EMA9 dưới MA20"

    # ----------------------------------------
    # OBV CONFIRM
    # ----------------------------------------

    if (
        signal == SIGNAL_SELL
        and pd.notna(obv)
        and pd.notna(obv_ema9)
        and obv < obv_ema9
    ):

        score += 20

        reason += " + OBV xác nhận"

    score = min(score, 100)

    return signal, reason, score


# =========================================================
# SELL SCORE COLOR
# =========================================================

def score_color(score):

    if score >= 80:
        return "🔴"

    if score >= 40:
        return "🟡"

    return "🟢"


# =========================================================
# BUILD POSITION TABLE
# =========================================================

def build_position_table(df):

    if df.empty:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():

        signal, reason, score = generate_signal(row)

        rows.append({

            "Mã": safe_value(row, "symbol", ""),
            "Giá": fmt_price(
                safe_value(row, "price")
            ),
            "EMA9": fmt_price(
        
                safe_value(row, "ema9")
            ),
            "MA20": fmt_price(
                safe_value(row, "ma20")
            ),
    "OBV": fmt_number(
        safe_value(row, "obv")
),

    "score": score,

    "Sell Score":
        f"{score_color(score)} {score}",

            "Trạng thái": signal,

            "Lý do": reason,

        })

    result = pd.DataFrame(rows)

    result = result.sort_values(

        by="score",

        ascending=False,

    )
    result = result.drop(
    columns=["score"]
)
    return result.reset_index(drop=True)

# =========================================================
# ROW COLOR
# =========================================================

def row_color(row):

    signal = row["Trạng thái"]

    if "🔴" in signal:

        return [
            "background-color:#ffd9d9"
        ] * len(row)

    if "🟡" in signal:

        return [
            "background-color:#fff6cc"
        ] * len(row)

    return [
        "background-color:#ddffdd"
    ] * len(row)


# =========================================================
# SUMMARY
# =========================================================

def render_summary(df):

    total = len(df)

    sell = (
        df["Trạng thái"]
        .str.contains("🔴")
        .sum()
    )

    warning = (
        df["Trạng thái"]
        .str.contains("🟡")
        .sum()
    )

    hold = (
        df["Trạng thái"]
        .str.contains("🟢")
        .sum()
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Theo dõi", total)

    c2.metric("🟢 Giữ", hold)

    c3.metric("🟡 Cảnh báo", warning)

    c4.metric("🔴 Bán", sell)


# =========================================================
# RENDER
# =========================================================

def render_guardian(scan_df, include_editor: bool = True):

    if include_editor:
        symbols = render_holdings_editor()
    elif HOLDINGS_WIDGET_KEY in st.session_state:
        symbols = parse_watchlist(st.session_state.get(HOLDINGS_WIDGET_KEY) or "")
    else:
        symbols = parse_watchlist(load_portfolio())

    watch_df = build_watchlist_df(
        scan_df,
        symbols,
    )

    if watch_df.empty:

        if include_editor:
            st.info(
                "Không có cổ phiếu trong Watchlist."
            )

        return

    if not include_editor:
        st.subheader("🛡️ POSITION GUARDIAN")
        st.caption("Theo dõi trạng thái các cổ phiếu đang nắm giữ")

    result = build_position_table(
        watch_df
    )

    render_summary(result)

    st.dataframe(

        result.style.apply(
            row_color,
            axis=1,
        ),

        use_container_width=True,

        hide_index=True,

    )

    st.caption(

        "🟢 Giữ  |  🟡 Giá dưới EMA9  |  🔴 EMA9 dưới MA20"

    )



