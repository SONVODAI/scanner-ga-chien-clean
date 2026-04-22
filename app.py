import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Scanner Gà Chiến V21", layout="wide")

# =========================
# THỜI GIAN VIỆT NAM
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
        ["MSH", 38700, 37564.16, 37280, 60.16, 55.81, 11054899, 10711110, 2.0, 1, 2, 3.02],
        ["BAF", 36650, 35990.81, 35295, 65.41, 63.36, 79514377, 74420465, 2.0, 2, 2, 1.83],
        ["CII", 19150, 19057.94, 18700, 56.66, 55.54, -44109676, -48783752, 2.0, 1, 2, 0.48],
        ["FMC", 38850, 38419.06, 38210, 55.31, 53.22, 625428, 527981, 2.0, 1, 2, 1.12],
        ["MSB", 12600, 12456.55, 11992.5, 63.71, 60.97, -276277156, -283201335, 2.0, 1, 2, 1.15],
        ["NKG", 14800, 14580.67, 14120, 58.51, 57.82, -17390697, -24329603, 2.0, 1, 2, 1.50],
        ["PAN", 32500, 31897.70, 31415, 59.62, 58.11, 33809126, 32110613, 2.0, 1, 2, 1.89],
        ["NVL", 17950, 16923.12, 15607.5, 75.58, 71.40, 279960394, 208596263, 2.0, 2, 2, 6.07],
        ["VHM", 151800, 136148.18, 121210, 76.83, 73.99, 33049934, 14155019, 2.0, 2, 2, 11.50],
        ["VIC", 198900, 177926.47, 154330, 79.61, 77.08, 145182792, 130390344, 2.0, 2, 2, 11.79],
        ["HSG", 16250, 15879.07, 15285, 64.36, 63.80, -13935652, -20061907, 2.0, 1, 2, 2.34],
        ["GEX", 41000, 39947.55, 38257.5, 61.47, 61.32, -69324329, -77020335, 2.0, 1, 2, 2.63],
        ["HPG", 28950, 28164.28, 27467.5, 63.67, 60.01, 199745607, 108745126, 2.0, 1, 2, 2.79],
        ["STB", 68600, 65255.74, 63530, 63.99, 51.76, 150526659, 137252350, 2.0, 1, 2, 5.12],
        ["EVF", 13950, 13863.14, 13860, 54.11, 52.53, -11654771, -14592055, 2.0, 0, 2, 0.63],
        ["LHG", 28550, 28370.05, 28262.5, 54.21, 51.60, -390974, -470393, 2.0, 0, 2, 0.63],
        ["TNH", 10350, 10277.58, 10180, 47.24, 44.86, -8978097, -9407165, 2.0, 0, 2, 0.70],
        ["VNM", 62100, 61668.52, 61450, 50.18, 47.11, -136772053, -137324604, 2.0, 0, 2, 0.70],
        ["BID", 40700, 40499.50, 40025, 48.64, 47.15, 20493865, 19973992, 2.0, 0, 2, 0.74],
    ]
    cols = [
        "symbol", "price", "ema9", "ma20", "rsi14", "rsi_base",
        "obv", "obv_ema9", "E", "R", "Q", "dist_from_ema9_pct"
    ]
    df = pd.DataFrame(data, columns=cols)
    return df

# =========================
# LOGIC PHÂN NHÓM
# =========================
def classify_group(row):
    rsi = row["rsi14"]
    dist = abs(row["dist_from_ema9_pct"])

    if rsi >= 75:
        return "CP MẠNH"
    if rsi >= 60 and dist <= 3.5:
        return "PULL VỪA"
    if rsi >= 60 and dist > 3.5:
        return "CP MẠNH"
    if 40 <= rsi <= 60 and dist <= 2:
        return "MUA EARLY"
    if 45 <= rsi <= 60:
        return "TÍCH LŨY"
    return "THEO DÕI"

def add_logic(df):
    df = df.copy()
    df["group"] = df.apply(classify_group, axis=1)
    df["obv_status"] = np.where(df["obv"] > df["obv_ema9"], "🟢", "🔴")
    df["pull_label"] = np.where(
        df["dist_from_ema9_pct"].abs() <= 2, "PULL ĐẸP",
        np.where(df["dist_from_ema9_pct"].abs() <= 4, "PULL VỪA", "PULL XẤU")
    )
    df["total_score"] = df["E"] + (2 - df["R"]) + df["Q"]
    return df

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V21</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {vn_now.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {vn_now.strftime('%H:%M:%S')}")

scan = st.button("🔄 SCAN")

st.markdown('<div class="small-note">Bản này không đọc data.csv nên sẽ không lỗi thiếu file.</div>', unsafe_allow_html=True)

# =========================
# SESSION STATE
# =========================
if "scanner_df" not in st.session_state:
    st.session_state["scanner_df"] = add_logic(make_demo_data())

if scan:
    st.session_state["scanner_df"] = add_logic(make_demo_data())

df = st.session_state["scanner_df"]

# =========================
# MARKET OVERVIEW
# =========================
st.markdown("---")
st.markdown('<div class="section-title">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)

market_real = round(min(13, 5 + len(df[df["group"].isin(["CP MẠNH", "PULL VỪA"])]) / 3), 1)
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
# TOP VÀO TIỀN
# =========================
st.markdown("---")
st.markdown('<div class="section-title">🎯 TOP VÀO TIỀN HÔM NAY</div>', unsafe_allow_html=True)

top = df[df["group"].isin(["PULL VỪA", "MUA EARLY"])].sort_values(
    by=["total_score", "dist_from_ema9_pct"], ascending=[False, True]
).head(3)

if top.empty:
    st.write("Chưa có mã nổi bật")
else:
    for _, r in top.iterrows():
        nav = "10-15% NAV" if r["group"] == "PULL VỪA" else "5-10% NAV"
        st.write(f"**{r['symbol']} — {r['group']}**")
        st.write(f"Giá: {r['price']} | Score: {r['total_score']} | Dist EMA9: {r['dist_from_ema9_pct']}% | Gợi ý NAV: {nav}")
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
# BẢNG TỔNG CHI TIẾT
# =========================
st.markdown("---")
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

detail_cols = [
    "symbol", "group", "price", "ema9", "ma20", "rsi14",
    "obv", "obv_ema9", "obv_status", "E", "R", "Q",
    "total_score", "dist_from_ema9_pct", "pull_label"
]

st.dataframe(df[detail_cols], use_container_width=True, height=560)

st.markdown("---")
st.caption("Đọc nhanh: CP MẠNH = leader đang chạy. PULL = điểm vào. EARLY = chuẩn bị chạy.")
