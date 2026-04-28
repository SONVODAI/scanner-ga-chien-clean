import streamlit as st
import pandas as pd
import numpy as np

# =========================
# CONFIG
# =========================

WATCHLIST = [
    "VIC","VHM","VRE","NVL","TCB","CTD","GVR","SHS","VND","SSI",
    "MBB","STB","ACB","HCM","VCI","GEX","GEE","VSC","VJC","BSR"
]

MARKET_SCORE = 8.0   # Anh có thể sửa tay theo điểm thị trường
MIN_MARKET_BUY = 8.0

# =========================
# DATA LOADER
# =========================

def load_price(symbol):
    """
    Anh thay đoạn này bằng hàm lấy dữ liệu realtime/stock_historical
    đang chạy tốt trong bản cũ của anh.
    Yêu cầu output có cột:
    time, open, high, low, close, volume
    """
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(period="6M", interval="1D")
        df = df.rename(columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "time": "time"
        })
        return df
    except Exception:
        return pd.DataFrame()

# =========================
# INDICATORS
# =========================

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()

def atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def macd(close):
    macd_line = ema(close, 12) - ema(close, 26)
    signal = ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist

# =========================
# CORE BOT LOGIC
# =========================

def analyze_symbol(symbol):
    df = load_price(symbol)

    if df.empty or len(df) < 60:
        return None

    df = df.copy()
    df["EMA9"] = ema(df["close"], 9)
    df["MA20"] = df["close"].rolling(20).mean()
    df["WMA45"] = df["close"].rolling(45).mean()
    df["RSI"] = rsi(df["close"])
    df["EMA9_RSI"] = ema(df["RSI"], 9)
    df["OBV"] = obv(df["close"], df["volume"])
    df["EMA9_OBV"] = ema(df["OBV"], 9)
    df["ATR"] = atr(df)
    df["MACD"], df["MACD_SIGNAL"], df["MACD_HIST"] = macd(df["close"])
    df["VOL_MA20"] = df["volume"].rolling(20).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = last["close"]
    ema9 = last["EMA9"]
    ma20 = last["MA20"]
    wma45 = last["WMA45"]
    rsi_v = last["RSI"]
    ema9_rsi = last["EMA9_RSI"]
    obv_v = last["OBV"]
    ema9_obv = last["EMA9_OBV"]
    macd_v = last["MACD"]
    macd_sig = last["MACD_SIGNAL"]
    hist = last["MACD_HIST"]
    atr_v = last["ATR"]
    volume = last["volume"]
    vol_ma20 = last["VOL_MA20"]

    recent_high = df["close"].tail(20).max()
    pullback_pct = (recent_high - close) / recent_high * 100 if recent_high else 0
    dist_ema9 = (close - ema9) / ema9 * 100 if ema9 else 0
    ema9_ma20_dist = (ema9 - ma20) / ma20 * 100 if ma20 else 0

    # =========================
    # 5 TRỤC
    # =========================

    price_axis = close > ema9 > ma20
    trend_axis = ema9 > prev["EMA9"] and ma20 >= prev["MA20"]
    rsi_axis = rsi_v > 55 and rsi_v > ema9_rsi
    obv_axis = obv_v > ema9_obv
    macd_axis = macd_v > macd_sig and hist >= 0
    atr_axis = atr_v > 0

    no_hoa = (
        price_axis and
        trend_axis and
        rsi_axis and
        obv_axis and
        macd_axis
    )

    # =========================
    # SCORE CŨ + BONUS DIST
    # =========================

    score = 0

    if price_axis:
        score += 2
    if trend_axis:
        score += 1
    if rsi_axis:
        score += 2
    if obv_axis:
        score += 2
    if macd_axis:
        score += 1
    if atr_axis:
        score += 1

    bonus_dist = 0

    if 4 <= dist_ema9 <= 7:
        bonus_dist = 1 if obv_axis and rsi_axis else 0.5
    elif 3 <= dist_ema9 < 4:
        bonus_dist = 0.5
    elif 7 < dist_ema9 <= 8:
        bonus_dist = 0.5

    final_score = score + bonus_dist

    # =========================
    # BUY LOGIC
    # =========================

    buy_early = (
        MARKET_SCORE >= MIN_MARKET_BUY and
        no_hoa and
        3 <= dist_ema9 <= 5 and
        ema9_ma20_dist > 0
    )

    buy_pull = (
        MARKET_SCORE >= MIN_MARKET_BUY and
        no_hoa and
        3 <= pullback_pct <= 6 and
        close >= ema9 * 0.97 and
        volume <= vol_ma20 * 1.2 and
        obv_v >= ema9_obv
    )

    fomo_zone = (
        dist_ema9 > 8 and
        rsi_v > 75
    )

    weak_reject = (
        close < ema9 or
        rsi_v < ema9_rsi or
        obv_v < ema9_obv
    )

    # =========================
    # SIGNAL
    # =========================

    signal = "THEO DÕI"
    nav = 0

    if MARKET_SCORE < MIN_MARKET_BUY:
        signal = "CHỜ - MARKET < 8"
        nav = 0

    elif weak_reject:
        signal = "LOẠI / CHƯA MUA"
        nav = 0

    elif fomo_zone:
        signal = "FOMO - KHÔNG MUA MỚI"
        nav = 0

    elif buy_pull:
        signal = "BUY_PULL - MUA 1/2 NAV"
        nav = 50

    elif buy_early:
        signal = "BUY_EARLY - MUA 30-40% NAV"
        nav = 35

    elif no_hoa:
        signal = "GÀ CHIẾN ĐANG CHẠY - CANH PULL"
        nav = 0

    # =========================
    # STOP ENGINE 2.0
    # =========================

    stop_running = max(
        ema9,
        close - 1.2 * atr_v
    ) if not np.isnan(atr_v) else ema9

    stop_base = min(
        ma20 - 0.8 * atr_v,
        df["low"].tail(10).min() - 0.5 * atr_v
    ) if not np.isnan(atr_v) else ma20

    if no_hoa and dist_ema9 >= 4:
        stoploss = stop_running
        stop_type = "Gà chạy - trailing sát"
    elif price_axis:
        stoploss = stop_base
        stop_type = "Gà nghỉ - stop dưới nền/MA20"
    else:
        stoploss = ema9
        stop_type = "Gà yếu - stop loại trừ"

    return {
        "Mã": symbol,
        "Close": round(close, 2),
        "Score": round(final_score, 2),
        "Bonus Dist": bonus_dist,
        "Dist EMA9 %": round(dist_ema9, 2),
        "Pullback %": round(pullback_pct, 2),
        "RSI": round(rsi_v, 2),
        "OBV > EMA9": "YES" if obv_axis else "NO",
        "Pattern": "NỞ HOA" if no_hoa else "CHƯA ĐỦ",
        "Signal": signal,
        "NAV %": nav,
        "Stoploss": round(stoploss, 2),
        "Stop Type": stop_type
    }

# =========================
# STREAMLIT APP
# =========================

st.set_page_config(page_title="BOT NỞ HOA - GÀ CHIẾN", layout="wide")

st.title("🔥 BOT NỞ HOA - GÀ CHIẾN")
st.write("Market-first | 5 trục | Dist EMA9 4–7% | BUY_EARLY | BUY_PULL | Stop Engine 2.0")

market_input = st.number_input("Điểm thị trường hiện tại", value=MARKET_SCORE, step=0.1)
MARKET_SCORE = market_input

symbols_text = st.text_area(
    "Danh sách mã",
    value=",".join(WATCHLIST),
    height=100
)

symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]

if st.button("QUÉT BOT"):
    results = []

    for symbol in symbols:
        result = analyze_symbol(symbol)
        if result:
            results.append(result)

    if results:
        df_result = pd.DataFrame(results)
        df_result = df_result.sort_values(
            by=["Score", "NAV %"],
            ascending=False
        )

        st.subheader("📌 Bảng kết quả")
        st.dataframe(df_result, use_container_width=True)

        st.subheader("🟢 Mã có tín hiệu mua")
        buy_df = df_result[df_result["Signal"].str.contains("BUY", na=False)]
        st.dataframe(buy_df, use_container_width=True)

        st.subheader("🔥 Gà chiến đang chạy")
        strong_df = df_result[df_result["Pattern"] == "NỞ HOA"]
        st.dataframe(strong_df, use_container_width=True)

    else:
        st.warning("Không có dữ liệu hoặc lỗi nguồn dữ liệu.")
