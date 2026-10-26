"""
Phase 3H.13 — Semantic novelty rank reconciliation bridge.

Reconciles planner-level raw novelty (embedded in base_score) with the
existing 3H.11 semantic valuation so effective candidate rank reflects
one semantic novelty determination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from modules.edge_research.research_novelty_valuation_bridge import (
    NoveltyGatingAudit,
    gate_novelty_component,
)

RESEARCH_NOVELTY_RANK_RECONCILIATION_VERSION = "research_novelty_rank_reconciliation_v1"


@dataclass(frozen=True)
class RankReconciliationAudit:
    version: str
    action_id: str
    valuation_class: str
    raw_planner_novelty: float
    gated_planner_novelty: float
    planner_novelty_delta: float
    base_score_before: float
    base_score_after: float
    reconciliation_applied: bool
    component_explanation: str
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "action_id": self.action_id,
            "valuation_class": self.valuation_class,
            "raw_planner_novelty": self.raw_planner_novelty,
            "gated_planner_novelty": self.gated_planner_novelty,
            "planner_novelty_delta": self.planner_novelty_delta,
            "base_score_before": self.base_score_before,
            "base_score_after": self.base_score_after,
            "reconciliation_applied": self.reconciliation_applied,
            "component_explanation": self.component_explanation,
            "built_at": self.built_at,
        }


def reconcile_planner_novelty_in_base_score(
    base_score: float,
    raw_planner_novelty: float,
    gating_audit: NoveltyGatingAudit,
) -> Tuple[float, RankReconciliationAudit]:
    """
    Replace raw planner novelty in base_score with semantically gated value.

    Uses the same valuation_class from 3H.11 — no second classifier.
    Zero means removal of novelty bonus, never a penalty.
    """
    raw = max(0.0, float(raw_planner_novelty))
    gated = gate_novelty_component(raw, valuation_class=gating_audit.valuation_class)
    reconciled = float(base_score) - raw + gated
    applied = gated != raw

    explanation = (
        f"Planner novelty reconciled: {raw:.4f} -> {gated:.4f} "
        f"({gating_audit.valuation_class})"
        if applied
        else f"Planner novelty preserved ({gating_audit.valuation_class})"
    )

    audit = RankReconciliationAudit(
        version=RESEARCH_NOVELTY_RANK_RECONCILIATION_VERSION,
        action_id=gating_audit.action_id,
        valuation_class=gating_audit.valuation_class,
        raw_planner_novelty=raw,
        gated_planner_novelty=gated,
        planner_novelty_delta=gated - raw,
        base_score_before=float(base_score),
        base_score_after=reconciled,
        reconciliation_applied=applied,
        component_explanation=explanation,
    )
    return reconciled, audit


def record_rank_reconciliation_audit(graph: Any, audit: RankReconciliationAudit) -> None:
    trail = list(getattr(graph.session, "research_rank_reconciliation_audit", None) or [])
    trail.append(audit.to_dict())
    graph.session.research_rank_reconciliation_audit = trail[-300:]
