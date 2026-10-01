"""
CONTRAST_TO_PROPOSITION — single general synthesis mechanism.

Derives scientific relation from empirical contrast. Does NOT use 24-template catalog.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.constants import (
    ALLOWED_RELATIONS,
    OBSERVATION_HORIZON,
    OPR_GENERATOR_VERSION,
)
from modules.edge_research.opr_bridge.evidence_ingest import DispersionEvidencePayload, QuintileSlice
from modules.edge_research.opr_bridge.proposition_record import (
    BirthCertificateAnswer,
    Confidence,
    DisconfirmingObservationSpec,
    EpistemicStatus,
    ObservationProvenance,
    PropositionRecord,
    ScientificBirthCertificate,
    stable_proposition_id,
    utc_now_iso,
)
from modules.edge_research.opr_bridge.surprise_detector import SurpriseAssessment
from modules.edge_research.research_proposition_core import build_canonical_proposition_core


def _infer_relation_and_direction(
    quintiles: Tuple[QuintileSlice, ...],
) -> Tuple[str, str, QuintileSlice, QuintileSlice]:
    """Derive relation type and contrast direction from quintile outcome means."""
    sorted_q = sorted(quintiles, key=lambda q: q.mean_dispersion)
    low = sorted_q[0]
    high = sorted_q[-1]
    delta = high.mean_outcome - low.mean_outcome
    if abs(delta) < 1e-9:
        relation = "contrasts_with"
        direction = "flat"
    elif delta > 0:
        relation = "predicts"
        direction = "positive"
    else:
        relation = "predicts"
        direction = "negative"
    if len(quintiles) >= 3 and any(
        quintiles[i].mean_outcome > quintiles[i + 1].mean_outcome
        for i in range(len(quintiles) - 1)
    ) and any(
        quintiles[i].mean_outcome < quintiles[i + 1].mean_outcome
        for i in range(len(quintiles) - 1)
    ):
        relation = "modulates"
    return relation, direction, low, high


def _population_spec_all() -> Dict[str, Any]:
    return {"kind": "all", "grammar_version": "research_grammar_v1"}


def _outcome_spec_compare(field: str, operator: str = ">") -> Dict[str, Any]:
    return {
        "kind": "compare",
        "field": field,
        "operator": operator,
        "value": 0.0,
        "grammar_version": "research_grammar_v1",
    }


def synthesize_contrast_to_proposition(
    evidence: DispersionEvidencePayload,
    surprise: SurpriseAssessment,
    *,
    research_step: int = 0,
    experiment_node_id: str = "opr_evidence_ingest",
) -> PropositionRecord:
    """
    Map empirical dispersion contrast → falsifiable PropositionRecord.

    Scientific content derived from quintile structure, not template catalog.
    """
    feat = evidence.dispersion_feature
    outcome = evidence.outcome_field
    relation, direction, low_q, high_q = _infer_relation_and_direction(evidence.quintile_slices)

    if relation not in ALLOWED_RELATIONS:
        relation = "contrasts_with"

    pop_spec = _population_spec_all()
    out_spec = _outcome_spec_compare(outcome)

    uncertainty_codes: Tuple[str, ...] = ("CROSS_SECTIONAL_DISPERSION",)
    core = build_canonical_proposition_core(
        population_spec=pop_spec,
        outcome_spec=out_spec,
        observation_horizon=OBSERVATION_HORIZON,
        uncertainty_codes=uncertainty_codes,
        conditioning_context={
            "dispersion_feature": feat,
            "focal_date": evidence.focal_date,
            "contrast_direction": direction,
        },
        enrichment_sources=("opr_contrast_to_proposition",),
    )

    core_dict = core.to_dict()

    motivating = (
        f"On {evidence.focal_date}, cross-sectional {feat} std={evidence.cross_sectional_dispersion:.4f} "
        f"across {evidence.cross_sectional_n} symbols; quintile {outcome} spread="
        f"{evidence.quintile_return_spread:.4f}."
    )

    scientific_q = (
        f"Does cross-sectional {feat} dispersion tier predict differential forward {outcome} "
        f"across the market cross-section?"
    )

    if direction == "positive":
        falsifiable = (
            f"High-{feat} quintile mean {outcome} ({high_q.mean_outcome:.4f}) exceeds "
            f"low-{feat} quintile ({low_q.mean_outcome:.4f}) by at least "
            f"{evidence.quintile_return_spread * 0.5:.4f} on partition_group_compare."
        )
        disconfirm_desc = (
            f"If high-{feat} names do not outperform low-{feat} names on forward {outcome} "
            f"when partitioned by {feat} quintile"
        )
        disconfirm_test = (
            f"partition_group_compare median_spread of {outcome} across {feat} quintiles <= 0"
        )
        disconfirm_threshold = "median_spread <= 0 or group rank reversal"
    elif direction == "negative":
        falsifiable = (
            f"Low-{feat} quintile mean {outcome} ({low_q.mean_outcome:.4f}) exceeds "
            f"high-{feat} quintile ({high_q.mean_outcome:.4f}) on partition test."
        )
        disconfirm_desc = (
            f"If low-{feat} names do not outperform high-{feat} names on forward {outcome}"
        )
        disconfirm_test = f"partition_group_compare shows opposite or flat quintile ordering"
        disconfirm_threshold = "quintile ordering reverses or spread < 0.5"
    else:
        falsifiable = f"Quintile spread of {outcome} across {feat} tiers exceeds 0.5."
        disconfirm_desc = f"If {outcome} is flat across {feat} quintiles"
        disconfirm_test = f"quintile_return_spread < 0.5"
        disconfirm_threshold = "spread < 0.5"

    null_expl = (
        f"The {outcome} differential across {feat} quintiles is a small-sample artifact "
        f"or confounded by market-wide level effects on {evidence.focal_date}."
    )

    disconfirm = DisconfirmingObservationSpec(
        description=disconfirm_desc,
        operational_test=disconfirm_test,
        threshold=disconfirm_threshold,
        alternative_interpretation=null_expl,
    )

    provenance = ObservationProvenance(
        evidence_anchor={
            "experiment_node_id": experiment_node_id,
            "tool_name": "opr_dispersion_evidence",
            "tool_version": OPR_GENERATOR_VERSION,
            "data_cutoff_date": evidence.data_cutoff_date,
            "focal_date": evidence.focal_date,
        },
        empirical_artifacts=evidence.empirical_artifacts,
        structural_context={
            "population_spec": pop_spec,
            "outcome_spec": out_spec,
            "observation_horizon": OBSERVATION_HORIZON,
            "feature_slice": feat,
            "focal_date": evidence.focal_date,
        },
        surprise_basis=surprise.surprise_basis_text,
        evidence_hash=evidence.evidence_hash,
    )

    explanatory_relation = {
        "feature_or_contrast": feat,
        "relation_type": relation,
        "comparison_groups": [
            {"label": "low_dispersion_quintile", "quintile": low_q.quintile, "n": low_q.n},
            {"label": "high_dispersion_quintile", "quintile": high_q.quintile, "n": high_q.n},
        ],
        "contrast_direction": direction,
        "empirical_delta": high_q.mean_outcome - low_q.mean_outcome,
    }

    evidence_required = (
        f"Partition-group compare experiment partitioning by {feat} with outcome {outcome} "
        f"at horizon {OBSERVATION_HORIZON}d, cohort n>={low_q.n + high_q.n}."
    )

    execution_requirements = {
        "required_tool_capabilities": ["partition_group_compare"],
        "min_sample": low_q.n + high_q.n,
        "legal_grammar_refs": ["research_grammar_v1", "research_frame_v1"],
        "partition_column": feat,
    }

    confidence = Confidence.MEDIUM if surprise.zscore_vs_baseline >= 2.0 else Confidence.LOW

    bc_answers = (
        BirthCertificateAnswer("BC_Q1", True, motivating),
        BirthCertificateAnswer("BC_Q2", True, surprise.surprise_basis_text),
        BirthCertificateAnswer("BC_Q3", True, scientific_q),
        BirthCertificateAnswer(
            "BC_Q4",
            True,
            f"{scientific_q} Population=all; relation={relation}; outcome={outcome}; horizon={OBSERVATION_HORIZON}.",
        ),
        BirthCertificateAnswer("BC_Q5", True, falsifiable),
        BirthCertificateAnswer("BC_Q6", True, f"{disconfirm.description} ({disconfirm.operational_test})"),
        BirthCertificateAnswer(
            "BC_Q7",
            True,
            "Proposition derived from empirical quintile contrast on focal date, not from template catalog lookup.",
        ),
        BirthCertificateAnswer(
            "BC_Q8",
            True,
            f"partition_group_compare on {feat} with outcome {outcome}.",
        ),
    )

    prop_id = stable_proposition_id(core_dict, evidence.evidence_hash)

    return PropositionRecord(
        proposition_id=prop_id,
        record_version="proposition_record_v1",
        created_at=utc_now_iso(),
        research_step=research_step,
        generator_version=OPR_GENERATOR_VERSION,
        observation_provenance=provenance,
        motivating_observation=motivating,
        surprise_or_uncertainty=surprise.surprise_basis_text,
        scientific_question=scientific_q,
        canonical_proposition_core=core_dict,
        population_context=pop_spec,
        explanatory_relation=explanatory_relation,
        outcome=out_spec,
        observation_horizon=OBSERVATION_HORIZON,
        falsifiable_expectation=falsifiable,
        null_competing_explanation=null_expl,
        disconfirming_observation_spec=disconfirm,
        evidence_required=evidence_required,
        execution_requirements=execution_requirements,
        epistemic_status=EpistemicStatus.HYPOTHESIS,
        confidence=confidence,
        semantic_parent_id=None,
        generation_lineage=(experiment_node_id, evidence.evidence_hash),
        birth_certificate=ScientificBirthCertificate(answers=bc_answers),
    )
