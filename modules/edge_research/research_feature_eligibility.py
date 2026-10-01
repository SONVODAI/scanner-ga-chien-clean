"""
Feature eligibility and temporal availability for adaptive slicing (Phase 3F).

Determines which variables may serve as explanatory features at a given
research observation horizon — no special-case T3 logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Sequence, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from modules.edge_research.feature_registry import (
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
    is_prohibited_feature_column,
)
from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS

FEATURE_ELIGIBILITY_VERSION = "feature_eligibility_v1"

# Trading-session availability: earliest session when field is observable.
# 0 = T0, 3 = after T3 matures, etc.
FIELD_AVAILABILITY_HORIZON: Dict[str, int] = {
    "trade_date": 0,
    "symbol": 0,
    "research_market_state": 0,
    "research_market_transition": 0,
    "partition_group": 0,
}
for feat in STOCK_NUMERIC_LEVEL_FEATURES:
    FIELD_AVAILABILITY_HORIZON[feat] = 0
for feat in STOCK_CATEGORICAL_LEVEL_FEATURES:
    FIELD_AVAILABILITY_HORIZON[feat] = 0
for feat in STOCK_RANK_LEVEL_FEATURES:
    FIELD_AVAILABILITY_HORIZON[feat] = 0
for h in HORIZONS:
    sessions = int(h.replace("T", ""))
    FIELD_AVAILABILITY_HORIZON[RETURN_COLUMNS[h]] = sessions

IDENTIFIER_FIELDS: FrozenSet[str] = frozenset({"symbol"})
TIMESTAMP_FIELDS: FrozenSet[str] = frozenset({"trade_date"})
CONTEXT_FIELDS: FrozenSet[str] = frozenset(
    {"research_market_state", "research_market_transition", "partition_group"}
)
CATEGORICAL_FIELDS: FrozenSet[str] = frozenset(
    set(STOCK_CATEGORICAL_LEVEL_FEATURES) | CONTEXT_FIELDS
)
CONTINUOUS_FIELDS: FrozenSet[str] = frozenset(
    set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_RANK_LEVEL_FEATURES)
)
OUTCOME_FIELDS: FrozenSet[str] = frozenset(RETURN_COLUMNS.values())


class FeatureRole(str, Enum):
    CONTINUOUS = "continuous"
    ORDINAL = "ordinal"
    CATEGORICAL = "categorical"
    CONTEXT = "context"
    FORWARD_OUTCOME = "forward_outcome"
    IDENTIFIER = "identifier"
    TIMESTAMP = "timestamp"
    PROHIBITED = "prohibited"
    UNKNOWN = "unknown"


class EligibilityError(ValueError):
    """Raised when a feature violates temporal or leakage rules."""


@dataclass(frozen=True)
class FeatureEligibility:
    field_name: str
    role: str
    availability_horizon: int
    eligible_at_observation: bool
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "role": self.role,
            "availability_horizon": self.availability_horizon,
            "eligible_at_observation": self.eligible_at_observation,
            "reason": self.reason,
        }


def classify_feature_role(field_name: str) -> str:
    """Classify a column into a research feature role."""
    name = str(field_name).strip()
    if is_prohibited_feature_column(name) and name not in OUTCOME_FIELDS:
        return FeatureRole.PROHIBITED.value
    if name in IDENTIFIER_FIELDS:
        return FeatureRole.IDENTIFIER.value
    if name in TIMESTAMP_FIELDS:
        return FeatureRole.TIMESTAMP.value
    if name in OUTCOME_FIELDS:
        return FeatureRole.FORWARD_OUTCOME.value
    if name in CONTEXT_FIELDS:
        return FeatureRole.CONTEXT.value
    if name in CATEGORICAL_FIELDS:
        return FeatureRole.CATEGORICAL.value
    if name in CONTINUOUS_FIELDS:
        return FeatureRole.CONTINUOUS.value
    if name.endswith("_rank") or name.endswith("_score"):
        return FeatureRole.ORDINAL.value
    return FeatureRole.UNKNOWN.value


def field_availability_horizon(field_name: str) -> int:
    """Sessions after T0 when field becomes observable."""
    name = str(field_name).strip()
    if name in FIELD_AVAILABILITY_HORIZON:
        return FIELD_AVAILABILITY_HORIZON[name]
    if is_prohibited_feature_column(name):
        return 999
    return 0


def get_research_observation_horizon(research_scope: Dict[str, Any]) -> int:
    """
    Determine research observation point in trading sessions.

    Explicit `research_observation_horizon` in scope, or inferred from
    population conditioning on matured outcome fields.
    """
    if "research_observation_horizon" in research_scope:
        return int(research_scope["research_observation_horizon"])

    pop = research_scope.get("population_spec") or {}
    # Infer from population filters on outcome fields (e.g. t3_return > 0)
    max_horizon = 0
    if isinstance(pop, dict):
        max_horizon = _horizon_from_population_dict(pop, max_horizon)
    return max_horizon


def _horizon_from_population_dict(pop: Dict[str, Any], current: int) -> int:
    field = pop.get("field") or pop.get("filter_field")
    if field and field in OUTCOME_FIELDS:
        current = max(current, field_availability_horizon(str(field)))
    for child in pop.get("children") or []:
        if isinstance(child, dict):
            current = _horizon_from_population_dict(child, current)
    parent = pop.get("parent")
    if isinstance(parent, dict):
        current = _horizon_from_population_dict(parent, current)
    return current


def is_explanatory_role(role: str) -> bool:
    return role in (
        FeatureRole.CONTINUOUS.value,
        FeatureRole.ORDINAL.value,
        FeatureRole.CATEGORICAL.value,
        FeatureRole.CONTEXT.value,
        FeatureRole.FORWARD_OUTCOME.value,
    )


def _infer_role_from_panel(field_name: str, panel: Optional["pd.DataFrame"]) -> Optional[str]:
    """Infer continuous/categorical role for panel columns not in registry."""
    if panel is None or field_name not in panel.columns:
        return None
    import pandas as pd

    series = panel[field_name]
    if pd.api.types.is_numeric_dtype(series):
        return FeatureRole.CONTINUOUS.value
    return FeatureRole.CATEGORICAL.value


def assess_feature_eligibility(
    field_name: str,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    observation_horizon: Optional[int] = None,
    panel: Optional["pd.DataFrame"] = None,
) -> FeatureEligibility:
    """
    Assess whether a field may be used as an explanatory variable.

    Temporal rule: field availability_horizon must be <= observation_horizon.
    At T0, t3_return is future leakage. At observation_horizon=3, t3_return
    may be legitimate for predicting T5/T10.
    """
    name = str(field_name).strip()
    role = classify_feature_role(name)
    if role == FeatureRole.UNKNOWN.value:
        inferred = _infer_role_from_panel(name, panel)
        if inferred:
            role = inferred
    avail = field_availability_horizon(name)
    obs = observation_horizon
    if obs is None:
        obs = get_research_observation_horizon(research_scope or {})

    if role == FeatureRole.PROHIBITED.value:
        return FeatureEligibility(name, role, avail, False, "prohibited_column")
    if role in (FeatureRole.IDENTIFIER.value, FeatureRole.TIMESTAMP.value):
        return FeatureEligibility(name, role, avail, False, "not_explanatory")
    if role == FeatureRole.UNKNOWN.value:
        return FeatureEligibility(name, role, avail, False, "unknown_column")

    if avail > obs:
        return FeatureEligibility(
            name,
            role,
            avail,
            False,
            f"future_leakage:available_at_T{avail}_observation_at_T{obs}",
        )

    if not is_explanatory_role(role):
        return FeatureEligibility(name, role, avail, False, "not_explanatory")

    return FeatureEligibility(name, role, avail, True, "eligible")


def list_eligible_explanatory_features(
    panel_columns: Sequence[str],
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    observation_horizon: Optional[int] = None,
    roles: Optional[Set[str]] = None,
) -> Tuple[FeatureEligibility, ...]:
    """Return eligibility assessments for all panel columns."""
    allowed_roles = roles or {
        FeatureRole.CONTINUOUS.value,
        FeatureRole.ORDINAL.value,
        FeatureRole.CATEGORICAL.value,
        FeatureRole.CONTEXT.value,
    }
    results: list[FeatureEligibility] = []
    for col in sorted(set(panel_columns)):
        assessment = assess_feature_eligibility(
            col,
            research_scope=research_scope,
            observation_horizon=observation_horizon,
        )
        if assessment.eligible_at_observation and assessment.role in allowed_roles:
            results.append(assessment)
    return tuple(results)


def require_eligible_feature(
    field_name: str,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    observation_horizon: Optional[int] = None,
    allowed_roles: Optional[Set[str]] = None,
    panel: Optional["pd.DataFrame"] = None,
) -> FeatureEligibility:
    """Validate feature eligibility — raises EligibilityError on violation."""
    assessment = assess_feature_eligibility(
        field_name,
        research_scope=research_scope,
        observation_horizon=observation_horizon,
        panel=panel,
    )
    if not assessment.eligible_at_observation:
        raise EligibilityError(
            f"Feature {field_name!r} not eligible: {assessment.reason} "
            f"(role={assessment.role}, availability=T{assessment.availability_horizon})"
        )
    if allowed_roles and assessment.role not in allowed_roles:
        raise EligibilityError(
            f"Feature {field_name!r} role {assessment.role} not in allowed {allowed_roles}"
        )
    return assessment
