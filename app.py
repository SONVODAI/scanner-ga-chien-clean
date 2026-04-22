import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Scanner Gà Chiến V22", layout="wide")

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
# DEMO DATA
# =========================
def make_demo_data():
    data = [
        # symbol, price, open, high, low, high_prev, volume, vol_sma20, ema9, ma20, rsi14, rsi_ema9, rsi_prev, obv, obv_ema9, obv_prev, E, R, Q, dist_from_ema9_pct
        ["MSH", 38700, 38950, 39000, 38550, 38400, 1800000, 1500000, 37564.16, 37280, 60.16, 55.81, 57.20, 11054899, 10711110, 10600000, 2, 1, 2, 3.02],
        ["BAF", 36650, 37000, 37200, 36550, 36400, 2200000, 2100000, 35990.81, 35295, 65.41, 63.36, 64.10, 79514377, 74420465, 77000000, 2, 2, 2, 1.83],
        ["CII", 19150, 19280, 19350, 19080, 19000, 1700000, 1400000, 19057.94, 18700, 56.66, 55.54, 54.90, -44109676, -48783752, -45000000, 2, 1, 2, 0.48],
        ["FMC", 38850, 38620, 38980, 38550, 38450, 1600000, 1200000, 38419.06, 38210, 55.31, 53.22, 52.80, 625428, 527981, 500000, 2, 1, 2, 1.12],
        ["MSB", 12600, 12480, 12680, 12460, 12450, 14000000, 11000000, 12456.55, 11992.5, 63.71, 60.97, 61.10, -276277156, -283201335, -279500000, 2, 1, 2, 1.15],
        ["NKG", 14800, 14720, 14880, 14680, 14650, 2400000, 1900000, 14580.67, 14120, 58.51, 57.82, 56.90, -17390697, -24329603, -18500000, 2, 1, 2, 1.50],
        ["PAN", 32500, 32320, 32600, 32250, 32150, 2100000, 1900000, 31897.70, 31415, 59.62, 58.11, 57.30, 33809126, 32110613, 33000000, 2, 1, 2, 1.89],
        ["NVL", 17950, 17650, 18050, 17600, 17500, 32000000, 22000000, 16923.12, 15607.5, 75.58, 71.40, 73.80, 279960394, 208596263, 265000000, 2, 2, 2, 6.07],
        ["VHM", 151800, 149000, 152500, 148500, 148000, 9000000, 7000000, 136148.18, 121210, 76.83, 73.99, 75.10, 33049934, 14155019, 30000000, 2, 2, 2, 11.50],
        ["VIC", 198900, 195500, 200000, 194800, 194000, 12000000, 8500000, 177926.47, 154330, 79.61, 77.08, 78.30, 145182792, 130390344, 139000000, 2, 2, 2, 11.79],
        ["HSG", 16250, 16120, 16300, 16080, 16050, 2800000, 2300000, 15879.07, 15285, 64.36, 63.80, 62.90, -13935652, -20061907, -15000000, 2, 1, 2, 2.34],
        ["GEX", 41000, 40850, 41150, 40750, 40600, 6500000, 5200000, 39947.55, 38257.5, 61.47, 61.32, 60.70, -69324329, -77020335, -71000000, 2, 1, 2, 2.63],
        ["HPG", 28950, 28750, 29020, 28680, 28600, 16000000, 12000000, 28164.28, 27467.5, 63.67, 60.01, 61.20, 199745607, 108745126, 190000000, 2, 1, 2, 2.79],
        ["STB", 68600, 68000, 68900, 67850, 67600, 15000000, 13000000, 65255.74, 63530, 63.99, 51.76, 61.50, 150526659, 137252350, 146000000, 2, 1, 2, 5.12],
        ["EVF", 13950, 13980, 14020, 13880, 13850, 3100000, 2800000, 13863.14, 13860, 54.11, 52.53, 53.80, -11654771, -14592055, -12000000, 2, 0, 2, 0.63],
        ["LHG", 28550, 28620, 28700, 28480, 28400, 980000, 900000, 28370.05, 28262.5, 54.21, 51.60, 53.90, -390974, -470393, -420000, 2, 0, 2, 0.63],
        ["TNH", 10350, 10380, 10410, 10310, 10280, 1200000, 1000000, 10277.58, 10180, 47.24, 44.86, 46.20, -8978097, -9407165, -9050000, 2, 0, 2, 0.70],
        ["VNM", 62100, 62020, 62250, 61950, 61800, 2600000, 2200000, 61668.52, 61450, 50.18, 47.11, 49.20, -136772053, -137324604, -137000000, 2, 0, 2, 0.70],
        ["BID", 40700, 40650, 40850, 40550, 40450, 7000000, 6200000, 40499.50, 40025, 48.64, 47.15, 47.80, 20493865, 19973992, 20150000, 2, 0, 2, 0.74],
        ["PVT", 22250, 22100, 22300, 22080, 22150, 2500000, 2300000, 21980.00, 21750.0, 51.40, 49.20, 50.10, 18000000, 17000000, 17600000, 2, 0, 1, 1.23],
        ["CTR", 86900, 86200, 87200, 86000, 85800, 800000, 650000, 85100.00, 83250.0, 68.20, 64.50, 66.90, 5200000, 4900000, 5100000, 2, 1, 2, 2.11],
        ["VHC", 62500, 62400, 62850, 62300, 62100, 1000000, 900000, 61512.77, 60050.0, 60.92, 60.16, 60.10, 8446001, 7690749, 8380000, 2, 1, 2, 1.60],
    ]
    cols = [
        "symbol", "price", "open", "high", "low", "high_prev", "volume", "vol_sma20",
        "ema9", "ma20", "rsi14", "rsi_ema9", "rsi_prev",
        "obv", "obv_ema9", "obv_prev", "E", "R", "Q", "dist_from_ema9_pct"
    ]
    return pd.DataFrame(data, columns=cols)

# =========================
# NORMALIZE UPLOAD
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

    if "dist_from_ema9_pct" not in df.columns:
        df["dist_from_ema9_pct"] = (df["price"] - df["ema9"]) / df["ema9"].replace(0, np.nan) * 100

    if "E" not in df.columns:
        df["E"] = 0
    if "R" not in df.columns:
        df["R"] = 1
    if "Q" not in df.columns:
        df["Q"] = 1

    return df

# =========================
# LOGIC
# =========================
def classify_group(row):
    rsi = row["rsi14"]
    dist = abs(row["dist_from_ema9_pct"])
    above_ema = row["price"] > row["ema9"] if pd.notna(row["price"]) and pd.notna(row["ema9"]) else False
    ema_above_ma = row["ema9"] > row["ma20"] if pd.notna(row["ema9"]) and pd.notna(row["ma20"]) else False
    obv_ok = row["obv"] > row["obv_ema9"] if pd.notna(row["obv"]) and pd.notna(row["obv_ema9"]) else False

    if above_ema and ema_above_ma and rsi >= 68 and obv_ok:
        return "CP MẠNH"

    if pd.notna(row["high_prev"]) and row["price"] > row["high_prev"] and rsi >= 55:
        return "MUA BREAK"

    if above_ema and ema_above_ma and rsi >= 58 and dist <= 1.2 and obv_ok:
        return "PULL ĐẸP"

    if above_ema and ema_above_ma and rsi >= 55 and dist <= 3.2:
        return "PULL VỪA"

    if 40 <= rsi <= 60 and dist <= 2.2:
        return "MUA EARLY"

    if 45 <= rsi <= 60:
        return "TÍCH LŨY"

    return "THEO DÕI"

def add_logic(df):
    df = df.copy()

    # phụ trợ dòng tiền hôm nay
    df["price_green_today"] = df["price"] > df["open"]
    df["rsi_accel"] = df["rsi14"] - df["rsi_prev"]
    df["obv_flow"] = df["obv"] - df["obv_prev"]
    df["vol_ratio"] = df["volume"] / df["vol_sma20"].replace(0, np.nan)

    df["group"] = df.apply(classify_group, axis=1)
    df["obv_status"] = np.where(df["obv"] > df["obv_ema9"], "🟢", "🔴")
    df["pull_label"] = np.where(
        df["dist_from_ema9_pct"].abs() <= 1.2, "PULL ĐẸP",
        np.where(df["dist_from_ema9_pct"].abs() <= 3.2, "PULL VỪA", "PULL XẤU")
    )

    # chấm lại E R Q nhẹ nhàng
    df["E"] = np.where((df["price"] > df["ema9"]) & (df["rsi14"] > df["rsi_ema9"]) & (df["obv"] > df["obv_ema9"]), 2, 1)

    risk_raw = 0
    # dùng vector hóa đơn giản
    df["R"] = 0
    df.loc[df["rsi14"] >= 75, "R"] += 1
    df.loc[df["dist_from_ema9_pct"].abs() >= 5.0, "R"] += 1
    df["R"] = df["R"].clip(0, 2)

    df["Q"] = 1
    df.loc[df["group"].isin(["CP MẠNH", "MUA BREAK", "PULL ĐẸP", "PULL VỪA"]), "Q"] = 2

    df["total_score"] = df["E"] + (2 - df["R"]) + df["Q"]

    return df

def pick_top_money(df):
    """
    Top vào tiền hôm nay:
    ưu tiên cổ phiếu có dòng tiền trong ngày, không chỉ đẹp kỹ thuật.
    """
    df = df.copy()

    # điều kiện tiền vào
    df["money_in_flag"] = (
        (df["price_green_today"] == True) &
        (df["rsi_accel"] > 0) &
        (df["obv"] > df["obv_ema9"]) &
        ((df["vol_ratio"] >= 1.0) | df["vol_ratio"].isna())
    )

    # ưu tiên nhóm đáng mua hơn
    priority_map = {
        "MUA BREAK": 0,
        "PULL ĐẸP": 1,
        "PULL VỪA": 2,
        "CP MẠNH": 3,
        "MUA EARLY": 4,
        "TÍCH LŨY": 5,
        "THEO DÕI": 6
    }
    df["money_priority"] = df["group"].map(priority_map).fillna(9)

    top = df[df["money_in_flag"]].sort_values(
        by=["money_priority", "vol_ratio", "rsi_accel", "total_score"],
        ascending=[True, False, False, False]
    ).head(5)

    return top

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V22</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {vn_now.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {vn_now.strftime('%H:%M:%S')}")

scan = st.button("🔄 SCAN")
st.markdown('<div class="small-note">V22 đã sửa: Top vào tiền theo dòng tiền hôm nay và bảng tổng chi tiết hiện full toàn bộ cổ phiếu.</div>', unsafe_allow_html=True)

uploaded = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])

# =========================
# SESSION STATE
# =========================
if "scanner_df_v22" not in st.session_state:
    st.session_state["scanner_df_v22"] = add_logic(make_demo_data())

if scan:
    if uploaded is not None:
        raw = load_uploaded_file(uploaded)
        if raw is not None and not raw.empty:
            raw = normalize_columns(raw)
            st.session_state["scanner_df_v22"] = add_logic(raw)
        else:
            st.warning("File upload lỗi hoặc rỗng. Tạm dùng demo data.")
            st.session_state["scanner_df_v22"] = add_logic(make_demo_data())
    else:
        st.session_state["scanner_df_v22"] = add_logic(make_demo_data())

df = st.session_state["scanner_df_v22"]

# =========================
# MARKET OVERVIEW
# =========================
st.markdown("---")
st.markdown('<div class="section-title">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)

market_real = round(min(13, 5 + len(df[df["group"].isin(["CP MẠNH", "MUA BREAK", "PULL ĐẸP", "PULL VỪA"])]) / 3), 1)
market_live = round(max(0, market_real - 0.7), 1)

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
        if r["group"] == "MUA EARLY":
            nav = "5-10% NAV"
        elif r["group"] in ["PULL ĐẸP", "PULL VỪA", "MUA BREAK"]:
            nav = "10-15% NAV"
        else:
            nav = "Chờ pull / theo dõi"

        st.write(f"**{r['symbol']} — {r['group']}**")
        st.write(
            f"Giá: {r['price']} | Score: {r['total_score']} | "
            f"Dist EMA9: {round(r['dist_from_ema9_pct'], 2)}% | "
            f"Vol ratio: {round(r['vol_ratio'], 2) if pd.notna(r['vol_ratio']) else '-'} | "
            f"RSI accel: {round(r['rsi_accel'], 2)} | Gợi ý NAV: {nav}"
        )
        st.write("")

# =========================
# CÁC LIST
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
# BẢNG TỔNG CHI TIẾT FULL
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

detail_cols = [
    "symbol", "group", "price", "open", "ema9", "ma20", "rsi14", "rsi_prev", "rsi_accel",
    "obv", "obv_prev", "obv_ema9", "obv_status",
    "volume", "vol_sma20", "vol_ratio",
    "price_green_today",
    "E", "R", "Q", "total_score",
    "dist_from_ema9_pct", "pull_label"
]

st.dataframe(df_display[detail_cols], use_container_width=True, height=560)

st.markdown("---")
st.caption("Đọc nhanh: CP MẠNH = leader đang chạy. PULL = điểm vào. EARLY = chuẩn bị chạy. Top vào tiền hôm nay ưu tiên giá xanh + RSI tăng + OBV tốt + vol xác nhận.")
