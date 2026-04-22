import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from vnstock import Quote

st.set_page_config(page_title="Scanner Gà Chiến V29", layout="wide")

# =========================================================
# STYLE
# =========================================================
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
# DANH MỤC THEO NHÓM NGÀNH
# Bỏ hẳn nhóm y tế theo ý anh
# =========================================================
SECTORS = {
    "BANK_CHUNGKHOAN": [
        "VCB","BID","CTG","TCB","VPB","MBB","ACB","SHB","SSB","STB","HDB","TPB","VIB","LPB","OCB","MSB","NAB","EIB",
        "VND","SSI","HCM","SHS","VIX","BSI","FTS","TVS","APS","AGR","VCI"
    ],
    "BDS_THEP_DAUTUCONG": [
        "C4G","FCN","CII","KSB","DHA","CTI","HBC","HPG","HSG","NKG","VGS","CTD","HHV","VCG",
        "HAG","TCH","DIG","DXG","CEO","NVL","VIC","VHM","VRE"
    ],
    "DAUKHI_VANTAi_LOGISTIC": [
        "PLX","PVS","PVD","PVB","PVC","PVT","BSR","OIL","GAS","HAH","VSC","GMD","VOS","VTO","ACV"
    ],
    "XUATKHAU_HOACHAT_DIEN": [
        "MSH","TNG","TCM","GIL","VHC","ANV","FMC","VCS","PTB",
        "BFC","DCM","DPM","CSV","DDV","LAS","BMP","NTP","AAA","PAC","MSR","REE","GEE","GEX","PC1","HDG","GEG","NT2","TV2","DGC"
    ],
    "BANLE_CONGNGHE_KHAC": [
        "MWG","FRT","DGW","PET","HAX","MSN","BAF","MCH","PAN","VNM","MML",
        "FPT","VGI","CTR","VTP","CMG","ELC","FOX",
        "HVN","VJC","BVH","SBT","LSS","PNJ","TLG","TNH"
    ],
}

SECTOR_ORDER = list(SECTORS.keys())

# =========================================================
# INDICATORS - THUẦN PANDAS
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
    out = 100 - (100 / (1 + rs))
    return out.bfill()

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    diff = close.diff().fillna(0)
    direction = np.sign(diff)
    direction = pd.Series(direction, index=close.index).replace(0, method="ffill").fillna(0)
    return (direction * volume).cumsum()

# =========================================================
# FETCH VNSTOCK
# =========================================================
@st.cache_data(ttl=180)
def fetch_symbol_history(symbol: str, source: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        quote = Quote(symbol=symbol, source=source)
        df = quote.history(start=start_date, end=end_date, interval="1D")
    except Exception:
        return pd.DataFrame()

    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()

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
    if any(c not in df.columns for c in needed):
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
    obv_ok = row["obv"] >= row["obv_ema9"]
    dist = abs(row["dist_from_ema9_pct"])
    vol_ratio = row["vol_ratio"]
    green = row["price_green_today"]

    # 1) CP MẠNH = leader thật, không cần là điểm mua
    if price > ema9_v >= ma20_v and rsi >= 58 and obv_ok:
        return "CP MẠNH"

    # 2) BREAK thật
    if price > row["high_3_prev"] and rsi >= 60 and vol_ratio >= 1.25 and green:
        return "MUA BREAK"

    # 3) PULL ĐẸP
    if price > ema9_v >= ma20_v and 55 <= rsi <= 72 and dist <= 1.5 and obv_ok:
        return "PULL ĐẸP"

    # 4) PULL VỪA
    if price > ema9_v >= ma20_v and rsi >= 50 and 1.5 < dist <= 3.0:
        return "PULL VỪA"

    # 5) EARLY
    if 45 <= rsi <= 55 and dist <= 2.0 and abs(row["ema9_ma20_gap_pct"]) <= 4.0:
        return "MUA EARLY"

    # 6) TÍCH LŨY
    if 45 <= rsi <= 60:
        return "TÍCH LŨY"

    return "THEO DÕI"

def calc_ero(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # E = energy
    df["E"] = 0
    df.loc[df["rsi14"] >= 55, "E"] += 1
    df.loc[df["price"] > df["ema9"], "E"] += 1
    df["E"] = df["E"].clip(0, 2)

    # R = risk
    df["R"] = 0
    df.loc[df["rsi14"] >= 75, "R"] += 1
    df.loc[df["dist_from_ema9_pct"].abs() >= 5, "R"] += 1
    df["R"] = df["R"].clip(0, 2)

    # O = dòng tiền
    df["O"] = np.where(df["obv"] >= df["obv_ema9"], 2, 1)

    df["total_score"] = df["E"] + (2 - df["R"]) + df["O"]
    return df

def calc_market_score(df: pd.DataFrame) -> tuple[float, float]:
    pct_above_ema9 = (df["price"] > df["ema9"]).mean()
    pct_above_ma20 = (df["price"] > df["ma20"]).mean()
    avg_rsi = df["rsi14"].mean()
    avg_rsi_accel = df["rsi_accel"].mean()
    pct_obv_ok = (df["obv"] >= df["obv_ema9"]).mean()
    pct_obv_flow_pos = (df["obv_flow"] > 0).mean()
    pct_hot_rsi = (df["rsi14"] >= 75).mean()
    pct_far_ema = (df["dist_from_ema9_pct"].abs() >= 5).mean()

    trend = 0
    if pct_above_ema9 > 0.60:
        trend += 2
    elif pct_above_ema9 > 0.45:
        trend += 1

    if pct_above_ma20 > 0.50:
        trend += 2
    elif pct_above_ma20 > 0.35:
        trend += 1

    momentum = 0
    if avg_rsi > 55:
        momentum += 2
    elif avg_rsi > 50:
        momentum += 1

    if avg_rsi_accel > 0:
        momentum += 1

    money = 0
    if pct_obv_ok > 0.60:
        money += 2
    elif pct_obv_ok > 0.45:
        money += 1

    if pct_obv_flow_pos > 0.55:
        money += 2
    elif pct_obv_flow_pos > 0.45:
        money += 1

    risk_penalty = 0
    if pct_hot_rsi > 0.20:
        risk_penalty += 1
    if pct_far_ema > 0.20:
        risk_penalty += 1

    real_score = trend + momentum + money - risk_penalty
    real_score = round(float(max(0, min(13, real_score))), 1)
    live_score = round(max(0.0, real_score - 0.7), 1)
    return real_score, live_score

def pick_top_money(df: pd.DataFrame) -> pd.DataFrame:
    entry_groups = ["PULL ĐẸP", "PULL VỪA", "MUA BREAK"]
    top = df[
        (df["group"].isin(entry_groups)) &
        (df["vol_ratio"] >= 1.0) &
        (df["rsi_accel"] > 0) &
        (df["price_green_today"])
    ].copy()

    return top.sort_values(
        by=["vol_ratio", "rsi_accel", "volume", "total_score"],
        ascending=[False, False, False, False]
    ).head(5)

# =========================================================
# BUILD TABLE CHO MỘT NHÓM NGÀNH
# =========================================================
@st.cache_data(ttl=180)
def build_sector_table(symbols: tuple[str, ...], source: str, start_date: str, end_date: str) -> pd.DataFrame:
    rows = []

    for symbol in symbols:
        try:
            raw = fetch_symbol_history(symbol, source=source, start_date=start_date, end_date=end_date)
            if raw.empty or len(raw) < 30:
                continue

            x = enrich_indicators(raw).dropna().reset_index(drop=True)
            if len(x) < 25:
                continue

            latest = x.iloc[-1]
            prev = x.iloc[-2]
            high_3_prev = x.iloc[-4:-1]["high"].max() if len(x) >= 4 else prev["high"]

            rows.append({
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
                "obv_status": "🟢" if latest["obv"] >= latest["obv_ema9"] else "🔴",
                "volume": float(latest["volume"]),
                "vol_sma20": float(latest["vol_sma20"]),
                "vol_ratio": float(latest["volume"] / latest["vol_sma20"]) if latest["vol_sma20"] else np.nan,
                "price_green_today": bool(latest["close"] > latest["open"]),
                "dist_from_ema9_pct": float((latest["close"] - latest["ema9"]) / latest["ema9"] * 100),
                "ema9_ma20_gap_pct": float((latest["ema9"] - latest["ma20"]) / latest["ma20"] * 100),
                "obv_flow": float(latest["obv"] - prev["obv"]),
                "high_3_prev": float(high_3_prev),
            })
        except Exception:
            continue

        time.sleep(0.12)

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
# SESSION STATE
# =========================================================
if "scanner_sector_index" not in st.session_state:
    st.session_state["scanner_sector_index"] = 0

if "scanner_data_map" not in st.session_state:
    st.session_state["scanner_data_map"] = {}

if "scanner_last_sector" not in st.session_state:
    st.session_state["scanner_last_sector"] = None

if "scanner_last_time" not in st.session_state:
    st.session_state["scanner_last_time"] = None

# =========================================================
# HEADER
# =========================================================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V29</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {now_vn.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {now_vn.strftime('%H:%M:%S')}")

source = st.selectbox("Nguồn dữ liệu Vnstock", ["KBS", "VCI"], index=0)

b1, b2, b3 = st.columns([1, 1, 3])
with b1:
    scan = st.button("🔄 SCAN ngành tiếp theo", use_container_width=True)
with b2:
    reset_scan = st.button("♻️ Reset vòng quét", use_container_width=True)

if reset_scan:
    st.session_state["scanner_sector_index"] = 0
    st.session_state["scanner_data_map"] = {}
    st.session_state["scanner_last_sector"] = None
    st.session_state["scanner_last_time"] = None

st.markdown(
    '<div class="small-note">V29 quét xoay vòng theo nhóm ngành để tránh treo app. '
    'Mỗi lần bấm SCAN sẽ cập nhật thêm 1 cụm ngành, dữ liệu cũ vẫn được giữ lại.</div>',
    unsafe_allow_html=True
)

# =========================================================
# SCAN MỘT NHÓM NGÀNH MỖI LẦN
# =========================================================
if scan:
    sector_name = SECTOR_ORDER[st.session_state["scanner_sector_index"]]
    symbols = SECTORS[sector_name]

    start_date = (now_vn - timedelta(days=220)).strftime("%Y-%m-%d")
    end_date = now_vn.strftime("%Y-%m-%d")

    with st.spinner(f"Đang quét nhóm: {sector_name} ..."):
        sector_df = build_sector_table(tuple(symbols), source=source, start_date=start_date, end_date=end_date)

    st.session_state["scanner_data_map"][sector_name] = sector_df
    st.session_state["scanner_last_sector"] = sector_name
    st.session_state["scanner_last_time"] = now_vn.strftime("%H:%M:%S")

    st.session_state["scanner_sector_index"] = (st.session_state["scanner_sector_index"] + 1) % len(SECTOR_ORDER)

# =========================================================
# GỘP DỮ LIỆU ĐÃ QUÉT
# =========================================================
frames = [df for df in st.session_state["scanner_data_map"].values() if df is not None and not df.empty]
if len(frames) > 0:
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["symbol"], keep="last").reset_index(drop=True)
else:
    df_all = pd.DataFrame()

# =========================================================
# THÔNG TIN VÒNG QUÉT
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">🔄 TRẠNG THÁI QUÉT</div>', unsafe_allow_html=True)

info1, info2, info3 = st.columns(3)
with info1:
    next_sector = SECTOR_ORDER[st.session_state["scanner_sector_index"]]
    st.write(f"**Ngành kế tiếp:** {next_sector}")
with info2:
    st.write(f"**Ngành vừa quét:** {st.session_state['scanner_last_sector'] or '-'}")
with info3:
    st.write(f"**Lúc quét gần nhất:** {st.session_state['scanner_last_time'] or '-'}")

done_count = len(st.session_state["scanner_data_map"])
st.caption(f"Đã quét {done_count}/{len(SECTOR_ORDER)} cụm ngành. Sau vài lần bấm SCAN, bảng sẽ đủ dần toàn watchlist.")

if df_all.empty:
    st.warning("Chưa có dữ liệu. Anh bấm 'SCAN ngành tiếp theo' để bắt đầu.")
    st.stop()

# =========================================================
# MARKET OVERVIEW
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)

market_real, market_live = calc_market_score(df_all)

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
# TOP VÀO TIỀN
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">🎯 TOP VÀO TIỀN HÔM NAY</div>', unsafe_allow_html=True)

top = pick_top_money(df_all)
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
        sub = df_all[df_all["group"] == g][["symbol", "price"]].reset_index(drop=True)
        if sub.empty:
            st.info("Không có mã")
        else:
            st.dataframe(sub, use_container_width=True, height=360, hide_index=False)

# =========================================================
# TOP 20 E-R-O
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">🧠 TOP 20 CỔ PHIẾU MẠNH (E-R-O)</div>', unsafe_allow_html=True)

top20 = df_all.sort_values(
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
# BẢNG TỔNG CHI TIẾT
# =========================================================
st.markdown("---")
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

filter_mode = st.selectbox("Hiển thị dữ liệu", ["Tất cả", ">= 4 điểm", ">= 5 điểm"], index=0)

if filter_mode == ">= 4 điểm":
    df_display = df_all[df_all["total_score"] >= 4].copy()
elif filter_mode == ">= 5 điểm":
    df_display = df_all[df_all["total_score"] >= 5].copy()
else:
    df_display = df_all.copy()

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
st.caption("CP MẠNH = leader. ENTRY = MUA BREAK / PULL ĐẸP / PULL VỪA. V29 quét xoay vòng theo ngành, dữ liệu tích lũy dần sau mỗi lần bấm SCAN.")
