"""Immutable first_seen at the Candidate persist boundary.

Last-wins on scores/conclusion must not destroy first_seen.
Does not backfill historical rows. Does not change Elite numbers.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.live_candidate.contract import (
    FIRST_SEEN_COL,
    UPDATED_COL,
    has_legal_first_seen,
    is_actionable,
)


def _norm_symbol(val: object) -> str:
    return str(val or "").strip().upper()


def _norm_date(val: object) -> str:
    ts = pd.to_datetime(val, errors="coerce")
    if pd.isna(ts):
        return str(val or "")[:10]
    return ts.strftime("%Y-%m-%d")


def _prior_first_seen_map(prior: pd.DataFrame) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    if prior is None or prior.empty or FIRST_SEEN_COL not in prior.columns:
        return out
    if "symbol" not in prior.columns or "date" not in prior.columns:
        return out
    for _, row in prior.iterrows():
        raw = row.get(FIRST_SEEN_COL)
        if not has_legal_first_seen(raw):
            continue
        key = (_norm_date(row.get("date")), _norm_symbol(row.get("symbol")))
        if key[0] and key[1]:
            out[key] = str(raw).strip()
    return out


def apply_immutable_first_seen(
    prior: pd.DataFrame | None,
    incoming: pd.DataFrame | None,
    *,
    observed_at: datetime,
) -> pd.DataFrame:
    """Stamp incoming actionable episodes; concat; last-wins without clobbering first_seen."""
    now = as_vn(observed_at)
    now_iso = now.isoformat()
    prior_df = prior.copy() if prior is not None and not prior.empty else pd.DataFrame()
    incoming_df = incoming.copy() if incoming is not None and not incoming.empty else pd.DataFrame()

    if incoming_df.empty:
        if FIRST_SEEN_COL not in prior_df.columns and not prior_df.empty:
            prior_df[FIRST_SEEN_COL] = ""
            prior_df[UPDATED_COL] = ""
        return prior_df.reset_index(drop=True)

    incoming_df["symbol"] = incoming_df["symbol"].map(_norm_symbol)
    incoming_df["date"] = incoming_df["date"].map(_norm_date)
    prior_map = _prior_first_seen_map(prior_df)

    first_seen_vals: list[str] = []
    updated_vals: list[str] = []
    for _, row in incoming_df.iterrows():
        key = (_norm_date(row.get("date")), _norm_symbol(row.get("symbol")))
        existing = prior_map.get(key, "")
        if has_legal_first_seen(existing):
            first_seen_vals.append(existing)
            updated_vals.append(now_iso)
        elif is_actionable(row.get("conclusion")):
            first_seen_vals.append(now_iso)
            updated_vals.append(now_iso)
        else:
            first_seen_vals.append("")
            updated_vals.append(now_iso)

    incoming_df[FIRST_SEEN_COL] = first_seen_vals
    incoming_df[UPDATED_COL] = updated_vals

    if prior_df.empty:
        hist = incoming_df
    else:
        if FIRST_SEEN_COL not in prior_df.columns:
            prior_df[FIRST_SEEN_COL] = ""
        if UPDATED_COL not in prior_df.columns:
            prior_df[UPDATED_COL] = ""
        prior_df["symbol"] = prior_df["symbol"].map(_norm_symbol)
        prior_df["date"] = prior_df["date"].map(_norm_date)
        hist = pd.concat([prior_df, incoming_df], ignore_index=True, sort=False)

    hist = hist.drop_duplicates(subset=["date", "symbol"], keep="last")
    return hist.reset_index(drop=True)
