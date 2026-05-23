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

FILE_NAME = "group_evolution_history.csv"


def save_evolution_history(scan_df):
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []

    rows.append({
        "date": today_str,
        "time": current_time,
        "symbol": "VNINDEX",
        "group": "THEO DÕI",
        "rank": 0,
    })

    for _, r in scan_df.iterrows():
        group = r.get("group", "")
        symbol = r.get("symbol", "")

        if pd.notna(group) and group != "" and symbol != "":
            rows.append({
                "date": today_str,
                "time": current_time,
                "symbol": symbol,
                "group": group,
                "rank": GROUP_RANK.get(group, 0),
            })

    new_df = pd.DataFrame(rows)

    try:
        old_df = pd.read_csv(FILE_NAME)
        full_df = pd.concat([old_df, new_df], ignore_index=True)
    except Exception:
        full_df = new_df.copy()

    full_df["date"] = full_df["date"].astype(str)

    full_df = full_df.drop_duplicates(
        subset=["date", "symbol"],
        keep="last"
    )

    latest_days = sorted(full_df["date"].unique())[-15:]

    full_df = full_df[
        full_df["date"].isin(latest_days)
    ].copy()

    full_df.to_csv(FILE_NAME, index=False)

    try:
        import requests
        import base64
        import streamlit as st

        github_token = st.secrets["GITHUB_TOKEN"]

        repo_owner = "SONVODAI"
        repo_name = "scanner-ga-chien-clean"
        file_path = "group_evolution_history.csv"

        csv_content = full_df.to_csv(index=False)

        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json",
        }

        get_response = requests.get(url, headers=headers)

        sha = None
        if get_response.status_code == 200:
            sha = get_response.json().get("sha")

        data = {
            "message": "update evolution history",
            "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8"),
            "branch": "main",
        }

        if sha:
            data["sha"] = sha

        put_response = requests.put(
            url,
            headers=headers,
            json=data
        )

        if put_response.status_code not in [200, 201]:
            st.warning(f"GitHub push lỗi: {put_response.status_code} - {put_response.text}")

    except Exception as e:
        try:
            import streamlit as st
            st.warning(f"GitHub push error: {e}")
        except Exception:
            print("GitHub push error:", e)

    return full_df, latest_days


def build_evolution_leaders(full_df):
    if full_df.empty:
        return pd.DataFrame()

    try:
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

            if len(row) < 3:
                continue

            groups = row.values.tolist()
            ranks = [GROUP_RANK.get(g, 0) for g in groups]

            score = 0
            up_days = 0

            for i in range(1, len(ranks)):
                if ranks[i] > ranks[i - 1]:
                    score += 1
                    up_days += 1

            if score >= 2:
                leaders.append({
                    "symbol": symbol,
                    "evolution_score": score,
                    "up_days": up_days,
                    "current_group": groups[-1],
                    "evolution": " ➜ ".join(groups[-5:]),
                })

        leaders_df = pd.DataFrame(leaders)

        if not leaders_df.empty:
            leaders_df = leaders_df.sort_values(
                by=["evolution_score", "up_days"],
                ascending=False
            ).reset_index(drop=True)

        return leaders_df

    except Exception:
        return pd.DataFrame()
