"""
V2 condition clauses: numeric, categorical, and boolean.

Does not inherit production ConditionClause.matches numeric-only limitation.
Missing values never match (exclude-row policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.multifamily_discovery_v2.registry import FeatureSpec, V2_REGISTRY


@dataclass(frozen=True)
class V2Clause:
    feature: str
    family: str
    datatype: str
    operator: str
    bucket_id: str
    threshold_lo: Optional[float] = None
    threshold_hi: Optional[float] = None
    category: Optional[str] = None
    boolean_value: Optional[bool] = None

    def to_text(self) -> str:
        label = self.feature.upper()
        if self.datatype == "categorical":
            return f"{label}=={self.category}"
        if self.datatype == "boolean":
            return f"{label}=={self.boolean_value}"
        if self.operator == "<=":
            return f"{label}<={self.threshold_hi:g}"
        if self.operator == ">":
            return f"{label}>{self.threshold_lo:g}"
        if self.threshold_lo is None:
            return f"{label}<={self.threshold_hi:g}"
        if self.threshold_hi is None:
            return f"{label}>{self.threshold_lo:g}"
        return f"{label}>{self.threshold_lo:g} & {label}<={self.threshold_hi:g}"

    def mask(self, panel: pd.DataFrame) -> pd.Series:
        if self.feature not in panel.columns:
            return pd.Series(False, index=panel.index)
        series = panel[self.feature]
        if self.datatype == "categorical":
            text = series.astype("string").fillna("")
            return text == str(self.category)
        if self.datatype == "boolean":
            coerced = series.map(_as_bool)
            return coerced == self.boolean_value
        values = pd.to_numeric(series, errors="coerce")
        valid = values.notna()
        v = values
        if self.operator == "<=":
            return valid & (v <= float(self.threshold_hi))
        if self.operator == ">":
            return valid & (v > float(self.threshold_lo))
        lo = float("-inf") if self.threshold_lo is None else float(self.threshold_lo)
        hi = float("inf") if self.threshold_hi is None else float(self.threshold_hi)
        return valid & (v > lo) & (v <= hi)


def _as_bool(value: object) -> Optional[bool]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    return None


def clauses_for_feature(name: str, registry: Optional[dict] = None) -> List[V2Clause]:
    spec: FeatureSpec = (registry or V2_REGISTRY)[name]
    out: List[V2Clause] = []
    if spec.proposition_kind == "numeric_bucket":
        for bucket in spec.numeric_buckets:
            out.append(
                V2Clause(
                    feature=spec.name,
                    family=spec.family,
                    datatype="numeric",
                    operator=bucket.operator,
                    bucket_id=bucket.bucket_id,
                    threshold_lo=bucket.threshold_lo,
                    threshold_hi=bucket.threshold_hi,
                )
            )
    elif spec.proposition_kind == "categorical_eq":
        for cat in spec.categorical_values:
            out.append(
                V2Clause(
                    feature=spec.name,
                    family=spec.family,
                    datatype="categorical",
                    operator="==",
                    bucket_id=f"{spec.name}_{cat}",
                    category=cat,
                )
            )
    elif spec.proposition_kind == "boolean_eq":
        for flag in spec.boolean_values:
            out.append(
                V2Clause(
                    feature=spec.name,
                    family=spec.family,
                    datatype="boolean",
                    operator="==",
                    bucket_id=f"{spec.name}_{flag}",
                    boolean_value=flag,
                )
            )
    return out


def canonical_condition_key(clauses: Sequence[V2Clause]) -> str:
    ordered = sorted(clauses, key=lambda c: (c.feature, c.bucket_id))
    return "|".join(f"{c.feature}:{c.bucket_id}" for c in ordered)


def canonical_condition_text(clauses: Sequence[V2Clause]) -> str:
    ordered = sorted(clauses, key=lambda c: c.feature)
    return " & ".join(c.to_text() for c in ordered)


def apply_clauses(panel: pd.DataFrame, clauses: Sequence[V2Clause]) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    mask = pd.Series(True, index=panel.index)
    for clause in clauses:
        mask &= clause.mask(panel)
    return panel[mask]


def clause_from_dict(payload: Dict[str, Any]) -> V2Clause:
    return V2Clause(
        feature=str(payload["feature"]),
        family=str(payload.get("family") or V2_REGISTRY[str(payload["feature"])].family),
        datatype=str(payload["datatype"]),
        operator=str(payload["operator"]),
        bucket_id=str(payload["bucket_id"]),
        threshold_lo=payload.get("threshold_lo"),
        threshold_hi=payload.get("threshold_hi"),
        category=payload.get("category"),
        boolean_value=payload.get("boolean_value"),
    )


def neighbor_clauses(clause: V2Clause, registry: Optional[dict] = None) -> Tuple[V2Clause, ...]:
    siblings = clauses_for_feature(clause.feature, registry=registry)
    return tuple(s for s in siblings if s.bucket_id != clause.bucket_id)
