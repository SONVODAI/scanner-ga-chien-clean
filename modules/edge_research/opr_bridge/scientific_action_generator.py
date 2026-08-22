"""
Phase 3I.16 — Minimal Scientific Action Generator.

ResearchPriorityDecision + EvidenceSynthesisRecord + PropositionRecord
→ objectives → candidates → dedup → rank → NextActionPackage → STOP
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceLedgerEntry,
    EvidenceSynthesisRecord,
    ResearchPriorityDecision,
    stable_hash,
    utc_now_iso,
    new_id,
)
from modules.edge_research.opr_bridge.scientific_action_context import (
    ActionGenerationContext,
    ExecutabilityContext,
)
from modules.edge_research.opr_bridge.scientific_action_core import deduplicate_candidates
from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives
from modules.edge_research.opr_bridge.scientific_action_operators import (
    OPERATOR_REGISTRY,
    ensure_operators_registered,
    operator_set_hash,
)
from modules.edge_research.opr_bridge.scientific_action_records import (
    ActionDisposition,
    GENERATOR_VERSION,
    PACKAGE_RECORD_VERSION,
    NextActionPackage,
    ScientificActionCandidateRecord,
    ScientificObjectiveRecord,
    SELECTOR_VERSION,
)
from modules.edge_research.opr_bridge.scientific_action_selector import SelectionResult, select_scientific_action


@dataclass(frozen=True)
class GenerationResult:
    objectives: Tuple[ScientificObjectiveRecord, ...]
    candidates: Tuple[ScientificActionCandidateRecord, ...]
    deduplicated: Tuple[ScientificActionCandidateRecord, ...]
    selection: SelectionResult
    package: NextActionPackage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objectives": [o.to_dict() for o in self.objectives],
            "candidates": [c.to_dict() for c in self.candidates],
            "deduplicated_candidates": [c.to_dict() for c in self.deduplicated],
            "selection": self.selection.to_dict(),
            "package": self.package.to_dict(),
        }


def generator_content_hash() -> str:
    ensure_operators_registered()
    return stable_hash(
        {
            "generator_version": GENERATOR_VERSION,
            "selector_version": SELECTOR_VERSION,
            "operator_set_hash": operator_set_hash(),
        }
    )


def generate_scientific_actions(
    ctx: ActionGenerationContext,
) -> GenerationResult:
    """
    Main entry — consumes authoritative multi-evidence state only.
    Does NOT read ResearchDecisionRecord for authority.
    """
    ensure_operators_registered()

    objectives = generate_objectives(ctx)
    raw_candidates: List[ScientificActionCandidateRecord] = []

    for objective in objectives:
        for op in OPERATOR_REGISTRY.values():
            if op.applies_to(objective, ctx):
                raw_candidates.extend(op.propose(objective, ctx))

    deduped = deduplicate_candidates(raw_candidates)
    selection = select_scientific_action(deduped, objectives, ctx)
    package = _freeze_package(ctx, objectives, raw_candidates, deduped, selection)

    return GenerationResult(
        objectives=tuple(objectives),
        candidates=tuple(raw_candidates),
        deduplicated=tuple(deduped),
        selection=selection,
        package=package,
    )


def _candidate_set_hash(candidates: Sequence[ScientificActionCandidateRecord]) -> str:
    return stable_hash({"candidate_hashes": sorted(c.record_hash for c in candidates)})


def _freeze_package(
    ctx: ActionGenerationContext,
    objectives: Sequence[ScientificObjectiveRecord],
    all_candidates: Sequence[ScientificActionCandidateRecord],
    deduped: Sequence[ScientificActionCandidateRecord],
    selection: SelectionResult,
) -> NextActionPackage:
    gen_hash = generator_content_hash()
    op_hash = operator_set_hash()
    cset_hash = _candidate_set_hash(deduped)
    ts = ctx.synthesis.created_at or utc_now_iso()
    pid = new_id("nap")

    selected = selection.selected
    payload = {
        "record_version": PACKAGE_RECORD_VERSION,
        "proposition_id": ctx.proposition_id,
        "proposition_hash": ctx.proposition_hash,
        "synthesis_id": ctx.synthesis.synthesis_id,
        "synthesis_hash": ctx.synthesis.synthesis_hash,
        "priority_decision_id": ctx.priority.decision_id,
        "priority_record_hash": ctx.priority.record_hash,
        "disposition": selection.disposition.value,
        "candidate_set_hash": cset_hash,
        "generator_version": GENERATOR_VERSION,
        "generator_content_hash": gen_hash,
        "operator_set_hash": op_hash,
        "selector_version": SELECTOR_VERSION,
        "execution_status": "NOT_EXECUTED",
        "created_at": ts,
    }
    package_hash = stable_hash(payload)

    return NextActionPackage(
        package_id=pid,
        package_hash=package_hash,
        selected_objective=selection.selected_objective,
        selected_candidate=selected,
        selected_core_hash=selected.scientific_action_core_hash if selected else None,
        experiment_spec=selected.experiment_spec if selected else None,
        epistemic_consequence_contract=selected.epistemic_consequences.to_dict() if selected else None,
        cutoff_leakage_policy=f"data_cutoff_date={ctx.executability.data_cutoff}; no rows after cutoff",
        anti_rescue_constraints=("outcome_field", "horizon", "population_refine", "feature_change"),
        candidate_count=len(all_candidates),
        eligible_count=len(selection.eligible),
        **payload,
    )


def build_context_from_synthesis(
    proposition_spec: Dict[str, Any],
    proposition_record: Dict[str, Any],
    synthesis: EvidenceSynthesisRecord,
    priority: ResearchPriorityDecision,
    ledger_entries: List[EvidenceLedgerEntry],
    executability: ExecutabilityContext,
    evidence_specs: Optional[List[Dict[str, Any]]] = None,
) -> ActionGenerationContext:
    return ActionGenerationContext(
        proposition_spec=proposition_spec,
        proposition_record=proposition_record,
        synthesis=synthesis,
        priority=priority,
        ledger_entries=ledger_entries,
        executability=executability,
        evidence_specs=evidence_specs or [],
    )
