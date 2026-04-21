# =========================================================
# SCANNER GÀ CHIẾN V18.1 CLEAN
# GIỮ NGUYÊN LOGIC V18 + THÊM MARKET SCORE
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V18.1 Clean",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V18.1 Clean")
st.caption("Giữ nguyên V18 + thêm Market Score")


# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = sorted(list(set([
    # Dầu khí & Vận tải
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV",

    # Xuất khẩu
    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB",

    # Điện & Hóa chất
    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP", "AAA",
    "PAC", "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "TV2", "DGC",

    # Đầu tư công & vật liệu
    "C4G", "FCN", "CII", "KSB", "DHA", "CTI", "HBC", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG",

    # Bán lẻ & chăn nuôi
    "MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF",
    "MCH", "PAN", "VNM", "MML",

    # Ngân hàng & tài chính
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "SHS", "VIX", "BSI", "FTS", "TVS", "APS",
    "AGR", "VCI",

    # Công nghệ & logistic
    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",

    # Cổ phiếu lẻ
    "HVN", "VJC", "IMP", "BVH", "SBT", "LSS", "PNJ", "TLG", "DHT",
    "TNH",

    # BĐS / mã hay xem
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "KBC", "IJC", "EVF", "LHG", "SAB"
])))

DEFAULT_SUFFIX = ".VN"


# =========================================================
# STYLE
# =========================================================
st.markdown("""
<style>
div[data-testid="stDataFrame"] {
    border-radius: 10px;
}
.small-note {
    color: #666;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# HELPERS
# =========================================================
def to_float(value, default=np.nan):
    try:
        if isinstance(value, pd.Series):
            if len(value) == 0:
                return default
            value = value.iloc[-1]
        if isinstance(value, np.ndarray):
            if len(value) == 0:
                return default
            value = value[-1]
        return float(value)
    except Exception:
        return default


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).fillna(0).cumsum()


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(x) for x in col if str(x) != ""]).strip("_")
            for col in df.columns.to_list()
        ]
    else:
        df.columns = [str(c) for c in df.columns]
    return df


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    for c in df.columns:
        cl = str(c).lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None


# =========================================================
# DATA
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def download_symbol_data(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    ticker = f"{symbol}{DEFAULT_SUFFIX}"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
            group_by="column",
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = flatten_columns(df).reset_index()

    date_col = find_col(df, ["Date", "Datetime"])
    open_col = find_col(df, ["Open"])
    high_col = find_col(df, ["High"])
    low_col = find_col(df, ["Low"])
    close_col = find_col(df, ["Close"])
    vol_col = find_col(df, ["Volume"])

    needed = [date_col, open_col, high_col, low_col, close_col, vol_col]
    if any(col is None for col in needed):
        return pd.DataFrame()

    out = df[[date_col, open_col, high_col, low_col, close_col, vol_col]].copy()
    out.columns = ["date", "open", "high", "low", "close", "volume"]

    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["close"])
    out = out.sort_values("date").reset_index(drop=True)
    return out


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_ema9"] = ema(x["rsi14"], 9)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    x["vol_ma20"] = sma(x["volume"], 20)

    x["highest_20"] = x["high"].rolling(20).max()
    x["lowest_20"] = x["low"].rolling(20).min()

    return x


# =========================================================
# SCORE
# =========================================================
def calc_price_score(close_, ema9_, ma20_, ema9_prev):
    if pd.notna(close_) and pd.notna(ema9_) and pd.notna(ma20_) and pd.notna(ema9_prev):
        if close_ > ema9_ > ma20_ and ema9_ > ema9_prev:
            return 2
        if close_ > ema9_:
            return 1
    return 0


def calc_rsi_score(rsi_, rsi_ema9_):
    if pd.notna(rsi_) and pd.notna(rsi_ema9_):
        if rsi_ > 60 and rsi_ > rsi_ema9_:
            return 2
        if rsi_ > 55:
            return 1
    return 0


def calc_obv_score(obv_, obv_ema9_, obv_prev):
    if pd.notna(obv_) and pd.notna(obv_ema9_) and pd.notna(obv_prev):
        if obv_ > obv_ema9_ and obv_ > obv_prev:
            return 2
        if obv_ > obv_ema9_:
            return 1
    return 0


def build_warning(close_, ema9_, rsi_, rsi_ema9_, obv_, obv_ema9_):
    warnings = []

    if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ < obv_ema9_:
        warnings.append("OBV gãy")

    if pd.notna(rsi_) and pd.notna(rsi_ema9_) and rsi_ < rsi_ema9_:
        warnings.append("RSI yếu")

    if pd.notna(close_) and pd.notna(ema9_) and close_ < ema9_:
        warnings.append("Giá dưới EMA9")

    return " | ".join(warnings)


def build_status(total_score, warning):
    if total_score >= 5 and warning == "":
        return "🟢"
    if total_score >= 3:
        return "🟡"
    return "🔴"


# =========================================================
# CLASSIFY - GIỮ NGUYÊN V18
# =========================================================
def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    ma20_ = row["ma20"]
    rsi_ = row["rsi14"]
    rsi_ema9_ = row["rsi_ema9"]
    obv_ = row["obv"]
    obv_ema9_ = row["obv_ema9"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
    dist_from_ema9 = row["dist_from_ema9_pct"]
    breakout_ref = row["breakout_ref"]

    leader = (
        total >= 5
        and e >= 1
        and o >= 1
        and pd.notna(price)
        and pd.notna(ema9_)
        and price >= ema9_ * 0.97
    )

    if not leader:
        if total <= 1:
            return "THEO DÕI"
        if total == 2:
            return "TÍCH LŨY"
        return "MUA EARLY"

    if (
        pd.notna(dist_from_ema9)
        and -3.0 <= dist_from_ema9 <= 1.5
        and pd.notna(price)
        and pd.notna(ma20_)
        and price >= ma20_
        and o >= 1
    ):
        return "MUA PULL"

    if (
        pd.notna(breakout_ref)
        and pd.notna(price)
        and pd.notna(vol_)
        and pd.notna(vol_ma20_)
        and price >= breakout_ref * 1.01
        and vol_ >= vol_ma20_ * 1.2
        and r >= 1
        and o >= 1
    ):
        return "MUA BREAK"

    if (
        pd.notna(dist_from_ema9)
        and dist_from_ema9 > 1.5
        and e == 2
        and r >= 1
        and o >= 1
    ):
        return "CP MẠNH"

    if (
        pd.notna(rsi_) and pd.notna(rsi_ema9_) and rsi_ > rsi_ema9_
        and pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ > obv_ema9_
    ):
        return "MUA EARLY"

    return "TÍCH LŨY"


# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)
    if len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    rsi_ = to_float(last["rsi14"])
    rsi_ema9_ = to_float(last["rsi_ema9"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    high20_prev = to_float(df["high"].iloc[-21:-1].max())

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_ema9_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)
    total_score = E + R + O

    warning = build_warning(price, ema9_, rsi_, rsi_ema9_, obv_, obv_ema9_)
    status = build_status(total_score, warning)

    row = {
        "symbol": symbol,
        "price": round(price, 0) if pd.notna(price) else np.nan,
        "ema9": round(ema9_, 2) if pd.notna(ema9_) else np.nan,
        "ma20": round(ma20_, 2) if pd.notna(ma20_) else np.nan,
        "rsi14": round(rsi_, 2) if pd.notna(rsi_) else np.nan,
        "rsi_ema9": round(rsi_ema9_, 2) if pd.notna(rsi_ema9_) else np.nan,
        "obv": round(obv_, 0) if pd.notna(obv_) else np.nan,
        "obv_ema9": round(obv_ema9_, 0) if pd.notna(obv_ema9_) else np.nan,
        "volume": round(vol_, 0) if pd.notna(vol_) else np.nan,
        "vol_ma20": round(vol_ma20_, 0) if pd.notna(vol_ma20_) else np.nan,
        "breakout_ref": round(high20_prev, 2) if pd.notna(high20_prev) else np.nan,
        "dist_from_ema9_pct": round(dist_from_ema9, 2) if pd.notna(dist_from_ema9) else np.nan,
        "E": E,
        "R": R,
        "O": O,
        "total_score": total_score,
        "status": status,
        "warning": warning,
    }

    row["group"] = classify_group(row)
    return row


# =========================================================
# SCAN
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def run_scan(symbols: list[str]) -> pd.DataFrame:
    rows = []

    for symbol in symbols:
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    df = df.sort_values(
        by=["total_score", "E", "O", "R", "dist_from_ema9_pct"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)

    return df


# =========================================================
# MARKET SCORE - THÊM MỚI
# =========================================================
def calc_market_score(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total

    strong = len(df[df["group"] == "CP MẠNH"])
    breakout = len(df[df["group"] == "MUA BREAK"])

    strong_score = min(strong / 10, 1) * 3
    breakout_score = min(breakout / 8, 1) * 2

    score = (
        e_ratio * 3
        + r_ratio * 3
        + o_ratio * 3
        + strong_score
        + breakout_score
    )

    return round(score, 1)


def market_status_text(score: float) -> tuple[str, str]:
    if score >= 8:
        return "🟢 THỊ TRƯỜNG KHỎE", "✅ Có thể vào tiền"
    if score >= 6:
        return "🟡 TRUNG TÍNH", "⚠️ Chỉ nên test nhỏ"
    return "🔴 THỊ TRƯỜNG YẾU", "⛔ Không nên vào tiền"


# =========================================================
# UI CONTROLS
# =========================================================
left1, left2, left3, left4 = st.columns([1.1, 1.2, 1.1, 2.2])

with left1:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with left2:
    auto_refresh = st.checkbox("Auto refresh 5 phút", value=True)

with left3:
    show_detail = st.checkbox("Hiện bảng tổng", value=False)

with left4:
    st.markdown(
        f"""
        <div class="small-note">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Update: <b>{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</b>
        </div>
        """,
        unsafe_allow_html=True
    )

if "last_auto_refresh" not in st.session_state:
    st.session_state["last_auto_refresh"] = time.time()

if auto_refresh:
    now_ts = time.time()
    if now_ts - st.session_state["last_auto_refresh"] > 300:
        st.session_state["last_auto_refresh"] = now_ts
        st.cache_data.clear()
        st.rerun()

if scan_btn:
    st.cache_data.clear()

with st.spinner("Đang quét dữ liệu..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra lại mạng hoặc nguồn Yahoo Finance.")
    st.stop()


# =========================================================
# MARKET OVERVIEW
# =========================================================
market_score = calc_market_score(scan_df)
market_status, market_action = market_status_text(market_score)

st.markdown("## 📊 MARKET OVERVIEW")

m1, m2 = st.columns([1, 2])

with m1:
    st.metric("Market Score", f"{market_score}/13")

with m2:
    st.subheader(market_status)

if market_score < 6:
    st.warning(market_action)
elif market_score < 8:
    st.info(market_action)
else:
    st.success(market_action)


# =========================================================
# SUMMARY
# =========================================================
GROUP_ORDER = ["CP MẠNH", "MUA BREAK", "MUA PULL", "MUA EARLY", "TÍCH LŨY", "THEO DÕI"]

sum_cols = st.columns(6)
for i, group_name in enumerate(GROUP_ORDER):
    cnt = int((scan_df["group"] == group_name).sum())
    with sum_cols[i]:
        st.metric(group_name, cnt)


# =========================================================
# DISPLAY
# =========================================================
DISPLAY_COLUMNS = ["symbol", "price", "E", "R", "O", "total_score", "status"]

def show_group_table(df: pd.DataFrame, group_name: str):
    sub = df[df["group"] == group_name].copy()
    if sub.empty:
        st.info("Không có mã")
        return

    if group_name == "MUA PULL":
        cols = ["symbol", "price", "E", "R", "O", "total_score", "dist_from_ema9_pct", "status"]
    elif group_name == "MUA BREAK":
        cols = ["symbol", "price", "E", "R", "O", "total_score", "breakout_ref", "status"]
    else:
        cols = DISPLAY_COLUMNS

    out = sub[cols].copy()
    out.index = range(len(out))

    st.dataframe(
        out,
        use_container_width=True,
        height=min(520, 80 + len(out) * 35)
    )


st.markdown("---")

cols = st.columns(6)
for i, group_name in enumerate(GROUP_ORDER):
    with cols[i]:
        st.subheader(group_name)
        show_group_table(scan_df, group_name)


# =========================================================
# DETAIL
# =========================================================
if show_detail:
    st.markdown("---")
    st.subheader("BẢNG TỔNG CHI TIẾT")

    detail_cols = [
        "symbol", "group", "price",
        "ema9", "ma20",
        "rsi14", "rsi_ema9",
        "E", "R", "O", "total_score",
        "dist_from_ema9_pct", "breakout_ref",
        "status", "warning"
    ]

    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))

    st.dataframe(detail_df, use_container_width=True, height=720)


# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.caption(
    "Đọc nhanh: "
    "E = trục giá, R = RSI, O = OBV. "
    "Pull = leader đang về gần EMA9. "
    "Break = leader vượt vùng gần nhất kèm vol. "
    "Market ≥ 8 mới đánh mạnh."
)
