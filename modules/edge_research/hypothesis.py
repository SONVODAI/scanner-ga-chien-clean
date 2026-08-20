"""
Frozen hypothesis specifications and scientific status model (PATCH 2A).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class ScientificStatus(str, Enum):
    RAW_DISCOVERY = "RAW_DISCOVERY"
    CANDIDATE = "CANDIDATE"
    FRAGILE = "FRAGILE"
    REJECTED = "REJECTED"
    READY_FOR_OOS = "READY_FOR_OOS"  # in-sample screening passed; OOS still required
    NO_EDGE_FOUND = "NO_EDGE_FOUND"


READY_FOR_OOS_MEANING = (
    "Survived current in-sample screening strongly enough to deserve frozen "
    "evaluation on unseen OOS data. RESEARCH ONLY — not a validated edge."
)


@dataclass(frozen=True)
class FrozenHypothesisSpec:
    """Immutable hypothesis specification for future OOS evaluation."""

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "condition_key": self.condition_key,
            "condition_text": self.condition_text,
            "market_transition": self.market_transition,
            "market_state": self.market_state,
            "feature_clauses": list(self.feature_clauses),
            "best_horizon": self.best_horizon,
            "discovery_run_id": self.discovery_run_id,
            "discovery_evidence": self.discovery_evidence,
            "challenger_status": self.challenger_status,
            "guardrails_summary": self.guardrails_summary,
            "data_cutoff_date": self.data_cutoff_date,
            "freeze_timestamp": self.freeze_timestamp,
            "guardrails_config_version": self.guardrails_config_version,
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FrozenHypothesisSpec":
        return cls(
            hypothesis_id=str(payload["hypothesis_id"]),
            condition_key=str(payload["condition_key"]),
            condition_text=str(payload["condition_text"]),
            market_transition=str(payload["market_transition"]),
            market_state=str(payload["market_state"]),
            feature_clauses=tuple(payload.get("feature_clauses") or ()),
            best_horizon=str(payload["best_horizon"]),
            discovery_run_id=str(payload.get("discovery_run_id", "")),
            discovery_evidence=dict(payload.get("discovery_evidence") or {}),
            challenger_status=str(payload.get("challenger_status", "")),
            guardrails_summary=dict(payload.get("guardrails_summary") or {}),
            data_cutoff_date=str(payload.get("data_cutoff_date", "")),
            freeze_timestamp=str(payload.get("freeze_timestamp", "")),
            guardrails_config_version=str(payload.get("guardrails_config_version", "")),
        )


def hypothesis_id_from_spec(spec: FrozenHypothesisSpec) -> str:
    """Deterministic hypothesis identifier from immutable spec fields."""
    canonical = json.dumps(
        {
            "condition_key": spec.condition_key,
            "condition_text": spec.condition_text,
            "market_transition": spec.market_transition,
            "market_state": spec.market_state,
            "feature_clauses": list(spec.feature_clauses),
            "best_horizon": spec.best_horizon,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_frozen_hypothesis_spec(
    *,
    condition_key: str,
    condition_text: str,
    market_transition: str,
    market_state: str,
    feature_clauses: Sequence[Dict[str, Any]],
    best_horizon: str,
    discovery_run_id: str,
    discovery_evidence: Dict[str, Any],
    challenger_status: str,
    guardrails_summary: Dict[str, Any],
    data_cutoff_date: str,
    guardrails_config_version: str,
    freeze_timestamp: Optional[str] = None,
) -> FrozenHypothesisSpec:
    ts = freeze_timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provisional = FrozenHypothesisSpec(
        hypothesis_id="",
        condition_key=condition_key,
        condition_text=condition_text,
        market_transition=market_transition,
        market_state=market_state,
        feature_clauses=tuple(feature_clauses),
        best_horizon=best_horizon,
        discovery_run_id=discovery_run_id,
        discovery_evidence=discovery_evidence,
        challenger_status=challenger_status,
        guardrails_summary=guardrails_summary,
        data_cutoff_date=data_cutoff_date,
        freeze_timestamp=ts,
        guardrails_config_version=guardrails_config_version,
    )
    hid = hypothesis_id_from_spec(provisional)
    return FrozenHypothesisSpec(
        hypothesis_id=hid,
        condition_key=condition_key,
        condition_text=condition_text,
        market_transition=market_transition,
        market_state=market_state,
        feature_clauses=tuple(feature_clauses),
        best_horizon=best_horizon,
        discovery_run_id=discovery_run_id,
        discovery_evidence=discovery_evidence,
        challenger_status=challenger_status,
        guardrails_summary=guardrails_summary,
        data_cutoff_date=data_cutoff_date,
        freeze_timestamp=ts,
        guardrails_config_version=guardrails_config_version,
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
