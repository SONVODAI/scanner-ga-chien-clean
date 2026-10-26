"""
Panel / registry preflight validation (Phase 3G.1).

Ensures generated actions reference fields present on the actual research panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

import pandas as pd

from modules.edge_research.feature_registry import (
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
)
from modules.edge_research.research_actions import ResearchActionCandidate
from modules.edge_research.research_feature_eligibility import (
    list_eligible_explanatory_features,
    require_eligible_feature,
)
from modules.edge_research.research_state import ExperimentSpec

PANEL_PREFLIGHT_VERSION = "panel_preflight_v1"

# Registry fields that may be absent from a built panel — exclude from generation.
_REGISTRY_OPTIONAL = frozenset({"health_group", "obv_status", "health_rank", "group_rank", "health_score"})


@dataclass(frozen=True)
class PanelPreflightReport:
    """Neutral audit of panel vs registry availability."""

    version: str = PANEL_PREFLIGHT_VERSION
    panel_columns: Tuple[str, ...] = field(default_factory=tuple)
    eligible_explanatory: Tuple[str, ...] = field(default_factory=tuple)
    registry_numeric: Tuple[str, ...] = field(default_factory=tuple)
    registry_categorical: Tuple[str, ...] = field(default_factory=tuple)
    registry_rank: Tuple[str, ...] = field(default_factory=tuple)
    registry_missing_from_panel: Tuple[str, ...] = field(default_factory=tuple)
    partition_columns_available: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "panel_columns": list(self.panel_columns),
            "eligible_explanatory": list(self.eligible_explanatory),
            "registry_numeric": list(self.registry_numeric),
            "registry_categorical": list(self.registry_categorical),
            "registry_rank": list(self.registry_rank),
            "registry_missing_from_panel": list(self.registry_missing_from_panel),
            "partition_columns_available": list(self.partition_columns_available),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PanelPreflightReport":
        return cls(
            version=str(payload.get("version", PANEL_PREFLIGHT_VERSION)),
            panel_columns=tuple(payload.get("panel_columns") or ()),
            eligible_explanatory=tuple(payload.get("eligible_explanatory") or ()),
            registry_numeric=tuple(payload.get("registry_numeric") or ()),
            registry_categorical=tuple(payload.get("registry_categorical") or ()),
            registry_rank=tuple(payload.get("registry_rank") or ()),
            registry_missing_from_panel=tuple(payload.get("registry_missing_from_panel") or ()),
            partition_columns_available=tuple(payload.get("partition_columns_available") or ()),
        )


def build_panel_preflight(panel: pd.DataFrame) -> PanelPreflightReport:
    """Build preflight report from canonical panel — no research interpretation."""
    cols = frozenset(panel.columns)
    eligible = tuple(
        e.field_name for e in list_eligible_explanatory_features(panel.columns, observation_horizon=0)
    )
    registry_all = set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_CATEGORICAL_LEVEL_FEATURES) | set(
        STOCK_RANK_LEVEL_FEATURES
    )
    missing = sorted(registry_all - cols)
    partition_cols = sorted(
        c
        for c in cols
        if c in eligible or c in STOCK_CATEGORICAL_LEVEL_FEATURES or c == "partition_group"
    )
    return PanelPreflightReport(
        panel_columns=tuple(sorted(cols)),
        eligible_explanatory=eligible,
        registry_numeric=tuple(STOCK_NUMERIC_LEVEL_FEATURES),
        registry_categorical=tuple(STOCK_CATEGORICAL_LEVEL_FEATURES),
        registry_rank=tuple(STOCK_RANK_LEVEL_FEATURES),
        registry_missing_from_panel=tuple(missing),
        partition_columns_available=tuple(partition_cols),
    )


def extract_required_fields(spec: Optional[ExperimentSpec]) -> Set[str]:
    """Fields referenced by an experiment spec inputs."""
    if spec is None:
        return set()
    inputs = spec.inputs or {}
    fields: Set[str] = set()
    for key in ("feature_column", "partition_column", "trajectory_feature", "primary_feature", "secondary_feature"):
        if key in inputs:
            fields.add(str(inputs[key]))
    return fields


def validate_action_against_panel(
    candidate: ResearchActionCandidate,
    panel_columns: Sequence[str],
) -> Tuple[bool, str]:
    """Return (valid, reason). Invalid actions must not crash the session."""
    if candidate.draft_spec is None:
        return True, "terminal_action"
    cols = frozenset(panel_columns)
    for field_name in extract_required_fields(candidate.draft_spec):
        if field_name not in cols:
            return False, f"field_absent_from_panel:{field_name}"
        try:
            require_eligible_feature(field_name, panel=pd.DataFrame(columns=list(cols)))
        except Exception as exc:
            return False, f"ineligible:{field_name}:{exc}"
    return True, "ok"


def filter_candidates_for_panel(
    candidates: Sequence[ResearchActionCandidate],
    panel_columns: Sequence[str],
) -> Tuple[ResearchActionCandidate, ...]:
    """Mark blocked invalid candidates — do not omit from audit record."""
    filtered: List[ResearchActionCandidate] = []
    for c in candidates:
        valid, reason = validate_action_against_panel(c, panel_columns)
        if valid or c.intent in ("STOP", "STOP_SESSION", "ABANDON"):
            filtered.append(c)
            continue
        filtered.append(
            ResearchActionCandidate(
                action_id=c.action_id,
                action_code=c.action_code,
                intent=c.intent,
                question_template_id=c.question_template_id,
                question_text=c.question_text,
                tool_name=c.tool_name,
                tool_version=c.tool_version,
                draft_spec=c.draft_spec,
                uncertainty_addressed=c.uncertainty_addressed,
                expected_information=c.expected_information,
                budget_cost=c.budget_cost,
                already_attempted=c.already_attempted,
                blocked=True,
                blocked_reason=reason,
                rationale_codes=c.rationale_codes,
                priority_hints=dict(c.priority_hints),
            )
        )
    return tuple(filtered)


def adaptive_partition_features(preflight: PanelPreflightReport) -> Tuple[str, ...]:
    """Continuous eligible features suitable for adaptive partition."""
    numeric = set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_RANK_LEVEL_FEATURES)
    return tuple(
        f
        for f in preflight.eligible_explanatory
        if f in numeric and f in preflight.panel_columns and f not in _REGISTRY_OPTIONAL
    )


def adaptive_features_from_columns(panel_columns: Sequence[str]) -> Tuple[str, ...]:
    """Panel-column-only helper when full panel DataFrame is unavailable."""
    eligible = tuple(
        e.field_name for e in list_eligible_explanatory_features(panel_columns, observation_horizon=0)
    )
    numeric = set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_RANK_LEVEL_FEATURES)
    cols = frozenset(panel_columns)
    return tuple(f for f in eligible if f in numeric and f in cols and f not in _REGISTRY_OPTIONAL)
