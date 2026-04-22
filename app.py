import pandas as pd
import numpy as np
import yfinance as yf
import time

# ========================
# WATCHLIST (GIỮ NGUYÊN)
# ========================
WATCHLIST = [
"VCB","BID","CTG","TCB","VPB","MBB","ACB","STB","HDB","TPB","VIB","LPB","MSB","EIB",
"SSI","VND","HCM","SHS","VIX","BSI","FTS",
"HPG","HSG","NKG",
"VHM","VIC","VRE","DXG","DIG","CEO","TCH",
"GAS","PVS","PVD","BSR","PLX",
"GMD","VSC","HAH","VTO","VOS",
"MWG","FRT","DGW","PET","MSN",
"FPT","CTR","VTP",
"DGC","DCM","DPM","LAS","BFC"
]

# ========================
# LOAD DATA (FIX LỖI)
# ========================
def load_data(symbol):
    try:
        df = yf.download(symbol + ".VN", period="6mo", interval="1d", progress=False)

        # 🔥 FIX LỖI MULTI COLUMN (QUAN TRỌNG)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is None or len(df) < 50:
            return None

        return df

    except:
        return None

# ========================
# INDICATORS (GIỮ NGUYÊN 18.4)
# ========================
def calc_indicators(df):
    df["ema9"] = df["Close"].ewm(span=9).mean()
    df["ma20"] = df["Close"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi_ema9"] = df["rsi"].ewm(span=9).mean()

    df["obv"] = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
    df["obv_ema9"] = df["obv"].ewm(span=9).mean()

    return df

# ========================
# SCORE (GIỮ NGUYÊN)
# ========================
def score_row(row):
    E = 0
    if row["Close"] > row["ema9"]: E += 1
    if row["ema9"] > row["ma20"]: E += 1

    R = 0
    if row["rsi"] > 55: R += 1
    if row["rsi"] > row["rsi_ema9"]: R += 1

    O = 0
    if row["obv"] > row["obv_ema9"]: O += 2

    total = E + R + O
    return E, R, O, total

# ========================
# CLASSIFY (GIỮ NGUYÊN CORE)
# ========================
def classify(E, R, O, total):
    if total >= 5 and O >= 2 and E >= 1:
        return "CP_MẠNH"
    elif total >= 4:
        return "PULL_ĐẸP"
    elif total >= 3:
        return "PULL_VỪA"
    else:
        return "THEO_DÕI"

# ========================
# MAIN SCAN
# ========================
data = []

print("🚀 SCANNING...")

for symbol in WATCHLIST:
    df = load_data(symbol)

    if df is None:
        print(f"❌ {symbol}")
        continue

    df = calc_indicators(df)
    last = df.iloc[-1]

    # đảm bảo là số (tránh lỗi so sánh)
    last = last.astype(float)

    E, R, O, total = score_row(last)
    group = classify(E, R, O, total)

    data.append({
        "symbol": symbol,
        "price": round(last["Close"],2),
        "E": E,
        "R": R,
        "O": O,
        "score": total,
        "group": group,
        "rsi": round(last["rsi"],1),
        "ema9": round(last["ema9"],2),
        "ma20": round(last["ma20"],2)
    })

    print(f"✔ {symbol} | {group} | {total}")

    time.sleep(0.2)

# ========================
# DATAFRAME
# ========================
df = pd.DataFrame(data)

# ========================
# MARKET (CHỈ CHỈNH NHẸ)
# ========================
market = round(df["score"].mean() * 1.6, 1)

print("\n📊 MARKET:", market)

# ========================
# SORT (GIỮ NGUYÊN TƯ DUY)
# ========================
rank_map = {
    "CP_MẠNH": 0,
    "PULL_ĐẸP": 1,
    "PULL_VỪA": 2,
    "THEO_DÕI": 3
}

df["rank"] = df["group"].map(rank_map)

df = df.sort_values(
    by=["rank","score","O","E","R"],
    ascending=[True, False, False, False, False]
)

# ========================
# SAVE
# ========================
df.to_csv("data_full.csv", index=False)

print("✅ DONE → data_full.csv")
