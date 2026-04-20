import datetime
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến V15", layout="wide")

# =========================
# AUTO REFRESH 5 PHÚT
# =========================
components.html(
    """
    <script>
        setTimeout(function() {
            window.parent.location.reload();
        }, 300000);
    </script>
    """,
    height=0,
)

st.title("🐔 Scanner Gà Chiến V15 – Alert Realtime")
st.caption(f"⏱ Tự cập nhật mỗi 5 phút | Cập nhật lúc: {datetime.datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Thiết lập")
market_score = st.sidebar.slider("Market Score", 1, 10, 8)
top_n = st.sidebar.slider("Top toàn thị trường", 3, 15, 5)

# =========================
# INPUT
# =========================
watchlist_text = st.text_area(
    "Danh sách mã theo dõi",
    """VCB, BID, CTG, TCB, MBB, VPB, STB, HDB, ACB, SHB, TPB, LPB, EIB, ABB, MSB, KLB, EVF, VNINDEX
SSI, VIX, SHS, MBS, HCM, VCI, VND, CTS, FTS, BSI, BVS, ORS, VDS, AGR
VHM, NLG, KDH, CEO, CII, DXG, TCH, DPG, HDC, NVL, NTL, NHA, HUT, DIG, PDR, DXS, VIC, VPL,VRE
VGC, IDC, KBC, SZC, BCM, LHG, IJC, GVR, PHR, DPR, SIP, TRC, DRC, CSM
MWG, DGW, FRT, PET, PNJ, MSN, PAN, FMC, DBC, HAG, VNM, SAB, SBT, TLG
REE, GEE, GEX, PC1, NT2, HDG, GEG, POW
DPM, DCM, LAS, DDV, DGC, CSV, BFC, MSR, BMP, NTP
BSR, PVS, PVD, PVB, PVC, PVT, OIL, PLX, GAS
VTP, CTR, VGI, FPT, CMG, FOX, TNH, YEG
HAH, GMD, VSC, VOS, VTO, HVN, VJC, ACV, CTD, HHV,FCN, LCG, KSB, CTI,C4G, HPG, HSG, NKG, VGS, TLH, TVN, BVH, MIG, BMI, MSH, TNG, TCM, GIL, VGT, VCS, PTB, VHC, ANV,""",
    height=220,
)

top_week_text = st.text_area(
    "Top tăng tuần",
    """VHM, VIC, GEE, NVL, HHS, HCM, GEX, PET, TCH, VJC, CII, VRE, VPL, SHS, KBC, LHG, MSB, LPB, IDC, VIX, VGI, BMP, HAG, DXG, VPB, VTP, CTR, TCB, HVN, BFC""",
    height=120,
)

top_month_text = st.text_area(
    "Top tăng tháng",
    """VHM, VIC, GEE, NVL, HHS, HCM, GEX, PET, TCH, VJC, CII, VRE, VPL, SHS, KBC, LHG, MSB, LPB, IDC, VIX, VGI, BMP, HAG, DXG, VPB, VTP, CTR, TCB, HVN, MSH""",
    height=120,
)

# =========================
# HELPERS
# =========================
def parse_codes(text: str):
    items = []
    for x in text.replace("\n", ",").split(","):
        x = x.strip().upper()
        if x:
            if not x.endswith(".VN"):
                x += ".VN"
            items.append(x)
    return list(dict.fromkeys(items))

watchlist = parse_codes(watchlist_text)
top_week = set(parse_codes(top_week_text))
top_month = set(parse_codes(top_month_text))

sector_map = {
    "VCB.VN":"BANK","BID.VN":"BANK","CTG.VN":"BANK","TCB.VN":"BANK","MBB.VN":"BANK","VPB.VN":"BANK","STB.VN":"BANK","HDB.VN":"BANK","ACB.VN":"BANK","SHB.VN":"BANK","TPB.VN":"BANK","LPB.VN":"BANK","EIB.VN":"BANK","ABB.VN":"BANK","MSB.VN":"BANK","KLB.VN":"BANK","EVF.VN":"BANK",
    "SSI.VN":"CK","VIX.VN":"CK","SHS.VN":"CK","MBS.VN":"CK","HCM.VN":"CK","VCI.VN":"CK","VND.VN":"CK","CTS.VN":"CK","FTS.VN":"CK","BSI.VN":"CK","BVS.VN":"CK","ORS.VN":"CK","VDS.VN":"CK","AGR.VN":"CK",
    "VHM.VN":"BDS","NLG.VN":"BDS","KDH.VN":"BDS","CEO.VN":"BDS","CII.VN":"BDS","DXG.VN":"BDS","TCH.VN":"BDS","DPG.VN":"BDS","HDC.VN":"BDS","NVL.VN":"BDS","NTL.VN":"BDS","NHA.VN":"BDS","HUT.VN":"BDS","DIG.VN":"BDS","PDR.VN":"BDS","DXS.VN":"BDS",
    "VGC.VN":"BDS_CN","IDC.VN":"BDS_CN","KBC.VN":"BDS_CN","SZC.VN":"BDS_CN","BCM.VN":"BDS_CN","LHG.VN":"BDS_CN","IJC.VN":"BDS_CN","GVR.VN":"BDS_CN","PHR.VN":"BDS_CN","DPR.VN":"BDS_CN","SIP.VN":"BDS_CN","TRC.VN":"BDS_CN","DRC.VN":"BDS_CN","CSM.VN":"BDS_CN",
    "MWG.VN":"BAN_LE","DGW.VN":"BAN_LE","FRT.VN":"BAN_LE","PET.VN":"BAN_LE","PNJ.VN":"BAN_LE","MSN.VN":"BAN_LE","PAN.VN":"BAN_LE","FMC.VN":"BAN_LE","DBC.VN":"BAN_LE","HAG.VN":"BAN_LE","VNM.VN":"BAN_LE","SAB.VN":"BAN_LE","SBT.VN":"BAN_LE","TLG.VN":"BAN_LE",
    "REE.VN":"DIEN","GEE.VN":"DIEN","GEX.VN":"DIEN","PC1.VN":"DIEN","NT2.VN":"DIEN","HDG.VN":"DIEN","GEG.VN":"DIEN","POW.VN":"DIEN",
    "DPM.VN":"HOA_CHAT","DCM.VN":"HOA_CHAT","LAS.VN":"HOA_CHAT","DDV.VN":"HOA_CHAT","DGC.VN":"HOA_CHAT","CSV.VN":"HOA_CHAT","BFC.VN":"HOA_CHAT","MSR.VN":"HOA_CHAT","BMP.VN":"HOA_CHAT","NTP.VN":"HOA_CHAT",
    "BSR.VN":"DAU","PVS.VN":"DAU","PVD.VN":"DAU","PVB.VN":"DAU","PVC.VN":"DAU","PVT.VN":"DAU","OIL.VN":"DAU","PLX.VN":"DAU","GAS.VN":"DAU",
    "HAH.VN":"LOGIS","GMD.VN":"LOGIS","VSC.VN":"LOGIS","VOS.VN":"LOGIS","VTO.VN":"LOGIS","HVN.VN":"LOGIS","VJC.VN":"LOGIS","ACV.VN":"LOGIS",
}

def normalize_series(x):
    if isinstance(x, pd.DataFrame):
        x = x.iloc[:, 0]
    return pd.to_numeric(x, errors="coerce")

def compute_rsi(close: pd.Series):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
def calc_obv(close: pd.Series, volume: pd.Series):
    return (np.sign(close.diff()) * volume).fillna(0).cumsum()

@st.cache_data(ttl=300)
def fetch_daily(symbol: str):
    return yf.download(
        symbol,
        period="9mo",
        interval="1d",
        progress=False,
        auto_adjust=False,
        threads=False,
    )
# =========================
# BUY TRIGGER REALTIME (B1-B2-B3)
# =========================
def check_buy_trigger(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    prev3 = df.iloc[-4] if len(df) >= 4 else df.iloc[0]

    close = latest["Close"]
    ema9 = latest["EMA9"]
    ma20 = latest["MA20"]
    rsi = latest["RSI"]
    rsi_ema = latest["RSI_EMA"]
    obv = latest["OBV"]
    obv_ema = latest["OBV_EMA"]
    vol = latest["Volume"]
    vol_ma = latest["VolMA20"]

    if pd.isna(ma20) or pd.isna(vol_ma):
        return None, ""

    # =========================
    # 1. Xác nhận trước đó cổ phiếu đã có pha tăng mạnh
    # =========================
    ref = df.iloc[-16:-4] if len(df) >= 20 else df.iloc[:-4]
    had_strong_run = False
    if len(ref) >= 8:
        ref_close_start = ref["Close"].iloc[0]
        ref_close_end = ref["Close"].iloc[-1]
        ref_rsi_max = ref["RSI"].max()
        ref_ema9 = ref["EMA9"].iloc[-1]
        ref_ma20 = ref["MA20"].iloc[-1]

        had_strong_run = (
            ref_close_end > ref_close_start * 1.08
            and ref_close_end > ref_ema9 > ref_ma20
            and ref_rsi_max >= 60
        )

    # =========================
    # 2. Pull đẹp thực sự
    # =========================
    recent_high = df["Close"].iloc[-9:-1].max() if len(df) >= 10 else df["Close"].max()
    drawdown = (recent_high - close) / recent_high if recent_high > 0 else 0

    near_ema9 = abs(close - ema9) / ema9 <= 0.02
    above_ma20 = close >= ma20 * 0.99
    pull_depth_ok = 0.02 <= drawdown <= 0.08
    vol_dry = vol < vol_ma
    candle_ok = abs(latest["Close"] - latest["Open"]) / latest["Close"] <= 0.03
    rsi_ok = rsi >= 50
    obv_ok = obv >= obv_ema * 0.995

    # loại case đã thủng EMA9 rồi mới ngoi lên lại
    reclaim_case = prev["Close"] < prev["EMA9"] * 0.992 and close >= ema9

    if (
        had_strong_run
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

    # =========================
    # 3. Reclaim EMA9
    # =========================
    reclaim_ok = (
        prev["Close"] < prev["EMA9"]
        and close >= ema9
        and obv >= obv_ema * 0.99
        and rsi > prev["RSI"]
    )
    if reclaim_ok:
        return "RE", "Reclaim EMA9"

    # =========================
    # 4. Breakout
    # =========================
    prev_high = df["High"].rolling(20).max().iloc[-2] if len(df) > 21 else df["High"].max()
    break_ok = (
        close > prev_high
        and vol > vol_ma * 1.3
        and rsi >= 60
        and obv >= obv_ema
    )
    if break_ok:
        return "B3", "Breakout mạnh"

    # =========================
    # 5. Early reversal
    # =========================
    early_ok = (
        rsi >= 45
        and rsi > rsi_ema
        and close >= ema9 * 0.995
        and obv >= obv_ema * 0.98
    )
    if early_ok:
        return "ER", "Early reversal"

    return None, ""
@st.cache_data(ttl=300)
def fetch_intraday(symbol: str):
    return yf.download(
        symbol,
        period="5d",
        interval="15m",
        progress=False,
        auto_adjust=False,
        threads=False,
    )

def analyze_stock(symbol: str):
    try:
        raw = fetch_daily(symbol)
        if raw is None or raw.empty or len(raw) < 80:
            return None

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

        if len(df) < 80:
            return None

        # indicators
        df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["RSI"] = compute_rsi(df["Close"])
        df["RSI_EMA"] = df["RSI"].ewm(span=9, adjust=False).mean()
        df["OBV"] = calc_obv(df["Close"], df["Volume"])
        df["OBV_EMA"] = df["OBV"].ewm(span=9, adjust=False).mean()
        df["VolMA20"] = df["Volume"].rolling(20).mean()

        latest = df.iloc[-1]

        close_now = float(latest["Close"])
        ema9 = float(latest["EMA9"])
        rsi = float(latest["RSI"]) if pd.notna(latest["RSI"]) else np.nan
        obv = float(latest["OBV"]) if pd.notna(latest["OBV"]) else np.nan
        obv_ema = float(latest["OBV_EMA"]) if pd.notna(latest["OBV_EMA"]) else np.nan
        vol = float(latest["Volume"])
        vol_ma = float(latest["VolMA20"]) if pd.notna(latest["VolMA20"]) else 0.0
        # =========================
        # CHECK BUY SIGNAL
        # =========================
        buy_code, buy_note = check_buy_trigger(df)
        # trend
        cond_price = (close_now > ema9 and ema9 > ma20) if not np.isnan(ma20) else False
        cond_obv = obv > obv_ema if not np.isnan(obv_ema) else False
        cond_slope = ema9 > float(df["EMA9"].iloc[-3])
        cond_rsi_turn = rsi > float(df["RSI"].iloc[-3]) if len(df) > 3 and pd.notna(df["RSI"].iloc[-3]) else False
        cond_rs = (close_now > ma20 * 1.03) if not np.isnan(ma20) else False

        dist_ma20 = (close_now - ma20) / ma20 if not np.isnan(ma20) and ma20 != 0 else 0.0
        too_extended = dist_ma20 > 0.15

        # returns
       ret_20d = (close_now / float(df["Close"].iloc[-20]) - 1) if len(df) > 20 else 0.0
ret_60d = (close_now / float(df["Close"].iloc[-60]) - 1) if len(df) > 60 else 0.0

# volume / money
vol_dry = vol_ma > 0 and vol < vol_ma * 0.8
vol_break = vol_ma > 0 and vol > vol_ma * 1.5
money_score = (vol / vol_ma) if vol_ma > 0 else 1.0

# ===== intraday confirm =====
intraday_ok = False

try:
    intra = fetch_intraday(symbol)

    if intra is not None and not intra.empty and len(intra) > 10:
        iclose = normalize_series(intra["Close"]).dropna()
        ivol = normalize_series(intra["Volume"]).reindex(iclose.index)

        if len(iclose) > 10:
            iema9 = iclose.ewm(span=9, adjust=False).mean()
            iobv = calc_obv(iclose, ivol)

            intraday_ok = bool(
                iclose.iloc[-1] > iema9.iloc[-1]
                and iobv.iloc[-1] > iobv.iloc[-3]
            )

except Exception:
    intraday_ok = False try:
    intra = fetch_intraday(symbol)

    if intra is not None and not intra.empty and len(intra) > 10:
        iclose = normalize_series(intra["Close"]).dropna()
        ivol = normalize_series(intra["Volume"]).reindex(iclose.index)

        if len(iclose) > 10:
            iema9 = iclose.ewm(span=9, adjust=False).mean()
            iobv = calc_obv(iclose, ivol)

            intraday_ok = bool(
                iclose.iloc[-1] > iema9.iloc[-1]
                and iobv.iloc[-1] > iobv.iloc[-3]
            )

except Exception:
    intraday_ok = False


# ===== leader score =====
leader_score = 0

if ret_20d > 0.15:
    leader_score += 1
if ret_60d > 0.30:
    leader_score += 1
if money_score > 1.2:
    leader_score += 1
if cond_rs:
    leader_score += 1
if cond_obv:
    leader_score += 1
if symbol in top_week:
    leader_score += 1
if symbol in top_month:
    leader_score += 1
if intraday_ok:
    leader_score += 1
try:
    intra = fetch_intraday(symbol)

    if intra is not None and not intra.empty and len(intra) > 10:
        iclose = normalize_series(intra["Close"]).dropna()
        ivol = normalize_series(intra["Volume"]).reindex(iclose.index)

        if len(iclose) > 10:
            iema9 = iclose.ewm(span=9, adjust=False).mean()
            iobv = calc_obv(iclose, ivol)

            intraday_ok = bool(
                iclose.iloc[-1] > iema9.iloc[-1]
                and iobv.iloc[-1] > iobv.iloc[-3]
            )

except Exception:
    intraday_ok = False
        # leader score
        leader_score = 0
        if ret_20d > 0.15:
            leader_score += 1
        if ret_60d > 0.30:
            leader_score += 1
        if money_score > 1.20:
            leader_score += 1
        if cond_rs:
            leader_score += 1
        if cond_obv:
            leader_score += 1
        if symbol in top_week:
            leader_score += 1
        if symbol in top_month:
            leader_score += 1
        if intraday_ok:
            leader_score += 1

        # stage
        if ret_20d < 0.10 and tight_base:
            stage = "B1-TÍCH LŨY"
        elif ret_20d >= 0.10 and ret_20d < 0.25 and leader_score >= 3:
            stage = "B2-ĐANG VÀO SÓNG"
        elif ret_20d >= 0.25 and leader_score >= 4 and not too_extended:
            stage = "B3-LEADER"
        elif too_extended:
            stage = "B3-QUÁ XA"
        else:
            stage = "NONE"
        # status
        # status (chuẩn hệ 4 trạng thái)
    if buy_code == "B2":
        status = "ƯU TIÊN MUA"
    
    elif buy_code == "B3":
        status = "ƯU TIÊN MUA"
    
    elif buy_code == "RE":
        status = "THEO DÕI"
    
    elif buy_code == "ER":
        status = "THEO DÕI ĐẢO CHIỀU"
    
    elif leader_score >= 4 and cond_price and cond_obv:
        status = "THEO DÕI"
    
    else:
    status = "LOẠI"
        # chicken state
    if stage == "B1-TÍCH LŨY":
            chicken = "🐣 Gà con"
    elif stage == "B2-ĐANG VÀO SÓNG":
            chicken = "🐥 Gà chạy"
    elif stage == "B3-LEADER":
            chicken = "🐔 Gà chiến"
    elif stage == "B3-QUÁ XA":
            chicken = "⚠️ Gà bay cao"
    else:
            chicken = "❌"

               # action
                # action
        if market_score < 8:
            if status == "THEO DÕI ĐẢO CHIỀU":
                action = "⏳ THEO DÕI ĐẢO CHIỀU"
            else:
                action = "Đứng ngoài"
        else:
            if buy_code == "B2":
                action = "👉 MUA PULL"
            elif buy_code == "B3":
                action = "👉 MUA BREAK"
            elif buy_code == "RE":
                action = "👀 THEO DÕI RECLAIM"
            elif buy_code == "ER":
                action = "🌱 MUA THĂM DÒ"
            elif status == "THEO DÕI":
                action = "👀 THEO DÕI"
            else:
                action = "❌ BỎ"
               buy_zone = round(ema9, 2)
            cut_loss = round(ma20, 2) if not np.isnan(ma20) else None
    
            score = leader_score + int(cond_price) + int(cond_rsi_turn)
            gold_score = score * market_score
            
            return {
                "Sector": sector_map.get(symbol, "KHÁC"),
                "Ticker": symbol,
                "Close": round(close_now, 2),
                "EMA9": round(ema9, 2),
                "MA20": round(ma20, 2) if not np.isnan(ma20) else None,
                "RSI": round(rsi, 2) if not np.isnan(rsi) else None,
                "Leader Score": leader_score,
                "Base": "✔" if tight_base else "✖",
                "Cạn cung": "✔" if vol_dry else "✖",
                "Break": "✔" if break_strong else "✖",
                "Top tuần": "✔" if symbol in top_week else "✖",
                "Top tháng": "✔" if symbol in top_month else "✖",
                "Intraday": "✔" if intraday_ok else "✖",
                "Money+": "✔" if money_score > 1.2 else "✖",
                "Ret 20D %": round(ret_20d * 100, 1),
                "Ret 60D %": round(ret_60d * 100, 1),
                "Stage": stage,
                "Trạng thái gà": chicken,
                "Hành động": action,
                "Điểm mua": buy_zone,
                "Cutloss": cut_loss,
                "Score": score,
                "Gold Score": gold_score,
                "Status": status,
                "Buy Code": buy_code if buy_code else "",
                "Buy Signal": buy_note,
                "Can Buy": "MUA" if buy_code in ["B2", "B3"] and market_score >= 8 else "",
                }
   except Exception:
            return None

# =========================
# ALERT STATE
# =========================
if "prev_results" not in st.session_state:
    st.session_state["prev_results"] = {}

def build_alerts(current_df: pd.DataFrame):
    alerts = []
    prev_map = st.session_state["prev_results"]
   
    for _, row in current_df.iterrows():
        ticker = row["Ticker"]
        current_status = row["Status"]
        current_stage = row["Stage"]
        current_break = row["Break"]

        old = prev_map.get(ticker)
        if old is not None:
            if old.get("Break") == "✖" and current_break == "✔":
                alerts.append(f"🚀 {ticker} vừa BREAK mạnh")
            if old.get("Stage") != "B2-ĐANG VÀO SÓNG" and current_stage == "B2-ĐANG VÀO SÓNG":
                alerts.append(f"🐥 {ticker} vừa vào B2")
            if old.get("Status") == "ƯU TIÊN MUA" and current_status != "ƯU TIÊN MUA":
                alerts.append(f"⚠️ {ticker} gãy khỏi nhóm ƯU TIÊN MUA")

        prev_map[ticker] = {
            "Status": current_status,
            "Stage": current_stage,
            "Break": current_break,
        }

    st.session_state["prev_results"] = prev_map
    return alerts

# =========================
# RUN
# =========================
run_scan = st.button("🚀 Quét V15")

if run_scan:
    results = []
    progress = st.progress(0)

    for i, symbol in enumerate(watchlist or []):
        row = analyze_stock(symbol)
        if row:
            results.append(row)
        total = len(watchlist) if watchlist else 1
        progress.progress((i + 1) / total)

    if not results:
        st.warning("Không có dữ liệu.")
        st.stop()

    df_res = pd.DataFrame(results)
    cols = ["Gold Score", "Leader Score", "Score", "Ret 20D %"]
    cols = [c for c in cols if c in df_res.columns]

    df_res = df_res.sort_values(by=cols, ascending=False)
    alerts = build_alerts(df_res)
    buy_now = df_res[df_res["Can Buy"] == "MUA"]

    if not buy_now.empty:
        st.subheader("🚀 TÍN HIỆU MUA REALTIME")
        st.dataframe(
          buy_now[["Ticker", "Buy Code", "Buy Signal"]],
           use_container_width=True
      )
    if alerts:
        st.subheader("🔔 Cảnh báo realtime")
        for msg in alerts:
            st.warning(msg)
    else:
        st.info("Chưa có tín hiệu mới so với lần quét trước.")

    display_cols = [
        "Buy Code",
        "Buy Signal",
        "Can Buy",
        "Sector", "Ticker", "Close", "EMA9", "MA20", "RSI",
        "Leader Score", "Base", "Cạn cung", "Break",
        "Top tuần", "Top tháng", "Intraday", "Money+",
        "Ret 20D %", "Ret 60D %",
        "Stage", "Trạng thái gà", "Hành động",
        "Điểm mua", "Cutloss", "Score", "Gold Score", "Status"
    ]

    st.subheader("📊 Kết quả tổng hợp")
    st.dataframe(df_res[display_cols], use_container_width=True)

    st.subheader("🔥 Nhóm ƯU TIÊN MUA")
    st.dataframe(
        df_res[df_res["Status"] == "ƯU TIÊN MUA"][display_cols].head(top_n),
        use_container_width=True
    )

    st.subheader("👀 Nhóm THEO DÕI")
    st.dataframe(
        df_res[df_res["Status"] == "THEO DÕI"][display_cols],
        use_container_width=True
    )

    st.subheader("🌱 Nhóm EARLY REVERSAL")
    st.dataframe(
        df_res[df_res["Status"] == "EARLY REVERSAL"][display_cols],
        use_container_width=True
    )

    st.subheader("❌ LOẠI")
    st.dataframe(
        df_res[df_res["Status"] == "LOẠI"][display_cols],
        use_container_width=True
    )

else:
    st.info("Bấm 'Quét V15' để chạy scanner.")
