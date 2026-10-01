"""Frozen confirmation symbol cohort (exact V1 / historical-audit HOSE eligible set)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ELIGIBILITY = Path("diagnostics/foreign_flow_historical_audit/ems142_hsx_eligibility.json")
DEFAULT_FREEZE = Path("data/foreign_flow_history/manifests/research_freeze.json")
COHORT_EVENT_LOG = Path("data/foreign_flow_confirmation/manifests/cohort_events.jsonl")

LAST_IN_SAMPLE = "2026-08-24"


def load_hose_eligible(path: Path = DEFAULT_ELIGIBILITY) -> List[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return sorted({str(s).strip().upper() for s in (data.get("hose_eligible") or [])})


def load_freeze_symbol_set(path: Path = DEFAULT_FREEZE) -> List[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cov = data.get("per_symbol_coverage") or []
    if cov:
        return sorted({str(r["symbol"]).strip().upper() for r in cov if isinstance(r, dict)})
    # fallback: directory listing is not used for cohort identity
    return load_hose_eligible()


def confirmation_cohort(*, eligibility_path: Path = DEFAULT_ELIGIBILITY, freeze_path: Path = DEFAULT_FREEZE) -> Dict[str, Any]:
    """
    Exact defensible cohort = intersection of EMS HOSE-eligible and freeze coverage.
    Must not silently expand/reduce after confirmation starts.
    """
    hose = set(load_hose_eligible(eligibility_path))
    freeze = set(load_freeze_symbol_set(freeze_path)) if Path(freeze_path).exists() else set(hose)
    symbols = sorted(hose & freeze) if freeze else sorted(hose)
    return {
        "cohort_id": "ff_confirmation_v1_hose_freeze_intersection",
        "asof_eligibility_trade_date": LAST_IN_SAMPLE,
        "n_hose_eligible": len(hose),
        "n_freeze": len(freeze) if freeze else None,
        "n_confirmation_cohort": len(symbols),
        "symbols": symbols,
        "eligibility_path": str(eligibility_path),
        "freeze_path": str(freeze_path),
        "note": "Present-day HOSE overlap; not historical membership-as-of. Do not fabricate HNX/UPCOM.",
    }


def record_cohort_event(event: Dict[str, Any], path: Path = COHORT_EVENT_LOG) -> None:
    """Explicit log when listing/delisting/availability changes are observed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
