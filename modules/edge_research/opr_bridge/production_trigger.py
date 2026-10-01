"""
Phase 3J.0 — Production autonomous OPR opportunity trigger.

Uses frozen OPR observation pipeline only — no new detector, no special-casing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.prioritized_pipeline import (
    PrioritizedOprPipelineResult,
    run_opr_pipeline_prioritized,
)
from modules.edge_research.opr_bridge.proposition_record import PropositionRecord

TRIGGER_VERSION = "production_opr_trigger_v1_3j0"


@dataclass
class ProductionOpportunityDetection:
    """Result of production-facing OPR opportunity scan."""

    trigger_version: str = TRIGGER_VERSION
    outcome: str = "SILENT"  # OPPORTUNITY_DETECTED | NO_ELIGIBLE_OBSERVATION | SILENT
    opportunity_identity: Optional[str] = None
    replay_identity: Optional[str] = None
    evidence_cutoff_hash: Optional[str] = None
    proposition_record: Optional[Dict[str, Any]] = None
    proposition_id: Optional[str] = None
    proposition_hash: Optional[str] = None
    pipeline_result: Optional[PrioritizedOprPipelineResult] = None
    silences: List[Dict[str, Any]] = field(default_factory=list)
    focal_dates_scanned: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_version": self.trigger_version,
            "outcome": self.outcome,
            "opportunity_identity": self.opportunity_identity,
            "replay_identity": self.replay_identity,
            "evidence_cutoff_hash": self.evidence_cutoff_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "silences": self.silences,
            "focal_dates_scanned": self.focal_dates_scanned,
            "propositions_emitted": 1 if self.proposition_record else 0,
        }


def compute_evidence_cutoff_hash(
    panel: pd.DataFrame,
    data_cutoff_date: str,
    focal_dates: List[str],
) -> str:
    """Deterministic replay identity from production-visible evidence boundary."""
    return stable_hash(
        {
            "data_cutoff_date": data_cutoff_date,
            "focal_dates": sorted(focal_dates),
            "row_count": len(panel),
            "columns": sorted(str(c) for c in panel.columns),
        }
    )


def compute_opportunity_identity(
    proposition_hash: str,
    data_cutoff_date: str,
    evidence_cutoff_hash: str,
) -> str:
    return stable_hash(
        {
            "proposition_hash": proposition_hash,
            "data_cutoff_date": data_cutoff_date,
            "evidence_cutoff_hash": evidence_cutoff_hash,
            "trigger_version": TRIGGER_VERSION,
        }
    )


def compute_replay_identity(
    opportunity_identity: str,
    session_id: str,
) -> str:
    return stable_hash({"opportunity_identity": opportunity_identity, "session_id": session_id})


def detect_production_opportunity(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    max_unique_propositions: int = 1,
) -> ProductionOpportunityDetection:
    """
    Smallest general production trigger: frozen prioritized OPR pipeline.

    No human invocation, no hidden benchmark, no known-edge encoding.
    """
    result = ProductionOpportunityDetection()
    pipeline = run_opr_pipeline_prioritized(
        panel,
        data_cutoff_date=data_cutoff_date,
        max_unique_propositions=max_unique_propositions,
        run_leakage=True,
    )
    result.pipeline_result = pipeline
    result.focal_dates_scanned = list(pipeline.focal_dates_scanned)
    result.silences = [s.to_dict() for s in pipeline.silences]

    if not pipeline.records:
        if pipeline.eligible_observations == 0:
            result.outcome = "NO_ELIGIBLE_OBSERVATION"
        else:
            result.outcome = "SILENT"
        return result

    record: PropositionRecord = pipeline.records[0]
    prop_dict = record.to_dict()
    prop_hash = proposition_content_hash(prop_dict)
    evidence_hash = compute_evidence_cutoff_hash(
        panel, data_cutoff_date, result.focal_dates_scanned
    )
    opp_id = compute_opportunity_identity(prop_hash, data_cutoff_date, evidence_hash)

    result.outcome = "OPPORTUNITY_DETECTED"
    result.proposition_record = prop_dict
    result.proposition_id = record.proposition_id
    result.proposition_hash = prop_hash
    result.evidence_cutoff_hash = evidence_hash
    result.opportunity_identity = opp_id
    return result


def new_production_session_id(proposition_id: str) -> str:
    return f"opr-prod-{proposition_id}-{new_id('sess')[:8]}"
