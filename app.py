import pandas as pd
import numpy as np
import time
from vnstock import Vnstock

# ========================
# WATCHLIST FULL
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
# INDICATOR (CHUẨN 5 TRỤC)
# ========================

def calc_indicators(df):
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ma20"] = df["close"].rolling(20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    df["rsi_ema"] = df["rsi"].ewm(span=9).mean()

    df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
    df["obv_ema"] = df["obv"].ewm(span=9).mean()

    return df

# ========================
# CHẤM ĐIỂM CHUẨN
# ========================

def score_stock(row):
    score = 0

    # TRỤC GIÁ
    if row["close"] > row["ema9"]: score += 1
    if row["ema9"] > row["ma20"]: score += 1

    # TRỤC RSI
    if row["rsi"] > 55: score += 1
    if row["rsi"] > row["rsi_ema"]: score += 1

    # TRỤC OBV
    if row["obv"] > row["obv_ema"]: score += 2

    return score

# ========================
# PHÂN LOẠI THỰC CHIẾN
# ========================

def classify(row):
    if row["score"] >= 5 and row["rsi"] > 60:
        return "CP_MẠNH"
    elif row["score"] >= 4:
        return "MUA_BREAK"
    elif row["score"] >= 3:
        return "PULL_ĐẸP"
    elif row["score"] >= 2:
        return "PULL_VỪA"
    else:
        return "THEO_DÕI"

# ========================
# LOAD DATA (CÓ RETRY)
# ========================

def load_stock(symbol):
    for i in range(3):
        try:
            stock = Vnstock().stock(symbol=symbol, source="VCI")
            df = stock.quote.history(period="1y", interval="1D")
            return df
        except:
            time.sleep(1)
    return None

# ========================
# MAIN
# ========================

data = []

print("🚀 Bắt đầu scan...")

for symbol in WATCHLIST:
    df = load_stock(symbol)

    if df is None or len(df) < 50:
        print(f"❌ bỏ {symbol}")
        continue

    df = calc_indicators(df)
    last = df.iloc[-1]

    row = {
        "symbol": symbol,
        "price": last["close"],
        "ema9": last["ema9"],
        "ma20": last["ma20"],
        "rsi": last["rsi"],
        "rsi_ema": last["rsi_ema"],
        "obv": last["obv"],
        "obv_ema": last["obv_ema"],
    }

    row["score"] = score_stock(row)
    row["group"] = classify(row)

    data.append(row)

    print(f"✔ {symbol} | score {row['score']}")

    time.sleep(0.3)

# ========================
# DATAFRAME
# ========================

df_all = pd.DataFrame(data)

# ========================
# MARKET CHUẨN
# ========================

market_score = round(df_all["score"].mean() * 1.8, 1)

print("\n📊 MARKET:", market_score)

# ========================
# SORT
# ========================

df_all = df_all.sort_values("score", ascending=False)

# ========================
# SAVE
# ========================

df_all.to_csv("data_full.csv", index=False)

print("✅ DONE → data_full.csv")
