"""
leader_memory.py
Mr.BOT PRO V4.0

Leader Memory Engine
Sprint 1

Chức năng:
- Tự tạo leader_memory.csv nếu chưa tồn tại
- Đọc Leader Memory
- Ghi Leader Memory
"""

from pathlib import Path
import pandas as pd

# ==========================================================
# FILE
# ==========================================================

MEMORY_FILE = Path("leader_memory.csv")


# ==========================================================
# CREATE
# ==========================================================

def create_empty_memory():

    columns = [
        "symbol",
        "first_seen",
        "last_seen",
    ]

    df = pd.DataFrame(columns=columns)

    df.to_csv(
        MEMORY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return df


# ==========================================================
# LOAD
# ==========================================================

def load_memory():

    if not MEMORY_FILE.exists():
        return create_empty_memory()

    return pd.read_csv(MEMORY_FILE)


# ==========================================================
# SAVE
# ==========================================================

def save_memory(df):

    df.to_csv(
        MEMORY_FILE,
        index=False,
        encoding="utf-8-sig",
    )


# ==========================================================
# UPDATE
# ==========================================================
from datetime import datetime


def update_memory(df_today):

    print(">>> UPDATE MEMORY CALLED")

    if df_today is None or len(df_today) == 0:
        return load_memory()

    memory = load_memory()

    today = datetime.now().strftime("%Y-%m-%d")

    # tên cột mã cổ phiếu
    symbol_col = None

    for c in ["symbol", "Symbol", "ticker", "Ticker", "Mã", "ma"]:
        if c in df_today.columns:
            symbol_col = c
            break

    if symbol_col is None:
        print("LeaderMemory: Không tìm thấy cột Symbol")
        return memory

    # ======================================================
    # thêm cổ phiếu mới
    # ======================================================

    for symbol in df_today[symbol_col].dropna().unique():

        symbol = str(symbol).strip()

        if symbol == "":
            continue

        if symbol not in memory["symbol"].values:

            memory.loc[len(memory)] = {
                "symbol": symbol,
                "first_seen": today,
                "last_seen": today,
            }

        else:

            idx = memory.index[memory["symbol"] == symbol][0]
            memory.loc[idx, "last_seen"] = today

    memory = memory.sort_values("symbol").reset_index(drop=True)

    save_memory(memory)

    print(f">>> Leader Memory: {len(memory)} symbols")

    return memory
