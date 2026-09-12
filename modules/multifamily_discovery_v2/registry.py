"""
V2 research-only feature registry.

Independent of production SEARCH_FEATURES. Temporal lag/delta/accel features
are registered as ineligible by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.multifamily_discovery_v2.contracts import (
    CONTROL_FEATURE_BUCKETS,
    DIST_FROM_EMA9_BUCKETS,
    EMA9_MA20_SLOPE_BUCKETS,
    HEALTH_GROUP_CATEGORIES,
    OBV_CATEGORIES,
    V2_REGISTRY_VERSION,
    VOLUME_RATIO20_BUCKETS,
)


@dataclass(frozen=True)
class NumericBucket:
    bucket_id: str
    threshold_lo: Optional[float]
    threshold_hi: Optional[float]
    operator: str  # <=, >, range


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    family: str
    datatype: str  # numeric | categorical | boolean
    source: str
    search_eligible: bool
    leakage_safe: bool
    t0_safe: bool
    missing_policy: str
    proposition_kind: str  # numeric_bucket | categorical_eq | boolean_eq | none
    numeric_buckets: Tuple[NumericBucket, ...] = ()
    categorical_values: Tuple[str, ...] = ()
    boolean_values: Tuple[bool, ...] = ()
    notes: str = ""
    degenerate_override: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "datatype": self.datatype,
            "source": self.source,
            "search_eligible": self.search_eligible,
            "leakage_safe": self.leakage_safe,
            "t0_safe": self.t0_safe,
            "missing_policy": self.missing_policy,
            "proposition_kind": self.proposition_kind,
            "numeric_buckets": [
                {
                    "bucket_id": b.bucket_id,
                    "threshold_lo": b.threshold_lo,
                    "threshold_hi": b.threshold_hi,
                    "operator": b.operator,
                }
                for b in self.numeric_buckets
            ],
            "categorical_values": list(self.categorical_values),
            "boolean_values": list(self.boolean_values),
            "notes": self.notes,
            "degenerate_override": self.degenerate_override,
        }


def _from_prod_buckets(raw: Sequence[Tuple[str, Optional[float], Optional[float], str]]) -> Tuple[NumericBucket, ...]:
    return tuple(NumericBucket(bucket_id, lo, hi, op) for bucket_id, lo, hi, op in raw)


MISSING_EXCLUDE = "exclude_row_from_clause"


def build_v2_registry() -> Dict[str, FeatureSpec]:
    """Frozen V2 registry. Eligibility is architectural, not outcome-tuned."""
    specs: List[FeatureSpec] = [
        FeatureSpec(
            name="rs5",
            family="rs_rsi",
            datatype="numeric",
            source="pattern_lifecycle.rs5",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(CONTROL_FEATURE_BUCKETS["rs5"]),
            notes="CONTROL feature. Production buckets copied verbatim.",
        ),
        FeatureSpec(
            name="rs10",
            family="rs_rsi",
            datatype="numeric",
            source="pattern_lifecycle.rs10",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(CONTROL_FEATURE_BUCKETS["rs10"]),
            notes="CONTROL feature. Production buckets copied verbatim.",
        ),
        FeatureSpec(
            name="rsi14",
            family="rs_rsi",
            datatype="numeric",
            source="pattern_lifecycle.rsi14",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(CONTROL_FEATURE_BUCKETS["rsi14"]),
            notes="CONTROL feature. Production buckets copied verbatim.",
        ),
        FeatureSpec(
            name="rs_spread",
            family="rs_rsi",
            datatype="numeric",
            source="pattern_lifecycle.rs_spread",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(CONTROL_FEATURE_BUCKETS["rs_spread"]),
            notes="CONTROL feature. Production buckets copied verbatim.",
        ),
        FeatureSpec(
            name="obv_status",
            family="obv",
            datatype="categorical",
            source="pattern_lifecycle.obv_status (normalized POSITIVE/NEGATIVE)",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="categorical_eq",
            categorical_values=OBV_CATEGORIES,
            notes="Stored T0 OBV state. Raw obv/obv_ema9 levels are not cross-sectionally comparable.",
        ),
        FeatureSpec(
            name="obv",
            family="obv",
            datatype="numeric",
            source="pattern_lifecycle.obv",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Absolute OBV is path-dependent and not comparable across symbols. Not search-eligible.",
        ),
        FeatureSpec(
            name="obv_ema9",
            family="obv",
            datatype="numeric",
            source="pattern_lifecycle.obv_ema9",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Absolute OBV EMA; not comparable. obv_status already encodes vs-EMA9 state.",
        ),
        FeatureSpec(
            name="volume_ratio20",
            family="volume",
            datatype="numeric",
            source="pattern_lifecycle.volume_ratio20",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(VOLUME_RATIO20_BUCKETS),
            notes="Relative volume. Buckets copied from earning-learning DNA p_volume, frozen a priori.",
        ),
        FeatureSpec(
            name="volume",
            family="volume",
            datatype="numeric",
            source="pattern_lifecycle.volume",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Raw volume not comparable across symbols.",
        ),
        FeatureSpec(
            name="vol_ma20",
            family="volume",
            datatype="numeric",
            source="pattern_lifecycle.vol_ma20",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Raw volume MA not comparable; volume_ratio20 is the relative form.",
        ),
        FeatureSpec(
            name="dryup",
            family="volume",
            datatype="boolean",
            source="pattern_lifecycle.dryup",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="boolean_eq",
            boolean_values=(True, False),
            notes="Eligible only if audit does not mark degenerate. Experiment runner may demote.",
        ),
        FeatureSpec(
            name="ema9_ma20_slope",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.ema9_ma20_slope",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(EMA9_MA20_SLOPE_BUCKETS),
            notes="Trend slope. Buckets copied from earning-learning DNA p_slope.",
        ),
        FeatureSpec(
            name="dist_from_ema9_pct",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.dist_from_ema9_pct",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="numeric_bucket",
            numeric_buckets=_from_prod_buckets(DIST_FROM_EMA9_BUCKETS),
            notes="Domain-neutral ±3% bands frozen a priori. Not fit on returns.",
        ),
        FeatureSpec(
            name="ema9",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.ema9",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Absolute price level; not comparable across symbols.",
        ),
        FeatureSpec(
            name="ma20",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.ma20",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Absolute MA level; not comparable across symbols.",
        ),
        FeatureSpec(
            name="ema9_ma20_slope_change",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.ema9_ma20_slope_change",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Held out of family screen to limit cardinality; slope level is the primary trend proposition.",
        ),
        FeatureSpec(
            name="price_vs_ema9_pct",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.price_vs_ema9_pct",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Redundant with dist_from_ema9_pct.",
        ),
        FeatureSpec(
            name="price_vs_ma20_pct",
            family="trend",
            datatype="numeric",
            source="pattern_lifecycle.price_vs_ma20_pct",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Held out of first family screen (cardinality). Not auto-eligible.",
        ),
        FeatureSpec(
            name="health_group",
            family="health_group",
            datatype="categorical",
            source="pattern_lifecycle.health_group (normalized)",
            search_eligible=True,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="categorical_eq",
            categorical_values=HEALTH_GROUP_CATEGORIES,
            notes="Normalized health-group labels. Primary health/group proposition.",
        ),
        FeatureSpec(
            name="health_score",
            family="health_group",
            datatype="numeric",
            source="pattern_lifecycle.health_score",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Continuous form of health_group. Not dual-searched to avoid redundant tests.",
        ),
        FeatureSpec(
            name="health_rank",
            family="health_group",
            datatype="numeric",
            source="pattern_lifecycle.health_rank",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Cross-sectional rank; universe size varies. Not auto-eligible.",
        ),
        FeatureSpec(
            name="group",
            family="health_group",
            datatype="categorical",
            source="pattern_lifecycle.group",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Production action/classification labels (MUA EARLY, MUA BREAK, ...). Definitional circularity risk.",
        ),
        FeatureSpec(
            name="group_rank",
            family="health_group",
            datatype="numeric",
            source="pattern_lifecycle.group_rank",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Not auto-eligible. Rank scale depends on daily universe.",
        ),
        FeatureSpec(
            name="total_score",
            family="health_group",
            datatype="numeric",
            source="pattern_lifecycle.total_score",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Likely redundant with health_score.",
        ),
        FeatureSpec(
            name="leader_score",
            family="other",
            datatype="numeric",
            source="pattern_lifecycle.leader_score",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Sparse in current lifecycle. Inventoried, not search-eligible.",
        ),
        FeatureSpec(
            name="green2",
            family="other",
            datatype="boolean",
            source="pattern_lifecycle.green2",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Degenerate candidate: expected all-False in current lifecycle. Not repaired.",
        ),
        FeatureSpec(
            name="early",
            family="other",
            datatype="boolean",
            source="pattern_lifecycle.early",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Degenerate candidate. Not repaired.",
        ),
        FeatureSpec(
            name="pull",
            family="other",
            datatype="boolean",
            source="pattern_lifecycle.pull",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Degenerate candidate. Not repaired.",
        ),
        FeatureSpec(
            name="rsi_slope",
            family="other",
            datatype="numeric",
            source="pattern_lifecycle.rsi_slope",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Inventoried only. RSI level is the CONTROL RSI proposition.",
        ),
        FeatureSpec(
            name="close",
            family="other",
            datatype="numeric",
            source="pattern_lifecycle.price as close",
            search_eligible=False,
            leakage_safe=True,
            t0_safe=True,
            missing_policy=MISSING_EXCLUDE,
            proposition_kind="none",
            notes="Absolute price; not a hypothesis feature.",
        ),
    ]
    return {s.name: s for s in specs}


V2_REGISTRY: Dict[str, FeatureSpec] = build_v2_registry()


def registry_to_dict() -> Dict[str, Any]:
    return {
        "registry_version": V2_REGISTRY_VERSION,
        "features": {name: spec.to_dict() for name, spec in V2_REGISTRY.items()},
    }


def eligible_names_for_families(families: Sequence[str], *, demoted: Optional[Sequence[str]] = None) -> Tuple[str, ...]:
    blocked = set(demoted or ())
    names: List[str] = []
    for spec in V2_REGISTRY.values():
        if spec.family not in families:
            continue
        if not spec.search_eligible or spec.name in blocked:
            continue
        names.append(spec.name)
    return tuple(names)
