"""
Mr.BOT PRO V4.0
Leader Brain Dashboard
======================

Pure Streamlit UI module for Leader Memory V5.

Principles
----------
- Read-only UI: does not modify leader_memory.py.
- Uses the public API exposed by modules.leader_memory.
- Defensive against empty DataFrames and missing columns.
- Safe to import: backend import errors are shown inside the UI.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------
# Backend import
# ---------------------------------------------------------------------

_BACKEND_IMPORT_ERROR: Optional[Exception] = None

try:
    from final_decision_engine import format_display_number
except Exception:  # pragma: no cover - fallback if engine unavailable at import
    format_display_number = None

try:
    from leader_memory import (
        get_active_leaders,
        get_engine_status,
        get_intelligence_tables,
        load_hall_of_fame,
        load_memory,
        load_pattern_library,
        load_recommendations,
    )
except Exception as exc:  # pragma: no cover - displayed in Streamlit
    _BACKEND_IMPORT_ERROR = exc


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

BOARD_TITLE = "🧠 LEADER BRAIN DASHBOARD"
BOARD_SUBTITLE = (
    "Trung tâm quan sát Leader, mẫu hình chiến thắng và khuyến nghị AI "
    "từ bộ nhớ học tập của Mr.BOT."
)

ACTION_ORDER = [
    "ƯU TIÊN CAO",
    "THEO DÕI MUA",
    "THEO DÕI",
    "CHƯA HÀNH ĐỘNG",
    "TRÁNH / CHỜ PHỤC HỒI",
]

LEVEL_ORDER = [
    "👑 SIÊU LEADER",
    "⭐⭐⭐⭐⭐ LEADER A+",
    "⭐⭐⭐⭐ LEADER A",
    "⭐⭐⭐ LEADER B",
    "⭐⭐ THEO DÕI",
    "⭐ CHƯA ĐỦ CHẤT LƯỢNG",
]

PREFERRED_ACTIVE_COLUMNS = [
    "symbol",
    "leader_level",
    "leader_score",
    "confidence_score",
    "persistence_20_pct",
    "current_group",
    "current_price",
    "current_rs5",
    "current_rs10",
    "current_rsi14",
    "current_obv_status",
    "winrate_t5_pct",
    "avg_return_t5_pct",
    "recommendation",
    "recommendation_reason",
]

PREFERRED_RECOMMENDATION_COLUMNS = [
    "rank",
    "symbol",
    "recommendation",
    "confidence_score",
    "leader_score",
    "leader_level",
    "current_group",
    "current_price",
    "current_rs5",
    "current_rs10",
    "current_rsi14",
    "current_obv_status",
    "winrate_t5_pct",
    "avg_return_t5_pct",
    "pattern_match_score",
    "matched_pattern_id",
    "reason",
]

PREFERRED_HOF_COLUMNS = [
    "rank",
    "symbol",
    "leader_score",
    "leader_level",
    "confidence_score",
    "appearances",
    "persistence_20_pct",
    "best_score",
    "winrate_t5_pct",
    "avg_return_t5_pct",
    "winrate_t10_pct",
    "avg_return_t10_pct",
    "best_return_pct",
    "worst_drawdown_pct",
    "first_seen",
    "last_seen",
]

PREFERRED_PATTERN_COLUMNS = [
    "pattern_id",
    "pattern_level",
    "pattern_score",
    "market_regime",
    "sample_count",
    "symbols_count",
    "avg_entry_score",
    "avg_rs5",
    "avg_rs10",
    "avg_rsi14",
    "obv_up_rate_pct",
    "winrate_t3_pct",
    "avg_return_t3_pct",
    "winrate_t5_pct",
    "avg_return_t5_pct",
    "winrate_t10_pct",
    "avg_return_t10_pct",
    "feature_signature",
]


# ---------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------

def _safe_dataframe(value: Any) -> pd.DataFrame:
    """Return a copy when value is a DataFrame, otherwise an empty DataFrame."""
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame()


def _existing_columns(df: pd.DataFrame, preferred: Sequence[str]) -> List[str]:
    return [col for col in preferred if col in df.columns]


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _safe_mean(df: pd.DataFrame, column: str) -> float:
    series = _numeric(df, column).dropna()
    return float(series.mean()) if not series.empty else np.nan


def _safe_max(df: pd.DataFrame, column: str) -> float:
    series = _numeric(df, column).dropna()
    return float(series.max()) if not series.empty else np.nan


def _safe_count(df: pd.DataFrame, column: str, values: Iterable[str]) -> int:
    if column not in df.columns:
        return 0
    allowed = {str(v).strip().upper() for v in values}
    series = df[column].astype(str).str.strip().str.upper()
    return int(series.isin(allowed).sum())


def _fmt_number(value: Any, digits: int = 1, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(number):
        return "—"
    if format_display_number is not None:
        formatted = format_display_number(number, max_decimals=digits, prefer_int=True)
        return f"{formatted}{suffix}" if formatted else "—"
    return f"{number:,.{digits}f}{suffix}"


def _fmt_int(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if not np.isfinite(number):
        return "0"
    return f"{int(round(number)):,}"


def _sort_if_possible(
    df: pd.DataFrame,
    columns: Sequence[str],
    ascending: Sequence[bool],
) -> pd.DataFrame:
    usable = [(col, asc) for col, asc in zip(columns, ascending) if col in df.columns]
    if not usable:
        return df
    sort_cols = [item[0] for item in usable]
    sort_asc = [item[1] for item in usable]
    return df.sort_values(sort_cols, ascending=sort_asc, kind="stable")


def _clean_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Presentation-only cleanup; underlying tables keep full numeric precision."""
    result = df.copy()

    int_tokens = (
        "sample",
        "samples",
        "count",
        "rank",
        "appearance",
    )
    score_tokens = (
        "score",
        "pct",
        "return",
        "rs5",
        "rs10",
        "rsi14",
        "drawdown",
        "persistence",
        "adjustment",
        "winrate",
        "continuation",
    )
    price_tokens = ("price",)

    for col in result.columns:
        lower = col.lower()
        converted = pd.to_numeric(result[col], errors="coerce")
        if not converted.notna().any():
            continue

        if format_display_number is None:
            if any(token in lower for token in score_tokens + price_tokens):
                result[col] = converted.round(2)
            continue

        if any(token in lower for token in int_tokens):
            result[col] = converted.map(
                lambda v: format_display_number(v, max_decimals=0, prefer_int=True)
                if pd.notna(v)
                else None
            )
        elif any(token in lower for token in price_tokens):
            result[col] = converted.map(
                lambda v: format_display_number(v, max_decimals=0, prefer_int=True)
                if pd.notna(v)
                else None
            )
        elif any(token in lower for token in score_tokens):
            result[col] = converted.map(
                lambda v: format_display_number(v, max_decimals=2, prefer_int=True)
                if pd.notna(v)
                else None
            )

    return result.replace({np.nan: None})


def _show_empty(message: str) -> None:
    st.info(message)


def _render_dataframe(
    df: pd.DataFrame,
    preferred_columns: Sequence[str],
    *,
    height: int = 430,
    hide_index: bool = True,
) -> None:
    if df.empty:
        _show_empty("Chưa có dữ liệu để hiển thị.")
        return

    columns = _existing_columns(df, preferred_columns)
    display_df = df[columns].copy() if columns else df.copy()
    display_df = _clean_for_display(display_df)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=hide_index,
        height=height,
    )


# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def _load_dashboard_data() -> Dict[str, Any]:
    """
    Read the public Leader Memory V5 API.

    Cache is deliberately short because the engine may be updated at end of day.
    """
    tables: Dict[str, pd.DataFrame] = {
        "brain": pd.DataFrame(),
        "active_leaders": pd.DataFrame(),
        "recommendations": pd.DataFrame(),
        "hall_of_fame": pd.DataFrame(),
        "patterns": pd.DataFrame(),
    }
    status: Dict[str, Any] = {}
    errors: List[str] = []

    loaders = [
        ("brain", load_memory),
        ("active_leaders", lambda: get_active_leaders(limit=100)),
        ("recommendations", load_recommendations),
        ("hall_of_fame", load_hall_of_fame),
        ("patterns", load_pattern_library),
    ]

    for name, loader in loaders:
        try:
            tables[name] = _safe_dataframe(loader())
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    try:
        status = dict(get_engine_status() or {})
    except Exception as exc:
        errors.append(f"engine_status: {exc}")

    # Prefer the all-in-one API where available, but never let it break the board.
    try:
        intelligence = get_intelligence_tables(
            leader_limit=100,
            pattern_limit=100,
            hof_limit=100,
            recommendation_limit=100,
        )
        if isinstance(intelligence, Mapping):
            mapping = {
                "active_leaders": "active_leaders",
                "ai_recommendation": "recommendations",
                "hall_of_fame": "hall_of_fame",
                "pattern_library": "patterns",
                "brain_score": "brain",
            }
            for source_name, target_name in mapping.items():
                candidate = _safe_dataframe(intelligence.get(source_name))
                if not candidate.empty:
                    tables[target_name] = candidate
    except Exception as exc:
        errors.append(f"intelligence_tables: {exc}")

    return {"tables": tables, "status": status, "errors": errors}


# ---------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------

def _multiselect_values(df: pd.DataFrame, column: str) -> List[str]:
    if column not in df.columns:
        return []
    values = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
    )
    values = values[values != ""]
    return sorted(values.unique().tolist())


def _apply_filters(
    df: pd.DataFrame,
    *,
    symbols: Sequence[str],
    levels: Sequence[str],
    groups: Sequence[str],
    actions: Sequence[str],
    min_leader_score: float,
    min_confidence: float,
) -> pd.DataFrame:
    result = df.copy()

    if symbols and "symbol" in result.columns:
        result = result[result["symbol"].astype(str).isin(symbols)]

    if levels and "leader_level" in result.columns:
        result = result[result["leader_level"].astype(str).isin(levels)]

    if groups:
        group_col = "current_group" if "current_group" in result.columns else "group"
        if group_col in result.columns:
            result = result[result[group_col].astype(str).isin(groups)]

    if actions:
        action_col = "recommendation" if "recommendation" in result.columns else "action"
        if action_col in result.columns:
            result = result[result[action_col].astype(str).isin(actions)]

    if "leader_score" in result.columns:
        result = result[_numeric(result, "leader_score").fillna(-np.inf) >= min_leader_score]

    if "confidence_score" in result.columns:
        result = result[_numeric(result, "confidence_score").fillna(-np.inf) >= min_confidence]

    return result.reset_index(drop=True)


def _render_filters(brain: pd.DataFrame) -> Dict[str, Any]:
    with st.expander("🎛️ Bộ lọc Dashboard", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            symbols = st.multiselect(
                "Mã cổ phiếu",
                options=_multiselect_values(brain, "symbol"),
                default=[],
                key="leader_brain_filter_symbols",
            )
            min_leader_score = st.slider(
                "Leader Score tối thiểu",
                min_value=0,
                max_value=100,
                value=0,
                step=1,
                key="leader_brain_filter_score",
            )

        with col2:
            levels = st.multiselect(
                "Cấp độ Leader",
                options=_multiselect_values(brain, "leader_level"),
                default=[],
                key="leader_brain_filter_levels",
            )
            min_confidence = st.slider(
                "Confidence tối thiểu",
                min_value=0,
                max_value=100,
                value=0,
                step=1,
                key="leader_brain_filter_confidence",
            )

        with col3:
            groups = st.multiselect(
                "Nhóm hiện tại",
                options=_multiselect_values(brain, "current_group"),
                default=[],
                key="leader_brain_filter_groups",
            )
            actions = st.multiselect(
                "Khuyến nghị",
                options=_multiselect_values(brain, "recommendation"),
                default=[],
                key="leader_brain_filter_actions",
            )

    return {
        "symbols": symbols,
        "levels": levels,
        "groups": groups,
        "actions": actions,
        "min_leader_score": float(min_leader_score),
        "min_confidence": float(min_confidence),
    }


# ---------------------------------------------------------------------
# Header and KPI
# ---------------------------------------------------------------------

def _render_header(status: Mapping[str, Any]) -> None:
    title_col, button_col = st.columns([5, 1])

    with title_col:
        st.subheader(BOARD_TITLE)
        st.caption(BOARD_SUBTITLE)

    with button_col:
        if st.button(
            "🔄 Làm mới",
            use_container_width=True,
            key="leader_brain_refresh",
            help="Xóa cache hiển thị và đọc lại dữ liệu từ Leader Memory.",
        ):
            st.cache_data.clear()
            st.rerun()

    engine_name = str(status.get("engine_name", "Mr.BOT Intelligence Center"))
    engine_version = str(status.get("engine_version", "—"))
    schema_version = str(status.get("schema_version", "—"))
    st.caption(
        f"Engine: **{engine_name}** · Version: **{engine_version}** · "
        f"Schema: **{schema_version}**"
    )


def _render_kpis(
    brain: pd.DataFrame,
    recommendations: pd.DataFrame,
    patterns: pd.DataFrame,
    hall_of_fame: pd.DataFrame,
) -> None:
    total_leaders = len(brain)
    priority_count = _safe_count(
        recommendations,
        "recommendation",
        ["ƯU TIÊN CAO", "THEO DÕI MUA"],
    )
    elite_patterns = _safe_count(
        patterns,
        "pattern_level",
        ["🏆 MẪU HÌNH TINH HOA", "⭐⭐⭐⭐ MẪU MẠNH"],
    )
    hof_count = len(hall_of_fame)
    avg_score = _safe_mean(brain, "leader_score")
    avg_confidence = _safe_mean(brain, "confidence_score")

    cols = st.columns(6)
    cols[0].metric("Leader đã học", _fmt_int(total_leaders))
    cols[1].metric("Ưu tiên / Theo dõi mua", _fmt_int(priority_count))
    cols[2].metric("Mẫu mạnh", _fmt_int(elite_patterns))
    cols[3].metric("Hall of Fame", _fmt_int(hof_count))
    cols[4].metric("Leader Score TB", _fmt_number(avg_score, 1))
    cols[5].metric("Confidence TB", _fmt_number(avg_confidence, 1))


# ---------------------------------------------------------------------
# Active Leaders
# ---------------------------------------------------------------------

def _leader_summary_text(df: pd.DataFrame) -> str:
    if df.empty:
        return "Chưa có Leader phù hợp với bộ lọc."

    top = _sort_if_possible(
        df,
        ["leader_score", "confidence_score"],
        [False, False],
    ).iloc[0]

    symbol = str(top.get("symbol", "—"))
    score = _fmt_number(top.get("leader_score"), 1)
    confidence = _fmt_number(top.get("confidence_score"), 1)
    action = str(top.get("recommendation", "Chưa có khuyến nghị"))

    return (
        f"Leader nổi bật hiện tại là **{symbol}**, Leader Score **{score}**, "
        f"Confidence **{confidence}**, trạng thái **{action}**."
    )


def _render_active_leaders(df: pd.DataFrame) -> None:
    st.markdown("### 🟢 Active Leaders")
    st.caption(
        "Các cổ phiếu đang đứng đầu Leader Brain, ưu tiên độ mạnh, độ bền, "
        "hiệu suất lịch sử và độ tin cậy."
    )

    if df.empty:
        _show_empty("Leader Brain chưa có dữ liệu hoặc không có mã phù hợp bộ lọc.")
        return

    ordered = _sort_if_possible(
        df,
        ["leader_score", "confidence_score", "persistence_20_pct"],
        [False, False, False],
    )

    st.info(_leader_summary_text(ordered))
    _render_dataframe(
        ordered,
        PREFERRED_ACTIVE_COLUMNS,
        height=480,
    )


# ---------------------------------------------------------------------
# AI Recommendation
# ---------------------------------------------------------------------

def _recommendation_action_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "recommendation" not in df.columns:
        return pd.DataFrame()

    counts = (
        df["recommendation"]
        .fillna("KHÔNG XÁC ĐỊNH")
        .astype(str)
        .value_counts()
        .rename_axis("Khuyến nghị")
        .reset_index(name="Số mã")
    )

    order_map = {name: idx for idx, name in enumerate(ACTION_ORDER)}
    counts["_order"] = counts["Khuyến nghị"].map(order_map).fillna(999)
    return counts.sort_values(["_order", "Số mã"], ascending=[True, False]).drop(
        columns="_order"
    )


def _render_recommendations(df: pd.DataFrame) -> None:
    st.markdown("### 🤖 AI Recommendation")
    st.caption(
        "Khuyến nghị được xếp hạng từ Leader Score, Confidence và mức độ khớp "
        "với mẫu hình đã học."
    )

    if df.empty:
        _show_empty("Chưa có khuyến nghị AI đủ điều kiện.")
        return

    ordered = _sort_if_possible(
        df,
        ["rank", "leader_score", "confidence_score"],
        [True, False, False],
    )

    left, right = st.columns([2, 5])

    with left:
        counts = _recommendation_action_counts(ordered)
        if not counts.empty:
            st.dataframe(
                counts,
                use_container_width=True,
                hide_index=True,
                height=260,
            )

        best_match = _safe_max(ordered, "pattern_match_score")
        best_win5 = _safe_max(ordered, "winrate_t5_pct")
        st.metric("Pattern Match cao nhất", _fmt_number(best_match, 1, "%"))
        st.metric("Winrate T+5 cao nhất", _fmt_number(best_win5, 1, "%"))

    with right:
        _render_dataframe(
            ordered,
            PREFERRED_RECOMMENDATION_COLUMNS,
            height=440,
        )


# ---------------------------------------------------------------------
# Hall of Fame
# ---------------------------------------------------------------------

def _render_hall_of_fame(df: pd.DataFrame) -> None:
    st.markdown("### 🏆 Hall of Fame")
    st.caption(
        "Các cổ phiếu có thành tích nổi bật và đủ độ bền trong bộ nhớ lịch sử."
    )

    if df.empty:
        _show_empty("Hall of Fame chưa có dữ liệu.")
        return

    ordered = _sort_if_possible(
        df,
        ["rank", "leader_score", "confidence_score"],
        [True, False, False],
    )

    podium = ordered.head(3)
    if not podium.empty:
        podium_cols = st.columns(len(podium))
        medals = ["🥇", "🥈", "🥉"]
        for idx, (_, row) in enumerate(podium.iterrows()):
            with podium_cols[idx]:
                st.metric(
                    f"{medals[idx]} {row.get('symbol', '—')}",
                    _fmt_number(row.get("leader_score"), 1),
                    delta=f"Confidence {_fmt_number(row.get('confidence_score'), 1)}",
                )

    _render_dataframe(
        ordered,
        PREFERRED_HOF_COLUMNS,
        height=430,
    )


# ---------------------------------------------------------------------
# Pattern Library
# ---------------------------------------------------------------------

def _render_patterns(df: pd.DataFrame) -> None:
    st.markdown("### 🧬 Pattern Library")
    st.caption(
        "Kho mẫu hình học được theo RS5/RS10, RSI, OBV, nhóm cổ phiếu, "
        "bối cảnh thị trường và kết quả T+."
    )

    if df.empty:
        _show_empty("Pattern Library chưa có dữ liệu.")
        return

    regime_options = _multiselect_values(df, "market_regime")
    level_options = _multiselect_values(df, "pattern_level")

    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        selected_regimes = st.multiselect(
            "Lọc theo Market Regime",
            options=regime_options,
            default=[],
            key="leader_pattern_regime_filter",
        )

    with col2:
        selected_levels = st.multiselect(
            "Lọc theo cấp mẫu hình",
            options=level_options,
            default=[],
            key="leader_pattern_level_filter",
        )

    with col3:
        min_samples = st.number_input(
            "Số mẫu tối thiểu",
            min_value=0,
            max_value=10000,
            value=0,
            step=1,
            key="leader_pattern_min_samples",
        )

    filtered = df.copy()

    if selected_regimes and "market_regime" in filtered.columns:
        filtered = filtered[
            filtered["market_regime"].astype(str).isin(selected_regimes)
        ]

    if selected_levels and "pattern_level" in filtered.columns:
        filtered = filtered[
            filtered["pattern_level"].astype(str).isin(selected_levels)
        ]

    if "sample_count" in filtered.columns:
        filtered = filtered[
            _numeric(filtered, "sample_count").fillna(0) >= float(min_samples)
        ]

    filtered = _sort_if_possible(
        filtered,
        ["pattern_score", "sample_count", "winrate_t5_pct"],
        [False, False, False],
    )

    if filtered.empty:
        _show_empty("Không có mẫu hình phù hợp bộ lọc.")
        return

    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Số mẫu", _fmt_int(len(filtered)))
    kpi_cols[1].metric(
        "Pattern Score cao nhất",
        _fmt_number(_safe_max(filtered, "pattern_score"), 1),
    )
    kpi_cols[2].metric(
        "Winrate T+5 TB",
        _fmt_number(_safe_mean(filtered, "winrate_t5_pct"), 1, "%"),
    )
    kpi_cols[3].metric(
        "Return T+10 TB",
        _fmt_number(_safe_mean(filtered, "avg_return_t10_pct"), 2, "%"),
    )

    _render_dataframe(
        filtered,
        PREFERRED_PATTERN_COLUMNS,
        height=500,
    )


# ---------------------------------------------------------------------
# Intelligence Summary and system status
# ---------------------------------------------------------------------

def _build_intelligence_summary(
    brain: pd.DataFrame,
    recommendations: pd.DataFrame,
    patterns: pd.DataFrame,
) -> List[str]:
    messages: List[str] = []

    if brain.empty:
        return ["Leader Brain chưa có dữ liệu để tổng hợp."]

    sorted_brain = _sort_if_possible(
        brain,
        ["leader_score", "confidence_score"],
        [False, False],
    )
    top = sorted_brain.iloc[0]

    messages.append(
        "Leader mạnh nhất: "
        f"**{top.get('symbol', '—')}** · Score "
        f"**{_fmt_number(top.get('leader_score'), 1)}** · Confidence "
        f"**{_fmt_number(top.get('confidence_score'), 1)}**."
    )

    priority = _safe_count(
        recommendations,
        "recommendation",
        ["ƯU TIÊN CAO"],
    )
    watch_buy = _safe_count(
        recommendations,
        "recommendation",
        ["THEO DÕI MUA"],
    )
    messages.append(
        f"AI đang xếp **{priority} mã ƯU TIÊN CAO** và "
        f"**{watch_buy} mã THEO DÕI MUA**."
    )

    elite_patterns = _safe_count(
        patterns,
        "pattern_level",
        ["🏆 MẪU HÌNH TINH HOA"],
    )
    strong_patterns = _safe_count(
        patterns,
        "pattern_level",
        ["⭐⭐⭐⭐ MẪU MẠNH"],
    )
    messages.append(
        f"Kho mẫu hình hiện có **{elite_patterns} mẫu tinh hoa** và "
        f"**{strong_patterns} mẫu mạnh**."
    )

    avg_win5 = _safe_mean(brain, "winrate_t5_pct")
    avg_ret5 = _safe_mean(brain, "avg_return_t5_pct")
    if np.isfinite(avg_win5) or np.isfinite(avg_ret5):
        messages.append(
            "Toàn bộ Leader Brain có Winrate T+5 trung bình "
            f"**{_fmt_number(avg_win5, 1, '%')}**, Return T+5 trung bình "
            f"**{_fmt_number(avg_ret5, 2, '%')}**."
        )

    return messages


def _render_status(status: Mapping[str, Any]) -> None:
    files = status.get("files", {})
    if not isinstance(files, Mapping) or not files:
        st.caption("Không đọc được trạng thái file engine.")
        return

    rows = []
    for name, item in files.items():
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Thành phần": name,
                "Tồn tại": bool(item.get("exists", False)),
                "Kích thước (KB)": round(float(item.get("size_bytes", 0)) / 1024, 2),
                "Đường dẫn": str(item.get("path", "")),
            }
        )

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=280,
        )


def _render_intelligence_summary(
    brain: pd.DataFrame,
    recommendations: pd.DataFrame,
    patterns: pd.DataFrame,
    status: Mapping[str, Any],
) -> None:
    st.markdown("### 📡 Intelligence Summary")

    left, right = st.columns([3, 2])

    with left:
        for message in _build_intelligence_summary(
            brain,
            recommendations,
            patterns,
        ):
            st.markdown(f"- {message}")

    with right:
        with st.expander("⚙️ Trạng thái Leader Memory Engine", expanded=False):
            _render_status(status)


# ---------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------

def show_leader_brain() -> None:
    """
    Render the complete Leader Brain Dashboard.

    Usage in app.py
    ---------------
    from modules.leader_brain_board import show_leader_brain

    st.markdown("---")
    show_leader_brain()
    """
    if _BACKEND_IMPORT_ERROR is not None:
        st.error(
            "Không thể import Leader Memory backend. "
            f"Chi tiết: {_BACKEND_IMPORT_ERROR}"
        )
        st.code(
            "from modules.leader_memory import load_memory, "
            "load_pattern_library, load_hall_of_fame, load_recommendations"
        )
        return

    payload = _load_dashboard_data()
    tables = payload.get("tables", {})
    status = payload.get("status", {})
    errors = payload.get("errors", [])

    brain = _safe_dataframe(tables.get("brain"))
    active = _safe_dataframe(tables.get("active_leaders"))
    recommendations = _safe_dataframe(tables.get("recommendations"))
    hall_of_fame = _safe_dataframe(tables.get("hall_of_fame"))
    patterns = _safe_dataframe(tables.get("patterns"))

    _render_header(status)

    if errors:
        with st.expander("⚠️ Một số nguồn dữ liệu chưa đọc được", expanded=False):
            for error in errors:
                st.warning(error)

    _render_kpis(brain, recommendations, patterns, hall_of_fame)

    if brain.empty and active.empty:
        st.warning(
            "Leader Memory chưa có dữ liệu. Dashboard vẫn hoạt động bình thường "
            "và sẽ tự hiển thị sau khi `update_memory()` tạo dữ liệu."
        )
        _render_intelligence_summary(
            brain,
            recommendations,
            patterns,
            status,
        )
        return

    filters = _render_filters(brain)

    filtered_brain = _apply_filters(brain, **filters)
    filtered_active = _apply_filters(active, **filters)
    filtered_recommendations = _apply_filters(recommendations, **filters)
    filtered_hof = _apply_filters(hall_of_fame, **filters)

    # If get_active_leaders() returned no rows, use filtered Leader Brain.
    if filtered_active.empty and not filtered_brain.empty:
        filtered_active = filtered_brain.head(100)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "🟢 Active Leaders",
            "🤖 AI Recommendation",
            "🏆 Hall of Fame",
            "🧬 Pattern Library",
            "📡 Tổng hợp",
        ]
    )

    with tab1:
        _render_active_leaders(filtered_active)

    with tab2:
        _render_recommendations(filtered_recommendations)

    with tab3:
        _render_hall_of_fame(filtered_hof)

    with tab4:
        _render_patterns(patterns)

    with tab5:
        _render_intelligence_summary(
            filtered_brain,
            filtered_recommendations,
            patterns,
            status,
        )


__all__ = ["show_leader_brain"]
