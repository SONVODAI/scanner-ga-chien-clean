# =========================================================
# MR.BOT - ELITE PRIME
# Final Decision Engine
# =========================================================

import pandas as pd
import numpy as np


MAX_TOP = 10
MAX_PER_SECTOR = 3


def _find_col(df, candidates):
    if df is None or df.empty:
        return None
    cols = list(df.columns)
    lower_map = {str(c).lower().strip(): c for c in cols}
    for name in candidates:
        key = name.lower().strip()
        if key in lower_map:
            return lower_map[key]
    return None


def _rank_score(rank):
    if pd.isna(rank):
        return 0
    return max(0, 101 - int(rank))


def _prepare_rank_df(df, table_name):
    if df is None or df.empty:
        return pd.DataFrame(columns=["symbol"])

    symbol_col = _find_col(df, ["symbol", "ticker", "mã", "ma", "cp"])
    if symbol_col is None:
        return pd.DataFrame(columns=["symbol"])

    out = df.copy().reset_index(drop=True)
    out["symbol"] = out[symbol_col].astype(str).str.upper().str.strip()
    out = out[out["symbol"] != ""].drop_duplicates("symbol").reset_index(drop=True)

    out[f"{table_name}_rank"] = np.arange(1, len(out) + 1)
    out[f"{table_name}_score"] = out[f"{table_name}_rank"].apply(_rank_score)

    sector_col = _find_col(out, ["ngành", "nganh", "sector", "industry", "group", "nhom_nganh"])
    keep_cols = ["symbol", f"{table_name}_rank", f"{table_name}_score"]

    if sector_col is not None:
        out = out.rename(columns={sector_col: "sector"})
        keep_cols.append("sector")

    return out[keep_cols]


def _merge_sector(row):
    for col in ["sector_elite", "sector_pull", "sector_green", "sector"]:
        if col in row and pd.notna(row[col]) and str(row[col]).strip() != "":
            return row[col]
    return "Khác"


def _apply_sector_limit(df, max_top=MAX_TOP, max_per_sector=MAX_PER_SECTOR):
    selected = []
    sector_count = {}

    for _, row in df.iterrows():
        sector = str(row.get("sector", "Khác"))
        if sector_count.get(sector, 0) >= max_per_sector:
            continue

        selected.append(row)
        sector_count[sector] = sector_count.get(sector, 0) + 1

        if len(selected) >= max_top:
            break

    if not selected:
        return pd.DataFrame()

    return pd.DataFrame(selected)


def build_elite_prime(
    elite_df,
    pull_df,
    green_df,
    max_top=MAX_TOP,
    max_per_sector=MAX_PER_SECTOR,
):
    elite = _prepare_rank_df(elite_df, "elite")
    pull = _prepare_rank_df(pull_df, "pull")
    green = _prepare_rank_df(green_df, "green")

    if elite.empty and pull.empty and green.empty:
        return pd.DataFrame()

    df = elite.merge(pull, on="symbol", how="outer", suffixes=("_elite", "_pull"))
    df = df.merge(green, on="symbol", how="outer", suffixes=("", "_green"))

    sector_cols = [c for c in df.columns if "sector" in c]
    if sector_cols:
        df["sector"] = df.apply(_merge_sector, axis=1)
    else:
        df["sector"] = "Khác"

    for col in [
        "elite_score", "pull_score", "green_score",
        "elite_rank", "pull_rank", "green_rank"
    ]:
        if col not in df.columns:
            df[col] = np.nan

    df["appear_count"] = df[["elite_rank", "pull_rank", "green_rank"]].notna().sum(axis=1)

    df["base_score"] = (
        df["elite_score"].fillna(0) * 0.50
        + df["pull_score"].fillna(0) * 0.30
        + df["green_score"].fillna(0) * 0.20
    )

    df["consensus_bonus"] = np.select(
        [
            df["appear_count"] >= 3,
            df["appear_count"] == 2,
        ],
        [10, 5],
        default=0,
    )

    df["confidence"] = df["base_score"] + df["consensus_bonus"]

    df["confirm"] = df["appear_count"].apply(
        lambda x: "✅ 3/3" if x >= 3 else ("⚠️ 2/3" if x == 2 else "1/3")
    )

    df = df.sort_values(
        by=["confidence", "appear_count", "elite_score", "pull_score", "green_score"],
        ascending=False,
    ).reset_index(drop=True)

    df = _apply_sector_limit(df, max_top=max_top, max_per_sector=max_per_sector)

    if df.empty:
        return pd.DataFrame()

    df = df.reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))

    final_cols = [
        "rank",
        "symbol",
        "confidence",
        "confirm",
        "elite_rank",
        "pull_rank",
        "green_rank",
        "sector",
    ]

    df = df[final_cols].copy()

    df = df.rename(columns={
        "rank": "#",
        "symbol": "Mã",
        "confidence": "Confidence",
        "confirm": "Đồng thuận",
        "elite_rank": "Elite",
        "pull_rank": "Pull",
        "green_rank": "Xanh",
        "sector": "Ngành",
    })

    df["Confidence"] = df["Confidence"].round(1)

    return df
