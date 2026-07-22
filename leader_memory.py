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

def update_memory(df_today):

    print(">>> UPDATE MEMORY CALLED")

    memory = load_memory()

    save_memory(memory)

    return memory
