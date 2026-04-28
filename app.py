def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)
    if len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    rsi_ = to_float(last["rsi14"])
    rsi_slope_ = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    breakout_ref = to_float(df["high"].iloc[-21:-1].max())

    # =========================
    # DIST EMA9
    # =========================
    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    # =========================
    # SCORE GỐC
    # =========================
    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)

    total_score = E + R + O

    # =========================
    # 🌸 NỞ HOA
    # =========================
    no_hoa = (
        pd.notna(price) and pd.notna(ema9_) and pd.notna(ma20_) and
        price > ema9_ > ma20_ and
        pd.notna(rsi_) and rsi_ > 55 and
        pd.notna(rsi_slope_) and rsi_slope_ >= 0 and
        pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_
    )

    # =========================
    # BONUS DIST (CHÌA KHÓA)
    # =========================
    bonus_dist = 0

    if pd.notna(dist_from_ema9):
        if 4 <= dist_from_ema9 <= 7:
            bonus_dist = 1
        elif 3 <= dist_from_ema9 < 4:
            bonus_dist = 0.5
        elif 7 < dist_from_ema9 <= 8:
            bonus_dist = 0.5

    total_score = total_score + bonus_dist

    # =========================
    # PULL + WARNING
    # =========================
    pull_label = classify_pull_label(
        dist_from_ema9,
        rsi_,
        rsi_slope_,
        obv_,
        obv_ema9_,
    )

    warning = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label)

    # =========================
    # GROUP
    # =========================
    row_temp = {
        "price": price,
        "ema9": ema9_,
        "ma20": ma20_,
        "volume": vol_,
        "vol_ma20": vol_ma20_,
        "breakout_ref": breakout_ref,
        "total_score": total_score,
        "E": E,
        "R": R,
        "O": O,
        "dist_from_ema9_pct": dist_from_ema9,
        "pull_label": pull_label
    }

    group = classify_group(row_temp)
    status = build_status(total_score, warning, group)

    obv_status = "🟢" if obv_ >= obv_ema9_ else "🔴"

    return {
        "symbol": symbol,
        "price": round(price, 0) if pd.notna(price) else np.nan,
        "ema9": round(ema9_, 2),
        "ma20": round(ma20_, 2),
        "rsi14": round(rsi_, 2),
        "rsi_slope": round(rsi_slope_, 2),
        "obv": round(obv_, 0),
        "obv_ema9": round(obv_ema9_, 0),
        "obv_status": obv_status,
        "volume": round(vol_, 0),
        "vol_ma20": round(vol_ma20_, 0),
        "breakout_ref": round(breakout_ref, 2),
        "dist_from_ema9_pct": round(dist_from_ema9, 2),
        "pull_label": pull_label,
        "E": E,
        "R": R,
        "O": O,
        "total_score": total_score,
        "group": group,
        "warning": warning,
        "status": status,
        "no_hoa": no_hoa
    }
