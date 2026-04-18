# ==============================
# 🚀 V13 – GÀ CHIẾN FINAL LOGIC
# ==============================

import numpy as np

# ===== BASIC =====
latest = df.iloc[-1]

close = latest["Close"]
ema9 = latest["EMA9"]
ma20 = latest["MA20"]
rsi = latest["RSI"]
obv = latest["OBV"]
obv_ema = latest["OBV_EMA"]

# ===== CONDITIONS =====
cond_price = close > ema9 > ma20
cond_obv = obv > obv_ema
cond_slope = ema9 > df["EMA9"].iloc[-3]
cond_rsi_turn = rsi > df["RSI"].iloc[-3]
cond_rs = latest["RS"] > df["RS"].rolling(10).mean().iloc[-1]

dist_ma20 = abs(close - ma20) / ma20

# ===== PERFORMANCE =====
ret_20d = (close / df["Close"].iloc[-20]) - 1 if len(df) > 20 else 0
ret_60d = (close / df["Close"].iloc[-60]) - 1 if len(df) > 60 else 0

# ===== VOLUME =====
vol = latest["Volume"]
vol_ma = df["Volume"].rolling(20).mean().iloc[-1]
vol_dry = vol < vol_ma * 0.8
vol_break = vol > vol_ma * 1.5

# ===== MONEY FLOW =====
money_score = vol / vol_ma if vol_ma > 0 else 1

# ===== BASE =====
price_range = (df["High"].rolling(15).max().iloc[-1] - df["Low"].rolling(15).min().iloc[-1]) / close
tight_base = price_range < 0.15

# ===== BREAK =====
break_strong = close >= df["High"].rolling(20).max().iloc[-2] and vol_break

# ===== EXTENDED =====
too_extended = dist_ma20 > 0.15

# ==============================
# 🧠 LEADER SCORE (CỐT LÕI)
# ==============================
leader_score = 0

if ret_20d > 0.15:
    leader_score += 1

if ret_60d > 0.3:
    leader_score += 1

if money_score > 1.2:
    leader_score += 1

if cond_rs:
    leader_score += 1

if cond_obv:
    leader_score += 1


# ==============================
# 🧠 STAGE (CHU KỲ GÀ)
# ==============================
if ret_20d < 0.1 and tight_base:
    stage = "B1-TÍCH LŨY"

elif ret_20d >= 0.1 and ret_20d < 0.25 and leader_score >= 2:
    stage = "B2-ĐANG VÀO SÓNG"

elif ret_20d >= 0.25 and leader_score >= 3:
    stage = "B3-LEADER"

elif too_extended:
    stage = "B3-QUÁ XA"

else:
    stage = "NONE"


# ==============================
# 🧠 CLASSIFY (QUAN TRỌNG NHẤT)
# ==============================

# ❌ LOẠI
if not cond_price or not cond_obv or not cond_slope:
    status = "LOẠI"

# 🌱 EARLY (CHƯA CHẠY)
elif (
    ret_20d < 0.1
    and rsi < 55
    and tight_base
    and vol_dry
):
    status = "EARLY REVERSAL"

# 🔥 ƯU TIÊN MUA (LEADER THẬT)
elif (
    leader_score >= 3
    and rsi > 58
    and cond_price
    and cond_obv
    and cond_slope
    and (break_strong or ret_20d > 0.15)
):
    status = "ƯU TIÊN MUA"

# ⚠️ CHẶN FOMO (ĐÃ CHẠY XA)
elif ret_20d > 0.35:
    status = "THEO DÕI"

# 👀 THEO DÕI
else:
    status = "THEO DÕI"


# ==============================
# 📊 SCORE
# ==============================
score = leader_score + (1 if cond_price else 0) + (1 if cond_rsi_turn else 0)

gold_score = score * market_score


# ==============================
# OUTPUT
# ==============================
result = {
    "Close": close,
    "EMA9": ema9,
    "MA20": ma20,
    "RSI": rsi,
    "Leader Score": leader_score,
    "Stage": stage,
    "Score": score,
    "Gold Score": gold_score,
    "Status": status
}
