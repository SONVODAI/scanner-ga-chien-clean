"""
Read-only RS5 / RS10 / RSI14 sweetspot research over earning-learning lifecycle.

Uses frozen T0 features from ``get_pattern_lifecycle()`` and compares them to
matured T3/T5/T10 returns. Does not write learning memory or influence decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

WindowMode = Literal["all", "recent_20"]

HORIZONS: Dict[str, Tuple[str, str]] = {
    "T3": ("t3_return_pct", "t3"),
    "T5": ("t5_return_pct", "t5"),
    "T10": ("t10_return_pct", "t10"),
}

FEATURE_COLUMNS: Tuple[str, str, str] = ("rs5", "rs10", "rsi14")

RS5_RS10_BIN_EDGES: Tuple[float, ...] = (
    float("-inf"),
    -10.0,
    -5.0,
    0.0,
    5.0,
    10.0,
    15.0,
    float("inf"),
)

RSI14_BIN_EDGES: Tuple[float, ...] = (
    float("-inf"),
    30.0,
    35.0,
    40.0,
    45.0,
    50.0,
    55.0,
    60.0,
    70.0,
    float("inf"),
)

# Ranking formula (transparent, no ML):
# eligible rows require N >= 20, then sort by:
#   1) winrate DESC
#   2) avg_return DESC
#   3) median_return DESC
#   4) N DESC
MIN_RANK_N = 20


def load_lifecycle_dataframe() -> pd.DataFrame:
    """Read canonical lifecycle via the earning-learning storage abstraction."""
    from modules.earning_learning import get_pattern_lifecycle

    df = get_pattern_lifecycle()
    return df.copy() if df is not None else pd.DataFrame()


def _format_bucket_label(left: float, right: float) -> str:
    if np.isneginf(left):
        return f"< {right:g}"
    if np.isposinf(right):
        return f"> {left:g}"
    return f"{left:g} → {right:g}"


def bucket_values(
    values: pd.Series,
    edges: Sequence[float],
) -> pd.Series:
    """
    Assign bucket labels with [left inclusive, right exclusive) intervals.

    The penultimate finite bucket includes its upper edge (e.g. 15 in ``10 → 15``).
    The final bucket is strictly ``> last_finite_edge``.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    labels = pd.Series(index=values.index, dtype="object")
    edge_list = list(edges)
    if len(edge_list) < 3:
        return labels

    last_finite = edge_list[-2]

    for idx, value in numeric.items():
        if pd.isna(value):
            continue
        assigned = False
        for i in range(len(edge_list) - 2):
            left = edge_list[i]
            right = edge_list[i + 1]
            penultimate_bucket = np.isfinite(right) and np.isposinf(edge_list[i + 2])

            if np.isneginf(left):
                if value < right:
                    labels[idx] = _format_bucket_label(left, right)
                    assigned = True
                    break
                continue

            if penultimate_bucket:
                if left <= value <= right:
                    labels[idx] = _format_bucket_label(left, right)
                    assigned = True
                    break
            elif left <= value < right:
                labels[idx] = _format_bucket_label(left, right)
                assigned = True
                break

        if not assigned and value > last_finite:
            labels[idx] = _format_bucket_label(last_finite, edge_list[-1])

    return labels


def evidence_label(n: int) -> str:
    if n < 20:
        return "INSUFFICIENT"
    if n < 50:
        return "EARLY"
    if n < 100:
        return "MODERATE"
    return "STRONGER EVIDENCE"


def filter_window(lifecycle: pd.DataFrame, window: WindowMode) -> pd.DataFrame:
    if lifecycle is None or lifecycle.empty:
        return pd.DataFrame()
    if window != "recent_20":
        return lifecycle.copy()

    date_col = "trade_date" if "trade_date" in lifecycle.columns else "entry_date"
    if date_col not in lifecycle.columns:
        return lifecycle.copy()

    dates = (
        pd.to_datetime(lifecycle[date_col], errors="coerce")
        .dropna()
        .sort_values()
        .dt.strftime("%Y-%m-%d")
        .unique()
        .tolist()
    )
    keep = set(dates[-20:])
    out = lifecycle.copy()
    out["_window_date"] = pd.to_datetime(out[date_col], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    return out[out["_window_date"].isin(keep)].drop(columns=["_window_date"])


def _horizon_frame(lifecycle: pd.DataFrame, horizon_key: str) -> pd.DataFrame:
    return_col, _ = HORIZONS[horizon_key]
    if lifecycle is None or lifecycle.empty or return_col not in lifecycle.columns:
        return pd.DataFrame()

    frame = lifecycle.copy()
    frame["_return_pct"] = pd.to_numeric(frame[return_col], errors="coerce")
    frame = frame[frame["_return_pct"].notna()].copy()
    if frame.empty:
        return frame

    for col in FEATURE_COLUMNS:
        frame[col] = pd.to_numeric(frame.get(col), errors="coerce")

    frame["_win"] = frame["_return_pct"] > 0
    frame["rs5_bucket"] = bucket_values(frame["rs5"], RS5_RS10_BIN_EDGES)
    frame["rs10_bucket"] = bucket_values(frame["rs10"], RS5_RS10_BIN_EDGES)
    frame["rsi14_bucket"] = bucket_values(frame["rsi14"], RSI14_BIN_EDGES)
    return frame


def _aggregate_group(
    group: pd.DataFrame,
    *,
    rs5_label: str,
    rs10_label: str,
    rsi14_label: str,
) -> Dict[str, Any]:
    returns = group["_return_pct"]
    n = int(len(group))
    wins = int(group["_win"].sum())
    losses = n - wins
    winrate = round(wins / n * 100.0, 2) if n else np.nan
    return {
        "RS5 Range": rs5_label,
        "RS10 Range": rs10_label,
        "RSI14 Range": rsi14_label,
        "N": n,
        "Wins": wins,
        "Losses": losses,
        "Winrate": winrate,
        "Avg Return": round(float(returns.mean()), 4) if n else np.nan,
        "Median Return": round(float(returns.median()), 4) if n else np.nan,
        "Min Return": round(float(returns.min()), 4) if n else np.nan,
        "Max Return": round(float(returns.max()), 4) if n else np.nan,
        "Evidence": evidence_label(n),
    }


def single_factor_statistics(
    lifecycle: pd.DataFrame,
    *,
    window: WindowMode = "all",
) -> Dict[str, pd.DataFrame]:
    """Bucket-level stats for RS5, RS10, RSI14 on each horizon."""
    scoped = filter_window(lifecycle, window)
    output: Dict[str, pd.DataFrame] = {}

    factor_buckets = {
        "rs5": ("rs5_bucket", "RS5 Range"),
        "rs10": ("rs10_bucket", "RS10 Range"),
        "rsi14": ("rsi14_bucket", "RSI14 Range"),
    }

    for horizon_key in HORIZONS:
        frame = _horizon_frame(scoped, horizon_key)
        rows: List[Dict[str, Any]] = []
        if frame.empty:
            output[horizon_key] = pd.DataFrame()
            continue

        for factor, (bucket_col, label_col) in factor_buckets.items():
            valid = frame[frame[factor].notna() & frame[bucket_col].notna()].copy()
            if valid.empty:
                continue
            grouped = valid.groupby(bucket_col, sort=False, dropna=True)
            for bucket_label, group in grouped:
                row = _aggregate_group(
                    group,
                    rs5_label=str(bucket_label) if label_col == "RS5 Range" else "",
                    rs10_label=str(bucket_label) if label_col == "RS10 Range" else "",
                    rsi14_label=str(bucket_label) if label_col == "RSI14 Range" else "",
                )
                row["Factor"] = factor.upper()
                row[label_col] = str(bucket_label)
                rows.append(row)

        output[horizon_key] = pd.DataFrame(rows)

    return output


def combined_statistics(
    lifecycle: pd.DataFrame,
    *,
    window: WindowMode = "all",
) -> Dict[str, pd.DataFrame]:
    """RS5 × RS10 × RSI14 combination stats per horizon."""
    scoped = filter_window(lifecycle, window)
    output: Dict[str, pd.DataFrame] = {}

    for horizon_key in HORIZONS:
        frame = _horizon_frame(scoped, horizon_key)
        if frame.empty:
            output[horizon_key] = pd.DataFrame()
            continue

        valid = frame[
            frame["rs5"].notna()
            & frame["rs10"].notna()
            & frame["rsi14"].notna()
            & frame["rs5_bucket"].notna()
            & frame["rs10_bucket"].notna()
            & frame["rsi14_bucket"].notna()
        ].copy()
        if valid.empty:
            output[horizon_key] = pd.DataFrame()
            continue

        rows: List[Dict[str, Any]] = []
        grouped = valid.groupby(
            ["rs5_bucket", "rs10_bucket", "rsi14_bucket"],
            sort=False,
            dropna=True,
        )
        for (rs5_b, rs10_b, rsi_b), group in grouped:
            rows.append(
                _aggregate_group(
                    group,
                    rs5_label=str(rs5_b),
                    rs10_label=str(rs10_b),
                    rsi14_label=str(rsi_b),
                )
            )
        output[horizon_key] = pd.DataFrame(rows)

    return output


def rank_top_sweetspots(
    combined: pd.DataFrame,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Rank combination rows with transparent sort keys.

    Ranking formula:
      eligible when N >= 20
      sort by Winrate DESC, Avg Return DESC, Median Return DESC, N DESC
    """
    if combined is None or combined.empty:
        return pd.DataFrame()

    eligible = combined[combined["N"] >= MIN_RANK_N].copy()
    if eligible.empty:
        return pd.DataFrame()

    ranked = eligible.sort_values(
        ["Winrate", "Avg Return", "Median Return", "N"],
        ascending=[False, False, False, False],
        kind="stable",
    )
    keep_cols = [
        "RS5 Range",
        "RS10 Range",
        "RSI14 Range",
        "N",
        "Winrate",
        "Avg Return",
        "Median Return",
        "Evidence",
    ]
    return ranked[keep_cols].head(max(1, int(top_n))).reset_index(drop=True)


def data_coverage(lifecycle: pd.DataFrame, *, window: WindowMode = "all") -> Dict[str, Any]:
    scoped = filter_window(lifecycle, window)
    date_col = "trade_date" if "trade_date" in scoped.columns else "entry_date"
    t0_dates = 0
    if date_col in scoped.columns and not scoped.empty:
        t0_dates = int(
            pd.to_datetime(scoped[date_col], errors="coerce").dropna().dt.normalize().nunique()
        )

    counts = {}
    for horizon_key, (return_col, _) in HORIZONS.items():
        if scoped.empty or return_col not in scoped.columns:
            counts[horizon_key] = 0
        else:
            counts[horizon_key] = int(pd.to_numeric(scoped[return_col], errors="coerce").notna().sum())

    return {
        "window": window,
        "t0_dates": t0_dates,
        "T3": counts.get("T3", 0),
        "T5": counts.get("T5", 0),
        "T10": counts.get("T10", 0),
        "observations": int(len(scoped)),
    }


def analyze_sweetspots(
    lifecycle: pd.DataFrame,
    *,
    window: WindowMode = "all",
    top_n: int = 10,
) -> Dict[str, Any]:
    """
    Full read-only analysis bundle.

    Does not mutate ``lifecycle``.
    """
    source_id = id(lifecycle)
    combined = combined_statistics(lifecycle, window=window)
    singles = single_factor_statistics(lifecycle, window=window)
    coverage = data_coverage(lifecycle, window=window)

    tops: Dict[str, pd.DataFrame] = {}
    for horizon_key, frame in combined.items():
        tops[horizon_key] = rank_top_sweetspots(frame, top_n=top_n)

    return {
        "window": window,
        "coverage": coverage,
        "single_factor": singles,
        "combined": combined,
        "top_sweetspots": tops,
        "source_unchanged": id(lifecycle) == source_id,
    }


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for col in ("Winrate", "Avg Return", "Median Return"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda x: f"{x:.2f}" if pd.notna(x) else "—"
            )
    return out


def render_sweetspot_research_panel() -> Dict[str, Any]:
    """
    Streamlit read-only research panel.

    Independent from BOT Learning Insight — no writes, no decision influence.
    """
    import streamlit as st

    st.caption(
        "Read-only lifecycle statistics. Recomputed from historical T0 RS/RSI features "
        "and matured T3/T5/T10 returns. Does not modify learning memory or recommendations."
    )

    try:
        lifecycle = load_lifecycle_dataframe()
    except Exception as exc:
        st.info("Sweetspot research unavailable — lifecycle read failed safely.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc)}

    if lifecycle.empty:
        st.info("No lifecycle observations available yet.")
        return {"ok": True, "status": "EMPTY"}

    window_label = st.radio(
        "Window",
        options=["ALL HISTORY", "RECENT 20 T0 DATES"],
        index=0,
        horizontal=True,
        key="sweetspot_window_selector",
    )
    window: WindowMode = "recent_20" if window_label.startswith("RECENT") else "all"

    analysis = analyze_sweetspots(lifecycle, window=window, top_n=10)
    coverage = analysis["coverage"]

    st.markdown("**DATA COVERAGE**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("T0 dates", f"{coverage['t0_dates']:,}")
    with c2:
        st.metric("T3 N", f"{coverage['T3']:,}")
    with c3:
        st.metric("T5 N", f"{coverage['T5']:,}")
    with c4:
        st.metric("T10 N", f"{coverage['T10']:,}")

    st.caption(
        "Ranking formula (N ≥ 20 only): Winrate DESC → Avg Return DESC → "
        "Median Return DESC → N DESC. Win = return > 0."
    )

    for horizon in ("T3", "T5", "T10"):
        st.markdown(f"**TOP SWEETSPOTS — {horizon}**")
        top = analysis["top_sweetspots"].get(horizon, pd.DataFrame())
        if top.empty:
            st.caption(f"No ranked {horizon} combinations with N ≥ {MIN_RANK_N}.")
        else:
            st.dataframe(_display_table(top.head(10)), use_container_width=True, hide_index=True)

    with st.expander("Single-Factor Detail", expanded=False):
        singles = analysis["single_factor"]
        for horizon in ("T3", "T5", "T10"):
            st.markdown(f"**{horizon}**")
            frame = singles.get(horizon, pd.DataFrame())
            if frame.empty:
                st.caption("No data.")
            else:
                for factor in ("RS5", "RS10", "RSI14"):
                    sub = frame[frame["Factor"] == factor].copy()
                    if sub.empty:
                        continue
                    st.markdown(f"*{factor}*")
                    show_cols = [
                        c
                        for c in [
                            "RS5 Range",
                            "RS10 Range",
                            "RSI14 Range",
                            "N",
                            "Winrate",
                            "Avg Return",
                            "Median Return",
                            "Min Return",
                            "Max Return",
                            "Evidence",
                        ]
                        if c in sub.columns and sub[c].astype(str).str.strip().ne("").any()
                    ]
                    st.dataframe(
                        _display_table(sub[show_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

    return {"ok": True, "window": window, "coverage": coverage}


__all__ = [
    "HORIZONS",
    "MIN_RANK_N",
    "RS5_RS10_BIN_EDGES",
    "RSI14_BIN_EDGES",
    "analyze_sweetspots",
    "bucket_values",
    "combined_statistics",
    "data_coverage",
    "evidence_label",
    "filter_window",
    "load_lifecycle_dataframe",
    "rank_top_sweetspots",
    "render_sweetspot_research_panel",
    "single_factor_statistics",
]
