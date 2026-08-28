"""
Phase 3K.5 — LIVE_FORWARD genesis contract (irreversible activation record).

Contract and persistence mechanism only — real production genesis NOT created in 3K.5.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_timezone_policy import (
    TRADING_SESSION_TIMEZONE,
    validate_genesis_first_eligible_date,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    DAY_0_SMOKE,
    HISTORICAL_REPLAY_TEST,
    LIVE_FORWARD,
    NON_FORWARD_MODES,
    PRE_DEPLOYMENT_DRY_RUN,
)
from modules.edge_research.storage import resolve_data_dir

GENESIS_VERSION = "live_forward_genesis_v1_3k5"
GENESIS_FILENAME = "live_forward_genesis.json"


@dataclass(frozen=True)
class LiveForwardGenesisRecord:
    """Irreversible LIVE_FORWARD activation identity — created once at go-live."""

    genesis_id: str
    activation_timestamp: str
    first_eligible_trade_date: str
    code_commit: str
    policy_hashes: Dict[str, str]
    dataset_identities: Dict[str, str]
    runtime_mode: str
    timezone: str
    authority_flags: Dict[str, bool]
    deployment_identity: str
    genesis_hash: str
    frozen: bool = True
    record_version: str = GENESIS_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "genesis_id": self.genesis_id,
            "activation_timestamp": self.activation_timestamp,
            "first_eligible_trade_date": self.first_eligible_trade_date,
            "code_commit": self.code_commit,
            "policy_hashes": dict(self.policy_hashes),
            "dataset_identities": dict(self.dataset_identities),
            "runtime_mode": self.runtime_mode,
            "timezone": self.timezone,
            "authority_flags": dict(self.authority_flags),
            "deployment_identity": self.deployment_identity,
            "genesis_hash": self.genesis_hash,
            "frozen": self.frozen,
            "record_version": self.record_version,
        }


def genesis_path(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir) / "production_observations"
    root.mkdir(parents=True, exist_ok=True)
    return root / GENESIS_FILENAME


def genesis_exists(data_dir: Optional[Path] = None) -> bool:
    return genesis_path(data_dir).exists()


def load_genesis(data_dir: Optional[Path] = None) -> Optional[LiveForwardGenesisRecord]:
    path = genesis_path(data_dir)
    if not path.exists():
        return None
    return _from_dict(json.loads(path.read_text(encoding="utf-8")))


def compute_genesis_hash(payload: Dict[str, Any]) -> str:
    return stable_hash({k: v for k, v in payload.items() if k not in ("genesis_hash",)})


def build_genesis_record(
    *,
    first_eligible_trade_date: str,
    code_commit: str,
    policy_hashes: Dict[str, str],
    dataset_identities: Dict[str, str],
    deployment_identity: str,
    timezone: str = TRADING_SESSION_TIMEZONE,
) -> LiveForwardGenesisRecord:
    """Build genesis record for deployment runbook — caller must explicitly persist."""
    ok, reason = validate_genesis_first_eligible_date(first_eligible_trade_date)
    if not ok:
        raise ValueError(f"invalid_genesis_first_eligible_date:{reason}")
    genesis_id = f"lfwd-gen-{stable_hash({'commit': code_commit, 'date': first_eligible_trade_date})[:16]}"
    payload = {
        "genesis_id": genesis_id,
        "activation_timestamp": utc_now_iso(),
        "first_eligible_trade_date": first_eligible_trade_date,
        "code_commit": code_commit,
        "policy_hashes": policy_hashes,
        "dataset_identities": dataset_identities,
        "runtime_mode": LIVE_FORWARD,
        "timezone": timezone,
        "trading_session_timezone": TRADING_SESSION_TIMEZONE,
        "first_eligible_semantics": "vn_trading_session_date",
        "authority_flags": {
            "research_only": True,
            "trading_authority": False,
            "buy_signal": False,
            "sell_signal": False,
            "edge_active": False,
        },
        "deployment_identity": deployment_identity,
        "record_version": GENESIS_VERSION,
    }
    ghash = compute_genesis_hash(payload)
    record_payload = {
        k: v
        for k, v in payload.items()
        if k not in ("trading_session_timezone", "first_eligible_semantics")
    }
    return LiveForwardGenesisRecord(genesis_hash=ghash, **record_payload)


def persist_genesis(
    genesis: LiveForwardGenesisRecord,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    path = genesis_path(data_dir)
    if path.exists() and not allow_overwrite:
        raise ValueError("genesis_already_exists:immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(genesis.to_dict(), indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def validate_live_forward_prerequisites(
    target_trade_date: str,
    *,
    run_mode: str,
    policy_hashes: Dict[str, str],
    expected_policy_hashes: Optional[Dict[str, str]] = None,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str, List[str]]:
    """
    Pre-run validation for LIVE_FORWARD. Returns (ok, reason, checks).
    """
    checks: List[str] = []
    if run_mode != LIVE_FORWARD:
        return True, "not_live_forward", checks

    if run_mode in NON_FORWARD_MODES:
        return False, f"non_forward_mode:{run_mode}", checks

    genesis = load_genesis(data_dir)
    if genesis is None:
        return False, "genesis_missing", checks
    checks.append("genesis_exists")

    if target_trade_date < genesis.first_eligible_trade_date:
        return False, "target_before_genesis_first_eligible_date", checks
    checks.append("target_on_or_after_genesis")

    if expected_policy_hashes:
        for k, v in expected_policy_hashes.items():
            if genesis.policy_hashes.get(k) != v:
                return False, f"genesis_policy_hash_mismatch:{k}", checks
        checks.append("policy_hashes_match_expected")
    else:
        for k, v in genesis.policy_hashes.items():
            if policy_hashes.get(k) != v:
                return False, f"live_policy_hash_mismatch_genesis:{k}", checks
        checks.append("live_policy_hashes_match_genesis")

    return True, "ok", checks


def reject_backfill_promotion_after_genesis(
    proposed_mode: str,
    *,
    original_mode: str,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """CF-READY7 — BACKFILL cannot be promoted to LIVE_FORWARD after genesis."""
    if not genesis_exists(data_dir):
        return True, "no_genesis"
    if original_mode == BACKFILL_NON_FORWARD and proposed_mode == LIVE_FORWARD:
        return False, "backfill_promotion_to_live_forward_rejected"
    return True, "ok"


def reject_day0_smoke_promotion(run_mode: str) -> Tuple[bool, str]:
    """CF-READY6 — DAY_0_SMOKE cannot become LIVE_FORWARD."""
    if run_mode == DAY_0_SMOKE:
        return False, "day0_smoke_never_counts_as_forward"
    return True, "ok"


def reject_genesis_backward_move(
    existing: LiveForwardGenesisRecord,
    proposed_first_eligible: str,
) -> Tuple[bool, str]:
    """CF-READY8 — genesis cannot move backward."""
    if proposed_first_eligible < existing.first_eligible_trade_date:
        return False, "genesis_backward_move_rejected"
    return True, "ok"


def reject_second_genesis_creation(data_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """CF-READY19 — second genesis rejected."""
    if genesis_exists(data_dir):
        return False, "genesis_already_exists"
    return True, "ok"


def ensure_live_forward_genesis_once(
    *,
    first_eligible_trade_date: str,
    code_commit: str,
    deployment_identity: str,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    dataset_identities: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Idempotent go-live helper: create genesis if missing; never overwrite.

    Safe for deploy scripts. Does not run research. Does not mutate existing genesis.
    """
    if genesis_exists(data_dir):
        existing = load_genesis(data_dir)
        return {
            "ok": True,
            "created": False,
            "reason": "genesis_already_exists",
            "path": str(genesis_path(data_dir)),
            "first_eligible_trade_date": existing.first_eligible_trade_date if existing else None,
            "genesis_id": existing.genesis_id if existing else None,
        }
    root = repo_root or Path(__file__).resolve().parents[3]
    policy = compute_research_policy_hashes_safe(root)
    genesis = build_genesis_record(
        first_eligible_trade_date=first_eligible_trade_date,
        code_commit=code_commit,
        policy_hashes=policy,
        dataset_identities=dataset_identities or {"panel": "production"},
        deployment_identity=deployment_identity,
    )
    path = persist_genesis(genesis, data_dir=data_dir, allow_overwrite=False)
    return {
        "ok": True,
        "created": True,
        "reason": "genesis_created",
        "path": str(path),
        "first_eligible_trade_date": genesis.first_eligible_trade_date,
        "genesis_id": genesis.genesis_id,
        "genesis_hash": genesis.genesis_hash,
    }


def compute_research_policy_hashes_safe(repo_root: Path) -> Dict[str, str]:
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        compute_research_policy_hashes,
    )

    return compute_research_policy_hashes(repo_root)


def reject_non_forward_mode_as_live(run_mode: str) -> Tuple[bool, str]:
    if run_mode in (BACKFILL_NON_FORWARD, HISTORICAL_REPLAY_TEST, DAY_0_SMOKE, PRE_DEPLOYMENT_DRY_RUN):
        return False, f"mode_not_live_forward:{run_mode}"
    return True, "ok"


def _from_dict(d: Dict[str, Any]) -> LiveForwardGenesisRecord:
    return LiveForwardGenesisRecord(
        genesis_id=d["genesis_id"],
        activation_timestamp=d["activation_timestamp"],
        first_eligible_trade_date=d["first_eligible_trade_date"],
        code_commit=d["code_commit"],
        policy_hashes=dict(d.get("policy_hashes") or {}),
        dataset_identities=dict(d.get("dataset_identities") or {}),
        runtime_mode=d.get("runtime_mode", LIVE_FORWARD),
        timezone=d.get("timezone", "Asia/Ho_Chi_Minh"),
        authority_flags=dict(d.get("authority_flags") or {}),
        deployment_identity=d.get("deployment_identity", ""),
        genesis_hash=d.get("genesis_hash", ""),
    )
