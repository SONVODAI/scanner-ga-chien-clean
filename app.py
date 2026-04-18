import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến V3", layout="wide")

st.title("🐔 Scanner Gà Chiến V3")

market_score = st.slider("Market Score", 1, 10, 8)

default_watchlist = """HPG.VN, HSG.VN, NKG.VN
FPT.VN, CMG.VN
MWG.VN, FRT.VN, DGW.VN
SSI.VN, VND.VN, HCM.VN, VCI.VN
MBB.VN, TCB.VN, CTG.VN, STB.VN
GMD.VN, VSC.VN
"""

watchlist_text = st.text_area(
    "Nhập danh sách mã (mỗi dòng hoặc cách nhau bằng dấu phẩy)",
    value=default_watchlist,
    height=180
)

raw_tickers = []
for line in watchlist_text.splitlines():
    parts = [x.strip().upper() for x in line.split(",") if x.strip()]
    raw_tickers.extend(parts)

tickers = []
for t in raw_tickers:
    if t not in tickers:
        tickers.append(t)

sector_map = {
    "HPG.VN": "Thép", "HSG.VN": "Thép", "NKG.VN": "Thép",
    "FPT.VN": "Công nghệ", "CMG.VN": "Công nghệ",
    "MWG.VN": "Bán lẻ", "FRT.VN": "Bán lẻ", "DGW.VN": "Bán lẻ",
    "SSI.VN": "Chứng khoán", "VND.VN": "Chứng khoán", "HCM.VN": "Chứng khoán", "VCI.VN": "Chứng khoán",
    "MBB.VN": "Ngân hàng", "TCB.VN": "Ngân hàng", "CTG.VN": "Ngân hàng", "STB.VN": "Ngân hàng",
    "GMD.VN": "Logistic", "VSC.VN": "Logistic",
}

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def classify_status(score: int) -> str:
    if score >= 6:
        return "🟩 ƯU TIÊN MUA"
    elif score >= 4:
        return "🟨 THEO DÕI"
    elif score >= 2:
        return "🟦 EARLY REVERSAL"
    return "🟥 LOẠI"

def action_text(status: str, pull_ok: bool, breakout_ok: bool, market_score: int) -> str:
    if market_score < 8:
        return "Đứng ngoài / giữ tiền"
    if status == "🟩 ƯU TIÊN MUA":
        if pull_ok:
            return "Canh mua pull"
        if breakout_ok:
            return "Canh mua break"
        return "Ưu tiên theo dõi sát"
    if status == "🟨 THEO DÕI":
        return "Chờ xác nhận thêm"
    if status == "🟦 EARLY REVERSAL":
        return "Mua thăm dò nhỏ"
    return "Loại"

results = []

for ticker in tickers:
    try:
        df = yf.download(ticker, period="6mo", progress=False, auto_adjust=False)

        if df is None or df.empty or "Close" not in df.columns or "Volume" not in df.columns:
            continue

        close = df["Close"]
        volume = df["Volume"]
        high = df["High"] if "High" in df.columns else None

        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        if isinstance(volume, pd.DataFrame):
            volume = volume.iloc[:, 0]
        if high is not None and isinstance(high, pd.DataFrame):
            high = high.iloc[:, 0]

        close = pd.to_numeric(close, errors="coerce").dropna()
        volume = pd.to_numeric(volume, errors="coerce").reindex(close.index)
        if high is not None:
            high = pd.to_numeric(high, errors="coerce").reindex(close.index)

        if len(close) < 30:
            continue

        ema9 = close.ewm(span=9, adjust=False).mean()
        ma20 = close.rolling(20).mean()

        rsi = compute_rsi(close, 14)
        rsi_ema9 = rsi.ewm(span=9, adjust=False).mean()

        direction = close.diff().fillna(0)
        obv_step = pd.Series(0, index=close.index, dtype="float64")
        obv_step[direction > 0] = volume[direction > 0]
        obv_step[direction < 0] = -volume[direction < 0]
        obv = obv_step.cumsum()
        obv_ema9 = obv.ewm(span=9, adjust=False).mean()

        vol_ma20 = volume.rolling(20).mean()

        latest_close = float(close.iloc[-1])
        latest_ema9 = float(ema9.iloc[-1])
        latest_ma20 = float(ma20.iloc[-1]) if pd.notna(ma20.iloc[-1]) else None
        latest_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
        latest_rsi_ema9 = float(rsi_ema9.iloc[-1]) if pd.notna(rsi_ema9.iloc[-1]) else None
        latest_obv = float(obv.iloc[-1]) if pd.notna(obv.iloc[-1]) else None
        latest_obv_ema9 = float(obv_ema9.iloc[-1]) if pd.notna(obv_ema9.iloc[-1]) else None
        latest_vol = float(volume.iloc[-1]) if pd.notna(volume.iloc[-1]) else None
        latest_vol_ma20 = float(vol_ma20.iloc[-1]) if pd.notna(vol_ma20.iloc[-1]) else None

        recent_10_high = float(close.iloc[-11:-1].max()) if len(close) >= 11 else latest_close
        recent_20_high = float(close.iloc[-21:-1].max()) if len(close) >= 21 else latest_close

        # ===== Điều kiện nền =====
        price_above_ema9 = latest_close > latest_ema9
        rsi_strong = latest_rsi is not None and latest_rsi > 55
        rsi_above_ema = latest_rsi is not None and latest_rsi_ema9 is not None and latest_rsi > latest_rsi_ema9
        obv_above_ema = latest_obv is not None and latest_obv_ema9 is not None and latest_obv > latest_obv_ema9
        obv_up = len(obv) >= 3 and obv.iloc[-1] > obv.iloc[-2] > obv.iloc[-3]

        # ===== Pull đẹp =====
        pull_ok = (
            latest_close >= latest_ema9 * 0.98
            and latest_close <= latest_ema9 * 1.03
            and price_above_ema9
            and obv_above_ema
        )

        # ===== Cạn cung =====
        can_cung = (
            latest_vol is not None and latest_vol_ma20 is not None
            and latest_vol < latest_vol_ma20 * 0.8
            and abs(latest_close - latest_ema9) / latest_ema9 < 0.04
        )

        # ===== Break chuẩn =====
        breakout_ok = (
            latest_close > recent_10_high
            and latest_vol is not None and latest_vol_ma20 is not None
            and latest_vol > latest_vol_ma20 * 1.2
            and price_above_ema9
        )

        # ===== Score =====
        score = 0
        if price_above_ema9:
            score += 1
        if rsi_strong:
            score += 1
        if rsi_above_ema:
            score += 1
        if obv_above_ema:
            score += 1
        if obv_up:
            score += 1
        if pull_ok:
            score += 1
        if can_cung:
            score += 1
        if breakout_ok:
            score += 1

        status = classify_status(score)
        gold_score = market_score * score if market_score >= 8 else 0
        action = action_text(status, pull_ok, breakout_ok, market_score)

        results.append({
            "Sector": sector_map.get(ticker, "Khác"),
            "Ticker": ticker,
            "Close": round(latest_close, 2),
            "EMA9": round(latest_ema9, 2),
            "RSI": round(latest_rsi, 2) if latest_rsi is not None else None,
            "OBV > EMA9": "✅" if obv_above_ema else "❌",
            "Pull đẹp": "✅" if pull_ok else "❌",
            "Cạn cung": "✅" if can_cung else "❌",
            "Break chuẩn": "✅" if breakout_ok else "❌",
            "Score": score,
            "Gold Score": gold_score,
            "Status": status,
            "Hành động": action
        })

    except Exception:
        continue

if results:
    out = pd.DataFrame(results).sort_values(
        by=["Gold Score", "Score", "RSI"],
        ascending=False
    )

    st.subheader("📊 Kết quả quét tổng hợp")
    st.dataframe(out, use_container_width=True)

    st.subheader("🔥 Nhóm ƯU TIÊN MUA")
    st.dataframe(out[out["Status"] == "🟩 ƯU TIÊN MUA"], use_container_width=True)

    st.subheader("👀 Nhóm THEO DÕI")
    st.dataframe(out[out["Status"] == "🟨 THEO DÕI"], use_container_width=True)

    st.subheader("🌱 Nhóm EARLY REVERSAL")
    st.dataframe(out[out["Status"] == "🟦 EARLY REVERSAL"], use_container_width=True)

    st.subheader("🏆 Top 1 mỗi ngành")
    top_sector = out.sort_values(
        by=["Gold Score", "Score", "RSI"],
        ascending=False
    ).groupby("Sector", as_index=False).head(1)
    st.dataframe(top_sector, use_container_width=True)
else:
    st.warning("⚠️ Không có dữ liệu hợp lệ.")
