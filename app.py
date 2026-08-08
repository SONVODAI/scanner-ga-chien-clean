# =========================================================
# SCANNER GÀ CHIẾN V20 - PULLBACK FIRST RESTRUCTURE
# Viết lại sạch 100% từ bản V18.4-Lite
# Mục tiêu:
#   1) Một nguồn dữ liệu sống duy nhất: scan_df
#   2) Live price được bơm vào cây nến cuối TRƯỚC khi tính indicator
#   3) Market / bảng nhóm / bảng chi tiết / bảng hành động / evolution dùng chung scan_df
#   4) Không còn tình trạng price đúng nhưng group/evo/detail lệch pha
# =========================================================

import os
import time
import base64
import json
import requests
from datetime import datetime, timedelta
from modules.learning_pattern_match import run as show_pattern_match
from zoneinfo import ZoneInfo
from modules.leader_brain_board import show_leader_brain
from leader_memory import update_memory
# from behavior_analyzer import BehaviorAnalyzer
from pattern_manager import save_pattern_history
from final_decision_engine import (
    build_final_decision,
    format_display_number,
    format_final_decision_for_display,
    style_final_decision,
)
from position_guardian import render_guardian
# Evolution Health is implemented locally below as the single source of truth.
from modules.daily_summary import process_and_render_daily_summary
from modules.earning_learning import (
    update_learning,
    get_learning_metadata,
    get_pattern_snapshot,
    get_pattern_lifecycle,
    get_continuation_knowledge,
    apply_learning_experience,
)
from modules.accumulation_opportunity import render_accumulation_board
from modules.experience_engine import run_experience_engine
from forecast_engine import ForecastEngine

_FORECAST_ENGINE = ForecastEngine()
import numpy as np
import pandas as pd
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None
# =========================================================
# V21 BRAIN / EXPERIENCE / DECISION MODULES
# =========================================================
try:
    from brain_manager import get_brain
    from learning_engine import save_experience_learning, build_learning_view
    from decision_engine import make_market_decision, build_decision_view, build_decision_history_view
    from brain_optimizer import (
    run_brain_optimizer,
    build_optimizer_view,
    build_recommendation_view,
    build_report_markdown,
)
except Exception as e:
    get_brain = None
    save_experience_learning = None
    build_learning_view = None
    make_market_decision = None
    build_decision_view = None
    build_decision_history_view = None
    run_brain_optimizer = None
    build_optimizer_view = None
    build_recommendation_view = None
    build_report_markdown = None
    BRAIN_IMPORT_ERROR = str(e)
else:
    BRAIN_IMPORT_ERROR = ""

# =========================================================
# EVOLUTION HEALTH ENGINE
# Tách thành module độc lập để app.py nhẹ hơn và chỉ điều phối.
# =========================================================
from modules.evolution_health import (
    add_evolution_health,
    export_earning_money_board_csv,
    get_earning_money_board,
    render_earning_money_board,
)
from modules.learning_pattern_match import (
    run as show_pattern_match,
    build_pattern_match,
)
# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Mr.BOT PRO V4.0",
    page_icon="🐔",
    layout="wide",
)

st.title("🤖 Mr.BOT PRO V4.0 - Scanner Gà Chiến")
st.caption("Observe • Learn • Think • Evolve. Market First → Mr.BOT PRO → Decision Engine → Learning Engine → Thinking Engine → Bot Evolution. Không dự đoán tương lai; chỉ học từ quá khứ để hỗ trợ quyết định hiện tại.")

# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = sorted(list(set([
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV", "HVN", "VJC",
    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "PTB", "VGT",
    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP",
    "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "DGC", "POW",
    "C4G", "FCN", "CII", "KSB", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG", "PLC", "TVN",
    "MWG", "FRT", "DGW", "PET", "MSN", "DBC", "HAG", "BAF",
    "MCH", "VNM", "MML",
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "VIX", "BSI", "FTS", "TVS", "SHS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",
    "VGC", "SZC", "IDC", "KBC", "IJC",
    "GVR", "SIP", "DPR", "PHR", "DRI",
    "FPT", "VGI", "CTR", "VTP", "CMG", "FOX",
    "BVH", "SBT", "PNJ",
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB", "VPL", "PDR", "DPG", "NHA", "HDC", "NTL", "HHS",
    "NLG", "KDH", "HUT",
])))

# =========================================================
# CONFIG
# =========================================================
EVOLUTION_FILE = "group_evolution_history.csv"
YAHOO_SUFFIX = ".VN"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Nếu có GITHUB_TOKEN trong Streamlit secrets thì evolution sẽ được lưu bền trên GitHub.
# Nếu không có token, app vẫn chạy bằng file local như bản cũ.
GITHUB_REPO_OWNER = "SONVODAI"
GITHUB_REPO_NAME = "scanner-ga-chien-clean"
GITHUB_EVO_PATH = EVOLUTION_FILE

BUY_ELITE_HISTORY_FILE = "buy_elite_learning_history.csv"
BUY_ELITE_PROFILE_FILE = "buy_elite_learning_profile.json"
BUY_ELITE_THINKING_FILE = "buy_elite_thinking_profile.json"
BUY_ELITE_THINKING_JOURNAL_FILE = "buy_elite_thinking_journal.csv"
MR_BOT_PRO_PROFILE_FILE = "mr_bot_pro_profile.json"
MR_BOT_PRO_JOURNAL_FILE = "mr_bot_pro_journal.csv"

# Daily data cache giữ nhẹ để không spam vnstock.
# Live price cache ngắn để bảng không lệch quá lâu.
DAILY_CACHE_TTL = 20 * 60
LIVE_CACHE_TTL = 90

GROUP_RANK = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,
    "PULL VỪA": 3,
    "PULL ĐẸP": 4,
    "MUA BREAK": 5,
    "CP MẠNH": 6,
    "GÀ TĂNG TỐC": 7,
}

GROUP_ORDER = [
    "GÀ TĂNG TỐC",
    "CP MẠNH",
    "MUA BREAK",
    "PULL ĐẸP",
    "PULL VỪA",
    "MUA EARLY",
    "TÍCH LŨY",
    "THEO DÕI",
]

# =========================================================
# HELPERS
# =========================================================
def to_float(value, default=np.nan):
    """Ép mọi kiểu dữ liệu về float an toàn.

    Mục tiêu: chặn các giá trị bẩn từ API như None, "", "--", Series,
    DataFrame, ndarray, inf... để không làm sập app khi gán vào candle cuối.
    """
    try:
        if value is None:
            return default

        if isinstance(value, pd.DataFrame):
            if value.empty:
                return default
            value = value.iloc[-1, -1]

        if isinstance(value, pd.Series):
            if len(value) == 0:
                return default
            value = value.iloc[-1]

        if isinstance(value, np.ndarray):
            if value.size == 0:
                return default
            value = value.flatten()[-1]

        if isinstance(value, str):
            value = value.strip()
            if value in ["", "--", "nan", "NaN", "None", "N/A", "null"]:
                return default
            value = value.replace(",", "")

        out = float(value)
        if pd.isna(out) or np.isinf(out):
            return default
        return out

    except Exception:
        return default


def is_valid_price(value) -> bool:
    v = to_float(value)
    return pd.notna(v) and v > 0


def safe_max_number(*values):
    nums = [to_float(v) for v in values]
    nums = [v for v in nums if pd.notna(v)]
    return max(nums) if nums else np.nan


def safe_min_number(*values):
    nums = [to_float(v) for v in values]
    nums = [v for v in nums if pd.notna(v)]
    return min(nums) if nums else np.nan


def log_runtime_error(symbol: str, stage: str, error):
    """Ghi lỗi mềm ra CSV để app không chết vì một mã hoặc một API lỗi."""
    try:
        row = pd.DataFrame([{
            "time": vn_time_str("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "stage": stage,
            "error": str(error),
        }])
        file_name = "runtime_error_log.csv"
        if os.path.exists(file_name):
            old = guard_dataframe_dtypes(pd.read_csv(file_name), text_cols=["time", "symbol", "stage", "error"], numeric_cols=[])
            row = pd.concat([old, row], ignore_index=True).tail(300)
        row = guard_dataframe_dtypes(row, text_cols=["time", "symbol", "stage", "error"], numeric_cols=[])
        row.to_csv(file_name, index=False)
    except Exception:
        pass

def safe_round(value, digits=2):
    try:
        if pd.isna(value):
            return np.nan
        return round(float(value), digits)
    except Exception:
        return np.nan


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).fillna(0).cumsum()


def slope_state_text(slope: float) -> str:
    if pd.isna(slope):
        return ""
    if slope > 2:
        return "🟢 Tăng tốc"
    if slope > 0:
        return "🟡 Ổn định"
    return "🔴 Yếu"


def vn_now() -> datetime:
    """Luôn lấy giờ Việt Nam, tránh lệch UTC trên server Streamlit Cloud."""
    return datetime.now(VN_TZ)


def today_str() -> str:
    return vn_now().strftime("%Y-%m-%d")


def vn_time_str(fmt: str = "%d/%m/%Y %H:%M:%S") -> str:
    return vn_now().strftime(fmt)


# =========================================================
# DATA GUARD LAYER - CHỐNG LỖI DTYPE PANDAS MỚI
# =========================================================
TEXT_GUARD_COLS = {
    "date", "time", "created_at", "updated_at", "last_outcome_update",
    "symbol", "group", "regime", "learning_mode", "conclusion", "nav",
    "dna", "obv", "status", "personality", "message", "mode", "note",
    "current_thought", "source", "stage", "error", "name", "version",
}

NUMERIC_GUARD_COLS = {
    "rank", "score", "price", "entry_price", "market_real", "market_forecast",
    "winprob", "elite_score", "storm", "persistence", "evolution",
    "recent_change", "rsi", "slope", "dist_ema9", "market_score",
    "action_score", "storm_score", "evo_score", "zone_score", "penalty",
    "t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win",
    "obv_value", "volume", "vol_ma20", "completed_t5", "baseline_winrate",
    "confidence", "age_days", "signals_today", "avg_winprob", "avg_elite_score",
    "high_consensus_count",
}


def ensure_object_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Ép các cột chữ/ngày giờ sang object để Pandas không báo lỗi khi gán string."""
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype("object")
        out[col] = out[col].where(pd.notna(out[col]), "")
    return out


def ensure_numeric_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Ép các cột số về numeric an toàn, lỗi thì thành NaN."""
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def guard_dataframe_dtypes(
    df: pd.DataFrame,
    text_cols=None,
    numeric_cols=None,
) -> pd.DataFrame:
    """Chuẩn hóa dtype trước khi setitem/concat/to_csv.

    Lỗi anh gặp xuất phát từ việc một cột đang là float64 nhưng bị gán chuỗi
    dạng '2026-06-29 07:16:49'. Hàm này tách rõ cột chữ và cột số để tránh
    Pandas 2.x/3.x chặn kiểu dữ liệu.
    """
    if df is None:
        return pd.DataFrame()
    out = df.copy()

    text_cols = list(TEXT_GUARD_COLS if text_cols is None else text_cols)
    numeric_cols = list(NUMERIC_GUARD_COLS if numeric_cols is None else numeric_cols)

    existing_text = [c for c in text_cols if c in out.columns]
    existing_numeric = [c for c in numeric_cols if c in out.columns and c not in existing_text]

    if existing_text:
        out = ensure_object_columns(out, existing_text)
    if existing_numeric:
        out = ensure_numeric_columns(out, existing_numeric)

    return out


def safe_read_csv_text(text: str | None) -> pd.DataFrame:
    if not text:
        return pd.DataFrame()
    try:
        from io import StringIO
        return pd.read_csv(StringIO(text))
    except Exception:
        return pd.DataFrame()


# =========================================================
# BOT LEARNING INSIGHT PANEL - READ ONLY
# Chỉ đọc dữ liệu Learning V3.1; tuyệt đối không ghi/xóa dữ liệu học.
# =========================================================
def _insight_numeric(series) -> pd.Series:
    """Ép một Series về numeric an toàn cho bảng Insight."""
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce")


def _insight_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return np.nan
    return round(float(numerator) / float(denominator) * 100.0, 1)


def _insight_band_label(left: float, right: float) -> str:
    if np.isneginf(left):
        return f"< {right:g}"
    if np.isposinf(right):
        return f"≥ {left:g}"
    return f"{left:g}–{right:g}"


def _best_numeric_feature_band(
    df: pd.DataFrame,
    feature: str,
    success_mask: pd.Series,
    eligible_mask: pd.Series,
    bins: list[float],
    *,
    min_samples: int,
) -> dict | None:
    """Tìm vùng feature có tỷ lệ thành công cao nhất, có chặn mẫu nhỏ."""
    if df is None or df.empty or feature not in df.columns:
        return None

    values = _insight_numeric(df[feature])
    eligible = eligible_mask.fillna(False) & values.notna()
    if int(eligible.sum()) < max(1, min_samples):
        return None

    temp = pd.DataFrame({
        "value": values,
        "eligible": eligible,
        "success": success_mask.fillna(False),
    })
    temp = temp[temp["eligible"]].copy()
    if temp.empty:
        return None

    edges = [-np.inf, *bins, np.inf]
    temp["band"] = pd.cut(
        temp["value"],
        bins=edges,
        include_lowest=True,
        right=False,
    )

    stats = (
        temp.groupby("band", observed=True)
        .agg(samples=("success", "size"), wins=("success", "sum"))
        .reset_index()
    )
    stats["rate"] = np.where(
        stats["samples"] > 0,
        stats["wins"] / stats["samples"] * 100.0,
        np.nan,
    )
    stats = stats[stats["samples"] >= max(1, min_samples)].copy()
    if stats.empty:
        return None

    # Ưu tiên tỷ lệ, sau đó ưu tiên mẫu lớn hơn.
    stats = stats.sort_values(
        ["rate", "samples"], ascending=[False, False], kind="stable"
    )
    best = stats.iloc[0]
    interval = best["band"]
    return {
        "feature": feature,
        "label": _insight_band_label(float(interval.left), float(interval.right)),
        "samples": int(best["samples"]),
        "wins": int(best["wins"]),
        "rate": round(float(best["rate"]), 1),
    }


def _best_category_feature(
    df: pd.DataFrame,
    feature: str,
    success_mask: pd.Series,
    eligible_mask: pd.Series,
    *,
    min_samples: int,
) -> dict | None:
    """Tìm trạng thái/cụm chữ có tỷ lệ thành công cao nhất."""
    if df is None or df.empty or feature not in df.columns:
        return None

    values = df[feature].astype("string").fillna("").str.strip()
    eligible = eligible_mask.fillna(False) & values.ne("")
    if int(eligible.sum()) < max(1, min_samples):
        return None

    temp = pd.DataFrame({
        "value": values,
        "eligible": eligible,
        "success": success_mask.fillna(False),
    })
    temp = temp[temp["eligible"]].copy()
    stats = (
        temp.groupby("value", dropna=False)
        .agg(samples=("success", "size"), wins=("success", "sum"))
        .reset_index()
    )
    stats["rate"] = np.where(
        stats["samples"] > 0,
        stats["wins"] / stats["samples"] * 100.0,
        np.nan,
    )
    stats = stats[stats["samples"] >= max(1, min_samples)].copy()
    if stats.empty:
        return None

    stats = stats.sort_values(
        ["rate", "samples"], ascending=[False, False], kind="stable"
    )
    best = stats.iloc[0]
    return {
        "feature": feature,
        "label": str(best["value"]),
        "samples": int(best["samples"]),
        "wins": int(best["wins"]),
        "rate": round(float(best["rate"]), 1),
    }


def _friendly_pattern_key(pattern_key: str) -> str:
    """Rút gọn pattern_key để đọc được trên giao diện."""
    text = str(pattern_key or "").strip()
    if not text:
        return ""
    parts = [part for part in text.split("|") if part and part != "NA"]
    # Giữ các mảnh có ý nghĩa nhất, tránh một câu quá dài trên mobile.
    preferred = []
    for part in parts:
        upper = part.upper()
        if any(token in upper for token in (
            "RECOVER", "NEUTRAL", "WEAK", "RSI", "EARLY", "PULL",
            "DRYUP", "POSITIVE", "NEGATIVE", "G2", ">=", "60-", "55-",
        )):
            preferred.append(part)
    chosen = preferred[:6] if preferred else parts[:6]
    return " + ".join(chosen)


def _latest_matching_symbols(
    snapshot: pd.DataFrame,
    pattern_key: str,
    *,
    limit: int = 5,
) -> list[str]:
    if (
        snapshot is None
        or snapshot.empty
        or not pattern_key
        or "pattern_key" not in snapshot.columns
        or "symbol" not in snapshot.columns
    ):
        return []

    matched = snapshot[snapshot["pattern_key"].astype(str) == str(pattern_key)].copy()
    if matched.empty:
        return []

    date_col = "trade_date" if "trade_date" in matched.columns else "entry_date"
    if date_col in matched.columns:
        matched[date_col] = pd.to_datetime(matched[date_col], errors="coerce")
        latest_date = matched[date_col].max()
        if pd.notna(latest_date):
            matched = matched[matched[date_col] == latest_date]

    return (
        matched["symbol"]
        .astype(str)
        .str.upper()
        .drop_duplicates()
        .head(max(1, int(limit)))
        .tolist()
    )


def render_bot_learning_insight() -> dict:
    """
    Hiển thị điều BOT học được từ T3/T5/T10.

    Đây là lớp READ ONLY:
    - Không gọi update_learning().
    - Không ghi CSV/JSON.
    - Lỗi Insight không được phép làm sập app hoặc ảnh hưởng dữ liệu học.
    """
    st.markdown("## 🧠 BOT LEARNING INSIGHT")
    st.caption(
        "BOT tự rút kinh nghiệm từ các cổ phiếu đã hoàn thành T3/T5/T10. "
        "Bảng này chỉ đọc bộ nhớ Learning, không thay đổi dữ liệu và không can thiệp logic giao dịch."
    )

    try:
        metadata = get_learning_metadata()
        snapshot = get_pattern_snapshot()
        lifecycle = get_pattern_lifecycle()
        continuation = get_continuation_knowledge(min_samples=1)
    except Exception as exc:
        st.info(
            "⏳ BOT chưa đọc được kho Learning Insight. "
            "Learning Engine vẫn hoạt động độc lập và dữ liệu không bị ảnh hưởng."
        )
        st.caption(f"Insight read-only: {type(exc).__name__}: {exc}")
        return {"ok": False, "status": "READ_ERROR", "error": str(exc)}

    metadata = metadata if isinstance(metadata, dict) else {}
    snapshot = snapshot if isinstance(snapshot, pd.DataFrame) else pd.DataFrame()
    lifecycle = lifecycle if isinstance(lifecycle, pd.DataFrame) else pd.DataFrame()
    continuation = continuation if isinstance(continuation, pd.DataFrame) else pd.DataFrame()

    if lifecycle.empty:
        t3 = pd.Series(dtype="float64")
        t5 = pd.Series(dtype="float64")
        t10 = pd.Series(dtype="float64")
    else:
        t3 = _insight_numeric(lifecycle.get("t3_return_pct"))
        t5 = _insight_numeric(lifecycle.get("t5_return_pct"))
        t10 = _insight_numeric(lifecycle.get("t10_return_pct"))

    t3_samples = int(t3.notna().sum())
    t5_samples = int(t5.notna().sum())
    t10_samples = int(t10.notna().sum())
    observation_rows = int(
        metadata.get("observations_rows", len(snapshot)) or len(snapshot)
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("DNA đã lưu", f"{observation_rows:,}")
    with m2:
        st.metric("Đủ T3", f"{t3_samples:,}", f"{_insight_pct(t3_samples, max(observation_rows, 1)):.1f}%")
    with m3:
        st.metric("Đủ T5", f"{t5_samples:,}", f"{_insight_pct(t5_samples, max(observation_rows, 1)):.1f}%")
    with m4:
        st.metric("Đủ T10", f"{t10_samples:,}", f"{_insight_pct(t10_samples, max(observation_rows, 1)):.1f}%")

    # Ba tầng tin cậy: đang học -> nhận xét sớm -> đủ nền để kết luận đáng tin hơn.
    reliable_targets = {"T3": 200, "T5": 100, "T10": 50}
    provisional_targets = {"T3": 30, "T5": 20, "T10": 10}

    if t3_samples < provisional_targets["T3"] or t5_samples < provisional_targets["T5"]:
        stage = "LEARNING"
        st.info(
            "⏳ **BOT đang tích lũy dữ liệu.** "
            f"Cần tối thiểu khoảng {provisional_targets['T3']} mẫu T3 và "
            f"{provisional_targets['T5']} mẫu T5 để bắt đầu phát biểu nhận xét sớm; "
            "đến lúc đó bảng sẽ tự chuyển trạng thái, không cần sửa code."
        )
    elif t10_samples < reliable_targets["T10"]:
        stage = "PROVISIONAL"
        st.warning(
            "🟡 **BOT đã có thể đưa ra nhận xét sớm**, nhưng mẫu T10 còn mỏng. "
            "Các kết luận bên dưới chỉ dùng để tham khảo và sẽ tự mạnh lên khi bộ nhớ dày hơn."
        )
    else:
        stage = "RELIABLE"
        st.success(
            "🟢 **BOT đã có đủ nền dữ liệu để diễn giải vòng đời T3 → T5 → T10.** "
            "Kết luận vẫn được chặn mẫu nhỏ và tiếp tục tự cập nhật sau mỗi phiên."
        )

    if lifecycle.empty or t3_samples == 0:
        st.caption(
            f"Tiến độ mục tiêu tin cậy: T3 {t3_samples}/{reliable_targets['T3']} • "
            f"T5 {t5_samples}/{reliable_targets['T5']} • "
            f"T10 {t10_samples}/{reliable_targets['T10']}"
        )
        return {
            "ok": True,
            "status": stage,
            "t3_samples": t3_samples,
            "t5_samples": t5_samples,
            "t10_samples": t10_samples,
        }

    has_t3 = t3.notna()
    has_t5 = t5.notna()
    has_t10 = t10.notna()
    t3_win = t3 > 0
    t5_win = t5 > 0
    t10_win = t10 > 0

    t3_wins = int((has_t3 & t3_win).sum())
    eligible_t3_t5 = int((has_t5 & t3_win).sum())
    continued_t3_t5 = int((has_t5 & t3_win & t5_win).sum())
    eligible_t5_t10 = int((has_t10 & t5_win).sum())
    continued_t5_t10 = int((has_t10 & t5_win & t10_win).sum())
    eligible_t3_t10 = int((has_t10 & t3_win).sum())
    continued_t3_t10 = int((has_t10 & t3_win & t10_win).sum())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Winrate T3", f"{_insight_pct(t3_wins, t3_samples):.1f}%", f"{t3_wins}/{t3_samples}")
    with c2:
        value = _insight_pct(continued_t3_t5, eligible_t3_t5)
        st.metric("T3+ → T5+", "—" if pd.isna(value) else f"{value:.1f}%", f"{continued_t3_t5}/{eligible_t3_t5}")
    with c3:
        value = _insight_pct(continued_t5_t10, eligible_t5_t10)
        st.metric("T5+ → T10+", "—" if pd.isna(value) else f"{value:.1f}%", f"{continued_t5_t10}/{eligible_t5_t10}")
    with c4:
        value = _insight_pct(continued_t3_t10, eligible_t3_t10)
        st.metric("T3+ → T10+", "—" if pd.isna(value) else f"{value:.1f}%", f"{continued_t3_t10}/{eligible_t3_t10}")

    # Chỉ phát biểu DNA khi có đủ số mẫu trong từng cụm.
    min_band_samples = 5 if stage == "PROVISIONAL" else 10
    eligible_t3_to_t5 = has_t5 & t3_win
    success_t3_to_t5 = has_t5 & t3_win & t5_win
    eligible_t3_to_t10 = has_t10 & t3_win
    success_t3_to_t10 = has_t10 & t3_win & t10_win

    findings: list[str] = []

    rsi_best = _best_numeric_feature_band(
        lifecycle,
        "rsi14",
        success_t3_to_t5,
        eligible_t3_to_t5,
        [45, 50, 55, 60, 65, 70],
        min_samples=min_band_samples,
    )
    if rsi_best:
        findings.append(
            f"**RSI {rsi_best['label']}** đang có tỷ lệ giữ lãi từ T3 sang T5 tốt nhất: "
            f"**{rsi_best['rate']:.1f}%** ({rsi_best['wins']}/{rsi_best['samples']} mẫu)."
        )

    rs_best = _best_numeric_feature_band(
        lifecycle,
        "rs10",
        success_t3_to_t5,
        eligible_t3_to_t5,
        [-2, 0, 2, 5, 10],
        min_samples=min_band_samples,
    )
    if rs_best:
        findings.append(
            f"Vùng **RS10 {rs_best['label']}** cho độ bền T3→T5 cao nhất: "
            f"**{rs_best['rate']:.1f}%** trên {rs_best['samples']} mẫu."
        )

    leader_best = _best_numeric_feature_band(
        lifecycle,
        "leader_score",
        success_t3_to_t10,
        eligible_t3_to_t10,
        [40, 60, 75, 85],
        min_samples=min_band_samples,
    )
    if leader_best:
        findings.append(
            f"**Leader Score {leader_best['label']}** hiện là vùng giữ lãi tới T10 tốt nhất: "
            f"**{leader_best['rate']:.1f}%** ({leader_best['wins']}/{leader_best['samples']} mẫu)."
        )

    obv_best = _best_category_feature(
        lifecycle,
        "obv_status",
        success_t3_to_t5,
        eligible_t3_to_t5,
        min_samples=min_band_samples,
    )
    if obv_best:
        findings.append(
            f"Trạng thái **OBV {obv_best['label']}** đang dẫn đầu độ bền T3→T5 với "
            f"**{obv_best['rate']:.1f}%** trên {obv_best['samples']} mẫu."
        )

    market_best = _best_numeric_feature_band(
        lifecycle,
        "market_score",
        success_t3_to_t10,
        eligible_t3_to_t10,
        [4, 6, 8],
        min_samples=min_band_samples,
    )
    if market_best:
        findings.append(
            f"Bối cảnh **Market Real {market_best['label']}** đang tạo xác suất T3→T10 tốt nhất: "
            f"**{market_best['rate']:.1f}%** trên {market_best['samples']} mẫu."
        )

    health_best = _best_category_feature(
        lifecycle,
        "health_group",
        success_t3_to_t5,
        eligible_t3_to_t5,
        min_samples=min_band_samples,
    )
    if health_best:
        findings.append(
            f"Nhóm **{health_best['label']}** đang có hiệu suất tiếp diễn T3→T5 tốt nhất: "
            f"**{health_best['rate']:.1f}%** trên {health_best['samples']} mẫu."
        )

    if findings:
        st.markdown("### BOT học được gì")
        for sentence in findings[:6]:
            st.markdown(f"- {sentence}")
    else:
        st.info(
            "BOT đã có Outcome nhưng từng cụm DNA vẫn còn quá ít mẫu để kết luận. "
            "Bảng sẽ tự phát biểu khi một vùng RSI/RS/OBV/Market đạt ngưỡng mẫu tối thiểu."
        )

    # Mẫu chính xác mạnh nhất: chỉ dùng khi có mẫu đủ lớn trong continuation_knowledge.
    if not continuation.empty:
        cont = continuation.copy()
        for col in (
            "eligible_t3_to_t5", "eligible_t3_to_t10", "samples_t10",
            "t3_to_t5_rate_pct", "t3_to_t10_rate_pct",
            "t3_to_t10_lower_bound_pct", "continuation_score", "avg_t10_return_pct",
        ):
            if col in cont.columns:
                cont[col] = pd.to_numeric(cont[col], errors="coerce")

        exact_min = 5 if stage == "PROVISIONAL" else 10
        eligible_col = "eligible_t3_to_t10" if "eligible_t3_to_t10" in cont.columns else "samples_t10"
        eligible_exact = cont[eligible_col].fillna(0) >= exact_min
        exact = cont[eligible_exact].copy()
        if not exact.empty:
            sort_cols = [c for c in ("continuation_score", "t3_to_t10_lower_bound_pct", eligible_col) if c in exact.columns]
            exact = exact.sort_values(sort_cols, ascending=[False] * len(sort_cols), kind="stable")
            top = exact.iloc[0]
            key = str(top.get("pattern_key", ""))
            readable = _friendly_pattern_key(key)
            rate = to_float(top.get("t3_to_t10_rate_pct", np.nan))
            lower = to_float(top.get("t3_to_t10_lower_bound_pct", np.nan))
            avg_t10 = to_float(top.get("avg_t10_return_pct", np.nan))
            samples = int(to_float(top.get(eligible_col, 0), 0))

            st.markdown("### 🧬 DNA bền nhất hiện tại")
            details = []
            if readable:
                details.append(f"**{readable}**")
            if pd.notna(rate):
                details.append(f"T3→T10: **{rate:.1f}%**")
            if pd.notna(lower):
                details.append(f"cận tin cậy: **{lower:.1f}%**")
            if pd.notna(avg_t10):
                details.append(f"lợi nhuận T10 TB: **{avg_t10:+.2f}%**")
            details.append(f"mẫu đủ điều kiện: **{samples}**")
            st.success(" • ".join(details))

            symbols = _latest_matching_symbols(snapshot, key, limit=5)
            if symbols:
                st.caption(
                    "Các mã mới nhất đang mang DNA tương tự: "
                    + ", ".join(f"**{symbol}**" for symbol in symbols)
                    + ". Đây là gợi ý nghiên cứu, không phải lệnh mua tự động."
                )

    # Cảnh báo flash winner giúp quyết định chốt sớm/thêm vốn.
    if "flash_winner" in lifecycle.columns:
        flash = lifecycle["flash_winner"].map(bool)
        flash_samples = int(flash.sum())
        if t3_wins > 0 and flash_samples > 0:
            flash_rate = _insight_pct(flash_samples, t3_wins)
            if pd.notna(flash_rate) and flash_rate >= 30:
                st.warning(
                    f"⚠️ Có **{flash_samples}/{t3_wins} mẫu thắng T3 ({flash_rate:.1f}%)** "
                    "đã trở thành Flash Winner — thắng sớm nhưng không giữ được lãi về sau. "
                    "BOT sẽ tiếp tục học nhóm này để hỗ trợ chốt sớm và hạn chế gia tăng vốn sai thời điểm."
                )

    st.caption(
        f"Tiến độ mục tiêu tin cậy: T3 {t3_samples}/{reliable_targets['T3']} • "
        f"T5 {t5_samples}/{reliable_targets['T5']} • "
        f"T10 {t10_samples}/{reliable_targets['T10']} • "
        f"Brain {metadata.get('brain_generation', 'GEN2')} • "
        f"Feature {metadata.get('feature_version', 'DNA_V3')}"
    )

    return {
        "ok": True,
        "status": stage,
        "t3_samples": t3_samples,
        "t5_samples": t5_samples,
        "t10_samples": t10_samples,
        "findings": findings,
    }


# =========================================================
# DATA DOWNLOAD
# =========================================================
@st.cache_data(ttl=DAILY_CACHE_TTL, show_spinner=False)
def download_symbol_data(symbol: str) -> pd.DataFrame:
    """Tải dữ liệu D1. Chỉ cache ở tầng dữ liệu nền, không cache analyze_symbol."""
    try:
        from vnstock import stock_historical_data

        df = stock_historical_data(
            symbol=symbol,
            start_date="2025-01-01",
            end_date=today_str(),
            resolution="1D",
            type="stock",
            beautify=True,
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

        rename_map = {}
        for c in df.columns:
            cl = str(c).lower()
            if "date" in cl or "time" in cl:
                rename_map[c] = "date"
            elif cl == "open":
                rename_map[c] = "open"
            elif cl == "high":
                rename_map[c] = "high"
            elif cl == "low":
                rename_map[c] = "low"
            elif cl == "close":
                rename_map[c] = "close"
            elif cl == "volume":
                rename_map[c] = "volume"

        df = df.rename(columns=rename_map)
        needed = ["date", "open", "high", "low", "close", "volume"]
        for c in needed:
            if c not in df.columns:
                return pd.DataFrame()

        df = df[needed].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=["date", "close"]).sort_values("date")
        return df.reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=LIVE_CACHE_TTL, show_spinner=False)
def fetch_live_price(symbol: str) -> dict:
    """
    Lấy giá live 15m từ yfinance.
    Trả về dict để sau này dễ mở rộng.
    Quan trọng: volume ở đây là tổng volume intraday YF nếu có, không lấy riêng cây 15m cuối.
    """
    if yf is None:
        return {"price": np.nan, "volume": np.nan, "source": "NO_YF", "ts": ""}

    ticker = f"{symbol}{YAHOO_SUFFIX}"

    try:
        data = yf.download(
            ticker,
            period="1d",
            interval="15m",
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        source = "YF_15M"

        if data is None or data.empty:
            data = yf.download(
                ticker,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            source = "YF_1D_FALLBACK"

        if data is None or data.empty:
            return {"price": np.nan, "volume": np.nan, "source": "NO_DATA", "ts": ""}

        # Xử lý cả trường hợp columns MultiIndex.
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] for c in data.columns]

        if "Close" not in data.columns:
            return {"price": np.nan, "volume": np.nan, "source": "NO_CLOSE", "ts": ""}

        close_series = pd.to_numeric(data["Close"], errors="coerce").dropna()
        if close_series.empty:
            return {"price": np.nan, "volume": np.nan, "source": "BAD_CLOSE", "ts": ""}

        live_price = to_float(close_series.iloc[-1])
        live_volume = np.nan
        if "Volume" in data.columns:
            vol_series = pd.to_numeric(data["Volume"], errors="coerce").dropna()
            if not vol_series.empty:
                live_volume = to_float(vol_series.sum())

        if pd.isna(live_price) or live_price <= 0:
            return {"price": np.nan, "volume": np.nan, "source": "BAD_PRICE", "ts": ""}

        try:
            ts = str(data.index[-1])
        except Exception:
            ts = ""

        return {
            "price": live_price,
            "volume": live_volume,
            "source": source,
            "ts": ts,
        }

    except Exception:
        return {"price": np.nan, "volume": np.nan, "source": "ERROR", "ts": ""}


# =========================================================
# REALTIME INJECTION - FIX FINAL
# =========================================================
def inject_live_into_daily(raw: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, dict]:
    """Bơm live price vào candle cuối theo chế độ an toàn.

    Nguyên tắc V19.2 SAFE:
    - Live lỗi / dữ liệu bẩn / giá rỗng => dùng D1, không crash.
    - Chỉ gán vào df sau khi final_price đã được kiểm tra là số hợp lệ.
    - Bất kỳ lỗi nào trong injection đều fallback về daily dataframe.
    """
    live = {
        "price": np.nan,
        "volume": np.nan,
        "source": "INIT",
        "ts": "",
        "daily_last_close_before_live": np.nan,
    }

    try:
        live = fetch_live_price(symbol)
        if not isinstance(live, dict):
            live = {"price": np.nan, "volume": np.nan, "source": "BAD_LIVE_DICT", "ts": ""}

        df = raw.copy().sort_values("date").reset_index(drop=True)
        if df.empty:
            live["source"] = "EMPTY_DAILY"
            return df, live

        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        df["is_live_adjusted"] = False
        last_idx = df.index[-1]

        last_close = to_float(df.loc[last_idx, "close"])
        last_open = to_float(df.loc[last_idx, "open"])
        last_high = to_float(df.loc[last_idx, "high"])
        last_low = to_float(df.loc[last_idx, "low"])
        last_volume = to_float(df.loc[last_idx, "volume"])

        live_price = to_float(live.get("price", np.nan))
        live_volume = to_float(live.get("volume", np.nan))
        live["daily_last_close_before_live"] = last_close

        now_vn = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")
        market_closed = (now_vn.hour > 15) or (now_vn.hour == 15 and now_vn.minute >= 0)

        # CASE 1: không có live hợp lệ -> giữ nguyên candle D1, không đánh dấu live.
        if not is_valid_price(live_price):
            live["price"] = last_close
            live["volume"] = last_volume
            live["source"] = "NO_DATA"
            return df.reset_index(drop=True), live

        # CASE 2: có live hợp lệ.
        if market_closed and is_valid_price(last_close):
            # Sau giờ đóng cửa: nếu live gần sát D1 thì ưu tiên D1 để tránh lệch dữ liệu.
            if abs(live_price - last_close) <= max(50, last_close * 0.003):
                final_price = last_close
                final_volume = safe_max_number(last_volume, live_volume)
                live["source"] = "D1_FINAL"
            else:
                final_price = live_price
                final_volume = safe_max_number(last_volume, live_volume)
                live["source"] = live.get("source", "YF_15M") or "YF_15M"
        else:
            final_price = live_price
            final_volume = safe_max_number(last_volume, live_volume)

        final_price = to_float(final_price)

        # Chốt chặn cuối: tuyệt đối không gán giá bẩn vào cột close.
        if not is_valid_price(final_price):
            live["price"] = last_close
            live["volume"] = last_volume
            live["source"] = "BAD_FINAL_PRICE"
            return df.reset_index(drop=True), live

        final_high = safe_max_number(last_high, last_open, final_price)
        final_low = safe_min_number(last_low, last_open, final_price)

        if not is_valid_price(final_high):
            final_high = final_price
        if not is_valid_price(final_low):
            final_low = final_price

        df.loc[last_idx, "close"] = float(final_price)
        df.loc[last_idx, "high"] = float(final_high)
        df.loc[last_idx, "low"] = float(final_low)

        if pd.notna(final_volume) and final_volume > 0:
            df.loc[last_idx, "volume"] = float(final_volume)

        df.loc[last_idx, "is_live_adjusted"] = True

        live["price"] = final_price
        live["volume"] = final_volume

        return df.reset_index(drop=True), live

    except Exception as e:
        log_runtime_error(symbol, "inject_live_into_daily", e)
        try:
            df = raw.copy().sort_values("date").reset_index(drop=True)
            if not df.empty:
                df["is_live_adjusted"] = False
                last = df.iloc[-1]
                live = {
                    "price": to_float(last.get("close", np.nan)),
                    "volume": to_float(last.get("volume", np.nan)),
                    "source": "SAFE_MODE_D1",
                    "ts": "",
                    "daily_last_close_before_live": to_float(last.get("close", np.nan)),
                }
                return df, live
        except Exception as e2:
            log_runtime_error(symbol, "inject_fallback", e2)

        live = {
            "price": np.nan,
            "volume": np.nan,
            "source": "SAFE_MODE_EMPTY",
            "ts": "",
            "daily_last_close_before_live": np.nan,
        }
        return pd.DataFrame(), live

# =========================================================
# INDICATORS
# =========================================================
def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)

    x["ema9_ma20_slope"] = np.where(
        x["ma20"] != 0,
        (x["ema9"] - x["ma20"]) / x["ma20"] * 100,
        np.nan,
    )
    x["ema9_ma20_slope_change"] = x["ema9_ma20_slope"] - x["ema9_ma20_slope"].shift(3)
    x["slope_state"] = x["ema9_ma20_slope"].apply(slope_state_text)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_slope"] = x["rsi14"] - x["rsi14"].shift(3)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    # Volume nền và volume trước phiên hiện tại.
    # Dry-up phải đo TRƯỚC khi GREEN2 xuất hiện, vì phiên GREEN2 thường volume đã tăng lại.
    x["vol_ma5"] = sma(x["volume"], 5)
    x["vol_ma10"] = sma(x["volume"], 10)
    x["vol_ma20"] = sma(x["volume"], 20)

    x["pre_vol_ma5"] = sma(x["volume"].shift(1), 5)
    x["pre_vol_ma10"] = sma(x["volume"].shift(1), 10)
    x["pre_vol_ma20"] = sma(x["volume"].shift(1), 20)

    x["dryup_ratio_5"] = np.where(
        x["pre_vol_ma20"] > 0,
        x["pre_vol_ma5"] / x["pre_vol_ma20"],
        np.nan,
    )
    x["dryup_ratio_10"] = np.where(
        x["pre_vol_ma20"] > 0,
        x["pre_vol_ma10"] / x["pre_vol_ma20"],
        np.nan,
    )
    x["dryup_ok"] = (x["dryup_ratio_5"] <= 0.75) | (x["dryup_ratio_10"] <= 0.85)

    # Gần đáy: đo khoảng cách so với đáy 20 phiên và 60 phiên.
    low20 = x["close"].rolling(20).min()
    low60 = x["close"].rolling(60).min()
    x["near_bottom_20_pct"] = np.where(low20 > 0, (x["close"] / low20 - 1) * 100, np.nan)
    x["near_bottom_60_pct"] = np.where(low60 > 0, (x["close"] / low60 - 1) * 100, np.nan)

    # Khoảng cách tới đỉnh gần nhất để tránh mua mã đã chạy lưng chừng.
    high20_prev = x["high"].shift(1).rolling(20).max()
    x["dist_high20_pct"] = np.where(high20_prev > 0, (x["close"] / high20_prev - 1) * 100, np.nan)

    x["rs5"] = ((x["close"] / x["close"].shift(5)) - 1) * 100
    x["rs10"] = ((x["close"] / x["close"].shift(10)) - 1) * 100

    x["green_candle"] = x["close"] > x["open"]
    x["body_pct"] = np.where(x["open"] > 0, (x["close"] / x["open"] - 1) * 100, np.nan)

    # GREEN2 bản cũ vẫn giữ để các bảng Storm/Pullback không bị lệch logic.
    x["green_2_confirm"] = np.where(
        (
            x["green_candle"].shift(1)
            & x["green_candle"]
            & (x["volume"] > x["volume"].shift(1))
            & (x["rsi14"] > 55)
            & (x["rsi14"] > x["rsi14"].shift(1))
            & (x["obv"] > x["obv_ema9"])
            & (x["obv"] > x["obv"].shift(1))
        ),
        "🟢 GREEN 2",
        "",
    )

    # GREEN2 EARLY: nhẹ hơn bản cũ, dùng riêng cho vùng đáy.
    # Mục tiêu là bắt 2 nến xanh nhỏ đầu tiên khi RSI còn 45-58.
    x["early_green2"] = np.where(
        (
            x["green_candle"].shift(1)
            & x["green_candle"]
            & (x["close"] > x["close"].shift(1))
            & (x["rsi14"] >= 45)
            & (x["rsi14"] <= 58)
            & (x["rsi14"] > x["rsi14"].shift(1))
            & (x["obv"] > x["obv"].shift(1))
            & (x["body_pct"].fillna(0).abs() <= 5.5)
        ),
        "✅ EARLY GREEN2",
        "",
    )

    x["early_dry_green2"] = np.where(
        (
            x["dryup_ok"]
            & x["early_green2"].astype(str).str.contains("EARLY GREEN2", na=False)
            & (x["near_bottom_20_pct"] <= 12)
            & (x["near_bottom_60_pct"] <= 22)
            & (x["ema9_ma20_slope"] <= 2.5)
        ),
        "🌱 EARLY DRY GREEN2",
        "",
    )

    return x


# =========================================================
# SCORE ENGINE
# =========================================================
def calc_price_score(close_, ema9_, ma20_, ema9_prev):
    if pd.notna(close_) and pd.notna(ema9_) and pd.notna(ma20_) and pd.notna(ema9_prev):
        if close_ > ema9_ > ma20_ and ema9_ > ema9_prev:
            return 2
        if close_ > ema9_:
            return 1
    return 0


def calc_rsi_score(rsi_, rsi_slope_):
    if pd.notna(rsi_) and pd.notna(rsi_slope_):
        if rsi_ > 65 and rsi_slope_ > 0:
            return 2
        if rsi_ > 55:
            return 1
    return 0


def calc_obv_score(obv_, obv_ema9_, obv_prev):
    if pd.notna(obv_) and pd.notna(obv_ema9_) and pd.notna(obv_prev):
        if obv_ > obv_ema9_ and obv_ > obv_prev:
            return 2
        if obv_ > obv_ema9_:
            return 1
    return 0


def calc_slope_score(slope_, slope_change_):
    if pd.notna(slope_) and pd.notna(slope_change_):
        if slope_ > 2 and slope_change_ > 0:
            return 2
        if slope_ > 0:
            return 1
    return 0


def calc_rs_score(rs5_, rs10_):
    if pd.notna(rs5_) and pd.notna(rs10_):
        if rs5_ >= 3 and rs10_ >= 5:
            return 2
        if rs5_ >= 1 or rs10_ >= 2:
            return 1
    return 0
def calc_volume_score(close_, open_, volume_, vol_ma20_):
    """
    Đánh giá chất lượng volume.
    Không đo volume lớn hay nhỏ đơn thuần.
    Đo volume có đi cùng giá đúng hướng hay không.
    """

    if (
        pd.isna(close_)
        or pd.isna(open_)
        or pd.isna(volume_)
        or pd.isna(vol_ma20_)
        or vol_ma20_ <= 0
    ):
        return 0

    vol_ratio = volume_ / vol_ma20_

    # Giá tăng + vol lớn
    if close_ > open_ and vol_ratio >= 1.2:
        return 2

    # Giá tăng + vol trung bình
    if close_ > open_ and vol_ratio >= 0.8:
        return 1

    # Giá giảm mạnh nhưng vol lớn
    if close_ < open_ and vol_ratio >= 1.2:
        return -2

    # Giá giảm nhẹ nhưng vol thấp
    if close_ < open_ and vol_ratio < 0.8:
        return 1

    return 0

# =========================================================
# LABELS / GROUPS
# =========================================================
def classify_pull_label(dist_from_ema9, rsi_, rsi_slope_, obv_, obv_ema9_):
    if not pd.notna(dist_from_ema9):
        return ""

    obv_ok = pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_
    rsi_ok = pd.notna(rsi_) and rsi_ > 55
    rsi_strong = pd.notna(rsi_) and rsi_ > 60
    slope_up = pd.notna(rsi_slope_) and rsi_slope_ > 0

    if -1.0 <= dist_from_ema9 <= 1.0 and rsi_strong and slope_up and obv_ok:
        return "PULL ĐẸP"

    if -2.5 <= dist_from_ema9 <= 2.0 and rsi_ok and obv_ok:
        return "PULL VỪA"

    return "PULL XẤU"


def build_warning(close_, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_):
    warnings = []

    if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ < obv_ema9_:
        warnings.append("OBV gãy")

    if pd.notna(rsi_) and rsi_ < 55:
        warnings.append("RSI yếu")

    if pd.notna(rsi_slope_) and rsi_slope_ < 0:
        warnings.append("RSI chững")

    if pd.notna(close_) and pd.notna(ema9_) and close_ < ema9_:
        warnings.append("Giá dưới EMA9")

    if pd.notna(slope_) and slope_ < 0:
        warnings.append("Slope âm")

    if pull_label == "PULL XẤU":
        warnings.append("Pull xấu")

    return " | ".join(dict.fromkeys(warnings))


def build_status(total_score, warning, group_name):
    if group_name == "PULL ĐẸP":
        return "🟢"
    if total_score >= 6 and warning == "":
        return "🟢"
    if total_score >= 3:
        return "🟡"
    return "🔴"


def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    V = row["V"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
    dist_from_ema9 = row["dist_from_ema9_pct"]
    breakout_ref = row["breakout_ref"]
    pull_label = row["pull_label"]
    slope_ = row["ema9_ma20_slope"]

    leader = (
        total >= 5
        and e >= 1
        and o >= 1
        and pd.notna(price)
        and pd.notna(ema9_)
        and price >= ema9_ * 0.97
    )


    if (
        pd.notna(slope_)
        and slope_ > 2
        and total >= 7
        and e >= 1
        and r >= 1
        and o >= 1
        and V >= 1
    ):
        return "GÀ TĂNG TỐC"

    if pull_label == "PULL ĐẸP":
        return "PULL ĐẸP"

    if pull_label == "PULL VỪA":
        return "PULL VỪA"

    if (
        pd.notna(breakout_ref)
        and pd.notna(price)
        and pd.notna(vol_)
        and pd.notna(vol_ma20_)
        and price >= breakout_ref * 1.01
        and vol_ >= vol_ma20_ * 1.2
        and r >= 1
        and o >= 1
    ):
        return "MUA BREAK"


    if (
        leader
        and pd.notna(dist_from_ema9)
        and dist_from_ema9 > 1.5
        and e == 2
        and r >= 1
        and o >= 1
        and V >= 1
    ):
        return "CP MẠNH"

    if not leader:
        if total <= 1:
            return "THEO DÕI"
        if total == 2:
            return "TÍCH LŨY"
        return "MUA EARLY"

    return "MUA EARLY"


# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    # Sửa bệnh chính: bơm live vào D1 trước khi tính indicator.
    live_df, live_info = inject_live_into_daily(raw, symbol)
    if live_df.empty or len(live_df) < 40:
        return None

    df = build_indicators(live_df)
    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    daily_price_before_live = live_info.get("daily_last_close_before_live", np.nan)

    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    slope_ = to_float(last["ema9_ma20_slope"])
    slope_change_ = to_float(last["ema9_ma20_slope_change"])

    rsi_ = to_float(last["rsi14"])
    rsi_slope_ = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])

    breakout_ref = to_float(df["high"].iloc[-21:-1].max())

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)
    S = calc_slope_score(slope_, slope_change_)
    RS = calc_rs_score(rs5_, rs10_)

    V = calc_volume_score(
    close_=last["close"],
    open_=last["open"],
    volume_=vol_,
    vol_ma20_=vol_ma20_,
)

    total_score = E + R + O + S + RS + V

    pull_label = classify_pull_label(
            dist_from_ema9=dist_from_ema9,
            rsi_=rsi_,
            rsi_slope_=rsi_slope_,
            obv_=obv_,
            obv_ema9_=obv_ema9_,
        )

    obv_status = "🟢" if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_ else "🔴"

    row = {
            "symbol": symbol,
            "date": last.get("date", None),
            "price": safe_round(price, 0),
            "daily_price_before_live": safe_round(daily_price_before_live, 0),
            "live_source": live_info.get("source", ""),
            "live_ts": live_info.get("ts", ""),
            "is_live_adjusted": bool(last.get("is_live_adjusted", False)),
            "ema9": safe_round(ema9_, 2),
            "ma20": safe_round(ma20_, 2),
            "ema9_ma20_slope": safe_round(slope_, 2),
            "ema9_ma20_slope_change": safe_round(slope_change_, 2),
            "slope_state": slope_state_text(slope_),
            "rsi14": safe_round(rsi_, 2),
            "rsi_slope": safe_round(rsi_slope_, 2),
            "obv": safe_round(obv_, 0),
            "obv_ema9": safe_round(obv_ema9_, 0),
            "obv_status": obv_status,
            "volume": safe_round(vol_, 0),
            "vol_ma20": safe_round(vol_ma20_, 0),
            "breakout_ref": safe_round(breakout_ref, 2),
            "dist_from_ema9_pct": safe_round(dist_from_ema9, 2),
            "pull_label": pull_label,
            "E": E,
            "R": R,
            "O": O,
            "S": S,
            "RS": RS,
            "V": V,
            "rs5": safe_round(rs5_, 2),
            "rs10": safe_round(rs10_, 2),
            "green_2_confirm": str(last.get("green_2_confirm", "")),
            "early_green2": str(last.get("early_green2", "")),
            "early_dry_green2": str(last.get("early_dry_green2", "")),
            "dryup_ratio_5": safe_round(last.get("dryup_ratio_5", np.nan), 2),
            "dryup_ratio_10": safe_round(last.get("dryup_ratio_10", np.nan), 2),
            "near_bottom_20_pct": safe_round(last.get("near_bottom_20_pct", np.nan), 2),
            "near_bottom_60_pct": safe_round(last.get("near_bottom_60_pct", np.nan), 2),
            "dist_high20_pct": safe_round(last.get("dist_high20_pct", np.nan), 2),
            "body_pct": safe_round(last.get("body_pct", np.nan), 2),
            "total_score": total_score,
        }

    row["group"] = classify_group(row)
    row["warning"] = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_)
    row["status"] = build_status(total_score, row["warning"], row["group"])

    return row


# =========================================================
# SCAN
# =========================================================
def run_scan(symbols: list[str]) -> pd.DataFrame:
    """Quét watchlist theo chế độ chịu lỗi.

    Một mã lỗi không được phép làm sập toàn bộ scanner.
    Lỗi được ghi vào runtime_error_log.csv, các mã còn lại vẫn chạy bình thường.
    """
    rows = []
    progress = st.progress(0)
    total = len(symbols)

    for i, symbol in enumerate(symbols):
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception as e:
            log_runtime_error(symbol, "analyze_symbol", e)
            continue
        finally:
            try:
                progress.progress((i + 1) / total)
            except Exception:
                pass

    progress.empty()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["group_rank"] = df["group"].map({g: i for i, g in enumerate(GROUP_ORDER)}).fillna(99)

    sort_cols = [
        "group_rank",
        "total_score",
        "S",
        "E",
        "O",
        "R",
        "ema9_ma20_slope",
    ]

    existing_sort_cols = [c for c in sort_cols if c in df.columns]
    ascending_map = {
        "group_rank": True,
        "total_score": False,
        "S": False,
        "E": False,
        "O": False,
        "R": False,
        "ema9_ma20_slope": False,
    }

    if existing_sort_cols:
        ascending = [ascending_map.get(c, False) for c in existing_sort_cols]
        df = df.sort_values(by=existing_sort_cols, ascending=ascending).reset_index(drop=True)

    return df

# =========================================================
# MARKET SCORE - DÙNG CHUNG scan_df
# =========================================================
def calc_market_real(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total

    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    pull_ok = len(df[df["group"] == "PULL VỪA"])

    score = (
        e_ratio * 3.0
        + r_ratio * 2.5
        + o_ratio * 2.5
        + s_ratio * 2.0
        + min(strong / 12, 1) * 1.0
        + min(accel / 8, 1) * 1.2
        + min((pull_good + pull_ok) / 12, 1) * 0.8
    )

    return round(min(score, 13), 1)


def calc_market_live(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    live_ok_ratio = len(df[df["is_live_adjusted"] == True]) / total if "is_live_adjusted" in df.columns else 0
    green_price_ratio = len(df[df["price"] >= df["daily_price_before_live"]]) / total if "daily_price_before_live" in df.columns else 0

    e_ratio = len(df[df["E"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total

    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])

    score = (
        e_ratio * 2.5
        + o_ratio * 2.0
        + s_ratio * 2.0
        + green_price_ratio * 2.0
        + live_ok_ratio * 1.0
        + min(accel / 6, 1) * 1.5
        + min(breakout / 8, 1) * 1.0
        + min(pull_good / 6, 1) * 1.0
    )

    return round(min(score, 13), 1)




def calc_market_forecast(df: pd.DataFrame):

    total = len(df)

    if total == 0:
        
        return _FORECAST_ENGINE.build_result(
            score=0,
            text="Không có dữ liệu",
        ) 

    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    weak = len(df[df["group"] == "THEO DÕI"])

    obv_good = len(df[df["obv_status"] == "🟢"]) / total
    slope_good = len(df[df["ema9_ma20_slope"] > 0]) / total

    score = 0

    score += min(accel / 5, 2)
    score += min(strong / 10, 2)
    score += min(breakout / 8, 2)
    score += min(pull_good / 8, 2)
    score += obv_good * 1
    score += slope_good * 1
    score -= min(weak / 15, 2)

    score = round(max(min(score, 10), 0), 1)
    # =====================================================
    # FORECAST CONFIDENCE V1
    # =====================================================

    confidence = 50.0

    confidence += min(accel * 3, 12)
    confidence += min(strong * 2, 10)
    confidence += min(breakout * 2, 10)
    confidence += min(pull_good * 2, 10)

    confidence += obv_good * 10
    confidence += slope_good * 10

    confidence -= min(weak * 2, 20)

    confidence = round(max(0.0, min(confidence, 100.0)), 1)
    if score >= 8:
        text = "🟢 Forecast tốt 5-10 ngày"

    elif score >= 6:
        text = "🟡 Forecast trung tính-khá"

    elif score >= 4:
        text = "🟠 Forecast yếu"

    else:
        text = "🔴 Forecast rủi ro"
    return _FORECAST_ENGINE.build_result(
        score=score,
        text=text,
        confidence=confidence,
    )
    
def market_status_text(score: float) -> tuple[str, str]:
    if score >= 8:
        return "🟢 THỊ TRƯỜNG KHỎE", "✅ Có thể vào tiền"
    if score >= 6:
        return "🟡 TRUNG TÍNH", "⚠️ Chỉ nên test nhỏ"
    return "🔴 THỊ TRƯỜNG YẾU", "⛔ Không nên vào tiền"


# =========================================================
# RSI BREADTH REPORT - ĐỘ RỘNG THỊ TRƯỜNG TỪ EARNING MONEY BOARD
# =========================================================
def build_rsi_breadth_report(scan_df: pd.DataFrame) -> dict:
    """Tổng hợp độ rộng RSI và sinh kết luận hành động từ chính scan_df.

    Hàm chỉ đọc dữ liệu đã có nên gần như không phát sinh thêm tải cho app.
    Breadth Score dùng tỷ lệ cổ phiếu có RSI > 50 trên toàn bộ mẫu hợp lệ.
    """
    empty_report = {
        "total": 0,
        "counts": {60: 0, 50: 0, 40: 0, 30: 0, 20: 0, 10: 0},
        "percentages": {60: 0.0, 50: 0.0, 40: 0.0, 30: 0.0, 20: 0.0, 10: 0.0},
        "score": 0,
        "level": "KHÔNG CÓ DỮ LIỆU",
        "icon": "⚪",
        "message": "Chưa có đủ dữ liệu RSI để đánh giá độ rộng thị trường.",
        "tone": "info",
    }

    if scan_df is None or scan_df.empty or "rsi14" not in scan_df.columns:
        return empty_report

    rsi = pd.to_numeric(scan_df["rsi14"], errors="coerce").dropna()
    total = int(len(rsi))
    if total == 0:
        return empty_report

    thresholds = [60, 50, 40, 30, 20, 10]
    counts = {level: int((rsi > level).sum()) for level in thresholds}
    percentages = {
        level: round(counts[level] / total * 100, 1)
        for level in thresholds
    }

    breadth_score = int(round(percentages[50]))
    pct60 = percentages[60]
    pct50 = percentages[50]
    pct40 = percentages[40]
    below50 = round(100 - pct50, 1)

    if pct50 >= 70:
        icon, level, tone = "🟢", "RẤT KHỎE", "success"
        action = "Độ rộng lan tỏa mạnh; có thể ưu tiên các cổ phiếu dẫn dắt và gia tăng vị thế có kiểm soát."
    elif pct50 >= 50:
        icon, level, tone = "🟢", "KHỎE", "success"
        action = "Phần lớn cổ phiếu giữ động lượng tích cực; ưu tiên mua đúng điểm và tiếp tục nắm giữ mã khỏe."
    elif pct50 >= 30:
        icon, level, tone = "🟡", "TRUNG TÍNH", "warning"
        action = "Cơ hội có nhưng chưa lan tỏa; chỉ chọn nhóm top đầu, mua nhỏ và tránh đuổi giá."
    elif pct50 >= 15:
        icon, level, tone = "🟠", "YẾU", "warning"
        action = "Dòng tiền chỉ tập trung ở số ít cổ phiếu; ưu tiên phòng thủ và chỉ theo dõi các mã dẫn dắt thật sự."
    else:
        icon, level, tone = "🔴", "RẤT YẾU", "error"
        action = "Xác suất kiếm tiền thấp; ưu tiên bảo toàn vốn và không cố tìm cơ hội trong nhóm cổ phiếu yếu."

    if pct60 < 5:
        leadership = "Số cổ phiếu thật sự mạnh gần như cạn kiệt."
    elif pct60 < 15:
        leadership = "Nhóm dẫn dắt rất hẹp, sức mạnh chưa lan tỏa."
    else:
        leadership = "Thị trường vẫn có một lớp cổ phiếu dẫn dắt đáng kể."

    message = (
        f"{icon} **RSI Breadth: {breadth_score}/100 – {level}.** "
        f"Có **{counts[50]}/{total} cổ phiếu ({pct50:.1f}%)** duy trì RSI trên 50; "
        f"**{counts[60]} mã ({pct60:.1f}%)** ở vùng sức mạnh cao và "
        f"**{below50:.1f}%** đã nằm dưới RSI 50. {leadership} {action}"
    )

    return {
        "total": total,
        "counts": counts,
        "percentages": percentages,
        "score": breadth_score,
        "level": level,
        "icon": icon,
        "message": message,
        "tone": tone,
        "pct40": pct40,
    }


def render_rsi_breadth_report(scan_df: pd.DataFrame) -> dict:
    """Hiển thị bảng thống kê RSI và lời kết luận tự động của Mr.BOT."""
    report = build_rsi_breadth_report(scan_df)

    st.markdown("### 🩺 RSI MARKET BREADTH")
    st.caption("Đo sức khỏe thực tế của toàn bộ cổ phiếu trong Earning Money Board, không chỉ nhìn điểm số VNIndex.")

    thresholds = [60, 50, 40, 30, 20, 10]
    cols = st.columns(6)
    for col, level in zip(cols, thresholds):
        count = report["counts"][level]
        pct = report["percentages"][level]
        with col:
            st.metric(f"RSI > {level}", f"{count}", f"{pct:.1f}%")

    tone = report.get("tone", "info")
    message = report.get("message", "")
    if tone == "success":
        st.success(message)
    elif tone == "warning":
        st.warning(message)
    elif tone == "error":
        st.error(message)
    else:
        st.info(message)

    return report


# =========================================================
# BUY RECOMMENDATION
# =========================================================
def nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"

    if action in ["MUA GÀ TĂNG TỐC", "MUA PULL ĐẸP", "MUA BREAK"]:
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"

    if action in ["MUA PULL VỪA", "CANH ADD CP MẠNH", "TEST EARLY"]:
        return "10-15% NAV" if market_real >= 8 else "5-10% NAV"

    return "0%"


def buy_recommendation(row, market_real: float):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    group = str(row.get("group", ""))
    score = row.get("total_score", 0)
    dist = row.get("dist_from_ema9_pct", np.nan)
    warning = str(row.get("warning", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    slope_ = row.get("ema9_ma20_slope", np.nan)

    if market_real < 6:
        return "🔴", "KHÔNG MUA", "-", "0%", "Market REAL < 6"

    if "OBV gãy" in warning or "Giá dưới EMA9" in warning:
        return "🔴", "KHÔNG MUA", "-", "0%", "Trục tiền/giá xấu"

    if group == "GÀ TĂNG TỐC" and obv_ok and pd.notna(slope_) and slope_ > 2:
        action = "MUA GÀ TĂNG TỐC"
        return "🟢", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Slope mở mạnh + OBV giữ"

    if group == "PULL ĐẸP" and obv_ok:
        action = "MUA PULL ĐẸP"
        zone = f"{round(ema9_, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        return "🟢", action, zone, nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"

    if group == "PULL VỪA" and obv_ok:
        action = "MUA PULL VỪA"
        zone = f"{round(ema9_ * 0.99, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        return "🟡", action, zone, nav_suggestion(action, market_real), "Pull vừa, mua thăm dò"

    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"

    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Early sạch, test nhỏ"

    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_, 0)} - {round(ema9_ * 1.02, 0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price, 0)}", nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"


def build_buy_table(scan_df: pd.DataFrame, market_real: float) -> pd.DataFrame:
    rows = []

    for _, row in scan_df.iterrows():
        light, action, zone, nav, reason = buy_recommendation(row, market_real)
        rows.append({
            "Mã": row["symbol"],
            "Đèn": light,
            "Hành động": action,
            "Nhóm": row["group"],
            "Giá": row["price"],
            "Vùng mua": zone,
            "NAV": nav,
            "Điểm": row["total_score"],
            "Slope": row["ema9_ma20_slope"],
            "RSI": row["rsi14"],
            "OBV": row["obv_status"],
            "Dist EMA9%": row["dist_from_ema9_pct"],
            "Live": "✅" if row.get("is_live_adjusted", False) else "",
            "Lý do": reason,
            "Cảnh báo": row["warning"],
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["rank_action"] = out["Hành động"].map({
        "MUA PULL ĐẸP": 0,
        "MUA BREAK": 1,
        "MUA GÀ TĂNG TỐC": 2,
        "MUA PULL VỪA": 3,
        "TEST EARLY": 4,
        "CANH ADD CP MẠNH": 5,
        "CHỜ PULL": 6,
        "KHÔNG MUA": 9,
    }).fillna(9)

    out = out.sort_values(
        by=["rank_action", "Điểm", "Slope"],
        ascending=[True, False, False],
    ).drop(columns=["rank_action"])

    return out


# =========================================================
# EVOLUTION ENGINE - HIỂN THỊ REALTIME, LƯU BỀN THEO PHIÊN
# =========================================================
def get_github_token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return None


def read_evolution_history() -> pd.DataFrame:
    """
    Đọc lịch sử evolution.
    Ưu tiên GitHub nếu có token để tránh mất ngày khi Streamlit redeploy/restart.
    Nếu GitHub lỗi thì fallback về file local.
    """
    token = get_github_token()

    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_EVO_PATH}"
            headers = {"Authorization": f"token {token}"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                content = r.json().get("content", "")
                decoded = base64.b64decode(content).decode("utf-8")
                from io import StringIO
                return guard_dataframe_dtypes(pd.read_csv(StringIO(decoded)))
        except Exception:
            pass

    try:
        return guard_dataframe_dtypes(pd.read_csv(EVOLUTION_FILE))
    except Exception:
        return pd.DataFrame()


def write_evolution_history(evo_df: pd.DataFrame) -> str:
    evo_df = guard_dataframe_dtypes(evo_df)
    """
    Ghi evolution ra local và nếu có GITHUB_TOKEN thì commit lên GitHub.
    Đây là điểm sửa bệnh mất ngày 27/5: dữ liệu phải có nơi lưu bền, không chỉ local trên Streamlit.
    """
    try:
        evo_df.to_csv(EVOLUTION_FILE, index=False)
    except Exception:
        pass

    token = get_github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        csv_content = evo_df.to_csv(index=False)
        encoded_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_EVO_PATH}"
        headers = {"Authorization": f"token {token}"}

        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")

        payload = {
            "message": f"Update evolution history {vn_time_str('%Y-%m-%d %H:%M:%S')}",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        put_r = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_r.status_code in [200, 201]:
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_r.status_code}"
    except Exception:
        return "GITHUB_ERROR"
@st.cache_data(ttl=5 * 60, show_spinner=False)
def is_vnindex_trading_today() -> tuple[bool, str]:
    """
    Chỉ trả True khi VNINDEX có dữ liệu ngày hôm nay.
    Nếu thứ 7, CN hoặc ngày lễ: dữ liệu VNINDEX mới nhất sẽ là phiên trước đó => False.
    """
    today = today_str()

    try:
        from vnstock import stock_historical_data

        attempts = [
            {"symbol": "VNINDEX", "type": "index"},
            {"symbol": "VNINDEX", "type": "stock"},
        ]

        last_seen_date = ""

        for cfg in attempts:
            try:
                df = stock_historical_data(
                    symbol=cfg["symbol"],
                    start_date=(vn_now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                    end_date=today,
                    resolution="1D",
                    type=cfg["type"],
                    beautify=True,
                )

                if df is None or df.empty:
                    continue

                date_col = None
                for c in df.columns:
                    if "date" in str(c).lower() or "time" in str(c).lower():
                        date_col = c
                        break

                if date_col is None:
                    continue

                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.dropna(subset=[date_col]).sort_values(date_col)

                if df.empty:
                    continue

                last_date = df[date_col].iloc[-1].strftime("%Y-%m-%d")
                last_seen_date = last_date

                if last_date == today:
                    return True, f"VNINDEX có giao dịch hôm nay: {today}"

            except Exception:
                continue

        return False, f"Không lưu Evolution: VNINDEX mới nhất là {last_seen_date}, không phải {today}"

    except Exception as e:
        return False, f"Không kiểm tra được VNINDEX: {e}"
def save_evolution(scan_df: pd.DataFrame, allow_save: bool = True, reason: str = "") -> tuple[pd.DataFrame, str]:

    """
    Lưu 1 bản cuối cho mỗi ngày/mã.
    Dữ liệu được đọc/ghi qua read_evolution_history + write_evolution_history để không mất phiên khi app restart.
    """
    if not allow_save:
        old_df = read_evolution_history()
        return old_df, f"SKIP_NO_TRADING_SESSION | {reason}"
    today = today_str()
    now_time = vn_time_str("%H:%M:%S")

    rows = []
    for _, r in scan_df.iterrows():
        rows.append({
            "date": today,
            "time": now_time,
            "symbol": r["symbol"],
            "group": r["group"],
            "rank": GROUP_RANK.get(r["group"], 0),
            "score": r.get("total_score", np.nan),
            "price": r.get("price", np.nan),
            "obv": r.get("obv", np.nan),
            "volume": r.get("volume", np.nan),
            "vol_ma20": r.get("vol_ma20", np.nan),
            "is_live_adjusted": r.get("is_live_adjusted", False),

        })

    new_df = guard_dataframe_dtypes(pd.DataFrame(rows))
    old_df = guard_dataframe_dtypes(read_evolution_history())

    if old_df.empty:
        evo_df = new_df
    else:
        evo_df = pd.concat([old_df, new_df], ignore_index=True)

    evo_df = evo_df.drop_duplicates(subset=["date", "symbol"], keep="last")
    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df = evo_df.dropna(subset=["date"])
    # =====================================================
    # DATA ASSET PROTECTION
    # Giữ toàn bộ lịch sử để phục vụ T+ và Brain Learning.
    # Không cắt 120 ngày như phiên bản cũ.
    # =====================================================
    evo_df = evo_df.sort_values(
        ["date", "symbol"]
    ).reset_index(drop=True)
    
    evo_df["date"] = evo_df["date"].dt.strftime("%Y-%m-%d")    
    evo_df = guard_dataframe_dtypes(evo_df)
    
    save_status = write_evolution_history(evo_df)
    return evo_df, save_status
# =========================================================
# STORM LEADERS - CP ĐANG MẠNH LÊN NHANH + TIỀN VÀO MẠNH
# =========================================================
def build_storm_leaders(scan_df: pd.DataFrame) -> pd.DataFrame:
    if scan_df.empty:
        return pd.DataFrame()

    current = scan_df.copy()

    # GREEN2 từ tín hiệu thật của hệ thống
    if "green_2_confirm" in current.columns:
        current["GREEN2"] = np.where(
            current["green_2_confirm"].astype(str).str.contains("GREEN 2", na=False),
            "✅",
            ""
        )
    else:
        current["GREEN2"] = ""

    for col in ["volume", "vol_ma20", "obv", "total_score", "O", "V", "rsi14", "ema9_ma20_slope"]:
        if col not in current.columns:
            current[col] = np.nan

    current["vol_ratio"] = np.where(
        current["vol_ma20"] > 0,
        current["volume"] / current["vol_ma20"],
        np.nan
    )

    current["volume_surge_score"] = np.select(
        [
            current["vol_ratio"] >= 2.0,
            current["vol_ratio"] >= 1.5,
            current["vol_ratio"] >= 1.2,
        ],
        [3, 2, 1],
        default=0
    )

    current["dna_accel"] = 0.0
    current["obv_accel_score"] = 0.0

    evo_df = read_evolution_history()

    if not evo_df.empty and {"date", "symbol", "score", "obv"}.issubset(evo_df.columns):
        hist = evo_df.copy()
        hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
        hist["score"] = pd.to_numeric(hist["score"], errors="coerce")
        hist["obv"] = pd.to_numeric(hist["obv"], errors="coerce")
        hist = hist.dropna(subset=["date", "symbol"])
        hist = hist.sort_values(["symbol", "date"])

        old_rows = []

        for symbol, sub in hist.groupby("symbol"):
            sub = sub.drop_duplicates("date", keep="last").sort_values("date")

            if len(sub) >= 5:
                old = sub.iloc[-5]
            elif len(sub) >= 2:
                old = sub.iloc[0]
            else:
                continue

            old_rows.append({
                "symbol": symbol,
                "old_score": old.get("score", np.nan),
                "old_obv": old.get("obv", np.nan),
            })

        old_df = pd.DataFrame(old_rows)

        if not old_df.empty:
            current = current.merge(old_df, on="symbol", how="left")
            current["dna_accel"] = current["total_score"] - current["old_score"]

            current["obv_accel_score"] = np.where(
                (pd.notna(current["obv"])) &
                (pd.notna(current["old_obv"])) &
                (current["obv"] > current["old_obv"]),
                2,
                0
            )

    current["storm_score"] = (
        current["dna_accel"].fillna(0) * 1.5
        + current["obv_accel_score"].fillna(0) * 2.0
        + current["volume_surge_score"].fillna(0) * 2.0
        + current["O"].fillna(0)
        + current["V"].fillna(0)
    )

    valid_groups = [
    "PULL ĐẸP",
    "PULL VỪA",
    ]


    out = current[
        (current["storm_score"] > 0)
        & (current["group"].isin(valid_groups))
    ].copy()

    if out.empty:
        return pd.DataFrame()

    out = out.sort_values(
        ["storm_score", "volume_surge_score", "dna_accel", "obv_accel_score", "O", "V"],
        ascending=False
    )

    out = out.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "storm_score": "STORM",
        "dna_accel": "DNA ACCEL",
        "obv_accel_score": "OBV ACCEL",
        "volume_surge_score": "VOL SURGE",
        "vol_ratio": "VOL/MA20",
        "total_score": "SCORE",
        "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "obv_status": "OBV",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "MÃ",
        "NHÓM",
        "GIÁ",
        "STORM",
        "GREEN2",
        "DNA ACCEL",
        "OBV ACCEL",
        "VOL SURGE",
        "VOL/MA20",
        "SCORE",
        "RSI",
        "SLOPE",
        "OBV",
        "CẢNH BÁO",
    ]

    cols = [c for c in cols if c in out.columns]

    return out[cols].head(20)

# =========================================================
# EVOLUTION QUALITY ENGINE
# =========================================================
def calculate_evolution_quality(hist_groups, today_rank):

    ranks = [GROUP_RANK.get(g, 0) for g in hist_groups]

    evo_quality = 0
    smoothness = 0

    if len(ranks) < 2:
        return 0, 0

    # =====================================================
    # CHẤM ĐIỂM CHUYỂN PHA
    # =====================================================

    for i in range(len(ranks) - 1):

        old = ranks[i]
        new = ranks[i + 1]

        # EARLY -> PULL
        if old == 2 and new in [3, 4]:
            evo_quality += 18

        # PULL -> MẠNH
        elif old in [3, 4] and new == 6:
            evo_quality += 25

        # MẠNH -> BREAK
        elif old == 6 and new == 5:
            evo_quality += 10

        # PHẠT NHẢY CÓC
        if new - old >= 3:
            evo_quality -= 8

        # PHẠT GÃY CẤU TRÚC
        if old - new >= 2:
            evo_quality -= 10

        # ĐỘ MƯỢT
        diff = abs(new - old)

        if diff <= 1:
            smoothness += 2
        elif diff == 2:
            smoothness += 1
        else:
            smoothness -= diff

    # =====================================================
    # THƯỞNG TIẾN BỘ
    # =====================================================

    growth_steps = 0

    for i in range(len(ranks) - 1):
        if ranks[i + 1] > ranks[i]:
            growth_steps += 1

    evo_quality += growth_steps * 3

    # =====================================================
    # PHẠT ĐỨNG YÊN
    # =====================================================

    flat_steps = 0

    for i in range(len(ranks) - 1):
        if ranks[i + 1] == ranks[i]:
            flat_steps += 1

    evo_quality -= flat_steps * 2

    # =====================================================
    # THƯỞNG ĐÍCH ĐẾN
    # =====================================================

    if today_rank == 6:      # CP MẠNH
        evo_quality += 10

    elif today_rank == 4:    # PULL ĐẸP
        evo_quality += 8

    elif today_rank == 3:    # PULL VỪA
        evo_quality += 5

    elif today_rank == 7:    # TĂNG TỐC
        evo_quality -= 5

    return evo_quality, smoothness
# =========================================================
# EVOLUTION TABLES
# =========================================================
def build_evolution_tables(scan_df: pd.DataFrame):
    evo_df = read_evolution_history()

    current = scan_df[["symbol", "group", "total_score", "price"]].copy()
    current = current.rename(columns={
        "group": "TODAY",
        "total_score": "today_score",
        "price": "today_price",
    })
    current["today_rank"] = current["TODAY"].map(GROUP_RANK).fillna(0)

    if evo_df.empty or not {"date", "symbol", "group"}.issubset(set(evo_df.columns)):
        base = current.copy()
        base["evolution"] = 0
        base["recent_change"] = 0
        base["arrow"] = "➡️"
        base["status"] = "⚪"
        return base, pd.DataFrame()

    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df = evo_df.dropna(subset=["date"])
    evo_df["date"] = evo_df["date"].dt.strftime("%Y-%m-%d")

    dates = sorted(evo_df["date"].unique())[-5:]

    pivot = evo_df.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first",
    ).reindex(columns=dates)

    hist_rows = []

    for symbol in pivot.index:
        row = {"symbol": symbol}
        for d in dates:
            row[d] = pivot.loc[symbol, d]
        hist_rows.append(row)

    hist = pd.DataFrame(hist_rows)

    if hist.empty:
        base = current.copy()
    else:
        base = hist.merge(current, on="symbol", how="outer")
    evo_scores = []
    recent_changes = []

    persistences = []
    dna_flags = []

    evo_quality_scores = []
    smooth_scores = []
    evo_final_scores = []

    arrows = []
    status_icons = []

    for _, r in base.iterrows():

        hist_groups = []

        for d in dates:
            g = r.get(d, np.nan)

            if pd.notna(g):
                hist_groups.append(g)

        today_group = r.get("TODAY", np.nan)
        today_rank = GROUP_RANK.get(today_group, 0)

        if hist_groups:

            first_rank = GROUP_RANK.get(hist_groups[0], 0)
            last_rank = GROUP_RANK.get(hist_groups[-1], 0)

            evolution = today_rank - first_rank
            recent_change = today_rank - last_rank

            ranks = [GROUP_RANK.get(g, 0) for g in hist_groups]

            if pd.notna(today_group):
                ranks.append(today_rank)

            persistence = round(sum(ranks) / len(ranks), 1)

            evo_quality, smoothness = calculate_evolution_quality(
                hist_groups,
                today_rank
            )

            evo_final = round(
                evo_quality * 0.50
                + smoothness * 0.25
                + persistence * 0.15
                + evolution * 0.10,
                1
            )

            if persistence >= 5.0:
                dna = "🟢 DNA MẠNH"

            elif persistence >= 3.5:
                dna = "🟡 BỀN"

            else:
                dna = "⚪ MỚI"

        else:

            evolution = 0
            recent_change = 0
            persistence = 0

            evo_quality = 0
            smoothness = 0
            evo_final = 0

            dna = "⚪ MỚI"

        evo_scores.append(evolution)
        recent_changes.append(recent_change)

        persistences.append(persistence)
        dna_flags.append(dna)

        evo_quality_scores.append(evo_quality)
        smooth_scores.append(smoothness)
        evo_final_scores.append(evo_final)

        if recent_change > 0:
            arrows.append("⬆️")
        elif recent_change < 0:
            arrows.append("⬇️")
        else:
            arrows.append("➡️")

        if evolution > 0:
            status_icons.append("🟢")
        elif evolution < 0:
            status_icons.append("🔴")
        else:
            status_icons.append("⚪")

    base["evolution"] = evo_scores
    base["recent_change"] = recent_changes

    base["Persistence"] = persistences
    base["DNA"] = dna_flags

    base["EvoQuality"] = evo_quality_scores
    base["Smooth"] = smooth_scores
    base["EvoFinal"] = evo_final_scores

    base["arrow"] = arrows
    base["status"] = status_icons
    sort_cols = [
    "EvoFinal",
    "Persistence",
    "evolution",
    "recent_change",
]

    sort_cols = [c for c in sort_cols if c in base.columns]

    if sort_cols:
        base = base.sort_values(
            by=sort_cols,
            ascending=[False] * len(sort_cols)
        ).reset_index(drop=True)

    buy_table = base[
        (
            (base["evolution"] >= 1)
            | (base["recent_change"] >= 1)
        )
        & base["TODAY"].isin([
            "MUA EARLY",
            "PULL VỪA",
            "PULL ĐẸP",
            "MUA BREAK",
            "CP MẠNH",
            "GÀ TĂNG TỐC",
        ])
    ].copy()

    return base, buy_table
# =========================================================
# GROUP PERFORMANCE STATISTICS
# =========================================================
def build_group_statistics():
    evo_df = read_evolution_history()

    if evo_df.empty:
        return pd.DataFrame()

    required = {"date", "symbol", "group", "price"}
    if not required.issubset(set(evo_df.columns)):
        return pd.DataFrame()

    evo_df = evo_df.copy()
    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df["price"] = pd.to_numeric(evo_df["price"], errors="coerce")
    evo_df["group"] = evo_df["group"].astype(str).str.strip()

    evo_df = evo_df.dropna(subset=["date", "symbol", "group", "price"])
    evo_df = evo_df[evo_df["symbol"] != "VNINDEX"].copy()
    evo_df = evo_df.sort_values(["symbol", "date"])

    horizons = {
        "T+1": 1,
        "T+3": 3,
        "T+5": 5,
    }

    results = []

    total_signals = (
        evo_df.groupby("group")
        .size()
        .reset_index(name="TotalSignals")
    )

    for symbol, sub in evo_df.groupby("symbol"):
        sub = (
            sub.sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )

        for i in range(len(sub)):
            start_row = sub.iloc[i]
            start_group = start_row["group"]
            start_price = start_row["price"]

            if pd.isna(start_price) or start_price <= 0:
                continue

            for horizon_name, step in horizons.items():
                future_i = i + step

                if future_i >= len(sub):
                    continue

                future_row = sub.iloc[future_i]
                future_price = future_row["price"]

                if pd.isna(future_price) or future_price <= 0:
                    continue

                ret = (future_price / start_price - 1) * 100

                results.append({
                    "Horizon": horizon_name,
                    "group": start_group,
                    "return_pct": ret,
                    "win": 1 if ret > 0 else 0,
                })

    if not results:
        return pd.DataFrame()

    stat_df = pd.DataFrame(results)

    summary = (
        stat_df.groupby(["Horizon", "group"])
        .agg(
            Samples=("return_pct", "count"),
            WinRate=("win", "mean"),
            AvgReturn=("return_pct", "mean"),
            MedianReturn=("return_pct", "median"),
            MaxReturn=("return_pct", "max"),
            MinReturn=("return_pct", "min"),
        )
        .reset_index()
    )

    summary = summary.merge(total_signals, on="group", how="left")
    summary["Pending"] = summary["TotalSignals"] - summary["Samples"]

    summary["WinRate"] = (summary["WinRate"] * 100).round(1)
    summary["AvgReturn"] = summary["AvgReturn"].round(2)
    summary["MedianReturn"] = summary["MedianReturn"].round(2)
    summary["MaxReturn"] = summary["MaxReturn"].round(2)
    summary["MinReturn"] = summary["MinReturn"].round(2)

    horizon_order = {"T+1": 1, "T+3": 2, "T+5": 3}
    summary["horizon_rank"] = summary["Horizon"].map(horizon_order).fillna(9)

    summary = summary.sort_values(
        ["horizon_rank", "AvgReturn", "WinRate"],
        ascending=[True, False, False]
    ).drop(columns=["horizon_rank"])

    return summary

# =========================================================
# BẢNG TỔNG HỢP NHANH
# =========================================================

def build_group_summary(stats_df):
    if stats_df.empty:
        return pd.DataFrame()

    rows = []

    for group in stats_df["group"].unique():

        sub = stats_df[stats_df["group"] == group]

        t1 = sub[sub["Horizon"] == "T+1"]
        t3 = sub[sub["Horizon"] == "T+3"]
        t5 = sub[sub["Horizon"] == "T+5"]

        def get_val(df, col):
            if df.empty:
                return 0
            return float(df.iloc[0][col])

        win_score = (
            get_val(t1, "WinRate") * 0.5 +
            get_val(t3, "WinRate") * 0.3 +
            get_val(t5, "WinRate") * 0.2
        )

        return_score = (
            get_val(t1, "AvgReturn") * 0.5 +
            get_val(t3, "AvgReturn") * 0.3 +
            get_val(t5, "AvgReturn") * 0.2
        )

        rows.append({
            "group": group,
            "Score": round(win_score, 1),
            "AvgReturn": round(return_score, 2),
            "T+1 Win": get_val(t1, "WinRate"),
            "T+3 Win": get_val(t3, "WinRate"),
            "T+5 Win": get_val(t5, "WinRate"),
        })

    summary = pd.DataFrame(rows)

    summary = summary.sort_values(
        ["Score", "AvgReturn"],
        ascending=False
    ).reset_index(drop=True)

    return summary

# =========================================================
# 👑 TINH HOA LEADERS - TINH HOA CỦA TINH HOA
# =========================================================
def score_rsi_tinh_hoa(rsi):
    """RSI đẹp nhất là vùng 60-70. Quá thấp là yếu, quá cao là nóng."""
    rsi = to_float(rsi)
    if pd.isna(rsi):
        return 0
    if 60 <= rsi <= 70:
        return 15
    if 55 <= rsi < 60 or 70 < rsi <= 75:
        return 11
    if 50 <= rsi < 55 or 75 < rsi <= 80:
        return 6
    if rsi > 80:
        return 3
    return 0


def score_slope_tinh_hoa(slope):
    """Slope đẹp nhất là dương vừa phải: có lực nhưng chưa quá nóng."""
    slope = to_float(slope)
    if pd.isna(slope):
        return 0
    if 1.0 <= slope <= 3.0:
        return 15
    if 0.3 <= slope < 1.0:
        return 10
    if 3.0 < slope <= 5.0:
        return 10
    if 0 < slope < 0.3:
        return 5
    if slope > 5.0:
        return 6
    return 0


def build_tinh_hoa_leaders(
    scan_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    storm_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> pd.DataFrame:
    """
    Bảng Tinh Hoa = giao thoa mềm giữa DNA + Evolution + Storm + chất lượng hiện tại.

    Tư duy:
    - DNA/Persistence: cổ phiếu mạnh bền, không phải mạnh một phiên.
    - GroupStrength: hôm nay đang thuộc nhóm tốt hay không.
    - RSI: ưu tiên vùng 60-70, tránh quá yếu hoặc quá nóng.
    - Slope: ưu tiên tăng đều, chưa quá dốc.
    - Storm: có tiền mới vào hiện tại.
    - Evolution: có tiến hóa hoặc giữ hạng tốt.
    """
    if scan_df.empty:
        return pd.DataFrame()

    valid_groups = [
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "MUA BREAK",
        "CP MẠNH",
        "GÀ TĂNG TỐC",
    ]

    base_cols = [
        "symbol", "group", "price", "total_score", "rsi14", "ema9_ma20_slope",
        "obv_status", "dist_from_ema9_pct", "green_2_confirm", "warning"
    ]
    base_cols = [c for c in base_cols if c in scan_df.columns]
    base = scan_df[base_cols].copy()

    if "group" not in base.columns or "symbol" not in base.columns:
        return pd.DataFrame()

    base = base[base["group"].isin(valid_groups)].copy()
    if base.empty:
        return pd.DataFrame()

    # Ghép DNA/Evolution từ evo_table
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = [
            "symbol", "Persistence", "DNA", "evolution", "recent_change", "TODAY", "today_score"
        ]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        evo_small = evo_table[evo_cols].copy()
        base = base.merge(evo_small, on="symbol", how="left")
    else:
        base["Persistence"] = 0
        base["DNA"] = "⚪ MỚI"
        base["evolution"] = 0
        base["recent_change"] = 0

    for c in ["Persistence", "evolution", "recent_change", "total_score", "rsi14", "ema9_ma20_slope", "dist_from_ema9_pct"]:
        if c not in base.columns:
            base[c] = np.nan
        base[c] = pd.to_numeric(base[c], errors="coerce")

    # Storm set: dùng bảng đã rename cột MÃ từ build_storm_leaders
    storm_symbols = set()
    if storm_df is not None and not storm_df.empty:
        if "MÃ" in storm_df.columns:
            storm_symbols = set(storm_df["MÃ"].astype(str))
        elif "symbol" in storm_df.columns:
            storm_symbols = set(storm_df["symbol"].astype(str))

    base["Storm"] = np.where(base["symbol"].astype(str).isin(storm_symbols), "✅", "")
    base["Green2"] = np.where(
        base.get("green_2_confirm", "").astype(str).str.contains("GREEN 2", na=False),
        "✅",
        ""
    )

    group_strength_map = {
        "GÀ TĂNG TỐC": 25,
        "CP MẠNH": 22,
        "MUA BREAK": 20,
        "PULL ĐẸP": 21,
        "PULL VỪA": 17,
        "MUA EARLY": 13,
    }

    base["DNA_SCORE"] = (base["Persistence"].fillna(0).clip(lower=0, upper=7) / 7 * 30).round(2)
    base["GROUP_SCORE"] = base["group"].map(group_strength_map).fillna(0)
    base["RSI_SCORE"] = base["rsi14"].apply(score_rsi_tinh_hoa)
    base["SLOPE_SCORE"] = base["ema9_ma20_slope"].apply(score_slope_tinh_hoa)
    base["STORM_SCORE"] = np.where(base["Storm"] == "✅", 10, 0)
    base["EVO_SCORE"] = np.select(
        [
            base["evolution"] >= 3,
            base["evolution"] >= 1,
            base["recent_change"] >= 1,
        ],
        [5, 4, 3],
        default=0,
    )

    base["TinhHoa"] = (
        base["DNA_SCORE"]
        + base["GROUP_SCORE"]
        + base["RSI_SCORE"]
        + base["SLOPE_SCORE"]
        + base["STORM_SCORE"]
        + base["EVO_SCORE"]
    ).round(1)

    # Số bảng đồng thuận: DNA đủ bền + Evolution có tiến hóa + Storm có tiền hiện tại
    base["Số bảng"] = (
        (base["Persistence"].fillna(0) >= 3.5).astype(int)
        + ((base["evolution"].fillna(0) >= 1) | (base["recent_change"].fillna(0) >= 1)).astype(int)
        + (base["Storm"] == "✅").astype(int)
    )

    base["Tier"] = np.select(
        [
            base["TinhHoa"] >= 90,
            base["TinhHoa"] >= 80,
            base["TinhHoa"] >= 70,
        ],
        ["🏆 S", "🥇 A", "🥈 B"],
        default="⚪ C",
    )

    def action_row(r):
        if market_real < 6:
            return "🟡 THEO DÕI - MARKET CHƯA ỦNG HỘ"
        if market_forecast < 3:
            return "🟡 CANH NHỎ - FORECAST CÒN YẾU"
        if str(r.get("warning", "")).find("OBV gãy") >= 0:
            return "🔴 LOẠI TẠM - OBV GÃY"
        dist = to_float(r.get("dist_from_ema9_pct", np.nan))
        group = str(r.get("group", ""))
        tier = str(r.get("Tier", ""))
        if group in ["GÀ TĂNG TỐC", "CP MẠNH", "MUA BREAK"] and pd.notna(dist) and dist > 4:
            return "🟡 CHỜ PULL VỀ EMA9"
        if tier == "🏆 S":
            return "🟢 ƯU TIÊN MUA KHI CÓ ĐIỂM ĐẸP"
        if tier == "🥇 A":
            return "🟡 CANH MUA ĐỎ / TEST NHỎ"
        if tier == "🥈 B":
            return "⚪ THEO DÕI THÊM"
        return "⚪ CHƯA PHẢI TINH HOA"

    base["Hành động"] = base.apply(action_row, axis=1)

    # Lọc tinh hoa: ưu tiên điểm cao, hoặc có ít nhất 2 bảng đồng thuận.
    base = base[(base["TinhHoa"] >= 65) | (base["Số bảng"] >= 2)].copy()
    if base.empty:
        return pd.DataFrame()

    base = base.sort_values(
        ["TinhHoa", "Số bảng", "Persistence", "STORM_SCORE", "GROUP_SCORE", "SLOPE_SCORE"],
        ascending=[False, False, False, False, False, False]
    ).reset_index(drop=True)

    base.insert(0, "Rank", range(1, len(base) + 1))
    out = base.rename(columns={
    "symbol": "MÃ",
    "group": "NHÓM",
    "price": "GIÁ",
    "Persistence": "DNA_GOC",
            "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "total_score": "SCORE",
        "evolution": "TIẾN HÓA",
        "recent_change": "GẦN NHẤT",
        "obv_status": "OBV",
        "dist_from_ema9_pct": "DIST EMA9%",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "Rank", "Tier", "MÃ", "TinhHoa", "Số bảng", "NHÓM", "GIÁ", "DNA_GOC", "DNA_SCORE",
        "DNA", "RSI", "SLOPE", "Storm", "Green2", "TIẾN HÓA", "GẦN NHẤT",
        "SCORE", "OBV", "DIST EMA9%", "Hành động", "CẢNH BÁO"
    ]
    cols = [c for c in cols if c in out.columns]

    return out[cols].head(20)


# =========================================================
# 🎯 PULLBACK BUY LIST - BẢNG MUA THỰC CHIẾN
# =========================================================
def build_pullback_buy_list(
    scan_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    storm_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> pd.DataFrame:
    """
    Bảng mua Pullback = cơ hội lên tàu khi cổ phiếu mạnh đang nghỉ.

    Triết lý:
    - Không mua mọi nhịp giảm.
    - Chỉ mua pullback của mã có tiền vào (Storm), sức mạnh bền (DNA/Persistence),
      và không gãy trục giá/tiền.
    - Ưu tiên nhịp test 3-5% từ đỉnh gần nhất, còn giữ EMA9 và vol hạ nhiệt.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    valid_groups = [
        "PULL ĐẸP",
        "PULL VỪA",
        "CP MẠNH",
        "MUA BREAK",
        "MUA EARLY",
        "GÀ TĂNG TỐC",
    ]

    needed = [
        "symbol", "group", "price", "ema9", "breakout_ref", "dist_from_ema9_pct",
        "rsi14", "rsi_slope", "ema9_ma20_slope", "obv_status", "volume", "vol_ma20",
        "total_score", "warning", "green_2_confirm", "is_live_adjusted"
    ]
    base = scan_df[[c for c in needed if c in scan_df.columns]].copy()
    if base.empty or "symbol" not in base.columns:
        return pd.DataFrame()

    base = base[base["group"].isin(valid_groups)].copy()
    if base.empty:
        return pd.DataFrame()

    # Ghép DNA/Evolution.
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = ["symbol", "Persistence", "DNA", "evolution", "recent_change"]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        base = base.merge(evo_table[evo_cols].copy(), on="symbol", how="left")
    else:
        base["Persistence"] = 0
        base["DNA"] = "⚪ MỚI"
        base["evolution"] = 0
        base["recent_change"] = 0

    # Ghép Storm.
    storm_small = pd.DataFrame()
    if storm_df is not None and not storm_df.empty:
        if "MÃ" in storm_df.columns:
            storm_small = storm_df.copy().rename(columns={"MÃ": "symbol", "STORM": "storm_raw"})
        elif "symbol" in storm_df.columns:
            storm_small = storm_df.copy().rename(columns={"STORM": "storm_raw"})

    if not storm_small.empty and "symbol" in storm_small.columns:
        keep = [c for c in ["symbol", "storm_raw", "GREEN2"] if c in storm_small.columns]
        base = base.merge(storm_small[keep], on="symbol", how="left")
    else:
        base["storm_raw"] = 0
        base["GREEN2"] = ""

    for c in [
        "price", "ema9", "breakout_ref", "dist_from_ema9_pct", "rsi14", "rsi_slope",
        "ema9_ma20_slope", "volume", "vol_ma20", "total_score", "Persistence",
        "evolution", "recent_change", "storm_raw"
    ]:
        if c not in base.columns:
            base[c] = np.nan
        base[c] = pd.to_numeric(base[c], errors="coerce")

    base["vol_ratio"] = np.where(base["vol_ma20"] > 0, base["volume"] / base["vol_ma20"], np.nan)
    base["dist_high_pct"] = np.where(
        (base["breakout_ref"] > 0) & pd.notna(base["price"]),
        (base["price"] / base["breakout_ref"] - 1) * 100,
        np.nan,
    )

    # 1) Độ sâu pullback: vùng ngọt nhất là giảm khoảng 2-5% so với đỉnh gần nhất.
    base["PULL_DEPTH_SCORE"] = np.select(
        [
            base["dist_high_pct"].between(-5.5, -2.0, inclusive="both"),
            base["dist_high_pct"].between(-7.0, -1.0, inclusive="both"),
            base["dist_high_pct"].between(-10.0, 0.0, inclusive="both"),
        ],
        [25, 18, 10],
        default=0,
    )

    # 2) Test EMA9: càng sát EMA9 càng dễ đặt stop ngắn.
    base["EMA_TEST_SCORE"] = np.select(
        [
            base["dist_from_ema9_pct"].between(-1.5, 1.5, inclusive="both"),
            base["dist_from_ema9_pct"].between(-3.0, 2.5, inclusive="both"),
            base["dist_from_ema9_pct"].between(-4.5, 4.0, inclusive="both"),
        ],
        [20, 14, 7],
        default=0,
    )

    # 3) DNA/Persistence: sức mạnh bền.
    base["DNA_SCORE"] = (base["Persistence"].fillna(0).clip(lower=0, upper=7) / 7 * 18).round(2)

    # 4) Storm: có tiền hiện tại.
    base["STORM_SCORE"] = np.where(base["storm_raw"].fillna(0) > 0, np.minimum(base["storm_raw"].fillna(0) * 3, 15), 0)

    # 5) Evolution: đang tiến hóa hoặc gần đây có cải thiện.
    base["EVO_SCORE"] = np.select(
        [
            base["evolution"] >= 2,
            base["evolution"] >= 1,
            base["recent_change"] >= 1,
        ],
        [10, 8, 6],
        default=0,
    )

    # 6) Chất lượng kỹ thuật: RSI, OBV, slope, vol hạ nhiệt.
    base["RSI_SCORE"] = np.select(
        [
            base["rsi14"].between(55, 70, inclusive="both"),
            base["rsi14"].between(50, 75, inclusive="both"),
        ],
        [8, 4],
        default=0,
    )
    base["OBV_SCORE"] = np.where(base.get("obv_status", "") == "🟢", 10, 0)
    base["SLOPE_SCORE"] = np.select(
        [
            base["ema9_ma20_slope"].between(0.3, 4.0, inclusive="both"),
            base["ema9_ma20_slope"].between(0.0, 6.0, inclusive="both"),
        ],
        [8, 4],
        default=0,
    )
    base["VOL_COOL_SCORE"] = np.select(
        [
            base["vol_ratio"].between(0.45, 1.10, inclusive="both"),
            base["vol_ratio"].between(0.30, 1.50, inclusive="both"),
        ],
        [8, 4],
        default=0,
    )

    base["PullScore"] = (
        base["PULL_DEPTH_SCORE"]
        + base["EMA_TEST_SCORE"]
        + base["DNA_SCORE"]
        + base["STORM_SCORE"]
        + base["EVO_SCORE"]
        + base["RSI_SCORE"]
        + base["OBV_SCORE"]
        + base["SLOPE_SCORE"]
        + base["VOL_COOL_SCORE"]
    ).clip(upper=100).round(1)

    base["Green2"] = np.where(
        base.get("green_2_confirm", "").astype(str).str.contains("GREEN 2", na=False)
        | base.get("GREEN2", "").astype(str).str.contains("✅", na=False),
        "✅",
        "",
    )

    def pull_action(r):
        warning = str(r.get("warning", ""))
        if market_real < 6:
            return "🟡 THEO DÕI - MARKET < 6"
        if "OBV gãy" in warning:
            return "🔴 BỎ QUA - OBV GÃY"
        if "Giá dưới EMA9" in warning and to_float(r.get("dist_from_ema9_pct", np.nan)) < -3:
            return "🔴 CHỜ LẠI - THỦNG EMA9 XA"
        score = to_float(r.get("PullScore", 0), 0)
        if score >= 78:
            return "🟢 ƯU TIÊN MUA PULL"
        if score >= 65:
            return "🟡 MUA THĂM DÒ / CANH ĐỎ"
        if score >= 52:
            return "⚪ THEO DÕI SÁT"
        return "⚪ CHƯA ĐỦ PULL"

    def stop_zone(r):
        ema9_ = to_float(r.get("ema9", np.nan))
        price_ = to_float(r.get("price", np.nan))
        if pd.notna(ema9_) and ema9_ > 0:
            return f"{round(ema9_ * 0.97, 0)} - {round(ema9_ * 0.985, 0)}"
        if pd.notna(price_) and price_ > 0:
            return f"{round(price_ * 0.965, 0)}"
        return "-"

    def buy_zone(r):
        ema9_ = to_float(r.get("ema9", np.nan))
        price_ = to_float(r.get("price", np.nan))
        if pd.notna(ema9_) and ema9_ > 0:
            return f"{round(ema9_ * 0.99, 0)} - {round(ema9_ * 1.015, 0)}"
        if pd.notna(price_) and price_ > 0:
            return f"{round(price_ * 0.99, 0)} - {round(price_ * 1.01, 0)}"
        return "-"

    def nav_pull(r):
        score = to_float(r.get("PullScore", 0), 0)
        if market_real < 6:
            return "0%"
        if score >= 78:
            return "10-15% NAV" if market_real >= 8 else "5-10% NAV"
        if score >= 65:
            return "5-10% NAV"
        return "0%"

    base["Hành động"] = base.apply(pull_action, axis=1)
    base["Vùng mua"] = base.apply(buy_zone, axis=1)
    base["Stop tham chiếu"] = base.apply(stop_zone, axis=1)
    base["NAV"] = base.apply(nav_pull, axis=1)

    # Loại bớt mã pull quá xấu để bảng thực chiến gọn.
    base = base[
    base["group"].isin(["PULL ĐẸP", "PULL VỪA"])
    & (base["PullScore"] >= 45)
    ].copy()
    if base.empty:
        return pd.DataFrame()

    base = base.sort_values(
        ["PullScore", "PULL_DEPTH_SCORE", "EMA_TEST_SCORE", "DNA_SCORE", "STORM_SCORE"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)

    base.insert(0, "Rank", range(1, len(base) + 1))
    out = base.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "ema9": "EMA9",
        "Persistence": "DNA_GỐC",
        "DNA": "DNA_LOẠI",
        "evolution": "TIẾN HÓA",
        "recent_change": "GẦN NHẤT",
        "storm_raw": "STORM",
        "dist_high_pct": "CÁCH ĐỈNH%",
        "dist_from_ema9_pct": "DIST EMA9%",
        "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "vol_ratio": "VOL/MA20",
        "obv_status": "OBV",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "Rank", "MÃ", "PullScore", "Hành động", "NAV", "NHÓM", "GIÁ", "Vùng mua", "Stop tham chiếu",
        "CÁCH ĐỈNH%", "DIST EMA9%", "DNA_GỐC", "DNA_LOẠI", "STORM", "TIẾN HÓA", "GẦN NHẤT",
        "RSI", "SLOPE", "VOL/MA20", "OBV", "Green2", "CẢNH BÁO"
    ]
    cols = [c for c in cols if c in out.columns]
    return out[cols].head(30)


# =========================================================
# 🌱 EARLY BUY LAB - CẠN CUNG + GREEN2 GẦN ĐÁY
# =========================================================
def build_early_buy_lab(
    scan_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    storm_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> pd.DataFrame:
    """
    EARLY BUY LAB tìm cổ phiếu vừa bật khỏi vùng đáy bằng 2 nến xanh nhỏ.

    Khác Pullback Buy List:
    - Pullback mua mã đã mạnh và đang nghỉ.
    - Early Buy Lab săn mã vừa có dấu hiệu dòng tiền quay lại sau giai đoạn cạn cung.

    Điều kiện lõi:
    - RSI còn thấp 45-58.
    - Có EARLY GREEN2.
    - Volume trước đó cạn so với MA20.
    - Giá còn gần đáy 20/60 phiên.
    - Slope chưa quá nóng.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    needed = [
        "symbol", "group", "price", "ema9", "ma20", "rsi14", "rsi_slope",
        "ema9_ma20_slope", "obv_status", "volume", "vol_ma20", "total_score",
        "green_2_confirm", "early_green2", "early_dry_green2", "dryup_ratio_5",
        "dryup_ratio_10", "near_bottom_20_pct", "near_bottom_60_pct",
        "dist_high20_pct", "dist_from_ema9_pct", "body_pct", "warning",
        "is_live_adjusted",
    ]
    base = scan_df[[c for c in needed if c in scan_df.columns]].copy()
    if base.empty or "symbol" not in base.columns:
        return pd.DataFrame()

    for c in [
        "price", "ema9", "ma20", "rsi14", "rsi_slope", "ema9_ma20_slope",
        "volume", "vol_ma20", "total_score", "dryup_ratio_5", "dryup_ratio_10",
        "near_bottom_20_pct", "near_bottom_60_pct", "dist_high20_pct",
        "dist_from_ema9_pct", "body_pct",
    ]:
        if c not in base.columns:
            base[c] = np.nan
        base[c] = pd.to_numeric(base[c], errors="coerce")

    if "early_green2" not in base.columns:
        base["early_green2"] = ""
    if "early_dry_green2" not in base.columns:
        base["early_dry_green2"] = ""

    base["EarlyGreen2"] = np.where(
        base["early_green2"].astype(str).str.contains("EARLY GREEN2", na=False),
        "✅",
        "",
    )
    base["DryUp"] = np.where(
        (base["dryup_ratio_5"] <= 0.75) | (base["dryup_ratio_10"] <= 0.85),
        "✅",
        "",
    )
    base["NearBottom"] = np.where(
        (base["near_bottom_20_pct"] <= 12) & (base["near_bottom_60_pct"] <= 22),
        "✅",
        "",
    )

    # Ghép DNA/Evolution.
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = ["symbol", "Persistence", "DNA", "evolution", "recent_change"]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        base = base.merge(evo_table[evo_cols].copy(), on="symbol", how="left")
    else:
        base["Persistence"] = 0
        base["DNA"] = "⚪ MỚI"
        base["evolution"] = 0
        base["recent_change"] = 0

    for c in ["Persistence", "evolution", "recent_change"]:
        if c not in base.columns:
            base[c] = 0
        base[c] = pd.to_numeric(base[c], errors="coerce").fillna(0)

    # Ghép Storm.
    storm_small = pd.DataFrame()
    if storm_df is not None and not storm_df.empty:
        if "MÃ" in storm_df.columns:
            storm_small = storm_df.copy().rename(columns={"MÃ": "symbol", "STORM": "storm_raw"})
        elif "symbol" in storm_df.columns:
            storm_small = storm_df.copy().rename(columns={"STORM": "storm_raw"})

    if not storm_small.empty and "symbol" in storm_small.columns:
        keep = [c for c in ["symbol", "storm_raw"] if c in storm_small.columns]
        base = base.merge(storm_small[keep], on="symbol", how="left")
    else:
        base["storm_raw"] = 0

    base["storm_raw"] = pd.to_numeric(base["storm_raw"], errors="coerce").fillna(0)
    base["Storm"] = np.where(base["storm_raw"] > 0, "✅", "")

    # Bộ lọc lõi: chỉ giữ đúng dạng anh đang muốn săn.
    base = base[
        (base["EarlyGreen2"] == "✅")
        & (base["DryUp"] == "✅")
        & (base["NearBottom"] == "✅")
        & (base["rsi14"].between(45, 58, inclusive="both"))
        & (base["ema9_ma20_slope"] <= 2.5)
        & (base["body_pct"].abs() <= 5.5)
    ].copy()

    if base.empty:
        return pd.DataFrame()

    base["RSI_SCORE"] = np.select(
        [
            base["rsi14"].between(47, 54, inclusive="both"),
            base["rsi14"].between(45, 58, inclusive="both"),
        ],
        [22, 15],
        default=0,
    )
    base["DRY_SCORE"] = np.select(
        [
            base["dryup_ratio_5"] <= 0.60,
            base["dryup_ratio_5"] <= 0.75,
            base["dryup_ratio_10"] <= 0.85,
        ],
        [22, 17, 12],
        default=0,
    )
    base["BOTTOM_SCORE"] = np.select(
        [
            (base["near_bottom_20_pct"] <= 6) & (base["near_bottom_60_pct"] <= 14),
            (base["near_bottom_20_pct"] <= 10) & (base["near_bottom_60_pct"] <= 20),
            (base["near_bottom_20_pct"] <= 12) & (base["near_bottom_60_pct"] <= 22),
        ],
        [20, 16, 12],
        default=0,
    )
    base["OBV_SCORE"] = np.where(base.get("obv_status", "") == "🟢", 12, 5)
    base["SLOPE_SCORE"] = np.select(
        [
            base["ema9_ma20_slope"].between(-1.5, 1.2, inclusive="both"),
            base["ema9_ma20_slope"].between(-2.5, 2.5, inclusive="both"),
        ],
        [12, 8],
        default=0,
    )
    base["DNA_SCORE"] = (base["Persistence"].clip(lower=0, upper=7) / 7 * 10).round(2)
    base["STORM_SCORE"] = np.where(base["storm_raw"] > 0, np.minimum(base["storm_raw"] * 1.5, 8), 0)
    base["EVO_SCORE"] = np.select(
        [
            base["evolution"] >= 2,
            base["evolution"] >= 1,
            base["recent_change"] >= 1,
        ],
        [6, 5, 4],
        default=0,
    )

    base["EarlyScore"] = (
        base["RSI_SCORE"]
        + base["DRY_SCORE"]
        + base["BOTTOM_SCORE"]
        + base["OBV_SCORE"]
        + base["SLOPE_SCORE"]
        + base["DNA_SCORE"]
        + base["STORM_SCORE"]
        + base["EVO_SCORE"]
    ).clip(upper=100).round(1)

    def early_action(r):
        warning = str(r.get("warning", ""))
        if market_real < 6:
            return "🟡 THEO DÕI - MARKET < 6"
        if market_forecast < 3:
            return "🟡 TEST RẤT NHỎ - FORECAST YẾU"
        if "OBV gãy" in warning:
            return "⚪ CHỜ OBV XÁC NHẬN"
        score = to_float(r.get("EarlyScore", 0), 0)
        if score >= 78:
            return "🟢 TEST EARLY ĐẸP"
        if score >= 65:
            return "🟡 CANH ĐỎ / TEST NHỎ"
        return "⚪ THEO DÕI THÊM"

    def early_nav(r):
        if market_real < 6:
            return "0%"
        score = to_float(r.get("EarlyScore", 0), 0)
        if score >= 78:
            return "5-10% NAV"
        if score >= 65:
            return "3-5% NAV"
        return "0%"

    def early_buy_zone(r):
        price_ = to_float(r.get("price", np.nan))
        ema9_ = to_float(r.get("ema9", np.nan))
        if pd.notna(ema9_) and ema9_ > 0:
            return f"{round(min(price_, ema9_ * 1.005), 0)} - {round(ema9_ * 1.02, 0)}"
        if pd.notna(price_) and price_ > 0:
            return f"{round(price_ * 0.99, 0)} - {round(price_ * 1.01, 0)}"
        return "-"

    def early_stop_zone(r):
        price_ = to_float(r.get("price", np.nan))
        ema9_ = to_float(r.get("ema9", np.nan))
        if pd.notna(ema9_) and ema9_ > 0:
            return f"{round(ema9_ * 0.965, 0)} - {round(ema9_ * 0.98, 0)}"
        if pd.notna(price_) and price_ > 0:
            return f"{round(price_ * 0.965, 0)}"
        return "-"

    base["Hành động"] = base.apply(early_action, axis=1)
    base["NAV"] = base.apply(early_nav, axis=1)
    base["Vùng mua"] = base.apply(early_buy_zone, axis=1)
    base["Stop tham chiếu"] = base.apply(early_stop_zone, axis=1)

    base = base.sort_values(
        ["EarlyScore", "BOTTOM_SCORE", "DRY_SCORE", "RSI_SCORE", "OBV_SCORE"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)

    base.insert(0, "Rank", range(1, len(base) + 1))
    out = base.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "rsi14": "RSI",
        "rsi_slope": "RSI SLOPE",
        "ema9_ma20_slope": "SLOPE",
        "dryup_ratio_5": "DRY5",
        "dryup_ratio_10": "DRY10",
        "near_bottom_20_pct": "GẦN ĐÁY 20D%",
        "near_bottom_60_pct": "GẦN ĐÁY 60D%",
        "dist_high20_pct": "CÁCH ĐỈNH 20D%",
        "dist_from_ema9_pct": "DIST EMA9%",
        "body_pct": "BODY%",
        "obv_status": "OBV",
        "Persistence": "DNA_GỐC",
        "DNA": "DNA_LOẠI",
        "evolution": "TIẾN HÓA",
        "recent_change": "GẦN NHẤT",
        "storm_raw": "STORM",
        "total_score": "SCORE",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "Rank", "MÃ", "EarlyScore", "Hành động", "NAV", "NHÓM", "GIÁ",
        "Vùng mua", "Stop tham chiếu", "RSI", "RSI SLOPE", "SLOPE",
        "DRY5", "DRY10", "GẦN ĐÁY 20D%", "GẦN ĐÁY 60D%",
        "CÁCH ĐỈNH 20D%", "DIST EMA9%", "BODY%", "OBV", "Storm",
        "DNA_GỐC", "DNA_LOẠI", "TIẾN HÓA", "GẦN NHẤT", "SCORE", "CẢNH BÁO",
    ]
    cols = [c for c in cols if c in out.columns]
    return out[cols].head(30)


# =========================================================
# 🟢🔴 XANH MUA - ĐỎ BÁN LAB
# =========================================================
def build_green_red_board(
    scan_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    storm_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> pd.DataFrame:
    """
    Bảng Xanh Mua - Đỏ Bán LAB.

    Mục tiêu:
    - TREND_SCORE: cổ phiếu có khỏe, có tiền, có DNA/Evolution hay không.
    - BUY_SCORE: điểm mua hiện tại có đẹp, có gần EMA9, RSI vừa phải, chưa nóng hay không.
    - TÍN HIỆU: ghép Market + Trend + Buy để ra đèn giao thông.

    Bảng này chỉ đọc scan_df/evo_table/storm_df, không làm thay đổi các bảng cũ.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    base = scan_df.copy()

    # -----------------------------------------------------
    # GHÉP EVOLUTION / DNA
    # -----------------------------------------------------
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = [
            "symbol",
            "Persistence",
            "DNA",
            "evolution",
            "recent_change",
            "EvoFinal",
            "EvoQuality",
            "Smooth",
        ]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        base = base.merge(evo_table[evo_cols], on="symbol", how="left")

    # -----------------------------------------------------
    # GHÉP STORM
    # -----------------------------------------------------
    base["Storm"] = 0.0

    if storm_df is not None and not storm_df.empty and "MÃ" in storm_df.columns:
        s = storm_df.copy()
        s = s.rename(columns={
            "MÃ": "symbol",
            "STORM": "Storm_from_storm",
        })

        keep_cols = [c for c in ["symbol", "Storm_from_storm"] if c in s.columns]
        if keep_cols:
            base = base.merge(s[keep_cols], on="symbol", how="left")
            if "Storm_from_storm" in base.columns:
                base["Storm"] = base["Storm_from_storm"].fillna(0)

    # -----------------------------------------------------
    # CHUẨN HÓA CỘT
    # -----------------------------------------------------
    numeric_cols = [
        "total_score",
        "rsi14",
        "rsi_slope",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "dist_from_ema9_pct",
        "volume",
        "vol_ma20",
        "Persistence",
        "evolution",
        "recent_change",
        "EvoFinal",
        "EvoQuality",
        "Smooth",
        "Storm",
        "near_bottom_20_pct",
        "near_bottom_60_pct",
        "dryup_ratio_5",
        "dryup_ratio_10",
        "dist_high20_pct",
        "body_pct",
        "E",
        "R",
        "O",
        "S",
        "RS",
        "V",
    ]

    for c in numeric_cols:
        if c not in base.columns:
            base[c] = np.nan
        base[c] = pd.to_numeric(base[c], errors="coerce")

    for c in [
        "symbol",
        "group",
        "obv_status",
        "warning",
        "early_dry_green2",
        "early_green2",
        "green_2_confirm",
        "pull_label",
    ]:
        if c not in base.columns:
            base[c] = ""

    base["vol_ratio"] = np.where(
        base["vol_ma20"] > 0,
        base["volume"] / base["vol_ma20"],
        np.nan,
    )

    # =====================================================
    # TREND SCORE: CỔ PHIẾU CÓ KHỎE KHÔNG?
    # =====================================================
    score_core = base["total_score"].fillna(0).clip(-3, 10) * 5

    score_persistence = base["Persistence"].fillna(0).clip(0, 7) * 4

    score_evolution = (
        base["evolution"].fillna(0).clip(0, 3) * 5
        + base["recent_change"].fillna(0).clip(0, 2) * 4
        + base["EvoFinal"].fillna(0).clip(0, 30) * 0.35
    )

    score_money = (
        np.where(base["obv_status"] == "🟢", 12, 0)
        + np.where(base["O"].fillna(0) >= 1, 6, 0)
        + np.where(base["Storm"].fillna(0) > 0, 12, 0)
    )

    score_slope = np.select(
        [
            base["ema9_ma20_slope"].between(0.3, 4.5),
            base["ema9_ma20_slope"].between(0.0, 0.3),
            base["ema9_ma20_slope"].between(4.5, 7.0),
        ],
        [12, 6, 5],
        default=0,
    )

    score_group_trend = base["group"].map({
        "PULL ĐẸP": 14,
        "PULL VỪA": 12,
        "CP MẠNH": 12,
        "MUA BREAK": 10,
        "MUA EARLY": 9,
        "GÀ TĂNG TỐC": 8,
        "TÍCH LŨY": 4,
        "THEO DÕI": 0,
    }).fillna(0)

    trend_penalty = (
        np.where(base["obv_status"] != "🟢", 12, 0)
        + np.where(base["ema9_ma20_slope"] < 0, 12, 0)
        + np.where(base["total_score"] <= 1, 10, 0)
    )

    base["TREND_SCORE"] = (
        score_core
        + score_persistence
        + score_evolution
        + score_money
        + score_slope
        + score_group_trend
        - trend_penalty
    ).clip(0, 100).round(1)

    # =====================================================
    # BUY SCORE: ĐIỂM MUA CÓ ĐẸP KHÔNG?
    # =====================================================
    group_buy_score = base["group"].map({
        "PULL ĐẸP": 30,
        "PULL VỪA": 24,
        "MUA EARLY": 20,
        "TÍCH LŨY": 10,
        "CP MẠNH": 8,
        "MUA BREAK": 5,
        "GÀ TĂNG TỐC": 0,
        "THEO DÕI": 0,
    }).fillna(0)

    rsi_buy_score = np.select(
        [
            base["rsi14"].between(45, 58),
            base["rsi14"].between(58, 68),
            base["rsi14"].between(68, 72),
            base["rsi14"].between(40, 45),
        ],
        [18, 16, 8, 6],
        default=0,
    )

    ema_buy_score = np.select(
        [
            base["dist_from_ema9_pct"].between(-1.5, 1.5),
            base["dist_from_ema9_pct"].between(-3.0, 2.5),
            base["dist_from_ema9_pct"].between(-5.0, 4.0),
        ],
        [20, 14, 6],
        default=0,
    )

    volume_buy_score = np.select(
        [
            base["vol_ratio"].between(0.45, 1.15),
            base["vol_ratio"].between(0.30, 1.50),
            base["vol_ratio"].between(1.50, 2.00),
        ],
        [10, 6, 3],
        default=0,
    )

    dryup_score = np.where(
        (base["dryup_ratio_5"] <= 0.75) | (base["dryup_ratio_10"] <= 0.85),
        8,
        0,
    )

    early_bonus = np.where(
        base["early_dry_green2"].astype(str).str.contains("EARLY DRY", na=False),
        14,
        np.where(
            base["early_green2"].astype(str).str.contains("EARLY GREEN2", na=False),
            8,
            0,
        ),
    )

    pull_bonus = np.where(
        base["pull_label"].astype(str).eq("PULL ĐẸP"),
        8,
        np.where(base["pull_label"].astype(str).eq("PULL VỪA"), 5, 0),
    )

    money_buy_score = (
        np.where(base["obv_status"] == "🟢", 10, 0)
        + np.where(base["ema9_ma20_slope"] > 0, 8, 0)
    )

    hot_penalty = (
        np.where(base["rsi14"] > 75, 15, 0)
        + np.where(base["rsi14"] > 80, 8, 0)
        + np.where(base["dist_from_ema9_pct"] > 5, 15, 0)
        + np.where(base["dist_from_ema9_pct"] > 8, 8, 0)
        + np.where(base["group"] == "GÀ TĂNG TỐC", 18, 0)
        + np.where(base["obv_status"] != "🟢", 18, 0)
        + np.where(base["ema9_ma20_slope"] < 0, 12, 0)
    )

    base["BUY_SCORE"] = (
        group_buy_score
        + rsi_buy_score
        + ema_buy_score
        + volume_buy_score
        + dryup_score
        + early_bonus
        + pull_bonus
        + money_buy_score
        - hot_penalty
    ).clip(0, 100).round(1)

    # =====================================================
    # ĐÈN GIAO THÔNG
    # =====================================================
    def make_signal(row):
        trend = to_float(row.get("TREND_SCORE", 0), 0)
        buy = to_float(row.get("BUY_SCORE", 0), 0)
        group = str(row.get("group", ""))
        warning = str(row.get("warning", ""))

        bad_warning = ("OBV gãy" in warning) or ("Giá dưới EMA9" in warning) or ("Slope âm" in warning)

        if market_real < 6:
            if trend >= 75 and buy >= 75 and not bad_warning:
                return "🟡 THEO DÕI - MARKET YẾU"
            return "🔴 KHÔNG MUA"

        if bad_warning and buy < 75:
            return "🔴 ĐỎ TRÁNH"

        if trend >= 78 and buy >= 78:
            return "🟢 XANH MUA"

        if trend >= 70 and buy >= 65:
            return "🟢 XANH NHẸ"

        if trend >= 75 and buy < 60:
            if group in ["CP MẠNH", "MUA BREAK", "GÀ TĂNG TỐC"]:
                return "🟡 CP KHỎE - CHỜ PULL"
            return "🟡 CHỜ ĐIỂM MUA"

        if trend >= 60 and buy >= 55:
            return "🟡 CANH MUA NHỎ"

        if trend < 45 or buy < 35:
            return "🔴 ĐỎ TRÁNH"

        return "⚪ THEO DÕI"

    base["TÍN HIỆU"] = base.apply(make_signal, axis=1)
    base["ĐÈN"] = base["TÍN HIỆU"].astype(str).str[:1]

    base["LÝ DO"] = np.select(
        [
            base["TÍN HIỆU"].astype(str).str.startswith("🟢"),
            base["TÍN HIỆU"].astype(str).str.contains("CHỜ PULL", na=False),
            base["BUY_SCORE"] >= 75,
            base["TREND_SCORE"] >= 75,
            base["TÍN HIỆU"].astype(str).str.startswith("🔴"),
        ],
        [
            "Trend khỏe + điểm mua đẹp",
            "Cổ phiếu khỏe nhưng điểm mua chưa đẹp",
            "Điểm mua đẹp",
            "Cổ phiếu khỏe, cần thêm điểm mua",
            "Chưa đủ điều kiện hoặc cảnh báo xấu",
        ],
        default="Theo dõi thêm",
    )

    # Gợi ý vùng mua theo triết lý pull/early.
    base["VÙNG MUA"] = np.where(
        base["group"].isin(["PULL ĐẸP", "PULL VỪA"]),
        base["ema9"].apply(lambda x: f"{round(x * 0.99, 0)} - {round(x * 1.01, 0)}" if pd.notna(x) else "-"),
        base["price"].apply(lambda x: f"{round(x * 0.99, 0)} - {round(x * 1.01, 0)}" if pd.notna(x) else "-"),
    )

    base["NAV"] = np.select(
        [
            base["TÍN HIỆU"].astype(str).str.startswith("🟢") & (market_real >= 8),
            base["TÍN HIỆU"].astype(str).str.startswith("🟢") & (market_real >= 6),
            base["TÍN HIỆU"].astype(str).str.startswith("🟡") & (market_real >= 6),
        ],
        [
            "10-15% NAV",
            "5-10% NAV",
            "0-5% NAV",
        ],
        default="0%",
    )

    out = base.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "dist_from_ema9_pct": "DIST EMA9%",
        "vol_ratio": "VOL/MA20",
        "obv_status": "OBV",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "ĐÈN",
        "MÃ",
        "TÍN HIỆU",
        "TREND_SCORE",
        "BUY_SCORE",
        "NHÓM",
        "GIÁ",
        "VÙNG MUA",
        "NAV",
        "RSI",
        "SLOPE",
        "DIST EMA9%",
        "VOL/MA20",
        "OBV",
        "Persistence",
        "evolution",
        "recent_change",
        "Storm",
        "early_dry_green2",
        "LÝ DO",
        "CẢNH BÁO",
    ]
    cols = [c for c in cols if c in out.columns]

    rank_signal = out["TÍN HIỆU"].map({
        "🟢 XANH MUA": 0,
        "🟢 XANH NHẸ": 1,
        "🟡 CANH MUA NHỎ": 2,
        "🟡 THEO DÕI - MARKET YẾU": 3,
        "🟡 CP KHỎE - CHỜ PULL": 4,
        "🟡 CHỜ ĐIỂM MUA": 5,
        "⚪ THEO DÕI": 6,
        "🔴 ĐỎ TRÁNH": 8,
        "🔴 KHÔNG MUA": 9,
    }).fillna(7)

    out = out.assign(_rank_signal=rank_signal)
    out = out.sort_values(
        ["_rank_signal", "BUY_SCORE", "TREND_SCORE"],
        ascending=[True, False, False],
    ).drop(columns=["_rank_signal"]).reset_index(drop=True)

    return out[cols].head(60)


def style_green_red_board(df: pd.DataFrame):
    """Tô màu cả dòng theo tín hiệu."""
    def row_style(row):
        sig = str(row.get("TÍN HIỆU", ""))

        if sig.startswith("🟢"):
            return ["background-color: #d9f7d9; color: #064e06; font-weight: 600"] * len(row)

        if sig.startswith("🟡"):
            return ["background-color: #fff3cd; color: #5f4300"] * len(row)

        if sig.startswith("🔴"):
            return ["background-color: #f8d7da; color: #6b0000"] * len(row)

        return ["background-color: #f5f5f5; color: #333333"] * len(row)

    return (
        df.style
        .apply(row_style, axis=1)
        .format({
            "TREND_SCORE": "{:.1f}",
            "BUY_SCORE": "{:.1f}",
            "GIÁ": "{:.0f}",
            "RSI": "{:.1f}",
            "SLOPE": "{:.2f}",
            "DIST EMA9%": "{:.2f}",
            "VOL/MA20": "{:.2f}",
            "Persistence": "{:.1f}",
            "evolution": "{:.0f}",
            "recent_change": "{:.0f}",
            "Storm": "{:.1f}",
        }, na_rep="")
    )



# =========================================================

# =========================================================
# BUY ELITE V3 / LEARNING ENGINE - TỰ HỌC CHẬM TỪ LỊCH SỬ
# =========================================================
def _github_read_text(path: str) -> str | None:
    """Đọc text từ GitHub nếu có token; lỗi thì trả None để fallback local."""
    token = get_github_token()
    if not token:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {token}"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            content = r.json().get("content", "")
            return base64.b64decode(content).decode("utf-8")
    except Exception:
        pass
    return None


def _github_write_text(path: str, text: str, message: str) -> str:
    """Ghi text lên GitHub nếu có token; đồng thời luôn ghi local."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

    token = get_github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {token}"}
        encoded_content = base64.b64encode(text.encode("utf-8")).decode("utf-8")

        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")

        payload = {"message": message, "content": encoded_content}
        if sha:
            payload["sha"] = sha

        put_r = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_r.status_code in [200, 201]:
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_r.status_code}"
    except Exception:
        return "GITHUB_ERROR"


def default_buy_elite_learning_profile() -> dict:
    return {
        "version": "BUY_ELITE_LEARNING_V3",
        "mode": "WARMUP",
        "created_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "updated_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "completed_t5": 0,
        "baseline_winrate": None,
        "min_completed_to_learn": 80,
        "min_feature_samples": 20,
        "note": "WARMUP: chưa đủ dữ liệu, multiplier giữ gần 1.0 để không làm méo hệ thống.",
        "multipliers": {
            "market": 1.0,
            "action": 1.0,
            "storm": 1.0,
            "evo": 1.0,
            "zone": 1.0,
            "obv": 1.0,
            "rsi_penalty": 1.0,
            "dist_penalty": 1.0,
        },
        "regime_multipliers": {
            "WINTER": {},
            "NEUTRAL": {},
            "SPRING": {},
        },
        "insights": [],
    }


def read_buy_elite_learning_profile() -> dict:
    text = _github_read_text(BUY_ELITE_PROFILE_FILE)
    if text is None:
        try:
            with open(BUY_ELITE_PROFILE_FILE, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            return default_buy_elite_learning_profile()
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return default_buy_elite_learning_profile()
        base = default_buy_elite_learning_profile()
        base.update(obj)
        base.setdefault("multipliers", {}).update(obj.get("multipliers", {}))
        base.setdefault("regime_multipliers", {}).update(obj.get("regime_multipliers", {}))
        return base
    except Exception:
        return default_buy_elite_learning_profile()


def write_buy_elite_learning_profile(profile: dict) -> str:
    try:
        text = json.dumps(profile, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(default_buy_elite_learning_profile(), ensure_ascii=False, indent=2)
    return _github_write_text(
        BUY_ELITE_PROFILE_FILE,
        text,
        f"Update BUY ELITE learning profile {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def read_buy_elite_history() -> pd.DataFrame:
    text = _github_read_text(BUY_ELITE_HISTORY_FILE)
    if text is not None:
        try:
            from io import StringIO
            return pd.read_csv(StringIO(text))
        except Exception:
            pass
    try:
        return guard_dataframe_dtypes(pd.read_csv(BUY_ELITE_HISTORY_FILE))
    except Exception:
        return pd.DataFrame()


def write_buy_elite_history(history_df: pd.DataFrame) -> str:
    if history_df is None:
        history_df = pd.DataFrame()
    history_df = guard_dataframe_dtypes(history_df)
    try:
        text = history_df.to_csv(index=False)
    except Exception:
        text = ""
    return _github_write_text(
        BUY_ELITE_HISTORY_FILE,
        text,
        f"Update BUY ELITE learning history {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def _regime_key(regime_name: str) -> str:
    text = str(regime_name)
    if "XUÂN" in text:
        return "SPRING"
    if "TRUNG" in text:
        return "NEUTRAL"
    return "WINTER"


def get_learning_multipliers(profile: dict | None, regime_name: str = "") -> dict:
    """Lấy multiplier đã học. Nếu chưa đủ dữ liệu, mặc định = 1.0."""
    base = default_buy_elite_learning_profile()["multipliers"].copy()
    if not isinstance(profile, dict):
        return base

    for k, v in profile.get("multipliers", {}).items():
        base[k] = to_float(v, base.get(k, 1.0))

    regime_key = _regime_key(regime_name)
    regime_mult = profile.get("regime_multipliers", {}).get(regime_key, {})
    if isinstance(regime_mult, dict):
        for k, v in regime_mult.items():
            base[k] = base.get(k, 1.0) * to_float(v, 1.0)

    # Chốt chặn: không cho AI non trẻ làm lệch hệ thống quá mạnh.
    for k in list(base.keys()):
        base[k] = float(np.clip(to_float(base[k], 1.0), 0.70, 1.35))
    return base


def update_buy_elite_outcomes(history_df: pd.DataFrame, scan_df: pd.DataFrame) -> pd.DataFrame:
    """Cập nhật T+1/T+3/T+5 cho các tín hiệu cũ bằng giá hiện tại trong scan_df."""
    if history_df is None or history_df.empty or scan_df is None or scan_df.empty:
        return history_df if history_df is not None else pd.DataFrame()

    hist = history_df.copy()
    if "date" not in hist.columns or "symbol" not in hist.columns or "entry_price" not in hist.columns:
        return hist

    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date", "symbol"])
    if hist.empty:
        return hist

    today = pd.to_datetime(today_str())
    current_prices = scan_df.set_index("symbol")["price"].to_dict() if {"symbol", "price"}.issubset(scan_df.columns) else {}

    # Dùng số phiên app có dữ liệu trong history làm proxy cho trading days.
    date_strs = sorted(set(hist["date"].dt.strftime("%Y-%m-%d").tolist() + [today_str()]))
    date_pos = {d: i for i, d in enumerate(date_strs)}

    # Pandas mới không cho gán chuỗi thời gian vào cột float64.
    # Vì vậy tách rõ cột số và cột chữ trước khi cập nhật outcome.
    outcome_num_cols = ["t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win"]
    for col in outcome_num_cols:
        if col not in hist.columns:
            hist[col] = np.nan
        hist[col] = pd.to_numeric(hist[col], errors="coerce")

    if "last_outcome_update" not in hist.columns:
        hist["last_outcome_update"] = ""
    hist["last_outcome_update"] = hist["last_outcome_update"].astype("object")
    hist["last_outcome_update"] = hist["last_outcome_update"].where(pd.notna(hist["last_outcome_update"]), "")

    for idx, r in hist.iterrows():
        symbol = str(r.get("symbol", ""))
        entry = to_float(r.get("entry_price", np.nan))
        if symbol not in current_prices or not is_valid_price(entry):
            continue
        current_price = to_float(current_prices.get(symbol, np.nan))
        if not is_valid_price(current_price):
            continue

        signal_date = r["date"].strftime("%Y-%m-%d")
        gap = date_pos.get(today_str(), 0) - date_pos.get(signal_date, 0)
        if gap <= 0:
            continue

        ret = round((current_price / entry - 1) * 100, 2)
        for h in [1, 3, 5]:
            ret_col = f"t{h}_return"
            win_col = f"t{h}_win"
            if gap >= h and pd.isna(r.get(ret_col, np.nan)):
                hist.at[idx, ret_col] = ret
                hist.at[idx, win_col] = 1 if ret > 0 else 0
                hist.at[idx, "last_outcome_update"] = vn_time_str("%Y-%m-%d %H:%M:%S")

    hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
    return guard_dataframe_dtypes(hist)


def append_today_buy_elite_signals(history_df: pd.DataFrame, buy_elite_df: pd.DataFrame, market_real: float, market_forecast: float, allow_save: bool = True) -> pd.DataFrame:
    """Ghi tín hiệu BUY ELITE trong ngày để vài phiên sau có dữ liệu học."""
    if not allow_save or buy_elite_df is None or buy_elite_df.empty:
        return history_df if history_df is not None else pd.DataFrame()

    today = today_str()
    now_time = vn_time_str("%H:%M:%S")
    rows = []

    for _, r in buy_elite_df.head(30).iterrows():
        rows.append({
            "date": today,
            "time": now_time,
            "symbol": r.get("MÃ", ""),
            "entry_price": r.get("GIÁ", np.nan),
            "market_real": market_real,
            "market_forecast": market_forecast,
            "regime": r.get("REGIME", ""),
            "learning_mode": r.get("LearningMode", ""),
            "conclusion": r.get("KẾT LUẬN", ""),
            "winprob": r.get("WinProb", np.nan),
            "elite_score": r.get("EliteScore", np.nan),
            "consensus": r.get("ĐỒNG THUẬN", ""),
            "nav": r.get("NAV ELITE", ""),
            "group": r.get("NHÓM", ""),
            "storm": r.get("Storm", np.nan),
            "persistence": r.get("Persistence", np.nan),
            "dna": r.get("DNA", ""),
            "evolution": r.get("evolution", np.nan),
            "recent_change": r.get("recent_change", np.nan),
            "rsi": r.get("RSI", np.nan),
            "slope": r.get("SLOPE", np.nan),
            "dist_ema9": r.get("DIST EMA9%", np.nan),
            "obv": r.get("OBV", ""),
            "market_score": r.get("MarketScore", np.nan),
            "action_score": r.get("ActionScore", np.nan),
            "storm_score": r.get("StormScore", np.nan),
            "evo_score": r.get("EvoScore", np.nan),
            "zone_score": r.get("ZoneScore", np.nan),
            "penalty": r.get("Penalty", np.nan),
            "t1_return": np.nan,
            "t3_return": np.nan,
            "t5_return": np.nan,
            "t1_win": np.nan,
            "t3_win": np.nan,
            "t5_win": np.nan,
            "last_outcome_update": "",
        })

    new_df = guard_dataframe_dtypes(pd.DataFrame(rows))
    if new_df.empty:
        return history_df if history_df is not None else pd.DataFrame()

    history_df = guard_dataframe_dtypes(history_df) if history_df is not None else pd.DataFrame()
    if history_df.empty:
        hist = new_df
    else:
        hist = pd.concat([history_df, new_df], ignore_index=True)

    hist = guard_dataframe_dtypes(hist)
    hist = hist.drop_duplicates(subset=["date", "symbol"], keep="last")
    return hist


def _feature_multiplier(completed: pd.DataFrame, mask: pd.Series, baseline: float, min_n: int, kind: str = "good") -> tuple[float, str | None]:
    sub = completed[mask.fillna(False)].copy()
    n = len(sub)
    if n < min_n or baseline is None or pd.isna(baseline):
        return 1.0, None

    wr = to_float(sub["t5_win"].mean(), np.nan)
    if pd.isna(wr):
        return 1.0, None

    if kind == "good":
        adj = np.clip((wr - baseline) * 0.45, -0.12, 0.12)
        mult = 1.0 + adj
    else:
        # Với rủi ro: winrate càng thấp hơn baseline thì phạt càng mạnh.
        adj = np.clip((baseline - wr) * 0.65, -0.18, 0.25)
        mult = 1.0 + adj

    insight = f"{kind}: n={n}, winrate={round(wr*100,1)}%, baseline={round(baseline*100,1)}%, mult={round(mult,3)}"
    return round(float(np.clip(mult, 0.80, 1.25)), 3), insight


def build_buy_elite_learning_profile(history_df: pd.DataFrame, old_profile: dict | None = None) -> dict:
    """Sinh learning profile từ lịch sử đã hoàn tất T+5. Học chậm, thay đổi nhỏ."""
    old_profile = old_profile if isinstance(old_profile, dict) else default_buy_elite_learning_profile()
    profile = default_buy_elite_learning_profile()
    profile["created_at"] = old_profile.get("created_at", profile["created_at"])
    profile["updated_at"] = vn_time_str("%Y-%m-%d %H:%M:%S")

    if history_df is None or history_df.empty or "t5_win" not in history_df.columns:
        profile["note"] = "Chưa có lịch sử BUY ELITE. V3 đang WARMUP, chưa tự chỉnh trọng số."
        return profile

    hist = history_df.copy()
    hist["t5_win"] = pd.to_numeric(hist["t5_win"], errors="coerce")
    hist["t5_return"] = pd.to_numeric(hist.get("t5_return", np.nan), errors="coerce")
    completed = hist.dropna(subset=["t5_win", "t5_return"]).copy()
    completed_count = len(completed)
    profile["completed_t5"] = int(completed_count)

    min_completed = int(profile.get("min_completed_to_learn", 80))
    min_feature_samples = int(profile.get("min_feature_samples", 20))

    if completed_count == 0:
        profile["note"] = "Đã ghi tín hiệu nhưng chưa có mã nào đủ T+5 để học."
        return profile

    baseline = to_float(completed["t5_win"].mean(), np.nan)
    avg_ret = to_float(completed["t5_return"].mean(), np.nan)
    profile["baseline_winrate"] = round(float(baseline), 4) if pd.notna(baseline) else None
    profile["avg_t5_return"] = round(float(avg_ret), 3) if pd.notna(avg_ret) else None

    if completed_count < min_completed:
        profile["mode"] = "WARMUP"
        profile["note"] = f"Đã có {completed_count}/{min_completed} mẫu T+5. Chưa tự chỉnh trọng số, chỉ ghi nhớ và thống kê."
        profile["insights"] = [
            f"Completed T+5: {completed_count}/{min_completed}",
            f"Baseline WinRate: {round(baseline*100,1)}%" if pd.notna(baseline) else "Baseline WinRate: chưa đủ",
            f"Average T+5: {round(avg_ret,2)}%" if pd.notna(avg_ret) else "Average T+5: chưa đủ",
        ]
        return profile

    profile["mode"] = "ACTIVE_LEARNING"
    profile["note"] = "Đủ dữ liệu tối thiểu. Learning Engine đã bắt đầu tự chỉnh trọng số rất chậm."

    completed["storm_num"] = pd.to_numeric(completed.get("storm", np.nan), errors="coerce")
    completed["persistence_num"] = pd.to_numeric(completed.get("persistence", np.nan), errors="coerce")
    completed["evolution_num"] = pd.to_numeric(completed.get("evolution", np.nan), errors="coerce")
    completed["recent_change_num"] = pd.to_numeric(completed.get("recent_change", np.nan), errors="coerce")
    completed["rsi_num"] = pd.to_numeric(completed.get("rsi", np.nan), errors="coerce")
    completed["dist_num"] = pd.to_numeric(completed.get("dist_ema9", np.nan), errors="coerce")
    completed["market_real_num"] = pd.to_numeric(completed.get("market_real", np.nan), errors="coerce")
    completed["action_score_num"] = pd.to_numeric(completed.get("action_score", np.nan), errors="coerce")
    completed["zone_score_num"] = pd.to_numeric(completed.get("zone_score", np.nan), errors="coerce")

    obv_series = completed["obv"].astype(str) if "obv" in completed.columns else pd.Series("", index=completed.index)
    features = {
        "market": (completed["market_real_num"] >= 6, "good"),
        "action": (completed["action_score_num"] > 0, "good"),
        "storm": (completed["storm_num"].notna(), "good"),
        "evo": ((completed["persistence_num"] >= 3.5) | (completed["evolution_num"] > 0) | (completed["recent_change_num"] > 0), "good"),
        "zone": (completed["zone_score_num"] > 0, "good"),
        "obv": (obv_series.str.contains("🟢", na=False), "good"),
        "rsi_penalty": (completed["rsi_num"] > 72, "risk"),
        "dist_penalty": (completed["dist_num"] > 3.5, "risk"),
    }

    insights = [
        f"Completed T+5: {completed_count}",
        f"Baseline WinRate: {round(baseline*100,1)}%",
        f"Average T+5: {round(avg_ret,2)}%" if pd.notna(avg_ret) else "Average T+5: chưa đủ",
    ]

    new_mult = {}
    for name, (mask, kind) in features.items():
        mult, insight = _feature_multiplier(completed, mask, baseline, min_feature_samples, kind=kind)
        # Học chậm: trộn 80% trọng số cũ + 20% kết quả mới.
        old_mult = to_float(old_profile.get("multipliers", {}).get(name, 1.0), 1.0)
        blended = round(float(np.clip(old_mult * 0.80 + mult * 0.20, 0.85, 1.15)), 3)
        new_mult[name] = blended
        if insight:
            insights.append(f"{name}: {insight}, blended={blended}")

    profile["multipliers"].update(new_mult)

    # Học theo mùa thị trường nếu từng mùa đủ mẫu.
    regime_mults = {"WINTER": {}, "NEUTRAL": {}, "SPRING": {}}
    for regime_key in regime_mults.keys():
        if "regime" not in completed.columns:
            continue
        if regime_key == "WINTER":
            sub = completed[completed["regime"].astype(str).str.contains("ĐÔNG|WINTER", regex=True, na=False)]
        elif regime_key == "NEUTRAL":
            sub = completed[completed["regime"].astype(str).str.contains("TRUNG|NEUTRAL", regex=True, na=False)]
        else:
            sub = completed[completed["regime"].astype(str).str.contains("XUÂN|SPRING", regex=True, na=False)]
        if len(sub) < max(40, min_feature_samples):
            continue
        sub_baseline = to_float(sub["t5_win"].mean(), np.nan)
        # Nếu một mùa thắng thấp hơn baseline chung, hạ nhẹ action/storm; nếu tốt hơn thì tăng nhẹ.
        if pd.notna(sub_baseline) and pd.notna(baseline):
            seasonal = round(float(np.clip(1.0 + (sub_baseline - baseline) * 0.25, 0.90, 1.10)), 3)
            regime_mults[regime_key] = {"action": seasonal, "storm": seasonal, "zone": round(float(np.clip(2 - seasonal, 0.90, 1.10)), 3)}
            insights.append(f"Regime {regime_key}: n={len(sub)}, winrate={round(sub_baseline*100,1)}%, seasonal={seasonal}")

    profile["regime_multipliers"] = regime_mults
    profile["insights"] = insights[-20:]
    return profile


def run_buy_elite_learning_cycle(
    buy_elite_df: pd.DataFrame,
    scan_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    trading_today: bool,
) -> tuple[pd.DataFrame, dict, str, str]:
    """Một vòng học: đọc history → cập nhật outcome → học profile → ghi tín hiệu hôm nay."""
    history = read_buy_elite_history()
    old_profile = read_buy_elite_learning_profile()

    history = update_buy_elite_outcomes(history, scan_df)
    profile = build_buy_elite_learning_profile(history, old_profile=old_profile)
    profile_status = write_buy_elite_learning_profile(profile)

    history = append_today_buy_elite_signals(history, buy_elite_df, market_real, market_forecast, allow_save=trading_today)
    # Giữ 260 phiên gần nhất để file nhẹ.
    if history is not None and not history.empty and "date" in history.columns:
        tmp = history.copy()
        tmp["date_dt"] = pd.to_datetime(tmp["date"], errors="coerce")
        keep_dates = sorted(tmp["date_dt"].dropna().dt.strftime("%Y-%m-%d").unique())[-260:]
        tmp["date_str"] = tmp["date_dt"].dt.strftime("%Y-%m-%d")
        history = tmp[tmp["date_str"].isin(keep_dates)].drop(columns=["date_dt", "date_str"], errors="ignore")
    hist_status = write_buy_elite_history(history)
    return history, profile, hist_status, profile_status


def build_learning_summary(profile: dict, history_df: pd.DataFrame) -> dict:
    completed = int(profile.get("completed_t5", 0) or 0)
    min_required = int(profile.get("min_completed_to_learn", 80) or 80)
    mode = profile.get("mode", "WARMUP")
    baseline = profile.get("baseline_winrate", None)
    avg_ret = profile.get("avg_t5_return", None)
    if baseline is None:
        wr_text = "-"
    else:
        wr_text = f"{round(float(baseline)*100,1)}%"
    avg_text = "-" if avg_ret is None else f"{round(float(avg_ret),2)}%"
    total_signals = 0 if history_df is None or history_df.empty else len(history_df)
    return {
        "mode": mode,
        "completed": f"{completed}/{min_required}",
        "winrate": wr_text,
        "avg_t5": avg_text,
        "total_signals": total_signals,
        "note": profile.get("note", ""),
    }


# =========================================================
# BUY ELITE V3.1 / THINKING ENGINE - QUAN SÁT, PHÂN TÍCH, PHẢN BIỆN
# =========================================================
def default_buy_elite_thinking_profile() -> dict:
    return {
        "version": "BUY_ELITE_THINKING_V3_1",
        "mode": "WARMUP",
        "created_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "updated_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "completed_t5": 0,
        "baseline_winrate": None,
        "observation": {},
        "hypotheses": [],
        "beliefs": [],
        "reflections": [],
        "current_thought": "Chưa đủ dữ liệu để hình thành tư duy. Bot chỉ quan sát và ghi nhớ.",
        "note": "Thinking Engine đang WARMUP: ưu tiên quan sát, chưa kết luận mạnh.",
    }


def read_buy_elite_thinking_profile() -> dict:
    raw = _github_read_text(BUY_ELITE_THINKING_FILE)
    if raw is None:
        try:
            with open(BUY_ELITE_THINKING_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return default_buy_elite_thinking_profile()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else default_buy_elite_thinking_profile()
    except Exception:
        return default_buy_elite_thinking_profile()


def write_buy_elite_thinking_profile(profile: dict) -> str:
    try:
        text = json.dumps(profile, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(default_buy_elite_thinking_profile(), ensure_ascii=False, indent=2)
    return _github_write_text(
        BUY_ELITE_THINKING_FILE,
        text,
        f"Update BUY ELITE Thinking Profile {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def _thinking_strength(n: int, delta: float) -> tuple[str, str]:
    """Phân cấp độ tin cậy của một phát hiện.

    Không để Bot ảo tưởng: ít mẫu thì chỉ là quan sát/giả thuyết.
    """
    ad = abs(to_float(delta, 0))
    if n >= 1000 and ad >= 0.08:
        return "NIỀM TIN MẠNH", "🔵"
    if n >= 500 and ad >= 0.07:
        return "XU HƯỚNG ĐÁNG TIN", "🟢"
    if n >= 200 and ad >= 0.06:
        return "GIẢ THUYẾT MẠNH", "🟡"
    if n >= 80 and ad >= 0.05:
        return "GIẢ THUYẾT", "🟠"
    return "QUAN SÁT", "⚪"


def _condition_stats(df: pd.DataFrame, mask, label: str, baseline: float) -> dict | None:
    try:
        sub = df[mask].copy()
    except Exception:
        return None

    n = len(sub)
    if n == 0 or "t5_win" not in sub.columns:
        return None

    wr = to_float(sub["t5_win"].mean(), np.nan)
    avg = to_float(sub["t5_return"].mean(), np.nan) if "t5_return" in sub.columns else np.nan
    if pd.isna(wr) or pd.isna(baseline):
        return None

    delta = wr - baseline
    strength, icon = _thinking_strength(n, delta)
    return {
        "label": label,
        "n": int(n),
        "winrate": round(float(wr) * 100, 1),
        "avg_t5": round(float(avg), 2) if pd.notna(avg) else None,
        "delta_vs_base": round(float(delta) * 100, 1),
        "strength": strength,
        "icon": icon,
    }


def _build_thinking_observation(buy_elite_df: pd.DataFrame, market_real: float, market_forecast: float) -> dict:
    regime_name, _, regime_note = elite_regime(market_real, market_forecast)
    obs = {
        "date": today_str(),
        "time": vn_time_str("%H:%M:%S"),
        "market_real": to_float(market_real, 0),
        "market_forecast": to_float(market_forecast, 0),
        "regime": regime_name,
        "regime_note": regime_note,
        "signals_today": 0,
        "top_watch": "-",
        "avg_winprob": None,
        "avg_elite_score": None,
        "high_consensus_count": 0,
    }

    if buy_elite_df is None or buy_elite_df.empty:
        return obs

    df = buy_elite_df.copy()
    obs["signals_today"] = int(len(df))
    if "MÃ" in df.columns:
        obs["top_watch"] = ", ".join(df["MÃ"].astype(str).head(3).tolist())

    if "WinProb" in df.columns:
        wp = pd.to_numeric(df["WinProb"].astype(str).str.replace("%", "", regex=False), errors="coerce")
        obs["avg_winprob"] = round(float(wp.mean()), 1) if wp.notna().any() else None

    if "EliteScore" in df.columns:
        es = pd.to_numeric(df["EliteScore"], errors="coerce")
        obs["avg_elite_score"] = round(float(es.mean()), 1) if es.notna().any() else None

    if "ĐỒNG THUẬN" in df.columns:
        try:
            nums = df["ĐỒNG THUẬN"].astype(str).str.extract(r"(\d+)")[0].astype(float)
            obs["high_consensus_count"] = int((nums >= 5).sum())
        except Exception:
            obs["high_consensus_count"] = 0

    return obs


def build_buy_elite_thinking_profile(
    history_df: pd.DataFrame,
    learning_profile: dict,
    buy_elite_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    old_profile: dict | None = None,
) -> dict:
    """Thinking Engine V3.1: từ dữ liệu lịch sử tạo ra quan sát, giả thuyết, niềm tin và phản biện.

    Đây không phải LLM. Đây là một bộ tư duy thống kê có kỷ luật:
    - ít mẫu: chỉ quan sát
    - đủ mẫu: đặt giả thuyết
    - nhiều mẫu: hình thành niềm tin
    - luôn phản biện: kiểm tra điều kiện nào chỉ đúng trong một bối cảnh cụ thể
    """
    old_profile = old_profile if isinstance(old_profile, dict) else default_buy_elite_thinking_profile()
    profile = default_buy_elite_thinking_profile()
    profile["created_at"] = old_profile.get("created_at", profile["created_at"])
    profile["updated_at"] = vn_time_str("%Y-%m-%d %H:%M:%S")
    profile["observation"] = _build_thinking_observation(buy_elite_df, market_real, market_forecast)

    if history_df is None or history_df.empty:
        profile["note"] = "Chưa có lịch sử BUY ELITE. Thinking Engine chỉ quan sát phiên hiện tại."
        profile["current_thought"] = "Bot đang học cách nhìn thị trường. Chưa đủ ký ức để phân tích nguyên nhân."
        return profile

    hist = history_df.copy()
    for c in ["t5_win", "t5_return", "market_real", "storm", "persistence", "rsi", "dist_ema9", "evolution", "recent_change", "elite_score", "consensus_count", "action_score", "zone_score"]:
        if c in hist.columns:
            hist[c] = pd.to_numeric(hist[c], errors="coerce")

    completed = hist.dropna(subset=["t5_win", "t5_return"]).copy()
    completed_count = len(completed)
    profile["completed_t5"] = int(completed_count)

    if completed_count == 0:
        profile["note"] = "Đã có tín hiệu ghi nhận nhưng chưa có mẫu đủ T+5. Thinking Engine đang WARMUP."
        profile["current_thought"] = "Hiện tại Bot mới có mắt quan sát, chưa có trải nghiệm đủ dài để hình thành tư duy."
        return profile

    baseline = to_float(completed["t5_win"].mean(), np.nan)
    avg_ret = to_float(completed["t5_return"].mean(), np.nan)
    profile["baseline_winrate"] = round(float(baseline), 4) if pd.notna(baseline) else None
    profile["avg_t5_return"] = round(float(avg_ret), 3) if pd.notna(avg_ret) else None

    if completed_count < 80:
        profile["mode"] = "WARMUP"
        profile["note"] = f"Đã có {completed_count}/80 mẫu T+5. Bot chỉ quan sát, chưa kết luận."
        profile["current_thought"] = f"Ta mới có {completed_count} trải nghiệm T+5. Chưa đủ để phản biện hệ thống, nhưng đã bắt đầu ghi nhớ."
        return profile

    if completed_count < 200:
        profile["mode"] = "OBSERVING"
    elif completed_count < 500:
        profile["mode"] = "HYPOTHESIS"
    else:
        profile["mode"] = "THINKING"

    # Chuẩn hóa các trường chữ
    if "group" in completed.columns:
        group_s = completed["group"].astype(str)
    else:
        group_s = pd.Series("", index=completed.index)
    if "regime" in completed.columns:
        regime_s = completed["regime"].astype(str)
    else:
        regime_s = pd.Series("", index=completed.index)
    if "obv" in completed.columns:
        obv_s = completed["obv"].astype(str)
    else:
        obv_s = pd.Series("", index=completed.index)

    tests = []

    # Các giả thuyết tổng quát
    if "market_real" in completed.columns:
        tests.append(_condition_stats(completed, completed["market_real"] >= 6, "Market REAL >= 6", baseline))
        tests.append(_condition_stats(completed, completed["market_real"] < 6, "Market REAL < 6", baseline))
        tests.append(_condition_stats(completed, completed["market_real"] >= 8, "Market REAL >= 8", baseline))

    if "storm" in completed.columns:
        tests.append(_condition_stats(completed, completed["storm"].notna(), "Có Storm xác nhận", baseline))
        tests.append(_condition_stats(completed, completed["storm"].fillna(0) >= 15, "Storm >= 15", baseline))

    if "persistence" in completed.columns:
        tests.append(_condition_stats(completed, completed["persistence"] >= 3.5, "Persistence >= 3.5", baseline))
        tests.append(_condition_stats(completed, completed["persistence"] >= 5.0, "Persistence >= 5.0", baseline))

    if "consensus_count" in completed.columns:
        tests.append(_condition_stats(completed, completed["consensus_count"] >= 5, "Đồng thuận >= 5/6", baseline))
        tests.append(_condition_stats(completed, completed["consensus_count"] <= 2, "Đồng thuận <= 2/6", baseline))

    if "zone_score" in completed.columns:
        tests.append(_condition_stats(completed, completed["zone_score"] > 0, "Có vùng mua tốt", baseline))

    if "action_score" in completed.columns:
        tests.append(_condition_stats(completed, completed["action_score"] > 0, "Xanh/Đỏ xác nhận hành động", baseline))

    if "rsi" in completed.columns:
        tests.append(_condition_stats(completed, completed["rsi"].between(55, 65), "RSI 55-65", baseline))
        tests.append(_condition_stats(completed, completed["rsi"] > 72, "RSI > 72", baseline))

    if "dist_ema9" in completed.columns:
        tests.append(_condition_stats(completed, completed["dist_ema9"].abs() <= 2, "Gần EMA9 ±2%", baseline))
        tests.append(_condition_stats(completed, completed["dist_ema9"] > 4, "Xa EMA9 >4%", baseline))

    tests.append(_condition_stats(completed, group_s.isin(["PULL ĐẸP", "PULL VỪA"]), "Nhóm Pull", baseline))
    tests.append(_condition_stats(completed, group_s.eq("MUA EARLY"), "Nhóm Early", baseline))
    tests.append(_condition_stats(completed, group_s.eq("MUA BREAK"), "Nhóm Break", baseline))
    tests.append(_condition_stats(completed, obv_s.str.contains("🟢", na=False), "OBV xanh", baseline))

    # Tư duy theo bối cảnh thị trường: cùng điều kiện nhưng regime khác nhau
    if "storm" in completed.columns:
        tests.append(_condition_stats(completed, completed["storm"].notna() & regime_s.str.contains("MÙA ĐÔNG", na=False), "Storm trong Mùa Đông", baseline))
        tests.append(_condition_stats(completed, completed["storm"].notna() & regime_s.str.contains("MÙA XUÂN", na=False), "Storm trong Mùa Xuân", baseline))
    tests.append(_condition_stats(completed, group_s.isin(["PULL ĐẸP", "PULL VỪA"]) & regime_s.str.contains("MÙA ĐÔNG", na=False), "Pull trong Mùa Đông", baseline))
    tests.append(_condition_stats(completed, group_s.eq("MUA BREAK") & regime_s.str.contains("MÙA XUÂN", na=False), "Break trong Mùa Xuân", baseline))

    tests = [t for t in tests if t is not None]

    # Sắp xếp theo độ lệch so với baseline và số mẫu
    tests_sorted = sorted(
        tests,
        key=lambda x: (abs(to_float(x.get("delta_vs_base", 0), 0)), x.get("n", 0)),
        reverse=True,
    )

    hypotheses = []
    beliefs = []
    observations = []

    for t in tests_sorted:
        line = (
            f"{t['icon']} {t['label']}: n={t['n']}, "
            f"WinRate={t['winrate']}%, AvgT+5={t.get('avg_t5', '-')}, "
            f"lệch baseline {t['delta_vs_base']}% → {t['strength']}"
        )
        if t["strength"] in ["NIỀM TIN MẠNH", "XU HƯỚNG ĐÁNG TIN"]:
            beliefs.append(line)
        elif t["strength"] in ["GIẢ THUYẾT MẠNH", "GIẢ THUYẾT"]:
            hypotheses.append(line)
        else:
            observations.append(line)

    # Phản biện: tìm trường hợp một niềm tin chỉ đúng theo bối cảnh
    reflections = []
    def add_reflection(condition_a: str, label_a: str, condition_b: str, label_b: str):
        found_a = next((x for x in tests if x["label"] == condition_a), None)
        found_b = next((x for x in tests if x["label"] == condition_b), None)
        if found_a and found_b and found_a["n"] >= 20 and found_b["n"] >= 20:
            diff = to_float(found_a["winrate"], 0) - to_float(found_b["winrate"], 0)
            if abs(diff) >= 12:
                better = label_a if diff > 0 else label_b
                worse = label_b if diff > 0 else label_a
                reflections.append(
                    f"🪞 Phản biện: cùng một yếu tố nhưng {better} tốt hơn {worse} khoảng {round(abs(diff),1)} điểm %. Không nên kết luận một chiều."
                )

    add_reflection("Storm trong Mùa Xuân", "Storm trong Mùa Xuân", "Storm trong Mùa Đông", "Storm trong Mùa Đông")
    add_reflection("Break trong Mùa Xuân", "Break trong Mùa Xuân", "Nhóm Break", "Break tổng thể")
    add_reflection("Pull trong Mùa Đông", "Pull trong Mùa Đông", "Nhóm Pull", "Pull tổng thể")

    # Nếu chưa có phản biện đủ mạnh, vẫn ghi nhắc nhở phương pháp
    if not reflections:
        reflections.append("🪞 Chưa có đủ mẫu để phản biện một niềm tin cụ thể. Bot giữ thái độ: mọi kết luận chỉ đúng cho đến khi dữ liệu mới chứng minh điều ngược lại.")

    profile["hypotheses"] = hypotheses[:12]
    profile["beliefs"] = beliefs[:12]
    profile["observations"] = observations[:12]
    profile["reflections"] = reflections[:8]

    if beliefs:
        profile["current_thought"] = beliefs[0]
    elif hypotheses:
        profile["current_thought"] = hypotheses[0]
    elif observations:
        profile["current_thought"] = observations[0]
    else:
        profile["current_thought"] = "Có dữ liệu T+5 nhưng chưa có mẫu hình nào đủ nổi bật so với baseline."

    profile["note"] = (
        f"Thinking Engine V3.1 đang ở chế độ {profile['mode']}. "
        f"Baseline WinRate T+5 = {round(baseline*100,1)}%, Avg T+5 = {round(avg_ret,2)}%. "
        "Bot phân biệt rõ Quan sát / Giả thuyết / Niềm tin và luôn tự phản biện."
    )
    return profile


def append_thinking_journal(thinking_profile: dict) -> str:
    """Ghi một dòng nhật ký tư duy mỗi ngày. Không ghi trùng ngày."""
    try:
        row = {
            "date": today_str(),
            "time": vn_time_str("%H:%M:%S"),
            "mode": thinking_profile.get("mode", ""),
            "completed_t5": thinking_profile.get("completed_t5", 0),
            "baseline_winrate": thinking_profile.get("baseline_winrate", None),
            "current_thought": thinking_profile.get("current_thought", ""),
            "note": thinking_profile.get("note", ""),
        }
        new = guard_dataframe_dtypes(pd.DataFrame([row]), text_cols=["date", "time", "mode", "current_thought", "note"], numeric_cols=["completed_t5", "baseline_winrate"])
        old = pd.DataFrame()
        raw = _github_read_text(BUY_ELITE_THINKING_JOURNAL_FILE)
        if raw is not None:
            from io import StringIO
            old = guard_dataframe_dtypes(pd.read_csv(StringIO(raw)))
        elif os.path.exists(BUY_ELITE_THINKING_JOURNAL_FILE):
            old = guard_dataframe_dtypes(pd.read_csv(BUY_ELITE_THINKING_JOURNAL_FILE))

        if old.empty:
            out = new
        else:
            out = pd.concat([old, new], ignore_index=True)
            out = out.drop_duplicates(subset=["date"], keep="last").tail(500)

        out = guard_dataframe_dtypes(out)
        csv_text = out.to_csv(index=False)
        return _github_write_text(
            BUY_ELITE_THINKING_JOURNAL_FILE,
            csv_text,
            f"Update BUY ELITE Thinking Journal {vn_time_str('%Y-%m-%d %H:%M:%S')}",
        )
    except Exception:
        return "THINKING_JOURNAL_ERROR"


def build_thinking_summary(profile: dict) -> dict:
    obs = profile.get("observation", {}) if isinstance(profile, dict) else {}
    return {
        "mode": profile.get("mode", "WARMUP") if isinstance(profile, dict) else "WARMUP",
        "completed": profile.get("completed_t5", 0) if isinstance(profile, dict) else 0,
        "beliefs": len(profile.get("beliefs", [])) if isinstance(profile, dict) else 0,
        "hypotheses": len(profile.get("hypotheses", [])) if isinstance(profile, dict) else 0,
        "reflections": len(profile.get("reflections", [])) if isinstance(profile, dict) else 0,
        "current_thought": profile.get("current_thought", "") if isinstance(profile, dict) else "",
        "top_watch": obs.get("top_watch", "-"),
        "signals_today": obs.get("signals_today", 0),
        "note": profile.get("note", "") if isinstance(profile, dict) else "",
    }


# =========================================================
# Mr.BOT PRO V4.0 / BOT EVOLUTION - NHÂN CÁCH, TRÍ NHỚ, BẢN NĂNG
# =========================================================
def default_mr_bot_pro_profile() -> dict:
    return {
        "version": "MR_BOT_PRO_V4.0",
        "name": "Mr.BOT PRO",
        "slogan": "Observe • Learn • Think • Evolve",
        "created_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "updated_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "age_days": 0,
        "bot_version_number": 4.0,
        "status": "WARMUP",
        "personality": "PHÒNG THỦ",
        "confidence": 0,
        "experience": {
            "observations": 0,
            "signals": 0,
            "completed_t5": 0,
            "hypotheses": 0,
            "beliefs": 0,
            "reflections": 0,
            "discarded_beliefs": 0,
        },
        "constitution": [
            "Không cố đoán tương lai.",
            "Market First: Market cấm thì không giải ngân thật.",
            "Không chắc thì đứng ngoài.",
            "Luôn ghi nhớ kết quả thực chiến.",
            "Sẵn sàng thừa nhận sai khi dữ liệu chứng minh điều ngược lại.",
            "Học chậm, đổi chậm, tránh ảo tưởng AI.",
        ],
        "current_message": "Tôi mới sinh ra. Tôi sẽ quan sát trước, học sau, rồi mới tư duy.",
        "proposals": [],
        "self_questions": [],
        "evolution_log": [],
    }


def read_mr_bot_pro_profile() -> dict:
    text = _github_read_text(MR_BOT_PRO_PROFILE_FILE)
    if text is None:
        try:
            with open(MR_BOT_PRO_PROFILE_FILE, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            return default_mr_bot_pro_profile()
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return default_mr_bot_pro_profile()
        base = default_mr_bot_pro_profile()
        base.update(obj)
        return base
    except Exception:
        return default_mr_bot_pro_profile()


def write_mr_bot_pro_profile(profile: dict) -> str:
    try:
        text = json.dumps(profile, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(default_mr_bot_pro_profile(), ensure_ascii=False, indent=2)
    return _github_write_text(
        MR_BOT_PRO_PROFILE_FILE,
        text,
        f"Update Mr.BOT PRO profile {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def _safe_date_age_days(created_at: str) -> int:
    try:
        dt = pd.to_datetime(created_at, errors="coerce")
        if pd.isna(dt):
            return 0
        return max((pd.to_datetime(today_str()) - pd.to_datetime(dt.strftime("%Y-%m-%d"))).days, 0)
    except Exception:
        return 0


def _mr_bot_personality(market_real: float, market_forecast: float, completed_t5: int) -> str:
    if completed_t5 < 80:
        return "HỌC VIỆC THẬN TRỌNG"
    if market_real < 6:
        return "PHÒNG THỦ"
    if market_real < 8:
        return "CÂN BẰNG"
    if market_forecast >= 6:
        return "TẤN CÔNG CÓ KỶ LUẬT"
    return "CÂN BẰNG"


def _mr_bot_status(completed_t5: int, confidence: float) -> str:
    if completed_t5 < 80:
        return "WARMUP"
    if completed_t5 < 300:
        return "LEARNING"
    if confidence < 70:
        return "THINKING"
    if completed_t5 < 1000:
        return "EVOLVING"
    return "MATURE"


def _mr_bot_confidence(winrate_t5, avg_t5, completed_t5: int, reflections: int) -> float:
    if completed_t5 <= 0:
        return 0.0
    wr = to_float(winrate_t5, np.nan)
    avg = to_float(avg_t5, 0)
    if pd.isna(wr):
        wr = 50.0
    # Confidence không phải xác suất thắng; là độ trưởng thành của hệ thống.
    sample_score = min(completed_t5 / 300, 1) * 45
    win_score = np.clip((wr - 45) * 1.2, 0, 35)
    avg_score = np.clip(avg * 2.0, 0, 10)
    reflection_score = min(reflections, 10)
    return round(float(np.clip(sample_score + win_score + avg_score + reflection_score, 0, 100)), 1)


def build_mr_bot_pro_profile(
    old_profile: dict,
    learning_profile: dict,
    thinking_profile: dict,
    history_df: pd.DataFrame,
    buy_elite_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> dict:
    profile = old_profile if isinstance(old_profile, dict) else default_mr_bot_pro_profile()
    created_at = profile.get("created_at") or vn_time_str("%Y-%m-%d %H:%M:%S")

    completed_t5 = int(to_float(learning_profile.get("completed_t5", 0) if isinstance(learning_profile, dict) else 0, 0))
    signals = len(history_df) if isinstance(history_df, pd.DataFrame) else 0
    hypotheses = len(thinking_profile.get("hypotheses", [])) if isinstance(thinking_profile, dict) else 0
    beliefs = len(thinking_profile.get("beliefs", [])) if isinstance(thinking_profile, dict) else 0
    reflections = len(thinking_profile.get("reflections", [])) if isinstance(thinking_profile, dict) else 0

    completed = pd.DataFrame()
    if isinstance(history_df, pd.DataFrame) and not history_df.empty and "t5_return" in history_df.columns:
        completed = history_df[pd.notna(pd.to_numeric(history_df["t5_return"], errors="coerce"))].copy()

    winrate_t5 = np.nan
    avg_t5 = np.nan
    if not completed.empty:
        completed["t5_return"] = pd.to_numeric(completed["t5_return"], errors="coerce")
        winrate_t5 = round((completed["t5_return"] > 0).mean() * 100, 1)
        avg_t5 = round(completed["t5_return"].mean(), 2)

    confidence = _mr_bot_confidence(winrate_t5, avg_t5, completed_t5, reflections)
    personality = _mr_bot_personality(market_real, market_forecast, completed_t5)
    status = _mr_bot_status(completed_t5, confidence)
    age_days = _safe_date_age_days(created_at)
    bot_version_number = round(4.0 + min(completed_t5 / 1000, 0.99) + min(reflections / 1000, 0.10), 3)

    top_watch = "-"
    if isinstance(buy_elite_df, pd.DataFrame) and not buy_elite_df.empty and "MÃ" in buy_elite_df.columns:
        top_watch = ", ".join(buy_elite_df.head(3)["MÃ"].astype(str).tolist())

    if market_real < 6:
        current_message = f"Market REAL {market_real} < 6. Tôi chỉ lập watchlist ({top_watch}), không đề xuất giải ngân thật. Kỷ luật quan trọng hơn cơ hội."
    elif completed_t5 < 80:
        current_message = f"Tôi đang WARMUP: đã ghi {signals} tín hiệu, nhưng mới có {completed_t5}/80 mẫu T+5. Tôi quan sát trước khi tự điều chỉnh."
    elif status in ["LEARNING", "THINKING"]:
        current_message = f"Tôi đã đủ dữ liệu tối thiểu để học chậm. Hiện tôi ưu tiên kiểm chứng giả thuyết hơn là thay đổi mạnh trọng số."
    else:
        current_message = f"Tôi đang tiến hóa thận trọng. Mỗi thay đổi phải được dữ liệu T+5 xác nhận, không thay đổi vì cảm xúc một vài phiên."

    proposals = []
    if completed_t5 < 80:
        proposals.append("Chưa đề xuất đổi trọng số: cần đủ tối thiểu 80 mẫu T+5.")
    else:
        if market_real < 6:
            proposals.append("Duy trì quyền phủ quyết của Market khi Market REAL < 6.")
        if beliefs:
            proposals.append("Theo dõi các niềm tin đã hình thành, chỉ nâng cấp khi được lặp lại qua nhiều mẫu.")
        if reflections:
            proposals.append("Ưu tiên các giả thuyết đã qua phản biện; giảm vai trò giả thuyết bị dữ liệu bác bỏ.")

    self_questions = [
        "Hôm nay tôi sai ở đâu nếu BUY ELITE không hiệu quả?",
        "Điều kiện nào khiến tín hiệu thắng chỉ là may mắn?",
        "Yếu tố nào còn giá trị khi Market đổi mùa?",
        "Niềm tin nào cần bị kiểm tra lại?",
    ]

    new_log = {
        "time": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "personality": personality,
        "confidence": confidence,
        "completed_t5": completed_t5,
        "market_real": market_real,
        "message": current_message,
    }

    old_log = profile.get("evolution_log", []) if isinstance(profile.get("evolution_log", []), list) else []
    old_log.append(new_log)
    old_log = old_log[-80:]

    profile.update({
        "version": "MR_BOT_PRO_V4.0",
        "name": "Mr.BOT PRO",
        "slogan": "Observe • Learn • Think • Evolve",
        "created_at": created_at,
        "updated_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "age_days": age_days,
        "bot_version_number": bot_version_number,
        "status": status,
        "personality": personality,
        "confidence": confidence,
        "current_message": current_message,
        "experience": {
            "observations": signals + len(read_evolution_history()) if isinstance(read_evolution_history(), pd.DataFrame) else signals,
            "signals": signals,
            "completed_t5": completed_t5,
            "hypotheses": hypotheses,
            "beliefs": beliefs,
            "reflections": reflections,
            "discarded_beliefs": max(reflections - beliefs, 0),
        },
        "proposals": proposals,
        "self_questions": self_questions,
        "evolution_log": old_log,
    })

    profile.setdefault("constitution", default_mr_bot_pro_profile()["constitution"])
    return profile


def write_mr_bot_pro_journal(profile: dict) -> str:
    try:
        row = pd.DataFrame([{
            "time": vn_time_str("%Y-%m-%d %H:%M:%S"),
            "date": today_str(),
            "name": profile.get("name", "Mr.BOT PRO"),
            "version": profile.get("bot_version_number", 4.0),
            "status": profile.get("status", "WARMUP"),
            "personality": profile.get("personality", ""),
            "confidence": profile.get("confidence", 0),
            "age_days": profile.get("age_days", 0),
            "message": profile.get("current_message", ""),
        }])
        old = pd.DataFrame()
        text = _github_read_text(MR_BOT_PRO_JOURNAL_FILE)
        if text is not None:
            from io import StringIO
            old = guard_dataframe_dtypes(pd.read_csv(StringIO(text)))
        elif os.path.exists(MR_BOT_PRO_JOURNAL_FILE):
            old = guard_dataframe_dtypes(pd.read_csv(MR_BOT_PRO_JOURNAL_FILE))
        row = guard_dataframe_dtypes(row)
        out = guard_dataframe_dtypes(pd.concat([old, row], ignore_index=True)).drop_duplicates(subset=["date"], keep="last").tail(500)
        return _github_write_text(
            MR_BOT_PRO_JOURNAL_FILE,
            out.to_csv(index=False),
            f"Update Mr.BOT PRO journal {vn_time_str('%Y-%m-%d %H:%M:%S')}",
        )
    except Exception:
        return "MR_BOT_JOURNAL_ERROR"


def build_mr_bot_pro_summary(profile: dict) -> dict:
    exp = profile.get("experience", {}) if isinstance(profile, dict) else {}
    return {
        "name": profile.get("name", "Mr.BOT PRO"),
        "version": profile.get("bot_version_number", 4.0),
        "status": profile.get("status", "WARMUP"),
        "personality": profile.get("personality", ""),
        "confidence": profile.get("confidence", 0),
        "age": profile.get("age_days", 0),
        "signals": exp.get("signals", 0),
        "completed_t5": exp.get("completed_t5", 0),
        "beliefs": exp.get("beliefs", 0),
        "hypotheses": exp.get("hypotheses", 0),
        "reflections": exp.get("reflections", 0),
        "message": profile.get("current_message", ""),
        "proposals": profile.get("proposals", []),
        "self_questions": profile.get("self_questions", []),
    }


# BUY ELITE V3 / DECISION ENGINE - BẢNG RA QUYẾT ĐỊNH MUA
# =========================================================
def elite_market_score(market_real: float, market_forecast: float) -> tuple[float, str]:
    """Market là cổng chặn đầu tiên, không phải chỉ là điểm cộng."""
    try:
        mr = float(market_real)
    except Exception:
        mr = 0.0

    try:
        mf = float(market_forecast)
    except Exception:
        mf = 0.0

    if mr >= 8 and mf >= 6:
        return 20, "Market ủng hộ mạnh"
    if mr >= 8:
        return 17, "Market REAL khỏe"
    if mr >= 6 and mf >= 4:
        return 12, "Market đủ test nhỏ"
    if mr >= 6:
        return 9, "Market trung tính, chỉ mua nhỏ"
    return 0, "Market yếu - chỉ theo dõi"


def elite_regime(market_real: float, market_forecast: float) -> tuple[str, dict, str]:
    """V2: trọng số thay đổi theo trạng thái thị trường.

    - Market yếu: không giải ngân thật, ưu tiên Watchlist và vùng mua.
    - Market trung tính: ưu tiên Pull/Early, giảm đuổi momentum.
    - Market khỏe: tăng trọng số Storm + Action.
    """
    mr = to_float(market_real, 0)
    mf = to_float(market_forecast, 0)

    if mr >= 8 and mf >= 5:
        return "🟢 MÙA XUÂN", {
            "market": 1.00,
            "action": 1.15,
            "storm": 1.15,
            "evo": 1.00,
            "zone": 0.95,
            "obv": 1.00,
        }, "Market khỏe: cho phép ưu tiên mã có động lượng + đồng thuận cao."

    if mr >= 6:
        return "🟡 TRUNG TÍNH", {
            "market": 1.00,
            "action": 1.00,
            "storm": 0.90,
            "evo": 1.05,
            "zone": 1.15,
            "obv": 1.10,
        }, "Market trung tính: ưu tiên Pull/Early, mua nhỏ, stop gần."

    return "🔴 MÙA ĐÔNG", {
        "market": 1.00,
        "action": 0.85,
        "storm": 0.70,
        "evo": 0.90,
        "zone": 1.25,
        "obv": 1.15,
    }, "Market yếu: chỉ lập watchlist, chưa giải ngân thật."


def elite_star(prob: float) -> str:
    p = to_float(prob, 0)
    if p >= 85:
        return "⭐⭐⭐⭐⭐"
    if p >= 75:
        return "⭐⭐⭐⭐"
    if p >= 65:
        return "⭐⭐⭐"
    if p >= 55:
        return "⭐⭐"
    return "⭐"


def elite_confidence(prob: float) -> str:
    p = to_float(prob, 0)
    if p >= 85:
        return "RẤT CAO"
    if p >= 75:
        return "CAO"
    if p >= 65:
        return "KHÁ"
    if p >= 55:
        return "VỪA"
    return "THẤP"


def elite_nav_v2(conclusion: str, win_prob: float, market_real: float) -> str:
    mr = to_float(market_real, 0)
    p = to_float(win_prob, 0)
    if mr < 6:
        return "0%"
    if "BUY ELITE" in str(conclusion):
        if mr >= 8 and p >= 85:
            return "15-20% NAV"
        if mr >= 8:
            return "10-15% NAV"
        return "5-10% NAV"
    if "MUA NHỎ" in str(conclusion):
        return "3-7% NAV"
    return "0%"


def build_buy_elite_decision_engine(
    scan_df: pd.DataFrame,
    green_red_df: pd.DataFrame,
    storm_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    pullback_df: pd.DataFrame,
    early_buy_lab_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    learning_profile: dict | None = None,
    pattern_match_df: pd.DataFrame | None = None,
    leader_memory_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    BUY ELITE V3 = Decision Engine có xác suất ước lượng, đồng thuận, trọng số theo mùa và Learning Engine.

    V2 khác V1 ở 5 điểm:
    1) Có WinProb: xác suất thắng ước lượng từ điểm đồng thuận, chưa phải xác suất thống kê thật.
    2) Có sao/độ tin cậy để nhìn nhanh trên điện thoại.
    3) Trọng số thay đổi theo Market regime.
    4) Rule Engine vẫn chặn Market yếu / OBV gãy / thủng EMA9.
    5) Lý do tách thành đồng thuận ✅ và rủi ro ❌ để đọc nhanh.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    needed = [
        "symbol",
        "group",
        "price",
        "ema9",
        "total_score",
        "rsi14",
        "rsi_slope",
        "ema9_ma20_slope",
        "dist_from_ema9_pct",
        "obv_status",
        "warning",
        "green_2_confirm",
        "early_dry_green2",
        "volume",
        "vol_ma20",
        "is_live_adjusted",
        # ===== Learning Engine =====
        "evolution_health_group",
        "health_group",
        "rs10",
        "rs_spread",
        "volume_ratio20",
    ]

    base = scan_df[[c for c in needed if c in scan_df.columns]].copy()
    if base.empty or "symbol" not in base.columns:
        return pd.DataFrame()
    # -----------------------------------------------------
    # LEADER MEMORY -> BUY ELITE
    # Ghép kinh nghiệm Leader Brain theo từng mã.
    # Chưa tác động EliteScore ở bước này.
    # -----------------------------------------------------
    if (
        leader_memory_df is not None
        and not leader_memory_df.empty
        and "symbol" in leader_memory_df.columns
    ):
        leader_cols = [
            "symbol",
            "leader_score",
            "confidence_score",
            "persistence_20_pct",
            "winrate_t5_pct",
            "avg_return_t5_pct",
            "performance_score",
            "market_fit_score",
            "recommendation",
        ]
        leader_cols = [
            c for c in leader_cols
            if c in leader_memory_df.columns
        ]

        leader_bridge = leader_memory_df[leader_cols].copy()

        leader_bridge = leader_bridge.rename(columns={
            "leader_score": "LeaderMemoryScore",
            "confidence_score": "LeaderMemoryConfidence",
            "persistence_20_pct": "LeaderMemoryPersistence",
            "winrate_t5_pct": "LeaderMemoryWinRateT5",
            "avg_return_t5_pct": "LeaderMemoryReturnT5",
            "performance_score": "LeaderMemoryPerformance",
            "market_fit_score": "LeaderMemoryMarketFit",
            "recommendation": "LeaderMemoryRecommendation",
        })

        base = base.merge(
            leader_bridge,
            on="symbol",
            how="left",
        )
        # -----------------------------------------------------
    # LEADER MEMORY ADJUSTMENT
    # Chỉ tạo tín hiệu kinh nghiệm; chưa cộng vào EliteScore.
    # Giới hạn +/-5 điểm để Leader Memory không lấn át tín hiệu hiện tại.
    # -----------------------------------------------------
    base["LeaderMemoryAdjustment"] = 0.0

    if "LeaderMemoryScore" in base.columns:
        lm_score = pd.to_numeric(
            base["LeaderMemoryScore"], errors="coerce"
        ).fillna(50.0)

        lm_conf = pd.to_numeric(
            base.get(
                "LeaderMemoryConfidence",
                pd.Series(0.0, index=base.index)
            ),
            errors="coerce",
        ).fillna(0.0)

        lm_perf = pd.to_numeric(
            base.get(
                "LeaderMemoryPerformance",
                pd.Series(50.0, index=base.index)
            ),
            errors="coerce",
        ).fillna(50.0)

        lm_market = pd.to_numeric(
            base.get(
                "LeaderMemoryMarketFit",
                pd.Series(50.0, index=base.index)
            ),
            errors="coerce",
        ).fillna(50.0)

        confidence_factor = (lm_conf / 60.0).clip(0.0, 1.0)

        raw_memory_adj = (
            (lm_score - 60.0) * 0.15
            + (lm_perf - 50.0) * 0.05
            + (lm_market - 50.0) * 0.05
        )

        base["LeaderMemoryAdjustment"] = (
            raw_memory_adj * confidence_factor
        ).clip(-5.0, 5.0)
    # -----------------------------------------------------
    # 1) GHÉP XANH MUA - ĐỎ BÁN: bảng hành động trung tâm
    # -----------------------------------------------------
    if green_red_df is not None and not green_red_df.empty and "MÃ" in green_red_df.columns:
        gr_cols = [
            "MÃ", "TÍN HIỆU", "TREND_SCORE", "BUY_SCORE", "VÙNG MUA", "NAV", "LÝ DO"
        ]
        gr_cols = [c for c in gr_cols if c in green_red_df.columns]
        gr = green_red_df[gr_cols].copy().rename(columns={
            "MÃ": "symbol",
            "TÍN HIỆU": "GR_SIGNAL",
            "TREND_SCORE": "GR_TREND_SCORE",
            "BUY_SCORE": "GR_BUY_SCORE",
            "VÙNG MUA": "GR_VÙNG MUA",
            "NAV": "GR_NAV",
            "LÝ DO": "GR_LÝ DO",
        })
        base = base.merge(gr, on="symbol", how="left")
    else:
        base["GR_SIGNAL"] = ""
        base["GR_TREND_SCORE"] = np.nan
        base["GR_BUY_SCORE"] = np.nan
        base["GR_VÙNG MUA"] = ""
        base["GR_NAV"] = ""
        base["GR_LÝ DO"] = ""

    # -----------------------------------------------------
    # 2) GHÉP STORM: tiền vào / động lượng
    # -----------------------------------------------------
    if storm_df is not None and not storm_df.empty and "MÃ" in storm_df.columns:
        st_cols = ["MÃ", "STORM", "GREEN2", "VOL/MA20", "DNA ACCEL", "OBV ACCEL", "VOL SURGE"]
        st_cols = [c for c in st_cols if c in storm_df.columns]
        st_part = storm_df[st_cols].copy().rename(columns={
            "MÃ": "symbol",
            "STORM": "Storm",
            "GREEN2": "Storm_GREEN2",
            "VOL/MA20": "Storm_VOL_MA20",
            "DNA ACCEL": "Storm_DNA_ACCEL",
            "OBV ACCEL": "Storm_OBV_ACCEL",
            "VOL SURGE": "Storm_VOL_SURGE",
        })
        base = base.merge(st_part, on="symbol", how="left")
    else:
        base["Storm"] = np.nan
        base["Storm_GREEN2"] = ""
        base["Storm_VOL_MA20"] = np.nan
        base["Storm_DNA_ACCEL"] = np.nan
        base["Storm_OBV_ACCEL"] = np.nan
        base["Storm_VOL_SURGE"] = np.nan

    # -----------------------------------------------------
    # 3) GHÉP EVOLUTION / DNA: tiến hóa và độ bền
    # -----------------------------------------------------
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = [
            "symbol", "Persistence", "DNA", "evolution", "recent_change", "EvoQuality", "Smooth", "EvoFinal"
        ]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        base = base.merge(evo_table[evo_cols].copy(), on="symbol", how="left")
    else:
        base["Persistence"] = 0
        base["DNA"] = "⚪ MỚI"
        base["evolution"] = 0
        base["recent_change"] = 0
        base["EvoQuality"] = 0
        base["Smooth"] = 0
        base["EvoFinal"] = 0

    # -----------------------------------------------------
    # 4) GHÉP PULLBACK / EARLY: đúng vùng mua hay chưa
    # -----------------------------------------------------
    pull_symbols = set()
    if pullback_df is not None and not pullback_df.empty and "MÃ" in pullback_df.columns:
        pull_symbols = set(pullback_df["MÃ"].astype(str))

    early_symbols = set()
    if early_buy_lab_df is not None and not early_buy_lab_df.empty and "MÃ" in early_buy_lab_df.columns:
        early_symbols = set(early_buy_lab_df["MÃ"].astype(str))

    base["InPullback"] = base["symbol"].astype(str).isin(pull_symbols)
    base["InEarlyLab"] = base["symbol"].astype(str).isin(early_symbols)

    # -----------------------------------------------------
    # 4B) GHÉP PATTERN MATCH: Pattern chỉ cộng điểm, chưa tham gia Consensus
    # -----------------------------------------------------
    if (
        pattern_match_df is not None
        and not pattern_match_df.empty
        and {"symbol", "pattern_match"}.issubset(pattern_match_df.columns)
    ):
        pm = pattern_match_df[["symbol", "pattern_match"]].copy()
        pm["symbol"] = pm["symbol"].astype(str)
        pm["pattern_match"] = pd.to_numeric(pm["pattern_match"], errors="coerce").fillna(0)
        pm = pm.drop_duplicates(subset=["symbol"], keep="first")
        base = base.merge(pm, on="symbol", how="left")
    else:
        base["pattern_match"] = 0.0

    base["pattern_match"] = pd.to_numeric(base["pattern_match"], errors="coerce").fillna(0).clip(0, 100)

    # Chỉ Pattern Match >= 70 mới được cộng điểm.
    # 70 = 0 điểm; 90 trở lên = tối đa 8 điểm.
    # Mục tiêu: Pattern có tiếng nói nhưng chưa được lấn át Rule/Market/Action.
    base["PatternScore"] = np.where(
        base["pattern_match"] >= 70,
        ((base["pattern_match"] - 70) / 20.0 * 8.0).clip(0, 8),
        0.0,
    ).round(2)

    # -----------------------------------------------------
    # 5) TÍNH ĐIỂM THEO CÁC CHUYÊN GIA + TRỌNG SỐ THEO MÙA
    # -----------------------------------------------------
    regime_name, weights, regime_note = elite_regime(market_real, market_forecast)

    # V3: áp dụng trọng số tự học rất chậm từ lịch sử BUY ELITE.
    # Nếu dữ liệu chưa đủ, learning_profile trả về multiplier = 1.0 nên V2 vẫn chạy y nguyên.
    learn_mult = get_learning_multipliers(learning_profile, regime_name)
    for _k in ["market", "action", "storm", "evo", "zone", "obv"]:
        weights[_k] = weights.get(_k, 1.0) * learn_mult.get(_k, 1.0)

    market_score, market_note = elite_market_score(market_real, market_forecast)
    base["REGIME"] = regime_name
    base["LearningMode"] = str((learning_profile or {}).get("mode", "WARMUP"))
    base["MarketScore"] = market_score * weights["market"]

    sig = base["GR_SIGNAL"].astype(str)
    base["ActionScoreRaw"] = np.select(
        [
            sig.str.startswith("🟢 XANH MUA"),
            sig.str.startswith("🟢"),
            sig.str.startswith("🟡 CANH"),
            sig.str.startswith("🟡"),
        ],
        [25, 20, 12, 8],
        default=0,
    )

    base["GR_BUY_SCORE_NUM"] = pd.to_numeric(base.get("GR_BUY_SCORE", np.nan), errors="coerce")
    base["BuyScoreBonusRaw"] = (base["GR_BUY_SCORE_NUM"].clip(lower=0, upper=100) / 100 * 10).fillna(0)
    base["ActionScore"] = (base["ActionScoreRaw"] + base["BuyScoreBonusRaw"]) * weights["action"]

    base["Storm_NUM"] = pd.to_numeric(base.get("Storm", np.nan), errors="coerce")
    base["StormScore"] = np.where(
        base["Storm_NUM"].notna(),
        10 + base["Storm_NUM"].clip(lower=0, upper=10),
        0,
    ) * weights["storm"]

    base["Persistence_NUM"] = pd.to_numeric(base.get("Persistence", 0), errors="coerce").fillna(0)
    base["evolution_NUM"] = pd.to_numeric(base.get("evolution", 0), errors="coerce").fillna(0)
    base["recent_change_NUM"] = pd.to_numeric(base.get("recent_change", 0), errors="coerce").fillna(0)
    base["EvoFinal_NUM"] = pd.to_numeric(base.get("EvoFinal", 0), errors="coerce").fillna(0)

    base["EvoScore"] = (
        base["Persistence_NUM"].clip(0, 7) * 1.5
        + base["evolution_NUM"].clip(lower=0, upper=5) * 2.0
        + base["recent_change_NUM"].clip(lower=0, upper=3) * 2.5
        + base["EvoFinal_NUM"].clip(lower=0, upper=20) * 0.25
    ).clip(0, 20) * weights["evo"]

    group = base["group"].astype(str)
    base["ZoneScore"] = np.select(
        [
            group.eq("PULL ĐẸP"),
            group.eq("PULL VỪA"),
            group.eq("MUA EARLY") & base["InEarlyLab"],
            group.eq("MUA EARLY"),
            base["InPullback"],
        ],
        [18, 15, 14, 9, 12],
        default=0,
    ) * weights["zone"]

    base["ObvScore"] = np.where(base.get("obv_status", "") == "🟢", 5, 0) * weights["obv"]

    # -----------------------------------------------------
    # 6) ĐỒNG THUẬN: đếm số chuyên gia cùng gật đầu
    # -----------------------------------------------------
    base["C_Market"] = to_float(market_real, 0) >= 6
    base["C_Action"] = sig.str.startswith(("🟢", "🟡"), na=False)
    base["C_Storm"] = base["Storm_NUM"].notna()
    base["C_Evo"] = (base["Persistence_NUM"] >= 3.5) | (base["evolution_NUM"] > 0) | (base["recent_change_NUM"] > 0)
    base["C_Zone"] = group.isin(["PULL ĐẸP", "PULL VỪA"]) | base["InPullback"] | base["InEarlyLab"]
    base["C_OBV"] = base.get("obv_status", "") == "🟢"

    consensus_cols = ["C_Market", "C_Action", "C_Storm", "C_Evo", "C_Zone", "C_OBV"]
    base["ConsensusCount"] = base[consensus_cols].sum(axis=1)
    base["ĐỒNG THUẬN"] = base["ConsensusCount"].astype(int).astype(str) + "/6"

    # -----------------------------------------------------
    # 7) RULE ENGINE: phạt và chặn điểm xấu cứng
    # -----------------------------------------------------
    warn = base.get("warning", "").astype(str)
    dist = pd.to_numeric(base.get("dist_from_ema9_pct", np.nan), errors="coerce")
    rsi = pd.to_numeric(base.get("rsi14", np.nan), errors="coerce")

    base["Penalty"] = 0
    base["Penalty"] += np.where(warn.str.contains("OBV gãy", na=False), 35, 0)
    base["Penalty"] += np.where(warn.str.contains("Giá dưới EMA9", na=False), 30, 0)
    base["Penalty"] += np.where(warn.str.contains("RSI yếu", na=False), 12, 0)
    dist_penalty_mult = learn_mult.get("dist_penalty", 1.0)
    rsi_penalty_mult = learn_mult.get("rsi_penalty", 1.0)
    base["Penalty"] += np.where(dist > 4.5, 12 * dist_penalty_mult, 0)
    base["Penalty"] += np.where(rsi > 75, 8 * rsi_penalty_mult, 0)
    base["Penalty"] += np.where(group.eq("GÀ TĂNG TỐC"), 10, 0)
    base["Penalty"] += np.where(group.eq("CP MẠNH") & (dist > 3), 10, 0)

    hard_bad = (
        warn.str.contains("OBV gãy", na=False)
        | warn.str.contains("Giá dưới EMA9", na=False)
    )
    mr = to_float(market_real, 0)

    # STEP 2: attach verified earning_learning evidence before final score.
    base = apply_learning_experience(
        base,
        market_real=market_real,
        market_forecast=market_forecast,
    )
    experience_adj = (
        pd.to_numeric(base.get("ExperienceAdjustment", 0.0), errors="coerce")
        .fillna(0.0)
        .clip(-8.0, 8.0)
    )
    # Safety-first: learning never boosts rows blocked by hard rules or weak market.
    effective_experience_adj = np.where(
        hard_bad,
        0.0,
        np.where(mr < 6, np.minimum(experience_adj, 0.0), experience_adj),
    )

    base["EliteScoreBase"] = (
        base["MarketScore"]
        + base["ActionScore"]
        + base["StormScore"]
        + base["EvoScore"]
        + base["ZoneScore"]
        + base["ObvScore"]
        + base["PatternScore"]
        + base["ConsensusCount"] * 2.0
        - base["Penalty"]
    ).clip(0, 100).round(1)
    # Leader Memory cũng phải tuân thủ Rule Engine và Market First.
    leader_memory_adj = (
        pd.to_numeric(
            base.get("LeaderMemoryAdjustment", 0.0),
            errors="coerce",
        )
        .fillna(0.0)
        .clip(-5.0, 5.0)
    )

    effective_leader_memory_adj = np.where(
        hard_bad,
        0.0,
        np.where(
            mr < 6,
            np.minimum(leader_memory_adj, 0.0),
            leader_memory_adj,
        ),
    )

    # Final score:
    # - EliteScoreBase = tín hiệu kỹ thuật hiện tại
    # - Experience = kinh nghiệm Pattern/Continuation T3/T5/T10
    # - Leader Memory = kinh nghiệm riêng của từng cổ phiếu
    base["EliteScore"] = (
        base["EliteScoreBase"]
        + effective_experience_adj
        + effective_leader_memory_adj
    ).clip(0, 100).round(1)
    # -----------------------------------------------------
    # 8) WIN PROBABILITY V2: xác suất ước lượng để xếp hạng thực chiến
    # -----------------------------------------------------
    base["WinProb"] = (
            28
            + base["EliteScore"] * 0.55
            + base["ConsensusCount"] * 4.0
            + np.where(group.eq("PULL ĐẸP"), 6, 0)
            + np.where(group.eq("PULL VỪA"), 3, 0)
            + np.where(base["InEarlyLab"], 5, 0)
            - np.where(rsi > 72, 8, 0)
            - np.where(dist > 3.5, 7, 0)
            - np.where(hard_bad, 35, 0)
        )

        # Market là trần xác suất, không để điểm đẹp đánh lừa khi thị trường yếu.

        # -----------------------------------------------------
        # MARKET FIRST: điều chỉnh WinProb theo sức khỏe thị trường
        # nhưng vẫn giữ thứ hạng giữa các cổ phiếu
        # -----------------------------------------------------

    if mr < 6:
        market_factor = 0.72
        market_cap = 55
    elif mr < 8:
        market_factor = 0.88
        market_cap = 78
    else:
        market_factor = 1.00
        market_cap = 95

    base["WinProb"] = (
        (base["WinProb"] * market_factor)
        .clip(0, market_cap)
        .round()
        .astype(int)
    )

    base["⭐"] = base["WinProb"].apply(elite_star)
    base["ĐỘ TIN CẬY"] = base["WinProb"].apply(elite_confidence)

    # -----------------------------------------------------
    # 9) ĐÈN / HÀNH ĐỘNG / NAV
    # -----------------------------------------------------
    base["ĐÈN"] = np.select(
        [
            (mr < 6),
            hard_bad,
            (base["WinProb"] >= 85) & (base["ConsensusCount"] >= 5),
            (base["WinProb"] >= 75) & (base["ConsensusCount"] >= 4),
            base["WinProb"] >= 60,
        ],
        ["🟡", "🔴", "🟢", "🟢", "🟡"],
        default="⚪",
    )

    base["KẾT LUẬN"] = np.select(
        [
            mr < 6,
            hard_bad,
            (base["WinProb"] >= 85) & (base["ConsensusCount"] >= 5),
            (base["WinProb"] >= 75) & (base["ConsensusCount"] >= 4),
            base["WinProb"] >= 60,
        ],
        [
            "WATCHLIST - MARKET YẾU",
            "LOẠI - TRỤC XẤU",
            "BUY ELITE",
            "MUA NHỎ / ƯU TIÊN",
            "WATCHLIST",
        ],
        default="CHƯA ĐỦ ĐỒNG THUẬN",
    )

    base["NAV ELITE"] = [
        elite_nav_v2(c, p, market_real)
        for c, p in zip(base["KẾT LUẬN"], base["WinProb"])
    ]

    # Vùng mua ưu tiên lấy từ Xanh/Đỏ; nếu không có thì tự tính quanh EMA9/giá.
    base["VÙNG MUA ELITE"] = base.get("GR_VÙNG MUA", "").astype(str)
    empty_zone = base["VÙNG MUA ELITE"].isin(["", "-", "nan", "None"])
    ema9_num = pd.to_numeric(base.get("ema9", np.nan), errors="coerce")
    price_num = pd.to_numeric(base.get("price", np.nan), errors="coerce")

    auto_zone = np.where(
        ema9_num.notna(),
        (ema9_num * 0.99).round(0).astype("Int64").astype(str)
        + " - "
        + (ema9_num * 1.01).round(0).astype("Int64").astype(str),
        price_num.round(0).astype("Int64").astype(str),
    )

    base.loc[empty_zone, "VÙNG MUA ELITE"] = auto_zone[empty_zone]
    # -----------------------------------------------------
    # 10) LÝ DO: phải giải thích được vì sao được chọn
    # -----------------------------------------------------
    reasons = []
    risks = []
    for _, r in base.iterrows():
        rs = []
        rk = []
        rs.append(regime_note)
        if str(r.get("GR_SIGNAL", "")).startswith("🟢"):
            rs.append("✅ Xanh/Đỏ cho mua")
        elif str(r.get("GR_SIGNAL", "")).startswith("🟡"):
            rs.append("✅ Xanh/Đỏ cho canh")
        if pd.notna(r.get("Storm", np.nan)):
            rs.append("✅ Storm")
        if r.get("Persistence_NUM", 0) >= 5:
            rs.append("✅ DNA mạnh")
        elif r.get("Persistence_NUM", 0) >= 3.5:
            rs.append("✅ DNA bền")
        if r.get("recent_change_NUM", 0) > 0 or r.get("evolution_NUM", 0) > 0:
            rs.append("✅ Evolution tăng")
        if bool(r.get("InPullback", False)):
            rs.append("✅ Pullback")
        if bool(r.get("InEarlyLab", False)):
            rs.append("✅ Early Lab")
        if str(r.get("obv_status", "")) == "🟢":
            rs.append("✅ OBV giữ")
        if to_float(r.get("pattern_match", 0), 0) >= 70:
            rs.append(f"✅ Pattern Match {to_float(r.get('pattern_match', 0), 0):.1f}%")
        exp_adj = to_float(r.get("ExperienceAdjustment", 0), 0)
        if exp_adj > 0:
            rs.append(f"✅ Learning +{exp_adj:.1f}")
        elif exp_adj < 0:
            rk.append(f"❌ Learning {exp_adj:.1f}")
        if to_float(market_real, 0) < 6:
            rk.append("❌ Market yếu")
        if r.get("Penalty", 0) > 0:
            rk.append(f"❌ Phạt rủi ro {int(r.get('Penalty', 0))}")
        if to_float(r.get("rsi14", np.nan), np.nan) > 72:
            rk.append("❌ RSI nóng")
        if to_float(r.get("dist_from_ema9_pct", np.nan), np.nan) > 3.5:
            rk.append("❌ Xa EMA9")
        reasons.append(" | ".join(dict.fromkeys(rs)))
        risks.append(" | ".join(dict.fromkeys(rk)))

    base["LÝ DO ELITE"] = reasons
    base["RỦI RO"] = risks

    out = base.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "dist_from_ema9_pct": "DIST EMA9%",
        "obv_status": "OBV",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "ĐÈN", "⭐", "MÃ", "KẾT LUẬN", "WinProb", "ĐỘ TIN CẬY", "ĐỒNG THUẬN", "EliteScore",
        "EliteScoreBase", "LeaderMemoryScore", "LeaderMemoryConfidence", "LeaderMemoryAdjustment",
        "ExperienceAdjustment", "ExperienceSamples", "LearnedWinRate",
        "ContinuationScore", "MatchedPattern", "MatchedMarketContext", "ContextMatchMode", "LearningStatus",
        "NHÓM", "GIÁ", "VÙNG MUA ELITE", "NAV ELITE", "REGIME", "LearningMode",
        "MarketScore", "ActionScore", "StormScore", "EvoScore", "ZoneScore", "PatternScore", "Penalty",
        "pattern_match", "GR_SIGNAL", "GR_BUY_SCORE", "Storm", "Persistence", "DNA", "evolution", "recent_change",
        "RSI", "SLOPE", "DIST EMA9%", "OBV", "LÝ DO ELITE", "RỦI RO", "CẢNH BÁO",
    ]
    cols = [c for c in cols if c in out.columns]

    out = out.sort_values(
        ["WinProb", "EliteScore", "ConsensusCount", "ActionScore", "StormScore", "EvoScore", "ZoneScore"],
        ascending=[False, False, False, False, False, False, False],
    ).reset_index(drop=True)

    # Giữ bảng đủ gọn: mã có xác suất/đồng thuận tương đối hoặc đang nằm trong Xanh/Đỏ / Storm / Pull / Early.
    out = out[
        (out["WinProb"] >= 45)
        | out.get("GR_SIGNAL", "").astype(str).str.startswith(("🟢", "🟡"), na=False)
        | out.get("Storm", pd.Series(index=out.index, dtype=float)).notna()
    ].copy()

    return out[cols].head(30)


def build_buy_elite_today_summary(buy_elite_df: pd.DataFrame, market_real: float, market_forecast: float) -> dict:
    """Tạo quyết định đầu trang để mở app là biết hôm nay làm gì."""
    regime_name, _, regime_note = elite_regime(market_real, market_forecast)
    if buy_elite_df is None or buy_elite_df.empty:
        return {
            "title": "⛔ KHÔNG CÓ MÃ ĐỦ ĐỒNG THUẬN",
            "detail": regime_note,
            "top": "-",
            "nav": "0%",
            "regime": regime_name,
        }

    actionable = buy_elite_df[buy_elite_df["KẾT LUẬN"].astype(str).isin(["BUY ELITE", "MUA NHỎ / ƯU TIÊN"])].copy()
    if to_float(market_real, 0) < 6:
        top_names = ", ".join(buy_elite_df.head(3)["MÃ"].astype(str).tolist())
        return {
            "title": "🟡 CHỈ LẬP WATCHLIST",
            "detail": "Market REAL < 6 nên BUY ELITE chưa cho giải ngân thật.",
            "top": top_names if top_names else "-",
            "nav": "0%",
            "regime": regime_name,
        }

    if actionable.empty:
        top_names = ", ".join(buy_elite_df.head(3)["MÃ"].astype(str).tolist())
        return {
            "title": "🟡 CHƯA CÓ ĐIỂM MUA ĐỦ MẠNH",
            "detail": "Có ứng viên theo dõi nhưng chưa đủ đồng thuận để giải ngân.",
            "top": top_names if top_names else "-",
            "nav": "0%",
            "regime": regime_name,
        }

    top = actionable.head(3)
    top_names = ", ".join(top["MÃ"].astype(str).tolist())
    best_nav = top.iloc[0].get("NAV ELITE", "0%")
    return {
        "title": "🔥 CÓ ỨNG VIÊN BUY ELITE",
        "detail": "Ưu tiên mua đúng vùng, không đuổi xanh quá xa EMA9.",
        "top": top_names,
        "nav": best_nav,
        "regime": regime_name,
    }


def style_buy_elite_board(df: pd.DataFrame):
    """Tô màu bảng BUY ELITE theo kết luận."""
    def row_style(row):
        sig = str(row.get("KẾT LUẬN", ""))
        light = str(row.get("ĐÈN", ""))

        if sig == "BUY ELITE" or light.startswith("🟢"):
            return ["background-color: #d9f7d9; color: #064e06; font-weight: 700"] * len(row)
        if sig.startswith("MUA NHỎ") or sig.startswith("WATCHLIST") or light.startswith("🟡"):
            return ["background-color: #fff3cd; color: #5f4300"] * len(row)
        if sig.startswith("LOẠI") or light.startswith("🔴"):
            return ["background-color: #f8d7da; color: #6b0000"] * len(row)
        return ["background-color: #f5f5f5; color: #333333"] * len(row)

    score_fmt = lambda v: format_display_number(v, max_decimals=2, prefer_int=True)
    int_fmt = lambda v: format_display_number(v, max_decimals=0, prefer_int=True)
    winprob_fmt = lambda v: (
        f"{format_display_number(v, max_decimals=0, prefer_int=True)}%"
        if format_display_number(v, max_decimals=0, prefer_int=True)
        else ""
    )

    return (
        df.style
        .apply(row_style, axis=1)
        .format({
            "EliteScore": score_fmt,
            "EliteScoreBase": score_fmt,
            "ExperienceAdjustment": score_fmt,
            "LearnedWinRate": score_fmt,
            "ContinuationScore": score_fmt,
            "PatternScore": score_fmt,
            "ExperienceSamples": int_fmt,
            "WinProb": winprob_fmt,
            "GIÁ": int_fmt,
            "MarketScore": score_fmt,
            "ActionScore": score_fmt,
            "StormScore": score_fmt,
            "EvoScore": score_fmt,
            "ZoneScore": score_fmt,
            "Penalty": int_fmt,
            "GR_BUY_SCORE": score_fmt,
            "Storm": score_fmt,
            "Persistence": score_fmt,
            "evolution": int_fmt,
            "recent_change": int_fmt,
            "RSI": score_fmt,
            "SLOPE": score_fmt,
            "DIST EMA9%": score_fmt,
        }, na_rep="")
    )

# =========================================================
# COMPACT TABLE VIEW - ẨN CỘT PHỤ CHO MOBILE
# =========================================================
def split_existing_cols(df: pd.DataFrame, main_cols: list[str]):
    """Tách cột chính / cột phụ nhưng không làm mất dữ liệu gốc.

    - main_cols: các cột cần nhìn nhanh trên điện thoại.
    - extra_cols: toàn bộ cột còn lại, mở trong expander khi cần soi kỹ.
    """
    if df is None or df.empty:
        return [], []

    main = [c for c in main_cols if c in df.columns]
    extra = [c for c in df.columns if c not in main]
    return main, extra


def show_compact_table(
    df: pd.DataFrame,
    main_cols: list[str],
    height: int = 420,
    detail_title: str = "🔎 Mở cột phụ / xem đầy đủ",
    hide_index: bool = True,
):
    """Hiển thị bảng tinh gọn trước, cột phụ để trong nút mở rộng.

    Cách này hợp với điện thoại: bảng chính chỉ còn các cột quyết định mua/bán.
    Dữ liệu phụ vẫn tồn tại và xem được trên máy tính bằng expander.
    """
    if df is None or df.empty:
        return

    main, extra = split_existing_cols(df, main_cols)

    if main:
        st.dataframe(
            df[main],
            use_container_width=True,
            hide_index=hide_index,
            height=height,
        )
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=hide_index,
            height=height,
        )

    if extra:
        with st.expander(detail_title, expanded=False):
            st.dataframe(
                df[main + extra] if main else df,
                use_container_width=True,
                hide_index=hide_index,
                height=min(700, height + 160),
            )

# =========================================================
# V21 BRAIN SYNC BRIDGE
# =========================================================
def build_market_snapshot_for_brain(scan_df, market_real, market_live, market_forecast):
    return pd.DataFrame([{
        "date": today_str(),
        "time": vn_time_str("%H:%M:%S"),
        "session_slot": "EOD" if vn_now().hour >= 15 else "INTRADAY",

        "market_real": market_real,
        "market_live": market_live,
        "market_forecast": market_forecast,

        "pull_dep": int((scan_df["group"] == "PULL ĐẸP").sum()),
        "pull_vua": int((scan_df["group"] == "PULL VỪA").sum()),
        "mua_early": int((scan_df["group"] == "MUA EARLY").sum()),
        "cp_manh": int((scan_df["group"] == "CP MẠNH").sum()),
        "ga_tang_toc": int((scan_df["group"] == "GÀ TĂNG TỐC").sum()),

        "obv_green_pct": round((scan_df["obv_status"] == "🟢").mean() * 100, 2) if "obv_status" in scan_df.columns else np.nan,
        "slope_positive_pct": round((scan_df["ema9_ma20_slope"] > 0).mean() * 100, 2) if "ema9_ma20_slope" in scan_df.columns else np.nan,
        "rsi_above_50_pct": round((scan_df["rsi14"] > 50).mean() * 100, 2) if "rsi14" in scan_df.columns else np.nan,
    }])


def run_v21_brain_cycle(
    scan_df,
    evo_saved_df,
    buy_elite_history_df,
    market_real,
    market_live,
    market_forecast,
    trading_today,
):
    if get_brain is None:
        return None, None, None, "BRAIN_IMPORT_ERROR", BRAIN_IMPORT_ERROR

    try:
        brain = get_brain()

        market_snapshot_df = build_market_snapshot_for_brain(
            scan_df=scan_df,
            market_real=market_real,
            market_live=market_live,
            market_forecast=market_forecast,
        )

        brain.remember(
            table="market_snapshot",
            data=market_snapshot_df,
            key=["date", "session_slot"],
            keep_days=720,
            date_col="date",
            sort_by=["date", "time"],
            sync_github=False,
        )

        if isinstance(evo_saved_df, pd.DataFrame) and not evo_saved_df.empty:
            brain.remember(
                table="group_evolution_history",
                data=evo_saved_df,
                key=["date", "symbol"],
                keep_days=720,
                date_col="date",
                sort_by=["date", "symbol"],
                sync_github=False,
            )

        if isinstance(buy_elite_history_df, pd.DataFrame) and not buy_elite_history_df.empty:
            brain.remember(
                table="buy_elite_learning_history",
                data=buy_elite_history_df,
                key=["date", "symbol"],
                keep_days=720,
                date_col="date",
                sort_by=["date", "symbol"],
                sync_github=False,
            )

        if save_experience_learning is not None and trading_today:
            experience_df, experience_status, experience_summary = save_experience_learning(brain)
        else:
            experience_df = brain.recall("bot_experience_learning")
            experience_status = "SKIP_INTRADAY_OR_NO_MODULE"
            experience_summary = {}

        if make_market_decision is not None:
            decision = make_market_decision(brain=brain, save=True)
        else:
            decision = {}

        return brain, experience_df, decision, experience_status, experience_summary

    except Exception as e:
        return None, None, None, "BRAIN_CYCLE_ERROR", str(e)
# =========================================================
# UI CONTROLS - V20 PULLBACK FIRST
# =========================================================
left1, left2, left3, left4, left5, left6, left7 = st.columns([1.05, 1.15, 1.0, 1.25, 1.2, 1.2, 2.4])

with left1:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with left2:
    auto_refresh = st.checkbox("Auto refresh", value=True)

with left3:
    refresh_seconds = st.selectbox("Nhịp", [60, 90, 120, 300, 600], index=2)

with left4:
    show_detail = st.checkbox("Chi tiết", value=False)

with left5:
    show_legacy = st.checkbox("Bảng phụ", value=False)

with left6:
    show_green_red = st.checkbox("Xanh/Đỏ", value=True)

with left7:
    st.markdown(
        f"""
        <div style="font-size:14px">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Live cache: <b>{LIVE_CACHE_TTL}s</b> &nbsp; | &nbsp;
        Daily cache: <b>{DAILY_CACHE_TTL // 60} phút</b> &nbsp; | &nbsp;
        Update VN: <b>{vn_time_str()}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

if "last_auto_refresh" not in st.session_state:
    st.session_state["last_auto_refresh"] = time.time()

if scan_btn:
    st.cache_data.clear()

if auto_refresh:
    now_ts = time.time()
    if now_ts - st.session_state["last_auto_refresh"] >= refresh_seconds:
        st.session_state["last_auto_refresh"] = now_ts
        st.cache_data.clear()
        st.rerun()

# =========================================================
# RUN SCAN
# =========================================================
with st.spinner("Đang quét realtime unified..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra mạng, vnstock hoặc requirements.txt.")
    st.stop()

# =========================================================
# EVOLUTION HEALTH V1.0 - TÍNH TRÊN CHÍNH scan_df
# =========================================================
scan_df = add_evolution_health(scan_df)

# =========================================================
# MARKET FIRST
# =========================================================
market_real = calc_market_real(scan_df)
market_live = calc_market_live(scan_df)

forecast_result = calc_market_forecast(scan_df)

market_forecast = forecast_result.score
market_forecast_text = forecast_result.text
market_confidence = forecast_result.confidence
market_status, market_action = market_status_text(market_real)
try:
    _, pattern_status = save_pattern_history(
        brain=None,
        scan_df=scan_df,
        market_real=market_real,
        market_forecast=market_forecast,
    )
    st.caption(f"Pattern Memory: {pattern_status}")
except Exception as e:
    st.warning(f"Pattern Memory Error: {e}")
# =========================================================
# MR.BOT BRAIN CONTROLLER
# =========================================================
try:
    from brain_controller import run_brain_controller

    brain_result = run_brain_controller(
        scan_df=scan_df,
        market_real=market_real,
        market_live=market_live,
        market_forecast=market_forecast,
        trading_today=trading_today if "trading_today" in globals() else True,
    )

except Exception as e:
    st.warning(f"Brain Controller: {e}")

    brain_result = {
        "status": "ERROR",
        "error": str(e),
    }
live_count = int(scan_df["is_live_adjusted"].sum()) if "is_live_adjusted" in scan_df.columns else 0
safe_mode_count = int((scan_df["live_source"].astype(str).str.contains("SAFE_MODE|NO_DATA|BAD", na=False)).sum()) if "live_source" in scan_df.columns else 0

st.markdown("## 🌍 MARKET FIRST")
m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
with m1:
    st.metric("REAL", f"{market_real}/13")
with m2:
    st.metric("LIVE", f"{market_live}/13")
with m3:
    st.metric("FORECAST", f"{market_forecast}/10")
with m4:
    st.metric("CONFIDENCE", f"{market_confidence:.0f}%")

with m5:
    st.metric("SCAN OK", len(scan_df))

with m6:
    st.metric("LIVE OK", live_count)

with m7:
    st.metric("WATCHLIST", len(WATCHLIST))
# =========================================================
# EARNING MONEY BOARD - BẢNG ĐIỀU KHIỂN CHÍNH
# =========================================================
render_earning_money_board(
    scan_df,
    title="🏆 EARNING MONEY BOARD",
    height=720,
)

# Độ rộng RSI + lời kết luận tự động của Mr.BOT.
rsi_breadth_report = render_rsi_breadth_report(scan_df)

daily_result = process_and_render_daily_summary(
    scan_df,
    title="📊 DAILY EARNING MONEY REPORT",
)
# =========================================================
# EXPERIENCE ENGINE
# =========================================================
try:
    experience_result = run_experience_engine(
        holding_detail=daily_result.holding_detail,
        save=True,
    )

    st.caption("🧠 " + experience_result.status)

except Exception as e:
    st.warning(f"Experience Engine: {e}")
# =========================================================
# EARNING LEARNING ENGINE
# =========================================================
try:
    _learning_market_context = {
        "market_score": market_real,
        "market_forecast": market_forecast,
        "market_regime": market_forecast_text,
    }
    if isinstance(rsi_breadth_report, dict):
        _breadth_score = rsi_breadth_report.get("score")
        if _breadth_score is not None:
            try:
                if pd.notna(_breadth_score):
                    _learning_market_context["breadth"] = float(_breadth_score)
            except (TypeError, ValueError):
                pass
    learning_result = update_learning(
        earning_board_df=scan_df,
        market_context=_learning_market_context,
    )
except Exception as e:
    st.warning(f"Earning Learning: {e}")

# =========================================================
# LEADER MEMORY ENGINE
# Cập nhật trước khi Pattern Match đọc Leader Brain.
# =========================================================
try:
    leader_memory_df = update_memory(
        df_today=scan_df,
        market_real=market_real,
        market_forecast=market_forecast,
        market_regime=market_forecast_text,
        raise_errors=True,
    )
except Exception as e:
    st.warning(f"Leader Memory: {type(e).__name__}: {e}")

# =========================================================
# BOT LEARNING INSIGHT - CHỈ HIỂN THỊ MỘT LẦN
# =========================================================
try:
    learning_insight_result = render_bot_learning_insight()
except Exception as e:
    st.info("🧠 BOT Learning Insight đang tạm ẩn; dữ liệu học vẫn được bảo toàn.")
    st.caption(f"Learning Insight Error: {type(e).__name__}: {e}")

# =========================================================
# TOP PATTERN MATCH
# Hiển thị sau Insight: BOT học gì → mã nào giống DNA thắng nhất.
# =========================================================
try:
    show_pattern_match(scan_df)
except Exception as e:
    st.warning(f"Pattern Match: {type(e).__name__}: {e}")

if market_real < 6:
    st.error(market_action)
elif market_real < 8:
    st.warning(market_action)
else:
    st.success(market_action)

st.caption(market_forecast_text)
if safe_mode_count > 0:
    st.caption(f"🟡 SAFE DATA: {safe_mode_count} mã đang dùng D1/NO_DATA thay cho live để tránh app bị crash.")
st.caption("Mr.BOT PRO V4.0: tất cả bảng vẫn dùng chung scan_df. BUY ELITE ra quyết định; Learning ghi nhớ; Thinking phản biện; Bot Evolution lưu nhân cách và tiến hóa chậm từ thực chiến.")

# =========================================================
# PREPARE CORE TABLES
# =========================================================
storm_df = build_storm_leaders(scan_df)
trading_today, trading_reason = is_vnindex_trading_today()
evo_saved_df, evo_save_status = save_evolution(scan_df, allow_save=trading_today, reason=trading_reason)
evo_table, evo_buy_table = build_evolution_tables(scan_df)
pullback_df = build_pullback_buy_list(
    scan_df=scan_df,
    evo_table=evo_table,
    storm_df=storm_df,
    market_real=market_real,
    market_forecast=market_forecast,
)
early_buy_lab_df = build_early_buy_lab(
    scan_df=scan_df,
    evo_table=evo_table,
    storm_df=storm_df,
    market_real=market_real,
    market_forecast=market_forecast,
)

green_red_df = build_green_red_board(
    scan_df=scan_df,
    evo_table=evo_table,
    storm_df=storm_df,
    market_real=market_real,
    market_forecast=market_forecast,
)

learning_profile = read_buy_elite_learning_profile()

# PATTERN -> DECISION BRIDGE
# Dùng Market Real hiện tại để Pattern Match chấm đúng bối cảnh phiên đang chạy.
try:
    pattern_input_df = scan_df.copy()
    pattern_input_df["market_real"] = market_real
    pattern_match_df = build_pattern_match(pattern_input_df)
except Exception as e:
    pattern_match_df = pd.DataFrame()
    st.warning(f"Pattern -> Decision Bridge: {type(e).__name__}: {e}")

buy_elite_df = build_buy_elite_decision_engine(
    scan_df=scan_df,
    green_red_df=green_red_df,
    storm_df=storm_df,
    evo_table=evo_table,
    pullback_df=pullback_df,
    early_buy_lab_df=early_buy_lab_df,
    market_real=market_real,
    market_forecast=market_forecast,
    learning_profile=learning_profile,
    pattern_match_df=pattern_match_df,
    leader_memory_df=leader_memory_df,
)
final_df, final_note = build_final_decision(
    buy_elite_df,
    green_red_df,
)
buy_elite_history_df, learning_profile_after, learning_hist_status, learning_profile_status = run_buy_elite_learning_cycle(
    buy_elite_df=buy_elite_df,
    scan_df=scan_df,
    market_real=market_real,
    market_forecast=market_forecast,
    trading_today=trading_today,
)
learning_summary = build_learning_summary(learning_profile_after, buy_elite_history_df)

thinking_profile_old = read_buy_elite_thinking_profile()
thinking_profile_after = build_buy_elite_thinking_profile(
    history_df=buy_elite_history_df,
    learning_profile=learning_profile_after,
    buy_elite_df=buy_elite_df,
    market_real=market_real,
    market_forecast=market_forecast,
    old_profile=thinking_profile_old,
)
thinking_profile_status = write_buy_elite_thinking_profile(thinking_profile_after)
thinking_journal_status = append_thinking_journal(thinking_profile_after)
thinking_summary = build_thinking_summary(thinking_profile_after)
# =========================================================
# V21 BRAIN / EXPERIENCE LEARNING / DECISION CYCLE
# =========================================================
brain, v21_experience_df, v21_decision, v21_brain_status, v21_brain_summary = run_v21_brain_cycle(
    scan_df=scan_df,
    evo_saved_df=evo_saved_df,
    buy_elite_history_df=buy_elite_history_df,
    market_real=market_real,
    market_live=market_live,
    market_forecast=market_forecast,
    trading_today=trading_today,
)
# =========================================================
# V21 BRAIN OPTIMIZER
# =========================================================
v21_optimizer_report = {}
v21_optimizer_recommendation = {}
v21_optimizer_save_result = None

if brain is not None and run_brain_optimizer is not None:
    try:
        v21_optimizer_report, v21_optimizer_recommendation, v21_optimizer_save_result = run_brain_optimizer(
            brain=brain,
            save=True,
        )
    except Exception as e:
        v21_optimizer_report = {
            "status": "OPTIMIZER_ERROR",
            "report_text": str(e),
        }
        v21_optimizer_recommendation = {}
        v21_optimizer_save_result = None
mr_bot_profile_old = read_mr_bot_pro_profile()
mr_bot_profile_after = build_mr_bot_pro_profile(
    old_profile=mr_bot_profile_old,
    learning_profile=learning_profile_after,
    thinking_profile=thinking_profile_after,
    history_df=buy_elite_history_df,
    buy_elite_df=buy_elite_df,
    market_real=market_real,
    market_forecast=market_forecast,
)
mr_bot_profile_status = write_mr_bot_pro_profile(mr_bot_profile_after)
mr_bot_journal_status = write_mr_bot_pro_journal(mr_bot_profile_after)
mr_bot_summary = build_mr_bot_pro_summary(mr_bot_profile_after)


# =========================================================
# Mr.BOT PRO V4.0 / DECISION + LEARNING + THINKING + EVOLUTION
# =========================================================
st.markdown("---")
st.markdown("# 🤖 Mr.BOT PRO V4.0")
st.caption("Observe • Learn • Think • Evolve | Tôi không dự đoán tương lai. Tôi học từ quá khứ để hỗ trợ quyết định hiện tại.")

b1, b2, b3, b4, b5 = st.columns([1.2, 1.0, 1.0, 1.0, 1.4])
with b1:
    st.metric("STATUS", mr_bot_summary["status"])
with b2:
    st.metric("AGE", f"{mr_bot_summary['age']} ngày")
with b3:
    st.metric("VERSION", mr_bot_summary["version"])
with b4:
    st.metric("CONFIDENCE", f"{mr_bot_summary['confidence']}%")
with b5:
    st.metric("NHÂN CÁCH", mr_bot_summary["personality"])

st.info(mr_bot_summary["message"])

with st.expander("🤖 Hồ sơ Mr.BOT PRO / Nhân cách / Đề xuất / Câu hỏi tự kiểm tra"):
    st.caption(f"Profile save: {mr_bot_profile_status} | Journal save: {mr_bot_journal_status}")
    st.markdown("**Hiến pháp của Mr.BOT PRO:**")
    for item in mr_bot_profile_after.get("constitution", []):
        st.write("• " + str(item))

    if mr_bot_summary.get("proposals"):
        st.markdown("**Đề xuất hiện tại:**")
        for item in mr_bot_summary["proposals"]:
            st.write("• " + str(item))

    if mr_bot_summary.get("self_questions"):
        st.markdown("**Câu hỏi tự phản biện:**")
        for item in mr_bot_summary["self_questions"]:
            st.write("• " + str(item))

    log_show = mr_bot_profile_after.get("evolution_log", [])
    if log_show:
        st.markdown("**Nhật ký tiến hóa gần nhất:**")
        st.dataframe(pd.DataFrame(log_show[-12:]), use_container_width=True, hide_index=True)
# =========================================================
# V21 BRAIN DASHBOARD
# =========================================================
st.markdown("## 🧠 V21 BRAIN - EXPERIENCE DECISION")
with st.expander("🧬 Brain Optimizer - Bot tự đánh giá"):
    if isinstance(v21_optimizer_report, dict) and v21_optimizer_report:
        st.dataframe(
            build_optimizer_view(v21_optimizer_report),
            use_container_width=True,
            hide_index=True,
        )

        if isinstance(v21_optimizer_recommendation, dict) and v21_optimizer_recommendation:
            st.markdown("**Recommendation:**")
            st.dataframe(
                build_recommendation_view(v21_optimizer_recommendation),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**Brain Report:**")
        st.code(
            build_report_markdown(v21_optimizer_report),
            language="text",
        )
    else:
        st.caption("Brain Optimizer đang chờ đủ dữ liệu.")
if v21_brain_status in ["SAVED", "LOCAL_ONLY"] or str(v21_brain_status).startswith("SKIP"):
    st.caption(f"Brain status: {v21_brain_status}")
else:
    st.warning(f"Brain status: {v21_brain_status} | {v21_brain_summary}")

if isinstance(v21_decision, dict) and v21_decision:
    d1, d2, d3, d4 = st.columns(4)

    with d1:
        st.metric("ACTION", v21_decision.get("action", ""))
    with d2:
        st.metric("CONFIDENCE", v21_decision.get("confidence", 0))
    with d3:
        st.metric("RISK", v21_decision.get("risk_level", ""))
    with d4:
        st.metric("NAV", f"{v21_decision.get('suggested_nav', 0)}%")

    st.info(v21_decision.get("decision_text", ""))

    with st.expander("🔎 V21 Decision chi tiết"):
        st.dataframe(
            build_decision_view(v21_decision),
            use_container_width=True,
            hide_index=True,
        )

        if brain is not None and build_decision_history_view is not None:
            hist_view = build_decision_history_view(brain, n=20)
            if hist_view is not None and not hist_view.empty:
                st.markdown("**Decision history gần nhất:**")
                st.dataframe(hist_view, use_container_width=True, hide_index=True)

if isinstance(v21_experience_df, pd.DataFrame) and not v21_experience_df.empty:
    with st.expander("📚 V21 Experience Learning"):
        view = build_learning_view(v21_experience_df) if build_learning_view is not None else v21_experience_df
        st.dataframe(view.tail(30), use_container_width=True, hide_index=True)
else:
    st.caption("V21 Experience Learning: đang chờ dữ liệu đủ để học.")
# =========================================================
# PHÂN TÍCH CHUYÊN SÂU - ẨN MẶC ĐỊNH
# =========================================================
show_advanced_analysis = st.toggle(
    "📂 PHÂN TÍCH CHUYÊN SÂU",
    value=False,
    help="Mở các bảng Elite, Xanh mua - Đỏ bán, Storm, DNA và Evolution.",
)

if show_advanced_analysis:
    st.markdown("## 👑 BUY ELITE - DECISION ENGINE")

    elite_summary = build_buy_elite_today_summary(buy_elite_df, market_real, market_forecast)

    s1, s2, s3, s4 = st.columns([1.8, 1.2, 1.2, 1.2])
    with s1:
        st.metric("🎯 TODAY ACTION", elite_summary["title"])
    with s2:
        st.metric("MARKET REGIME", elite_summary["regime"])
    with s3:
        st.metric("TOP WATCH", elite_summary["top"])
    with s4:
        st.metric("NAV GỢI Ý", elite_summary["nav"])

    if market_real < 6:
        st.warning(elite_summary["detail"])
    elif market_real < 8:
        st.warning(elite_summary["detail"])
    else:
        st.success(elite_summary["detail"])

    st.markdown("### 🧠 LEARNING ENGINE - Trí nhớ thực chiến")
    l1, l2, l3, l4, l5 = st.columns([1.2, 1.0, 1.0, 1.0, 1.2])
    with l1:
        st.metric("MODE", learning_summary["mode"])
    with l2:
        st.metric("T+5 MẪU", learning_summary["completed"])
    with l3:
        st.metric("WINRATE T+5", learning_summary["winrate"])
    with l4:
        st.metric("AVG T+5", learning_summary["avg_t5"])
    with l5:
        st.metric("TÍN HIỆU ĐÃ GHI", learning_summary["total_signals"])

    if learning_summary["mode"] == "ACTIVE_LEARNING":
        st.success("Learning Engine đã đủ mẫu tối thiểu và đang tự chỉnh trọng số rất chậm.")
    else:
        st.info(learning_summary["note"])

    with st.expander("🧠 Nhật ký học của Mr.BOT PRO"):
        st.caption(f"History save: {learning_hist_status} | Profile save: {learning_profile_status}")
        profile_show = learning_profile_after if isinstance(learning_profile_after, dict) else {}
        mult = profile_show.get("multipliers", {})
        mult_df = pd.DataFrame([{"Yếu tố": k, "Multiplier": v} for k, v in mult.items()])
        if not mult_df.empty:
            st.dataframe(mult_df, use_container_width=True, hide_index=True)
        insights = profile_show.get("insights", [])
        if insights:
            st.markdown("**Những điều bot đang học được:**")
            for item in insights[-12:]:
                st.write("• " + str(item))
        else:
            st.write("Bot đang bắt đầu ghi nhớ dữ liệu. Chưa có insight đủ mạnh.")


    st.markdown("### 🧠 THINKING ENGINE - Tư duy & phản biện")
    t1, t2, t3, t4, t5 = st.columns([1.2, 1.0, 1.0, 1.0, 1.4])
    with t1:
        st.metric("MODE", thinking_summary["mode"])
    with t2:
        st.metric("T+5 MẪU", thinking_summary["completed"])
    with t3:
        st.metric("NIỀM TIN", thinking_summary["beliefs"])
    with t4:
        st.metric("GIẢ THUYẾT", thinking_summary["hypotheses"])
    with t5:
        st.metric("PHẢN BIỆN", thinking_summary["reflections"])

    if thinking_summary["mode"] in ["THINKING", "HYPOTHESIS"]:
        st.success(thinking_summary["current_thought"])
    else:
        st.info(thinking_summary["current_thought"])

    with st.expander("🧠 Nhật ký tư duy / Quan sát / Giả thuyết / Phản biện của Mr.BOT PRO"):
        st.caption(f"Thinking profile: {thinking_profile_status} | Thinking journal: {thinking_journal_status}")
        st.markdown("**Quan sát phiên hiện tại:**")
        obs_show = thinking_profile_after.get("observation", {}) if isinstance(thinking_profile_after, dict) else {}
        obs_df = pd.DataFrame([obs_show]) if obs_show else pd.DataFrame()
        if not obs_df.empty:
            st.dataframe(obs_df, use_container_width=True, hide_index=True)

        beliefs = thinking_profile_after.get("beliefs", []) if isinstance(thinking_profile_after, dict) else []
        hypotheses = thinking_profile_after.get("hypotheses", []) if isinstance(thinking_profile_after, dict) else []
        reflections = thinking_profile_after.get("reflections", []) if isinstance(thinking_profile_after, dict) else []
        observations = thinking_profile_after.get("observations", []) if isinstance(thinking_profile_after, dict) else []

        if beliefs:
            st.markdown("**Niềm tin đang hình thành:**")
            for item in beliefs[:10]:
                st.write("• " + str(item))
        if hypotheses:
            st.markdown("**Giả thuyết đáng theo dõi:**")
            for item in hypotheses[:10]:
                st.write("• " + str(item))
        if observations:
            st.markdown("**Quan sát thống kê:**")
            for item in observations[:8]:
                st.write("• " + str(item))
        if reflections:
            st.markdown("**Bot tự phản biện:**")
            for item in reflections[:8]:
                st.write("• " + str(item))

        st.caption("Nguyên tắc Mr.BOT PRO: không cố chứng minh mình đúng; chỉ liên tục giảm số lần sai bằng dữ liệu thực chiến.")


    if not buy_elite_df.empty:
        elite_compact_cols = [
            "ĐÈN", "⭐", "MÃ", "KẾT LUẬN", "WinProb", "ĐỘ TIN CẬY", "ĐỒNG THUẬN",
            "EliteScore", "NHÓM", "GIÁ", "VÙNG MUA ELITE", "NAV ELITE",
            "Storm", "Persistence", "RSI", "SLOPE", "DIST EMA9%", "OBV", "LÝ DO ELITE", "RỦI RO"
        ]
        elite_compact_cols = [c for c in elite_compact_cols if c in buy_elite_df.columns]
        st.dataframe(
        style_buy_elite_board(
            buy_elite_df[elite_compact_cols]
        ),
        use_container_width=True,
        hide_index=True,
        height=520,
    )


        with st.expander("🔎 Mở đầy đủ cột BUY ELITE"):
            st.dataframe(
                style_buy_elite_board(buy_elite_df),
                use_container_width=True,
                hide_index=True,
                height=760,
            )
            st.caption(
                "Mr.BOT PRO V4.0 = Decision + Learning + Thinking + Evolution: ngoài tự học T+1/T+3/T+5, Bot còn có nhân cách, trí nhớ, câu hỏi phản biện và nhật ký tiến hóa. "
                "Khi dữ liệu chưa đủ, hệ thống chạy WARMUP và không tự thay đổi quá mạnh."
            )
    else:
        st.info("Chưa có mã đủ đồng thuận cho BUY ELITE. Mr.BOT PRO chọn đứng ngoài thay vì ép lệnh.")
# =========================================================
# XANH MUA - ĐỎ BÁN LAB
# =========================================================
st.markdown("---")
st.markdown("## 👑 FINAL DECISION")

st.info(final_note)

if not final_df.empty:

    st.dataframe(
        style_final_decision(format_final_decision_for_display(final_df)),
        use_container_width=True,
        hide_index=True,
        height=520,
    )

else:

    st.warning("Không có cổ phiếu đủ chuẩn giải ngân.")
if show_advanced_analysis:
    if show_green_red:
        st.markdown("---")
        st.markdown("## 🟢🔴 XANH MUA - ĐỎ BÁN LAB")

        if market_real < 6:
            st.warning("Market REAL < 6: bảng chỉ dùng để theo dõi sớm, chưa nên mua thật.")
        elif market_real < 8:
            st.warning("Market trung tính: chỉ ưu tiên mã xanh có BuyScore cao, mua nhỏ và có stop gần.")
        else:
            st.success("Market ủng hộ: ưu tiên mã vừa TrendScore cao vừa BuyScore cao.")

        if not green_red_df.empty:

            compact_cols = [
                "ĐÈN",
                "MÃ",
                "TÍN HIỆU",
                "BUY_SCORE",
                "NHÓM",
                "GIÁ",
                "VÙNG MUA",
                "NAV",
            ]

            st.dataframe(
                style_green_red_board(
                    green_red_df[compact_cols]
                ),
                use_container_width=True,
                hide_index=True,
                height=560,
            )

            with st.expander("🔎 Mở đầy đủ cột Xanh/Đỏ"):
                st.dataframe(
                    style_green_red_board(green_red_df),
                    use_container_width=True,
                    hide_index=True,
                    height=700,
                )

                st.caption(
                    "TrendScore đo sức khỏe cổ phiếu. BuyScore đo chất lượng điểm mua. "
                    "Đèn xanh tốt nhất là mã vừa khỏe vừa có điểm mua gần EMA9, RSI hợp lý, OBV còn giữ."
                )
        else:
            st.info("Chưa có dữ liệu cho bảng Xanh mua - Đỏ bán.")

if show_advanced_analysis:
    # =========================================================
    # STORM LEADERS
    # =========================================================
    st.markdown("---")
    st.markdown("## ⚡ STORM LEADERS - TIỀN ĐANG VÀO ĐÂU")
    if not storm_df.empty:
        show_compact_table(
            storm_df,
            main_cols=["MÃ", "NHÓM", "GIÁ", "STORM", "GREEN2", "VOL/MA20", "RSI", "SLOPE", "OBV", "CẢNH BÁO"],
            height=360,
            detail_title="🔎 Mở đầy đủ cột Storm",
        )
    else:
        st.info("Chưa có mã đạt tiêu chí Storm Leaders.")

# =========================================================
# EARLY BUY LAB - MAIN EARLY TABLE
# =========================================================
st.markdown("---")
st.markdown("## 🌱 EARLY BUY LAB - CẠN CUNG + 2 NẾN XANH GẦN ĐÁY")

if market_real < 6:
    st.warning("Market REAL < 6: Early Buy Lab chỉ dùng để lập watchlist, chưa đánh lớn.")
elif market_real < 8:
    st.warning("Market trung tính: chỉ test nhỏ các mã EarlyScore cao, ưu tiên mua đỏ và stop ngắn.")
else:
    st.success("Market ủng hộ: có thể test sớm mã EarlyScore cao, nhưng vẫn giữ tỷ trọng nhỏ hơn Pullback.")

if not early_buy_lab_df.empty:
    show_compact_table(
        early_buy_lab_df,
        main_cols=["ĐÈN", "MÃ", "TÍN HIỆU", "NHÓM", "GIÁ", "VÙNG MUA", "NAV", "EarlyScore", "RSI", "SLOPE", "OBV", "LÝ DO", "CẢNH BÁO"],
        height=430,
        detail_title="🔎 Mở đầy đủ cột Early Lab",
    )
    st.caption(
        "EarlyScore ưu tiên: RSI 45-58 + cạn cung trước phiên hiện tại + EARLY GREEN2 + gần đáy 20/60 phiên + OBV/Slope không xấu."
    )
else:
    st.info("Chưa có mã đạt chuẩn Early Buy Lab. Đây là bảng săn sớm nên không cần ngày nào cũng có mã.")

# =========================================================
# PULLBACK BUY LIST - MAIN ACTION TABLE
# =========================================================
st.markdown("---")
st.markdown("## 🎯 PULLBACK BUY LIST - MÃ KHỎE ĐANG TEST 3-5%")

if market_real < 6:
    st.warning("Market REAL < 6: bảng Pullback chỉ để lập danh sách theo dõi, chưa dùng để đánh lớn.")
elif market_real < 8:
    st.warning("Market trung tính: ưu tiên test nhỏ, mua đỏ, đặt stop ngắn quanh EMA9.")
else:
    st.success("Market ủng hộ: ưu tiên mã PullScore cao, có Storm + DNA + Evolution đồng thuận.")

if not pullback_df.empty:
    show_compact_table(
        pullback_df,
        main_cols=["ĐÈN", "MÃ", "TÍN HIỆU", "NHÓM", "GIÁ", "VÙNG MUA", "NAV", "PullScore", "RSI", "SLOPE", "DIST EMA9%", "OBV", "LÝ DO", "CẢNH BÁO"],
        height=470,
        detail_title="🔎 Mở đầy đủ cột Pullback",
    )
    st.caption(
        "PullScore ưu tiên: pull 2-5% từ đỉnh gần nhất + test EMA9 + DNA bền + Storm có tiền + Evolution không xấu + OBV/RSI/Slope/Vol ổn."
    )
else:
    st.info("Chưa có mã đạt chuẩn Pullback Buy. Đây thường là lúc nên kiên nhẫn, không ép lệnh.")

if show_advanced_analysis:
    # =========================================================
    # DNA / EVOLUTION - SUPPORTING TABLES
    # =========================================================
    st.markdown("---")
    st.markdown("## 🧬 DNA / EVOLUTION - SỨC MẠNH BỀN VÀ TIẾN HÓA")

    saved_dates = []
    try:
        saved_dates = sorted(pd.to_datetime(evo_saved_df["date"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique())
    except Exception:
        saved_dates = []

    st.caption(
        f"Evolution save: {evo_save_status} | {trading_reason} | Dates: "
        f"{', '.join(saved_dates[-7:]) if saved_dates else 'chưa có'}"
    )

    d1, d2 = st.columns(2)
    with d1:
        st.subheader("🏆 DNA Leaders")
        try:
            if not evo_table.empty and "Persistence" in evo_table.columns:
                dna_leaders = evo_table[evo_table["Persistence"] >= 3.5].copy()
                extra_cols = ["symbol", "rsi14", "ema9_ma20_slope", "total_score", "group", "dist_from_ema9_pct"]
                scan_extra = scan_df[[c for c in extra_cols if c in scan_df.columns]].copy()
                dna_leaders = dna_leaders.merge(scan_extra, on="symbol", how="left")
                cols = ["symbol", "Persistence", "DNA", "group", "rsi14", "ema9_ma20_slope", "dist_from_ema9_pct", "total_score", "evolution", "recent_change"]
                cols = [c for c in cols if c in dna_leaders.columns]
                dna_leaders = dna_leaders[cols].rename(columns={
                    "symbol": "MÃ", "Persistence": "DNA", "DNA": "LOẠI", "group": "NHÓM",
                    "rsi14": "RSI", "ema9_ma20_slope": "SLOPE", "dist_from_ema9_pct": "DIST EMA9%",
                    "total_score": "SCORE", "evolution": "TIẾN HÓA", "recent_change": "GẦN NHẤT"
                })
                dna_leaders = dna_leaders.sort_values(["DNA", "TIẾN HÓA", "SCORE"], ascending=[False, False, False]).head(20)
                show_compact_table(
                    dna_leaders,
                    main_cols=["MÃ", "DNA", "LOẠI", "NHÓM", "RSI", "SLOPE", "DIST EMA9%", "SCORE"],
                    height=380,
                    detail_title="🔎 Mở đầy đủ cột DNA",
                )
            else:
                st.info("Chưa đủ dữ liệu DNA.")
        except Exception as e:
            st.warning(f"DNA LEADERS ERROR: {e}")

    with d2:
        st.subheader("🚀 Evolution chọn lọc")
        if not evo_buy_table.empty:
            show_compact_table(
                evo_buy_table,
                main_cols=["symbol", "TODAY", "today_score", "today_price", "Persistence", "DNA", "EvoFinal", "evolution", "recent_change", "arrow"],
                height=380,
                detail_title="🔎 Mở đầy đủ cột Evolution",
                hide_index=True,
            )
        else:
            st.info("Chưa có cổ phiếu tiến hóa đạt điều kiện mua/theo dõi.")

# =========================================================
# QUICK GROUP SNAPSHOT
# =========================================================
st.markdown("---")
st.markdown("## 📦 NHÓM CỔ PHIẾU - SNAPSHOT")
cols = st.columns(len(GROUP_ORDER))
for c, g in zip(cols, GROUP_ORDER):
    with c:
        st.metric(g, int((scan_df["group"] == g).sum()))
# ==========================================================
# PATTERN MEMORY
# ==========================================================

try:
    brain = get_brain()
    print(">>> SAVE PATTERN START")
    save_pattern_history(
        brain=brain,
        scan_df=scan_df,
        market_real=market_real,
        market_forecast=market_forecast,
    )
    print(">>> SAVE PATTERN DONE")
    print(">>> LEADER MEMORY DONE")
except Exception as e:
    st.error(f"Pattern / Leader Memory Error: {e}")   
# =========================================================
# LEADER MEMORY - CẬP NHẬT TRƯỚC PATTERN MATCH
# =========================================================
try:
    leader_brain_df = update_memory(
        scan_df,
        market_real=market_real,
        market_forecast=market_forecast,
        market_regime=market_forecast_text,
        raise_errors=True,
    )
    st.caption(f"🧠 Leader Memory: {len(leader_brain_df)} mã")
except Exception as e:
    st.warning(f"Leader Memory Update: {type(e).__name__}: {e}")
# =========================================================
# OPTIONAL / LEGACY TABLES
# =========================================================
if show_legacy:
    with st.expander("⚡ Bảng hành động nhanh cũ", expanded=False):
        old_buy_df = build_buy_table(scan_df, market_real)
        show_buy = old_buy_df[old_buy_df["Hành động"] != "KHÔNG MUA"].copy() if not old_buy_df.empty else pd.DataFrame()
        if not show_buy.empty:
            show_compact_table(
                show_buy.head(30),
                main_cols=["Đèn", "Mã", "Hành động", "Nhóm", "Giá", "Vùng mua", "NAV", "Điểm", "RSI", "OBV", "Lý do"],
                height=460,
                detail_title="🔎 Mở đầy đủ cột Hành động nhanh cũ",
            )
        else:
            st.info("Chưa có mã đạt điều kiện mua theo bảng cũ.")

    with st.expander("👑 Tinh Hoa Leaders cũ", expanded=False):
        try:
            tinh_hoa_df = build_tinh_hoa_leaders(
                scan_df=scan_df,
                evo_table=evo_table,
                storm_df=storm_df,
                market_real=market_real,
                market_forecast=market_forecast,
            )
            if not tinh_hoa_df.empty:
                show_compact_table(
                    tinh_hoa_df,
                    main_cols=["MÃ", "NHÓM", "GIÁ", "TINH HOA", "RSI", "SLOPE", "OBV", "CẢNH BÁO"],
                    height=480,
                    detail_title="🔎 Mở đầy đủ cột Tinh Hoa",
                )
            else:
                st.info("Chưa có mã đạt chuẩn Tinh Hoa.")
        except Exception as e:
            st.warning(f"TINH HOA LEADERS ERROR: {e}")

    with st.expander("📊 Thống kê hiệu suất nhóm", expanded=False):
        group_stats = build_group_statistics()
        summary_df = build_group_summary(group_stats)
        if not summary_df.empty:
            st.subheader("🏆 Xếp hạng nhóm tổng hợp")
            st.dataframe(summary_df, use_container_width=True, hide_index=True, height=260)
            st.subheader("Chi tiết T+1 / T+3 / T+5")
            st.dataframe(group_stats, use_container_width=True, hide_index=True, height=420)
        else:
            st.info("Chưa đủ dữ liệu để thống kê.")

    with st.expander("🐔 Bảng theo nhóm", expanded=False):
        tabs = st.tabs(GROUP_ORDER)
        for tab, group_name in zip(tabs, GROUP_ORDER):
            with tab:
                sub = scan_df[scan_df["group"] == group_name].copy()
                if sub.empty:
                    st.info("Không có mã")
                else:
                    show_cols = [
                        "symbol", "status", "price", "total_score", "E", "R", "O", "S", "RS", "V",
                        "rsi14", "ema9_ma20_slope", "obv_status", "dist_from_ema9_pct", "green_2_confirm", "warning"
                    ]
                    show_cols = [c for c in show_cols if c in sub.columns]
                    st.dataframe(sub[show_cols], use_container_width=True, hide_index=True, height=min(600, 80 + len(sub) * 35))
# =========================================================
# LEADER BRAIN DASHBOARD
# =========================================================
st.markdown("---")
show_leader_brain()                    
# =========================================================
# ACCUMULATION OPPORTUNITY
# =========================================================
# =========================================================
# ACCUMULATION OPPORTUNITY
# =========================================================

st.markdown("---")

render_accumulation_board(scan_df)

# =========================================================
# POSITION GUARDIAN
# =========================================================

st.markdown("---")

render_guardian(scan_df)                    
# =========================================================
# POSITION GUARDIAN
# =========================================================

st.markdown("---")
if show_detail:
    with st.expander("📋 Bảng chi tiết đầy đủ", expanded=True):
        detail_cols = [
            "symbol", "date", "group", "status", "price", "daily_price_before_live", "live_source",
            "is_live_adjusted", "ema9", "ma20", "ema9_ma20_slope", "ema9_ma20_slope_change",
            "rsi14", "rsi_slope", "obv_status", "volume", "vol_ma20", "breakout_ref",
            "dist_from_ema9_pct", "pull_label", "E", "R", "O", "S", "RS", "V", "rs5", "rs10",
            "green_2_confirm", "early_green2", "early_dry_green2", "dryup_ratio_5", "dryup_ratio_10",
            "near_bottom_20_pct", "near_bottom_60_pct", "dist_high20_pct", "body_pct", "total_score", "warning"
        ]
        detail_cols = [c for c in detail_cols if c in scan_df.columns]
        show_compact_table(
            scan_df[detail_cols],
            main_cols=["symbol", "group", "status", "price", "total_score", "rsi14", "ema9_ma20_slope", "obv_status", "dist_from_ema9_pct", "warning"],
            height=620,
            detail_title="🔎 Mở toàn bộ cột chi tiết",
        )

st.markdown("---")
st.caption("Mr.BOT PRO V4.0 | Market → Decision → Learning → Thinking → Evolution | Observe • Learn • Think • Evolve | Khi không chắc, đứng ngoài.")
