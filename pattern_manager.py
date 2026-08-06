# =========================================================
# GENESIS V23
# CORE SCHEMA
# =========================================================

SCHEMA_VERSION = "GENESIS_V23"

LEARNING_GROUPS = (
    "MUA EARLY",
    "PULL VỪA",
    "PULL ĐẸP",
    "CP MẠNH",
)

IDENTITY_COLUMNS = [
    "sample_id",
    "date",
    "time",
    "schema_version",
    "symbol",
]

CONTEXT_COLUMNS = [
    "market_real",
    "market_forecast",
]

DNA_COLUMNS = [
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

OUTCOME_COLUMNS = [
    "t1_return",
    "t3_return",
    "t5_return",
    "t10_return",

    "t1_win",
    "t3_win",
    "t5_win",
    "t10_win",
]

ALL_COLUMNS = (
    IDENTITY_COLUMNS
    + CONTEXT_COLUMNS
    + DNA_COLUMNS
    + OUTCOME_COLUMNS
# =========================================================
# FILTER
# =========================================================

def filter_learning_samples(scan_df: pd.DataFrame) -> pd.DataFrame:

    if scan_df is None:
        return pd.DataFrame()

    if scan_df.empty:
        return pd.DataFrame()

    if "group" not in scan_df.columns:
        return pd.DataFrame()

    return (
        scan_df[
            scan_df["group"].isin(LEARNING_GROUPS)
        ]
        .copy()
        .reset_index(drop=True)
    )
    
# =========================================================
# BUILDERS
# =========================================================

def build_identity(df: pd.DataFrame) -> pd.DataFrame:

    out = df.copy()

    out["date"] = today_str()
    out["time"] = now_time_str()

    out["schema_version"] = SCHEMA_VERSION

    out["sample_id"] = (
        out["date"].astype(str)
        + "_"
        + out["symbol"].astype(str)
    )

    return out
def build_context(
    df,
    market_real,
    market_forecast,
):

    out = df.copy()

    out["market_real"] = market_real
    out["market_forecast"] = market_forecast

    return out
def build_outcome(df):

    out = df.copy()

    for col in OUTCOME_COLUMNS:

        if col not in out.columns:
            out[col] = None

    return out
def normalize_schema(df):

    out = df.copy()

    for col in ALL_COLUMNS:

        if col not in out.columns:
            out[col] = None

    return out[ALL_COLUMNS]
# =========================================================
# HISTORY MERGE
# =========================================================

def merge_history(
    old_df: pd.DataFrame,
    new_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ghép lịch sử cũ và dữ liệu mới.
    Luôn giữ record mới nhất của cùng 1 ngày + 1 mã.
    """

    if old_df is None or old_df.empty:
        return normalize_schema(new_df)

    old_df = normalize_schema(old_df)
    new_df = normalize_schema(new_df)

    out = pd.concat(
        [
            old_df,
            new_df,
        ],
        ignore_index=True,
    )

    out = (
        out
        .drop_duplicates(
            subset=[
                "date",
                "symbol",
            ],
            keep="last",
        )
        .sort_values(
            [
                "date",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )

    return out

# =========================================================
# MAIN SAVE ENGINE
# =========================================================

def save_pattern_history(
    brain,
    scan_df,
    market_real,
    market_forecast,
):

    if scan_df is None or scan_df.empty:
        print("PATTERN SKIP : EMPTY SCAN")
        return pd.DataFrame(), "EMPTY_SCAN"

    df = filter_learning_samples(scan_df)

    if df.empty:
        print("PATTERN SKIP : EMPTY LEARNING GROUP")
        return pd.DataFrame(), "EMPTY_LEARNING"

    keep_cols = [
        c
        for c in DNA_COLUMNS
        if c in df.columns
    ]

    df = df[
        ["symbol"] + keep_cols
    ].copy()

    df = build_identity(df)

    df = build_context(
        df,
        market_real,
        market_forecast,
    )

    df = build_outcome(df)

    df = normalize_schema(df)

    old_df = read_pattern_history()

    history = merge_history(
        old_df,
        df,
    )

    status = write_pattern_history(history)

    print("=" * 60)
    print("PATTERN HISTORY")
    print("=" * 60)
    print("TODAY :", len(df))
    print("TOTAL :", len(history))
    print("STATUS:", status)

    return history, status
# =========================================================
# T+ UPDATE ENGINE
# =========================================================

def _safe_float(x):
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _calc_return(buy_price, sell_price):

    buy = _safe_float(buy_price)
    sell = _safe_float(sell_price)

    if buy is None:
        return None

    if sell is None:
        return None

    if buy <= 0:
        return None

    return round((sell - buy) / buy * 100, 2)


def _calc_win(ret):

    if ret is None:
        return None

    return int(ret > 0)
# =========================================================
# UPDATE T+
# =========================================================

def update_tplus_result(
    history_df: pd.DataFrame,
    today_price_df: pd.DataFrame,
    hold_days: int,
):

    if history_df is None:
        return history_df

    if history_df.empty:
        return history_df

    if today_price_df is None:
        return history_df

    if today_price_df.empty:
        return history_df

    return_col = f"t{hold_days}_return"
    win_col = f"t{hold_days}_win"

    if return_col not in history_df.columns:
        history_df[return_col] = None

    if win_col not in history_df.columns:
        history_df[win_col] = None

    price_map = (
        today_price_df
        .set_index("symbol")["price"]
        .to_dict()
    )

    history = history_df.copy()

    for idx in history.index:

        if pd.notna(history.at[idx, return_col]):
            continue

        symbol = history.at[idx, "symbol"]

        if symbol not in price_map:
            continue

        buy_price = history.at[idx, "price"]

        sell_price = price_map[symbol]

        ret = _calc_return(
            buy_price,
            sell_price,
        )

        history.at[idx, return_col] = ret

        history.at[idx, win_col] = _calc_win(ret)

    return history
# =========================================================
# WRAPPER
# =========================================================

def update_all_tplus(
    history_df,
    t1_price_df=None,
    t3_price_df=None,
    t5_price_df=None,
    t10_price_df=None,
):

    out = history_df.copy()

    if t1_price_df is not None:
        out = update_tplus_result(
            out,
            t1_price_df,
            1,
        )

    if t3_price_df is not None:
        out = update_tplus_result(
            out,
            t3_price_df,
            3,
        )

    if t5_price_df is not None:
        out = update_tplus_result(
            out,
            t5_price_df,
            5,
        )

    if t10_price_df is not None:
        out = update_tplus_result(
            out,
            t10_price_df,
            10,
        )

    return out
# =========================================================
# LEARNING STATISTICS ENGINE
# =========================================================

def build_pattern_statistics(history_df: pd.DataFrame):

    if history_df is None:
        return pd.DataFrame()

    if history_df.empty:
        return pd.DataFrame()

    df = history_df.copy()

    stats = []

    feature_cols = [
        "group",
        "E",
        "R",
        "O",
        "S",
        "RS",
        "V",
        "green_2_confirm",
        "early_green2",
        "early_dry_green2",
        "warning",
    ]

    for feature in feature_cols:

        if feature not in df.columns:
            continue

        values = (
            df[feature]
            .dropna()
            .unique()
        )

        for value in values:

            sub = df[
                df[feature] == value
            ]

            row = {
                "feature": feature,
                "value": value,
                "samples": len(sub),
            }

            for t in [1,3,5,10]:

                ret_col = f"t{t}_return"
                win_col = f"t{t}_win"

                if ret_col in sub.columns:

                    row[f"avg_t{t}"] = round(
                        sub[ret_col].dropna().mean(),
                        2
                    )

                if win_col in sub.columns:

                    row[f"winrate_t{t}"] = round(
                        sub[win_col].dropna().mean()*100,
                        1
                    )

            stats.append(row)

    return pd.DataFrame(stats)
# =========================================================
# BEST DNA
# =========================================================

def build_best_pattern(stats_df):

    if stats_df.empty:
        return pd.DataFrame()

    df = stats_df.copy()

    if "winrate_t5" in df.columns:

        df = df.sort_values(

            by=[
                "winrate_t5",
                "avg_t5",
                "samples",
            ],

            ascending=False,

        )

    return df.reset_index(drop=True)
# =========================================================
# LEARNING SNAPSHOT
# =========================================================

def build_learning_snapshot(history_df):

    stats = build_pattern_statistics(history_df)

    best = build_best_pattern(stats)

    return {

        "history_rows": len(history_df),

        "patterns": len(best),

        "best_pattern": best.head(30),

    }
# =========================================================
# DNA SIGNATURE
# =========================================================

def build_pattern_signature(row):

    parts = [

        f"G={row.get('group','')}",

        f"E={row.get('E','')}",
        f"R={row.get('R','')}",
        f"O={row.get('O','')}",
        f"S={row.get('S','')}",
        f"RS={row.get('RS','')}",
        f"V={row.get('V','')}",

        f"RSI={round(float(row.get('rsi14',0)),1)}",

        f"OBV={row.get('obv_status','')}",

        f"G2={row.get('green_2_confirm','')}",

        f"EARLY={row.get('early_green2','')}",
    ]

    return "|".join(parts)
# =========================================================
# BUILD DNA
# =========================================================

def build_pattern_dna(history_df):

    df = history_df.copy()

    df["pattern_signature"] = df.apply(

        build_pattern_signature,

        axis=1,

    )

    return df
# =========================================================
# DNA STATISTICS
# =========================================================

def build_dna_statistics(history_df):

    if history_df.empty:

        return pd.DataFrame()

    df = build_pattern_dna(history_df)

    rows = []

    for dna, sub in df.groupby("pattern_signature"):

        row = {

            "pattern_signature": dna,

            "samples": len(sub),

        }

        for t in [1,3,5,10]:

            r = f"t{t}_return"

            w = f"t{t}_win"

            if r in sub.columns:

                row[f"avg_t{t}"] = round(

                    sub[r].dropna().mean(),

                    2,

                )

            if w in sub.columns:

                row[f"winrate_t{t}"] = round(

                    sub[w].dropna().mean()*100,

                    1,

                )

        rows.append(row)

    out = pd.DataFrame(rows)

    if out.empty:

        return out

    return out.sort_values(

        by=[

            "winrate_t5",

            "avg_t5",

            "samples",

        ],

        ascending=False,

    ).reset_index(drop=True)
# =========================================================
# EXPORT LEARNING
# =========================================================

def export_learning_snapshot(history_df):

    feature_stats = build_pattern_statistics(

        history_df,

    )

    dna_stats = build_dna_statistics(

        history_df,

    )

    return {

        "feature_stats": feature_stats,

        "dna_stats": dna_stats,

        "best_dna": dna_stats.head(20),

    }
# =========================================================
# FEATURE NORMALIZATION
# =========================================================

def normalize_rsi(rsi):

    r = _safe_float(rsi)

    if r is None:
        return "UNKNOWN"

    if r < 40:
        return "<40"

    if r < 45:
        return "40-45"

    if r < 50:
        return "45-50"

    if r < 55:
        return "50-55"

    if r < 60:
        return "55-60"

    if r < 65:
        return "60-65"

    if r < 70:
        return "65-70"

    return ">=70"


def normalize_rs(rs):

    r = _safe_float(rs)

    if r is None:
        return "?"

    if r <= -4:
        return "<=-4"

    if r <= -2:
        return "-4~-2"

    if r <= 0:
        return "-2~0"

    if r <= 2:
        return "0~2"

    if r <= 4:
        return "2~4"

    return ">4"
# =========================================================
# NORMALIZE OBV
# =========================================================

def normalize_obv(value):

    if pd.isna(value):
        return "UNKNOWN"

    s = str(value).upper()

    if "GREEN" in s:
        return "GREEN"

    if "RED" in s:
        return "RED"

    if "UP" in s:
        return "UP"

    if "DOWN" in s:
        return "DOWN"

    return s
def build_pattern_signature(row):

    parts = [

        f"G={row.get('group','')}",

        f"RS={normalize_rs(row.get('RS'))}",

        f"RSI={normalize_rsi(row.get('rsi14'))}",

        f"OBV={normalize_obv(row.get('obv_status'))}",

        f"E={row.get('E','')}",

        f"R={row.get('R','')}",

        f"S={row.get('S','')}",

        f"G2={row.get('green_2_confirm','')}",

        f"EARLY={row.get('early_green2','')}",
    ]

    return "|".join(parts)
# =========================================================
# MIN SAMPLE FILTER
# =========================================================

MIN_PATTERN_SAMPLE = 5


def filter_valid_patterns(stats_df):

    if stats_df is None:
        return pd.DataFrame()

    if stats_df.empty:
        return pd.DataFrame()

    return (
        stats_df[
            stats_df["samples"] >= MIN_PATTERN_SAMPLE
        ]
        .copy()
        .reset_index(drop=True)
    )
# =========================================================
# SCORE PATTERN
# =========================================================

def score_pattern(row):

    score = 0

    samples = row.get("samples", 0)

    score += min(samples, 30)

    for t in [3,5,10]:

        wr = row.get(f"winrate_t{t}")

        if pd.notna(wr):

            score += wr * 0.40

        avg = row.get(f"avg_t{t}")

        if pd.notna(avg):

            score += max(avg,0) * 3

    return round(score,2)
# =========================================================
# RANK PATTERN
# =========================================================

def rank_patterns(stats_df):

    if stats_df.empty:

        return stats_df

    df = filter_valid_patterns(stats_df)

    if df.empty:

        return df

    df["learning_score"] = df.apply(

        score_pattern,

        axis=1,

    )

    df = df.sort_values(

        by=[

            "learning_score",

            "samples",

        ],

        ascending=False,

    )

    return df.reset_index(drop=True)
# =========================================================
# SAVE LEARNING TABLE
# =========================================================

def export_learning_table(history_df):

    stats = build_pattern_statistics(

        history_df,

    )

    stats = rank_patterns(

        stats,

    )

    return stats
# =========================================================
# CONFIDENCE ENGINE
# =========================================================

def calculate_pattern_confidence(row):

    samples = row.get("samples", 0)

    wr = row.get("winrate_t5")

    if pd.isna(wr):
        wr = 0

    if samples < 5:
        return "LOW"

    if samples < 10:

        if wr >= 80:
            return "MEDIUM"

        return "LOW"

    if samples < 20:

        if wr >= 75:
            return "HIGH"

        if wr >= 60:
            return "MEDIUM"

        return "LOW"

    if wr >= 75:
        return "VERY_HIGH"

    if wr >= 60:
        return "HIGH"

    return "MEDIUM"
# =========================================================
# ENRICH LEARNING TABLE
# =========================================================

def enrich_learning_table(df):

    if df.empty:
        return df

    out = df.copy()

    out["confidence"] = out.apply(
        calculate_pattern_confidence,
        axis=1,
    )

    return out
def export_learning_table(history_df):

    stats = build_pattern_statistics(
        history_df,
    )

    stats = rank_patterns(
        stats,
    )

    stats = enrich_learning_table(
        stats,
    )

    return stats
# =========================================================
# TOP LEARNING PATTERNS
# =========================================================

def get_best_learning_patterns(
    history_df,
    top_n=20,
):

    table = export_learning_table(
        history_df,
    )

    if table.empty:
        return table

    return (
        table[
            table["confidence"].isin(
                [
                    "VERY_HIGH",
                    "HIGH",
                ]
            )
        ]
        .head(top_n)
        .reset_index(drop=True)
    )
# =========================================================
# LEARNING INSIGHT ENGINE
# =========================================================

def build_learning_insight(history_df):

    table = get_best_learning_patterns(
        history_df,
        top_n=30,
    )

    if table.empty:
        return {
            "patterns": [],
            "summary": {},
        }

    insight = []

    for _, row in table.iterrows():

        insight.append({

            "pattern": row["pattern_signature"],

            "confidence": row["confidence"],

            "samples": int(row["samples"]),

            "winrate": row.get("winrate_t5"),

            "avg_return": row.get("avg_t5"),

            "learning_score": row.get("learning_score"),

        })

    summary = {

        "total_patterns": len(insight),

        "very_high": sum(
            p["confidence"] == "VERY_HIGH"
            for p in insight
        ),

        "high": sum(
            p["confidence"] == "HIGH"
            for p in insight
        ),

    }

    return {

        "patterns": insight,

        "summary": summary,

    }
# =========================================================
# MATCH ENGINE
# =========================================================

def match_pattern(
    scan_row,
    learning_patterns,
):

    dna = build_pattern_signature(
        scan_row,
    )

    for p in learning_patterns:

        if p["pattern"] == dna:

            return {

                "matched": True,

                "confidence": p["confidence"],

                "winrate": p["winrate"],

                "avg_return": p["avg_return"],

                "learning_score": p["learning_score"],

            }

    return {

        "matched": False,

    }
# =========================================================
# SCORE BOOST
# =========================================================

def calculate_learning_bonus(match):

    if not match["matched"]:
        return 0

    bonus = 0

    if match["confidence"] == "VERY_HIGH":
        bonus += 25

    elif match["confidence"] == "HIGH":
        bonus += 18

    elif match["confidence"] == "MEDIUM":
        bonus += 10

    wr = match.get("winrate")

    if wr is not None:
        bonus += wr / 20

    return round(bonus,2)
# =========================================================
# PUBLIC API
# =========================================================

def learning_bonus_for_stock(
    scan_row,
    history_df,
):

    insight = build_learning_insight(
        history_df,
    )

    match = match_pattern(

        scan_row,

        insight["patterns"],

    )

    return calculate_learning_bonus(
        match,
    )

