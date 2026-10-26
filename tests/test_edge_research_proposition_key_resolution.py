"""Phase 3H.12 — Canonical proposition core and same-question detection tests."""

from __future__ import annotations

import pytest

from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_line_identity import (
    ResearchLineIdentity,
    derive_identity_from_candidate,
    derive_identity_from_experiment_spec,
)
from modules.edge_research.research_line_registry import assign_experiment_to_line
from modules.edge_research.research_line_relationship import (
    ResearchLineRelationship,
    classify_research_line_relationship,
)
from modules.edge_research.research_novelty_valuation_bridge import (
    NoveltyValuationClass,
    apply_novelty_valuation_bridge,
    classify_novelty_valuation,
    gate_novelty_component,
)
from modules.edge_research.research_planner import WEIGHT_NOVELTY
from modules.edge_research.research_portfolio import WEIGHT_NOVELTY_PORTFOLIO
from modules.edge_research.research_proposition_core import (
    build_canonical_proposition_core,
    cores_same_question,
    instrument_features_materially_different,
    RepresentationEnvelope,
)
from modules.edge_research.research_state import ExperimentSpec, NodeType

CUTOFF = "2026-08-20"
POP = {"grammar_version": "research_grammar_v1", "kind": "all"}
OUT = {"field": "t5_return", "grammar_version": "research_grammar_v1", "kind": "compare", "operator": ">", "value": 0.0}
OUT_B = {"field": "t10_return", "grammar_version": "research_grammar_v1", "kind": "compare", "operator": ">", "value": 0.0}
POP_B = {"grammar_version": "research_grammar_v1", "kind": "refine", "children": [{"field": "t5_return", "kind": "filter", "operator": ">", "value": 0.0}]}


def _graph() -> ResearchGraph:
    g = ResearchGraph.create_session(session_id="prop-key-test", data_cutoff_date=CUTOFF, experiment_budget=12)
    g.session.panel_preflight = {"eligible_explanatory": ["f1", "f2", "rs10", "rs_spread"]}
    return g


def _identity(**kwargs) -> ResearchLineIdentity:
    defaults = dict(
        population_spec=POP,
        outcome_spec=OUT,
        observation_horizon=0,
        uncertainty_codes=("HORIZON_STABILITY",),
        research_needs=(),
        conditioning_context={},
        feature_slice=(),
        evidence_lineage=(),
        metadata={"tool_name": "horizon_comparison", "action_id": "a1"},
    )
    defaults.update(kwargs)
    from modules.edge_research.research_line_identity import RESEARCH_LINE_IDENTITY_VERSION, _build_identity

    return _build_identity(
        pop=defaults["population_spec"],
        out=defaults["outcome_spec"],
        horizon=defaults["observation_horizon"],
        conditioning=defaults["conditioning_context"],
        uncertainty_codes=defaults["uncertainty_codes"],
        research_needs=defaults["research_needs"],
        feature_slice=defaults["feature_slice"],
        evidence_lineage=defaults["evidence_lineage"],
        metadata=defaults["metadata"],
    )


def _spec(tool: str, feat: str = "f1", pop=None, out=None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs={"feature_column": feat},
        research_scope={
            "population_spec": pop or POP,
            "outcome_spec": out or OUT,
            "pending_question_context": {"observation_horizon": 0},
        },
        data_cutoff_date=CUTOFF,
    )


def _candidate(tool: str, feat: str = "f1", pop=None, out=None, action_id: str = "c1"):
    from modules.edge_research.research_actions import ResearchActionCandidate

    spec = _spec(tool, feat, pop, out)
    return ResearchActionCandidate(
        action_id=action_id,
        action_code="TEST",
        intent="RUN_TOOL",
        question_template_id="T",
        question_text="q",
        tool_name=tool,
        tool_version="v1",
        draft_spec=spec,
        uncertainty_addressed="HORIZON_STABILITY",
        expected_information="MEDIUM",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )


class TestPropositionPairMatrix:
    """Pre-registered cases A–L."""

    def test_A_same_question_different_tool(self):
        prior = _identity(metadata={"tool_name": "horizon_comparison", "action_id": "p1"})
        cand = _identity(metadata={"tool_name": "adaptive_partition_compare", "action_id": "c1"})
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification == ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value

    def test_B_same_question_different_frame_representation(self):
        prior = _identity(metadata={"tool_name": "horizon_comparison", "action_id": "p1", "frame_id": "f1"})
        cand = _identity(metadata={"tool_name": "horizon_comparison", "action_id": "c1", "frame_id": "f2"})
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification in (
            ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
            ResearchLineRelationship.NEAR_DUPLICATE.value,
        )

    def test_C_same_question_fresh_evidence(self):
        prior = _identity(metadata={"tool_name": "horizon_comparison", "action_id": "p1"})
        cand = _identity(metadata={"tool_name": "sensitivity_analysis", "action_id": "c1"})
        audit = classify_research_line_relationship(prior, cand, new_evidence_available=True)
        assert audit.classification == ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value

    def test_D_same_feature_different_outcome_distinct(self):
        prior = _identity(outcome_spec=OUT)
        cand = _identity(outcome_spec=OUT_B)
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification in (
            ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
            ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        )
        assert audit.classification != ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value

    def test_E_different_population_distinct(self):
        prior = _identity(population_spec=POP)
        cand = _identity(population_spec=POP_B)
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification in (
            ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
            ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
        )

    def test_F_different_uncertainty_distinct(self):
        prior = _identity(uncertainty_codes=("HORIZON_STABILITY",))
        cand = _identity(uncertainty_codes=("EPISODE_REPLICATION",))
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification in (
            ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
            ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
        )

    def test_G_superficial_slice_same_core(self):
        prior = _identity(feature_slice=("f1",), metadata={"tool_name": "adaptive_partition_compare", "action_id": "p1"})
        cand = _identity(feature_slice=("f1",), metadata={"tool_name": "threshold_exploration", "action_id": "c1"})
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification == ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value

    def test_H_material_slice_distinct(self):
        prior = _identity(
            feature_slice=("f1",),
            uncertainty_codes=("HORIZON_STABILITY",),
            metadata={"tool_name": "adaptive_partition_compare", "action_id": "p1"},
        )
        cand = _identity(
            feature_slice=("f2",),
            uncertainty_codes=("HORIZON_STABILITY",),
            metadata={"tool_name": "adaptive_partition_compare", "action_id": "c1"},
        )
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification == ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value

    def test_I_different_horizon_distinct(self):
        prior = _identity(observation_horizon=0)
        cand = _identity(observation_horizon=5)
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification in (
            ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
            ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        )

    def test_J_missing_fields_insufficient_evidence(self):
        prior = _identity(population_spec={}, outcome_spec={})
        cand = _identity(population_spec={}, outcome_spec={})
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification == ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value

    def test_K_independent_proposition(self):
        prior = _identity(population_spec=POP, outcome_spec=OUT, uncertainty_codes=("HORIZON_STABILITY",))
        cand = _identity(population_spec=POP_B, outcome_spec=OUT_B, uncertainty_codes=("EPISODE_REPLICATION",))
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification == ResearchLineRelationship.GENUINELY_INDEPENDENT.value

    def test_L_tool_name_alone_not_sufficient(self):
        """Same tool, different core — must NOT classify as same question."""
        prior = _identity(outcome_spec=OUT, metadata={"tool_name": "horizon_comparison", "action_id": "p1"})
        cand = _identity(outcome_spec=OUT_B, metadata={"tool_name": "horizon_comparison", "action_id": "c1"})
        audit = classify_research_line_relationship(prior, cand)
        assert audit.classification != ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value


class TestBranchContextEnrichment:
    def _add_experiment(self, g: ResearchGraph, spec: ExperimentSpec, node_id: str = "exp-parent") -> str:
        from modules.edge_research.research_state import NodeStatus, ResearchNode

        g.nodes[node_id] = ResearchNode(
            node_id=node_id,
            session_id=g.session.research_session_id,
            node_type=NodeType.EXPERIMENT,
            status=NodeStatus.RESOLVED,
            created_at="2026-08-20T00:00:00Z",
            parent_node_ids=[],
            experiment_spec=spec,
        )
        return node_id

    def test_missing_outcome_enriched_from_branch_root(self):
        g = _graph()
        parent_spec = _spec("horizon_comparison", pop=POP, out=OUT)
        parent_id = self._add_experiment(g, parent_spec)
        mech_spec = ExperimentSpec(
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            inputs={"feature_column": "rs10"},
            research_scope={"population_spec": POP},
            data_cutoff_date=CUTOFF,
        )
        from modules.edge_research.research_actions import ResearchActionCandidate

        cand = ResearchActionCandidate(
            action_id="mech1",
            action_code="TEST",
            intent="RUN_TOOL",
            question_template_id="T",
            question_text="q",
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            draft_spec=mech_spec,
            uncertainty_addressed="HORIZON_STABILITY",
            expected_information="MEDIUM",
            budget_cost=1,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
        )
        ident = derive_identity_from_candidate(cand, graph=g, branch_root_id=parent_id)
        assert ident is not None
        assert ident.outcome_spec == OUT
        assert "branch_root.outcome_spec" in (ident.canonical_core.get("enrichment_sources") or [])

    def test_enriched_candidate_activates_novelty_gating(self):
        g = _graph()
        parent_spec = _spec("horizon_comparison")
        parent_id = self._add_experiment(g, parent_spec)
        prior_ident = derive_identity_from_experiment_spec(
            experiment_spec=parent_spec, uncertainty_codes=("HORIZON_STABILITY",)
        )
        assign_experiment_to_line(g, experiment_node_id=parent_id, identity=prior_ident, gain_level="LOW")

        mech_spec = ExperimentSpec(
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            inputs={"feature_column": "f1"},
            research_scope={"population_spec": POP},
            data_cutoff_date=CUTOFF,
        )
        from modules.edge_research.research_actions import ResearchActionCandidate

        cand = ResearchActionCandidate(
            action_id="mech1",
            action_code="TEST",
            intent="RUN_TOOL",
            question_template_id="T",
            question_text="q",
            tool_name="adaptive_partition_compare",
            tool_version="v1",
            draft_spec=mech_spec,
            uncertainty_addressed="HORIZON_STABILITY",
            expected_information="MEDIUM",
            budget_cost=1,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
        )
        assessment = ResearchAssessment(
            source_experiment_node_id=parent_id,
            tool_name="adaptive_partition_compare",
            tool_status="OK",
            information_gaps=("HORIZON_STABILITY",),
            branch_tools_attempted=("horizon_comparison",),
            branch_observation_codes=(),
            descriptive_strength=DescriptiveStrength.GROUP_DIFFERENCE.value,
            interesting=True,
        )
        raw = WEIGHT_NOVELTY * (WEIGHT_NOVELTY_PORTFOLIO / 2.0)
        gated, audit = apply_novelty_valuation_bridge(
            g, cand, assessment, raw_novelty_component=raw, branch_root_id=parent_id
        )
        assert audit.valuation_class == NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value
        assert gated == 0.0
        assert gated < raw


class TestNoNegativePenalty:
    def test_gating_never_negative(self):
        raw = 1.5
        assert gate_novelty_component(raw, valuation_class=NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value) == 0.0


class TestCoreKeyExcludesInstrument:
    def test_different_tools_same_core_key(self):
        a = build_canonical_proposition_core(
            population_spec=POP, outcome_spec=OUT, observation_horizon=0, uncertainty_codes=("HORIZON_STABILITY",)
        )
        b = build_canonical_proposition_core(
            population_spec=POP, outcome_spec=OUT, observation_horizon=0, uncertainty_codes=("HORIZON_STABILITY",)
        )
        assert cores_same_question(a, b)
        rep_a = RepresentationEnvelope(tool_name="horizon_comparison", instrument_features=("f1",))
        rep_b = RepresentationEnvelope(tool_name="adaptive_partition_compare", instrument_features=("f1",))
        assert rep_a.tool_name != rep_b.tool_name
        assert not instrument_features_materially_different(rep_a, rep_b)
