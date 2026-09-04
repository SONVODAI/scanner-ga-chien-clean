"""
Production-safe cross-episode research memory.

Remembers proposition families so future generation/selection can consult
prior SUPPORT / FALSIFY / unresolved / forward history. Does not encode a
preferred edge and does not rewrite historical birth records.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.storage import resolve_data_dir

RESEARCH_MEMORY_VERSION = "research_memory_v1"
MEMORY_INDEX_FILE = "research_memory_index.json"
MEMORY_EVENTS_FILE = "research_memory_events.jsonl"
MEMORY_DIRNAME = "research_memory"

CLAIM_FAMILY_CROSS_SECTIONAL_TIER = "CROSS_SECTIONAL_TIER_DIFFERENTIAL"


def proposition_family_key(
    *,
    feature: str,
    outcome: str,
    horizon: Any,
    population_kind: str,
    claim_family: str,
) -> str:
    """Stable family identity — excludes date, evidence hash, and proposition_id."""
    return stable_hash(
        {
            "feature": str(feature or ""),
            "outcome": str(outcome or ""),
            "horizon": horizon,
            "population_kind": str(population_kind or "all"),
            "claim_family": str(claim_family or ""),
        }
    )


def family_key_from_proposition(prop: Dict[str, Any]) -> str:
    rel = prop.get("explanatory_relation") or {}
    exec_req = prop.get("execution_requirements") or {}
    outcome = prop.get("outcome") or {}
    codes = ((prop.get("canonical_proposition_core") or {}).get("uncertainty_codes")) or ()
    claim_family = (
        CLAIM_FAMILY_CROSS_SECTIONAL_TIER
        if ("CROSS_SECTIONAL_DISPERSION" in codes or exec_req.get("partition_column"))
        else "GENERIC"
    )
    return proposition_family_key(
        feature=str(exec_req.get("partition_column") or rel.get("feature_or_contrast") or ""),
        outcome=str(outcome.get("field") or ""),
        horizon=prop.get("observation_horizon"),
        population_kind=str((prop.get("population_context") or {}).get("kind") or "all"),
        claim_family=claim_family,
    )


def family_identity_fields(prop: Dict[str, Any]) -> Dict[str, Any]:
    rel = prop.get("explanatory_relation") or {}
    exec_req = prop.get("execution_requirements") or {}
    outcome = prop.get("outcome") or {}
    codes = ((prop.get("canonical_proposition_core") or {}).get("uncertainty_codes")) or ()
    claim_family = (
        CLAIM_FAMILY_CROSS_SECTIONAL_TIER
        if ("CROSS_SECTIONAL_DISPERSION" in codes or exec_req.get("partition_column"))
        else "GENERIC"
    )
    return {
        "feature": str(exec_req.get("partition_column") or rel.get("feature_or_contrast") or ""),
        "outcome": str(outcome.get("field") or ""),
        "horizon": prop.get("observation_horizon"),
        "population_kind": str((prop.get("population_context") or {}).get("kind") or "all"),
        "claim_family": claim_family,
        "directional_claim": rel.get("contrast_direction"),
        "scientific_question": prop.get("scientific_question"),
    }


@dataclass
class PropositionFamilyMemory:
    family_key: str
    feature: str = ""
    outcome: str = ""
    horizon: Any = None
    population_kind: str = "all"
    claim_family: str = ""
    directional_claim: Optional[str] = None
    scientific_question: Optional[str] = None
    market_context_hashes: List[str] = field(default_factory=list)
    episode_count: int = 0
    tested_episode_dates: List[str] = field(default_factory=list)
    support_count: int = 0
    falsify_count: int = 0
    unresolved_count: int = 0
    contradiction_count: int = 0
    surviving_nulls: List[str] = field(default_factory=list)
    forward_validation_history: List[Dict[str, Any]] = field(default_factory=list)
    last_tested_date: Optional[str] = None
    last_focal_date: Optional[str] = None
    last_epistemic_state: Optional[str] = None
    repetition_count: int = 0
    last_selection_provenance: Optional[Dict[str, Any]] = None
    observation_ids: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family_key": self.family_key,
            "feature": self.feature,
            "outcome": self.outcome,
            "horizon": self.horizon,
            "population_kind": self.population_kind,
            "claim_family": self.claim_family,
            "directional_claim": self.directional_claim,
            "scientific_question": self.scientific_question,
            "market_context_hashes": list(self.market_context_hashes),
            "episode_count": self.episode_count,
            "tested_episode_dates": list(self.tested_episode_dates),
            "support_count": self.support_count,
            "falsify_count": self.falsify_count,
            "unresolved_count": self.unresolved_count,
            "contradiction_count": self.contradiction_count,
            "surviving_nulls": list(self.surviving_nulls),
            "forward_validation_history": list(self.forward_validation_history),
            "last_tested_date": self.last_tested_date,
            "last_focal_date": self.last_focal_date,
            "last_epistemic_state": self.last_epistemic_state,
            "repetition_count": self.repetition_count,
            "last_selection_provenance": self.last_selection_provenance,
            "observation_ids": list(self.observation_ids),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PropositionFamilyMemory":
        return cls(
            family_key=payload["family_key"],
            feature=payload.get("feature", ""),
            outcome=payload.get("outcome", ""),
            horizon=payload.get("horizon"),
            population_kind=payload.get("population_kind", "all"),
            claim_family=payload.get("claim_family", ""),
            directional_claim=payload.get("directional_claim"),
            scientific_question=payload.get("scientific_question"),
            market_context_hashes=list(payload.get("market_context_hashes") or []),
            episode_count=int(payload.get("episode_count", 0)),
            tested_episode_dates=list(payload.get("tested_episode_dates") or []),
            support_count=int(payload.get("support_count", 0)),
            falsify_count=int(payload.get("falsify_count", 0)),
            unresolved_count=int(payload.get("unresolved_count", 0)),
            contradiction_count=int(payload.get("contradiction_count", 0)),
            surviving_nulls=list(payload.get("surviving_nulls") or []),
            forward_validation_history=list(payload.get("forward_validation_history") or []),
            last_tested_date=payload.get("last_tested_date"),
            last_focal_date=payload.get("last_focal_date"),
            last_epistemic_state=payload.get("last_epistemic_state"),
            repetition_count=int(payload.get("repetition_count", 0)),
            last_selection_provenance=payload.get("last_selection_provenance"),
            observation_ids=list(payload.get("observation_ids") or []),
            updated_at=payload.get("updated_at") or utc_now_iso(),
        )

    def has_unresolved_null(self) -> bool:
        return self.unresolved_count > 0 or bool(self.surviving_nulls)

    def has_contradiction(self) -> bool:
        return self.contradiction_count > 0

    def needs_replication(self) -> bool:
        return self.support_count > 0 and self.episode_count < 2

    def forward_validation_pending(self) -> bool:
        if not self.forward_validation_history:
            return self.episode_count > 0
        last = self.forward_validation_history[-1]
        return str(last.get("adjudication") or "") in {
            "",
            "MISSING_DATA",
            "CONTEXT_ONLY",
            "LEGACY_INSUFFICIENT_CLAIM_SPEC",
            "CLAIM_INCONCLUSIVE",
        }


@dataclass
class ResearchMemoryStore:
    version: str = RESEARCH_MEMORY_VERSION
    families: Dict[str, PropositionFamilyMemory] = field(default_factory=dict)

    def lookup(self, family_key: str) -> Optional[PropositionFamilyMemory]:
        return self.families.get(family_key)

    def upsert(self, family: PropositionFamilyMemory) -> None:
        family.updated_at = utc_now_iso()
        self.families[family.family_key] = family

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "families": {k: v.to_dict() for k, v in sorted(self.families.items())},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchMemoryStore":
        families = {
            k: PropositionFamilyMemory.from_dict(v)
            for k, v in (payload.get("families") or {}).items()
        }
        return cls(version=payload.get("version", RESEARCH_MEMORY_VERSION), families=families)


def _memory_dir(data_dir: Optional[Path] = None) -> Path:
    path = resolve_data_dir(data_dir) / MEMORY_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_index_path(data_dir: Optional[Path] = None) -> Path:
    return _memory_dir(data_dir) / MEMORY_INDEX_FILE


def memory_events_path(data_dir: Optional[Path] = None) -> Path:
    return _memory_dir(data_dir) / MEMORY_EVENTS_FILE


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def load_research_memory(data_dir: Optional[Path] = None) -> ResearchMemoryStore:
    path = memory_index_path(data_dir)
    if not path.exists():
        store = ResearchMemoryStore()
        _bootstrap_from_births(store, data_dir)
        return store
    try:
        return ResearchMemoryStore.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return ResearchMemoryStore()


def save_research_memory(store: ResearchMemoryStore, data_dir: Optional[Path] = None) -> Path:
    path = memory_index_path(data_dir)
    _atomic_write(path, json.dumps(store.to_dict(), indent=2, default=str))
    return path


def append_memory_event(event: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    path = memory_events_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def _bootstrap_from_births(store: ResearchMemoryStore, data_dir: Optional[Path]) -> None:
    """Read existing birth index additively. Never mutates historical JSON."""
    try:
        from modules.edge_research.opr_bridge.production_observation_persistence import (
            load_observation_index,
            lookup_birth_record,
        )
    except Exception:
        return
    index = load_observation_index(data_dir)
    for obs_id in (index.get("observations") or {}):
        birth = lookup_birth_record(obs_id, data_dir=data_dir)
        if birth is None:
            continue
        record_family_from_birth(store, birth, persist=False, data_dir=data_dir)
    if store.families:
        save_research_memory(store, data_dir=data_dir)


def record_family_from_birth(
    store: ResearchMemoryStore,
    birth: Any,
    *,
    persist: bool = True,
    data_dir: Optional[Path] = None,
    selection_provenance: Optional[Dict[str, Any]] = None,
) -> PropositionFamilyMemory:
    question = getattr(birth, "research_question", None)
    feature = ""
    outcome = ""
    horizon = None
    population_kind = "all"
    claim_family = CLAIM_FAMILY_CROSS_SECTIONAL_TIER
    direction = None

    contract = getattr(birth, "forward_evaluation_contract", None)
    spec = {}
    if contract is not None:
        spec = getattr(contract, "claim_spec", None) or {}
        if not spec:
            spec = (getattr(contract, "evaluation_criteria", None) or {}).get("claim_spec") or {}
    if spec:
        feature = str(spec.get("feature") or "")
        outcome = str(spec.get("outcome_field") or "")
        horizon = spec.get("observation_horizon")
        population_kind = str(spec.get("population_kind") or "all")
        claim_family = str(spec.get("claim_family") or claim_family)
        direction = spec.get("direction_expectation")
        question = spec.get("scientific_question") or question

    if not feature and question:
        # Legacy births: recover a family from the question text without preferring an edge.
        feature = "unknown"
        outcome = "unknown"

    key = proposition_family_key(
        feature=feature or "unknown",
        outcome=outcome or "unknown",
        horizon=horizon,
        population_kind=population_kind,
        claim_family=claim_family,
    )
    family = store.lookup(key) or PropositionFamilyMemory(
        family_key=key,
        feature=feature,
        outcome=outcome,
        horizon=horizon,
        population_kind=population_kind,
        claim_family=claim_family,
        directional_claim=direction,
        scientific_question=question,
    )
    trade_date = getattr(getattr(birth, "cutoff", None), "trade_date", None)
    if trade_date and trade_date not in family.tested_episode_dates:
        family.tested_episode_dates.append(str(trade_date))
        family.episode_count = len(family.tested_episode_dates)
    obs_id = getattr(birth, "observation_id", None)
    if obs_id and obs_id not in family.observation_ids:
        family.observation_ids.append(obs_id)
        family.repetition_count = max(0, len(family.observation_ids) - 1)
    epistemic = getattr(birth, "final_epistemic_state", None)
    family.last_epistemic_state = epistemic
    if epistemic == "SUPPORTED":
        family.support_count += 1
    elif epistemic == "FALSIFIED":
        family.falsify_count += 1
    elif epistemic in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE", None):
        family.unresolved_count += 1
    family.surviving_nulls = list(getattr(birth, "surviving_nulls", ()) or family.surviving_nulls)
    family.contradiction_count += len(getattr(birth, "contradictions", ()) or ())
    ctx = getattr(getattr(birth, "cutoff", None), "market_context_hash", None)
    if ctx and ctx not in family.market_context_hashes:
        family.market_context_hashes.append(ctx)
    family.last_tested_date = str(trade_date) if trade_date else family.last_tested_date
    family.last_focal_date = family.last_tested_date
    if selection_provenance:
        family.last_selection_provenance = selection_provenance
    store.upsert(family)
    if persist:
        save_research_memory(store, data_dir=data_dir)
        append_memory_event(
            {
                "event": "BIRTH_RECORDED",
                "family_key": key,
                "observation_id": obs_id,
                "trade_date": trade_date,
                "epistemic": epistemic,
                "selection_provenance": selection_provenance,
                "created_at": utc_now_iso(),
            },
            data_dir=data_dir,
        )
    return family


def record_forward_adjudication(
    store: ResearchMemoryStore,
    *,
    family_key: str,
    observation_id: str,
    horizon: str,
    adjudication: str,
    data_dir: Optional[Path] = None,
) -> None:
    family = store.lookup(family_key)
    if family is None:
        return
    family.forward_validation_history.append(
        {
            "observation_id": observation_id,
            "horizon": horizon,
            "adjudication": adjudication,
            "recorded_at": utc_now_iso(),
        }
    )
    if adjudication == "CLAIM_SUPPORTING":
        family.support_count += 1
    elif adjudication == "CLAIM_DISCONFIRMING":
        family.falsify_count += 1
        family.contradiction_count += 1
    store.upsert(family)
    save_research_memory(store, data_dir=data_dir)
    append_memory_event(
        {
            "event": "FORWARD_ADJUDICATION",
            "family_key": family_key,
            "observation_id": observation_id,
            "horizon": horizon,
            "adjudication": adjudication,
            "created_at": utc_now_iso(),
        },
        data_dir=data_dir,
    )


def scientific_repeat_reasons(family: Optional[PropositionFamilyMemory], *, cutoff_date: str) -> Tuple[str, ...]:
    """Explicit reasons a previously tested family may be selected again."""
    if family is None:
        return ("NOVEL_FAMILY",)
    reasons: List[str] = []
    if cutoff_date and cutoff_date not in family.tested_episode_dates:
        reasons.append("NEW_INDEPENDENT_EPISODE")
    if family.has_unresolved_null():
        reasons.append("UNRESOLVED_NULL")
    if family.has_contradiction():
        reasons.append("CONTRADICTION")
    if family.needs_replication():
        reasons.append("ROBUSTNESS_REPLICATION")
    if family.forward_validation_pending():
        reasons.append("FORWARD_VALIDATION_PENDING")
    if not reasons:
        reasons.append("REDUNDANT_REPETITION")
    return tuple(reasons)
