"""
BB-Prop-01 Zone D — Offline hidden evaluator.

Runs ONLY after PropositionRecords are frozen. Never imported by generator runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[3]
ZONE_C_REGISTRY = REPO / "benchmarks" / "bb_prop_01" / "zone_c_hidden" / "phenomena_registry.json"

_STOPWORDS = frozenset(
    {"a", "an", "the", "is", "are", "does", "do", "how", "what", "if", "or", "and", "to", "of", "in", "on", "for", "by", "with"}
)


class HiddenConvergenceClass(str, Enum):
    EXACT_REDISCOVERY = "EXACT_REDISCOVERY"
    PARTIAL_SEMANTIC_CONVERGENCE = "PARTIAL_SEMANTIC_CONVERGENCE"
    ADJACENT_INDEPENDENT = "ADJACENT_INDEPENDENT"
    UNRELATED = "UNRELATED"
    TEMPLATE_LEAKAGE = "TEMPLATE_LEAKAGE"


@dataclass
class PhenomenonMatch:
    phenomenon_id: str
    classification: HiddenConvergenceClass
    semantic_similarity: float
    structural_overlap: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phenomenon_id": self.phenomenon_id,
            "classification": self.classification.value,
            "semantic_similarity": self.semantic_similarity,
            "structural_overlap": self.structural_overlap,
        }


def _tokenize(text: str) -> set:
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def _semantic_similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _structural_overlap(prop: Dict[str, Any], phenom: Dict[str, Any]) -> float:
    sig = phenom.get("population_outcome_horizon_signature", {})
    score = 0.0
    prop_out = prop.get("outcome", {}).get("field", "")
    phen_out = sig.get("outcome", "")
    if phen_out in prop_out or prop_out in str(phen_out):
        score += 0.4
    rel = prop.get("explanatory_relation", {})
    feat = rel.get("feature_or_contrast", "")
    pop_feats = sig.get("population_features", [])
    if feat in pop_feats:
        score += 0.3
    if prop.get("observation_horizon") == sig.get("horizon", -1):
        score += 0.2
    if "dispersion" in prop.get("scientific_question", "").lower() and "dispersion" in phenom.get("embedding_text", ""):
        score += 0.1
    return min(1.0, score)


def _classify_match(sem: float, struct: float) -> HiddenConvergenceClass:
    if sem >= 0.75 and struct >= 0.6:
        return HiddenConvergenceClass.EXACT_REDISCOVERY
    if sem >= 0.45 and struct >= 0.4:
        return HiddenConvergenceClass.PARTIAL_SEMANTIC_CONVERGENCE
    if sem >= 0.25 or struct >= 0.3:
        return HiddenConvergenceClass.ADJACENT_INDEPENDENT
    return HiddenConvergenceClass.UNRELATED


def load_zone_c_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or ZONE_C_REGISTRY
    return json.loads(p.read_text(encoding="utf-8"))


def evaluate_proposition_against_zone_c(prop: Dict[str, Any], registry: Dict[str, Any]) -> List[PhenomenonMatch]:
    """Evaluate one frozen proposition against all hidden phenomena — evaluator only."""
    composite = " ".join(
        [
            prop.get("scientific_question", ""),
            prop.get("motivating_observation", ""),
            prop.get("surprise_or_uncertainty", ""),
        ]
    )
    matches: List[PhenomenonMatch] = []
    for phenom in registry.get("phenomena", []):
        embed = phenom.get("embedding_text", "") + " " + phenom.get("scientific_description", "")
        sem = _semantic_similarity(composite, embed)
        struct = _structural_overlap(prop, phenom)
        cls = _classify_match(sem, struct)
        matches.append(
            PhenomenonMatch(
                phenomenon_id=phenom["phenomenon_id"],
                classification=cls,
                semantic_similarity=round(sem, 4),
                structural_overlap=round(struct, 4),
            )
        )
    return matches


def aggregate_hidden_convergence(
    proposition_records: List[Dict[str, Any]],
    registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Produce abstract aggregate report per 3I.1 protection policy.
    Does NOT expose per-phenomenon mappings in generator-visible output.
    """
    reg = registry or load_zone_c_registry()
    if not proposition_records:
        return {
            "hidden_convergence_class": "NONE",
            "propositions_evaluated": 0,
            "exact_rediscovery_count": 0,
            "partial_convergence_count": 0,
            "adjacent_independent_count": 0,
            "unrelated_count": 0,
            "abstract_summary": "No propositions to evaluate against hidden phenomena",
        }

    exact = partial = adjacent = unrelated = 0
    for prop in proposition_records:
        matches = evaluate_proposition_against_zone_c(prop, reg)
        best = max(matches, key=lambda m: m.semantic_similarity + m.structural_overlap)
        if best.classification == HiddenConvergenceClass.EXACT_REDISCOVERY:
            exact += 1
        elif best.classification == HiddenConvergenceClass.PARTIAL_SEMANTIC_CONVERGENCE:
            partial += 1
        elif best.classification == HiddenConvergenceClass.ADJACENT_INDEPENDENT:
            adjacent += 1
        else:
            unrelated += 1

    n = len(proposition_records)
    if exact > 0:
        conv_class = "HIGH"
    elif partial > 0:
        conv_class = "MODERATE"
    elif adjacent > 0:
        conv_class = "PARTIAL"
    else:
        conv_class = "NONE"

    return {
        "hidden_convergence_class": conv_class,
        "propositions_evaluated": n,
        "exact_rediscovery_count": exact,
        "partial_convergence_count": partial,
        "adjacent_independent_count": adjacent,
        "unrelated_count": unrelated,
        "abstract_summary": (
            f"Evaluated {n} frozen proposition(s) against {reg.get('phenomenon_count', 0)} hidden phenomena. "
            f"Convergence class: {conv_class}."
        ),
    }


def evaluate_frozen_run(
    frozen_records_path: Path,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Offline evaluation entry point — Zone D only."""
    payload = json.loads(frozen_records_path.read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else payload.get("records", [])
    aggregate = aggregate_hidden_convergence(records)
    result = {"evaluator": "zone_d_v1", "aggregate": aggregate}
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
