"""
Memory-aware proposition selection.

Consults research memory so production does not blindly regenerate the same
family every session. Repetition is allowed only with an explicit scientific
reason. Does not hard-code a preferred feature or edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.feature_registry import LEGACY_SEARCH_FEATURES
from modules.edge_research.opr_bridge.constants import DISPERSION_FEATURE, OUTCOME_FIELD
from modules.edge_research.opr_bridge.evidence_ingest import (
    find_eligible_focal_dates,
    ingest_dispersion_evidence,
)
from modules.edge_research.opr_bridge.proposition_record import PropositionRecord
from modules.edge_research.opr_bridge.proposition_synthesizer import synthesize_contrast_to_proposition
from modules.edge_research.opr_bridge.research_memory import (
    ResearchMemoryStore,
    family_identity_fields,
    family_key_from_proposition,
    scientific_repeat_reasons,
)
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise

# Deterministic scores — not tuned from production outcomes.
SCORE_NOVEL_FAMILY = 100.0
SCORE_UNRESOLVED_NULL = 90.0
SCORE_CONTRADICTION = 90.0
SCORE_ROBUSTNESS = 80.0
SCORE_FORWARD_VALIDATION = 80.0
SCORE_NEW_EPISODE = 10.0
PENALTY_REDUNDANT = 50.0

ADMISSIBLE_OUTCOMES: Tuple[str, ...] = ("t3_return", "t5_return", "t10_return")
MAX_DATES_PER_ALTERNATIVE_ANCHOR = 5

# Memory may switch the day's proposition only in live/shadow research modes.
# Replay, backfill, smoke, and dry-run keep the frozen trigger pick so
# historical artifacts and regression identities stay stable.
MEMORY_SWITCH_MODES = frozenset({"LIVE_FORWARD", "PRODUCTION_SHADOW"})


@dataclass(frozen=True)
class PropositionCandidate:
    record: PropositionRecord
    family_key: str
    feature: str
    outcome: str
    focal_date: str
    surprise_strength: float
    identity_fields: Dict[str, Any]
    source: str = "alternative_anchor"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family_key": self.family_key,
            "feature": self.feature,
            "outcome": self.outcome,
            "focal_date": self.focal_date,
            "surprise_strength": self.surprise_strength,
            "scientific_question": self.record.scientific_question,
            "proposition_id": self.record.proposition_id,
            "source": self.source,
            "identity_fields": dict(self.identity_fields),
        }


@dataclass
class SelectionProvenance:
    selected_family_key: str
    selected_question: str
    selected_feature: str
    selected_outcome: str
    scientific_reasons: Tuple[str, ...]
    why_selected: str
    considered: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    memory_consulted: bool = True
    empty_memory: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_family_key": self.selected_family_key,
            "selected_question": self.selected_question,
            "selected_feature": self.selected_feature,
            "selected_outcome": self.selected_outcome,
            "scientific_reasons": list(self.scientific_reasons),
            "why_selected": self.why_selected,
            "considered": list(self.considered),
            "rejected": list(self.rejected),
            "memory_consulted": self.memory_consulted,
            "empty_memory": self.empty_memory,
        }


def admissible_feature_outcome_pairs(panel: pd.DataFrame) -> List[Tuple[str, str]]:
    """Admissible anchors from existing search-feature machinery ∩ panel columns."""
    if panel is None or panel.empty:
        return []
    cols = set(str(c) for c in panel.columns)
    features = sorted(name for name in LEGACY_SEARCH_FEATURES if name in cols)
    outcomes = [o for o in ADMISSIBLE_OUTCOMES if o in cols]
    return [(f, o) for f in features for o in outcomes]


def candidate_from_record(
    record: PropositionRecord,
    *,
    surprise_strength: float = 0.0,
    focal_date: str = "",
    source: str = "default_pipeline",
) -> PropositionCandidate:
    ident = family_identity_fields(record.to_dict())
    return PropositionCandidate(
        record=record,
        family_key=family_key_from_proposition(record.to_dict()),
        feature=str(ident.get("feature") or ""),
        outcome=str(ident.get("outcome") or ""),
        focal_date=focal_date,
        surprise_strength=float(surprise_strength),
        identity_fields=ident,
        source=source,
    )


def _best_candidate_for_anchor(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    feature: str,
    outcome: str,
    dates: Sequence[str],
) -> Optional[PropositionCandidate]:
    best: Optional[PropositionCandidate] = None
    for date in dates:
        evidence = ingest_dispersion_evidence(
            panel,
            focal_date=date,
            data_cutoff_date=data_cutoff_date,
            dispersion_feature=feature,
            outcome_field=outcome,
        )
        if evidence is None:
            continue
        surprise = assess_dispersion_surprise(evidence)
        if not surprise.is_surprising:
            continue
        record = synthesize_contrast_to_proposition(evidence, surprise)
        strength = abs(float(surprise.zscore_vs_baseline or 0.0)) + float(
            evidence.quintile_return_spread or 0.0
        )
        cand = candidate_from_record(
            record,
            surprise_strength=strength,
            focal_date=date,
            source="alternative_anchor",
        )
        if best is None or cand.surprise_strength > best.surprise_strength:
            best = cand
    return best


def collect_alternative_candidates(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    exclude_pair: Optional[Tuple[str, str]] = None,
) -> List[PropositionCandidate]:
    """
    Scan admissible feature/outcome pairs for surprising contrasts.

    Bounded: registry search features × return columns, recent dates only.
    Other outcomes are probed only on the latest eligible date.
    Deterministic. Does not randomly spam hypotheses.
    """
    exclude_pair = exclude_pair or (DISPERSION_FEATURE, OUTCOME_FIELD)
    default_feature, default_outcome = exclude_pair
    out: List[PropositionCandidate] = []
    pairs = admissible_feature_outcome_pairs(panel)
    for feature, outcome in pairs:
        if (feature, outcome) == exclude_pair:
            continue
        dates = find_eligible_focal_dates(
            panel,
            data_cutoff_date=data_cutoff_date,
            dispersion_feature=feature,
            outcome_field=outcome,
        )
        if not dates:
            continue
        if outcome == default_outcome:
            scan_dates = dates[-MAX_DATES_PER_ALTERNATIVE_ANCHOR:]
        else:
            scan_dates = dates[-1:]
        best = _best_candidate_for_anchor(
            panel,
            data_cutoff_date=data_cutoff_date,
            feature=feature,
            outcome=outcome,
            dates=scan_dates,
        )
        if best is not None:
            out.append(best)
    return out


def _score_candidate(
    candidate: PropositionCandidate,
    memory: ResearchMemoryStore,
    *,
    cutoff_date: str,
) -> Tuple[float, Tuple[str, ...]]:
    family = memory.lookup(candidate.family_key)
    reasons = scientific_repeat_reasons(family, cutoff_date=cutoff_date)
    score = float(candidate.surprise_strength)
    if family is None or "NOVEL_FAMILY" in reasons:
        return score + SCORE_NOVEL_FAMILY, ("NOVEL_FAMILY",)
    if "REDUNDANT_REPETITION" in reasons and len(reasons) == 1:
        return score - PENALTY_REDUNDANT, reasons
    if "UNRESOLVED_NULL" in reasons:
        score += SCORE_UNRESOLVED_NULL
    if "CONTRADICTION" in reasons:
        score += SCORE_CONTRADICTION
    if "ROBUSTNESS_REPLICATION" in reasons:
        score += SCORE_ROBUSTNESS
    if "FORWARD_VALIDATION_PENDING" in reasons:
        score += SCORE_FORWARD_VALIDATION
    if "NEW_INDEPENDENT_EPISODE" in reasons:
        score += SCORE_NEW_EPISODE
        if set(reasons) == {"NEW_INDEPENDENT_EPISODE"}:
            score -= PENALTY_REDUNDANT * 0.7
    return score, reasons


def select_proposition_with_memory(
    *,
    default_candidate: PropositionCandidate,
    alternatives: Sequence[PropositionCandidate],
    memory: ResearchMemoryStore,
    cutoff_date: str,
) -> Tuple[PropositionCandidate, SelectionProvenance]:
    """
    Choose one proposition for this session.

    Empty memory preserves the default pipeline pick (production-safe first day).
    Thereafter, redundant repetition without a scientific reason loses to a
    valid novel family. Strong scientific reasons may reselect the same family.
    """
    empty = not memory.families
    considered = [default_candidate, *list(alternatives)]
    # Deduplicate by family_key, keep highest surprise.
    by_family: Dict[str, PropositionCandidate] = {}
    for cand in considered:
        prev = by_family.get(cand.family_key)
        if prev is None or cand.surprise_strength > prev.surprise_strength:
            by_family[cand.family_key] = cand
    unique = list(by_family.values())

    if empty:
        provenance = SelectionProvenance(
            selected_family_key=default_candidate.family_key,
            selected_question=default_candidate.record.scientific_question,
            selected_feature=default_candidate.feature,
            selected_outcome=default_candidate.outcome,
            scientific_reasons=("EMPTY_MEMORY_DEFAULT_PIPELINE",),
            why_selected=(
                "Research memory was empty, so the existing prioritized pipeline "
                f"pick ({default_candidate.feature} → {default_candidate.outcome}) "
                "was retained. Alternatives were recorded but not promoted."
            ),
            considered=[c.to_dict() for c in unique],
            rejected=[
                {**c.to_dict(), "rejected_reason": "empty_memory_preserve_default_pipeline"}
                for c in unique
                if c.family_key != default_candidate.family_key
            ],
            memory_consulted=True,
            empty_memory=True,
        )
        return default_candidate, provenance

    scored: List[Tuple[float, Tuple[str, ...], PropositionCandidate]] = []
    for cand in unique:
        score, reasons = _score_candidate(cand, memory, cutoff_date=cutoff_date)
        scored.append((score, reasons, cand))
    scored.sort(
        key=lambda row: (-row[0], -row[2].surprise_strength, row[2].family_key)
    )
    best_score, best_reasons, selected = scored[0]

    rejected = []
    for score, reasons, cand in scored[1:]:
        rejected.append(
            {
                **cand.to_dict(),
                "score": score,
                "scientific_reasons": list(reasons),
                "rejected_reason": (
                    "lower_memory_aware_score_than_selected"
                    if cand.family_key != selected.family_key
                    else "duplicate_family"
                ),
            }
        )

    why = (
        f"Selected {selected.feature} → {selected.outcome} because "
        + ", ".join(best_reasons)
        + f" (score={best_score:.3f}). "
        + "Memory was consulted; redundant repetition without a new scientific "
        + "reason is penalized against novel admissible families."
    )
    provenance = SelectionProvenance(
        selected_family_key=selected.family_key,
        selected_question=selected.record.scientific_question,
        selected_feature=selected.feature,
        selected_outcome=selected.outcome,
        scientific_reasons=best_reasons,
        why_selected=why,
        considered=[
            {**c.to_dict(), "score": s, "scientific_reasons": list(r)}
            for s, r, c in scored
        ],
        rejected=rejected,
        memory_consulted=True,
        empty_memory=False,
    )
    return selected, provenance


def candidate_from_prop_dict(
    prop: Dict[str, Any],
    *,
    surprise_strength: float = 0.0,
    focal_date: str = "",
    source: str = "default_pipeline",
) -> PropositionCandidate:
    ident = family_identity_fields(prop)

    class _RecordView:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self.scientific_question = str(payload.get("scientific_question") or "")
            self.proposition_id = payload.get("proposition_id")
            self._payload = payload

        def to_dict(self) -> Dict[str, Any]:
            return dict(self._payload)

    return PropositionCandidate(
        record=_RecordView(prop),  # type: ignore[arg-type]
        family_key=family_key_from_proposition(prop),
        feature=str(ident.get("feature") or ""),
        outcome=str(ident.get("outcome") or ""),
        focal_date=focal_date,
        surprise_strength=float(surprise_strength),
        identity_fields=ident,
        source=source,
    )


def refine_detected_proposition(
    proposition_record: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    memory: Optional[ResearchMemoryStore] = None,
    data_dir: Optional[Any] = None,
    observation_mode: str = "PRODUCTION_SHADOW",
) -> Tuple[Dict[str, Any], SelectionProvenance]:
    """
    Consult research memory after the frozen production trigger.

    Does not modify detect_production_opportunity (3J.14 frozen policy file).
    Empty memory returns the trigger pick unchanged.
    Non-forward replay/backfill/smoke modes consult memory for provenance
    but do not switch the frozen trigger proposition.
    """
    from modules.edge_research.opr_bridge.research_memory import load_research_memory

    store = memory if memory is not None else load_research_memory(data_dir)
    default = candidate_from_prop_dict(
        proposition_record,
        focal_date=data_cutoff_date,
        source="default_pipeline",
    )
    allow_switch = str(observation_mode) in MEMORY_SWITCH_MODES
    if not allow_switch:
        provenance = SelectionProvenance(
            selected_family_key=default.family_key,
            selected_question=default.record.scientific_question,
            selected_feature=default.feature,
            selected_outcome=default.outcome,
            scientific_reasons=("NON_FORWARD_PRESERVE_FROZEN_TRIGGER",),
            why_selected=(
                f"Observation mode {observation_mode} preserves the frozen "
                "prioritized-pipeline pick. Memory was consulted for the family "
                "record but alternatives were not promoted."
            ),
            considered=[default.to_dict()],
            rejected=[],
            memory_consulted=True,
            empty_memory=not store.families,
        )
        return proposition_record, provenance

    alternatives: List[PropositionCandidate] = []
    # Scan alternatives only when this family is already in memory (redundancy
    # is possible). First-seen families keep the frozen trigger pick.
    if store.lookup(default.family_key) is not None:
        exclude = (default.feature, default.outcome) if default.feature and default.outcome else None
        alternatives = collect_alternative_candidates(
            panel,
            data_cutoff_date=data_cutoff_date,
            exclude_pair=exclude,
        )
    selected, provenance = select_proposition_with_memory(
        default_candidate=default,
        alternatives=alternatives,
        memory=store,
        cutoff_date=data_cutoff_date,
    )
    if selected.source == "default_pipeline" or selected.family_key == default.family_key:
        return proposition_record, provenance
    record = selected.record
    if hasattr(record, "to_dict"):
        return record.to_dict(), provenance
    return proposition_record, provenance
