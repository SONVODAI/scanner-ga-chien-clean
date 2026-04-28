import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")
FILE_NAME = "portfolio.csv"

st.title("🔥 Portfolio Gà Chiến – V23 (5 Trục Chuẩn)")

# =========================
# LOAD DATA + AUTO FIX
# =========================
def load_data():
    cols = ["Mã","Giá mua","Giá hiện tại","%NAV","RSI","OBV","MACD"]

    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)

        for c in cols:
            if c not in df.columns:
                df[c] = 0

        return df[cols]

    return pd.DataFrame(columns=cols)

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

df = load_data()
save_data(df)

# =========================
# INPUT
# =========================
st.sidebar.header("📌 Nhập dữ liệu 5 trục")

ma = st.sidebar.text_input("Mã").upper()
gia_mua = st.sidebar.number_input("Giá mua", 0.0)
gia_ht = st.sidebar.number_input("Giá hiện tại", 0.0)
nav = st.sidebar.number_input("%NAV", 0.0)

rsi = st.sidebar.number_input("RSI", 0.0)
obv = st.sidebar.selectbox("OBV", ["Tăng", "Giảm"])
macd = st.sidebar.selectbox("MACD", ["Dương", "Âm"])

col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("Lưu"):
        if ma:
            obv_val = 1 if obv=="Tăng" else -1
            macd_val = 1 if macd=="Dương" else -1

            row = [ma,gia_mua,gia_ht,nav,rsi,obv_val,macd_val]

            if ma in df["Mã"].values:
                df.loc[df["Mã"]==ma] = row
            else:
                df.loc[len(df)] = row

            save_data(df)
            st.rerun()

with col2:
    if st.button("Xóa"):
        df = df[df["Mã"]!=ma]
        save_data(df)
        st.rerun()

# =========================
# 5 TRỤC THẬT
# =========================
def evaluate(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]
    rsi = row["RSI"]
    obv = row["OBV"]
    macd = row["MACD"]

    if price==0:
        return None

    pnl = (price-buy)/buy*100

    # ===== TRỤC 1: GIÁ =====
    if pnl > 3:
        t1 = 2
    elif pnl > -2:
        t1 = 1
    else:
        t1 = -2

    # ===== TRỤC 2: RSI =====
    if rsi > 65:
        t2 = 2
    elif rsi > 55:
        t2 = 1
    else:
        t2 = -1

    # ===== TRỤC 3: OBV =====
    t3 = 2 if obv==1 else -2

    # ===== TRỤC 4: MACD =====
    t4 = 2 if macd==1 else -1

    # ===== TRỤC 5: ATR =====
    t5 = 1 if abs(pnl)<7 else 0

    score = t1+t2+t3+t4+t5

    # ===== PHÂN LOẠI =====
    if score >=7:
        status="🟢 Gà chiến"
        action="GIỮ CHẶT"
        stop=price*0.97
    elif score>=4:
        status="🔵 Gà khỏe"
        action="GIỮ"
        stop=price*0.95
    elif score>=1:
        status="🟡 Yếu dần"
        action="GIẢM"
        stop=price*0.93
    else:
        status="🔴 Gãy"
        action="BÁN"
        stop=price

    return {
        "PNL":round(pnl,2),
        "Score":score,
        "5Truc":f"{t1}/{t2}/{t3}/{t4}/{t5}",
        "Status":status,
        "Stop":round(stop,0),
        "Action":action
    }

# =========================
# DISPLAY
# =========================
st.subheader("📊 Danh mục")

if len(df)==0:
    st.info("Chưa có dữ liệu")
else:
    result=[]

    for _,row in df.iterrows():
        e = evaluate(row)

        if e:
            result.append({
                "Mã":row["Mã"],
                "Giá":row["Giá hiện tại"],
                "%Lãi":e["PNL"],
                "RSI":row["RSI"],
                "OBV":row["OBV"],
                "MACD":row["MACD"],
                "Điểm":e["Score"],
                "5 Trục":e["5Truc"],
                "Trạng thái":e["Status"],
                "Stop":e["Stop"],
                "Hành động":e["Action"]
            })

    st.dataframe(pd.DataFrame(result), use_container_width=True)
