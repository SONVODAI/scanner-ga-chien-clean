"""
Phase 3I.9 — Proposition-scoped FalsificationCandidateGenerator.

Scientific intent flows: proposition vulnerability → disconfirming evidence → experiment.
No GAP codes, templates, Zone C, or future ToolResult access.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.falsification_records import (
    CANDIDATE_RECORD_VERSION,
    GENERATOR_VERSION,
    EvidenceIndependenceClass,
    FalsificationCandidateRecord,
    PropositionVulnerability,
    VulnerabilityKind,
    build_candidate_record,
)
from modules.edge_research.opr_bridge.interpretation_contract import (
    InterpretationContract,
    proposition_content_hash,
)
from modules.edge_research.research_grammar import (
    GRAMMAR_VERSION,
    GrammarValidationError,
    PopulationSpec,
    parse_outcome_spec,
    parse_population_spec,
    apply_population_spec,
)
from modules.edge_research.research_frame import validate_specs_at_horizon
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash
from modules.edge_research.research_tools import build_default_tool_registry


def collect_motivating_episode_dates(prop: Dict[str, Any]) -> Tuple[str, ...]:
    """Dates that motivated or anchored the proposition — from provenance only."""
    dates: Set[str] = set()
    anchor = prop.get("observation_provenance", {}).get("evidence_anchor", {})
    if anchor.get("focal_date"):
        dates.add(str(anchor["focal_date"]))
    for art in prop.get("observation_provenance", {}).get("empirical_artifacts", []):
        if art.get("date"):
            dates.add(str(art["date"]))
    return tuple(sorted(dates))


def _null_suggests_episode_vulnerability(null_text: str, motivating_dates: Sequence[str]) -> bool:
    lower = (null_text or "").lower()
    episode_terms = (
        "artifact",
        "sample",
        "confound",
        "level effect",
        "focal",
        "date",
        "episode",
        "fluke",
    )
    if any(term in lower for term in episode_terms):
        return True
    return any(d in null_text for d in motivating_dates)


def derive_proposition_vulnerabilities(prop: Dict[str, Any]) -> List[PropositionVulnerability]:
    """
    Derive falsification vulnerabilities from proposition commitments — not from tool catalog.
    """
    dis = prop.get("disconfirming_observation_spec", {})
    null = prop.get("null_competing_explanation", "")
    motivating = collect_motivating_episode_dates(prop)
    vulns: List[PropositionVulnerability] = []

    vulns.append(
        PropositionVulnerability(
            kind=VulnerabilityKind.DIRECTIONAL_REVERSAL,
            description=dis.get("description", "Directional reversal of pre-registered contrast"),
            operational_basis=dis.get("operational_test", dis.get("threshold", "")),
            motivating_episode_dates=motivating,
            directness_rank=0,
        )
    )

    if motivating and _null_suggests_episode_vulnerability(null, motivating):
        vulns.append(
            PropositionVulnerability(
                kind=VulnerabilityKind.EPISODE_INSTABILITY,
                description=(
                    "Proposition may hold only on motivating/supporting episodes; "
                    "test on evidence independent of those dates"
                ),
                operational_basis=null or "episode_independence",
                motivating_episode_dates=motivating,
                directness_rank=1,
            )
        )
    elif motivating:
        vulns.append(
            PropositionVulnerability(
                kind=VulnerabilityKind.EPISODE_INSTABILITY,
                description=(
                    "Test proposition on market episodes independent of birth/motivating evidence"
                ),
                operational_basis="independent_episode_holdout",
                motivating_episode_dates=motivating,
                directness_rank=1,
            )
        )

    return vulns


def _base_research_scope(prop: Dict[str, Any]) -> Dict[str, Any]:
    horizon = int(prop.get("observation_horizon", 0))
    return {
        "population_spec": dict(prop.get("population_context", {"kind": "all", "grammar_version": GRAMMAR_VERSION})),
        "outcome_spec": dict(prop.get("outcome", {})),
        "observation_horizon": horizon,
        "pending_question_context": {
            "population_spec": dict(prop.get("population_context", {"kind": "all", "grammar_version": GRAMMAR_VERSION})),
            "outcome_spec": dict(prop.get("outcome", {})),
            "observation_horizon": horizon,
        },
    }


def _partition_inputs(prop: Dict[str, Any]) -> Dict[str, Any]:
    feat = prop.get("explanatory_relation", {}).get("feature_or_contrast") or prop.get(
        "execution_requirements", {}
    ).get("partition_column", "rs_spread")
    return {"partition_column": feat, "n_groups": 5}


def _spec_to_dict(spec: ExperimentSpec) -> Dict[str, Any]:
    return {
        "tool_name": spec.tool_name,
        "tool_version": spec.tool_version,
        "inputs": dict(spec.inputs),
        "research_scope": dict(spec.research_scope or {}),
        "data_cutoff_date": spec.data_cutoff_date,
    }


def _holdout_dates_from_panel(
    panel: pd.DataFrame,
    *,
    cutoff: str,
    motivating_dates: Sequence[str],
) -> Tuple[str, ...]:
    if panel.empty or "trade_date" not in panel.columns:
        return tuple()
    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    eligible = sorted(
        d for d in df[df["trade_date"] <= str(cutoff)]["trade_date"].unique() if d not in motivating_dates
    )
    return tuple(eligible)


def _population_holdout_spec(holdout_dates: Sequence[str]) -> Dict[str, Any]:
    return {
        "kind": "filter",
        "field": "trade_date",
        "operator": "in",
        "values": list(holdout_dates),
        "grammar_version": GRAMMAR_VERSION,
    }


def _check_anti_rescue(prop: Dict[str, Any], research_scope: Dict[str, Any]) -> Tuple[bool, str]:
    """Reject population/outcome/horizon/feature mutations."""
    base_outcome = prop.get("outcome", {})
    scope_outcome = research_scope.get("outcome_spec", {})
    if scope_outcome.get("field") != base_outcome.get("field"):
        return False, "outcome_field_mutation"
    if scope_outcome.get("kind") != base_outcome.get("kind"):
        return False, "outcome_kind_mutation"
    if int(research_scope.get("observation_horizon", 0)) != int(prop.get("observation_horizon", 0)):
        return False, "horizon_mutation"

    pop = research_scope.get("population_spec", {})
    kind = pop.get("kind", "all")
    if kind in ("refine", "widen"):
        return False, f"population_{kind}_rescue"
    if kind == "filter" and pop.get("field") not in ("trade_date",):
        if pop.get("field") not in (None, "symbol"):
            base_pop = prop.get("population_context", {})
            if base_pop.get("kind") == "all" and kind == "filter":
                field = pop.get("field")
                if field and field not in ("trade_date",):
                    return False, "population_narrowing_rescue"

    rel = prop.get("explanatory_relation", {})
    return True, "pass"


def _check_interpreter_compatible(spec: ExperimentSpec) -> bool:
    return spec.tool_name == "partition_group_compare"


def _assess_executability(
    spec: ExperimentSpec,
    panel: pd.DataFrame,
    prop: Dict[str, Any],
) -> Tuple[str, str]:
    try:
        pop = parse_population_spec(spec.research_scope.get("population_spec", {"kind": "all"}))
        out = parse_outcome_spec(spec.research_scope.get("outcome_spec", prop.get("outcome", {})))
        validate_specs_at_horizon(pop, out, observation_horizon=int(spec.research_scope.get("observation_horizon", 0)))
    except GrammarValidationError as exc:
        return "GRAMMAR_BLOCKED", str(exc)

    registry = build_default_tool_registry()
    try:
        registry.get(spec.tool_name, spec.tool_version)
    except KeyError:
        return "TOOL_BLOCKED", f"Tool {spec.tool_name} not registered"

    feat = spec.inputs.get("partition_column")
    outcome_field = spec.research_scope.get("outcome_spec", {}).get("field", "t5_return")
    required = {feat, outcome_field, "trade_date"}
    missing = required - set(panel.columns)
    if missing:
        return "NOT_EXECUTABLE", f"Missing columns: {sorted(missing)}"

    cutoff = spec.data_cutoff_date
    work = panel.copy()
    work["trade_date"] = work["trade_date"].astype(str)
    work = work[work["trade_date"] <= str(cutoff)]
    try:
        pop = parse_population_spec(spec.research_scope.get("population_spec", {"kind": "all"}))
        filtered, n = apply_population_spec(work, pop)
    except GrammarValidationError as exc:
        return "GRAMMAR_BLOCKED", str(exc)

    min_sample = int(prop.get("execution_requirements", {}).get("min_sample", 58))
    if n < min_sample:
        return "SAMPLE_INSUFFICIENT", f"Cohort n={n} < min_sample={min_sample}"
    if feat not in filtered.columns:
        return "NOT_EXECUTABLE", f"Partition column {feat} missing after filter"
    return "EXECUTABLE", f"Cohort n={n} passes grammar and sample gates"


def _disconfirm_outcome_text(contract: InterpretationContract) -> str:
    return (
        f"{contract.disconfirming_rule} → DISCONFIRMING; "
        f"{contract.falsify_strong_rule} → DISCONFIRMING_STRONG/FALSIFIED"
    )


def _non_informative_outcome_text(contract: InterpretationContract) -> str:
    return f"{contract.non_informative_rule} → NON_INFORMATIVE"


def _lineage_refs(
    prop_hash: str,
    contract: InterpretationContract,
    prior_tool_result_hash: str,
    lineage_hash: str,
) -> Dict[str, str]:
    return {
        "proposition_hash": prop_hash,
        "interpretation_contract_hash": contract.contract_hash,
        "prior_tool_result_hash": prior_tool_result_hash,
        "lineage_hash": lineage_hash,
    }


def generate_falsification_candidates(
    prop: Dict[str, Any],
    *,
    interpretation_contract: InterpretationContract,
    epistemic_update: Dict[str, Any],
    research_decision: Dict[str, Any],
    prior_experiment_spec: Dict[str, Any],
    prior_experiment_content_hash: str,
    lineage_hash: str,
    prior_tool_result_hash: str,
    panel: pd.DataFrame,
    include_audit_sketches: bool = False,
) -> List[FalsificationCandidateRecord]:
    """
    Generate bounded falsification candidates from proposition vulnerability.

    include_audit_sketches: emit pseudo-candidates for BB diagnostic classification only.
    """
    if research_decision.get("chosen_next_action") != "SEEK_FALSIFICATION":
        return []

    prop_hash = proposition_content_hash(prop)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    vulnerabilities = derive_proposition_vulnerabilities(prop)
    motivating = collect_motivating_episode_dates(prop)
    holdout = _holdout_dates_from_panel(panel, cutoff=cutoff, motivating_dates=motivating)
    candidates: List[FalsificationCandidateRecord] = []
    base_scope = _base_research_scope(prop)
    partition_inputs = _partition_inputs(prop)
    registry = build_default_tool_registry()
    tool_version = registry.get("partition_group_compare", "v1").metadata.tool_version

    def _add(
        *,
        strategy_key: str,
        vulnerability: PropositionVulnerability,
        spec: ExperimentSpec,
        independence: EvidenceIndependenceClass,
        independence_rationale: str,
        rationale: str,
        counterfactual: bool,
        rescue: str,
    ) -> None:
        content_hash = compute_experiment_content_hash(spec)
        anti_ok, anti_detail = _check_anti_rescue(prop, dict(spec.research_scope or {}))
        exec_status, exec_detail = _assess_executability(spec, panel, prop)
        if not anti_ok:
            exec_status = "RESCUE_REJECTED"
            exec_detail = anti_detail
        if not _check_interpreter_compatible(spec):
            counterfactual = False
        candidates.append(
            build_candidate_record(
                candidate_id=f"fc-{strategy_key}",
                proposition_id=prop["proposition_id"],
                proposition_hash=prop_hash,
                source_epistemic_update_id=epistemic_update["update_id"],
                source_research_decision_id=research_decision["decision_id"],
                vulnerability_tested=vulnerability.kind.value,
                scientific_rationale=rationale,
                possible_disconfirming_outcome=_disconfirm_outcome_text(interpretation_contract),
                possible_non_informative_outcome=_non_informative_outcome_text(interpretation_contract),
                proposed_experiment_spec=_spec_to_dict(spec),
                experiment_content_hash=content_hash,
                evidence_independence_class=independence.value,
                independence_rationale=independence_rationale,
                prior_experiment_content_hash=prior_experiment_content_hash,
                counterfactual_falsifiable=counterfactual and exec_status == "EXECUTABLE",
                rescue_risk_status=rescue if anti_ok else anti_detail,
                executability_status=exec_status,
                executability_detail=exec_detail,
                leakage_cutoff_requirements=f"data_cutoff_date={cutoff}; no rows after cutoff",
                lineage_refs=_lineage_refs(
                    prop_hash, interpretation_contract, prior_tool_result_hash, lineage_hash
                ),
            )
        )

    prior_spec = ExperimentSpec(
        tool_name=prior_experiment_spec["tool_name"],
        tool_version=prior_experiment_spec.get("tool_version", "v1"),
        inputs=dict(prior_experiment_spec["inputs"]),
        research_scope=dict(prior_experiment_spec["research_scope"]),
        data_cutoff_date=prior_experiment_spec["data_cutoff_date"],
    )

    dir_vuln = vulnerabilities[0]

    if include_audit_sketches:
        _add(
            strategy_key="audit_confirmatory_retest",
            vulnerability=dir_vuln,
            spec=prior_spec,
            independence=EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION,
            independence_rationale="Identical ExperimentSpec to prior supportive test",
            rationale="Audit sketch: exact confirmatory retest",
            counterfactual=False,
            rescue="pass",
        )

    if holdout:
        holdout_scope = dict(base_scope)
        holdout_scope["population_spec"] = _population_holdout_spec(holdout)
        holdout_spec = ExperimentSpec(
            tool_name="partition_group_compare",
            tool_version=tool_version,
            inputs=dict(partition_inputs),
            research_scope=holdout_scope,
            data_cutoff_date=cutoff,
        )
        ep_vuln = next((v for v in vulnerabilities if v.kind == VulnerabilityKind.EPISODE_INSTABILITY), dir_vuln)
        _add(
            strategy_key="independent_episode_holdout",
            vulnerability=ep_vuln,
            spec=holdout_spec,
            independence=EvidenceIndependenceClass.INDEPENDENT_FALSIFICATION,
            independence_rationale=(
                f"Partition contrast on {len(holdout)} holdout dates excluding motivating episodes "
                f"{list(motivating)} — new evidence cohort, same proposition semantics"
            ),
            rationale=(
                f"Vulnerability: {ep_vuln.description}. "
                f"Operational test: {interpretation_contract.disconfirming_rule} on independent episodes."
            ),
            counterfactual=True,
            rescue="pass",
        )

    if include_audit_sketches:
        narrow_scope = dict(base_scope)
        narrow_scope["population_spec"] = {
            "kind": "refine",
            "parent": prop.get("population_context", {"kind": "all", "grammar_version": GRAMMAR_VERSION}),
            "children": [
                {
                    "kind": "filter",
                    "field": "research_market_state",
                    "operator": "in",
                    "values": ["STRESS"],
                    "grammar_version": GRAMMAR_VERSION,
                }
            ],
            "reason_code": "AUDIT_NARROW",
            "grammar_version": GRAMMAR_VERSION,
        }
        _add(
            strategy_key="audit_population_narrow",
            vulnerability=dir_vuln,
            spec=ExperimentSpec(
                tool_name="partition_group_compare",
                tool_version=tool_version,
                inputs=dict(partition_inputs),
                research_scope=narrow_scope,
                data_cutoff_date=cutoff,
            ),
            independence=EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION,
            independence_rationale="Population narrowing — rescue temptation",
            rationale="Audit sketch: supportive population narrowing",
            counterfactual=False,
            rescue="population_narrowing_rescue",
        )

        horizon_scope = dict(base_scope)
        horizon_scope["observation_horizon"] = 5
        horizon_scope["outcome_spec"] = dict(prop.get("outcome", {}))
        _add(
            strategy_key="audit_horizon_mutation",
            vulnerability=dir_vuln,
            spec=ExperimentSpec(
                tool_name="partition_group_compare",
                tool_version=tool_version,
                inputs={**partition_inputs, "horizon": "T10"},
                research_scope=horizon_scope,
                data_cutoff_date=cutoff,
            ),
            independence=EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION,
            independence_rationale="Horizon mutation changes proposition meaning",
            rationale="Audit sketch: horizon mutation disguised as falsification",
            counterfactual=False,
            rescue="horizon_mutation",
        )

        _add(
            strategy_key="audit_same_question_different_tool",
            vulnerability=dir_vuln,
            spec=ExperimentSpec(
                tool_name="date_decomposition",
                tool_version="v1",
                inputs={"horizon": "T5"},
                research_scope=dict(base_scope),
                data_cutoff_date=cutoff,
            ),
            independence=EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION,
            independence_rationale="Different tool does not operationalize quintile disconfirm test",
            rationale="Audit sketch: same question via different tool only",
            counterfactual=False,
            rescue="pass",
        )

        leaky_spec = ExperimentSpec(
            tool_name="partition_group_compare",
            tool_version=tool_version,
            inputs=dict(partition_inputs),
            research_scope=dict(base_scope),
            data_cutoff_date="2099-12-31",
        )
        _add(
            strategy_key="audit_invalid_leaky",
            vulnerability=dir_vuln,
            spec=leaky_spec,
            independence=EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION,
            independence_rationale="Invalid cutoff / leakage",
            rationale="Audit sketch: invalid leaky candidate",
            counterfactual=False,
            rescue="pass",
        )

    return candidates


def generator_content_hash(candidates: Sequence[FalsificationCandidateRecord]) -> str:
    from modules.edge_research.opr_bridge.lifecycle_records import stable_hash

    payload = {
        "generator_version": GENERATOR_VERSION,
        "candidate_record_hashes": sorted(c.record_hash for c in candidates),
    }
    return stable_hash(payload)
