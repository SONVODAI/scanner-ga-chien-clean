"""
snapshot_storage.py
Mr.BOT PRO - Snapshot Storage V2.0

Mục tiêu:
- Bảo vệ dữ liệu T+3 / T+5 / T+10.
- Ưu tiên đọc dữ liệu bền từ GitHub khi có GITHUB_TOKEN.
- Fallback về file local và bản backup khi GitHub không khả dụng.
- Ghi CSV theo cơ chế atomic: ghi file tạm rồi os.replace().
- Tạo backup trước khi thay file hiện tại.
- Không ghi đè bằng DataFrame rỗng hoặc dữ liệu không hợp lệ.
- Ghi nhật ký lưu trữ để dễ kiểm tra lỗi.

Module này chỉ phụ trách lưu trữ. Logic phân loại, thống kê và giao diện
vẫn nằm trong modules/daily_summary.py.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

try:
    import requests
except ImportError:  # App vẫn chạy local nếu chưa có requests.
    requests = None


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

DEFAULT_GITHUB_OWNER = "SONVODAI"
DEFAULT_GITHUB_REPO = "scanner-ga-chien-clean"
DEFAULT_GITHUB_BRANCH = "main"
DEFAULT_REMOTE_PATH = "data/earning_money_snapshots.csv"

BACKUP_KEEP = 30
LOG_KEEP_LINES = 2_000


@dataclass(frozen=True)
class StorageStatus:
    source: str = "EMPTY"
    local_status: str = "NOT_RUN"
    remote_status: str = "NOT_RUN"
    backup_status: str = "NOT_RUN"
    rows: int = 0
    sessions: int = 0
    message: str = ""

    def as_text(self) -> str:
        return (
            f"source={self.source} | local={self.local_status} | "
            f"remote={self.remote_status} | backup={self.backup_status} | "
            f"rows={self.rows} | sessions={self.sessions}"
        )


_LAST_STATUS = StorageStatus()


def get_last_storage_status() -> StorageStatus:
    return _LAST_STATUS


def _set_last_status(status: StorageStatus) -> None:
    global _LAST_STATUS
    _LAST_STATUS = status


def _now() -> datetime:
    return datetime.now(VN_TZ)


def _get_setting(name: str, default: str | None = None) -> str | None:
    """
    Thứ tự đọc cấu hình:
    1. Biến môi trường.
    2. Streamlit secrets.
    3. Giá trị mặc định.
    """
    value = os.getenv(name)
    if value:
        return str(value).strip()

    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret).strip()
    except Exception:
        pass

    return default


def _github_config(local_path: Path) -> dict[str, str | None]:
    remote_default = (
        DEFAULT_REMOTE_PATH
        if local_path.name == "earning_money_snapshots.csv"
        else f"data/{local_path.name}"
    )
    return {
        "token": _get_setting("GITHUB_TOKEN"),
        "owner": _get_setting("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER),
        "repo": _get_setting("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO),
        "branch": _get_setting("GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH),
        "remote_path": _get_setting("GITHUB_SNAPSHOT_PATH", remote_default),
    }


def _empty(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _backup_dir(path: Path) -> Path:
    return path.parent / "backups" / path.stem


def _log_file(path: Path) -> Path:
    return path.parent / "logs" / "snapshot_storage.log"


def _write_log(path: Path, event: str, **details: object) -> None:
    try:
        log_path = _log_file(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "time": _now().isoformat(timespec="seconds"),
            "event": event,
            **details,
        }
        line = json.dumps(payload, ensure_ascii=False, default=str)

        old_lines: list[str] = []
        if log_path.exists():
            try:
                old_lines = log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()[-(LOG_KEEP_LINES - 1):]
            except OSError:
                old_lines = []

        old_lines.append(line)
        log_path.write_text("\n".join(old_lines) + "\n", encoding="utf-8")
    except Exception:
        # Logging không được phép làm app dừng.
        pass


def _validate_dataframe(
    df: pd.DataFrame,
    required_columns: Iterable[str],
    key_columns: Iterable[str],
    *,
    allow_empty: bool = False,
) -> pd.DataFrame:
    if df is None:
        raise ValueError("Snapshot history là None.")

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Snapshot history phải là pandas.DataFrame.")

    if df.empty and not allow_empty:
        raise ValueError("Từ chối ghi DataFrame rỗng.")

    required = list(required_columns)
    keys = list(key_columns)

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Thiếu cột bắt buộc: {missing}")

    missing_keys = [col for col in keys if col not in df.columns]
    if missing_keys:
        raise ValueError(f"Thiếu cột khóa: {missing_keys}")

    out = df.copy()

    if not out.empty:
        for key in keys:
            if out[key].isna().any():
                raise ValueError(f"Cột khóa {key!r} có giá trị rỗng.")

        out = out.drop_duplicates(keys, keep="last")

        if "snapshot_date" in out.columns:
            parsed = pd.to_datetime(out["snapshot_date"], errors="coerce")
            if parsed.isna().any():
                raise ValueError("Có snapshot_date không hợp lệ.")
            out["snapshot_date"] = parsed.dt.strftime("%Y-%m-%d")

        if "symbol" in out.columns:
            out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
            bad_symbol = out["symbol"].isin(["", "NAN", "NONE"])
            if bad_symbol.any():
                raise ValueError("Có symbol rỗng hoặc không hợp lệ.")

    return out.reindex(columns=required)


def _read_csv_bytes(
    raw: bytes,
    required_columns: Iterable[str],
    key_columns: Iterable[str],
) -> pd.DataFrame:
    text = raw.decode("utf-8-sig")
    df = pd.read_csv(StringIO(text))
    return _validate_dataframe(
        df,
        required_columns,
        key_columns,
        allow_empty=True,
    )


def _read_local(
    path: Path,
    required_columns: Iterable[str],
    key_columns: Iterable[str],
) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty(required_columns)

    df = pd.read_csv(path, encoding="utf-8-sig")
    return _validate_dataframe(
        df,
        required_columns,
        key_columns,
        allow_empty=True,
    )


def _github_api_url(owner: str, repo: str, remote_path: str) -> str:
    clean_path = str(remote_path).lstrip("/")
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{clean_path}"


def _read_remote(
    path: Path,
    required_columns: Iterable[str],
    key_columns: Iterable[str],
) -> tuple[pd.DataFrame, str]:
    cfg = _github_config(path)
    token = cfg["token"]

    if not token:
        return _empty(required_columns), "NO_TOKEN"

    if requests is None:
        return _empty(required_columns), "NO_REQUESTS"

    owner = str(cfg["owner"])
    repo = str(cfg["repo"])
    branch = str(cfg["branch"])
    remote_path = str(cfg["remote_path"])

    url = _github_api_url(owner, repo, remote_path)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params={"ref": branch},
            timeout=15,
        )

        if response.status_code == 404:
            return _empty(required_columns), "REMOTE_NOT_FOUND"

        if response.status_code != 200:
            return _empty(required_columns), f"REMOTE_HTTP_{response.status_code}"

        content = response.json().get("content", "")
        if not content:
            return _empty(required_columns), "REMOTE_EMPTY"

        raw = base64.b64decode(content)
        df = _read_csv_bytes(raw, required_columns, key_columns)
        return df, "REMOTE_OK"

    except Exception as exc:
        _write_log(path, "REMOTE_READ_ERROR", error=repr(exc))
        return _empty(required_columns), "REMOTE_ERROR"


def _latest_valid_backup(
    path: Path,
    required_columns: Iterable[str],
    key_columns: Iterable[str],
) -> tuple[pd.DataFrame, str]:
    folder = _backup_dir(path)
    if not folder.exists():
        return _empty(required_columns), "NO_BACKUP"

    backups = sorted(
        folder.glob(f"{path.stem}_*.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    for backup in backups:
        try:
            df = _read_local(backup, required_columns, key_columns)
            if not df.empty:
                return df, f"BACKUP_OK:{backup.name}"
        except Exception:
            continue

    return _empty(required_columns), "NO_VALID_BACKUP"


def load_history(
    path: str | Path,
    required_columns: Iterable[str],
    *,
    key_columns: Iterable[str] = ("snapshot_date", "symbol"),
    prefer_remote: bool = True,
) -> pd.DataFrame:
    """
    Đọc lịch sử theo thứ tự:
    - GitHub (nếu có token).
    - File local.
    - Backup local gần nhất.

    Khi GitHub có dữ liệu hợp lệ, tự đồng bộ một bản local bằng atomic write
    nhưng không tạo backup để tránh sinh backup chỉ vì thao tác đọc.
    """
    csv_path = Path(path)
    columns = list(required_columns)
    keys = list(key_columns)

    remote_df = _empty(columns)
    remote_status = "SKIPPED"
    if prefer_remote:
        remote_df, remote_status = _read_remote(csv_path, columns, keys)

    local_df = _empty(columns)
    local_status = "LOCAL_NOT_FOUND"
    try:
        local_df = _read_local(csv_path, columns, keys)
        local_status = "LOCAL_OK" if not local_df.empty else "LOCAL_EMPTY"
    except Exception as exc:
        local_status = "LOCAL_CORRUPT"
        _write_log(csv_path, "LOCAL_READ_ERROR", error=repr(exc))

    if not remote_df.empty:
        selected = remote_df
        source = "GITHUB"

        # Đồng bộ local để app vẫn chạy khi GitHub tạm lỗi ở lần sau.
        try:
            _atomic_write_csv(selected, csv_path)
            local_status = "LOCAL_SYNCED_FROM_GITHUB"
        except Exception as exc:
            local_status = "LOCAL_SYNC_ERROR"
            _write_log(csv_path, "LOCAL_SYNC_ERROR", error=repr(exc))

    elif not local_df.empty:
        selected = local_df
        source = "LOCAL"

    else:
        backup_df, backup_status = _latest_valid_backup(csv_path, columns, keys)
        if not backup_df.empty:
            selected = backup_df
            source = "BACKUP"
            try:
                _atomic_write_csv(selected, csv_path)
                local_status = "LOCAL_RESTORED_FROM_BACKUP"
            except Exception as exc:
                local_status = "LOCAL_RESTORE_ERROR"
                _write_log(csv_path, "LOCAL_RESTORE_ERROR", error=repr(exc))
        else:
            selected = _empty(columns)
            source = "EMPTY"
            local_status = f"{local_status}|{backup_status}"

    sessions = (
        int(selected["snapshot_date"].nunique())
        if "snapshot_date" in selected.columns and not selected.empty
        else 0
    )

    status = StorageStatus(
        source=source,
        local_status=local_status,
        remote_status=remote_status,
        backup_status="NOT_NEEDED",
        rows=len(selected),
        sessions=sessions,
        message="Đọc lịch sử snapshot hoàn tất.",
    )
    _set_last_status(status)
    _write_log(csv_path, "LOAD_HISTORY", status=status.as_text())

    return selected.reset_index(drop=True).reindex(columns=columns)


def merge_upsert(
    history: pd.DataFrame,
    snapshot: pd.DataFrame,
    required_columns: Iterable[str],
    *,
    key_columns: Iterable[str] = ("snapshot_date", "symbol"),
) -> pd.DataFrame:
    columns = list(required_columns)
    keys = list(key_columns)

    base = (
        _empty(columns)
        if history is None or history.empty
        else history.reindex(columns=columns).copy()
    )

    if snapshot is None or snapshot.empty:
        return base

    current = snapshot.reindex(columns=columns).copy()
    merged = pd.concat([base, current], ignore_index=True)
    merged = merged.drop_duplicates(keys, keep="last")

    sort_cols = [col for col in ["snapshot_date", "health_rank", "symbol"] if col in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols, kind="stable")

    return merged.reset_index(drop=True).reindex(columns=columns)


def _create_backup(path: Path) -> tuple[str, Path | None]:
    if not path.exists() or path.stat().st_size == 0:
        return "NO_OLD_FILE", None

    folder = _backup_dir(path)
    folder.mkdir(parents=True, exist_ok=True)

    stamp = _now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = folder / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)

    backups = sorted(
        folder.glob(f"{path.stem}_*{path.suffix}"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[BACKUP_KEEP:]:
        try:
            old_backup.unlink()
        except OSError:
            pass

    return "BACKUP_OK", backup_path


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """
    Ghi cùng thư mục để os.replace() là thao tác atomic trên cùng filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            df.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())

        # Đọc lại file tạm để chắc chắn CSV vừa ghi không hỏng.
        check = pd.read_csv(temp_path, encoding="utf-8-sig")
        if len(check) != len(df):
            raise IOError(
                f"Xác minh file tạm thất bại: expected={len(df)}, actual={len(check)}"
            )

        os.replace(temp_path, path)

        # Cố gắng flush metadata thư mục trên hệ điều hành hỗ trợ.
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _write_remote(path: Path, df: pd.DataFrame) -> str:
    cfg = _github_config(path)
    token = cfg["token"]

    if not token:
        return "NO_TOKEN"

    if requests is None:
        return "NO_REQUESTS"

    owner = str(cfg["owner"])
    repo = str(cfg["repo"])
    branch = str(cfg["branch"])
    remote_path = str(cfg["remote_path"])

    url = _github_api_url(owner, repo, remote_path)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        sha = None
        get_response = requests.get(
            url,
            headers=headers,
            params={"ref": branch},
            timeout=15,
        )
        if get_response.status_code == 200:
            sha = get_response.json().get("sha")
        elif get_response.status_code not in (404,):
            return f"REMOTE_GET_HTTP_{get_response.status_code}"

        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        payload: dict[str, object] = {
            "message": (
                "Update earning money snapshots "
                f"{_now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            "content": base64.b64encode(csv_bytes).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=25,
        )
        if response.status_code in (200, 201):
            return "REMOTE_OK"

        return f"REMOTE_PUT_HTTP_{response.status_code}"

    except Exception as exc:
        _write_log(path, "REMOTE_WRITE_ERROR", error=repr(exc))
        return "REMOTE_ERROR"


def save_history(
    df: pd.DataFrame,
    path: str | Path,
    required_columns: Iterable[str],
    *,
    key_columns: Iterable[str] = ("snapshot_date", "symbol"),
    push_remote: bool = True,
) -> StorageStatus:
    """
    Lưu dữ liệu đã merge.

    Quy tắc an toàn:
    - Không ghi DataFrame rỗng.
    - Kiểm tra schema và khóa.
    - Backup file cũ.
    - Ghi atomic vào local.
    - Sau khi local thành công mới đẩy GitHub.
    """
    csv_path = Path(path)
    columns = list(required_columns)
    keys = list(key_columns)

    validated = _validate_dataframe(
        df,
        columns,
        keys,
        allow_empty=False,
    )

    backup_status = "NOT_RUN"
    backup_path: Path | None = None
    local_status = "NOT_RUN"
    remote_status = "SKIPPED"

    try:
        backup_status, backup_path = _create_backup(csv_path)
        _atomic_write_csv(validated, csv_path)
        local_status = "LOCAL_OK"
    except Exception as exc:
        status = StorageStatus(
            source="MEMORY",
            local_status="LOCAL_ERROR",
            remote_status="NOT_RUN",
            backup_status=backup_status,
            rows=len(validated),
            sessions=(
                int(validated["snapshot_date"].nunique())
                if "snapshot_date" in validated.columns
                else 0
            ),
            message=f"Không lưu được snapshot local: {exc}",
        )
        _set_last_status(status)
        _write_log(
            csv_path,
            "SAVE_LOCAL_ERROR",
            error=repr(exc),
            backup=str(backup_path) if backup_path else None,
        )
        raise

    if push_remote:
        remote_status = _write_remote(csv_path, validated)

    sessions = (
        int(validated["snapshot_date"].nunique())
        if "snapshot_date" in validated.columns
        else 0
    )
    status = StorageStatus(
        source="MEMORY",
        local_status=local_status,
        remote_status=remote_status,
        backup_status=backup_status,
        rows=len(validated),
        sessions=sessions,
        message="Snapshot history đã được lưu an toàn.",
    )
    _set_last_status(status)
    _write_log(
        csv_path,
        "SAVE_HISTORY",
        status=status.as_text(),
        backup=str(backup_path) if backup_path else None,
    )
    return status


def restore_latest_backup(
    path: str | Path,
    required_columns: Iterable[str],
    *,
    key_columns: Iterable[str] = ("snapshot_date", "symbol"),
) -> pd.DataFrame:
    """
    Hàm cứu hộ thủ công. Chỉ cần gọi khi muốn phục hồi backup gần nhất.
    """
    csv_path = Path(path)
    restored, backup_status = _latest_valid_backup(
        csv_path,
        required_columns,
        key_columns,
    )
    if restored.empty:
        raise FileNotFoundError("Không tìm thấy backup snapshot hợp lệ.")

    _atomic_write_csv(restored, csv_path)
    _write_log(
        csv_path,
        "RESTORE_BACKUP",
        backup_status=backup_status,
        rows=len(restored),
    )
    return restored

