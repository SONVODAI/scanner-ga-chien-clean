from __future__ import annotations

import numpy as np
import pandas as pd
HEALTH_ORDER = {
    "🌱 ĐANG HỒI": 0,
    "🟡 TRUNG TÍNH": 1,
    "🔴 YẾU": 2,
    "⚠️ YẾU DẦN": 3,
    "⛔ RẤT YẾU": 4,
}


def _num(series: pd.Series | None, index: pd.Index) -> pd.Series:
    """Đưa cột về numeric; nếu thiếu cột thì trả về NaN cùng index."""
    if series is None:
        return pd.Series(np.nan, index=index, dtype="float64")
    return pd.to_numeric(series, errors="coerce").reindex(index)


def _bool(series: pd.Series | None, index: pd.Index) -> pd.Series:
    """Chuẩn hóa cột boolean/string về True/False."""
    if series is None:
        return pd.Series(False, index=index, dtype="bool")

    s = series.reindex(index)
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)

    true_values = {
        "1", "true", "yes", "y", "có", "co", "green", "early",
        "🟢", "✅", "🌱",
    }
    return (
        s.astype(str)
        .str.strip()
        .str.lower()
        .isin(true_values)
    )


def _clip01(x: pd.Series) -> pd.Series:
    return x.clip(lower=0.0, upper=1.0)


def _scale_centered(
    x: pd.Series,
    center: float,
    width: float,
) -> pd.Series:
    """
    Chuẩn hóa tuyến tính quanh center:
    center - width => 0
    center         => 0.5
    center + width => 1
    """
    width = max(float(width), 1e-9)
    return _clip01(0.5 + (x - center) / (2.0 * width))


def _obv_score(df: pd.DataFrame) -> pd.Series:
    """
    Ưu tiên dùng obv_status vì đây là cột đã có trong bảng chi tiết.
    Hỗ trợ cả boolean và chuỗi mô tả.
    """
    idx = df.index
    if "obv_status" not in df.columns:
        return pd.Series(0.5, index=idx)

    s = df["obv_status"]

    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(float)

    text = s.astype(str).str.upper().str.strip()

    positive = (
        text.str.contains("TỐT|MANH|MẠNH|TANG|TĂNG|GIU|GIỮ|DUONG|DƯƠNG|OK|GREEN|🟢", regex=True)
    )
    negative = (
        text.str.contains("GAY|GÃY|XAU|XẤU|GIAM|GIẢM|AM|ÂM|YEU|YẾU|RED|🔴", regex=True)
    )

    score = pd.Series(0.5, index=idx, dtype="float64")
    score.loc[positive] = 1.0
    score.loc[negative] = 0.0

    # Trường hợp dữ liệu là 0/1 nhưng lưu dạng text
    numeric = pd.to_numeric(s, errors="coerce")
    score.loc[numeric.notna()] = numeric.loc[numeric.notna()].clip(0, 1)
    return score


def _volume_score(df: pd.DataFrame) -> pd.Series:
    """
    Dùng volume/vol_ma20 nếu có.
    Mục tiêu Health không thưởng cực đoan cho vol quá lớn:
    - 0.65–1.40 lần MA20 là vùng hữu ích.
    - Quá thấp hoặc quá cao đều không được điểm tối đa.
    """
    idx = df.index
    volume = _num(df.get("volume"), idx)
    vol_ma20 = _num(df.get("vol_ma20"), idx)

    ratio = volume / vol_ma20.replace(0, np.nan)

    # Điểm dạng tam giác, cao nhất quanh 1.05
    score = 1.0 - (ratio - 1.05).abs() / 1.05
    score = score.clip(0, 1)

    # Nếu thiếu dữ liệu thì trung tính, không phạt.
    return score.fillna(0.5)


def _position_score(df: pd.DataFrame) -> pd.Series:
    """
    Đánh giá vị trí giá bằng các cột đã có:
    - dist_from_ema9_pct: tốt nhất quanh 0 đến +4%
    - dist_high20_pct: càng gần đỉnh 20 phiên càng tốt nhưng không bắt buộc
    """
    idx = df.index
    dist_ema = _num(df.get("dist_from_ema9_pct"), idx)

    # Tốt nhất quanh +1.5%, giảm dần khi quá xa hoặc dưới EMA9 sâu.
    ema_score = 1.0 - (dist_ema - 1.5).abs() / 10.0
    ema_score = ema_score.clip(0, 1).fillna(0.5)

    if "dist_high20_pct" in df.columns:
        dist_high = _num(df.get("dist_high20_pct"), idx)
        high_score = _scale_centered(dist_high, center=-8.0, width=12.0).fillna(0.5)
        return 0.75 * ema_score + 0.25 * high_score

    return ema_score


def _technical_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo các điểm thành phần 0–100 chỉ từ cột có sẵn trong scan_df."""
    idx = df.index

    rsi14 = _num(df.get("rsi14"), idx)
    rsi_slope = _num(df.get("rsi_slope"), idx)
    ema_slope = _num(df.get("ema9_ma20_slope"), idx)
    ema_slope_change = _num(df.get("ema9_ma20_slope_change"), idx)
    rs5 = _num(df.get("rs5"), idx)
    rs10 = _num(df.get("rs10"), idx)

    # RSI: ưu tiên 48–68; quá thấp hoặc quá nóng đều giảm điểm.
    rsi_level = 1.0 - (rsi14 - 58.0).abs() / 35.0
    rsi_level = rsi_level.clip(0, 1).fillna(0.5)
    rsi_trend = _scale_centered(rsi_slope, center=0.0, width=5.0).fillna(0.5)
    rsi_score = 0.65 * rsi_level + 0.35 * rsi_trend

    # EMA: độ dốc hiện tại quan trọng hơn thay đổi độ dốc.
    ema_now = _scale_centered(ema_slope, center=0.0, width=4.0).fillna(0.5)
    ema_change = _scale_centered(
        ema_slope_change,
        center=0.0,
        width=2.5,
    ).fillna(0.5)
    ema_score = 0.72 * ema_now + 0.28 * ema_change

    # RS: giữ nguyên tinh thần RS5 và RS10.
    rs5_score = _scale_centered(rs5, center=0.0, width=12.0).fillna(0.5)
    rs10_score = _scale_centered(rs10, center=0.0, width=12.0).fillna(0.5)
    rs_accel = _scale_centered(rs5 - rs10, center=0.0, width=8.0).fillna(0.5)
    rs_score = 0.42 * rs5_score + 0.28 * rs10_score + 0.30 * rs_accel

    obv_score = _obv_score(df)
    volume_score = _volume_score(df)
    position_score = _position_score(df)

    green2 = _bool(df.get("green_2_confirm"), idx)
    early_green2 = _bool(df.get("early_green2"), idx)
    early_dry = _bool(df.get("early_dry_green2"), idx)

    pattern_score = (
        green2.astype(float) * 0.40
        + early_green2.astype(float) * 0.30
        + early_dry.astype(float) * 0.30
    )
    # Không có mẫu hình cũng không đồng nghĩa rất yếu.
    pattern_score = 0.35 + 0.65 * pattern_score

    scores = pd.DataFrame(
        {
            "_health_rsi": rsi_score * 100,
            "_health_ema": ema_score * 100,
            "_health_obv": obv_score * 100,
            "_health_rs": rs_score * 100,
            "_health_volume": volume_score * 100,
            "_health_position": position_score * 100,
            "_health_pattern": pattern_score * 100,
        },
        index=idx,
    )
    return scores.clip(0, 100)


def _assign_group(score: pd.Series, weakening: pd.Series) -> pd.Series:
    """
    Nhóm v1:
    - Đang hồi: điểm cao và không có cấu trúc suy yếu rõ.
    - Trung tính
    - Yếu
    - Yếu dần: điểm thấp vừa phải nhưng có dấu hiệu đang xấu thêm.
    - Rất yếu
    """
    group = pd.Series("🔴 YẾU", index=score.index, dtype="object")

    group.loc[score >= 68] = "🌱 ĐANG HỒI"
    group.loc[(score >= 54) & (score < 68)] = "🟡 TRUNG TÍNH"
    group.loc[(score >= 40) & (score < 54)] = "🔴 YẾU"
    group.loc[(score >= 27) & (score < 40)] = "⚠️ YẾU DẦN"
    group.loc[score < 27] = "⛔ RẤT YẾU"

    # Trường hợp suy yếu đồng thuận thì ưu tiên nhãn Yếu dần.
    group.loc[
        weakening
        & (score >= 27)
        & (score < 54)
    ] = "⚠️ YẾU DẦN"

    return group


def _action_from_group(group: str) -> str:
    mapping = {
        "🌱 ĐANG HỒI": "🟢 MUA / GIỮ",
        "🟡 TRUNG TÍNH": "👀 THEO DÕI",
        "🔴 YẾU": "⏳ CHỜ",
        "⚠️ YẾU DẦN": "🟠 HẠN CHẾ / GIẢM",
        "⛔ RẤT YẾU": "🔴 TRÁNH / BÁN",
    }
    return mapping.get(str(group), "👀 THEO DÕI")


def _build_reason(row: pd.Series) -> str:
    """Tạo lý do ngắn, tối đa 3 ý."""
    positives: list[tuple[float, str]] = []
    negatives: list[tuple[float, str]] = []

    components = [
        ("_health_rs", "RS mạnh", "RS yếu"),
        ("_health_ema", "Xu hướng lên", "Xu hướng giảm"),
        ("_health_obv", "OBV tốt", "OBV xấu"),
        ("_health_rsi", "RSI cải thiện", "RSI yếu"),
        ("_health_volume", "Vol xác nhận", "Vol chưa xác nhận"),
        ("_health_position", "Vị trí giá tốt", "Giá lệch xu hướng"),
        ("_health_pattern", "Mẫu hồi đẹp", "Thiếu mẫu xác nhận"),
    ]

    for col, pos_text, neg_text in components:
        value = pd.to_numeric(pd.Series([row.get(col)]), errors="coerce").iloc[0]
        if pd.isna(value):
            continue
        if value >= 65:
            positives.append((float(value), pos_text))
        elif value <= 38:
            negatives.append((float(value), neg_text))

    positives.sort(key=lambda x: x[0], reverse=True)
    negatives.sort(key=lambda x: x[0])

    group = str(row.get("evolution_health_group", ""))

    if group in {"🌱 ĐANG HỒI", "🟡 TRUNG TÍNH"}:
        selected = [x[1] for x in positives[:3]]
        if len(selected) < 2:
            selected += [x[1] for x in negatives[: 2 - len(selected)]]
    else:
        selected = [x[1] for x in negatives[:3]]
        if len(selected) < 2:
            selected += [x[1] for x in positives[: 2 - len(selected)]]

    if not selected:
        return "Chưa đủ tín hiệu rõ"

    # Loại trùng nhưng giữ thứ tự.
    return " + ".join(dict.fromkeys(selected))


def add_evolution_health(scan_df: pd.DataFrame) -> pd.DataFrame:

    if scan_df is None or not isinstance(scan_df, pd.DataFrame):
        raise TypeError("scan_df phải là pandas DataFrame")

    if scan_df.empty:
        return scan_df.copy()

    out = scan_df.copy()
    scores = _technical_scores(out)

    idx = out.index

    rs5 = _num(out.get("rs5"), idx)
    rs10 = _num(out.get("rs10"), idx)
    rsi14 = _num(out.get("rsi14"), idx)
    ema_slope = _num(out.get("ema9_ma20_slope"), idx)
    ema_change = _num(out.get("ema9_ma20_slope_change"), idx)
    rsi_slope = _num(out.get("rsi_slope"), idx)

    out = pd.concat([out, scores], axis=1)

    # =====================================================
    # ĐIỂM CƠ SỞ
    # =====================================================

    health_score = (
        scores["_health_rs"] * 0.24
        + scores["_health_ema"] * 0.20
        + scores["_health_obv"] * 0.18
        + scores["_health_rsi"] * 0.15
        + scores["_health_volume"] * 0.08
        + scores["_health_position"] * 0.09
        + scores["_health_pattern"] * 0.06
    )

    # =====================================================
    # SUPER STOCK BONUS
    # =====================================================

    bonus = pd.Series(0.0, index=idx)

    bonus += np.where(rs5 > 0, 3, -3)

    bonus += np.where(rs10 > 0, 3, -3)

    bonus += np.where(rs5 > rs10, 3, 0)

    bonus += np.where((rsi14 >= 55) & (rsi14 <= 68), 4, 0)

    bonus += np.where(ema_slope > 0, 4, -4)

    obv_good = (
        out["obv_status"]
        .astype(str)
        .str.upper()
        .str.contains("TỐT|GOOD|POS|UP|STRONG|GREEN|DƯƠNG")
    )

    bonus += np.where(obv_good, 5, -5)

    health_score = (health_score + bonus).clip(0, 100)

    # =====================================================
    # WEAKENING
    # =====================================================

    weakening_votes = (
        (ema_slope < 0).astype(int)
        + (ema_change < 0).astype(int)
        + (rsi_slope < 0).astype(int)
        + (rs5 < rs10).astype(int)
        + (rs5 < 0).astype(int)
    )

    weakening = weakening_votes >= 3

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

    out["evolution_action"] = out["evolution_health_group"].map(
        _action_from_group
    )

    out["evolution_reason"] = out.apply(
        _build_reason,
        axis=1,
    )

    sort_cols = [
        "evolution_health_rank",
        "evolution_health_score",
        "rs5",
        "rs10",
        "symbol",
    ]

    ascending = [
        True,
        False,
        False,
        False,
        True,
    ]

    out = (
        out.sort_values(
            sort_cols,
            ascending=ascending,
            na_position="last",
            kind="stable",
        )
        .reset_index(drop=True)
    )

    return out

def get_earning_money_board(scan_df: pd.DataFrame) -> pd.DataFrame:
    """
    Trả ra đúng board điều khiển đã chốt.
    Tự chạy add_evolution_health nếu scan_df chưa có cột Health.
    """
    required = {
        "evolution_health_score",
        "evolution_health_group",
        "evolution_action",
        "evolution_reason",
    }
    if not required.issubset(scan_df.columns):
        scan_df = add_evolution_health(scan_df)

    preferred_cols = [
        "evolution_health_group",
        "symbol",
        "price",
        "rs5",
        "rs10",
        "rsi14",
        "evolution_action",
        "evolution_reason",
    ]
    cols = [c for c in preferred_cols if c in scan_df.columns]
    board = scan_df[cols].copy()

    rename = {
        "evolution_health_group": "Health",
        "symbol": "Mã",
        "price": "Giá",
        "rs5": "RS5",
        "rs10": "RS10",
        "rsi14": "RSI14",
        "evolution_action": "Action",
        "evolution_reason": "Why",
    }
    return board.rename(columns=rename).reset_index(drop=True)


def render_earning_money_board(
    scan_df: pd.DataFrame,
    *,
    title: str = "🏆 EARNING MONEY BOARD",
    height: int = 720,
) -> pd.DataFrame:
    """
    Render Streamlit nếu streamlit có sẵn.
    Luôn trả về board DataFrame để dễ test/export.
    """
    board = get_earning_money_board(scan_df)

    try:
        import streamlit as st
    except ImportError:
        return board

    st.markdown("---")
    st.markdown(f"## {title}")

    def style_health(value: object) -> str:
        text = str(value)
        color_map = {
            "🌱 ĐANG HỒI": "background-color:#d9ead3;color:#1b4332;font-weight:700",
            "🟡 TRUNG TÍNH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
            "🔴 YẾU": "background-color:#fce5cd;color:#9c5700;font-weight:700",
            "⚠️ YẾU DẦN": "background-color:#f4cccc;color:#990000;font-weight:700",
            "⛔ RẤT YẾU": "background-color:#d9d9d9;color:#333333;font-weight:700",
        }
        return color_map.get(text, "")

    styled = board.style.map(style_health, subset=["Health"])
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=height,
    )
    return board


def export_earning_money_board_csv(
    scan_df: pd.DataFrame,
) -> bytes:
    """Dữ liệu cho st.download_button nếu cần."""
    board = get_earning_money_board(scan_df)
    return board.to_csv(index=False).encode("utf-8-sig")

