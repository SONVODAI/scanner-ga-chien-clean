"""
Evolution Health Engine
=======================

Module độc lập tạo:
- Evolution Health Score
- Nhóm sức khỏe cổ phiếu
- Hành động gợi ý
- Lý do ngắn
- Earning Money Board

Thiết kế:
- Chỉ dùng dữ liệu đã có trong ``scan_df``.
- Không tải dữ liệu, không phụ thuộc scanner chính.
- Không sửa trực tiếp DataFrame đầu vào.
- Có thể import thẳng vào ``app.py``.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd


HEALTH_ORDER: Final[dict[str, int]] = {
    "🌱 ĐANG HỒI": 0,
    "🟡 TRUNG TÍNH": 1,
    "🔴 YẾU": 2,
    "⚠️ YẾU DẦN": 3,
    "⛔ RẤT YẾU": 4,
}

ACTION_BY_GROUP: Final[dict[str, str]] = {
    "🌱 ĐANG HỒI": "🟢 MUA / GIỮ",
    "🟡 TRUNG TÍNH": "👀 THEO DÕI",
    "🔴 YẾU": "⏳ CHỜ",
    "⚠️ YẾU DẦN": "🟠 HẠN CHẾ / GIẢM",
    "⛔ RẤT YẾU": "🔴 TRÁNH / BÁN",
}

HEALTH_STYLE: Final[dict[str, str]] = {
    "🌱 ĐANG HỒI": "background-color:#d9ead3;color:#1b4332;font-weight:700",
    "🟡 TRUNG TÍNH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
    "🔴 YẾU": "background-color:#fce5cd;color:#9c5700;font-weight:700",
    "⚠️ YẾU DẦN": "background-color:#f4cccc;color:#990000;font-weight:700",
    "⛔ RẤT YẾU": "background-color:#d9d9d9;color:#333333;font-weight:700",
}

HEALTH_OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "evolution_health_score",
    "evolution_health_group",
    "evolution_health_rank",
    "evolution_action",
    "evolution_reason",
)

BOARD_COLUMNS: Final[tuple[str, ...]] = (
    "evolution_health_group",
    "symbol",
    "price",
    "rs5",
    "rs10",
    "rsi14",
    "evolution_action",
    "evolution_reason",
)

BOARD_RENAME: Final[dict[str, str]] = {
    "evolution_health_group": "Health",
    "symbol": "Mã",
    "price": "Giá",
    "rs5": "RS5",
    "rs10": "RS10",
    "rsi14": "RSI14",
    "evolution_action": "Action",
    "evolution_reason": "Why",
}

_REASON_COMPONENTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("_health_rs", "RS mạnh", "RS yếu"),
    ("_health_ema", "Xu hướng lên", "Xu hướng giảm"),
    ("_health_obv", "OBV tốt", "OBV xấu"),
    ("_health_rsi", "RSI cải thiện", "RSI yếu"),
    ("_health_volume", "Vol xác nhận", "Vol chưa xác nhận"),
    ("_health_position", "Vị trí giá tốt", "Giá lệch xu hướng"),
    ("_health_pattern", "Mẫu hồi đẹp", "Thiếu mẫu xác nhận"),
)


def _validate_dataframe(scan_df: pd.DataFrame) -> None:
    if not isinstance(scan_df, pd.DataFrame):
        raise TypeError("scan_df phải là pandas DataFrame")


def _num(series: pd.Series | None, index: pd.Index) -> pd.Series:
    """Đưa cột về numeric; cột thiếu được thay bằng NaN cùng index."""
    if series is None:
        return pd.Series(np.nan, index=index, dtype="float64")
    return pd.to_numeric(series, errors="coerce").reindex(index)


def _bool(series: pd.Series | None, index: pd.Index) -> pd.Series:
    """Chuẩn hóa boolean hoặc chuỗi tín hiệu về True/False."""
    if series is None:
        return pd.Series(False, index=index, dtype="bool")

    values = series.reindex(index)
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)

    true_values = {
        "1", "true", "yes", "y", "có", "co", "green", "early",
        "🟢", "✅", "🌱",
    }
    return (
        values.astype(str)
        .str.strip()
        .str.lower()
        .isin(true_values)
    )


def _clip01(values: pd.Series) -> pd.Series:
    return values.clip(lower=0.0, upper=1.0)


def _scale_centered(
    values: pd.Series,
    center: float,
    width: float,
) -> pd.Series:
    """
    Chuẩn hóa tuyến tính:
    center - width -> 0
    center         -> 0.5
    center + width -> 1
    """
    safe_width = max(float(width), 1e-9)
    return _clip01(0.5 + (values - center) / (2.0 * safe_width))


def _obv_score(df: pd.DataFrame) -> pd.Series:
    """Chấm OBV từ ``obv_status``; thiếu dữ liệu được coi là trung tính."""
    index = df.index
    if "obv_status" not in df.columns:
        return pd.Series(0.5, index=index, dtype="float64")

    values = df["obv_status"]
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(float)

    text = values.astype(str).str.upper().str.strip()
    positive = text.str.contains(
        "TỐT|MANH|MẠNH|TANG|TĂNG|GIU|GIỮ|DUONG|DƯƠNG|OK|GREEN|🟢",
        regex=True,
    )
    negative = text.str.contains(
        "GAY|GÃY|XAU|XẤU|GIAM|GIẢM|AM|ÂM|YEU|YẾU|RED|🔴",
        regex=True,
    )

    score = pd.Series(0.5, index=index, dtype="float64")
    score.loc[positive] = 1.0
    score.loc[negative] = 0.0

    numeric = pd.to_numeric(values, errors="coerce")
    valid_numeric = numeric.notna()
    score.loc[valid_numeric] = numeric.loc[valid_numeric].clip(0, 1)
    return score


def _volume_score(df: pd.DataFrame) -> pd.Series:
    """
    Chấm tỷ lệ volume/MA20 theo dạng tam giác, tốt nhất quanh 1.05.
    Thiếu dữ liệu không bị phạt.
    """
    index = df.index
    volume = _num(df.get("volume"), index)
    vol_ma20 = _num(df.get("vol_ma20"), index)
    ratio = volume / vol_ma20.replace(0, np.nan)

    score = 1.0 - (ratio - 1.05).abs() / 1.05
    return score.clip(0, 1).fillna(0.5)


def _position_score(df: pd.DataFrame) -> pd.Series:
    """Chấm vị trí giá so với EMA9 và đỉnh 20 phiên."""
    index = df.index
    dist_ema = _num(df.get("dist_from_ema9_pct"), index)

    ema_score = 1.0 - (dist_ema - 1.5).abs() / 10.0
    ema_score = ema_score.clip(0, 1).fillna(0.5)

    if "dist_high20_pct" not in df.columns:
        return ema_score

    dist_high = _num(df.get("dist_high20_pct"), index)
    high_score = _scale_centered(
        dist_high,
        center=-8.0,
        width=12.0,
    ).fillna(0.5)
    return 0.75 * ema_score + 0.25 * high_score


def _technical_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo các điểm thành phần 0-100 từ dữ liệu sẵn có."""
    index = df.index

    rsi14 = _num(df.get("rsi14"), index)
    rsi_slope = _num(df.get("rsi_slope"), index)
    ema_slope = _num(df.get("ema9_ma20_slope"), index)
    ema_slope_change = _num(df.get("ema9_ma20_slope_change"), index)
    rs5 = _num(df.get("rs5"), index)
    rs10 = _num(df.get("rs10"), index)

    rsi_level = (1.0 - (rsi14 - 58.0).abs() / 35.0).clip(0, 1).fillna(0.5)
    rsi_trend = _scale_centered(rsi_slope, center=0.0, width=5.0).fillna(0.5)
    rsi_score = 0.65 * rsi_level + 0.35 * rsi_trend

    ema_now = _scale_centered(ema_slope, center=0.0, width=4.0).fillna(0.5)
    ema_change = _scale_centered(
        ema_slope_change,
        center=0.0,
        width=2.5,
    ).fillna(0.5)
    ema_score = 0.72 * ema_now + 0.28 * ema_change

    rs5_score = _scale_centered(rs5, center=0.0, width=12.0).fillna(0.5)
    rs10_score = _scale_centered(rs10, center=0.0, width=12.0).fillna(0.5)
    rs_accel = _scale_centered(rs5 - rs10, center=0.0, width=8.0).fillna(0.5)
    rs_score = 0.42 * rs5_score + 0.28 * rs10_score + 0.30 * rs_accel

    pattern_score = (
        _bool(df.get("green_2_confirm"), index).astype(float) * 0.40
        + _bool(df.get("early_green2"), index).astype(float) * 0.30
        + _bool(df.get("early_dry_green2"), index).astype(float) * 0.30
    )
    pattern_score = 0.35 + 0.65 * pattern_score

    scores = pd.DataFrame(
        {
            "_health_rsi": rsi_score * 100,
            "_health_ema": ema_score * 100,
            "_health_obv": _obv_score(df) * 100,
            "_health_rs": rs_score * 100,
            "_health_volume": _volume_score(df) * 100,
            "_health_position": _position_score(df) * 100,
            "_health_pattern": pattern_score * 100,
        },
        index=index,
    )
    return scores.clip(0, 100)


def _assign_group(score: pd.Series, weakening: pd.Series) -> pd.Series:
    """Phân nhóm Health theo điểm và trạng thái suy yếu đồng thuận."""
    group = pd.Series("🔴 YẾU", index=score.index, dtype="object")
    group.loc[score >= 68] = "🌱 ĐANG HỒI"
    group.loc[(score >= 54) & (score < 68)] = "🟡 TRUNG TÍNH"
    group.loc[(score >= 40) & (score < 54)] = "🔴 YẾU"
    group.loc[(score >= 27) & (score < 40)] = "⚠️ YẾU DẦN"
    group.loc[score < 27] = "⛔ RẤT YẾU"

    group.loc[
        weakening
        & (score >= 27)
        & (score < 54)
    ] = "⚠️ YẾU DẦN"
    return group


def _build_reason(row: pd.Series) -> str:
    """Tạo lý do ngắn, tối đa ba ý."""
    positives: list[tuple[float, str]] = []
    negatives: list[tuple[float, str]] = []

    for column, positive_text, negative_text in _REASON_COMPONENTS:
        value = pd.to_numeric(
            pd.Series([row.get(column)]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(value):
            continue
        if value >= 65:
            positives.append((float(value), positive_text))
        elif value <= 38:
            negatives.append((float(value), negative_text))

    positives.sort(key=lambda item: item[0], reverse=True)
    negatives.sort(key=lambda item: item[0])

    group = str(row.get("evolution_health_group", ""))
    if group in {"🌱 ĐANG HỒI", "🟡 TRUNG TÍNH"}:
        selected = [text for _, text in positives[:3]]
        if len(selected) < 2:
            selected += [text for _, text in negatives[: 2 - len(selected)]]
    else:
        selected = [text for _, text in negatives[:3]]
        if len(selected) < 2:
            selected += [text for _, text in positives[: 2 - len(selected)]]

    if not selected:
        return "Chưa đủ tín hiệu rõ"
    return " + ".join(dict.fromkeys(selected))


def _empty_result(scan_df: pd.DataFrame) -> pd.DataFrame:
    out = scan_df.copy()
    out["evolution_health_score"] = pd.Series(index=out.index, dtype="float64")
    out["evolution_health_group"] = pd.Series(index=out.index, dtype="object")
    out["evolution_health_rank"] = pd.Series(index=out.index, dtype="int64")
    out["evolution_action"] = pd.Series(index=out.index, dtype="object")
    out["evolution_reason"] = pd.Series(index=out.index, dtype="object")
    return out


def add_evolution_health(scan_df: pd.DataFrame) -> pd.DataFrame:
    """
    Thêm Evolution Health vào ``scan_df`` và trả về bản đã sắp xếp.

    Hàm không sửa trực tiếp DataFrame đầu vào.
    """
    _validate_dataframe(scan_df)
    if scan_df.empty:
        return _empty_result(scan_df)

    out = scan_df.copy()
    scores = _technical_scores(out)

    health_score = (
        scores["_health_rs"] * 0.24
        + scores["_health_ema"] * 0.20
        + scores["_health_obv"] * 0.18
        + scores["_health_rsi"] * 0.15
        + scores["_health_volume"] * 0.08
        + scores["_health_position"] * 0.09
        + scores["_health_pattern"] * 0.06
    )

    index = out.index
    ema_slope = _num(out.get("ema9_ma20_slope"), index)
    ema_change = _num(out.get("ema9_ma20_slope_change"), index)
    rsi_slope = _num(out.get("rsi_slope"), index)
    rs5 = _num(out.get("rs5"), index)
    rs10 = _num(out.get("rs10"), index)

    weakening_votes = (
        (ema_slope < 0).astype(int)
        + (ema_change < 0).astype(int)
        + (rsi_slope < 0).astype(int)
        + (rs5 < rs10).astype(int)
        + (rs5 < 0).astype(int)
    )
    weakening = weakening_votes >= 3

    out = pd.concat([out, scores], axis=1)
    out["evolution_health_score"] = health_score.round(1)
    out["evolution_health_group"] = _assign_group(
        out["evolution_health_score"],
        weakening,
    )
    out["evolution_health_rank"] = (
        out["evolution_health_group"]
        .map(HEALTH_ORDER)
        .fillna(99)
        .astype(int)
    )
    out["evolution_action"] = (
        out["evolution_health_group"]
        .map(ACTION_BY_GROUP)
        .fillna("👀 THEO DÕI")
    )
    out["evolution_reason"] = out.apply(_build_reason, axis=1)

    sort_columns = ["evolution_health_rank", "evolution_health_score"]
    ascending = [True, False]

    for column, direction in (
        ("rs5", False),
        ("rs10", False),
        ("symbol", True),
    ):
        if column in out.columns:
            sort_columns.append(column)
            ascending.append(direction)

    return (
        out.sort_values(
            sort_columns,
            ascending=ascending,
            na_position="last",
            kind="stable",
        )
        .reset_index(drop=True)
    )


def get_earning_money_board(scan_df: pd.DataFrame) -> pd.DataFrame:
    """Trả về board điều khiển gọn đã chốt."""
    _validate_dataframe(scan_df)

    required = {
        "evolution_health_score",
        "evolution_health_group",
        "evolution_action",
        "evolution_reason",
    }
    enriched = (
        scan_df
        if required.issubset(scan_df.columns)
        else add_evolution_health(scan_df)
    )

    available_columns = [
        column for column in BOARD_COLUMNS
        if column in enriched.columns
    ]
    return (
        enriched.loc[:, available_columns]
        .copy()
        .rename(columns=BOARD_RENAME)
        .reset_index(drop=True)
    )


def render_earning_money_board(
    scan_df: pd.DataFrame,
    *,
    title: str = "🏆 EARNING MONEY BOARD",
    height: int = 720,
) -> pd.DataFrame:
    """
    Render Streamlit khi được gọi trong app.
    Luôn trả về DataFrame để có thể test hoặc export.
    """
    
    board = get_earning_money_board(scan_df)

    # Learning persistence: canonical path is app.py update_learning(scan_df,
    # market_context=...) after RSI breadth is available.
    try:
        import streamlit as st
    except ImportError:
        return board

    st.markdown("---")
    st.markdown(f"## {title}")

    def style_health(value: object) -> str:
        return HEALTH_STYLE.get(str(value), "")

    styled = board.style.map(style_health, subset=["Health"])
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=height,
    )
    return board


def export_earning_money_board_csv(scan_df: pd.DataFrame) -> bytes:
    """Xuất Earning Money Board thành CSV UTF-8 BOM."""
    return (
        get_earning_money_board(scan_df)
        .to_csv(index=False)
        .encode("utf-8-sig")
    )


__all__ = [
    "HEALTH_ORDER",
    "add_evolution_health",
    "get_earning_money_board",
    "render_earning_money_board",
    "export_earning_money_board_csv",
]
