# =========================================================
# SCANNER GÀ CHIẾN V18.4 + SLOPE (FULL CLEAN)
# =========================================================

import time
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# ================= PAGE =================
st.set_page_config(page_title="Scanner Gà Chiến V18.4 SLOPE", layout="wide")
st.title("🐔 Scanner Gà Chiến V18.4 + SLOPE")

# ================= CONFIG =================
WATCHLIST = ["VND","SSI","MBB","VPB","GEX","VIX","FPT","MWG","HPG","GVR","DIG","DXG"]
SUFFIX = ".VN"

# ================= INDICATORS =================
def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def sma(series, window):
    return series.rolling(window).mean()

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period).mean()
    avg_loss = loss.ewm(alpha=1/period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()

# ================= BUILD =================
def build_indicators(df):
    x = df.copy()

    x["ema9"] = ema(x["Close"], 9)
    x["ma20"] = sma(x["Close"], 20)

    # 🔥 SLOPE (CORE)
    x["slope"] = (x["ema9"] - x["ma20"]) / x["ma20"] * 100
    x["slope_change"] = x["slope"] - x["slope"].shift(3)

    x["rsi"] = calc_rsi(x["Close"])
    x["rsi_slope"] = x["rsi"].diff()

    x["obv"] = calc_obv(x["Close"], x["Volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    x["vol_ma20"] = sma(x["Volume"], 20)

    return x

# ================= SCORE =================
def score_row(row, prev):
    score = 0

    # Price
    if row["Close"] > row["ema9"] > row["ma20"]:
        score += 2
    elif row["Close"] > row["ema9"]:
        score += 1

    # RSI
    if row["rsi"] > 65 and row["rsi_slope"] > 0:
        score += 2
    elif row["rsi"] > 55:
        score += 1

    # OBV
    if row["obv"] > row["obv_ema9"] and row["obv"] > prev["obv"]:
        score += 2
    elif row["obv"] > row["obv_ema9"]:
        score += 1

    return score

# ================= CLASSIFY =================
def classify(row):
    slope = row["slope"]
    rsi = row["rsi"]
    obv_ok = row["obv"] >= row["obv_ema9"]
    price = row["Close"]
    ema9 = row["ema9"]
    ma20 = row["ma20"]

    if slope > 2 and rsi > 60 and obv_ok and price > ema9 > ma20:
        return "🟢 GÀ TĂNG TỐC"

    if slope > 0 and rsi > 55 and obv_ok and price > ema9:
        return "🟡 GÀ KHỎE"

    return "🔴 YẾU"

# ================= ANALYZE =================
def analyze(symbol):
    try:
        df = yf.download(symbol + SUFFIX, period="6mo", progress=False)
        if df.empty or len(df) < 30:
            return None

        df = build_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        score = score_row(last, prev)

        return {
            "Symbol": symbol,
            "Price": round(last["Close"],0),
            "EMA9": round(last["ema9"],2),
            "MA20": round(last["ma20"],2),
            "Slope %": round(last["slope"],2),
            "Slope Δ": round(last["slope_change"],2),
            "RSI": round(last["rsi"],2),
            "RSI slope": round(last["rsi_slope"],2),
            "OBV": "🟢" if last["obv"] >= last["obv_ema9"] else "🔴",
            "Score": score,
            "Signal": classify(last)
        }

    except:
        return None

# ================= RUN =================
rows = []
for sym in WATCHLIST:
    data = analyze(sym)
    if data:
        rows.append(data)

df = pd.DataFrame(rows)

# ================= SORT =================
df = df.sort_values(by=["Slope %","Score"], ascending=[False,False])

# ================= MARKET =================
market_score = round(df["Score"].mean(),1) if not df.empty else 0

st.metric("Market Score", market_score)

# ================= DISPLAY =================
st.subheader("📊 TOÀN BỘ DANH SÁCH")
st.dataframe(df, use_container_width=True)

# ================= TOP =================
st.subheader("🐔 GÀ TĂNG TỐC")

top = df[df["Signal"] == "🟢 GÀ TĂNG TỐC"]

if top.empty:
    st.warning("Không có gà tăng tốc")
else:
    st.dataframe(top, use_container_width=True)

# ================= INFO =================
st.markdown("""
### 🧠 LOGIC:
- Slope > 2% → dòng tiền đẩy mạnh
- RSI > 60 → động lượng
- OBV xanh → chưa phân phối
👉 = gà chuẩn bị chạy mạnh
""")
