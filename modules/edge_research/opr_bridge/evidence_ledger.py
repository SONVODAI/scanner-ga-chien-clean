"""
Phase 3I.12 — Evidence ledger entry construction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceLedgerEntry,
    stable_hash,
)


def _ledger_hash_body(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "record_hash"}


def build_ledger_entry(
    *,
    evidence_id: str,
    proposition_id: str,
    proposition_hash: str,
    experiment_id: str,
    experiment_content_hash: str,
    epistemic_update_ref: Optional[str],
    evidence_class: str,
    validity: str,
    feature_semantics: str,
    population_semantics: str,
    outcome_semantics: str,
    horizon: str,
    cohort_episode_scope: str,
    data_cutoff: str,
    sample_size: int,
    effect_direction: str,
    effect_magnitude: str,
    measurement_tool: str,
    uncertainty_axis_tested: str,
    falsification_intent: bool,
    cohort_overlap_ratio: float,
    provenance_refs: Optional[Dict[str, str]] = None,
) -> EvidenceLedgerEntry:
    body = {
        "evidence_id": evidence_id,
        "proposition_id": proposition_id,
        "proposition_hash": proposition_hash,
        "experiment_id": experiment_id,
        "experiment_content_hash": experiment_content_hash,
        "epistemic_update_ref": epistemic_update_ref,
        "evidence_class": evidence_class,
        "validity": validity,
        "feature_semantics": feature_semantics,
        "population_semantics": population_semantics,
        "outcome_semantics": outcome_semantics,
        "horizon": horizon,
        "cohort_episode_scope": cohort_episode_scope,
        "data_cutoff": data_cutoff,
        "sample_size": sample_size,
        "effect_direction": effect_direction,
        "effect_magnitude": effect_magnitude,
        "measurement_tool": measurement_tool,
        "uncertainty_axis_tested": uncertainty_axis_tested,
        "falsification_intent": falsification_intent,
        "cohort_overlap_ratio": cohort_overlap_ratio,
        "provenance_refs": provenance_refs or {},
    }
    record_hash = stable_hash(_ledger_hash_body(body))
    return EvidenceLedgerEntry(record_hash=record_hash, **body)


def build_ledger_from_specs(
    proposition_id: str,
    proposition_hash: str,
    specs: List[Dict[str, Any]],
) -> List[EvidenceLedgerEntry]:
    """Build ordered ledger from abstract or normalized evidence specs."""
    entries: List[EvidenceLedgerEntry] = []
    for i, spec in enumerate(specs):
        prior_overlap = 0.0
        if i > 0 and "cohort_overlap_ratio" not in spec:
            prior_overlap = _estimate_overlap_vs_prior(spec, specs[:i])
        overlap = float(spec.get("cohort_overlap_ratio", prior_overlap))
        entries.append(
            build_ledger_entry(
                evidence_id=spec["evidence_id"],
                proposition_id=proposition_id,
                proposition_hash=proposition_hash,
                experiment_id=spec.get("experiment_id", spec["evidence_id"]),
                experiment_content_hash=spec.get("experiment_content_hash", spec["evidence_id"]),
                epistemic_update_ref=spec.get("epistemic_update_ref"),
                evidence_class=spec["evidence_class"],
                validity=spec.get("validity", "VALID"),
                feature_semantics=spec["feature_semantics"],
                population_semantics=spec["population_semantics"],
                outcome_semantics=spec["outcome_semantics"],
                horizon=spec.get("horizon", "H1"),
                cohort_episode_scope=spec["cohort_episode_scope"],
                data_cutoff=spec.get("data_cutoff", "2020-01-01"),
                sample_size=int(spec.get("sample_size", 100)),
                effect_direction=spec.get("effect_direction", "positive"),
                effect_magnitude=spec.get("effect_magnitude", "strong"),
                measurement_tool=spec.get("measurement_tool", "tier_compare"),
                uncertainty_axis_tested=spec["uncertainty_axis_tested"],
                falsification_intent=bool(spec.get("falsification_intent", False)),
                cohort_overlap_ratio=overlap,
                provenance_refs=spec.get("provenance_refs"),
            )
        )
    return entries


def _estimate_overlap_vs_prior(spec: Dict[str, Any], prior: List[Dict[str, Any]]) -> float:
    if not prior:
        return 0.0
    best = 0.0
    for p in prior:
        if spec.get("experiment_content_hash") == p.get("experiment_content_hash"):
            return 1.0
        if (
            spec.get("feature_semantics") == p.get("feature_semantics")
            and spec.get("outcome_semantics") == p.get("outcome_semantics")
            and spec.get("population_semantics") == p.get("population_semantics")
            and spec.get("cohort_episode_scope") == p.get("cohort_episode_scope")
        ):
            best = max(best, 1.0)
        elif (
            spec.get("feature_semantics") == p.get("feature_semantics")
            and spec.get("outcome_semantics") == p.get("outcome_semantics")
        ):
            overlap_hint = spec.get("cohort_overlap_ratio")
            if overlap_hint is not None:
                best = max(best, float(overlap_hint))
            elif spec.get("population_semantics") != p.get("population_semantics"):
                best = max(best, 0.5)
            else:
                best = max(best, 0.9)
    return best
