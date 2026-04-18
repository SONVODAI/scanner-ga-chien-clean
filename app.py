import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Scanner Gà Chiến V7", layout="wide")

# =========================
# DEFAULT WATCHLIST
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
# HELPERS
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

@st.cache_data(ttl=120, show_spinner=False)
def load_daily_data(ticker: str):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return df

@st.cache_data(ttl=60, show_spinner=False)
def load_intraday_data(ticker: str, interval: str):
    # Yahoo thường hỗ trợ 5m/15m tốt trong phạm vi ngắn
    df = yf.download(
        ticker,
        period="5d",
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return df

def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().fillna(0)
    obv_step = pd.Series(0.0, index=close.index)
    obv_step[direction > 0] = volume[direction > 0]
    obv_step[direction < 0] = -volume[direction < 0]
    return obv_step.cumsum()

def analyze_ticker(sector: str, ticker: str, market_score: int, use_intraday: bool, intraday_interval: str):
    try:
        daily_df = load_daily_data(ticker)
        if daily_df is None or daily_df.empty:
            return None

        required_cols = ["Close", "Volume", "High", "Low"]
        for col in required_cols:
            if col not in daily_df.columns:
                return None

        close_d = normalize_series(daily_df["Close"]).dropna()
        volume_d = normalize_series(daily_df["Volume"]).reindex(close_d.index)
        if len(close_d) < 30:
            return None

        ema9_d = close_d.ewm(span=9, adjust=False).mean()
        ma20_d = close_d.rolling(20).mean()

        rsi_d = compute_rsi(close_d, 14)
        rsi_ema9_d = rsi_d.ewm(span=9, adjust=False).mean()

        obv_d = calc_obv(close_d, volume_d)
        obv_ema9_d = obv_d.ewm(span=9, adjust=False).mean()

        vol_ma20_d = volume_d.rolling(20).mean()

        latest_close = float(close_d.iloc[-1])
        latest_ema9 = float(ema9_d.iloc[-1])
        latest_ma20 = float(ma20_d.iloc[-1]) if pd.notna(ma20_d.iloc[-1]) else None
        latest_rsi = float(rsi_d.iloc[-1]) if pd.notna(rsi_d.iloc[-1]) else None
        latest_rsi_ema9 = float(rsi_ema9_d.iloc[-1]) if pd.notna(rsi_ema9_d.iloc[-1]) else None
        latest_obv = float(obv_d.iloc[-1]) if pd.notna(obv_d.iloc[-1]) else None
        latest_obv_ema9 = float(obv_ema9_d.iloc[-1]) if pd.notna(obv_ema9_d.iloc[-1]) else None
        latest_vol = float(volume_d.iloc[-1]) if pd.notna(volume_d.iloc[-1]) else None
        latest_vol_ma20 = float(vol_ma20_d.iloc[-1]) if pd.notna(vol_ma20_d.iloc[-1]) else None

        recent_10_high = float(close_d.iloc[-11:-1].max()) if len(close_d) >= 11 else latest_close

        # ===== DAILY CONDITIONS =====
        price_above_ema9 = latest_close > latest_ema9
        rsi_strong = latest_rsi is not None and latest_rsi > 55
        rsi_above_ema = latest_rsi is not None and latest_rsi_ema9 is not None and latest_rsi > latest_rsi_ema9
        obv_above_ema = latest_obv is not None and latest_obv_ema9 is not None and latest_obv > latest_obv_ema9
        obv_up = len(obv_d) >= 3 and obv_d.iloc[-1] > obv_d.iloc[-2] > obv_d.iloc[-3]

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

        # ===== INTRADAY CHECK =====
        intraday_break = False
        intraday_obv_up = False
        intraday_note = "Không dùng intraday"

        chart_close = close_d.tail(80)
        chart_ema9 = ema9_d.tail(80)
        chart_ma20 = ma20_d.tail(80)

        if use_intraday:
            try:
                intra_df = load_intraday_data(ticker, intraday_interval)
                if intra_df is not None and not intra_df.empty and "Close" in intra_df.columns and "Volume" in intra_df.columns:
                    close_i = normalize_series(intra_df["Close"]).dropna()
                    vol_i = normalize_series(intra_df["Volume"]).reindex(close_i.index)

                    if len(close_i) >= 10:
                        ema9_i = close_i.ewm(span=9, adjust=False).mean()
                        obv_i = calc_obv(close_i, vol_i)
                        intraday_high_10 = float(close_i.iloc[-11:-1].max()) if len(close_i) >= 11 else float(close_i.iloc[-1])

                        intraday_break = float(close_i.iloc[-1]) > intraday_high_10
                        intraday_obv_up = len(obv_i) >= 3 and obv_i.iloc[-1] > obv_i.iloc[-2] > obv_i.iloc[-3]
                        intraday_note = "Intraday xác nhận" if (intraday_break or intraday_obv_up) else "Intraday trung tính"

                        chart_close = close_i.tail(80)
                        chart_ema9 = ema9_i.tail(80)
                        chart_ma20 = close_i.rolling(20).mean().tail(80)
                    else:
                        intraday_note = "Intraday thiếu dữ liệu"
                else:
                    intraday_note = "Intraday không có dữ liệu"
            except Exception:
                intraday_note = "Intraday lỗi"

        # ===== SCORE 10 ĐIỂM =====
        score = 0
        score += int(price_above_ema9)
        score += int(rsi_strong)
        score += int(rsi_above_ema)
        score += int(obv_above_ema)
        score += int(obv_up)
        score += int(pull_ok)
        score += int(can_cung)
        score += int(breakout_ok)
        score += int(intraday_break)
        score += int(intraday_obv_up)

        # ===== STATUS =====
        if score >= 7:
            status = "🟩 ƯU TIÊN MUA"
        elif score >= 5:
            status = "🟨 THEO DÕI"
        elif score >= 3:
            status = "🟦 EARLY REVERSAL"
        else:
            status = "🟥 LOẠI"

        # ===== STAGE =====
        if breakout_ok and intraday_break:
            stage = "🚀 Break mạnh + intraday xác nhận"
        elif breakout_ok:
            stage = "🚀 Break daily"
        elif pull_ok and can_cung:
            stage = "📉 Pull đẹp + cạn cung"
        elif pull_ok:
            stage = "📉 Pull đẹp"
        elif intraday_obv_up:
            stage = "🌱 Early intraday"
        elif score >= 3:
            stage = "🌱 Early daily"
        else:
            stage = "❌ Chưa đạt"

        # ===== HÀNH ĐỘNG =====
        if market_score < 8:
            action = "Đứng ngoài / giữ tỷ trọng thấp"
        else:
            if status == "🟩 ƯU TIÊN MUA":
                if pull_ok:
                    action = "Canh mua pull"
                elif breakout_ok or intraday_break:
                    action = "Canh mua break"
                else:
                    action = "Ưu tiên theo dõi sát"
            elif status == "🟨 THEO DÕI":
                action = "Chờ xác nhận thêm"
            elif status == "🟦 EARLY REVERSAL":
                action = "Mua thăm dò nhỏ"
            else:
                action = "Loại"

        # ===== NAV GỢI Ý =====
        if market_score < 8:
            nav = "0-10%"
        else:
            if status == "🟩 ƯU TIÊN MUA":
                nav = "20-30%"
            elif status == "🟨 THEO DÕI":
                nav = "10-15%"
            elif status == "🟦 EARLY REVERSAL":
                nav = "5-10%"
            else:
                nav = "0%"

        gold_score = market_score * score if market_score >= 8 else 0

        chart_df = pd.DataFrame({
            "Close": chart_close,
            "EMA9": chart_ema9,
            "MA20": chart_ma20,
        }).dropna(how="all")

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
            "Intraday Break": "✅" if intraday_break else "❌",
            "Intraday OBV": "✅" if intraday_obv_up else "❌",
            "Score": score,
            "Gold Score": gold_score,
            "Stage": stage,
            "Status": status,
            "Hành động": action,
            "NAV gợi ý": nav,
            "Ghi chú intraday": intraday_note,
            "_chart": chart_df,
        }
    except Exception:
        return None

# =========================
# STYLE
# =========================
st.markdown("""
<style>
div[data-testid="stDataFrame"] {
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)

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
use_intraday = st.sidebar.toggle("Bật quét intraday", value=True)
intraday_interval = st.sidebar.selectbox("Khung intraday", ["15m", "5m"], index=0)

# =========================
# TITLE
# =========================
st.title("🐔 Scanner Gà Chiến V7")
st.caption("V7: có intraday gần realtime, cột Stage rộng hơn, thêm NAV gợi ý và ghi chú intraday.")

# =========================
# INPUT
# =========================
watchlist_text = st.text_area(
    "Danh sách mã theo ngành",
    value=build_default_text(),
    height=280
)

col_a, col_b, col_c = st.columns([1, 1, 1])
with col_a:
    run_scan = st.button("🚀 Quét ngay", use_container_width=True)
with col_b:
    refresh_now = st.button("🔄 Refresh", use_container_width=True)
with col_c:
    st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

if refresh_now:
    st.rerun()

# =========================
# RUN
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
            row = analyze_ticker(sector, ticker, market_score, use_intraday, intraday_interval)
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

            out = out[out["Status"].isin(status_filter)].copy()
            charts = {row["Ticker"]: row["_chart"] for row in results}

            display_cols = [
                "Sector", "Ticker", "Close", "EMA9", "MA20", "RSI",
                "OBV > EMA9", "Pull đẹp", "Cạn cung", "Break chuẩn",
                "Intraday Break", "Intraday OBV",
                "Score", "Gold Score", "Stage", "Status", "Hành động", "NAV gợi ý", "Ghi chú intraday"
            ]

            st.subheader("📊 Kết quả quét tổng hợp")
            st.dataframe(
                out[display_cols],
                use_container_width=True,
                column_config={
                    "Stage": st.column_config.TextColumn("Stage", width="large"),
                    "Hành động": st.column_config.TextColumn("Hành động", width="medium"),
                    "Ghi chú intraday": st.column_config.TextColumn("Ghi chú intraday", width="medium"),
                }
            )

            top_market = out.head(show_top_n)
            st.subheader(f"🔥 Top {show_top_n} toàn thị trường")
            st.dataframe(
                top_market[display_cols],
                use_container_width=True,
                column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
            )

            st.subheader("🏆 Top 1 mỗi ngành")
            top_sector = (
                out.sort_values(by=["Gold Score", "Score", "RSI"], ascending=False)
                   .groupby("Sector", as_index=False)
                   .head(1)
            )
            st.dataframe(
                top_sector[display_cols],
                use_container_width=True,
                column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
            )

            st.subheader("🔥 Nhóm ƯU TIÊN MUA")
            st.dataframe(
                out[out["Status"] == "🟩 ƯU TIÊN MUA"][display_cols],
                use_container_width=True,
                column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
            )

            st.subheader("👀 Nhóm THEO DÕI")
            st.dataframe(
                out[out["Status"] == "🟨 THEO DÕI"][display_cols],
                use_container_width=True,
                column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
            )

            st.subheader("🌱 Nhóm EARLY REVERSAL")
            st.dataframe(
                out[out["Status"] == "🟦 EARLY REVERSAL"][display_cols],
                use_container_width=True,
                column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
            )

            st.subheader("🚨 Gà chiến mới nổi")
            alert = out[(out["Status"] == "🟩 ƯU TIÊN MUA") & ((out["Break chuẩn"] == "✅") | (out["Intraday Break"] == "✅"))]
            if not alert.empty:
                st.success("Có gà mạnh mới nổi.")
                st.dataframe(
                    alert[display_cols],
                    use_container_width=True,
                    column_config={"Stage": st.column_config.TextColumn("Stage", width="large")}
                )
            else:
                st.info("Chưa có gà mới nổi.")

            st.subheader("📈 Xem chart nhanh từng mã")
            selected = st.selectbox("Chọn mã để xem chart", out["Ticker"].tolist())
            if selected in charts:
                st.line_chart(charts[selected], use_container_width=True)

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
