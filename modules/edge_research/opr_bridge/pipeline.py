"""
OPR pipeline orchestrator — research-only, isolated from planner/BUY/SELL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from modules.edge_research.opr_bridge.constants import MAX_PROPOSITIONS_PER_SESSION
from modules.edge_research.opr_bridge.evidence_ingest import (
    find_eligible_focal_dates,
    ingest_dispersion_evidence,
)
from modules.edge_research.opr_bridge.executability_adapter import ExecutabilityResult, adapt_executability
from modules.edge_research.opr_bridge.laundering_audit import LaunderingAuditResult, audit_laundering, replay_surprise_without_ontology
from modules.edge_research.opr_bridge.leakage_audit import LeakageAuditResult, run_leakage_audit
from modules.edge_research.opr_bridge.proposition_record import NoPropositionEmitted, PropositionRecord
from modules.edge_research.opr_bridge.proposition_synthesizer import synthesize_contrast_to_proposition
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise
from modules.edge_research.opr_bridge.template_independence import evaluate_template_independence


@dataclass
class OprPipelineResult:
    records: List[PropositionRecord] = field(default_factory=list)
    silences: List[NoPropositionEmitted] = field(default_factory=list)
    executability: List[ExecutabilityResult] = field(default_factory=list)
    laundering: List[LaunderingAuditResult] = field(default_factory=list)
    leakage_audit: Optional[LeakageAuditResult] = None
    eligible_observations: int = 0
    focal_dates_scanned: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "silences": [s.to_dict() for s in self.silences],
            "executability": [e.to_dict() for e in self.executability],
            "laundering": [l.to_dict() for l in self.laundering],
            "leakage_audit": self.leakage_audit.to_dict() if self.leakage_audit else None,
            "eligible_observations": self.eligible_observations,
            "focal_dates_scanned": self.focal_dates_scanned,
            "propositions_emitted": len(self.records),
            "silence_rate": (
                len(self.silences) / (len(self.silences) + len(self.records))
                if (self.silences or self.records)
                else 1.0
            ),
        }


def run_opr_pipeline(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    research_step: int = 0,
    focal_date: Optional[str] = None,
    max_propositions: int = MAX_PROPOSITIONS_PER_SESSION,
    run_leakage: bool = True,
) -> OprPipelineResult:
    """
    End-to-end minimal OPR: dispersion evidence → surprise → proposition → audits.

    Does NOT connect to planner, portfolio selection, or trading systems.
    """
    result = OprPipelineResult()
    if run_leakage:
        result.leakage_audit = run_leakage_audit()

    eligible = find_eligible_focal_dates(panel, data_cutoff_date=data_cutoff_date)
    result.eligible_observations = len(eligible)

    if focal_date:
        dates_to_scan = [focal_date] if focal_date in eligible else []
    else:
        dates_to_scan = eligible

    result.focal_dates_scanned = dates_to_scan

    emitted = 0
    for date in dates_to_scan:
        if emitted >= max_propositions:
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="BUDGET_EXHAUSTED",
                    detail=f"Max propositions {max_propositions} reached",
                )
            )
            break

        evidence = ingest_dispersion_evidence(
            panel, focal_date=date, data_cutoff_date=data_cutoff_date
        )
        if evidence is None:
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="INSUFFICIENT_GROUNDING",
                    detail=f"Could not ingest dispersion evidence for {date}",
                )
            )
            continue

        surprise = assess_dispersion_surprise(evidence)
        if not surprise.is_surprising:
            result.silences.append(
                NoPropositionEmitted(
                    reason_code="INSUFFICIENT_SURPRISE",
                    detail=surprise.surprise_basis_text,
                    evidence_hash=evidence.evidence_hash,
                )
            )
            continue

        record = synthesize_contrast_to_proposition(
            evidence, surprise, research_step=research_step
        )

        # Template independence AFTER synthesis — never modifies proposition
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
                    evidence_hash=evidence.evidence_hash,
                )
            )
            continue

        result.records.append(record)
        emitted += 1
        # One proposition per observation — no retry for novelty
        if focal_date:
            break

    return result
