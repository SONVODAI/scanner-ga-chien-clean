"""
Capability Awareness / Research Laboratory Map (Phase 3H).

Neutral, auditable inventory of what Edge Research can legally access and operate on.
Discovery → describe → expose → audit only — no allocation, prioritization, or hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from modules.edge_research.adapters import (
    BUY_ELITE_HISTORY_PATH,
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    OUTCOMES_PATH,
    PATTERN_HISTORY_PATH,
    REPO_ROOT,
    earning_learning_digests,
    file_digest,
)
from modules.edge_research.feature_registry import (
    CANONICAL_STOCK_HISTORY_SOURCE,
    LEGACY_SEARCH_FEATURES,
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
)
from modules.edge_research.research_feature_eligibility import (
    FIELD_AVAILABILITY_HORIZON,
    FeatureRole,
    assess_feature_eligibility,
    classify_feature_role,
    field_availability_horizon,
    list_eligible_explanatory_features,
)
from modules.edge_research.research_frame import FrameTransformationType
from modules.edge_research.research_grammar import (
    ALLOWED_OUTCOME_FIELDS,
    ALLOWED_POPULATION_FIELDS,
    GRAMMAR_VERSION,
)
from modules.edge_research.research_panel_preflight import (
    PANEL_PREFLIGHT_VERSION,
    PanelPreflightReport,
    build_panel_preflight,
)
from modules.edge_research.research_search_accounting import SEARCH_ACCOUNTING_VERSION
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import TOOLBOX_VERSION, ToolRegistry, build_default_tool_registry

CAPABILITY_REGISTRY_VERSION = "research_capability_registry_v1"
LABORATORY_MAP_VERSION = "research_laboratory_map_v1"

# Research panel build path — wired in adapters.build_research_panel.
_RESEARCH_PANEL_SOURCES: Tuple[Tuple[str, Path, bool], ...] = (
    ("pattern_lifecycle", EARNING_LEARNING_DIR / "pattern_lifecycle.csv", True),
    ("market_t0_snapshot", MARKET_T0_SNAPSHOT_PATH, True),
    ("pattern_history", PATTERN_HISTORY_PATH, True),
    ("buy_elite_history", BUY_ELITE_HISTORY_PATH, True),
    ("outcomes_csv", OUTCOMES_PATH, True),
)

# System artifacts discovered in repository but NOT wired into research panel/tools.
_DISCOVERED_NON_RESEARCH_SOURCES: Tuple[Tuple[str, Path, str], ...] = (
    (
        "market_aware_sweetspot_observer_ledger",
        EARNING_LEARNING_DIR / "market_aware_sweetspot_observer_ledger.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "trajectory_knowledge",
        EARNING_LEARNING_DIR / "trajectory_knowledge.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "regime_recall_index",
        EARNING_LEARNING_DIR / "regime_recall_index.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "pattern_knowledge",
        EARNING_LEARNING_DIR / "pattern_knowledge.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "continuation_knowledge",
        EARNING_LEARNING_DIR / "continuation_knowledge.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "decision_archive",
        EARNING_LEARNING_DIR / "decision_archive.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "market_daily_t0",
        EARNING_LEARNING_DIR / "market_daily_t0.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "pattern_snapshot",
        EARNING_LEARNING_DIR / "pattern_snapshot.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "verified_decisions",
        EARNING_LEARNING_DIR / "verified_decisions.csv",
        "ALTERNATE_PANEL_SOURCE_NOT_DEFAULT",
    ),
    (
        "observations",
        EARNING_LEARNING_DIR / "observations.csv",
        "ALTERNATE_PANEL_SOURCE_NOT_DEFAULT",
    ),
    (
        "t0_observation_freeze",
        EARNING_LEARNING_DIR / "t0_observation_freeze.csv",
        "NOT_WIRED_TO_RESEARCH_PANEL_OR_TOOLS",
    ),
    (
        "intraday_camera_memory",
        REPO_ROOT / "intraday_memory",
        "PRODUCTION_CAMERA_PATH_NOT_RESEARCH_ACCESSIBLE",
    ),
)

_TOOL_OPERATION_MAP: Dict[str, Tuple[str, ...]] = {
    "partition_group_compare": ("partition",),
    "adaptive_partition_compare": ("partition", "threshold"),
    "threshold_exploration": ("threshold",),
    "threshold_neighborhood": ("threshold", "neighborhood"),
    "categorical_adaptive_compare": ("partition",),
    "interaction_partition": ("interaction", "partition"),
    "date_decomposition": ("decomposition",),
    "symbol_decomposition": ("decomposition",),
    "episode_decomposition": ("decomposition",),
    "market_conditioning": ("decomposition", "context"),
    "horizon_comparison": ("outcome_comparison",),
    "sensitivity_analysis": ("falsification", "robustness"),
    "neighborhood_stability": ("falsification", "neighborhood", "robustness"),
    "trajectory_partition_compare": ("decomposition", "partition"),
}

_FORBIDDEN_AWARENESS_TOKENS: FrozenSet[str] = frozenset(
    {
        "blind_benchmark",
        "bb01",
        "bb02",
        "bb03",
        "bb04",
        "bb05",
        "bb06",
        "bb07",
        "bb08",
        "predictive",
        "should use",
        "recommended",
        "buy signal",
        "sell signal",
        "edge active",
    }
)


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    AVAILABLE_WITH_CONSTRAINTS = "AVAILABLE_WITH_CONSTRAINTS"
    NOT_RESEARCH_ACCESSIBLE = "NOT_RESEARCH_ACCESSIBLE"
    TEMPORALLY_ILLEGAL = "TEMPORALLY_ILLEGAL"
    MISSING_FROM_PANEL = "MISSING_FROM_PANEL"
    UNAVAILABLE = "UNAVAILABLE"


class CapabilityCategory(str, Enum):
    DATA_SOURCE = "data_source"
    FIELD = "field"
    CATEGORICAL_DIMENSION = "categorical_dimension"
    OUTCOME = "outcome"
    INFORMATION_HORIZON = "information_horizon"
    RESEARCH_TOOL = "research_tool"
    TRANSFORMATION = "transformation"
    PARTITION_CAPABILITY = "partition_capability"
    THRESHOLD_CAPABILITY = "threshold_capability"
    NEIGHBORHOOD_CAPABILITY = "neighborhood_capability"
    DECOMPOSITION_CAPABILITY = "decomposition_capability"
    INTERACTION_CAPABILITY = "interaction_capability"
    FALSIFICATION_CAPABILITY = "falsification_capability"
    REFRAMING_CAPABILITY = "reframing_capability"
    POPULATION_OUTCOME_TRANSFORMATION = "population_outcome_transformation"
    SEARCH_ACCOUNTING_CAPABILITY = "search_accounting_capability"


@dataclass(frozen=True)
class CapabilityEntry:
    capability_id: str
    category: str
    name: str
    status: str
    blocker: str = ""
    constraints: Tuple[str, ...] = field(default_factory=tuple)
    source_provenance: str = ""
    availability_horizon: Optional[int] = None
    legal_at_horizons: Tuple[int, ...] = field(default_factory=tuple)
    panel_included: bool = False
    exists_in_system: bool = True
    currently_research_accessible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "blocker": self.blocker,
            "constraints": list(self.constraints),
            "source_provenance": self.source_provenance,
            "availability_horizon": self.availability_horizon,
            "legal_at_horizons": list(self.legal_at_horizons),
            "panel_included": self.panel_included,
            "exists_in_system": self.exists_in_system,
            "currently_research_accessible": self.currently_research_accessible,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CapabilityEntry":
        return cls(
            capability_id=str(payload["capability_id"]),
            category=str(payload["category"]),
            name=str(payload["name"]),
            status=str(payload["status"]),
            blocker=str(payload.get("blocker") or ""),
            constraints=tuple(payload.get("constraints") or ()),
            source_provenance=str(payload.get("source_provenance") or ""),
            availability_horizon=payload.get("availability_horizon"),
            legal_at_horizons=tuple(payload.get("legal_at_horizons") or ()),
            panel_included=bool(payload.get("panel_included", False)),
            exists_in_system=bool(payload.get("exists_in_system", True)),
            currently_research_accessible=bool(payload.get("currently_research_accessible", False)),
            metadata=dict(payload.get("metadata") or {}),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _horizons_for_field(field_name: str) -> Tuple[int, ...]:
    avail = field_availability_horizon(field_name)
    return tuple(h for h in (0, 3, 5, 10) if h >= avail)


def _field_status(
    field_name: str,
    panel_columns: Set[str],
    observation_horizon: int,
) -> Tuple[str, str, Tuple[str, ...]]:
    """Return (status, blocker, constraints) for a field at observation horizon."""
    on_panel = field_name in panel_columns
    role = classify_feature_role(field_name)
    avail = field_availability_horizon(field_name)
    assessment = assess_feature_eligibility(field_name, observation_horizon=observation_horizon)

    if role == FeatureRole.PROHIBITED.value and field_name not in ALLOWED_OUTCOME_FIELDS:
        return CapabilityStatus.UNAVAILABLE.value, "PROHIBITED_FIELD", ("prohibited",)

    if field_name in ALLOWED_OUTCOME_FIELDS:
        if not on_panel:
            return CapabilityStatus.MISSING_FROM_PANEL.value, "FIELD_ABSENT_FROM_PANEL", ()
        if not assessment.eligible_at_observation:
            return (
                CapabilityStatus.TEMPORALLY_ILLEGAL.value,
                f"REQUIRES_HORIZON_{avail}",
                (f"available_from_session_{avail}",),
            )
        if avail > 0:
            return (
                CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
                "",
                (f"outcome_matured_from_session_{avail}",),
            )
        return CapabilityStatus.AVAILABLE.value, "", ()

    if not on_panel:
        if field_name in set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_CATEGORICAL_LEVEL_FEATURES) | set(
            STOCK_RANK_LEVEL_FEATURES
        ):
            return CapabilityStatus.MISSING_FROM_PANEL.value, "REGISTRY_FIELD_ABSENT_FROM_PANEL", ()
        return CapabilityStatus.UNAVAILABLE.value, "UNKNOWN_FIELD", ()

    if not assessment.eligible_at_observation:
        return (
            CapabilityStatus.TEMPORALLY_ILLEGAL.value,
            f"REQUIRES_HORIZON_{avail}",
            (f"available_from_session_{avail}",),
        )

    constraints: List[str] = []
    if field_name in LEGACY_SEARCH_FEATURES:
        constraints.append("legacy_discovery_eligible")
    if role == FeatureRole.CONTEXT.value:
        constraints.append("context_dimension")
    status = CapabilityStatus.AVAILABLE.value
    if constraints:
        status = CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value
    return status, "", tuple(constraints)


def _cap_id(category: str, name: str) -> str:
    return f"{category}:{name}"


def discover_system_data_sources() -> List[CapabilityEntry]:
    """Audit repository data sources — exists vs research-accessible."""
    entries: List[CapabilityEntry] = []
    for source_id, path, research_wired in _RESEARCH_PANEL_SOURCES:
        exists = path.exists()
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(CapabilityCategory.DATA_SOURCE.value, source_id),
                category=CapabilityCategory.DATA_SOURCE.value,
                name=source_id,
                status=CapabilityStatus.AVAILABLE.value
                if exists and research_wired
                else CapabilityStatus.UNAVAILABLE.value
                if not exists
                else CapabilityStatus.NOT_RESEARCH_ACCESSIBLE.value,
                blocker="" if exists else "FILE_NOT_FOUND",
                source_provenance=str(path.relative_to(REPO_ROOT))
                if str(path).startswith(str(REPO_ROOT))
                else str(path),
                panel_included=research_wired,
                exists_in_system=exists,
                currently_research_accessible=exists and research_wired,
                metadata={
                    "digest_sha256": file_digest(path),
                    "research_panel_wired": research_wired,
                    "canonical_stock_source": source_id == "pattern_lifecycle",
                },
            )
        )

    for source_id, path, blocker in _DISCOVERED_NON_RESEARCH_SOURCES:
        exists = path.exists()
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(CapabilityCategory.DATA_SOURCE.value, source_id),
                category=CapabilityCategory.DATA_SOURCE.value,
                name=source_id,
                status=CapabilityStatus.NOT_RESEARCH_ACCESSIBLE.value
                if exists
                else CapabilityStatus.UNAVAILABLE.value,
                blocker=blocker if exists else "PATH_NOT_FOUND",
                source_provenance=str(path.relative_to(REPO_ROOT))
                if str(path).startswith(str(REPO_ROOT))
                else str(path),
                panel_included=False,
                exists_in_system=exists,
                currently_research_accessible=False,
                metadata={"digest_sha256": file_digest(path) if path.is_file() else None},
            )
        )
    return entries


def _build_field_capabilities(
    panel: pd.DataFrame,
    observation_horizon: int,
) -> List[CapabilityEntry]:
    panel_cols = set(panel.columns)
    entries: List[CapabilityEntry] = []

    all_known_fields = sorted(
        set(FIELD_AVAILABILITY_HORIZON.keys())
        | set(STOCK_NUMERIC_LEVEL_FEATURES)
        | set(STOCK_CATEGORICAL_LEVEL_FEATURES)
        | set(STOCK_RANK_LEVEL_FEATURES)
        | set(ALLOWED_OUTCOME_FIELDS)
        | set(ALLOWED_POPULATION_FIELDS)
    )

    for field_name in all_known_fields:
        role = classify_feature_role(field_name)
        status, blocker, constraints = _field_status(field_name, panel_cols, observation_horizon)
        category = CapabilityCategory.FIELD.value
        if role in (FeatureRole.CATEGORICAL.value, FeatureRole.CONTEXT.value):
            category = CapabilityCategory.CATEGORICAL_DIMENSION.value
        elif field_name in ALLOWED_OUTCOME_FIELDS:
            category = CapabilityCategory.OUTCOME.value

        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(category, field_name),
                category=category,
                name=field_name,
                status=status,
                blocker=blocker,
                constraints=constraints,
                source_provenance=CANONICAL_STOCK_HISTORY_SOURCE
                if field_name in STOCK_NUMERIC_LEVEL_FEATURES
                else "research_panel",
                availability_horizon=field_availability_horizon(field_name),
                legal_at_horizons=_horizons_for_field(field_name),
                panel_included=field_name in panel_cols,
                exists_in_system=True,
                currently_research_accessible=status
                in (
                    CapabilityStatus.AVAILABLE.value,
                    CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
                ),
                metadata={"role": role},
            )
        )
    return entries


def _build_horizon_capabilities() -> List[CapabilityEntry]:
    entries: List[CapabilityEntry] = []
    for h in (0, 3, 5, 10):
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(CapabilityCategory.INFORMATION_HORIZON.value, f"H{h}"),
                category=CapabilityCategory.INFORMATION_HORIZON.value,
                name=f"observation_horizon_{h}",
                status=CapabilityStatus.AVAILABLE.value,
                source_provenance="feature_eligibility_v1",
                availability_horizon=h,
                legal_at_horizons=(h,),
                exists_in_system=True,
                currently_research_accessible=True,
                metadata={"session_offset": h},
            )
        )
    return entries


def _build_tool_capabilities(tool_registry: ToolRegistry) -> List[CapabilityEntry]:
    entries: List[CapabilityEntry] = []
    for meta in tool_registry.list_tools():
        ops = _TOOL_OPERATION_MAP.get(meta.tool_name, ())
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(
                    CapabilityCategory.RESEARCH_TOOL.value,
                    f"{meta.tool_name}@{meta.tool_version}",
                ),
                category=CapabilityCategory.RESEARCH_TOOL.value,
                name=meta.tool_name,
                status=CapabilityStatus.AVAILABLE.value,
                source_provenance=TOOLBOX_VERSION,
                exists_in_system=True,
                currently_research_accessible=True,
                metadata={
                    "tool_version": meta.tool_version,
                    "description": meta.description,
                    "input_schema": meta.input_schema,
                    "leakage_classification": meta.leakage_classification,
                    "operation_classes": list(ops),
                    "minimum_data_requirements": meta.minimum_data_requirements,
                },
            )
        )
        for op in ops:
            cat_map = {
                "partition": CapabilityCategory.PARTITION_CAPABILITY,
                "threshold": CapabilityCategory.THRESHOLD_CAPABILITY,
                "neighborhood": CapabilityCategory.NEIGHBORHOOD_CAPABILITY,
                "decomposition": CapabilityCategory.DECOMPOSITION_CAPABILITY,
                "interaction": CapabilityCategory.INTERACTION_CAPABILITY,
                "falsification": CapabilityCategory.FALSIFICATION_CAPABILITY,
                "robustness": CapabilityCategory.FALSIFICATION_CAPABILITY,
                "context": CapabilityCategory.CATEGORICAL_DIMENSION,
                "outcome_comparison": CapabilityCategory.OUTCOME,
            }
            cat = cat_map.get(op, CapabilityCategory.RESEARCH_TOOL)
            entries.append(
                CapabilityEntry(
                    capability_id=_cap_id(cat.value, f"{meta.tool_name}:{op}"),
                    category=cat.value,
                    name=f"{meta.tool_name}_{op}",
                    status=CapabilityStatus.AVAILABLE.value,
                    blocker="",
                    source_provenance=f"tool:{meta.tool_name}",
                    exists_in_system=True,
                    currently_research_accessible=True,
                    metadata={"parent_tool": meta.tool_name, "operation": op},
                )
            )
    return entries


def _build_reframing_capabilities() -> List[CapabilityEntry]:
    entries: List[CapabilityEntry] = []
    for tf in FrameTransformationType:
        if tf == FrameTransformationType.INITIAL:
            continue
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(CapabilityCategory.REFRAMING_CAPABILITY.value, tf.value),
                category=CapabilityCategory.REFRAMING_CAPABILITY.value,
                name=tf.value,
                status=CapabilityStatus.AVAILABLE.value,
                source_provenance="research_frame_v1",
                exists_in_system=True,
                currently_research_accessible=True,
                metadata={"transformation_type": tf.value},
            )
        )
    for kind in ("compare", "persist", "continuation", "reversal", "filter", "refine", "widen", "all"):
        entries.append(
            CapabilityEntry(
                capability_id=_cap_id(
                    CapabilityCategory.POPULATION_OUTCOME_TRANSFORMATION.value,
                    kind,
                ),
                category=CapabilityCategory.POPULATION_OUTCOME_TRANSFORMATION.value,
                name=kind,
                status=CapabilityStatus.AVAILABLE.value,
                source_provenance=GRAMMAR_VERSION,
                exists_in_system=True,
                currently_research_accessible=True,
                metadata={"grammar_kind": kind},
            )
        )
    entries.append(
        CapabilityEntry(
            capability_id=_cap_id(
                CapabilityCategory.SEARCH_ACCOUNTING_CAPABILITY.value,
                "session_ledger",
            ),
            category=CapabilityCategory.SEARCH_ACCOUNTING_CAPABILITY.value,
            name="search_accounting_session_ledger",
            status=CapabilityStatus.AVAILABLE.value,
            source_provenance=SEARCH_ACCOUNTING_VERSION,
            exists_in_system=True,
            currently_research_accessible=True,
            metadata={"records_experiments_and_complexity": True},
        )
    )
    return entries


def build_capability_registry(
    panel: pd.DataFrame,
    tool_registry: Optional[ToolRegistry] = None,
    *,
    observation_horizon: int = 0,
    preflight: Optional[PanelPreflightReport] = None,
) -> "ResearchCapabilityRegistry":
    """
    Machine-readable capability inventory from actual code/data state.

    Does not alter planner, allocator, or scoring behavior.
    """
    registry = tool_registry or build_default_tool_registry()
    pre = preflight or build_panel_preflight(panel)
    capabilities: Dict[str, CapabilityEntry] = {}

    for entry in (
        discover_system_data_sources()
        + _build_field_capabilities(panel, observation_horizon)
        + _build_horizon_capabilities()
        + _build_tool_capabilities(registry)
        + _build_reframing_capabilities()
    ):
        capabilities[entry.capability_id] = entry

    return ResearchCapabilityRegistry(
        built_at=_utc_now(),
        observation_horizon=observation_horizon,
        panel_preflight_version=pre.version,
        capabilities=capabilities,
        audit_trail=[
            {
                "event": "REGISTRY_BUILT",
                "timestamp": _utc_now(),
                "observation_horizon": observation_horizon,
                "capability_count": len(capabilities),
                "panel_row_count": int(len(panel)),
                "panel_column_count": len(pre.panel_columns),
            }
        ],
    )


@dataclass
class ResearchCapabilityRegistry:
    """Session-persistent capability inventory and exercise tracking."""

    version: str = CAPABILITY_REGISTRY_VERSION
    built_at: str = ""
    observation_horizon: int = 0
    panel_preflight_version: str = PANEL_PREFLIGHT_VERSION
    capabilities: Dict[str, CapabilityEntry] = field(default_factory=dict)
    exercised_capability_ids: Set[str] = field(default_factory=set)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "observation_horizon": self.observation_horizon,
            "panel_preflight_version": self.panel_preflight_version,
            "capabilities": {k: v.to_dict() for k, v in sorted(self.capabilities.items())},
            "exercised_capability_ids": sorted(self.exercised_capability_ids),
            "audit_trail": list(self.audit_trail),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchCapabilityRegistry":
        caps = {
            k: CapabilityEntry.from_dict(v)
            for k, v in (payload.get("capabilities") or {}).items()
        }
        return cls(
            version=str(payload.get("version", CAPABILITY_REGISTRY_VERSION)),
            built_at=str(payload.get("built_at", "")),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            panel_preflight_version=str(
                payload.get("panel_preflight_version", PANEL_PREFLIGHT_VERSION)
            ),
            capabilities=caps,
            exercised_capability_ids=set(payload.get("exercised_capability_ids") or ()),
            audit_trail=list(payload.get("audit_trail") or []),
        )

    def laboratory_map(self) -> "ResearchLaboratoryMap":
        return ResearchLaboratoryMap(self)

    def record_exercise(
        self,
        spec: Optional[ExperimentSpec],
        *,
        experiment_node_id: str = "",
        frame_id: str = "",
    ) -> None:
        """Record capabilities exercised by an experiment — audit only."""
        if spec is None:
            return
        exercised: Set[str] = set()
        tool_id = _cap_id(
            CapabilityCategory.RESEARCH_TOOL.value,
            f"{spec.tool_name}@{spec.tool_version}",
        )
        if tool_id in self.capabilities:
            exercised.add(tool_id)

        inputs = dict(spec.inputs or {})
        for key in ("feature_column", "partition_column"):
            feat = inputs.get(key)
            if feat:
                for cat in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value):
                    fid = _cap_id(cat, str(feat))
                    if fid in self.capabilities:
                        exercised.add(fid)

        for op in _TOOL_OPERATION_MAP.get(spec.tool_name, ()):
            oid = _cap_id(
                {
                    "partition": CapabilityCategory.PARTITION_CAPABILITY.value,
                    "threshold": CapabilityCategory.THRESHOLD_CAPABILITY.value,
                    "neighborhood": CapabilityCategory.NEIGHBORHOOD_CAPABILITY.value,
                    "decomposition": CapabilityCategory.DECOMPOSITION_CAPABILITY.value,
                    "interaction": CapabilityCategory.INTERACTION_CAPABILITY.value,
                    "falsification": CapabilityCategory.FALSIFICATION_CAPABILITY.value,
                    "robustness": CapabilityCategory.FALSIFICATION_CAPABILITY.value,
                }.get(op, CapabilityCategory.RESEARCH_TOOL.value),
                f"{spec.tool_name}:{op}",
            )
            if oid in self.capabilities:
                exercised.add(oid)

        if frame_id:
            fid = _cap_id(CapabilityCategory.REFRAMING_CAPABILITY.value, frame_id)
            # frame_id is not transformation type — skip unless matches
            for cap_id, cap in self.capabilities.items():
                if cap.category == CapabilityCategory.REFRAMING_CAPABILITY.value:
                    pass

        self.exercised_capability_ids |= exercised
        self.audit_trail.append(
            {
                "event": "CAPABILITY_EXERCISED",
                "timestamp": _utc_now(),
                "experiment_node_id": experiment_node_id,
                "tool_name": spec.tool_name,
                "capability_ids": sorted(exercised),
            }
        )

    def available_capabilities(self) -> List[CapabilityEntry]:
        return [
            c
            for c in self.capabilities.values()
            if c.status
            in (
                CapabilityStatus.AVAILABLE.value,
                CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
            )
        ]

    def unexplored_capabilities(self) -> List[CapabilityEntry]:
        return [c for c in self.available_capabilities() if c.capability_id not in self.exercised_capability_ids]

    def blocked_capabilities(self) -> List[CapabilityEntry]:
        return [
            c
            for c in self.capabilities.values()
            if c.status
            not in (
                CapabilityStatus.AVAILABLE.value,
                CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
            )
        ]


@dataclass(frozen=True)
class ResearchLaboratoryMap:
    """
    Neutral query surface over capability registry.

    Describes what exists and what is legal — never what to prioritize.
    """

    registry: ResearchCapabilityRegistry

    @property
    def version(self) -> str:
        return LABORATORY_MAP_VERSION

    def legal_fields_at_horizon(self, horizon: int) -> List[Dict[str, Any]]:
        """What information fields can be legally inspected at this horizon?"""
        result: List[Dict[str, Any]] = []
        for cap in self.registry.capabilities.values():
            if cap.category not in (
                CapabilityCategory.FIELD.value,
                CapabilityCategory.CATEGORICAL_DIMENSION.value,
                CapabilityCategory.OUTCOME.value,
            ):
                continue
            assessment = assess_feature_eligibility(cap.name, observation_horizon=horizon)
            if assessment.eligible_at_observation and cap.panel_included:
                result.append(
                    {
                        "field": cap.name,
                        "role": cap.metadata.get("role"),
                        "status": cap.status,
                        "availability_horizon": cap.availability_horizon,
                    }
                )
            elif cap.panel_included:
                result.append(
                    {
                        "field": cap.name,
                        "role": cap.metadata.get("role"),
                        "status": CapabilityStatus.TEMPORALLY_ILLEGAL.value,
                        "blocker": assessment.reason,
                        "availability_horizon": cap.availability_horizon,
                    }
                )
        return sorted(result, key=lambda x: x["field"])

    def uninvestigated_dimensions(self) -> List[Dict[str, Any]]:
        """Dimensions available on panel but not yet exercised in session."""
        exercised_fields = {
            c.name
            for c in self.registry.capabilities.values()
            if c.capability_id in self.registry.exercised_capability_ids
            and c.category
            in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value)
        }
        result: List[Dict[str, Any]] = []
        for cap in self.registry.unexplored_capabilities():
            if cap.category not in (
                CapabilityCategory.FIELD.value,
                CapabilityCategory.CATEGORICAL_DIMENSION.value,
            ):
                continue
            if not cap.panel_included:
                continue
            result.append(
                {
                    "field": cap.name,
                    "status": cap.status,
                    "role": cap.metadata.get("role"),
                    "previously_exercised": cap.name in exercised_fields,
                }
            )
        return sorted(result, key=lambda x: x["field"])

    def available_operations(self) -> List[Dict[str, Any]]:
        """Research operations available — tool descriptions only, no feature hints."""
        ops: List[Dict[str, Any]] = []
        for cap in self.registry.capabilities.values():
            if cap.category != CapabilityCategory.RESEARCH_TOOL.value:
                continue
            if cap.status != CapabilityStatus.AVAILABLE.value:
                continue
            ops.append(
                {
                    "tool_name": cap.name,
                    "description": cap.metadata.get("description"),
                    "operation_classes": cap.metadata.get("operation_classes"),
                    "input_schema": cap.metadata.get("input_schema"),
                    "leakage_classification": cap.metadata.get("leakage_classification"),
                }
            )
        return sorted(ops, key=lambda x: x["tool_name"])

    def blocked_with_reasons(self) -> List[Dict[str, Any]]:
        """Capabilities that cannot currently be used, and why."""
        blocked: List[Dict[str, Any]] = []
        for cap in self.registry.blocked_capabilities():
            blocked.append(
                {
                    "capability_id": cap.capability_id,
                    "name": cap.name,
                    "category": cap.category,
                    "status": cap.status,
                    "blocker": cap.blocker,
                    "exists_in_system": cap.exists_in_system,
                    "panel_included": cap.panel_included,
                    "source_provenance": cap.source_provenance,
                }
            )
        return sorted(blocked, key=lambda x: x["capability_id"])

    def constructible_views(self) -> List[Dict[str, Any]]:
        """
        Additional legal research views constructible from data already on panel.

        Neutral structural descriptions only.
        """
        views: List[Dict[str, Any]] = []
        preflight_cols = {
            c.name
            for c in self.registry.capabilities.values()
            if c.panel_included
            and c.status
            in (
                CapabilityStatus.AVAILABLE.value,
                CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
            )
            and c.category
            in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value)
        }
        for tool_cap in self.registry.available_capabilities():
            if tool_cap.category != CapabilityCategory.RESEARCH_TOOL.value:
                continue
            tool_name = tool_cap.name
            schema = tool_cap.metadata.get("input_schema") or {}
            views.append(
                {
                    "operation": tool_name,
                    "supports": tool_cap.metadata.get("operation_classes"),
                    "input_parameters": list(schema.keys()) if isinstance(schema, dict) else [],
                    "requires_panel_fields": "feature_column or partition_column per input_schema",
                    "constructible_when": "required fields present on panel and temporally legal",
                }
            )
        views.append(
            {
                "operation": "population_outcome_spec",
                "supports": ["population_outcome_transformation"],
                "input_parameters": list(ALLOWED_POPULATION_FIELDS | ALLOWED_OUTCOME_FIELDS)[:0],
                "constructible_when": f"fields from grammar {GRAMMAR_VERSION} on panel at legal horizon",
                "panel_fields_available": sorted(preflight_cols),
            }
        )
        return views

    def temporal_availability_map(self) -> Dict[str, Any]:
        """Field availability by information horizon — from FIELD_AVAILABILITY_HORIZON."""
        by_horizon: Dict[int, List[str]] = {0: [], 3: [], 5: [], 10: []}
        for field_name, avail in sorted(FIELD_AVAILABILITY_HORIZON.items()):
            for h in by_horizon:
                if h >= avail:
                    by_horizon[h].append(field_name)
        return {
            "version": LABORATORY_MAP_VERSION,
            "field_availability_horizon": dict(FIELD_AVAILABILITY_HORIZON),
            "legal_fields_by_horizon": {str(k): v for k, v in by_horizon.items()},
            "earning_learning_digests": earning_learning_digests(),
        }

    def discovery_audit(self) -> List[Dict[str, Any]]:
        """Capabilities/data that exist in system but are not research-accessible."""
        audit: List[Dict[str, Any]] = []
        for cap in self.registry.capabilities.values():
            if cap.category != CapabilityCategory.DATA_SOURCE.value:
                continue
            audit.append(
                {
                    "source": cap.name,
                    "exists": cap.exists_in_system,
                    "currently_research_accessible": cap.currently_research_accessible,
                    "panel_included": cap.panel_included,
                    "status": cap.status,
                    "blocker": cap.blocker,
                    "temporal_availability": "N/A_for_unwired_source",
                    "legality": "NOT_RESEARCH_ACCESSIBLE" if not cap.currently_research_accessible else "LEGAL",
                }
            )
        return audit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "observation_horizon": self.registry.observation_horizon,
            "legal_fields_at_current_horizon": self.legal_fields_at_horizon(
                self.registry.observation_horizon
            ),
            "uninvestigated_dimensions": self.uninvestigated_dimensions(),
            "available_operations": self.available_operations(),
            "blocked_with_reasons": self.blocked_with_reasons(),
            "constructible_views": self.constructible_views(),
            "temporal_availability_map": self.temporal_availability_map(),
            "discovery_audit": self.discovery_audit(),
            "exercised_count": len(self.registry.exercised_capability_ids),
            "available_count": len(self.registry.available_capabilities()),
            "unexplored_count": len(self.registry.unexplored_capabilities()),
        }


def ensure_session_capability_registry(
    graph: Any,
    panel: pd.DataFrame,
    tool_registry: Optional[ToolRegistry] = None,
) -> ResearchCapabilityRegistry:
    """Build or reload capability registry on session — does not affect planning."""
    if graph.session.research_capabilities:
        reg = ResearchCapabilityRegistry.from_dict(graph.session.research_capabilities)
        graph._capability_registry = reg  # noqa: SLF001 — lazy cache
        return reg
    reg = build_capability_registry(panel, tool_registry)
    graph.session.research_capabilities = reg.to_dict()
    graph._capability_registry = reg  # noqa: SLF001
    return reg


def record_experiment_capability_exercise(
    graph: Any,
    experiment_node_id: str,
    spec: Optional[ExperimentSpec],
) -> None:
    """Post-experiment capability exercise audit — no planner/allocator effect."""
    if not graph.session.research_capabilities:
        return
    reg = graph.get_capability_registry()
    node = graph.get_node(experiment_node_id)
    frame_id = ""
    if node.question_context:
        frame_id = node.question_context.frame_id or ""
    reg.record_exercise(spec, experiment_node_id=experiment_node_id, frame_id=frame_id)
    graph.persist_capability_registry()


def validate_no_hint_leakage(payload: Any) -> List[str]:
    """Return forbidden tokens found in serialized awareness payload."""
    text = str(payload).lower()
    return sorted(t for t in _FORBIDDEN_AWARENESS_TOKENS if t in text)
