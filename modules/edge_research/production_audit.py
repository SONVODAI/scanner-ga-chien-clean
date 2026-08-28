"""
Read-only production Edge Research state audit. No science. No BUY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from modules.edge_research.eod_cycle import EOD_STATUS_FILENAME, read_latest_eod_status
from modules.edge_research.forward_ledger import read_latest_assessment
from modules.edge_research.storage import read_ledger, resolve_data_dir
from modules.edge_research.t0_universe import latest_freeze_trade_date, load_t0_freeze


def _status_counts(df, col: str = "status") -> Dict[str, int]:
    if df is None or df.empty or col not in df.columns:
        return {}
    return df[col].astype(str).str.upper().value_counts().to_dict()


def collect_production_audit(data_dir: Path | None = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    freeze_info: Dict[str, Any] = {"latest_t0": "", "universe_count": None, "error": ""}
    try:
        freeze = load_t0_freeze()
        latest = latest_freeze_trade_date(freeze)
        freeze_info["latest_t0"] = latest
        if latest and not freeze.empty and "trade_date" in freeze.columns:
            freeze_info["universe_count"] = int(
                (freeze["trade_date"].astype(str).str[:10] == str(latest)[:10]).sum()
            )
    except Exception as exc:
        freeze_info["error"] = f"{type(exc).__name__}: {exc}"

    mem = read_ledger("edge_memory.csv", root)
    ledger = read_ledger("edge_forward_ledger.csv", root)
    hyp = read_ledger("edge_hypothesis_ledger.csv", root)
    anti = read_ledger("edge_anti_context.csv", root)
    shadows = read_ledger("edge_shadow_observations.csv", root)
    assessments = read_ledger("edge_session_assessments.csv", root)
    latest_rec = read_latest_assessment(root)
    eod = read_latest_eod_status(root)

    def _horizon_n(col: str) -> int:
        if ledger.empty or col not in ledger.columns:
            return 0
        return int((ledger[col].astype(str) == "MATURE").sum())

    frozen_dir = root / "frozen_specs"
    return {
        "data_dir": str(root),
        "latest_t0": freeze_info,
        "hypotheses": int(len(hyp)),
        "oos_status": _status_counts(hyp, "oos_status") if not hyp.empty else {},
        "memory_status": _status_counts(mem),
        "births": int(len(ledger)),
        "pending_births": int((ledger["outcome_status"].astype(str) == "PENDING").sum())
        if not ledger.empty and "outcome_status" in ledger.columns
        else 0,
        "mature_t3": _horizon_n("t3_status"),
        "mature_t5": _horizon_n("t5_status"),
        "mature_t10": _horizon_n("t10_status"),
        "anti_context": int(len(anti)),
        "shadows": int(len(shadows)),
        "session_assessments": int(len(assessments)),
        "frozen_specs": int(len(list(frozen_dir.glob("*.json")))) if frozen_dir.exists() else 0,
        "latest_assessment": {
            "state": (latest_rec or {}).get("assessment_state"),
            "reason": (latest_rec or {}).get("reason"),
            "trade_date": (latest_rec or {}).get("trade_date"),
            "qualified_match_count": (latest_rec or {}).get("qualified_match_count"),
        },
        "latest_eod_run": eod,
        "eod_status_file": str(root / EOD_STATUS_FILENAME),
    }


def main() -> int:
    report = collect_production_audit()
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
