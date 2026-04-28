# =====================================================
# BUY RECOMMENDATION - V25
# =====================================================
def buy_recommendation(r, mk):
    price = float(r["price"])
    ema9 = float(r["ema9"])
    score = int(r["score13"])
    rsi = float(r["rsi14"])
    dist = float(r["dist_ema9_pct"])
    group = str(r["group"])
    warn = str(r["warning"])
    obv_ok = r["obv_status"] == "🟢"

    if mk < 6:
        return "🔴", "KHÔNG MUA", "-", "0%", "Market yếu"

    if "OBV gãy" in warn or "Giá dưới EMA9" in warn:
        return "🔴", "KHÔNG MUA", "-", "0%", "Trục tiền/giá xấu"

    if group == "PULL ĐẸP":
        nav = "15-20%" if mk >= 8 else "5-10%"
        return "🟢", "MUA PULL ĐẸP", f"{round(ema9)} - {round(ema9*1.01)}", nav, "Pull sát EMA9, OBV còn xanh"

    if group == "PULL VỪA":
        nav = "10-15%" if mk >= 8 else "5-10%"
        return "🟡", "MUA THĂM DÒ PULL", f"{round(ema9*0.99)} - {round(ema9*1.01)}", nav, "Pull vừa, chưa phải điểm đẹp nhất"

    if group == "MUA EARLY" and score >= 6 and rsi >= 50 and obv_ok and abs(dist) <= 2:
        return "🟡", "TEST EARLY", f"{round(price*0.99)} - {round(price*1.01)}", "5-10%", "Early sạch, test nhỏ"

    if group == "MUA BREAK":
        nav = "15-20%" if mk >= 8 else "5-10%"
        return "🟢", "MUA BREAK", f"{round(price)} - {round(price*1.01)}", nav, "Break xác nhận"

    if group == "CP MẠNH":
        if dist > 4:
            return "🟡", "CHỜ PULL, KHÔNG ĐUỔI", f"Canh về {round(ema9)} - {round(ema9*1.02)}", "0%", "CP mạnh nhưng đã xa EMA9"
        return "🟢", "MUA NHỎ / CANH ADD", f"{round(price*0.99)} - {round(price)}", "5-10%", "CP mạnh, chưa quá xa EMA9"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"
