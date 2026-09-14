# =========================================================
# POSITION GUARDIAN
# Version : 1.00
#
# Mr.BOT PROJECT
#
# Sprint 1
# ---------------------------------------------------------
# ✓ Watchlist
# ✓ EMA9
# ✓ MA20
# ✓ OBV
# ✓ Green / Yellow / Red Signal
#
# Future
# ---------------------------------------------------------
# V1.1 Holding Days
# V1.2 Cost Price
# V1.3 Profit %
# V2.0 Sell Score
# V3.0 Brain Learning
# =========================================================

import streamlit as st
import pandas as pd
import numpy as np


# =========================================================
# CONFIG
# =========================================================
DEFAULT_WATCHLIST = ""
# =========================================================
# PORTFOLIO MEMORY (user-owned, not keyed by trade_date)
# =========================================================

PORTFOLIO_FILE = "portfolio_symbols.txt"
HOLDINGS_WIDGET_KEY = "position_guardian_watchlist"
HOLDINGS_EDITOR_SHOWN_KEY = "_user_holdings_editor_shown"
HOLDINGS_EDITOR_KEY = "user_holdings_ledger_editor"
MISSING = "—"


def load_portfolio():
    from modules.user_holdings import load_positions

    try:
        return "\n".join(item["symbol"] for item in load_positions())
    except Exception:
        return DEFAULT_WATCHLIST


def save_portfolio(text):
    from modules.user_holdings import (
        load_positions,
        persist_positions_if_changed,
        positions_from_legacy_text,
    )

    persist_positions_if_changed(
        positions_from_legacy_text(text if text is not None else ""),
        load_positions(),
    )


SIGNAL_HOLD = "🟢 GIỮ"
SIGNAL_WARNING = "🟡 CẢNH BÁO"
SIGNAL_SELL = "🔴 BÁN"


# =========================================================
# SAFE VALUE
# =========================================================

def safe_value(row, column, default=np.nan):

    if column not in row.index:
        return default

    value = row[column]

    if pd.isna(value):
        return default

    return value


# =========================================================
# WATCHLIST
# =========================================================

def parse_watchlist(text):

    if text is None:
        return []

    text = text.upper()
    text = text.replace("\n", ",")

    symbols = []

    for item in text.split(","):

        item = item.strip()

        if item == "":
            continue

        if item not in symbols:
            symbols.append(item)

    return symbols


# =========================================================
# HEADER
# =========================================================

def _positions_to_editor_frame(positions):
    from datetime import date as _date

    rows = []
    for item in positions:
        raw_date = item.get("entry_date")
        parsed_date = None
        if raw_date:
            try:
                parsed_date = _date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                parsed_date = None
        rows.append(
            {
                "Mã": item.get("symbol") or "",
                "Giá vốn": item.get("entry_price"),
                "Ngày mua": parsed_date,
            }
        )
    if not rows:
        rows = [{"Mã": "", "Giá vốn": None, "Ngày mua": None}]
    return pd.DataFrame(rows)


def _editor_frame_to_positions(frame):
    from modules.user_holdings import normalize_positions

    if frame is None or frame.empty:
        return []
    rows = []
    for _, raw in frame.iterrows():
        rows.append(
            {
                "symbol": raw.get("Mã"),
                "entry_price": raw.get("Giá vốn"),
                "entry_date": raw.get("Ngày mua"),
            }
        )
    return normalize_positions(rows)


def render_holdings_editor():
    """Editable user ledger. Persist only on explicit Save when canonical JSON differs."""
    from modules.user_holdings import load_positions, persist_positions_if_changed

    st.markdown("---")
    st.subheader("📦 Cổ phiếu đang nắm giữ")
    st.caption(
        "Sổ vị thế do bạn nhập thủ công · Mã / Giá vốn / Ngày mua · "
        "giữ nguyên qua ngày mới · chỉ lưu khi bạn bấm Lưu · "
        "không bị Rotation / BOT / Learning tự thêm hoặc xóa"
    )

    durable = load_positions()
    edited = st.data_editor(
        _positions_to_editor_frame(durable),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Mã": st.column_config.TextColumn("Mã", help="Mã chứng khoán"),
            "Giá vốn": st.column_config.NumberColumn(
                "Giá vốn",
                help="Giá vốn / giá trung bình. Để trống nếu chưa nhập.",
                format="%.2f",
                min_value=0.0,
                step=0.05,
            ),
            "Ngày mua": st.column_config.DateColumn(
                "Ngày mua",
                help="Ngày mua. Để trống nếu chưa nhập.",
                format="YYYY-MM-DD",
            ),
        },
        key=HOLDINGS_EDITOR_KEY,
    )
    save = st.button("Lưu danh sách nắm giữ", type="primary")
    if save:
        incoming = _editor_frame_to_positions(edited)
        _, changed, status = persist_positions_if_changed(incoming, durable)
        if changed:
            st.success("Đã lưu sổ vị thế." + (f" ({status})" if status else ""))
        else:
            st.info("Không có thay đổi để lưu.")
        durable = load_positions()
    st.session_state[HOLDINGS_EDITOR_SHOWN_KEY] = True
    return durable


def guardian_header():
    return render_holdings_editor()


# =========================================================
# BUILD WATCHLIST
# =========================================================

def build_watchlist_df(scan_df, symbols):

    if scan_df is None:
        return pd.DataFrame()

    if len(symbols) == 0:
        return pd.DataFrame()

    df = scan_df.copy()

    df["symbol"] = (
        df["symbol"]
        .astype(str)
        .str.upper()
    )

    df = df[df["symbol"].isin(symbols)]

    df = df.reset_index(drop=True)

    return df


# =========================================================
# FORMAT NUMBER
# =========================================================

def fmt_price(value):
    if value is None or value == "":
        return MISSING
    try:
        if pd.isna(value):
            return MISSING
    except (TypeError, ValueError):
        return MISSING
    return f"{float(value):,.2f}"


def fmt_number(value):
    if value is None or value == "":
        return MISSING
    try:
        if pd.isna(value):
            return MISSING
    except (TypeError, ValueError):
        return MISSING
    return f"{float(value):,.0f}"


def fmt_missing(value):
    if value is None or value == "":
        return MISSING
    try:
        if pd.isna(value):
            return MISSING
    except (TypeError, ValueError):
        pass
    return str(value)


def fmt_pnl(value):
    if value is None:
        return MISSING
    try:
        if pd.isna(value):
            return MISSING
    except (TypeError, ValueError):
        return MISSING
    return f"{float(value):.2f}%"


def fmt_days(value):
    if value is None:
        return MISSING
    return str(int(value))
# =========================================================
# SIGNAL ENGINE
# =========================================================

def generate_signal(row):

    price = safe_value(row, "price")
    ema9 = safe_value(row, "ema9")
    ma20 = safe_value(row, "ma20")

    obv = safe_value(row, "obv")
    obv_ema9 = safe_value(row, "obv_ema9")

    signal = SIGNAL_HOLD
    reason = "Xu hướng khỏe"

    score = 0

    # ----------------------------------------
    # PRICE < EMA9
    # ----------------------------------------

    if (
        pd.notna(price)
        and pd.notna(ema9)
        and price < ema9
    ):

        score += 40

        signal = SIGNAL_WARNING

        reason = "Giá dưới EMA9"

    # ----------------------------------------
    # EMA9 < MA20
    # ----------------------------------------

    if (
        pd.notna(ema9)
        and pd.notna(ma20)
        and ema9 < ma20
    ):

        score += 60

        signal = SIGNAL_SELL

        reason = "EMA9 dưới MA20"

    # ----------------------------------------
    # OBV CONFIRM
    # ----------------------------------------

    if (
        signal == SIGNAL_SELL
        and pd.notna(obv)
        and pd.notna(obv_ema9)
        and obv < obv_ema9
    ):

        score += 20

        reason += " + OBV xác nhận"

    score = min(score, 100)

    return signal, reason, score


# =========================================================
# SELL SCORE COLOR
# =========================================================

def score_color(score):

    if score >= 80:
        return "🔴"

    if score >= 40:
        return "🟡"

    return "🟢"


# =========================================================
# BUILD POSITION TABLE
# =========================================================

def _vn_today():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def _scan_rows_by_symbol(scan_df):
    by_symbol = {}
    if scan_df is None or getattr(scan_df, "empty", True):
        return by_symbol
    if "symbol" not in scan_df.columns:
        return by_symbol
    df = scan_df.copy()
    df["symbol"] = df["symbol"].astype(str).str.upper()
    for _, row in df.iterrows():
        by_symbol[row["symbol"]] = row
    return by_symbol


def build_position_table(scan_df, positions=None, today=None):
    """Join the user ledger with scan_df. Preserve holdings even when scan has no row."""
    from modules.user_holdings import holding_days, load_positions, pnl_pct

    if positions is None:
        positions = load_positions()
    if not positions:
        return pd.DataFrame()

    scan_by_symbol = _scan_rows_by_symbol(scan_df)
    as_of = today or _vn_today()
    rows = []

    for item in positions:
        symbol = item.get("symbol") or ""
        entry_price = item.get("entry_price")
        entry_date = item.get("entry_date")
        scan_row = scan_by_symbol.get(symbol)

        if scan_row is None:
            current_price = None
            signal = MISSING
            reason = MISSING
            sell_score = MISSING
            ema9_s = MISSING
            ma20_s = MISSING
            obv_s = MISSING
        else:
            current_price = safe_value(scan_row, "price")
            signal, reason, score = generate_signal(scan_row)
            sell_score = f"{score_color(score)} {score}"
            ema9_s = fmt_price(safe_value(scan_row, "ema9"))
            ma20_s = fmt_price(safe_value(scan_row, "ma20"))
            obv_s = fmt_number(safe_value(scan_row, "obv"))

        rows.append(
            {
                "Mã": symbol,
                "Giá vốn": fmt_price(entry_price),
                "Ngày mua": fmt_missing(entry_date),
                "Giá hiện tại": fmt_price(current_price),
                "P/L %": fmt_pnl(pnl_pct(current_price, entry_price)),
                "Số ngày giữ": fmt_days(holding_days(entry_date, today=as_of)),
                "EMA9": ema9_s,
                "MA20": ma20_s,
                "OBV": obv_s,
                "Sell Score": sell_score,
                "Trạng thái": signal,
                "Lý do": reason,
            }
        )

    return pd.DataFrame(rows)

# =========================================================
# ROW COLOR
# =========================================================

def row_color(row):

    signal = str(row["Trạng thái"])

    if signal == MISSING:

        return [
            "background-color:#f3f4f6"
        ] * len(row)

    if "🔴" in signal:

        return [
            "background-color:#ffd9d9"
        ] * len(row)

    if "🟡" in signal:

        return [
            "background-color:#fff6cc"
        ] * len(row)

    return [
        "background-color:#ddffdd"
    ] * len(row)


# =========================================================
# SUMMARY
# =========================================================

def render_summary(df):

    total = len(df)
    status = df["Trạng thái"].astype(str)
    known = status[status != MISSING]

    sell = known.str.contains("🔴").sum()
    warning = known.str.contains("🟡").sum()
    hold = known.str.contains("🟢").sum()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Theo dõi", total)

    c2.metric("🟢 Giữ", hold)

    c3.metric("🟡 Cảnh báo", warning)

    c4.metric("🔴 Bán", sell)


# =========================================================
# RENDER
# =========================================================

def render_guardian(scan_df, include_editor: bool = True):
    from modules.user_holdings import load_positions

    if include_editor:
        positions = render_holdings_editor()
    else:
        positions = load_positions()

    if not include_editor:
        st.subheader("🛡️ POSITION GUARDIAN")
        st.caption(
            "Theo dõi trạng thái các cổ phiếu đang nắm giữ · "
            "P/L % và số ngày giữ chỉ là ngữ cảnh hiển thị, không đổi tín hiệu Guardian"
        )

    if not positions:
        st.info("Chưa có cổ phiếu đang nắm giữ.")
        return

    result = build_position_table(scan_df, positions)

    render_summary(result)

    st.dataframe(

        result.style.apply(
            row_color,
            axis=1,
        ),

        use_container_width=True,

        hide_index=True,

    )

    st.caption(

        "🟢 Giữ  |  🟡 Giá dưới EMA9  |  🔴 EMA9 dưới MA20  |  — chưa có dữ liệu quét"

    )



