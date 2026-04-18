import os
import io
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Scanner Gà Chiến V15.2", layout="wide")

# ======================
# HEADER
# ======================
st.title("🐔 Scanner Gà Chiến V15.2 – Stable No-Crash")
st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# ======================
# SIDEBAR
# ======================
st.sidebar.header("Thiết lập")
market_score = st.sidebar.slider("Market Score", 1.0, 10.0, 8.0, 0.5)
top_n = st.sidebar.slider("Top cổ phiếu", 5, 30, 10)

st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader("Upload stock_data.csv", type=["csv"])

# ======================
# DATA INPUT
# ======================
st.subheader("Nguồn dữ liệu")

csv_text = st.text_area(
    "Hoặc dán CSV vào đây",
    value="",
    height=140,
    placeholder=(
        "Ví dụ:\n"
        "Ticker,OBV_trend,Price_vs_EMA,RSI,MACD\n"
        "VCI,strong,above_ema9,66,bullish\n"
        "HDB,strong,near_ema9,61,bullish"
    ),
)

# ======================
# FALLBACK DEMO DATA
# ======================
def get_demo_data():
    return pd.DataFrame([
        {"Ticker": "VCI", "OBV_trend": "strong", "Price_vs_EMA": "above_ema9", "RSI": 66, "MACD": "bullish"},
        {"Ticker": "HDB", "OBV_trend": "strong", "Price_vs_EMA": "near_ema9", "RSI": 61, "MACD": "bullish"},
        {"Ticker": "NTL", "OBV_trend": "strong", "Price_vs_EMA": "near_ema9", "RSI": 63, "MACD": "neutral"},
        {"Ticker": "DPR", "OBV_trend": "strong", "Price_vs_EMA": "near_ema9", "RSI": 68, "MACD": "neutral"},
        {"Ticker": "BCM", "OBV_trend": "medium", "Price_vs_EMA": "above_ema9", "RSI": 64, "MACD": "bullish"},
        {"Ticker": "FTS", "OBV_trend": "medium", "Price_vs_EMA": "above_ema9", "RSI": 62, "MACD": "bullish"},
        {"Ticker": "DGW", "OBV_trend": "medium", "Price_vs_EMA": "above_ema9", "RSI": 58, "MACD": "neutral"},
        {"Ticker": "MSB", "OBV_trend": "recover", "Price_vs_EMA": "near_ema9", "RSI": 54, "MACD": "neutral"},
        {"Ticker": "PVS", "OBV_trend": "recover", "Price_vs_EMA": "near_ema9", "RSI": 52, "MACD": "neutral"},
        {"Ticker": "VHM", "OBV_trend": "weak", "Price_vs_EMA": "below_ma20", "RSI": 45, "MACD": "bearish"},
    ])

# ======================
# LOAD DATA
# ======================
def load_data():
    # 1) file local
    if os.path.exists("stock_data.csv"):
        try:
            df = pd.read_csv("stock_data.csv")
            return df, "Đang dùng file local: stock_data.csv"
        except Exception as e:
            st.warning(f"Đọc file local lỗi: {e}")

    # 2) uploaded file
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            return df, "Đang dùng file upload"
        except Exception as e:
            st.warning(f"Đọc file upload lỗi: {e}")

    # 3) pasted csv text
    if csv_text.strip():
        try:
            df = pd.read_csv(io.StringIO(csv_text.strip()))
            return df, "Đang dùng dữ liệu dán tay"
        except Exception as e:
            st.warning(f"Đọc dữ liệu dán tay lỗi: {e}")

    # 4) demo fallback
    return get_demo_data(), "Đang dùng DEMO MODE vì chưa có dữ liệu thật"

df, source_note = load_data()

# ======================
# NORMALIZE COLUMNS
# ======================
df.columns = [str(c).strip() for c in df.columns]

required_cols = ["Ticker", "OBV_trend", "Price_vs_EMA", "RSI", "MACD"]
missing_cols = [c for c in required_cols if c not in df.columns]

if missing_cols:
    st.error("Thiếu cột bắt buộc: " + ", ".join(missing_cols))
    st.write("Cột hiện có trong file:", list(df.columns))
    st.stop()

# Clean dữ liệu
df = df.copy()
df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
df["OBV_trend"] = df["OBV_trend"].astype(str).str.strip().str.lower()
df["Price_vs_EMA"] = df["Price_vs_EMA"].astype(str).str.strip().str.lower()
df["MACD"] = df["MACD"].astype(str).str.strip().str.lower()
df["RSI"] = pd.to_numeric(df["RSI"], errors="coerce")
df = df.dropna(subset=["Ticker", "RSI"]).drop_duplicates(subset=["Ticker"]).reset_index(drop=True)

# ======================
# MAP GIÁ TRỊ VỀ CHUẨN
# ======================
def map_obv(x):
    if x in ["strong", "manh", "mạnh", "up", "bullish"]:
        return "strong"
    if x in ["medium", "vua", "vừa", "flat", "neutral"]:
        return "medium"
    if x in ["recover", "dao chieu", "đảo chiều", "reversal"]:
        return "recover"
    return "weak"

def map_price(x):
    if x in ["above_ema9", "above ema9", "tren ema9", "trên ema9"]:
        return "above_ema9"
    if x in ["near_ema9", "near ema9", "gan ema9", "gần ema9", "pull_ema9"]:
        return "near_ema9"
    return "below_ma20"

def map_macd(x):
    if x in ["bullish", "bull", "duong", "dương", "positive"]:
        return "bullish"
    if x in ["neutral", "flat", "trung tinh", "trung tính"]:
        return "neutral"
    return "bearish"

df["OBV_trend"] = df["OBV_trend"].apply(map_obv)
df["Price_vs_EMA"] = df["Price_vs_EMA"].apply(map_price)
df["MACD"] = df["MACD"].apply(map_macd)

# ======================
# SCORE V15 STYLE
# ======================
def score(row):
    s = 0

    # OBV
    if row["OBV_trend"] == "strong":
        s += 3
    elif row["OBV_trend"] == "medium":
        s += 2
    elif row["OBV_trend"] == "recover":
        s += 1

    # PRICE
    if row["Price_vs_EMA"] == "above_ema9":
        s += 3
    elif row["Price_vs_EMA"] == "near_ema9":
        s += 1

    # RSI
    if row["RSI"] >= 65:
        s += 2
    elif row["RSI"] >= 55:
        s += 1

    # MACD
    if row["MACD"] == "bullish":
        s += 2
    elif row["MACD"] == "neutral":
        s += 1

    return s

df["Score"] = df.apply(score, axis=1)

# ======================
# CLASSIFY
# ======================
def classify(row):
    if row["Score"] >= 8 and row["OBV_trend"] == "strong" and row["Price_vs_EMA"] != "below_ma20":
        return "🟩 ƯU TIÊN MUA"
    elif row["Score"] >= 6:
        return "🟨 THEO DÕI"
    elif row["Score"] >= 4:
        return "🟦 ĐẢO CHIỀU SỚM"
    else:
        return "🟥 LOẠI"

df["State"] = df.apply(classify, axis=1)

# ======================
# GOLD SCORE
# ======================
if market_score >= 8:
    df["GoldScore"] = (df["Score"] * market_score).round(2)
else:
    df["GoldScore"] = 0.0

# ======================
# ACTION
# ======================
def action_text(row):
    if market_score < 8:
        return "Đứng ngoài / quan sát"

    if row["State"] == "🟩 ƯU TIÊN MUA":
        return "Canh mua thăm dò / pull đẹp"
    if row["State"] == "🟨 THEO DÕI":
        return "Theo dõi chờ xác nhận"
    if row["State"] == "🟦 ĐẢO CHIỀU SỚM":
        return "Quan sát thêm"
    return "Loại"

df["Action"] = df.apply(action_text, axis=1)

# ======================
# REASON
# ======================
def reason_text(row):
    parts = []

    if row["OBV_trend"] == "strong":
        parts.append("OBV khỏe")
    elif row["OBV_trend"] == "medium":
        parts.append("OBV vừa")
    elif row["OBV_trend"] == "recover":
        parts.append("OBV hồi")
    else:
        parts.append("OBV yếu")

    if row["Price_vs_EMA"] == "above_ema9":
        parts.append("giá trên EMA9")
    elif row["Price_vs_EMA"] == "near_ema9":
        parts.append("giá gần EMA9")
    else:
        parts.append("giá dưới MA20")

    parts.append(f"RSI {row['RSI']:.1f}")

    if row["MACD"] == "bullish":
        parts.append("MACD dương")
    elif row["MACD"] == "neutral":
        parts.append("MACD trung tính")
    else:
        parts.append("MACD âm")

    return " | ".join(parts)

df["Reason"] = df.apply(reason_text, axis=1)

# ======================
# SORT
# ======================
state_order = {
    "🟩 ƯU TIÊN MUA": 4,
    "🟨 THEO DÕI": 3,
    "🟦 ĐẢO CHIỀU SỚM": 2,
    "🟥 LOẠI": 1,
}
df["StateRank"] = df["State"].map(state_order)

df = df.sort_values(
    by=["GoldScore", "StateRank", "Score", "RSI", "Ticker"],
    ascending=[False, False, False, False, True]
).reset_index(drop=True)

strong = df[df["State"] == "🟩 ƯU TIÊN MUA"].copy()
watch = df[df["State"] == "🟨 THEO DÕI"].copy()
early = df[df["State"] == "🟦 ĐẢO CHIỀU SỚM"].copy()

# ======================
# SOURCE NOTE
# ======================
if "DEMO MODE" in source_note:
    st.warning(source_note)
else:
    st.success(source_note)

# ======================
# METRICS
# ======================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tổng số mã", len(df))
c2.metric("Ưu tiên mua", len(strong))
c3.metric("Theo dõi", len(watch))
c4.metric("Đảo chiều sớm", len(early))

st.markdown("---")

# ======================
# MAIN TABLES
# ======================
tab1, tab2, tab3 = st.tabs(["🏆 Top cổ phiếu", "🔥 Ưu tiên mua", "📋 Toàn bộ dữ liệu"])

with tab1:
    st.dataframe(
        df[["Ticker", "Score", "GoldScore", "State", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "Reason", "Action"]].head(top_n),
        use_container_width=True,
        hide_index=True
    )

with tab2:
    if strong.empty:
        st.info("Chưa có mã nào đạt chuẩn ƯU TIÊN MUA.")
    else:
        st.dataframe(
            strong[["Ticker", "Score", "GoldScore", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "Reason", "Action"]].head(top_n),
            use_container_width=True,
            hide_index=True
        )

with tab3:
    st.dataframe(
        df[["Ticker", "Score", "GoldScore", "State", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "Reason", "Action"]],
        use_container_width=True,
        hide_index=True
    )

# ======================
# GUIDE
# ======================
with st.expander("Hướng dẫn format CSV"):
    st.code(
        "Ticker,OBV_trend,Price_vs_EMA,RSI,MACD\n"
        "VCI,strong,above_ema9,66,bullish\n"
        "HDB,strong,near_ema9,61,bullish\n"
        "NTL,strong,near_ema9,63,neutral\n",
        language="csv"
    )

st.caption("V15.2 | Ưu tiên ổn định, không crash | Có local file / upload / paste CSV / demo fallback")
