import time
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Scanner + Portfolio Gà Chiến", page_icon="🐔", layout="wide")

# =========================
# WATCHLIST
# =========================
WATCHLIST = sorted(list(set([
    "PLX","PVS","PVD","PVB","PVC","PVT","BSR","OIL","GAS","HAH","VSC","GMD","VOS","VTO","ACV",
    "MSH","TNG","TCM","GIL","VHC","ANV","FMC","VCS","PTB",
    "BFC","DCM","DPM","CSV","DDV","LAS","BMP","NTP","AAA","PAC","MSR","REE","GEE","GEX","PC1","HDG","GEG","NT2","TV2","DGC",
    "C4G","FCN","CII","KSB","DHA","CTI","HBC","HPG","HSG","NKG","VGS","CTD","HHV","VCG",
    "MWG","FRT","DGW","PET","HAX","MSN","DBC","HAG","BAF","MCH","PAN","VNM","MML",
    "VCB","BID","CTG","TCB","VPB","MBB","ACB","SHB","SSB","STB","HDB","TPB","VIB","LPB","OCB","MSB","NAB","EIB",
    "VND","SSI","HCM","SHS","VIX","BSI","FTS","TVS","APS","AGR","VCI","TCX","VCK","VPX","ORS","BVS","VDS","MBS",
    "VGC","SZC","IDC","KBC","LHG","IJC","DTD","BCM",
    "GVR","SIP","DPR","PHR","DRI",
    "FPT","VGI","CTR","VTP","CMG","ELC","FOX",
    "HVN","VJC","IMP","BVH","SBT","LSS","PNJ","TLG","DHT","TNH",
    "VIC","VHM","VRE","NVL","DXG","DXS","DIG","CEO","TCH","EVF","SAB"
])))

# =========================
# HELPERS
# =========================
def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def sma(s, window):
    return s.rolling(window).mean()

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)

def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).fillna(0).cumsum()

def atr(df, period=14):
    h_l = df["high"] - df["low"]
    h_c = (df["high"] - df["close"].shift()).abs()
    l_c = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def clean_yahoo(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.reset_index()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    rename = {
        "Date": "date", "Datetime": "date",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    }
    df = df.rename(columns=rename)

    need = ["open","high","low","close","volume"]
    if not all(c in df.columns for c in need):
        return pd.DataFrame()

    for c in need:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.dropna(subset=["close"]).reset_index(drop=True)

@st.cache_data(ttl=300, show_spinner=False)
def download(symbol):
    for suffix in [".VN", ".HN"]:
        try:
            df = yf.download(
                symbol + suffix,
                period="8mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )
            df = clean_yahoo(df)
            if len(df) >= 50:
                return df
        except Exception:
            pass
    return pd.DataFrame()

def indicators(df):
    x = df.copy()
    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)
    x["rsi14"] = rsi(x["close"], 14)
    x["rsi_ema9"] = ema(x["rsi14"], 9)
    x["obv"] = obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    ema12 = ema(x["close"], 12)
    ema26 = ema(x["close"], 26)
    x["macd"] = ema12 - ema26
    x["macd_signal"] = ema(x["macd"], 9)
    x["hist"] = x["macd"] - x["macd_signal"]

    x["atr14"] = atr(x, 14)
    x["vol_ma20"] = sma(x["volume"], 20)
    return x

# =========================
# SCAN LOGIC
# =========================
def analyze(symbol):
    raw = download(symbol)
    if raw.empty:
        return None

    df = indicators(raw)
    if len(df) < 50:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["close"])
    ema9 = float(last["ema9"])
    ma20 = float(last["ma20"])
    rsi14 = float(last["rsi14"])
    rsi_ema9 = float(last["rsi_ema9"])
    obv_now = float(last["obv"])
    obv_ma = float(last["obv_ema9"])
    hist = float(last["hist"])
    atr14 = float(last["atr14"]) if pd.notna(last["atr14"]) else 0
    vol = float(last["volume"])
    vol_ma20 = float(last["vol_ma20"]) if pd.notna(last["vol_ma20"]) else 0

    # ===== 13 điểm chuẩn Daily =====
    score = 0
    warn = []

    # OBV max 4
    if obv_now > obv_ma:
        score += 3
        if last["obv"] > prev["obv"]:
            score += 1
    else:
        warn.append("OBV gãy")

    # Giá max 3
    if price > ema9:
        score += 1
    else:
        warn.append("Giá dưới EMA9")

    if ema9 > ma20:
        score += 1
    else:
        warn.append("EMA9 chưa trên MA20")

    if price > ma20:
        score += 1
    else:
        warn.append("Giá dưới MA20")

    # RSI max 3
    if rsi14 > 55:
        score += 1
    else:
        warn.append("RSI yếu")

    if rsi14 > rsi_ema9:
        score += 1
    else:
        warn.append("RSI dưới EMA9")

    if 60 <= rsi14 <= 75:
        score += 1

    # MACD max 2
    if hist > 0:
        score += 1
    else:
        warn.append("MACD âm")

    if last["hist"] > prev["hist"]:
        score += 1
    else:
        warn.append("MACD co lại")

    # ATR max 1
    if atr14 > 0 and atr14 / price < 0.06:
        score += 1

    score = min(score, 13)

    dist_ema9 = (price / ema9 - 1) * 100 if ema9 else np.nan
    breakout_ref = df["high"].iloc[-21:-1].max()

    if score >= 10 and price > ema9 > ma20 and obv_now > obv_ma:
        group = "CP MẠNH"
    elif -1 <= dist_ema9 <= 1.2 and score >= 8 and obv_now > obv_ma:
        group = "PULL ĐẸP"
    elif -2.5 <= dist_ema9 <= 2.5 and score >= 7:
        group = "PULL VỪA"
    elif price >= breakout_ref * 1.01 and vol_ma20 > 0 and vol >= vol_ma20 * 1.2 and score >= 8:
        group = "MUA BREAK"
    elif score >= 6:
        group = "MUA EARLY"
    elif score >= 4:
        group = "TÍCH LŨY"
    else:
        group = "THEO DÕI"

    if score >= 10:
        status = "🟢 Gà chiến"
    elif score >= 8:
        status = "🔵 Gà khỏe"
    elif score >= 6:
        status = "🟡 Gà nghỉ"
    elif score >= 4:
        status = "🟠 Yếu dần"
    else:
        status = "🔴 Gãy"

    return {
        "symbol": symbol,
        "group": group,
        "price": round(price, 0),
        "ema9": round(ema9, 2),
        "ma20": round(ma20, 2),
        "rsi14": round(rsi14, 2),
        "rsi_ema9": round(rsi_ema9, 2),
        "obv": round(obv_now, 0),
        "obv_ema9": round(obv_ma, 0),
        "obv_status": "🟢" if obv_now > obv_ma else "🔴",
        "hist": round(hist, 2),
        "atr14": round(atr14, 2),
        "dist_ema9_pct": round(dist_ema9, 2),
        "score13": score,
        "status": status,
        "warning": " / ".join(warn) if warn else "Không"
    }

@st.cache_data(ttl=300, show_spinner=False)
def run_scan(symbols):
    rows = []
    for s in symbols:
        try:
            item = analyze(s)
            if item:
                rows.append(item)
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    order = {
        "CP MẠNH": 1,
        "PULL ĐẸP": 2,
        "MUA BREAK": 3,
        "PULL VỪA": 4,
        "MUA EARLY": 5,
        "TÍCH LŨY": 6,
        "THEO DÕI": 7
    }
    df["rank"] = df["group"].map(order).fillna(99)
    return df.sort_values(["rank", "score13"], ascending=[True, False]).reset_index(drop=True)

# =========================
# MARKET
# =========================
def market_score(df):
    if df.empty:
        return 0

    total = len(df)
    strong = len(df[df["score13"] >= 8]) / total
    obv_ok = len(df[df["obv_status"] == "🟢"]) / total
    price_ok = len(df[df["price"] > df["ema9"]]) / total

    score = strong * 5 + obv_ok * 4 + price_ok * 4
    return round(min(score, 13), 1)

# =========================
# PORTFOLIO
# =========================
def parse_portfolio(text):
    rows = []
    for line in text.splitlines():
        try:
            p = line.split(",")
            if len(p) >= 2:
                sym = p[0].strip().upper()
                buy = float(p[1])
                nav = float(p[2]) if len(p) >= 3 else 0
                rows.append((sym, buy, nav))
        except Exception:
            continue
    return rows

def stop_engine(r):
    price = float(r["price"])
    ema9 = float(r["ema9"])
    ma20 = float(r["ma20"])
    atr14 = float(r["atr14"]) if pd.notna(r["atr14"]) else 0

    if r["score13"] >= 10:
        return max(ema9, price - 1.2 * atr14)
    if r["score13"] >= 8:
        return max(ma20, price - 1.5 * atr14)
    if r["score13"] >= 6:
        return ma20
    return price

def portfolio_action(r, pnl, market):
    warning = str(r["warning"])

    if market < 6:
        if r["score13"] < 8 or "OBV gãy" in warning:
            return "🔴 GIẢM/BÁN - thị trường yếu"
        return "🟡 GIỮ NHỎ - không add"

    if "OBV gãy" in warning and "RSI yếu" in warning:
        return "🔴 BÁN / GIẢM MẠNH"

    if r["score13"] >= 10:
        return "🟢 GIỮ CHẶT"
    if r["score13"] >= 8:
        return "🔵 GIỮ"
    if r["score13"] >= 6:
        return "🟡 GIỮ CÓ ĐIỀU KIỆN"
    return "🔴 BÁN / LOẠI"

def build_portfolio_table(scan_df, text, market):
    rows = []
    for sym, buy, nav in parse_portfolio(text):
        sub = scan_df[scan_df["symbol"] == sym]
        if sub.empty:
            rows.append({
                "Mã": sym,
                "Giá mua": buy,
                "Giá hiện tại": None,
                "% Lãi/Lỗ": None,
                "%NAV": nav,
                "Điểm": None,
                "Nhóm": "Không có data",
                "Trạng thái": "⚪ Không rõ",
                "Cảnh báo": "Không có trong scan",
                "Stop Engine": None,
                "Hành động": "CHECK TAY"
            })
            continue

        r = sub.iloc[0]
        price = float(r["price"])
        pnl = (price - buy) / buy * 100 if buy > 0 else 0
        stop = stop_engine(r)
        action = portfolio_action(r, pnl, market)

        rows.append({
            "Mã": sym,
            "Giá mua": buy,
            "Giá hiện tại": price,
            "% Lãi/Lỗ": round(pnl, 2),
            "%NAV": nav,
            "Điểm": r["score13"],
            "Nhóm": r["group"],
            "Trạng thái": r["status"],
            "Cảnh báo": r["warning"],
            "Stop Engine": round(stop, 0),
            "Hành động": action
        })

    return pd.DataFrame(rows)

# =========================
# UI
# =========================
st.title("🐔 Scanner Gà Chiến + Quản trị danh mục")
st.caption("Một nguồn dữ liệu – một hệ thống: Scanner chọn gà, Portfolio quản trị gà.")

c1, c2, c3 = st.columns([1, 1, 3])

with c1:
    if st.button("🚀 SCAN / REFRESH", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with c2:
    show_detail = st.checkbox("Hiện bảng chi tiết", value=False)

with c3:
    st.write(f"Watchlist: **{len(WATCHLIST)} mã** | Cập nhật: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**")

with st.spinner("Đang quét dữ liệu..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu.")
    st.stop()

mk = market_score(scan_df)

st.markdown("## 📊 MARKET OVERVIEW")

m1, m2, m3 = st.columns(3)
m1.metric("Market Score", f"{mk}/13")
m2.metric("Số mã mạnh ≥8 điểm", len(scan_df[scan_df["score13"] >= 8]))
m3.metric("OBV xanh", len(scan_df[scan_df["obv_status"] == "🟢"]))

if mk >= 8:
    st.success("🟢 Thị trường đủ điều kiện chọn gà")
elif mk >= 6:
    st.warning("🟡 Thị trường trung tính – chỉ test nhỏ")
else:
    st.error("🔴 Thị trường yếu – ưu tiên quản trị rủi ro")

# =========================
# PORTFOLIO FIRST
# =========================
st.markdown("---")
st.markdown("## 📊 QUẢN TRỊ DANH MỤC")

portfolio_text = st.text_area(
    "Anh chỉ nhập: Mã,Giá mua,%NAV",
    placeholder="BAF,36600,4.5\nGVR,33217,12\nVHM,144300,3.5",
    height=130
)

pf = build_portfolio_table(scan_df, portfolio_text, mk)

if pf.empty:
    st.info("Chưa nhập danh mục.")
else:
    st.dataframe(pf, use_container_width=True, height=360)

    a, b, c = st.columns(3)
    a.metric("Lãi/Lỗ TB", f"{round(pf['% Lãi/Lỗ'].dropna().mean(), 2)}%")
    b.metric("Tổng NAV", f"{round(pd.to_numeric(pf['%NAV'], errors='coerce').fillna(0).sum(), 2)}%")
    c.metric("Số mã", len(pf))

# =========================
# TOP / GROUPS
# =========================
st.markdown("---")
st.markdown("## 🎯 TOP GÀ ĐÁNG CHÚ Ý")

top_cols = ["symbol","group","price","score13","rsi14","obv_status","dist_ema9_pct","status","warning"]
st.dataframe(scan_df[top_cols].head(15), use_container_width=True, height=420)

st.markdown("## 🐔 PHÂN NHÓM")

groups = ["CP MẠNH","PULL ĐẸP","MUA BREAK","PULL VỪA","MUA EARLY","TÍCH LŨY","THEO DÕI"]
cols = st.columns(len(groups))

for i, g in enumerate(groups):
    with cols[i]:
        st.metric(g, int((scan_df["group"] == g).sum()))

selected_group = st.selectbox("Xem nhóm", groups)
sub = scan_df[scan_df["group"] == selected_group]
st.dataframe(sub[top_cols], use_container_width=True, height=420)

if show_detail:
    st.markdown("## 📋 BẢNG TỔNG CHI TIẾT")
    detail_cols = [
        "symbol","group","price","ema9","ma20","rsi14","rsi_ema9",
        "obv","obv_ema9","obv_status","hist","atr14",
        "dist_ema9_pct","score13","status","warning"
    ]
    st.dataframe(scan_df[detail_cols], use_container_width=True, height=720)

st.markdown("---")
st.caption("Market-first. Portfolio dùng chung dữ liệu với scanner. Không nhập 5 trục thủ công.")
