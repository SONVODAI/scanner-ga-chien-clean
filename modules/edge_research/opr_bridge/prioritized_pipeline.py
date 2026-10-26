"""
Phase 3I.5 — Prioritized OPR pipeline.

Adds PRIORITIZE capability without modifying frozen opr_generator_v1_3i2 synthesizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.constants import MAX_PROPOSITIONS_PER_SESSION
from modules.edge_research.opr_bridge.evidence_ingest import (
    find_eligible_focal_dates,
    ingest_dispersion_evidence,
)
from modules.edge_research.opr_bridge.executability_adapter import ExecutabilityResult, adapt_executability
from modules.edge_research.opr_bridge.laundering_audit import LaunderingAuditResult, audit_laundering, replay_surprise_without_ontology
from modules.edge_research.opr_bridge.leakage_audit import LeakageAuditResult, run_leakage_audit
from modules.edge_research.opr_bridge.observation_entities import ObservationEvent, ScientificPropositionGroup
from modules.edge_research.opr_bridge.pipeline import OprPipelineResult
from modules.edge_research.opr_bridge.prioritization import PRIORITIZER_VERSION, prioritize_proposition_groups
from modules.edge_research.opr_bridge.proposition_record import NoPropositionEmitted, PropositionRecord
from modules.edge_research.opr_bridge.proposition_synthesizer import synthesize_contrast_to_proposition
from modules.edge_research.opr_bridge.scientific_identity import group_observation_events
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise
from modules.edge_research.opr_bridge.template_independence import evaluate_template_independence


@dataclass
class EvidenceLineage:
    """Append-only evidence lineage for an emitted proposition."""

    proposition_identity_key: str
    representative_focal_date: str
    representative_evidence_hash: str
    aggregated_evidence_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposition_identity_key": self.proposition_identity_key,
            "representative_focal_date": self.representative_focal_date,
            "representative_evidence_hash": self.representative_evidence_hash,
            "aggregated_evidence_events": self.aggregated_evidence_events,
            "independent_evidence_count": len(self.aggregated_evidence_events),
        }


@dataclass
class PrioritizedOprPipelineResult(OprPipelineResult):
    """Extended result with prioritization audit trail."""

    prioritizer_version: str = PRIORITIZER_VERSION
    observation_events_considered: int = 0
    surprising_observation_events: int = 0
    unique_proposition_groups: int = 0
    proposition_groups: List[ScientificPropositionGroup] = field(default_factory=list)
    evidence_lineages: List[EvidenceLineage] = field(default_factory=list)
    prioritization_audit: Optional[Dict[str, Any]] = None
    selection_mode: str = "PRIORITIZED"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "prioritizer_version": self.prioritizer_version,
                "selection_mode": self.selection_mode,
                "observation_events_considered": self.observation_events_considered,
                "surprising_observation_events": self.surprising_observation_events,
                "unique_proposition_groups": self.unique_proposition_groups,
                "proposition_groups": [g.to_dict() for g in self.proposition_groups],
                "evidence_lineages": [el.to_dict() for el in self.evidence_lineages],
                "prioritization_audit": self.prioritization_audit,
                "unique_propositions_emitted": len(self.records),
            }
        )
        return base


def _collect_observation_events(
    panel: pd.DataFrame,
    dates: List[str],
    data_cutoff_date: str,
) -> List[ObservationEvent]:
    events: List[ObservationEvent] = []
    for date in dates:
        evidence = ingest_dispersion_evidence(
            panel, focal_date=date, data_cutoff_date=data_cutoff_date
        )
        if evidence is None:
            continue
        surprise = assess_dispersion_surprise(evidence)
        events.append(
            ObservationEvent(
                focal_date=date,
                data_cutoff_date=data_cutoff_date,
                evidence=evidence,
                surprise=surprise,
            )
        )
    return events


def run_opr_pipeline_prioritized(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    research_step: int = 0,
    focal_date: Optional[str] = None,
    max_unique_propositions: int = MAX_PROPOSITIONS_PER_SESSION,
    run_leakage: bool = True,
) -> PrioritizedOprPipelineResult:
    """
    OPR pipeline with scientific-identity grouping and prioritization.

    Budget consumes unique scientific propositions, not observation dates.
    Frozen synthesizer unchanged — prioritization is orchestration-only.
    """
    result = PrioritizedOprPipelineResult()
    if run_leakage:
        result.leakage_audit = run_leakage_audit()

    eligible = find_eligible_focal_dates(panel, data_cutoff_date=data_cutoff_date)
    result.eligible_observations = len(eligible)

    if focal_date:
        dates_to_scan = [focal_date] if focal_date in eligible else []
    else:
        dates_to_scan = eligible

    result.focal_dates_scanned = dates_to_scan

    all_events = _collect_observation_events(panel, dates_to_scan, data_cutoff_date)
    result.observation_events_considered = len(all_events)

    surprising = [e for e in all_events if e.surprise.is_surprising]
    result.surprising_observation_events = len(surprising)

    for obs in all_events:
        if not obs.surprise.is_surprising:
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="INSUFFICIENT_SURPRISE",
                    detail=obs.surprise.surprise_basis_text,
                    evidence_hash=obs.evidence_hash,
                )
            )

    groups = group_observation_events(surprising)
    result.proposition_groups = groups
    result.unique_proposition_groups = len(groups)

    prioritization = prioritize_proposition_groups(
        groups, max_unique_propositions=max_unique_propositions
    )
    result.prioritization_audit = prioritization.to_dict()

    for silenced in prioritization.silenced_groups:
        result.silences.append(
            NoPropositionEmitted(
                reason_code=silenced["reason"],
                detail=f"Group {silenced['identity_key']} rank={silenced.get('rank_position')}",
            )
        )

    emitted_identities: set[str] = set()

    for group in prioritization.ranked_groups:
        rep = group.representative
        if rep is None:
            continue

        if group.identity_key in emitted_identities:
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="DUPLICATE_SCIENTIFIC_IDENTITY",
                    detail=f"Proposition group {group.identity_key} already emitted",
                    evidence_hash=rep.evidence_hash,
                )
            )
            continue

        record = synthesize_contrast_to_proposition(
            rep.evidence, rep.surprise, research_step=research_step
        )

        record.template_independence_audit = evaluate_template_independence(record)
        if result.leakage_audit:
            record.leakage_audit = result.leakage_audit.to_dict()

        exec_result = adapt_executability(record, panel)
        result.executability.append(exec_result)

        launder = audit_laundering(record, raw_evidence_produced=True)
        result.laundering.append(launder)

        if not replay_surprise_without_ontology(record):
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="LAUNDERING_FAILURE",
                    detail="Cannot replay surprise without ontology labels",
                    evidence_hash=rep.evidence_hash,
                )
            )
            continue

        lineage = EvidenceLineage(
            proposition_identity_key=group.identity_key,
            representative_focal_date=rep.focal_date,
            representative_evidence_hash=rep.evidence_hash,
            aggregated_evidence_events=[e.to_dict() for e in group.evidence_events],
        )
        result.evidence_lineages.append(lineage)
        result.records.append(record)
        emitted_identities.add(group.identity_key)

        for ev in group.evidence_events:
            if ev.observation_event.focal_date != rep.focal_date:
                result.silences.append(
                    NoPropositionEmitted(
                        reason_code="AGGREGATED_AS_EVIDENCE",
                        detail=(
                            f"Evidence for {group.identity_key} aggregated; "
                            f"representative={rep.focal_date}"
                        ),
                        evidence_hash=ev.observation_event.evidence_hash,
                    )
                )

    return result
