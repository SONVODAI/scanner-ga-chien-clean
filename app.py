import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến",
    page_icon="🐔",
    layout="wide"
)

# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST_BY_SECTOR = {
    "BANK": [
        "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB",
        "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "EIB"
    ],
    "CHUNG_KHOAN": [
        "VND", "SSI", "HCM", "SHS", "VIX", "BSI", "FTS", "VCI", "TVS", "AGR"
    ],
    "BAT_DONG_SAN": [
        "VHM", "VIC", "VRE", "NVL", "DXG", "DIG", "CEO", "TCH", "KDH", "NLG"
    ],
    "THEP": [
        "HPG", "HSG", "NKG"
    ],
    "DAU_KHI": [
        "GAS", "PVS", "PVD", "BSR", "PLX"
    ],
    "VAN_TAI_LOGISTIC": [
        "HAH", "GMD", "VSC", "VOS", "VTO"
    ],
    "BAN_LE": [
        "MWG", "FRT", "DGW", "PNJ"
    ],
    "CONG_NGHE": [
        "FPT", "CTR", "VTP", "CMG"
    ],
    "PHAN_BON_HOA_CHAT": [
        "DGC", "DCM", "DPM", "CSV", "DDV", "BFC", "LAS"
    ],
    "KHAC": [
        "REE", "PC1", "GEX", "GEE", "VGI"
    ]
}

WATCHLIST = []
for _, arr in WATCHLIST_BY_SECTOR.items():
    WATCHLIST.extend(arr)

WATCHLIST = list(dict.fromkeys(WATCHLIST))

# =========================================================
# HELPERS
# =========================================================
def normalize_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    obv_values = [0]
    for i in range(1, len(close)):
        prev_close = close.iloc[i - 1]
        curr_close = close.iloc[i]
        curr_vol = volume.iloc[i]

        if curr_close > prev_close:
            obv_values.append(obv_values[-1] + curr_vol)
        elif curr_close < prev_close:
            obv_values.append(obv_values[-1] - curr_vol)
        else:
            obv_values.append(obv_values[-1])

    return pd.Series(obv_values, index=close.index)

def safe_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def get_sector_of_symbol(symbol: str) -> str:
    for sector, arr in WATCHLIST_BY_SECTOR.items():
        if symbol in arr:
            return sector
    return "KHAC"

def format_pct(x) -> str:
    if pd.isna(x):
        return ""
    return f"{x:.1f}%"

# =========================================================
# DATA FETCH
# =========================================================
@st.cache_data(ttl=300)

@st.cache_data(ttl=300)
def fetch_daily(symbol: str) -> pd.DataFrame:
    try:
        # ===== 1. TRY YFINANCE =====
        df = yf.download(symbol + ".VN", period="6mo", progress=False)
        if df is not None and not df.empty:
            return df

        # ===== 2. FALLBACK: FIREANT API =====
        url = f"https://restv2.fireant.vn/symbols/{symbol}/prices?startDate=2023-01-01"
        res = requests.get(url)
        
       if res.status_code != 200:
    return pd.DataFrame()

data = res.json()
if not data:
    return pd.DataFrame()

try:
    df = pd.DataFrame(data)

    df.rename(columns={
        "open": "Open",
        "close": "Close",
        "high": "High",
        "low": "Low",
        "volume": "Volume"
    }, inplace=True)

    df["Date"] = pd.to_datetime(df["date"] if "date" in df.columns else df["Date"])
    df.set_index("Date", inplace=True)

    return df

except Exception:
    return pd.DataFrame()
def fetch_daily(symbol: str) -> pd.DataFrame:
    try:
        df = yf.download(symbol + ".VN", period="6mo", progress=False)

        if df is None or df.empty:
            return pd.DataFrame()

        return df

    except Exception:
        return pd.DataFrame()    
# =========================================================
# INDICATORS
# =========================================================
def build_indicator_df(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()

    close = normalize_series(raw["Close"]).dropna()
    high = normalize_series(raw["High"]).reindex(close.index)
    low = normalize_series(raw["Low"]).reindex(close.index)
    volume = normalize_series(raw["Volume"]).reindex(close.index)

    df = pd.DataFrame({
        "Close": close,
        "High": high,
        "Low": low,
        "Volume": volume
    }).dropna()

    if len(df) < 60:
        return pd.DataFrame()

    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["RSI_EMA"] = df["RSI"].ewm(span=9, adjust=False).mean()
    df["OBV"] = calc_obv(df["Close"], df["Volume"])
    df["OBV_EMA"] = df["OBV"].ewm(span=9, adjust=False).mean()
    df["VOL_MA20"] = df["Volume"].rolling(20).mean()

    df["RET_20D"] = df["Close"].pct_change(20)
    df["RET_60D"] = df["Close"].pct_change(60)

    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - df["Close"].shift(1)).abs()
    tr3 = (df["Low"] - df["Close"].shift(1)).abs()
    df["TR"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR14"] = df["TR"].rolling(14).mean()

    return df.dropna()

# =========================================================
# INTRADAY CHECK
# =========================================================
def intraday_confirm(symbol: str) -> bool:
    intra = fetch_intraday(symbol)
    if intra is None or intra.empty:
        return False

    try:
        iclose = normalize_series(intra["Close"]).dropna()
        ivol = normalize_series(intra["Volume"]).reindex(iclose.index)

        if len(iclose) < 10:
            return False

        iema9 = iclose.ewm(span=9, adjust=False).mean()
        iobv = calc_obv(iclose, ivol)

        return bool(
            iclose.iloc[-1] > iema9.iloc[-1]
            and iobv.iloc[-1] > iobv.iloc[-3]
        )
    except Exception:
        return False

# =========================================================
# BUY TRIGGER ENGINE
# =========================================================
def check_buy_trigger(df: pd.DataFrame, symbol: str):
    if df is None or df.empty or len(df) < 60:
        return "NONE", "data thiếu"

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    prev3 = df.iloc[-4] if len(df) >= 4 else df.iloc[0]

    close_now = safe_float(latest["Close"])
    ema9 = safe_float(latest["EMA9"])
    ma20 = safe_float(latest["MA20"])
    rsi = safe_float(latest["RSI"])
    rsi_ema = safe_float(latest["RSI_EMA"])
    obv = safe_float(latest["OBV"])
    obv_ema = safe_float(latest["OBV_EMA"])
    vol = safe_float(latest["Volume"])
    vol_ma = safe_float(latest["VOL_MA20"], default=1.0)

    if pd.isna(ma20) or pd.isna(vol_ma):
        return "NONE", "thiếu MA20 hoặc VOL_MA20"

    # 1. Xu hướng nền
    cond_price = close_now > ema9 and ema9 > ma20
    cond_obv = obv > obv_ema if not pd.isna(obv_ema) else False
    cond_slope = ema9 > safe_float(df["EMA9"].iloc[-3], ema9)
    cond_rsi_turn = rsi > safe_float(df["RSI"].iloc[-3], rsi) if len(df) > 3 else False
    cond_rs = close_now > ma20 * 1.03 if not pd.isna(ma20) else False

    dist_ma20 = (close_now - ma20) / ma20 if ma20 != 0 else 0.0
    too_extended = dist_ma20 > 0.15

    # 2. returns
    ret_20d = safe_float(latest["RET_20D"], 0.0)
    ret_60d = safe_float(latest["RET_60D"], 0.0)

    # 3. volume
    vol_dry = vol_ma > 0 and vol < vol_ma * 0.8
    vol_break = vol_ma > 0 and vol > vol_ma * 1.3
    money_score = (vol / vol_ma) if vol_ma > 0 else 1.0

    # 4. intraday confirm
    intraday_ok = intraday_confirm(symbol)

    # 5. leader score
    leader_score = 0
    if ret_20d > 0.10:
        leader_score += 1
    if ret_60d > 0.20:
        leader_score += 1
    if money_score > 1.2:
        leader_score += 1
    if cond_rs:
        leader_score += 1
    if cond_obv:
        leader_score += 1
    if intraday_ok:
        leader_score += 1

    # 6. Pull đẹp
    recent_high = df["Close"].iloc[-10:].max() if len(df) >= 10 else df["Close"].max()
    drawdown = (recent_high - close_now) / recent_high if recent_high > 0 else 0

    near_ema9 = abs(close_now - ema9) / ema9 <= 0.03 if ema9 > 0 else False
    above_ma20 = close_now >= ma20 * 0.99 if ma20 > 0 else False
    pull_depth_ok = 0.02 <= drawdown <= 0.08
    candle_ok = abs(close_now - safe_float(latest["Open"], close_now)) / close_now <= 0.035 if "Open" in df.columns else True
    rsi_ok = rsi >= 50
    obv_ok = obv >= obv_ema * 0.995 if not pd.isna(obv_ema) else False

    reclaim_case = safe_float(prev["Close"]) < safe_float(prev["EMA9"]) * 0.992 and close_now >= ema9

    if (
        cond_price
        and near_ema9
        and above_ma20
        and pull_depth_ok
        and vol_dry
        and candle_ok
        and rsi_ok
        and obv_ok
        and not reclaim_case
    ):
        return "B2", "Pull đẹp thật"

    # 7. Reclaim EMA9
    reclaim_ok = (
        safe_float(prev["Close"]) < safe_float(prev["EMA9"])
        and close_now >= ema9
        and obv >= obv_ema * 0.99
        and rsi > safe_float(prev["RSI"], rsi)
    )
    if reclaim_ok:
        return "RE", "Reclaim EMA9"

    # 8. Breakout
    prev_high = df["High"].rolling(20).max().iloc[-2] if len(df) > 21 else df["High"].max()
    break_ok = (
        close_now > prev_high
        and vol_break
        and rsi >= 60
        and obv >= obv_ema
    )
    if break_ok and not too_extended:
        return "B3", "Breakout mạnh"

    # 9. Early reversal
    early_ok = (
        rsi >= 45
        and rsi > rsi_ema
        and close_now >= ema9 * 0.995
        and obv >= obv_ema * 0.98
        and cond_rsi_turn
    )
    if early_ok:
        return "ER", "Early reversal"

    return "NONE", ""

# =========================================================
# ANALYZE ONE STOCK
# =========================================================
def analyze_stock(symbol: str):
    raw = fetch_daily(symbol)
    if raw is None or raw.empty:
        return None

    df = build_indicator_df(raw)
    if df is None or df.empty or len(df) < 60:
        return None

    latest = df.iloc[-1]

    close_now = safe_float(latest["Close"])
    ema9 = safe_float(latest["EMA9"])
    ma20 = safe_float(latest["MA20"])
    rsi = safe_float(latest["RSI"])
    rsi_ema = safe_float(latest["RSI_EMA"])
    obv = safe_float(latest["OBV"])
    obv_ema = safe_float(latest["OBV_EMA"])
    vol = safe_float(latest["Volume"])
    vol_ma = safe_float(latest["VOL_MA20"], 1.0)
    ret_20d = safe_float(latest["RET_20D"], 0.0)
    ret_60d = safe_float(latest["RET_60D"], 0.0)

    # trigger
    buy_code, buy_note = check_buy_trigger(df, symbol)

    # score
    score = 0

    # OBV (4)
    if obv > obv_ema:
        score += 2
    if obv > safe_float(df["OBV"].iloc[-3], obv):
        score += 2

    # PRICE (3)
    if close_now > ema9:
        score += 1
    if ema9 > ma20:
        score += 1
    if ema9 > safe_float(df["EMA9"].iloc[-3], ema9):
        score += 1

    # RSI (3)
    if rsi > 55:
        score += 1
    if rsi > rsi_ema:
        score += 1
    if rsi > safe_float(df["RSI"].iloc[-3], rsi):
        score += 1

    # MOMENTUM (2)
    if ret_20d > 0.10:
        score += 1
    if ret_60d > 0.20:
        score += 1

    # ATR / ổn định (1)
    if safe_float(latest["ATR14"], 0) / close_now < 0.06:
        score += 1

    intraday_ok = intraday_confirm(symbol)

    # stage
    if ret_20d < 0.10:
        stage = "B1-TÍCH LŨY"
    elif ret_20d < 0.25:
        stage = "B2-ĐANG VÀO SÓNG"
    elif (close_now - ma20) / ma20 < 0.15:
        stage = "B3-LEADER"
    else:
        stage = "B3-QUÁ XA"

    # status
    if buy_code in ["B2", "B3"]:
        status = "ƯU TIÊN MUA"
    elif buy_code == "RE":
        status = "THEO DÕI"
    elif buy_code == "ER":
        status = "THEO DÕI ĐẢO CHIỀU"
    elif score >= 8:
        status = "THEO DÕI"
    else:
        status = "LOẠI"

    # chicken
    if stage == "B1-TÍCH LŨY":
        chicken = "🐣 Gà con"
    elif stage == "B2-ĐANG VÀO SÓNG":
        chicken = "🐔 Gà chạy"
    elif stage == "B3-LEADER":
        chicken = "🦅 Gà chiến"
    else:
        chicken = "⚠️ Gà bay cao"

    return {
        "Mã": symbol,
        "Ngành": get_sector_of_symbol(symbol),
        "Giá": round(close_now, 2),
        "RSI": round(rsi, 1),
        "OBV>EMA": "✅" if obv > obv_ema else "❌",
        "EMA9>MA20": "✅" if ema9 > ma20 else "❌",
        "Ret20d": round(ret_20d * 100, 1),
        "Ret60d": round(ret_60d * 100, 1),
        "Vol/MA20": round(vol / vol_ma, 2) if vol_ma > 0 else np.nan,
        "Intraday": "✅" if intraday_ok else "❌",
        "Điểm": score,
        "Stage": stage,
        "Trạng thái": status,
        "Gà": chicken,
        "Tín hiệu": buy_code,
        "Ghi chú": buy_note
    }

# =========================================================
# UI
# =========================================================
st.title("🐔 Scanner Gà Chiến Clean")

left_col, right_col = st.columns([1, 2])

with left_col:
    st.subheader("Thiết lập")
    selected_sector = st.selectbox(
        "Chọn nhóm",
        ["TẤT CẢ"] + list(WATCHLIST_BY_SECTOR.keys())
    )

    only_priority = st.checkbox("Chỉ hiện ƯU TIÊN MUA / THEO DÕI", value=False)
    min_score = st.slider("Điểm tối thiểu", 0, 13, 6)
    run_scan = st.button("🚀 SCAN")

with right_col:
    st.subheader("Watchlist đang dùng")
    if selected_sector == "TẤT CẢ":
        symbols = WATCHLIST
    else:
        symbols = WATCHLIST_BY_SECTOR[selected_sector]
    st.write(", ".join(symbols))

if run_scan:
    results = []

    progress = st.progress(0)
    total = len(symbols)

    for idx, sym in enumerate(symbols, start=1):
        try:
            item = analyze_stock(sym)
            if item is not None:
                results.append(item)
        except Exception:
            pass

        progress.progress(idx / total)

    if not results:
        st.warning("Không có dữ liệu")
    else:
        out = pd.DataFrame(results)

        out = out[out["Điểm"] >= min_score]

        if only_priority:
            out = out[out["Trạng thái"].isin(["ƯU TIÊN MUA", "THEO DÕI", "THEO DÕI ĐẢO CHIỀU"])]

        out = out.sort_values(
            by=["Điểm", "Ret20d"],
            ascending=[False, False]
        ).reset_index(drop=True)

        st.subheader("Kết quả scan")
        st.dataframe(out, use_container_width=True)

        st.subheader("🟩 ƯU TIÊN MUA")
        pri = out[out["Trạng thái"] == "ƯU TIÊN MUA"]
        st.dataframe(pri, use_container_width=True)

        st.subheader("🟨 THEO DÕI")
        watch = out[out["Trạng thái"] == "THEO DÕI"]
        st.dataframe(watch, use_container_width=True)

        st.subheader("🟦 THEO DÕI ĐẢO CHIỀU")
        er = out[out["Trạng thái"] == "THEO DÕI ĐẢO CHIỀU"]
        st.dataframe(er, use_container_width=True)

        st.subheader("🟥 LOẠI")
        bad = out[out["Trạng thái"] == "LOẠI"]
        st.dataframe(bad, use_container_width=True)

st.caption(f"Cập nhật: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
