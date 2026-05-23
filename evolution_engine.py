import pandas as pd
import numpy as np
from datetime import datetime


GROUP_RANK = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,f
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
    try:
        github_token = st.secrets["GITHUB_TOKEN"]

    repo_owner = "SONVODAI"
    repo_name = "scanner-ga-chien-clean"
    file_path = "group_evolution_history.csv"

    with open(FILE_NAME, "r", encoding="utf-8") as f:
        content = f.read()

    encoded_content = base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")

    # lấy SHA file cũ
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    headers = {
        "Authorization": f"token {github_token}"
    }

    response = requests.get(url, headers=headers)

    sha = None

    if response.status_code == 200:
        sha = response.json()["sha"]

    data = {
        "message": "update evolution history",
        "content": encoded_content,
        "branch": "main"
    }

    if sha:
        data["sha"] = sha

    requests.put(
        url,
        headers=headers,
        json=data
    )
except Exception as e:
    st.error(f"GitHub push error: {e}")
    full_df.to_csv(FILE_NAME, index=False)

    try:
        import requests
        import base64
        import streamlit as st

        github_token = st.secrets["GITHUB_TOKEN"]

        repo_owner = "SONVODAI"
        repo_name = "scanner-ga-chien-clean"
        file_path = "group_evolution_history.csv"

        with open(FILE_NAME, "r", encoding="utf-8") as f:
            content = f.read()

        encoded_content = base64.b64encode(
            content.encode("utf-8")
        ).decode("utf-8")

        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        headers = {
            "Authorization": f"token {github_token}"
        }

        response = requests.get(url, headers=headers)

        sha = None

        if response.status_code == 200:
            sha = response.json()["sha"]

        data = {
            "message": "update evolution history",
            "content": encoded_content,
            "branch": "main"
        }

        if sha:
            data["sha"] = sha

        requests.put(
            url,
            headers=headers,
            json=data
        )

    except Exception as e:
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

            score = 0

            for i in range(1, len(groups)):

                prev_rank = GROUP_RANK.get(groups[i - 1], 0)
                curr_rank = GROUP_RANK.get(groups[i], 0)

                if curr_rank > prev_rank:
                    score += 1

            if score >= 2:

                leaders.append({
                    "symbol": symbol,
                    "evolution_score": score,
                    "current_group": groups[-1]
                })

        leaders_df = pd.DataFrame(leaders)

        if not leaders_df.empty:
            leaders_df = leaders_df.sort_values(
                by="evolution_score",
                ascending=False
            )

        return leaders_df

    except Exception:
        return pd.DataFrame()

    
