"""
leader_memory.py
Mr.Bot Pro V4.0

Leader Memory Engine
Version : 1.0

Chức năng:
- Tự tạo leader_memory.csv nếu chưa tồn tại
- Đọc Leader Memory
- Ghi Leader Memory
- Chuẩn bị cho các phiên bản sau
"""

from pathlib import Path
import pandas as pd


# ==========================================================
# CẤU HÌNH
# ==========================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

MEMORY_FILE = DATA_DIR / "leader_memory.csv"


# ==========================================================
# KHỞI TẠO
# ==========================================================

def create_empty_memory():
    """
    Tạo file Leader Memory rỗng nếu chưa tồn tại.
    """

    columns = [
        "symbol",
        "first_seen",
        "last_seen"
    ]

    df = pd.DataFrame(columns=columns)
    df.to_csv(MEMORY_FILE, index=False, encoding="utf-8-sig")

    return df


# ==========================================================
# LOAD
# ==========================================================

def load_memory():
    """
    Đọc Leader Memory.
    Nếu chưa có sẽ tự tạo.
    """

    if not MEMORY_FILE.exists():
        return create_empty_memory()

    return pd.read_csv(MEMORY_FILE)


# ==========================================================
# SAVE
# ==========================================================

def save_memory(df):
    """
    Lưu Leader Memory.
    """

    df.to_csv(
        MEMORY_FILE,
        index=False,
        encoding="utf-8-sig"
    )


# ==========================================================
# UPDATE
# ==========================================================

def update_memory(df_today):
     print(">>> UPDATE MEMORY CALLED")
    """
    Placeholder.
    Sprint 1 chưa xử lý.

    Sprint 2 sẽ:
        - cập nhật mã mới
        - cập nhật last_seen
        - thêm first_seen
    """

    memory = load_memory()

    # Chưa làm ở Sprint 1

    save_memory(memory)

    return memory
