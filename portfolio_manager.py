import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio Manager PRO V15", layout="wide")
st.title("🐔 Portfolio Manager PRO V15 – 5 Trục + Stop Engine 2.0")

DATA_FILE = "portfolio.csv"

# ================= LOAD / SAVE =================
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            df = pd.read_csv(DATA_FILE)
            if {"Mã", "Giá mua", "%NAV"}.issubset(df.columns):
                return df
    except:
        pass
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= GET DATA (YAHOO) =================
@st.cache_data(ttl=300)
def get_history(code):
    try:
        ticker = yf.Ticker(f"{code}.VN")
        df = ticker.history(period="6mo", interval="1d")

        # fallback nếu VN lỗi
        if df is None or df.empty:
            ticker = yf.Ticker(code)
            df = ticker.history(period="6mo", interval="1d")

        if df is None or df.empty or len(df) < 30:
            return None

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        return df[["open", "high", "low", "close", "volume"]].dropna()

    except:
        return None

# ================= INDICATORS =================
def calc_indicators(df):
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ema9 = close.ewm(span=9).mean()
    ema20 = close.ewm(span=20).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_ema9 = rsi.ewm(span=9).mean()

    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    obv_ema9 = obv.ewm(span=9).mean()

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    hist = macd - signal

    vol_ma20 = volume.rolling(20).mean()

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr14 = tr.rolling(14).mean()

    return {
        "price": float(close.iloc[-1]),
        "ema9": float(ema9.iloc[-1]),
        "ema20": float(ema20.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "rsi_ema9": float(rsi_ema9.iloc[-1]),
        "obv": float(obv.iloc[-1]),
        "obv_ema9": float(obv_ema9.iloc[-1]),
        "macd": float(macd.iloc[-1]),
        "signal": float(signal.iloc[-1]),
        "hist": float(hist.iloc[-1]),
        "hist_prev": float(hist.iloc[-2]),
        "volume": float(volume.iloc[-1]),
        "vol_ma20": float(vol_ma20.iloc[-1]),
        "atr14": float(atr14.iloc[-1]),
        "low_recent": float(low.tail(10).min())
    }

# ================= SCORE =================
def score_5_axis(ind):
    score = 0

    if ind["price"] > ind["ema9"] >= ind["ema20"]:
        score += 2.5
    elif ind["price"] >= ind["ema20"]:
        score += 1.2

    if ind["rsi"] >= 55 and ind["rsi"] >= ind["rsi_ema9"]:
        score += 2
    elif ind["rsi"] >= 50:
        score += 1

    if ind["obv"] >= ind["obv_ema9"]:
        score += 3

    if ind["macd"] >= ind["signal"]:
        score += 1.5

    if ind["volume"] >= ind["vol_ma20"] * 0.8:
        score += 1

    return round(score, 2)

def tech_status(score):
    if score >= 8.5:
        return "🟢 Gà chiến"
    elif score >= 7:
        return "🔵 Sắp chạy"
    elif score >= 5.5:
        return "🟡 Nghỉ khỏe"
    elif score >= 4:
        return "🟠 Yếu"
    return "🔴 Gãy"

# ================= SIDEBAR =================
st.sidebar.header("📥 Nhập danh mục")

raw = st.sidebar.text_area(
    "Format: Mã,Giá,%NAV\nVD:\nMBB,27000,5",
    height=150
)

if st.sidebar.button("💾 Lưu danh mục"):
    rows = []
    for line in raw.split("\n"):
        parts = line.split(",")
        if len(parts) == 3:
            try:
                rows.append({
                    "Mã": parts[0].strip().upper(),
                    "Giá mua": float(parts[1]),
                    "%NAV": float(parts[2])
                })
            except:
                pass

    df_save = pd.DataFrame(rows)
    save_data(df_save)
    st.sidebar.success("✅ Đã lưu")

# ================= MAIN =================
df = load_data()

st.subheader("📊 Danh mục hiện tại")

if df.empty:
    st.info("👉 Chưa có dữ liệu")
else:
    result = []

    for _, r in df.iterrows():
        code = r["Mã"]
        buy = r["Giá mua"]
        nav = r["%NAV"]

        hist = get_history(code)

        if hist is None:
            result.append({
                "Mã": code,
                "Giá hiện tại": "Lỗi data",
                "%NAV": nav
            })
            continue

        ind = calc_indicators(hist)
        pnl = (ind["price"] - buy) / buy * 100
        score = score_5_axis(ind)
        status = tech_status(score)

        result.append({
            "Mã": code,
            "Giá mua": buy,
            "Giá hiện tại": round(ind["price"], 2),
            "%NAV": nav,
            "%Lãi/Lỗ": round(pnl, 2),
            "Điểm": score,
            "Trạng thái": status
        })

    df_out = pd.DataFrame(result)
    st.dataframe(df_out, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Lãi/Lỗ TB (%)", round(df_out["%Lãi/Lỗ"].mean(), 2))
    c2.metric("Điểm TB", round(df_out["Điểm"].mean(), 2))
    c3.metric("Tổng NAV", round(df_out["%NAV"].sum(), 2))
