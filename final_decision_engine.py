# =========================================================
# MR.BOT FINAL DECISION ENGINE
# PART 1/3
# =========================================================

import pandas as pd
import numpy as np
import re

MAX_TOP = 10
MAX_PER_SECTOR = 3

# =========================================================
# COLUMN DETECTOR
# =========================================================

def find_col(df, names):

    if df is None or df.empty:
        return None

    cols = list(df.columns)

    lower = {
        str(c).strip().lower(): c
        for c in cols
    }

    for name in names:

        key = str(name).strip().lower()

        if key in lower:
            return lower[key]

    return None


# =========================================================
# SAFE NUMBER
# =========================================================

def to_number(x, default=0):

    try:

        if pd.isna(x):
            return default

        s = str(x)

        s = s.replace("%", "")
        s = s.replace(",", ".")
        s = s.strip()

        m = re.search(r"-?\d+(\.\d+)?", s)

        if m is None:
            return default

        return float(m.group())

    except:

        return default


# =========================================================
# NORMALIZE
# =========================================================

def normalize_percent(x):

    v = to_number(x)

    if v <= 1:
        v *= 100

    if v < 0:
        v = 0

    if v > 100:
        v = 100

    return v


# =========================================================
# CONFIDENCE
# =========================================================

def confidence_value(x):

    s = str(x).upper()

    if "RẤT CAO" in s:
        return 95

    if "VERY HIGH" in s:
        return 95

    if "CAO" in s:
        return 85

    if "HIGH" in s:
        return 85

    if "TRUNG" in s:
        return 65

    if "TB" in s:
        return 65

    if "MEDIUM" in s:
        return 65

    if "THẤP" in s:
        return 40

    if "LOW" in s:
        return 40

    return normalize_percent(x)


# =========================================================
# CONSENSUS
# =========================================================

def consensus_value(x):

    s = str(x)

    m = re.search(r"(\d+)\s*/\s*(\d+)", s)

    if m:

        a = float(m.group(1))
        b = float(m.group(2))

        if b == 0:
            return 0

        return a / b * 100

    if "✅" in s:
        return 100

    return normalize_percent(x)


# =========================================================
# STAR
# =========================================================

def star(score):

    if score >= 95:
        return "★★★★★"

    if score >= 90:
        return "★★★★☆"

    if score >= 80:
        return "★★★☆☆"

    if score >= 70:
        return "★★☆☆☆"

    return "★☆☆☆☆"


# =========================================================
# ONLY BUY
# =========================================================

def filter_buy_only(df):

    if df is None:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    result = df.copy()

    conclusion_col = find_col(
        result,
        [
            "KẾT LUẬN",
            "KET LUAN",
            "ACTION",
        ],
    )

    if conclusion_col is None:
        return result

    allow = [

        "MUA",

        "MUA NHỎ",

        "MUA NHỎ / ƯU TIÊN",

        "MUA ƯU TIÊN",

        "BUY",

        "BUY SMALL",

    ]

    result = result[
        result[conclusion_col]
        .astype(str)
        .str.upper()
        .isin([x.upper() for x in allow])
    ]

    result = result.reset_index(drop=True)

    return result


# =========================================================
# GREEN BONUS
# =========================================================

def build_green_set(green_df):

    if green_df is None:
        return set()

    if green_df.empty:
        return set()

    symbol_col = find_col(
        green_df,
        [
            "MÃ",
            "SYMBOL",
            "TICKER",
        ],
    )

    if symbol_col is None:
        return set()

    return set(

        green_df[symbol_col]

        .astype(str)

        .str.upper()

        .str.strip()

    )
    # =========================================================
# MR.BOT FINAL DECISION ENGINE
# PART 2/3
# =========================================================

# =========================================================
# BUILD DECISION
# =========================================================

def build_final_decision(
    buy_elite_df,
    green_red_df=None,
    max_top=MAX_TOP,
    max_per_sector=MAX_PER_SECTOR,
):

    buy_df = filter_buy_only(buy_elite_df)

    if buy_df.empty:
        return (
            pd.DataFrame(),
            "Hôm nay không có cổ phiếu đủ điều kiện MUA.",
        )

    green_set = build_green_set(green_red_df)

    symbol_col = find_col(
        buy_df,
        [
            "MÃ",
            "SYMBOL",
            "TICKER",
        ],
    )

    elite_col = find_col(
        buy_df,
        [
            "EliteScore",
            "ELITESCORE",
            "ELITE SCORE",
        ],
    )

    win_col = find_col(
        buy_df,
        [
            "WinProb",
            "WINPROB",
        ],
    )

    trust_col = find_col(
        buy_df,
        [
            "ĐỘ TIN CẬY",
            "DO TIN CAY",
            "CONFIDENCE",
        ],
    )

    consensus_col = find_col(
        buy_df,
        [
            "ĐỒNG THUẬN",
            "DONG THUAN",
        ],
    )

    sector_col = find_col(
        buy_df,
        [
            "NGÀNH",
            "NGANH",
            "SECTOR",
            "INDUSTRY",
            "NHÓM",
        ],
    )

    group_col = find_col(
        buy_df,
        [
            "NHÓM",
            "GROUP",
        ],
    )

    price_col = find_col(
        buy_df,
        [
            "GIÁ",
            "PRICE",
        ],
    )

    zone_col = find_col(
        buy_df,
        [
            "VÙNG MUA ELITE",
            "VÙNG MUA",
        ],
    )

    nav_col = find_col(
        buy_df,
        [
            "NAV ELITE",
            "NAV",
        ],
    )

    reason_col = find_col(
        buy_df,
        [
            "LÝ DO ELITE",
            "LÝ DO",
        ],
    )

    risk_col = find_col(
        buy_df,
        [
            "RỦI RO",
            "RISK",
        ],
    )

    result = buy_df.copy()

    result["_symbol"] = (
        result[symbol_col]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    result["_elite"] = (
        result[elite_col].apply(normalize_percent)
        if elite_col else 0
    )

    result["_win"] = (
        result[win_col].apply(normalize_percent)
        if win_col else 0
    )

    result["_trust"] = (
        result[trust_col].apply(confidence_value)
        if trust_col else 0
    )

    result["_consensus"] = (
        result[consensus_col].apply(consensus_value)
        if consensus_col else 0
    )

    result["_green"] = result["_symbol"].apply(
        lambda x: 100 if x in green_set else 0
    )

    # =====================================================
    # DECISION SCORE
    # =====================================================

    result["DecisionScore"] = (

        result["_elite"] * 0.35

        + result["_win"] * 0.25

        + result["_trust"] * 0.20

        + result["_consensus"] * 0.10

        + result["_green"] * 0.10

    )

    result["DecisionScore"] = result["DecisionScore"].round(2)

    result["⭐"] = result["DecisionScore"].apply(star)

    result["GREEN"] = result["_symbol"].apply(
        lambda x: "🟢" if x in green_set else ""
    )

    if sector_col:

        result["_sector"] = (
            result[sector_col]
            .fillna("Khác")
            .astype(str)
        )

    else:

        result["_sector"] = "Khác"

    result = result.sort_values(

        "DecisionScore",

        ascending=False,

    ).reset_index(drop=True)

    # =====================================================
    # SECTOR LIMIT
    # =====================================================

    selected = []

    sector_counter = {}

    for _, row in result.iterrows():

        sector = row["_sector"]

        if sector_counter.get(sector, 0) >= max_per_sector:
            continue

        selected.append(row)

        sector_counter[sector] = (
            sector_counter.get(sector, 0) + 1
        )

        if len(selected) >= max_top:
            break

    if len(selected) == 0:

        return (
            pd.DataFrame(),
            "Không còn cổ phiếu sau khi áp dụng bộ lọc ngành.",
        )

    result = pd.DataFrame(selected).reset_index(drop=True)

    result.insert(

        0,

        "#",

        np.arange(

            1,

            len(result) + 1,

        ),

    )
    # =========================================================
# MR.BOT FINAL DECISION ENGINE
# PART 3/3
# =========================================================

    # =====================================================
    # BUILD REASON
    # =====================================================

    reasons = []

    for _, row in result.iterrows():

        txt = []

        if row["_elite"] >= 90:
            txt.append("Elite rất mạnh")
        elif row["_elite"] >= 80:
            txt.append("Elite mạnh")

        if row["_win"] >= 75:
            txt.append("WinProb cao")

        if row["_trust"] >= 80:
            txt.append("Độ tin cậy cao")

        if row["_consensus"] >= 80:
            txt.append("Đồng thuận mạnh")

        if row["_green"] > 0:
            txt.append("Có mặt bảng Xanh")

        reasons.append(" • ".join(txt))

    result["Lý do chọn"] = reasons

    # =====================================================
    # FINAL COLUMNS
    # =====================================================

    keep = [
        "#",
        "⭐",
    ]

    keep.append(symbol_col)

    keep.append("DecisionScore")

    keep.append("Lý do chọn")

    if group_col:
        keep.append(group_col)

    if sector_col and sector_col != group_col:
        keep.append(sector_col)
    if price_col:
        keep.append(price_col)

    if zone_col:
        keep.append(zone_col)

    if nav_col:
        keep.append(nav_col)

    if elite_col:
        keep.append(elite_col)

    if win_col:
        keep.append(win_col)

    if trust_col:
        keep.append(trust_col)

    if consensus_col:
        keep.append(consensus_col)

    if reason_col:
        keep.append(reason_col)

    if risk_col:
        keep.append(risk_col)

    keep = [c for c in keep if c in result.columns]

    result = result[keep].copy()

    result = result.rename(
        columns={
            symbol_col: "MÃ",
            group_col: "NHÓM",
            sector_col: "NGÀNH",
            price_col: "GIÁ",
            zone_col: "VÙNG MUA",
            nav_col: "NAV",
            elite_col: "EliteScore",
            win_col: "WinProb",
            trust_col: "ĐỘ TIN CẬY",
            consensus_col: "ĐỒNG THUẬN",
            reason_col: "LÝ DO ELITE",
            risk_col: "RỦI RO",
        }
    )
        result = result.loc[:, ~result.columns.duplicated()].copy()
    return (
        result.reset_index(drop=True),
        f"Tìm được {len(result)} cổ phiếu tinh hoa."
    )


# =========================================================
# STYLE
# =========================================================

def style_final_decision(df):

    if df is None or df.empty:
        return df

    styler = df.style

    if "DecisionScore" in df.columns:

        styler = styler.background_gradient(
            subset=["DecisionScore"],
            cmap="YlGn",
        )

    return styler
