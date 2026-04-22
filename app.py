import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from vnstock import Quote, Trading

st.set_page_config(page_title="Scanner Gà Chiến V31", layout="wide")

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
# WATCHLIST / SECTORS
# =========================================================
SECTORS = {
    "BANK_CHUNGKHOAN": [
        "VCB","BID","CTG","TCB","VPB","MBB","ACB","SHB","SSB","STB","HDB","TPB","VIB","LPB","OCB","MSB","NAB","EIB",
        "VND","SSI","HCM","SHS","VIX","BSI","FTS","TVS","APS","AGR","VCI"
    ],
    "BDS_THEP": [
        "VHM","VIC","VRE","NVL","DXG","DIG","CEO","TCH",
        "HPG","HSG","NKG","VGS","CTD","HHV","VCG","CII","FCN","C4G"
    ],
    "DAUKHI_LOGISTIC": [
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
# HELPER: indicators
# =========================================================
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()

def rsi_wilder(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill()

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    diff = close.diff().fillna(0)
    direction = np.sign(diff)
    direction = pd.Series(direction, index=close.index).replace(0, method="ffill").fillna(0)
    return (direction * volume).cumsum()

def pick_first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None

# =========================================================
# FETCH SNAPSHOT MANY TICKERS AT ONCE
# =========================================================
@st.cache_data(ttl=120)
def fetch_price_board(symbols: tuple[str, ...], source: str) -> pd.DataFrame:
    """
    Lấy bảng giá nhiều mã cùng lúc.
    """
    try:
        board = Trading(source=source).price_board(list(symbols))
    except Exception:
        return pd.DataFrame()

    if board is None or len(board) == 0:
        return pd.DataFrame()

    df = board.copy()

    # Chuẩn hóa cột theo nhiều khả năng tên khác nhau
    symbol_col = pick_first_existing(df, ["symbol", "ticker", "code"])
    close_col = pick_first_existing(df, ["match_price", "price", "close", "last_price"])
    open_col = pick_first_existing(df, ["open", "open_price"])
    vol_col = pick_first_existing(df, ["match_volume", "volume", "total_volume", "accumulated_volume"])

    if symbol_col is None or close_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["symbol"] = df[symbol_col].astype(str).str.upper()
    out["price"] = pd.to_numeric(df[close_col], errors="coerce")
    out["open"] = pd.to_numeric(df[open_col], errors="coerce") if open_col else np.nan
    out["volume"] = pd.to_numeric(df[vol_col], errors="coerce") if vol_col else np.nan

    out = out.dropna(subset=["symbol", "price"]).reset_index(drop=True)
    return out

# =========================================================
# FETCH HISTORY ONLY FOR SHORTLISTED TICKERS
# =========================================================
@st.cache_data(ttl=300)
def fetch_symbol_history(symbol: str, source: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        q = Quote(symbol=symbol, source=source)
        df = q.history(start=start_date, end=end_date, interval="1D")
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

    need = ["time", "open", "high", "low", "close", "volume"]
    if any(c not in df.columns for c in need):
        return pd.DataFrame()

    df = df[need].copy()
    df["time"] = pd.to_datetime(df["time"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna().reset_index(drop=True)

def enrich_history(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)
    x["rsi14"] = rsi_wilder(x["close"], 14)
    x["rsi_ema9"] = ema(x["rsi14"], 9)
    x["obv"] = obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)
    x["vol_sma20"] = sma(x["volume"], 20)
    return x

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

    if price > ema9_v >= ma20_v and rsi >= 58 and obv_ok:
        return "CP MẠNH"

    if price > row["high_3_prev"] and rsi >= 60 and vol_ratio >= 1.25 and green:
        return "MUA BREAK"

    if price > ema9_v >= ma20_v and 55 <= rsi <= 72 and dist <= 1.5 and obv_ok:
        return "PULL ĐẸP"

    if price > ema9_v >= ma20_v and rsi >= 50 and 1.5 < dist <= 3.0:
        return "PULL VỪA"

    if 45 <= rsi <= 55 and dist <= 2.0 and abs(row["ema9_ma20_gap_pct"]) <= 4.0:
        return "MUA EARLY"

    if 45 <= rsi <= 60:
        return "TÍCH LŨY"

    return "THEO DÕI"

def calc_ero(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["E"] = 0
    df.loc[df["rsi14"] >= 55, "E"] += 1
    df.loc[df["price"] > df["ema9"], "E"] += 1
    df["E"] = df["E"].clip(0, 2)

    df["R"] = 0
    df.loc[df["rsi14"] >= 75, "R"] += 1
    df.loc[df["dist_from_ema9_pct"].abs() >= 5, "R"] += 1
    df["R"] = df["R"].clip(0, 2)

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

    real = round(float(max(0, min(13, trend + momentum + money - risk_penalty))), 1)
    live = round(max(0.0, real - 0.7), 1)
    return real, live

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
# BUILD ONE SECTOR:
# 1) board nhiều mã 1 lần
# 2) chỉ fetch history cho shortlist
# =========================================================
def build_sector_table(symbols: list[str], source: str, start_date: str, end_date: str, progress_bar=None) -> pd.DataFrame:
    snapshot = fetch_price_board(tuple(symbols), source=source)
    if snapshot.empty:
        return pd.DataFrame()

    # shortlist sơ bộ từ snapshot
    # ưu tiên mã có giá/open/volume đầy đủ và volume dương
    candidates = snapshot.copy()
    candidates = candidates.dropna(subset=["symbol", "price"])
    if "volume" in candidates.columns:
        candidates = candidates[candidates["volume"].fillna(0) >= 0]

    # lấy tối đa 12 mã mỗi ngành để nhẹ cloud
    candidates = candidates.head(12).reset_index(drop=True)

    rows = []
    total = len(candidates)

    for i, item in candidates.iterrows():
        symbol = item["symbol"]
        try:
            raw = fetch_symbol_history(symbol, source=source, start_date=start_date, end_date=end_date)
            if raw.empty or len(raw) < 30:
                continue

            x = enrich_history(raw).dropna().reset_index(drop=True)
            if len(x) < 25:
                continue

            latest = x.iloc[-1]
            prev = x.iloc[-2]
            high_3_prev = x.iloc[-4:-1]["high"].max() if len(x) >= 4 else prev["high"]

            open_today = float(item["open"]) if pd.notna(item.get("open", np.nan)) else float(latest["open"])
            volume_now = float(item["volume"]) if pd.notna(item.get("volume", np.nan)) else float(latest["volume"])

            rows.append({
                "symbol": symbol,
                "price": float(item["price"]),
                "open": open_today,
                "ema9": float(latest["ema9"]),
                "ma20": float(latest["ma20"]),
                "rsi14": float(latest["rsi14"]),
                "rsi_prev": float(prev["rsi14"]),
                "rsi_accel": float(latest["rsi14"] - prev["rsi14"]),
                "obv": float(latest["obv"]),
                "obv_prev": float(prev["obv"]),
                "obv_ema9": float(latest["obv_ema9"]),
                "obv_status": "🟢" if latest["obv"] >= latest["obv_ema9"] else "🔴",
                "volume": volume_now,
                "vol_sma20": float(latest["vol_sma20"]),
                "vol_ratio": float(volume_now / latest["vol_sma20"]) if latest["vol_sma20"] else np.nan,
                "price_green_today": bool(float(item["price"]) > open_today),
                "dist_from_ema9_pct": float((float(item["price"]) - latest["ema9"]) / latest["ema9"] * 100),
                "ema9_ma20_gap_pct": float((latest["ema9"] - latest["ma20"]) / latest["ma20"] * 100),
                "obv_flow": float(latest["obv"] - prev["obv"]),
                "high_3_prev": float(high_3_prev),
            })
        except Exception:
            pass

        if progress_bar is not None and total > 0:
            progress_bar.progress((i + 1) / total)

        time.sleep(0.08)

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
# SESSION
# =========================================================
if "scanner_sector_index" not in st.session_state:
    st.session_state["scanner_sector_index"] = 0
if "scanner_data_map" not in st.session_state:
    st.session_state["scanner_data_map"] = {}
if "scanner_last_sector" not in st.session_state:
    st.session_state["scanner_last_sector"] = None
if "scanner_last_time" not in st.session_state:
    st.session_state["scanner_last_time"] = None
if "scanner_initialized" not in st.session_state:
    st.session_state["scanner_initialized"] = False

# =========================================================
# UI
# =========================================================
st.markdown('<div class="main-title">📊 SCANNER GÀ CHIẾN V31</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"🗓 **Ngày theo dõi:** {now_vn.strftime('%d/%m/%Y')}")
with c2:
    st.markdown(f"⏰ **Giờ VN:** {now_vn.strftime('%H:%M:%S')}")

source = st.selectbox("Nguồn dữ liệu Vnstock", ["KBS", "VCI"], index=0)

b1, b2 = st.columns(2)
with b1:
    scan = st.button("🔄 SCAN ngành tiếp theo", use_container_width=True)
with b2:
    reset_scan = st.button("♻️ Reset vòng quét", use_container_width=True)

if reset_scan:
    st.session_state["scanner_sector_index"] = 0
    st.session_state["scanner_data_map"] = {}
    st.session_state["scanner_last_sector"] = None
    st.session_state["scanner_last_time"] = None
    st.session_state["scanner_initialized"] = False

st.markdown(
    '<div class="small-note">V31 dùng bảng giá nhiều mã trước, rồi mới lấy history cho shortlist. '
    'Cách này nhẹ hơn hẳn so với gọi history cho từng mã.</div>',
    unsafe_allow_html=True
)

if scan:
    sector_name = SECTOR_ORDER[st.session_state["scanner_sector_index"]]
    symbols = SECTORS[sector_name]
    start_date = (now_vn - timedelta(days=220)).strftime("%Y-%m-%d")
    end_date = now_vn.strftime("%Y-%m-%d")

    st.info(f"Đang quét nhóm: {sector_name}")
    progress = st.progress(0.0)

    sector_df = build_sector_table(
        symbols=symbols,
        source=source,
        start_date=start_date,
        end_date=end_date,
        progress_bar=progress
    )

    st.session_state["scanner_data_map"][sector_name] = sector_df
    st.session_state["scanner_last_sector"] = sector_name
    st.session_state["scanner_last_time"] = now_vn.strftime("%H:%M:%S")
    st.session_state["scanner_initialized"] = True
    st.session_state["scanner_sector_index"] = (st.session_state["scanner_sector_index"] + 1) % len(SECTOR_ORDER)

frames = [x for x in st.session_state["scanner_data_map"].values() if x is not None and not x.empty]
if frames:
    df_all = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["symbol"], keep="last")
else:
    df_all = pd.DataFrame()

st.markdown("---")
st.markdown('<div class="section-title">🔄 TRẠNG THÁI QUÉT</div>', unsafe_allow_html=True)

i1, i2, i3 = st.columns(3)
with i1:
    st.write(f"**Ngành kế tiếp:** {SECTOR_ORDER[st.session_state['scanner_sector_index']]}")
with i2:
    st.write(f"**Ngành vừa quét:** {st.session_state['scanner_last_sector'] or '-'}")
with i3:
    st.write(f"**Lúc quét gần nhất:** {st.session_state['scanner_last_time'] or '-'}")

done_count = len(st.session_state["scanner_data_map"])
st.caption(f"Đã quét {done_count}/{len(SECTOR_ORDER)} cụm ngành.")

if not st.session_state["scanner_initialized"]:
    st.warning("Chưa có dữ liệu. Anh bấm 'SCAN ngành tiếp theo' để bắt đầu.")
    st.stop()

if df_all.empty:
    st.error("Đã scan nhưng chưa lấy được dữ liệu hợp lệ. Đổi source KBS/VCI rồi scan lại.")
    st.stop()

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

st.markdown("---")
st.markdown('<div class="section-title">🎯 TOP VÀO TIỀN HÔM NAY</div>', unsafe_allow_html=True)

top = pick_top_money(df_all)
if top.empty:
    st.write("Chưa có mã vào tiền nổi bật hôm nay.")
else:
    for _, r in top.iterrows():
        st.write(
            f"**{r['symbol']} — {r['group']}** | Giá: {round(r['price'],2)} | "
            f"Score: {int(r['total_score'])} | Dist EMA9: {round(r['dist_from_ema9_pct'],2)}% | "
            f"Vol ratio: {round(r['vol_ratio'],2)} | RSI accel: {round(r['rsi_accel'],2)}"
        )

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

st.markdown("---")
st.markdown('<div class="section-title">🧠 TOP 20 CỔ PHIẾU MẠNH (E-R-O)</div>', unsafe_allow_html=True)

top20 = df_all.sort_values(by=["total_score","E","O","price"], ascending=[False,False,False,False]).head(20)
st.dataframe(
    top20[["symbol","group","price","E","R","O","total_score","rsi14","dist_from_ema9_pct","obv_status"]],
    use_container_width=True,
    height=420,
    hide_index=False
)

st.markdown("---")
st.markdown('<div class="section-title">BẢNG TỔNG CHI TIẾT</div>', unsafe_allow_html=True)

group_priority = {
    "CP MẠNH": 0, "MUA BREAK": 1, "PULL ĐẸP": 2, "PULL VỪA": 3,
    "MUA EARLY": 4, "TÍCH LŨY": 5, "THEO DÕI": 6
}
df_show = df_all.copy()
df_show["group_priority"] = df_show["group"].map(group_priority).fillna(9)
df_show = df_show.sort_values(by=["group_priority","total_score","E","O","price"], ascending=[True,False,False,False,False])

st.dataframe(
    df_show[[
        "symbol","group","price","open","ema9","ma20","rsi14","rsi_prev","rsi_accel",
        "obv","obv_prev","obv_ema9","obv_status","volume","vol_sma20","vol_ratio",
        "price_green_today","dist_from_ema9_pct","pull_label"
    ]],
    use_container_width=True,
    height=560,
    hide_index=False
)
