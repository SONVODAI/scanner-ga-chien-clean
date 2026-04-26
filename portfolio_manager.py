import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from vnstock import Vnstock

st.set_page_config(page_title="Portfolio PRO V9", layout="wide")
st.title("🐔 Portfolio Manager PRO V9 – Kết nối Scanner Gà Chiến")

DATA_FILE = "portfolio_v9.json"

# ===== LOAD / SAVE =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# ===== VNSTOCK DATA =====
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(start="2024-01-01")
        if df is None or df.empty:
            return None
        return df
    except:
        return None

# ===== INDICATORS =====
def calc_indicators(df):
    close = df["close"]
    volume = df["volume"]

    ema9 = close.ewm(span=9).mean()

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

    return {
        "price": float(close.iloc[-1]),
        "gia_ok": int(close.iloc[-1] > ema9.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "rsi_ok": int(rsi.iloc[-1] > rsi_ema9.iloc[-1]),
        "obv_ok": int(obv.iloc[-1] > obv_ema9.iloc[-1]),
        "macd_ok": int(macd.iloc[-1] > signal.iloc[-1] and hist.iloc[-1] > hist.iloc[-2]),
        "vol_ok": int(volume.iloc[-1] >= vol_ma20.iloc[-1])
    }

# ===== SCORING =====
def score_stock(ind):
    score = 0
    if ind["gia_ok"]: score += 2
    if ind["rsi"] >= 55: score += 2
    elif ind["rsi"] >= 50: score += 1
    if ind["rsi_ok"]: score += 1
    if ind["obv_ok"]: score += 3
    if ind["macd_ok"]: score += 1.5
    if ind["vol_ok"]: score += 0.5
    return round(score, 2)

def tech_status(score):
    if score >= 8.5:
        return "🟩 Gà chiến"
    elif score >= 7:
        return "🟦 Gà sắp chạy"
    elif score >= 5.5:
        return "🟨 Gà nghỉ khỏe"
    elif score >= 4:
        return "⚠️ Yếu dần"
    return "🟥 Gãy kỹ thuật"

def decision(buy, price, score, status):
    pnl = (price - buy) / buy * 100

    if "🟩" in status and pnl >= 0:
        return pnl, "GIỮ / CÓ THỂ TĂNG", price * 0.97, "Tăng NAV nếu thị trường ủng hộ", "Thấp"
    elif "🟦" in status and pnl > -3:
        return pnl, "SOI CHART / CANH TĂNG", buy * 0.98, "Tăng nhẹ nếu chart xác nhận", "Thấp-Trung bình"
    elif "🟨" in status and pnl > -5:
        return pnl, "THEO DÕI", buy * 0.95, "Giữ nguyên", "Trung bình"
    elif "⚠️" in status or pnl <= -3:
        return pnl, "SIẾT STOP / GIẢM", price * 0.98, "Giảm 1/2 nếu không hồi", "Cao"
    return pnl, "BÁN NGAY", None, "Thoát toàn bộ", "Rất cao"

# ===== SIDEBAR =====
st.sidebar.header("1️⃣ Nhập danh mục")
input_text = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nVJC,172.8,6\nVSC,25.3,3",
    height=140
)

if st.sidebar.button("💾 Lưu danh mục"):
    data = []
    for line in input_text.split("\n"):
        try:
            code, buy, nav = line.split(",")
            data.append({
                "symbol": code.strip().upper(),
                "buy": float(buy),
                "nav": float(nav)
            })
        except:
            pass
    save_data(data)
    st.sidebar.success("Đã lưu danh mục.")

portfolio = load_data()

# ===== MAIN =====
rows = []

for item in portfolio:
    symbol = item["symbol"]
    buy = item["buy"]
    nav = item["nav"]

    df = get_stock_data(symbol)

    if df is None:
        rows.append({
            "Mã": symbol,
            "Giá mua": buy,
            "%NAV": nav,
            "Trạng thái": "❌ Không có dữ liệu",
            "Hành động": "Check mã / nguồn dữ liệu"
        })
        continue

    ind = calc_indicators(df)
    score = score_stock(ind)
    status = tech_status(score)
    pnl, action, stop, nav_action, risk = decision(buy, ind["price"], score, status)

    rows.append({
        "Mã": symbol,
        "Giá mua": buy,
        "Giá hiện tại": round(ind["price"], 2),
        "%NAV": nav,
        "% Lãi/Lỗ": round(pnl, 2),
        "Điểm 5 trục": score,
        "Trạng thái": status,
        "RSI": round(ind["rsi"], 1),
        "Giá_OK": ind["gia_ok"],
        "RSI_OK": ind["rsi_ok"],
        "OBV_OK": ind["obv_ok"],
        "MACD_OK": ind["macd_ok"],
        "VOL_OK": ind["vol_ok"],
        "Hành động": action,
        "Stop gợi ý": "-" if stop is None else round(stop, 2),
        "NAV đề xuất": nav_action,
        "Rủi ro": risk
    })

result_df = pd.DataFrame(rows)

st.subheader("📊 Danh mục hiện tại – Auto Scanner")
st.dataframe(result_df, use_container_width=True)

if not result_df.empty and "% Lãi/Lỗ" in result_df.columns:
    c1, c2, c3 = st.columns(3)
    c1.metric("📈 Lãi/Lỗ TB (%)", round(result_df["% Lãi/Lỗ"].mean(), 2))
    c2.metric("🔥 Điểm kỹ thuật TB", round(result_df["Điểm 5 trục"].mean(), 2))
    c3.metric("💰 Tổng %NAV", round(result_df["%NAV"].sum(), 2))

st.subheader("🚨 Cảnh báo nhanh")

if result_df.empty:
    st.info("👉 Chưa có danh mục.")
else:
    for _, row in result_df.iterrows():
        code = row["Mã"]
        action = row.get("Hành động", "")
        status = row.get("Trạng thái", "")

        if "BÁN" in action:
            st.error(f"{code} → {status} → {action}")
        elif "SIẾT" in action:
            st.warning(f"{code} → {status} → {action}")
        elif "CANH" in action:
            st.info(f"{code} → {status} → {action}")
        elif "GIỮ" in action:
            st.success(f"{code} → {status} → {action}")
