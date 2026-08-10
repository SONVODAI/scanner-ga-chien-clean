# ==========================================================
# modules/learning_pattern_match.py
# MR.BOT ELITE PRIME
# Learning Pattern Match Engine v1.00
#
# BOT Learning Insight
#          ↓
# Pattern DNA
#          ↓
# Scan toàn bộ scan_df
#          ↓
# Similarity Score
#          ↓
# TOP PATTERN MATCH
# ==========================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict
from typing import List
from typing import Tuple
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

# ----------------------------------------------------------
# Learning Engine
# ----------------------------------------------------------

from modules.earning_learning import (
    get_learning_metadata,
    get_pattern_snapshot,
    get_pattern_lifecycle,
    get_continuation_knowledge,
)

# ----------------------------------------------------------
# Leader Brain
# ----------------------------------------------------------
from leader_memory import (
    load_pattern_library,
    get_active_leaders,
)

# ==========================================================
# CONFIG
# ==========================================================

TOP_N = 20

WEIGHTS = {

    "rsi":22,

    "rs":18,

    "obv":15,

    "leader":20,

    "market":15,

    "continuation":10,

}

# ==========================================================
# Pattern DNA
# ==========================================================

@dataclass

class PatternDNA:

    rsi_low:float=0

    rsi_high:float=100

    rs_low:float=-999

    rs_high:float=999

    obv:str=""

    health:str=""

    market_real:float=0

    continuation:float=0

    winrate:float=0

# ==========================================================
# Utils
# ==========================================================

def clamp(v,low,high):

    return max(low,min(high,v))


def safe_float(v):

    try:

        if pd.isna(v):

            return 0.0

        return float(v)

    except:

        return 0.0


# ==========================================================
# Read Learning
# ==========================================================

def load_learning_context():

    metadata=get_learning_metadata()

    snapshot=get_pattern_snapshot()

    lifecycle=get_pattern_lifecycle()

    continuation=get_continuation_knowledge()

    return {

        "metadata":metadata,

        "snapshot":snapshot,

        "lifecycle":lifecycle,

        "continuation":continuation,

    }


# ==========================================================
# Build Pattern DNA
# ==========================================================

def build_pattern_dna()->PatternDNA:

    ctx=load_learning_context()

    snapshot=ctx["snapshot"]

    lifecycle=ctx["lifecycle"]

    continuation=ctx["continuation"]

    dna=PatternDNA()

    # -------------------------------------
    # Snapshot
    # -------------------------------------

    if snapshot is not None and len(snapshot)>0:

        row=snapshot.iloc[0]

        dna.rsi_low=safe_float(row.get("rsi_low",45))

        dna.rsi_high=safe_float(row.get("rsi_high",55))

        dna.rs_low=safe_float(row.get("rs_low",-1))

        dna.rs_high=safe_float(row.get("rs_high",3))

        dna.obv=str(row.get("obv_status",""))

        dna.health=str(row.get("health_group",""))

        dna.market_real=safe_float(
            row.get("market_real",0)
        )

    # -------------------------------------
    # Continuation
    # -------------------------------------

    if continuation is not None:

        if len(continuation)>0:

            dna.continuation=safe_float(

                continuation.iloc[0].get(

                    "continuation_score",

                    0,

                )

            )

    # -------------------------------------
    # Lifecycle
    # -------------------------------------

    if lifecycle is not None:

        if len(lifecycle)>0:

            dna.winrate=safe_float(

                lifecycle.iloc[0].get(

                    "winrate",

                    0,

                )

            )

    return dna
# ==========================================================
# Similarity Engine
# ==========================================================

def score_rsi(dna: PatternDNA, row: pd.Series) -> float:

    rsi = safe_float(row.get("rsi14", 0))

    if dna.rsi_low <= rsi <= dna.rsi_high:
        return WEIGHTS["rsi"]

    center = (dna.rsi_low + dna.rsi_high) / 2.0

    dist = abs(rsi - center)

    score = WEIGHTS["rsi"] * math.exp(-dist / 10.0)

    return clamp(score, 0, WEIGHTS["rsi"])


def score_rs(dna: PatternDNA, row: pd.Series) -> float:

    rs = safe_float(row.get("RS", row.get("rs", 0)))

    if dna.rs_low <= rs <= dna.rs_high:
        return WEIGHTS["rs"]

    center = (dna.rs_low + dna.rs_high) / 2.0

    dist = abs(rs - center)

    score = WEIGHTS["rs"] * math.exp(-dist / 3.0)

    return clamp(score, 0, WEIGHTS["rs"])


def score_obv(dna: PatternDNA, row: pd.Series) -> float:

    obv = str(row.get("obv_status", "")).upper()

    target = str(dna.obv).upper()

    if obv == target:
        return WEIGHTS["obv"]

    if target in obv:
        return WEIGHTS["obv"] * 0.8

    if obv in target:
        return WEIGHTS["obv"] * 0.8

    return 0


def score_leader(row: pd.Series) -> float:

    leader = safe_float(row.get("leader_score", 0))

    confidence = safe_float(row.get("confidence_score", 0))

    score = leader * 0.7 + confidence * 0.3

    score = score / 100.0

    return clamp(

        score * WEIGHTS["leader"],

        0,

        WEIGHTS["leader"],

    )


def score_market(dna: PatternDNA, row: pd.Series) -> float:

    current = safe_float(

        row.get(

            "market_real",

            dna.market_real,

        )

    )

    diff = abs(current - dna.market_real)

    score = WEIGHTS["market"] * math.exp(-diff / 2.0)

    return clamp(

        score,

        0,

        WEIGHTS["market"],

    )


def score_continuation(

    dna: PatternDNA,

    row: pd.Series,

) -> float:

    t5 = safe_float(

        row.get(

            "winrate_t5_pct",

            0,

        )

    )

    t10 = safe_float(

        row.get(

            "winrate_t10_pct",

            t5,

        )

    )

    value = max(t5, t10)

    value = value / 100.0

    return clamp(

        value * WEIGHTS["continuation"],

        0,

        WEIGHTS["continuation"],

    )


# ==========================================================
# Final Similarity
# ==========================================================

def similarity_score(

    dna: PatternDNA,

    row: pd.Series,

) -> Dict:

    s_rsi = score_rsi(dna, row)

    s_rs = score_rs(dna, row)

    s_obv = score_obv(dna, row)

    s_leader = score_leader(row)

    s_market = score_market(dna, row)

    s_continue = score_continuation(dna, row)

    total = (

        s_rsi +

        s_rs +

        s_obv +

        s_leader +

        s_market +

        s_continue

    )

    return {

        "score": round(total, 2),

        "rsi": round(s_rsi, 2),

        "rs": round(s_rs, 2),

        "obv": round(s_obv, 2),

        "leader": round(s_leader, 2),

        "market": round(s_market, 2),

        "continuation": round(s_continue, 2),

    }
# ==========================================================
# Build Pattern Match Table
# ==========================================================

def build_pattern_match(scan_df: pd.DataFrame) -> pd.DataFrame:

    if scan_df is None:
        return pd.DataFrame()

    if scan_df.empty:
        return pd.DataFrame()
    # =====================================================
    # Merge Leader Brain
    # =====================================================
    try:
        leaders = get_active_leaders(limit=1000)
        if not leaders.empty:

            keep = [
                c
                for c in (
                    "symbol",
                    "leader_score",
                    "confidence_score",
                )
                if c in leaders.columns
            ]

            leaders = leaders[keep]

            scan_df = scan_df.merge(
                leaders,
                on="symbol",
                how="left",
            )

    except Exception as e:
        st.warning(f"Leader Merge Error: {e}")
    dna = build_pattern_dna()

    rows = []

    for _, row in scan_df.iterrows():

        result = similarity_score(
            dna,
            row,
        )

        rows.append({

            "symbol": row.get("symbol", ""),

            "group": row.get("group", ""),

            "price": safe_float(row.get("price", 0)),

            "health": row.get("health_group", ""),

            "leader_score": safe_float(
                row.get("leader_score", 0)
            ),

            "confidence": safe_float(
                row.get("confidence_score", 0)
            ),

            "pattern_match": result["score"],

            "rsi_score": result["rsi"],

            "rs_score": result["rs"],

            "obv_score": result["obv"],

            "leader_component": result["leader"],

            "market_component": result["market"],

            "continuation_component": result["continuation"],

            "rsi14": safe_float(
                row.get("rsi14", 0)
            ),

            "RS": safe_float(
                row.get(
                    "RS",
                    row.get("rs", 0),
                )
            ),

            "obv_status": row.get(
                "obv_status",
                "",
            ),

        })

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    out = out.sort_values(

        "pattern_match",

        ascending=False,

    )

    out = out.reset_index(drop=True)

    out["rank"] = out.index + 1

    cols = [

        "rank",

        "symbol",

        "group",

        "price",

        "pattern_match",

        "leader_score",

        "confidence",

        "rsi14",

        "RS",

        "obv_status",

        "rsi_score",

        "rs_score",

        "obv_score",

        "leader_component",

        "market_component",

        "continuation_component",

    ]

    cols = [

        c

        for c in cols

        if c in out.columns

    ]

    return out[cols].head(TOP_N)


# ==========================================================
# Explain Pattern
# ==========================================================

def explain_pattern(row: pd.Series) -> List[str]:

    reasons = []

    if safe_float(row.get("rsi_score", 0)) > 18:
        reasons.append("✅ RSI rất gần mẫu thắng")

    if safe_float(row.get("rs_score", 0)) > 15:
        reasons.append("✅ RS gần DNA thắng")

    if safe_float(row.get("obv_score", 0)) > 12:
        reasons.append("✅ OBV đồng pha")

    if safe_float(row.get("leader_component", 0)) > 15:
        reasons.append("✅ Leader Brain đánh giá cao")

    if safe_float(row.get("market_component", 0)) > 10:
        reasons.append("✅ Phù hợp bối cảnh thị trường")

    if safe_float(row.get("continuation_component", 0)) > 6:
        reasons.append("✅ Có sức bền T5/T10")

    return reasons
# ==========================================================
# Streamlit UI
# ==========================================================

_EARLY_RADAR_COLUMNS = (
    "rank",
    "symbol",
    "group",
    "price",
    "pattern_match",
    "leader_score",
    "confidence",
    "rsi14",
    "RS",
    "obv_status",
)

_EARLY_RADAR_DISPLAY_NAMES = {
    "pattern_match": "DNA Match (%)",
    "leader_score": "Leader Score",
    "confidence": "Confidence",
}


def render_pattern_match_early_radar(
    pattern_match_df: pd.DataFrame,
    *,
    top_n: int = 10,
) -> None:
    """Compact read-only Top-N radar for the default dashboard."""
    st.markdown("---")
    st.markdown("## 🧠 TOP PATTERN MATCH — EARLY RADAR")
    st.caption(
        "Radar phát hiện sớm các cổ phiếu có DNA gần mẫu thắng. "
        "Dùng để theo dõi Early/Tích lũy trước khi trở thành Leader; "
        "không đồng nghĩa khuyến nghị mua."
    )

    if pattern_match_df is None or pattern_match_df.empty:
        st.info("Không có dữ liệu Pattern Match.")
        return

    cols = [c for c in _EARLY_RADAR_COLUMNS if c in pattern_match_df.columns]
    if not cols:
        st.info("Không có dữ liệu Pattern Match.")
        return

    display = pattern_match_df.head(max(1, int(top_n)))[cols].copy()
    display = display.rename(columns=_EARLY_RADAR_DISPLAY_NAMES)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "DNA Match (%)": st.column_config.NumberColumn(
                "DNA Match (%)",
                help="Mức độ tương đồng với DNA thắng mà BOT đã học trong bối cảnh hiện tại.",
                format="%.2f%%",
            ),
        },
    )


def show_pattern_match(
    scan_df: pd.DataFrame,
    *,
    pattern_match_df: Optional[pd.DataFrame] = None,
):
    
    st.markdown("---")
    st.subheader("🧠 TOP PATTERN MATCH")

    try:

        dna = build_pattern_dna()

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric(
                "RSI DNA",
                f"{dna.rsi_low:.0f}-{dna.rsi_high:.0f}",
            )

        with c2:
            st.metric(
                "RS DNA",
                f"{dna.rs_low:.1f} → {dna.rs_high:.1f}",
            )

        with c3:
            st.metric(
                "Winrate",
                f"{dna.winrate:.1f}%",
            )

    except Exception as e:

        st.warning(f"Learning DNA unavailable : {e}")

    result = (
        pattern_match_df.copy()
        if pattern_match_df is not None
        else build_pattern_match(scan_df)
    )

    if result.empty:

        st.info("Không có dữ liệu Pattern Match.")

        return

    # Tên hiển thị dễ hiểu: đây là mức độ giống DNA thắng, không phải lệnh mua.
    display_result = result.rename(
        columns={
            "pattern_match": "DNA Match (%)",
            "leader_score": "Leader Score",
            "confidence": "Confidence",
        }
    )

    st.dataframe(
        display_result,
        width="stretch",
        hide_index=True,
        column_config={
            "DNA Match (%)": st.column_config.NumberColumn(
                "DNA Match (%)",
                help="Mức độ tương đồng với DNA thắng mà BOT đã học trong bối cảnh hiện tại.",
                format="%.2f%%",
            ),
        },
    )

    # =====================================================
    # Detail
    # =====================================================

    st.markdown("### 🔍 Giải thích")

    symbols = result["symbol"].tolist()

    symbol = st.selectbox(

        "Chọn cổ phiếu",

        symbols,

        key="pattern_match_symbol",

    )

    row = result[

        result["symbol"] == symbol

    ].iloc[0]

    st.metric(

        "Pattern Match",

        f"{row['pattern_match']:.1f}/100",

    )

    reasons = explain_pattern(row)

    for r in reasons:

        st.write(r)

    # =====================================================
    # Export
    # =====================================================

    csv = display_result.to_csv(
        index=False,
        encoding="utf-8-sig",
    )

    st.download_button(

        "📥 Export Pattern Match",

        csv,

        file_name="pattern_match.csv",

        mime="text/csv",

    )


# ==========================================================
# Public API
# ==========================================================

def run(scan_df):

    """
    API dùng trong app.py

    run(scan_df)

    """

    show_pattern_match(scan_df)
