"""Apply the Candidate time contract to interpret loops and stored ledgers.

Does not change P×V features, decide_evidence, thresholds, or debounce rules.
Re-running PublishedDebouncer after dropping illegal rows is required so
published state is not inherited from pre-existence RAW bars.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.examine import apply_debounce_columns, ensure_asof_ts
from modules.intraday_pxv_v1.time_contract import asof_allowed, resolve_legal_existence


def event_from_ledger_row(row: pd.Series) -> CandidateEvent:
    sess = str(row.get("session") or "")[:10]
    return CandidateEvent(
        symbol=str(row.get("symbol") or ""),
        session=pd.Timestamp(sess).date(),
        candidate_reason=str(row.get("candidate_reason") or ""),
        candidate_ts=str(row.get("candidate_ts") or ""),
        bot_context=str(row.get("bot_context") or ""),
        candidate_first_seen_ts=str(row.get("candidate_first_seen_ts") or ""),
        candidate_updated_ts=str(row.get("candidate_updated_ts") or ""),
    )


def chronology_clean_ledger(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drop illegal as-of rows, then re-apply the existing 2-bar debounce.

    Overlay values are left as stored (retrospective/reconciled). This is not a
    live as-of Camera reconstruction.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame(), {
            "rows_in": 0,
            "rows_out": 0,
            "rows_removed_illegal": 0,
            "events_in": 0,
            "events_out": 0,
            "events_removed_after_close": 0,
            "events_removed_missing_ts": 0,
            "events_next_session_open_eligible": 0,
        }

    work = ensure_asof_ts(df)
    keep_idx: list[int] = []
    after_close_keys: set[tuple[str, str]] = set()
    missing_keys: set[tuple[str, str]] = set()
    next_open = 0
    seen_keys: set[tuple[str, str]] = set()
    legal_by_key: dict[tuple[str, str], Any] = {}

    for idx, row in work.iterrows():
        key = (str(row.get("symbol")), str(row.get("session"))[:10])
        if key not in legal_by_key:
            legal_by_key[key] = resolve_legal_existence(event_from_ledger_row(row))
        legal = legal_by_key[key]
        if key not in seen_keys:
            seen_keys.add(key)
            if legal.next_session_open_eligible:
                next_open += 1
            if legal.provenance == "MISSING_UNUSABLE":
                missing_keys.add(key)
            if not legal.same_day_intraday_eligible and legal.gate_ts is not None:
                after_close_keys.add(key)
        asof = row["asof_ts"]
        if getattr(asof, "tzinfo", None) is None:
            asof = pd.Timestamp(asof).tz_localize(VN_TZ)
        if asof_allowed(asof.to_pydatetime() if hasattr(asof, "to_pydatetime") else asof, legal):
            keep_idx.append(idx)

    clean = work.loc[keep_idx].copy() if keep_idx else work.iloc[0:0].copy()
    if not clean.empty:
        clean = apply_debounce_columns(clean)
        if "alert_eligible" in clean.columns:
            clean["alert_eligible"] = False

    events_out = int(clean.groupby(["symbol", "session"]).ngroups) if len(clean) else 0
    stats = {
        "rows_in": int(len(work)),
        "rows_out": int(len(clean)),
        "rows_removed_illegal": int(len(work) - len(clean)),
        "events_in": int(len(seen_keys)),
        "events_out": events_out,
        "events_removed_after_close": int(len(after_close_keys)),
        "events_removed_missing_ts": int(len(missing_keys)),
        "events_next_session_open_eligible": int(next_open),
        "overlay_truth_class": "retrospective_reconciled when overlay_applied else canonical_first_write",
        "note": (
            "Published evidence re-debounced from the first legal as-of. "
            "Historical overlay remains retrospective/reconciled — not live Camera knowledge."
        ),
    }
    return clean.reset_index(drop=True), stats
