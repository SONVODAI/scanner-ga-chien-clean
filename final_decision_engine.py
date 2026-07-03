import pandas as pd
import numpy as np
import re

MAX_TOP = 10
MAX_PER_SECTOR = 3


def _find_col(df, names):
    if df is None or df.empty:
        return None
    lower = {str(c).lower().strip(): c for c in df.columns}
    for n in names:
        key = str(n).lower().strip()
        if key in lower:
            return lower[key]
    return None


def _to_num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        s = str(x).replace("%", "").replace(",", ".").strip()
        m = re.search(r"-?\d+(\.\d+)?", s)
        if not m:
            return default
        return float(m.group())
    except Exception:
        return default


def _scale_100(x):
    v = _to_num(x, 0)
    if v <= 1 and v > 0:
        v = v * 100
    return max(0, min(100, v))


def _confidence_score(x):
    s = str(x).upper()
    if any(k in s for k in ["RẤT CAO", "VERY HIGH", "A+"]):
        return 95
    if any(k in s for k in ["CAO", "HIGH", "A"]):
        return 85
    if any(k in s for k in ["TB", "TRUNG", "MEDIUM", "B"]):
        return 65
    if any(k in s for k in ["THẤP", "LOW", "C"]):
        return 40
    return _scale_100(x)


def _consensus_score(x):
    s = str(x)
    m = re.search(r"(\d+)\s*/\s*(\d+)", s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return max(0, min(100, a / b * 100)) if b else 0
    if "✅" in s or "3/3" in s:
        return 100
    if "2/3" in s:
        return 70
    return _scale_100(x)


def _star(score):
    if score >= 90:
        return "★★★★★"
    if score >= 80:
        return "★★★★☆"
    if score >= 70:
        return "★★★☆☆"
    if score >= 60:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def build_final_decision(
    buy_elite_df,
    green_red_df=None,
    max_top=MAX_TOP,
    max_per_sector=MAX_PER_SECTOR,
):
    if buy_elite_df is None or buy_elite_df.empty:
        return pd.DataFrame(), "Chưa có dữ liệu BUY ELITE."

    df = buy_elite_df.copy().reset_index(drop=True)

    symbol_col = _find_col(df, ["MÃ", "symbol", "ticker", "cp"])
    if symbol_col is None:
        return pd.DataFrame(), "Không tìm thấy cột mã cổ phiếu."

    elite_col = _find_col(df, ["EliteScore", "ELITE SCORE", "elite_score"])
    win_col = _find_col(df, ["WinProb", "WINPROB", "winprob"])
    trust_col = _find_col(df, ["ĐỘ TIN CẬY", "DO TIN CAY", "confidence"])
    cons_col = _find_col(df, ["ĐỒNG THUẬN", "DONG THUAN", "consensus"])
    sector_col = _find_col(df, ["NGÀNH", "Nghành", "ngành", "sector", "industry", "NHÓM"])
    group_col = _find_col(df, ["NHÓM", "group"])
    price_col = _find_col(df, ["GIÁ", "price"])
    zone_col = _find_col(df, ["VÙNG MUA ELITE", "VÙNG MUA", "buy zone"])
    nav_col = _find_col(df, ["NAV ELITE", "NAV"])
    action_col = _find_col(df, ["KẾT LUẬN", "HÀNH ĐỘNG", "action"])
    reason_col = _find_col(df, ["LÝ DO ELITE", "LÝ DO", "reason"])
    risk_col = _find_col(df, ["RỦI RO", "CẢNH BÁO", "risk"])

    df["_symbol"] = df[symbol_col].astype(str).str.upper().str.strip()

    green_symbols = set()
    if green_red_df is not None and not green_red_df.empty:
        g_symbol_col = _find_col(green_red_df, ["MÃ", "symbol", "ticker", "cp"])
        if g_symbol_col is not None:
            green_symbols = set(
                green_red_df[g_symbol_col].astype(str).str.upper().str.strip()
            )

    df["_elite"] = df[elite_col].apply(_scale_100) if elite_col else 0
    df["_win"] = df[win_col].apply(_scale_100) if win_col else 0
    df["_trust"] = df[trust_col].apply(_confidence_score) if trust_col else 0
    df["_consensus"] = df[cons_col].apply(_consensus_score) if cons_col else 0
    df["_green_bonus"] = df["_symbol"].apply(lambda x: 100 if x in green_symbols else 0)

    df["PrimeScore"] = (
        df["_elite"] * 0.35
        + df["_win"] * 0.25
        + df["_trust"] * 0.20
        + df["_consensus"] * 0.10
        + df["_green_bonus"] * 0.10
    ).round(1)

    df["⭐ PRIME"] = df["PrimeScore"].apply(_star)
    df["Xanh Mua"] = df["_symbol"].apply(lambda x: "✅" if x in green_symbols else "")

    if sector_col:
        df["_sector"] = df[sector_col].astype(str).fillna("Khác")
    else:
        df["_sector"] = "Khác"

    df = df.sort_values("PrimeScore", ascending=False).reset_index(drop=True)

    selected = []
    sector_count = {}

    for _, row in df.iterrows():
        sector = str(row["_sector"])
        if sector_count.get(sector, 0) >= max_per_sector:
            continue

        selected.append(row)
        sector_count[sector] = sector_count.get(sector, 0) + 1

        if len(selected) >= max_top:
            break

    if not selected:
        return pd.DataFrame(), "Không có mã đạt chuẩn FINAL DECISION."

    out = pd.DataFrame(selected).reset_index(drop=True)
    out.insert(0, "#", np.arange(1, len(out) + 1))

    result = pd.DataFrame()
    result["#"] = out["#"]
    result["⭐ PRIME"] = out["⭐ PRIME"]
    result["MÃ"] = out["_symbol"]
    result["PrimeScore"] = out["PrimeScore"]
    result["Xanh Mua"] = out["Xanh Mua"]

    if win_col:
        result["WinProb"] = out[win_col]
    if trust_col:
        result["Độ tin cậy"] = out[trust_col]
    if cons_col:
        result["Đồng thuận"] = out[cons_col]
    if group_col:
        result["Nhóm"] = out[group_col]
    if sector_col:
        result["Ngành"] = out["_sector"]
    if price_col:
        result["Giá"] = out[price_col]
    if zone_col:
        result["Vùng mua"] = out[zone_col]
    if nav_col:
        result["NAV"] = out[nav_col]
    if action_col:
        result["Kết luận"] = out[action_col]
    if reason_col:
        result["Lý do"] = out[reason_col]
    if risk_col:
        result["Rủi ro"] = out[risk_col]

    summary = f"BOT chọn {len(result)} cơ hội tốt nhất, tối đa {max_per_sector} mã mỗi ngành/nhóm."

    return result, summary
