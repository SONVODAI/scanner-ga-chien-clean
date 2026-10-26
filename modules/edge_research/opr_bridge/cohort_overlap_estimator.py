"""
Phase 3I.17b — Pre-result cohort overlap estimation (no outcome columns).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.cohort_binding_records import CohortOverlapProfile
from modules.edge_research.research_grammar import GRAMMAR_VERSION, parse_population_spec, apply_population_spec


@dataclass
class PriorCohortFingerprint:
    evidence_id: str
    row_keys: Set[Tuple[str, str]]  # (trade_date, symbol)
    dates: Set[str]
    symbols: Set[str]
    contexts: Set[str]
    population_semantics: str
    cohort_overlap_ratio: float


@dataclass
class PanelMetadataIndex:
    """Pre-result panel metadata — no outcome fields used."""

    row_keys: Set[Tuple[str, str]]
    dates: Set[str]
    symbols: Set[str]
    contexts: Set[str]
    context_by_row: Dict[Tuple[str, str], str]
    total_rows: int

    @classmethod
    def from_dataframe(cls, df, *, cutoff: str, context_field: str = "research_market_state") -> "PanelMetadataIndex":
        import pandas as pd

        work = df.copy()
        work["trade_date"] = work["trade_date"].astype(str)
        work = work[work["trade_date"] <= str(cutoff)]
        row_keys: Set[Tuple[str, str]] = set()
        dates: Set[str] = set()
        symbols: Set[str] = set()
        contexts: Set[str] = set()
        context_by_row: Dict[Tuple[str, str], str] = {}
        for _, row in work.iterrows():
            d = str(row["trade_date"])
            s = str(row.get("symbol", ""))
            key = (d, s)
            row_keys.add(key)
            dates.add(d)
            symbols.add(s)
            ctx = str(row.get(context_field, "UNKNOWN"))
            contexts.add(ctx)
            context_by_row[key] = ctx
        return cls(
            row_keys=row_keys,
            dates=dates,
            symbols=symbols,
            contexts=contexts,
            context_by_row=context_by_row,
            total_rows=len(row_keys),
        )

    @classmethod
    def from_abstract_fixture(cls, fixture: Dict[str, Any]) -> "PanelMetadataIndex":
        rows = fixture.get("rows", [])
        row_keys = {(r["trade_date"], r["symbol"]) for r in rows}
        dates = {r["trade_date"] for r in rows}
        symbols = {r["symbol"] for r in rows}
        contexts = {r.get("context_state", "CTX_A") for r in rows}
        context_by_row = {(r["trade_date"], r["symbol"]): r.get("context_state", "CTX_A") for r in rows}
        return cls(row_keys=row_keys, dates=dates, symbols=symbols, contexts=contexts, context_by_row=context_by_row, total_rows=len(row_keys))


def candidate_row_keys(
    panel: PanelMetadataIndex,
    population_spec: Dict[str, Any],
) -> Set[Tuple[str, str]]:
    """Apply population filter using metadata only."""
    keys = panel.row_keys
    spec = population_spec
    kind = spec.get("kind", "all")
    if kind == "all":
        return set(keys)
    if kind == "filter":
        field = spec.get("field")
        op = spec.get("operator")
        values = set(str(v) for v in spec.get("values", []))
        out: Set[Tuple[str, str]] = set()
        for key in keys:
            d, s = key
            if field == "trade_date":
                val = d
            elif field == "symbol":
                val = s
            elif field in ("research_market_state", "context_state"):
                val = panel.context_by_row.get(key, "UNKNOWN")
            else:
                val = panel.context_by_row.get(key, "UNKNOWN")
            if op == "in" and val in values:
                out.add(key)
            elif op == "not_in" and val not in values:
                out.add(key)
            elif op == "==" and val in values:
                out.add(key)
        return out
    return set(keys)


def estimate_overlap(
    candidate_keys: Set[Tuple[str, str]],
    panel: PanelMetadataIndex,
    priors: List[PriorCohortFingerprint],
    *,
    motivating_dates: Tuple[str, ...],
) -> CohortOverlapProfile:
    n = len(candidate_keys)
    if n == 0:
        return CohortOverlapProfile(
            candidate_row_count=0,
            row_overlap_fraction=1.0,
            date_overlap_fraction=1.0,
            symbol_overlap_fraction=1.0,
            context_overlap_fraction=1.0,
            relation_to_prior="unknown",
            overlaps_motivating_dates=bool(motivating_dates),
            overlaps_prior_falsification_cohort=False,
            max_prior_row_overlap=1.0,
        )

    cand_dates = {d for d, _ in candidate_keys}
    cand_symbols = {s for _, s in candidate_keys}
    cand_contexts = {panel.context_by_row.get(k, "UNKNOWN") for k in candidate_keys}

    max_row_overlap = 0.0
    best_relation = "partial_overlap"
    overlaps_falsify = False

    for prior in priors:
        if not prior.row_keys:
            continue
        inter = len(candidate_keys & prior.row_keys)
        union = len(candidate_keys | prior.row_keys) or 1
        jaccard = inter / union
        overlap_frac = inter / max(len(candidate_keys), 1)
        max_row_overlap = max(max_row_overlap, overlap_frac)
        if overlap_frac > 0.95:
            best_relation = "subset" if candidate_keys <= prior.row_keys else "partial_overlap"
        elif overlap_frac < 0.05:
            best_relation = "disjoint"
        if "holdout" in prior.population_semantics or prior.cohort_overlap_ratio < 0.5:
            overlaps_falsify = overlaps_falsify or overlap_frac > 0.8

    # Date/symbol/context overlap vs union panel
    date_overlap = len(cand_dates & panel.dates) / max(len(cand_dates), 1)
    sym_overlap = len(cand_symbols & panel.symbols) / max(len(cand_symbols), 1)
    ctx_overlap = len(cand_contexts & panel.contexts) / max(len(cand_contexts), 1) if cand_contexts else 0.0

    overlaps_motivating = bool(cand_dates & set(motivating_dates))

    return CohortOverlapProfile(
        candidate_row_count=n,
        row_overlap_fraction=max_row_overlap,
        date_overlap_fraction=date_overlap,
        symbol_overlap_fraction=sym_overlap,
        context_overlap_fraction=ctx_overlap,
        relation_to_prior=best_relation,
        overlaps_motivating_dates=overlaps_motivating,
        overlaps_prior_falsification_cohort=overlaps_falsify,
        max_prior_row_overlap=max_row_overlap,
    )


def derive_independence_from_overlap(
    overlap: CohortOverlapProfile,
    *,
    source_dimension: str,
) -> "ScientificEvidenceIndependenceProfile":
    from modules.edge_research.opr_bridge.cohort_binding_records import ScientificEvidenceIndependenceProfile

    row_o = overlap.row_overlap_fraction
    rationale: List[str] = [f"row_overlap_fraction={row_o:.3f}"]

    def level(high_thresh: float, low_thresh: float) -> str:
        if row_o <= high_thresh:
            return "HIGH"
        if row_o >= low_thresh:
            return "LOW"
        if row_o >= 0.85:
            return "NONE"
        return "MEDIUM"

    sample = level(0.35, 0.85)
    population = level(0.40, 0.80)
    episode = "LOW" if overlap.overlaps_motivating_dates else ("HIGH" if row_o < 0.3 else "MEDIUM")
    context = "HIGH" if overlap.context_overlap_fraction < 0.5 and row_o < 0.6 else ("LOW" if row_o > 0.8 else "MEDIUM")
    measurement = "HIGH"  # outcome not used in cohort selection
    semantic = "HIGH" if overlap.relation_to_prior != "subset" else "MEDIUM"
    rationale.append(f"context_overlap={overlap.context_overlap_fraction:.3f}")

    return ScientificEvidenceIndependenceProfile(
        sample_independence=sample,
        episode_independence=episode,
        population_independence=population,
        context_independence=context,
        measurement_independence=measurement,
        semantic_continuity=semantic,
        rationale=tuple(rationale),
    )
