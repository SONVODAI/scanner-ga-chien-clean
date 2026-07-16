from pathlib import Path
import pandas as pd

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)


def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.parquet"


def exists(name: str) -> bool:
    return cache_path(name).exists()


def save_dataframe(name: str, df: pd.DataFrame) -> None:
    if df is None:
        return
    df.to_parquet(cache_path(name), index=False)


def load_dataframe(name: str) -> pd.DataFrame:
    return pd.read_parquet(cache_path(name))


def clear_cache() -> None:
    for f in CACHE_DIR.glob("*.parquet"):
        f.unlink(missing_ok=True)
