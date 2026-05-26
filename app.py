# =========================================================
# SCANNER TIẾN HÓA CP - V18.4 EVOLUTION REWRITE
# Viết mới 100% theo lõi realtime V18.4
# Mục tiêu:
#   1) Lấy dữ liệu realtime nhẹ, ổn định
#   2) Bảng chi tiết đủ đọc: Giá / RSI / OBV / Slope / Score / State
#   3) Lưu lịch sử tiến hóa 15 phiên
#   4) Bảng CP tiến hóa nhảy riêng
# =========================================================

import os
import time
import base64
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Tiến Hóa CP",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Tiến Hóa CP - Realtime Core V18.4")
st.caption("Bản nhẹ: realtime + bảng chi tiết + lịch sử tiến hóa + CP tiến hóa")


# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = sorted(list(set([
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV", "HVN", "VJC",

    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB", "VGT",

    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP", "AAA",
    "PAC", "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "TV2", "DGC", "POW",

    "C4G", "FCN", "CII", "KSB", "DHA", "CTI", "HBC", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG", "PLC", "TLH", "TVN",

    "MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF",
    "MCH", "PAN", "VNM", "MML", "TLG",

    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "VIX", "BSI", "FTS", "TVS", "SHS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",

    "VGC", "SZC", "IDC", "KBC", "LHG", "IJC", "DTD", "BCM",

    "GVR", "SIP", "DPR", "PHR", "DRI",

    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",

    "IMP", "BVH", "SBT", "LSS", "PNJ", "DHT", "TNH", "YEG",

    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB", "VPL", "PDR", "DPG", "NHA", "HDC", "NTL", "HHS",
    "NLG", "KDH", "HUT",
])))

DEFAULT_SUFFIX = ".VN"
EVOLUTION_FILE = "group_evolution_history.csv"
MAX_HISTORY_DAYS = 15


# =========================================================
# BASIC HELPERS
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


def safe_round(value, digits=2):
    try:
        if pd.isna(value):
            return np.nan
        return round(float(value), digits)
    except Exception:
        return np.nan


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
# REALTIME DATA DOWNLOAD - GIỮ TINH THẦN V18.4
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


# =========================================================
# INDICATORS
# =========================================================
def slope_state_text(slope: float) -> str:
    if pd.isna(slope):
        return ""
    if slope > 2:
        return "🟢 Mở mạnh"
    if slope > 0:
        return "🟡 Dương"
    return "🔴 Âm"


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)

    x["ema9_ma20_slope"] = np.where(
        x["ma20"] != 0,
        (x["ema9"] - x["ma20"]) / x["ma20"] * 100,
        np.nan,
    )
    x["ema9_ma20_slope_change"] = x["ema9_ma20_slope"] - x["ema9_ma20_slope"].shift(3)
    x["slope_state"] = x["ema9_ma20_slope"].apply(slope_state_text)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_ema9"] = ema(x["rsi14"], 9)
    x["rsi_slope"] = x["rsi14"] - x["rsi14"].shift(3)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)
    x["obv_slope"] = x["obv"] - x["obv"].shift(3)

    x["vol_ma20"] = sma(x["volume"], 20)

    x["rs5"] = ((x["close"] / x["close"].shift(5)) - 1) * 100
    x["rs10"] = ((x["close"] / x["close"].shift(10)) - 1) * 100

    return x


# =========================================================
# SCORING - GỌN 10 ĐIỂM
# =========================================================
def calc_price_score(close_, ema9_, ma20_, ema9_prev):
    if pd.notna(close_) and pd.notna(ema9_) and pd.notna(ma20_) and pd.notna(ema9_prev):
        if close_ > ema9_ > ma20_ and ema9_ > ema9_prev:
            return 2
        if close_ > ema9_ and ema9_ >= ma20_:
            return 1
    return 0


def calc_rsi_score(rsi_, rsi_ema9_, rsi_slope_):
    if pd.notna(rsi_) and pd.notna(rsi_ema9_) and pd.notna(rsi_slope_):
        if rsi_ >= 60 and rsi_ >= rsi_ema9_ and rsi_slope_ > 0:
            return 2
        if rsi_ >= 55 and rsi_ >= rsi_ema9_:
            return 1
    return 0


def calc_obv_score(obv_, obv_ema9_, obv_slope_):
    if pd.notna(obv_) and pd.notna(obv_ema9_) and pd.notna(obv_slope_):
        if obv_ > obv_ema9_ and obv_slope_ > 0:
            return 2
        if obv_ >= obv_ema9_:
            return 1
    return 0


def calc_slope_score(slope_, slope_change_):
    if pd.notna(slope_) and pd.notna(slope_change_):
        if slope_ > 2 and slope_change_ > 0:
            return 2
        if slope_ > 0:
            return 1
    return 0


def calc_rs_score(rs5_, rs10_):
    if pd.notna(rs5_) and pd.notna(rs10_):
        if rs5_ >= 3 and rs10_ >= 5:
            return 2
        if rs5_ >= 1 or rs10_ >= 2:
            return 1
    return 0


def classify_state(total_score: int) -> str:
    if total_score >= 8:
        return "🟢 MẠNH"
    if total_score >= 6:
        return "🟡 TÍCH LŨY"
    if total_score >= 4:
        return "🟠 YẾU"
    return "🔴 LOẠI"


STATE_RANK = {
    "🔴 LOẠI": 0,
    "🟠 YẾU": 1,
    "🟡 TÍCH LŨY": 2,
    "🟢 MẠNH": 3,
}


def build_warning(row: dict) -> str:
    warnings = []

    if row.get("price", 0) < row.get("ema9", 10**18):
        warnings.append("Giá < EMA9")

    if row.get("rsi14", 0) < row.get("rsi_ema9", 10**18):
        warnings.append("RSI < EMA9 RSI")

    if row.get("obv", 0) < row.get("obv_ema9", 10**18):
        warnings.append("OBV < EMA9 OBV")

    if row.get("ema9_ma20_slope", -999) < 0:
        warnings.append("Slope âm")

    return " | ".join(warnings)


# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)

    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)

    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    slope_ = to_float(last["ema9_ma20_slope"])
    slope_change_ = to_float(last["ema9_ma20_slope_change"])

    rsi_ = to_float(last["rsi14"])
    rsi_ema9_ = to_float(last["rsi_ema9"])
    rsi_slope_ = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_slope_ = to_float(last["obv_slope"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_ema9_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_slope_)
    S = calc_slope_score(slope_, slope_change_)
    RS = calc_rs_score(rs5_, rs10_)

    total_score = E + R + O + S + RS
    state = classify_state(total_score)

    row = {
        "symbol": symbol,
        "price": safe_round(price, 0),
        "ema9": safe_round(ema9_, 2),
        "ma20": safe_round(ma20_, 2),
        "dist_ema9_%": safe_round(dist_from_ema9, 2),

        "rsi14": safe_round(rsi_, 2),
        "rsi_ema9": safe_round(rsi_ema9_, 2),
        "rsi_slope": safe_round(rsi_slope_, 2),

        "obv": safe_round(obv_, 0),
        "obv_ema9": safe_round(obv_ema9_, 0),
        "obv_slope": safe_round(obv_slope_, 0),
        "obv_status": "🟢" if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_ else "🔴",

        "volume": safe_round(vol_, 0),
        "vol_ma20": safe_round(vol_ma20_, 0),

        "ema9_ma20_slope": safe_round(slope_, 2),
        "ema9_ma20_slope_change": safe_round(slope_change_, 2),
        "slope_state": str(last["slope_state"]),

        "rs5": safe_round(rs5_, 2),
        "rs10": safe_round(rs10_, 2),

        "E": E,
        "R": R,
        "O": O,
        "S": S,
        "RS": RS,
        "total_score": total_score,
        "state": state,
        "state_rank": STATE_RANK.get(state, 0),
    }

    row["warning"] = build_warning(row)

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
        except Exception as e:
            # Không để 1 mã lỗi làm hỏng toàn app
            pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    df = df.sort_values(
        by=["total_score", "state_rank", "ema9_ma20_slope", "rs5"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    return df


# =========================================================
# MARKET SIMPLE SCORE
# =========================================================
def calc_market_score(df: pd.DataFrame) -> tuple[float, str]:
    if df.empty:
        return 0, "Không có dữ liệu"

    total = len(df)

    strong_ratio = len(df[df["state"] == "🟢 MẠNH"]) / total
    acc_ratio = len(df[df["total_score"] >= 8]) / total
    obv_ratio = len(df[df["obv_status"] == "🟢"]) / total
    slope_ratio = len(df[df["ema9_ma20_slope"] > 0]) / total
    rsi_ratio = len(df[df["rsi14"] >= 55]) / total

    score = (
        strong_ratio * 3
        + acc_ratio * 2
        + obv_ratio * 3
        + slope_ratio * 3
        + rsi_ratio * 2
    )

    score = round(min(score, 13), 1)

    if score >= 8:
        text = "🟢 Thị trường đủ khỏe để chọn CP tiến hóa"
    elif score >= 6:
        text = "🟡 Trung tính - chỉ ưu tiên CP tiến hóa rõ"
    else:
        text = "🔴 Yếu - chỉ quan sát, hạn chế mua"

    return score, text


# =========================================================
# EVOLUTION HISTORY ENGINE
# =========================================================
def load_evolution_history() -> pd.DataFrame:
    if not os.path.exists(EVOLUTION_FILE):
        return pd.DataFrame(columns=["date", "time", "symbol", "state", "state_rank", "score"])

    try:
        df = pd.read_csv(EVOLUTION_FILE)
    except Exception:
        return pd.DataFrame(columns=["date", "time", "symbol", "state", "state_rank", "score"])

    needed = ["date", "time", "symbol", "state", "state_rank", "score"]
    for col in needed:
        if col not in df.columns:
            df[col] = np.nan

    df = df[needed].copy()
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    df["state_rank"] = pd.to_numeric(df["state_rank"], errors="coerce").fillna(0).astype(int)
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(float)

    return df


def trim_history_days(history: pd.DataFrame, max_days: int = MAX_HISTORY_DAYS) -> pd.DataFrame:
    if history.empty:
        return history

    dates = sorted(history["date"].dropna().unique().tolist())
    keep_dates = dates[-max_days:]
    return history[history["date"].isin(keep_dates)].copy()


def save_evolution_history(scan_df: pd.DataFrame) -> pd.DataFrame:
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    history = load_evolution_history()

    # Xóa bản ghi của ngày hiện tại để mỗi ngày chỉ giữ snapshot mới nhất
    if not history.empty:
        history = history[history["date"] != today].copy()

    rows = []
    for _, r in scan_df.iterrows():
        rows.append({
            "date": today,
            "time": now_time,
            "symbol": r["symbol"],
            "state": r["state"],
            "state_rank": int(r["state_rank"]),
            "score": float(r["total_score"]),
        })

    today_df = pd.DataFrame(rows)
    history = pd.concat([history, today_df], ignore_index=True)
    history = trim_history_days(history, MAX_HISTORY_DAYS)

    history.to_csv(EVOLUTION_FILE, index=False, encoding="utf-8-sig")

    return history


# =========================================================
# OPTIONAL: PUSH CSV TO GITHUB
# Nếu anh chưa muốn dùng thì để mặc định False
# =========================================================
def push_history_to_github():
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            return False, "Chưa có GITHUB_TOKEN trong secrets"

        github_token = st.secrets["GITHUB_TOKEN"]

        repo_owner = st.secrets.get("REPO_OWNER", "SONVODAI")
        repo_name = st.secrets.get("REPO_NAME", "scanner-ga-chien-clean")
        file_path = st.secrets.get("EVOLUTION_FILE_PATH", EVOLUTION_FILE)

        if not os.path.exists(EVOLUTION_FILE):
            return False, "Chưa có file evolution để đẩy"

        with open(EVOLUTION_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        headers = {"Authorization": f"token {github_token}"}

        get_resp = requests.get(url, headers=headers, timeout=10)
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        payload = {
            "message": f"Update evolution history {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(url, headers=headers, json=payload, timeout=10)

        if put_resp.status_code in [200, 201]:
            return True, "Đã đẩy evolution history lên GitHub"

        return False, f"GitHub lỗi: {put_resp.status_code} - {put_resp.text[:200]}"

    except Exception as e:
        return False, f"Không đẩy được GitHub: {e}"


# =========================================================
# EVOLUTION TABLES
# =========================================================
def build_evolution_pivot(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()

    temp = history.copy()
    temp["cell"] = temp["state"] + " (" + temp["score"].astype(int).astype(str) + ")"

    pivot = temp.pivot_table(
        index="symbol",
        columns="date",
        values="cell",
        aggfunc="last",
    )

    pivot = pivot.sort_index(axis=1)
    return pivot.reset_index()


def build_evolution_leaders(history: pd.DataFrame, scan_df: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()

    dates = sorted(history["date"].dropna().unique().tolist())
    if len(dates) < 2:
        return pd.DataFrame()

    leaders = []

    for symbol, g in history.groupby("symbol"):
        g = g.sort_values("date").tail(5).copy()

        if len(g) < 2:
            continue

        ranks = g["state_rank"].astype(int).tolist()
        scores = g["score"].astype(float).tolist()
        states = g["state"].astype(str).tolist()
        dates_used = g["date"].astype(str).tolist()

        rank_change = ranks[-1] - ranks[0]
        score_change = scores[-1] - scores[0]

        up_days = 0
        score_up_days = 0

        for i in range(1, len(g)):
            if ranks[i] > ranks[i - 1]:
                up_days += 1
            if scores[i] > scores[i - 1]:
                score_up_days += 1

        latest_rank = ranks[-1]
        latest_score = scores[-1]

        # Điều kiện nhảy bảng riêng:
        # 1) Rank tăng ít nhất 1 bậc
        # 2) Hoặc điểm tăng >= 2
        # 3) Hoặc điểm tăng 2 phiên liên tục và hiện tại >= 6
        is_leader = (
            rank_change >= 1
            or score_change >= 2
            or (score_up_days >= 2 and latest_score >= 6)
        )

        if not is_leader:
            continue

        current = scan_df[scan_df["symbol"] == symbol]
        if current.empty:
            continue

        r = current.iloc[0]

        leaders.append({
            "symbol": symbol,
            "price": r.get("price", np.nan),
            "state_now": states[-1],
            "score_now": latest_score,
            "rank_change": rank_change,
            "score_change": round(score_change, 2),
            "up_days": up_days,
            "score_up_days": score_up_days,
            "from_state": states[0],
            "to_state": states[-1],
            "from_date": dates_used[0],
            "to_date": dates_used[-1],
            "rsi14": r.get("rsi14", np.nan),
            "obv_status": r.get("obv_status", ""),
            "slope": r.get("ema9_ma20_slope", np.nan),
            "rs5": r.get("rs5", np.nan),
            "warning": r.get("warning", ""),
        })

    if not leaders:
        return pd.DataFrame()

    out = pd.DataFrame(leaders)
    out = out.sort_values(
        by=["rank_change", "score_change", "score_now", "slope"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    return out


# =========================================================
# UI CONTROLS
# =========================================================
left1, left2, left3, left4 = st.columns([1, 1.2, 1.2, 2.5])

with left1:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with left2:
    auto_refresh = st.checkbox("Auto refresh 5 phút", value=True)

with left3:
    push_github = st.checkbox("Đẩy CSV lên GitHub", value=False)

with left4:
    st.markdown(
        f"""
        <div style="font-size: 14px; color: #666;">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Update: <b>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</b>
        </div>
        """,
        unsafe_allow_html=True,
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


# =========================================================
# RUN SCAN
# =========================================================
with st.spinner("Đang quét dữ liệu realtime..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra lại mạng hoặc nguồn Yahoo Finance.")
    st.stop()


# =========================================================
# SAVE EVOLUTION
# =========================================================
history_df = save_evolution_history(scan_df)

if push_github:
    ok, msg = push_history_to_github()
    if ok:
        st.success(msg)
    else:
        st.warning(msg)


# =========================================================
# MARKET OVERVIEW
# =========================================================
market_score, market_text = calc_market_score(scan_df)

st.markdown("---")
st.markdown("## 📊 MARKET OVERVIEW GỌN")

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.metric("Market Score", f"{market_score}/13")

with m2:
    st.metric("Mạnh", int((scan_df["state"] == "🟢 MẠNH").sum()))

with m3:
    st.metric("Tích lũy", int((scan_df["state"] == "🟡 TÍCH LŨY").sum()))

with m4:
    st.metric("OBV xanh", int((scan_df["obv_status"] == "🟢").sum()))

if market_score >= 8:
    st.success(market_text)
elif market_score >= 6:
    st.warning(market_text)
else:
    st.error(market_text)


# =========================================================
# EVOLUTION LEADERS - BẢNG QUAN TRỌNG NHẤT
# =========================================================
st.markdown("---")
st.markdown("## 🚀 CP TIẾN HÓA - NHẢY BẢNG RIÊNG")

leaders_df = build_evolution_leaders(history_df, scan_df)

leader_cols = [
    "symbol", "price", "from_state", "to_state",
    "score_now", "score_change", "rank_change",
    "up_days", "score_up_days",
    "rsi14", "obv_status", "slope", "rs5", "warning",
]

if leaders_df.empty:
    st.info("Chưa có CP tiến hóa đủ điều kiện. Cần ít nhất 2 phiên dữ liệu.")
else:
    leader_cols = [c for c in leader_cols if c in leaders_df.columns]
    st.dataframe(
        leaders_df[leader_cols],
        use_container_width=True,
        height=min(520, 100 + len(leaders_df) * 35),
    )


# =========================================================
# DETAIL TABLE
# =========================================================
st.markdown("---")
st.markdown("## 📋 BẢNG CHI TIẾT REALTIME")

search_text = st.text_input("Lọc mã", value="", placeholder="Ví dụ: GVR, VHM, VIX...")

show_df = scan_df.copy()
if search_text.strip():
    key = search_text.strip().upper()
    show_df = show_df[show_df["symbol"].str.contains(key, na=False)].copy()

detail_cols = [
    "symbol", "price", "state", "total_score",
    "E", "R", "O", "S", "RS",
    "rsi14", "rsi_ema9", "obv_status",
    "ema9_ma20_slope", "slope_state",
    "dist_ema9_%", "rs5", "rs10",
    "warning",
]

detail_cols = [c for c in detail_cols if c in show_df.columns]

show_df = show_df[detail_cols].copy()
show_df.index = range(len(show_df))

st.dataframe(
    show_df,
    use_container_width=True,
    height=720,
)


# =========================================================
# EVOLUTION HISTORY PIVOT
# =========================================================
st.markdown("---")
st.markdown("## 📈 LỊCH SỬ TIẾN HÓA 15 PHIÊN")

pivot_df = build_evolution_pivot(history_df)

if pivot_df.empty:
    st.info("Chưa có lịch sử tiến hóa.")
else:
    # Ưu tiên hiển thị các mã đang có trong bảng leader trước
    if not leaders_df.empty:
        leader_symbols = leaders_df["symbol"].tolist()
        pivot_df["_priority"] = pivot_df["symbol"].apply(lambda x: 0 if x in leader_symbols else 1)
        pivot_df = pivot_df.sort_values(["_priority", "symbol"]).drop(columns=["_priority"])

    st.dataframe(
        pivot_df,
        use_container_width=True,
        height=620,
    )


# =========================================================
# RAW HISTORY DOWNLOAD
# =========================================================
st.markdown("---")
st.markdown("## 💾 FILE LỊCH SỬ")

c1, c2, c3 = st.columns([1, 1, 3])

with c1:
    st.metric("Số ngày lưu", history_df["date"].nunique() if not history_df.empty else 0)

with c2:
    st.metric("Số dòng lịch sử", len(history_df))

with c3:
    st.caption(f"File: {EVOLUTION_FILE}. Mỗi ngày lưu snapshot mới nhất, tối đa {MAX_HISTORY_DAYS} phiên.")

if os.path.exists(EVOLUTION_FILE):
    with open(EVOLUTION_FILE, "rb") as f:
        st.download_button(
            label="⬇️ Tải group_evolution_history.csv",
            data=f,
            file_name=EVOLUTION_FILE,
            mime="text/csv",
        )


# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.caption(
    "Bản nhẹ: không còn bảng nhóm nặng. Quyết định chính nằm ở CP TIẾN HÓA. "
    "Realtime giữ cache 5 phút giống lõi V18.4."
)
