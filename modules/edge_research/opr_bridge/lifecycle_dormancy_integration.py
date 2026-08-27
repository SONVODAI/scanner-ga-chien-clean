"""
Phase 3I.20 — Automatic research dormancy & reopening lifecycle integration.

Wires frozen 3I.18 frontier + 3I.19 dormancy into append-only lifecycle lineage.
Does NOT generate, select, or execute experiments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.dormancy_deriver import derive_dormancy_record, should_enter_dormancy
from modules.edge_research.opr_bridge.dormancy_records import (
    DORMANCY_VERSION,
    ResearchActivityTransition,
    ResearchDormancyRecord,
    ReopeningEvaluationOutcome,
    ReopeningEvaluationRecord,
    ReopeningEvaluationResult,
    dormancy_content_hash,
)
from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import (
    CurrentResearchSnapshot,
    DormantResearchReopeningEvaluator,
    ResearchOpportunityDescriptor,
)
from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
from modules.edge_research.opr_bridge.evidence_ledger_builder import build_ledger_specs_from_events, proposition_spec_from_record
from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.frontier_records import FrontierDecision, FrontierReassessmentResult
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import (
    AUTHORITY_DORMANCY,
    AUTHORITY_FRONTIER,
    AUTHORITY_REOPENING,
    LifecycleKnowledgeState,
    SynthesisIntegrationOutcome,
)
from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext, ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor
from modules.edge_research.opr_bridge.synthesis_integration import FROZEN_ENGINE_HASH, verify_frozen_engine_integrity

INTEGRATION_VERSION = "lifecycle_dormancy_integration_v1_3i20"

TERMINAL_EPISTEMIC_STATES = frozenset({"FALSIFIED", "ABANDONED"})


@dataclass
class ResearchOpportunityState:
    """
    Pre-result scientific opportunity structure.
    No outcome attractiveness, profitability, or ToolResult.
    """

    proposition_id: str
    proposition_hash: str
    available_operators: Set[str] = field(default_factory=set)
    max_cohort_overlap: Optional[float] = None
    overlap_relation_to_prior: str = "unknown"
    additional_row_count: int = 0
    context_values_renamed: bool = False
    identical_evidence_added: bool = False
    newly_available_operators: Set[str] = field(default_factory=set)
    restored_executability_for: Set[str] = field(default_factory=set)
    feature_changed: bool = False
    outcome_changed: bool = False
    horizon_changed: bool = False
    population_claim_changed: bool = False
    proposition_hash_changed: bool = False
    resolved_uncertainties: Set[str] = field(default_factory=set)
    outcome_profitability_signal: bool = False
    future_return_magnitude_signal: bool = False
    zone_c_match: bool = False
    human_review_request: bool = False
    subgroup_outcome_mining: bool = False
    known_hidden_edge: bool = False
    clock_elapsed_days: int = 0
    schema_version: str = INTEGRATION_VERSION
    operator_set_version: str = ""

    def content_hash(self) -> str:
        payload = {
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "max_cohort_overlap": self.max_cohort_overlap,
            "overlap_relation": self.overlap_relation_to_prior,
            "additional_rows": self.additional_row_count,
            "context_renamed": self.context_values_renamed,
            "identical_evidence": self.identical_evidence_added,
            "new_ops": sorted(self.newly_available_operators),
            "restored": sorted(self.restored_executability_for),
            "semantic_change": (
                self.feature_changed,
                self.outcome_changed,
                self.horizon_changed,
                self.population_claim_changed,
                self.proposition_hash_changed,
            ),
            "resolved": sorted(self.resolved_uncertainties),
            "forbidden_signals": (
                self.outcome_profitability_signal,
                self.future_return_magnitude_signal,
                self.zone_c_match,
                self.subgroup_outcome_mining,
                self.known_hidden_edge,
            ),
            "clock_days": self.clock_elapsed_days,
            "schema": self.schema_version,
        }
        return stable_hash(payload)

    def to_descriptor(self) -> ResearchOpportunityDescriptor:
        return ResearchOpportunityDescriptor(
            new_evidence_overlap=self.max_cohort_overlap,
            overlap_relation_to_prior=self.overlap_relation_to_prior,
            additional_row_count=self.additional_row_count,
            context_values_renamed=self.context_values_renamed,
            identical_evidence_added=self.identical_evidence_added,
            newly_available_operators=set(self.newly_available_operators),
            restored_executability_for=set(self.restored_executability_for),
            proposition_hash_changed=self.proposition_hash_changed,
            feature_changed=self.feature_changed,
            outcome_changed=self.outcome_changed,
            horizon_changed=self.horizon_changed,
            population_claim_changed=self.population_claim_changed,
            outcome_profitability_signal=self.outcome_profitability_signal,
            future_return_magnitude_signal=self.future_return_magnitude_signal,
            zone_c_match=self.zone_c_match,
            human_review_request=self.human_review_request,
            subgroup_outcome_mining=self.subgroup_outcome_mining,
            known_hidden_edge=self.known_hidden_edge,
            clock_elapsed_days=self.clock_elapsed_days,
            resolved_uncertainties=set(self.resolved_uncertainties),
            trigger_source=self.content_hash(),
        )


@dataclass(frozen=True)
class DormancyHookOutcome:
    status: str  # SUCCESS | SKIPPED | FAILED
    dormancy_record: Optional[ResearchDormancyRecord]
    idempotent_skip: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "idempotent_skip": self.idempotent_skip,
            "error": self.error,
            "dormancy_record": self.dormancy_record.to_dict() if self.dormancy_record else None,
        }


@dataclass(frozen=True)
class ReopeningHookOutcome:
    status: str  # SUCCESS | SKIPPED | FAILED
    evaluation_record: Optional[ReopeningEvaluationRecord]
    evaluation_result: Optional[ReopeningEvaluationResult]
    idempotent_skip: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "idempotent_skip": self.idempotent_skip,
            "error": self.error,
            "evaluation_record": self.evaluation_record.to_dict() if self.evaluation_record else None,
            "outcome": self.evaluation_result.outcome.value if self.evaluation_result else None,
        }


@dataclass(frozen=True)
class FrontierPipelineOutcome:
    frontier: FrontierReassessmentResult
    dormancy: DormancyHookOutcome
    research_activity_state: str
    epistemic_state: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frontier_decision": self.frontier.frontier_decision.value,
            "research_activity_state": self.research_activity_state,
            "epistemic_state": self.epistemic_state,
            "dormancy": self.dormancy.to_dict(),
        }


def _dormancy_idempotency_key(synthesis_hash: str, frontier_hash: str) -> str:
    return stable_hash({"synthesis_hash": synthesis_hash, "frontier_hash": frontier_hash})


def _rehydrate_dormancy(record_dict: Dict[str, Any]) -> ResearchDormancyRecord:
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningConditionRecord

    conditions = tuple(
        ReopeningConditionRecord(
            condition_id=c["condition_id"],
            target_uncertainty=c["target_uncertainty"],
            blocking_reason=c["blocking_reason"],
            required_scientific_change=c["required_scientific_change"],
            measurable_criterion=dict(c["measurable_criterion"]),
            independence_requirement=c["independence_requirement"],
            minimum_semantic_continuity=c["minimum_semantic_continuity"],
            does_not_qualify=tuple(c["does_not_qualify"]),
            provenance=tuple(c["provenance"]),
            record_hash=c["record_hash"],
        )
        for c in record_dict.get("reopening_conditions", [])
    )
    return ResearchDormancyRecord(
        dormancy_id=record_dict["dormancy_id"],
        record_version=record_dict["record_version"],
        proposition_id=record_dict["proposition_id"],
        proposition_hash=record_dict["proposition_hash"],
        synthesis_hash=record_dict["synthesis_hash"],
        frontier_assessment_hash=record_dict["frontier_assessment_hash"],
        epistemic_state_at_dormancy=record_dict["epistemic_state_at_dormancy"],
        research_activity_state=record_dict["research_activity_state"],
        dormancy_trigger=record_dict["dormancy_trigger"],
        unresolved_uncertainties=tuple(record_dict["unresolved_uncertainties"]),
        blocked_axes=tuple(record_dict["blocked_axes"]),
        redundant_axes=tuple(record_dict["redundant_axes"]),
        dormancy_reason=record_dict["dormancy_reason"],
        evidence_coverage=tuple(record_dict["evidence_coverage"]),
        independence_limitations=tuple(record_dict["independence_limitations"]),
        reopening_conditions=conditions,
        forbidden_reopening_triggers=tuple(record_dict["forbidden_reopening_triggers"]),
        created_at=record_dict["created_at"],
        record_hash=record_dict["record_hash"],
    )


def _rehydrate_synthesis(syn_dict: Dict[str, Any]):
    from modules.edge_research.opr_bridge.evidence_synthesis_records import EvidenceSynthesisRecord

    return EvidenceSynthesisRecord(
        synthesis_id=syn_dict["synthesis_id"],
        proposition_id=syn_dict["proposition_id"],
        proposition_hash=syn_dict["proposition_hash"],
        evidence_ids=tuple(syn_dict["evidence_ids"]),
        evidence_hashes=tuple(syn_dict["evidence_hashes"]),
        relationship_map=dict(syn_dict["relationship_map"]),
        independence_profiles=dict(syn_dict["independence_profiles"]),
        supporting_structure=list(syn_dict["supporting_structure"]),
        disconfirming_structure=list(syn_dict["disconfirming_structure"]),
        contradiction_structure=list(syn_dict["contradiction_structure"]),
        invalid_non_informative=list(syn_dict["invalid_non_informative"]),
        uncertainty_covered=tuple(syn_dict["uncertainty_covered"]),
        uncertainty_unresolved=tuple(syn_dict["uncertainty_unresolved"]),
        saturation_assessment=dict(syn_dict["saturation_assessment"]),
        synthesized_epistemic_state=syn_dict["synthesized_epistemic_state"],
        prior_epistemic_state=syn_dict["prior_epistemic_state"],
        scientific_rationale=tuple(syn_dict["scientific_rationale"]),
        counterfactual_causality_refs=tuple(syn_dict.get("counterfactual_causality_refs", [])),
        synthesis_engine_version=syn_dict["synthesis_engine_version"],
        created_at=syn_dict["created_at"],
        synthesis_hash=syn_dict["synthesis_hash"],
    )


def _rehydrate_priority(pri_dict: Dict[str, Any]):
    from modules.edge_research.opr_bridge.evidence_synthesis_records import ResearchPriorityDecision

    return ResearchPriorityDecision(
        decision_id=pri_dict["decision_id"],
        proposition_id=pri_dict["proposition_id"],
        synthesis_id=pri_dict["synthesis_id"],
        synthesized_epistemic_state=pri_dict["synthesized_epistemic_state"],
        unresolved_uncertainty=tuple(pri_dict["unresolved_uncertainty"]),
        saturation_level=pri_dict["saturation_level"],
        marginal_information=pri_dict["marginal_information"],
        contradiction_status=pri_dict["contradiction_status"],
        independence_summary=pri_dict["independence_summary"],
        chosen_priority_action=pri_dict["chosen_priority_action"],
        rationale=tuple(pri_dict["rationale"]),
        rejected_alternatives=tuple(pri_dict.get("rejected_alternatives", [])),
        created_at=pri_dict["created_at"],
        synthesis_engine_version=pri_dict["synthesis_engine_version"],
        record_hash=pri_dict["record_hash"],
    )


def build_action_context_from_lifecycle(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    *,
    executability: Optional[ExecutabilityContext] = None,
    evidence_specs: Optional[List[Dict[str, Any]]] = None,
) -> ActionGenerationContext:
    """Build ActionGenerationContext from latest authoritative lifecycle records."""
    if not state.synthesis_history or not state.priority_history:
        raise ValueError("Lifecycle state missing synthesis or priority history")

    syn_dict = state.latest_synthesis()
    pri_dict = state.latest_priority()

    if evidence_specs is not None:
        prop_spec = {
            "proposition_id": proposition["proposition_id"],
            "proposition_hash": proposition.get("proposition_hash", f"abstract_{proposition['proposition_id']}"),
            "proposition_type": proposition.get("proposition_type", "partition_contrast"),
        }
        specs = evidence_specs
    else:
        prop_spec = proposition_spec_from_record(proposition)
        specs = build_ledger_specs_from_events(proposition, state.evidence_events)

    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)

    synthesis = _rehydrate_synthesis(syn_dict)
    priority = _rehydrate_priority(pri_dict)

    ex = executability or ExecutabilityContext.abstract_default()
    return build_context_from_synthesis(prop_spec, proposition, synthesis, priority, entries, ex, specs)


def run_frontier_assessment(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    *,
    executability: Optional[ExecutabilityContext] = None,
    cohort_constraints_override: Any = None,
    evidence_specs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[FrontierReassessmentResult, ActionGenerationContext]:
    ctx = build_action_context_from_lifecycle(
        proposition, state, executability=executability, evidence_specs=evidence_specs
    )
    gen = generate_scientific_actions(ctx)
    frontier = ScientificFrontierReassessor().reassess(
        ctx, gen, cohort_constraints_override=cohort_constraints_override
    )
    return frontier, ctx


def on_scientific_frontier_completed(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    frontier: FrontierReassessmentResult,
    ctx: ActionGenerationContext,
) -> DormancyHookOutcome:
    """
    Canonical dormancy hook downstream of frontier assessment.
    Idempotent, append-only, failure-isolated.
    """
    try:
        frontier_dict = frontier.to_dict()
        if not state.frontier_history or state.frontier_history[-1].get("record_hash") != frontier.record_hash:
            state.frontier_history.append(
                {
                    **frontier_dict,
                    "record_hash": frontier.record_hash,
                    "authority": AUTHORITY_FRONTIER,
                }
            )

        decision = frontier.frontier_decision.value
        if not should_enter_dormancy(decision, priority_action=ctx.priority_action):
            if state.research_activity_state == ResearchActivityTransition.DORMANT.value:
                state.research_activity_state = ResearchActivityTransition.ACTIVE.value
            return DormancyHookOutcome(status="SKIPPED", dormancy_record=None, idempotent_skip=False)

        idem_key = _dormancy_idempotency_key(ctx.synthesis.synthesis_hash, frontier.record_hash)
        if idem_key in state._dormancy_idempotency_keys:
            latest = state.latest_dormancy()
            dormancy = _rehydrate_dormancy(latest) if latest else None
            return DormancyHookOutcome(status="SUCCESS", dormancy_record=dormancy, idempotent_skip=True)

        dormancy = derive_dormancy_record(ctx, frontier)
        if dormancy is None:
            return DormancyHookOutcome(status="SKIPPED", dormancy_record=None, idempotent_skip=False)

        state._dormancy_idempotency_keys.append(idem_key)
        state.dormancy_history.append({**dormancy.to_dict(), "authority": AUTHORITY_DORMANCY})
        state.research_activity_state = ResearchActivityTransition.DORMANT.value
        return DormancyHookOutcome(status="SUCCESS", dormancy_record=dormancy, idempotent_skip=False)

    except Exception as exc:
        return DormancyHookOutcome(status="FAILED", dormancy_record=None, idempotent_skip=False, error=str(exc))


def _snapshot_from_lifecycle(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    ctx: ActionGenerationContext,
    *,
    epistemic_state_override: Optional[str] = None,
) -> CurrentResearchSnapshot:
    return CurrentResearchSnapshot(
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        proposition_record=proposition,
        epistemic_state=epistemic_state_override or ctx.synthesis.synthesized_epistemic_state,
        unresolved_uncertainties=set(ctx.unresolved_axes),
        covered_axes=ctx.covered_axes,
        redundant_axes=ctx.redundant_axes,
        max_cohort_overlap=ctx.max_cohort_overlap,
        available_operators=set(ctx.executability.available_tools),
    )


def _evaluation_to_record(
    dormancy: ResearchDormancyRecord,
    opportunity: ResearchOpportunityState,
    result: ReopeningEvaluationResult,
    *,
    created_at: str,
) -> ReopeningEvaluationRecord:
    eid = new_id("reval")
    body = {
        "evaluation_id": eid,
        "dormancy_id": dormancy.dormancy_id,
        "dormancy_record_hash": dormancy.record_hash,
        "proposition_id": dormancy.proposition_id,
        "proposition_hash": dormancy.proposition_hash,
        "opportunity_state_hash": opportunity.content_hash(),
        "outcome": result.outcome.value,
        "rationale": result.rationale,
    }
    return ReopeningEvaluationRecord(
        evaluation_id=eid,
        dormancy_id=dormancy.dormancy_id,
        dormancy_record_hash=dormancy.record_hash,
        proposition_id=dormancy.proposition_id,
        proposition_hash=dormancy.proposition_hash,
        opportunity_state_hash=opportunity.content_hash(),
        outcome=result.outcome.value,
        rationale=result.rationale,
        satisfied_conditions=result.satisfied_conditions,
        rejected_triggers=result.rejected_triggers,
        trigger_fingerprint=result.trigger_fingerprint,
        created_at=created_at,
        record_hash=stable_hash(body),
    )


def on_research_opportunity_state_changed(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    opportunity: ResearchOpportunityState,
    *,
    ctx: Optional[ActionGenerationContext] = None,
    evidence_specs: Optional[List[Dict[str, Any]]] = None,
) -> ReopeningHookOutcome:
    """
    Canonical reopening hook for dormant propositions only.
    Uses frozen DormancyRecord conditions — does not re-derive.
    STOP after recording — no experiment generation.
    """
    try:
        if opportunity.proposition_id != state.proposition_id:
            return ReopeningHookOutcome(
                status="FAILED",
                evaluation_record=None,
                evaluation_result=None,
                idempotent_skip=False,
                error="proposition_id mismatch",
            )

        latest_dormancy_dict = state.latest_dormancy()
        if latest_dormancy_dict is None:
            return ReopeningHookOutcome(
                status="SKIPPED",
                evaluation_record=None,
                evaluation_result=None,
                idempotent_skip=False,
                error="no dormancy record",
            )

        if opportunity.proposition_hash != latest_dormancy_dict.get("proposition_hash"):
            return ReopeningHookOutcome(
                status="FAILED",
                evaluation_record=None,
                evaluation_result=None,
                idempotent_skip=False,
                error="stale dormancy proposition hash mismatch",
            )

        opp_hash = opportunity.content_hash()
        if opp_hash in state._opportunity_hashes_seen:
            return ReopeningHookOutcome(
                status="SUCCESS",
                evaluation_record=None,
                evaluation_result=None,
                idempotent_skip=True,
            )

        dormancy = _rehydrate_dormancy(latest_dormancy_dict)
        specs = evidence_specs or state._abstract_evidence_specs
        action_ctx = ctx or build_action_context_from_lifecycle(proposition, state, evidence_specs=specs)
        snapshot = _snapshot_from_lifecycle(proposition, state, action_ctx)

        # Terminal epistemic precedence
        if snapshot.epistemic_state in TERMINAL_EPISTEMIC_STATES:
            result = ReopeningEvaluationResult(
                outcome=ReopeningEvaluationOutcome.REMAIN_DORMANT,
                rationale=f"Terminal epistemic state {snapshot.epistemic_state} dominates reopening",
                record_hash=stable_hash({"outcome": "REMAIN_DORMANT", "terminal": snapshot.epistemic_state}),
            )
        else:
            descriptor = opportunity.to_descriptor()
            evaluator = DormantResearchReopeningEvaluator()
            seen = set(state._opportunity_hashes_seen)
            from modules.edge_research.opr_bridge.dormancy_records import ResearchMemoryLedger

            memory = ResearchMemoryLedger(seen_trigger_fingerprints=seen)
            result = evaluator.evaluate(dormancy, snapshot, descriptor, memory=memory)

        ts = utc_now_iso()
        record = _evaluation_to_record(dormancy, opportunity, result, created_at=ts)
        state._opportunity_hashes_seen.append(opp_hash)
        state.reopening_history.append({**record.to_dict(), "authority": AUTHORITY_REOPENING})

        if result.outcome == ReopeningEvaluationOutcome.REOPEN_RESEARCH:
            state.research_activity_state = ResearchActivityTransition.REOPEN_CANDIDATE.value
        elif result.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT:
            state.research_activity_state = ResearchActivityTransition.DORMANT.value
        # NEW_PROPOSITION_REQUIRED / INSUFFICIENT_EVIDENCE: proposition stays dormant, no mutation

        return ReopeningHookOutcome(
            status="SUCCESS",
            evaluation_record=record,
            evaluation_result=result,
            idempotent_skip=False,
        )

    except Exception as exc:
        return ReopeningHookOutcome(
            status="FAILED",
            evaluation_record=None,
            evaluation_result=None,
            idempotent_skip=False,
            error=str(exc),
        )


def run_post_synthesis_frontier_pipeline(
    proposition: Dict[str, Any],
    state: LifecycleKnowledgeState,
    synthesis_outcome: SynthesisIntegrationOutcome,
    *,
    executability: Optional[ExecutabilityContext] = None,
    cohort_constraints_override: Any = None,
    evidence_specs: Optional[List[Dict[str, Any]]] = None,
) -> FrontierPipelineOutcome:
    """
    Evidence update → synthesis → frontier → dormancy (if warranted).
    Does not execute experiments.
    """
    if synthesis_outcome.integration_status != "SUCCESS" or not synthesis_outcome.synthesis:
        raise ValueError("Synthesis must succeed before frontier pipeline")

    frontier, ctx = run_frontier_assessment(
        proposition,
        state,
        executability=executability,
        cohort_constraints_override=cohort_constraints_override,
        evidence_specs=evidence_specs,
    )
    if evidence_specs is not None:
        state._abstract_evidence_specs = evidence_specs
    dormancy_outcome = on_scientific_frontier_completed(proposition, state, frontier, ctx)

    return FrontierPipelineOutcome(
        frontier=frontier,
        dormancy=dormancy_outcome,
        research_activity_state=state.research_activity_state,
        epistemic_state=ctx.synthesis.synthesized_epistemic_state,
    )


def reconstruct_authoritative_state(state: LifecycleKnowledgeState) -> Dict[str, Any]:
    """Deterministic latest-authoritative-record resolution for session bootstrap."""
    syn = state.latest_synthesis()
    pri = state.latest_priority()
    frontier = state.latest_frontier()
    dormancy = state.latest_dormancy()
    reopening = state.latest_reopening()
    return {
        "proposition_id": state.proposition_id,
        "epistemic_state": syn.get("synthesized_epistemic_state") if syn else None,
        "synthesis_hash": syn.get("synthesis_hash") if syn else None,
        "priority_action": pri.get("chosen_priority_action") if pri else None,
        "frontier_decision": frontier.get("frontier_decision") if frontier else None,
        "research_activity_state": state.research_activity_state,
        "is_dormant": state.is_dormant(),
        "dormancy_hash": dormancy.get("record_hash") if dormancy else None,
        "dormancy_reason": dormancy.get("dormancy_reason") if dormancy else None,
        "unresolved_uncertainties": dormancy.get("unresolved_uncertainties") if dormancy else None,
        "reopening_conditions_count": len(dormancy.get("reopening_conditions", [])) if dormancy else 0,
        "latest_reopening_outcome": reopening.get("outcome") if reopening else None,
        "evidence_event_count": len(state.evidence_events),
    }


def verify_frozen_scientific_integrity() -> Dict[str, Any]:
    engine = verify_frozen_engine_integrity()
    return {
        "synthesis_engine": engine,
        "dormancy_module_hash": dormancy_content_hash(),
        "dormancy_version": DORMANCY_VERSION,
        "integration_version": INTEGRATION_VERSION,
        "passed": engine["passed"],
    }


def integration_content_hash() -> str:
    return stable_hash({"version": INTEGRATION_VERSION})
