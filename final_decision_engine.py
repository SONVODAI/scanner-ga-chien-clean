# =========================================================
# MR.BOT FINAL DECISION ENGINE V2
# =========================================================

import math

import pandas as pd
import numpy as np
import re


MAX_TOP = 10
MAX_PER_SECTOR = 3

# Upstream Buy Elite (STEP 2) already applies ExperienceAdjustment to EliteScore/WinProb.
# Final Decision must NOT add ExperienceAdjustment again.
LEARNING_AUDIT_COLS = (
    "EliteScoreBase",
    "ExperienceAdjustment",
    "ExperienceSamples",
    "LearnedWinRate",
    "ContinuationScore",
    "MatchedPattern",
    "MatchedMarketContext",
    "ContextMatchMode",
    "LearningStatus",
)


# =========================================================
# HELPERS
# =========================================================

def _num(x, default=0.0):
    try:
        if pd.isna(x):
            return default

        s = str(x)
        s = s.replace("%", "")
        s = s.replace(",", ".")
        s = s.strip()

        m = re.search(r"-?\d+(\.\d+)?", s)
        if not m:
            return default

        return float(m.group())
    except Exception:
        return default


def _pct(x):
    v = _num(x, 0.0)

    if 0 < v <= 1:
        v *= 100

    return max(0, min(100, v))


def _trust_score(x):
    s = str(x).upper()

    if "RẤT CAO" in s:
        return 95
    if "CAO" in s:
        return 85
    if "TRUNG" in s or "TB" in s:
        return 65
    if "THẤP" in s:
        return 35

    return _pct(x)


def _consensus_score(x):
    s = str(x).upper()

    m = re.search(r"(\d+)\s*/\s*(\d+)", s)
    if m:
        a = float(m.group(1))
        b = float(m.group(2))
        if b == 0:
            return 0
        return max(0, min(100, a / b * 100))

    if "✅" in s:
        return 100

    if "MẠNH" in s:
        return 85

    return _pct(x)


def _star(score):
    if score >= 92:
        return "★★★★★"
    if score >= 85:
        return "★★★★☆"
    if score >= 75:
        return "★★★☆☆"
    if score >= 65:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def _rank_icon(i):
    if i == 1:
        return "🥇"
    if i == 2:
        return "🥈"
    if i == 3:
        return "🥉"
    return str(i)


def _safe_str(x):
    if pd.isna(x):
        return ""
    return str(x)


# =========================================================
# DISPLAY FORMATTING (presentation layer only)
# =========================================================

FINAL_DECISION_TEXT_COLS = frozenset({
    "#",
    "⭐",
    "MÃ",
    "KẾT LUẬN",
    "Lý do chọn",
    "NHÓM",
    "VÙNG MUA ELITE",
    "NAV ELITE",
    "ĐỘ TIN CẬY",
    "ĐỒNG THUẬN",
    "LÝ DO ELITE",
    "RỦI RO",
    "MatchedPattern",
    "MatchedMarketContext",
    "LearningStatus",
})

FINAL_DECISION_INT_COLS = frozenset({
    "ExperienceSamples",
    "GIÁ",
})

FINAL_DECISION_SCORE_COLS = frozenset({
    "DecisionScoreBase",
    "DecisionScoreLearningDelta",
    "EliteScore",
    "EliteScoreBase",
    "ExperienceAdjustment",
    "LearnedWinRate",
    "ContinuationScore",
})


def format_display_number(value, max_decimals=2, prefer_int=True):
    """Format a numeric value for UI/export only; does not alter calculation inputs."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, float) and (math.isnan(value) or not math.isfinite(value)):
        return ""

    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "-"}:
            return ""
        pct_suffix = text.endswith("%")
        raw = text[:-1].strip() if pct_suffix else text
        try:
            number = float(raw.replace(",", ""))
        except ValueError:
            return value
        formatted = _format_display_float(number, max_decimals, prefer_int)
        return f"{formatted}%" if pct_suffix else formatted

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if math.isnan(number) or not math.isfinite(number):
        return ""

    return _format_display_float(number, max_decimals, prefer_int)


def _format_display_float(number, max_decimals, prefer_int):
    if prefer_int and abs(number - round(number)) < 1e-4:
        return str(int(round(number)))

    rounded = round(number, max_decimals)
    if prefer_int and abs(rounded - round(rounded)) < 1e-4:
        return str(int(round(rounded)))

    text = f"{rounded:.{max_decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _format_winprob_display(value):
    formatted = format_display_number(value, max_decimals=0, prefer_int=True)
    if not formatted:
        return ""
    if formatted.endswith("%"):
        return formatted
    return f"{formatted}%"


def format_final_decision_for_display(df):
    """Return a presentation copy; upstream numeric precision is unchanged."""
    if df is None or df.empty:
        return df

    out = df.copy()

    for col in out.columns:
        if col == "DecisionScore":
            continue
        if col == "WinProb":
            out[col] = out[col].map(_format_winprob_display)
            continue
        if col in FINAL_DECISION_TEXT_COLS:
            continue
        if col in FINAL_DECISION_INT_COLS:
            out[col] = out[col].map(
                lambda v: format_display_number(v, max_decimals=0, prefer_int=True)
            )
            continue
        if col in FINAL_DECISION_SCORE_COLS:
            out[col] = out[col].map(
                lambda v: format_display_number(v, max_decimals=2, prefer_int=True)
            )

    return out


def _has_col(df, col):
    return isinstance(df, pd.DataFrame) and col in df.columns


# =========================================================
# CORE FILTER
# =========================================================

def _filter_buy_only(df):
    if df is None or df.empty:
        return pd.DataFrame()

    if "KẾT LUẬN" not in df.columns:
        return pd.DataFrame()

    out = df.copy()

    action = out["KẾT LUẬN"].astype(str).str.upper().str.strip()

    allow_mask = (
        action.str.contains("MUA")
        & ~action.str.contains("CHƯA")
        & ~action.str.contains("WATCH")
        & ~action.str.contains("THEO DÕI")
        & ~action.str.contains("KHÔNG")
    )

    out = out[allow_mask].copy().reset_index(drop=True)

    return out


def _green_symbols(green_red_df):
    if green_red_df is None or green_red_df.empty:
        return set()

    if "MÃ" not in green_red_df.columns:
        return set()

    return set(
        green_red_df["MÃ"]
        .astype(str)
        .str.upper()
        .str.strip()
        .tolist()
    )


# =========================================================
# SECTOR LIMIT
# =========================================================

def _apply_sector_limit(df, max_top=MAX_TOP, max_per_sector=MAX_PER_SECTOR):
    if df is None or df.empty:
        return pd.DataFrame()

    sector_col = "NGÀNH" if "NGÀNH" in df.columns else None

    if sector_col is None:
        sector_col = "NHÓM" if "NHÓM" in df.columns else None

    selected = []
    counter = {}

    for _, row in df.iterrows():
        sector = _safe_str(row.get(sector_col, "Khác")) if sector_col else "Khác"

        if counter.get(sector, 0) >= max_per_sector:
            continue

        selected.append(row)
        counter[sector] = counter.get(sector, 0) + 1

        if len(selected) >= max_top:
            break

    if not selected:
        return pd.DataFrame()

    return pd.DataFrame(selected).reset_index(drop=True)


# =========================================================
# DECISION SCORE
# =========================================================

def _build_score(df, green_set):
    out = df.copy()

    # Learning influence enters here exactly once: via upstream EliteScore / WinProb
    # (already adjusted in Buy Elite STEP 2). No second ExperienceAdjustment term.
    out["_elite_score"] = out["EliteScore"].apply(_pct) if "EliteScore" in out.columns else 0
    out["_winprob"] = out["WinProb"].apply(_pct) if "WinProb" in out.columns else 0
    out["_trust"] = out["ĐỘ TIN CẬY"].apply(_trust_score) if "ĐỘ TIN CẬY" in out.columns else 0
    out["_consensus"] = out["ĐỒNG THUẬN"].apply(_consensus_score) if "ĐỒNG THUẬN" in out.columns else 0

    if "MÃ" in out.columns:
        out["_green"] = out["MÃ"].astype(str).str.upper().str.strip().apply(
            lambda x: 100 if x in green_set else 0
        )
    else:
        out["_green"] = 0

    out["DecisionScore"] = (
        out["_elite_score"] * 0.35
        + out["_winprob"] * 0.25
        + out["_trust"] * 0.20
        + out["_consensus"] * 0.10
        + out["_green"] * 0.10
    ).round(2)

    if "EliteScoreBase" in out.columns:
        out["_elite_score_base"] = out["EliteScoreBase"].apply(_pct)
        elite_learning_delta = (out["_elite_score"] - out["_elite_score_base"]).round(2)
        # WinProb upstream already embeds learning via EliteScore * 0.55 (STEP 2).
        winprob_learning_delta = elite_learning_delta * 0.55
        out["_winprob_base"] = (out["_winprob"] - winprob_learning_delta).clip(0, 100)
        out["DecisionScoreBase"] = (
            out["_elite_score_base"] * 0.35
            + out["_winprob_base"] * 0.25
            + out["_trust"] * 0.20
            + out["_consensus"] * 0.10
            + out["_green"] * 0.10
        ).round(2)
        out["DecisionScoreLearningDelta"] = (
            out["DecisionScore"] - out["DecisionScoreBase"]
        ).round(2)

    out["⭐"] = out["DecisionScore"].apply(_star)

    return out


# =========================================================
# REASON
# =========================================================

def _reason(row):
    reasons = []

    if row.get("_elite_score", 0) >= 85:
        reasons.append("Elite mạnh")

    if row.get("_winprob", 0) >= 70:
        reasons.append("WinProb tốt")

    if row.get("_trust", 0) >= 80:
        reasons.append("Tin cậy cao")

    if row.get("_consensus", 0) >= 75:
        reasons.append("Đồng thuận tốt")

    if row.get("_green", 0) > 0:
        reasons.append("Có mặt bảng Xanh")

    exp_adj = _num(row.get("ExperienceAdjustment", 0))
    if exp_adj > 0:
        reasons.append(f"Learning +{exp_adj:.1f} (Buy Elite)")
    elif exp_adj < 0:
        reasons.append(f"Learning {exp_adj:.1f} (Buy Elite)")

    learning_status = _safe_str(row.get("LearningStatus", "")).strip()
    if learning_status and learning_status not in ("READY_FOR_CONNECTION", ""):
        reasons.append(f"LearningStatus={learning_status}")

    if not reasons:
        reasons.append("Đủ chuẩn MUA")

    return " • ".join(reasons)


# =========================================================
# PUBLIC API
# =========================================================

def build_final_decision(
    buy_elite_df,
    green_red_df=None,
    max_top=MAX_TOP,
    max_per_sector=MAX_PER_SECTOR,
):
    buy_df = _filter_buy_only(buy_elite_df)

    if buy_df.empty:
        return pd.DataFrame(), "Hôm nay không có cổ phiếu đủ chuẩn MUA."

    green_set = _green_symbols(green_red_df)

    scored = _build_score(buy_df, green_set)

    scored["Lý do chọn"] = scored.apply(_reason, axis=1)

    scored = scored.sort_values(
        by=["DecisionScore"],
        ascending=False,
    ).reset_index(drop=True)

    final = _apply_sector_limit(
        scored,
        max_top=max_top,
        max_per_sector=max_per_sector,
    )

    if final.empty:
        return pd.DataFrame(), "Không còn cổ phiếu sau khi áp dụng giới hạn ngành."

    final = final.reset_index(drop=True)
    final.insert(0, "#", [_rank_icon(i + 1) for i in range(len(final))])

    cols = [
        "#",
        "⭐",
        "MÃ",
        "DecisionScore",
        "DecisionScoreBase",
        "DecisionScoreLearningDelta",
        "KẾT LUẬN",
        "Lý do chọn",
        "NHÓM",
        "GIÁ",
        "VÙNG MUA ELITE",
        "NAV ELITE",
        "EliteScore",
        "WinProb",
        "ĐỘ TIN CẬY",
        "ĐỒNG THUẬN",
        "LÝ DO ELITE",
        "RỦI RO",
        *LEARNING_AUDIT_COLS,
    ]

    cols = [c for c in cols if c in final.columns]

    final = final[cols].copy()
    final["DecisionScore"] = pd.to_numeric(final["DecisionScore"], errors="coerce")

    note = f"Tìm được {len(final)} cổ phiếu tinh hoa đủ chuẩn MUA."

    return final, note


def style_final_decision(df):
    if df is None or df.empty:
        return df

    if "DecisionScore" not in df.columns:
        return df

    return (
        df.style
        .background_gradient(
            subset=["DecisionScore"],
            cmap="YlGn",
        )
        .format(
            {
                "DecisionScore": lambda v: format_display_number(
                    v, max_decimals=2, prefer_int=True
                ),
            },
            na_rep="",
        )
    )
