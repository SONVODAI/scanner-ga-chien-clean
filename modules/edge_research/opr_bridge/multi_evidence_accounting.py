"""
Phase 3J.8 — Multi-evidence dependence accounting and incremental contribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_independence import compute_independence_profile
from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_entry
from modules.edge_research.opr_bridge.evidence_relationship_classifier import classify_pair
from modules.edge_research.opr_bridge.evidence_synthesis_records import EvidenceLedgerEntry, EvidenceRelationship
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    EvidenceDirection,
    EvidenceRelevance,
    EvidenceStrength,
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
    NullExplanationState,
)
from modules.edge_research.opr_bridge.lifecycle_records import EvidenceClass


@dataclass(frozen=True)
class EvidenceDependenceAccounting:
    row_overlap_fraction: float
    null_target_overlap: float
    scientific_question_overlap: float
    sample_dependence_level: str
    question_novelty: str
    evidence_relationship: str
    counted_as_independent_replication: bool
    independence_rationale: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_overlap_fraction": self.row_overlap_fraction,
            "null_target_overlap": self.null_target_overlap,
            "scientific_question_overlap": self.scientific_question_overlap,
            "sample_dependence_level": self.sample_dependence_level,
            "question_novelty": self.question_novelty,
            "evidence_relationship": self.evidence_relationship,
            "counted_as_independent_replication": self.counted_as_independent_replication,
            "independence_rationale": list(self.independence_rationale),
        }


@dataclass(frozen=True)
class IncrementalEvidenceContribution:
    raw_evidence_strength: str
    incremental_strength: str
    incremental_direction: str
    double_counting_blocked: bool
    conflict_detected: bool
    conflict_description: str
    rationale: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_evidence_strength": self.raw_evidence_strength,
            "incremental_strength": self.incremental_strength,
            "incremental_direction": self.incremental_direction,
            "double_counting_blocked": self.double_counting_blocked,
            "conflict_detected": self.conflict_detected,
            "conflict_description": self.conflict_description,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class CumulativeEvidenceAssessment:
    experiment_ordinal: int
    per_experiment_assessments: Tuple[Dict[str, Any], ...]
    dependence_accounting: EvidenceDependenceAccounting
    incremental_contribution: IncrementalEvidenceContribution
    cumulative_null_ledger: Tuple[NullExplanationAccounting, ...]
    cumulative_evidence_summary: str
    limitations: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_ordinal": self.experiment_ordinal,
            "per_experiment_assessments": list(self.per_experiment_assessments),
            "dependence_accounting": self.dependence_accounting.to_dict(),
            "incremental_contribution": self.incremental_contribution.to_dict(),
            "cumulative_null_ledger": [n.to_dict() for n in self.cumulative_null_ledger],
            "cumulative_evidence_summary": self.cumulative_evidence_summary,
            "limitations": list(self.limitations),
        }


def _sample_dependence_level(row_overlap: float) -> str:
    if row_overlap >= 0.90:
        return "HIGH"
    if row_overlap >= 0.50:
        return "MEDIUM"
    if row_overlap > 0.0:
        return "LOW"
    return "NONE"


def _question_novelty(null_overlap: float, question_overlap: float) -> str:
    if null_overlap >= 1.0 and question_overlap >= 1.0:
        return "NONE"
    if null_overlap == 0.0 and question_overlap == 0.0:
        return "HIGH"
    if null_overlap == 0.0:
        return "MARGINAL"
    return "LOW"


def _cap_strength(raw: str, *, dependence: str, double_count: bool) -> str:
    order = [
        EvidenceStrength.INSUFFICIENT.value,
        EvidenceStrength.WEAK.value,
        EvidenceStrength.MODERATE.value,
        EvidenceStrength.STRONG.value,
    ]
    if raw not in order:
        return raw
    idx = order.index(raw)
    if double_count or dependence == "HIGH":
        idx = min(idx, order.index(EvidenceStrength.WEAK.value))
    elif dependence == "MEDIUM":
        idx = min(idx, order.index(EvidenceStrength.MODERATE.value))
    return order[idx]


def _ledger_from_assessment(
    *,
    evidence_id: str,
    experiment_id: str,
    experiment_content_hash: str,
    epistemic_update_ref: str,
    assessment: IntentAwareEvidenceAssessment,
    base_interpretation: Dict[str, Any],
    tool_result: Dict[str, Any],
    proposition_id: str,
    proposition_hash: str,
    cohort_overlap: float,
    falsification_intent: bool,
    null_key: str,
) -> EvidenceLedgerEntry:
    pop = (tool_result.get("research_scope") or {}) if isinstance(tool_result.get("research_scope"), dict) else {}
    return build_ledger_entry(
        evidence_id=evidence_id,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        experiment_id=experiment_id,
        experiment_content_hash=experiment_content_hash,
        epistemic_update_ref=epistemic_update_ref,
        evidence_class=str(base_interpretation.get("evidence_class", "INVALID")),
        validity="VALID" if base_interpretation.get("validity_passed") else "INVALID",
        feature_semantics=assessment.cohort_strategy,
        population_semantics=str(pop.get("kind", "all")),
        outcome_semantics=str((tool_result.get("outcome_field") or "t5_return")),
        horizon=str(tool_result.get("horizon", "0")),
        cohort_episode_scope=assessment.cohort_strategy,
        data_cutoff=str(tool_result.get("data_cutoff_date", "")),
        sample_size=int(tool_result.get("sample_size", 0)),
        effect_direction=assessment.evidence_direction,
        effect_magnitude=assessment.evidence_strength,
        measurement_tool=str(tool_result.get("tool_name", "")),
        uncertainty_axis_tested=assessment.target_uncertainty,
        falsification_intent=falsification_intent,
        cohort_overlap_ratio=cohort_overlap,
    )


def _direction_conflict(dir1: str, dir2: str) -> bool:
    opposing = {
        (EvidenceDirection.SUPPORTS.value, EvidenceDirection.CONTRADICTS.value),
        (EvidenceDirection.SUPPORTS.value, EvidenceDirection.WEAKENS.value),
        (EvidenceDirection.CONTRADICTS.value, EvidenceDirection.SUPPORTS.value),
        (EvidenceDirection.WEAKENS.value, EvidenceDirection.SUPPORTS.value),
    }
    return (dir1, dir2) in opposing or (dir2, dir1) in opposing


def build_cumulative_assessment(
    *,
    first_assessment: IntentAwareEvidenceAssessment,
    first_interpretation: Dict[str, Any],
    first_execution_meta: Dict[str, Any],
    second_assessment: IntentAwareEvidenceAssessment,
    second_interpretation: Dict[str, Any],
    second_execution_meta: Dict[str, Any],
    novelty_decomposition: Dict[str, Any],
    proposition_id: str,
    proposition_hash: str,
    first_null_ledger: Tuple[NullExplanationAccounting, ...],
) -> CumulativeEvidenceAssessment:
    row_overlap = float(novelty_decomposition.get("ROW_OVERLAP", 0.0))
    null_overlap = float(novelty_decomposition.get("NULL_TARGET_OVERLAP", 0.0))
    question_overlap = float(novelty_decomposition.get("SCIENTIFIC_QUESTION_OVERLAP", 0.0))
    sample_dep = _sample_dependence_level(row_overlap)
    q_novelty = _question_novelty(null_overlap, question_overlap)

    first_ledger = _ledger_from_assessment(
        evidence_id="evidence_1",
        experiment_id=str(first_execution_meta.get("execution_id", "")),
        experiment_content_hash=str(first_execution_meta.get("experiment_content_hash", "")),
        epistemic_update_ref=str(first_execution_meta.get("epistemic_update_id", "")),
        assessment=first_assessment,
        base_interpretation=first_interpretation,
        tool_result=first_execution_meta.get("tool_result") or {},
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        cohort_overlap=0.0,
        falsification_intent=False,
        null_key=first_assessment.null_accounting[0].null_key if first_assessment.null_accounting else "",
    )
    second_ledger = _ledger_from_assessment(
        evidence_id="evidence_2",
        experiment_id=str(second_execution_meta.get("execution_id", "")),
        experiment_content_hash=str(second_execution_meta.get("experiment_content_hash", "")),
        epistemic_update_ref="",
        assessment=second_assessment,
        base_interpretation=second_interpretation,
        tool_result=second_execution_meta.get("tool_result") or {},
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        cohort_overlap=row_overlap,
        falsification_intent=True,
        null_key=second_assessment.null_accounting[0].null_key if second_assessment.null_accounting else "",
    )

    relationship = classify_pair(second_ledger, first_ledger)
    indep_profile = compute_independence_profile(second_ledger, [first_ledger])
    counted_independent = (
        relationship
        in (
            EvidenceRelationship.INDEPENDENT_REPLICATION,
            EvidenceRelationship.INDEPENDENT_FALSIFICATION,
        )
        and row_overlap < 0.50
    )
    double_count = (
        row_overlap >= 0.85
        and null_overlap >= 1.0
        and question_overlap >= 1.0
    ) or relationship == EvidenceRelationship.EXACT_REPLICATION

    raw_strength = second_assessment.evidence_strength
    incremental_strength = _cap_strength(
        raw_strength,
        dependence=sample_dep,
        double_count=double_count or row_overlap >= 0.85,
    )
    if q_novelty == "HIGH" and null_overlap == 0.0 and row_overlap >= 0.85:
        incremental_strength = _cap_strength(
            raw_strength,
            dependence="HIGH",
            double_count=False,
        )

    conflict = _direction_conflict(first_assessment.evidence_direction, second_assessment.evidence_direction)
    conflict_desc = ""
    if conflict:
        if sample_dep == "HIGH":
            conflict_desc = "directional_conflict_under_high_sample_dependence"
        else:
            conflict_desc = "directional_conflict_with_prior_evidence"

    rationale: List[str] = []
    rationale.extend(indep_profile.rationale)
    if double_count:
        rationale.append("double_counting_blocked:high_overlap_same_question")
    elif row_overlap >= 0.85 and null_overlap == 0.0:
        rationale.append("new_null_high_sample_reuse:not_independent_replication")
    if relationship == EvidenceRelationship.PARTIAL_REPLICATION:
        rationale.append("partial_replication:incremental_contribution_capped")

    incremental = IncrementalEvidenceContribution(
        raw_evidence_strength=raw_strength,
        incremental_strength=incremental_strength,
        incremental_direction=second_assessment.evidence_direction,
        double_counting_blocked=double_count,
        conflict_detected=conflict,
        conflict_description=conflict_desc,
        rationale=tuple(rationale),
    )

    dependence = EvidenceDependenceAccounting(
        row_overlap_fraction=row_overlap,
        null_target_overlap=null_overlap,
        scientific_question_overlap=question_overlap,
        sample_dependence_level=sample_dep,
        question_novelty=q_novelty,
        evidence_relationship=relationship.value,
        counted_as_independent_replication=counted_independent,
        independence_rationale=tuple(indep_profile.rationale),
    )

    cumulative_ledger = _merge_null_ledger(
        first_null_ledger=first_null_ledger,
        second_null_entry=second_assessment.null_accounting[0] if second_assessment.null_accounting else None,
        other_nulls=second_assessment.other_nulls_still_alive,
    )

    limitations = list(second_assessment.limitations)
    if row_overlap >= 0.85:
        limitations.append("high_sample_overlap_with_experiment_1")
    if not counted_independent:
        limitations.append("not_counted_as_independent_replication")

    summary = (
        f"ordinal_2;relationship={relationship.value};"
        f"incremental_strength={incremental_strength};"
        f"sample_dependence={sample_dep};question_novelty={q_novelty}"
    )

    return CumulativeEvidenceAssessment(
        experiment_ordinal=2,
        per_experiment_assessments=(
            {"experiment_ordinal": 1, "assessment": first_assessment.to_dict()},
            {"experiment_ordinal": 2, "assessment": second_assessment.to_dict()},
        ),
        dependence_accounting=dependence,
        incremental_contribution=incremental,
        cumulative_null_ledger=cumulative_ledger,
        cumulative_evidence_summary=summary,
        limitations=tuple(limitations),
    )


def _merge_null_ledger(
    *,
    first_null_ledger: Tuple[NullExplanationAccounting, ...],
    second_null_entry: Optional[NullExplanationAccounting],
    other_nulls: Tuple[str, ...],
) -> Tuple[NullExplanationAccounting, ...]:
    ledger: Dict[str, NullExplanationAccounting] = {}
    for entry in first_null_ledger:
        ledger[entry.null_key] = entry
    if second_null_entry:
        prior = ledger.get(second_null_entry.null_key)
        state_before = prior.state_after if prior else second_null_entry.state_before
        ledger[second_null_entry.null_key] = NullExplanationAccounting(
            null_explanation_text=second_null_entry.null_explanation_text,
            null_key=second_null_entry.null_key,
            state_before=state_before,
            state_after=second_null_entry.state_after,
            rationale=second_null_entry.rationale,
        )
    for key in other_nulls:
        if key not in ledger:
            ledger[key] = NullExplanationAccounting(
                null_explanation_text=key,
                null_key=key,
                state_before=NullExplanationState.STILL_PLAUSIBLE.value,
                state_after=NullExplanationState.STILL_PLAUSIBLE.value,
                rationale="Not tested by Experiment #2",
            )
    return tuple(ledger[k] for k in sorted(ledger.keys()))


def build_rolling_cumulative_assessment(
    *,
    prior_assessments: Tuple[IntentAwareEvidenceAssessment, ...],
    prior_interpretations: Tuple[Dict[str, Any], ...],
    prior_execution_metas: Tuple[Dict[str, Any], ...],
    latest_assessment: IntentAwareEvidenceAssessment,
    latest_interpretation: Dict[str, Any],
    latest_execution_meta: Dict[str, Any],
    novelty_decomposition: Dict[str, Any],
    proposition_id: str,
    proposition_hash: str,
    initial_null_ledger: Tuple[NullExplanationAccounting, ...],
    experiment_ordinal: int,
) -> CumulativeEvidenceAssessment:
    """
    Generalize cumulative assessment for Experiment #N against full prior history.
    Uses conservative max-overlap dependence vs all prior experiments.
    """
    if not prior_assessments:
        raise ValueError("prior_assessments required for rolling cumulative assessment")

    row_overlap = float(novelty_decomposition.get("ROW_OVERLAP", 0.0))
    null_overlap = float(novelty_decomposition.get("NULL_TARGET_OVERLAP", 0.0))
    question_overlap = float(novelty_decomposition.get("SCIENTIFIC_QUESTION_OVERLAP", 0.0))

    prior_ledgers: List[EvidenceLedgerEntry] = []
    max_row_overlap = row_overlap
    for idx, (assess, interp, meta) in enumerate(
        zip(prior_assessments, prior_interpretations, prior_execution_metas), start=1
    ):
        prior_overlap = float(meta.get("cohort_overlap", 0.0))
        max_row_overlap = max(max_row_overlap, prior_overlap, row_overlap)
        prior_ledgers.append(
            _ledger_from_assessment(
                evidence_id=f"evidence_{idx}",
                experiment_id=str(meta.get("execution_id", "")),
                experiment_content_hash=str(meta.get("experiment_content_hash", "")),
                epistemic_update_ref=str(meta.get("epistemic_update_id", "")),
                assessment=assess,
                base_interpretation=interp,
                tool_result=meta.get("tool_result") or {},
                proposition_id=proposition_id,
                proposition_hash=proposition_hash,
                cohort_overlap=prior_overlap,
                falsification_intent=idx > 1,
                null_key=assess.null_accounting[0].null_key if assess.null_accounting else "",
            )
        )

    latest_ledger = _ledger_from_assessment(
        evidence_id=f"evidence_{experiment_ordinal}",
        experiment_id=str(latest_execution_meta.get("execution_id", "")),
        experiment_content_hash=str(latest_execution_meta.get("experiment_content_hash", "")),
        epistemic_update_ref="",
        assessment=latest_assessment,
        base_interpretation=latest_interpretation,
        tool_result=latest_execution_meta.get("tool_result") or {},
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        cohort_overlap=row_overlap,
        falsification_intent=True,
        null_key=latest_assessment.null_accounting[0].null_key if latest_assessment.null_accounting else "",
    )

    relationships = [classify_pair(latest_ledger, pl) for pl in prior_ledgers]
    relationship = relationships[0]
    for rel in relationships[1:]:
        if rel.value in ("EXACT_REPLICATION", "PARTIAL_REPLICATION"):
            relationship = rel

    indep_profile = compute_independence_profile(latest_ledger, prior_ledgers)
    sample_dep = _sample_dependence_level(max_row_overlap)
    q_novelty = _question_novelty(null_overlap, question_overlap)

    double_count = (
        max_row_overlap >= 0.85 and null_overlap >= 1.0 and question_overlap >= 1.0
    ) or relationship == EvidenceRelationship.EXACT_REPLICATION

    counted_independent = (
        relationship
        in (EvidenceRelationship.INDEPENDENT_REPLICATION, EvidenceRelationship.INDEPENDENT_FALSIFICATION)
        and max_row_overlap < 0.50
    )

    raw_strength = latest_assessment.evidence_strength
    incremental_strength = _cap_strength(
        raw_strength,
        dependence=sample_dep,
        double_count=double_count or max_row_overlap >= 0.85,
    )

    prior_dir = prior_assessments[-1].evidence_direction
    conflict = _direction_conflict(prior_dir, latest_assessment.evidence_direction)
    for assess in prior_assessments[:-1]:
        if _direction_conflict(assess.evidence_direction, latest_assessment.evidence_direction):
            conflict = True
            break

    conflict_desc = ""
    if conflict:
        conflict_desc = (
            "directional_conflict_under_high_sample_dependence"
            if sample_dep == "HIGH"
            else "directional_conflict_with_prior_evidence"
        )

    rationale: List[str] = list(indep_profile.rationale)
    if double_count:
        rationale.append("double_counting_blocked:high_overlap_same_question")
    elif max_row_overlap >= 0.85 and null_overlap == 0.0:
        rationale.append("new_null_high_sample_reuse:not_independent_replication")
    rationale.append(f"rolling_history_experiments={len(prior_assessments)}")

    incremental = IncrementalEvidenceContribution(
        raw_evidence_strength=raw_strength,
        incremental_strength=incremental_strength,
        incremental_direction=latest_assessment.evidence_direction,
        double_counting_blocked=double_count,
        conflict_detected=conflict,
        conflict_description=conflict_desc,
        rationale=tuple(rationale),
    )

    dependence = EvidenceDependenceAccounting(
        row_overlap_fraction=max_row_overlap,
        null_target_overlap=null_overlap,
        scientific_question_overlap=question_overlap,
        sample_dependence_level=sample_dep,
        question_novelty=q_novelty,
        evidence_relationship=relationship.value,
        counted_as_independent_replication=counted_independent,
        independence_rationale=tuple(indep_profile.rationale),
    )

    cumulative_ledger = initial_null_ledger
    for assess in prior_assessments[1:]:
        if assess.null_accounting:
            cumulative_ledger = _merge_null_ledger(
                first_null_ledger=cumulative_ledger,
                second_null_entry=assess.null_accounting[0],
                other_nulls=assess.other_nulls_still_alive,
            )
    if latest_assessment.null_accounting:
        cumulative_ledger = _merge_null_ledger(
            first_null_ledger=cumulative_ledger,
            second_null_entry=latest_assessment.null_accounting[0],
            other_nulls=latest_assessment.other_nulls_still_alive,
        )

    per_experiment = tuple(
        {"experiment_ordinal": i + 1, "assessment": a.to_dict()}
        for i, a in enumerate(prior_assessments)
    ) + ({"experiment_ordinal": experiment_ordinal, "assessment": latest_assessment.to_dict()},)

    limitations = list(latest_assessment.limitations)
    if max_row_overlap >= 0.85:
        limitations.append("high_sample_overlap_with_prior_experiments")
    if not counted_independent:
        limitations.append("not_counted_as_independent_replication")

    summary = (
        f"ordinal_{experiment_ordinal};relationship={relationship.value};"
        f"incremental_strength={incremental_strength};"
        f"sample_dependence={sample_dep};max_row_overlap={max_row_overlap:.3f}"
    )

    return CumulativeEvidenceAssessment(
        experiment_ordinal=experiment_ordinal,
        per_experiment_assessments=per_experiment,
        dependence_accounting=dependence,
        incremental_contribution=incremental,
        cumulative_null_ledger=cumulative_ledger,
        cumulative_evidence_summary=summary,
        limitations=tuple(limitations),
    )


AUTHORITATIVE_FALSIFICATION_KEY = "AUTHORITATIVE_FALSIFICATION"
AUTHORITATIVE_FALSIFICATION_PRIORS = frozenset({"SUPPORTED", "WEAKENED", "HYPOTHESIS"})


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def evaluate_authoritative_falsification(
    *,
    prior_state: str,
    base_interpretation: Dict[str, Any],
    incremental: IncrementalEvidenceContribution,
    tested_null_key: str,
    experiment_completed: bool = True,
    falsification_capable: Optional[bool] = None,
    evidence_relevant: Optional[bool] = None,
    frozen_falsify_matched: Optional[bool] = None,
    targeted_null_addressed: Optional[bool] = None,
    integrity_failure: Optional[bool] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Generic contract for later-experiment authoritative falsification.

    Evidence + frozen scientific conditions drive FALSIFIED.
    Action labels such as ABANDON are not consulted.
    """
    ec = str(base_interpretation.get("evidence_class", "INVALID"))
    metrics = base_interpretation.get("metrics_used") or {}
    strength = str(metrics.get("falsify_strength") or "WEAK")
    validity_passed = base_interpretation.get("validity_passed")
    if validity_passed is None:
        validity_passed = not bool(base_interpretation.get("validity_failures"))
    if integrity_failure is None:
        integrity_failure = (
            not bool(validity_passed)
            or incremental.double_counting_blocked
            or incremental.incremental_strength == EvidenceStrength.INSUFFICIENT.value
        )
    if falsification_capable is None:
        falsification_capable = bool(tested_null_key)
    if evidence_relevant is None:
        raw_rel = _enum_value(base_interpretation.get("evidence_relevance"))
        if raw_rel in (None, ""):
            evidence_relevant = ec == EvidenceClass.DISCONFIRMING.value
        else:
            evidence_relevant = (
                ec == EvidenceClass.DISCONFIRMING.value
                and str(raw_rel) == EvidenceRelevance.HIGH.value
            )
    if frozen_falsify_matched is None:
        frozen_falsify_matched = (
            ec == EvidenceClass.DISCONFIRMING.value
            and strength == "STRONG"
            and bool(validity_passed)
        )
    if targeted_null_addressed is None:
        explicit = base_interpretation.get("targeted_null_addressed")
        null_after = str(_enum_value(base_interpretation.get("null_state_after")) or "")
        if explicit is not None:
            targeted_null_addressed = bool(explicit)
        elif null_after:
            targeted_null_addressed = null_after == NullExplanationState.ADDRESSED.value
        else:
            targeted_null_addressed = (
                ec == EvidenceClass.DISCONFIRMING.value
                and strength == "STRONG"
                and bool(tested_null_key)
                and bool(validity_passed)
            )

    checks = {
        "prior_state_eligible": prior_state in AUTHORITATIVE_FALSIFICATION_PRIORS,
        "experiment_completed": bool(experiment_completed),
        "falsification_capable": bool(falsification_capable),
        "evidence_relevant": bool(evidence_relevant),
        "evidence_class_disconfirming": ec == EvidenceClass.DISCONFIRMING.value,
        "falsify_strength_strong": strength == "STRONG",
        "frozen_falsify_matched": bool(frozen_falsify_matched),
        "targeted_null_addressed": bool(targeted_null_addressed),
        "no_integrity_failure": not bool(integrity_failure),
        "no_double_counting": not incremental.double_counting_blocked,
        "incremental_not_insufficient": incremental.incremental_strength
        != EvidenceStrength.INSUFFICIENT.value,
    }
    warranted = all(checks.values())
    rationale = {
        "key": AUTHORITATIVE_FALSIFICATION_KEY if warranted else "AUTHORITATIVE_FALSIFICATION_NOT_WARRANTED",
        "warranted": warranted,
        "prior_state": prior_state,
        "tested_null_key": tested_null_key,
        "evidence_class": ec,
        "falsify_strength": strength,
        "checks": checks,
        "driven_by": "evidence_and_frozen_contract",
        "action_label_ignored": True,
    }
    return warranted, rationale


def apply_incremental_epistemic_transition(
    prior_state: str,
    base_interpretation: Dict[str, Any],
    incremental: IncrementalEvidenceContribution,
    *,
    tested_null_key: str,
    experiment_completed: bool = True,
    falsification_capable: Optional[bool] = None,
    evidence_relevant: Optional[bool] = None,
    frozen_falsify_matched: Optional[bool] = None,
    targeted_null_addressed: Optional[bool] = None,
    integrity_failure: Optional[bool] = None,
    rationale_out: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Apply epistemic transition reflecting incremental — not doubled — evidence.

    A later experiment may move SUPPORTED/WEAKENED → FALSIFIED only when
    evaluate_authoritative_falsification is warranted. Weaker disconfirming
    evidence still yields WEAKENED. ABANDON is not consulted.
    """
    ec = str(base_interpretation.get("evidence_class", "INVALID"))
    warranted, auth_rationale = evaluate_authoritative_falsification(
        prior_state=prior_state,
        base_interpretation=base_interpretation,
        incremental=incremental,
        tested_null_key=tested_null_key,
        experiment_completed=experiment_completed,
        falsification_capable=falsification_capable,
        evidence_relevant=evidence_relevant,
        frozen_falsify_matched=frozen_falsify_matched,
        targeted_null_addressed=targeted_null_addressed,
        integrity_failure=integrity_failure,
    )
    if incremental.double_counting_blocked:
        key = f"{ec}_DOUBLE_COUNT_BLOCKED"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": prior_state})
        return prior_state, key

    if incremental.incremental_strength == EvidenceStrength.INSUFFICIENT.value:
        key = f"{ec}_INSUFFICIENT_INCREMENTAL"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": prior_state})
        return prior_state, key

    if warranted:
        if rationale_out is not None:
            rationale_out.update(
                {
                    **auth_rationale,
                    "key": AUTHORITATIVE_FALSIFICATION_KEY,
                    "resulting": "FALSIFIED",
                    "reason": (
                        "Later experiment met the frozen authoritative falsification "
                        "contract; belief updated from evidence, not from action label."
                    ),
                }
            )
        return "FALSIFIED", AUTHORITATIVE_FALSIFICATION_KEY

    if incremental.conflict_detected:
        if incremental.incremental_strength in (EvidenceStrength.STRONG.value, EvidenceStrength.MODERATE.value):
            key = f"{ec}_CONFLICT"
            if rationale_out is not None:
                rationale_out.update({**auth_rationale, "key": key, "resulting": "WEAKENED"})
            return "WEAKENED", key
        if prior_state == "SUPPORTED":
            key = f"{ec}_DEPENDENT_CONFLICT"
            if rationale_out is not None:
                rationale_out.update({**auth_rationale, "key": key, "resulting": "SUPPORTED"})
            return "SUPPORTED", key
        key = f"{ec}_DEPENDENT_CONFLICT"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": prior_state})
        return prior_state, key

    if ec == EvidenceClass.SUPPORTING.value:
        if prior_state == "SUPPORTED" and incremental.incremental_strength in (
            EvidenceStrength.WEAK.value,
            EvidenceStrength.MODERATE.value,
        ):
            key = "SUPPORTING_INCREMENTAL_MODEST"
            if rationale_out is not None:
                rationale_out.update({**auth_rationale, "key": key, "resulting": "SUPPORTED"})
            return "SUPPORTED", key
        if prior_state in ("HYPOTHESIS", "INSUFFICIENT_EVIDENCE"):
            key = "SUPPORTING"
            if rationale_out is not None:
                rationale_out.update({**auth_rationale, "key": key, "resulting": "SUPPORTED"})
            return "SUPPORTED", key
        key = "SUPPORTING_NO_ESCALATION"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": prior_state})
        return prior_state, key

    if ec == EvidenceClass.DISCONFIRMING.value:
        strength = base_interpretation.get("metrics_used", {}).get("falsify_strength", "WEAK")
        if strength == "STRONG":
            key = "DISCONFIRMING_STRONG"
            if rationale_out is not None:
                rationale_out.update({**auth_rationale, "key": key, "resulting": "WEAKENED"})
            return "WEAKENED", key
        key = "DISCONFIRMING"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": "WEAKENED"})
        return "WEAKENED", key

    if ec == EvidenceClass.CONTRADICTORY.value:
        key = "CONTRADICTORY"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": "WEAKENED"})
        return "WEAKENED", key

    if ec == EvidenceClass.NON_INFORMATIVE.value:
        key = "NON_INFORMATIVE"
        if rationale_out is not None:
            rationale_out.update({**auth_rationale, "key": key, "resulting": prior_state})
        return prior_state, key

    if rationale_out is not None:
        rationale_out.update({**auth_rationale, "key": ec, "resulting": prior_state})
    return prior_state, ec


def incremental_transition_kwargs_from_assessment(
    *,
    interpretation: Dict[str, Any],
    assessment: Any,
    execution_outcome: str,
    tested_null_key: str,
) -> Dict[str, Any]:
    """Map interpreter assessment + execution onto the generic falsification contract."""
    relevance = getattr(assessment, "evidence_relevance", None)
    relevance_val = _enum_value(relevance)
    null_addressed = False
    for entry in getattr(assessment, "null_accounting", ()) or ():
        key = getattr(entry, "null_key", None)
        after = _enum_value(getattr(entry, "state_after", None))
        if key == tested_null_key and after == NullExplanationState.ADDRESSED.value:
            null_addressed = True
            break
    validity_passed = interpretation.get("validity_passed")
    if validity_passed is None:
        validity_passed = not bool(interpretation.get("validity_failures"))
    completed = str(execution_outcome).upper() == "SUCCESS"
    return {
        "experiment_completed": completed,
        "falsification_capable": bool(tested_null_key),
        "evidence_relevant": (
            str(interpretation.get("evidence_class")) == EvidenceClass.DISCONFIRMING.value
            and relevance_val == EvidenceRelevance.HIGH.value
        ),
        "frozen_falsify_matched": (
            str(interpretation.get("evidence_class")) == EvidenceClass.DISCONFIRMING.value
            and str((interpretation.get("metrics_used") or {}).get("falsify_strength") or "") == "STRONG"
            and bool(validity_passed)
        ),
        "targeted_null_addressed": null_addressed,
        "integrity_failure": (not completed) or (not bool(validity_passed)),
    }
