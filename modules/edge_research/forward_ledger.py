"""
Canonical edge × stock LIVE_FORWARD births and session assessments (Phase B).

edge_forward_ledger.csv is the canonical truth store. Sidecars are derived
and rebuildable. Births are first-write-wins and never attach future outcomes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.contracts import (
    EDGE_FORWARD_LEDGER_COLUMNS,
    EDGE_SESSION_ASSESSMENT_COLUMNS,
    FORWARD_OUTCOME_PENDING,
)
from modules.edge_research.storage import ensure_storage, read_ledger, resolve_data_dir

LATEST_RECOGNITION_FILE = "latest_future_recognition.json"
SIDECAR_DIRNAME = "daily_edge_matches"
RESEARCH_LABEL = "RESEARCH MATCH — NOT AUTOMATIC BUY"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def birth_idempotency_key(hypothesis_id: str, t0_trade_date: str, symbol: str) -> str:
    return f"{hypothesis_id}|{t0_trade_date}|{str(symbol).upper().strip()}"


def ledger_id_for(hypothesis_id: str, t0_trade_date: str, symbol: str) -> str:
    import hashlib

    return hashlib.sha256(birth_idempotency_key(hypothesis_id, t0_trade_date, symbol).encode("utf-8")).hexdigest()


def _existing_keys(ledger: pd.DataFrame) -> set[str]:
    if ledger.empty:
        return set()
    hid = ledger.get("hypothesis_id", pd.Series(dtype=str)).astype(str)
    date = ledger.get("t0_trade_date", ledger.get("t0_date", pd.Series(dtype=str))).astype(str)
    sym = ledger.get("symbol", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
    return set(f"{h}|{d}|{s}" for h, d, s in zip(hid, date, sym))


def persist_births(
    births: List[Dict[str, Any]],
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Append new births; skip duplicates by (hypothesis_id, t0_trade_date, symbol)."""
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
    keys = _existing_keys(ledger)
    new_rows: List[Dict[str, Any]] = []
    skipped = 0
    for birth in births:
        key = birth_idempotency_key(
            str(birth.get("hypothesis_id", "")),
            str(birth.get("t0_trade_date") or birth.get("t0_date") or ""),
            str(birth.get("symbol", "")),
        )
        if key in keys:
            skipped += 1
            continue
        keys.add(key)
        row = dict(birth)
        row.setdefault("outcome_status", FORWARD_OUTCOME_PENDING)
        row.setdefault("t0_date", row.get("t0_trade_date"))
        row.setdefault("research_label", RESEARCH_LABEL)
        # Never persist future labels at birth.
        for forbidden in ("t3_return", "t5_return", "t10_return", "forward_return"):
            row.pop(forbidden, None)
        new_rows.append(row)
    aligned: List[Dict[str, Any]] = []
    new_edge_ids: List[str] = []
    for row in new_rows:
        aligned.append({col: row.get(col, "") for col in EDGE_FORWARD_LEDGER_COLUMNS})
        new_edge_ids.append(str(row.get("edge_id") or ""))
    if aligned:
        ledger = pd.concat([ledger, pd.DataFrame(aligned)], ignore_index=True)
        out_cols = list(EDGE_FORWARD_LEDGER_COLUMNS)
        for col in ledger.columns:
            if col not in out_cols:
                out_cols.append(col)
        ledger = ledger.reindex(columns=out_cols)
        ledger.to_csv(root / "edge_forward_ledger.csv", index=False)
    return {
        "new_births": len(aligned),
        "duplicate_skips": skipped,
        "total": int(len(ledger)),
        "new_edge_ids": new_edge_ids,
    }


def append_session_assessment(
    assessment: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    root = ensure_storage(data_dir)
    history = read_ledger("edge_session_assessments.csv", data_dir=root)
    row = {col: assessment.get(col, "") for col in EDGE_SESSION_ASSESSMENT_COLUMNS}
    # Idempotent on run_id
    if not history.empty and "run_id" in history.columns:
        if (history["run_id"].astype(str) == str(row.get("run_id", ""))).any():
            return root / "edge_session_assessments.csv"
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    path = root / "edge_session_assessments.csv"
    history.to_csv(path, index=False)
    return path


def write_latest_assessment(assessment: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / LATEST_RECOGNITION_FILE
    path.write_text(json.dumps(assessment, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def read_latest_assessment(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    path = root / LATEST_RECOGNITION_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild_daily_sidecar(
    trade_date: str,
    assessment: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    """Derived/rebuildable operator sidecar. Ledger remains canonical."""
    root = ensure_storage(data_dir)
    side_dir = root / SIDECAR_DIRNAME
    side_dir.mkdir(parents=True, exist_ok=True)
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
    matches: List[Dict[str, Any]] = []
    if not ledger.empty:
        date_col = "t0_trade_date" if "t0_trade_date" in ledger.columns else "t0_date"
        session = ledger[ledger[date_col].astype(str) == str(trade_date)]
        matches = session.to_dict(orient="records")
    payload = {
        "trade_date": trade_date,
        "assessment_state": assessment.get("assessment_state"),
        "reason": assessment.get("reason"),
        "run_id": assessment.get("run_id"),
        "universe_count": assessment.get("universe_count"),
        "active_edge_count": assessment.get("active_edge_count"),
        "qualified_match_count": assessment.get("qualified_match_count"),
        "research_label": RESEARCH_LABEL,
        "matches": matches,
        "rebuilt_at": _iso_now(),
        "canonical_source": "edge_forward_ledger.csv",
    }
    path = side_dir / f"{trade_date}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load_session_matches(trade_date: str, *, data_dir: Optional[Path] = None) -> pd.DataFrame:
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=data_dir)
    if ledger.empty:
        return ledger
    date_col = "t0_trade_date" if "t0_trade_date" in ledger.columns else "t0_date"
    return ledger[ledger[date_col].astype(str) == str(trade_date)].copy()
