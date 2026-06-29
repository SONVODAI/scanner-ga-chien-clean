# =========================================================
# MR.BOT V21 - BRAIN MANAGER
# File: brainmanager.py
#
# Nhiệm vụ:
#   - Là bộ nhớ trung tâm cho Mr.Bot
#   - Cung cấp API thống nhất:
#       brain.remember(...)
#       brain.recall(...)
#       brain.forget(...)
#       brain.search(...)
#   - Phục vụ Learning Engine / Thinking Engine / Decision Engine
# =========================================================

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# =========================================================
# DEFAULT PATH
# =========================================================

DEFAULT_BRAIN_DIR = Path("data") / "brain"


def bm_now():
    return datetime.now(VN_TZ)


def bm_today_str():
    return bm_now().strftime("%Y-%m-%d")


def safe_df(data):
    """
    Ép mọi kiểu dữ liệu phổ biến về DataFrame.
    """

    if data is None:
        return pd.DataFrame()

    if isinstance(data, pd.DataFrame):
        return data.copy()

    if isinstance(data, dict):
        return pd.DataFrame([data])

    if isinstance(data, list):
        return pd.DataFrame(data)

    return pd.DataFrame()


def normalize_table_name(table):
    name = str(table).strip()
    name = name.replace(" ", "_")
    name = name.replace("/", "_")
    name = name.replace("\\", "_")
    return name


class BrainManager:
    """
    BrainManager là bộ nhớ trung tâm.

    Các module khác chỉ cần biết:
        brain.remember(...)
        brain.recall(...)

    Không cần biết dữ liệu đang nằm ở CSV, SQLite hay GitHub.
    """

    def __init__(self, brain_dir=DEFAULT_BRAIN_DIR):
        self.brain_dir = Path(brain_dir)
        self.brain_dir.mkdir(parents=True, exist_ok=True)

        self.cache = {}

    # -----------------------------------------------------
    # PATH
    # -----------------------------------------------------

    def table_path(self, table):
        table = normalize_table_name(table)
        return self.brain_dir / f"{table}.csv"

    # -----------------------------------------------------
    # RECALL
    # -----------------------------------------------------

    def recall(self, table, prefer_github=True):
        """
        Đọc một bảng từ Brain.

        Parameters
        ----------
        table : str
            Tên bảng cần đọc.

        Returns
        -------
        DataFrame
        """

        table = normalize_table_name(table)

        if table in self.cache:
            return self.cache[table].copy()

        path = self.table_path(table)

        if not path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_csv(path)

            self.cache[table] = df.copy()

            return df

        except Exception as e:
            print(f"BrainManager recall error [{table}]: {e}")
            return pd.DataFrame()

    # -----------------------------------------------------
    # REMEMBER
    # -----------------------------------------------------

    def remember(
        self,
        table,
        data,
        key=None,
        keep_days=None,
        date_col="date",
        sort_by=None,
        sync_github=True,
        prefer_github=True,
    ):
        """
        Ghi dữ liệu vào Brain.

        Hàm này được thiết kế để khớp trực tiếp với Learning Engine hiện tại.

        Parameters
        ----------
        table : str
            Tên bảng.
        data : DataFrame / dict / list
            Dữ liệu mới cần lưu.
        key : list[str] / str / None
            Cột dùng để chống trùng.
        keep_days : int / None
            Giữ dữ liệu trong bao nhiêu ngày.
        date_col : str
            Cột ngày.
        sort_by : list[str] / str / None
            Cột dùng để sắp xếp.
        sync_github : bool
            Để sẵn cho giai đoạn sync GitHub.
        prefer_github : bool
            Để sẵn cho giai đoạn đọc ưu tiên GitHub.

        Returns
        -------
        saved_df, status
        """

        table = normalize_table_name(table)

        new_df = safe_df(data)

        if new_df.empty:
            old = self.recall(table, prefer_github=prefer_github)
            return old, "NO_NEW_DATA"

        old_df = self.recall(table, prefer_github=prefer_github)

        if old_df is None or old_df.empty:
            combined = new_df.copy()
        else:
            combined = pd.concat(
                [old_df, new_df],
                ignore_index=True
            )

        # ------------------------------
        # Deduplicate
        # ------------------------------

        if key is not None:
            if isinstance(key, str):
                key = [key]

            existing_keys = [
                c for c in key
                if c in combined.columns
            ]

            if existing_keys:
                combined = combined.drop_duplicates(
                    subset=existing_keys,
                    keep="last"
                )

        # ------------------------------
        # Keep recent days
        # ------------------------------

        if keep_days is not None:
            combined = self.keep_recent_days(
                combined,
                keep_days=keep_days,
                date_col=date_col
            )

        # ------------------------------
        # Sort
        # ------------------------------

        if sort_by is not None:
            if isinstance(sort_by, str):
                sort_by = [sort_by]

            sort_cols = [
                c for c in sort_by
                if c in combined.columns
            ]

            if sort_cols:
                combined = combined.sort_values(
                    sort_cols
                ).reset_index(drop=True)

        # ------------------------------
        # Save
        # ------------------------------

        status = self.save_table(table, combined)

        # ------------------------------
        # Optional GitHub sync stub
        # ------------------------------

        if sync_github:
            self.try_sync_github(table)

        return combined, status

    # -----------------------------------------------------
    # SAVE TABLE
    # -----------------------------------------------------

    def save_table(self, table, df):
        table = normalize_table_name(table)

        path = self.table_path(table)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            df.to_csv(
                path,
                index=False,
                encoding="utf-8-sig"
            )

            self.cache[table] = df.copy()

            return "SAVED"

        except Exception as e:
            print(f"BrainManager save error [{table}]: {e}")
            return "SAVE_ERROR"

    # -----------------------------------------------------
    # KEEP RECENT DAYS
    # -----------------------------------------------------

    def keep_recent_days(self, df, keep_days=360, date_col="date"):
        if df is None or df.empty:
            return pd.DataFrame()

        if date_col not in df.columns:
            return df

        out = df.copy()

        dates = pd.to_datetime(
            out[date_col],
            errors="coerce"
        )

        if dates.dropna().empty:
            return out

        max_date = dates.max()
        min_date = max_date - pd.Timedelta(days=keep_days)

        out = out[dates >= min_date].copy()

        return out.reset_index(drop=True)

    # -----------------------------------------------------
    # FORGET
    # -----------------------------------------------------

    def forget(self, table):
        """
        Xóa hẳn một bảng khỏi Brain.
        """

        table = normalize_table_name(table)
        path = self.table_path(table)

        try:
            if path.exists():
                path.unlink()

            if table in self.cache:
                del self.cache[table]

            return "FORGOTTEN"

        except Exception as e:
            print(f"BrainManager forget error [{table}]: {e}")
            return "FORGET_ERROR"

    # -----------------------------------------------------
    # LIST TABLES
    # -----------------------------------------------------

    def list_tables(self):
        files = sorted(self.brain_dir.glob("*.csv"))
        return [f.stem for f in files]

    # -----------------------------------------------------
    # TAIL
    # -----------------------------------------------------

    def tail(self, table, n=20):
        df = self.recall(table)

        if df.empty:
            return df

        return df.tail(n)

    # -----------------------------------------------------
    # LATEST
    # -----------------------------------------------------

    def latest(self, table, date_col="date"):
        df = self.recall(table)

        if df.empty:
            return pd.DataFrame()

        if date_col not in df.columns:
            return df.tail(1)

        out = df.copy()
        out["_bm_date"] = pd.to_datetime(
            out[date_col],
            errors="coerce"
        )

        out = out.sort_values("_bm_date")
        out = out.drop(columns=["_bm_date"])

        return out.tail(1)

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    def search(self, table, keyword, columns=None):
        df = self.recall(table)

        if df.empty:
            return df

        keyword = str(keyword).lower()

        if columns is None:
            columns = df.columns

        columns = [
            c for c in columns
            if c in df.columns
        ]

        if not columns:
            return pd.DataFrame()

        mask = pd.Series(False, index=df.index)

        for c in columns:
            mask = mask | df[c].astype(str).str.lower().str.contains(
                keyword,
                na=False
            )

        return df[mask].copy()

    # -----------------------------------------------------
    # BUILD CONTEXT
    # -----------------------------------------------------

    def build_context(
        self,
        symbol=None,
        latest_snapshot=None,
        max_rows=10
    ):
        """
        Tạo context tóm tắt cho Thinking Engine / Decision Engine sau này.
        """

        context = {}

        # Market Snapshot
        market = self.recall("market_snapshot")
        if not market.empty:
            context["latest_market"] = market.tail(1).to_dict("records")

        # Learning
        learning = self.recall("bot_experience_learning")
        if not learning.empty:
            context["recent_lessons"] = learning.tail(max_rows).to_dict("records")

        # Symbol-specific
        if symbol:
            symbol = str(symbol).upper()

            evo = self.recall("group_evolution_history")
            if not evo.empty and "symbol" in evo.columns:
                sub = evo[
                    evo["symbol"].astype(str).str.upper() == symbol
                ].tail(max_rows)

                context["symbol_evolution"] = sub.to_dict("records")

            elite = self.recall("buy_elite_learning_history")
            if not elite.empty and "symbol" in elite.columns:
                sub = elite[
                    elite["symbol"].astype(str).str.upper() == symbol
                ].tail(max_rows)

                context["symbol_buy_history"] = sub.to_dict("records")

        if latest_snapshot is not None:
            context["latest_snapshot_input"] = latest_snapshot

        return context

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    def summary(self):
        rows = []

        for table in self.list_tables():
            df = self.recall(table)

            rows.append({
                "table": table,
                "rows": len(df),
                "cols": len(df.columns) if not df.empty else 0,
            })

        return pd.DataFrame(rows)

    # -----------------------------------------------------
    # CLEAR CACHE
    # -----------------------------------------------------

    def clear_cache(self):
        self.cache = {}

    # -----------------------------------------------------
    # GITHUB SYNC STUB
    # -----------------------------------------------------

    def try_sync_github(self, table):
        """
        Để mở sẵn cho giai đoạn sau.

        Nếu app.py của anh đã có hàm sync GitHub riêng,
        sau này mình chỉ cần nối vào đây.
        Hiện tại hàm này không làm gì để tránh gây lỗi.
        """

        return "SKIPPED"


# =========================================================
# SINGLETON
# =========================================================

_GLOBAL_BRAIN = None


def get_brain(brain_dir=DEFAULT_BRAIN_DIR):
    global _GLOBAL_BRAIN

    if _GLOBAL_BRAIN is None:
        _GLOBAL_BRAIN = BrainManager(brain_dir=brain_dir)

    return _GLOBAL_BRAIN


# =========================================================
# QUICK TEST
# =========================================================

if __name__ == "__main__":

    brain = get_brain()

    test_df = pd.DataFrame([
        {
            "date": bm_today_str(),
            "symbol": "TEST",
            "group": "MUA EARLY",
            "score": 100,
        }
    ])

    saved, status = brain.remember(
        table="brain_test",
        data=test_df,
        key=["date", "symbol"],
        keep_days=30,
        date_col="date",
        sort_by=["date", "symbol"],
        sync_github=False,
    )

    print(status)
    print(saved.tail())
    print(brain.summary())
