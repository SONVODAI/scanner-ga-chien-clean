# =========================================================
# MR.BOT V22
# PATTERN MEMORY
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def today_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


# =========================================================
# SAVE PATTERN HISTORY
# =========================================================

def save_pattern_history(
    brain,
    scan_df,
    market_real,
    market_forecast,
):
    """
    Lưu toàn bộ pattern của phiên.

    Không học.
    Không phân tích.

    Chỉ lưu dữ liệu chất lượng cao
    để Brain học sau này.
    """

    if brain is None:
        return

    if scan_df is None or scan_df.empty:
        return

    keep_cols = [
        "symbol",
        "group",
        "price",
        "total_score",
        "trend_score",
        "buy_score",
        "storm",
        "persistence",
        "evolution",
        "recent_change",
        "rsi14",
        "ema9_ma20_slope",
        "dist_from_ema9_pct",
        "obv_status",
    ]
    learn_groups = [
    "MUA EARLY",
    "PULL VỪA",
    "PULL ĐẸP",
    "CP MẠNH",
]

df = scan_df[
    scan_df["group"].isin(learn_groups)
].copy()

cols = [c for c in keep_cols if c in df.columns]
df = df[cols]
    

    df["date"] = today_str()

    df["market_real"] = market_real
    df["market_forecast"] = market_forecast

    # kết quả tương lai
    df["t1_return"] = None
    df["t3_return"] = None
    df["t5_return"] = None

    df["t1_win"] = None
    df["t3_win"] = None
    df["t5_win"] = None
    print("PATTERN DF ROWS =", len(df))
    print(df.head())
    saved, status = brain.remember(
    table="pattern_history",
    data=df,
    key=["date", "symbol"],
    keep_days=720,
    sort_by=["date", "symbol"],
    sync_github=True,
)
    print("PATTERN STATUS =", status)
    print("PATTERN SAVED =", len(saved))
