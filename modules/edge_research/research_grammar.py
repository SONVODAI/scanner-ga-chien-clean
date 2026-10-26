"""
Controlled OutcomeSpec and PopulationSpec grammars for Edge Research (PATCH 3D/3E).

Domain-general research operations — no encoded discovery paths or privileged thresholds.
Serializable, deterministic, auditable, hashable; no arbitrary eval/code execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

import pandas as pd

from modules.edge_research.feature_registry import (
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
    is_prohibited_feature_column,
)
from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS

GRAMMAR_VERSION = "research_grammar_v1"

# Forward outcome fields — matured labels only; valid in OutcomeSpec, not PopulationSpec filters.
ALLOWED_OUTCOME_FIELDS: FrozenSet[str] = frozenset(RETURN_COLUMNS.values())

# T0-safe population filter fields (panel metadata + feature registry).
ALLOWED_POPULATION_CATEGORICAL: FrozenSet[str] = frozenset(
    {
        "symbol",
        "trade_date",
        "research_market_state",
        "research_market_transition",
        "health_group",
        "obv_status",
        "partition_group",
    }
    | set(STOCK_CATEGORICAL_LEVEL_FEATURES)
)

ALLOWED_POPULATION_NUMERIC: FrozenSet[str] = frozenset(
    set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_RANK_LEVEL_FEATURES)
)

ALLOWED_POPULATION_FIELDS: FrozenSet[str] = (
    ALLOWED_POPULATION_CATEGORICAL | ALLOWED_POPULATION_NUMERIC
)

COMPARE_OPERATORS: FrozenSet[str] = frozenset({">", "<", ">=", "<=", "==", "!="})


class GrammarValidationError(ValueError):
    """Raised when a spec violates grammar or leakage rules."""


class OutcomeKind(str, Enum):
    COMPARE = "compare"
    AND = "and"
    OR = "or"
    NOT = "not"
    PERSIST = "persist"
    CONTINUATION = "continuation"
    REVERSAL = "reversal"


class PopulationKind(str, Enum):
    ALL = "all"
    FILTER = "filter"
    AND = "and"
    REFINE = "refine"
    WIDEN = "widen"


@dataclass(frozen=True)
class SearchAccountingMetadata:
    """Hooks for future Phase 3G search accounting — metadata only."""

    branch_depth: int = 0
    predicate_count: int = 0
    outcome_complexity: int = 0
    population_complexity: int = 0
    parent_branch_hash: str = ""
    alternatives_considered: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_depth": self.branch_depth,
            "predicate_count": self.predicate_count,
            "outcome_complexity": self.outcome_complexity,
            "population_complexity": self.population_complexity,
            "parent_branch_hash": self.parent_branch_hash,
            "alternatives_considered": self.alternatives_considered,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SearchAccountingMetadata":
        return cls(
            branch_depth=int(payload.get("branch_depth", 0)),
            predicate_count=int(payload.get("predicate_count", 0)),
            outcome_complexity=int(payload.get("outcome_complexity", 0)),
            population_complexity=int(payload.get("population_complexity", 0)),
            parent_branch_hash=str(payload.get("parent_branch_hash", "")),
            alternatives_considered=int(payload.get("alternatives_considered", 0)),
        )


@dataclass(frozen=True)
class PopulationChangeRecord:
    """Audit trail for population refinement or widening."""

    parent_population_hash: str
    reason_code: str
    triggering_evidence: Dict[str, Any] = field(default_factory=dict)
    resulting_n: Optional[int] = None
    complexity_increment: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_population_hash": self.parent_population_hash,
            "reason_code": self.reason_code,
            "triggering_evidence": dict(self.triggering_evidence),
            "resulting_n": self.resulting_n,
            "complexity_increment": self.complexity_increment,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PopulationChangeRecord":
        return cls(
            parent_population_hash=str(payload.get("parent_population_hash", "")),
            reason_code=str(payload.get("reason_code", "")),
            triggering_evidence=dict(payload.get("triggering_evidence") or {}),
            resulting_n=payload.get("resulting_n"),
            complexity_increment=int(payload.get("complexity_increment", 0)),
        )


@dataclass(frozen=True)
class OutcomeSpec:
    """
    Controlled forward-outcome expression.

    Supports compare, boolean composition, persistence, continuation, reversal.
    """

    kind: str
    outcome_field: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[float] = None
    children: Tuple["OutcomeSpec", ...] = field(default_factory=tuple)
    horizons: Tuple[str, ...] = field(default_factory=tuple)
    threshold: Optional[float] = None
    early_horizon: Optional[str] = None
    late_horizon: Optional[str] = None
    grammar_version: str = GRAMMAR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "grammar_version": self.grammar_version,
            "kind": self.kind,
        }
        if self.outcome_field is not None:
            payload["field"] = self.outcome_field
        if self.operator is not None:
            payload["operator"] = self.operator
        if self.value is not None:
            payload["value"] = self.value
        if self.children:
            payload["children"] = [c.to_dict() for c in self.children]
        if self.horizons:
            payload["horizons"] = list(self.horizons)
        if self.threshold is not None:
            payload["threshold"] = self.threshold
        if self.early_horizon is not None:
            payload["early_horizon"] = self.early_horizon
        if self.late_horizon is not None:
            payload["late_horizon"] = self.late_horizon
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OutcomeSpec":
        children = tuple(
            cls.from_dict(c) for c in (payload.get("children") or [])
        )
        val = payload.get("value")
        thr = payload.get("threshold")
        return cls(
            kind=str(payload["kind"]),
            outcome_field=payload.get("field"),
            operator=payload.get("operator"),
            value=float(val) if val is not None else None,
            children=children,
            horizons=tuple(payload.get("horizons") or ()),
            threshold=float(thr) if thr is not None else None,
            early_horizon=payload.get("early_horizon"),
            late_horizon=payload.get("late_horizon"),
            grammar_version=str(payload.get("grammar_version", GRAMMAR_VERSION)),
        )

    def content_hash(self) -> str:
        return compute_spec_hash(self.to_dict())

    def complexity(self) -> int:
        return _outcome_complexity(self)

    @staticmethod
    def compare(field: str, operator: str, value: float) -> "OutcomeSpec":
        return OutcomeSpec(
            kind=OutcomeKind.COMPARE.value,
            outcome_field=field,
            operator=operator,
            value=float(value),
        )

    @staticmethod
    def and_(*children: "OutcomeSpec") -> "OutcomeSpec":
        return OutcomeSpec(kind=OutcomeKind.AND.value, children=tuple(children))

    @staticmethod
    def or_(*children: "OutcomeSpec") -> "OutcomeSpec":
        return OutcomeSpec(kind=OutcomeKind.OR.value, children=tuple(children))

    @staticmethod
    def not_(child: "OutcomeSpec") -> "OutcomeSpec":
        return OutcomeSpec(kind=OutcomeKind.NOT.value, children=(child,))

    @staticmethod
    def persist(field: str, operator: str, threshold: float, horizons: Sequence[str]) -> "OutcomeSpec":
        return OutcomeSpec(
            kind=OutcomeKind.PERSIST.value,
            outcome_field=field,
            operator=operator,
            threshold=float(threshold),
            horizons=tuple(horizons),
        )

    @staticmethod
    def continuation(
        early_horizon: str,
        late_horizon: str,
        operator: str,
        threshold: float,
    ) -> "OutcomeSpec":
        return OutcomeSpec(
            kind=OutcomeKind.CONTINUATION.value,
            early_horizon=early_horizon,
            late_horizon=late_horizon,
            operator=operator,
            threshold=float(threshold),
        )

    @staticmethod
    def reversal(
        early_horizon: str,
        late_horizon: str,
        early_threshold: float,
        late_threshold: float,
    ) -> "OutcomeSpec":
        return OutcomeSpec(
            kind=OutcomeKind.REVERSAL.value,
            early_horizon=early_horizon,
            late_horizon=late_horizon,
            threshold=float(early_threshold),
            value=float(late_threshold),
        )


@dataclass(frozen=True)
class PopulationSpec:
    """
    Controlled cohort definition with refinement/widening lineage.

    Supports ALL, filters, conjunction, parent refinement, widening.
    """

    kind: str
    filter_field: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[Union[float, str, bool]] = None
    values: Tuple[str, ...] = field(default_factory=tuple)
    children: Tuple["PopulationSpec", ...] = field(default_factory=tuple)
    parent: Optional["PopulationSpec"] = None
    reason_code: str = ""
    triggering_evidence: Dict[str, Any] = field(default_factory=dict)
    grammar_version: str = GRAMMAR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "grammar_version": self.grammar_version,
            "kind": self.kind,
        }
        if self.filter_field is not None:
            payload["field"] = self.filter_field
        if self.operator is not None:
            payload["operator"] = self.operator
        if self.value is not None:
            payload["value"] = self.value
        if self.values:
            payload["values"] = list(self.values)
        if self.children:
            payload["children"] = [c.to_dict() for c in self.children]
        if self.parent is not None:
            payload["parent"] = self.parent.to_dict()
        if self.reason_code:
            payload["reason_code"] = self.reason_code
        if self.triggering_evidence:
            payload["triggering_evidence"] = dict(self.triggering_evidence)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PopulationSpec":
        parent_raw = payload.get("parent")
        children = tuple(cls.from_dict(c) for c in (payload.get("children") or []))
        val = payload.get("value")
        return cls(
            kind=str(payload["kind"]),
            filter_field=payload.get("field"),
            operator=payload.get("operator"),
            value=val,
            values=tuple(payload.get("values") or ()),
            children=children,
            parent=cls.from_dict(parent_raw) if parent_raw else None,
            reason_code=str(payload.get("reason_code", "")),
            triggering_evidence=dict(payload.get("triggering_evidence") or {}),
            grammar_version=str(payload.get("grammar_version", GRAMMAR_VERSION)),
        )

    def content_hash(self) -> str:
        return compute_spec_hash(self.to_dict())

    def complexity(self) -> int:
        return _population_complexity(self)

    @staticmethod
    def all_() -> "PopulationSpec":
        return PopulationSpec(kind=PopulationKind.ALL.value)

    @staticmethod
    def filter_numeric(field: str, operator: str, value: float) -> "PopulationSpec":
        return PopulationSpec(
            kind=PopulationKind.FILTER.value,
            filter_field=field,
            operator=operator,
            value=float(value),
        )

    @staticmethod
    def filter_categorical(field: str, values: Sequence[str]) -> "PopulationSpec":
        return PopulationSpec(
            kind=PopulationKind.FILTER.value,
            filter_field=field,
            operator="in",
            values=tuple(str(v) for v in values),
        )

    @staticmethod
    def and_(*children: "PopulationSpec") -> "PopulationSpec":
        return PopulationSpec(kind=PopulationKind.AND.value, children=tuple(children))

    @staticmethod
    def refine(
        parent: "PopulationSpec",
        additional: "PopulationSpec",
        *,
        reason_code: str,
        triggering_evidence: Optional[Dict[str, Any]] = None,
    ) -> "PopulationSpec":
        return PopulationSpec(
            kind=PopulationKind.REFINE.value,
            parent=parent,
            children=(additional,),
            reason_code=reason_code,
            triggering_evidence=dict(triggering_evidence or {}),
        )

    @staticmethod
    def widen(
        parent: "PopulationSpec",
        *,
        reason_code: str,
        triggering_evidence: Optional[Dict[str, Any]] = None,
    ) -> "PopulationSpec":
        return PopulationSpec(
            kind=PopulationKind.WIDEN.value,
            parent=parent,
            reason_code=reason_code,
            triggering_evidence=dict(triggering_evidence or {}),
        )


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_for_hash(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_hash(v) for v in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


def compute_spec_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(
        _normalize_for_hash(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def outcome_specs_equal(a: OutcomeSpec, b: OutcomeSpec) -> bool:
    return a.content_hash() == b.content_hash()


def population_specs_equal(a: PopulationSpec, b: PopulationSpec) -> bool:
    return a.content_hash() == b.content_hash()


def _outcome_complexity(spec: OutcomeSpec) -> int:
    if spec.kind == OutcomeKind.COMPARE.value:
        return 1
    if spec.kind in (OutcomeKind.AND.value, OutcomeKind.OR.value):
        return sum(_outcome_complexity(c) for c in spec.children)
    if spec.kind == OutcomeKind.NOT.value:
        return 1 + sum(_outcome_complexity(c) for c in spec.children)
    if spec.kind in (
        OutcomeKind.PERSIST.value,
        OutcomeKind.CONTINUATION.value,
        OutcomeKind.REVERSAL.value,
    ):
        return 2 + len(spec.horizons)
    return 1


def _population_complexity(spec: PopulationSpec) -> int:
    if spec.kind == PopulationKind.ALL.value:
        return 0
    if spec.kind == PopulationKind.FILTER.value:
        return 1
    if spec.kind == PopulationKind.AND.value:
        return sum(_population_complexity(c) for c in spec.children)
    if spec.kind == PopulationKind.REFINE.value:
        base = _population_complexity(spec.parent) if spec.parent else 0
        extra = sum(_population_complexity(c) for c in spec.children)
        return base + extra + 1
    if spec.kind == PopulationKind.WIDEN.value:
        base = _population_complexity(spec.parent) if spec.parent else 0
        return max(0, base - 1) + 1
    return 1


def _validate_horizon(h: str) -> None:
    if h not in HORIZONS:
        raise GrammarValidationError(f"Unknown horizon: {h!r}. Allowed: {HORIZONS}")


def _validate_outcome_field(field: str) -> None:
    if field not in ALLOWED_OUTCOME_FIELDS:
        raise GrammarValidationError(
            f"Outcome field {field!r} not allowed. Allowed: {sorted(ALLOWED_OUTCOME_FIELDS)}"
        )
    if is_prohibited_feature_column(field) and field not in ALLOWED_OUTCOME_FIELDS:
        raise GrammarValidationError(f"Outcome field {field!r} is prohibited (future leakage risk)")


def _validate_population_field(field: str) -> None:
    if field not in ALLOWED_POPULATION_FIELDS:
        raise GrammarValidationError(
            f"Population field {field!r} not allowed. Allowed T0-safe: {sorted(ALLOWED_POPULATION_FIELDS)}"
        )
    if field in ALLOWED_OUTCOME_FIELDS:
        raise GrammarValidationError(
            f"Population field {field!r} is a forward outcome field — use OutcomeSpec instead"
        )
    if is_prohibited_feature_column(field):
        raise GrammarValidationError(f"Population field {field!r} is prohibited (future leakage)")


def _validate_operator(op: str) -> None:
    if op not in COMPARE_OPERATORS and op != "in":
        raise GrammarValidationError(f"Operator {op!r} not allowed")


def validate_outcome_spec(spec: OutcomeSpec) -> None:
    """Validate OutcomeSpec against allowed columns/operators — raises on violation."""
    if spec.kind == OutcomeKind.COMPARE.value:
        if spec.outcome_field is None or spec.operator is None or spec.value is None:
            raise GrammarValidationError("COMPARE requires field, operator, value")
        _validate_outcome_field(spec.outcome_field)
        _validate_operator(spec.operator)
        return

    if spec.kind in (OutcomeKind.AND.value, OutcomeKind.OR.value):
        if len(spec.children) < 2:
            raise GrammarValidationError(f"{spec.kind.upper()} requires at least 2 children")
        for child in spec.children:
            validate_outcome_spec(child)
        return

    if spec.kind == OutcomeKind.NOT.value:
        if len(spec.children) != 1:
            raise GrammarValidationError("NOT requires exactly 1 child")
        validate_outcome_spec(spec.children[0])
        return

    if spec.kind == OutcomeKind.PERSIST.value:
        if spec.outcome_field is None or spec.operator is None or spec.threshold is None:
            raise GrammarValidationError("PERSIST requires field, operator, threshold")
        if len(spec.horizons) < 2:
            raise GrammarValidationError("PERSIST requires at least 2 horizons")
        _validate_outcome_field(spec.outcome_field)
        _validate_operator(spec.operator)
        for h in spec.horizons:
            _validate_horizon(h)
        return

    if spec.kind == OutcomeKind.CONTINUATION.value:
        if not spec.early_horizon or not spec.late_horizon or spec.threshold is None:
            raise GrammarValidationError("CONTINUATION requires early_horizon, late_horizon, threshold")
        _validate_horizon(spec.early_horizon)
        _validate_horizon(spec.late_horizon)
        if spec.operator:
            _validate_operator(spec.operator)
        return

    if spec.kind == OutcomeKind.REVERSAL.value:
        if not spec.early_horizon or not spec.late_horizon:
            raise GrammarValidationError("REVERSAL requires early_horizon and late_horizon")
        _validate_horizon(spec.early_horizon)
        _validate_horizon(spec.late_horizon)
        return

    raise GrammarValidationError(f"Unknown OutcomeSpec kind: {spec.kind!r}")


def validate_population_spec(spec: PopulationSpec) -> None:
    """Validate PopulationSpec — rejects forward/outcome fields in filters."""
    if spec.kind == PopulationKind.ALL.value:
        return

    if spec.kind == PopulationKind.FILTER.value:
        if spec.filter_field is None:
            raise GrammarValidationError("FILTER requires field")
        _validate_population_field(spec.filter_field)
        if spec.operator == "in":
            if not spec.values:
                raise GrammarValidationError("Categorical FILTER requires values")
        else:
            _validate_operator(spec.operator or "")
            if spec.value is None:
                raise GrammarValidationError("Numeric FILTER requires value")
        return

    if spec.kind == PopulationKind.AND.value:
        if len(spec.children) < 2:
            raise GrammarValidationError("AND requires at least 2 children")
        for child in spec.children:
            validate_population_spec(child)
        return

    if spec.kind == PopulationKind.REFINE.value:
        if spec.parent is None:
            raise GrammarValidationError("REFINE requires parent population")
        validate_population_spec(spec.parent)
        for child in spec.children:
            validate_population_spec(child)
        return

    if spec.kind == PopulationKind.WIDEN.value:
        if spec.parent is None:
            raise GrammarValidationError("WIDEN requires parent population")
        validate_population_spec(spec.parent)
        return

    raise GrammarValidationError(f"Unknown PopulationSpec kind: {spec.kind!r}")


def _apply_compare(series: pd.Series, operator: str, value: float) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if operator == ">":
        return s > value
    if operator == "<":
        return s < value
    if operator == ">=":
        return s >= value
    if operator == "<=":
        return s <= value
    if operator == "==":
        return s == value
    if operator == "!=":
        return s != value
    raise GrammarValidationError(f"Unknown operator: {operator!r}")


def evaluate_outcome_spec(spec: OutcomeSpec, row: pd.Series) -> bool:
    """Evaluate OutcomeSpec against one panel row (deterministic, no eval)."""
    validate_outcome_spec(spec)

    if spec.kind == OutcomeKind.COMPARE.value:
        assert spec.outcome_field and spec.operator is not None and spec.value is not None
        result = _apply_compare(row[spec.outcome_field], spec.operator, spec.value)
        return bool(result) if pd.notna(result) else False

    if spec.kind == OutcomeKind.AND.value:
        return all(evaluate_outcome_spec(c, row) for c in spec.children)

    if spec.kind == OutcomeKind.OR.value:
        return any(evaluate_outcome_spec(c, row) for c in spec.children)

    if spec.kind == OutcomeKind.NOT.value:
        return not evaluate_outcome_spec(spec.children[0], row)

    if spec.kind == OutcomeKind.PERSIST.value:
        assert spec.outcome_field and spec.operator and spec.threshold is not None
        for h in spec.horizons:
            col = RETURN_COLUMNS[h]
            if not bool(_apply_compare(row[col], spec.operator, spec.threshold)):
                return False
        return True

    if spec.kind == OutcomeKind.CONTINUATION.value:
        assert spec.early_horizon and spec.late_horizon and spec.threshold is not None
        op = spec.operator or ">"
        early_col = RETURN_COLUMNS[spec.early_horizon]
        late_col = RETURN_COLUMNS[spec.late_horizon]
        return bool(_apply_compare(row[early_col], op, spec.threshold)) and bool(
            _apply_compare(row[late_col], op, spec.threshold)
        )

    if spec.kind == OutcomeKind.REVERSAL.value:
        assert spec.early_horizon and spec.late_horizon and spec.threshold is not None and spec.value is not None
        early_col = RETURN_COLUMNS[spec.early_horizon]
        late_col = RETURN_COLUMNS[spec.late_horizon]
        return bool(_apply_compare(row[early_col], ">", spec.threshold)) and bool(
            _apply_compare(row[late_col], "<", spec.value)
        )

    return False


def _resolve_population_base(spec: PopulationSpec) -> PopulationSpec:
    """Flatten REFINE/WIDEN to effective filter tree."""
    if spec.kind == PopulationKind.REFINE.value and spec.parent is not None:
        parent_resolved = _resolve_population_base(spec.parent)
        if spec.children:
            return PopulationSpec.and_(parent_resolved, *spec.children)
        return parent_resolved
    if spec.kind == PopulationKind.WIDEN.value and spec.parent is not None:
        return _resolve_population_base(spec.parent)
    return spec


def apply_population_spec(
    panel: pd.DataFrame,
    spec: PopulationSpec,
) -> Tuple[pd.DataFrame, int]:
    """
    Apply PopulationSpec to panel — returns filtered copy and N.

    Does NOT apply cutoff; caller must pre-filter via apply_research_cutoff.
    """
    validate_population_spec(spec)
    if panel.empty:
        return panel.copy(), 0

    resolved = _resolve_population_base(spec)
    if resolved.kind == PopulationKind.ALL.value:
        return panel.copy(), int(len(panel))

    mask = _population_mask(resolved, panel)
    filtered = panel[mask].copy()
    return filtered, int(len(filtered))


def _population_mask(spec: PopulationSpec, panel: pd.DataFrame) -> pd.Series:
    if spec.kind == PopulationKind.ALL.value:
        return pd.Series(True, index=panel.index)

    if spec.kind == PopulationKind.FILTER.value:
        assert spec.filter_field is not None
        if spec.filter_field not in panel.columns:
            return pd.Series(False, index=panel.index)
        if spec.operator == "in":
            return panel[spec.filter_field].astype(str).isin(set(spec.values))
        assert spec.operator and spec.value is not None
        return _apply_compare(panel[spec.filter_field], spec.operator, float(spec.value))

    if spec.kind == PopulationKind.AND.value:
        combined = pd.Series(True, index=panel.index)
        for child in spec.children:
            combined &= _population_mask(child, panel)
        return combined

    raise GrammarValidationError(f"Cannot apply unresolved population kind: {spec.kind!r}")


def population_spec_to_research_scope(spec: PopulationSpec) -> Dict[str, Any]:
    """
    Convert PopulationSpec to research_scope dict for resolve_cohort compatibility.

    Embeds serialized spec for audit; extracts market filters and condition_clauses.
    """
    validate_population_spec(spec)
    scope: Dict[str, Any] = {
        "population_spec": spec.to_dict(),
        "population_spec_hash": spec.content_hash(),
    }
    resolved = _resolve_population_base(spec)
    _extract_scope_filters(resolved, scope)
    return scope


def _extract_scope_filters(spec: PopulationSpec, scope: Dict[str, Any]) -> None:
    if spec.kind == PopulationKind.ALL.value:
        return
    if spec.kind == PopulationKind.FILTER.value:
        assert spec.filter_field
        if spec.filter_field == "research_market_transition":
            scope["market_transition"] = str(spec.values[0] if spec.values else spec.value)
        elif spec.filter_field == "research_market_state":
            scope["market_state"] = str(spec.values[0] if spec.values else spec.value)
        elif spec.filter_field in ALLOWED_POPULATION_NUMERIC and spec.operator and spec.value is not None:
            clauses = list(scope.get("condition_clauses") or [])
            op = spec.operator
            lo, hi = None, None
            if op in (">", ">="):
                lo = float(spec.value)
            elif op in ("<", "<="):
                hi = float(spec.value)
            elif op == "==":
                lo = hi = float(spec.value)
            clauses.append(
                {
                    "feature": spec.filter_field,
                    "operator": "between" if lo is not None and hi is not None else "gt" if lo else "lt",
                    "threshold_lo": lo,
                    "threshold_hi": hi,
                    "bucket_id": f"{spec.filter_field}_grammar",
                }
            )
            scope["condition_clauses"] = clauses
        return
    if spec.kind == PopulationKind.AND.value:
        for child in spec.children:
            _extract_scope_filters(child, scope)


def build_search_accounting(
    *,
    population_spec: PopulationSpec,
    outcome_spec: OutcomeSpec,
    research_depth: int,
    parent_branch_hash: str = "",
    alternatives_considered: int = 0,
) -> SearchAccountingMetadata:
    pop_complexity = population_spec.complexity()
    out_complexity = outcome_spec.complexity()
    return SearchAccountingMetadata(
        branch_depth=research_depth,
        predicate_count=pop_complexity + out_complexity,
        outcome_complexity=out_complexity,
        population_complexity=pop_complexity,
        parent_branch_hash=parent_branch_hash,
        alternatives_considered=alternatives_considered,
    )


def propose_outcome_reframes(current: OutcomeSpec) -> Tuple[OutcomeSpec, ...]:
    """
    Generate generic alternative outcome specs — planner chooses among them.

    No privileged thresholds or field-specific discovery paths.
    """
    proposals: List[OutcomeSpec] = []
    validate_outcome_spec(current)

    if current.kind == OutcomeKind.COMPARE.value and current.outcome_field and current.value is not None:
        # Alternative horizon for same comparison shape.
        for col in ALLOWED_OUTCOME_FIELDS:
            if col != current.outcome_field:
                alt = OutcomeSpec.compare(col, current.operator or ">", current.value)
                try:
                    validate_outcome_spec(alt)
                    proposals.append(alt)
                except GrammarValidationError:
                    pass
        # Persistence across adjacent horizons when single-horizon compare.
        horizon_for_field = {RETURN_COLUMNS[h]: h for h in HORIZONS}
        if current.outcome_field in horizon_for_field:
            h = horizon_for_field[current.outcome_field]
            idx = HORIZONS.index(h)
            if idx + 1 < len(HORIZONS):
                persist = OutcomeSpec.persist(
                    current.outcome_field,
                    current.operator or ">",
                    current.value,
                    (h, HORIZONS[idx + 1]),
                )
                try:
                    validate_outcome_spec(persist)
                    proposals.append(persist)
                except GrammarValidationError:
                    pass

    if current.kind == OutcomeKind.COMPARE.value:
        # Continuation across T3->T5 or T5->T10 generically.
        for early, late in [("T3", "T5"), ("T5", "T10")]:
            cont = OutcomeSpec.continuation(early, late, ">", 0.0)
            try:
                validate_outcome_spec(cont)
                if not outcome_specs_equal(cont, current):
                    proposals.append(cont)
            except GrammarValidationError:
                pass

    # Deduplicate
    seen: set[str] = {current.content_hash()}
    unique: List[OutcomeSpec] = []
    for p in proposals:
        h = p.content_hash()
        if h not in seen:
            seen.add(h)
            unique.append(p)
    return tuple(unique)


def propose_population_refinements(
    current: PopulationSpec,
    *,
    reason_code: str,
    triggering_evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[PopulationSpec, ...]:
    """Generic population refinements — numeric/categorical filters on T0-safe fields."""
    proposals: List[PopulationSpec] = []
    evidence = dict(triggering_evidence or {})

    # Generic numeric refinement templates on available T0 features.
    for feat in ("rs10", "rsi14", "health_rank"):
        filt = PopulationSpec.filter_numeric(feat, ">", 0.0)
        refined = PopulationSpec.refine(
            current,
            filt,
            reason_code=reason_code,
            triggering_evidence=evidence,
        )
        try:
            validate_population_spec(refined)
            if not population_specs_equal(refined, current):
                proposals.append(refined)
        except GrammarValidationError:
            pass

    seen: set[str] = {current.content_hash()}
    unique: List[PopulationSpec] = []
    for p in proposals:
        h = p.content_hash()
        if h not in seen:
            seen.add(h)
            unique.append(p)
    return tuple(unique)


def propose_population_widenings(
    current: PopulationSpec,
    *,
    reason_code: str,
    triggering_evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[PopulationSpec, ...]:
    """Propose widening when current population is refined."""
    if current.kind not in (PopulationKind.REFINE.value, PopulationKind.AND.value):
        if current.parent is None and current.kind == PopulationKind.FILTER.value:
            widened = PopulationSpec.all_()
            return (widened,)
        return ()

    parent = current.parent if current.parent else PopulationSpec.all_()
    widened = PopulationSpec.widen(
        parent,
        reason_code=reason_code,
        triggering_evidence=dict(triggering_evidence or {}),
    )
    try:
        validate_population_spec(widened)
        if not population_specs_equal(widened, current):
            return (widened,)
    except GrammarValidationError:
        pass
    return ()


def parse_outcome_spec(payload: Dict[str, Any]) -> OutcomeSpec:
    spec = OutcomeSpec.from_dict(payload)
    validate_outcome_spec(spec)
    return spec


def parse_population_spec(payload: Dict[str, Any]) -> PopulationSpec:
    spec = PopulationSpec.from_dict(payload)
    validate_population_spec(spec)
    return spec
