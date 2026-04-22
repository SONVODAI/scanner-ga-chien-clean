import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Scanner Gà Chiến V26", layout="wide")

# =========================
# TIME VN
# =========================
vn_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))

# =========================
# STYLE
# =========================
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
    margin-top: 20px;
    margin-bottom: 10px;
}
.small-note {
    color: #666;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# =========================
# WATCHLIST FALLBACK
# =========================
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

# =========================
# FALLBACK DATA
# =========================
def generate_full_market():
    np.random.seed(26)
    rows = []
    for s in WATCHLIST:
        price = np.random.randint(10000, 90000)
        open_p = price * np.random.uniform(0.985, 1.015)
        high = max(price, open_p) * np.random.uniform(1.002, 1.03)
        low = min(price, open_p) * np.random.uniform(0.97, 0.998)
        high_prev = price * np.random.uniform(0.98, 1.01)

        volume = np.random.randint(800000, 20000000)
        vol_sma20 = np.random.randint(800000, 18000000)

        ema9 = price * np.random.uniform(0.96, 1.03)
        ma20 = ema9 * np.random.uniform(0.96, 1.05)

        rsi14 = np.random.uniform(42, 80)
        rsi_ema9 = rsi14 - np.random.uniform(-2.0, 4.0)
        rsi_prev = rsi14 - np.random.uniform(-2.0, 2.0)

        obv = np.random.randint(-100000000, 300000000)
        obv_ema9 = obv - np.random.randint(-15000000, 30000000)
        obv_prev = obv - np.random.randint(-12000000, 12000000)

        rows.append([
            s,
            round(price, 2),
            round(open_p, 2),
            round(high, 2),
            round(low, 2),
            round(high_prev, 2),
            volume,
            vol_sma20,
            round(ema9, 2),
            round(ma20, 2),
            round(rsi14, 2),
            round(rsi_ema9, 2),
            round(rsi_prev, 2),
            int(obv),
            int(obv_ema9),
            int(obv_prev),
        ])

    cols = [
        "symbol", "price", "open", "high", "low", "high_prev", "volume", "vol_sma20",
        "ema9", "ma20", "rsi14", "rsi_ema9", "rsi_prev",
        "obv", "obv_ema9", "obv_prev"
    ]
    return pd.DataFrame(rows, columns=cols)

# =========================
# LOAD FILE
# =========================
def load_uploaded_file(uploaded_file):
    try:
        name = uploaded_file.name.lower()
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            return pd.read_excel(uploaded_file)
        return None
    except Exception as e:
        st.error(f"Lỗi đọc file upload: {e}")
        return None

def normalize_columns(df):
    df = df.copy()

    rename_map = {
        "ticker": "symbol",
        "code": "symbol",
        "stock": "symbol",

        "close": "price",
        "Close": "price",

        "Open": "open",
        "High": "high",
        "Low": "low",
        "Volume": "volume",

        "EMA9": "ema9",
        "MA20": "ma20",

        "RSI": "rsi14",
        "RSI14": "rsi14",
        "RSI_EMA9": "rsi_ema9",
        "RSI_PREV": "rsi_prev",

        "OBV": "obv",
        "OBV_EMA9": "obv_ema9",
        "OBV_PREV": "obv_prev",

        "HIGH_PREV": "high_prev",
        "VOL_SMA20": "vol_sma20",
    }

    df = df.rename(columns=rename_map)

    required = [
        "symbol", "price", "open", "high", "low", "high_prev", "volume", "vol_sma20",
        "ema9", "ma20", "rsi14", "rsi_ema9", "rsi_prev",
        "obv", "obv_ema9", "obv_prev"
    ]

    for c in required:
        if c not in df.columns:
            df[c] = np.nan

    for c in required:
        if c != "symbol":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

# =========================
# LOGIC CORE
# =========================
def add_features(df):
    df = df.copy()
    df["dist_from_ema9_pct"] = (df["price"] - df["ema9"]) / df["ema9"].replace(0, np.nan) * 100
    df["ema9_ma20_gap_pct"] = (df["ema9"] - df["ma20"]) / df["ma20"].replace(0, np.nan) * 100
    df["price_green_today"] = df["price"] > df["open"]
    df["rsi_accel"] = df["rsi14"] - df["rsi_prev"]
    df["obv_flow"] = df["obv"] - df["obv_prev"]
    df["vol_ratio"] = df["volume"] / df["vol_sma20"].replace(0, np.nan)
    df["obv_status"] = np.where(df["obv"] > df["obv_ema9"], "🟢", "🔴")
    return df

def classify_group(row):
    price = row["price"]
    ema9 = row["ema9"]
    ma20 = row["ma20"]
    rsi = row["rsi14"]
    obv_ok = row["obv"] > row["obv_ema9"] if pd.notna(row["obv"]) and pd.notna(row["obv_ema9"]) else False
    rsi_ok = row["rsi14"] > row["rsi_ema9"] if pd.notna(row["rsi14"]) and pd.notna(row["rsi_ema9"]) else False
    dist = row["dist_from_ema9_pct"]

    # 1) CP MẠNH = leader, KHÔNG phải điểm mua
    if price > ema9 > ma20 and rsi >= 60 and obv_ok and rsi_ok:
        return "CP MẠNH"

    # 2) ENTRY
    if abs(dist) <= 1 and rsi >= 55:
        return "PULL ĐẸP"

    if abs(dist) <= 3 and rsi >= 50:
        return "PULL VỪA"

    if rsi > 60 and dist > 2:
        return "MUA BREAK"

    # 3) EARLY
    if 45 <= rsi <= 55:
        return "MUA EARLY"

    # 4) tích lũy
    if 45 <= rsi <= 60:
        return "TÍCH LŨY"

    return "THEO DÕI"

def calc_scores(df):
    df = df.copy()

    # E = Energy / động lượng
    df["E"] = 0
    df.loc[df["rsi14"] > 55, "E"] += 1
    df.loc[df["price"] > df["ema9"], "E"] += 1
    df["E"] = df["E"].clip(0, 2)

    # R = Risk
    df["R"] = 0
    df.loc[df["rsi14"] >= 75, "R"] += 1
    df.loc[df["dist_from_ema9_pct"].abs() >= 5, "R"] += 1
    df["R"] = df["R"].clip(0, 2)

    # O = OBV / dòng tiền
    df["O"] = np.where(df["obv"] > df["obv_ema9"], 2, 1)

    df["total_score"] = df["E"] + (2 - df["R"]) + df["O"]
    df["pull_label"] = np.where(
        df["dist_from_ema9_pct"].abs() <= 1.2, "PULL ĐẸP",
        np.where(df["dist_from_ema9_pct"].abs() <= 3.2, "PULL VỪA", "PULL XẤU")
    )
    return df

def process_df(df):
    df = normalize_columns(df)
    df = add_features(df)
    df["group"] = df.apply(classify_group, axis=1)
    df = calc_scores(df)
    return df

# =========================
# MARKET SCORE
# =========================
def calc_market_scores(df):
    total_n = max(len(df), 1)

    strong_n = len(df[df["group"].isin(["CP MẠNH", "MUA BREAK", "PULL ĐẸP", "PULL VỪA"])])
    overheat_n = len(df[df["rsi14"] >= 75])
    far_ema_n = len(df[df["dist_from_ema9_pct"].abs() >= 5])
    pull_bad_n = len(df[df["pull_label"] == "PULL XẤU"])

    base_score = (strong_n / total_n) * 10.0
    overheat_penalty = (overheat_n / total_n) * 3.0
    far_ema_penalty = (far_ema_n / total_n) * 3.0
    pull_bad_penalty = (pull_bad_n / total_n) * 2.0

    market_real = round(base_score - overheat_penalty - far_ema_penalty - pull_bad_penalty + 5.0, 1)
    market_real = max(3.0, min(10.0, market_real))
    market_live = round(max(0.0, market_real - 0.7), 1)
    return market_real, market_live

# =========================
# TOP VÀO TIỀN
# =========================
def pick_top_money(df):
    df = df.copy()

    entry_groups = ["PULL ĐẸP", "PULL VỪA", "MUA BREAK"]
    top_money = df[
        (df["group"].isin(entry_groups)) &
        (df["rsi14"] > 55)
    ].sort_values(
        by=["volume", "vol_ratio", "rsi_accel", "total_score"],
        ascending=[False, False, False, False]
    ).head(5)

    return top_money

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V26</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {vn_now.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {vn_now.strftime('%H:%M:%S')}")

scan = st.button("🔄 SCAN")
st.markdown(
    '<div class="small-note">V26 đã tách chuẩn: CP MẠNH = leader, ENTRY = điểm mua, Top vào tiền chỉ lấy từ nhóm entry.</div>',
    unsafe_allow_html=True
)

uploaded = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])

# =========================
# SESSION
# =========================
if "scanner_df_v26" not in st.session_state:
    st.session_state["scanner_df_v26"] = process_df(generate_full_market())

if scan:
    if uploaded is not None:
        raw = load_uploaded_file(uploaded)
        if raw is not None and not raw.empty:
            st.session_state["scanner_df_v26"] = process_df(raw)
        else:
            st.warning("File upload lỗi hoặc rỗng. Tạm dùng fallback.")
            st.session_state["scanner_df_v26"] = process_df(generate_full_market())
    else:
        st.session_state["scanner_df_v26"] = process_df(generate_full_market())

df = st.session_state["scanner_df_v26"]

# =========================
# MARKET OVERVIEW
# =========================
st.markdown("---")
st.markdown('<div class="section-title">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)

market_real, market_live = calc_market_scores(df)

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

st.caption("REAL để ra quyết định. LIVE để quan sát trong phiên.")

# =========================
# TOP VÀO TIỀN HÔM NAY
# =========================
st.markdown("---")
st.markdown('<div class="section-title">🎯 TOP VÀO TIỀN HÔM NAY</div>', unsafe_allow_html=True)

top = pick_top_money(df)

if top.empty:
    st.write("Chưa có mã vào tiền nổi bật hôm nay.")
else:
    for _, r in top.iterrows():
        nav = "10-15% NAV"
        st.write(f"**{r['symbol']} — {r['group']}**")
        st.write(
            f"Giá: {r['price']} | Score: {r['total_score']} | "
            f"Dist EMA9: {round(r['dist_from_ema9_pct'], 2)}% | "
            f"Vol ratio: {round(r['vol_ratio'], 2) if pd.notna(r['vol_ratio']) else '-'} | "
            f"RSI accel: {round(r['rsi_accel'], 2)} | Gợi ý NAV: {nav}"
        )
        st.write("")

# =========================
# LIST GROUPS
# =========================
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
            st.dataframe(sub, use_container_width=True, height=360)

# =========================
# TOP 20 E-R-O
# =========================
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

st.dataframe(top20[ero_cols], use_container_width=True, height=420)

# =========================
# FULL DETAIL TABLE
# =========================
st.markdown("---")
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

filter_mode = st.selectbox(
    "Hiển thị dữ liệu",
    ["Tất cả", ">= 4 điểm", ">= 5 điểm"],
    index=0
)

if filter_mode == ">= 4 điểm":
    df_display = df[df["total_score"] >= 4].copy()
elif filter_mode == ">= 5 điểm":
    df_display = df[df["total_score"] >= 5].copy()
else:
    df_display = df.copy()

# sort mã mạnh phía trên
group_priority = {
    "CP MẠNH": 0,
    "MUA BREAK": 1,
    "PULL ĐẸP": 2,
    "PULL VỪA": 3,
    "MUA EARLY": 4,
    "TÍCH LŨY": 5,
    "THEO DÕI": 6
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

st.dataframe(df_display[detail_cols], use_container_width=True, height=560)

st.markdown("---")
st.caption("Đọc nhanh: CP MẠNH = leader đang chạy. ENTRY = điểm mua. Top vào tiền chỉ lấy từ ENTRY. Bảng E-R-O để quyết định nhanh.")
