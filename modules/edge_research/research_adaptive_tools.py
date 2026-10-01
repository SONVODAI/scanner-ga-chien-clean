"""
Adaptive slicing research tools for Phase 3F.

Data-driven partition, threshold exploration, neighborhood stability,
and categorical comparison — all OutcomeSpec-operational.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.research_feature_eligibility import (
    FeatureRole,
    require_eligible_feature,
)
from modules.edge_research.research_outcome_evaluator import (
    compare_group_outcome_profiles,
    compute_outcome_profile,
    default_outcome_spec_for_horizon,
    resolve_outcome_spec_from_scope,
)
from modules.edge_research.research_shape import (
    OBS_SHAPE_EXTREME_BIN,
    OBS_SHAPE_FLAT,
    OBS_SHAPE_GRADIENT,
    OBS_SHAPE_MONOTONIC_DECREASING,
    OBS_SHAPE_MONOTONIC_INCREASING,
    OBS_SHAPE_NOISY,
    OBS_SHAPE_STEP_CHANGE,
    interpret_partition_shape,
)
from modules.edge_research.research_tools import (
    OBS_NO_CLEAR_DIFFERENCE,
    OBS_NO_VARIATION,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    LeakageClass,
    ResearchTool,
    ToolMetadata,
    ToolResult,
    ToolStatus,
    _base_result,
    _obs,
    resolve_cohort,
)

ADAPTIVE_TOOLBOX_VERSION = "adaptive_toolbox_v1"

DEFAULT_MIN_TOTAL_N = 20
DEFAULT_MIN_BIN_N = 5
DEFAULT_MAX_BINS = 4


def _resolve_outcome_spec(research_scope: Dict[str, Any], inputs: Dict[str, Any]):
    spec = resolve_outcome_spec_from_scope(research_scope)
    if spec is not None:
        return spec
    horizon = str(inputs.get("horizon", "T5"))
    return default_outcome_spec_for_horizon(horizon)


def _quantile_bin_edges(
    values: pd.Series,
    max_bins: int,
    min_bin_n: int,
) -> List[float]:
    """Deterministic quantile boundaries with tie handling."""
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return []
    n = len(clean)
    effective_bins = min(max_bins, max(2, n // min_bin_n))
    if effective_bins < 2:
        return []
    quantiles = np.linspace(0, 1, effective_bins + 1)[1:-1]
    edges = sorted(set(float(clean.quantile(q, interpolation="linear")) for q in quantiles))
    return edges


def _assign_quantile_bins(values: pd.Series, edges: Sequence[float]) -> pd.Series:
    if not edges:
        return pd.Series(["all"] * len(values), index=values.index, dtype="object")
    bins = pd.cut(
        pd.to_numeric(values, errors="coerce"),
        bins=[-np.inf] + list(edges) + [np.inf],
        labels=[f"q{i + 1}" for i in range(len(edges) + 1)],
        duplicates="drop",
    )
    return bins.astype(str)


def _shape_observation(shape) -> Any:
    code_map = {
        "SHAPE_MONOTONIC_INCREASING": OBS_SHAPE_MONOTONIC_INCREASING,
        "SHAPE_MONOTONIC_DECREASING": OBS_SHAPE_MONOTONIC_DECREASING,
        "SHAPE_STEP_CHANGE": OBS_SHAPE_STEP_CHANGE,
        "SHAPE_EXTREME_BIN_EFFECT": OBS_SHAPE_EXTREME_BIN,
        "SHAPE_FLAT": OBS_SHAPE_FLAT,
        "SHAPE_NOISY_INCONCLUSIVE": OBS_SHAPE_NOISY,
        "SHAPE_GRADIENT_DETECTED": OBS_SHAPE_GRADIENT,
    }
    code = code_map.get(shape.shape_code, OBS_SHAPE_GRADIENT)
    severity = "HIGH" if shape.strength > 5.0 else "MEDIUM"
    return _obs(code, shape.to_dict(), severity)


class AdaptivePartitionCompareTool(ResearchTool):
    """Data-driven quantile partition of a continuous feature vs OutcomeSpec."""

    metadata = ToolMetadata(
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        description="Partition continuous feature by data-derived quantiles; compare OutcomeSpec across bins.",
        input_schema={
            "feature_column": "str",
            "max_bins": "int",
            "min_bin_n": "int",
            "min_total_n": "int",
            "partition_method": "quantile",
        },
        output_schema={"groups": "dict", "metrics": "dict", "shape": "dict"},
        minimum_data_requirements={"min_rows": DEFAULT_MIN_TOTAL_N},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        feature = str(inputs["feature_column"])
        max_bins = int(inputs.get("max_bins", DEFAULT_MAX_BINS))
        min_bin_n = int(inputs.get("min_bin_n", DEFAULT_MIN_BIN_N))
        min_total_n = int(inputs.get("min_total_n", DEFAULT_MIN_TOTAL_N))
        outcome_spec = _resolve_outcome_spec(research_scope, inputs)

        try:
            require_eligible_feature(
                feature,
                research_scope=research_scope,
                allowed_roles={FeatureRole.CONTINUOUS.value, FeatureRole.ORDINAL.value},
                panel=panel,
            )
        except Exception as exc:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=0,
                metrics={"error": str(exc)},
                limitations=[str(exc)],
            )

        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
        )
        if len(cohort) < min_total_n:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=len(cohort),
                metrics={"min_total_n": min_total_n},
                diagnostics=diag,
                limitations=["insufficient_total_n"],
            )

        if feature not in cohort.columns:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=len(cohort),
                metrics={},
                diagnostics=diag,
                limitations=[f"missing_feature:{feature}"],
            )

        edges = _quantile_bin_edges(cohort[feature], max_bins, min_bin_n)
        group_key = _assign_quantile_bins(cohort[feature], edges)
        groups, baseline = compare_group_outcome_profiles(
            cohort,
            group_key,
            outcome_spec,
            data_cutoff_date=data_cutoff_date,
        )

        # Enforce min bin N
        valid_groups = {
            k: v for k, v in groups.items() if int(v.get("n_eligible", 0)) >= min_bin_n
        }
        if len(valid_groups) < 2:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=len(cohort),
                metrics={
                    "feature_column": feature,
                    "discovered_boundaries": edges,
                    "outcome_spec_hash": outcome_spec.content_hash(),
                },
                groups=groups,
                diagnostics=diag,
                limitations=["insufficient_bin_n"],
            )

        shape = interpret_partition_shape(
            valid_groups,
            baseline_rate=baseline.success_rate,
            min_bin_n=min_bin_n,
        )
        obs = [_shape_observation(shape)]
        spread = shape.effect_spread
        if shape.shape_code == OBS_SHAPE_FLAT:
            obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"effect_spread": spread}))
            status = ToolStatus.OK
        elif spread < 0.01:
            obs.append(_obs(OBS_NO_VARIATION, {"effect_spread": spread}))
            status = ToolStatus.NO_VARIATION
        else:
            obs.append(
                _obs(
                    OBS_TRAJECTORY_GROUP_DIFFERENCE,
                    {"effect_spread": spread, "shape_code": shape.shape_code},
                )
            )
            status = ToolStatus.OK

        boundaries_record = [
            {"index": i, "value": e} for i, e in enumerate(edges)
        ]
        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=status,
            sample_size=len(cohort),
            metrics={
                "adaptive_toolbox_version": ADAPTIVE_TOOLBOX_VERSION,
                "feature_column": feature,
                "partition_method": "quantile",
                "discovered_boundaries": edges,
                "boundaries_record": boundaries_record,
                "outcome_spec_hash": outcome_spec.content_hash(),
                "baseline_success_rate": baseline.success_rate,
                "shape": shape.to_dict(),
                "bin_count": len(valid_groups),
                "partitions_considered": len(edges) + 1,
            },
            groups=valid_groups,
            diagnostics=diag,
            observations=obs,
        )


class ThresholdExplorationTool(ResearchTool):
    """Data-derived threshold cut exploration driven by prior partition evidence."""

    metadata = ToolMetadata(
        tool_name="threshold_exploration",
        tool_version="v1",
        description="Test data-derived cut points on continuous feature against OutcomeSpec.",
        input_schema={
            "feature_column": "str",
            "candidate_cuts": "list[float]",
            "direction": "high|low",
            "parent_experiment_id": "str",
        },
        output_schema={"candidates": "list", "best_threshold": "dict"},
        minimum_data_requirements={"min_rows": DEFAULT_MIN_TOTAL_N},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        feature = str(inputs["feature_column"])
        cuts = [float(c) for c in (inputs.get("candidate_cuts") or [])]
        direction = str(inputs.get("direction", "high"))
        outcome_spec = _resolve_outcome_spec(research_scope, inputs)

        try:
            require_eligible_feature(
                feature,
                research_scope=research_scope,
                allowed_roles={FeatureRole.CONTINUOUS.value, FeatureRole.ORDINAL.value},
                panel=panel,
            )
        except Exception as exc:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=0,
                metrics={"error": str(exc)},
                limitations=[str(exc)],
            )

        if not cuts:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=0,
                metrics={},
                limitations=["candidate_cuts_required"],
            )

        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
        )
        baseline = compute_outcome_profile(cohort, outcome_spec, data_cutoff_date=data_cutoff_date)
        candidates: List[Dict[str, Any]] = []

        for cut in sorted(set(cuts)):
            if direction == "high":
                mask = pd.to_numeric(cohort[feature], errors="coerce") >= cut
            else:
                mask = pd.to_numeric(cohort[feature], errors="coerce") <= cut
            subset = cohort[mask]
            prof = compute_outcome_profile(subset, outcome_spec, data_cutoff_date=data_cutoff_date)
            base_rate = baseline.success_rate or 0.0
            grp_rate = prof.success_rate or 0.0
            candidates.append(
                {
                    "threshold": cut,
                    "direction": direction,
                    "candidate_n": prof.n_eligible,
                    "baseline_n": baseline.n_eligible,
                    "success_rate": grp_rate,
                    "baseline_success_rate": base_rate,
                    "incremental_success_rate": grp_rate - base_rate,
                    "search_origin": inputs.get("parent_experiment_id", ""),
                    "complexity_increment": 1,
                }
            )

        best = max(candidates, key=lambda c: abs(c["incremental_success_rate"]))
        obs = []
        if abs(best["incremental_success_rate"]) >= 2.0:
            obs.append(
                _obs(
                    OBS_TRAJECTORY_GROUP_DIFFERENCE,
                    {"best_threshold": best["threshold"], "incremental": best["incremental_success_rate"]},
                )
            )
        else:
            obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"best_threshold": best["threshold"]}))

        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK,
            sample_size=len(cohort),
            metrics={
                "feature_column": feature,
                "direction": direction,
                "outcome_spec_hash": outcome_spec.content_hash(),
                "candidates_tested": len(candidates),
                "best_threshold": best,
                "thresholds_considered": len(candidates),
            },
            groups={"candidates": candidates},
            diagnostics=diag,
            observations=obs,
        )


class ThresholdNeighborhoodTool(ResearchTool):
    """Test neighboring data-derived cuts around a discovered threshold."""

    metadata = ToolMetadata(
        tool_name="threshold_neighborhood",
        tool_version="v1",
        description="Neighborhood stability test for data-derived threshold regions.",
        input_schema={
            "feature_column": "str",
            "center_threshold": "float",
            "neighbor_offsets": "list[float]",
            "direction": "high|low",
        },
        output_schema={"neighbors": "list", "stability_class": "str"},
        minimum_data_requirements={"min_rows": DEFAULT_MIN_TOTAL_N},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        feature = str(inputs["feature_column"])
        center = float(inputs["center_threshold"])
        offsets = [float(o) for o in (inputs.get("neighbor_offsets") or [])]
        direction = str(inputs.get("direction", "high"))
        outcome_spec = _resolve_outcome_spec(research_scope, inputs)

        if not offsets:
            # Default: adjacent quantile-style offsets from data spread
            cohort, diag = resolve_cohort(
                panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
            )
            vals = pd.to_numeric(cohort[feature], errors="coerce").dropna()
            if len(vals) > 1:
                spread = float(vals.std()) if vals.std() > 0 else float(vals.max() - vals.min()) / 4.0
                offsets = [-spread, spread] if spread > 0 else [-0.01, 0.01]
            else:
                offsets = [-0.01, 0.01]
        else:
            cohort, diag = resolve_cohort(
                panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
            )

        baseline = compute_outcome_profile(cohort, outcome_spec, data_cutoff_date=data_cutoff_date)
        center_prof = _threshold_profile(cohort, feature, center, direction, outcome_spec, data_cutoff_date)
        neighbors: List[Dict[str, Any]] = []
        for off in offsets:
            t = center + off
            prof = _threshold_profile(cohort, feature, t, direction, outcome_spec, data_cutoff_date)
            neighbors.append(
                {
                    "threshold": t,
                    "offset": off,
                    "incremental_success_rate": prof["incremental_success_rate"],
                    "candidate_n": prof["candidate_n"],
                }
            )

        center_inc = center_prof["incremental_success_rate"]
        neighbor_incs = [n["incremental_success_rate"] for n in neighbors]
        same_sign = all(
            (center_inc >= 0 and n >= 0) or (center_inc < 0 and n < 0) for n in neighbor_incs
        )
        magnitude_close = all(abs(n - center_inc) < max(5.0, abs(center_inc) * 0.5 + 2.0) for n in neighbor_incs)

        if same_sign and magnitude_close and abs(center_inc) >= 2.0:
            stability = "ROBUST_REGION"
            obs_code = "THRESHOLD_ROBUST_REGION"
        elif abs(center_inc) >= 2.0 and not same_sign:
            stability = "UNSTABLE_THRESHOLD"
            obs_code = "THRESHOLD_UNSTABLE"
        elif abs(center_inc) >= 2.0:
            stability = "POINT_ESTIMATE_ONLY"
            obs_code = "THRESHOLD_POINT_ONLY"
        else:
            stability = "UNSTABLE_THRESHOLD"
            obs_code = "THRESHOLD_UNSTABLE"

        from modules.edge_research.research_tools import OBS_NEIGHBORHOOD_STABLE, OBS_NEIGHBORHOOD_UNSTABLE

        obs = [
            _obs(
                OBS_NEIGHBORHOOD_STABLE if stability == "ROBUST_REGION" else OBS_NEIGHBORHOOD_UNSTABLE,
                {
                    "stability_class": stability,
                    "center_threshold": center,
                    "center_incremental": center_inc,
                    "neighbors": neighbors,
                },
            )
        ]

        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK,
            sample_size=len(cohort),
            metrics={
                "feature_column": feature,
                "center_threshold": center,
                "stability_class": stability,
                "outcome_spec_hash": outcome_spec.content_hash(),
                "center_profile": center_prof,
                "neighbors_tested": len(neighbors),
            },
            groups={"neighbors": neighbors},
            diagnostics=diag,
            observations=obs,
        )


def _threshold_profile(
    cohort: pd.DataFrame,
    feature: str,
    threshold: float,
    direction: str,
    outcome_spec,
    data_cutoff_date: str,
) -> Dict[str, Any]:
    if direction == "high":
        mask = pd.to_numeric(cohort[feature], errors="coerce") >= threshold
    else:
        mask = pd.to_numeric(cohort[feature], errors="coerce") <= threshold
    subset = cohort[mask]
    prof = compute_outcome_profile(subset, outcome_spec, data_cutoff_date=data_cutoff_date)
    baseline = compute_outcome_profile(cohort, outcome_spec, data_cutoff_date=data_cutoff_date)
    base_rate = baseline.success_rate or 0.0
    grp_rate = prof.success_rate or 0.0
    return {
        "threshold": threshold,
        "candidate_n": prof.n_eligible,
        "baseline_n": baseline.n_eligible,
        "success_rate": grp_rate,
        "incremental_success_rate": grp_rate - base_rate,
    }


class CategoricalAdaptiveCompareTool(ResearchTool):
    """Compare OutcomeSpec across categorical feature levels."""

    metadata = ToolMetadata(
        tool_name="categorical_adaptive_compare",
        tool_version="v1",
        description="Compare OutcomeSpec across categorical levels with separation detection.",
        input_schema={
            "feature_column": "str",
            "min_category_n": "int",
        },
        output_schema={"groups": "dict", "separation": "dict"},
        minimum_data_requirements={"min_rows": 10},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        feature = str(inputs["feature_column"])
        min_cat_n = int(inputs.get("min_category_n", DEFAULT_MIN_BIN_N))
        outcome_spec = _resolve_outcome_spec(research_scope, inputs)

        try:
            require_eligible_feature(
                feature,
                research_scope=research_scope,
                allowed_roles={
                    FeatureRole.CATEGORICAL.value,
                    FeatureRole.CONTEXT.value,
                },
                panel=panel,
            )
        except Exception as exc:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=0,
                metrics={"error": str(exc)},
                limitations=[str(exc)],
            )

        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
        )
        if feature not in cohort.columns:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=len(cohort),
                metrics={},
                limitations=[f"missing_feature:{feature}"],
            )

        group_key = cohort[feature].astype(str)
        groups, baseline = compare_group_outcome_profiles(
            cohort, group_key, outcome_spec, data_cutoff_date=data_cutoff_date
        )
        valid = {k: v for k, v in groups.items() if int(v.get("n_eligible", 0)) >= min_cat_n}
        if len(valid) < 2:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=len(cohort),
                metrics={"feature_column": feature},
                groups=groups,
                diagnostics=diag,
                limitations=["insufficient_category_n"],
            )

        rates = [v.get("success_rate") or 0.0 for v in valid.values()]
        spread = max(rates) - min(rates)
        best_cat = max(valid.items(), key=lambda kv: kv[1].get("success_rate") or 0.0)
        worst_cat = min(valid.items(), key=lambda kv: kv[1].get("success_rate") or 0.0)

        obs = []
        if spread >= 2.0:
            obs.append(
                _obs(
                    OBS_TRAJECTORY_GROUP_DIFFERENCE,
                    {
                        "category_spread": spread,
                        "best_category": best_cat[0],
                        "worst_category": worst_cat[0],
                    },
                )
            )
            obs.append(
                _obs(
                    "CATEGORY_SEPARATION_DETECTED",
                    {"spread": spread, "feature": feature},
                )
            )
            status = ToolStatus.OK
        else:
            obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"category_spread": spread}))
            status = ToolStatus.OK

        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=status,
            sample_size=len(cohort),
            metrics={
                "feature_column": feature,
                "outcome_spec_hash": outcome_spec.content_hash(),
                "category_spread": spread,
                "best_category": best_cat[0],
                "worst_category": worst_cat[0],
                "categories_compared": len(valid),
            },
            groups=valid,
            diagnostics=diag,
            observations=obs,
        )


class InteractionPartitionTool(ResearchTool):
    """Bounded two-variable interaction when prior evidence justifies it."""

    metadata = ToolMetadata(
        tool_name="interaction_partition",
        tool_version="v1",
        description="Two-variable partition follow-up when prior shape evidence exists.",
        input_schema={
            "primary_feature": "str",
            "secondary_feature": "str",
            "max_bins": "int",
        },
        output_schema={"groups": "dict"},
        minimum_data_requirements={"min_rows": DEFAULT_MIN_TOTAL_N},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        primary = str(inputs["primary_feature"])
        secondary = str(inputs["secondary_feature"])
        outcome_spec = _resolve_outcome_spec(research_scope, inputs)

        for feat in (primary, secondary):
            try:
                require_eligible_feature(feat, research_scope=research_scope, panel=panel)
            except Exception as exc:
                return _base_result(
                    self,
                    inputs=inputs,
                    research_scope=research_scope,
                    data_cutoff_date=data_cutoff_date,
                    status=ToolStatus.INVALID_INPUT,
                    sample_size=0,
                    metrics={"error": str(exc)},
                    limitations=[str(exc)],
                )

        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=["T3", "T5", "T10"]
        )
        combo = (
            cohort[primary].astype(str) + "|" + cohort[secondary].astype(str)
        )
        groups, baseline = compare_group_outcome_profiles(
            cohort, combo, outcome_spec, data_cutoff_date=data_cutoff_date
        )
        rates = [v.get("success_rate") or 0.0 for v in groups.values() if v.get("n_eligible", 0) >= 5]
        spread = max(rates) - min(rates) if len(rates) >= 2 else 0.0
        obs = [
            _obs(
                OBS_TRAJECTORY_GROUP_DIFFERENCE if spread >= 2.0 else OBS_NO_CLEAR_DIFFERENCE,
                {"interaction_spread": spread, "primary": primary, "secondary": secondary},
            )
        ]
        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK,
            sample_size=len(cohort),
            metrics={
                "primary_feature": primary,
                "secondary_feature": secondary,
                "interaction_spread": spread,
                "complexity_increment": 2,
                "outcome_spec_hash": outcome_spec.content_hash(),
            },
            groups=groups,
            diagnostics=diag,
            observations=obs,
        )


def build_adaptive_tool_registry():
    """Return adaptive tools for registration alongside default toolbox."""
    return (
        AdaptivePartitionCompareTool(),
        ThresholdExplorationTool(),
        ThresholdNeighborhoodTool(),
        CategoricalAdaptiveCompareTool(),
        InteractionPartitionTool(),
    )
