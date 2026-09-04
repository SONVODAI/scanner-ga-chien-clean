"""
Phase 3I.16 — Action generation context (authoritative multi-evidence state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import (
    EvidenceLedgerEntry,
    EvidenceSynthesisRecord,
    ResearchPriorityDecision,
)


@dataclass
class ExecutabilityContext:
    """Tool/interpreter capabilities — may change without altering scientific core."""

    available_tools: Set[str] = field(default_factory=set)
    has_regime_column: bool = False
    has_symbol_level: bool = False
    has_date_decomposition: bool = False
    panel_columns: Set[str] = field(default_factory=set)
    min_sample: int = 50
    data_cutoff: str = "2019-06-01"
    abstract_mode: bool = True

    @classmethod
    def abstract_default(cls, *, tools: Optional[Set[str]] = None) -> "ExecutabilityContext":
        return cls(
            available_tools=tools or {"tier_compare", "flux_decomposition", "regime_contrast"},
            has_regime_column=True,
            has_symbol_level=True,
            has_date_decomposition=True,
            panel_columns={"trade_date", "flux_index", "delta_yield", "research_market_state", "symbol"},
            abstract_mode=True,
        )

    @classmethod
    def real_partition_default(
        cls,
        *,
        data_cutoff: str,
        panel_columns: Optional[Set[str]] = None,
    ) -> "ExecutabilityContext":
        cols = set(panel_columns) if panel_columns else {
            "trade_date",
            "rs_spread",
            "t5_return",
            "research_market_state",
            "symbol",
        }
        return cls(
            available_tools={"partition_group_compare", "date_decomposition"},
            has_regime_column=True,
            has_symbol_level=True,
            has_date_decomposition=True,
            panel_columns=cols,
            min_sample=58,
            data_cutoff=data_cutoff,
            abstract_mode=False,
        )

    @classmethod
    def real_partition_for_panel(
        cls,
        *,
        data_cutoff: str,
        panel: Any,
    ) -> "ExecutabilityContext":
        """Bind real-partition executability to the columns actually on this panel.

        Does not encode a preferred feature. Callers without a panel keep
        real_partition_default()'s historical fallback set.
        """
        columns = None
        if panel is not None and getattr(panel, "columns", None) is not None:
            columns = set(map(str, panel.columns))
        return cls.real_partition_default(data_cutoff=data_cutoff, panel_columns=columns)


@dataclass
class ActionGenerationContext:
    """Bundles authoritative inputs for ScientificActionGenerator."""

    proposition_spec: Dict[str, Any]
    proposition_record: Dict[str, Any]
    synthesis: EvidenceSynthesisRecord
    priority: ResearchPriorityDecision
    ledger_entries: List[EvidenceLedgerEntry]
    executability: ExecutabilityContext
    evidence_specs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def proposition_id(self) -> str:
        return self.proposition_spec["proposition_id"]

    @property
    def proposition_hash(self) -> str:
        return self.proposition_spec.get("proposition_hash", self.synthesis.proposition_hash)

    @property
    def proposition_type(self) -> str:
        return self.proposition_spec.get("proposition_type", "partition_contrast")

    @property
    def priority_action(self) -> str:
        return self.priority.chosen_priority_action

    @property
    def covered_axes(self) -> Set[str]:
        return set(self.synthesis.uncertainty_covered)

    @property
    def unresolved_axes(self) -> Tuple[str, ...]:
        return self.synthesis.uncertainty_unresolved

    @property
    def redundant_axes(self) -> Set[str]:
        return set(self.synthesis.saturation_assessment.get("redundant_test_axes", []))

    @property
    def major_unresolved(self) -> Set[str]:
        return set(self.synthesis.saturation_assessment.get("major_uncertainty_dimensions_remaining", []))

    @property
    def has_contradiction(self) -> bool:
        return bool(self.synthesis.contradiction_structure)

    @property
    def motivating_dates(self) -> Tuple[str, ...]:
        dates: Set[str] = set()
        prov = self.proposition_record.get("observation_provenance", {})
        anchor = prov.get("evidence_anchor", {})
        if anchor.get("focal_date"):
            dates.add(str(anchor["focal_date"]))
        for art in prov.get("empirical_artifacts", []):
            if art.get("date"):
                dates.add(str(art["date"]))
        # Abstract fixtures may store motivating_dates directly
        for d in self.proposition_record.get("motivating_dates", []):
            dates.add(str(d))
        return tuple(sorted(dates))

    @property
    def null_competing_explanation(self) -> str:
        return str(
            self.proposition_record.get("null_competing_explanation")
            or self.proposition_record.get("disconfirming_observation_spec", {}).get("alternative_interpretation", "")
        )

    @property
    def max_cohort_overlap(self) -> float:
        if not self.ledger_entries:
            return 0.0
        return max(e.cohort_overlap_ratio for e in self.ledger_entries)

    @property
    def executed_core_hashes(self) -> Set[str]:
        """Cores implied by prior ledger — used for redundancy detection."""
        from modules.edge_research.opr_bridge.scientific_action_core import infer_executed_core_hashes

        return infer_executed_core_hashes(self)

    def axis_is_saturated(self, axis: str) -> bool:
        return axis in self.redundant_axes

    def low_population_independence(self) -> bool:
        for e in self.ledger_entries:
            if e.cohort_overlap_ratio >= 0.9:
                return True
        return False
