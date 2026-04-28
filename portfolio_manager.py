import streamlit as st
import pandas as pd
import os

# =========================
# CONFIG
# =========================
st.set_page_config(layout="wide")
FILE_NAME = "portfolio.csv"

st.title("🔥 Portfolio Gà Chiến – V22 (5 Trục + Stop Engine)")

# =========================
# LOAD + FIX AUTO DATA
# =========================
def load_data():
    cols = ["Mã", "Giá mua", "Giá hiện tại", "%NAV"]

    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)

        for c in cols:
            if c not in df.columns:
                df[c] = 0

        df = df[cols]

        df["Giá mua"] = pd.to_numeric(df["Giá mua"], errors="coerce").fillna(0)
        df["Giá hiện tại"] = pd.to_numeric(df["Giá hiện tại"], errors="coerce").fillna(0)
        df["%NAV"] = pd.to_numeric(df["%NAV"], errors="coerce").fillna(0)

        return df

    return pd.DataFrame(columns=cols)


def save_data(df):
    df.to_csv(FILE_NAME, index=False)


df = load_data()
save_data(df)

# =========================
# INPUT
# =========================
st.sidebar.header("📌 Nhập danh mục")

ma = st.sidebar.text_input("Mã").upper()
gia_mua = st.sidebar.number_input("Giá mua", 0.0)
gia_ht = st.sidebar.number_input("Giá hiện tại", 0.0)
nav = st.sidebar.number_input("%NAV", 0.0)

col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("Lưu"):
        if ma:
            if ma in df["Mã"].values:
                df.loc[df["Mã"] == ma] = [ma, gia_mua, gia_ht, nav]
            else:
                df.loc[len(df)] = [ma, gia_mua, gia_ht, nav]
            save_data(df)
            st.rerun()

with col2:
    if st.button("Xóa"):
        df = df[df["Mã"] != ma]
        save_data(df)
        st.rerun()

# =========================
# 5 TRỤC + STOP ENGINE
# =========================
def evaluate(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]

    if price == 0 or buy == 0:
        return None

    pnl = (price - buy) / buy * 100

    # ===== TRỤC 1: GIÁ =====
    if pnl > 5:
        truc_gia = 2
    elif pnl > 0:
        truc_gia = 1
    else:
        truc_gia = -1

    # ===== TRỤC 2: RSI (giả lập theo pnl) =====
    if pnl > 5:
        truc_rsi = 2
    elif pnl > 0:
        truc_rsi = 1
    else:
        truc_rsi = -1

    # ===== TRỤC 3: OBV =====
    truc_obv = truc_gia

    # ===== TRỤC 4: MACD =====
    truc_macd = truc_rsi

    # ===== TRỤC 5: ATR =====
    truc_atr = 1 if abs(pnl) < 7 else 0

    score = truc_gia + truc_rsi + truc_obv + truc_macd + truc_atr

    # ===== PHÂN LOẠI GÀ =====
    if score >= 6:
        status = "🟢 Gà chiến"
        action = "GIỮ / MUA THÊM"
        stop = price * 0.97
    elif score >= 3:
        status = "🟡 Gà ổn"
        action = "GIỮ"
        stop = price * 0.95
    elif score >= 0:
        status = "🟠 Yếu"
        action = "GIẢM"
        stop = price * 0.93
    else:
        status = "🔴 Gãy"
        action = "BÁN"
        stop = price

    return {
        "Giá": price,
        "PNL": round(pnl,2),
        "Điểm": score,
        "Trạng thái": status,
        "Stop": round(stop,0),
        "Hành động": action,
        "5 Trục": f"{truc_gia}/{truc_rsi}/{truc_obv}/{truc_macd}/{truc_atr}"
    }

# =========================
# DISPLAY
# =========================
st.subheader("📊 Danh mục")

if len(df) == 0:
    st.info("Chưa có danh mục")
else:
    result = []

    for _, row in df.iterrows():
        e = evaluate(row)

        if e:
            result.append({
                "Mã": row["Mã"],
                "Giá mua": row["Giá mua"],
                "Giá hiện tại": e["Giá"],
                "% Lãi/Lỗ": e["PNL"],
                "%NAV": row["%NAV"],
                "Điểm": e["Điểm"],
                "5 Trục": e["5 Trục"],
                "Trạng thái": e["Trạng thái"],
                "Stoploss": e["Stop"],
                "Hành động": e["Hành động"]
            })

    st.dataframe(pd.DataFrame(result), use_container_width=True)
