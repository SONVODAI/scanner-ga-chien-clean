"""
Conservative migration/audit of existing EDGE-XXXX candidates (Phase A).

Never auto-ACTIVEs old candidates. Never rewrites historical discovery/challenger
metrics. Never invents retrospective OOS from already-seen history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.contracts import (
    FREEZE_CHALLENGER_PENDING,
    FREEZE_ELIGIBLE,
    FREEZE_FRAGILE,
    FREEZE_HISTORICAL_ONLY,
    FREEZE_NON_FREEZABLE,
    FREEZE_REJECT,
    ROBUSTNESS_FRAGILE,
    ROBUSTNESS_PASS,
    ROBUSTNESS_REJECT,
)
from modules.edge_research.freeze import classify_freeze_eligibility
from modules.edge_research.storage import ensure_storage, read_ledger, resolve_data_dir


def audit_existing_candidates(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=root)
    categories = {
        "pass_reconstructable_ready_for_oos": [],
        "reconstruction_mismatch_historical_only": [],
        "fragile_remain_historical": [],
        "reject_remain_historical": [],
        "challenger_not_run": [],
        "already_frozen": [],
        "other": [],
    }
    for _, row in ledger.iterrows() if not ledger.empty else []:
        edge_id = str(row.get("edge_id", "") or "")
        decision = classify_freeze_eligibility(row)
        hid_raw = row.get("hypothesis_id", "")
        hash_raw = row.get("frozen_spec_hash", "") if "frozen_spec_hash" in row.index else ""
        already = (not pd.isna(hid_raw) and str(hid_raw).strip() not in ("", "nan")) and (
            not pd.isna(hash_raw) and str(hash_raw).strip() not in ("", "nan")
        )
        if already:
            categories["already_frozen"].append(edge_id)
            continue
        if decision.eligibility == FREEZE_ELIGIBLE:
            categories["pass_reconstructable_ready_for_oos"].append(edge_id)
        elif decision.eligibility in (FREEZE_HISTORICAL_ONLY, FREEZE_NON_FREEZABLE) and "mismatch" in decision.reason:
            categories["reconstruction_mismatch_historical_only"].append(edge_id)
        elif decision.eligibility == FREEZE_HISTORICAL_ONLY:
            categories["reconstruction_mismatch_historical_only"].append(edge_id)
        elif decision.eligibility == FREEZE_FRAGILE:
            categories["fragile_remain_historical"].append(edge_id)
        elif decision.eligibility == FREEZE_REJECT:
            categories["reject_remain_historical"].append(edge_id)
        elif decision.eligibility == FREEZE_CHALLENGER_PENDING:
            categories["challenger_not_run"].append(edge_id)
        else:
            categories["other"].append({"edge_id": edge_id, "eligibility": decision.eligibility, "reason": decision.reason})

    counts = {k: len(v) for k, v in categories.items()}
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ledger_rows": 0 if ledger.empty else int(len(ledger)),
        "auto_active": 0,
        "note": (
            "Existing EDGE-XXXX candidates are NOT auto-ACTIVEd. "
            "Challenger PASS + reconstructable + READY_FOR_OOS may freeze now and "
            "must use PROSPECTIVE OOS only. Reconstruction mismatch → historical-only. "
            "FRAGILE/REJECT remain historical. Challenger not run → no OOS. "
            "Old metrics are never rewritten to manufacture OOS evidence."
        ),
        "counts": counts,
        "categories": categories,
    }

    mig_dir = root / "migration"
    mig_dir.mkdir(parents=True, exist_ok=True)
    path = mig_dir / "phase_a_existing_edge_audit.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
