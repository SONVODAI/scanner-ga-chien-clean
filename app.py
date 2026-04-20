import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Scanner Gà Chiến", layout="wide")

# ==============================
# UTILS
# ==============================
def normalize_series(s):
    return pd.to_numeric(s, errors="coerce")

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_obv(close, volume):
    obv = [0]
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i-1]:
            obv.append(obv[-1] + volume.iloc[i])
        elif close.iloc[i] < close.iloc[i-1]:
            obv.append(obv[-1] - volume.iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=close.index)

# ==============================
# DATA
# ==============================
@st.cache_data(ttl=300)
def fetch_daily(symbol):
    return yf.download(symbol, period="6mo", progress=False)

@st.cache_data(ttl=300)
def fetch_intraday(symbol):
    return yf.download(symbol, period="5d", interval="15m", progress=False)

# ==============================
# CORE LOGIC
# ==============================
def analyze_stock(symbol):
    raw = fetch_daily(symbol)

    if raw is None or raw.empty or len(raw) < 60:
        return None

    close = normalize_series(raw["Close"]).dropna()
    high = normalize_series(raw["High"]).reindex(close.index)
    low = normalize_series(raw["Low"]).reindex(close.index)
    volume = normalize_series(raw["Volume"]).reindex(close.index)

    df = pd.DataFrame({
        "Close": close,
        "High": high,
        "Low": low,
        "Volume": volume
    }).dropna()

    if len(df) < 60:
        return None

    # ===== indicators =====
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["RSI_EMA"] = df["RSI"].ewm(span=9).mean()
    df["OBV"] = calc_obv(df["Close"], df["Volume"])
    df["OBV_EMA"] = df["OBV"].ewm(span=9).mean()
    df["VOL_MA20"] = df["Volume"].rolling(20).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close_now = latest["Close"]
    ema9 = latest["EMA9"]
    ma20 = latest["MA20"]
    rsi = latest["RSI"]
    rsi_ema = latest["RSI_EMA"]
    obv = latest["OBV"]
    obv_ema = latest["OBV_EMA"]
    vol = latest["Volume"]
    vol_ma = latest["VOL_MA20"]

    # ======================
    # TREND
    # ======================
    cond_price = close_now > ema9 > ma20
    cond_rsi = rsi > 55 and rsi > rsi_ema
    cond_obv = obv > obv_ema

    trend_ok = cond_price and cond_rsi and cond_obv

    # ======================
    # PULL
    # ======================
    recent_high = df["Close"].iloc[-10:].max()
    drawdown = (recent_high - close_now) / recent_high

    pull_ok = (
        drawdown <= 0.08
        and abs(close_now - ema9)/ema9 <= 0.03
        and vol < vol_ma
    )

    # ======================
    # BREAK
    # ======================
    prev_high = df["High"].rolling(20).max().iloc[-2]

    break_ok = (
        close_now > prev_high
        and vol > vol_ma * 1.3
        and rsi > 60
        and obv > obv_ema
    )

    # ======================
    # EARLY REVERSAL
    # ======================
    early_ok = (
        rsi > 45
        and rsi > rsi_ema
        and close_now >= ema9 * 0.99
        and obv >= obv_ema * 0.98
    )

    # ======================
    # INTRADAY CONFIRM
    # ======================
    intraday_ok = False
    try:
        intra = fetch_intraday(symbol)
        if intra is not None and not intra.empty:
            iclose = normalize_series(intra["Close"]).dropna()
            ivol = normalize_series(intra["Volume"]).reindex(iclose.index)

            if len(iclose) > 10:
                iema9 = iclose.ewm(span=9).mean()
                iobv = calc_obv(iclose, ivol)

                intraday_ok = (
                    iclose.iloc[-1] > iema9.iloc[-1]
                    and iobv.iloc[-1] > iobv.iloc[-3]
                )
    except:
        intraday_ok = False

    # ======================
    # FINAL DECISION
    # ======================
    if break_ok:
        return symbol, "🟩 BREAK"

    if trend_ok and pull_ok:
        return symbol, "🟨 PULL ĐẸP"

    if early_ok:
        return symbol, "🟦 EARLY"

    return None


# ==============================
# UI
# ==============================
st.title("🐔 Scanner Gà Chiến V18")

symbols_input = st.text_area(
    "Nhập danh sách mã (cách nhau bằng dấu phẩy)",
    "VCB, BID, CTG, MBB, VND, SSI"
)

symbols = [s.strip().upper() for s in symbols_input.split(",")]

if st.button("SCAN"):
    results = []

    for sym in symbols:
        try:
            r = analyze_stock(sym)
            if r:
                results.append(r)
        except:
            continue

    if results:
        df_out = pd.DataFrame(results, columns=["Symbol", "Signal"])
        st.dataframe(df_out)
    else:
        st.warning("Không có mã đạt điều kiện")
