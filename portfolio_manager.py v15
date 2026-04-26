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

# ================= YAHOO DATA =================
@st.cache_data(ttl=300)
def get_history(code):
    try:
        ticker = yf.Ticker(f"{code}.VN")
        df = ticker.history(period="9mo", interval="1d")
        if df is None or df.empty or len(df) < 60:
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

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_ema9 = rsi.ewm(span=9, adjust=False).mean()

    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    obv_ema9 = obv.ewm(span=9, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    vol_ma20 = volume.rolling(20).mean()

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
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

# ================= UNIT FIX =================
def normalize_units(ind, buy):
    price = ind["price"]

    # Nếu Yahoo trả đồng nhưng anh nhập nghìn
    if price > 1000 and buy < 1000:
        factor = 1000
    # Nếu anh nhập đồng nhưng Yahoo trả nghìn
    elif price < 1000 and buy > 1000:
        factor = 1 / 1000
    else:
        factor = 1

    if factor == 1000:
        for k in ["price", "ema9", "ema20", "atr14", "low_recent"]:
            ind[k] = ind[k] / 1000
    elif factor == 1 / 1000:
        for k in ["price", "ema9", "ema20", "atr14", "low_recent"]:
            ind[k] = ind[k] * 1000

    return ind

# ================= SCORE 5 TRỤC =================
def score_5_axis(ind):
    price_ok = ind["price"] > ind["ema9"] and ind["ema9"] >= ind["ema20"]
    rsi_ok = ind["rsi"] >= 55 and ind["rsi"] >= ind["rsi_ema9"]
    obv_ok = ind["obv"] >= ind["obv_ema9"]
    macd_ok = ind["macd"] >= ind["signal"] and ind["hist"] >= ind["hist_prev"]
    vol_ok = ind["volume"] >= ind["vol_ma20"] * 0.8

    score = 0
    if price_ok:
        score += 2.5
    elif ind["price"] >= ind["ema20"]:
        score += 1.2

    if rsi_ok:
        score += 2
    elif ind["rsi"] >= 50:
        score += 1

    if obv_ok:
        score += 3

    if macd_ok:
        score += 1.5

    if vol_ok:
        score += 1

    return round(score, 2), price_ok, rsi_ok, obv_ok, macd_ok, vol_ok

def tech_status(score):
    if score >= 8.5:
        return "🟢 Gà chiến"
    elif score >= 7:
        return "🔵 Gà sắp chạy"
    elif score >= 5.5:
        return "🟡 Gà nghỉ khỏe"
    elif score >= 4:
        return "🟠 Yếu dần"
    return "🔴 Gãy kỹ thuật"

# ================= STOP ENGINE 2.0 =================
def stop_engine_2(ind, status, buy):
    price = ind["price"]
    ema9 = ind["ema9"]
    ema20 = ind["ema20"]
    atr = ind["atr14"]
    low_recent = ind["low_recent"]

    stop_atr = price - 1.2 * atr
    stop_ema9 = ema9
    stop_struct = low_recent - 0.5 * atr
    stop_ma20 = ema20 - 0.8 * atr

    if "🟢" in status:
        stop = max(stop_ema9, stop_atr, stop_struct)
        rule = "Trailing sát: MAX(EMA9, Price-1.2ATR, đáy gần nhất-0.5ATR)"
        return round(stop, 2), rule

    if "🔵" in status:
        stop = max(buy * 0.98, stop_atr)
        rule = "Sắp chạy: stop bảo vệ gần điểm mua / ATR"
        return round(stop, 2), rule

    if "🟡" in status:
        stop = min(stop_ma20, stop_struct)
        rule = "Gà nghỉ: stop theo MA20/đáy nền, tránh quét oan"
        return round(stop, 2), rule

    if "🟠" in status:
        stop = max(price * 0.98, stop_atr)
        rule = "Yếu dần: siết stop sát, không bình quân giá"
        return round(stop, 2), rule

    return "-", "Gãy kỹ thuật: ưu tiên thoát"

# ================= DECISION =================
def decision_engine(pnl, score, status, ind, buy):
    stop, stop_rule = stop_engine_2(ind, status, buy)
    price = ind["price"]

    if "🟢" in status:
        action = "GIỮ / CÓ THỂ TĂNG"
        risk = "Thấp"
        note = "5 trục mạnh → giữ gà, trailing theo Stop Engine 2.0"

    elif "🔵" in status:
        action = "SOI CHART / CANH TĂNG NHẸ"
        risk = "Thấp-Trung bình"
        note = "Sắp chuyển pha → chỉ tăng khi chart xác nhận"

    elif "🟡" in status:
        if pnl <= -5:
            action = "SIẾT STOP"
            risk = "Trung bình-Cao"
            note = "Nghỉ khỏe nhưng PnL xấu → không chủ quan"
        else:
            action = "THEO DÕI"
            risk = "Trung bình"
            note = "Gà nghỉ khỏe → chưa bán vội"

    elif "🟠" in status:
        action = "GIẢM / SIẾT STOP"
        risk = "Cao"
        note = "5 trục yếu dần → không bình quân giá"

    else:
        action = "BÁN / THOÁT"
        risk = "Rất cao"
        note = "Gãy kỹ thuật → bảo vệ vốn trước"

    # cảnh báo chạm stop
    if stop != "-" and price <= stop:
        action = "CHẠM STOP / XỬ LÝ NGAY"
        risk = "Rất cao"
        note = "Giá đã chạm/vượt stop động → ưu tiên xử lý"

    return action, stop, stop_rule, risk, note

# ================= SIDEBAR =================
st.sidebar.header("📥 Nhập danh mục")
raw = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nMSB,12600,4\nVJC,172800,6",
    height=160
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
    st.sidebar.success("✅ Đã lưu danh mục")

# ================= MAIN =================
df_input = load_data()
st.subheader("📊 Danh mục hiện tại – V15")

if df_input.empty:
    st.info("👉 Chưa có danh mục")
else:
    rows = []

    for _, r in df_input.iterrows():
        code = r["Mã"]
        buy = float(r["Giá mua"])
        nav = float(r["%NAV"])

        hist_df = get_history(code)

        if hist_df is None:
            rows.append({
                "Mã": code,
                "Giá mua": buy,
                "Giá hiện tại": None,
                "%NAV": nav,
                "Trạng thái": "⚠️ Lỗi data",
                "Hành động": "Check mã / nguồn dữ liệu"
            })
            continue

        ind = calc_indicators(hist_df)
        ind = normalize_units(ind, buy)

        pnl = (ind["price"] - buy) / buy * 100

        score, price_ok, rsi_ok, obv_ok, macd_ok, vol_ok = score_5_axis(ind)
        status = tech_status(score)

        action, stop, stop_rule, risk, note = decision_engine(pnl, score, status, ind, buy)

        rows.append({
            "Mã": code,
            "Giá mua": buy,
            "Giá hiện tại": round(ind["price"], 2),
            "%NAV": nav,
            "% Lãi/Lỗ": round(pnl, 2),
            "Điểm 5 trục": score,
            "Trạng thái": status,
            "Giá_OK": "✅" if price_ok else "❌",
            "RSI": round(ind["rsi"], 1),
            "RSI_OK": "✅" if rsi_ok else "❌",
            "OBV_OK": "✅" if obv_ok else "❌",
            "MACD_OK": "✅" if macd_ok else "❌",
            "VOL_OK": "✅" if vol_ok else "❌",
            "Stop Engine 2.0": stop,
            "Luật stop": stop_rule,
            "Hành động": action,
            "Rủi ro": risk,
            "Ghi chú": note
        })

    result = pd.DataFrame(rows)
    st.dataframe(result, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("📈 Lãi/Lỗ TB (%)", round(result["% Lãi/Lỗ"].mean(), 2))
    c2.metric("🔥 Điểm 5 trục TB", round(result["Điểm 5 trục"].mean(), 2))
    c3.metric("💰 Tổng %NAV", round(result["%NAV"].sum(), 2))

    st.subheader("🚨 Cảnh báo nhanh")
    for _, row in result.iterrows():
        action = row.get("Hành động", "")
        if "CHẠM STOP" in action or "BÁN" in action:
            st.error(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "SIẾT" in action or "GIẢM" in action:
            st.warning(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "CANH" in action:
            st.info(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "GIỮ" in action:
            st.success(f"{row['Mã']} → {row['Trạng thái']} → {action}")
