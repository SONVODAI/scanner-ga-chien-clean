# =========================================================
# MR.BOT V21 - BRAIN STORAGE ENGINE V1
# File: brain_storage.py
# Mục tiêu:
#   1) Một cổng lưu/đọc dữ liệu duy nhất cho Mr.Bot
#   2) Hỗ trợ CSV local + GitHub storage
#   3) Tự merge, deduplicate, giữ lịch sử N ngày
#   4) Không phụ thuộc thuật toán scanner
# =========================================================

import os
import json
import base64
from io import StringIO
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def brain_now():
    return datetime.now(VN_TZ)


def brain_time_str(fmt="%Y-%m-%d %H:%M:%S"):
    return brain_now().strftime(fmt)


TEXT_COL_HINTS = {
    "date", "time", "created_at", "updated_at", "session", "session_slot",
    "symbol", "group", "status", "source", "note", "message", "reason",
    "regime", "market_status", "market_action", "forecast_text",
    "table", "version", "stage", "error",
}

NUMERIC_COL_HINTS = {
    "rank", "score", "price", "volume", "vol_ma20", "market_real",
    "market_live", "market_forecast", "rsi", "rsi14", "slope",
    "ema9_ma20_slope", "dist_ema9", "dist_from_ema9_pct",
    "total_score", "persistence", "evolution", "recent_change",
    "storm", "storm_score", "winrate", "avg_return", "count",
}


def brain_guard_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    out = df.copy()

    for col in out.columns:
        if col in TEXT_COL_HINTS:
            out[col] = out[col].astype("object")
            out[col] = out[col].where(pd.notna(out[col]), "")
        elif col in NUMERIC_COL_HINTS:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    return out


class BrainStorage:
    def __init__(
        self,
        repo_owner: str = "",
        repo_name: str = "",
        token_getter=None,
        base_dir: str = ".",
        github_dir: str = "",
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.token_getter = token_getter
        self.base_dir = base_dir
        self.github_dir = github_dir.strip("/")

    # =====================================================
    # CORE PATH
    # =====================================================
    def local_path(self, table: str) -> str:
        if table.endswith(".csv") or table.endswith(".json"):
            filename = table
        else:
            filename = f"{table}.csv"
        return os.path.join(self.base_dir, filename)

    def github_path(self, table: str) -> str:
        if table.endswith(".csv") or table.endswith(".json"):
            filename = table
        else:
            filename = f"{table}.csv"

        if self.github_dir:
            return f"{self.github_dir}/{filename}"
        return filename

    def token(self):
        if callable(self.token_getter):
            try:
                return self.token_getter()
            except Exception:
                return None
        return None

    def has_github(self) -> bool:
        return bool(self.repo_owner and self.repo_name and self.token())

    # =====================================================
    # GITHUB LOW LEVEL
    # =====================================================
    def github_url(self, table: str) -> str:
        path = self.github_path(table)
        return (
            f"https://api.github.com/repos/"
            f"{self.repo_owner}/{self.repo_name}/contents/{path}"
        )

    def github_headers(self):
        token = self.token()
        if not token:
            return {}
        return {"Authorization": f"token {token}"}

    def read_text_from_github(self, table: str) -> tuple[str, str]:
        if not self.has_github():
            return "", "NO_GITHUB"

        try:
            r = requests.get(
                self.github_url(table),
                headers=self.github_headers(),
                timeout=12,
            )

            if r.status_code == 200:
                content = r.json().get("content", "")
                decoded = base64.b64decode(content).decode("utf-8")
                return decoded, "GITHUB_OK"

            if r.status_code == 404:
                return "", "GITHUB_NOT_FOUND"

            return "", f"GITHUB_READ_FAIL_{r.status_code}"

        except Exception as e:
            return "", f"GITHUB_READ_ERROR_{e}"

    def write_text_to_github(self, table: str, text: str, message: str = "") -> str:
        if not self.has_github():
            return "NO_GITHUB"

        try:
            url = self.github_url(table)
            headers = self.github_headers()

            sha = None
            get_r = requests.get(url, headers=headers, timeout=12)
            if get_r.status_code == 200:
                sha = get_r.json().get("sha")

            encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")

            payload = {
                "message": message or f"Brain update {table} {brain_time_str()}",
                "content": encoded,
            }

            if sha:
                payload["sha"] = sha

            put_r = requests.put(
                url,
                headers=headers,
                json=payload,
                timeout=20,
            )

            if put_r.status_code in [200, 201]:
                return "GITHUB_OK"

            return f"GITHUB_WRITE_FAIL_{put_r.status_code}"

        except Exception as e:
            return f"GITHUB_WRITE_ERROR_{e}"

    # =====================================================
    # CSV LOAD / SAVE
    # =====================================================
    def load_csv(self, table: str, prefer_github: bool = True) -> pd.DataFrame:
        if prefer_github:
            text, status = self.read_text_from_github(table)
            if text:
                try:
                    return brain_guard_dataframe(pd.read_csv(StringIO(text)))
                except Exception:
                    pass

        path = self.local_path(table)
        try:
            if os.path.exists(path):
                return brain_guard_dataframe(pd.read_csv(path))
        except Exception:
            pass

        return pd.DataFrame()

    def write_csv(self, table: str, df: pd.DataFrame, sync_github: bool = True) -> str:
        df = brain_guard_dataframe(df)

        local_status = "LOCAL_SKIP"
        try:
            path = self.local_path(table)
            df.to_csv(path, index=False)
            local_status = "LOCAL_OK"
        except Exception as e:
            local_status = f"LOCAL_ERROR_{e}"

        if not sync_github:
            return local_status

        try:
            csv_text = df.to_csv(index=False)
            gh_status = self.write_text_to_github(
                table=table,
                text=csv_text,
                message=f"Brain update {table} {brain_time_str()}",
            )
            if gh_status == "GITHUB_OK":
                return "GITHUB_OK"
            return f"{local_status} | {gh_status}"

        except Exception as e:
            return f"{local_status} | GITHUB_ERROR_{e}"

    # =====================================================
    # UPSERT / REMEMBER
    # =====================================================
    def remember(
        self,
        table: str,
        data,
        key: list[str] | None = None,
        keep_days: int | None = None,
        date_col: str = "date",
        sort_by: list[str] | None = None,
        sync_github: bool = True,
        prefer_github: bool = True,
    ) -> tuple[pd.DataFrame, str]:
        """
        Hàm lưu chính của Brain.

        data có thể là:
        - dict
        - list[dict]
        - DataFrame

        key:
        - ví dụ ["date", "symbol"]
        - nếu có key thì bản mới ghi đè bản cũ cùng key

        keep_days:
        - giữ N ngày gần nhất theo date_col
        """

        new_df = self._to_dataframe(data)
        new_df = brain_guard_dataframe(new_df)

        old_df = self.load_csv(table, prefer_github=prefer_github)
        old_df = brain_guard_dataframe(old_df)

        if old_df.empty:
            out = new_df.copy()
        elif new_df.empty:
            out = old_df.copy()
        else:
            out = pd.concat([old_df, new_df], ignore_index=True)

        out = brain_guard_dataframe(out)

        if key:
            existing_key = [c for c in key if c in out.columns]
            if existing_key:
                out = out.drop_duplicates(subset=existing_key, keep="last")

        if keep_days and date_col in out.columns:
            out = self._keep_recent_days(out, date_col=date_col, keep_days=keep_days)

        if sort_by:
            existing_sort = [c for c in sort_by if c in out.columns]
            if existing_sort:
                out = out.sort_values(existing_sort).reset_index(drop=True)

        status = self.write_csv(table, out, sync_github=sync_github)
        return out, status

    def recall(self, table: str, prefer_github: bool = True) -> pd.DataFrame:
        return self.load_csv(table, prefer_github=prefer_github)

    # alias dễ đọc
    load = recall
    save = remember

    # =====================================================
    # JSON LOAD / SAVE
    # =====================================================
    def load_json(self, table: str, default=None, prefer_github: bool = True):
        if default is None:
            default = {}

        if not table.endswith(".json"):
            table = f"{table}.json"

        if prefer_github:
            text, status = self.read_text_from_github(table)
            if text:
                try:
                    return json.loads(text)
                except Exception:
                    pass

        path = self.local_path(table)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

        return default

    def write_json(self, table: str, data, sync_github: bool = True) -> str:
        if not table.endswith(".json"):
            table = f"{table}.json"

        text = json.dumps(data, ensure_ascii=False, indent=2)

        local_status = "LOCAL_SKIP"
        try:
            path = self.local_path(table)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            local_status = "LOCAL_OK"
        except Exception as e:
            local_status = f"LOCAL_ERROR_{e}"

        if not sync_github:
            return local_status

        gh_status = self.write_text_to_github(
            table=table,
            text=text,
            message=f"Brain update {table} {brain_time_str()}",
        )

        if gh_status == "GITHUB_OK":
            return "GITHUB_OK"

        return f"{local_status} | {gh_status}"

    # =====================================================
    # UTILS
    # =====================================================
    def _to_dataframe(self, data) -> pd.DataFrame:
        if data is None:
            return pd.DataFrame()

        if isinstance(data, pd.DataFrame):
            return data.copy()

        if isinstance(data, dict):
            return pd.DataFrame([data])

        if isinstance(data, list):
            if len(data) == 0:
                return pd.DataFrame()
            return pd.DataFrame(data)

        return pd.DataFrame()

    def _keep_recent_days(
        self,
        df: pd.DataFrame,
        date_col: str = "date",
        keep_days: int = 120,
    ) -> pd.DataFrame:
        out = df.copy()

        out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
        out = out.dropna(subset=[date_col])

        if out.empty:
            return out

        unique_dates = sorted(out[date_col].dt.strftime("%Y-%m-%d").unique())
        keep_dates = unique_dates[-keep_days:]

        out["_brain_date_str"] = out[date_col].dt.strftime("%Y-%m-%d")
        out = out[out["_brain_date_str"].isin(keep_dates)].copy()
        out = out.drop(columns=["_brain_date_str"])

        out[date_col] = out[date_col].dt.strftime("%Y-%m-%d")
        return brain_guard_dataframe(out)

    # =====================================================
    # DIAGNOSTIC
    # =====================================================
    def status(self) -> dict:
        return {
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "github_dir": self.github_dir,
            "has_token": bool(self.token()),
            "has_github": self.has_github(),
            "time": brain_time_str(),
        }

    def table_exists_local(self, table: str) -> bool:
        return os.path.exists(self.local_path(table))

    def table_exists_github(self, table: str) -> bool:
        if not self.has_github():
            return False

        try:
            r = requests.get(
                self.github_url(table),
                headers=self.github_headers(),
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False
