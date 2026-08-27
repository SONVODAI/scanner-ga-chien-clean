"""
Phase 3H.3 — Operational Capability Awareness.

Aggregates authoritative laboratory sources into a queryable awareness state.
AWARENESS ≠ PREFERENCE ≠ ACTION — defines legal choice set only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.feature_registry import (
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
)
from modules.edge_research.research_capability_registry import (
    CAPABILITY_REGISTRY_VERSION,
    CapabilityCategory,
    CapabilityStatus,
    ResearchCapabilityRegistry,
    ResearchLaboratoryMap,
    build_capability_registry,
    ensure_session_capability_registry,
)
from modules.edge_research.research_exposure_governance import (
    EXPOSURE_GOVERNANCE_VERSION,
    ResearchExposureContract,
    build_research_exposure_contract,
    ensure_session_exposure_contract,
)
from modules.edge_research.research_feature_eligibility import (
    assess_feature_eligibility,
    classify_feature_role,
    field_availability_horizon,
)
from modules.edge_research.research_panel_exposure import PHASE_3H2B_FIRST_CONTROLLED_FIELD
from modules.edge_research.research_panel_preflight import (
    PANEL_PREFLIGHT_VERSION,
    PanelPreflightReport,
    adaptive_features_from_columns,
    build_panel_preflight,
)
from modules.edge_research.research_provenance_proof import PROVENANCE_PROOF_VERSION
from modules.edge_research.research_tools import TOOLBOX_VERSION, ToolRegistry, build_default_tool_registry

OPERATIONAL_AWARENESS_VERSION = "research_operational_awareness_v1"

_FORBIDDEN_AWARENESS_TOKENS: FrozenSet[str] = frozenset(
    {
        "promising",
        "best feature",
        "should investigate",
        "likely edge",
        "preferred tool",
        "high-potential",
        "recommended",
        "blind_benchmark",
        "bb01",
        "bb02",
        "bb03",
        "bb04",
        "bb05",
        "bb06",
        "bb07",
        "bb08",
        "bb09",
        "chatgpt",
        "predictive edge",
    }
)

# Neutral affordance descriptions — structural, not prescriptive.
_TOOL_AFFORDANCE_NEUTRAL: Dict[str, str] = {
    "partition_group_compare": "compares outcome structure across categorical partition groups",
    "adaptive_partition_compare": "compares regions using data-derived numeric partitions",
    "threshold_exploration": "investigates numeric threshold structure on a continuous feature",
    "threshold_neighborhood": "tests stability of outcomes near a threshold neighborhood",
    "categorical_adaptive_compare": "compares categorical regions with adaptive binning",
    "interaction_partition": "investigates conditional interaction structure across two dimensions",
    "date_decomposition": "inspects outcome distribution across trade dates",
    "symbol_decomposition": "inspects outcome distribution across symbols",
    "episode_decomposition": "inspects outcome distribution across market episodes",
    "market_conditioning": "conditions analysis on market context dimensions",
    "horizon_comparison": "compares outcome metrics across forward horizons",
    "sensitivity_analysis": "tests sensitivity of findings to specification choices",
    "neighborhood_stability": "tests robustness in feature neighborhoods (falsification)",
    "trajectory_partition_compare": "partitions by trajectory-derived dimensions",
}


class AwarenessBlockerClass(str, Enum):
    NOT_APPROVED = "NOT_APPROVED_FOR_EXPOSURE"
    NOT_WIRED = "NOT_WIRED_TO_PANEL"
    MISSING_FROM_PANEL = "MISSING_FROM_PANEL"
    TEMPORAL_ILLEGAL = "TEMPORAL_ILLEGAL"
    PROVENANCE_UNRESOLVED = "PROVENANCE_UNRESOLVED"
    CONTAMINATED = "KNOWLEDGE_CONTAMINATED"
    PRODUCTION_ONLY = "PRODUCTION_ONLY"
    UNSUPPORTED = "UNSUPPORTED_OPERATION"
    UNKNOWN = "UNKNOWN_BLOCKER"


@dataclass(frozen=True)
class CapabilityAwarenessEntry:
    capability_id: str
    name: str
    category: str
    known: bool
    available: bool
    considered: bool
    exercised: bool
    temporal_legal: bool
    blocker: str
    why_cannot_use: str
    affordance_description: str
    exposure_approved: Optional[bool] = None
    exposure_wired: Optional[bool] = None
    exposure_accessible: Optional[bool] = None
    availability_horizon: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "category": self.category,
            "known": self.known,
            "available": self.available,
            "considered": self.considered,
            "exercised": self.exercised,
            "temporal_legal": self.temporal_legal,
            "blocker": self.blocker,
            "why_cannot_use": self.why_cannot_use,
            "affordance_description": self.affordance_description,
            "exposure_approved": self.exposure_approved,
            "exposure_wired": self.exposure_wired,
            "exposure_accessible": self.exposure_accessible,
            "availability_horizon": self.availability_horizon,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CapabilityAwarenessEntry":
        return cls(
            capability_id=str(payload["capability_id"]),
            name=str(payload["name"]),
            category=str(payload["category"]),
            known=bool(payload.get("known", False)),
            available=bool(payload.get("available", False)),
            considered=bool(payload.get("considered", False)),
            exercised=bool(payload.get("exercised", False)),
            temporal_legal=bool(payload.get("temporal_legal", False)),
            blocker=str(payload.get("blocker") or ""),
            why_cannot_use=str(payload.get("why_cannot_use") or ""),
            affordance_description=str(payload.get("affordance_description") or ""),
            exposure_approved=payload.get("exposure_approved"),
            exposure_wired=payload.get("exposure_wired"),
            exposure_accessible=payload.get("exposure_accessible"),
            availability_horizon=payload.get("availability_horizon"),
        )


@dataclass
class OperationalAwareness:
    version: str = OPERATIONAL_AWARENESS_VERSION
    built_at: str = ""
    observation_horizon: int = 0
    frame_id: str = ""
    entries: Dict[str, CapabilityAwarenessEntry] = field(default_factory=dict)
    tool_affordances: List[Dict[str, Any]] = field(default_factory=list)
    constructible_operation_classes: Tuple[str, ...] = field(default_factory=tuple)
    audit_summary: Dict[str, Any] = field(default_factory=dict)
    source_versions: Dict[str, str] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "observation_horizon": self.observation_horizon,
            "frame_id": self.frame_id,
            "entries": {k: v.to_dict() for k, v in sorted(self.entries.items())},
            "tool_affordances": list(self.tool_affordances),
            "constructible_operation_classes": list(self.constructible_operation_classes),
            "audit_summary": dict(self.audit_summary),
            "source_versions": dict(self.source_versions),
            "audit_trail": list(self.audit_trail),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OperationalAwareness":
        entries = {
            k: CapabilityAwarenessEntry.from_dict(v)
            for k, v in (payload.get("entries") or {}).items()
        }
        return cls(
            version=str(payload.get("version", OPERATIONAL_AWARENESS_VERSION)),
            built_at=str(payload.get("built_at", "")),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            frame_id=str(payload.get("frame_id", "")),
            entries=entries,
            tool_affordances=list(payload.get("tool_affordances") or []),
            constructible_operation_classes=tuple(payload.get("constructible_operation_classes") or ()),
            audit_summary=dict(payload.get("audit_summary") or {}),
            source_versions=dict(payload.get("source_versions") or {}),
            audit_trail=list(payload.get("audit_trail") or []),
        )

    def entry_for_field(self, field_name: str) -> Optional[CapabilityAwarenessEntry]:
        for cat in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value):
            key = f"{cat}:{field_name}"
            if key in self.entries:
                return self.entries[key]
        for e in self.entries.values():
            if e.name == field_name and e.category in (
                CapabilityCategory.FIELD.value,
                CapabilityCategory.CATEGORICAL_DIMENSION.value,
            ):
                return e
        return None

    def constructible_explanatory_features(self) -> Tuple[str, ...]:
        """AVAILABLE + temporal legal numeric/rank explanatory fields on panel."""
        numeric = set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_RANK_LEVEL_FEATURES)
        feats: List[str] = []
        for e in self.entries.values():
            if e.category not in (
                CapabilityCategory.FIELD.value,
                CapabilityCategory.CATEGORICAL_DIMENSION.value,
            ):
                continue
            if not e.available or not e.temporal_legal:
                continue
            if e.name not in numeric:
                continue
            feats.append(e.name)
        return tuple(sorted(set(feats)))

    def available_fields(self) -> Tuple[str, ...]:
        return tuple(
            sorted(e.name for e in self.entries.values() if e.available and e.temporal_legal)
        )

    def known_but_unavailable(self) -> Tuple[str, ...]:
        return tuple(
            sorted(e.name for e in self.entries.values() if e.known and not e.available)
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tool_affordance(tool_name: str, registry_meta: Optional[Dict[str, Any]] = None) -> str:
    if registry_meta and registry_meta.get("description"):
        desc = str(registry_meta["description"]).strip()
        if desc and not any(t in desc.lower() for t in _FORBIDDEN_AWARENESS_TOKENS):
            return desc
    neutral = _TOOL_AFFORDANCE_NEUTRAL.get(tool_name, "")
    if neutral:
        return neutral
    ops = (registry_meta or {}).get("operation_classes") or ()
    if ops:
        return f"research operation supporting: {', '.join(ops)}"
    return "registered research tool operation"


def _exposure_overlay(
    field_name: str,
    contract: Optional[ResearchExposureContract],
) -> Tuple[Optional[bool], Optional[bool], Optional[bool], str]:
    if contract is None:
        return None, None, None, ""
    rec = contract.records.get(f"exposure:{field_name}")
    if rec is None:
        return None, None, None, ""
    blocker = ""
    if not rec.research_accessible_now:
        blocker = rec.blockers[0] if rec.blockers else "NOT_RESEARCH_ACCESSIBLE"
    return (
        rec.approved_for_exposure,
        rec.wired_to_panel,
        rec.research_accessible_now,
        blocker,
    )


def _field_available(
    cap_status: str,
    panel_included: bool,
    temporal_legal: bool,
    exposure_accessible: Optional[bool],
) -> bool:
    if exposure_accessible is False:
        return False
    if not panel_included:
        return False
    if not temporal_legal:
        return False
    return cap_status in {
        CapabilityStatus.AVAILABLE.value,
        CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
    }


def _why_cannot_use(
    *,
    known: bool,
    available: bool,
    cap_status: str,
    cap_blocker: str,
    exposure_blocker: str,
    temporal_legal: bool,
    panel_included: bool,
    exposure_approved: Optional[bool],
    exposure_wired: Optional[bool],
    category: str = "",
) -> str:
    if available:
        return ""
    if not known:
        if "PRODUCTION" in cap_blocker.upper() or "CAMERA" in cap_blocker.upper():
            return AwarenessBlockerClass.PRODUCTION_ONLY.value
        return "UNKNOWN_CAPABILITY"
    if exposure_approved is False:
        return AwarenessBlockerClass.NOT_APPROVED.value
    if exposure_wired is False and exposure_approved is not None:
        return AwarenessBlockerClass.NOT_WIRED.value
    if "NOT_WIRED" in cap_blocker.upper():
        return AwarenessBlockerClass.NOT_WIRED.value
    if not panel_included and category != CapabilityCategory.DATA_SOURCE.value:
        return AwarenessBlockerClass.MISSING_FROM_PANEL.value
    if not temporal_legal:
        return AwarenessBlockerClass.TEMPORAL_ILLEGAL.value
    if cap_status == CapabilityStatus.TEMPORALLY_ILLEGAL.value:
        return AwarenessBlockerClass.TEMPORAL_ILLEGAL.value
    if "CONTAMINATED" in cap_blocker.upper() or "KNOWLEDGE" in cap_blocker.upper():
        return AwarenessBlockerClass.CONTAMINATED.value
    if "PRODUCTION" in cap_blocker.upper() or "CAMERA" in cap_blocker.upper():
        return AwarenessBlockerClass.PRODUCTION_ONLY.value
    if exposure_blocker:
        if "CONTAMINATED" in exposure_blocker.upper():
            return AwarenessBlockerClass.CONTAMINATED.value
        if "PRODUCTION" in exposure_blocker.upper():
            return AwarenessBlockerClass.PRODUCTION_ONLY.value
        return exposure_blocker
    if cap_blocker:
        return cap_blocker
    if category == CapabilityCategory.DATA_SOURCE.value:
        return AwarenessBlockerClass.NOT_WIRED.value
    return AwarenessBlockerClass.UNKNOWN.value


def build_operational_awareness(
    panel: pd.DataFrame,
    registry: ResearchCapabilityRegistry,
    *,
    exposure_contract: Optional[ResearchExposureContract] = None,
    preflight: Optional[PanelPreflightReport] = None,
    observation_horizon: int = 0,
    frame_id: str = "",
    tool_registry: Optional[ToolRegistry] = None,
) -> OperationalAwareness:
    """Synthesize awareness from authoritative sources — no parallel truth system."""
    pre = preflight or build_panel_preflight(panel)
    contract = exposure_contract
    lab = registry.laboratory_map()
    tools = tool_registry or build_default_tool_registry()

    entries: Dict[str, CapabilityAwarenessEntry] = {}
    exercised_ids = registry.exercised_capability_ids

    for cap_id, cap in registry.capabilities.items():
        horizon = cap.availability_horizon if cap.availability_horizon is not None else field_availability_horizon(cap.name)
        temporal_legal = True
        if cap.category in (
            CapabilityCategory.FIELD.value,
            CapabilityCategory.CATEGORICAL_DIMENSION.value,
            CapabilityCategory.OUTCOME.value,
        ):
            assess = assess_feature_eligibility(cap.name, observation_horizon=observation_horizon)
            temporal_legal = bool(assess.eligible_at_observation)

        exp_approved, exp_wired, exp_accessible, exp_blocker = _exposure_overlay(cap.name, contract)

        available = _field_available(
            cap.status,
            cap.panel_included,
            temporal_legal,
            exp_accessible if cap.category in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value) else None,
        )
        if cap.category == CapabilityCategory.RESEARCH_TOOL.value:
            available = cap.status == CapabilityStatus.AVAILABLE.value

        known = cap.exists_in_system or cap.status != CapabilityStatus.UNAVAILABLE.value
        exercised = cap_id in exercised_ids
        if contract:
            exp_rec = contract.records.get(f"exposure:{cap.name}")
            if exp_rec and exp_rec.exercised_by_researcher:
                exercised = True

        why = _why_cannot_use(
            known=known,
            available=available,
            cap_status=cap.status,
            cap_blocker=cap.blocker,
            exposure_blocker=exp_blocker,
            temporal_legal=temporal_legal,
            panel_included=cap.panel_included,
            exposure_approved=exp_approved,
            exposure_wired=exp_wired,
            category=cap.category,
        )

        affordance = ""
        if cap.category == CapabilityCategory.RESEARCH_TOOL.value:
            affordance = _tool_affordance(cap.name, cap.metadata)
        elif cap.category in (CapabilityCategory.FIELD.value, CapabilityCategory.CATEGORICAL_DIMENSION.value):
            role = cap.metadata.get("role") or classify_feature_role(cap.name)
            if hasattr(role, "value"):
                role = role.value
            affordance = f"observable {role} dimension on research panel"

        entries[cap_id] = CapabilityAwarenessEntry(
            capability_id=cap_id,
            name=cap.name,
            category=cap.category,
            known=known,
            available=available,
            considered=False,
            exercised=exercised,
            temporal_legal=temporal_legal,
            blocker=cap.blocker if not available else "",
            why_cannot_use=why,
            affordance_description=affordance,
            exposure_approved=exp_approved,
            exposure_wired=exp_wired,
            exposure_accessible=exp_accessible,
            availability_horizon=horizon,
        )

    tool_affordances: List[Dict[str, Any]] = []
    op_classes: set[str] = set()
    for cap in registry.capabilities.values():
        if cap.category != CapabilityCategory.RESEARCH_TOOL.value:
            continue
        if cap.status != CapabilityStatus.AVAILABLE.value:
            continue
        desc = _tool_affordance(cap.name, cap.metadata)
        ops = tuple(cap.metadata.get("operation_classes") or ())
        op_classes.update(str(o) for o in ops)
        tool_affordances.append(
            {
                "tool_name": cap.name,
                "affordance": desc,
                "operation_classes": list(ops),
                "available": True,
            }
        )

    awareness = OperationalAwareness(
        built_at=_utc_now(),
        observation_horizon=observation_horizon,
        frame_id=frame_id,
        entries=entries,
        tool_affordances=sorted(tool_affordances, key=lambda x: x["tool_name"]),
        constructible_operation_classes=tuple(sorted(op_classes)),
        source_versions={
            "capability_registry": registry.version,
            "panel_preflight": pre.version,
            "exposure_governance": contract.version if contract else "",
            "toolbox": TOOLBOX_VERSION,
            "provenance_proof": PROVENANCE_PROOF_VERSION,
        },
        audit_summary=_build_audit_summary(entries),
    )
    return awareness


def _build_audit_summary(entries: Dict[str, CapabilityAwarenessEntry]) -> Dict[str, Any]:
    known = [e for e in entries.values() if e.known]
    available = [e for e in entries.values() if e.available]
    exercised = [e for e in entries.values() if e.exercised]
    unavailable = [e for e in entries.values() if e.known and not e.available]
    unexercised_avail = [e for e in entries.values() if e.available and not e.exercised]
    blockers: Dict[str, int] = {}
    for e in unavailable:
        reason = e.why_cannot_use or "UNKNOWN"
        blockers[reason] = blockers.get(reason, 0) + 1
    return {
        "known_capabilities_count": len(known),
        "currently_available_count": len(available),
        "unavailable_blocked_count": len(unavailable),
        "exercised_count": len(exercised),
        "available_but_unexercised_count": len(unexercised_avail),
        "blockers_by_reason": blockers,
    }


def partition_features_for_construction(
    panel_columns: Optional[Sequence[str]],
    operational_awareness: Optional[OperationalAwareness] = None,
) -> Tuple[str, ...]:
    """
    Legal explanatory features for candidate construction.

    When awareness is provided, uses AVAILABLE constructible set.
    Otherwise falls back to legacy panel-column helper (unchanged path).
    """
    if operational_awareness is not None:
        return operational_awareness.constructible_explanatory_features()
    if panel_columns:
        return adaptive_features_from_columns(panel_columns)
    return ()


def mark_awareness_consulted(
    awareness: OperationalAwareness,
    *,
    event: str = "AWARENESS_CONSULTED",
    constructible_features: Optional[Sequence[str]] = None,
) -> OperationalAwareness:
    """Record structured consultation audit — no chain-of-thought."""
    trail = list(awareness.audit_trail)
    trail.append(
        {
            "event": event,
            "timestamp": _utc_now(),
            "observation_horizon": awareness.observation_horizon,
            "constructible_features": list(constructible_features or ()),
        }
    )
    awareness.audit_trail = trail
    return awareness


def mark_awareness_considered_from_candidates(
    awareness: OperationalAwareness,
    candidates: Sequence[Any],
) -> OperationalAwareness:
    """Mark CONSIDERED for capabilities referenced by generated candidates."""
    considered_fields: set[str] = set()
    considered_tools: set[str] = set()
    for c in candidates:
        if getattr(c, "blocked", False):
            continue
        tool = getattr(c, "tool_name", "") or ""
        if tool:
            considered_tools.add(str(tool))
        spec = getattr(c, "draft_spec", None)
        if spec and getattr(spec, "inputs", None):
            for key in ("feature_column", "partition_column"):
                val = spec.inputs.get(key)
                if val:
                    considered_fields.add(str(val))

    new_entries: Dict[str, CapabilityAwarenessEntry] = {}
    for cap_id, entry in awareness.entries.items():
        considered = entry.considered
        if entry.name in considered_fields or entry.name in considered_tools:
            considered = True
        new_entries[cap_id] = replace(entry, considered=considered)

    trail = list(awareness.audit_trail)
    trail.append(
        {
            "event": "AWARENESS_CONSIDERED_UPDATED",
            "timestamp": _utc_now(),
            "considered_fields": sorted(considered_fields),
            "considered_tools": sorted(considered_tools),
        }
    )
    awareness.entries = new_entries
    awareness.audit_trail = trail
    return awareness


def filter_candidates_to_awareness_legal_set(
    candidates: Sequence[Any],
    awareness: OperationalAwareness,
) -> Tuple[Any, ...]:
    """
    Remove candidates that reference unavailable/non-constructible capabilities.
    Does not alter scores — only legal choice set filtering.
    """
    constructible = set(awareness.constructible_explanatory_features())
    partition_dims = set(
        e.name
        for e in awareness.entries.values()
        if e.available
        and e.category == CapabilityCategory.CATEGORICAL_DIMENSION.value
    )
    out: List[Any] = []
    for c in candidates:
        intent = getattr(c, "intent", "")
        if intent in ("STOP", "STOP_SESSION", "ABANDON") or not getattr(c, "draft_spec", None):
            out.append(c)
            continue
        spec = c.draft_spec
        inputs = dict(getattr(spec, "inputs", None) or {})
        feat = inputs.get("feature_column")
        part = inputs.get("partition_column")
        legal = True
        if feat and feat not in constructible and feat not in partition_dims:
            if awareness.entry_for_field(str(feat)) is not None:
                legal = False
            elif str(feat) not in ("feature_x", "feature_y", "feat_alpha", "partition_group"):
                entry = awareness.entry_for_field(str(feat))
                if entry and not entry.available:
                    legal = False
        if part and part not in partition_dims and part not in constructible:
            entry = awareness.entry_for_field(str(part))
            if entry and not entry.available:
                legal = False
        if legal:
            out.append(c)
    return tuple(out)


def validate_no_recommendation_language(payload: Any) -> List[str]:
    text = str(payload).lower()
    return sorted(t for t in _FORBIDDEN_AWARENESS_TOKENS if t in text)


def ensure_session_operational_awareness(
    graph: Any,
    panel: pd.DataFrame,
    tool_registry: Optional[ToolRegistry] = None,
) -> OperationalAwareness:
    if graph.session.research_operational_awareness:
        awareness = OperationalAwareness.from_dict(graph.session.research_operational_awareness)
        graph._operational_awareness = awareness  # noqa: SLF001
        return awareness

    reg = ensure_session_capability_registry(graph, panel, tool_registry)
    contract = ensure_session_exposure_contract(graph)
    obs_horizon = int(getattr(reg, "observation_horizon", 0) or 0)
    awareness = build_operational_awareness(
        panel,
        reg,
        exposure_contract=contract,
        observation_horizon=obs_horizon,
        tool_registry=tool_registry,
    )
    graph.session.research_operational_awareness = awareness.to_dict()
    graph._operational_awareness = awareness  # noqa: SLF001
    return awareness


def persist_operational_awareness(graph: Any) -> None:
    if getattr(graph, "_operational_awareness", None) is not None:
        graph.session.research_operational_awareness = graph._operational_awareness.to_dict()


def rebuild_awareness_at_horizon(
    graph: Any,
    panel: pd.DataFrame,
    *,
    observation_horizon: int,
    tool_registry: Optional[ToolRegistry] = None,
) -> OperationalAwareness:
    """Horizon-dynamic awareness refresh."""
    reg = graph.get_capability_registry() if hasattr(graph, "get_capability_registry") else build_capability_registry(panel, tool_registry)
    contract = graph.get_exposure_contract() if hasattr(graph, "get_exposure_contract") else build_research_exposure_contract(panel)
    awareness = build_operational_awareness(
        panel,
        reg,
        exposure_contract=contract,
        observation_horizon=observation_horizon,
        tool_registry=tool_registry,
    )
    graph.session.research_operational_awareness = awareness.to_dict()
    graph._operational_awareness = awareness  # noqa: SLF001
    return awareness
