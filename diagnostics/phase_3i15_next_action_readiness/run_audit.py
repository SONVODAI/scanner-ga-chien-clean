#!/usr/bin/env python3
"""
Phase 3I.15 — Autonomous Next Scientific Action Readiness.

AUDIT + DESIGN ONLY — no next-action generator implementation, no new experiments.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I314 = REPO / "diagnostics/phase_3i14_automatic_synthesis_hook/artifacts"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def capability_inventory() -> Dict[str, Any]:
    """Section 3 — inventory all experiment/action proposal mechanisms."""
    mechanisms = [
        {
            "name": "FalsificationCandidateGenerator",
            "path": "modules/edge_research/opr_bridge/falsification_candidate_generator.py",
            "trigger": "ResearchDecisionRecord.chosen_next_action == SEEK_FALSIFICATION",
            "inputs": ["PropositionRecord", "EpistemicUpdateRecord", "ResearchDecisionRecord", "prior ExperimentSpec", "panel"],
            "outputs": ["FalsificationCandidateRecord[] with embedded ExperimentSpec"],
            "classification": ["PROPOSITION_SCOPED_REASONING", "TOOL_BOUND", "TEMPLATE_BOUND"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": (
                "Derives vulnerabilities from proposition commitments; emits at most one real candidate "
                "(independent_episode_holdout) plus audit sketches. Hard-wired to partition_group_compare. "
                "Does not read EvidenceSynthesisRecord or ResearchPriorityDecision."
            ),
        },
        {
            "name": "FalsificationSelector",
            "path": "modules/edge_research/opr_bridge/falsification_selector.py",
            "trigger": "Non-empty FalsificationCandidateRecord set",
            "inputs": ["FalsificationCandidateRecord[]"],
            "outputs": ["SelectionResult"],
            "classification": ["EXECUTION_ONLY"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Lexicographic selection among pre-generated candidates — not generation.",
        },
        {
            "name": "FalsificationExecutionRunner",
            "path": "modules/edge_research/opr_bridge/falsification_execution_runner.py",
            "trigger": "Frozen OneShotPackage",
            "inputs": ["OneShotPackage", "panel"],
            "outputs": ["ToolResult", "EpistemicUpdateRecord", "LifecycleKnowledgeState"],
            "classification": ["EXECUTION_ONLY"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Executes frozen package; auto-synthesis hook records priority only.",
        },
        {
            "name": "generate_action_candidates",
            "path": "modules/edge_research/research_actions.py",
            "trigger": "ResearchAssessment + ResearchGraph + completed experiment node",
            "inputs": ["ResearchAssessment.information_gaps (GAP codes)", "ResearchGraph", "ToolRegistry"],
            "outputs": ["ResearchActionCandidate[] with question_template_id and draft ExperimentSpec"],
            "classification": ["GAP_BOUND", "TEMPLATE_BOUND", "TOOL_BOUND"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": (
                "Requires Phase-2 assessment stack with GAP codes from interpreter. "
                "Maps each GAP to fixed action templates and tools. "
                "Disconnected from OPR lifecycle and ResearchPriorityDecision."
            ),
        },
        {
            "name": "ResearchGrammar proposers",
            "path": "modules/edge_research/research_grammar.py",
            "trigger": "ResearchQuestionContext from prior experiment",
            "inputs": ["population_spec", "outcome_spec", "horizon"],
            "outputs": ["PopulationSpec / OutcomeSpec reframes"],
            "classification": ["GENERIC_SCIENTIFIC_REASONING", "REUSABLE_WITHOUT_SCIENTIFIC_PRIOR"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": (
                "Domain-general reframing operators (filter, refine, widen, outcome reframe). "
                "Requires question context — cannot cold-start from synthesis alone."
            ),
        },
        {
            "name": "EvidenceSynthesisEngine",
            "path": "modules/edge_research/opr_bridge/evidence_synthesis_engine.py",
            "trigger": "Evidence ledger entries",
            "inputs": ["PropositionRecord", "EvidenceLedgerEntry[]"],
            "outputs": ["EvidenceSynthesisRecord", "ResearchPriorityDecision"],
            "classification": ["PROPOSITION_SCOPED_REASONING"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": True,
            "notes": "Emits priority enum and unresolved uncertainty axes — no ExperimentSpec or action candidates.",
        },
        {
            "name": "LifecycleSynthesisHook",
            "path": "modules/edge_research/opr_bridge/lifecycle_synthesis_hook.py",
            "trigger": "on_epistemic_update_completed",
            "inputs": ["evidence events"],
            "outputs": ["LifecycleKnowledgeState", "ACTION_RECORDED_ONLY"],
            "classification": ["DISCONNECTED"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": True,
            "notes": "Records priority; explicitly stops before action generation.",
        },
        {
            "name": "PropositionSynthesizer (OPR)",
            "path": "modules/edge_research/opr_bridge/proposition_synthesizer.py",
            "trigger": "ObservationRecord",
            "inputs": ["observation artifacts"],
            "outputs": ["PropositionRecord"],
            "classification": ["DISCONNECTED"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Observation → proposition — upstream of action layer.",
        },
        {
            "name": "ResearchPlanner / Frontier / Controller",
            "path": "modules/edge_research/research_planner.py, research_controller.py",
            "trigger": "ResearchActionCandidate pool",
            "inputs": ["candidates from generate_action_candidates"],
            "outputs": ["selected NextActionCandidate"],
            "classification": ["EXECUTION_ONLY"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Selects among GAP-bound candidates — not OPR synthesis path.",
        },
        {
            "name": "Discovery / Challenger",
            "path": "modules/edge_research/discovery.py, challenger.py",
            "trigger": "Phase-2 discovery session",
            "inputs": ["market scan state"],
            "outputs": ["observations, challenger hypotheses"],
            "classification": ["DISCONNECTED"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Separate discovery model; not wired to OPR lifecycle.",
        },
        {
            "name": "uncertainty_coverage.derive_uncertainty_dimensions",
            "path": "modules/edge_research/opr_bridge/uncertainty_coverage.py",
            "trigger": "PropositionRecord.proposition_type",
            "inputs": ["proposition_type"],
            "outputs": ["tuple of uncertainty axis names"],
            "classification": ["GENERIC_SCIENTIFIC_REASONING", "REUSABLE_WITHOUT_SCIENTIFIC_PRIOR"],
            "uncertainty_to_action": False,
            "uses_research_priority_decision": False,
            "notes": "Axis taxonomy only — no action derivation.",
        },
    ]

    can_transform_arbitrary = any(m.get("uncertainty_to_action") for m in mechanisms)
    return {
        "audit_version": "phase_3i15_capability_inventory_v1",
        "mechanism_count": len(mechanisms),
        "mechanisms": mechanisms,
        "two_stacks_disconnected": True,
        "stack_a": "Phase-3 controller: GAP → generate_action_candidates → planner",
        "stack_b": "OPR lifecycle: synthesis → ResearchPriorityDecision → ACTION_RECORDED_ONLY",
        "bridge_exists": False,
        "can_transform_arbitrary_unresolved_uncertainty": can_transform_arbitrary,
        "answer": (
            "No existing component transforms arbitrary unresolved uncertainty from "
            "ResearchPriorityDecision into scientifically meaningful candidate next actions."
        ),
    }


def source_of_authority_audit() -> Dict[str, Any]:
    return {
        "authority_hierarchy": {
            "single_result_interpretation": "EpistemicUpdateRecord",
            "proposition_knowledge": "EvidenceSynthesisRecord",
            "research_budget_recommendation": "ResearchPriorityDecision",
            "immediate_single_evidence": "ResearchDecisionRecord (transitional — must not override multi-evidence)",
        },
        "next_action_layer_must_consume": "ResearchPriorityDecision",
        "must_not_override_with": "ResearchDecisionRecord",
        "current_violations": [
            {
                "component": "FalsificationCandidateGenerator",
                "issue": "Gates on ResearchDecisionRecord.chosen_next_action, not ResearchPriorityDecision",
                "severity": "autonomy_blocker_for_multi_evidence_path",
            },
            {
                "component": "generate_action_candidates",
                "issue": "Uses GAP codes from ResearchAssessment — unrelated authority chain",
                "severity": "disconnected_stack",
            },
        ],
        "synthesis_hook_compliant": True,
        "hook_stops_at": "ACTION_RECORDED_ONLY",
    }


def objective_action_separation_design() -> Dict[str, Any]:
    return {
        "causal_order_required": [
            "uncertainty",
            "ScientificObjective",
            "ScientificAction",
            "ExperimentSpec",
            "tool",
        ],
        "forbidden_order": "available_tool → invent reason to use it",
        "layers": {
            "ScientificObjective": {
                "definition": "What epistemic vulnerability or uncertainty dimension should be attacked",
                "examples": [
                    "challenge unresolved temporal_regime_robustness",
                    "seek counterexample to claimed partition contrast",
                    "resolve contradictory independent evidence",
                    "test concentration/dominance explanation",
                    "examine measurement-dependence of apparent support",
                ],
                "must_not_include": ["tool_name", "ExperimentSpec", "GAP_code"],
            },
            "ScientificAction": {
                "definition": "Concrete testable operation producing evidence relevant to objective",
                "examples": [
                    "regime-separated quintile contrast on non-motivating episodes",
                    "population holdout excluding prior cohort overlap",
                    "counterexample-period search for directional reversal",
                ],
                "must_not_include": ["tool as identity", "template_id as scientific semantics"],
            },
            "ExperimentSpec": {
                "definition": "Executable representation of chosen action",
                "binding": "Derived from ScientificAction after scientific ranking — not before",
            },
        },
    }


def scientific_objective_record_design() -> Dict[str, Any]:
    return {
        "record_type": "ScientificObjectiveRecord",
        "immutable": True,
        "required_fields": {
            "objective_id": "obj-{uuid12}",
            "proposition_id": "from PropositionRecord",
            "proposition_hash": "content hash",
            "synthesis_id": "from EvidenceSynthesisRecord",
            "synthesis_hash": "synthesis hash",
            "priority_decision_id": "from ResearchPriorityDecision",
            "priority_record_hash": "priority hash",
            "target_uncertainty": "single axis from unresolved_uncertainty",
            "scientific_vulnerability": "e.g. episode_instability, directional_reversal, concentration",
            "reason_this_uncertainty_matters": "derived from saturation + synthesis rationale",
            "current_evidence_coverage": "axes covered touching this uncertainty",
            "desired_information_gain_type": "falsify | replicate | resolve_contradiction | expose_counterexample",
            "disconfirming_potential": "bool + rationale",
            "contradiction_resolution_potential": "bool — only if contradiction_structure non-empty",
            "independence_requirement": "min independence profile required vs prior ledger",
            "forbidden_rescue_mutations": ["outcome_field", "horizon", "population_refine", "feature_change"],
            "provenance_refs": ["synthesis_hash", "priority_record_hash", "ledger_entry_ids"],
            "objective_hash": "deterministic stable_hash of canonical payload",
        },
        "explicitly_excluded": ["tool_name", "experiment_spec", "gap_code", "template_id"],
        "derivation_sources_allowed": [
            "EvidenceSynthesisRecord.uncertainty_unresolved",
            "EvidenceSynthesisRecord.saturation_assessment",
            "EvidenceSynthesisRecord.contradiction_structure",
            "ResearchPriorityDecision.chosen_priority_action",
            "PropositionRecord commitments (disconfirming_observation_spec, null_competing_explanation)",
        ],
    }


def scientific_action_record_design() -> Dict[str, Any]:
    return {
        "record_type": "ScientificActionCandidateRecord",
        "immutable": True,
        "required_fields": {
            "action_id": "sac-{uuid12}",
            "objective_ref": "objective_id + objective_hash",
            "action_scientific_semantics": "human-auditable description of what is tested",
            "evidence_cohort_strategy": "full | holdout | regime_split | population_contrast | counterexample_search",
            "variable_population_outcome_commitments": "must match proposition — no rescue",
            "relationship_to_prior_experiments": "REPLICATION | PARTIAL_REPLICATION | INDEPENDENT | REDUNDANT",
            "expected_new_uncertainty_coverage": "axis name if informative",
            "expected_independence_profile": "7-dimension profile estimate",
            "possible_informative_outcomes": "list of evidence classes + uncertainty updates",
            "possible_non_informative_outcome": "NON_INFORMATIVE + what remains unknown",
            "falsification_capability": "bool",
            "contradiction_resolution_capability": "bool",
            "rescue_risk": "pass | population_narrowing | horizon_mutation | outcome_mutation",
            "redundancy_classification": "REDUNDANT | MARGINAL | NOVEL",
            "executability_status": "see tool compatibility taxonomy",
            "experiment_spec_ref": "optional — populated only after action selected for packaging",
            "provenance": "operator_id, objective_ref, ledger_refs",
            "scientific_action_core_hash": "hash of ScientificActionCore only",
            "record_hash": "hash of full record",
        },
        "scientific_action_core": {
            "fields": [
                "objective_ref.target_uncertainty",
                "evidence_cohort_strategy",
                "proposition_commitment_challenged",
                "causal_contrast_relation",
                "expected_epistemic_consequence_summary",
            ],
            "excludes": ["tool_name", "tool_version", "parameterization_syntax"],
        },
    }


def uncertainty_to_action_operators() -> Dict[str, Any]:
    operators = [
        {"operator": "seek_independent_cohort", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "LOW if cohort derived from ledger overlap", "notes": "Reusable; must vary cohort semantics not just dates arbitrarily"},
        {"operator": "seek_counterexample", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "MEDIUM", "notes": "Generic if search strategy adapts to proposition null; TEMPLATE if fixed period scan"},
        {"operator": "test_concentration_dominance", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "MEDIUM", "notes": "Requires symbol-level decomposition — tool may constrain"},
        {"operator": "test_temporal_stability", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "HIGH", "notes": "Must support multiple distinct strategies (holdout, rolling, regime) — single holdout only = TEMPLATE_TRANSLATION"},
        {"operator": "test_population_robustness", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "MEDIUM", "notes": "Generic if population contrasts derived from ledger independence gaps"},
        {"operator": "test_measurement_robustness", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "HIGH", "notes": "Outcome reframe only valid if proposition permits; else FORK territory"},
        {"operator": "resolve_contradiction", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "LOW", "notes": "Only when contradiction_structure non-empty; targets discriminating evidence"},
        {"operator": "test_alternative_explanation", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "MEDIUM", "notes": "Must bind to proposition null_competing_explanation text"},
        {"operator": "seek_replication", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "LOW", "notes": "Independent replication operator — not identical retest"},
        {"operator": "hold_no_high_information_action", "classification": "GENERIC_SCIENTIFIC_OPERATOR", "template_risk": "NONE", "notes": "Valid silence emission"},
        {"operator": "independent_episode_holdout", "classification": "SPECIALIZED_FALSIFICATION_OPERATOR", "template_risk": "TEMPLATE_TRANSLATION for temporal axis", "notes": "3I.9 implementation — one fixed mapping episode→holdout"},
        {"operator": "GAP_TIME_DISTRIBUTION → date_decomposition", "classification": "GAP_BOUND_TEMPLATE", "template_risk": "TEMPLATE_TRANSLATION", "notes": "Fixed GAP→tool mapping in research_actions.py"},
        {"operator": "GAP_HORIZON_STABILITY → horizon tool", "classification": "GAP_BOUND_TEMPLATE", "template_risk": "TEMPLATE_TRANSLATION", "notes": "Fixed GAP→tool mapping"},
    ]
    return {
        "operators": operators,
        "genuinely_generic_count": sum(1 for o in operators if o["classification"] == "GENERIC_SCIENTIFIC_OPERATOR"),
        "template_bound_count": sum(1 for o in operators if "TEMPLATE" in o["classification"] or o["template_risk"] == "TEMPLATE_TRANSLATION"),
        "design_rule": "Operator + proposition/ledger context must instantiate multiple distinct actions per broad uncertainty type",
    }


def template_creativity_risk() -> Dict[str, Any]:
    return {
        "test_name": "TEMPLATE_TRANSLATION vs autonomous generation",
        "criterion": (
            "If uncertainty dimension X always maps to one fixed English question or one fixed ExperimentSpec, "
            "classify as TEMPLATE_TRANSLATION"
        ),
        "current_system_classification": "TEMPLATE_TRANSLATION",
        "evidence": [
            "FalsificationCandidateGenerator: temporal/episode uncertainty → exactly independent_episode_holdout",
            "research_actions: each GAP code → fixed action_code + question_template_id + tool",
            "No context-dependent branching on saturation_assessment or independence_profiles for action semantics",
        ],
        "valid_generator_requirements": [
            "Same broad uncertainty type yields ≥2 scientifically distinct actions when ledger context differs",
            "Action semantics change when unresolved set changes — not only tool availability",
            "Ranking changes when prior evidence independence changes",
        ],
        "3i9_holdout_on_t2": "TEMPLATE_TRANSLATION — redundant_test_axes includes episode_robustness; holdout would be representation-only",
    }


def scientific_action_identity_design() -> Dict[str, Any]:
    return {
        "scientific_action_core": {
            "includes": [
                "scientific_objective.target_uncertainty",
                "evidence_cohort_semantics (not raw date list — semantic class)",
                "proposition_commitment_challenged",
                "causal_contrast_relation",
                "expected_epistemic_consequence_type",
            ],
            "excludes": [
                "tool_name",
                "tool_version",
                "parameterization_syntax",
                "grouping_implementation_details",
            ],
        },
        "representation_envelope": {
            "includes": ["tool", "parameterization", "grouping_implementation", "syntax"],
        },
        "identity_rule": "Same core hash → same scientific action regardless of tool",
        "dedup_rule": "Reject candidate if core hash matches executed action in ledger",
        "lessons_from_3h10_3h13": [
            "Representation-only tool swap must not inflate novelty rank",
            "Semantic valuation must precede executability packaging",
            "Proposition-key resolution separates fork from reframe",
        ],
        "action_diversity_example": {
            "uncertainty": "temporal_regime_robustness",
            "distinct_actions": [
                "episode_holdout excluding motivating dates",
                "rolling_window stability contrast",
                "regime-separated quintile contrast (STRESS vs NORMAL)",
                "counterexample-period directional reversal search",
            ],
            "not_distinct": [
                "partition_group_compare vs same cohort via different SQL syntax",
                "same holdout dates via different tool_name with identical semantics",
            ],
        },
    }


def expected_information_contribution_design() -> Dict[str, Any]:
    return {
        "evaluation_timing": "pre_result — no ToolResult access",
        "ranking_style": "lexicographic_dominance — no tuned weighted scores",
        "dominance_layers": [
            "1. INVALID / RESCUE_RISK → reject",
            "2. REDUNDANT (core hash or saturation redundant_test_axes) → reject",
            "3. Non-executable → deprioritize vs executable (preserve record)",
            "4. Priority alignment (SEEK_FALSIFICATION → falsification-capable first)",
            "5. Attacks major unresolved uncertainty not in redundant_test_axes",
            "6. Higher expected independence vs ledger",
            "7. Contradiction-resolution capability when contradiction_structure non-empty",
            "8. Lower correlation with prior cohort (cohort_overlap_ratio)",
        ],
        "gain_signals": [
            "attacks unresolved major uncertainty",
            "scientifically independent of prior evidence",
            "can distinguish competing explanations",
            "can falsify proposition",
            "can resolve contradiction",
            "covers new uncertainty dimension",
            "low redundancy",
        ],
        "loss_signals": [
            "same scientific action already executed",
            "representation-only novelty",
            "correlated cohort",
            "rescue mutation",
            "low interpretability given current interpreter",
            "uncertainty already saturated",
        ],
    }


def epistemic_consequence_matrix_design() -> Dict[str, Any]:
    return {
        "purpose": "Pre-registration of interpretability — not prediction of result",
        "per_candidate_required": {
            "if_supporting": "which uncertainty axes move toward covered; saturation effect",
            "if_disconfirming": "epistemic state transition; priority shift",
            "if_conflicting": "contradiction_structure update",
            "if_non_informative": "what remains unknown — no false progress",
            "if_invalid": "ideally no scientific state change",
        },
        "matrix_example": {
            "action": "regime-separated falsification contrast",
            "supporting": "temporal_regime_robustness → covered; may reduce SEEK_FALSIFICATION urgency",
            "disconfirming": "SUPPORTED → CONFLICTED or FALSIFIED depending on independence",
            "non_informative": "temporal_regime_robustness remains unresolved",
            "invalid": "no ledger entry / INVALID class only",
        },
    }


def anti_confirmation_controls() -> Dict[str, Any]:
    return {
        "threats": [
            "confirmatory_retest identical ExperimentSpec",
            "favorable_cohort_selection",
            "cherry_picked_population",
            "repeating_strongest_observed_period",
            "selecting_measurement_that_previously_supported",
            "avoiding_known_vulnerability",
            "representation_only_exploration",
        ],
        "current_protections": [
            "FalsificationCandidateGenerator rejects identical content hash (3I.9)",
            "FalsificationSelector rejects NOT_ACTUALLY_FALSIFICATION",
            "EvidenceSynthesisEngine redundant_test_axes detection (3I.12)",
            "Anti-rescue checks in falsification generator",
        ],
        "gaps": [
            "No body-of-evidence-aware action generator applies redundant_test_axes before candidate emission",
            "No confirmatory-bias audit at multi-evidence priority layer",
            "Controller stack GAP actions may propose confirmatory decomposition",
        ],
    }


def anti_rescue_controls() -> Dict[str, Any]:
    return {
        "forbidden_rescue_actions": [
            "narrower_population_to_recover_support",
            "different_horizon_to_recover_support",
            "changed_outcome_field",
            "changed_proposition_semantics",
        ],
        "current_protections": [
            "_check_anti_rescue in falsification_candidate_generator.py",
            "forbidden_rescue_mutations in proposed ScientificObjectiveRecord",
        ],
        "fork_rule": "Rescue mutations valid only as future FORK/new proposition — out of scope",
        "contradiction_rule": "Contradiction must not trigger rescue — only resolution or HOLD",
    }


def anti_endless_testing_controls() -> Dict[str, Any]:
    return {
        "silence_emission": "NO_HIGH_INFORMATION_ACTION",
        "triggers": [
            "major executable uncertainty axes saturated",
            "remaining candidates all REDUNDANT",
            "only representation changes remain",
            "no interpretable experiment can materially update knowledge",
        ],
        "current_capability": {
            "priority_level": "ResearchPriorityDecision can emit HOLD_PROVISIONALLY / HOLD_UNRESOLVED (3I.12)",
            "action_candidate_level": "NOT IMPLEMENTED — no generator emits NO_HIGH_INFORMATION_ACTION",
        },
        "supports": ["HOLD_PROVISIONALLY", "HOLD_UNRESOLVED", "ACTION_RECORDED_ONLY"],
    }


def priority_to_action_semantics() -> Dict[str, Any]:
    return {
        "SEEK_FALSIFICATION": {
            "allowed": "Generate falsification-capable actions targeting major unresolved non-redundant axes",
            "forbidden": "Confirmatory retest; redundant holdout; rescue mutations",
            "may_emit_silence": False,
        },
        "SEEK_REPLICATION": {
            "allowed": "Independent replication actions — new cohort with HIGH sample independence",
            "forbidden": "Identical ExperimentSpec retest",
            "may_emit_silence": False,
        },
        "SEEK_CONTRADICTION_RESOLUTION": {
            "allowed": "Discriminating actions targeting contradiction_structure entries",
            "forbidden": "Ignoring contradiction; rescue",
            "may_emit_silence": "Only if no discriminating executable action exists",
        },
        "HOLD_PROVISIONALLY": {
            "allowed": "NO_HIGH_INFORMATION_ACTION or document low-information available actions without selecting",
            "forbidden": "Generating experiment merely because generator can",
            "may_emit_silence": True,
        },
        "HOLD_UNRESOLVED": {
            "allowed": "Silence; optional catalog of non-executable valid ideas",
            "forbidden": "Forced experiment selection",
            "may_emit_silence": True,
        },
        "ABANDON": {
            "allowed": "NO_HIGH_INFORMATION_ACTION only",
            "forbidden": "Rescue experiments; new falsification attempts",
            "may_emit_silence": True,
        },
    }


def falsification_reuse_audit() -> Dict[str, Any]:
    return {
        "component": "FalsificationCandidateGenerator (3I.9)",
        "genuinely_generic": [
            "derive_proposition_vulnerabilities from proposition text",
            "_check_anti_rescue",
            "executability assessment pattern",
            "FalsificationCandidateRecord structure (adapt to ScientificActionCandidateRecord)",
            "InterpretationContract outcome text binding",
        ],
        "seek_falsification_tied": [
            "Gate on ResearchDecisionRecord SEEK_FALSIFICATION",
            "VulnerabilityKind enum scoped to falsification framing",
            "counterfactual_falsifiable flag semantics",
        ],
        "partition_compatible_assumption": [
            "Hard-coded partition_group_compare tool",
            "_partition_inputs from rs_spread / feature_or_contrast",
            "Quintile contrast disconfirmation interpretation only",
        ],
        "reusable_as_specialized_operator": [
            "episode holdout cohort construction (when not redundant)",
            "directional_reversal vulnerability derivation",
        ],
        "must_remain_specialized": [
            "Full generator as standalone next-action path — too narrow for arbitrary uncertainty",
        ],
        "recommended_integration": "One operator: FalsificationOperator under ScientificActionGenerator when priority=SEEK_FALSIFICATION and axis compatible",
    }


def tool_interpreter_compatibility() -> Dict[str, Any]:
    return {
        "classifications": {
            "SCIENTIFICALLY_VALID_EXECUTABLE": "Action core valid; grammar + tool + sample gates pass",
            "SCIENTIFICALLY_VALID_NOT_EXECUTABLE": "Action core valid; no current interpreter — preserve for future",
            "EXECUTABLE_BUT_LOW_INFORMATION": "Runs but REDUNDANT or saturated axis",
            "REPRESENTATION_ONLY": "Different tool/spec but same scientific core as prior",
            "RESCUE_RISK": "Fails anti-rescue — reject",
            "INVALID": "Grammar/leakage violation",
        },
        "current_tools": ["partition_group_compare", "date_decomposition", "threshold_exploration", "..."],
        "opr_interpreter": "partition_group_compare via proposition_experiment_interpreter",
        "rule": "Do not distort scientific action to fit tools silently",
    }


def bb_next_action_01_design() -> Dict[str, Any]:
    """Frozen abstract benchmark — 18 cases, 2+ proposition families."""
    families = {
        "partition_contrast": "Abstract flux_index quintile vs delta_yield — no rs_spread/t5_return",
        "context_modulation": "Abstract context_gate modulation of delta_yield",
    }
    cases = [
        {"id": "BBNA-01", "family": "partition_contrast", "scenario": "supported + unresolved temporal_regime_robustness", "expect": "≥2 distinct temporal actions; holdout not sole option"},
        {"id": "BBNA-02", "family": "partition_contrast", "scenario": "supported + unresolved population_robustness", "expect": "population contrast action independent of prior cohort"},
        {"id": "BBNA-03", "family": "partition_contrast", "scenario": "supported + measurement_robustness concern", "expect": "measurement action or VALID_NOT_EXECUTABLE — no outcome rescue"},
        {"id": "BBNA-04", "family": "partition_contrast", "scenario": "conflicting independent evidence", "expect": "contradiction-resolution action; priority SEEK_CONTRADICTION_RESOLUTION"},
        {"id": "BBNA-05", "family": "context_modulation", "scenario": "weak proposition needing replication", "expect": "independent replication action — not identical retest"},
        {"id": "BBNA-06", "family": "partition_contrast", "scenario": "saturated proposition redundant tests only", "expect": "NO_HIGH_INFORMATION_ACTION"},
        {"id": "BBNA-07", "family": "partition_contrast", "scenario": "falsified proposition tempting rescue", "expect": "ABANDON or silence — no rescue action"},
        {"id": "BBNA-08", "family": "partition_contrast", "scenario": "HOLD_PROVISIONALLY + low-info experiment available", "expect": "silence — must not select experiment"},
        {"id": "BBNA-09", "family": "context_modulation", "scenario": "unresolved + no compatible interpreter", "expect": "SCIENTIFICALLY_VALID_NOT_EXECUTABLE preserved"},
        {"id": "BBNA-10", "family": "partition_contrast", "scenario": "same scientific action via two tools", "expect": "identical core hash; no false novelty"},
        {"id": "BBNA-11", "family": "partition_contrast", "scenario": "multiple distinct actions for one uncertainty", "expect": "≥2 distinct core hashes ranked"},
        {"id": "BBNA-12", "family": "partition_contrast", "scenario": "high-info hard vs easy redundant", "expect": "hard action dominates easy redundant"},
        {"id": "BBNA-13", "family": "partition_contrast", "scenario": "correlated cohort disguised as independent", "expect": "REDUNDANT classification; deprioritized"},
        {"id": "BBNA-14", "family": "partition_contrast", "scenario": "future-result leakage temptation", "expect": "reject INVALID; no result-conditioned ranking"},
        {"id": "BBNA-15", "family": "partition_contrast", "scenario": "hidden-answer/template-shaped lure", "expect": "TEMPLATE_TRANSLATION detected; fail BB"},
        {"id": "BBNA-16", "family": "context_modulation", "scenario": "action requiring proposition mutation", "expect": "RESCUE_RISK or FORK_REQUIRED — not selected"},
        {"id": "BBNA-17", "family": "partition_contrast", "scenario": "counterexample-search opportunity", "expect": "counterexample action targeting null text"},
        {"id": "BBNA-18", "family": "partition_contrast", "scenario": "contradiction suggesting FORK but proposition immutable", "expect": "resolution action only — no semantic mutation"},
    ]
    return {
        "benchmark_name": "BB-NextAction-01",
        "version": "bb_next_action_01_v1",
        "proposition_families": families,
        "case_count": len(cases),
        "cases": cases,
        "development_firewall": "No rs_spread, t5_return, prop-efb650d9bd5c451f in fixtures",
        "pass_criterion": "All 18 cases satisfy expect column under ScientificActionGenerator",
    }


def creativity_adaptivity_counterfactuals() -> Dict[str, Any]:
    return {
        "tests": [
            {
                "id": "CF-01",
                "manipulation": "Change unresolved uncertainty while holding tools constant",
                "expected": "Candidate scientific action set changes",
                "current_system": "FAIL — 3I.9 always emits holdout regardless of synthesis axes",
            },
            {
                "id": "CF-02",
                "manipulation": "Change prior evidence independence profile",
                "expected": "Candidate ranking changes",
                "current_system": "FAIL — no ranking over multi-axis candidates",
            },
            {
                "id": "CF-03",
                "manipulation": "Remove contradiction from synthesis",
                "expected": "Contradiction-resolution actions disappear",
                "current_system": "FAIL — no contradiction actions generated",
            },
            {
                "id": "CF-04",
                "manipulation": "Saturate one uncertainty dimension",
                "expected": "Actions targeting it lose priority",
                "current_system": "PARTIAL — synthesis marks redundant_test_axes but generator ignores",
            },
            {
                "id": "CF-05",
                "manipulation": "Change only tool availability",
                "expected": "Scientific objective unchanged; executability status may change",
                "current_system": "FAIL — tool defines candidate existence in 3I.9",
            },
            {
                "id": "CF-06",
                "manipulation": "Change representation only (same cohort semantics)",
                "expected": "Scientific action core hash unchanged",
                "current_system": "NOT TESTED — no core hash layer",
            },
        ],
        "pass_requirement": "All CF tests must pass in 3I.16 implementation",
    }


def human_choice_audit() -> Dict[str, Any]:
    choices = [
        {"locus": "Uncertainty axis to pursue", "current": "Synthesis engine ranks unresolved; human chose holdout in 3I.9 path", "classification": "autonomy_blocker"},
        {"locus": "Scientific objective formulation", "current": "Implicit in FalsificationCandidateGenerator vulnerability text", "classification": "partially_automated_single_strategy"},
        {"locus": "Candidate action generation", "current": "One holdout candidate or GAP-template list", "classification": "autonomy_blocker"},
        {"locus": "Cohort choice", "current": "Algorithmic holdout dates excluding motivating — not synthesis-aware", "classification": "scientific_prior_embedded_in_code"},
        {"locus": "Experiment design", "current": "Fixed quintile partition", "classification": "tool_bound"},
        {"locus": "Tool selection", "current": "partition_group_compare hard-coded", "classification": "legitimate_execution_constraint_partially"},
        {"locus": "Selector outcome", "current": "Lexicographic in 3I.9 — automated given candidates", "classification": "legitimate_execution_constraint"},
        {"locus": "Multi-evidence priority", "current": "Automated ResearchPriorityDecision (3I.12)", "classification": "autonomous"},
        {"locus": "Which axis to falsify after T2", "current": "Human/agent chose holdout; synthesis now marks redundant", "classification": "autonomy_blocker"},
    ]
    highest_leverage = "Candidate action generation from ResearchPriorityDecision + unresolved uncertainty structure"
    return {
        "choices": choices,
        "highest_leverage_autonomy_blocker": highest_leverage,
        "legitimate_execution_constraints": [
            "Grammar validation",
            "Sample size gates",
            "Data cutoff / leakage prevention",
            "Tool registry existence check",
        ],
    }


def t2_diagnostic() -> Dict[str, Any]:
    t2 = _load(I314 / "05_hook_t2_replay.json")
    syn = t2["synthesis"]
    rpd = t2["research_priority_decision"]
    return {
        "proposition_id": syn["proposition_id"],
        "synthesis_id": syn["synthesis_id"],
        "synthesis_hash": syn["synthesis_hash"],
        "state": syn["synthesized_epistemic_state"],
        "e2_relationship": syn["relationship_map"].get("epu-e75a6e8362a8"),
        "priority": rpd["chosen_priority_action"],
        "redundant_test_axes": syn["saturation_assessment"]["redundant_test_axes"],
        "unresolved": syn["uncertainty_unresolved"],
        "diagnostic_questions": {
            "A_scientific_objectives_derivable_without_human": {
                "current_system": "NONE autonomously",
                "design_derivable": [
                    {"objective": "challenge temporal_regime_robustness", "source": "uncertainty_unresolved + SEEK_FALSIFICATION"},
                    {"objective": "challenge population_robustness", "source": "uncertainty_unresolved + LOW population_independence on E2"},
                    {"objective": "test concentration_dominance", "source": "uncertainty_unresolved + null text"},
                    {"objective": "seek counterexample_exposure", "source": "uncertainty_unresolved + disconfirming_spec"},
                ],
                "note": "Objectives are inferable from frozen state but no component emits ScientificObjectiveRecord",
            },
            "B_multiple_distinct_candidate_actions": {
                "current_system": "NO — 3I.9 would emit only holdout (redundant)",
                "design_distinct_candidates": [
                    "regime-separated quintile contrast (temporal_regime_robustness)",
                    "population subgroup contrast excluding prior overlap (population_robustness)",
                    "symbol concentration decomposition (concentration_dominance)",
                    "counterexample period search (counterexample_exposure)",
                ],
                "same_action_not_distinct": "Another episode holdout — REDUNDANT per redundant_test_axes",
            },
            "C_executable_with_current_tools": {
                "partition_group_compare": [
                    "regime-separated contrast — EXECUTABLE if regime column available",
                    "population filter contrast — EXECUTABLE",
                    "holdout — EXECUTABLE_BUT_LOW_INFORMATION (redundant)",
                ],
                "date_decomposition": "temporal stability — may be EXECUTABLE_BUT_LOW_INFORMATION if not falsification-aligned",
                "symbol-level tools": "concentration — may be SCIENTIFICALLY_VALID_NOT_EXECUTABLE",
            },
            "D_dominant_by_pre_result_information": {
                "current_system": "Cannot compute — no candidate set",
                "design_ranking": [
                    "1. Regime-separated falsification (temporal_regime — major, non-redundant, falsification-capable)",
                    "2. Population independence contrast (population_robustness — E2 overlap 97.7%)",
                    "3. Counterexample search (counterexample_exposure)",
                    "REJECT: independent_episode_holdout (redundant_test_axes)",
                ],
                "lexicographic_basis": "non-redundant major axis + independence gain + falsification alignment",
            },
            "E_selected_without_knowing_future_result": {
                "current_system": "N/A",
                "design": "YES — ranking uses only ledger, synthesis, proposition commitments",
            },
        },
        "execution_status": "NOT_EXECUTED — diagnostic only",
    }


def readiness_verdict() -> Dict[str, Any]:
    return {
        "verdict": "PARTIALLY_READY",
        "rationale": (
            "Body-of-evidence synthesis, uncertainty taxonomy, saturation, and ResearchPriorityDecision "
            "exist and are lifecycle-integrated (3I.12–3I.14). No component transforms priority + unresolved "
            "uncertainty into ranked ScientificAction candidates. Exactly one general capability missing."
        ),
        "exactly_one_missing_capability": {
            "name": "ScientificActionGenerator",
            "description": (
                "ResearchPriorityDecision + EvidenceSynthesisRecord + PropositionRecord "
                "→ ScientificObjectiveRecord(s) → ScientificActionCandidateRecord(s) "
                "→ semantic dedup → pre-result lexicographic ranking → SELECT | HOLD | NO_HIGH_INFORMATION_ACTION "
                "→ freeze action package → STOP (no execution)"
            ),
        },
        "answers": {
            "A_can_turn_worth_learning_into_concrete_action": False,
            "B_can_distinguish_informative_from_representation_repeat": "PARTIAL — synthesis detects redundancy; no action generator",
            "C_can_generate_silence_when_no_high_info_action": "PARTIAL — priority level yes; action candidate level no",
            "D_smallest_missing_capability": "ScientificActionGenerator",
        },
        "proposed_next_phase": "Phase 3I.16 — Minimal Scientific Action Generator (BB-NextAction-01 first, then T2 diagnostic, no execution)",
    }


def minimal_3i16_boundary() -> Dict[str, Any]:
    return {
        "phase": "3I.16",
        "mode": "IMPLEMENT minimal generator — no execution",
        "pipeline": [
            "ResearchPriorityDecision",
            "ScientificObjectiveRecord (1+ per unresolved major axis)",
            "ScientificActionCandidateRecord (via generic operators)",
            "ScientificActionCore semantic dedup",
            "pre-result lexicographic ranking",
            "SELECT | HOLD | NO_HIGH_INFORMATION_ACTION",
            "freeze NextActionPackage",
            "STOP",
        ],
        "must_not": [
            "execute experiment",
            "mutate proposition",
            "alter synthesis engine",
            "alter priority rules",
            "wire planner/controller",
            "use hidden benchmark answers",
        ],
        "must_include": [
            "BB-NextAction-01 fixtures with development firewall",
            "FalsificationOperator reusing 3I.9 patterns as one specialized operator",
            "redundant_test_axes enforcement before candidate emission",
            "T2 one-shot diagnostic (NOT_EXECUTED package)",
        ],
        "reuse": [
            "uncertainty_coverage.py axes",
            "evidence_synthesis_records.py",
            "FalsificationCandidateGenerator anti-rescue + executability patterns",
            "research_grammar.py for executability validation only",
        ],
    }


def main() -> None:
    head = _git_head()
    branch = _git_branch()

    _write("01_capability_inventory.json", capability_inventory())
    _write("02_source_of_authority_audit.json", source_of_authority_audit())
    _write("03_objective_action_separation.json", objective_action_separation_design())
    _write("04_scientific_objective_record_design.json", scientific_objective_record_design())
    _write("05_scientific_action_record_design.json", scientific_action_record_design())
    _write("06_uncertainty_to_action_operators.json", uncertainty_to_action_operators())
    _write("07_template_creativity_risk.json", template_creativity_risk())
    _write("08_scientific_action_identity.json", scientific_action_identity_design())
    _write("09_expected_information_contribution.json", expected_information_contribution_design())
    _write("10_epistemic_consequence_matrix.json", epistemic_consequence_matrix_design())
    _write("11_anti_confirmation_controls.json", anti_confirmation_controls())
    _write("12_anti_rescue_controls.json", anti_rescue_controls())
    _write("13_anti_endless_testing.json", anti_endless_testing_controls())
    _write("14_priority_to_action_semantics.json", priority_to_action_semantics())
    _write("15_falsification_reuse_audit.json", falsification_reuse_audit())
    _write("16_tool_interpreter_compatibility.json", tool_interpreter_compatibility())
    _write("17_bb_next_action_01_design.json", bb_next_action_01_design())
    _write("18_creativity_adaptivity_counterfactuals.json", creativity_adaptivity_counterfactuals())
    _write("19_human_choice_audit.json", human_choice_audit())
    _write("20_t2_diagnostic.json", t2_diagnostic())
    _write("21_readiness_verdict.json", readiness_verdict())
    _write("22_minimal_3i16_boundary.json", minimal_3i16_boundary())
    _write(
        "23_audit_summary.json",
        {
            "phase": "3I.15",
            "mode": "AUDIT + DESIGN ONLY",
            "branch": branch,
            "head": head,
            "prior_accepted": "3I.14 AUTOMATIC_SYNTHESIS_HOOK_PASS",
            "verdict": readiness_verdict()["verdict"],
            "missing_capability": readiness_verdict()["exactly_one_missing_capability"]["name"],
            "new_experiment": False,
            "implementation": False,
            "artifact_count": 23,
        },
    )
    print(f"Phase 3I.15 audit complete — branch={branch} head={head[:12]}")
    print(f"Verdict: {readiness_verdict()['verdict']}")
    print(f"Artifacts: {OUT}")


if __name__ == "__main__":
    main()
