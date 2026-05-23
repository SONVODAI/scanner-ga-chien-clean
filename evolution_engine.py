import pandas as pd
import numpy as np
from datetime import datetime
def save_evolution_history(scan_df):
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

    today_df = pd.DataFrame(rows)

    today_df = today_df.drop_duplicates(
        subset=["date", "symbol"],
        keep="last"
    )

    if os.path.exists(EVOLUTION_FILE):

        old_df = pd.read_csv(EVOLUTION_FILE)

        full_df = pd.concat(
            [old_df, today_df],
            ignore_index=True
        )

    else:

        full_df = today_df.copy()

    full_df = full_df.drop_duplicates(
        subset=["date", "symbol"],
        keep="last"
    )

    all_days = sorted(
        full_df["date"].dropna().unique()
    )

    latest_days = all_days[-MAX_EVOLUTION_DAYS:]

    full_df = full_df[
        full_df["date"].isin(latest_days)
    ].copy()

    full_df = full_df.sort_values(
        by=["date", "symbol"]
    ).reset_index(drop=True)

    full_df.to_csv(
        EVOLUTION_FILE,
        index=False
    )

    backup_name = f"backup_evolution_{today_str}.csv"

    full_df.to_csv(
        backup_name,
        index=False
    )

    return full_df, latest_days


# =====================================================
# BUILD EVOLUTION LEADERS
# =====================================================

def build_evolution_leaders(full_df, scan_df):

    if full_df.empty:
        return pd.DataFrame()

    pivot = full_df.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first"
    )

    pivot = pivot.sort_index(axis=1)

    leaders = []

    for symbol in pivot.index:

        row = pivot.loc[symbol].dropna()

        if len(row) < 1:
            continue

        groups = row.values.tolist()

        ranks = [
            GROUP_RANK.get(g, 0)
            for g in groups
        ]

        last_groups = groups[-5:]
        last_ranks = ranks[-5:]

        speed = last_ranks[-1] - last_ranks[0]

        up_days = 0
        down_days = 0
        flat_days = 0

        for i in range(1, len(last_ranks)):

            if last_ranks[i] > last_ranks[i - 1]:
                up_days += 1

            elif last_ranks[i] < last_ranks[i - 1]:
                down_days += 1

            else:
                flat_days += 1

        current_rank = last_ranks[-1]
        current_group = last_groups[-1]

        # =========================
        # ICON / TREND
        # =========================

        if speed >= 3 or up_days >= 3:
            evo_icon = "🔥↑↑"
            evo_trend = "TĂNG TỐC"

        elif speed > 0:
            evo_icon = "🟢↑"
            evo_trend = "MẠNH LÊN"

        elif speed < -2 or down_days >= 3:
            evo_icon = "🚨↓↓"
            evo_trend = "YẾU NHANH"

        elif speed < 0:
            evo_icon = "⚠️↓"
            evo_trend = "YẾU ĐI"

        elif current_rank >= 5:
            evo_icon = "🟢→"
            evo_trend = "ĐI NGANG KHỎE"

        else:
            evo_icon = "→"
            evo_trend = "ĐI NGANG"

        evolution_text = " ➜ ".join(last_groups)

        # =========================
        # VOLUME STATUS
        # =========================

        vol_status = "⚪ N/A"
        # =========================
        # EVOLUTION QUALITY SCORE
        # =========================

        evo_score = 0

        # tốc độ tiến hóa
        if speed >= 3:
            evo_score += 2

        elif speed > 0:
            evo_score += 1

        # tăng liên tục
        if up_days >= 3:
            evo_score += 2

        elif up_days >= 2:
            evo_score += 1

        # không bị suy yếu
        if down_days == 0:
            evo_score += 2

        # giữ nhóm mạnh
        if current_rank >= 6:
            evo_score += 2

        elif current_rank >= 5:
            evo_score += 1

        # đi ngang khỏe
        if flat_days >= 2 and current_rank >= 5:
            evo_score += 1
        sub_scan = scan_df[
            scan_df["symbol"] == symbol
        ]

        if not sub_scan.empty:

            scan_row = sub_scan.iloc[0]

            vol_now = scan_row.get("volume", np.nan)
            vol_ma20 = scan_row.get("vol_ma20", np.nan)

            if (
                pd.notna(vol_now)
                and pd.notna(vol_ma20)
                and vol_ma20 > 0
            ):

                ratio = vol_now / vol_ma20

                if ratio >= 1.5:
                    vol_status = "🔥 VOL BREAK"

                elif ratio >= 1.0:
                    vol_status = "🟢 VOL OK"

                elif ratio >= 0.7:
                    vol_status = "🟡 VOL TB"

                else:
                    vol_status = "🔴 VOL YẾU"
        # =========================
        # EVOLUTION TYPE
        # =========================

        if evo_score >= 8:

            evo_type = "🚀 SIÊU TIẾN HÓA"

        elif evo_score >= 6:

            evo_type = "🔥 TĂNG TỐC"

        elif evo_score >= 4:

            evo_type = "🧱 TÍCH LŨY ĐẸP"

        elif evo_score >= 2:

            evo_type = "🟡 THEO DÕI"

        else:

            evo_type = "⚠️ NHIỄU"
        leaders.append({
            "symbol": symbol,
            "evo_icon": evo_icon,
            "evo_trend": evo_trend,
            "evolution": evolution_text,
            "speed": speed,
            
            "evo_score": evo_score,
            "evo_type": evo_type,
            
            "up_days": up_days,
            "down_days": down_days,
            "flat_days": flat_days,
            "volume_status": vol_status,
            "current_group": current_group,
            "current_rank": current_rank
        })

    if not leaders:
        return pd.DataFrame()

    out = pd.DataFrame(leaders)

    out = out.sort_values(
        by=["speed", "current_rank", "up_days"],
        ascending=False
    ).reset_index(drop=True)

    return out


# =====================================================
# RUN EVOLUTION ENGINE
# =====================================================

# =====================================================
# DISPLAY EVOLUTION LEADERS
# =====================================================

