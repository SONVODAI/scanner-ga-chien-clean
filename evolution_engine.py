import pandas as pd
import numpy as np
from datetime import datetime


GROUP_RANK = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,
    "PULL VỪA": 3,
    "PULL ĐẸP": 4,
    "MUA BREAK": 5,
    "CP MẠNH": 6,
    "GÀ TĂNG TỐC": 7,
}


def save_evolution_history(scan_df):

    today_str = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []

    # VNINDEX
    vnindex_group = "THEO DÕI"

    rows.append({
        "date": today_str,
        "time": current_time,
        "symbol": "VNINDEX",
        "group": vnindex_group,
        "rank": GROUP_RANK.get(vnindex_group, 0)
    })

    # STOCKS
    for _, r in scan_df.iterrows():

        group = r.get("group", "")

        if pd.notna(group) and group != "":

            rows.append({
                "date": today_str,
                "time": current_time,
                "symbol": r["symbol"],
                "group": group,
                "rank": GROUP_RANK.get(group, 0)
            })

    new_df = pd.DataFrame(rows)

    FILE_NAME = "group_evolution_history.csv"

    try:
        old_df = pd.read_csv(FILE_NAME)

        full_df = pd.concat(
            [old_df, new_df],
            ignore_index=True
        )

        full_df = full_df.drop_duplicates(
            subset=["date", "symbol"],
            keep="last"
        )

    except Exception:
        full_df = new_df.copy()

    latest_days = sorted(
        full_df["date"].unique()
    )[-15:]

    full_df = full_df[
        full_df["date"].isin(latest_days)
    ]

    full_df.to_csv(FILE_NAME, index=False)

    def build_evolution_leaders(full_df):

    if full_df.empty:
        return pd.DataFrame()

    pivot = full_df.pivot_table(
        index="symbol",
        columns="date",
        values="rank",
        aggfunc="first"
    )

    pivot = pivot.sort_index(axis=1)

    leaders = []

    for symbol in pivot.index:

        row = pivot.loc[symbol].dropna()

        if len(row) < 3:
            continue

        ranks = row.values.tolist()

        recent = ranks[-5:]

        speed = recent[-1] - recent[0]

        up_days = 0

        for i in range(1, len(recent)):

            if recent[i] > recent[i - 1]:
                up_days += 1

        current_rank = recent[-1]

        if speed >= 2 or up_days >= 2:

            leaders.append({
                "symbol": symbol,
                "speed": speed,
                "up_days": up_days,
                "current_rank": current_rank
            })

    if not leaders:
        return pd.DataFrame()

    out = pd.DataFrame(leaders)

    out = out.sort_values(
        by=["speed", "current_rank"],
        ascending=False
    )

    return out

    return full_df, latest_days
