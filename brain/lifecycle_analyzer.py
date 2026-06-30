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
# THƯ MỤC
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



        return history
