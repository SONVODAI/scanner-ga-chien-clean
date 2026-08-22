"""
Phase 3K.3 — Bot self-knowledge read model (research-only, no self-congratulation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import (
    list_ledger_entries,
    list_snapshots,
)
from modules.edge_research.opr_bridge.production_calibration_records import (
    SELF_KNOWLEDGE_VERSION,
    ClaimMaturity,
    derive_claim_maturity,
)
from modules.edge_research.opr_bridge.production_observation_persistence import load_observation_index


def build_self_knowledge_read_model(*, data_dir=None) -> Dict[str, Any]:
    """
    Research-only statements derived from ledger state.
    No profitability claims. No BUY/SELL.
    """
    entries = list_ledger_entries(data_dir=data_dir, forward_only=True)
    snapshots = list_snapshots(data_dir=data_dir)
    latest = snapshots[-1] if snapshots else None

    obs_index = load_observation_index(data_dir)
    live_forward_obs = [
        oid for oid, meta in obs_index.get("observations", {}).items()
        if meta.get("observation_mode") == "LIVE_FORWARD"
    ]

    by_obs: Dict[str, List] = {}
    for e in entries:
        by_obs.setdefault(e.observation_id, []).append(e)

    t5_reached = sum(1 for oid, es in by_obs.items() if any(x.horizon == "T5" for x in es))
    t5_pending = len(live_forward_obs) - t5_reached if live_forward_obs else 0

    weakened = sum(
        1 for e in entries
        if e.pre_outcome_snapshot.lifecycle_state in ("WEAKENED", "CHALLENGED")
    )

    maturity = latest.maturity_label if latest else derive_claim_maturity(len(entries))
    eligible_n = latest.eligible_n if latest else len(entries)

    statements: List[str] = []

    if not entries:
        statements.append("I currently have no authoritative LIVE_FORWARD forward evidence in the calibration ledger.")
    else:
        statements.append(f"I currently have {len(set(e.observation_id for e in entries))} LIVE_FORWARD observations with forward evidence entries.")

    if t5_reached < 2:
        statements.append(f"Only {t5_reached} observation(s) have reached T5; this is too little evidence for a reliable conclusion.")
    else:
        statements.append(f"{t5_reached} observations have reached T5; sample remains descriptive only.")

    if maturity in (ClaimMaturity.IMMATURE.value, ClaimMaturity.EARLY_SAMPLE.value, ClaimMaturity.NO_FORWARD_EVIDENCE.value):
        statements.append("My SUPPORTED observations have not accumulated enough independent forward evidence for a reliable conclusion.")

    if weakened:
        statements.append(f"{weakened} prior observation(s) were in weakened/challenged lifecycle state at pre-outcome snapshot.")

    if maturity == ClaimMaturity.NO_FORWARD_EVIDENCE.value:
        statements.append("Forward evidence maturity: NO_FORWARD_EVIDENCE — measurement infrastructure ready but no LIVE_FORWARD outcomes yet.")

    return {
        "version": SELF_KNOWLEDGE_VERSION,
        "live_forward_observation_count": len(live_forward_obs),
        "ledger_entry_count": len(entries),
        "eligible_forward_evidence_n": eligible_n,
        "maturity_label": maturity,
        "t5_reached_count": t5_reached,
        "t5_pending_count": max(0, t5_pending),
        "weakened_or_challenged_count": weakened,
        "statements": statements,
        "latest_snapshot_id": latest.snapshot_id if latest else None,
        "shadow_authority": {"research_only": True, "trading_authority": False, "edge_active": False},
        "no_profitability_claim": True,
        "no_buy_sell": True,
    }
