from pathlib import Path
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ==========================================================
# TURBO CACHE
# ==========================================================

CACHE_DIR = Path("cache")

CACHE_DIR.mkdir(parents=True, exist_ok=True)


CACHE_FILES = {
    "summary": CACHE_DIR / "daily_summary.parquet",
    "movement": CACHE_DIR / "movement.parquet",
    "holding_summary": CACHE_DIR / "holding_summary.parquet",
    "holding_detail": CACHE_DIR / "holding_detail.parquet",
}


# ==========================================================
# SAVE
# ==========================================================

def save_cache(name: str, df: pd.DataFrame):

    if df is None:
        return

    if name not in CACHE_FILES:
        raise ValueError(f"Unknown cache: {name}")

    df.to_parquet(
        CACHE_FILES[name],
        index=False,
    )


# ==========================================================
# LOAD
# ==========================================================

def load_cache(name: str):

    if name not in CACHE_FILES:
        raise ValueError(f"Unknown cache: {name}")

    path = CACHE_FILES[name]

    if not path.exists():
        return None

    try:
        return pd.read_parquet(path)

    except Exception as e:

        logger.warning(f"Turbo cache load failed: {e}")

        return None


# ==========================================================
# EXIST
# ==========================================================

def has_cache(name: str):

    if name not in CACHE_FILES:
        return False

    return CACHE_FILES[name].exists()


# ==========================================================
# CLEAR
# ==========================================================

def clear_cache():

    for path in CACHE_FILES.values():

        if path.exists():

            path.unlink()

    logger.info("Turbo cache cleared.")

# ==========================================================
# BUILD DAILY SUMMARY CACHE
# ==========================================================

from modules.daily_summary import (
    build_snapshot,
    compare_snapshot,
    build_summary,
    build_holding_detail,
    build_holding_summary,
)


def build_daily_cache(current_df: pd.DataFrame, history_df: pd.DataFrame):

    """
    Sinh toàn bộ cache Daily Summary.
    Chỉ chạy sau khi kết phiên hoặc khi cache chưa tồn tại.
    """

    snapshot = build_snapshot(current_df)

    movement = compare_snapshot(snapshot)

    summary = build_summary(movement)

    holding_detail = build_holding_detail(history_df)

    holding_summary = build_holding_summary(holding_detail)

    save_cache("summary", summary)

    save_cache("movement", movement)

    save_cache("holding_detail", holding_detail)

    save_cache("holding_summary", holding_summary)

    logger.info("Turbo cache built successfully.")








