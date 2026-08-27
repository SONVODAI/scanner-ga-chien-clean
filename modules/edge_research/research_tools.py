"""
Deterministic research toolbox for Edge Research (PATCH 3B).

Callable empirical instruments only — no planner, no edge search, no investment logic.
"""

from __future__ import annotations

import copy
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type

import numpy as np
import pandas as pd

from modules.edge_research.contracts import (
    DATE_CONCENTRATION_SEVERE,
    FEATURE_BUCKETS,
    SYMBOL_CONCENTRATION_SEVERE,
)
from modules.edge_research.discovery import ConditionClause, apply_condition
from modules.edge_research.episodes import segment_market_episodes
from modules.edge_research.feature_builder import build_t0_feature_matrix
from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS, compute_horizon_profile
from modules.edge_research.research_graph import ResearchGraph, ResearchGraphError
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    StructuredResearchObservation,
    compute_experiment_content_hash,
    compute_result_hash,
)
from modules.edge_research.robustness import test_neighborhood_stability
from modules.edge_research.statistical_guardrails import (
    compute_concentration_diagnostics,
    compute_episode_validation,
    MIN_UNIQUE_DATES_FOR_STABILITY,
    MIN_UNIQUE_SYMBOLS_FOR_STABILITY,
)

TOOLBOX_VERSION = "research_toolbox_v1"

# Empirical observation codes — machine-readable, no investment meaning.
OBS_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
OBS_NO_CLEAR_DIFFERENCE = "NO_CLEAR_DIFFERENCE"
OBS_NO_VARIATION = "NO_VARIATION"
OBS_DATE_CONCENTRATED = "DATE_CONCENTRATED"
OBS_DATE_BROAD = "DATE_BROAD"
OBS_SYMBOL_CONCENTRATED = "SYMBOL_CONCENTRATED"
OBS_SYMBOL_BROAD = "SYMBOL_BROAD"
OBS_EPISODE_HETEROGENEOUS = "EPISODE_HETEROGENEOUS"
OBS_EPISODE_CONSISTENT = "EPISODE_CONSISTENT"
OBS_EPISODE_INSUFFICIENT = "EPISODE_INSUFFICIENT"
OBS_MARKET_HETEROGENEOUS = "MARKET_HETEROGENEOUS"
OBS_HORIZON_HETEROGENEOUS = "HORIZON_HETEROGENEOUS"
OBS_NEIGHBORHOOD_UNSTABLE = "NEIGHBORHOOD_UNSTABLE"
OBS_NEIGHBORHOOD_STABLE = "NEIGHBORHOOD_STABLE"
OBS_EXTREME_WINNER_SENSITIVE = "EXTREME_WINNER_SENSITIVE"
OBS_EXTREME_WINNER_ROBUST = "EXTREME_WINNER_ROBUST"
OBS_TRAJECTORY_GROUP_DIFFERENCE = "TRAJECTORY_GROUP_DIFFERENCE"
OBS_SENSITIVITY_FRAGILE = "SENSITIVITY_FRAGILE"
OBS_SENSITIVITY_ROBUST = "SENSITIVITY_ROBUST"

HORIZON_SESSION_OFFSET = {"T3": 3, "T5": 5, "T10": 10}
TARGET_DATE_COLUMNS = {"T3": "t3_target_date", "T5": "t5_target_date", "T10": "t10_target_date"}


class ToolStatus(str, Enum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    NO_VARIATION = "NO_VARIATION"


class LeakageClass(str, Enum):
    T0_SAFE = "T0_SAFE"
    MATURED_OUTCOME = "MATURED_OUTCOME"
    REQUIRES_EXPLICIT_CUTOFF = "REQUIRES_EXPLICIT_CUTOFF"


@dataclass(frozen=True)
class ToolResult:
    """Common structured envelope for all research tools."""

    tool_name: str
    tool_version: str
    data_cutoff_date: str
    input_hash: str
    sample_size: int
    status: ToolStatus
    metrics: Dict[str, Any] = field(default_factory=dict)
    groups: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    structured_observations: Tuple[StructuredResearchObservation, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "data_cutoff_date": self.data_cutoff_date,
            "input_hash": self.input_hash,
            "sample_size": self.sample_size,
            "status": self.status.value,
            "metrics": dict(self.metrics),
            "groups": dict(self.groups),
            "diagnostics": dict(self.diagnostics),
            "limitations": list(self.limitations),
            "structured_observations": [o.to_dict() for o in self.structured_observations],
        }

    def metrics_for_experiment(self) -> Dict[str, Any]:
        """Flatten envelope for ExperimentResult.metrics storage."""
        return {
            "toolbox_version": TOOLBOX_VERSION,
            "tool_status": self.status.value,
            "input_hash": self.input_hash,
            "sample_size": self.sample_size,
            **self.metrics,
            "groups": self.groups,
            "diagnostics": self.diagnostics,
            "limitations": self.limitations,
        }


@dataclass(frozen=True)
class ToolMetadata:
    tool_name: str
    tool_version: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    minimum_data_requirements: Dict[str, Any]
    leakage_classification: str
    deterministic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "minimum_data_requirements": self.minimum_data_requirements,
            "leakage_classification": self.leakage_classification,
            "deterministic": self.deterministic,
        }


class ResearchTool(ABC):
    """Deterministic empirical research instrument."""

    metadata: ToolMetadata

    @abstractmethod
    def execute(
        self,
        panel: pd.DataFrame,
        *,
        inputs: Dict[str, Any],
        research_scope: Dict[str, Any],
        data_cutoff_date: str,
    ) -> ToolResult:
        ...


def compute_tool_input_hash(
    tool_name: str,
    tool_version: str,
    inputs: Dict[str, Any],
    research_scope: Dict[str, Any],
    data_cutoff_date: str,
) -> str:
    canonical = json.dumps(
        {
            "tool_name": tool_name,
            "tool_version": tool_version,
            "inputs": _normalize_json(inputs),
            "research_scope": _normalize_json(research_scope),
            "data_cutoff_date": data_cutoff_date,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_json(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, list):
        return [_normalize_json(v) for v in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


def _parse_clauses(scope: Dict[str, Any]) -> Tuple[ConditionClause, ...]:
    clauses: List[ConditionClause] = []
    for item in scope.get("condition_clauses") or []:
        clauses.append(
            ConditionClause(
                feature=str(item["feature"]),
                operator=str(item["operator"]),
                threshold_lo=item.get("threshold_lo"),
                threshold_hi=item.get("threshold_hi"),
                bucket_id=str(item.get("bucket_id", f"{item['feature']}_custom")),
            )
        )
    return tuple(clauses)


def apply_research_cutoff(
    panel: pd.DataFrame,
    data_cutoff_date: str,
    *,
    horizon: Optional[str] = None,
    horizons: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Filter panel to T0 rows on/before cutoff with matured outcomes only.

    Returns copy — never mutates source panel.
    """
    diagnostics: Dict[str, Any] = {
        "data_cutoff_date": data_cutoff_date,
        "rows_before_cutoff_filter": int(len(panel)),
    }
    if panel.empty:
        return panel.copy(), diagnostics

    work = panel.copy()
    work["_trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce")
    cutoff = pd.Timestamp(data_cutoff_date)
    after_cutoff = int((work["_trade_date_dt"] > cutoff).sum())
    work = work[work["_trade_date_dt"] <= cutoff].copy()
    diagnostics["rows_excluded_after_t0_cutoff"] = after_cutoff
    diagnostics["rows_after_t0_cutoff"] = int(len(work))

    hs = list(horizons or ([horizon] if horizon else []))
    for h in hs:
        col = RETURN_COLUMNS.get(h, "")
        if not col or col not in work.columns:
            continue
        target_col = TARGET_DATE_COLUMNS.get(h, "")
        if target_col in work.columns:
            tgt = pd.to_datetime(work[target_col], errors="coerce")
            immature = work[col].notna() & (tgt > cutoff)
            diagnostics[f"rows_excluded_immature_{h}"] = int(immature.sum())
            work.loc[immature, col] = np.nan
        # Rows with NaN return are implicitly immature/unavailable

    work = work.drop(columns=["_trade_date_dt"], errors="ignore")
    return work, diagnostics


def resolve_cohort(
    panel: pd.DataFrame,
    research_scope: Dict[str, Any],
    *,
    data_cutoff_date: str,
    horizon: Optional[str] = None,
    horizons: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Apply cutoff then scope filters. Returns copy."""
    filtered, cutoff_diag = apply_research_cutoff(
        panel, data_cutoff_date, horizon=horizon, horizons=horizons
    )
    diag = {"cutoff": cutoff_diag}
    if filtered.empty:
        return filtered, diag

    cohort = filtered
    transition = research_scope.get("market_transition")
    if transition:
        cohort = cohort[cohort["research_market_transition"] == str(transition)]
    state = research_scope.get("market_state")
    if state:
        cohort = cohort[cohort["research_market_state"] == str(state)]

    clauses = _parse_clauses(research_scope)
    if clauses:
        cohort = apply_condition(cohort, clauses)

    symbol_filter = research_scope.get("symbols")
    if symbol_filter:
        sym_set = set(str(s) for s in symbol_filter)
        cohort = cohort[cohort["symbol"].astype(str).isin(sym_set)]

    diag["cohort_n"] = int(len(cohort))
    return cohort.copy(), diag


def _horizon_col(horizon: str) -> str:
    if horizon not in RETURN_COLUMNS:
        raise ValueError(f"Unknown horizon: {horizon}")
    return RETURN_COLUMNS[horizon]


def _obs(code: str, evidence: Dict[str, Any], severity: str = "MEDIUM") -> StructuredResearchObservation:
    return StructuredResearchObservation(code=code, severity=severity, evidence=evidence)


def _base_result(
    tool: ResearchTool,
    *,
    inputs: Dict[str, Any],
    research_scope: Dict[str, Any],
    data_cutoff_date: str,
    status: ToolStatus,
    sample_size: int,
    metrics: Dict[str, Any],
    groups: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
    limitations: Optional[List[str]] = None,
    observations: Optional[Sequence[StructuredResearchObservation]] = None,
) -> ToolResult:
    return ToolResult(
        tool_name=tool.metadata.tool_name,
        tool_version=tool.metadata.tool_version,
        data_cutoff_date=data_cutoff_date,
        input_hash=compute_tool_input_hash(
            tool.metadata.tool_name,
            tool.metadata.tool_version,
            inputs,
            research_scope,
            data_cutoff_date,
        ),
        sample_size=sample_size,
        status=status,
        metrics=metrics,
        groups=groups or {},
        diagnostics=diagnostics or {},
        limitations=list(limitations or []),
        structured_observations=tuple(observations or ()),
    )


def _assign_numeric_bins(series: pd.Series, bins: Sequence[Dict[str, Any]]) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    labels: List[Optional[str]] = []
    for v in values:
        if pd.isna(v):
            labels.append(None)
            continue
        matched = None
        for spec in bins:
            lo = spec.get("lo")
            hi = spec.get("hi")
            lo_ok = True if lo is None else float(v) > float(lo)
            hi_ok = True if hi is None else float(v) <= float(hi)
            if lo_ok and hi_ok:
                matched = str(spec.get("label", "bin"))
                break
        labels.append(matched)
    return pd.Series(labels, index=series.index, dtype="object")


class PartitionGroupCompareTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="partition_group_compare",
        tool_version="v1",
        description="Compare an outcome measure across explicitly supplied groups.",
        input_schema={
            "partition_column": "str",
            "partition_type": "categorical|numeric_bins",
            "bins": "optional list of {lo, hi, label}",
            "horizon": "T3|T5|T10",
        },
        output_schema={"groups": "dict", "metrics": "dict"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        col = _horizon_col(horizon)
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )

        from modules.edge_research.research_outcome_evaluator import (
            compare_group_outcome_profiles,
            resolve_outcome_spec_from_scope,
            default_outcome_spec_for_horizon,
        )

        outcome_spec = resolve_outcome_spec_from_scope(research_scope)
        use_outcome_spec = outcome_spec is not None
        if outcome_spec is None:
            outcome_spec = default_outcome_spec_for_horizon(horizon)

        if cohort.empty:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0,
                metrics={},
                diagnostics=diag,
                limitations=["empty_cohort"],
            )

        part_col = str(inputs["partition_column"])
        if part_col not in cohort.columns:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT,
                sample_size=len(cohort),
                metrics={},
                diagnostics=diag,
                limitations=[f"missing_partition_column:{part_col}"],
            )

        if inputs.get("partition_type") == "numeric_bins":
            bins = inputs.get("bins") or []
            if not bins:
                return _base_result(
                    self,
                    inputs=inputs,
                    research_scope=research_scope,
                    data_cutoff_date=data_cutoff_date,
                    status=ToolStatus.INVALID_INPUT,
                    sample_size=len(cohort),
                    metrics={},
                    diagnostics=diag,
                    limitations=["numeric_bins_required"],
                )
            group_key = _assign_numeric_bins(cohort[part_col], bins)
        else:
            group_key = cohort[part_col].astype(str)

        if use_outcome_spec:
            groups_raw, baseline = compare_group_outcome_profiles(
                cohort,
                group_key,
                outcome_spec,
                data_cutoff_date=data_cutoff_date,
            )
            groups = {
                k: {
                    "n": v.get("n_eligible", 0),
                    "median": v.get("median_primary_return"),
                    "mean": v.get("mean_primary_return"),
                    "success_rate": v.get("success_rate"),
                    "incremental_success_rate": v.get("incremental_success_rate"),
                }
                for k, v in groups_raw.items()
            }
            spread_vals = [v.get("incremental_success_rate") for v in groups_raw.values() if v.get("incremental_success_rate") is not None]
            spread = max(spread_vals) - min(spread_vals) if len(spread_vals) >= 2 else 0.0
            obs: List[StructuredResearchObservation] = []
            if len(groups) < 2:
                status = ToolStatus.NO_VARIATION
                obs.append(_obs(OBS_NO_VARIATION, {"group_count": len(groups)}))
            else:
                status = ToolStatus.OK
                if spread < 0.01:
                    obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"outcome_spread": spread}))
                else:
                    obs.append(
                        _obs(
                            OBS_TRAJECTORY_GROUP_DIFFERENCE,
                            {
                                "outcome_spread": spread,
                                "outcome_spec_hash": outcome_spec.content_hash(),
                                "groups": len(groups),
                            },
                        )
                    )
            sample_size = int(baseline.n_eligible)
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=status,
                sample_size=sample_size,
                metrics={
                    "horizon": horizon,
                    "group_count": len(groups),
                    "outcome_spread": spread,
                    "outcome_spec_hash": outcome_spec.content_hash(),
                    "baseline_success_rate": baseline.success_rate,
                    "uses_outcome_spec": True,
                },
                groups=groups,
                diagnostics=diag,
                observations=obs,
            )

        matured = cohort[group_key.notna() & cohort[col].notna()].copy()
        matured["_group"] = group_key[group_key.notna() & cohort[col].notna()]
        if matured.empty:
            return _base_result(
                self,
                inputs=inputs,
                research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0,
                metrics={},
                diagnostics=diag,
            )

        groups: Dict[str, Any] = {}
        for g, grp in matured.groupby("_group", sort=True):
            rets = pd.to_numeric(grp[col], errors="coerce").dropna()
            groups[str(g)] = {
                "n": int(len(grp)),
                "median": float(rets.median()) if len(rets) else None,
                "mean": float(rets.mean()) if len(rets) else None,
                "std": float(rets.std()) if len(rets) > 1 else None,
            }

        medians = [v["median"] for v in groups.values() if v["median"] is not None]
        obs: List[StructuredResearchObservation] = []
        spread: Optional[float] = None
        if len(groups) < 2:
            status = ToolStatus.NO_VARIATION
            obs.append(_obs(OBS_NO_VARIATION, {"group_count": len(groups)}))
        else:
            status = ToolStatus.OK
            spread = max(medians) - min(medians) if medians else 0.0
            if spread < 0.01:
                obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"median_spread": spread}))
            else:
                obs.append(
                    _obs(OBS_TRAJECTORY_GROUP_DIFFERENCE, {"median_spread": spread, "groups": len(groups)})
                )

        return _base_result(
            self,
            inputs=inputs,
            research_scope=research_scope,
            data_cutoff_date=data_cutoff_date,
            status=status,
            sample_size=len(matured),
            metrics={"horizon": horizon, "group_count": len(groups), "median_spread": spread},
            groups=groups,
            diagnostics=diag,
            observations=obs,
        )


class DateDecompositionTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="date_decomposition",
        tool_version="v1",
        description="Measure time distribution and date concentration of cohort outcomes.",
        input_schema={"horizon": "T3|T5|T10"},
        output_schema={"metrics": "dict", "groups": "per-date stats"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        col = _horizon_col(horizon)
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        matured = cohort[cohort[col].notna()]
        if len(matured) < 1:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0, metrics={}, diagnostics=diag,
            )

        conc = compute_concentration_diagnostics(matured, horizon=horizon)
        per_date: Dict[str, Any] = {}
        for d, grp in matured.groupby("trade_date"):
            rets = pd.to_numeric(grp[col], errors="coerce").dropna()
            per_date[str(d)] = {"n": int(len(grp)), "median": float(rets.median()) if len(rets) else None}

        obs = []
        if conc["largest_date_share"] is not None and conc["largest_date_share"] >= DATE_CONCENTRATION_SEVERE:
            obs.append(_obs(OBS_DATE_CONCENTRATED, {"largest_date_share": conc["largest_date_share"]}, "HIGH"))
        elif conc["unique_t0_dates"] is not None and conc["unique_t0_dates"] >= MIN_UNIQUE_DATES_FOR_STABILITY:
            obs.append(_obs(OBS_DATE_BROAD, {"unique_t0_dates": conc["unique_t0_dates"]}))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK, sample_size=len(matured),
            metrics={**conc, "horizon": horizon},
            groups={"by_date": per_date}, diagnostics=diag, observations=obs,
        )


class SymbolDecompositionTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="symbol_decomposition",
        tool_version="v1",
        description="Measure symbol distribution and concentration of cohort outcomes.",
        input_schema={"horizon": "T3|T5|T10"},
        output_schema={"metrics": "dict", "groups": "per-symbol stats"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        col = _horizon_col(horizon)
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        matured = cohort[cohort[col].notna()]
        if len(matured) < 1:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0, metrics={}, diagnostics=diag,
            )

        conc = compute_concentration_diagnostics(matured, horizon=horizon)
        per_sym: Dict[str, Any] = {}
        for sym, grp in matured.groupby("symbol"):
            rets = pd.to_numeric(grp[col], errors="coerce").dropna()
            per_sym[str(sym)] = {"n": int(len(grp)), "median": float(rets.median()) if len(rets) else None}

        obs = []
        if conc["largest_symbol_share"] is not None and conc["largest_symbol_share"] >= SYMBOL_CONCENTRATION_SEVERE:
            obs.append(_obs(OBS_SYMBOL_CONCENTRATED, {"largest_symbol_share": conc["largest_symbol_share"]}, "HIGH"))
        elif conc["unique_symbols"] is not None and conc["unique_symbols"] >= MIN_UNIQUE_SYMBOLS_FOR_STABILITY:
            obs.append(_obs(OBS_SYMBOL_BROAD, {"unique_symbols": conc["unique_symbols"]}))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK, sample_size=len(matured),
            metrics={**conc, "horizon": horizon},
            groups={"by_symbol": per_sym}, diagnostics=diag, observations=obs,
        )


class EpisodeDecompositionTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="episode_decomposition",
        tool_version="v1",
        description="Episode-level replication diagnostics for a cohort.",
        input_schema={"horizon": "T3|T5|T10"},
        output_schema={"metrics": "dict"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        if cohort.empty:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0, metrics={}, diagnostics=diag,
            )

        filtered_panel, _ = apply_research_cutoff(panel, data_cutoff_date)
        episodes = segment_market_episodes(filtered_panel)
        ep_val = compute_episode_validation(cohort, episodes, best_horizon=horizon)
        obs = []
        consistency = ep_val.get("episode_consistency", "")
        if consistency in ("INSUFFICIENT_EPISODES", "INSUFFICIENT"):
            obs.append(_obs(OBS_EPISODE_INSUFFICIENT, ep_val))
            status = ToolStatus.INSUFFICIENT_DATA
        elif consistency in ("INCONSISTENT", "MIXED"):
            obs.append(_obs(OBS_EPISODE_HETEROGENEOUS, ep_val))
            status = ToolStatus.OK
        else:
            obs.append(_obs(OBS_EPISODE_CONSISTENT, ep_val))
            status = ToolStatus.OK

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=status, sample_size=len(cohort), metrics=ep_val, diagnostics=diag,
            observations=obs,
        )


class MarketConditioningTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="market_conditioning",
        tool_version="v1",
        description="Compare cohort outcomes across explicitly requested Market states/transitions.",
        input_schema={
            "horizon": "T3|T5|T10",
            "partition_by": "research_market_state|research_market_transition",
            "states_or_transitions": "optional explicit list; default=all observed in cohort",
        },
        output_schema={"groups": "dict"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        col = _horizon_col(horizon)
        partition_by = str(inputs.get("partition_by", "research_market_state"))
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        if cohort.empty or partition_by not in cohort.columns:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INSUFFICIENT_DATA if cohort.empty else ToolStatus.INVALID_INPUT,
                sample_size=len(cohort), metrics={}, diagnostics=diag,
            )

        requested = inputs.get("states_or_transitions")
        matured = cohort[cohort[col].notna()].copy()
        groups: Dict[str, Any] = {}
        keys = sorted(matured[partition_by].dropna().unique()) if not requested else list(requested)
        for key in keys:
            grp = matured[matured[partition_by].astype(str) == str(key)]
            rets = pd.to_numeric(grp[col], errors="coerce").dropna()
            groups[str(key)] = {
                "n": int(len(grp)),
                "median": float(rets.median()) if len(rets) else None,
                "mean": float(rets.mean()) if len(rets) else None,
            }

        medians = [g["median"] for g in groups.values() if g["median"] is not None and g["n"] > 0]
        obs = []
        if len(medians) >= 2 and (max(medians) - min(medians)) >= 0.5:
            obs.append(_obs(OBS_MARKET_HETEROGENEOUS, {"median_range": max(medians) - min(medians)}))
        elif len(medians) >= 2:
            obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"median_range": max(medians) - min(medians)}))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK, sample_size=len(matured),
            metrics={"horizon": horizon, "partition_by": partition_by, "group_count": len(groups)},
            groups=groups, diagnostics=diag, observations=obs,
        )


class HorizonComparisonTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="horizon_comparison",
        tool_version="v1",
        description="Compare the same cohort across requested T3/T5/T10 horizons.",
        input_schema={"horizons": "optional list, default all"},
        output_schema={"groups": "per-horizon profiles"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizons = list(inputs.get("horizons") or HORIZONS)
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizons=horizons
        )
        if cohort.empty:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0, metrics={}, diagnostics=diag,
            )

        groups: Dict[str, Any] = {}
        medians: List[float] = []
        for h in horizons:
            col = _horizon_col(h)
            rets = pd.to_numeric(cohort[col], errors="coerce").dropna()
            prof = compute_horizon_profile(rets, h)
            groups[h] = prof.to_dict("cohort")
            if prof.median_return is not None:
                medians.append(prof.median_return)

        obs = []
        if len(medians) >= 2 and (max(medians) - min(medians)) >= 1.0:
            obs.append(_obs(OBS_HORIZON_HETEROGENEOUS, {"median_spread": max(medians) - min(medians)}))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK, sample_size=len(cohort),
            metrics={"horizons_requested": horizons, "median_spread": (max(medians) - min(medians)) if medians else None},
            groups=groups, diagnostics=diag, observations=obs,
        )


class SensitivityAnalysisTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="sensitivity_analysis",
        tool_version="v1",
        description="Leave-one-out and extreme-winner sensitivity for a cohort.",
        input_schema={
            "horizon": "T3|T5|T10",
            "tests": "list of leave_one_date|leave_one_symbol|remove_largest_positive",
        },
        output_schema={"metrics": "dict", "groups": "per-test results"},
        minimum_data_requirements={"min_rows": 3},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        col = _horizon_col(horizon)
        tests = list(inputs.get("tests") or ["leave_one_date", "leave_one_symbol", "remove_largest_positive"])
        cohort, diag = resolve_cohort(
            panel, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        matured = cohort[cohort[col].notna()].copy()
        if len(matured) < 3:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=len(matured), metrics={}, diagnostics=diag,
            )

        base_med = float(pd.to_numeric(matured[col], errors="coerce").median())
        results: Dict[str, Any] = {}
        fragile = False

        if "leave_one_date" in tests:
            date_medians = []
            for d in matured["trade_date"].unique():
                sub = matured[matured["trade_date"] != d]
                if len(sub) >= 1:
                    date_medians.append(float(pd.to_numeric(sub[col], errors="coerce").median()))
            survives = all(m > 0 for m in date_medians) if date_medians else None
            results["leave_one_date"] = {"survives_positive_median": survives, "medians": date_medians}
            if survives is False:
                fragile = True

        if "leave_one_symbol" in tests:
            sym_medians = []
            for sym in matured["symbol"].unique():
                sub = matured[matured["symbol"] != sym]
                if len(sub) >= 1:
                    sym_medians.append(float(pd.to_numeric(sub[col], errors="coerce").median()))
            survives = all(m > 0 for m in sym_medians) if sym_medians else None
            results["leave_one_symbol"] = {"survives_positive_median": survives, "medians": sym_medians}
            if survives is False:
                fragile = True

        if "remove_largest_positive" in tests:
            rets = pd.to_numeric(matured[col], errors="coerce")
            trimmed = matured.drop(index=rets.idxmax())
            trim_med = float(pd.to_numeric(trimmed[col], errors="coerce").median()) if len(trimmed) else None
            survives = trim_med is not None and trim_med > 0
            results["remove_largest_positive"] = {
                "baseline_median": base_med,
                "trimmed_median": trim_med,
                "survives_positive_median": survives,
            }
            if survives is False:
                fragile = True

        obs = [
            _obs(
                OBS_EXTREME_WINNER_SENSITIVE if fragile else OBS_EXTREME_WINNER_ROBUST,
                {"fragile": fragile},
                "HIGH" if fragile else "LOW",
            )
        ]
        if fragile:
            obs.append(_obs(OBS_SENSITIVITY_FRAGILE, results))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK, sample_size=len(matured),
            metrics={"baseline_median": base_med, "fragile": fragile, "horizon": horizon},
            groups=results, diagnostics=diag, observations=obs,
        )


class NeighborhoodStabilityTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="neighborhood_stability",
        tool_version="v1",
        description="Evaluate supplied numeric condition against neighboring buckets.",
        input_schema={
            "horizon": "T3|T5|T10",
            "condition_clauses": "list of clause dicts (explicit, not optimized)",
        },
        output_schema={"metrics": "stability classification"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.MATURED_OUTCOME.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        filtered_panel, diag = apply_research_cutoff(panel, data_cutoff_date, horizon=horizon)
        clauses = _parse_clauses({"condition_clauses": inputs.get("condition_clauses") or research_scope.get("condition_clauses") or []})
        if not clauses:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INVALID_INPUT,
                sample_size=0, metrics={}, diagnostics=diag,
                limitations=["condition_clauses_required"],
            )

        fake_row = pd.Series(
            {
                "market_transition": research_scope.get("market_transition", ""),
                "market_state": research_scope.get("market_state", ""),
                "best_horizon": horizon,
            }
        )
        nb = test_neighborhood_stability(filtered_panel, fake_row, clauses, horizon)
        stability = nb.get("stability", "UNKNOWN")
        obs = []
        if stability == "ISOLATED_BUCKET":
            obs.append(_obs(OBS_NEIGHBORHOOD_UNSTABLE, nb, "HIGH"))
        elif stability == "BROAD_STABLE":
            obs.append(_obs(OBS_NEIGHBORHOOD_STABLE, nb))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK,
            sample_size=int(nb.get("original_n") or 0),
            metrics=nb, diagnostics=diag, observations=obs,
        )


class TrajectoryPartitionCompareTool(ResearchTool):
    metadata = ToolMetadata(
        tool_name="trajectory_partition_compare",
        tool_version="v1",
        description="Partition cohort by an explicit T0-safe temporal feature using caller bins.",
        input_schema={
            "temporal_feature": "str column from feature matrix",
            "bins": "explicit numeric bins",
            "horizon": "T3|T5|T10",
            "lag_windows": "optional, default feature_builder defaults",
        },
        output_schema={"groups": "dict"},
        minimum_data_requirements={"min_rows": 1},
        leakage_classification=LeakageClass.T0_SAFE.value,
    )

    def execute(self, panel, *, inputs, research_scope, data_cutoff_date):
        horizon = str(inputs.get("horizon", "T5"))
        feature = str(inputs["temporal_feature"])
        bins = inputs.get("bins") or []
        col = _horizon_col(horizon)

        filtered, cutoff_diag = apply_research_cutoff(panel, data_cutoff_date, horizon=horizon)
        if filtered.empty:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INSUFFICIENT_DATA,
                sample_size=0, metrics={}, diagnostics={"cutoff": cutoff_diag},
            )

        matrix = build_t0_feature_matrix(filtered)
        if feature not in matrix.columns:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date, status=ToolStatus.INVALID_INPUT,
                sample_size=0, metrics={}, diagnostics={"cutoff": cutoff_diag},
                limitations=[f"missing_temporal_feature:{feature}"],
            )

        merged = filtered.merge(
            matrix[["trade_date", "symbol", feature]],
            on=["trade_date", "symbol"],
            how="left",
            suffixes=("", "_feat"),
        )
        cohort, scope_diag = resolve_cohort(
            merged, research_scope, data_cutoff_date=data_cutoff_date, horizon=horizon
        )
        if cohort.empty or not bins:
            return _base_result(
                self, inputs=inputs, research_scope=research_scope,
                data_cutoff_date=data_cutoff_date,
                status=ToolStatus.INVALID_INPUT if not bins else ToolStatus.INSUFFICIENT_DATA,
                sample_size=len(cohort), metrics={}, diagnostics={"cutoff": cutoff_diag, "scope": scope_diag},
            )

        group_key = _assign_numeric_bins(cohort[feature], bins)
        matured = cohort[group_key.notna() & cohort[col].notna()].copy()
        matured["_group"] = group_key[group_key.notna() & cohort[col].notna()]
        groups: Dict[str, Any] = {}
        for g, grp in matured.groupby("_group", sort=True):
            rets = pd.to_numeric(grp[col], errors="coerce").dropna()
            groups[str(g)] = {"n": int(len(grp)), "median": float(rets.median()) if len(rets) else None}

        medians = [v["median"] for v in groups.values() if v["median"] is not None]
        spread = (max(medians) - min(medians)) if medians else None
        obs = []
        if spread is not None and spread >= 0.01:
            obs.append(_obs(OBS_TRAJECTORY_GROUP_DIFFERENCE, {"feature": feature, "spread": spread}))
        else:
            obs.append(_obs(OBS_NO_CLEAR_DIFFERENCE, {"feature": feature}))

        return _base_result(
            self, inputs=inputs, research_scope=research_scope, data_cutoff_date=data_cutoff_date,
            status=ToolStatus.OK if groups else ToolStatus.NO_VARIATION,
            sample_size=len(matured),
            metrics={"temporal_feature": feature, "horizon": horizon, "median_spread": spread},
            groups=groups,
            diagnostics={"cutoff": cutoff_diag, "scope": scope_diag},
            observations=obs,
        )


class ToolRegistry:
    """Deterministic registry of research tools."""

    def __init__(self) -> None:
        self._tools: Dict[Tuple[str, str], ResearchTool] = {}

    def register(self, tool: ResearchTool) -> None:
        key = (tool.metadata.tool_name, tool.metadata.tool_version)
        if key in self._tools:
            raise ValueError(f"Conflicting duplicate registration: {key}")
        self._tools[key] = tool

    def get(self, tool_name: str, tool_version: str = "v1") -> ResearchTool:
        key = (tool_name, tool_version)
        if key not in self._tools:
            raise KeyError(f"Unknown research tool: {tool_name}@{tool_version}")
        return self._tools[key]

    def list_tools(self) -> List[ToolMetadata]:
        return sorted(
            (t.metadata for t in self._tools.values()),
            key=lambda m: (m.tool_name, m.tool_version),
        )

    def metadata_dicts(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self.list_tools()]


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        PartitionGroupCompareTool(),
        DateDecompositionTool(),
        SymbolDecompositionTool(),
        EpisodeDecompositionTool(),
        MarketConditioningTool(),
        HorizonComparisonTool(),
        SensitivityAnalysisTool(),
        NeighborhoodStabilityTool(),
        TrajectoryPartitionCompareTool(),
    ):
        registry.register(tool)
    from modules.edge_research.research_adaptive_tools import build_adaptive_tool_registry

    for tool in build_adaptive_tool_registry():
        registry.register(tool)
    return registry


class ResearchToolExecutionError(ValueError):
    """Raised when experiment execution preconditions fail."""


def execute_research_experiment(
    graph: ResearchGraph,
    experiment_node_id: str,
    tool_registry: ToolRegistry,
    research_panel: pd.DataFrame,
) -> ToolResult:
    """
    Bridge: run tool for an EXPERIMENT node and attach immutable result to graph.

    Does NOT spawn next questions or select tools.
    """
    node = graph.get_node(experiment_node_id)
    if node.node_type != NodeType.EXPERIMENT:
        raise ResearchToolExecutionError("Node must be EXPERIMENT type")
    if node.experiment_result is not None and node.experiment_result.finalized:
        raise ResearchToolExecutionError(
            f"Experiment {experiment_node_id} already has finalized result"
        )
    if node.experiment_spec is None:
        raise ResearchToolExecutionError("Experiment node missing ExperimentSpec")

    spec = node.experiment_spec
    if spec.data_cutoff_date != graph.session.data_cutoff_date:
        raise ResearchToolExecutionError(
            "ExperimentSpec data_cutoff_date must match session data_cutoff_date"
        )

    content_hash = compute_experiment_content_hash(spec)
    if node.experiment_content_hash and node.experiment_content_hash != content_hash:
        raise ResearchToolExecutionError("Experiment content hash mismatch on node")

    existing = graph.find_experiment_by_content_hash(content_hash)
    if existing and existing != experiment_node_id:
        finalized = graph.get_node(existing).experiment_result
        if finalized is not None and finalized.finalized:
            raise ResearchToolExecutionError(
                f"Duplicate experiment already executed at node {existing}"
            )

    tool = tool_registry.get(spec.tool_name, spec.tool_version)
    panel_copy = research_panel.copy()
    result = tool.execute(
        panel_copy,
        inputs=dict(spec.inputs),
        research_scope=dict(spec.research_scope),
        data_cutoff_date=spec.data_cutoff_date,
    )

    graph.attach_experiment_result(
        experiment_node_id,
        metrics=result.metrics_for_experiment(),
        observations=list(result.structured_observations),
        completed_at=None,
    )
    exp_node = graph.get_node(experiment_node_id)
    if exp_node.experiment_result and exp_node.experiment_result.result_hash != compute_result_hash(
        result.metrics_for_experiment()
    ):
        pass  # hash computed inside attach from metrics

    return result
