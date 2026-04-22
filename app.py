import pandas as pd
import numpy as np
from vnstock import Vnstock
import time

# ========================
# WATCHLIST FULL CỦA ANH
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
# INDICATOR
# ========================

def calc_indicators(df):
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ma20"] = df["close"].rolling(20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
    df["obv_ema"] = df["obv"].ewm(span=9).mean()

    return df

# ========================
# CHẤM ĐIỂM (GIỐNG ANH)
# ========================

def score_stock(row):
    score = 0

    # Giá
    if row["close"] > row["ema9"]: score += 1
    if row["ema9"] > row["ma20"]: score += 1

    # RSI
    if row["rsi"] > 55: score += 1

    # OBV
    if row["obv"] > row["obv_ema"]: score += 1

    return score

# ========================
# PHÂN LOẠI (NỚI LỎNG NHƯ ANH MUỐN)
# ========================

def classify(row):
    if row["score"] >= 4 and row["rsi"] > 60:
        return "CP_MẠNH"
    elif row["score"] >= 3:
        return "PULL_ĐẸP"
    elif row["score"] >= 2:
        return "PULL_VỪA"
    else:
        return "THEO_DÕI"

# ========================
# MAIN SCAN
# ========================

data_all = []

print("🚀 Bắt đầu scan...")

for symbol in WATCHLIST:
    try:
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(period="6mo", interval="1D")

        df = calc_indicators(df)
        last = df.iloc[-1]

        row = {
            "symbol": symbol,
            "price": last["close"],
            "ema9": last["ema9"],
            "ma20": last["ma20"],
            "rsi": last["rsi"],
            "obv": last["obv"],
            "obv_ema": last["obv_ema"],
        }

        row["score"] = score_stock(row)
        row["group"] = classify(row)

        data_all.append(row)

        print(f"✔ {symbol}")

        time.sleep(0.5)

    except:
        print(f"❌ lỗi {symbol}")

df_all = pd.DataFrame(data_all)

# ========================
# MARKET SCORE (GIỐNG ANH CHẤM)
# ========================

market_score = round(df_all["score"].mean() * 2, 1)

print("\n📊 MARKET SCORE:", market_score)

# ========================
# SAVE FILE
# ========================

df_all.to_csv("data_full.csv", index=False)

print("✅ DONE → data_full.csv")
