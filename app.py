import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from vnstock import Quote

# =========================================================
# CONFIG UI
# =========================================================
st.set_page_config(page_title="Scanner Gà Chiến V27", layout="wide")

st.markdown("""
<style>
.main-title {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 10px;
}
.section-title {
    font-size: 20px;
    font-weight: 800;
    margin-top: 22px;
    margin-bottom: 10px;
}
.small-note {
    color: #666;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn = datetime.now(VN_TZ)

# =========================================================
# WATCHLIST CỦA ANH
# =========================================================
WATCHLIST = [
    "PLX","PVS","PVD","PVB","PVC","PVT","BSR","OIL","GAS","HAH","VSC","GMD","VOS","VTO","ACV",
    "MSH","TNG","TCM","GIL","VHC","ANV","FMC","VCS","PTB",
    "BFC","DCM","DPM","CSV","DDV","LAS","BMP","NTP","AAA","PAC","MSR","REE","GEE","GEX","PC1","HDG","GEG","NT2","TV2","DGC",
    "C4G","FCN","CII","KSB","DHA","CTI","HBC","HPG","HSG","NKG","VGS","CTD","HHV","VCG",
    "MWG","FRT","DGW","PET","HAX","MSN","DBC","HAG","BAF","MCH","PAN","VNM","MML",
    "VCB","BID","CTG","TCB","VPB","MBB","ACB","SHB","SSB","STB","HDB","TPB","VIB","LPB","OCB","MSB","NAB","EIB","VND","SSI","HCM","SHS","VIX","BSI","FTS","TVS","APS","AGR","VCI",
    "FPT","VGI","CTR","VTP","CMG","ELC","FOX",
    "HVN","VJC","IMP","BVH","SBT","LSS","PNJ","TLG","DHT","TNH"
]

# =========================================================
# INDICATORS - KHÔNG DÙNG pandas_ta
# =========================================================
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()

def rsi_wilder(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(method="bfill")

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    direction = direction.replace(0, method="ffill").fillna(0)
    return (direction * volume).cumsum()

# =========================================================
# FETCH DỮ LIỆU VNSTOCK
# Docs Vnstock hiện dùng Quote(symbol, source).history(...)
# và hỗ trợ source VCI/KBS. VCI đầy đủ hơn. 
# =========================================================
@st.cache_data(ttl=180)
def fetch_symbol_history(symbol: str, source: str = "VCI", length: str = "6M") -> pd.DataFrame:
    quote = Quote(symbol=symbol, source=source)
    df = quote.history(length=length, interval="1D")
    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()
    # Chuẩn hóa tên cột
    cols = {c.lower(): c for c in df.columns}
    rename_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl == "time":
            rename_map[c] = "time"
        elif cl == "open":
            rename_map[c] = "open"
        elif cl == "high":
            rename_map[c] = "high"
        elif cl == "low":
            rename_map[c] = "low"
        elif cl == "close":
            rename_map[c] = "close"
        elif cl == "volume":
            rename_map[c] = "volume"
    df = df.rename(columns=rename_map)

    needed = ["time", "open", "high", "low", "close", "volume"]
    for c in needed:
        if c not in df.columns:
            return pd.DataFrame()

    df = df[needed].copy()
    df["time"] = pd.to_datetime(df["time"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    return df

def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ma20"] = sma(df["close"], 20)
    df["rsi14"] = rsi_wilder(df["close"], 14)
    df["rsi_ema9"] = ema(df["rsi14"], 9)
    df["obv"] = obv(df["close"], df["volume"])
    df["obv_ema9"] = ema(df["obv"], 9)
    df["vol_sma20"] = sma(df["volume"], 20)
    return df

# =========================================================
# LOGIC TRADER
# =========================================================
def classify_group(row: pd.Series) -> str:
    price = row["price"]
    ema9_v = row["ema9"]
    ma20_v = row["ma20"]
    rsi = row["rsi14"]
    obv_ok = row["obv"] > row["obv_ema9"]
    dist = row["dist_from_ema9_pct"]
    vol_ratio = row["vol_ratio"]
    price_green = row["price_green_today"]

    # CP MẠNH = leader thật, không phải điểm mua
    if price > ema9_v > ma20_v and rsi >= 58 and obv_ok:
        return "CP MẠNH"

    # MUA BREAK = break thật có volume
    if row["price"] > row["high_3_prev"] and rsi >= 60 and vol_ratio >= 1.3 and price_green:
        return "MUA BREAK"

    # PULL ĐẸP = pull sát EMA9, vẫn giữ trục
    if price > ema9_v >= ma20_v and 55 <= rsi <= 70 and abs(dist) <= 1.5 and obv_ok:
        return "PULL ĐẸP"

    # PULL VỪA
    if price > ema9_v >= ma20_v and rsi >= 50 and 1.5 < abs(dist) <= 3.0:
        return "PULL VỪA"

    # EARLY
    if 45 <= rsi <= 55 and abs(dist) <= 2.0 and abs(row["ema9_ma20_gap_pct"]) <= 4.0:
        return "MUA EARLY"

    # Tích lũy
    if 45 <= rsi <= 60:
        return "TÍCH LŨY"

    return "THEO DÕI"

def calc_ero(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # E = Energy
    out["E"] = 0
    out.loc[out["rsi14"] >= 55, "E"] += 1
    out.loc[out["price"] > out["ema9"], "E"] += 1
    out["E"] = out["E"].clip(0, 2)

    # R = Risk
    out["R"] = 0
    out.loc[out["rsi14"] >= 75, "R"] += 1
    out.loc[out["dist_from_ema9_pct"].abs() >= 5, "R"] += 1
    out["R"] = out["R"].clip(0, 2)

    # O = OBV / dòng tiền
    out["O"] = np.where(out["obv"] > out["obv_ema9"], 2, 1)

    out["total_score"] = out["E"] + (2 - out["R"]) + out["O"]
    return out

def calc_market_score(df: pd.DataFrame) -> tuple[float, float]:
    n = max(len(df), 1)

    pct_above_ema9 = (df["price"] > df["ema9"]).mean()
    pct_above_ma20 = (df["price"] > df["ma20"]).mean()
    avg_rsi = df["rsi14"].mean()
    avg_rsi_accel = df["rsi_accel"].mean()
    pct_obv_ok = (df["obv"] > df["obv_ema9"]).mean()
    avg_obv_flow_pos = (df["obv_flow"] > 0).mean()

    pct_hot_rsi = (df["rsi14"] >= 75).mean()
    pct_far_ema = (df["dist_from_ema9_pct"].abs() >= 5).mean()

    trend = 0
    if pct_above_ema9 > 0.60: trend += 2
    elif pct_above_ema9 > 0.45: trend += 1
    if pct_above_ma20 > 0.50: trend += 2
    elif pct_above_ma20 > 0.35: trend += 1

    momentum = 0
    if avg_rsi > 55: momentum += 2
    elif avg_rsi > 50: momentum += 1
    if avg_rsi_accel > 0: momentum += 1

    money = 0
    if pct_obv_ok > 0.60: money += 2
    elif pct_obv_ok > 0.45: money += 1
    if avg_obv_flow_pos > 0.55: money += 2
    elif avg_obv_flow_pos > 0.45: money += 1

    risk_penalty = 0
    if pct_hot_rsi > 0.20: risk_penalty += 1
    if pct_far_ema > 0.20: risk_penalty += 1

    real_score = trend + momentum + money - risk_penalty
    real_score = round(max(0, min(13, real_score)), 1)
    live_score = round(max(0, real_score - 0.7), 1)
    return real_score, live_score

def pick_top_money(df: pd.DataFrame) -> pd.DataFrame:
    entry_groups = ["PULL ĐẸP", "PULL VỪA", "MUA BREAK"]
    top = df[
        (df["group"].isin(entry_groups)) &
        (df["vol_ratio"] >= 1.0) &
        (df["rsi_accel"] > 0)
    ].copy()

    top = top.sort_values(
        by=["vol_ratio", "rsi_accel", "volume", "total_score"],
        ascending=[False, False, False, False]
    ).head(5)
    return top

# =========================================================
# PIPELINE
# =========================================================
@st.cache_data(ttl=180)
def build_scanner_table(symbols: list[str], source: str) -> pd.DataFrame:
    rows = []

    for symbol in symbols:
        try:
            raw = fetch_symbol_history(symbol, source=source, length="6M")
            if raw.empty or len(raw) < 30:
                continue

            x = enrich_indicators(raw)
            x = x.dropna().reset_index(drop=True)
            if len(x) < 25:
                continue

            latest = x.iloc[-1]
            prev = x.iloc[-2]
            high_3_prev = x.iloc[-4:-1]["high"].max() if len(x) >= 4 else prev["high"]

            row = {
                "symbol": symbol,
                "price": float(latest["close"]),
                "open": float(latest["open"]),
                "ema9": float(latest["ema9"]),
                "ma20": float(latest["ma20"]),
                "rsi14": float(latest["rsi14"]),
                "rsi_prev": float(prev["rsi14"]),
                "rsi_accel": float(latest["rsi14"] - prev["rsi14"]),
                "obv": float(latest["obv"]),
                "obv_prev": float(prev["obv"]),
                "obv_ema9": float(latest["obv_ema9"]),
                "obv_status": "🟢" if latest["obv"] > latest["obv_ema9"] else "🔴",
                "volume": float(latest["volume"]),
                "vol_sma20": float(latest["vol_sma20"]),
                "vol_ratio": float(latest["volume"] / latest["vol_sma20"]) if latest["vol_sma20"] else np.nan,
                "price_green_today": bool(latest["close"] > latest["open"]),
                "dist_from_ema9_pct": float((latest["close"] - latest["ema9"]) / latest["ema9"] * 100),
                "ema9_ma20_gap_pct": float((latest["ema9"] - latest["ma20"]) / latest["ma20"] * 100),
                "high_3_prev": float(high_3_prev),
            }
            rows.append(row)
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["group"] = df.apply(classify_group, axis=1)
    df["pull_label"] = np.where(
        df["dist_from_ema9_pct"].abs() <= 1.5, "PULL ĐẸP",
        np.where(df["dist_from_ema9_pct"].abs() <= 3.0, "PULL VỪA", "PULL XẤU")
    )
    df = calc_ero(df)
    return df

# =========================================================
# HEADER
# =========================================================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V27</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {now_vn.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {now_vn.strftime('%H:%M:%S')}")

source = st.selectbox("Nguồn dữ liệu Vnstock", ["VCI", "KBS"], index=0)
scan = st.button("🔄 SCAN")
st.markdown(
    '<div class="small-note">Bản này dùng Vnstock Quote.history(), không dùng pandas_ta. '
    'VCI thường đầy đủ hơn; KBS hợp Colab/Kaggle hơn theo tài liệu Vnstock.</div>',
    unsafe_allow_html=True
)

# =========================================================
# SESSION
# =========================================================
if "scanner_df_v27" not in st.session_state:
    st.session_state["scanner_df_v27"] = pd.DataFrame()

if scan or st.session_state["scanner_df_v27"].empty:
    with st.spinner("Đang tải dữ liệu thật từ Vnstock..."):
        st.session_state["scanner_df_v27"] = build_scanner_table(WATCHLIST, source=source)

df = st.session_state["scanner_df_v27"]

if df.empty:
    st.error("Không lấy được dữ liệu. Kiểm tra lại requirements.txt, mạng, hoặc đổi source từ VCI sang KBS.")
    st.stop()

# =========================================================
# MARKET OVERVIEW
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)

market_real, market_live = calc_market_score(df)

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Market REAL", f"{market_real}/13")
with m2:
    st.metric("Market LIVE", f"{market_live}/13")
with m3:
    if market_real >= 8:
        st.markdown("### 🟢 KHỎE")
    elif market_real >= 6:
        st.markdown("### 🟡 TRUNG TÍNH")
    else:
        st.markdown("### 🔴 YẾU")

if market_real >= 8:
    st.success("Có thể đánh mạnh hơn")
elif market_real >= 6:
    st.warning("Chỉ nên test nhỏ")
else:
    st.error("Ưu tiên phòng thủ")

st.caption("Market REAL = quyết định. Market LIVE = quan sát trong phiên.")

# =========================================================
# TOP VÀO TIỀN HÔM NAY
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">🎯 TOP VÀO TIỀN HÔM NAY</div>', unsafe_allow_html=True)

top = pick_top_money(df)
if top.empty:
    st.write("Chưa có mã vào tiền nổi bật hôm nay.")
else:
    for _, r in top.iterrows():
        st.write(f"**{r['symbol']} — {r['group']}**")
        st.write(
            f"Giá: {round(r['price'],2)} | "
            f"Score: {int(r['total_score'])} | "
            f"Dist EMA9: {round(r['dist_from_ema9_pct'],2)}% | "
            f"Vol ratio: {round(r['vol_ratio'],2)} | "
            f"RSI accel: {round(r['rsi_accel'],2)} | "
            f"Gợi ý NAV: 10-15% NAV"
        )
        st.write("")

# =========================================================
# LIST GROUPS
# =========================================================
st.markdown("---")
groups = ["CP MẠNH", "MUA BREAK", "PULL ĐẸP", "PULL VỪA", "MUA EARLY", "TÍCH LŨY", "THEO DÕI"]
cols = st.columns(len(groups))

for i, g in enumerate(groups):
    with cols[i]:
        st.markdown(f"### {g}")
        sub = df[df["group"] == g][["symbol", "price"]].reset_index(drop=True)
        if sub.empty:
            st.info("Không có mã")
        else:
            st.dataframe(sub, use_container_width=True, height=360, hide_index=False)

# =========================================================
# TOP 20 E-R-O
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">🧠 TOP 20 CỔ PHIẾU MẠNH (E-R-O)</div>', unsafe_allow_html=True)

top20 = df.sort_values(
    by=["total_score", "E", "O", "price"],
    ascending=[False, False, False, False]
).head(20)

ero_cols = [
    "symbol", "group", "price",
    "E", "R", "O", "total_score",
    "rsi14", "dist_from_ema9_pct", "obv_status"
]
st.dataframe(top20[ero_cols], use_container_width=True, height=420, hide_index=False)

# =========================================================
# FULL DETAIL TABLE
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

filter_mode = st.selectbox("Hiển thị dữ liệu", ["Tất cả", ">= 4 điểm", ">= 5 điểm"], index=0)

if filter_mode == ">= 4 điểm":
    df_display = df[df["total_score"] >= 4].copy()
elif filter_mode == ">= 5 điểm":
    df_display = df[df["total_score"] >= 5].copy()
else:
    df_display = df.copy()

group_priority = {
    "CP MẠNH": 0,
    "MUA BREAK": 1,
    "PULL ĐẸP": 2,
    "PULL VỪA": 3,
    "MUA EARLY": 4,
    "TÍCH LŨY": 5,
    "THEO DÕI": 6,
}
df_display["group_priority"] = df_display["group"].map(group_priority).fillna(9)
df_display = df_display.sort_values(
    by=["group_priority", "total_score", "E", "O", "price"],
    ascending=[True, False, False, False, False]
)

detail_cols = [
    "symbol", "group", "price", "open", "ema9", "ma20",
    "rsi14", "rsi_prev", "rsi_accel",
    "obv", "obv_prev", "obv_ema9", "obv_status",
    "volume", "vol_sma20", "vol_ratio",
    "price_green_today",
    "dist_from_ema9_pct", "pull_label"
]
st.dataframe(df_display[detail_cols], use_container_width=True, height=560, hide_index=False)

st.markdown("---")
st.caption("CP MẠNH = leader. ENTRY = MUA BREAK / PULL ĐẸP / PULL VỪA. Top vào tiền chỉ lấy từ ENTRY.")
