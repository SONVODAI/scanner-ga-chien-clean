import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio Manager PRO V14", layout="wide")
st.title("🐔 Portfolio Manager PRO V14 – 5 Trục Gà Chiến")

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

# ================= DATA =================
@st.cache_data(ttl=300)
def get_history(code):
    try:
        ticker = yf.Ticker(f"{code}.VN")
        df = ticker.history(period="9mo", interval="1d")
        if df is None or df.empty or len(df) < 50:
            return None
        df = df.rename(columns={"Close": "close", "Volume": "volume", "High": "high", "Low": "low"})
        return df[["high", "low", "close", "volume"]].dropna()
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

    price = float(close.iloc[-1])

    return {
        "price": price,
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
        "atr14": float(atr14.iloc[-1])
    }

# ================= SCORE 5 TRỤC =================
def score_5_axis(ind):
    score = 0

    price_ok = ind["price"] > ind["ema9"] and ind["ema9"] >= ind["ema20"]
    rsi_ok = ind["rsi"] >= 55 and ind["rsi"] >= ind["rsi_ema9"]
    obv_ok = ind["obv"] >= ind["obv_ema9"]
    macd_ok = ind["macd"] >= ind["signal"] and ind["hist"] >= ind["hist_prev"]
    vol_ok = ind["volume"] >= ind["vol_ma20"] * 0.8

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

# ================= DECISION =================
def decision_engine(pnl, score, status, ind, buy):
    atr_stop = ind["price"] - 1.2 * ind["atr14"]

    if "🟢" in status:
        return "GIỮ / CÓ THỂ TĂNG", round(max(ind["ema9"], atr_stop), 2), "Thấp", "5 trục mạnh → không bán vì rung lắc nhỏ"

    if "🔵" in status:
        return "SOI CHART / CANH TĂNG NHẸ", round(max(buy * 0.98, atr_stop), 2), "Thấp-Trung bình", "Sắp chuyển pha → cần xác nhận chart"

    if "🟡" in status:
        if pnl <= -5:
            return "SIẾT STOP", round(ind["price"] * 0.98, 2), "Trung bình-Cao", "Đang nghỉ nhưng lỗ sâu hơn ngưỡng an toàn"
        return "THEO DÕI", round(buy * 0.95, 2), "Trung bình", "Gà nghỉ khỏe → chưa bán vội"

    if "🟠" in status:
        return "GIẢM / SIẾT STOP", round(ind["price"] * 0.98, 2), "Cao", "5 trục yếu dần → không bình quân giá"

    return "BÁN / THOÁT", "-", "Rất cao", "Gãy kỹ thuật → ưu tiên bảo vệ vốn"

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
st.subheader("📊 Danh mục hiện tại – 5 Trục")

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
        price = ind["price"]

        # Đồng bộ đơn vị: nếu giá mua nhập theo nghìn nhưng Yahoo trả đồng, tự chỉnh
        if price > 1000 and buy < 1000:
            price_for_calc = price / 1000
            ind["price"] = price_for_calc
            ind["ema9"] = ind["ema9"] / 1000
            ind["ema20"] = ind["ema20"] / 1000
            ind["atr14"] = ind["atr14"] / 1000
        else:
            price_for_calc = price

        pnl = (price_for_calc - buy) / buy * 100

        score, price_ok, rsi_ok, obv_ok, macd_ok, vol_ok = score_5_axis(ind)
        status = tech_status(score)
        action, stop, risk, note = decision_engine(pnl, score, status, ind, buy)

        rows.append({
            "Mã": code,
            "Giá mua": buy,
            "Giá hiện tại": round(price_for_calc, 2),
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
            "Hành động": action,
            "Stop gợi ý": stop,
            "Rủi ro": risk,
            "Ghi chú": note
        })

    result = pd.DataFrame(rows)
    st.dataframe(result, use_container_width=True)

    if "% Lãi/Lỗ" in result.columns:
        c1, c2, c3 = st.columns(3)
        c1.metric("📈 Lãi/Lỗ TB (%)", round(result["% Lãi/Lỗ"].mean(), 2))
        c2.metric("🔥 Điểm 5 trục TB", round(result["Điểm 5 trục"].mean(), 2))
        c3.metric("💰 Tổng %NAV", round(result["%NAV"].sum(), 2))

    st.subheader("🚨 Cảnh báo nhanh")
    for _, row in result.iterrows():
        action = row.get("Hành động", "")
        if "BÁN" in action:
            st.error(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "SIẾT" in action or "GIẢM" in action:
            st.warning(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "CANH" in action:
            st.info(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "GIỮ" in action:
            st.success(f"{row['Mã']} → {row['Trạng thái']} → {action}")
