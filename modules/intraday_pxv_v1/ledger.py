"""Isolated shadow ledger. Never writes Camera or production stores."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from modules.intraday_pxv_v1.paths import output_root


def write_ledger(df: pd.DataFrame, out_dir: Path | None = None) -> Path:
    root = out_dir or output_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "shadow_ledger.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for rec in df.to_dict(orient="records"):
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    parquet = root / "shadow_ledger.parquet"
    try:
        df.to_parquet(parquet, index=False)
    except Exception:
        pass
    return path
