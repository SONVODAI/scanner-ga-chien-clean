"""
Frozen hypothesis specifications and scientific status model (PATCH 2A + Phase A).

FrozenHypothesisSpec is the immutable machine-readable contract used by
prospective OOS (Phase A) and, later, the Future Matcher (Phase B).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.contracts import (
    FEATURE_BUCKET_CONFIG_VERSION,
    FROZEN_SPEC_SCHEMA_VERSION,
    GUARDRAILS_CONFIG_VERSION,
    MARKET_STATE_CONFIG_VERSION,
    OOS_MODE_PROSPECTIVE_AFTER_FREEZE,
)


class ScientificStatus(str, Enum):
    RAW_DISCOVERY = "RAW_DISCOVERY"
    CANDIDATE = "CANDIDATE"
    FRAGILE = "FRAGILE"
    REJECTED = "REJECTED"
    READY_FOR_OOS = "READY_FOR_OOS"  # in-sample screening passed; OOS still required
    NO_EDGE_FOUND = "NO_EDGE_FOUND"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    NON_FREEZABLE = "NON_FREEZABLE"
    SPEC_FROZEN = "SPEC_FROZEN"
    OOS_PENDING = "OOS_PENDING"
    OOS_PASS = "OOS_PASS"
    OOS_FAIL = "OOS_FAIL"
    OOS_INCONCLUSIVE = "OOS_INCONCLUSIVE"


READY_FOR_OOS_MEANING = (
    "Survived current in-sample screening strongly enough to deserve frozen "
    "evaluation on unseen OOS data. RESEARCH ONLY — not a validated edge."
)

VALIDATED_EDGE_MEANING = (
    "Reusable/validated edge knowledge exists only as edge_memory status=ACTIVE "
    "after OOS_PASS. Challenger PASS, READY_FOR_OOS, SPEC_FROZEN, and OOS_PENDING "
    "are not validated."
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_feature_clauses(feature_clauses: Sequence[Any]) -> List[Dict[str, Any]]:
    """Normalize ALL clauses (not only feature_1/2) for identity and persistence."""
    normalized: List[Dict[str, Any]] = []
    for raw in feature_clauses or ():
        if hasattr(raw, "feature"):
            item = {
                "feature": str(getattr(raw, "feature", "")),
                "operator": str(getattr(raw, "operator", "")),
                "threshold_lo": getattr(raw, "threshold_lo", None),
                "threshold_hi": getattr(raw, "threshold_hi", None),
                "bucket_id": str(getattr(raw, "bucket_id", "")),
            }
        elif isinstance(raw, dict):
            item = {
                "feature": str(raw.get("feature", "")),
                "operator": str(raw.get("operator", "")),
                "threshold_lo": raw.get("threshold_lo", raw.get("threshold")),
                "threshold_hi": raw.get("threshold_hi", raw.get("threshold")),
                "bucket_id": str(raw.get("bucket_id", "")),
            }
            if "threshold" in raw and raw.get("operator") == "<=":
                item["threshold_lo"] = None
                item["threshold_hi"] = raw.get("threshold")
            elif "threshold" in raw and raw.get("operator") == ">":
                item["threshold_lo"] = raw.get("threshold")
                item["threshold_hi"] = None
        else:
            continue
        normalized.append(item)
    normalized.sort(key=lambda c: (c.get("feature", ""), c.get("bucket_id", ""), c.get("operator", "")))
    return normalized


def _identity_payload(
    *,
    condition_key: str,
    condition_text: str,
    market_transition: str,
    market_state: str,
    feature_clauses: Sequence[Any],
    best_horizon: str,
    baseline_type: str = "",
    feature_bucket_config_version: str = "",
    market_state_config_version: str = "",
    guardrails_config_version: str = "",
) -> Dict[str, Any]:
    return {
        "condition_key": condition_key,
        "condition_text": condition_text,
        "market_transition": market_transition,
        "market_state": market_state,
        "feature_clauses": canonical_feature_clauses(feature_clauses),
        "best_horizon": best_horizon,
        "baseline_type": baseline_type,
        "feature_bucket_config_version": feature_bucket_config_version,
        "market_state_config_version": market_state_config_version,
        "guardrails_config_version": guardrails_config_version,
    }


@dataclass(frozen=True)
class FrozenHypothesisSpec:
    """Immutable hypothesis specification for OOS evaluation and future matching."""

    hypothesis_id: str
    condition_key: str
    condition_text: str
    market_transition: str
    market_state: str
    feature_clauses: Tuple[Dict[str, Any], ...]
    best_horizon: str
    discovery_run_id: str
    discovery_evidence: Dict[str, Any]
    challenger_status: str
    guardrails_summary: Dict[str, Any]
    data_cutoff_date: str
    freeze_timestamp: str
    guardrails_config_version: str
    spec_schema_version: str = FROZEN_SPEC_SCHEMA_VERSION
    edge_id: str = ""
    baseline_type: str = ""
    discovery_start_date: str = ""
    discovery_end_date: str = ""
    challenger_research_cutoff: str = ""
    feature_bucket_config_version: str = FEATURE_BUCKET_CONFIG_VERSION
    market_state_config_version: str = MARKET_STATE_CONFIG_VERSION
    challenger_run_id: str = ""
    frozen_at: str = ""
    spec_hash: str = ""
    oos_mode: str = OOS_MODE_PROSPECTIVE_AFTER_FREEZE
    oos_start_date: str = ""
    embargo_trading_sessions: int = 10
    holdout_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        frozen_at = self.frozen_at or self.freeze_timestamp
        return {
            "spec_schema_version": self.spec_schema_version,
            "hypothesis_id": self.hypothesis_id,
            "edge_id": self.edge_id,
            "condition_key": self.condition_key,
            "condition_text": self.condition_text,
            "market_transition": self.market_transition,
            "market_state": self.market_state,
            "baseline_type": self.baseline_type,
            "feature_clauses": canonical_feature_clauses(self.feature_clauses),
            "best_horizon": self.best_horizon,
            "discovery_run_id": self.discovery_run_id,
            "challenger_run_id": self.challenger_run_id,
            "discovery_evidence": self.discovery_evidence,
            "challenger_status": self.challenger_status,
            "guardrails_summary": self.guardrails_summary,
            "discovery_start_date": self.discovery_start_date,
            "discovery_end_date": self.discovery_end_date,
            "challenger_research_cutoff": self.challenger_research_cutoff or self.data_cutoff_date,
            "data_cutoff_date": self.data_cutoff_date,
            "freeze_timestamp": self.freeze_timestamp,
            "frozen_at": frozen_at,
            "guardrails_config_version": self.guardrails_config_version,
            "feature_bucket_config_version": self.feature_bucket_config_version,
            "market_state_config_version": self.market_state_config_version,
            "spec_hash": self.spec_hash,
            "oos_mode": self.oos_mode,
            "oos_start_date": self.oos_start_date,
            "embargo_trading_sessions": int(self.embargo_trading_sessions),
            "holdout_applied": bool(self.holdout_applied),
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, default=str)

    def canonical_identity_json(self) -> str:
        return json.dumps(
            _identity_payload(
                condition_key=self.condition_key,
                condition_text=self.condition_text,
                market_transition=self.market_transition,
                market_state=self.market_state,
                feature_clauses=self.feature_clauses,
                best_horizon=self.best_horizon,
                baseline_type=self.baseline_type,
                feature_bucket_config_version=self.feature_bucket_config_version,
                market_state_config_version=self.market_state_config_version,
                guardrails_config_version=self.guardrails_config_version,
            ),
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FrozenHypothesisSpec":
        freeze_ts = str(payload.get("freeze_timestamp") or payload.get("frozen_at") or "")
        return cls(
            hypothesis_id=str(payload["hypothesis_id"]),
            condition_key=str(payload["condition_key"]),
            condition_text=str(payload["condition_text"]),
            market_transition=str(payload["market_transition"]),
            market_state=str(payload["market_state"]),
            feature_clauses=tuple(canonical_feature_clauses(payload.get("feature_clauses") or ())),
            best_horizon=str(payload["best_horizon"]),
            discovery_run_id=str(payload.get("discovery_run_id", "")),
            discovery_evidence=dict(payload.get("discovery_evidence") or {}),
            challenger_status=str(payload.get("challenger_status", "")),
            guardrails_summary=dict(payload.get("guardrails_summary") or {}),
            data_cutoff_date=str(payload.get("data_cutoff_date", "")),
            freeze_timestamp=freeze_ts,
            guardrails_config_version=str(
                payload.get("guardrails_config_version") or GUARDRAILS_CONFIG_VERSION
            ),
            spec_schema_version=str(
                payload.get("spec_schema_version") or FROZEN_SPEC_SCHEMA_VERSION
            ),
            edge_id=str(payload.get("edge_id", "")),
            baseline_type=str(payload.get("baseline_type", "")),
            discovery_start_date=str(payload.get("discovery_start_date", "")),
            discovery_end_date=str(payload.get("discovery_end_date", "")),
            challenger_research_cutoff=str(
                payload.get("challenger_research_cutoff") or payload.get("data_cutoff_date") or ""
            ),
            feature_bucket_config_version=str(
                payload.get("feature_bucket_config_version") or FEATURE_BUCKET_CONFIG_VERSION
            ),
            market_state_config_version=str(
                payload.get("market_state_config_version") or MARKET_STATE_CONFIG_VERSION
            ),
            challenger_run_id=str(payload.get("challenger_run_id", "")),
            frozen_at=str(payload.get("frozen_at") or freeze_ts),
            spec_hash=str(payload.get("spec_hash", "")),
            oos_mode=str(payload.get("oos_mode") or OOS_MODE_PROSPECTIVE_AFTER_FREEZE),
            oos_start_date=str(payload.get("oos_start_date", "")),
            embargo_trading_sessions=int(payload.get("embargo_trading_sessions") or 10),
            holdout_applied=bool(payload.get("holdout_applied", False)),
        )


def spec_hash_from_dict(payload: Dict[str, Any]) -> str:
    """Deterministic hash of the frozen contract excluding the hash field itself."""
    body = dict(payload)
    body.pop("spec_hash", None)
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hypothesis_id_from_spec(spec: FrozenHypothesisSpec) -> str:
    """Deterministic hypothesis identifier from immutable scientific identity fields."""
    return hashlib.sha256(spec.canonical_identity_json().encode("utf-8")).hexdigest()[:16]


def build_frozen_hypothesis_spec(
    *,
    condition_key: str,
    condition_text: str,
    market_transition: str,
    market_state: str,
    feature_clauses: Sequence[Any],
    best_horizon: str,
    discovery_run_id: str,
    discovery_evidence: Dict[str, Any],
    challenger_status: str,
    guardrails_summary: Dict[str, Any],
    data_cutoff_date: str,
    guardrails_config_version: str,
    freeze_timestamp: Optional[str] = None,
    edge_id: str = "",
    baseline_type: str = "",
    discovery_start_date: str = "",
    discovery_end_date: str = "",
    challenger_research_cutoff: str = "",
    feature_bucket_config_version: str = FEATURE_BUCKET_CONFIG_VERSION,
    market_state_config_version: str = MARKET_STATE_CONFIG_VERSION,
    challenger_run_id: str = "",
    oos_mode: str = OOS_MODE_PROSPECTIVE_AFTER_FREEZE,
    oos_start_date: str = "",
    embargo_trading_sessions: int = 10,
    holdout_applied: bool = False,
    spec_schema_version: str = FROZEN_SPEC_SCHEMA_VERSION,
) -> FrozenHypothesisSpec:
    ts = freeze_timestamp or _iso_now()
    clauses = tuple(canonical_feature_clauses(feature_clauses))
    provisional = FrozenHypothesisSpec(
        hypothesis_id="",
        condition_key=condition_key,
        condition_text=condition_text,
        market_transition=market_transition,
        market_state=market_state,
        feature_clauses=clauses,
        best_horizon=best_horizon,
        discovery_run_id=discovery_run_id,
        discovery_evidence=dict(discovery_evidence or {}),
        challenger_status=challenger_status,
        guardrails_summary=dict(guardrails_summary or {}),
        data_cutoff_date=data_cutoff_date,
        freeze_timestamp=ts,
        guardrails_config_version=guardrails_config_version,
        spec_schema_version=spec_schema_version,
        edge_id=edge_id,
        baseline_type=baseline_type,
        discovery_start_date=discovery_start_date,
        discovery_end_date=discovery_end_date or data_cutoff_date,
        challenger_research_cutoff=challenger_research_cutoff or data_cutoff_date,
        feature_bucket_config_version=feature_bucket_config_version,
        market_state_config_version=market_state_config_version,
        challenger_run_id=challenger_run_id,
        frozen_at=ts,
        spec_hash="",
        oos_mode=oos_mode,
        oos_start_date=oos_start_date,
        embargo_trading_sessions=int(embargo_trading_sessions),
        holdout_applied=bool(holdout_applied),
    )
    hid = hypothesis_id_from_spec(provisional)
    with_id = FrozenHypothesisSpec(
        hypothesis_id=hid,
        condition_key=provisional.condition_key,
        condition_text=provisional.condition_text,
        market_transition=provisional.market_transition,
        market_state=provisional.market_state,
        feature_clauses=provisional.feature_clauses,
        best_horizon=provisional.best_horizon,
        discovery_run_id=provisional.discovery_run_id,
        discovery_evidence=provisional.discovery_evidence,
        challenger_status=provisional.challenger_status,
        guardrails_summary=provisional.guardrails_summary,
        data_cutoff_date=provisional.data_cutoff_date,
        freeze_timestamp=provisional.freeze_timestamp,
        guardrails_config_version=provisional.guardrails_config_version,
        spec_schema_version=provisional.spec_schema_version,
        edge_id=provisional.edge_id,
        baseline_type=provisional.baseline_type,
        discovery_start_date=provisional.discovery_start_date,
        discovery_end_date=provisional.discovery_end_date,
        challenger_research_cutoff=provisional.challenger_research_cutoff,
        feature_bucket_config_version=provisional.feature_bucket_config_version,
        market_state_config_version=provisional.market_state_config_version,
        challenger_run_id=provisional.challenger_run_id,
        frozen_at=provisional.frozen_at,
        spec_hash="",
        oos_mode=provisional.oos_mode,
        oos_start_date=provisional.oos_start_date,
        embargo_trading_sessions=provisional.embargo_trading_sessions,
        holdout_applied=provisional.holdout_applied,
    )
    digest = spec_hash_from_dict(with_id.to_dict())
    return FrozenHypothesisSpec(
        hypothesis_id=hid,
        condition_key=with_id.condition_key,
        condition_text=with_id.condition_text,
        market_transition=with_id.market_transition,
        market_state=with_id.market_state,
        feature_clauses=with_id.feature_clauses,
        best_horizon=with_id.best_horizon,
        discovery_run_id=with_id.discovery_run_id,
        discovery_evidence=with_id.discovery_evidence,
        challenger_status=with_id.challenger_status,
        guardrails_summary=with_id.guardrails_summary,
        data_cutoff_date=with_id.data_cutoff_date,
        freeze_timestamp=with_id.freeze_timestamp,
        guardrails_config_version=with_id.guardrails_config_version,
        spec_schema_version=with_id.spec_schema_version,
        edge_id=with_id.edge_id,
        baseline_type=with_id.baseline_type,
        discovery_start_date=with_id.discovery_start_date,
        discovery_end_date=with_id.discovery_end_date,
        challenger_research_cutoff=with_id.challenger_research_cutoff,
        feature_bucket_config_version=with_id.feature_bucket_config_version,
        market_state_config_version=with_id.market_state_config_version,
        challenger_run_id=with_id.challenger_run_id,
        frozen_at=with_id.frozen_at,
        spec_hash=digest,
        oos_mode=with_id.oos_mode,
        oos_start_date=with_id.oos_start_date,
        embargo_trading_sessions=with_id.embargo_trading_sessions,
        holdout_applied=with_id.holdout_applied,
    )


def derive_scientific_status(
    *,
    raw_signal: bool,
    multiple_testing_survives: bool,
    robustness_status: str,
    concentration_fragile: bool,
    episode_consistency: str,
) -> ScientificStatus:
    """
    Map in-sample evidence to research status.

    READY_FOR_OOS means the hypothesis cleared current in-sample screening and
    robustness checks sufficiently to warrant frozen OOS evaluation — NOT that an
    edge is validated. FDR survival alone never yields READY_FOR_OOS.
    """
    if not raw_signal:
        return ScientificStatus.NO_EDGE_FOUND
    if not multiple_testing_survives:
        return ScientificStatus.RAW_DISCOVERY
    if robustness_status == "REJECT":
        return ScientificStatus.REJECTED
    if robustness_status == "FRAGILE" or concentration_fragile:
        return ScientificStatus.FRAGILE
    if episode_consistency in ("INSUFFICIENT_EPISODES", "INCONSISTENT"):
        return ScientificStatus.FRAGILE
    if robustness_status == "PASS":
        return ScientificStatus.READY_FOR_OOS
    return ScientificStatus.CANDIDATE
