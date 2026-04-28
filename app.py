import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến PRO", layout="wide")

# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=300)
def load_data(symbol):
    df = yf.download(symbol + ".VN", period="3mo", interval="1d", progress=False)
    if df.empty:
        return None
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["MA20"] = df["Close"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    df["OBV"] = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
    df["OBV_EMA"] = df["OBV"].ewm(span=9).mean()

    return df


# =========================
# SCORE
# =========================
def score_stock(df):
    last = df.iloc[-1]

    score = 0

    # Giá
    if last["Close"] > last["EMA9"]:
        score += 2

    if last["EMA9"] > last["MA20"]:
        score += 1

    # RSI
    if last["RSI"] > 55:
        score += 2

    # OBV
    if last["OBV"] > last["OBV_EMA"]:
        score += 3

    # Bonus
    if last["RSI"] > 65:
        score += 2

    return score


# =========================
# PHÂN LOẠI
# =========================
def classify(df):
    last = df.iloc[-1]

    dist = (last["Close"] - last["EMA9"]) / last["EMA9"] * 100

    if dist < 1:
        return "PULL ĐẸP"
    elif dist < 3:
        return "PULL VỪA"
    elif dist > 5:
        return "CP MẠNH"
    else:
        return "MUA EARLY"


# =========================
# STOP ENGINE
# =========================
def stop_engine(df):
    last = df.iloc[-1]
    return round(last["EMA9"] * 0.98)


# =========================
# BUY LOGIC
# =========================
def buy_logic(score, group, price, ema9, market_ok):

    if not market_ok:
        return "🔴 KHÔNG MUA", "-", "0%"

    if group == "PULL ĐẸP":
        return "🟢 MUA PULL", f"{round(ema9)}", "15-20%"

    if group == "PULL VỪA":
        return "🟡 MUA NHỎ", f"{round(ema9)}", "5-10%"

    if group == "MUA EARLY" and score >= 6:
        return "🟡 TEST EARLY", f"{round(price)}", "5-10%"

    if group == "CP MẠNH":
        return "🟡 CHỜ PULL", f"Canh EMA9", "0%"

    return "🔴 KHÔNG MUA", "-", "0%"


# =========================
# UI
# =========================
st.title("🐔 Scanner Gà Chiến + Quản trị danh mục V25")

st.markdown("Anh nhập: Mã,Giá mua,%NAV")

input_text = st.text_area(
    "",
    "BAF,36600,4.5\nCII,19100,5\nDXG,15000,4"
)

rows = []

market_ok = True  # có thể nâng cấp sau

for line in input_text.strip().split("\n"):
    try:
        symbol, buy, nav = line.split(",")
        buy = float(buy)
        nav = float(nav)

        df = load_data(symbol)
        if df is None:
            continue

        last = df.iloc[-1]

        price = float(last["Close"])
        ema9 = float(last["EMA9"])

        score = score_stock(df)
        group = classify(df)
        stop = stop_engine(df)

        action, buy_zone, buy_nav = buy_logic(
            score, group, price, ema9, market_ok
        )

        pnl = (price - buy) / buy * 100

        rows.append({
            "Mã": symbol,
            "Giá mua": buy,
            "Giá hiện tại": round(price),
            "% Lãi/Lỗ": round(pnl, 2),
            "%NAV": nav,
            "Điểm": score,
            "Nhóm": group,
            "Stop": stop,
            "Khuyến nghị": action,
            "Vùng mua": buy_zone,
            "NAV gợi ý": buy_nav
        })

    except:
        continue


df_result = pd.DataFrame(rows)

# =========================
# OUTPUT
# =========================
st.markdown("## 📊 QUẢN TRỊ DANH MỤC")

if not df_result.empty:
    st.dataframe(df_result, use_container_width=True)
else:
    st.warning("Chưa có dữ liệu")
