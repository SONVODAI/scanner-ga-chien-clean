# =========================================================
# POSITION GUARDIAN
# Version : 1.00
#
# Mr.BOT PROJECT
#
# Sprint 1
# ----------------------------------------
# ✓ Watchlist
# ✓ EMA9
# ✓ MA20
# ✓ OBV
# ✓ Green / Yellow / Red Signal
#
# Future
# ----------------------------------------
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

DEFAULT_WATCHLIST = (
    "SSI,MBB,TCB,VPB,"
    "STB,CTG,ACB,"
    "PVD,PVS,BSR,"
    "VND,SHS,HCM"
)


# =========================================================
# SIGNAL CONSTANT
# =========================================================

SIGNAL_HOLD = "🟢 GIỮ"

SIGNAL_WARNING = "🟡 CẢNH BÁO"

SIGNAL_SELL = "🔴 BÁN"


# =========================================================
# SAFE COLUMN
# =========================================================

def safe_value(row, column, default=np.nan):

    if column not in row.index:
        return default

    return row[column]


# =========================================================
# WATCHLIST
# =========================================================

def parse_watchlist(text):

    if text is None:
        return []

    text = text.upper()

    text = text.replace("\n", ",")

    symbols = []

    for x in text.split(","):

        x = x.strip()

        if x == "":
            continue

        if x not in symbols:
            symbols.append(x)

    return symbols


# =========================================================
# FILTER DATA
# =========================================================

def build_watchlist_df(
    scan_df,
    symbols,
):

    if scan_df is None:

        return pd.DataFrame()

    if len(symbols) == 0:

        return pd.DataFrame()

    df = scan_df.copy()

    df["symbol"] = df["symbol"].astype(str)

    df = df[df["symbol"].isin(symbols)]

    return df.reset_index(drop=True)


# =========================================================
# UI HEADER
# =========================================================

def guardian_header():

    st.markdown("---")

    st.subheader("🛡️ POSITION GUARDIAN")

    st.caption(
        "Quản lý các cổ phiếu đang nắm giữ"
    )

    watch_text = st.text_area(

        "Watchlist",

        value=DEFAULT_WATCHLIST,

        height=90,

# =========================================================
# GENERATE SIGNAL
# =========================================================

def generate_signal(row):

    price = safe_value(row, "price")

    ema9 = safe_value(row, "ema9")

    ma20 = safe_value(row, "ma20")

    obv = safe_value(row, "obv")

    obv_ema9 = safe_value(row, "obv_ema9")

    signal = SIGNAL_HOLD

    reason = "Xu hướng khỏe"

    # ------------------------------------
    # SELL
    # ------------------------------------

    if (
        pd.notna(ema9)
        and pd.notna(ma20)
        and ema9 < ma20
    ):

        signal = SIGNAL_SELL

        reason = "EMA9 cắt xuống MA20"

        if (
            pd.notna(obv)
            and pd.notna(obv_ema9)
            and obv < obv_ema9
        ):

            reason += " + OBV xác nhận"

        return signal, reason

    # ------------------------------------
    # WARNING
    # ------------------------------------

    if (
        pd.notna(price)
        and pd.notna(ema9)
        and price < ema9
    ):

        signal = SIGNAL_WARNING

        reason = "Giá dưới EMA9"

        return signal, reason

    return signal, reason


# =========================================================
# BUILD POSITION TABLE
# =========================================================

def build_position_table(df):

    rows = []

    if df.empty:

        return pd.DataFrame()

    for _, row in df.iterrows():

        signal, reason = generate_signal(row)

        rows.append({

            "Mã": safe_value(row, "symbol", ""),

            "Giá": round(safe_value(row, "price"), 2),

            "EMA9": round(safe_value(row, "ema9"), 2),

            "MA20": round(safe_value(row, "ma20"), 2),

            "OBV": round(safe_value(row, "obv"), 0),

            "Trạng thái": signal,

            "Lý do": reason,

        })

    return pd.DataFrame(rows)      
    )

    return parse_watchlist(watch_text)

  # =========================================================
# COLOR ENGINE
# =========================================================

def row_color(row):

    signal = row["Trạng thái"]

    if "🔴" in signal:

        return [
            "background-color:#ffd6d6"
        ] * len(row)

    if "🟡" in signal:

        return [
            "background-color:#fff5cc"
        ] * len(row)

    return [
        "background-color:#ddffdd"
    ] * len(row)


# =========================================================
# RENDER
# =========================================================

def render_guardian(scan_df):

    symbols = guardian_header()

    watch_df = build_watchlist_df(
        scan_df,
        symbols,
    )

    if watch_df.empty:

        st.info(
            "Chưa có cổ phiếu trong Watchlist."
        )

        return

    result = build_position_table(
        watch_df
    )

    st.dataframe(

        result.style.apply(

            row_color,

            axis=1,

        ),

        use_container_width=True,

        hide_index=True,

    )

    st.caption(

        "🟢 Giữ  |  🟡 Cảnh báo  |  🔴 Bán"

    )








