# =========================================================
# MR.BOT V22 - PATTERN MEMORY
# Ghi trực tiếp pattern_history.csv
# Không phụ thuộc brain.remember()
# =========================================================

import os
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO

import pandas as pd
import requests
import streamlit as st

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

PATTERN_FILE = "pattern_history.csv"
GITHUB_REPO_OWNER = "SONVODAI"
GITHUB_REPO_NAME = "scanner-ga-chien-clean"
GITHUB_PATTERN_PATH = PATTERN_FILE


def today_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def now_time_str():
    return datetime.now(VN_TZ).strftime("%H:%M:%S")


def get_github_token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return None


def read_pattern_history() -> pd.DataFrame:
    token = get_github_token()

    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_PATTERN_PATH}"
            headers = {"Authorization": f"token {token}"}
            r = requests.get(url, headers=headers, timeout=10)

            if r.status_code == 200:
                content = r.json().get("content", "")
                if content:
                    decoded = base64.b64decode(content).decode("utf-8")
                    if decoded.strip():
                        return pd.read_csv(StringIO(decoded))
        except Exception as e:
            print("READ PATTERN GITHUB ERROR:", e)

    try:
        if os.path.exists(PATTERN_FILE) and os.path.getsize(PATTERN_FILE) > 1:
            return pd.read_csv(PATTERN_FILE)
    except Exception as e:
        print("READ PATTERN LOCAL ERROR:", e)

    return pd.DataFrame()


def write_pattern_history(df: pd.DataFrame) -> str:
    if df is None:
        return "NO_DF"

    df = df.copy()
    df.to_csv(PATTERN_FILE, index=False)

    token = get_github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        csv_content = df.to_csv(index=False)
        encoded_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_PATTERN_PATH}"
        headers = {"Authorization": f"token {token}"}

        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")

        payload = {
            "message": f"Update pattern history {today_str()} {now_time_str()}",
            "content": encoded_content,
        }

        if sha:
            payload["sha"] = sha

        put_r = requests.put(url, headers=headers, json=payload, timeout=15)

        if put_r.status_code in [200, 201]:
            return "GITHUB_OK"

        return f"GITHUB_FAIL_{put_r.status_code}: {put_r.text[:200]}"

    except Exception as e:
        return f"GITHUB_ERROR: {e}"


def save_pattern_history(
    brain,
    scan_df,
    market_real,
    market_forecast,
):
    if scan_df is None or scan_df.empty:
        print("PATTERN SKIP: scan_df empty")
        return pd.DataFrame(), "EMPTY_SCAN"

    learn_groups = [
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "CP MẠNH",
    ]

    df = scan_df[scan_df["group"].isin(learn_groups)].copy()

    if df.empty:
        print("PATTERN SKIP: no learn groups")
        return pd.DataFrame(), "EMPTY_LEARN_GROUP"

    keep_cols = [
        "symbol",
        "group",
        "price",
        "total_score",
        "E",
        "R",
        "O",
        "S",
        "RS",
        "V",
        "rsi14",
        "ema9_ma20_slope",
        "dist_from_ema9_pct",
        "obv_status",
        "volume",
        "vol_ma20",
        "green_2_confirm",
        "early_green2",
        "early_dry_green2",
        "warning",
    ]

    cols = [c for c in keep_cols if c in df.columns]
    df = df[cols].copy()

    df["date"] = today_str()
    df["time"] = now_time_str()
    df["market_real"] = market_real
    df["market_forecast"] = market_forecast

    df["t1_return"] = None
    df["t3_return"] = None
    df["t5_return"] = None
    df["t1_win"] = None
    df["t3_win"] = None
    df["t5_win"] = None

    old_df = read_pattern_history()

    if old_df.empty:
        out = df
    else:
        out = pd.concat([old_df, df], ignore_index=True)

    out = out.drop_duplicates(subset=["date", "symbol"], keep="last")
    out = out.sort_values(["date", "symbol"]).reset_index(drop=True)

    status = write_pattern_history(out)

    print("PATTERN ROWS TODAY =", len(df))
    print("PATTERN TOTAL ROWS =", len(out))
    print("PATTERN STATUS =", status)

    return out, status
