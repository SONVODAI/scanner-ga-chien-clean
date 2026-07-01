# ==========================================================
# BRAIN V1 - LIFECYCLE ANALYZER
# ==========================================================
# Mr BOT Brain
#
# Nhiệm vụ:
#   1. Đọc toàn bộ snapshot đã lưu
#   2. Ghép vòng đời của từng cổ phiếu
#   3. Phát hiện quá trình tiến hóa
#   4. Sinh lifecycle_history.csv
#   5. Sinh transition_history.csv
#
# Đây là module đầu tiên của Brain.
# Scanner KHÔNG xử lý phần này.
# ==========================================================

from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import os

# ==========================================================
# ROOT
# ==========================================================

ROOT = Path(__file__).resolve().parent.parent

SNAPSHOT_DIR = ROOT / "snapshot"

BRAIN_DATA = ROOT / "brain_data"

BRAIN_DATA.mkdir(exist_ok=True)

# ==========================================================
# OUTPUT
# ==========================================================

LIFECYCLE_HISTORY = BRAIN_DATA / "lifecycle_history.csv"

LIFECYCLE_SUMMARY = BRAIN_DATA / "lifecycle_summary.csv"

TRANSITION_HISTORY = BRAIN_DATA / "transition_history.csv"

# ---------- NEW ----------

BEHAVIOR_DAILY = BRAIN_DATA / "behavior_daily.csv"

BEHAVIOR_PATTERN = BRAIN_DATA / "behavior_pattern.csv"

BEHAVIOR_SUMMARY = BRAIN_DATA / "behavior_summary.csv"

BEHAVIOR_TRANSITION = BRAIN_DATA / "behavior_transition.csv"
# ==========================================================
# THỨ TỰ TIẾN HÓA
# ==========================================================

GROUP_ORDER = {

    "THEO DÕI":0,

    "TÍCH LŨY":1,

    "MUA EARLY":2,

    "PULL VỪA":3,

    "PULL ĐẸP":4,

    "MUA BREAK":5,

    "CP MẠNH":6,

    "GÀ TĂNG TỐC":7,

}



# ==========================================================
# CLASS
# ==========================================================

class LifecycleAnalyzer:

    def __init__(self):

    self.snapshot_files = []

    self.history = pd.DataFrame()

    self.lifecycle = pd.DataFrame()

    self.summary = pd.DataFrame()

    self.transition = pd.DataFrame()

    # ===========================
    # Behavior
    # ===========================

    self.behavior_daily = pd.DataFrame()

    self.behavior_pattern = pd.DataFrame()

    self.behavior_summary = pd.DataFrame()

    self.behavior_transition = pd.DataFrame()
# ==========================================================
# TÌM TOÀN BỘ SNAPSHOT
# ==========================================================

    def load_snapshot_list(self):

        if not SNAPSHOT_DIR.exists():

            print("❌ Không tìm thấy thư mục snapshot")

            return []

        files = sorted(SNAPSHOT_DIR.glob("*.csv"))

        self.snapshot_files = files

        print(f"📂 Tìm thấy {len(files)} snapshot")

        return files



# ==========================================================
# ĐỌC 1 SNAPSHOT
# ==========================================================

    def read_snapshot(self, file):

        try:

            df = pd.read_csv(file)

        except Exception as e:

            print(f"Lỗi đọc {file.name}")

            print(e)

            return None

        cols = [c.lower() for c in df.columns]

        df.columns = cols



        # --------------------------------------------------

        # symbol

        # --------------------------------------------------

        if "symbol" not in df.columns:

            return None



        # --------------------------------------------------

        # group

        # --------------------------------------------------

        group_col = None

        for c in [

            "group",

            "nhóm",

            "nhom"

        ]:

            if c in df.columns:

                group_col = c

                break



        if group_col is None:

            return None



        # --------------------------------------------------

        # date

        # --------------------------------------------------

        date_str = file.stem[:10]



        df = df[["symbol", group_col]].copy()

        df.columns = [

            "symbol",

            "group"

        ]



        df["date"] = date_str



        df["group_rank"] = (

            df["group"]

            .map(GROUP_ORDER)

            .fillna(-1)

        )



        return df



# ==========================================================
# ĐỌC TOÀN BỘ SNAPSHOT
# ==========================================================

    def build_history(self):

        frames = []

        self.load_snapshot_list()



        for file in self.snapshot_files:

            df = self.read_snapshot(file)

            if df is None:

                continue

            frames.append(df)



        if len(frames) == 0:

            print("Không có dữ liệu.")

            return pd.DataFrame()



        history = pd.concat(

            frames,

            ignore_index=True

        )



        history["date"] = pd.to_datetime(

            history["date"]

        )



        history = history.sort_values(

            [

                "symbol",

                "date"

            ]

        ).reset_index(drop=True)



        self.history = history



        print(

            f"Đọc xong {len(history)} dòng lịch sử."

        )
# ==========================================================
# GHÉP VÒNG ĐỜI CỔ PHIẾU
# ==========================================================

    def build_lifecycle(self):

        if self.history.empty:
            self.build_history()

        if self.history.empty:
            return pd.DataFrame()

        rows = []

        for symbol, df in self.history.groupby("symbol"):

            df = df.sort_values("date").reset_index(drop=True)

            first_group = df.iloc[0]["group"]
            current_group = df.iloc[-1]["group"]

            first_date = df.iloc[0]["date"]
            last_date = df.iloc[-1]["date"]

            highest_rank = df["group_rank"].max()

            highest_group = (
                df.loc[
                    df["group_rank"].idxmax(),
                    "group"
                ]
            )

            life_days = len(df)

            rows.append({

                "symbol": symbol,

                "first_date": first_date,

                "last_date": last_date,

                "life_days": life_days,

                "first_group": first_group,

                "current_group": current_group,

                "highest_group": highest_group,

                "highest_rank": highest_rank

            })

        lifecycle = pd.DataFrame(rows)

        lifecycle = lifecycle.sort_values(

            ["highest_rank", "life_days"],

            ascending=False

        ).reset_index(drop=True)

        self.lifecycle = lifecycle

        print(

            f"🧬 Lifecycle: {len(lifecycle)} cổ phiếu"

        )

        return lifecycle



# ==========================================================
# PHÁT HIỆN CHUYỂN TRẠNG THÁI
# ==========================================================

    def build_transition_history(self):

        if self.history.empty:
            self.build_history()

        rows = []
    # ==========================================================
# BUILD BEHAVIOR DAILY
# ==========================================================

    def build_behavior_daily(self):

        if self.history.empty:
            self.build_history()

        if self.history.empty:
            return pd.DataFrame()

        rows = []

        for date, df in self.history.groupby("date"):

            total = len(df)

            early = (df["group"] == "MUA EARLY").sum()

            pull = (
                (df["group"] == "PULL VỪA").sum()
                +
                (df["group"] == "PULL ĐẸP").sum()
            )

            strong = (df["group"] == "CP MẠNH").sum()

            breakout = (df["group"] == "MUA BREAK").sum()

            rocket = (df["group"] == "GÀ TĂNG TỐC").sum()

            rows.append({

                "date": date,

                "total": total,

                "early": early,

                "pull": pull,

                "strong": strong,

                "break": breakout,

                "rocket": rocket,

                "early_ratio": round(early / total * 100, 2) if total else 0,

                "pull_ratio": round(pull / total * 100, 2) if total else 0,

                "strong_ratio": round(strong / total * 100, 2) if total else 0,

            })

        self.behavior_daily = pd.DataFrame(rows)

        return self.behavior_daily



# ==========================================================
# BUILD BEHAVIOR TRANSITION
# ==========================================================

    def build_behavior_transition(self):

        if self.transition.empty:
            self.build_transition_history()

        if self.transition.empty:
            return pd.DataFrame()

        df = self.transition.copy()

        result = (

            df.groupby(

                [

                    "from_group",

                    "to_group"

                ]

            )

            .size()

            .reset_index(name="count")

            .sort_values(

                "count",

                ascending=False

            )

            .reset_index(drop=True)

        )

        self.behavior_transition = result

        return result
        for symbol, df in self.history.groupby("symbol"):

            df = df.sort_values("date").reset_index(drop=True)

            prev_group = None
            prev_rank = None
            prev_date = None

            for _, r in df.iterrows():

                if prev_group is None:

                    prev_group = r.group
                    prev_rank = r.group_rank
                    prev_date = r.date

                    continue

                if r.group != prev_group:

                    rows.append({

                        "symbol": symbol,

                        "date": r.date,

                        "from_group": prev_group,

                        "to_group": r.group,

                        "from_rank": prev_rank,

                        "to_rank": r.group_rank,

                        "step": r.group_rank - prev_rank,

                        "days_after":

                            (r.date - prev_date).days

                    })

                prev_group = r.group
                prev_rank = r.group_rank
                prev_date = r.date

        transition = pd.DataFrame(rows)

        if len(transition):

            transition = transition.sort_values(

                [

                    "date",

                    "symbol"

                ]

            )

        self.transition = transition

        print(

            f"🔄 Transition: {len(transition)} lần chuyển"

        )

        return transition



# ==========================================================
# THỐNG KÊ MỘT CỔ PHIẾU
# ==========================================================

    def get_symbol_history(self, symbol):

        if self.history.empty:
            self.build_history()

        return (

            self.history

            .query("symbol==@symbol")

            .sort_values("date")

            .reset_index(drop=True)

        )



# ==========================================================
# IN THỬ VÒNG ĐỜI
# ==========================================================

    def print_symbol(self, symbol):

        df = self.get_symbol_history(symbol)

        if df.empty:

            print("Không có dữ liệu.")

            return

        print()

        print("=" * 60)

        print(symbol)

        print("=" * 60)

        for _, r in df.iterrows():

            print(

                r.date.strftime("%Y-%m-%d"),

                "->",

                r.group

            )

        print()
# ==========================================================
# LƯU lifecycle_history.csv
# ==========================================================

    def save_lifecycle(self):

        if self.lifecycle.empty:
            self.build_lifecycle()

        self.lifecycle.to_csv(

            LIFECYCLE_HISTORY,

            index=False,

            encoding="utf-8-sig"

        )

        print(

            f"💾 Saved: {LIFECYCLE_HISTORY.name}"

        )



# ==========================================================
# LƯU transition_history.csv
# ==========================================================

    def save_transition(self):

        if self.transition.empty:
            self.build_transition_history()

        self.transition.to_csv(

            TRANSITION_HISTORY,

            index=False,

            encoding="utf-8-sig"

        )

        print(

            f"💾 Saved: {TRANSITION_HISTORY.name}"

        )



# ==========================================================
# TẠO SUMMARY
# ==========================================================

    def build_summary(self):

        if self.history.empty:
            self.build_history()

        rows = []

        for symbol, df in self.history.groupby("symbol"):

            df = df.sort_values("date")

            rows.append({

                "symbol": symbol,

                "days":

                    len(df),

                "first":

                    df.iloc[0]["group"],

                "last":

                    df.iloc[-1]["group"],

                "highest_rank":

                    df["group_rank"].max(),

                "highest_group":

                    df.loc[

                        df["group_rank"].idxmax(),

                        "group"

                    ],

                "transition":

                    max(

                        len(df)-1,

                        0

                    )

            })

        summary = pd.DataFrame(rows)

        summary = summary.sort_values(

            [

                "highest_rank",

                "days"

            ],

            ascending=False

        )

        self.summary = summary

        return summary



# ==========================================================
# LƯU SUMMARY
# ==========================================================

    def save_summary(self):

        if self.summary.empty:

            self.build_summary()
        self.build_behavior_daily()

self.build_behavior_transition()

self.build_behavior_summary()
        self.summary.to_csv(

            LIFECYCLE_SUMMARY,

            index=False,

            encoding="utf-8-sig"

        )

        print(

            f"💾 Saved: {LIFECYCLE_SUMMARY.name}"

        )

# ==========================================================
# SAVE BEHAVIOR
# ==========================================================

    def save_behavior(self):

        if self.behavior_daily.empty:
            self.build_behavior_daily()

        if self.behavior_transition.empty:
            self.build_behavior_transition()

        self.behavior_daily.to_csv(
            BEHAVIOR_DAILY,
            index=False,
            encoding="utf-8-sig"
        )

        self.behavior_transition.to_csv(
            BEHAVIOR_TRANSITION,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"💾 Saved: {BEHAVIOR_DAILY.name}")
        print(f"💾 Saved: {BEHAVIOR_TRANSITION.name}")


# ==========================================================
# BUILD BEHAVIOR SUMMARY
# ==========================================================

    def build_behavior_summary(self):

        if self.behavior_daily.empty:
            self.build_behavior_daily()

        if self.behavior_transition.empty:
            self.build_behavior_transition()

        summary = {}

        if len(self.behavior_daily):

            summary["snapshot_days"] = len(self.behavior_daily)

            summary["avg_early"] = round(
                self.behavior_daily["early"].mean(), 2
            )

            summary["avg_pull"] = round(
                self.behavior_daily["pull"].mean(), 2
            )

            summary["avg_strong"] = round(
                self.behavior_daily["strong"].mean(), 2
            )

        if len(self.behavior_transition):

            summary["transition_count"] = len(
                self.behavior_transition
            )

        self.behavior_summary = pd.DataFrame([summary])

        self.behavior_summary.to_csv(
            BEHAVIOR_SUMMARY,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"💾 Saved: {BEHAVIOR_SUMMARY.name}")

        return self.behavior_summary

# ==========================================================
# EXPORT TOÀN BỘ
# ==========================================================

    def export_all(self):

    self.save_lifecycle()

    self.save_transition()

    self.save_summary()

    self.save_behavior()

    print()

    print("✅ Export hoàn tất.")

    print()


# ==========================================================
# CHẠY TOÀN BỘ ENGINE
# ==========================================================

    def run(self):

        print()

        print("="*70)

        print("🧠 BRAIN : LIFECYCLE ANALYZER")

        print("="*70)

        print()

        self.build_history()

        self.build_lifecycle()

        self.build_transition_history()

        self.build_summary()

        self.export_all()

        print()

        print("🧠 Lifecycle Analyzer Finished")

        print()



# ==========================================================
# TEST ĐỘC LẬP
# ==========================================================

if __name__ == "__main__":

    brain = LifecycleAnalyzer()

    brain.run()

        return history
