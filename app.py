import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Scanner Gà Chiến V6", layout="wide")

# =========================
# WATCHLIST MẶC ĐỊNH THEO ẢNH ANH GỬI
# =========================
DEFAULT_SECTORS = {
    "BANK": ["VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","TPB","LPB","EIB","ABB","MSB","KLB","EVF"],
    "CK": ["SSI","VIX","SHS","MBS","TCX","VCK","VPX","HCM","VCI","VND","CTS","FTS","BSI","BVS","ORS","VDS","AGR"],
    "BDS": ["VHM","NLG","KDH","CEO","CII","DXG","TCH","IHS","DPG","HDC","NVL","NTL","NHA","HUT","DIG","PDR","DXS"],
    "BDS_CN": ["VGC","IDC","KBC","SZC","BCM","DTD","LHG","IJC","GVR","PHR","DPR","DRI","SIP","TRC","DRC","CSM"],
    "BAN_LE": ["MWG","DGW","FRT","PET","PNJ","MSN","MCH","PAN","FMC","DBC","HAG","VNM","MML","SAB","SBT","TLG","HPA"],
    "DIEN": ["REE","GEE","GEX","PC1","NT2","GEL","HDG","GEG","POW"],
    "HOA_CHAT": ["DPM","DCM","LAS","DDV","DGC","CSV","BFC","MSR","BMP","NTP"],
    "DAU": ["BSR","PVS","PVD","PVB","PVC","PVT","OIL","PLX","GAS"],
    "LOGIS": ["HAH","GMD","VSC","VOS","VTO","HVN","VJC","ACV"],
}

STATUS_ORDER = {
    "🟩 ƯU TIÊN MUA": 4,
    "🟨 THEO DÕI": 3,
    "🟦 EARLY REVERSAL": 2,
    "🟥 LOẠI": 1,
}

# =========================
# HÀM PHỤ
# =========================
def build_default_text() -> str:
    lines = []
    for sector, tickers in DEFAULT_SECTORS.items():
        lines.append(f"{sector}:")
        lines.append(", ".join(tickers))
        lines.append("")
    return "\n".join(lines)

def parse_watchlist(text: str):
    rows = []
    current_sector = "KHÁC"
    for raw in text.splitlines():
        line = raw.strip().upper()
        if not line:
            continue
        if line.endswith(":"):
            current_sector = line[:-1].strip()
            continue
        for token in line.split(","):
            code = token.strip().upper()
            if code:
                if not code.endswith(".VN"):
                    code = f"{code}.VN"
                rows.append((current_sector, code))
    # bỏ trùng
    seen = set()
    dedup = []
    for sector, ticker in rows:
        if ticker not in seen:
            dedup.append((sector, ticker))
            seen.add(ticker)
    return dedup

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def normalize_series(x):
    if isinstance(x, pd.DataFrame):
        x = x.iloc[:, 0]
    return pd.to_numeric(x, errors="coerce")

def analyze_ticker(sector: str, ticker: str, market_score: int):
    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return None

        required_cols = ["Close", "Volume", "High", "Low"]
        for col in required_cols:
            if col not in df.columns:
                return None

        close = normalize_series(df["Close"]).dropna()
        volume = normalize_series(df["Volume"]).reindex(close.index)
        high = normalize_series(df["High"]).reindex(close.index)
        low = normalize_series(df["Low"]).reindex(close.index)

        if len(close) < 30:
            return None

        ema9 = close.ewm(span=9, adjust=False).mean()
        ma20 = close.rolling(20).mean()

        rsi = compute_rsi(close, 14)
        rsi_ema9 = rsi.ewm(span=9, adjust=False).mean()

        direction = close.diff().fillna(0)
        obv_step = pd.Series(0.0, index=close.index)
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

        # ===== TRỤC =====
        price_above_ema9 = latest_close > latest_ema9
        rsi_strong = latest_rsi is not None and latest_rsi > 55
        rsi_above_ema = (
            latest_rsi is not None
            and latest_rsi_ema9 is not None
            and latest_rsi > latest_rsi_ema9
        )
        obv_above_ema = (
            latest_obv is not None
            and latest_obv_ema9 is not None
            and latest_obv > latest_obv_ema9
        )
        obv_up = len(obv) >= 3 and obv.iloc[-1] > obv.iloc[-2] > obv.iloc[-3]

        # ===== MẪU HÌNH =====
        pull_ok = (
            latest_close >= latest_ema9 * 0.98
            and latest_close <= latest_ema9 * 1.03
            and price_above_ema9
            and obv_above_ema
        )

        can_cung = (
            latest_vol is not None
            and latest_vol_ma20 is not None
            and latest_vol < latest_vol_ma20 * 0.8
            and abs(latest_close - latest_ema9) / latest_ema9 < 0.04
        )

        breakout_ok = (
            latest_close > recent_10_high
            and latest_vol is not None
            and latest_vol_ma20 is not None
            and latest_vol > latest_vol_ma20 * 1.2
            and price_above_ema9
        )

        # ===== STOCK SCORE 8 ĐIỂM =====
        score = 0
        score += int(price_above_ema9)
        score += int(rsi_strong)
        score += int(rsi_above_ema)
        score += int(obv_above_ema)
        score += int(obv_up)
        score += int(pull_ok)
        score += int(can_cung)
        score += int(breakout_ok)

        # ===== PHÂN LOẠI =====
        if score >= 6:
            status = "🟩 ƯU TIÊN MUA"
        elif score >= 4:
            status = "🟨 THEO DÕI"
        elif score >= 2:
            status = "🟦 EARLY REVERSAL"
        else:
            status = "🟥 LOẠI"

        # ===== GIAI ĐOẠN =====
        if breakout_ok:
            stage = "🚀 Break"
        elif pull_ok:
            stage = "📉 Pull"
        elif score >= 2:
            stage = "🌱 Early"
        else:
            stage = "❌"

        # ===== HÀNH ĐỘNG =====
        if market_score < 8:
            action = "Đứng ngoài"
        else:
            if status == "🟩 ƯU TIÊN MUA":
                action = "Canh mua pull" if pull_ok else ("Canh mua break" if breakout_ok else "Ưu tiên theo dõi sát")
            elif status == "🟨 THEO DÕI":
                action = "Chờ xác nhận thêm"
            elif status == "🟦 EARLY REVERSAL":
                action = "Mua thăm dò nhỏ"
            else:
                action = "Loại"

        gold_score = market_score * score if market_score >= 8 else 0

        chart_df = pd.DataFrame({
            "Close": close.tail(80),
            "EMA9": ema9.tail(80),
            "MA20": ma20.tail(80),
            "RSI": rsi.tail(80),
        })

        return {
            "Sector": sector,
            "Ticker": ticker,
            "Close": round(latest_close, 2),
            "EMA9": round(latest_ema9, 2),
            "MA20": round(latest_ma20, 2) if latest_ma20 is not None else None,
            "RSI": round(latest_rsi, 2) if latest_rsi is not None else None,
            "OBV > EMA9": "✅" if obv_above_ema else "❌",
            "Pull đẹp": "✅" if pull_ok else "❌",
            "Cạn cung": "✅" if can_cung else "❌",
            "Break chuẩn": "✅" if breakout_ok else "❌",
            "Score": score,
            "Gold Score": gold_score,
            "Stage": stage,
            "Status": status,
            "Hành động": action,
            "_chart": chart_df,
        }
    except Exception:
        return None

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Thiết lập")
market_score = st.sidebar.slider("Market Score", 1, 10, 8)
show_top_n = st.sidebar.slider("Top toàn thị trường", 3, 10, 5, 1)
status_filter = st.sidebar.multiselect(
    "Lọc trạng thái",
    ["🟩 ƯU TIÊN MUA", "🟨 THEO DÕI", "🟦 EARLY REVERSAL", "🟥 LOẠI"],
    default=["🟩 ƯU TIÊN MUA", "🟨 THEO DÕI", "🟦 EARLY REVERSAL", "🟥 LOẠI"]
)

# =========================
# INPUT WATCHLIST
# =========================
watchlist_text = st.text_area(
    "Danh sách mã theo ngành",
    value=build_default_text(),
    height=280
)

col_a, col_b, col_c = st.columns([1,1,1])
with col_a:
    run_scan = st.button("🚀 Quét ngay", use_container_width=True)
with col_b:
    refresh_now = st.button("🔄 Refresh", use_container_width=True)
with col_c:
    st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

if refresh_now:
    st.rerun()

# =========================
# MAIN
# =========================
if run_scan:
    watchlist = parse_watchlist(watchlist_text)

    if not watchlist:
        st.warning("Chưa có mã hợp lệ.")
    else:
        progress = st.progress(0, text="Đang quét...")
        results = []

        total = len(watchlist)
        for idx, (sector, ticker) in enumerate(watchlist, start=1):
            row = analyze_ticker(sector, ticker, market_score)
            if row is not None:
                results.append(row)
            progress.progress(idx / total, text=f"Đang quét {ticker} ({idx}/{total})")

        progress.empty()

        if not results:
            st.warning("Không có dữ liệu hợp lệ.")
        else:
            out = pd.DataFrame(results)
            out["StatusRank"] = out["Status"].map(STATUS_ORDER)
            out = out.sort_values(
                by=["Gold Score", "Score", "StatusRank", "RSI"],
                ascending=[False, False, False, False]
            )

            # filter
            out = out[out["Status"].isin(status_filter)].copy()

            # charts dict
            charts = {row["Ticker"]: row["_chart"] for row in results}

            display_cols = [
                "Sector", "Ticker", "Close", "EMA9", "MA20", "RSI",
                "OBV > EMA9", "Pull đẹp", "Cạn cung", "Break chuẩn",
                "Score", "Gold Score", "Stage", "Status", "Hành động"
            ]

            st.subheader("📊 Kết quả quét tổng hợp")
            st.dataframe(out[display_cols], use_container_width=True)

            top_market = out.head(show_top_n)
            st.subheader(f"🔥 Top {show_top_n} toàn thị trường")
            st.dataframe(top_market[display_cols], use_container_width=True)

            st.subheader("🏆 Top 1 mỗi ngành")
            top_sector = (
                out.sort_values(by=["Gold Score", "Score", "RSI"], ascending=False)
                   .groupby("Sector", as_index=False)
                   .head(1)
            )
            st.dataframe(top_sector[display_cols], use_container_width=True)

            st.subheader("🔥 Nhóm ƯU TIÊN MUA")
            st.dataframe(out[out["Status"] == "🟩 ƯU TIÊN MUA"][display_cols], use_container_width=True)

            st.subheader("👀 Nhóm THEO DÕI")
            st.dataframe(out[out["Status"] == "🟨 THEO DÕI"][display_cols], use_container_width=True)

            st.subheader("🌱 Nhóm EARLY REVERSAL")
            st.dataframe(out[out["Status"] == "🟦 EARLY REVERSAL"][display_cols], use_container_width=True)

            st.subheader("🚨 Gà chiến mới nổi")
            alert = out[(out["Status"] == "🟩 ƯU TIÊN MUA") & (out["Break chuẩn"] == "✅")]
            if not alert.empty:
                st.success("Có gà mạnh mới nổi.")
                st.dataframe(alert[display_cols], use_container_width=True)
            else:
                st.info("Chưa có gà mới nổi.")

            st.subheader("📈 Xem chart nhanh từng mã")
            selected = st.selectbox("Chọn mã để xem chart", out["Ticker"].tolist())
            if selected in charts:
                st.line_chart(charts[selected][["Close", "EMA9", "MA20"]])

            st.subheader("🧠 Kết luận nhanh")
            if market_score < 8:
                st.warning("Thị trường yếu → đứng ngoài hoặc giữ tỷ trọng thấp.")
            else:
                strong_count = (out["Status"] == "🟩 ƯU TIÊN MUA").sum()
                if strong_count >= 3:
                    st.success("Có nhiều gà chiến → có thể giải ngân có chọn lọc.")
                elif strong_count >= 1:
                    st.info("Có một số mã tốt → ưu tiên đúng leader, không dàn trải.")
                else:
                    st.warning("Chưa đủ leader rõ → kiên nhẫn chờ thêm.")
else:
    st.info("Bấm 'Quét ngay' để chạy scanner.")
