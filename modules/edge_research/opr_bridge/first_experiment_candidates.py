"""
Phase 3J.2 — First-experiment candidate generation (scientific-first, tools-last).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.first_experiment_birth_evidence import (
    BirthEvidenceFingerprint,
    build_birth_evidence_fingerprint,
    measure_birth_overlap,
)
from modules.edge_research.opr_bridge.first_experiment_records import (
    CandidateClassification,
    FirstExperimentCandidateRecord,
    InitialExperimentObjectiveRecord,
    build_candidate_record,
)
from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    _check_anti_rescue,
    _holdout_dates_from_panel,
    _population_holdout_spec,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_executability import bind_experiment_spec
from modules.edge_research.opr_bridge.scientific_action_records import RescueRiskClass, ScientificActionCore
from modules.edge_research.research_grammar import GRAMMAR_VERSION


@dataclass
class FirstExperimentContext:
    """Minimal birth-time context — no synthesis or ToolResult."""

    proposition_record: Dict[str, Any]
    executability: ExecutabilityContext
    panel: PanelMetadataIndex
    birth_fingerprint: BirthEvidenceFingerprint

    @property
    def proposition_id(self) -> str:
        return self.proposition_record["proposition_id"]

    @property
    def proposition_hash(self) -> str:
        return proposition_content_hash(self.proposition_record)

    @property
    def motivating_dates(self) -> Tuple[str, ...]:
        return self.birth_fingerprint.motivating_dates

    @property
    def proposition_type(self) -> str:
        return self.proposition_record.get("proposition_type", "partition_contrast")


def _commitment_label(ctx: FirstExperimentContext) -> str:
    ptype = ctx.proposition_type
    if ptype == "context_modulation":
        feat = ctx.proposition_record.get("feature", "context_gate")
        return f"context_modulation_{feat}"
    rel = ctx.proposition_record.get("explanatory_relation", {})
    feat = rel.get("feature_or_contrast") or ctx.proposition_record.get("feature", "partition_feature")
    return f"partition_contrast_{feat}"


def _contrast_relation(ctx: FirstExperimentContext) -> str:
    if ctx.proposition_type == "context_modulation":
        return "context_modulation_contrast"
    rel = ctx.proposition_record.get("explanatory_relation", {})
    if rel.get("relation_kind") == "surface_skew":
        return "surface_skew_contrast"
    return "partition_quintile_contrast"


def _feature_field(ctx: FirstExperimentContext) -> str:
    ptype = ctx.proposition_type
    if ptype == "context_modulation":
        return str(ctx.proposition_record.get("feature", "context_gate"))
    if ctx.executability.abstract_mode:
        rel = ctx.proposition_record.get("explanatory_relation", {})
        return str(rel.get("feature_or_contrast") or ctx.proposition_record.get("feature", "flux_index"))
    rel = ctx.proposition_record.get("explanatory_relation", {})
    return rel.get("feature_or_contrast") or ctx.proposition_record.get("execution_requirements", {}).get(
        "partition_column", "partition_feature"
    )


def _outcome_field(ctx: FirstExperimentContext) -> str:
    outcome = ctx.proposition_record.get("outcome", {})
    if isinstance(outcome, dict):
        return outcome.get("field", "outcome_field")
    return str(outcome)


def _make_core(
    ctx: FirstExperimentContext,
    *,
    target_uncertainty: str,
    cohort_strategy: str,
    information_gain: str,
) -> ScientificActionCore:
    return ScientificActionCore(
        objective_target_uncertainty=target_uncertainty,
        proposition_commitment_challenged=_commitment_label(ctx),
        cohort_strategy=cohort_strategy,
        contrast_relation=_contrast_relation(ctx),
        expected_epistemic_consequence_type=f"{information_gain}_{target_uncertainty}",
        information_gain_type=information_gain,
    )


def _action_ctx_adapter(ctx: FirstExperimentContext):
    """Adapt to ActionGenerationContext shape for executability binding."""
    from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
    from modules.edge_research.opr_bridge.evidence_synthesis_records import (
        EvidenceSynthesisRecord,
        ResearchPriorityDecision,
    )

    prop = ctx.proposition_record
    syn = EvidenceSynthesisRecord(
        synthesis_id="birth_synthesis_stub",
        proposition_id=prop["proposition_id"],
        proposition_hash=ctx.proposition_hash,
        evidence_ids=(),
        evidence_hashes=(),
        relationship_map={},
        independence_profiles={},
        supporting_structure=[],
        disconfirming_structure=[],
        contradiction_structure=[],
        invalid_non_informative=[],
        uncertainty_covered=(),
        uncertainty_unresolved=("directional_effect_full_universe", "episode_robustness"),
        saturation_assessment={},
        synthesized_epistemic_state="HYPOTHESIS",
        prior_epistemic_state="HYPOTHESIS",
        scientific_rationale=(),
        counterfactual_causality_refs=(),
        synthesis_engine_version="birth_stub",
        created_at="",
        synthesis_hash="birth_stub",
    )
    pri = ResearchPriorityDecision(
        decision_id="birth_priority_stub",
        proposition_id=prop["proposition_id"],
        synthesis_id="birth_synthesis_stub",
        synthesized_epistemic_state="HYPOTHESIS",
        unresolved_uncertainty=("directional_effect_full_universe",),
        saturation_level="low",
        marginal_information="high",
        contradiction_status="none",
        independence_summary="birth",
        chosen_priority_action="SEEK_FALSIFICATION",
        rationale=("First experiment at proposition birth",),
        rejected_alternatives=(),
        created_at="",
        synthesis_engine_version="birth_stub",
        record_hash="birth_stub",
    )
    return ActionGenerationContext(
        proposition_spec={
            "proposition_id": prop["proposition_id"],
            "proposition_hash": ctx.proposition_hash,
            "proposition_type": ctx.proposition_type,
        },
        proposition_record=prop,
        synthesis=syn,
        priority=pri,
        ledger_entries=[],
        executability=ctx.executability,
    )


def _detect_rescue_risk_local(prop: Dict[str, Any], population_spec: Dict[str, Any], scope: Dict[str, Any]) -> str:
    """Birth-time anti-rescue — avoid false positive on kind=all population specs."""
    kind = population_spec.get("kind", "all")
    if kind in ("refine", "widen"):
        return RescueRiskClass.POPULATION_NARROWING.value
    base_outcome = prop.get("outcome", {})
    scope_outcome = scope.get("outcome_spec", {})
    if isinstance(base_outcome, dict) and scope_outcome:
        if scope_outcome.get("field") and scope_outcome.get("field") != base_outcome.get("field"):
            return RescueRiskClass.OUTCOME_MUTATION.value
    if int(scope.get("observation_horizon", 0)) != int(prop.get("observation_horizon", 0)):
        return RescueRiskClass.HORIZON_MUTATION.value
    return RescueRiskClass.PASS.value


def _population_all() -> Dict[str, Any]:
    return {"kind": "all", "grammar_version": GRAMMAR_VERSION}


def _population_holdout(ctx: FirstExperimentContext, panel_df=None) -> Optional[Dict[str, Any]]:
    cutoff = ctx.executability.data_cutoff
    holdout = _holdout_dates_from_panel(
        panel_df if panel_df is not None else _empty_panel_df(),
        cutoff=cutoff,
        motivating_dates=ctx.motivating_dates,
    )
    if not holdout:
        return None
    return _population_holdout_spec(holdout)


def _empty_panel_df():
    import pandas as pd

    return pd.DataFrame(columns=["trade_date", "symbol"])


def _classify_candidate(
    *,
    core: ScientificActionCore,
    overlap: float,
    indep: Dict[str, str],
    rescue: str,
    exec_status: str,
    falsification_capable: bool,
    is_representation_duplicate: bool,
    matches_birth_draft: bool,
) -> Tuple[str, Tuple[str, ...], str, bool]:
    secondary: List[str] = []
    if rescue != RescueRiskClass.PASS.value:
        if rescue == RescueRiskClass.OUTCOME_MUTATION.value:
            return CandidateClassification.NEW_PROPOSITION_REQUIRED.value, (), f"Rescue: {rescue}", False
        return CandidateClassification.RESCUE_MUTATION.value, (), f"Rescue mutation: {rescue}", False

    if exec_status == "INVALID":
        return CandidateClassification.NON_INFORMATIVE.value, (), "Invalid or leaky evidence path", False

    if is_representation_duplicate:
        return CandidateClassification.REPRESENTATION_ONLY.value, (), "Duplicate scientific identity — representation only", False

    if overlap >= 0.85 and core.cohort_strategy in ("full_panel_contrast", "confirmatory_retest"):
        secondary.append(CandidateClassification.CONFIRMATORY_ONLY.value)
        return (
            CandidateClassification.REDUNDANT_WITH_BIRTH_EVIDENCE.value,
            tuple(secondary),
            f"Birth overlap {overlap:.3f} — recomputes motivating evidence cohort",
            matches_birth_draft,
        )

    if falsification_capable and indep.get("sample_independence") in ("HIGH", "MEDIUM"):
        return (
            CandidateClassification.FALSIFICATION_CAPABLE.value,
            (),
            "Independent cohort can materially disconfirm proposition commitment",
            False,
        )

    if overlap >= 0.85:
        secondary.append(CandidateClassification.CONFIRMATORY_ONLY.value)
        return (
            CandidateClassification.REDUNDANT_WITH_BIRTH_EVIDENCE.value,
            tuple(secondary),
            f"High birth overlap {overlap:.3f}",
            True,
        )

    if core.cohort_strategy == "full_panel_contrast":
        return (
            CandidateClassification.DIRECT_INITIAL_TEST.value,
            (),
            "Direct test of central directional commitment on full panel",
            True,
        )

    if exec_status in ("NOT_EXECUTABLE", "SCIENTIFICALLY_VALID_NOT_EXECUTABLE", "TOOL_BLOCKED", "GRAMMAR_BLOCKED"):
        return CandidateClassification.NOT_EXECUTABLE.value, (), exec_status, False

    return CandidateClassification.DIRECT_INITIAL_TEST.value, (), "Scientifically valid candidate", False


def _bind_candidate(
    ctx: FirstExperimentContext,
    core: ScientificActionCore,
    objective: InitialExperimentObjectiveRecord,
    *,
    tool_override: Optional[str] = None,
    population_spec_override: Optional[Dict[str, Any]] = None,
    strategy_key: str,
    falsification_capable: bool,
    force_rescue: Optional[str] = None,
) -> FirstExperimentCandidateRecord:
    actx = _action_ctx_adapter(ctx)
    pop = population_spec_override or {"kind": "all", "grammar_version": GRAMMAR_VERSION}
    scope = {
        "population_spec": pop,
        "outcome_spec": {"field": _outcome_field(ctx), "kind": "compare"},
        "observation_horizon": int(ctx.proposition_record.get("observation_horizon", 0)),
    }
    rescue = force_rescue or _detect_rescue_risk_local(ctx.proposition_record, pop, scope)
    if rescue == RescueRiskClass.PASS.value:
        anti_ok, anti_detail = _check_anti_rescue(ctx.proposition_record, scope)
        if not anti_ok:
            rescue = anti_detail

    spec, envelope, exec_class, exec_detail = bind_experiment_spec(
        actx,
        core=core,
        rescue_risk=rescue if rescue != RescueRiskClass.PASS.value else RescueRiskClass.PASS.value,
        tool_override=tool_override,
        population_spec_override=population_spec_override,
    )

    exec_map = {
        "SCIENTIFICALLY_VALID_EXECUTABLE": "EXECUTABLE",
        "SCIENTIFICALLY_VALID_NOT_EXECUTABLE": "NOT_EXECUTABLE",
        "RESCUE_RISK": "RESCUE_REJECTED",
        "INVALID": "INVALID",
    }
    exec_status = exec_map.get(exec_class, exec_class)

    overlap, indep = measure_birth_overlap(
        candidate_population_spec=pop,
        candidate_contrast_relation=core.contrast_relation,
        candidate_feature=_feature_field(ctx),
        panel=ctx.panel,
        birth=ctx.birth_fingerprint,
    )

    matches_draft = _matches_experiment_draft(ctx, spec)
    primary, secondary, rationale, confirmatory = _classify_candidate(
        core=core,
        overlap=overlap,
        indep=indep,
        rescue=rescue if rescue != RescueRiskClass.PASS.value else RescueRiskClass.PASS.value,
        exec_status=exec_status,
        falsification_capable=falsification_capable,
        is_representation_duplicate=False,
        matches_birth_draft=matches_draft,
    )

    epistemic = "HIGH" if falsification_capable and indep.get("sample_independence") == "HIGH" else "MEDIUM"
    if primary in (CandidateClassification.REDUNDANT_WITH_BIRTH_EVIDENCE.value, CandidateClassification.CONFIRMATORY_ONLY.value):
        epistemic = "LOW"

    return build_candidate_record(
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        objective_id=objective.objective_id,
        scientific_action_core_hash=core.core_hash,
        scientific_identity=core.to_canonical_dict(),
        primary_classification=primary,
        secondary_classifications=secondary,
        classification_rationale=rationale,
        falsification_capable=falsification_capable and primary == CandidateClassification.FALSIFICATION_CAPABLE.value,
        confirmatory_only=confirmatory or CandidateClassification.CONFIRMATORY_ONLY.value in secondary,
        birth_evidence_overlap_fraction=overlap,
        independence_profile=indep,
        directness_rank=objective.directness_rank,
        epistemic_alteration_potential=epistemic,
        rescue_risk_status=rescue if rescue != RescueRiskClass.PASS.value else "pass",
        executability_status=exec_status,
        executability_detail=exec_detail,
        experiment_spec=spec,
        representation_envelope=envelope,
    )


def _matches_experiment_draft(ctx: FirstExperimentContext, spec: Optional[Dict[str, Any]]) -> bool:
    if spec is None:
        return False
    draft = ctx.proposition_record.get("experiment_spec_draft")
    if not draft:
        return False
    return (
        draft.get("tool_name") == spec.get("tool_name")
        and draft.get("inputs") == spec.get("inputs")
        and (draft.get("research_scope") or {}).get("population_spec", {}).get("kind")
        == (spec.get("research_scope") or {}).get("population_spec", {}).get("kind")
    )


def deduplicate_first_experiment_candidates(
    candidates: List[FirstExperimentCandidateRecord],
) -> List[FirstExperimentCandidateRecord]:
    """Keep best scientific merit per core hash — mirrors 3I.16 dedup."""
    rank = {
        CandidateClassification.FALSIFICATION_CAPABLE.value: 0,
        CandidateClassification.DIRECT_INITIAL_TEST.value: 1,
        CandidateClassification.NOT_EXECUTABLE.value: 2,
        CandidateClassification.CONFIRMATORY_ONLY.value: 3,
        CandidateClassification.REDUNDANT_WITH_BIRTH_EVIDENCE.value: 4,
        CandidateClassification.REPRESENTATION_ONLY.value: 5,
        CandidateClassification.RESCUE_MUTATION.value: 6,
        CandidateClassification.NEW_PROPOSITION_REQUIRED.value: 7,
        CandidateClassification.NON_INFORMATIVE.value: 8,
    }
    best: Dict[str, FirstExperimentCandidateRecord] = {}
    for c in candidates:
        key = c.scientific_action_core_hash
        if key not in best or rank.get(c.primary_classification, 9) < rank.get(best[key].primary_classification, 9):
            best[key] = c
    return list(best.values())


def generate_first_experiment_candidates(
    prop: Dict[str, Any],
    objectives: List[InitialExperimentObjectiveRecord],
    panel: PanelMetadataIndex,
    executability: ExecutabilityContext,
    *,
    include_audit_sketches: bool = False,
    panel_df=None,
) -> List[FirstExperimentCandidateRecord]:
    """
    Generate bounded scientifically distinct first-experiment candidates.
    Tools bound last via bind_experiment_spec.
    """
    ctx = FirstExperimentContext(
        proposition_record=prop,
        executability=executability,
        panel=panel,
        birth_fingerprint=build_birth_evidence_fingerprint(prop, panel),
    )
    candidates: List[FirstExperimentCandidateRecord] = []

    dir_obj = next((o for o in objectives if o.target_uncertainty == "directional_effect_full_universe"), objectives[0])
    ep_obj = next((o for o in objectives if o.target_uncertainty == "episode_robustness"), dir_obj)

    # 1. Full-panel direct test
    core_direct = _make_core(ctx, target_uncertainty="directional_effect_full_universe", cohort_strategy="full_panel_contrast", information_gain="inform")
    candidates.append(
        _bind_candidate(ctx, core_direct, dir_obj, strategy_key="direct_full_panel", falsification_capable=False)
    )

    # 2. Episode holdout falsification
    holdout_pop = _population_holdout(ctx, panel_df)
    if holdout_pop:
        core_holdout = _make_core(ctx, target_uncertainty="episode_robustness", cohort_strategy="episode_holdout_excluding_motivating", information_gain="falsify")
        candidates.append(
            _bind_candidate(
                ctx,
                core_holdout,
                ep_obj,
                population_spec_override=holdout_pop,
                strategy_key="episode_holdout",
                falsification_capable=True,
            )
        )

    # 3. Alternative tool representation (same scientific core) — always when multiple tools exist
    primary_tool = "tier_compare" if executability.abstract_mode else "partition_group_compare"
    alt_tools = [t for t in executability.available_tools if t != primary_tool]
    if alt_tools:
            core_alt = _make_core(ctx, target_uncertainty="directional_effect_full_universe", cohort_strategy="full_panel_contrast", information_gain="inform")
            alt_c = _bind_candidate(
                ctx,
                core_alt,
                dir_obj,
                tool_override=alt_tools[0],
                strategy_key="alt_tool_representation",
                falsification_capable=False,
            )
            alt_c = build_candidate_record(
                proposition_id=alt_c.proposition_id,
                proposition_hash=alt_c.proposition_hash,
                objective_id=alt_c.objective_id,
                scientific_action_core_hash=alt_c.scientific_action_core_hash,
                scientific_identity=alt_c.scientific_identity,
                primary_classification=CandidateClassification.REPRESENTATION_ONLY.value,
                secondary_classifications=(),
                classification_rationale="Same scientific core — different tool envelope only",
                falsification_capable=False,
                confirmatory_only=True,
                birth_evidence_overlap_fraction=alt_c.birth_evidence_overlap_fraction,
                independence_profile=alt_c.independence_profile,
                directness_rank=alt_c.directness_rank,
                epistemic_alteration_potential="LOW",
                rescue_risk_status=alt_c.rescue_risk_status,
                executability_status=alt_c.executability_status,
                executability_detail=alt_c.executability_detail,
                experiment_spec=alt_c.experiment_spec,
                representation_envelope=alt_c.representation_envelope,
            )
            candidates.append(alt_c)

    # 4. Counterexample period search (distinct cohort strategy)
    if holdout_pop and ctx.proposition_type == "partition_contrast":
        core_counter = _make_core(
            ctx,
            target_uncertainty="episode_robustness",
            cohort_strategy="counterexample_period_search",
            information_gain="falsify",
        )
        candidates.append(
            _bind_candidate(
                ctx,
                core_counter,
                ep_obj,
                population_spec_override={
                    "kind": "filter",
                    "field": "trade_date",
                    "operator": "not_in",
                    "values": list(ctx.motivating_dates),
                    "grammar_version": GRAMMAR_VERSION,
                },
                strategy_key="counterexample_search",
                falsification_capable=True,
            )
        )

    if include_audit_sketches:
        # Rescue: population narrowing
        narrow_pop = {
            "kind": "refine",
            "parent": _population_all(),
            "children": [{"kind": "filter", "field": "research_market_state", "operator": "in", "values": ["STRESS"], "grammar_version": GRAMMAR_VERSION}],
            "reason_code": "AUDIT_NARROW",
            "grammar_version": GRAMMAR_VERSION,
        }
        core_rescue = _make_core(ctx, target_uncertainty="directional_effect_full_universe", cohort_strategy="population_subgroup_contrast", information_gain="inform")
        candidates.append(
            _bind_candidate(
                ctx,
                core_rescue,
                dir_obj,
                population_spec_override=narrow_pop,
                strategy_key="rescue_population_narrow",
                falsification_capable=False,
                force_rescue=RescueRiskClass.POPULATION_NARROWING.value,
            )
        )

        # Outcome mutation
        mutated_pop = _population_all()
        core_outcome = _make_core(ctx, target_uncertainty="directional_effect_full_universe", cohort_strategy="full_panel_contrast", information_gain="inform")
        actx = _action_ctx_adapter(ctx)
        spec, envelope, exec_class, exec_detail = bind_experiment_spec(
            actx,
            core=core_outcome,
            rescue_risk=RescueRiskClass.OUTCOME_MUTATION.value,
            population_spec_override=mutated_pop,
        )
        candidates.append(
            build_candidate_record(
                proposition_id=ctx.proposition_id,
                proposition_hash=ctx.proposition_hash,
                objective_id=dir_obj.objective_id,
                scientific_action_core_hash=core_outcome.core_hash + "_outcome_mut",
                scientific_identity={**core_outcome.to_canonical_dict(), "outcome_mutation": "true"},
                primary_classification=CandidateClassification.NEW_PROPOSITION_REQUIRED.value,
                secondary_classifications=(),
                classification_rationale="Outcome field mutation requires new proposition",
                falsification_capable=False,
                confirmatory_only=False,
                birth_evidence_overlap_fraction=0.0,
                independence_profile={"sample_independence": "UNKNOWN"},
                directness_rank=99,
                epistemic_alteration_potential="LOW",
                rescue_risk_status=RescueRiskClass.OUTCOME_MUTATION.value,
                executability_status="RESCUE_REJECTED",
                executability_detail="outcome_field_mutation",
                experiment_spec=spec,
                representation_envelope=envelope,
            )
        )

        # Invalid leaky cutoff
        core_leak = _make_core(ctx, target_uncertainty="directional_effect_full_universe", cohort_strategy="full_panel_contrast", information_gain="inform")
        actx.executability = ExecutabilityContext(
            available_tools=actx.executability.available_tools,
            data_cutoff="2099-12-31",
            panel_columns=actx.executability.panel_columns,
            abstract_mode=actx.executability.abstract_mode,
        )
        spec2, env2, ec2, ed2 = bind_experiment_spec(actx, core=core_leak, rescue_risk=RescueRiskClass.PASS.value)
        candidates.append(
            build_candidate_record(
                proposition_id=ctx.proposition_id,
                proposition_hash=ctx.proposition_hash,
                objective_id=dir_obj.objective_id,
                scientific_action_core_hash=core_leak.core_hash + "_leak",
                scientific_identity=core_leak.to_canonical_dict(),
                primary_classification=CandidateClassification.NON_INFORMATIVE.value,
                secondary_classifications=(),
                classification_rationale="Invalid leaky cutoff",
                falsification_capable=False,
                confirmatory_only=False,
                birth_evidence_overlap_fraction=1.0,
                independence_profile={"sample_independence": "NONE"},
                directness_rank=99,
                epistemic_alteration_potential="LOW",
                rescue_risk_status="pass",
                executability_status="INVALID",
                executability_detail=ed2,
                experiment_spec=spec2,
                representation_envelope=env2,
            )
        )

    # Context modulation family
    if ctx.proposition_type == "context_modulation":
        ctx_obj = next((o for o in objectives if o.target_uncertainty == "context_modulation_direction"), dir_obj)
        core_ctx = _make_core(ctx, target_uncertainty="context_modulation_direction", cohort_strategy="regime_separated_contrast", information_gain="falsify")
        ctx_pop = {
            "kind": "filter",
            "field": "research_market_state",
            "operator": "in",
            "values": ["CTX_B"],
            "grammar_version": GRAMMAR_VERSION,
        }
        candidates.append(
            _bind_candidate(
                ctx,
                core_ctx,
                ctx_obj,
                population_spec_override=ctx_pop,
                strategy_key="context_modulation",
                falsification_capable=True,
            )
        )

    return candidates
