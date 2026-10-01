"""
Phase 3J.13 — Research history context for generic Experiment #N candidate generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.bounded_lifecycle_records import ExperimentHistoryEntry
from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex, candidate_row_keys
from modules.edge_research.opr_bridge.first_experiment_birth_evidence import build_birth_evidence_fingerprint
from modules.edge_research.opr_bridge.first_experiment_execution_overlap import (
    FirstExperimentCohortFingerprint,
    build_first_experiment_fingerprint,
    measure_first_experiment_overlap,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import envelope_from_dict as first_envelope_from_dict
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import SearchAccountingContext
from modules.edge_research.opr_bridge.follow_on_research_decision_adapter import normalize_prior_decision
from modules.edge_research.opr_bridge.second_experiment_execution_persistence import (
    envelope_from_dict as second_envelope_from_dict,
)


def _cohort_strategy_from_package_dict(package: Optional[Dict[str, Any]]) -> str:
    if not package:
        return "unknown"
    sel = package.get("selected_candidate_id")
    if not sel:
        return "unknown"
    for c in package.get("deduplicated_candidates") or package.get("candidates_considered") or []:
        if c.get("candidate_id") == sel:
            return (c.get("scientific_identity") or {}).get("cohort_strategy", "unknown")
    return "unknown"


def _target_from_package(package: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not package:
        return "", ""
    obj = package.get("objective") or {}
    return str(obj.get("target_null_key", "")), str(obj.get("target_uncertainty", ""))


@dataclass(frozen=True)
class PriorExperimentFingerprint:
    ordinal: int
    population_spec: Dict[str, Any]
    cohort_strategy: str
    row_keys: Set[Tuple[str, str]]
    dates: Set[str]
    experiment_content_hash: str
    scientific_action_core_hash: str
    target_null_key: str
    target_uncertainty: str
    tool_name: str
    scientific_identity: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "cohort_strategy": self.cohort_strategy,
            "experiment_content_hash": self.experiment_content_hash,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "target_null_key": self.target_null_key,
            "target_uncertainty": self.target_uncertainty,
            "tool_name": self.tool_name,
            "row_count": len(self.row_keys),
        }


@dataclass(frozen=True)
class FollowOnHistoryContext:
    experiment_ordinal: int
    prior_fingerprints: Tuple[PriorExperimentFingerprint, ...]
    birth_fingerprint: FirstExperimentCohortFingerprint
    birth_evidence: Any
    tested_null_keys: Tuple[str, ...]
    tested_null_cohort_pairs: Tuple[Tuple[str, str, str], ...]
    content_hashes: Tuple[str, ...]
    core_hashes: Tuple[str, ...]
    rejected_core_hashes: Tuple[str, ...]
    cumulative_null_ledger: Tuple[Dict[str, Any], ...]
    search_accounting: SearchAccountingContext
    search_burden_score: float

    @property
    def prior_count(self) -> int:
        return len(self.prior_fingerprints)


def _build_prior_fingerprint(
    entry: ExperimentHistoryEntry,
    panel: PanelMetadataIndex,
) -> Optional[PriorExperimentFingerprint]:
    if not entry.execution:
        return None
    cohort = _cohort_strategy_from_package_dict(entry.package)
    null_key, uncertainty = _target_from_package(entry.package)

    if entry.ordinal == 1:
        env = first_envelope_from_dict(entry.execution)
        fp = build_first_experiment_fingerprint(env, panel, cohort_strategy=cohort)
        sci_id = {
            "cohort_strategy": cohort,
            "contrast_relation": "partition_quintile_contrast",
            "objective_target_uncertainty": uncertainty or "episode_robustness",
        }
        return PriorExperimentFingerprint(
            ordinal=entry.ordinal,
            population_spec=fp.population_spec,
            cohort_strategy=cohort,
            row_keys=fp.row_keys,
            dates=fp.dates,
            experiment_content_hash=fp.experiment_content_hash,
            scientific_action_core_hash=fp.scientific_action_core_hash,
            target_null_key=null_key,
            target_uncertainty=uncertainty,
            tool_name=fp.tool_name,
            scientific_identity=sci_id,
        )

    env = second_envelope_from_dict(entry.execution)
    pop = dict(env.binding_audit.population_spec)
    keys = candidate_row_keys(panel, pop)
    dates = {d for d, _ in keys}
    sci_id = {
        "cohort_strategy": cohort,
        "contrast_relation": "partition_quintile_contrast",
        "objective_target_uncertainty": uncertainty or env.target_uncertainty,
    }
    return PriorExperimentFingerprint(
        ordinal=entry.ordinal,
        population_spec=pop,
        cohort_strategy=cohort,
        row_keys=keys,
        dates=dates,
        experiment_content_hash=env.experiment_content_hash,
        scientific_action_core_hash=env.scientific_action_core_hash,
        target_null_key=null_key or env.target_null_key,
        target_uncertainty=uncertainty or env.target_uncertainty,
        tool_name=env.binding_audit.tool_name,
        scientific_identity=sci_id,
    )


def measure_max_prior_overlap(
    *,
    candidate_population_spec: Dict[str, Any],
    panel: PanelMetadataIndex,
    prior_fingerprints: Tuple[PriorExperimentFingerprint, ...],
) -> Tuple[float, Dict[str, str], int]:
    """Return (max_overlap_fraction, independence_profile, worst_prior_ordinal)."""
    if not prior_fingerprints:
        return 0.0, {"sample_independence": "HIGH", "rationale": "no_prior_experiments"}, 0

    max_overlap = 0.0
    best_indep: Dict[str, str] = {"sample_independence": "HIGH"}
    worst_ord = 0

    for pf in prior_fingerprints:
        fp = FirstExperimentCohortFingerprint(
            population_spec=pf.population_spec,
            cohort_strategy=pf.cohort_strategy,
            row_keys=pf.row_keys,
            dates=pf.dates,
            experiment_content_hash=pf.experiment_content_hash,
            scientific_action_core_hash=pf.scientific_action_core_hash,
            tool_name=pf.tool_name,
        )
        overlap, indep = measure_first_experiment_overlap(
            candidate_population_spec=candidate_population_spec,
            panel=panel,
            first_fp=fp,
        )
        if overlap > max_overlap:
            max_overlap = overlap
            best_indep = indep
            worst_ord = pf.ordinal

    return max_overlap, best_indep, worst_ord


def build_follow_on_history_context(
    *,
    prop: Dict[str, Any],
    history: List[ExperimentHistoryEntry],
    experiment_ordinal: int,
    panel: PanelMetadataIndex,
    prior_decision_dict: Optional[Dict[str, Any]] = None,
) -> FollowOnHistoryContext:
    if experiment_ordinal < 3:
        raise ValueError("follow_on history context requires experiment_ordinal >= 3")

    prior_entries = sorted(
        [e for e in history if e.ordinal < experiment_ordinal and e.execution],
        key=lambda e: e.ordinal,
    )
    prior_fps: List[PriorExperimentFingerprint] = []
    for entry in prior_entries:
        fp = _build_prior_fingerprint(entry, panel)
        if fp:
            prior_fps.append(fp)

    birth = next((e for e in history if e.ordinal == 1), None)
    if not birth or not birth.execution:
        raise ValueError("missing birth execution in history")

    birth_cohort = _cohort_strategy_from_package_dict(birth.package)
    birth_env = first_envelope_from_dict(birth.execution)
    birth_fp = build_first_experiment_fingerprint(birth_env, panel, cohort_strategy=birth_cohort)
    birth_evidence = build_birth_evidence_fingerprint(prop, panel)

    tested_nulls: List[str] = []
    null_cohort_pairs: List[Tuple[str, str, str]] = []
    content_hashes: List[str] = []
    core_hashes: List[str] = []
    rejected_cores: List[str] = []

    for entry in prior_entries:
        nk, tu = _target_from_package(entry.package)
        if nk:
            tested_nulls.append(nk)
        cohort = _cohort_strategy_from_package_dict(entry.package)
        if nk and cohort:
            null_cohort_pairs.append((nk, cohort, tu))

        pkg = entry.package or {}
        for c in pkg.get("candidates_considered") or []:
            if c.get("primary_classification") != "ADMISSIBLE":
                ch = c.get("scientific_action_core_hash")
                if ch:
                    rejected_cores.append(ch)

    for pf in prior_fps:
        if pf.experiment_content_hash:
            content_hashes.append(pf.experiment_content_hash)
        if pf.scientific_action_core_hash:
            core_hashes.append(pf.scientific_action_core_hash)

    cumulative_ledger: Tuple[Dict[str, Any], ...] = ()
    search_accounting = SearchAccountingContext(
        experiments_attempted=len(prior_fps),
        search_complexity_score=float(len(prior_fps) * 2.0),
        search_cardinality=len(prior_fps),
        evidence_burden_assessment="MODERATE",
        budget_exhausted=False,
    )

    if prior_decision_dict:
        norm = normalize_prior_decision(prior_decision_dict)
        cumulative_ledger = norm.cumulative_null_ledger
        search_accounting = norm.search_accounting
        for item in cumulative_ledger:
            nk = str(item.get("null_key", item.get("target_null_key", "")))
            if nk and nk not in tested_nulls:
                tested_nulls.append(nk)

    burden = (
        search_accounting.search_complexity_score
        + search_accounting.search_cardinality * 0.5
        + len(prior_fps) * 0.25
    )

    return FollowOnHistoryContext(
        experiment_ordinal=experiment_ordinal,
        prior_fingerprints=tuple(prior_fps),
        birth_fingerprint=birth_fp,
        birth_evidence=birth_evidence,
        tested_null_keys=tuple(dict.fromkeys(tested_nulls)),
        tested_null_cohort_pairs=tuple(null_cohort_pairs),
        content_hashes=tuple(dict.fromkeys(content_hashes)),
        core_hashes=tuple(dict.fromkeys(core_hashes)),
        rejected_core_hashes=tuple(dict.fromkeys(rejected_cores)),
        cumulative_null_ledger=cumulative_ledger,
        search_accounting=search_accounting,
        search_burden_score=burden,
    )
