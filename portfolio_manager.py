import streamlit as st
import pandas as pd
import numpy as np
import os
import yfinance as yf

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Portfolio Gà Chiến PRO", layout="wide")

FILE_NAME = "portfolio.csv"

st.title("🔥 Portfolio Gà Chiến PRO – V20 Stable")

# =========================
# LOAD / SAVE
# =========================
def load_portfolio():
    if os.path.exists(FILE_NAME):
        try:
            df = pd.read_csv(FILE_NAME)
            for col in ["Mã", "Giá mua", "%NAV"]:
                if col not in df.columns:
                    df[col] = ""
            return df[["Mã", "Giá mua", "%NAV"]]
        except:
            return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])


def save_portfolio(df):
    df.to_csv(FILE_NAME, index=False)


df = load_portfolio()

# =========================
# SIDEBAR INPUT
# =========================
st.sidebar.header("📌 Nhập / sửa danh mục")

ma = st.sidebar.text_input("Mã cổ phiếu", value="").upper().strip()
gia_mua = st.sidebar.number_input("Giá mua", min_value=0.0, step=100.0)
nav = st.sidebar.number_input("%NAV", min_value=0.0, step=0.5)

col_a, col_b = st.sidebar.columns(2)

with col_a:
    if st.button("✅ Lưu mã"):
        if ma:
            if ma in df["Mã"].astype(str).values:
                df.loc[df["Mã"] == ma, ["Giá mua", "%NAV"]] = [gia_mua, nav]
            else:
                df.loc[len(df)] = [ma, gia_mua, nav]
            save_portfolio(df)
            st.success(f"Đã lưu {ma}")
            st.rerun()

with col_b:
    if st.button("🗑️ Xóa mã"):
        if ma:
            df = df[df["Mã"] != ma]
            save_portfolio(df)
            st.warning(f"Đã xóa {ma}")
            st.rerun()

if st.sidebar.button("❌ Xóa toàn bộ danh mục"):
    df = pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])
    save_portfolio(df)
    st.warning("Đã xóa toàn bộ")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("Dữ liệu lưu trong file portfolio.csv, refresh không mất.")

# =========================
# DATA SOURCE
# =========================
def download_yahoo(symbol):
    """
    Ưu tiên thử nhiều đuôi Yahoo cho cổ phiếu Việt Nam:
    - .VN thường dùng cho HOSE
    - .HN thường dùng cho HNX
    Nếu không có data thì trả None.
    """
    candidates = [f"{symbol}.VN", f"{symbol}.HN"]

    for ticker in candidates:
        try:
            data = yf.download(
                ticker,
                period="8mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if data is not None and not data.empty and len(data) >= 40:
                data = data.reset_index()

                # Xử lý MultiIndex nếu yfinance trả về dạng nhiều tầng
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = [c[0] for c in data.columns]

                data = data.rename(columns={
                    "Close": "close",
                    "Volume": "volume",
                    "High": "high",
                    "Low": "low",
                    "Open": "open"
                })

                needed = ["close", "volume"]
                if all(c in data.columns for c in needed):
                    return data, ticker
        except:
            continue

    return None, None


# =========================
# INDICATORS
# =========================
def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_obv(close, volume):
    obv = [0]
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.append(obv[-1] + volume.iloc[i])
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.append(obv[-1] - volume.iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv)


def safe_round(x, n=2):
    try:
        if pd.isna(x):
            return None
        return round(float(x), n)
    except:
        return None


# =========================
# EVALUATION
# =========================
def evaluate_stock(symbol, buy_price):
    data, source = download_yahoo(symbol)

    if data is None:
        return {
            "Mã": symbol,
            "Nguồn": "Không có data",
            "Giá mua": buy_price,
            "Giá hiện tại": None,
            "% Lãi/Lỗ": None,
            "Điểm 13": 0,
            "Trạng thái": "⚪ Không data",
            "Cảnh báo": "Không lấy được dữ liệu Yahoo",
            "Stoploss": None,
            "Hành động": "CHECK TAY"
        }

    close = data["close"].astype(float)
    volume = data["volume"].fillna(0).astype(float)

    price = close.iloc[-1]
    ema9 = close.ewm(span=9, adjust=False).mean()
    ma20 = close.rolling(20).mean()

    rsi = calc_rsi(close)
    rsi_ema9 = rsi.ewm(span=9, adjust=False).mean()

    obv = calc_obv(close, volume)
    obv_ema9 = obv.ewm(span=9, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    # Lấy giá trị cuối
    ema9_now = ema9.iloc[-1]
    ma20_now = ma20.iloc[-1]
    rsi_now = rsi.iloc[-1]
    rsi_ma_now = rsi_ema9.iloc[-1]
    obv_now = obv.iloc[-1]
    obv_ma_now = obv_ema9.iloc[-1]
    hist_now = hist.iloc[-1]

    # =========================
    # CHẤM ĐIỂM 13
    # =========================
    score = 0
    warnings = []

    # OBV max 4
    if obv_now > obv_ma_now:
        score += 3
        if len(obv) >= 3 and obv.iloc[-1] > obv.iloc[-2] > obv.iloc[-3]:
            score += 1
    else:
        warnings.append("OBV dưới EMA9")

    # Price / EMA max 3
    if price > ema9_now:
        score += 1
    else:
        warnings.append("Giá dưới EMA9")

    if ema9_now > ma20_now:
        score += 1
    else:
        warnings.append("EMA9 chưa trên MA20")

    if price > ma20_now:
        score += 1
    else:
        warnings.append("Giá dưới MA20")

    # RSI max 3
    if rsi_now > 55:
        score += 1
    else:
        warnings.append("RSI yếu")

    if rsi_now > rsi_ma_now:
        score += 1
    else:
        warnings.append("RSI dưới EMA9 RSI")

    if 60 <= rsi_now <= 75:
        score += 1

    # MACD max 2
    if hist_now > 0:
        score += 1
    else:
        warnings.append("MACD Hist âm")

    if len(hist) >= 3 and hist.iloc[-1] > hist.iloc[-2]:
        score += 1
    else:
        warnings.append("MACD co lại")

    # ATR đơn giản / độ ổn định max 1
    if len(close) >= 15:
        atr_proxy = (data["high"].astype(float) - data["low"].astype(float)).rolling(14).mean().iloc[-1] if "high" in data.columns and "low" in data.columns else None
        if atr_proxy is not None and price > 0 and atr_proxy / price < 0.06:
            score += 1

    score = min(score, 13)

    # =========================
    # PHÂN LOẠI
    # =========================
    if score >= 10:
        status = "🟢 Gà chiến"
        action = "GIỮ / CANH GIA TĂNG"
    elif score >= 8:
        status = "🔵 Gà sắp chạy"
        action = "GIỮ"
    elif score >= 6:
        status = "🟡 Gà nghỉ"
        action = "GIỮ CÓ ĐIỀU KIỆN"
    elif score >= 4:
        status = "🟠 Yếu dần"
        action = "GIẢM / SIẾT STOP"
    else:
        status = "🔴 Gãy kỹ thuật"
        action = "BÁN / LOẠI"

    # Stoploss đơn giản theo cấu trúc
    stoploss = min(ema9_now, ma20_now) * 0.97

    pnl = None
    if buy_price and buy_price > 0:
        pnl = (price - buy_price) / buy_price * 100

    return {
        "Mã": symbol,
        "Nguồn": source,
        "Giá mua": buy_price,
        "Giá hiện tại": safe_round(price, 0),
        "% Lãi/Lỗ": safe_round(pnl, 2),
        "Điểm 13": score,
        "Trạng thái": status,
        "Cảnh báo": " / ".join(warnings) if warnings else "Không",
        "Stoploss": safe_round(stoploss, 0),
        "Hành động": action
    }


# =========================
# DISPLAY
# =========================
st.subheader("📊 Danh mục hiện tại")

if len(df) == 0:
    st.info("Chưa có danh mục. Anh nhập mã ở bên trái rồi bấm Lưu mã.")
else:
    results = []
    with st.spinner("Đang tải dữ liệu thật từ Yahoo Finance..."):
        for _, row in df.iterrows():
            symbol = str(row["Mã"]).upper().strip()
            buy_price = float(row["Giá mua"]) if pd.notna(row["Giá mua"]) else 0
            result = evaluate_stock(symbol, buy_price)
            result["%NAV"] = row["%NAV"]
            results.append(result)

    result_df = pd.DataFrame(results)

    cols = [
        "Mã", "Nguồn", "Giá mua", "Giá hiện tại", "% Lãi/Lỗ", "%NAV",
        "Điểm 13", "Trạng thái", "Cảnh báo", "Stoploss", "Hành động"
    ]

    st.dataframe(result_df[cols], use_container_width=True, height=420)

    # Tổng quan
    st.markdown("### 📌 Tổng quan nhanh")
    c1, c2, c3 = st.columns(3)

    avg_pnl = result_df["% Lãi/Lỗ"].dropna().mean()
    avg_score = result_df["Điểm 13"].dropna().mean()
    total_nav = pd.to_numeric(result_df["%NAV"], errors="coerce").fillna(0).sum()

    c1.metric("Lãi/Lỗ TB (%)", safe_round(avg_pnl, 2))
    c2.metric("Điểm 13 TB", safe_round(avg_score, 2))
    c3.metric("Tổng %NAV", safe_round(total_nav, 2))

st.success("✅ Bản V20 Stable đang dùng yfinance, không phụ thuộc vnstock.")
