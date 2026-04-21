# app.py
# ============================================
# SCANNER GÀ CHIẾN V17 CLEAN
# Full rewrite - copy toàn bộ vào app.py
# ============================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# ============================================
# PAGE CONFIG
# ============================================

st.set_page_config(
    page_title="Scanner Gà Chiến V17 Clean",
    page_icon="🐔",
    layout="wide"
)

# ============================================
# WATCHLIST - CHỈ PHÂN TÍCH CÁC MÃ ANH THEO DÕI
# Nếu cần thêm/xóa mã, sửa ngay trong list này
# ============================================

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

    # BĐS / thêm các mã anh hay xem
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "KBC", "IJC", "EVF", "LHG", "SAB"
])))

# Nếu Yahoo data cho VN cần hậu tố .VN hoặc .HM / .HN thì sửa ở đây
DEFAULT_SUFFIX = ".VN"

# ============================================
# UI STYLE
# ============================================

st.markdown("""
<style>
    .main-title {
        font-size: 30px;
        font-weight: 800;
        margin-bottom: 8px;
    }
    .sub-note {
        color: #666;
        font-size: 14px;
        margin-bottom: 18px;
    }
    .small-box {
        padding: 8px 12px;
        border-radius: 12px;
        background: #f6f7fb;
        border: 1px solid #e5e7eb;
        margin-bottom: 10px;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# INDICATOR FUNCTIONS
# ============================================

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).fillna(0).cumsum()
    return obv


def safe_num(x, ndigits=2):
    try:
        if pd.isna(x):
            return None
        return round(float(x), ndigits)
    except Exception:
        return None

# ============================================
# DATA DOWNLOAD
# ============================================

@st.cache_data(ttl=300, show_spinner=False)
def download_symbol_data(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Tải dữ liệu từ Yahoo Finance.
    Mặc định dùng mã + .VN
    """
    ticker = f"{symbol}{DEFAULT_SUFFIX}"
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # Chuẩn hóa cột nếu Yahoo trả multi-index
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume"
    }
    df = df.rename(columns=rename_map)
    df = df.reset_index()

    needed = ["Date", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            return pd.DataFrame()

    df = df[needed].copy()
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df = df.dropna(subset=["close"])
    return df


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ema9"] = ema(df["close"], 9)
    df["ma20"] = sma(df["close"], 20)

    df["rsi14"] = calc_rsi(df["close"], 14)
    df["rsi_ema9"] = ema(df["rsi14"], 9)

    df["obv"] = calc_obv(df["close"], df["volume"])
    df["obv_ema9"] = ema(df["obv"], 9)

    df["vol_ma20"] = sma(df["volume"], 20)

    return df

# ============================================
# SCORING LOGIC V17
# ============================================

def price_score(last_row: pd.Series, prev_row: pd.Series) -> tuple[int, str]:
    """
    E_score:
    2 = giá > EMA9 > MA20 và EMA9 dốc lên
    1 = giá > EMA9
    0 = còn lại
    """
    close_ = last_row["close"]
    ema9_ = last_row["ema9"]
    ma20_ = last_row["ma20"]

    ema9_prev = prev_row["ema9"]

    if pd.notna(close_) and pd.notna(ema9_) and pd.notna(ma20_):
        if close_ > ema9_ > ma20_ and ema9_ > ema9_prev:
            return 2, "Cực khỏe"
        elif close_ > ema9_:
            return 1, "Khỏe"
    return 0, "Yếu"


def rsi_score(last_row: pd.Series) -> tuple[int, str]:
    """
    R_score:
    2 = RSI > 60 và RSI > EMA9(RSI)
    1 = RSI > 55
    0 = còn lại
    """
    rsi_ = last_row["rsi14"]
    rsi_ema9_ = last_row["rsi_ema9"]

    if pd.notna(rsi_) and pd.notna(rsi_ema9_):
        if rsi_ > 60 and rsi_ > rsi_ema9_:
            return 2, "Rất khỏe"
        elif rsi_ > 55:
            return 1, "Ổn"
    return 0, "Yếu"


def obv_score(last_row: pd.Series, prev_row: pd.Series) -> tuple[int, str]:
    """
    O_score:
    2 = OBV > EMA9(OBV) và OBV tăng
    1 = OBV > EMA9(OBV) nhưng đi ngang/không tăng rõ
    0 = OBV < EMA9(OBV)
    """
    obv_ = last_row["obv"]
    obv_ema9_ = last_row["obv_ema9"]
    obv_prev = prev_row["obv"]

    if pd.notna(obv_) and pd.notna(obv_ema9_):
        if obv_ > obv_ema9_ and obv_ > obv_prev:
            return 2, "Tiền vào"
        elif obv_ > obv_ema9_:
            return 1, "Giữ nền"
    return 0, "Tiền yếu"


def build_warning(last_row: pd.Series) -> str:
    warnings = []

    if pd.notna(last_row["obv"]) and pd.notna(last_row["obv_ema9"]):
        if last_row["obv"] < last_row["obv_ema9"]:
            warnings.append("OBV gãy")

    if pd.notna(last_row["rsi14"]) and pd.notna(last_row["rsi_ema9"]):
        if last_row["rsi14"] < last_row["rsi_ema9"]:
            warnings.append("Mất động lượng")

    if pd.notna(last_row["close"]) and pd.notna(last_row["ema9"]):
        if last_row["close"] < last_row["ema9"]:
            warnings.append("Giá dưới EMA9")

    if not warnings:
        return ""
    return " | ".join(warnings)


def build_status(total_score: int, warning: str) -> str:
    if total_score >= 5 and warning == "":
        return "🟢"
    elif total_score >= 3:
        return "🟡"
    return "🔴"


def classify_group(row: pd.Series) -> str:
    """
    Chia nhóm theo đúng tư duy app cũ nhưng logic mới.
    """
    total = row["total_score"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
    close_ = row["price"]
    ema9_ = row["ema9"]
    ma20_ = row["ma20"]
    rsi_ = row["rsi14"]
    rsi_ema9_ = row["rsi_ema9"]
    obv_ = row["obv"]
    obv_ema9_ = row["obv_ema9"]

    # 1) CP MẠNH
    if total >= 5 and e == 2 and r >= 1 and o >= 1:
        return "CP MẠNH"

    # 2) MUA BREAK
    # Rất khỏe, giá đang trên EMA9 & MA20, phù hợp đi break
    if total >= 4 and close_ > ema9_ and close_ > ma20_ and r >= 1 and o >= 1:
        return "MUA BREAK"

    # 3) MUA PULL
    # Giá vẫn trên MA20 nhưng đang gần EMA9, trục chưa hỏng
    if (
        total >= 3
        and close_ >= ema9_ * 0.985
        and close_ >= ma20_
        and o >= 1
    ):
        return "MUA PULL"

    # 4) MUA EARLY
    # Giá chưa mạnh hoàn toàn nhưng RSI/OBV bắt đầu cải thiện
    if (
        total >= 3
        and r >= 1
        and o >= 1
        and rsi_ > rsi_ema9_
        and obv_ > obv_ema9_
    ):
        return "MUA EARLY"

    # 5) TÍCH LŨY
    if total == 2:
        return "TÍCH LŨY"

    # 6) THEO DÕI
    return "THEO DÕI"

# ============================================
# SYMBOL ANALYSIS
# ============================================

def analyze_symbol(symbol: str) -> dict | None:
    try:
        raw = download_symbol_data(symbol)

        if raw.empty or len(raw) < 30:
            return None

        df = build_indicators(raw)

        if len(df) < 21:
            return None

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        e_score, e_text = price_score(last_row, prev_row)
        r_score, r_text = rsi_score(last_row)
        o_score, o_text = obv_score(last_row, prev_row)

        total_score = e_score + r_score + o_score
        warning = build_warning(last_row)
        status = build_status(total_score, warning)

        result = {
            "symbol": symbol,
            "price": safe_num(last_row["close"], 0),
            "E": e_score,
            "R": r_score,
            "O": o_score,
            "total_score": total_score,
            "status": status,
            "warning": warning,
            "ema9": safe_num(last_row["ema9"], 2),
            "ma20": safe_num(last_row["ma20"], 2),
            "rsi14": safe_num(last_row["rsi14"], 2),
            "rsi_ema9": safe_num(last_row["rsi_ema9"], 2),
            "obv": safe_num(last_row["obv"], 0),
            "obv_ema9": safe_num(last_row["obv_ema9"], 0),
            "E_text": e_text,
            "R_text": r_text,
            "O_text": o_text,
        }

        result["group"] = classify_group(pd.Series(result))
        return result

    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def run_scan(symbols: list[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        item = analyze_symbol(symbol)
        if item is not None:
            rows.append(item)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Sort ưu tiên:
    # 1. total_score giảm dần
    # 2. E, O, R
    # 3. price
    df = df.sort_values(
        by=["total_score", "E", "O", "R", "price"],
        ascending=[False, False, False, False, False]
    ).reset_index(drop=True)

    return df

# ============================================
# DISPLAY HELPERS
# ============================================

GROUP_ORDER = [
    "CP MẠNH",
    "MUA BREAK",
    "MUA PULL",
    "MUA EARLY",
    "TÍCH LŨY",
    "THEO DÕI",
]

DISPLAY_COLUMNS = [
    "symbol", "price", "E", "R", "O", "total_score", "status", "warning"
]

def show_group_table(df: pd.DataFrame, group_name: str):
    group_df = df[df["group"] == group_name].copy()

    if group_df.empty:
        st.info("Không có mã")
        return

    show_df = group_df[DISPLAY_COLUMNS].copy()
    show_df.index = range(len(show_df))

    st.dataframe(
        show_df,
        use_container_width=True,
        height=min(600, 80 + len(show_df) * 35)
    )

# ============================================
# HEADER
# ============================================

st.markdown('<div class="main-title">🐔 Scanner Gà Chiến V17 Clean</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-note">Logic mới: E_score + RSI_score + OBV_score → Total Score → tự phân nhóm mạnh / break / pull / early / tích lũy / theo dõi</div>',
    unsafe_allow_html=True
)

# ============================================
# TOP CONTROL
# ============================================

col_a, col_b, col_c, col_d = st.columns([1.2, 1, 1, 1.4])

with col_a:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with col_b:
    auto_refresh = st.checkbox("Auto refresh 5 phút", value=True)

with col_c:
    show_detail = st.checkbox("Hiện bảng tổng", value=False)

with col_d:
    st.markdown(
        f"""
        <div class="small-box">
        <b>Watchlist:</b> {len(WATCHLIST)} mã<br>
        <b>Update:</b> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================
# AUTO REFRESH
# ============================================

if "last_auto_refresh" not in st.session_state:
    st.session_state.last_auto_refresh = time.time()

if auto_refresh:
    now_ts = time.time()
    if now_ts - st.session_state.last_auto_refresh > 300:
        st.session_state.last_auto_refresh = now_ts
        st.cache_data.clear()
        st.rerun()

# ============================================
# MAIN SCAN
# ============================================

if scan_btn or "scan_df" not in st.session_state:
    with st.spinner("Đang quét dữ liệu..."):
        st.cache_data.clear()
        scan_df = run_scan(WATCHLIST)
        st.session_state.scan_df = scan_df
else:
    scan_df = st.session_state.scan_df

# ============================================
# RESULT SUMMARY
# ============================================

if scan_df is None or scan_df.empty:
    st.warning("Không lấy được dữ liệu. Anh kiểm tra lại internet hoặc nguồn dữ liệu Yahoo Finance.")
    st.stop()

count_cols = st.columns(6)
for i, group_name in enumerate(GROUP_ORDER):
    with count_cols[i]:
        cnt = int((scan_df["group"] == group_name).sum())
        st.metric(group_name, cnt)

# ============================================
# MAIN GROUP TABLES
# ============================================

st.markdown("---")

cols = st.columns(6)
for i, group_name in enumerate(GROUP_ORDER):
    with cols[i]:
        st.subheader(group_name)
        show_group_table(scan_df, group_name)

# ============================================
# DETAIL TABLE
# ============================================

if show_detail:
    st.markdown("---")
    st.subheader("BẢNG TỔNG CHI TIẾT")

    detail_cols = [
        "symbol", "group", "price",
        "E", "R", "O", "total_score", "status", "warning",
        "ema9", "ma20", "rsi14", "rsi_ema9", "obv", "obv_ema9",
        "E_text", "R_text", "O_text"
    ]

    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))

    st.dataframe(detail_df, use_container_width=True, height=700)

# ============================================
# FOOTER NOTE
# ============================================

st.markdown("---")
st.caption(
    "Gợi ý đọc nhanh: "
    "E = trục giá, R = RSI, O = OBV. "
    "Total càng cao càng mạnh. "
    "🟢 = đẹp, 🟡 = cần chọn lọc, 🔴 = yếu/cảnh báo."
)
