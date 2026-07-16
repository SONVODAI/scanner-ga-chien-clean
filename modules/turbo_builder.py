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
