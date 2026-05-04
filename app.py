# ==========================================================
# SCANNER GÀ CHIẾN V19 - RA QUYẾT ĐỊNH NHANH
# Bản sạch standalone app.py
# Thêm mới:
#   1) Bảng ỨNG VIÊN NGÀY MAI
#   2) Cột NAV_REASON: giải thích vì sao NAV = 0 hoặc chỉ mua thăm dò
#   3) Luật Market-first linh hoạt:
#       - Market < 5  : NAV = 0
#       - Market 5-8  : chỉ gà 1kg/sách giáo khoa được mua thăm dò 5-10% NAV
#       - Market >= 8 : cho phép mua chính theo chất lượng điểm mua
# ==========================================================

import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# ==========================================================
# 1. CẤU HÌNH TRANG
# ==========================================================

st.set_page_config(
    page_title="Scanner Gà Chiến V19",
    page_icon="🐔",
    layout="wide"
)

st.title("🐔 SCANNER GÀ CHIẾN V19 - RA QUYẾT ĐỊNH NHANH")
st.caption("Market-first | Gà 1kg | Ứng viên ngày mai | NAV có lý do rõ ràng")

# ==========================================================
# 2. WATCHLIST THEO NHÓM NGÀNH
# ==========================================================

SECTORS: Dict[str, List[str]] = {
    "BANK": ["VCB", "BID", "CTG", "TCB", "MBB", "VPB", "STB", "HDB", "ACB", "SHB", "TPB", "LPB", "EIB", "MSB", "SSB", "VIB", "OCB", "NAB"],
    "CHỨNG KHOÁN": ["SSI", "VIX", "SHS", "MBS", "HCM", "VCI", "VND", "CTS", "FTS", "BSI", "BVS", "ORS", "VDS", "AGR"],
    "BĐS DÂN CƯ": ["VHM", "VIC", "VRE", "CEO", "CII", "DXG", "TCH", "HDC", "NVL", "DIG", "PDR", "DXS", "NLG", "KDH", "NTL", "NHA", "DPG"],
    "BĐS KCN": ["VGC", "IDC", "KBC", "SZC", "BCM", "DTD", "LHG", "IJC"],
    "THÉP - ĐẦU TƯ CÔNG": ["HPG", "HSG", "NKG", "VGS", "C4G", "FCN", "KSB", "DHA", "CTI", "HHV", "VCG", "CTD"],
    "HÓA CHẤT - PHÂN BÓN": ["DGC", "DCM", "DPM", "DDV", "CSV", "BFC", "LAS", "PAC", "MSR", "BMP", "NTP", "AAA"],
    "ĐIỆN": ["REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2", "TV2"],
    "DẦU KHÍ - VẬN TẢI": ["PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS", "HAH", "VSC", "GMD", "VOS", "VTO", "ACV"],
    "BÁN LẺ - TIÊU DÙNG": ["MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF", "MCH", "PAN", "VNM", "MML", "PNJ", "TLG"],
    "XUẤT KHẨU": ["MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB"],
    "CÔNG NGHỆ - LOGISTIC": ["FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX"],
    "CP LẺ": ["HVN", "VJC", "IMP", "BVH", "SBT", "LSS", "DHT", "TNH"],
}

ALL_SYMBOLS = sorted(list({s for group in SECTORS.values() for s in group}))

# ==========================================================
# 3. SIDEBAR
# ==========================================================

st.sidebar.header("⚙️ Cài đặt quét")
selected_sectors = st.sidebar.multiselect(
    "Chọn nhóm ngành",
    options=list(SECTORS.keys()),
    default=list(SECTORS.keys())
)

scan_symbols = sorted(list({s for sec in selected_sectors for s in SECTORS[sec]}))

max_symbols = st.sidebar.slider(
    "Số mã tối đa để quét",
    min_value=10,
    max_value=len(scan_symbols) if scan_symbols else 10,
    value=min(120, len(scan_symbols)) if scan_symbols else 10,
    step=5
)

scan_symbols = scan_symbols[:max_symbols]

lookback_days = st.sidebar.slider("Số ngày dữ liệu", 90, 365, 180, 30)
source = st.sidebar.selectbox("Nguồn vnstock", ["VCI", "TCBS"], index=0)
run_scan = st.sidebar.button("🚀 QUÉT NGAY", type="primary")

st.sidebar.markdown("---")
st.sidebar.info(
    "Luật NAV V19:\n"
    "- Market < 5: không mua\n"
    "- Market 5-8: chỉ mua thăm dò gà 1kg 5-10%\n"
    "- Market >= 8: cho phép mua chính"
)

# ==========================================================
# 4. HÀM DỮ LIỆU
# ==========================================================

def standardize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hóa dữ liệu OHLCV từ nhiều phiên bản vnstock."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    rename_map = {
        "time": "date",
        "tradingdate": "date",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
        "match_volume": "volume",
        "vol": "volume",
    }
    df = df.rename(columns=rename_map)

    required = ["date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    df = df[required].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna().sort_values("date").reset_index(drop=True)
    return df


@st.cache_data(ttl=600, show_spinner=False)
def fetch_symbol_data(symbol: str, source: str, lookback_days: int) -> pd.DataFrame:
    """Lấy dữ liệu giá. Có nhiều nhánh để tương thích các bản vnstock khác nhau."""
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    # Cách 1: vnstock bản mới
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source=source)
        df = stock.quote.history(start=start_s, end=end_s, interval="1D")
        df = standardize_ohlcv(df)
        if not df.empty:
            return df
    except Exception:
        pass

    # Cách 2: vnstock bản cũ
    try:
        from vnstock import stock_historical_data
        df = stock_historical_data(symbol, start_s, end_s, "1D", source=source)
        df = standardize_ohlcv(df)
        if not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame()

# ==========================================================
# 5. HÀM CHỈ BÁO KỸ THUẬT
# ==========================================================

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def slope_pct(series: pd.Series, window: int = 3) -> float:
    """Độ dốc % trong vài phiên gần nhất, dùng để phân loại gà."""
    if len(series) <= window:
        return 0.0
    old = series.iloc[-window-1]
    new = series.iloc[-1]
    if old == 0 or pd.isna(old) or pd.isna(new):
        return 0.0
    return float((new / old - 1) * 100)


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    df["rsi14"] = rsi(df["close"], 14)
    df["rsi_ema9"] = ema(df["rsi14"], 9)

    df["obv"] = obv(df["close"], df["volume"])
    df["obv_ema9"] = ema(df["obv"], 9)

    df["macd"] = ema(df["close"], 12) - ema(df["close"], 26)
    df["macd_signal"] = ema(df["macd"], 9)
    df["hist"] = df["macd"] - df["macd_signal"]

    df["atr14"] = atr(df, 14)
    df["dist_ema9_pct"] = (df["close"] / df["ema9"] - 1) * 100
    df["slope_ema9"] = df["ema9"].rolling(4).apply(lambda x: (x.iloc[-1] / x.iloc[0] - 1) * 100 if x.iloc[0] != 0 else 0)
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma20"]
    return df

# ==========================================================
# 6. CHẤM ĐIỂM CỔ PHIẾU
# ==========================================================

def score_stock(row: pd.Series, prev: pd.Series) -> Dict:
    close = row["close"]
    ema9_v = row["ema9"]
    ma20_v = row["ma20"]
    rsi_v = row["rsi14"]
    rsi_ema = row["rsi_ema9"]
    obv_v = row["obv"]
    obv_ema = row["obv_ema9"]
    macd_v = row["macd"]
    signal_v = row["macd_signal"]
    hist_v = row["hist"]
    hist_prev = prev["hist"]
    dist = row["dist_ema9_pct"]
    slope = row["slope_ema9"]
    vol_ratio = row["vol_ratio"]

    price_ok = close > ema9_v > ma20_v
    rsi_ok = rsi_v > rsi_ema and rsi_v >= 55
    obv_ok = obv_v > obv_ema
    macd_ok = macd_v > signal_v and hist_v > 0
    hist_expand = hist_v > hist_prev
    vol_ok = vol_ratio >= 1.0

    # E = Energy
    E = 0
    if rsi_v >= 60: E += 1
    if macd_ok: E += 1
    if hist_expand: E += 1
    if slope >= 2: E += 1

    # R = Risk đảo chiều: điểm cao nghĩa là rủi ro thấp
    R = 0
    if 0 <= dist <= 5: R += 1
    if rsi_v <= 70: R += 1
    if close >= ema9_v: R += 1
    if obv_ok: R += 1

    # O = Opportunity
    O = 0
    if price_ok: O += 1
    if obv_ok: O += 1
    if 2 <= slope <= 4: O += 1
    if 60 <= rsi_v <= 70: O += 1

    # S = Slope / Structure
    S = 0
    if slope > 0: S += 1
    if slope >= 2: S += 1
    if ema9_v > ma20_v: S += 1
    if close > ema9_v: S += 1

    total = E + R + O + S

    # Phân loại trạng thái
    textbook = bool(obv_ok and price_ok and 2 <= slope <= 4 and 2 <= dist <= 5 and 60 <= rsi_v <= 70)
    too_hot = bool(slope > 5 or dist > 6 or rsi_v > 70)
    pull_watch = bool(price_ok and obv_ok and rsi_v >= 55 and dist <= 2 and close >= ma20_v)
    break_watch = bool(price_ok and obv_ok and vol_ratio >= 1.2 and hist_expand and 0 <= dist <= 6)
    early_reversal = bool((not price_ok) and obv_ok and rsi_v > rsi_ema and hist_v > hist_prev and rsi_v >= 45)

    if textbook:
        status = "🟢 ƯU TIÊN MUA - GÀ 1KG"
    elif too_hot and price_ok and obv_ok:
        status = "🟡 MẠNH NHƯNG NÓNG - CHỜ PULL"
    elif pull_watch:
        status = "🟡 PULL WATCH"
    elif break_watch:
        status = "🟢 BREAK WATCH"
    elif early_reversal:
        status = "🟠 THEO DÕI ĐẢO CHIỀU"
    elif total >= 9 and obv_ok:
        status = "🟡 THEO DÕI"
    else:
        status = "🔴 LOẠI / CHƯA ĐẠT"

    return {
        "E": E,
        "R": R,
        "O": O,
        "S": S,
        "TOTAL": total,
        "PRICE_OK": price_ok,
        "RSI_OK": rsi_ok,
        "OBV_OK": obv_ok,
        "MACD_OK": macd_ok,
        "TEXTBOOK": textbook,
        "TOO_HOT": too_hot,
        "PULL_WATCH": pull_watch,
        "BREAK_WATCH": break_watch,
        "EARLY_REVERSAL": early_reversal,
        "STATUS": status,
    }

# ==========================================================
# 7. MARKET SCORE
# ==========================================================

def calculate_market_score(df_all: pd.DataFrame) -> Tuple[float, str]:
    if df_all.empty:
        return 0.0, "Không có dữ liệu"

    n = len(df_all)
    if n == 0:
        return 0.0, "Không có dữ liệu"

    pct_price_ok = df_all["PRICE_OK"].mean()
    pct_obv_ok = df_all["OBV_OK"].mean()
    pct_rsi_ok = df_all["RSI_OK"].mean()
    pct_macd_ok = df_all["MACD_OK"].mean()
    pct_green = (df_all["change_pct"] > 0).mean()
    pct_strong = (df_all["TOTAL"] >= 9).mean()
    pct_textbook = df_all["TEXTBOOK"].mean()

    # 13 điểm: đo breadth + chất lượng cổ phiếu
    score = 0
    score += pct_price_ok * 2.0
    score += pct_obv_ok * 2.5
    score += pct_rsi_ok * 2.0
    score += pct_macd_ok * 1.5
    score += pct_green * 1.5
    score += pct_strong * 2.0
    score += pct_textbook * 1.5
    score = round(float(score), 2)

    if score < 5:
        label = "🔴 Market yếu - không mua"
    elif score < 8:
        label = "🟡 Market trung tính - chỉ mua thăm dò gà 1kg"
    else:
        label = "🟢 Market khỏe - cho phép mua chính"

    return score, label

# ==========================================================
# 8. NAV ENGINE V19
# ==========================================================

def nav_engine(row: pd.Series, market_score: float) -> Tuple[int, str]:
    """Trả về NAV gợi ý và lý do cụ thể."""
    symbol = row["symbol"]

    if market_score < 5:
        return 0, "❌ Market < 5: bảo toàn vốn, không mua"

    if row["TOO_HOT"]:
        return 0, "❌ Cổ phiếu đã nóng: RSI/Dist/Slope cao, chờ pull"

    if not row["OBV_OK"]:
        return 0, "❌ OBV chưa xanh / tiền chưa vào đủ"

    if not row["PRICE_OK"]:
        if row["EARLY_REVERSAL"]:
            return 0, "🟠 Có dấu hiệu đảo chiều sớm nhưng giá chưa xác nhận EMA9>MA20"
        return 0, "❌ Giá chưa đạt cấu trúc Price > EMA9 > MA20"

    if market_score < 8:
        if row["TEXTBOOK"]:
            # Trong market 5-8 chỉ mua thăm dò
            if row["TOTAL"] >= 12:
                return 10, "🟡 Market 5-8 + gà 1kg rất đẹp: mua thăm dò 10% NAV"
            return 5, "🟡 Market 5-8 + gà 1kg: mua thăm dò 5% NAV"
        return 0, "⚠️ Market 5-8: chưa phải gà 1kg sách giáo khoa nên chỉ theo dõi"

    # Market >= 8
    if row["TEXTBOOK"]:
        if row["TOTAL"] >= 12:
            return 15, "🟢 Market khỏe + gà 1kg đẹp: mua chính 15% NAV"
        return 10, "🟢 Market khỏe + gà 1kg: mua 10% NAV"

    if row["PULL_WATCH"]:
        return 7, "🟢 Market khỏe + pull watch: mua 7% NAV"

    if row["BREAK_WATCH"]:
        return 5, "🟢 Market khỏe + break watch: mua thăm dò 5% NAV"

    return 0, "⚠️ Market khỏe nhưng cổ phiếu chưa có điểm mua đẹp"

# ==========================================================
# 9. QUÉT TOÀN BỘ WATCHLIST
# ==========================================================

def get_sector(symbol: str) -> str:
    for sector, symbols in SECTORS.items():
        if symbol in symbols:
            return sector
    return "KHÁC"


def analyze_symbol(symbol: str, source: str, lookback_days: int) -> Dict:
    df = fetch_symbol_data(symbol, source, lookback_days)
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "Không đủ dữ liệu"}

    df = enrich_indicators(df)
    df = df.dropna().reset_index(drop=True)
    if len(df) < 30:
        return {"symbol": symbol, "error": "Không đủ dữ liệu sau chỉ báo"}

    row = df.iloc[-1]
    prev = df.iloc[-2]
    score = score_stock(row, prev)

    change_pct = (row["close"] / prev["close"] - 1) * 100 if prev["close"] else 0

    out = {
        "symbol": symbol,
        "sector": get_sector(symbol),
        "date": row["date"].strftime("%Y-%m-%d"),
        "close": round(float(row["close"]), 2),
        "change_pct": round(float(change_pct), 2),
        "volume": int(row["volume"]),
        "vol_ratio": round(float(row["vol_ratio"]), 2),
        "rsi": round(float(row["rsi14"]), 2),
        "dist": round(float(row["dist_ema9_pct"]), 2),
        "slope": round(float(row["slope_ema9"]), 2),
        "ema9": round(float(row["ema9"]), 2),
        "ma20": round(float(row["ma20"]), 2),
        "hist": round(float(row["hist"]), 4),
        "error": "",
    }
    out.update(score)
    return out


def scan_market(symbols: List[str], source: str, lookback_days: int) -> pd.DataFrame:
    results = []
    progress = st.progress(0)
    status = st.empty()

    for i, symbol in enumerate(symbols):
        status.write(f"Đang quét {symbol} ({i+1}/{len(symbols)})...")
        results.append(analyze_symbol(symbol, source, lookback_days))
        progress.progress((i + 1) / len(symbols))

    status.empty()
    progress.empty()
    return pd.DataFrame(results)

# ==========================================================
# 10. HIỂN THỊ BẢNG
# ==========================================================

def style_table(df: pd.DataFrame):
    def color_nav(v):
        try:
            v = float(v)
        except Exception:
            return ""
        if v <= 0:
            return "background-color: #ffe6e6"
        if v <= 5:
            return "background-color: #fff3cd"
        if v <= 10:
            return "background-color: #d1e7dd"
        return "background-color: #b6effb"

    def color_status(v):
        s = str(v)
        if "ƯU TIÊN" in s or "BREAK" in s:
            return "background-color: #d1e7dd"
        if "THEO DÕI" in s or "PULL" in s or "NÓNG" in s:
            return "background-color: #fff3cd"
        if "LOẠI" in s:
            return "background-color: #ffe6e6"
        return ""

    cols = df.columns
    styler = df.style
    if "NAV" in cols:
        styler = styler.applymap(color_nav, subset=["NAV"])
    if "STATUS" in cols:
        styler = styler.applymap(color_status, subset=["STATUS"])
    return styler


def show_df(title: str, df: pd.DataFrame, height: int = 420):
    st.subheader(title)
    if df.empty:
        st.info("Không có mã đạt điều kiện.")
        return
    st.dataframe(style_table(df), use_container_width=True, height=height)

# ==========================================================
# 11. MAIN APP
# ==========================================================

if not run_scan:
    st.info("Bấm **🚀 QUÉT NGAY** ở sidebar để chạy scanner V19.")
    st.markdown(
        "### V19 có gì mới?\n"
        "1. **Ứng viên ngày mai**: lọc đúng gà 1kg: OBV xanh, slope 2-4, dist 2-5, RSI 60-70, giá > EMA9 > MA20.\n"
        "2. **NAV có lý do**: nếu NAV = 0 sẽ ghi rõ do Market-first, quá nóng, OBV chưa xanh, chưa có điểm mua...\n"
        "3. **Market 5-8 vẫn được mua thăm dò** nếu cổ phiếu đạt chuẩn sách giáo khoa."
    )
    st.stop()

if not scan_symbols:
    st.warning("Anh chưa chọn nhóm ngành nào.")
    st.stop()

raw = scan_market(scan_symbols, source, lookback_days)

if raw.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra lại vnstock / internet / requirements.txt.")
    st.stop()

errors = raw[raw["error"] != ""] if "error" in raw.columns else pd.DataFrame()
df = raw[raw["error"] == ""].copy() if "error" in raw.columns else raw.copy()

if df.empty:
    st.error("Không có mã nào đủ dữ liệu để phân tích.")
    if not errors.empty:
        st.dataframe(errors, use_container_width=True)
    st.stop()

market_score, market_label = calculate_market_score(df)

navs = df.apply(lambda r: nav_engine(r, market_score), axis=1)
df["NAV"] = [x[0] for x in navs]
df["NAV_REASON"] = [x[1] for x in navs]

# Sắp xếp tổng thể
df = df.sort_values(["NAV", "TOTAL", "O", "slope"], ascending=[False, False, False, False]).reset_index(drop=True)

# ==========================================================
# 12. DASHBOARD TỔNG QUAN
# ==========================================================

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Market Score", f"{market_score}/13")
c2.metric("Trạng thái", market_label)
c3.metric("Số mã quét", len(df))
c4.metric("Gà 1kg", int(df["TEXTBOOK"].sum()))
c5.metric("Có NAV > 0", int((df["NAV"] > 0).sum()))

if market_score < 5:
    st.error("🔴 Market-first: thị trường yếu, hệ thống khóa mua mới.")
elif market_score < 8:
    st.warning("🟡 Market trung tính: chỉ mua thăm dò 5-10% NAV với cổ phiếu sách giáo khoa.")
else:
    st.success("🟢 Market khỏe: cho phép mua chính theo điểm mua đẹp.")

# ==========================================================
# 13. CÁC BẢNG QUAN TRỌNG
# ==========================================================

cols_main = [
    "symbol", "sector", "close", "change_pct", "volume", "vol_ratio",
    "rsi", "dist", "slope", "E", "R", "O", "S", "TOTAL",
    "STATUS", "NAV", "NAV_REASON"
]

cols_tech = [
    "symbol", "sector", "close", "change_pct", "rsi", "dist", "slope",
    "ema9", "ma20", "hist", "vol_ratio", "PRICE_OK", "RSI_OK", "OBV_OK", "MACD_OK",
    "TEXTBOOK", "TOO_HOT", "PULL_WATCH", "BREAK_WATCH", "EARLY_REVERSAL",
    "TOTAL", "NAV", "NAV_REASON"
]

# 1. Ứng viên ngày mai
candidates_tomorrow = df[df["TEXTBOOK"]].copy()
candidates_tomorrow = candidates_tomorrow.sort_values(["NAV", "TOTAL", "O", "dist"], ascending=[False, False, False, True])

# 2. Top vào tiền hôm nay: ưu tiên vol_ratio + change + OBV xanh
money_in = df[(df["OBV_OK"]) & (df["change_pct"] > 0)].copy()
money_in = money_in.sort_values(["vol_ratio", "change_pct", "TOTAL"], ascending=[False, False, False]).head(30)

# 3. Gà mạnh nhưng nóng
hot = df[df["TOO_HOT"] & df["PRICE_OK"] & df["OBV_OK"]].copy()
hot = hot.sort_values(["TOTAL", "slope", "dist"], ascending=[False, False, False]).head(30)

# 4. Pull / Break watch
pull_break = df[(df["PULL_WATCH"]) | (df["BREAK_WATCH"])].copy()
pull_break = pull_break.sort_values(["NAV", "TOTAL", "O"], ascending=[False, False, False]).head(30)

# 5. Early reversal
early = df[df["EARLY_REVERSAL"]].copy()
early = early.sort_values(["TOTAL", "rsi", "vol_ratio"], ascending=[False, False, False]).head(30)

# 6. Có NAV > 0
buyable = df[df["NAV"] > 0].copy()
buyable = buyable.sort_values(["NAV", "TOTAL", "O"], ascending=[False, False, False])

# 7. Toàn bộ
df_display = df[cols_main].copy()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔥 Ứng viên ngày mai",
    "💰 Top vào tiền hôm nay",
    "✅ Có thể mua",
    "🐔 Gà mạnh nhưng nóng",
    "🔁 Pull/Break Watch",
    "🌱 Early đảo chiều",
    "📋 Toàn bộ chi tiết",
])

with tab1:
    st.markdown("### 🔥 ỨNG VIÊN NGÀY MAI - GÀ 1KG SÁCH GIÁO KHOA")
    st.caption("Điều kiện: OBV xanh | Slope 2-4 | Dist 2-5 | RSI 60-70 | Giá > EMA9 > MA20")
    show_df("Danh sách ứng viên", candidates_tomorrow[cols_main] if not candidates_tomorrow.empty else candidates_tomorrow, 500)

with tab2:
    st.markdown("### 💰 TOP CỔ PHIẾU VÀO TIỀN HÔM NAY")
    st.caption("Nếu NAV = 0, xem ngay cột NAV_REASON để biết lý do: Market-first, quá nóng, chưa pull, OBV chưa xanh...")
    show_df("Top vào tiền", money_in[cols_main] if not money_in.empty else money_in, 500)

with tab3:
    st.markdown("### ✅ CỔ PHIẾU ĐƯỢC PHÉP MUA THEO NAV ENGINE V19")
    show_df("Có NAV > 0", buyable[cols_main] if not buyable.empty else buyable, 500)

with tab4:
    st.markdown("### 🐔 GÀ MẠNH NHƯNG ĐÃ NÓNG - CHỈ THEO DÕI PULL")
    st.caption("Nhóm này thường mạnh thật nhưng slope/dist/RSI đã cao. Không đuổi, chờ pull về EMA9/MA20.")
    show_df("Gà mạnh nhưng nóng", hot[cols_main] if not hot.empty else hot, 500)

with tab5:
    st.markdown("### 🔁 PULL / BREAK WATCH")
    show_df("Pull/Break", pull_break[cols_main] if not pull_break.empty else pull_break, 500)

with tab6:
    st.markdown("### 🌱 THEO DÕI ĐẢO CHIỀU SỚM")
    st.caption("Có tín hiệu sớm nhưng chưa phải điểm mua chính. Dùng để canh sau vài phiên xác nhận.")
    show_df("Early đảo chiều", early[cols_main] if not early.empty else early, 500)

with tab7:
    st.markdown("### 📋 TOÀN BỘ BẢNG CHI TIẾT")
    show_df("Toàn bộ", df[cols_tech], 700)

# ==========================================================
# 14. BẢNG THEO NGÀNH
# ==========================================================

st.markdown("---")
st.subheader("🏭 Top theo từng nhóm ngành")

sector_rows = []
for sector in sorted(df["sector"].unique()):
    tmp = df[df["sector"] == sector].sort_values(["NAV", "TOTAL", "O"], ascending=[False, False, False]).head(3)
    sector_rows.append(tmp)

if sector_rows:
    sector_df = pd.concat(sector_rows, ignore_index=True)
    st.dataframe(style_table(sector_df[cols_main]), use_container_width=True, height=600)

# ==========================================================
# 15. DOWNLOAD CSV
# ==========================================================

st.markdown("---")
csv = df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="⬇️ Tải kết quả CSV",
    data=csv,
    file_name=f"scanner_ga_chien_v19_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    mime="text/csv"
)

if not errors.empty:
    with st.expander("⚠️ Mã lỗi / thiếu dữ liệu"):
        st.dataframe(errors, use_container_width=True)

st.caption("V19 by Sơn Võ system: Market-first + Gà 1kg + NAV reason + Ứng viên ngày mai")
