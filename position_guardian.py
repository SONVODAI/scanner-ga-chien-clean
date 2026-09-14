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
import re


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
HOLDINGS_EDITOR_KEY = "user_holdings_ledger_editor_ddmm"
ENTRY_DATE_COLUMN_FORMAT = "DD/MM/YYYY"
ENTRY_DATE_TEXT_PATTERN = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
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
    rows = []
    for item in positions:
        rows.append(
            {
                "Mã": item.get("symbol") or "",
                "Giá vốn": item.get("entry_price"),
                "Ngày mua": format_entry_date_display(item.get("entry_date")) or "",
            }
        )
    if not rows:
        rows = [{"Mã": "", "Giá vốn": None, "Ngày mua": ""}]
    return pd.DataFrame(rows)


def parse_editor_entry_date(value):
    """Parse a user-facing DD/MM/YYYY cell.

    Returns (iso_or_none, invalid).
    Blank -> (None, False). Strict DD/MM/YYYY only.
    """
    from datetime import date as _date

    if value is None:
        return None, False
    try:
        if pd.isna(value):
            return None, False
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return None, False
    match = ENTRY_DATE_TEXT_PATTERN.fullmatch(text)
    if not match:
        return None, True
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        parsed = _date(year, month, day)
    except ValueError:
        return None, True
    return parsed.isoformat(), False


def parse_editor_frame(frame):
    """Convert the ledger editor to ISO positions. Collect invalid-date errors."""
    from modules.user_holdings import normalize_positions

    if frame is None or frame.empty:
        return [], []
    rows = []
    errors = []
    for _, raw in frame.iterrows():
        iso_date, invalid = parse_editor_entry_date(raw.get("Ngày mua"))
        symbol = str(raw.get("Mã") or "").strip().upper()
        if invalid:
            label = symbol or "mã trống"
            errors.append(
                f"Ngày mua của {label} không hợp lệ. "
                "Vui lòng nhập theo DD/MM/YYYY, ví dụ 10/09/2026."
            )
        rows.append(
            {
                "symbol": raw.get("Mã"),
                "entry_price": raw.get("Giá vốn"),
                "entry_date": iso_date,
            }
        )
    return normalize_positions(rows), errors


def _editor_frame_to_positions(frame):
    positions, errors = parse_editor_frame(frame)
    if errors:
        return []
    return positions


def format_entry_date_display(value):
    """User-facing DD/MM/YYYY. Durable storage stays ISO YYYY-MM-DD."""
    from datetime import date as _date
    from datetime import datetime as _datetime

    if value is None or value == "":
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, _date) and not isinstance(value, _datetime):
        day = value
    else:
        text = str(value).strip()
        if ENTRY_DATE_TEXT_PATTERN.fullmatch(text):
            return text
        try:
            day = _date.fromisoformat(text[:10])
        except ValueError:
            return ""
    return day.strftime("%d/%m/%Y")


def future_entry_date_messages(positions, today=None):
    """Reject entry_date after Vietnam today. Null dates are allowed."""
    from datetime import date as _date
    from datetime import datetime as _datetime

    as_of = today or _vn_today()
    messages = []
    for item in positions or []:
        raw = item.get("entry_date")
        if raw is None or raw == "":
            continue
        try:
            if pd.isna(raw):
                continue
        except (TypeError, ValueError):
            pass
        try:
            if isinstance(raw, _date) and not isinstance(raw, _datetime):
                day = raw
            else:
                day = _date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if day > as_of:
            symbol = item.get("symbol") or ""
            shown = format_entry_date_display(day)
            messages.append(
                f"Ngày mua của {symbol} ({shown}) nằm trong tương lai. Vui lòng kiểm tra lại."
            )
    return messages


def commit_editor_positions(
    incoming,
    durable,
    *,
    today=None,
    github_writer=None,
    parse_errors=None,
):
    """Validate then persist. Invalid or future dates block the whole save."""
    from modules.user_holdings import persist_positions_if_changed

    if parse_errors:
        return durable, False, "INVALID_DATE", list(parse_errors)
    errors = future_entry_date_messages(incoming, today=today)
    if errors:
        return durable, False, "FUTURE_DATE", errors
    saved, changed, status = persist_positions_if_changed(
        incoming,
        durable,
        github_writer=github_writer,
    )
    return saved, changed, status, []


def render_holdings_editor():
    """Editable user ledger. Persist only on explicit Save when canonical JSON differs."""
    from modules.user_holdings import load_positions

    st.markdown("---")
    st.subheader("📦 Cổ phiếu đang nắm giữ")
    st.caption(
        "Sổ vị thế do bạn nhập thủ công · Mã / Giá vốn / Ngày mua · "
        "Ngày mua: DD/MM/YYYY, ví dụ 10/09/2026 · "
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
            "Ngày mua": st.column_config.TextColumn(
                "Ngày mua",
                help="DD/MM/YYYY. Ví dụ: 10/09/2026. Để trống nếu chưa nhập.",
                max_chars=10,
            ),
        },
        key=HOLDINGS_EDITOR_KEY,
    )
    save = st.button("Lưu danh sách nắm giữ", type="primary")
    if save:
        incoming, parse_errors = parse_editor_frame(edited)
        durable, changed, status, errors = commit_editor_positions(
            incoming,
            durable,
            parse_errors=parse_errors,
        )
        if errors:
            for message in errors:
                st.error(message)
        elif changed:
            st.success("Đã lưu sổ vị thế." + (f" ({status})" if status else ""))
        else:
            st.info("Không có thay đổi để lưu.")
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



