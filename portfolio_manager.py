import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio PRO V16", layout="wide")
st.title("🐔 Portfolio PRO V16 – Nuôi Gà Chiến Full Hệ")

DATA_FILE = "portfolio.csv"

# ================= LOAD / SAVE =================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            if {"Mã", "Giá mua", "%NAV"}.issubset(df.columns):
                return df
        except:
            pass
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV", "Giá hiện tại nhập tay"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= DATA =================
@st.cache_data(ttl=300)
def get_history(code):
    try:
        df = yf.Ticker(f"{code}.VN").history(period="9mo", interval="1d")
        if df is None or df.empty or len(df) < 40:
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

# ================= UNIT FIX =================
def normalize_units(ind, buy):
    price = ind["price"]
    if price > 1000 and buy < 1000:
        factor = 1000
    elif price < 1000 and buy > 1000:
        factor = 1 / 1000
    else:
        factor = 1

    if factor == 1000:
        for k in ["price", "ema9", "ema20", "atr14", "low_recent"]:
            ind[k] /= 1000

    elif factor == 1 / 1000:
        for k in ["price", "ema9", "ema20", "atr14", "low_recent"]:
            ind[k] *= 1000

    return ind

# ================= SCORE =================
def score_5_axis(ind):
    price_ok = ind["price"] > ind["ema9"] and ind["ema9"] >= ind["ema20"]
    rsi_ok = ind["rsi"] >= 55 and ind["rsi"] >= ind["rsi_ema9"]
    obv_ok = ind["obv"] >= ind["obv_ema9"]
    macd_ok = ind["macd"] >= ind["signal"] and ind["hist"] >= ind["hist_prev"]
    vol_ok = ind["volume"] >= ind["vol_ma20"] * 0.8

    score = 0
    score += 2.5 if price_ok else 1.2 if ind["price"] >= ind["ema20"] else 0
    score += 2 if rsi_ok else 1 if ind["rsi"] >= 50 else 0
    score += 3 if obv_ok else 0
    score += 1.5 if macd_ok else 0
    score += 1 if vol_ok else 0

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

# ================= STOP ENGINE =================
def stop_engine(ind, status, buy):
    price = ind["price"]
    atr = ind["atr14"]
    ema9 = ind["ema9"]
    ema20 = ind["ema20"]
    low_recent = ind["low_recent"]

    stop_atr = price - 1.2 * atr
    stop_struct = low_recent - 0.5 * atr
    stop_ma20 = ema20 - 0.8 * atr

    if "🟢" in status:
        return round(max(ema9, stop_atr, stop_struct), 2), "Trailing sát theo EMA9 / ATR / đáy gần"
    if "🔵" in status:
        return round(max(buy * 0.98, stop_atr), 2), "Sắp chạy: stop bảo vệ gần điểm mua"
    if "🟡" in status:
        return round(min(stop_ma20, stop_struct), 2), "Gà nghỉ: stop dưới MA20 / đáy nền"
    if "🟠" in status:
        return round(max(price * 0.98, stop_atr), 2), "Yếu dần: siết stop sát"
    return "-", "Gãy kỹ thuật: ưu tiên thoát"

def decision(status, price, stop):
    if stop != "-" and price <= stop:
        return "CHẠM STOP / XỬ LÝ NGAY", "Rất cao"

    if "🟢" in status:
        return "GIỮ / CÓ THỂ TĂNG", "Thấp"
    if "🔵" in status:
        return "SOI CHART / CANH TĂNG NHẸ", "Thấp-Trung bình"
    if "🟡" in status:
        return "THEO DÕI", "Trung bình"
    if "🟠" in status:
        return "GIẢM / SIẾT STOP", "Cao"
    return "BÁN / THOÁT", "Rất cao"

# ================= SIDEBAR =================
st.sidebar.header("📥 Nhập danh mục")

raw = st.sidebar.text_area(
    "Format:\nMã,Giá mua,%NAV\nhoặc: Mã,Giá mua,%NAV,Giá hiện tại\n\nVD:\nMBB,27000,5\nBAF,36600,4.5,36700",
    height=220
)

if st.sidebar.button("💾 Lưu danh mục"):
    rows = []
    for line in raw.split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                rows.append({
                    "Mã": parts[0].upper(),
                    "Giá mua": float(parts[1]),
                    "%NAV": float(parts[2]),
                    "Giá hiện tại nhập tay": float(parts[3]) if len(parts) >= 4 and parts[3] != "" else np.nan
                })
            except:
                pass

    save_data(pd.DataFrame(rows))
    st.sidebar.success("✅ Đã lưu")

# ================= MAIN =================
df_input = load_data()
st.subheader("📊 Danh mục hiện tại – V16")

if df_input.empty:
    st.info("👉 Chưa có danh mục")
else:
    rows = []

    for _, r in df_input.iterrows():
        code = r["Mã"]
        buy = float(r["Giá mua"])
        nav = float(r["%NAV"])
        manual_price = r.get("Giá hiện tại nhập tay", np.nan)

        hist_df = get_history(code)

        # Case 1: có data kỹ thuật
        if hist_df is not None:
            ind = calc_indicators(hist_df)
            ind = normalize_units(ind, buy)

            # nếu có giá tay thì ưu tiên dùng giá tay cho PnL
            if not pd.isna(manual_price):
                ind["price"] = float(manual_price)

            pnl = (ind["price"] - buy) / buy * 100
            score, price_ok, rsi_ok, obv_ok, macd_ok, vol_ok = score_5_axis(ind)
            status = tech_status(score)
            stop, stop_rule = stop_engine(ind, status, buy)
            action, risk = decision(status, ind["price"], stop)

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
                "Ghi chú": "Đủ data kỹ thuật"
            })

        # Case 2: không có data kỹ thuật nhưng có giá nhập tay
        elif not pd.isna(manual_price):
            price = float(manual_price)
            pnl = (price - buy) / buy * 100

            rows.append({
                "Mã": code,
                "Giá mua": buy,
                "Giá hiện tại": round(price, 2),
                "%NAV": nav,
                "% Lãi/Lỗ": round(pnl, 2),
                "Điểm 5 trục": "N/A",
                "Trạng thái": "⚪ Thiếu data kỹ thuật",
                "Giá_OK": "N/A",
                "RSI": "N/A",
                "RSI_OK": "N/A",
                "OBV_OK": "N/A",
                "MACD_OK": "N/A",
                "VOL_OK": "N/A",
                "Stop Engine 2.0": "N/A",
                "Luật stop": "Cần soi chart thủ công",
                "Hành động": "THEO DÕI THỦ CÔNG",
                "Rủi ro": "Chưa xác định",
                "Ghi chú": "Yahoo thiếu mã, dùng giá nhập tay"
            })

        # Case 3: không có gì
        else:
            rows.append({
                "Mã": code,
                "Giá mua": buy,
                "Giá hiện tại": "Lỗi data",
                "%NAV": nav,
                "% Lãi/Lỗ": "N/A",
                "Điểm 5 trục": "N/A",
                "Trạng thái": "⚠️ Thiếu dữ liệu",
                "Hành động": "Nhập thêm giá hiện tại thủ công",
                "Rủi ro": "Chưa xác định",
                "Ghi chú": "Format: Mã,Giá mua,%NAV,Giá hiện tại"
            })

    result = pd.DataFrame(rows)
    st.dataframe(result, use_container_width=True)

    c1, c2, c3 = st.columns(3)

    pnl_series = pd.to_numeric(result["% Lãi/Lỗ"], errors="coerce")
    score_series = pd.to_numeric(result["Điểm 5 trục"], errors="coerce")

    c1.metric("📈 Lãi/Lỗ TB (%)", "N/A" if pnl_series.dropna().empty else round(pnl_series.mean(), 2))
    c2.metric("🔥 Điểm 5 trục TB", "N/A" if score_series.dropna().empty else round(score_series.mean(), 2))
    c3.metric("💰 Tổng %NAV", round(result["%NAV"].sum(), 2))

    st.subheader("🚨 Cảnh báo nhanh")
    for _, row in result.iterrows():
        action = str(row.get("Hành động", ""))
        if "BÁN" in action or "CHẠM STOP" in action:
            st.error(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "GIẢM" in action or "SIẾT" in action:
            st.warning(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        elif "GIỮ" in action:
            st.success(f"{row['Mã']} → {row['Trạng thái']} → {action}")
        else:
            st.info(f"{row['Mã']} → {row['Trạng thái']} → {action}")
